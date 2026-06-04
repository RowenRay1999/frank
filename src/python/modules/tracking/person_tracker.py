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
    face_quality: Optional[Any] = None                 # FaceQualityResult (lazy import to avoid circular)
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

    def get_consensus(self, window: int = 5) -> tuple:
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

    def update_kf(self, detection: 'Detection'):
        """Kalman 更新（用检测结果修正）"""
        x, y, w, h = detection.bbox
        z = np.array([x, y, w, h], dtype=np.float64)

        # 观测矩阵 H (4x8): 只观测位置+大小
        H = np.zeros((4, 8))
        H[0, 0] = H[1, 1] = H[2, 2] = H[3, 3] = 1.0

        # 观测噪声 R
        R = np.eye(4) * 0.05
        R[2, 2] = R[3, 3] = 0.01  # 大小观测更准

        # Kalman gain (带正则化，防止奇异矩阵)
        S = H @ self.kf_covariance @ H.T + R
        try:
            K = self.kf_covariance @ H.T @ np.linalg.inv(S + np.eye(4) * 0.001)
        except np.linalg.LinAlgError:
            # 退化情况：跳过更新，保持预测状态
            return

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


class PersonTracker:
    """多人时空跟踪器（DeepSORT 范式）

    每帧调用 update() 传入 Detection 列表，返回 (track_id → identity) 映射。
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
    CROSS_IOU_THRESHOLD = 0.3

    def __init__(self, reid_extractor=None):
        self._tracks: dict[int, Track] = {}
        self._next_id = 0
        self._reid = reid_extractor
        self._removed_tracks: list[Track] = []
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
        self._on_identity_bind = callback

    def set_on_identity_unbind(self, callback: Callable):
        self._on_identity_unbind = callback

    def set_on_identity_switch(self, callback: Callable):
        self._on_identity_switch = callback

    def set_on_track_created(self, callback: Callable):
        self._on_track_created = callback

    def set_on_track_removed(self, callback: Callable):
        self._on_track_removed = callback

    # ─── 主更新入口 ───────────────────────────────────────

    def update(self, detections: list[Detection], frame: np.ndarray | None = None,
               timestamp: float | None = None) -> dict[int, dict]:
        """每帧调用，处理一批检测结果"""
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
                except Exception as e:
                    logger.warning(f'on_track_created callback error: {e}')

        # Step 7: 处理未匹配的 track（丢失）
        for track_id in unmatched_tracks:
            track = self._tracks[track_id]
            track.lost_since = time.time() if track.lost_since == 0 else track.lost_since
            if track.state == TrackState.ACTIVE:
                track.state = TrackState.LOST
                logger.debug(f'Track {track_id} lost')
            time_lost = now - track.lost_since
            if time_lost > self.LOST_TIMEOUT / 30.0:
                track.state = TrackState.REMOVED
                self._removed_tracks.append(track)
                self._cleanup_removed_tracks(now)
                del self._tracks[track_id]
                if self._on_track_removed:
                    try:
                        self._on_track_removed({'track_id': track_id, 'track': track})
                    except Exception as e:
                        logger.warning(f'on_track_removed callback error: {e}')

        # Step 8: 返回当前活跃的 track 身份映射
        return self._get_active_identities()

    # ─── 代价矩阵 ───────────────────────────────────────

    def _compute_cost_matrix(self, detections: list[Detection],
                              tracks: list[Track]) -> np.ndarray:
        """计算三维联合代价矩阵 Cost = α × motion + β × appearance + γ × face"""
        M, N = len(tracks), len(detections)
        cost = np.full((M, N), 1e9, dtype=np.float64)

        for i, track in enumerate(tracks):
            for j, det in enumerate(detections):
                motion_cost = self._motion_cost(track, det)
                app_cost = self._appearance_cost(track, det)
                face_cost = self._face_cost(track, det)

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

        S = track.kf_covariance[:4, :4]
        try:
            diff = z - pred
            inv_S = np.linalg.inv(S + np.eye(4) * 0.001)
            mahalanobis = np.sqrt(diff @ inv_S @ diff)
            return min(float(mahalanobis), 10.0)
        except np.linalg.LinAlgError:
            return min(float(np.linalg.norm(diff)), 10.0)

    def _appearance_cost(self, track: Track, det: Detection) -> float:
        """外观特征余弦距离"""
        if track.appearance_feature is None or det.appearance_feature is None:
            return 0.5
        return float(1.0 - np.dot(track.appearance_feature, det.appearance_feature))

    def _face_cost(self, track: Track, det: Detection) -> float:
        """人脸 embedding 余弦距离"""
        if track.last_face_embedding is None or det.face_embedding is None:
            return 0.5
        return float(1.0 - np.dot(track.last_face_embedding, det.face_embedding))

    def _detect_cross_scenario(self, track: Track, all_tracks: list[Track]) -> float:
        """检测当前 track 是否处于交叉场景"""
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
        """匈牙利算法最优分配"""
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
        """级联匹配：优先匹配丢失时间短的 track"""
        active_tracks = [t for t in self._tracks.values()
                        if t.state in (TrackState.ACTIVE, TrackState.LOST, TrackState.CANDIDATE)]

        if not active_tracks:
            return {}, set(range(len(detections))), set()

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

        # 第二轮：丢失 track 与剩余检测
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
        """简单的检测-轨道匹配（用于低分检测）"""
        tracks = [self._tracks[tid] for tid in track_ids]
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
        """尝试将新 detection 与最近移除的 track 做外观 ReID 匹配"""
        if det.appearance_feature is None:
            return False
        for removed in self._removed_tracks:
            if removed.appearance_feature is None:
                continue
            similarity = float(np.dot(det.appearance_feature, removed.appearance_feature))
            if similarity > 0.7:
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
                if self._on_identity_switch:
                    try:
                        self._on_identity_switch({
                            'track_id': track_id,
                            'from': old_member_id,
                            'to': consensus_id,
                            'to_name': consensus_name,
                            'score': avg_score,
                        })
                    except Exception as e:
                        logger.warning(f'on_identity_switch callback error: {e}')
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
                except Exception as e:
                    logger.warning(f'on_identity_bind callback error: {e}')

    def get_track_identity(self, track_id: int) -> dict:
        """获取 track 的当前身份"""
        track = self._tracks.get(track_id)
        if not track:
            return {'track_id': track_id, 'member_id': None, 'status': 'unknown'}
        slot = track.identity
        if slot.bound_member_id:
            if time.time() - slot.last_good_face_time > self.FACE_KEEP_ALIVE:
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
                    except Exception as e:
                        logger.warning(f'on_identity_unbind callback error: {e}')

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
        return self._tracks.get(track_id)

    def get_active_tracks(self) -> list[Track]:
        return [t for t in self._tracks.values()
                if t.state in (TrackState.ACTIVE, TrackState.LOST)]

    def reset(self):
        self._tracks.clear()
        self._removed_tracks.clear()
        self._next_id = 0

    # ─── 交叉回滚验证 ───────────────────────────────────────

    def verify_post_cross(self, track_a_id: int, track_b_id: int) -> bool:
        """交叉后验证：检查两个 track 是否发生了 ID 交换"""
        track_a = self._tracks.get(track_a_id)
        track_b = self._tracks.get(track_b_id)
        if not track_a or not track_b:
            return False
        if track_a.appearance_feature is None or track_b.appearance_feature is None:
            return False

        for removed in self._removed_tracks:
            if removed.appearance_feature is None:
                continue
            sim_a = float(np.dot(track_a.appearance_feature, removed.appearance_feature))
            sim_b = float(np.dot(track_b.appearance_feature, removed.appearance_feature))
            if sim_a > 0.8 and sim_b < 0.5:
                logger.warning(f'Post-cross identity swap detected! Correcting...')
                track_a.identity, track_b.identity = track_b.identity, track_a.identity
                track_a.identity.track_id = track_a_id
                track_b.identity.track_id = track_b_id
                return True
        return False
