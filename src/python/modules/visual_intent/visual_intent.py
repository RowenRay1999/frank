"""
Frank 视觉意图识别 (Phase 3)

基于 MediaPipe Face Mesh (468 landmarks) + Hands (21 landmarks):
- 注视检测: 视线向量与摄像头夹角
- 点头/摇头: 鼻尖关键点轨迹模式匹配
- 挥手: 手掌横向移动
"""

import logging
import time
from collections import deque
from typing import Any, Callable

import numpy as np

logger = logging.getLogger('frank.visual')

# MediaPipe lazy import
_mp_face_mesh = None
_mp_hands = None


class VisualIntentDetector:
    """视觉意图检测器"""

    # 关键点索引 (MediaPipe Face Mesh)
    NOSE_TIP = 1
    LEFT_EYE_OUTER = 33
    LEFT_EYE_INNER = 133
    RIGHT_EYE_OUTER = 362
    RIGHT_EYE_INNER = 263
    LEFT_IRIS = 468
    RIGHT_IRIS = 473

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.gaze_angle_threshold = self.config.get('gaze_threshold', 10.0)  # 度
        self.gaze_duration = self.config.get('gaze_duration', 2.0)  # 秒
        self.nod_threshold = self.config.get('nod_threshold', 0.015)  # Y 轴位移阈值(归一化)
        self.shake_threshold = self.config.get('shake_threshold', 0.015)

        self._face_mesh = None
        self._hands = None
        self._ready = False

        # 轨迹缓冲
        self._nose_trail: deque[tuple[float, float, float]] = deque(maxlen=60)  # 1s @ 30fps
        self._gaze_start: float | None = None
        self._palm_trail: deque[tuple[float, float]] = deque(maxlen=30)  # 0.5s

        # 回调
        self._on_gaze_detected: Callable | None = None
        self._on_nod: Callable | None = None
        self._on_shake: Callable | None = None
        self._on_wave: Callable | None = None

    def set_on_gaze_detected(self, cb: Callable): self._on_gaze_detected = cb
    def set_on_nod(self, cb: Callable): self._on_nod = cb
    def set_on_shake(self, cb: Callable): self._on_shake = cb
    def set_on_wave(self, cb: Callable): self._on_wave = cb

    @property
    def is_ready(self) -> bool:
        return self._ready

    def initialize(self):
        """初始化 MediaPipe Face Mesh + Hands"""
        try:
            global _mp_face_mesh, _mp_hands
            if _mp_face_mesh is None:
                import mediapipe as mp
                _mp_face_mesh = mp.solutions.face_mesh
                _mp_hands = mp.solutions.hands

            self._face_mesh = _mp_face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                refine_landmarks=True,  # 启用虹膜关键点
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._hands = _mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._ready = True
            logger.info('Visual intent detector initialized (Face Mesh + Hands)')
        except Exception as e:
            logger.warning(f'Visual intent detector init failed: {e}')
            self._ready = False

    def process_frame(self, frame_rgb: np.ndarray, frame_w: int, frame_h: int) -> dict:
        """处理一帧，返回检测到的视觉意图"""
        results = {'gaze': False, 'nod': False, 'shake': False, 'wave': False}

        if not self._ready:
            return results

        try:
            # Face Mesh
            mesh_results = self._face_mesh.process(frame_rgb)
            if mesh_results.multi_face_landmarks:
                landmarks = mesh_results.multi_face_landmarks[0]

                # 更新鼻尖轨迹
                nose = landmarks.landmark[self.NOSE_TIP]
                self._nose_trail.append((nose.x, nose.y, nose.z))

                # 注视检测
                if self._detect_gaze(landmarks, frame_w, frame_h):
                    results['gaze'] = True

                # 点头/摇头
                if len(self._nose_trail) >= 30:
                    if self._detect_nod():
                        results['nod'] = True
                    if self._detect_shake():
                        results['shake'] = True

            # Hands
            hands_results = self._hands.process(frame_rgb)
            if hands_results.multi_hand_landmarks:
                for hand_landmarks in hands_results.multi_hand_landmarks:
                    palm_x = hand_landmarks.landmark[9].x  # 手腕
                    self._palm_trail.append((palm_x, time.time()))
                    if self._detect_wave():
                        results['wave'] = True
                        break

        except Exception as e:
            logger.error(f'Visual intent process error: {e}')

        return results

    def _detect_gaze(self, landmarks, frame_w: int, frame_h: int) -> bool:
        """检测注视：视线与摄像头夹角 < threshold 持续 > duration"""
        # 计算左右眼中心
        left_eye = np.array([
            (landmarks.landmark[self.LEFT_EYE_OUTER].x + landmarks.landmark[self.LEFT_EYE_INNER].x) / 2,
            (landmarks.landmark[self.LEFT_EYE_OUTER].y + landmarks.landmark[self.LEFT_EYE_INNER].y) / 2,
        ])
        right_eye = np.array([
            (landmarks.landmark[self.RIGHT_EYE_OUTER].x + landmarks.landmark[self.RIGHT_EYE_INNER].x) / 2,
            (landmarks.landmark[self.RIGHT_EYE_OUTER].y + landmarks.landmark[self.RIGHT_EYE_INNER].y) / 2,
        ])

        # 虹膜位置（相对偏移）
        left_iris = np.array([
            landmarks.landmark[self.LEFT_IRIS].x - left_eye[0],
            landmarks.landmark[self.LEFT_IRIS].y - left_eye[1],
        ])
        right_iris = np.array([
            landmarks.landmark[self.RIGHT_IRIS].x - right_eye[0],
            landmarks.landmark[self.RIGHT_IRIS].y - right_eye[1],
        ])

        # 检查虹膜是否接近中心（正视前方时虹膜偏移 < 0.02）
        iris_offset = (np.linalg.norm(left_iris) + np.linalg.norm(right_iris)) / 2

        is_gazing = iris_offset < 0.025  # 归一化坐标中的阈值

        now = time.time()
        if is_gazing:
            if self._gaze_start is None:
                self._gaze_start = now
            elif now - self._gaze_start >= self.gaze_duration:
                if self._on_gaze_detected:
                    self._on_gaze_detected({'duration': now - self._gaze_start})
                self._gaze_start = None  # 重置避免重复触发
                return True
        else:
            self._gaze_start = None

        return False

    def _detect_nod(self) -> bool:
        """检测点头：Y 轴先上后下模式"""
        if len(self._nose_trail) < 30:
            return False

        trail = list(self._nose_trail)[-30:]  # ~1s
        y_vals = [p[1] for p in trail]

        # 找 Y 轴最小值（最高点）和最大值（最低点）
        min_y = min(y_vals)
        max_y = max(y_vals)
        amplitude = max_y - min_y

        if amplitude > self.nod_threshold:
            # 找最高点和最低点的时序：先高后低 = 点头
            min_idx = y_vals.index(min_y)
            max_idx = y_vals.index(max_y)
            if min_idx < max_idx:  # 先上(小Y)后下(大Y)
                if self._on_nod:
                    self._on_nod({'confidence': min(1.0, amplitude / 0.03)})
                self._nose_trail.clear()
                return True

        return False

    def _detect_shake(self) -> bool:
        """检测摇头：X 轴左右摆动模式"""
        if len(self._nose_trail) < 30:
            return False

        trail = list(self._nose_trail)[-30:]
        x_vals = [p[0] for p in trail]

        min_x = min(x_vals)
        max_x = max(x_vals)
        amplitude = max_x - min_x

        if amplitude > self.shake_threshold:
            mid = len(x_vals) // 2
            first_half = x_vals[:mid]
            second_half = x_vals[mid:]
            first_mean = sum(first_half) / len(first_half)
            second_mean = sum(second_half) / len(second_half)

            # 左右摆动：一侧均值 > 另一侧
            if abs(first_mean - second_mean) > self.shake_threshold * 0.5:
                if self._on_shake:
                    self._on_shake({'confidence': min(1.0, amplitude / 0.03)})
                self._nose_trail.clear()
                return True

        return False

    def _detect_wave(self) -> bool:
        """检测挥手：手掌 X 轴快速移动"""
        if len(self._palm_trail) < 5:
            return False

        recent = list(self._palm_trail)[-15:]  # ~0.5s
        if len(recent) < 5:
            return False

        x_vals = [p[0] for p in recent]
        t_vals = [p[1] for p in recent]
        movement = max(x_vals) - min(x_vals)
        duration = t_vals[-1] - t_vals[0]

        if duration > 0 and movement / duration > 0.3:  # 快速横向移动
            if self._on_wave:
                self._on_wave({'confidence': min(1.0, movement / 0.1)})
            self._palm_trail.clear()
            return True

        return False

    def close(self):
        """清理资源"""
        if self._face_mesh:
            self._face_mesh.close()
            self._face_mesh = None
        if self._hands:
            self._hands.close()
            self._hands = None
        self._ready = False
