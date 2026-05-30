"""
Frank LLM Provider 模块 (Phase 3)

可插拔架构：OpenAI / Azure OpenAI / Ollama
支持流式响应 + 对话历史 + 自动回退
"""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Callable

logger = logging.getLogger('frank.llm')


# ─── 抽象接口 ─────────────────────────────────────────────

class LLMProvider(ABC):
    """LLM Provider 抽象基类"""

    @abstractmethod
    async def generate(self, messages: list[dict], **kwargs) -> str:
        """非流式生成"""
        ...

    @abstractmethod
    async def generate_stream(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        """流式生成"""
        ...


# ─── OpenAI Provider ──────────────────────────────────────

class OpenAIProvider(LLMProvider):
    """OpenAI / Azure OpenAI Provider"""

    def __init__(self, config: dict):
        self.model = config.get('model', 'gpt-4o-mini')
        self.base_url = config.get('base_url')  # None = default OpenAI, set for Azure
        self.timeout = config.get('timeout', 15)
        self.max_tokens = config.get('max_tokens', 1024)
        self.temperature = config.get('temperature', 0.7)

        # API Key: 环境变量 > 配置文件
        api_key_env = config.get('api_key_env', 'FRANK_LLM_API_KEY')
        self.api_key = os.environ.get(api_key_env)
        if not self.api_key:
            logger.warning(f'LLM API key not found in env var {api_key_env}')

        self._client = None

    def _get_client(self):
        if self._client is None and self.api_key:
            from openai import AsyncOpenAI
            kwargs = {'api_key': self.api_key, 'timeout': self.timeout}
            if self.base_url:
                kwargs['base_url'] = self.base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def generate(self, messages: list[dict], **kwargs) -> str:
        client = self._get_client()
        if not client:
            raise RuntimeError('LLM client not available (no API key)')

        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            **kwargs,
        )
        return response.choices[0].message.content or ''

    async def generate_stream(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        client = self._get_client()
        if not client:
            raise RuntimeError('LLM client not available (no API key)')

        stream = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stream=True,
            **kwargs,
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# ─── Ollama Provider (本地回退) ───────────────────────────

class OllamaProvider(LLMProvider):
    """Ollama 本地 LLM Provider"""

    def __init__(self, config: dict):
        self.model = config.get('model', 'qwen2.5:7b')
        self.base_url = config.get('base_url', 'http://localhost:11434')
        self.timeout = config.get('timeout', 30)
        self.max_tokens = config.get('max_tokens', 512)

    async def _call(self, messages: list[dict], stream: bool = False):
        import aiohttp
        url = f'{self.base_url}/api/chat'
        payload = {
            'model': self.model,
            'messages': messages,
            'stream': stream,
            'options': {'num_predict': self.max_tokens},
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=self.timeout) as resp:
                if stream:
                    return resp  # 返回 response 对象供流式读取
                data = await resp.json()
                return data.get('message', {}).get('content', '')

    async def generate(self, messages: list[dict], **kwargs) -> str:
        try:
            return await self._call(messages, stream=False)
        except Exception as e:
            logger.error(f'Ollama generate error: {e}')
            raise

    async def generate_stream(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        try:
            import json
            import aiohttp
            url = f'{self.base_url}/api/chat'
            payload = {
                'model': self.model,
                'messages': messages,
                'stream': True,
                'options': {'num_predict': self.max_tokens},
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=self.timeout) as resp:
                    buffer = b''
                    async for chunk in resp.content:
                        buffer += chunk
                        while b'\n' in buffer:
                            line, buffer = buffer.split(b'\n', 1)
                            line = line.strip()
                            if line:
                                try:
                                    data = json.loads(line)
                                    content = data.get('message', {}).get('content', '')
                                    if content:
                                        yield content
                                except json.JSONDecodeError:
                                    continue
        except Exception as e:
            logger.error(f'Ollama stream error: {e}')

    @staticmethod
    async def is_available(base_url: str = 'http://localhost:11434') -> bool:
        """检查 Ollama 是否可用"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f'{base_url}/api/tags', timeout=3) as resp:
                    return resp.status == 200
        except Exception:
            return False


# ─── LLM Manager (编排) ───────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """你是 Frank（弗兰克），一个家庭工作助手。你运行在家庭共享的 Windows 电脑上。

## 当前用户
- 姓名: {display_name}
- 角色: {role_display} ({role})
- 称呼: {honorific}

## 行为准则
1. 用中文回复，简洁友好
2. 称呼用户为"{honorific}"（如"王先生"、"李女士"）
3. 回复控制在 1-3 句话，不要啰嗦
4. 如果不知道答案，诚实说不知道
5. 保护家庭隐私，不泄露其他成员信息

## 可用能力
你现在可以进行以下操作：
- 回答问题、提供信息
- 设置提醒
- 查询天气（需要网络）
- 播放音乐（需要网络）
- 更多能力正在开发中...

{extra_context}
"""


class LLMManager:
    """LLM 编排器：Provider 切换 + 对话历史 + 系统提示词"""

    def __init__(self, config: dict):
        self.config = config
        self.primary_provider: LLMProvider | None = None
        self.fallback_provider: LLMProvider | None = None
        self.conversation_history: list[dict] = []
        self.max_history_rounds = config.get('max_history_rounds', 10)

        self._on_token: Callable | None = None
        self._on_response: Callable | None = None
        self._on_error: Callable | None = None

    def set_on_token(self, cb: Callable): self._on_token = cb
    def set_on_response(self, cb: Callable): self._on_response = cb
    def set_on_error(self, cb: Callable): self._on_error = cb

    async def initialize(self):
        """初始化 Provider"""
        provider_type = self.config.get('provider', 'openai')

        if provider_type in ('openai', 'azure'):
            self.primary_provider = OpenAIProvider(self.config)
        elif provider_type == 'ollama':
            self.primary_provider = OllamaProvider(self.config)

        # 回退总是 Ollama（如果可用）
        if provider_type != 'ollama':
            self.fallback_provider = OllamaProvider({'model': 'qwen2.5:7b'})

        logger.info(f'LLM Manager initialized: primary={provider_type}, fallback={"ollama" if self.fallback_provider else "none"}')

    def build_system_prompt(self, identity: dict | None = None, extra: str = '') -> str:
        """构建系统提示词"""
        if not identity:
            identity = {'display_name': '用户', 'role': 'guest'}

        role = identity.get('role', 'guest')
        role_map = {'owner': '主人', 'adult': '成人', 'child': '儿童', 'guest': '访客'}
        display_name = identity.get('display_name', '用户')

        # 推断称呼
        honorific_map = {'owner': '主人', 'child': '', 'guest': '访客'}
        honorific = honorific_map.get(role, '')
        if role == 'adult':
            honorific = f'{display_name}先生' if '女士' not in display_name else display_name
        elif not honorific:
            honorific = display_name

        return SYSTEM_PROMPT_TEMPLATE.format(
            display_name=display_name,
            role=role,
            role_display=role_map.get(role, '访客'),
            honorific=honorific,
            extra_context=extra,
        )

    def add_to_history(self, role: str, content: str):
        self.conversation_history.append({'role': role, 'content': content})
        # 裁剪
        max_msgs = self.max_history_rounds * 2
        if len(self.conversation_history) > max_msgs:
            self.conversation_history = self.conversation_history[-max_msgs:]

    def clear_history(self):
        self.conversation_history = []

    async def chat(self, user_message: str, identity: dict | None = None,
                    stream: bool = True) -> str:
        """完整对话：系统提示词 + 历史 + 用户消息 → 回复"""
        system_prompt = self.build_system_prompt(identity)
        messages = [{'role': 'system', 'content': system_prompt}]
        messages.extend(self.conversation_history)
        messages.append({'role': 'user', 'content': user_message})

        self.add_to_history('user', user_message)

        # 尝试主 Provider
        provider = self.primary_provider
        response = ''

        try:
            if stream:
                response = await self._stream_with_fallback(provider, messages)
            else:
                response = await asyncio.wait_for(
                    provider.generate(messages),
                    timeout=self.config.get('timeout', 15)
                )
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f'Primary LLM failed ({e}), trying fallback...')
            if self.fallback_provider and await OllamaProvider.is_available():
                try:
                    response = await asyncio.wait_for(
                        self.fallback_provider.generate(messages),
                        timeout=30
                    )
                except Exception as e2:
                    logger.error(f'Fallback LLM also failed: {e2}')
                    response = '抱歉，我现在无法连接到语言服务。请检查网络后重试。'
            else:
                response = '抱歉，我现在无法连接到语言服务。请检查网络后重试。'

        self.add_to_history('assistant', response)

        if self._on_response:
            self._on_response({'text': response, 'streaming': stream})

        return response

    async def _stream_with_fallback(self, provider: LLMProvider, messages: list[dict]) -> str:
        """流式生成 + 回退"""
        full_response = ''
        try:
            async for token in provider.generate_stream(messages):
                full_response += token
                if self._on_token:
                    self._on_token({'token': token, 'partial': full_response})
                await asyncio.sleep(0)  # 让出控制权

            return full_response

        except Exception as e:
            # 流式失败，尝试非流式
            logger.warning(f'Stream failed ({e}), trying non-stream...')
            return await asyncio.wait_for(
                provider.generate(messages),
                timeout=self.config.get('timeout', 15)
            )
