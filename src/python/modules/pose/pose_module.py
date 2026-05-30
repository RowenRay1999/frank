"""
Frank 姿态/手势识别模块 (Phase 5)

实现设计文档 FRANK-SPEC-005 第 12 节预留的 PoseModule 接口:
- Body-level: MediaPipe Pose (BlazePose) 提取 33 关节点
- Hand-level: MediaPipe Hands 提取 21 关节点
- 手势动作槽 pub-sub 系统
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np

from .gesture_classifier import GestureClassifier

logger = logging.getLogger('frank.pose')

# MediaPipe lazy import
_mp_pose = None
_mp_hands_pose = None


@dataclass
class PoseFrame:
    """单帧姿态数据"""
    body_landmarks: np.ndarray | None = None       # shape (33, 4) — 33 关键点 (x, y, z, visibility)
    left_hand_landmarks: np.ndarray | None = None   # shape (21, 3) — 左手关键点
    right_hand_landmarks: np.ndarray | None = None  # shape (21, 3) — 右手关键点
    frame_timestamp: float = 0.0                     # 时间戳（秒）


@dataclass
class GestureEvent:
    """识别到的手势事件"""
    gesture_type: str = "none"          # "raise_hand"|"point"|"wave"|"come_closer"|"custom"|"none"
    confidence: float = 0.0             # 0.0 - 1.0
    gesture_id: Optional[str] = None    # 自定义手势 ID，custom 类型必填
    direction: Optional[dict] = None    # 指向方向（point 手势）


class PoseModule:
    """姿态/手势识别模块"""

    # 关键点索引 (MediaPipe Pose)
    NOSE = 0
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_ELBOW = 13
    RIGHT_ELBOW = 14
    LEFT_WRIST = 15
    RIGHT_WRIST = 16
    LEFT_INDEX = 19
    RIGHT_INDEX = 20

    # MediaPipe Hands 关键点
    HAND_WRIST = 0
    HAND_INDEX_TIP = 8

    def __init__(self, pose_config: dict | None = None, gesture_config: dict | None = None):
        self.pose_config = pose_config or {}
        self.gesture_config = gesture_config or {}
        self.enabled = self.pose_config.get('enabled', True)

        self._pose = None
        self._hands = None
        self._ready = False

        # 手势分类器
        self._classifier = GestureClassifier(gesture_config)

        # 手势动作槽: dict[gesture_type, list[Callable]]
        self._action_slots: dict[str, list[Callable]] = {}

        # 状态提供者（用于判断是否应在低功耗状态跳过）
        self._state_provider: Callable | None = None

        # 回调
        self._on_gesture_detected: Callable | None = None

    # ─── 回调设置 ───────────────────────────────────────

    def set_on_gesture_detected(self, callback: Callable):
        self._on_gesture_detected = callback

    def set_state_provider(self, provider: Callable):
        self._state_provider = provider

    @property
    def is_ready(self) -> bool:
        return self._ready

    # ─── 初始化 ──────────────────────────────────────────

    def initialize(self):
        """初始化 MediaPipe Pose + Hands"""
        if not self.enabled:
            logger.info('Pose module disabled by config')
            return

        try:
            global _mp_pose, _mp_hands_pose
            if _mp_pose is None:
                import mediapipe as mp
                _mp_pose = mp.solutions.pose
                _mp_hands_pose = mp.solutions.hands

            self._pose = _mp_pose.Pose(
                static_image_mode=False,
                model_complexity=self.pose_config.get('model_complexity', 1),
                smooth_landmarks=True,
                enable_segmentation=False,
                min_detection_confidence=self.pose_config.get('min_detection_confidence', 0.5),
                min_tracking_confidence=self.pose_config.get('min_tracking_confidence', 0.5),
            )
            self._hands = _mp_hands_pose.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._ready = True
            logger.info('Pose module ready (BlazePose + Hands)')
        except Exception as e:
            logger.warning(f'Pose module init failed (degraded): {e}')
            self._ready = False

    # ─── 姿态提取 ───────────────────────────────────────

    def extract_pose(self, frame_rgb: np.ndarray) -> Optional[PoseFrame]:
        """从单帧 RGB 图像中提取身体姿态和双手关键点"""
        if not self._ready:
            return None

        # 低功耗状态下跳过 Pose 提取
        if self._state_provider:
            try:
                state_info = self._state_provider()
                state = state_info.get('state', '')
                if state in ('Idle',):
                    return None
            except Exception:
                pass

        try:
            # Pose 提取
            pose_results = self._pose.process(frame_rgb)
            body = None
            if pose_results.pose_landmarks:
                body = np.array([
                    [lm.x, lm.y, lm.z, lm.visibility]
                    for lm in pose_results.pose_landmarks.landmark
                ], dtype=np.float32)

            # Hands 提取
            hands_results = self._hands.process(frame_rgb)
            left_hand = None
            right_hand = None
            if hands_results.multi_hand_landmarks:
                for idx, hand_lms in enumerate(hands_results.multi_hand_landmarks):
                    landmarks = np.array([
                        [lm.x, lm.y, lm.z]
                        for lm in hand_lms.landmark
                    ], dtype=np.float32)

                    # 根据手腕位置判断左右手
                    handedness = hands_results.multi_handedness[idx].classification[0].label
                    if handedness == 'Left':
                        left_hand = landmarks
                    else:
                        right_hand = landmarks

            if body is None and left_hand is None and right_hand is None:
                return None

            return PoseFrame(
                body_landmarks=body,
                left_hand_landmarks=left_hand,
                right_hand_landmarks=right_hand,
                frame_timestamp=time.time(),
            )
        except Exception as e:
            logger.error(f'Pose extraction error: {e}')
            return None

    # ─── 手势分类（委托给 GestureClassifier）─────────────

    def classify_gesture(self, sequence: list[PoseFrame]) -> GestureEvent:
        """对一段连续姿态帧序列进行分类"""
        if not self.gesture_config.get('enabled', True):
            return GestureEvent(gesture_type='none', confidence=0.0)
        return self._classifier.classify_gesture(sequence)

    def register_custom_gesture(self, name: str, sequence: list[PoseFrame], member_id: str = '') -> str:
        """注册用户自定义手势，返回 gesture_id"""
        return self._classifier.register_custom_gesture(name, sequence, member_id)

    def match_custom_gesture(self, sequence: list[PoseFrame]) -> Optional[GestureEvent]:
        """匹配已注册的自定义手势"""
        return self._classifier.match_custom_gesture(sequence)

    def delete_custom_gesture(self, gesture_id: str):
        """删除自定义手势"""
        self._classifier.delete_custom_gesture(gesture_id)

    def list_custom_gestures(self) -> list[dict]:
        """列出所有自定义手势"""
        return self._classifier.list_custom_gestures()

    # ─── 手势动作槽 ─────────────────────────────────────

    def register_action_slot(self, gesture_type: str, callback: Callable) -> None:
        """注册手势触发槽（pub-sub 模式）"""
        if gesture_type not in self._action_slots:
            self._action_slots[gesture_type] = []
        self._action_slots[gesture_type].append(callback)
        logger.debug(f'Action slot registered: {gesture_type} → {callback.__name__ if hasattr(callback, "__name__") else "lambda"}')

    def register_default_actions(self):
        """注册默认手势动作绑定"""
        logger.info('Registering default gesture actions')

        async def on_raise_hand(event: GestureEvent):
            logger.info(f'Default action: raise_hand → pause/resume conversation')
            if self._on_gesture_detected:
                if asyncio.iscoroutinefunction(self._on_gesture_detected):
                    await self._on_gesture_detected(event)
                else:
                    self._on_gesture_detected(event)

        async def on_wave(event: GestureEvent):
            logger.info(f'Default action: wave → switch skill')

        async def on_point(event: GestureEvent):
            logger.info(f'Default action: point → context query')

        async def on_come_closer(event: GestureEvent):
            logger.info(f'Default action: come_closer → activate')

        self.register_action_slot('raise_hand', on_raise_hand)
        self.register_action_slot('wave', on_wave)
        self.register_action_slot('point', on_point)
        self.register_action_slot('come_closer', on_come_closer)

    def _dispatch_gesture(self, gesture_event: GestureEvent):
        """异步分发手势事件到所有匹配的订阅者"""
        gesture_type = gesture_event.gesture_type
        if gesture_type == 'none':
            return

        # 分发到预定义手势槽
        slots = self._action_slots.get(gesture_type, [])
        for callback in slots:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(gesture_event))
                else:
                    callback(gesture_event)
            except Exception as e:
                logger.error(f'Action slot error for {gesture_type}: {e}')

        # 自定义手势：查找绑定的动作
        if gesture_type == 'custom' and gesture_event.gesture_id:
            custom_slots = self._action_slots.get(f'custom:{gesture_event.gesture_id}', [])
            for callback in custom_slots:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.create_task(callback(gesture_event))
                    else:
                        callback(gesture_event)
                except Exception as e:
                    logger.error(f'Custom action slot error: {e}')

    # ─── 手势动作绑定（持久化）──────────────────────────

    def bind_custom_action(self, gesture_id: str, action: str, params: dict, member_id: str = ''):
        """绑定自定义手势到系统动作（持久化到数据库）"""
        from src.python.shared.database import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO gesture_actions (gesture_id, action, params_json, member_id) VALUES (?, ?, ?, ?)",
                (gesture_id, action, __import__('json').dumps(params), member_id)
            )
        logger.info(f'Custom action bound: {gesture_id} → {action}')

    def unbind_custom_action(self, gesture_id: str):
        """解绑自定义手势的所有动作"""
        from src.python.shared.database import get_connection

        with get_connection() as conn:
            conn.execute("DELETE FROM gesture_actions WHERE gesture_id = ?", (gesture_id,))
        logger.info(f'Custom action unbound: {gesture_id}')

    def list_bindings(self) -> list[dict]:
        """查询所有手势动作绑定"""
        import json
        from src.python.shared.database import get_connection

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT ga.*, cg.name as gesture_name FROM gesture_actions ga "
                "LEFT JOIN custom_gestures cg ON ga.gesture_id = cg.id"
            ).fetchall()
        return [dict(r) for r in rows]

    # ─── 帧处理入口（由 CameraPipeline 调用）────────────

    def process_frame(self, frame_rgb: np.ndarray, frame_w: int, frame_h: int) -> Optional[GestureEvent]:
        """处理一帧：提取姿态 → 加入缓冲区 → 分类 → 分发"""
        pose_frame = self.extract_pose(frame_rgb)
        if pose_frame is None:
            return None

        # 加入滑动窗口
        event = self._classifier.process_frame(pose_frame)
        if event and event.gesture_type != 'none':
            # 分发手势到动作槽
            self._dispatch_gesture(event)
        return event

    # ─── 资源管理 ────────────────────────────────────────

    def close(self):
        """清理资源"""
        if self._pose:
            self._pose.close()
            self._pose = None
        if self._hands:
            self._hands.close()
            self._hands = None
        self._ready = False
        self._action_slots.clear()
        logger.info('Pose module closed')

    def __repr__(self) -> str:
        return f'PoseModule(ready={self._ready}, actions={len(self._action_slots)})'
