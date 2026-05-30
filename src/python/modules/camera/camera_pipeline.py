"""
Frank 摄像头采集管线

负责：
1. 摄像头设备枚举
2. OpenCV 帧捕获（自适应帧率）
3. InsightFace buffalo_l 人脸检测+识别（主）/ MediaPipe Face Detector（回退）
4. 检测事件推送（含 512-dim embedding，质量达标时）

Phase 2: InsightFace 集成，提供人脸 embedding 用于身份识别
"""

import asyncio
import logging
import os
import time
from typing import Any, Callable

import cv2
import numpy as np

logger = logging.getLogger('frank.camera')

# MediaPipe（回退方案）— 延迟导入，避免依赖缺失时模块导入崩溃
mp_face_detection = None

# InsightFace 延迟导入
_insightface = None

FACE_EMBEDDING_DIM = 512
MIN_FACE_SIZE_PX = 80
MAX_FACE_ANGLE_DEG = 30


class CameraPipeline:
    """摄像头采集与人脸检测管线（Phase 2: InsightFace 主 + MediaPipe 回退）"""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

        # 配置参数
        self.device_id = self.config.get('device_id', 0)
        self.width = self.config.get('width', 640)
        self.height = self.config.get('height', 480)
        self.fps_idle = self.config.get('fps_idle', 1)
        self.fps_aware = self.config.get('fps_aware', 5)
        self.fps_active = self.config.get('fps_active', 10)
        self.detection_confidence = self.config.get('detection_confidence', 0.7)

        # 内部状态
        self._cap: cv2.VideoCapture | None = None
        self._face_detector = None  # MediaPipe fallback
        self._insightface_ready = False  # InsightFace 是否就绪
        self._insightface_model = None
        self._running = False
        self._capture_task: asyncio.Task | None = None
        self._faces_last_frame = 0
        self._current_fps = self.fps_idle
        self._frame_interval = 1.0 / self.fps_idle
        self._init_task: asyncio.Task | None = None
        self._no_face_frames = 0  # WR-06: debounce face_lost
        self._last_error_time: dict[str, float] = {}  # WR-07: error debounce

        # 回调
        self._on_face_detected: Callable | None = None
        self._on_face_lost: Callable | None = None
        self._on_face_embedding: Callable | None = None  # Phase 2: embedding 专用回调
        self._on_pose_frame: Callable | None = None       # Phase 5: 姿态帧回调
        self._on_error: Callable | None = None
        self._state_provider: Callable | None = None

    # ─── 回调设置 ───────────────────────────────────────

    def set_on_face_detected(self, callback: Callable):
        self._on_face_detected = callback

    def set_on_face_lost(self, callback: Callable):
        self._on_face_lost = callback

    def set_on_face_embedding(self, callback: Callable):
        """Phase 2: embedding 单独回调（传给融合引擎）"""
        self._on_face_embedding = callback

    def set_on_pose_frame(self, callback: Callable):
        """Phase 5: 姿态帧回调（传给 PoseModule）"""
        self._on_pose_frame = callback

    def set_on_error(self, callback: Callable):
        self._on_error = callback

    def set_state_provider(self, provider: Callable):
        self._state_provider = provider

    @property
    def is_insightface_ready(self) -> bool:
        return self._insightface_ready

    # ─── InsightFace 异步加载 ──────────────────────────

    async def _init_insightface(self):
        """异步加载 InsightFace 模型（不阻塞主采集循环）"""
        try:
            global _insightface
            if _insightface is None:
                logger.info('Loading InsightFace buffalo_l model...')
                import insightface
                _insightface = insightface
            # 创建模型实例（自动下载到 data/models/）
            model_root = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'data', 'models')
            os.makedirs(model_root, exist_ok=True)
            self._insightface_model = _insightface.app.FaceAnalysis(
                name='buffalo_l',
                root=model_root,
                providers=['CPUExecutionProvider'],
            )
            self._insightface_model.prepare(ctx_id=-1, det_size=(self.width, self.height))
            self._insightface_ready = True
            logger.info('InsightFace buffalo_l ready (detection + recognition)')
        except Exception as e:
            logger.warning(f'InsightFace init failed, falling back to MediaPipe only: {e}')
            self._insightface_ready = False
            self._insightface_model = None

    # ─── 设备枚举 ───────────────────────────────────────

    @staticmethod
    def enumerate_devices() -> list[dict[str, Any]]:
        """枚举可用摄像头设备"""
        devices = []
        for i in range(5):  # 扫描前 5 个设备
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                devices.append({
                    'id': i,
                    'name': f'Camera {i}',
                    'resolutions': [
                        {'width': 640, 'height': 480, 'fps': 30},
                        {'width': 1280, 'height': 720, 'fps': 30},
                    ],
                })
                cap.release()
        return devices

    # ─── 启动/停止 ───────────────────────────────────────

    async def start(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """启动摄像头采集"""
        if params:
            self.device_id = params.get('device_id', self.device_id)
            self.width = params.get('width', self.width)
            self.height = params.get('height', self.height)

        # 打开摄像头
        self._cap = cv2.VideoCapture(self.device_id, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            await self._emit_error('CAM_NOT_FOUND',
                f'无法打开摄像头 (device_id={self.device_id})，请确认摄像头已连接并启用',
                True,
                '请检查摄像头连接，或在设置中选择其他摄像头设备')
            raise RuntimeError(f'Camera device {self.device_id} not found')

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, 30)

        # 初始化 MediaPipe（回退，延迟导入避免崩溃）
        try:
            import mediapipe as mp
            global mp_face_detection
            mp_face_detection = mp.solutions.face_detection
            self._face_detector = mp_face_detection.FaceDetection(
                model_selection=0,
                min_detection_confidence=self.detection_confidence,
            )
        except Exception as e:
            logger.warning(f'MediaPipe init failed, face detection degraded: {e}')
            self._face_detector = None

        # 异步加载 InsightFace（不阻塞启动）
        self._init_task = asyncio.create_task(self._init_insightface())

        # 启动采集循环
        self._running = True
        self._capture_task = asyncio.create_task(self._capture_loop())

        logger.info(f'Camera started: device={self.device_id}, {self.width}x{self.height}')
        return {'device_id': self.device_id, 'width': self.width, 'height': self.height}

    async def stop(self):
        """停止摄像头采集"""
        self._running = False
        if self._capture_task:
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass
            self._capture_task = None

        if self._face_detector:
            self._face_detector.close()
            self._face_detector = None

        if self._cap:
            self._cap.release()
            self._cap = None

        logger.info('Camera stopped')

    async def configure(self, params: dict[str, Any]) -> dict[str, Any]:
        """动态更新配置"""
        if 'device_id' in params:
            self.device_id = params['device_id']
        if 'width' in params:
            self.width = params['width']
        if 'height' in params:
            self.height = params['height']
        if 'detection_confidence' in params:
            self.detection_confidence = params['detection_confidence']

        # 如果正在运行，重启以应用新配置
        if self._running:
            await self.stop()
            await self.start()

        return {'device_id': self.device_id, 'width': self.width, 'height': self.height}

    # ─── 采集循环 ───────────────────────────────────────

    async def _capture_loop(self):
        """主采集循环"""
        last_frame_time = 0

        while self._running:
            try:
                # 根据当前状态调整帧率
                self._update_fps()

                now = time.time()
                if now - last_frame_time < self._frame_interval:
                    await asyncio.sleep(0.01)
                    continue
                last_frame_time = now

                # 读取帧
                if not self._cap or not self._cap.isOpened():
                    now = time.time()
                    if now - self._last_error_time.get('CAM_DISCONNECTED', 0) > 5:
                        await self._emit_error('CAM_DISCONNECTED',
                            '摄像头连接中断，正在尝试恢复...', True,
                            '请检查摄像头连接，系统将自动尝试重新连接')
                        self._last_error_time['CAM_DISCONNECTED'] = now
                    await asyncio.sleep(2)
                    continue

                ret, frame = self._cap.read()
                if not ret or frame is None:
                    continue

                # RGB 转换
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # 人脸检测（InsightFace 主 / MediaPipe 回退）
                faces = []
                if self._insightface_ready and self._insightface_model:
                    faces = self._detect_with_insightface(frame_rgb)
                elif self._face_detector:
                    faces = self._detect_with_mediapipe(frame_rgb)

                # 人脸数变化事件
                current_count = len(faces)
                if current_count > 0 and self._faces_last_frame == 0:
                    await self._emit_face_detected(faces)
                elif current_count == 0 and self._faces_last_frame > 0:
                    self._no_face_frames += 1
                    if self._no_face_frames >= 3:  # debounce: 3 consecutive frames
                        await self._emit_face_lost()
                        self._no_face_frames = 0
                elif current_count > 0:
                    self._no_face_frames = 0

                self._faces_last_frame = current_count

                # Phase 5: 姿态帧回调（在 Auth/Chat 状态下）
                if self._on_pose_frame:
                    try:
                        if asyncio.iscoroutinefunction(self._on_pose_frame):
                            await self._on_pose_frame(frame_rgb, self.width, self.height)
                        else:
                            self._on_pose_frame(frame_rgb, self.width, self.height)
                    except Exception as e:
                        logger.debug(f'Pose frame callback error: {e}')

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f'Capture loop error: {e}')
                await asyncio.sleep(0.5)

    # ─── InsightFace 检测+识别 ──────────────────────────

    def _detect_with_insightface(self, frame_rgb: np.ndarray) -> list[dict]:
        """InsightFace 检测+识别：输出 bbox + embedding"""
        faces = []
        try:
            results = self._insightface_model.get(frame_rgb)
            for face in results:
                bbox = face.bbox.astype(float)
                h, w = frame_rgb.shape[:2]
                face_info = {
                    'bbox': {
                        'x': bbox[0] / w,
                        'y': bbox[1] / h,
                        'width': (bbox[2] - bbox[0]) / w,
                        'height': (bbox[3] - bbox[1]) / h,
                    },
                    'confidence': float(face.det_score),
                    'landmarks': [],
                }

                # 质量门控 + embedding 提取
                if self._check_embedding_quality(face_info, w, h):
                    embedding = face.normed_embedding  # InsightFace 已 L2 归一化
                    face_info['embedding'] = embedding.astype(np.float32).tolist()

                faces.append(face_info)
        except Exception as e:
            logger.error(f'InsightFace detection error: {e}')
        return faces

    def _detect_with_mediapipe(self, frame_rgb: np.ndarray) -> list[dict]:
        """MediaPipe 回退检测（无 embedding）"""
        if self._face_detector is None:
            return []
        faces = []
        try:
            results = self._face_detector.process(frame_rgb)
            if results.detections:
                for detection in results.detections:
                    bbox = detection.location_data.relative_bounding_box
                    faces.append({
                        'bbox': {
                            'x': bbox.xmin,
                            'y': bbox.ymin,
                            'width': bbox.width,
                            'height': bbox.height,
                        },
                        'confidence': detection.score[0],
                        'landmarks': [
                            {'x': lm.x, 'y': lm.y, 'z': lm.z}
                            for lm in (detection.location_data.relative_keypoints or [])
                        ],
                    })
        except Exception as e:
            logger.error(f'MediaPipe detection error: {e}')
        return faces

    def _check_embedding_quality(self, face_info: dict, frame_w: int, frame_h: int) -> bool:
        """检查人脸质量是否满足 embedding 提取条件"""
        bbox = face_info['bbox']
        face_w = bbox['width'] * frame_w
        face_h = bbox['height'] * frame_h

        # 大小检查
        if face_w < MIN_FACE_SIZE_PX or face_h < MIN_FACE_SIZE_PX:
            return False

        # 置信度检查
        if face_info['confidence'] < self.detection_confidence:
            return False

        return True

    # ─── 帧率控制 ───────────────────────────────────────

    def _update_fps(self):
        """根据状态机状态调整帧率"""
        if self._state_provider:
            try:
                state_info = self._state_provider()
                state = state_info.get('state', 'Idle')
            except Exception:
                state = 'Idle'
        else:
            state = 'Idle'

        match state:
            case 'Idle':
                self._current_fps = self.fps_idle
            case 'Aware':
                self._current_fps = self.fps_aware
            case 'Auth' | 'Chat':
                self._current_fps = self.fps_active

        self._frame_interval = 1.0 / self._current_fps if self._current_fps > 0 else 1.0

    # ─── 事件发送 ───────────────────────────────────────

    async def _emit_face_detected(self, faces: list[dict]):
        payload = {'faces': faces, 'count': len(faces)}

        # 主检测事件
        if self._on_face_detected:
            if asyncio.iscoroutinefunction(self._on_face_detected):
                await self._on_face_detected(payload)
            else:
                self._on_face_detected(payload)

        # Phase 2: embedding 单独路由到融合引擎
        if self._on_face_embedding and self._insightface_ready:
            for face in faces:
                if 'embedding' in face:
                    emb = np.array(face['embedding'], dtype=np.float32)
                    if asyncio.iscoroutinefunction(self._on_face_embedding):
                        await self._on_face_embedding(emb, face['confidence'])
                    else:
                        self._on_face_embedding(emb, face['confidence'])

    async def _emit_face_lost(self):
        if self._on_face_lost:
            payload = {}
            if asyncio.iscoroutinefunction(self._on_face_lost):
                await self._on_face_lost(payload)
            else:
                self._on_face_lost(payload)

    async def _emit_error(self, code: str, message: str, recoverable: bool, suggestion: str):
        payload = {'code': code, 'message': message, 'recoverable': recoverable, 'suggestion': suggestion}
        if self._on_error:
            if asyncio.iscoroutinefunction(self._on_error):
                await self._on_error(payload)
            else:
                self._on_error(payload)

    def __repr__(self) -> str:
        return f'CameraPipeline(device={self.device_id}, running={self._running}, fps={self._current_fps})'
