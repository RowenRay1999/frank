"""
Frank 核心状态机

状态: Idle → Aware → Auth → Chat

Phase 1: 基础线性流转，不含多人模式分支
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger('frank.state_machine')


class State(Enum):
    IDLE = 'Idle'       # 待机：无人检测到
    AWARE = 'Aware'     # 检测到人：有人脸或声音
    AUTH = 'Auth'       # 身份确认：人脸持续识别
    CHAT = 'Chat'       # 对话中：唤醒词触发


class StateMachine:
    """Frank 核心状态机"""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

        # 超时配置（秒）
        self.timeout_aware_to_idle = self.config.get('timeout_aware_to_idle', 30)
        self.timeout_auth_delay = self.config.get('timeout_auth_delay', 2)
        self.timeout_chat_to_auth = self.config.get('timeout_chat_to_auth', 300)
        self.timeout_auth_to_idle = self.config.get('timeout_auth_to_idle', 60)

        # 当前状态
        self._state = State.IDLE
        self._state_entered_at = time.time()
        self._face_present_since: float | None = None
        self._last_activity_at: float | None = None
        self._face_detected = False
        self._wake_word_detected = False
        self._current_identity: dict | None = None  # Phase 2: 当前身份上下文

        # 回调
        self._on_state_changed: Callable | None = None

        # 超时监控任务
        self._timeout_task: asyncio.Task | None = None
        self._running = False

    # ─── 公共接口 ────────────────────────────────────────

    def set_on_state_changed(self, callback: Callable):
        """设置状态变更回调"""
        self._on_state_changed = callback

    def set_identity(self, identity: dict):
        """Phase 2: 设置当前身份上下文"""
        self._current_identity = identity

    def get_current_state(self) -> dict[str, Any]:
        """返回当前状态信息（含身份上下文）"""
        result = {
            'state': self._state.value,
            'time_in_state': time.time() - self._state_entered_at,
            'state_entered_at': datetime.fromtimestamp(self._state_entered_at, tz=timezone.utc).isoformat(),
        }
        if self._current_identity:
            result['identity'] = {
                'member_id': self._current_identity.get('member_id'),
                'display_name': self._current_identity.get('display_name'),
                'role': self._current_identity.get('role', 'guest'),
            }
        return result

    def get_state_provider(self) -> Callable:
        """返回获取当前状态的函数（供其他模块使用）"""
        return self.get_current_state

    def transition(self, to_state: str, trigger: str = 'manual') -> dict[str, Any]:
        """手动状态转换"""
        new_state = State(to_state)
        return self._do_transition(new_state, trigger)

    def on_event(self, event: str, payload: dict[str, Any] | None = None):
        """处理外部事件（来自摄像头/音频管线）"""
        logger.debug(f'Event: {event}, current state: {self._state.value}')

        match event:
            case 'face_detected':
                self._face_detected = True
                self._last_activity_at = time.time()

                if self._state == State.IDLE:
                    self._face_present_since = time.time()
                    self._do_transition(State.AWARE, 'face_detected')

                elif self._state == State.AWARE:
                    if self._face_present_since is None:
                        self._face_present_since = time.time()
                    # 人脸持续足够时间 → 身份确认
                    elif time.time() - self._face_present_since >= self.timeout_auth_delay:
                        self._face_present_since = None
                        self._do_transition(State.AUTH, 'face_continuous')

            case 'face_lost':
                self._face_detected = False
                self._face_present_since = None

            case 'voice_start':
                self._last_activity_at = time.time()
                if self._state == State.IDLE:
                    self._do_transition(State.AWARE, 'voice_start')

            case 'wake_word':
                self._wake_word_detected = True
                if self._state in (State.AUTH, State.CHAT):
                    self._last_activity_at = time.time()
                    self._do_transition(State.CHAT, 'wake_word')

            case 'identity_confirmed':
                # Phase 2: 融合引擎确认身份 → 进入 Auth
                self._last_activity_at = time.time()
                self._do_transition(State.AUTH, 'identity_confirmed')

            case 'identity_changing':
                # Phase 2: 身份变更 → 重新确认
                self._do_transition(State.AWARE, 'identity_changing')

            case 'gesture_detected':
                # Phase 5: 手势驱动状态转换
                gesture_type = (payload or {}).get('gesture_type', '')
                if gesture_type == 'come_closer':
                    self._last_activity_at = time.time()
                    if self._state == State.IDLE:
                        self._do_transition(State.AWARE, 'gesture_come_closer')
                elif gesture_type == 'raise_hand':
                    # 举手暂停/恢复：记录事件，由对话编排器处理
                    self._last_activity_at = time.time()

    # ─── 内部方法 ────────────────────────────────────────

    def _do_transition(self, new_state: State, trigger: str) -> dict[str, Any]:
        """执行状态转换"""
        old_state = self._state
        if old_state == new_state:
            return {'from': old_state.value, 'to': new_state.value, 'trigger': trigger, 'no_change': True}

        timestamp = datetime.now(timezone.utc).isoformat()
        transition_info = {
            'from': old_state.value,
            'to': new_state.value,
            'timestamp': timestamp,
            'trigger': trigger,
        }

        self._state = new_state
        self._state_entered_at = time.time()

        logger.info(f'State transition: {old_state.value} → {new_state.value} (trigger: {trigger})')

        # 触发回调
        if self._on_state_changed:
            try:
                if asyncio.iscoroutinefunction(self._on_state_changed):
                    asyncio.create_task(self._on_state_changed(transition_info))
                else:
                    self._on_state_changed(transition_info)
            except Exception as e:
                logger.error(f'State change callback error: {e}')

        # 启动或重启超时监控
        if not self._running:
            self._running = True
            self._timeout_task = asyncio.create_task(self._timeout_monitor())

        return transition_info

    async def _timeout_monitor(self):
        """超时监控任务，每秒检查一次"""
        try:
            while self._running:
                await asyncio.sleep(1)

                now = time.time()
                state = self._state

                match state:
                    case State.AWARE:
                        # Aware → Idle: 无活动超时
                        if self._last_activity_at and (now - self._last_activity_at >= self.timeout_aware_to_idle):
                            self._last_activity_at = None
                            self._face_present_since = None
                            self._do_transition(State.IDLE, 'timeout_aware_to_idle')

                    case State.AUTH:
                        # Auth → Idle: 无人脸超时
                        if not self._face_detected:
                            time_since_state = now - self._state_entered_at
                            if time_since_state >= self.timeout_auth_to_idle:
                                self._do_transition(State.IDLE, 'timeout_auth_to_idle')

                    case State.CHAT:
                        # Chat → Auth: 对话静默超时
                        if self._last_activity_at and (now - self._last_activity_at >= self.timeout_chat_to_auth):
                            self._do_transition(State.AUTH, 'timeout_chat_to_auth')

                    case State.IDLE:
                        # Idle 状态不做超时处理，等待事件触发
                        pass

        except asyncio.CancelledError:
            logger.debug('Timeout monitor cancelled')
        except Exception as e:
            logger.error(f'Timeout monitor error: {e}')

    def stop(self):
        """停止状态机"""
        self._running = False
        if self._timeout_task:
            self._timeout_task.cancel()
            self._timeout_task = None

    def __repr__(self) -> str:
        return f'StateMachine(state={self._state.value}, time_in_state={time.time() - self._state_entered_at:.1f}s)'
