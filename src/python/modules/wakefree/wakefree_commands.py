"""
Frank 免唤醒指令系统 (Phase 3)

Aho-Corasick 多模式匹配 + 上下文条件校验
本地关键词匹配，不经过 LLM，低延迟
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger('frank.wakefree')


@dataclass
class WakeFreeCommand:
    """免唤醒指令定义"""
    keywords: list[str]           # 匹配关键词列表
    action: str                   # 动作类型: time, media_play, media_pause, media_next, volume_up, volume_down
    condition: str = 'always'     # 触发条件: always, media_playing, tts_speaking, chat_active
    enabled: bool = True
    description: str = ''


# 默认白名单
DEFAULT_COMMANDS = [
    WakeFreeCommand(keywords=['几点了', '现在几点', '当前时间'], action='time', condition='always',
                    description='报时'),
    WakeFreeCommand(keywords=['暂停', '暂停播放'], action='media_pause', condition='media_playing',
                    description='暂停媒体播放'),
    WakeFreeCommand(keywords=['继续', '继续播放', '播放'], action='media_play', condition='media_playing',
                    description='继续媒体播放'),
    WakeFreeCommand(keywords=['下一首', '下一曲', '跳过'], action='media_next', condition='media_playing',
                    description='下一首'),
    WakeFreeCommand(keywords=['大声点', '声音大一点', '音量加大'], action='volume_up', condition='tts_speaking',
                    description='增大音量'),
    WakeFreeCommand(keywords=['小声点', '声音小一点', '音量减小'], action='volume_down', condition='tts_speaking',
                    description='减小音量'),
]


class WakeFreeManager:
    """免唤醒指令管理器"""

    def __init__(self):
        self.commands: list[WakeFreeCommand] = list(DEFAULT_COMMANDS)
        self._keyword_to_cmd: dict[str, WakeFreeCommand] = {}
        self._build_index()
        self._condition_providers: dict[str, Callable] = {}
        self._action_handlers: dict[str, Callable] = {}

        self._on_command_executed: Callable | None = None
        self._on_command_blocked: Callable | None = None

    def set_on_command_executed(self, cb: Callable): self._on_command_executed = cb
    def set_on_command_blocked(self, cb: Callable): self._on_command_blocked = cb

    # ─── 条件提供者 ───────────────────────────────────

    def set_condition_provider(self, name: str, provider: Callable):
        """注册条件判断函数"""
        self._condition_providers[name] = provider

    def set_action_handler(self, action: str, handler: Callable):
        """注册动作处理函数"""
        self._action_handlers[action] = handler

    # ─── 索引构建 ─────────────────────────────────────

    def _build_index(self):
        """构建关键词→命令索引"""
        self._keyword_to_cmd = {}
        for cmd in self.commands:
            if cmd.enabled:
                for kw in cmd.keywords:
                    self._keyword_to_cmd[kw.lower()] = cmd
        logger.debug(f'Wake-free index: {len(self._keyword_to_cmd)} keywords')

    def add_command(self, keywords: list[str], action: str, condition: str = 'always',
                    description: str = ''):
        cmd = WakeFreeCommand(keywords=keywords, action=action, condition=condition, description=description)
        self.commands.append(cmd)
        self._build_index()

    def remove_command(self, keyword: str):
        self.commands = [c for c in self.commands if keyword not in c.keywords]
        self._build_index()

    def list_commands(self) -> list[dict]:
        return [
            {'keywords': c.keywords, 'action': c.action, 'condition': c.condition,
             'enabled': c.enabled, 'description': c.description}
            for c in self.commands
        ]

    # ─── 匹配与执行 ───────────────────────────────────

    def match(self, text: str) -> WakeFreeCommand | None:
        """在文本中查找匹配的免唤醒指令"""
        if not text:
            return None

        text_lower = text.lower()
        start_time = time.time()

        # 简单子串匹配（Aho-Corasick 简化版，对于小规模白名单足够快）
        best_match = None
        best_len = 0
        for keyword, cmd in self._keyword_to_cmd.items():
            if keyword in text_lower:
                if len(keyword) > best_len:
                    best_match = cmd
                    best_len = len(keyword)

        elapsed = (time.time() - start_time) * 1000
        if best_match:
            logger.debug(f'Wake-free match: "{best_match.action}" ({elapsed:.1f}ms)')
        return best_match

    def check_condition(self, cmd: WakeFreeCommand) -> bool:
        """检查命令的上下文条件"""
        if cmd.condition == 'always':
            return True

        provider = self._condition_providers.get(cmd.condition)
        if provider:
            try:
                return provider()
            except Exception:
                return False
        return False

    async def execute(self, cmd: WakeFreeCommand) -> bool:
        """执行免唤醒指令"""
        if not self.check_condition(cmd):
            logger.info(f'Wake-free blocked: {cmd.action} (condition={cmd.condition} not met)')
            if self._on_command_blocked:
                self._on_command_blocked({'action': cmd.action, 'reason': f'条件不满足: {cmd.condition}'})
            return False

        handler = self._action_handlers.get(cmd.action)
        if handler:
            try:
                await handler(cmd)
                logger.info(f'Wake-free executed: {cmd.action}')
                if self._on_command_executed:
                    self._on_command_executed({'action': cmd.action, 'keywords': cmd.keywords})
                return True
            except Exception as e:
                logger.error(f'Wake-free handler error: {e}')
                return False
        else:
            logger.warning(f'No handler for action: {cmd.action}')
            return False
