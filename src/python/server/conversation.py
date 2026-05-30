"""
Frank 对话编排器 (Phase 3)

协调 STT → LLM → TTS 流水线
管理 Chat 子状态: Listening → Transcribing → Thinking → Speaking
"""

import asyncio
import logging
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger('frank.conversation')


class ChatSubState(Enum):
    LISTENING = 'listening'
    TRANSCRIBING = 'transcribing'
    THINKING = 'thinking'
    SPEAKING = 'speaking'


class ConversationOrchestrator:
    """对话编排器"""

    def __init__(self):
        self._sub_state = ChatSubState.LISTENING
        self._current_identity: dict | None = None
        self._stt_module = None
        self._llm_manager = None
        self._tts_module = None
        self._wakefree_manager = None

        # 回调
        self._on_sub_state_change: Callable | None = None
        self._on_user_message: Callable | None = None
        self._on_assistant_message: Callable | None = None

    def set_modules(self, stt=None, llm=None, tts=None, wakefree=None):
        self._stt_module = stt
        self._llm_manager = llm
        self._tts_module = tts
        self._wakefree_manager = wakefree

    def set_on_sub_state_change(self, cb: Callable): self._on_sub_state_change = cb
    def set_on_user_message(self, cb: Callable): self._on_user_message = cb
    def set_on_assistant_message(self, cb: Callable): self._on_assistant_message = cb

    @property
    def sub_state(self) -> ChatSubState:
        return self._sub_state

    def set_identity(self, identity: dict):
        self._current_identity = identity

    async def _change_sub_state(self, new_state: ChatSubState):
        old = self._sub_state
        self._sub_state = new_state
        logger.debug(f'Chat sub-state: {old.value} → {new_state.value}')
        if self._on_sub_state_change:
            if asyncio.iscoroutinefunction(self._on_sub_state_change):
                await self._on_sub_state_change({'from': old.value, 'to': new_state.value})
            else:
                self._on_sub_state_change({'from': old.value, 'to': new_state.value})

    async def handle_wake_word(self):
        """唤醒词命中 → 进入对话循环"""
        await self._change_sub_state(ChatSubState.LISTENING)

    async def process_speech(self, audio_segment, sample_rate: int = 16000):
        """处理语音段：STT → WakeFree check → LLM → TTS"""
        if not audio_segment or len(audio_segment) < sample_rate * 0.5:
            return

        # 1. STT 转写
        await self._change_sub_state(ChatSubState.TRANSCRIBING)
        import numpy as np
        audio_np = audio_segment if isinstance(audio_segment, np.ndarray) else np.array(audio_segment)

        transcription = None
        if self._stt_module:
            if hasattr(self._stt_module, 'is_ready') and not self._stt_module.is_ready:
                logger.warning('STT module not ready yet, skipping transcription')
                await self._change_sub_state(ChatSubState.LISTENING)
                return
            transcription = await self._stt_module.transcribe(audio_np, sample_rate)

        if not transcription or not transcription.get('text'):
            await self._change_sub_state(ChatSubState.LISTENING)
            return

        text = transcription['text']
        logger.info(f'User said: "{text}"')

        if self._on_user_message:
            if asyncio.iscoroutinefunction(self._on_user_message):
                await self._on_user_message({'text': text})
            else:
                self._on_user_message({'text': text})

        # 2. 免唤醒指令检查
        if self._wakefree_manager:
            cmd = self._wakefree_manager.match(text)
            if cmd and self._wakefree_manager.check_condition(cmd):
                await self._wakefree_manager.execute(cmd)
                await self._change_sub_state(ChatSubState.LISTENING)
                return

        # 3. LLM 理解
        await self._change_sub_state(ChatSubState.THINKING)

        response = ''
        if self._llm_manager:
            response = await self._llm_manager.chat(text, self._current_identity, stream=True)

        if not response:
            await self._change_sub_state(ChatSubState.LISTENING)
            return

        if self._on_assistant_message:
            if asyncio.iscoroutinefunction(self._on_assistant_message):
                await self._on_assistant_message({'text': response})
            else:
                self._on_assistant_message({'text': response})

        # 4. TTS 朗读
        if response and self._tts_module:
            await self._change_sub_state(ChatSubState.SPEAKING)
            await self._tts_module.speak(response)

        # 5. 回到 Listening
        await self._change_sub_state(ChatSubState.LISTENING)

    async def handle_text_input(self, text: str):
        """处理文字输入（手动输入模式）"""
        if not text:
            return

        if self._on_user_message:
            if asyncio.iscoroutinefunction(self._on_user_message):
                await self._on_user_message({'text': text})
            else:
                self._on_user_message({'text': text})

        # 免唤醒指令检查
        if self._wakefree_manager:
            cmd = self._wakefree_manager.match(text)
            if cmd and self._wakefree_manager.check_condition(cmd):
                await self._wakefree_manager.execute(cmd)
                return

        await self._change_sub_state(ChatSubState.THINKING)

        response = ''
        if self._llm_manager:
            response = await self._llm_manager.chat(text, self._current_identity, stream=True)

        if response and self._on_assistant_message:
            if asyncio.iscoroutinefunction(self._on_assistant_message):
                await self._on_assistant_message({'text': response})
            else:
                self._on_assistant_message({'text': response})

        if response and self._tts_module:
            await self._change_sub_state(ChatSubState.SPEAKING)
            await self._tts_module.speak(response)

        await self._change_sub_state(ChatSubState.LISTENING)

    def get_status(self) -> dict:
        return {
            'sub_state': self._sub_state.value,
            'identity': self._current_identity,
        }
