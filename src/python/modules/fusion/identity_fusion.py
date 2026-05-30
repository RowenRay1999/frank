"""
Frank 身份融合引擎

并行人脸+声纹双模态融合：
- 接收 camera_pipeline 的人脸 embedding
- 接收 audio_pipeline 的声纹 embedding
- 各自独立搜索数据库 → 产出最佳匹配 + 分数
- 融合决策矩阵做最终判定
- 输出 identity.confirmed / identity.changing / identity.unknown 事件
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

import numpy as np

from src.python.shared.database import (
    search_by_face_embedding,
    search_by_voice_embedding,
    search_unidentified_by_face,
    add_unidentified,
    update_unidentified,
    get_next_visitor_name,
    get_member,
    update_member,
)

logger = logging.getLogger('frank.fusion')


class IdentityStatus(Enum):
    UNKNOWN = 'unknown'          # 未识别
    TENTATIVE = 'tentative'      # 暂确认（单模态或低置信）
    CONFIRMED = 'confirmed'      # 已确认（双模态通过）
    CONFLICT = 'conflict'         # 冲突（两路指向不同人）
    CHANGING = 'changing'        # 身份变更中


@dataclass
class ModalityEvidence:
    """单模态证据"""
    member_id: str | None = None
    display_name: str | None = None
    score: float = 0.0
    timestamp: float = 0.0
    source: str = ''  # 'face' | 'voice'

    @property
    def is_valid(self) -> bool:
        return self.member_id is not None and self.score > 0


@dataclass
class IdentityState:
    """当前身份假设状态"""
    member_id: str | None = None
    display_name: str | None = None
    role: str = 'guest'
    status: IdentityStatus = IdentityStatus.UNKNOWN
    confidence: float = 0.0
    face_evidence: ModalityEvidence = field(default_factory=ModalityEvidence)
    voice_evidence: ModalityEvidence = field(default_factory=ModalityEvidence)
    evidence_count: int = 0
    last_updated: float = 0.0
    tentative_since: float | None = None


class IdentityFusionEngine:
    """双模态身份融合引擎"""

    # 融合决策阈值
    HIGH_THRESHOLD = 0.7       # 高置信度阈值
    FACE_DOMINANT_THRESHOLD = 0.85  # 人脸可独立拍板的阈值
    LOW_THRESHOLD = 0.5        # 低置信度阈值
    CONFLICT_DIFF = 0.15       # 两路指向不同人且分差小于此值视为冲突
    EVIDENCE_MIN_COUNT = 2     # 最少证据累积次数才确认
    TENTATIVE_TIMEOUT = 10.0   # 暂确认超时（秒），过期未确认降级为 unknown

    def __init__(self):
        self._state = IdentityState()
        self._face_queue: deque[ModalityEvidence] = deque(maxlen=10)
        self._voice_queue: deque[ModalityEvidence] = deque(maxlen=10)
        self._running = False
        self._process_task: asyncio.Task | None = None
        self._last_face_event_time = 0.0
        self._last_voice_event_time = 0.0
        self._last_evaluated = 0.0  # WR-08: track last evaluation time
        self._last_active_update = 0.0  # WR-10: throttle update_member calls
        self._last_face_embedding: np.ndarray | None = None  # 最近人脸嵌入（供自动发现使用）
        self._unidentified_cooldown: dict[str, float] = {}  # embedding_hash → last_seen

        # 回调
        self._on_identity_confirmed: Callable | None = None
        self._on_identity_changing: Callable | None = None
        self._on_identity_unknown: Callable | None = None
        self._on_error: Callable | None = None

    # ─── 回调设置 ───────────────────────────────────────

    def set_on_identity_confirmed(self, callback: Callable):
        self._on_identity_confirmed = callback

    def set_on_identity_changing(self, callback: Callable):
        self._on_identity_changing = callback

    def set_on_identity_unknown(self, callback: Callable):
        self._on_identity_unknown = callback

    def set_on_error(self, callback: Callable):
        self._on_error = callback

    # ─── 证据接收 ───────────────────────────────────────

    def submit_face_evidence(self, embedding: np.ndarray, confidence: float):
        """接收人脸 embedding 证据"""
        if not self._running:
            return

        self._last_face_embedding = embedding  # 保存原始嵌入供自动发现使用

        matches = search_by_face_embedding(embedding, top_n=1)
        ev = ModalityEvidence(
            member_id=matches[0][0]['id'] if matches else None,
            display_name=matches[0][0]['display_name'] if matches else None,
            score=matches[0][1] if matches else 0.0,
            timestamp=time.time(),
            source='face',
        )
        self._face_queue.append(ev)
        self._last_face_event_time = time.time()
        logger.debug(f'Face evidence: {ev.display_name} score={ev.score:.3f}')

    def submit_voice_evidence(self, embedding: np.ndarray, confidence: float):
        """接收声纹 embedding 证据"""
        if not self._running:
            return

        matches = search_by_voice_embedding(embedding, top_n=1)
        ev = ModalityEvidence(
            member_id=matches[0][0]['id'] if matches else None,
            display_name=matches[0][0]['display_name'] if matches else None,
            score=matches[0][1] if matches else 0.0,
            timestamp=time.time(),
            source='voice',
        )
        self._voice_queue.append(ev)
        self._last_voice_event_time = time.time()
        logger.debug(f'Voice evidence: {ev.display_name} score={ev.score:.3f}')

    # ─── 融合决策 ───────────────────────────────────────

    def _evaluate(self) -> IdentityState:
        """运行融合决策矩阵"""
        face_ev = self._face_queue[-1] if self._face_queue else ModalityEvidence()
        voice_ev = self._voice_queue[-1] if self._voice_queue else ModalityEvidence()

        f_score = face_ev.score
        v_score = voice_ev.score
        f_id = face_ev.member_id
        v_id = voice_ev.member_id

        new_state = IdentityState(
            face_evidence=face_ev,
            voice_evidence=voice_ev,
            last_updated=time.time(),
        )

        # Case 1: 两路都高置信度
        if f_score >= self.HIGH_THRESHOLD and v_score >= self.HIGH_THRESHOLD:
            if f_id == v_id:
                # 两路同意 → 确认
                new_state.member_id = f_id
                new_state.display_name = face_ev.display_name
                new_state.status = IdentityStatus.CONFIRMED
                new_state.confidence = max(f_score, v_score)
                new_state.evidence_count = self._state.evidence_count + 1
            else:
                # 两路指向不同人 → 冲突
                new_state.status = IdentityStatus.CONFLICT
                new_state.confidence = max(f_score, v_score)
                # 取高分者
                if f_score >= v_score:
                    new_state.member_id = f_id
                    new_state.display_name = face_ev.display_name
                else:
                    new_state.member_id = v_id
                    new_state.display_name = voice_ev.display_name

        # Case 2: 人脸主导（高置信人脸 + 低声纹）
        elif f_score >= self.FACE_DOMINANT_THRESHOLD:
            new_state.member_id = f_id
            new_state.display_name = face_ev.display_name
            new_state.status = IdentityStatus.TENTATIVE
            new_state.confidence = f_score * 0.8  # 单模态打折扣
            new_state.tentative_since = time.time()

        # Case 3: 声纹主导（低声纹高 + 低人脸）
        elif v_score >= self.HIGH_THRESHOLD and f_score < self.LOW_THRESHOLD:
            new_state.member_id = v_id
            new_state.display_name = voice_ev.display_name
            new_state.status = IdentityStatus.TENTATIVE
            new_state.confidence = v_score * 0.8
            new_state.tentative_since = time.time()

        # Case 4: 两路都低 → 未识别
        else:
            new_state.status = IdentityStatus.UNKNOWN
            new_state.confidence = max(f_score, v_score)

        # 证据累积
        if new_state.member_id == self._state.member_id and self._state.member_id:
            new_state.evidence_count = self._state.evidence_count + 1

        # 获取角色
        if new_state.member_id:
            member = get_member(new_state.member_id)
            if member:
                new_state.role = member.get('role', 'guest')
                new_state.display_name = member.get('display_name', new_state.display_name)

        # 证据累积门控：未达到最小证据数时降级为暂确认
        if new_state.evidence_count < self.EVIDENCE_MIN_COUNT and new_state.status == IdentityStatus.CONFIRMED:
            new_state.status = IdentityStatus.TENTATIVE

        return new_state

    # ─── 自动发现 ───────────────────────────────────────

    def _check_auto_discovery(self, face_emb: np.ndarray) -> dict | None:
        """检查是否触发自动发现"""
        # 先搜索未标识人物
        unid_matches = search_unidentified_by_face(face_emb, threshold=0.6)
        if unid_matches:
            person, score = unid_matches[0]
            update_unidentified(person['id'], face_emb=face_emb)
            logger.info(f'Auto-discovery: matched existing unidentified {person["display_name"]} (appearances: {person["appearance_count"] + 1})')
            return person

        # 检查是否满足自动发现条件：30 秒冷却
        emb_hash = hash(face_emb.tobytes())
        now = time.time()
        if emb_hash in self._unidentified_cooldown:
            if now - self._unidentified_cooldown[emb_hash] < 30:
                return None

        self._unidentified_cooldown[emb_hash] = now

        # 创建新的未标识人物
        name = get_next_visitor_name()
        person_id = add_unidentified(name, face_emb=face_emb)
        logger.info(f'Auto-discovery: new unidentified person {name} ({person_id[:8]}...)')
        return {'id': person_id, 'display_name': name, 'appearance_count': 1}

    # ─── 主循环 ───────────────────────────────────────

    async def start(self):
        """启动融合引擎"""
        self._running = True
        self._process_task = asyncio.create_task(self._process_loop())
        logger.info('Identity fusion engine started')

    async def stop(self):
        """停止融合引擎"""
        self._running = False
        if self._process_task:
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass
            self._process_task = None
        logger.info('Identity fusion engine stopped')

    async def _process_loop(self):
        """主处理循环：监控队列 + 运行融合决策"""
        while self._running:
            try:
                # 检查是否有新证据
                has_new = (self._last_face_event_time > self._last_evaluated or
                           self._last_voice_event_time > self._last_evaluated)

                if has_new:
                    new_state = self._evaluate()
                    self._last_evaluated = time.time()

                    # 身份变更检测
                    if self._state.status == IdentityStatus.CONFIRMED and \
                       new_state.member_id and \
                       new_state.member_id != self._state.member_id:
                        await self._emit_identity_changing({
                            'from': {'id': self._state.member_id, 'name': self._state.display_name},
                            'to': {'id': new_state.member_id, 'name': new_state.display_name},
                        })

                    old_status = self._state.status
                    self._state = new_state

                    # 基于新状态触发事件
                    match new_state.status:
                        case IdentityStatus.CONFIRMED:
                            if old_status != IdentityStatus.CONFIRMED:
                                await self._emit_identity_confirmed(self._state_to_dict())
                            # 更新最后活跃时间（限频：最多每 60 秒一次）
                            if new_state.member_id:
                                now = time.time()
                                if now - self._last_active_update > 60:
                                    update_member(new_state.member_id, last_active_at=datetime.now(timezone.utc).isoformat())
                                    self._last_active_update = now

                        case IdentityStatus.CONFLICT | IdentityStatus.TENTATIVE:
                            # 暂确认：等待更多证据
                            if new_state.tentative_since and \
                               time.time() - new_state.tentative_since > self.TENTATIVE_TIMEOUT:
                                logger.info('Tentative identity timed out, resetting')
                                self._state = IdentityState()

                        case IdentityStatus.UNKNOWN:
                            if old_status != IdentityStatus.UNKNOWN:
                                await self._emit_identity_unknown({})
                            # 自动发现：尝试匹配或创建未标识访客记录
                            if new_state.face_evidence.is_valid and new_state.face_evidence.member_id is None:
                                face_emb = self._last_face_embedding
                                if face_emb is not None:
                                    self._check_auto_discovery(face_emb)

                # 检查超时
                if self._state.status == IdentityStatus.TENTATIVE and self._state.tentative_since:
                    if time.time() - self._state.tentative_since > self.TENTATIVE_TIMEOUT:
                        self._state = IdentityState()
                        await self._emit_identity_unknown({'reason': 'tentative_timeout'})

                await asyncio.sleep(0.2)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f'Fusion process loop error: {e}')
                await asyncio.sleep(0.5)

    # ─── 公共接口 ───────────────────────────────────────

    def get_current_identity(self) -> dict:
        """获取当前身份信息"""
        return self._state_to_dict()

    def reset_identity(self):
        """重置身份状态（用于手动退出或登出）"""
        self._state = IdentityState()
        self._face_queue.clear()
        self._voice_queue.clear()
        logger.info('Identity state reset')

    def _state_to_dict(self) -> dict:
        s = self._state
        return {
            'member_id': s.member_id,
            'display_name': s.display_name,
            'role': s.role,
            'status': s.status.value,
            'confidence': s.confidence,
            'evidence_count': s.evidence_count,
            'face_score': s.face_evidence.score,
            'voice_score': s.voice_evidence.score,
        }

    # ─── 事件发送 ───────────────────────────────────────

    async def _emit_identity_confirmed(self, identity: dict):
        if self._on_identity_confirmed:
            try:
                if asyncio.iscoroutinefunction(self._on_identity_confirmed):
                    await self._on_identity_confirmed(identity)
                else:
                    self._on_identity_confirmed(identity)
            except Exception as e:
                logger.error(f'on_identity_confirmed error: {e}')

    async def _emit_identity_changing(self, change_info: dict):
        if self._on_identity_changing:
            try:
                if asyncio.iscoroutinefunction(self._on_identity_changing):
                    await self._on_identity_changing(change_info)
                else:
                    self._on_identity_changing(change_info)
            except Exception as e:
                logger.error(f'on_identity_changing error: {e}')

    async def _emit_identity_unknown(self, info: dict):
        if self._on_identity_unknown:
            try:
                if asyncio.iscoroutinefunction(self._on_identity_unknown):
                    await self._on_identity_unknown(info)
                else:
                    self._on_identity_unknown(info)
            except Exception as e:
                logger.error(f'on_identity_unknown error: {e}')
