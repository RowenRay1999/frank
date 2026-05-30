"""
Frank 姿态模块共享类型定义

分离自 pose_module.py，避免循环导入：
  pose_module.py → gesture_classifier.py → pose_types.py (无循环)
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np


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
