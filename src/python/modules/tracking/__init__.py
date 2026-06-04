"""Frank 人物跟踪模块 — DeepSORT 多人跟踪 + 身份槽位"""
# PersonTracker 将在 Task 1.3 中实现
# ReIDExtractor 将在 Task 1.2 中实现
# QualityGate / FaceQualityResult 将在 Task 3.1 中实现
from src.python.modules.tracking.person_tracker import TrackState, Track, IdentitySlot

__all__ = [
    'TrackState', 'Track', 'IdentitySlot',
]
