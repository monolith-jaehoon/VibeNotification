"""
核心模块

整合所有组件，提供主要功能
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from .models import NotificationConfig, NotificationEvent
from .config import get_env_config
from .managers import ParserManager, NotifierManager, NotificationBuilder
from .factories import AdapterFactory
from .exceptions import VibeNotificationError
from .i18n import set_language, t
from .debounce import handle_codex_turn_event


class VibeNotifier:
    """VibeNotification 核心类 - 简化的主协调器"""

    def __init__(self, config: Optional[NotificationConfig] = None):
        self.config = config or get_env_config()
        set_language(getattr(self.config, "language", "zh"))
        self.logger = logging.getLogger(__name__)

        # 设置日志
        self._setup_logging()

        # 创建组件
        self.executor = AdapterFactory.create_default_executor()
        self.platform_adapter = AdapterFactory.create_platform_adapter(self.executor, self.config)
        self.parser_manager = ParserManager()
        self.notifier_manager = NotifierManager(self.config, self.platform_adapter)
        self.notification_builder = NotificationBuilder()

    def _setup_logging(self):
        """设置日志"""
        log_level = getattr(logging, self.config.log_level.upper(), logging.INFO)

        # 获取日志文件路径 (放在项目目录或用户目录)
        log_path = Path.home() / ".config" / "vibe-notification" / "vibe_notification.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # 只使用文件日志,避免在 Codex 终端显示
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_path, encoding='utf-8')
            ],
            force=True  # 强制重新配置,覆盖任何现有配置
        )
        self.logger = logging.getLogger(__name__)

    def run(self):
        """主运行方法"""
        self.logger.info("VibeNotification 启动")

        try:
            # 获取解析器并解析事件
            parser = self.parser_manager.get_available_parser()
            raw_event_data = None
            if parser:
                # 对 Codex 解析器，保留原始数据用于防抖
                if hasattr(parser, '_load_event_data'):
                    raw_event_data = parser._load_event_data()
                event = parser.parse()
            else:
                self.logger.warning("未知运行模式，使用测试事件")
                event = NotificationEvent(
                    type="test",
                    agent="vibe-notification",
                    message=t("test_message"),
                    summary=t("test_summary"),
                    timestamp=datetime.now().isoformat(),
                    conversation_end=True,
                    is_last_turn=True
                )

            if event is None:
                self.logger.info("解析结果为空，跳过通知发送")
                return

            # Codex turn-complete 防抖：交给 debounce 模块处理
            if raw_event_data is not None and handle_codex_turn_event(raw_event_data, event):
                self.logger.info(
                    "Codex turn 事件已进入防抖队列: %s - %s",
                    event.agent,
                    event.type,
                )
                return

            # 处理事件
            self.process_event(event)
            self.logger.info("VibeNotification 完成")

        except VibeNotificationError as e:
            self.logger.error(f"VibeNotification 错误: {e}")
            # 发送错误通知
            self._send_error_notification(e, t("runtime_error"))
            raise
        except Exception as e:
            self.logger.error(f"未预期的错误: {e}", exc_info=True)
            # 发送错误通知
            self._send_error_notification(e, t("unknown_error"))
            raise

    def process_event(self, event: NotificationEvent):
        """处理事件并发送通知"""
        self.logger.info(f"处理事件: {event.agent} - {event.type} - 会话结束: {event.conversation_end}")

        try:
            if self.config.detect_conversation_end and not event.conversation_end:
                self.logger.info(
                    "跳过非结束事件通知: %s - %s",
                    event.agent,
                    event.type,
                )
                return

            # 构建通知内容
            content = self.notification_builder.build_notification_content(event)
            focus_path = self._extract_focus_path(event)
            notify_kwargs = {
                "title": content["title"],
                "message": content["message"],
                "level": content["level"],
                "subtitle": content["subtitle"],
            }
            if focus_path is not None:
                notify_kwargs["focus_path"] = focus_path

            # 发送通知
            self.notifier_manager.send_notifications(**notify_kwargs)

            # 记录到日志
            self.logger.info(f"已发送通知: {content['title']} - {content['message']}")

        except VibeNotificationError:
            # 重新抛出已知错误
            raise
        except Exception as e:
            # 包装未知错误
            raise VibeNotificationError(f"处理事件失败: {e}") from e

    def _extract_focus_path(self, event: NotificationEvent) -> Optional[str]:
        """从事件元数据中提取 VS Code 聚焦路径。"""
        metadata = event.metadata
        if not isinstance(metadata, dict):
            return None

        cwd = metadata.get("cwd")
        if isinstance(cwd, str):
            cwd = cwd.strip()
            if cwd:
                return cwd

        return None

    def _send_error_notification(self, error: Exception, context: str):
        """发送错误通知"""
        try:
            content = self.notification_builder.build_error_notification(error, context)
            self.notifier_manager.send_notifications(
                title=content["title"],
                message=content["message"],
                level=content["level"],
                subtitle=content["subtitle"]
            )
        except Exception as e:
            # 如果错误通知也失败了，只能记录到日志
            self.logger.error(f"发送错误通知失败: {e}")
