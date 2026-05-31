"""
Frank 外部通知服务接口（预留）

支持：
- SMTP 邮件通知
- 即时通讯 Webhook 通知（企业微信/钉钉/Slack）
"""

import logging

logger = logging.getLogger('frank.notification')


class ExternalNotifier:
    """外部通知服务接口"""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.email_enabled = self.config.get('email', {}).get('enabled', False)
        self.im_enabled = self.config.get('im', {}).get('enabled', False)

    async def send_email(self, to: str, subject: str, body: str):
        """通过 SMTP 发送邮件"""
        if not self.email_enabled:
            logger.info(f'[NOTIFIER-STUB] Email not enabled. Would send to {to}: {subject}')
            return
        raise NotImplementedError("SMTP email not yet implemented")

    async def send_im(self, message: str):
        """通过即时通讯 Webhook 发送消息"""
        if not self.im_enabled:
            im_config = self.config.get('im', {})
            service = im_config.get('service', 'unknown')
            logger.info(f'[NOTIFIER-STUB] IM ({service}) not enabled. Would send: {message}')
            return
        raise NotImplementedError("IM webhook not yet implemented")

    async def notify_owners(self, event: str, details: dict):
        """通知所有主人和管理员关于事件"""
        logger.info(f'[NOTIFIER-STUB] Event: {event}, Details: {details}')
