"""
Frank 手势分类器 (Phase 5)

实现:
- 规则引擎识别 4 种预定义手势（举手/指向/挥手/走近）
- DTW 序列对齐匹配自定义手势
- 滑动窗口缓冲 + 质量门控 + 防抖
"""

import logging
import time
import uuid
from collections import deque
from typing import Optional

import numpy as np

from .pose_module import PoseFrame, GestureEvent

logger = logging.getLogger('frank.pose.classifier')

# Pose 关键点索引
POSE_NOSE = 0
POSE_LEFT_WRIST = 15
POSE_RIGHT_WRIST = 16
POSE_LEFT_ELBOW = 13
POSE_RIGHT_ELBOW = 14
POSE_LEFT_SHOULDER = 11
POSE_RIGHT_SHOULDER = 12
POSE_LEFT_INDEX = 19
POSE_RIGHT_INDEX = 20


class GestureClassifier:
    """手势分类器：规则引擎 + DTW 自定义手势"""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.dtw_threshold = self.config.get('dtw_threshold', 0.65)
        self.debounce_seconds = self.config.get('debounce_seconds', 3)
        self.window_frames = self.config.get('window_frames', 30)

        # 滑动窗口
        self._frame_buffer: deque[PoseFrame] = deque(maxlen=60)

        # 防抖: gesture_type → last_trigger_time
        self._last_trigger: dict[str, float] = {}

        # 挥手辅助状态
        self._wrist_x_history: list[float] = []
        self._wrist_direction_changes = 0

        # 走近辅助状态
        self._nose_z_start: float | None = None
        self._face_area_start: float | None = None
        self._approach_start_time: float | None = None

    # ─── 帧处理 ──────────────────────────────────────────

    def process_frame(self, pose_frame: PoseFrame) -> Optional[GestureEvent]:
        """将一帧加入滑动窗口，运行分类"""
        self._frame_buffer.append(pose_frame)

        # 仅在有足够帧时分类
        if len(self._frame_buffer) < self.window_frames:
            return None

        # 质量门控
        if not self._check_quality(self._frame_buffer):
            return None

        # 规则引擎分类
        return self.classify_gesture(list(self._frame_buffer))

    def _check_quality(self, frames: deque[PoseFrame]) -> bool:
        """检查滑动窗口质量：至少 50% 的关键点可见"""
        if len(frames) < self.window_frames:
            return False

        valid_frames = 0
        for f in frames:
            if f.body_landmarks is not None:
                visible = np.sum(f.body_landmarks[:, 3] > 0.5)
                if visible >= 15:  # 至少 15 个关键点可见（上半身）
                    valid_frames += 1

        return valid_frames >= self.window_frames * 0.5

    # ─── 规则引擎分类 ────────────────────────────────────

    def classify_gesture(self, sequence: list[PoseFrame]) -> GestureEvent:
        """对连续帧序列进行手势分类"""
        if not sequence:
            return GestureEvent()

        # 按置信度从高到低检查
        result = self._detect_raise_hand(sequence)
        if result and result.confidence >= 0.7:
            return self._apply_debounce(result)

        result = self._detect_wave(sequence)
        if result and result.confidence >= 0.7:
            return self._apply_debounce(result)

        result = self._detect_come_closer(sequence)
        if result and result.confidence >= 0.7:
            return self._apply_debounce(result)

        result = self._detect_point(sequence)
        if result and result.confidence >= 0.5:
            return self._apply_debounce(result)

        # 自定义手势匹配
        custom = self.match_custom_gesture(sequence)
        if custom:
            return self._apply_debounce(custom)

        return GestureEvent(gesture_type='none', confidence=0.0)

    def _apply_debounce(self, event: GestureEvent) -> GestureEvent:
        """应用防抖过滤"""
        now = time.time()
        last = self._last_trigger.get(event.gesture_type, 0)
        if now - last < self.debounce_seconds:
            return GestureEvent(gesture_type='none', confidence=0.0)
        self._last_trigger[event.gesture_type] = now
        return event

    # ─── 举手检测 ────────────────────────────────────────

    def _detect_raise_hand(self, sequence: list[PoseFrame]) -> Optional[GestureEvent]:
        """检测举手：手腕 Y 坐标小于鼻尖 Y 坐标持续 >= 1s"""
        raise_count = 0
        for f in sequence[-self.window_frames:]:
            if f.body_landmarks is None:
                continue

            nose_y = f.body_landmarks[POSE_NOSE, 1]
            left_wrist_y = f.body_landmarks[POSE_LEFT_WRIST, 1]
            right_wrist_y = f.body_landmarks[POSE_RIGHT_WRIST, 1]
            left_vis = f.body_landmarks[POSE_LEFT_WRIST, 3]
            right_vis = f.body_landmarks[POSE_RIGHT_WRIST, 3]

            left_raised = left_vis > 0.5 and left_wrist_y < nose_y
            right_raised = right_vis > 0.5 and right_wrist_y < nose_y

            if left_raised or right_raised:
                raise_count += 1

        ratio = raise_count / self.window_frames
        if ratio >= 0.6:
            return GestureEvent(
                gesture_type='raise_hand',
                confidence=ratio,
            )
        return None

    # ─── 指向检测 ────────────────────────────────────────

    def _detect_point(self, sequence: list[PoseFrame]) -> Optional[GestureEvent]:
        """检测指向：手臂伸展 + 食指方向稳定"""
        point_count = 0
        directions = []

        for f in sequence[-self.window_frames:]:
            if f.body_landmarks is None:
                continue

            for side in ['left', 'right']:
                if side == 'left':
                    wrist_idx, elbow_idx, shoulder_idx = POSE_LEFT_WRIST, POSE_LEFT_ELBOW, POSE_LEFT_SHOULDER
                else:
                    wrist_idx, elbow_idx, shoulder_idx = POSE_RIGHT_WRIST, POSE_RIGHT_ELBOW, POSE_RIGHT_SHOULDER

                wrist = f.body_landmarks[wrist_idx]
                elbow = f.body_landmarks[elbow_idx]
                shoulder = f.body_landmarks[shoulder_idx]

                if wrist[3] < 0.5 or elbow[3] < 0.5:
                    continue

                # 计算肘部角度（上臂-前臂夹角）
                upper_arm = np.array([elbow[0] - shoulder[0], elbow[1] - shoulder[1]])
                forearm = np.array([wrist[0] - elbow[0], wrist[1] - elbow[1]])

                upper_norm = np.linalg.norm(upper_arm)
                forearm_norm = np.linalg.norm(forearm)

                if upper_norm < 0.01 or forearm_norm < 0.01:
                    continue

                cos_angle = np.dot(upper_arm, forearm) / (upper_norm * forearm_norm)
                cos_angle = np.clip(cos_angle, -1, 1)
                angle_deg = np.degrees(np.arccos(cos_angle))

                # 手臂伸展：肘部角度 > 120 度
                if angle_deg > 120:
                    point_count += 1
                    # 指向方向：手腕到指尖向量
                    direction = np.array([wrist[0] - elbow[0], wrist[1] - elbow[1]])
                    directions.append(direction)

        ratio = point_count / (self.window_frames * 2)  # 两只手
        if ratio >= 0.4 and directions:
            avg_dir = np.mean(directions, axis=0)
            return GestureEvent(
                gesture_type='point',
                confidence=min(1.0, ratio * 1.5),
                direction={'x': float(avg_dir[0]), 'y': float(avg_dir[1])},
            )
        return None

    # ─── 挥手检测 ────────────────────────────────────────

    def _detect_wave(self, sequence: list[PoseFrame]) -> Optional[GestureEvent]:
        """检测挥手：手腕 X 坐标方向反转 >= 3 次，振幅 > 0.05"""
        x_vals = []
        for f in sequence[-self.window_frames:]:
            if f.body_landmarks is None:
                continue

            # 优先使用右手腕，其次左手腕
            right_vis = f.body_landmarks[POSE_RIGHT_WRIST, 3]
            left_vis = f.body_landmarks[POSE_LEFT_WRIST, 3]

            if right_vis > 0.5:
                x_vals.append(f.body_landmarks[POSE_RIGHT_WRIST, 0])
            elif left_vis > 0.5:
                x_vals.append(f.body_landmarks[POSE_LEFT_WRIST, 0])

        if len(x_vals) < 15:
            return None

        # 计算方向反转次数
        changes = 0
        direction = None
        for i in range(1, len(x_vals)):
            diff = x_vals[i] - x_vals[i - 1]
            if abs(diff) < 0.003:  # 忽略微小抖动
                continue
            cur_dir = 1 if diff > 0 else -1
            if direction is not None and cur_dir != direction:
                changes += 1
            direction = cur_dir

        amplitude = max(x_vals) - min(x_vals)
        if changes >= 3 and amplitude > 0.05:
            return GestureEvent(
                gesture_type='wave',
                confidence=min(1.0, changes / 6),
            )
        return None

    # ─── 走近检测 ────────────────────────────────────────

    def _detect_come_closer(self, sequence: list[PoseFrame]) -> Optional[GestureEvent]:
        """检测走近：鼻尖 Z 深度减小 > 0.1 持续 >= 1s"""
        z_vals = []
        for f in sequence[-self.window_frames:]:
            if f.body_landmarks is not None and f.body_landmarks[POSE_NOSE, 3] > 0.5:
                z_vals.append((f.body_landmarks[POSE_NOSE, 2], f.frame_timestamp))

        if len(z_vals) < 15:
            return None

        # 检查 Z 深度是否持续减小（走近）
        first_z = z_vals[0][0]
        last_z = z_vals[-1][0]
        duration = z_vals[-1][1] - z_vals[0][1]

        if duration < 0.5:
            return None

        # Z 减小（负值更小 = 更近）
        z_change = first_z - last_z
        if z_change > 0.03:  # 归一化坐标中的显著变化
            return GestureEvent(
                gesture_type='come_closer',
                confidence=min(1.0, z_change * 10),
            )
        return None

    # ─── DTW 算法 ─────────────────────────────────────────

    @staticmethod
    def _dtw_distance(seq1: np.ndarray, seq2: np.ndarray) -> float:
        """计算两个序列的 DTW 距离（简化版本）"""
        n, m = len(seq1), len(seq2)
        if n == 0 or m == 0:
            return float('inf')

        dtw = np.full((n + 1, m + 1), float('inf'))
        dtw[0, 0] = 0

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                cost = np.linalg.norm(seq1[i - 1] - seq2[j - 1])
                dtw[i, j] = cost + min(dtw[i - 1, j], dtw[i, j - 1], dtw[i - 1, j - 1])

        return dtw[n, m]

    def _sequence_to_feature(self, sequence: list[PoseFrame]) -> np.ndarray | None:
        """将 PoseFrame 序列转为归一化特征向量序列"""
        features = []
        for f in sequence:
            if f.body_landmarks is None:
                continue
            # 提取上半身关键点 (0-16，肩部以上) 的 (x, y) 坐标
            # 以鼻尖为原点，归一化
            nose = f.body_landmarks[POSE_NOSE]
            if nose[3] < 0.5:
                continue

            vec = []
            for i in range(17):  # 鼻尖 + 肩部以上
                if f.body_landmarks[i, 3] > 0.5:
                    vec.append(f.body_landmarks[i, 0] - nose[0])
                    vec.append(f.body_landmarks[i, 1] - nose[1])
                else:
                    vec.append(0.0)
                    vec.append(0.0)

            if vec:
                features.append(np.array(vec, dtype=np.float32))

        if not features:
            return None
        return np.array(features)

    # ─── 自定义手势管理 ──────────────────────────────────

    def register_custom_gesture(self, name: str, sequence: list[PoseFrame], member_id: str = '') -> str:
        """注册自定义手势，返回 gesture_id"""
        import json
        from src.python.shared.database import get_connection

        features = self._sequence_to_feature(sequence)
        if features is None:
            raise ValueError('无法从序列中提取有效特征')

        # 归一化：计算平均模板
        template = np.mean(features, axis=0).astype(np.float32)

        gesture_id = str(uuid.uuid4())

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO custom_gestures (id, member_id, name, gesture_type, landmarks_template) "
                "VALUES (?, ?, ?, 'custom', ?)",
                (gesture_id, member_id, name, template.tobytes())
            )

        logger.info(f'Custom gesture registered: {name} (id={gesture_id[:8]}...)')
        return gesture_id

    def match_custom_gesture(self, sequence: list[PoseFrame]) -> Optional[GestureEvent]:
        """匹配已注册的自定义手势"""
        from src.python.shared.database import get_connection, deserialize_embedding

        features = self._sequence_to_feature(sequence)
        if features is None or len(features) < 10:
            return None

        # 取当前序列的平均特征
        query = np.mean(features, axis=0)

        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM custom_gestures").fetchall()

        best_score = 0.0
        best_gesture = None

        for row in rows:
            template_data = row['landmarks_template']
            if template_data:
                template = np.frombuffer(template_data, dtype=np.float32)
                if len(template) != len(query):
                    continue

                # 余弦相似度（特征向量作为整体）
                dot = np.dot(query, template)
                norm = np.linalg.norm(query) * np.linalg.norm(template)
                score = dot / norm if norm > 0 else 0

                if score > best_score and score >= self.dtw_threshold:
                    best_score = score
                    best_gesture = row

        if best_gesture:
            return GestureEvent(
                gesture_type='custom',
                confidence=float(best_score),
                gesture_id=best_gesture['id'],
            )
        return None

    def delete_custom_gesture(self, gesture_id: str):
        """删除自定义手势"""
        from src.python.shared.database import get_connection

        with get_connection() as conn:
            conn.execute("DELETE FROM custom_gestures WHERE id = ?", (gesture_id,))
        logger.info(f'Custom gesture deleted: {gesture_id[:8]}...')

    def list_custom_gestures(self) -> list[dict]:
        """列出所有自定义手势"""
        from src.python.shared.database import get_connection

        with get_connection() as conn:
            rows = conn.execute("SELECT id, name, gesture_type, member_id, created_at FROM custom_gestures").fetchall()
        return [dict(r) for r in rows]
