"""
Frank 角色权限系统

四级角色：
- Owner (主人): 每个部署环境仅 1 人，最高权限
- Adult (成人): 常规技能，不可管理成员和配置
- Child (儿童): 受限技能+使用时长限制
- Guest (访客): 仅基础查询，不持久化数据

指令优先级：Owner > Adult > Child > Guest
"""

import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable

logger = logging.getLogger('frank.role')


class Role(IntEnum):
    """角色等级（数值越大权限越高）"""
    GUEST = 0
    CHILD = 1
    ADULT = 2
    OWNER = 3

    @classmethod
    def from_string(cls, s: str) -> 'Role':
        mapping = {
            'guest': cls.GUEST,
            'child': cls.CHILD,
            'adult': cls.ADULT,
            'owner': cls.OWNER,
        }
        return mapping.get(s.lower(), cls.GUEST)


# 角色中文名称
ROLE_NAMES = {
    Role.OWNER: '主人',
    Role.ADULT: '成人',
    Role.CHILD: '儿童',
    Role.GUEST: '访客',
}

# 角色徽章符号
ROLE_BADGES = {
    Role.OWNER: '👑',
    Role.ADULT: '🔵',
    Role.CHILD: '🟢',
    Role.GUEST: '⚪',
}

# 角色 CSS 类名
ROLE_CSS_CLASSES = {
    Role.OWNER: 'role-owner',
    Role.ADULT: 'role-adult',
    Role.CHILD: 'role-child',
    Role.GUEST: 'role-guest',
}

# 各角色可访问的技能白名单（技能名列表，'*' 表示全部）
SKILL_WHITELIST = {
    Role.OWNER: ['*'],
    Role.ADULT: ['*'],  # 除成员管理和系统配置外（在代码中额外检查）
    Role.CHILD: [
        'weather', 'time', 'reminder', 'music', 'translation',
        'knowledge', 'story', 'joke',
    ],
    Role.GUEST: ['weather', 'time', 'knowledge', 'joke'],
}

# 使用时长限制（秒/天，0 表示无限制）
DAILY_USAGE_LIMITS = {
    Role.OWNER: 0,
    Role.ADULT: 0,
    Role.CHILD: 7200,   # 2 小时
    Role.GUEST: 1800,   # 30 分钟
}

# 敏感操作（仅 Owner 可执行）
OWNER_ONLY_ACTIONS = {
    'member.add', 'member.remove', 'member.edit_role',
    'config.modify', 'system.restart', 'system.shutdown',
}


@dataclass
class SessionContext:
    """会话上下文（附着角色信息）"""
    member_id: str | None = None
    display_name: str | None = None
    role: Role = Role.GUEST
    session_start: float = field(default_factory=time.time)
    daily_usage_seconds: float = 0.0


class RoleManager:
    """角色权限管理器"""

    def __init__(self):
        self._sessions: dict[str, SessionContext] = {}  # member_id → session
        self._daily_usage: dict[str, float] = {}        # member_id → 今日累计秒数
        self._command_queue: list[tuple[SessionContext, str, float]] = []  # (ctx, command, timestamp)
        self._on_owner_exists_check: Callable | None = None

    # ─── 会话管理 ───────────────────────────────────────

    def create_session(self, member_id: str, display_name: str, role_str: str) -> SessionContext:
        """为用户创建会话"""
        role = Role.from_string(role_str)
        ctx = SessionContext(
            member_id=member_id,
            display_name=display_name,
            role=role,
        )
        self._sessions[member_id] = ctx
        logger.info(f'Session created: {display_name} (role={role.name})')
        return ctx

    def end_session(self, member_id: str):
        """结束会话"""
        if member_id in self._sessions:
            ctx = self._sessions.pop(member_id)
            duration = time.time() - ctx.session_start
            logger.info(f'Session ended: {ctx.display_name} (duration={duration:.0f}s)')

    def get_session(self, member_id: str) -> SessionContext | None:
        return self._sessions.get(member_id)

    # ─── 权限检查 ───────────────────────────────────────

    def can_execute(self, member_id: str, action: str) -> tuple[bool, str]:
        """检查用户是否可以执行某操作

        Returns:
            (allowed, reason) - reason 在拒绝时提供中文说明
        """
        ctx = self._sessions.get(member_id)
        if not ctx:
            return False, '用户未登录'

        role = ctx.role

        # Owner 专属操作
        if action in OWNER_ONLY_ACTIONS and role != Role.OWNER:
            return False, f'此操作仅主人可执行，你的角色是{ROLE_NAMES.get(role, "未知")}'

        # 技能白名单检查
        skill = action.replace('skill.', '') if action.startswith('skill.') else action
        allowed_skills = SKILL_WHITELIST.get(role, [])
        if '*' not in allowed_skills and skill not in allowed_skills:
            return False, f'你的角色({ROLE_NAMES.get(role)})不支持此功能'

        # 时长限制检查
        limit = DAILY_USAGE_LIMITS.get(role, 0)
        if limit > 0:
            today_usage = self._daily_usage.get(member_id, 0)
            if today_usage >= limit:
                return False, f'今日使用时长已达上限({limit // 60}分钟)，请明天再来'

        return True, ''

    def record_usage(self, member_id: str, seconds: float):
        """记录使用时长"""
        self._daily_usage[member_id] = self._daily_usage.get(member_id, 0) + seconds

    # ─── 优先级抢占 ─────────────────────────────────────

    def check_preemption(self, new_member_id: str, current_member_id: str | None) -> tuple[bool, str]:
        """检查新来者是否可以抢占当前会话

        Returns:
            (can_preempt, reason)
        """
        if current_member_id is None:
            return True, ''

        new_ctx = self._sessions.get(new_member_id)
        cur_ctx = self._sessions.get(current_member_id)

        if not new_ctx:
            return False, '新用户未登录'
        if not cur_ctx:
            return True, ''

        # Owner 始终可抢占
        if new_ctx.role == Role.OWNER:
            return True, '主人优先'

        # 高等级可抢占低等级
        if new_ctx.role > cur_ctx.role:
            return True, f'{ROLE_NAMES[new_ctx.role]}优先于{ROLE_NAMES[cur_ctx.role]}'

        # 同等级先到先服务
        if new_ctx.role == cur_ctx.role:
            return False, f'当前{ROLE_NAMES[cur_ctx.role]}用户正在使用中，请稍后'

        return False, f'当前用户的优先级更高'

    # ─── 工具方法 ───────────────────────────────────────

    def reset_daily_usage(self):
        """重置每日使用统计（每日零点调用）"""
        self._daily_usage.clear()
        logger.info('Daily usage stats reset')

    def get_role_info(self, role_str: str) -> dict:
        """获取角色信息"""
        role = Role.from_string(role_str)
        return {
            'name': role.name.lower(),
            'display_name': ROLE_NAMES.get(role, '未知'),
            'badge': ROLE_BADGES.get(role, ''),
            'css_class': ROLE_CSS_CLASSES.get(role, ''),
            'level': int(role),
            'daily_limit_seconds': DAILY_USAGE_LIMITS.get(role, 0),
        }

    def get_all_roles(self) -> list[dict]:
        return [self.get_role_info(r.name.lower()) for r in Role]

    def get_all_roles_info(self) -> list[dict]:
        """返回四级角色的完整定义（含权限矩阵和技能白名单）"""
        roles_info = []
        for r in Role:
            role_name = r.name.lower()
            base = self.get_role_info(role_name)
            skills = SKILL_WHITELIST.get(r, [])
            limit = DAILY_USAGE_LIMITS.get(r, 0)

            # 权限项定义
            permissions = {
                'member_management': r == Role.OWNER,
                'system_config': r == Role.OWNER,
                'full_data_access': r == Role.OWNER,
                'regular_skills': r in (Role.OWNER, Role.ADULT),
                'smart_home_control': r in (Role.OWNER, Role.ADULT),
                'calendar_notes': r in (Role.OWNER, Role.ADULT),
                'file_operations': r in (Role.OWNER, Role.ADULT),
                'third_party_skills': r in (Role.OWNER, Role.ADULT),
                'session_preempt': r == Role.OWNER,
                'basic_qa': True,  # 所有角色都可基础问答
            }

            base['permissions'] = permissions
            base['skills'] = ['全部技能'] if skills == ['*'] else skills
            base['daily_limit_minutes'] = limit // 60 if limit > 0 else 0
            base['description'] = {
                'owner': '家庭管理员，拥有全部权限',
                'adult': '成年家庭成员，可使用所有常规技能',
                'child': '儿童成员，受限技能 + 每日使用时长限制',
                'guest': '临时访客，仅基础问答，不保留数据',
            }.get(role_name, '')

            roles_info.append(base)

        return roles_info

    def get_role_detail(self, role_name: str) -> dict | None:
        """获取指定角色的完整详情"""
        for info in self.get_all_roles_info():
            if info['name'] == role_name.lower():
                return info
        return None
