"""
Frank 多人模式管理器 (Phase 4)

检测多人 → 模式切换 → 身份队列管理 → 并行会话协调
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger('frank.multi_person')


class MultiPersonState(Enum):
    SINGLE = 'single'           # 单人模式
    ENTERING = 'entering'       # 检测到多人，确认中（3s 窗口）
    MULTI_AUTH = 'multi_auth'   # 识别所有人身份
    MULTI_WAIT = 'multi_wait'   # 所有人已识别，静默等待指令
    MULTI_CHAT = 'multi_chat'   # 至少一人在对话中


@dataclass
class PersonSlot:
    """一个人的身份槽位"""
    person_id: str
    display_name: str
    role: str = 'guest'
    face_embedding: Any = None
    detected_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    session_active: bool = False


class MultiPersonManager:
    """多人模式管理器"""

    ENTER_THRESHOLD = 3.0     # 多人确认时间 (秒)
    EXIT_THRESHOLD = 5.0      # 退出多人确认时间 (秒)
    REVERT_THRESHOLD = 10.0   # 回退单人时间 (秒)

    def __init__(self):
        self._state = MultiPersonState.SINGLE
        self._persons: dict[str, PersonSlot] = {}  # person_id → slot
        self._multi_start: float | None = None
        self._single_start: float | None = None
        self._primary_person_id: str | None = None
        self._person_queue: list[str] = []  # person_id 队列

        self._on_state_change: Callable | None = None
        self._on_person_join: Callable | None = None
        self._on_person_leave: Callable | None = None

    def set_on_state_change(self, cb: Callable): self._on_state_change = cb
    def set_on_person_join(self, cb: Callable): self._on_person_join = cb
    def set_on_person_leave(self, cb: Callable): self._on_person_leave = cb

    @property
    def state(self) -> MultiPersonState:
        return self._state

    @property
    def person_count(self) -> int:
        return len(self._persons)

    @property
    def is_multi(self) -> bool:
        return self._state != MultiPersonState.SINGLE

    def update_person(self, person_id: str, display_name: str = '', role: str = 'guest',
                       face_embedding=None):
        """更新/添加一个人"""
        now = time.time()

        if person_id in self._persons:
            self._persons[person_id].last_seen = now
            if face_embedding is not None:
                self._persons[person_id].face_embedding = face_embedding
        else:
            slot = PersonSlot(
                person_id=person_id,
                display_name=display_name or f'Person-{person_id[:6]}',
                role=role,
                face_embedding=face_embedding,
            )
            self._persons[person_id] = slot
            self._person_queue.append(person_id)
            logger.info(f'Person joined: {slot.display_name} (role={role}, total={len(self._persons)})')
            if self._on_person_join:
                self._on_person_join({
                    'person_id': person_id, 'display_name': slot.display_name,
                    'role': role, 'total': len(self._persons),
                })

        self._check_state_transition()

    def remove_person(self, person_id: str):
        """移除一个人"""
        if person_id in self._persons:
            name = self._persons[person_id].display_name
            del self._persons[person_id]
            if person_id in self._person_queue:
                self._person_queue.remove(person_id)
            if self._primary_person_id == person_id:
                self._primary_person_id = self._person_queue[0] if self._person_queue else None
            logger.info(f'Person left: {name} (total={len(self._persons)})')
            if self._on_person_leave:
                self._on_person_leave({
                    'person_id': person_id, 'display_name': name,
                    'total': len(self._persons),
                })

        self._check_state_transition()

    def _check_state_transition(self):
        """检查并触发模式切换"""
        count = len(self._persons)
        now = time.time()

        match self._state:
            case MultiPersonState.SINGLE:
                if count >= 2:
                    if self._multi_start is None:
                        self._multi_start = now
                    elif now - self._multi_start >= self.ENTER_THRESHOLD:
                        self._transition(MultiPersonState.ENTERING)
                        self._multi_start = None
                else:
                    self._multi_start = None

            case MultiPersonState.ENTERING | MultiPersonState.MULTI_AUTH | \
                 MultiPersonState.MULTI_WAIT | MultiPersonState.MULTI_CHAT:
                if count < 2:
                    if self._single_start is None:
                        self._single_start = now
                    elif now - self._single_start >= self.REVERT_THRESHOLD:
                        self._transition(MultiPersonState.SINGLE)
                        self._single_start = None
                else:
                    self._single_start = None

    async def on_all_identified(self):
        """所有人身份识别完成 → MULTI_WAIT"""
        if self._state == MultiPersonState.ENTERING:
            self._transition(MultiPersonState.MULTI_AUTH)
            # 短暂延迟后进入等待
            await asyncio.sleep(0.5)
            self._transition(MultiPersonState.MULTI_WAIT)
            logger.info(f'All {len(self._persons)} persons identified, entering multi-wait')

    def activate_session(self, person_id: str):
        """激活某人的会话"""
        if person_id in self._persons:
            self._persons[person_id].session_active = True
            if self._state == MultiPersonState.MULTI_WAIT:
                self._transition(MultiPersonState.MULTI_CHAT)

    def deactivate_session(self, person_id: str):
        """结束某人的会话"""
        if person_id in self._persons:
            self._persons[person_id].session_active = False
        # 检查是否所有会话都结束
        if not any(p.session_active for p in self._persons.values()):
            if self._state == MultiPersonState.MULTI_CHAT:
                self._transition(MultiPersonState.MULTI_WAIT)

    def get_primary_person(self) -> PersonSlot | None:
        """获取主用户（Owner 优先，否则先到先服务）"""
        # Owner 优先
        for pid in self._person_queue:
            if pid in self._persons and self._persons[pid].role == 'owner':
                self._primary_person_id = pid
                return self._persons[pid]
        # 先到先服务
        for pid in self._person_queue:
            if pid in self._persons:
                self._primary_person_id = pid
                return self._persons[pid]
        return None

    def get_secondary_persons(self) -> list[PersonSlot]:
        """获取排在后面的用户"""
        primary = self.get_primary_person()
        if not primary:
            return []
        return [
            self._persons[pid]
            for pid in self._person_queue
            if pid in self._persons and pid != primary.person_id
        ]

    def get_status(self) -> dict:
        return {
            'state': self._state.value,
            'person_count': len(self._persons),
            'is_multi': self.is_multi,
            'persons': [
                {
                    'person_id': pid,
                    'display_name': p.display_name,
                    'role': p.role,
                    'session_active': p.session_active,
                    'detected_seconds_ago': time.time() - p.detected_at,
                }
                for pid, p in self._persons.items()
            ],
            'primary': self._primary_person_id,
            'queue': [pid for pid in self._person_queue if pid in self._persons],
        }

    def _transition(self, new_state: MultiPersonState):
        old = self._state
        self._state = new_state
        logger.info(f'Multi-person: {old.value} → {new_state.value}')
        if self._on_state_change:
            self._on_state_change({
                'from': old.value, 'to': new_state.value,
                'person_count': len(self._persons),
            })
