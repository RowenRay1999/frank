"""
Frank 消息数据类
定义消息信封格式和错误消息结构
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


@dataclass
class Message:
    """标准消息信封

    格式: { type, id (UUID), timestamp (ISO8601), payload }
    响应消息含 in_reply_to
    """
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    in_reply_to: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            'type': self.type,
            'id': self.id,
            'timestamp': self.timestamp,
            'payload': self.payload,
        }
        if self.in_reply_to:
            result['in_reply_to'] = self.in_reply_to
        return result


@dataclass
class ErrorMessage:
    """错误消息结构

    格式: { type: "error", payload: { code, message, recoverable, suggestion } }
    """
    code: str           # 错误码 (e.g., CAM_NOT_FOUND, MIC_PERMISSION_DENIED)
    message: str        # 中文错误描述
    recoverable: bool = True   # 是否可恢复
    suggestion: str = ''       # 建议操作

    def to_message(self, in_reply_to: str | None = None) -> Message:
        return Message(
            type='error',
            payload={
                'code': self.code,
                'message': self.message,
                'recoverable': self.recoverable,
                'suggestion': self.suggestion,
            },
            in_reply_to=in_reply_to,
        )


# ─── 预定义错误 ───

CAM_NOT_FOUND = ErrorMessage(
    code='CAM_NOT_FOUND',
    message='未找到摄像头设备，请确认摄像头已连接并启用',
    recoverable=True,
    suggestion='请检查摄像头连接，或在设置中选择其他摄像头设备',
)

CAM_PERMISSION_DENIED = ErrorMessage(
    code='CAM_PERMISSION_DENIED',
    message='摄像头权限被拒绝，请在系统设置中允许 Frank 访问摄像头',
    recoverable=True,
    suggestion='请前往 Windows 设置 → 隐私 → 摄像头，允许应用访问摄像头',
)

CAM_DISCONNECTED = ErrorMessage(
    code='CAM_DISCONNECTED',
    message='摄像头连接中断，正在尝试恢复...',
    recoverable=True,
    suggestion='请检查摄像头连接，系统将自动尝试重新连接',
)

MIC_NOT_FOUND = ErrorMessage(
    code='MIC_NOT_FOUND',
    message='未找到麦克风设备，请确认麦克风已连接并启用',
    recoverable=True,
    suggestion='请检查麦克风连接，或在设置中选择其他麦克风设备',
)

MIC_PERMISSION_DENIED = ErrorMessage(
    code='MIC_PERMISSION_DENIED',
    message='麦克风权限被拒绝，请在系统设置中允许 Frank 访问麦克风',
    recoverable=True,
    suggestion='请前往 Windows 设置 → 隐私 → 麦克风，允许应用访问麦克风',
)

MIC_DISCONNECTED = ErrorMessage(
    code='MIC_DISCONNECTED',
    message='麦克风连接中断，正在尝试恢复...',
    recoverable=True,
    suggestion='请检查麦克风连接，系统将自动尝试重新连接',
)
