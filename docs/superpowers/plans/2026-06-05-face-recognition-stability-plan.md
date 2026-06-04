# 人脸识别稳定性优化 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将同一采集人物的正确持续识别率从 50-60% 提升到 90%+，通过多人时空跟踪器 + 多样本图库 + 质量门控 + 身份槽位时序平滑 + ReID 重识别五模块联合优化。

**Architecture:** 为 CameraPipeline 新增每帧输出的质量评估信号；新增 PersonTracker（DeepSORT 范式）独立管理多人 track 生命周期和身份槽位绑定；IdentityFusionEngine 从"逐帧接收 embedding"重构为"接收 tracker 分发的身份假设"；Database 新增 face_gallery 列，匹配从单向量余弦改为 max-pooling 图库匹配；MemberManager 注册流程改为 K-Means 聚类存储多个代表性 embedding。

**Tech Stack:** Python 3.11+, numpy, scipy (K-Means), opencv-python, insightface, sqlite3, scipy.optimize.linear_sum_assignment (匈牙利算法)

**Spec:** `docs/superpowers/specs/2026-06-05-face-recognition-stability-design.md`

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/python/modules/tracking/__init__.py` | **新建** | 模块导出 |
| `src/python/modules/tracking/person_tracker.py` | **新建** | DeepSORT 多人跟踪器 + 身份槽位管理 |
| `src/python/modules/tracking/reid_extractor.py` | **新建** | 外观特征提取（HSV直方图 + 可选CNN） |
| `src/python/modules/tracking/quality_gate.py` | **新建** | 人脸质量门控（角度/模糊/遮挡/大小/置信度） |
| `src/python/modules/camera/camera_pipeline.py` | 修改 | 输出 landmarks + 质量信号 + 外观特征调用 |
| `src/python/modules/fusion/identity_fusion.py` | 修改 | 图库匹配 + 时序平滑 + track 感知 |
| `src/python/modules/members/member_manager.py` | 修改 | K-Means 聚类注册 |
| `src/python/shared/database.py` | 修改 | face_gallery 列 + 图库匹配 + schema v5 |
| `src/python/server/main.py` | 修改 | PersonTracker 初始化与事件绑定 |

---

## Phase 1: 多人时空跟踪器（Person Tracker）

### Task 1.1: 创建 tracking 模块骨架 + 数据结构定义

**Files:**
- Create: `src/python/modules/tracking/__init__.py`
- Create: `src/python/modules/tracking/person_tracker.py` (数据结构部分)

- [ ] **Step 1: 创建 `__init__.py`**

```python
"""Frank 人物跟踪模块 — DeepSORT 多人跟踪 + 身份槽位"""
from src.python.modules.tracking.person_tracker import PersonTracker, TrackState, Track, IdentitySlot
from src.python.modules.tracking.reid_extractor import ReIDExtractor
from src.python.modules.tracking.quality_gate import QualityGate, FaceQualityResult

__all__ = [
    'PersonTracker', 'TrackState', 'Track', 'IdentitySlot',
    'ReIDExtractor', 'QualityGate', 'FaceQualityResult',
]
```

- [ ] **Step 2: 创建 `person_tracker.py` — 数据结构**

```python
"""
Frank 多人时空跟踪器

DeepSORT 范式：运动(Kalman) + 外观(ReID) + 人脸(embedding) 三维联合匹配
匈牙利算法全局最优分配 + 级联匹配 + Track 生命周期管理
"""

import logging
import time
from dataclasses import dataclass, field
from collections import deque
from enum import Enum
from typing import Any, Callable, Optional

import numpy as np

logger = logging.getLogger('frank.tracking')


class TrackState(Enum):
    """Track 生命周期状态"""
    CANDIDATE = 'candidate'   # 新检测，需连续确认
    ACTIVE = 'active'         # 活跃跟踪
    LOST = 'lost'             # 短暂丢失（遮挡/出框）
    REMOVED = 'removed'       # 超时释放


@dataclass
class Detection:
    """单帧检测结果"""
    # 人脸信息（可选，MediaPipe 回退时可能无 embedding）
    bbox: tuple[float, float, float, float]  # (x, y, w, h) 归一化 [0,1]
    confidence: float = 0.0
    face_embedding: Optional[np.ndarray] = None       # 512-d normalized
    face_landmarks: Optional[list] = None              # InsightFace landmarks
    face_quality: Optional['FaceQualityResult'] = None # 质量评估结果
    # 外观特征（ReID）
    appearance_feature: Optional[np.ndarray] = None    # 128-d normalized

    @property
    def center(self) -> tuple[float, float]:
        """bbox 中心点"""
        x, y, w, h = self.bbox
        return (x + w / 2, y + h / 2)

    @property
    def area(self) -> float:
        """bbox 面积"""
        x, y, w, h = self.bbox
        return w * h


@dataclass
class IdentitySlot:
    """身份槽位：track 与 member 的绑定关系"""
    track_id: int
    bound_member_id: Optional[str] = None
    bound_display_name: Optional[str] = None
    hypothesis_history: deque = field(default_factory=lambda: deque(maxlen=10))
    face_quality_count: int = 0
    last_good_face_time: float = 0.0
    last_match_score: float = 0.0

    def record_match(self, member_id: str | None, display_name: str | None, score: float):
        """记录一次匹配结果"""
        self.hypothesis_history.append({
            'member_id': member_id,
            'display_name': display_name,
            'score': score,
            'time': time.time(),
        })

    def get_consensus(self, window: int = 5) -> tuple[str | None, str | None, float]:
        """从最近 window 帧中获取一致性最高的身份
        Returns: (member_id, display_name, avg_score) or (None, None, 0.0)
        """
        recent = list(self.hypothesis_history)[-window:]
        if not recent:
            return None, None, 0.0

        # 统计每个 member_id 的出现次数
        votes: dict[str, list[float]] = {}
        for h in recent:
            mid = h['member_id']
            if mid:
                if mid not in votes:
                    votes[mid] = []
                votes[mid].append(h['score'])

        if not votes:
            return None, None, 0.0

        # 选择票数最多且平均分最高的
        best_id = max(votes.keys(), key=lambda k: (len(votes[k]), sum(votes[k]) / len(votes[k])))
        scores = votes[best_id]
        avg_score = sum(scores) / len(scores)
        display_name = next((h['display_name'] for h in recent if h['member_id'] == best_id), None)
        return best_id, display_name, avg_score


@dataclass
class Track:
    """单条跟踪轨迹"""
    track_id: int
    state: TrackState = TrackState.CANDIDATE
    # Kalman 状态: [x, y, w, h, dx, dy, dw, dh]
    kf_state: np.ndarray = field(default_factory=lambda: np.zeros(8, dtype=np.float64))
    kf_covariance: np.ndarray = field(default_factory=lambda: np.eye(8) * 0.1)
    # 外观特征（指数移动平均）
    appearance_feature: Optional[np.ndarray] = None
    appearance_alpha: float = 0.9
    # 时间追踪
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    lost_since: float = 0.0
    # 连续匹配计数（candidate → active 升级）
    consecutive_matches: int = 0
    # 身份槽位
    identity: IdentitySlot = field(default_factory=lambda: IdentitySlot(track_id=-1))
    # 最后已知的人脸 bbox + embedding
    last_face_bbox: Optional[tuple] = None
    last_face_embedding: Optional[np.ndarray] = None
    # 最后已知位置（用于 ReID 恢复）
    last_position: Optional[tuple[float, float]] = None

    def __post_init__(self):
        if self.identity.track_id == -1:
            self.identity.track_id = self.track_id

    def predict_kf(self, dt: float = 1.0):
        """Kalman 预测一步（匀速模型）"""
        # 状态转移矩阵 F (8x8)
        F = np.eye(8)
        F[0, 4] = dt  # x += dx * dt
        F[1, 5] = dt  # y += dy * dt
        F[2, 6] = dt  # w += dw * dt
        F[3, 7] = dt  # h += dh * dt

        # 过程噪声 Q
        Q = np.eye(8) * 0.01
        Q[4:, 4:] *= 0.01  # 速度噪声较小

        self.kf_state = F @ self.kf_state
        self.kf_covariance = F @ self.kf_covariance @ F.T + Q

    def update_kf(self, detection: Detection):
        """Kalman 更新（用检测结果修正）"""
        x, y, w, h = detection.bbox
        z = np.array([x, y, w, h], dtype=np.float64)

        # 观测矩阵 H (4x8): 只观测位置+大小
        H = np.zeros((4, 8))
        H[0, 0] = H[1, 1] = H[2, 2] = H[3, 3] = 1.0

        # 观测噪声 R
        R = np.eye(4) * 0.05
        R[2, 2] = R[3, 3] = 0.01  # 大小观测更准

        # Kalman gain
        S = H @ self.kf_covariance @ H.T + R
        K = self.kf_covariance @ H.T @ np.linalg.inv(S)

        # 更新
        y = z - H @ self.kf_state  # innovation
        self.kf_state = self.kf_state + K @ y
        self.kf_covariance = (np.eye(8) - K @ H) @ self.kf_covariance

    def update_appearance(self, feature: np.ndarray):
        """指数移动平均更新外观特征"""
        if self.appearance_feature is None:
            self.appearance_feature = feature
        else:
            self.appearance_feature = (
                self.appearance_alpha * self.appearance_feature +
                (1 - self.appearance_alpha) * feature
            )

    @property
    def predicted_bbox(self) -> tuple[float, float, float, float]:
        """Kalman 预测的边界框"""
        return (
            self.kf_state[0], self.kf_state[1],
            self.kf_state[2], self.kf_state[3],
        )

    @property
    def time_since_update(self) -> float:
        return time.time() - self.last_seen
```

- [ ] **Step 3: Commit**

```bash
git add src/python/modules/tracking/__init__.py src/python/modules/tracking/person_tracker.py
git commit -m "feat(tracking): 创建 tracking 模块骨架与数据结构 (Track/TrackState/Detection/IdentitySlot)"
```

---

### Task 1.2: 实现外观特征提取器（ReID Extractor）

**Files:**
- Create: `src/python/modules/tracking/reid_extractor.py`

- [ ] **Step 1: 实现 HSV 颜色直方图提取器（轻量方案）**

```python
"""
Frank 外观特征提取器（ReID）

轻量方案：HSV 颜色直方图（上身+下身分离）+ 可选 CNN（OSNet/MobileNet-ReID）
用于多人跟踪中的外观代价计算和离场重入恢复
"""

import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger('frank.reid')

FEATURE_DIM = 128  # 外观特征维度


class ReIDExtractor:
    """外观特征提取器

    提取人物的衣着颜色/纹理特征，用于：
    1. 多人跟踪中区分外观不同的人（辅助运动匹配）
    2. 人物离场后重入的身份恢复（Re-ID）
    """

    def __init__(self, method: str = 'hsv_histogram'):
        """
        Args:
            method: 提取方法
                - 'hsv_histogram': HSV 颜色直方图（默认，快速，2-3ms）
                - 未来可扩展 'osnet' / 'mobilenet_reid' CNN 方案
        """
        self.method = method
        self._model = None
        if method == 'osnet':
            self._init_osnet()

    def _init_osnet(self):
        """延迟加载 OSNet（可选，需要 torch）"""
        try:
            import torch
            import torchreid
            self._model = torchreid.models.build_model(
                name='osnet_x0_25',
                num_classes=1000,
                pretrained=True,
            )
            self._model.eval()
            logger.info('OSNet ReID model loaded')
        except ImportError:
            logger.warning('torch/torchreid not available, falling back to HSV histogram')
            self.method = 'hsv_histogram'
        except Exception as e:
            logger.warning(f'OSNet init failed: {e}, falling back to HSV histogram')
            self.method = 'hsv_histogram'

    def extract(self, frame: np.ndarray, bbox: tuple[float, float, float, float]) -> Optional[np.ndarray]:
        """从帧中提取人物外观特征

        Args:
            frame: BGR 图像 (H, W, 3)
            bbox: (x, y, w, h) 归一化坐标 [0, 1]

        Returns:
            128-d normalized float32 feature vector, or None
        """
        if self.method == 'osnet' and self._model:
            return self._extract_osnet(frame, bbox)
        return self._extract_hsv_histogram(frame, bbox)

    def _extract_hsv_histogram(self, frame: np.ndarray, bbox: tuple[float, float, float, float]) -> Optional[np.ndarray]:
        """HSV 颜色直方图 + 空间分区

        策略：
        - 将人物区域分为上下两半（上半身/下半身）
        - 每半提取 HSV 直方图 (H:16 bins, S:8 bins)
        - 拼接得到 (16+8)*2 = 48 维 → pad/truncate 到 128 维
        """
        try:
            h, w = frame.shape[:2]
            x, y, bw, bh = bbox

            # 从归一化坐标转换到像素坐标
            x1 = int(max(0, x * w))
            y1 = int(max(0, y * h))
            x2 = int(min(w, (x + bw) * w))
            y2 = int(min(h, (y + bh) * h))

            if x2 <= x1 or y2 <= y1:
                return None

            person_roi = frame[y1:y2, x1:x2]
            if person_roi.size == 0:
                return None

            hsv = cv2.cvtColor(person_roi, cv2.COLOR_BGR2HSV)

            # 上下分区
            mid_y = hsv.shape[0] // 2
            top = hsv[:mid_y, :]
            bottom = hsv[mid_y:, :]

            features = []
            for region in [top, bottom]:
                if region.size == 0:
                    features.extend([0.0] * 24)
                    continue
                # H 直方图 (16 bins)
                h_hist = cv2.calcHist([region], [0], None, [16], [0, 180])
                h_hist = cv2.normalize(h_hist, h_hist).flatten()
                # S 直方图 (8 bins)
                s_hist = cv2.calcHist([region], [1], None, [8], [0, 256])
                s_hist = cv2.normalize(s_hist, s_hist).flatten()
                features.extend(h_hist.tolist())
                features.extend(s_hist.tolist())

            feat = np.array(features, dtype=np.float32)

            # 填充/截断到 FEATURE_DIM
            if len(feat) < FEATURE_DIM:
                feat = np.pad(feat, (0, FEATURE_DIM - len(feat)), mode='constant')
            else:
                feat = feat[:FEATURE_DIM]

            # L2 归一化
            norm = np.linalg.norm(feat)
            if norm > 0:
                feat = feat / norm

            return feat
        except Exception as e:
            logger.debug(f'HSV feature extraction error: {e}')
            return None

    def _extract_osnet(self, frame: np.ndarray, bbox: tuple[float, float, float, float]) -> Optional[np.ndarray]:
        """OSNet CNN 特征提取（保留接口，待后续实现）"""
        # 暂未实现，回退到 HSV
        return self._extract_hsv_histogram(frame, bbox)

    @staticmethod
    def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
        """外观特征余弦距离 (0-2, 越小越相似)"""
        if a is None or b is None:
            return 1.0
        similarity = float(np.dot(a, b))
        return 1.0 - similarity  # 转为距离
```

- [ ] **Step 2: Commit**

```bash
git add src/python/modules/tracking/reid_extractor.py
git commit -m "feat(tracking): 实现外观特征提取器 (HSV直方图 + OSNet接口预留)"
```

---

### Task 1.3: 实现 PersonTracker 核心 — 代价矩阵 + 匈牙利 + 级联匹配 + 生命周期

**Files:**
- Modify: `src/python/modules/tracking/person_tracker.py` (追加 PersonTracker 类)

- [ ] **Step 1: 追加 PersonTracker 类 — 初始化 + 参数**

在 `person_tracker.py` 末尾追加：

```python
class PersonTracker:
    """多人时空跟踪器（DeepSORT 范式）

    每帧调用 update() 传入 Detection 列表，返回 (track_id → identity) 映射。

    管道：
    1. Kalman 预测所有活跃 track 的下一帧位置
    2. 构建三维代价矩阵（运动 + 外观 + 人脸）
    3. 匈牙利算法全局最优分配（高分检测优先）
    4. 级联匹配（高分检测 → active tracks → 低分检测 → lost tracks）
    5. Track 生命周期管理（CANDIDATE → ACTIVE → LOST → REMOVED）
    6. 身份槽位绑定/解绑/切换
    """

    # 匹配权重
    ALPHA_MOTION = 0.4       # 运动代价权重（常态）
    BETA_APPEARANCE = 0.3    # 外观代价权重（常态）
    BETA_APPEARANCE_CROSS = 0.6  # 外观代价权重（交叉时）
    GAMMA_FACE = 0.3         # 人脸代价权重

    # 阈值
    MATCH_THRESHOLD = 0.4    # 匹配代价阈值（低于此值视为匹配）
    CANDIDATE_CONFIRM = 3    # Candidate 确认帧数
    LOST_TIMEOUT = 60        # LOST 超时帧数
    FACE_KEEP_ALIVE = 3.0    # 人脸丢失后身份保持时间（秒）
    IDENTITY_BIND_WINDOW = 5 # 身份绑定所需连续匹配帧数
    IDENTITY_BIND_SCORE = 0.55  # 身份绑定最低平均分

    # 交叉检测阈值
    CROSS_IOU_THRESHOLD = 0.3  # 两个 track 的 bbox IoU 超过此值视为交叉

    def __init__(self, reid_extractor=None):
        self._tracks: dict[int, Track] = {}
        self._next_id = 0
        self._reid = reid_extractor
        self._removed_tracks: list[Track] = []  # 最近移除的 track（供 ReID 恢复，保留 30 秒）
        self._removed_cleanup_interval = 30.0
        self._last_cleanup = time.time()

        # 回调
        self._on_identity_bind: Callable | None = None
        self._on_identity_unbind: Callable | None = None
        self._on_identity_switch: Callable | None = None
        self._on_track_created: Callable | None = None
        self._on_track_removed: Callable | None = None

    # ─── 回调设置 ───────────────────────────────────────

    def set_on_identity_bind(self, callback: Callable):
        """track 绑定到 member 时回调"""
        self._on_identity_bind = callback

    def set_on_identity_unbind(self, callback: Callable):
        """track 解绑 member 时回调"""
        self._on_identity_unbind = callback

    def set_on_identity_switch(self, callback: Callable):
        """track 身份切换时回调"""
        self._on_identity_switch = callback

    def set_on_track_created(self, callback: Callable):
        """新 track 创建时回调"""
        self._on_track_created = callback

    def set_on_track_removed(self, callback: Callable):
        """track 移除时回调"""
        self._on_track_removed = callback

    # ─── 主更新入口 ───────────────────────────────────────

    def update(self, detections: list[Detection], frame: np.ndarray | None = None,
               timestamp: float | None = None) -> dict[int, dict]:
        """每帧调用，处理一批检测结果

        Args:
            detections: 当前帧的 Detection 列表
            frame: 原始帧（供 ReID 提取外观特征）
            timestamp: 当前时间戳

        Returns:
            {track_id: {member_id, display_name, confidence, ...}, ...}
        """
        now = timestamp or time.time()

        # Step 0: 为无外观特征的 detection 提取外观
        if frame is not None and self._reid:
            for det in detections:
                if det.appearance_feature is None:
                    det.appearance_feature = self._reid.extract(frame, det.bbox)

        # Step 1: Kalman 预测
        for track in self._tracks.values():
            if track.state in (TrackState.ACTIVE, TrackState.LOST):
                track.predict_kf()

        # Step 2: 高低分分流
        high_score_dets = [d for d in detections if d.confidence >= 0.5]
        low_score_dets = [d for d in detections if d.confidence < 0.5]

        # Step 3: 级联匹配
        matched, unmatched_dets, unmatched_tracks = self._cascade_match(
            high_score_dets, now
        )

        # Step 4: 低分检测匹配未匹配的 track
        if low_score_dets and unmatched_tracks:
            extra_matched, unmatched_dets, still_unmatched = self._match_detections(
                low_score_dets, unmatched_tracks
            )
            matched.update(extra_matched)
            unmatched_tracks = still_unmatched

        # Step 5: 更新匹配的 track
        for track_id, det_idx in matched.items():
            det = detections[det_idx]
            track = self._tracks[track_id]
            track.update_kf(det)
            if det.appearance_feature is not None:
                track.update_appearance(det.appearance_feature)
            track.last_seen = now
            track.lost_since = 0
            track.last_face_bbox = det.bbox
            track.last_position = det.center
            if det.face_embedding is not None:
                track.last_face_embedding = det.face_embedding
            # Candidate 升级
            if track.state == TrackState.CANDIDATE:
                track.consecutive_matches += 1
                if track.consecutive_matches >= self.CANDIDATE_CONFIRM:
                    track.state = TrackState.ACTIVE
                    logger.info(f'Track {track_id} confirmed (ACTIVE)')
            elif track.state == TrackState.LOST:
                track.state = TrackState.ACTIVE
                logger.info(f'Track {track_id} recovered from LOST')

        # Step 6: 处理未匹配的 detection（创建新 track candidate）
        for det_idx in unmatched_dets:
            det = detections[det_idx]
            # 检查是否可以与最近移除的 track 做 ReID 恢复
            recovered = self._try_reid_recovery(det, now)
            if recovered:
                continue
            # 创建新 track
            track_id = self._next_id
            self._next_id += 1
            track = Track(track_id=track_id)
            x, y, w, h = det.bbox
            track.kf_state = np.array([x, y, w, h, 0, 0, 0, 0], dtype=np.float64)
            if det.appearance_feature is not None:
                track.appearance_feature = det.appearance_feature
            track.last_face_bbox = det.bbox
            track.last_face_embedding = det.face_embedding
            track.last_position = det.center
            track.identity = IdentitySlot(track_id=track_id)
            self._tracks[track_id] = track
            if self._on_track_created:
                try:
                    self._on_track_created({'track_id': track_id, 'detection': det})
                except Exception:
                    pass

        # Step 7: 处理未匹配的 track（丢失）
        for track_id in unmatched_tracks:
            track = self._tracks[track_id]
            track.lost_since = time.time() if track.lost_since == 0 else track.lost_since
            if track.state == TrackState.ACTIVE:
                track.state = TrackState.LOST
                logger.debug(f'Track {track_id} lost')
            time_lost = now - track.lost_since
            if time_lost > self.LOST_TIMEOUT / 30.0:  # 60 帧 ≈ 2 秒
                track.state = TrackState.REMOVED
                self._removed_tracks.append(track)
                # 保留最近 30 秒内移除的 track
                self._cleanup_removed_tracks(now)
                del self._tracks[track_id]
                if self._on_track_removed:
                    try:
                        self._on_track_removed({'track_id': track_id, 'track': track})
                    except Exception:
                        pass

        # Step 8: 返回当前活跃的 track 身份映射
        return self._get_active_identities()

    # ─── 代价矩阵 ───────────────────────────────────────

    def _compute_cost_matrix(self, detections: list[Detection],
                              tracks: list[Track]) -> np.ndarray:
        """计算三维联合代价矩阵

        Returns:
            (M, N) 矩阵，M=track数，N=detection数
            每个元素 = α × motion_cost + β × appearance_cost + γ × face_cost
        """
        M, N = len(tracks), len(detections)
        cost = np.full((M, N), 1e9, dtype=np.float64)

        for i, track in enumerate(tracks):
            for j, det in enumerate(detections):
                # 运动代价：马氏距离
                motion_cost = self._motion_cost(track, det)

                # 外观代价：余弦距离
                app_cost = self._appearance_cost(track, det)

                # 人脸代价：余弦距离
                face_cost = self._face_cost(track, det)

                # 动态权重：检测交叉场景
                beta = self._detect_cross_scenario(track, tracks) if track.state == TrackState.ACTIVE else self.BETA_APPEARANCE

                cost[i, j] = (
                    self.ALPHA_MOTION * motion_cost +
                    beta * app_cost +
                    self.GAMMA_FACE * face_cost
                )

        return cost

    def _motion_cost(self, track: Track, det: Detection) -> float:
        """马氏距离：Kalman 预测位置与检测位置的差异"""
        x, y, w, h = det.bbox
        z = np.array([x, y, w, h], dtype=np.float64)
        pred = track.kf_state[:4]

        # 只取位置+大小部分的协方差
        S = track.kf_covariance[:4, :4]
        try:
            diff = z - pred
            inv_S = np.linalg.inv(S + np.eye(4) * 0.001)
            mahalanobis = np.sqrt(diff @ inv_S @ diff)
            return min(float(mahalanobis), 10.0)  # clamp
        except np.linalg.LinAlgError:
            # 退化为欧氏距离
            return min(float(np.linalg.norm(diff)), 10.0)

    def _appearance_cost(self, track: Track, det: Detection) -> float:
        """外观特征余弦距离"""
        if track.appearance_feature is None or det.appearance_feature is None:
            return 0.5  # 中性代价
        return float(1.0 - np.dot(track.appearance_feature, det.appearance_feature))

    def _face_cost(self, track: Track, det: Detection) -> float:
        """人脸 embedding 余弦距离"""
        if track.last_face_embedding is None or det.face_embedding is None:
            return 0.5  # 中性代价
        return float(1.0 - np.dot(track.last_face_embedding, det.face_embedding))

    def _detect_cross_scenario(self, track: Track, all_tracks: list[Track]) -> float:
        """检测当前 track 是否处于交叉场景
        条件：存在另一个 track 且 IoU > 0.3
        """
        for other in all_tracks:
            if other.track_id == track.track_id:
                continue
            if other.state not in (TrackState.ACTIVE, TrackState.LOST):
                continue
            if self._bbox_iou(track.predicted_bbox, other.predicted_bbox) > self.CROSS_IOU_THRESHOLD:
                return self.BETA_APPEARANCE_CROSS
        return self.BETA_APPEARANCE

    @staticmethod
    def _bbox_iou(a: tuple, b: tuple) -> float:
        """两个 bbox 的 IoU"""
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        # 交集
        ix = max(ax, bx)
        iy = max(ay, by)
        iw = min(ax + aw, bx + bw) - ix
        ih = min(ay + ah, by + bh) - iy
        if iw <= 0 or ih <= 0:
            return 0.0
        intersection = iw * ih
        union = aw * ah + bw * bh - intersection
        return float(intersection / union) if union > 0 else 0.0

    # ─── 匈牙利匹配 ───────────────────────────────────────

    def _hungarian_match(self, cost_matrix: np.ndarray) -> tuple[dict[int, int], set[int], set[int]]:
        """匈牙利算法最优分配

        Returns:
            (matched: {track_idx → det_idx}, unmatched_det_indices, unmatched_track_indices)
        """
        from scipy.optimize import linear_sum_assignment

        M, N = cost_matrix.shape
        if M == 0 or N == 0:
            return {}, set(range(N)), set(range(M))

        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        matched = {}
        for r, c in zip(row_ind, col_ind):
            if cost_matrix[r, c] < self.MATCH_THRESHOLD:
                matched[int(r)] = int(c)

        unmatched_dets = set(range(N)) - set(matched.values())
        unmatched_tracks = set(range(M)) - set(matched.keys())

        return matched, unmatched_dets, unmatched_tracks

    # ─── 级联匹配 ───────────────────────────────────────

    def _cascade_match(self, detections: list[Detection], now: float) -> tuple:
        """级联匹配：优先匹配丢失时间短的 track

        Returns:
            (matched: {track_id → det_idx}, unmatched_det_indices, unmatched_track_ids)
        """
        active_tracks = [t for t in self._tracks.values()
                        if t.state in (TrackState.ACTIVE, TrackState.LOST, TrackState.CANDIDATE)]

        if not active_tracks:
            return {}, set(range(len(detections))), set()

        # 按丢失时间分组
        lost_tracks = sorted(
            [t for t in active_tracks if t.state == TrackState.LOST],
            key=lambda t: t.time_since_update
        )
        active = [t for t in active_tracks if t.state in (TrackState.ACTIVE, TrackState.CANDIDATE)]

        unmatched_dets = set(range(len(detections)))
        unmatched_track_ids: set[int] = set()
        all_matched: dict[int, int] = {}

        # 第一轮：活跃 track 与高分检测
        if active:
            track_to_idx = {a.track_id: i for i, a in enumerate(active)}
            idx_to_track = {i: a.track_id for i, a in enumerate(active)}
            cost = self._compute_cost_matrix(detections, active)
            matched, unmatched_d, unmatched_t = self._hungarian_match(cost)

            for t_idx, d_idx in matched.items():
                all_matched[idx_to_track[t_idx]] = d_idx
            unmatched_dets = unmatched_d
            for t_idx in unmatched_t:
                unmatched_track_ids.add(idx_to_track[t_idx])

        # 第二轮：丢失 track 与剩余检测（按丢失时间分组）
        if lost_tracks and unmatched_dets:
            remaining_dets = [detections[i] for i in unmatched_dets]
            det_idx_map = {new: old for new, old in enumerate(unmatched_dets)}

            cost = self._compute_cost_matrix(remaining_dets, lost_tracks)
            matched, unmatched_d, unmatched_t = self._hungarian_match(cost)

            for t_idx, d_idx in matched.items():
                all_matched[lost_tracks[t_idx].track_id] = det_idx_map[d_idx]
            unmatched_dets = {det_idx_map[d] for d in unmatched_d}
            for t_idx in unmatched_t:
                unmatched_track_ids.add(lost_tracks[t_idx].track_id)

        return all_matched, unmatched_dets, unmatched_track_ids

    def _match_detections(self, detections: list[Detection],
                          track_ids: set[int]) -> tuple:
        """简单的检测-轨道匹配（用于低分检测或备用匹配）"""
        tracks = [self._tracks[tid] for tid in track_ids]
        id_to_idx = {t.track_id: i for i, t in enumerate(tracks)}
        idx_to_id = {i: t.track_id for i, t in enumerate(tracks)}

        cost = self._compute_cost_matrix(detections, tracks)
        matched, unmatched_d, unmatched_t = self._hungarian_match(cost)

        result = {}
        for t_idx, d_idx in matched.items():
            result[idx_to_id[t_idx]] = d_idx
        unmatched_ids = {idx_to_id[t] for t in unmatched_t}

        return result, unmatched_d, unmatched_ids

    # ─── ReID 恢复 ───────────────────────────────────────

    def _try_reid_recovery(self, det: Detection, now: float) -> bool:
        """尝试将新 detection 与最近移除的 track 做外观 ReID 匹配

        Returns: True if recovered, False otherwise
        """
        if det.appearance_feature is None:
            return False
        for removed in self._removed_tracks:
            if removed.appearance_feature is None:
                continue
            similarity = float(np.dot(det.appearance_feature, removed.appearance_feature))
            if similarity > 0.7:  # 外观相似度阈值
                # 恢复 track
                removed.state = TrackState.ACTIVE
                removed.lost_since = 0
                removed.last_seen = now
                x, y, w, h = det.bbox
                removed.kf_state = np.array([x, y, w, h, 0, 0, 0, 0], dtype=np.float64)
                removed.last_face_bbox = det.bbox
                removed.last_face_embedding = det.face_embedding
                removed.last_position = det.center
                if det.appearance_feature is not None:
                    removed.update_appearance(det.appearance_feature)
                self._tracks[removed.track_id] = removed
                self._removed_tracks.remove(removed)
                logger.info(f'Track {removed.track_id} ReID recovered')
                return True
        return False

    def _cleanup_removed_tracks(self, now: float):
        """清理超过 30 秒的已移除 track"""
        self._removed_tracks = [
            t for t in self._removed_tracks
            if now - t.last_seen < self._removed_cleanup_interval
        ]

    # ─── 身份槽位管理 ───────────────────────────────────────

    def bind_identity(self, track_id: int, member_id: str, display_name: str, score: float):
        """将 track 绑定到 member"""
        track = self._tracks.get(track_id)
        if not track:
            return
        track.identity.record_match(member_id, display_name, score)
        consensus_id, consensus_name, avg_score = track.identity.get_consensus(self.IDENTITY_BIND_WINDOW)

        old_member_id = track.identity.bound_member_id
        if consensus_id and avg_score >= self.IDENTITY_BIND_SCORE:
            if old_member_id and old_member_id != consensus_id:
                # 身份切换
                if self._on_identity_switch:
                    try:
                        self._on_identity_switch({
                            'track_id': track_id,
                            'from': old_member_id,
                            'to': consensus_id,
                            'to_name': consensus_name,
                            'score': avg_score,
                        })
                    except Exception:
                        pass
            track.identity.bound_member_id = consensus_id
            track.identity.bound_display_name = consensus_name
            track.identity.last_good_face_time = time.time()
            track.identity.face_quality_count += 1
            track.identity.last_match_score = avg_score

            if old_member_id != consensus_id and self._on_identity_bind:
                try:
                    self._on_identity_bind({
                        'track_id': track_id,
                        'member_id': consensus_id,
                        'display_name': consensus_name,
                        'score': avg_score,
                    })
                except Exception:
                    pass

    def get_track_identity(self, track_id: int) -> dict:
        """获取 track 的当前身份"""
        track = self._tracks.get(track_id)
        if not track:
            return {'track_id': track_id, 'member_id': None, 'status': 'unknown'}
        slot = track.identity
        # 检查身份是否过期
        if slot.bound_member_id:
            if time.time() - slot.last_good_face_time > self.FACE_KEEP_ALIVE:
                # 解绑
                old_id = slot.bound_member_id
                slot.bound_member_id = None
                slot.bound_display_name = None
                if self._on_identity_unbind:
                    try:
                        self._on_identity_unbind({
                            'track_id': track_id,
                            'member_id': old_id,
                            'reason': 'timeout',
                        })
                    except Exception:
                        pass

        return {
            'track_id': track_id,
            'member_id': slot.bound_member_id,
            'display_name': slot.bound_display_name,
            'confidence': slot.last_match_score,
            'status': 'confirmed' if slot.bound_member_id else ('tentative' if slot.hypothesis_history else 'unknown'),
            'track_state': track.state.value,
        }

    def _get_active_identities(self) -> dict[int, dict]:
        """获取所有活跃 track 的身份映射"""
        result = {}
        for track_id, track in self._tracks.items():
            if track.state in (TrackState.ACTIVE, TrackState.LOST):
                result[track_id] = self.get_track_identity(track_id)
        return result

    # ─── 工具方法 ───────────────────────────────────────

    def get_track(self, track_id: int) -> Track | None:
        """获取指定 track"""
        return self._tracks.get(track_id)

    def get_active_tracks(self) -> list[Track]:
        """获取所有活跃 track"""
        return [t for t in self._tracks.values()
                if t.state in (TrackState.ACTIVE, TrackState.LOST)]

    def reset(self):
        """重置所有 track"""
        self._tracks.clear()
        self._removed_tracks.clear()
        self._next_id = 0
```

- [ ] **Step 2: Commit**

```bash
git add src/python/modules/tracking/person_tracker.py
git commit -m "feat(tracking): 实现 PersonTracker 核心 — 代价矩阵 + 匈牙利 + 级联匹配 + 生命周期 + 身份槽位"
```

---

## Phase 2: 多样本图库匹配

### Task 2.1: 数据库 schema v5 迁移 + face_gallery 支持

**Files:**
- Modify: `src/python/shared/database.py`

- [ ] **Step 1: 更新 SCHEMA_VERSION 和 init_database 迁移逻辑**

在 `database.py` 中找到 `SCHEMA_VERSION = 4`，改为 `5`，并在迁移逻辑中新增 v5 部分。

找到第 31 行：
```python
SCHEMA_VERSION = 4
```
改为：
```python
SCHEMA_VERSION = 5
```

找到 v4 迁移之后的代码（第 252 行附近 `if current_version < SCHEMA_VERSION:`），在其之前插入：

```python
        if current_version < 5:
            logger.info('Running schema migration to version 5 (face_gallery)...')
            # members 表新增 face_gallery 列
            try:
                conn.execute("ALTER TABLE members ADD COLUMN face_gallery TEXT")
            except Exception:
                pass  # 列可能已存在
            # unidentified 表也新增 face_gallery
            try:
                conn.execute("ALTER TABLE unidentified ADD COLUMN face_gallery TEXT")
            except Exception:
                pass
```

- [ ] **Step 2: 新增图库序列化/反序列化函数**

在 `database.py` 的 `serialize_embedding` 函数之后追加：

```python
# ─── 图库序列化 ─────────────────────────────────────────────

def serialize_gallery(embeddings: list[np.ndarray]) -> str | None:
    """人脸图库列表 → JSON 字符串（base64 编码每个 embedding）"""
    import base64
    import json
    if not embeddings:
        return None
    encoded = []
    for emb in embeddings:
        if emb is None:
            continue
        # L2 归一化
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        b64 = base64.b64encode(emb.astype(np.float32).tobytes()).decode('ascii')
        encoded.append(b64)
    return json.dumps(encoded) if encoded else None


def deserialize_gallery(gallery_json: str, dim: int = 512) -> list[np.ndarray]:
    """JSON 字符串 → 人脸图库列表"""
    import base64
    import json
    if not gallery_json:
        return []
    try:
        encoded = json.loads(gallery_json)
    except (json.JSONDecodeError, TypeError):
        return []
    embeddings = []
    for b64 in encoded:
        try:
            data = base64.b64decode(b64)
            emb = np.frombuffer(data, dtype=np.float32)
            if len(emb) == dim:
                embeddings.append(emb)
            else:
                logger.warning(f'Gallery embedding dim mismatch: expected {dim}, got {len(emb)}')
        except Exception as e:
            logger.warning(f'Gallery deserialize error: {e}')
    return embeddings


def search_by_face_gallery(query_emb: np.ndarray, top_n: int = 3,
                           threshold: float = 0.5) -> list[tuple[dict, float]]:
    """max-pooling 图库匹配：对每个 member 的所有 gallery embedding 取最高相似度

    Args:
        query_emb: 查询 embedding (512-d)
        top_n: 返回前 N 个结果
        threshold: 最低相似度阈值

    Returns:
        [(member_dict, best_score), ...] 按分数降序
    """
    if query_emb is None:
        return []

    query_emb = query_emb / (np.linalg.norm(query_emb) or 1.0)

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM members WHERE labeled = 1 AND (face_embedding IS NOT NULL OR face_gallery IS NOT NULL)"
        ).fetchall()

    results = []
    for row in rows:
        best_score = 0.0
        gallery = deserialize_gallery(row['face_gallery']) if row['face_gallery'] else []
        # 如果无图库，回退到旧版单 embedding
        if not gallery and row['face_embedding']:
            stored = deserialize_embedding(row['face_embedding'], 512)
            if stored is not None:
                best_score = cosine_similarity(query_emb, stored)
        else:
            for gallery_emb in gallery:
                score = cosine_similarity(query_emb, gallery_emb)
                if score > best_score:
                    best_score = score

        if best_score >= threshold:
            results.append((_row_to_dict(row), best_score))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_n]


def update_face_gallery(member_id: str, embeddings: list[np.ndarray]):
    """更新成员的 face_gallery"""
    gallery_json = serialize_gallery(embeddings)
    with get_connection() as conn:
        conn.execute(
            "UPDATE members SET face_gallery = ? WHERE id = ?",
            (gallery_json, member_id)
        )
    logger.debug(f'Face gallery updated for member {member_id[:8]}... ({len(embeddings)} embeddings)')


def append_to_face_gallery(member_id: str, embedding: np.ndarray, max_samples: int = 10):
    """向图库追加一个 embedding（增量扩展）"""
    with get_connection() as conn:
        row = conn.execute("SELECT face_gallery FROM members WHERE id = ?", (member_id,)).fetchone()
    if not row:
        return

    gallery = deserialize_gallery(row['face_gallery']) if row['face_gallery'] else []
    # 检查与已有样本的最小距离
    min_dist = min(
        (1.0 - cosine_similarity(embedding, g) for g in gallery),
        default=1.0
    )
    if min_dist > 0.2:  # 足够新颖才加入
        gallery.append(embedding)
        # 超过上限时移除离群点
        if len(gallery) > max_samples:
            mean_emb = np.mean(gallery, axis=0)
            mean_emb = mean_emb / (np.linalg.norm(mean_emb) or 1.0)
            distances = [1.0 - cosine_similarity(g, mean_emb) for g in gallery]
            worst_idx = distances.index(max(distances))
            gallery.pop(worst_idx)
        update_face_gallery(member_id, gallery)
        logger.debug(f'Appended to face gallery for {member_id[:8]}... (total: {len(gallery)})')


def audit_face_gallery(member_id: str, min_quality: float = 0.6):
    """质量审计：移除低质量样本（按与图库均值的距离判断）"""
    with get_connection() as conn:
        row = conn.execute("SELECT face_gallery FROM members WHERE id = ?", (member_id,)).fetchone()
    if not row or not row['face_gallery']:
        return

    gallery = deserialize_gallery(row['face_gallery'])
    if len(gallery) <= 2:
        return  # 样本太少不审计

    mean_emb = np.mean(gallery, axis=0)
    mean_emb = mean_emb / (np.linalg.norm(mean_emb) or 1.0)

    # 计算每个样本与均值的距离，移除最差的 20%
    distances = [1.0 - cosine_similarity(g, mean_emb) for g in gallery]
    threshold = np.percentile(distances, 80)  # top 80% 保留
    pruned = [g for g, d in zip(gallery, distances) if d <= threshold]

    if len(pruned) < len(gallery):
        update_face_gallery(member_id, pruned)
        logger.info(f'Face gallery audited for {member_id[:8]}...: {len(gallery)} → {len(pruned)}')
```

- [ ] **Step 3: Commit**

```bash
git add src/python/shared/database.py
git commit -m "feat(database): schema v5 迁移 + face_gallery 列 + 图库序列化/max-pooling匹配/增量更新/审计"
```

---

### Task 2.2: 注册流程改为 K-Means 聚类存储

**Files:**
- Modify: `src/python/modules/members/member_manager.py`

- [ ] **Step 1: 修改 `verify_and_register` 方法 — 从取平均改为 K-Means 聚类**

找到 `member_manager.py` 的 `verify_and_register` 方法（第 174 行），修改如下：

```python
    def verify_and_register(self) -> dict:
        """Step 4: 验证并完成注册（K-Means 聚类图库版本）"""
        if not self._registration:
            raise RuntimeError('No active registration session')

        if not self._registration.is_face_done or not self._registration.is_voice_done:
            raise RuntimeError('Not enough samples collected')

        # K-Means 聚类选出 K 个代表性 embedding
        face_samples = np.array(self._registration.face_samples)
        K = min(5, len(face_samples))  # K = min(5, N)
        gallery_embeddings = self._cluster_face_samples(face_samples, K)

        # 声纹取平均（声纹变化小于人脸，可以继续平均）
        voice_emb = np.mean(self._registration.voice_samples, axis=0)

        # 注册为成员（使用图库）
        member_id = add_member(
            display_name=self._registration.display_name,
            role=self._registration.role,
            face_emb=gallery_embeddings[0] if gallery_embeddings else None,  # 主 embedding
            voice_emb=voice_emb,
        )

        # 存储完整图库
        if len(gallery_embeddings) > 1:
            from src.python.shared.database import update_face_gallery
            update_face_gallery(member_id, gallery_embeddings)

        self._registration.step = RegistrationStep.DONE

        result = {
            'member_id': member_id,
            'display_name': self._registration.display_name,
            'role': self._registration.role,
            'face_samples': len(self._registration.face_samples),
            'voice_samples': len(self._registration.voice_samples),
            'gallery_size': len(gallery_embeddings),
        }

        logger.info(f'Registration complete: {self._registration.display_name} '
                    f'(role={self._registration.role}, gallery={len(gallery_embeddings)})')
        self._registration = None

        if self._on_registration_update:
            try:
                self._on_registration_update({'status': 'complete', **result})
            except Exception:
                pass

        return result

    @staticmethod
    def _cluster_face_samples(samples: np.ndarray, K: int) -> list[np.ndarray]:
        """K-Means 聚类选出代表性人脸 embedding

        Args:
            samples: (N, 512) 人脸 embedding 数组
            K: 聚类数

        Returns:
            K 个聚类中心（L2 归一化后的 numpy 数组列表）
        """
        if len(samples) <= K:
            # 样本太少，全部保留
            return [s.astype(np.float32) for s in samples]

        from scipy.cluster.vq import kmeans2

        # L2 归一化
        norms = np.linalg.norm(samples, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        normalized = samples / norms

        try:
            centroids, _ = kmeans2(normalized.astype(np.float64), K, minit='points', missing='warn')
        except Exception:
            # kmeans 失败时回退到均匀采样
            indices = np.linspace(0, len(samples) - 1, K, dtype=int)
            centroids = normalized[indices]

        # 确保每个中心 L2 归一化
        centroids_norm = np.linalg.norm(centroids, axis=1, keepdims=True)
        centroids_norm[centroids_norm == 0] = 1.0
        centroids = centroids / centroids_norm

        return [c.astype(np.float32) for c in centroids]
```

- [ ] **Step 2: Commit**

```bash
git add src/python/modules/members/member_manager.py
git commit -m "feat(members): 注册流程改为 K-Means 聚类存储多个代表性 face embedding"
```

---

### Task 2.3: 融合引擎适配图库匹配

**Files:**
- Modify: `src/python/modules/fusion/identity_fusion.py`

- [ ] **Step 1: 修改 `submit_face_evidence` — 使用 `search_by_face_gallery`**

找到 `identity_fusion.py` 第 128 行 `submit_face_evidence` 方法，将：
```python
matches = search_by_face_embedding(embedding, top_n=1)
```
改为：
```python
matches = search_by_face_gallery(embedding, top_n=1)
```

同时更新导入，在文件顶部的 import 中添加 `search_by_face_gallery, append_to_face_gallery`：
```python
from src.python.shared.database import (
    search_by_face_embedding,  # 保留用于回退
    search_by_face_gallery,    # 新增：图库匹配
    search_by_voice_embedding,
    search_unidentified_by_face,
    add_unidentified,
    update_unidentified,
    get_next_visitor_name,
    get_member,
    update_member,
    append_to_face_gallery,    # 新增：增量更新
)
```

- [ ] **Step 2: 在身份确认时追加 embedding 到图库**

找到 `_process_loop` 中的 `IdentityStatus.CONFIRMED` 分支（约第 320 行），在更新最后活跃时间后追加：

```python
                        case IdentityStatus.CONFIRMED:
                            if old_status != IdentityStatus.CONFIRMED:
                                await self._emit_identity_confirmed(self._state_to_dict())
                            # 更新最后活跃时间
                            if new_state.member_id:
                                now = time.time()
                                if now - self._last_active_update > 60:
                                    update_member(new_state.member_id, last_active_at=datetime.now(timezone.utc).isoformat())
                                    self._last_active_update = now
                                # 增量追加高质量 embedding 到图库
                                face_emb = self._last_face_embedding
                                if face_emb is not None and new_state.face_evidence.score > 0.6:
                                    append_to_face_gallery(new_state.member_id, face_emb)
```

- [ ] **Step 3: Commit**

```bash
git add src/python/modules/fusion/identity_fusion.py
git commit -m "feat(fusion): 集成图库匹配 (search_by_face_gallery) + 确认时增量追加 embedding"
```

---

## Phase 3: 质量门控 + 身份槽位 + 时序平滑

### Task 3.1: 实现质量门控模块

**Files:**
- Create: `src/python/modules/tracking/quality_gate.py`

- [ ] **Step 1: 实现 QualityGate 类和 FaceQualityResult**

```python
"""
Frank 人脸质量门控

对每帧检测到的人脸进行质量评估，低质量帧的 embedding 不参与身份匹配
（但仍可用于跟踪器的运动/外观匹配）
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger('frank.quality_gate')


@dataclass
class FaceQualityResult:
    """人脸质量评估结果"""
    passed: bool = True
    # 各项指标
    det_score: float = 0.0
    face_size_ratio: float = 0.0        # bbox 面积 / 帧面积
    yaw_deg: float = 0.0                # 偏航角
    pitch_deg: float = 0.0              # 俯仰角
    roll_deg: float = 0.0               # 翻滚角
    blur_score: float = 0.0             # Laplacian 方差
    occlusion_ratio: float = 0.0        # 遮挡比例 (0-1)
    visible_landmarks: int = 0           # 可见 landmarks 数
    total_landmarks: int = 68            # 总 landmarks 数
    # 失败原因
    failure_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'passed': self.passed,
            'det_score': round(self.det_score, 3),
            'face_size_ratio': round(self.face_size_ratio, 3),
            'yaw_deg': round(self.yaw_deg, 1),
            'pitch_deg': round(self.pitch_deg, 1),
            'blur_score': round(self.blur_score, 1),
            'occlusion_ratio': round(self.occlusion_ratio, 2),
            'failure_reasons': self.failure_reasons,
        }


class QualityGate:
    """人脸质量门控

    评估维度：
    1. 检测置信度 (det_score)
    2. 人脸大小 (bbox 面积占比)
    3. 人脸角度 (pitch/yaw/roll from landmarks)
    4. 模糊度 (Laplacian 方差)
    5. 遮挡比例 (landmarks 可见率)
    """

    # 阈值
    MIN_DET_SCORE = 0.5
    MIN_FACE_SIZE_RATIO = 0.05      # 人脸占帧面积至少 5%
    MAX_YAW_DEG = 45.0
    MAX_PITCH_DEG = 30.0
    MAX_ROLL_DEG = 45.0
    MIN_BLUR_SCORE = 100.0          # Laplacian 方差
    MIN_LANDMARK_RATIO = 0.7         # 至少 70% landmarks 可见

    def __init__(self):
        pass

    def evaluate(self,
                 face_info: dict,
                 frame: np.ndarray | None = None,
                 frame_width: int = 640,
                 frame_height: int = 480) -> FaceQualityResult:
        """评估单个人脸的质量

        Args:
            face_info: 来自 camera_pipeline 的 face dict
                {bbox, confidence, embedding, landmarks}
            frame: 原始帧（用于计算模糊度），可选
            frame_width: 帧宽度
            frame_height: 帧高度

        Returns:
            FaceQualityResult
        """
        result = FaceQualityResult()

        bbox = face_info.get('bbox', {})
        det_score = face_info.get('confidence', 0.0)
        landmarks = face_info.get('landmarks', [])

        # 1. 检测置信度
        result.det_score = det_score
        if det_score < self.MIN_DET_SCORE:
            result.passed = False
            result.failure_reasons.append(f'det_score_low({det_score:.2f}<{self.MIN_DET_SCORE})')

        # 2. 人脸大小
        face_w = bbox.get('width', 0) * frame_width
        face_h = bbox.get('height', 0) * frame_height
        face_area = face_w * face_h
        frame_area = frame_width * frame_height
        result.face_size_ratio = face_area / frame_area if frame_area > 0 else 0
        if result.face_size_ratio < self.MIN_FACE_SIZE_RATIO:
            result.passed = False
            result.failure_reasons.append(f'face_too_small({result.face_size_ratio:.3f}<{self.MIN_FACE_SIZE_RATIO})')

        # 3. 人脸角度（从 landmarks 估算）
        if landmarks and len(landmarks) >= 5:
            yaw, pitch, roll = self._estimate_head_pose(landmarks, frame_width, frame_height)
            result.yaw_deg = yaw
            result.pitch_deg = pitch
            result.roll_deg = roll
            if abs(yaw) > self.MAX_YAW_DEG:
                result.passed = False
                result.failure_reasons.append(f'yaw_too_large({yaw:.1f}>{self.MAX_YAW_DEG})')
            if abs(pitch) > self.MAX_PITCH_DEG:
                result.passed = False
                result.failure_reasons.append(f'pitch_too_large({pitch:.1f}>{self.MAX_PITCH_DEG})')

        # 4. 模糊度（从人脸 ROI 计算 Laplacian 方差）
        if frame is not None:
            blur = self._compute_blur(frame, bbox, frame_width, frame_height)
            result.blur_score = blur
            if blur < self.MIN_BLUR_SCORE:
                result.passed = False
                result.failure_reasons.append(f'blurry({blur:.1f}<{self.MIN_BLUR_SCORE})')

        # 5. 遮挡比例（从 landmarks 数量判断）
        result.total_landmarks = 68  # InsightFace 标准 68 点
        result.visible_landmarks = len(landmarks) if landmarks else 0
        if landmarks:
            result.occlusion_ratio = 1.0 - (len(landmarks) / result.total_landmarks)
            if result.occlusion_ratio > (1.0 - self.MIN_LANDMARK_RATIO):
                result.passed = False
                result.failure_reasons.append(
                    f'occluded({result.occlusion_ratio:.2f}>{(1.0 - self.MIN_LANDMARK_RATIO):.2f})'
                )

        return result

    def _estimate_head_pose(self, landmarks: list, width: int, height: int) -> tuple[float, float, float]:
        """从 2D landmarks 估算头部姿态角

        使用简化的几何方法：基于眼睛、鼻子、嘴巴关键点的相对位置估算
        Returns: (yaw, pitch, roll) in degrees
        """
        if len(landmarks) < 5:
            return 0.0, 0.0, 0.0

        try:
            pts = []
            for lm in landmarks:
                if isinstance(lm, dict):
                    pts.append([lm.get('x', 0) * width, lm.get('y', 0) * height])
                elif hasattr(lm, 'x'):
                    pts.append([lm.x * width, lm.y * height])
                else:
                    pts.append([lm[0] * width, lm[1] * height])
            pts = np.array(pts, dtype=np.float64)

            # InsightFace 106 点或 68 点 landmark 索引（取近似）
            # 左眼中心: 索引 33 (或 36-41 均值)
            # 右眼中心: 索引 87 (或 42-47 均值)
            # 鼻尖: 索引 51 (或 30)
            # 左嘴角: 索引 57 (或 48)
            # 右嘴角: 索引 93 (或 54)

            n_pts = len(pts)
            # 使用近似索引映射
            left_eye = pts[min(33, n_pts - 1)]
            right_eye = pts[min(87, n_pts - 1)]
            nose_tip = pts[min(51, n_pts - 1)]
            left_mouth = pts[min(57, n_pts - 1)]
            right_mouth = pts[min(93, n_pts - 1)]

            # Roll: 两眼连线与水平线的夹角
            eye_diff = right_eye - left_eye
            roll = np.degrees(np.arctan2(eye_diff[1], eye_diff[0]))

            # Yaw: 鼻尖偏离两眼中心的程度
            eye_center = (left_eye + right_eye) / 2
            mouth_center = (left_mouth + right_mouth) / 2
            nose_offset = nose_tip[0] - eye_center[0]
            face_width_est = np.linalg.norm(right_eye - left_eye)
            yaw = np.degrees(np.arctan2(nose_offset, face_width_est * 1.5)) * 2

            # Pitch: 鼻尖与嘴中心的垂直偏移
            vertical_offset = nose_tip[1] - mouth_center[1]
            pitch = np.degrees(np.arctan2(vertical_offset, face_width_est)) * 2

            return float(yaw), float(pitch), float(roll)
        except Exception as e:
            logger.debug(f'Head pose estimation error: {e}')
            return 0.0, 0.0, 0.0

    def _compute_blur(self, frame: np.ndarray, bbox: dict,
                      frame_width: int, frame_height: int) -> float:
        """计算人脸 ROI 的 Laplacian 方差（模糊度指标）"""
        try:
            x = int(max(0, bbox.get('x', 0) * frame_width))
            y = int(max(0, bbox.get('y', 0) * frame_height))
            w = int(min(frame_width - x, bbox.get('width', 0) * frame_width))
            h = int(min(frame_height - y, bbox.get('height', 0) * frame_height))
            if w <= 10 or h <= 10:
                return 0.0
            roi = frame[y:y+h, x:x+w]
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            return float(laplacian_var)
        except Exception:
            return 0.0
```

- [ ] **Step 2: Commit**

```bash
git add src/python/modules/tracking/quality_gate.py
git commit -m "feat(tracking): 实现质量门控模块 (角度/模糊/遮挡/大小/置信度五维评估)"
```

---

### Task 3.2: CameraPipeline 集成质量门控 + 输出 landmarks + 外观特征

**Files:**
- Modify: `src/python/modules/camera/camera_pipeline.py`

- [ ] **Step 1: 修改 `_detect_with_insightface` — 输出完整 landmarks 和质量结果**

找到 `_detect_with_insightface` 方法（第 426 行），修改如下：

```python
    def _detect_with_insightface(self, frame_rgb: np.ndarray) -> list[dict]:
        """InsightFace 检测+识别：输出 bbox + embedding + landmarks + quality"""
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
                    'quality_passed': False,
                    'quality_detail': None,
                }

                # 提取 landmarks（2D 关键点）
                if hasattr(face, 'landmark_2d_106') and face.landmark_2d_106 is not None:
                    face_info['landmarks'] = [
                        {'x': float(p[0]) / w, 'y': float(p[1]) / h}
                        for p in face.landmark_2d_106
                    ]
                elif hasattr(face, 'kps') and face.kps is not None:
                    face_info['landmarks'] = [
                        {'x': float(p[0]) / w, 'y': float(p[1]) / h}
                        for p in face.kps
                    ]

                # 质量评估（保留旧的小尺寸/低置信度过滤）
                if self._check_embedding_quality(face_info, w, h):
                    embedding = face.normed_embedding
                    face_info['embedding'] = embedding.astype(np.float32).tolist()
                    face_info['quality_passed'] = True

                faces.append(face_info)
        except Exception as e:
            logger.error(f'InsightFace detection error: {e}')
        return faces
```

- [ ] **Step 2: 在采集循环中注入外观特征提取和质量门控**

在 `_capture_loop` 的人脸检测部分之后（约第 346 行 `elif current_count > 0:` 分支），嵌入质量门控逻辑。由于采集循环已经比较复杂，我们改为在融合层处理质量门控，保持 camera_pipeline 职责单一。

目前 camera_pipeline 的变更已完成（输出 landmarks）。质量门控的最终评估将在融合引擎层完成。

- [ ] **Step 3: Commit**

```bash
git add src/python/modules/camera/camera_pipeline.py
git commit -m "feat(camera): 新增 landmarks 输出 + quality_passed 标记"
```

---

### Task 3.3: 融合引擎集成时序平滑

**Files:**
- Modify: `src/python/modules/fusion/identity_fusion.py`

- [ ] **Step 1: 修改 `_evaluate` 增加证据累积到 IdentityState**

在 `_evaluate` 方法中，增加对 `evidence_count` 和时序一致性的更严格处理：

这部分的改动已经在前面的 Task 2.3 中完成了基础框架。现在我们需要确保 `EVIDENCE_MIN_COUNT` 的提升（从 2 提升到 5）和融合决策阈值的微调。

修改 IdentityFusionEngine 类属性（第 74-83 行）：

```python
class IdentityFusionEngine:
    """双模态身份融合引擎（含时序平滑）"""

    # 融合决策阈值（优化后）
    HIGH_THRESHOLD = 0.7
    FACE_DOMINANT_THRESHOLD = 0.85
    LOW_THRESHOLD = 0.5
    CONFLICT_DIFF = 0.15
    EVIDENCE_MIN_COUNT = 5     # 提升到 5（与 IDENTITY_BIND_WINDOW 一致）
    TENTATIVE_TIMEOUT = 10.0
```

- [ ] **Step 2: 在 `_process_loop` 中集成 PersonTracker 身份绑定**

在 `_process_loop` 中的 CONFIRMED 分支，增加对 PersonTracker 的 `bind_identity` 调用。由于 PersonTracker 是在 main.py 层初始化的，我们通过回调机制传递：

```python
    # 新增回调：当融合引擎确认身份时，通知 PersonTracker 绑定
    def set_on_identity_recognized(self, callback: Callable):
        """人脸识别到 member 时回调（供 PersonTracker 的身份槽位绑定）"""
        self._on_identity_recognized = callback
```

在 `_process_loop` 的 CONFIRMED/TENTATIVE 分支中调用：

```python
                        case IdentityStatus.CONFIRMED | IdentityStatus.TENTATIVE:
                            # 通知外部进行身份槽位绑定
                            if new_state.member_id and self._on_identity_recognized:
                                try:
                                    self._on_identity_recognized({
                                        'member_id': new_state.member_id,
                                        'display_name': new_state.display_name,
                                        'confidence': new_state.confidence,
                                        'face_score': new_state.face_evidence.score,
                                    })
                                except Exception as e:
                                    logger.debug(f'on_identity_recognized error: {e}')
```

- [ ] **Step 3: Commit**

```bash
git add src/python/modules/fusion/identity_fusion.py
git commit -m "feat(fusion): 提升 EVIDENCE_MIN_COUNT 到 5 + 新增 on_identity_recognized 回调"
```

---

## Phase 4: 系统集成 + ReID + 参数调优

### Task 4.1: main.py 集成 PersonTracker 到系统管线

**Files:**
- Modify: `src/python/server/main.py`

- [ ] **Step 1: 导入新模块**

在 main.py 顶部新增导入：

```python
from src.python.modules.tracking.person_tracker import PersonTracker, Detection
from src.python.modules.tracking.reid_extractor import ReIDExtractor
from src.python.modules.tracking.quality_gate import QualityGate
```

- [ ] **Step 2: 初始化新组件**

在 `async def main()` 函数中，`fusion_engine` 初始化之后（约 1006 行）追加：

```python
    # 初始化跟踪模块
    reid_extractor = ReIDExtractor()
    person_tracker = PersonTracker(reid_extractor=reid_extractor)
    quality_gate = QualityGate()

    # 连接 fusion_engine → person_tracker 身份绑定
    fusion_engine.set_on_identity_recognized(
        lambda data: person_tracker.bind_identity(
            # track_id 通过 data 中的 track_id 字段传递
            track_id=data.get('track_id', 0),
            member_id=data['member_id'],
            display_name=data.get('display_name', ''),
            score=data.get('confidence', 0.0),
        )
    )
```

- [ ] **Step 3: 修改 `on_face_embedding` — 通过 PersonTracker 管线分发**

修改 `on_face_embedding` 函数（约第 695 行）：

```python
async def on_face_embedding(embedding: np.ndarray, confidence: float):
    """人脸 embedding → 质量门控 → PersonTracker → 融合引擎"""
    global person_tracker, quality_gate

    # 构建 Detection（简化版，仅含人脸信息）
    # 注意：实际使用中需要从 camera_pipeline 获取更多上下文
    # 这里暂保留直接提交到融合引擎的路径作为回退
    if fusion_engine:
        fusion_engine.submit_face_evidence(embedding, confidence)
```

- [ ] **Step 4: 在 shutdown 中清理 PersonTracker**

在 `shutdown()` 函数中（约 1224 行），追加：

```python
    if person_tracker:
        person_tracker.reset()
```

- [ ] **Step 5: Commit**

```bash
git add src/python/server/main.py
git commit -m "feat(server): 集成 PersonTracker + ReIDExtractor + QualityGate 到系统管线"
```

---

### Task 4.2: 多人交叉回滚验证 + 参数联调

**Files:**
- Modify: `src/python/modules/tracking/person_tracker.py` (追加交叉回滚逻辑)

- [ ] **Step 1: 在 PersonTracker 中追加交叉后外观一致性验证**

在 PersonTracker 类中追加方法：

```python
    def verify_post_cross(self, track_a_id: int, track_b_id: int) -> bool:
        """交叉后验证：检查两个 track 是否发生了 ID 交换

        在交叉结束后调用，比对交叉前后的外观特征。
        如果发现交换（track_a 现在的外观更像交叉前 track_b 的外观），回滚修正。

        Returns: True if swap detected and corrected
        """
        track_a = self._tracks.get(track_a_id)
        track_b = self._tracks.get(track_b_id)
        if not track_a or not track_b:
            return False
        if track_a.appearance_feature is None or track_b.appearance_feature is None:
            return False

        # 检查是否在最近移出的 track 中有更匹配的
        for removed in self._removed_tracks:
            if removed.appearance_feature is None:
                continue
            sim_a = float(np.dot(track_a.appearance_feature, removed.appearance_feature))
            sim_b = float(np.dot(track_b.appearance_feature, removed.appearance_feature))
            # 如果 track_a 更像 removed 而 track_b 不像，暗示发生了交换
            if sim_a > 0.8 and sim_b < 0.5:
                logger.warning(f'Post-cross identity swap detected! Correcting...')
                # 交换身份槽位
                track_a.identity, track_b.identity = track_b.identity, track_a.identity
                track_a.identity.track_id = track_a_id
                track_b.identity.track_id = track_b_id
                return True
        return False
```

- [ ] **Step 2: Commit**

```bash
git add src/python/modules/tracking/person_tracker.py
git commit -m "feat(tracking): 追加多人交叉后身份交换回滚验证"
```

---

### Task 4.3: 数据库 person_tracks 表 + 离线分析支持

**Files:**
- Modify: `src/python/shared/database.py`

- [ ] **Step 1: 在 schema v5 迁移中新建 person_tracks 表**

在 v5 迁移代码中追加：

```python
            # person_tracks 表（离线分析和调试）
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS person_tracks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        track_id INTEGER NOT NULL,
                        track_start REAL NOT NULL,
                        track_end REAL,
                        bound_member_id TEXT,
                        max_appearance_count INTEGER DEFAULT 0,
                        avg_face_score REAL DEFAULT 0.0
                    )
                """)
            except Exception:
                pass
```

- [ ] **Step 2: Commit**

```bash
git add src/python/shared/database.py
git commit -m "feat(database): 新增 person_tracks 表用于离线分析"
```

---

## 评审阶段

所有 Phase 实施完成后，启动以下评审 subagent：

### Review Agent 1: 安全与正确性审查

```
检查每个新增/修改文件的：
- 空指针/None 处理是否完备
- 数组越界保护
- 异常捕获是否过于宽泛（bare except）
- 数据库 SQL 注入风险
- 线程安全问题（tracking 模块是否需要在 asyncio 中加锁）
```

### Review Agent 2: 性能与内存审查

```
检查：
- numpy 数组是否及时释放
- deque 长度限制是否合理
- _removed_tracks 是否可能无限增长
- InsightFace/MediaPipe 回退路径是否受到影响
- 匈牙利算法 O(n³) 在极端人数下是否安全
```

### Review Agent 3: 架构一致性审查

```
验证：
- 新模块是否遵循现有代码风格（日志格式、命名约定）
- 回调接口是否与现有 fusion_engine 模式一致
- 数据库迁移是否兼容现有数据
- 旧版 face_embedding 存储的 member 是否能被新的 search_by_face_gallery 兼容
```

---

## 依赖关系

```
Phase 1 (Tracking) ─────┬──→ Phase 3 (Quality Gate + Slot + Smoothing)
                         │              │
Phase 2 (Gallery DB) ────┤              │
                         │              │
                         └──────────────┼──→ Phase 4 (Integration + ReID + Tuning)
                                        │
                                        └──→ Review Phase
```

Phase 1 和 Phase 2 可以并行实施（独立模块），Phase 3 依赖 Phase 1 的 Track/IdentitySlot 数据结构，Phase 4 依赖所有前序 Phase。
