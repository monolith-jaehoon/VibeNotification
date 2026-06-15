"""
系统通知器

负责显示系统通知
"""

import sys
from typing import Optional
from .base import BaseNotifier
from ..models import NotificationConfig, NotificationLevel
from ..adapters import PlatformAdapter


class SystemNotifier(BaseNotifier):
    """系统通知器"""

    def __init__(self, config: NotificationConfig, platform_adapter: PlatformAdapter):
        super().__init__(config)
        self.platform_adapter = platform_adapter

    def is_enabled(self) -> bool:
        """检查是否启用"""
        return self.config.enable_notification and self.platform_adapter.is_notification_available()

    def notify(self, title: str, message: str, level: NotificationLevel = NotificationLevel.INFO, **kwargs):
        """显示系统通知"""
        if not self.is_enabled():
            # 提示配置禁用了系统通知，避免用户误以为失败
            self.logger.info("系统通知已禁用（enable_notification = False 或平台不支持）")
            return

        subtitle = kwargs.get("subtitle", "")
        self.log_notification(title, message, level)

        try:
            # 使用平台适配器显示通知
            focus_path = kwargs.get("focus_path")
            if focus_path is not None:
                self.platform_adapter.show_notification(
                    title,
                    message,
                    subtitle,
                    focus_path=focus_path,
                )
            else:
                self.platform_adapter.show_notification(title, message, subtitle)
        except Exception as e:
            self.logger.warning(f"显示通知失败: {e}")
            # 回退到打印
            print(f"[VibeNotification] {title}: {message}", file=sys.stderr)
