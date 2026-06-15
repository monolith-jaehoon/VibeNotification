"""
管理器模块

负责管理解析器、通知器等组件
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Dict, Any
import logging
import os
import re
import subprocess
from pathlib import Path
from .models import NotificationConfig, NotificationEvent, NotificationLevel
from .parsers import BaseParser, ClaudeCodeParser, CodexParser
from .notifiers import BaseNotifier, SoundNotifier, SystemNotifier
from .adapters import PlatformAdapter, CommandExecutor, DefaultCommandExecutor, create_platform_adapter
from .exceptions import NotifierError
from .i18n import t
from .parsers.routing import detect_parser_type

DEFAULT_NOTIFICATION_TITLE = "VibeNotification"
HOST_CONTEXT_ENV_KEYS = ("TERM_PROGRAM",)


class ParserManager:
    """解析器管理器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.parsers: List[BaseParser] = []
        self._initialize_parsers()

    def _initialize_parsers(self):
        """初始化所有解析器"""
        self.parsers = [
            ClaudeCodeParser(),
            CodexParser(),
        ]
        self.parsers_by_type = {
            getattr(parser, "parser_type", parser.__class__.__name__.lower()): parser
            for parser in self.parsers
        }
        self.logger.info(f"Initialized {len(self.parsers)} parsers")

    def detect_parser_type(self) -> Optional[str]:
        """检测当前上下文对应的 parser 类型。"""
        return detect_parser_type()

    def get_available_parser(self) -> Optional[BaseParser]:
        """获取当前可用的解析器"""
        parser_type = self.detect_parser_type()
        if parser_type is None:
            self.logger.warning("No parser route detected")
            return None

        parser = self.parsers_by_type.get(parser_type)
        if parser and parser.can_parse():
            self.logger.debug(f"Using parser: {parser.__class__.__name__}")
            return parser
        self.logger.warning("No suitable parser found")
        return None

    def add_parser(self, parser: BaseParser):
        """添加新的解析器"""
        self.parsers.append(parser)
        self.parsers_by_type[getattr(parser, "parser_type", parser.__class__.__name__.lower())] = parser
        self.logger.info(f"Added parser: {parser.__class__.__name__}")

    def remove_parser(self, parser_type: type):
        """移除指定类型的解析器"""
        removed = [p for p in self.parsers if isinstance(p, parser_type)]
        self.parsers = [p for p in self.parsers if not isinstance(p, parser_type)]
        for parser in removed:
            self.parsers_by_type.pop(getattr(parser, "parser_type", parser.__class__.__name__.lower()), None)
        self.logger.info(f"Removed parsers of type: {parser_type.__name__}")

    def list_parsers(self) -> List[str]:
        """列出所有解析器"""
        return [parser.__class__.__name__ for parser in self.parsers]


class NotifierManager:
    """通知器管理器"""

    def __init__(self, config: NotificationConfig, platform_adapter: PlatformAdapter):
        self.config = config
        self.platform_adapter = platform_adapter
        self.logger = logging.getLogger(__name__)
        self.notifiers: List[BaseNotifier] = []
        self._initialize_notifiers()

    def _initialize_notifiers(self):
        """初始化所有通知器"""
        self.notifiers = [
            SoundNotifier(self.config, self.platform_adapter),
            SystemNotifier(self.config, self.platform_adapter),
        ]
        self.logger.info(f"Initialized {len(self.notifiers)} notifiers")

    def send_notifications(self, title: str, message: str, level: NotificationLevel, subtitle: str = ""):
        """发送通知到所有启用的通知器"""
        successful = 0
        failed = 0
        enabled_notifiers: List[BaseNotifier] = []

        for notifier in self.notifiers:
            if notifier.is_enabled():
                enabled_notifiers.append(notifier)
            else:
                self.logger.debug(f"Notifier {notifier.__class__.__name__} is disabled")

        first_error: Optional[NotifierError] = None
        if enabled_notifiers:
            with ThreadPoolExecutor(max_workers=len(enabled_notifiers), thread_name_prefix="vibe-notify") as executor:
                future_map = {
                    executor.submit(notifier.notify, title, message, level, subtitle=subtitle): notifier
                    for notifier in enabled_notifiers
                }

                for future in as_completed(future_map):
                    notifier = future_map[future]
                    try:
                        future.result()
                        successful += 1
                        self.logger.debug(f"Notification sent via {notifier.__class__.__name__}")
                    except Exception as e:
                        failed += 1
                        self.logger.warning(f"Notifier {notifier.__class__.__name__} failed: {e}")
                        if first_error is None:
                            first_error = NotifierError(
                                f"Failed to send notification via {notifier.__class__.__name__}: {e}"
                            )

        self.logger.info(f"Notifications sent: {successful} successful, {failed} failed")
        if first_error is not None:
            raise first_error

    def add_notifier(self, notifier: BaseNotifier):
        """添加新的通知器"""
        self.notifiers.append(notifier)
        self.logger.info(f"Added notifier: {notifier.__class__.__name__}")

    def remove_notifier(self, notifier_type: type):
        """移除指定类型的通知器"""
        self.notifiers = [n for n in self.notifiers if not isinstance(n, notifier_type)]
        self.logger.info(f"Removed notifiers of type: {notifier_type.__name__}")

    def list_notifiers(self) -> List[str]:
        """列出所有通知器"""
        return [notifier.__class__.__name__ for notifier in self.notifiers]

    def get_enabled_notifiers(self) -> List[str]:
        """获取启用的通知器列表"""
        return [n.__class__.__name__ for n in self.notifiers if n.is_enabled()]


class NotificationBuilder:
    """通知内容构建器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def _extract_name(self, value: Any) -> Optional[str]:
        """从路径或名称中提取项目名"""
        if value is None:
            return None

        try:
            text = str(value).strip()
        except Exception:
            return None

        if not text:
            return None

        try:
            name = Path(text).name
        except Exception:
            name = text

        if not name or name in {os.sep, "."}:
            return None

        return name

    def _extract_name_from_metadata(self, metadata: Dict[str, Any]) -> Optional[str]:
        """从事件元数据中提取项目名或路径"""
        if not isinstance(metadata, dict):
            return None

        name_keys = (
            "project_name", "project", "workspace_name", "workspace", "repo_name"
        )
        path_keys = (
            "cwd", "pwd", "working_directory", "workdir",
            "workspace_dir", "workspace_root", "project_dir",
            "project_root", "repo_root", "root", "path"
        )

        for key in name_keys:
            name = self._extract_name(metadata.get(key))
            if name:
                return name

        for key in path_keys:
            value = metadata.get(key)
            if isinstance(value, dict):
                for nested_key in path_keys:
                    name = self._extract_name(value.get(nested_key))
                    if name:
                        return name
            else:
                name = self._extract_name(value)
                if name:
                    return name

        env_context = metadata.get("environment_context") or metadata.get("context")
        if isinstance(env_context, str):
            match = re.search(r"<cwd>(.*?)</cwd>", env_context, re.DOTALL)
            if match:
                name = self._extract_name(match.group(1).strip())
                if name:
                    return name

        for nested_key in ("metadata", "details"):
            nested = metadata.get(nested_key)
            if isinstance(nested, dict):
                name = self._extract_name_from_metadata(nested)
                if name:
                    return name

        return None

    def _get_git_root_name(self, cwd: Optional[str] = None) -> Optional[str]:
        """尝试通过 git 仓库根目录获取项目名"""
        for candidate_cwd in (cwd, os.environ.get("PWD"), None):
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    cwd=candidate_cwd,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0:
                    root = result.stdout.strip()
                    name = self._extract_name(root)
                    if name:
                        return name
            except Exception as exc:  # pragma: no cover - git 不在 PATH 或目录不存在
                self.logger.debug(f"git root detection failed: {exc}")
        return None

    def _get_project_name(self, event: Optional[NotificationEvent] = None) -> str:
        """获取当前项目名称（工作目录名或事件提供的工作区信息）"""
        if event and event.metadata:
            name_from_metadata = self._extract_name_from_metadata(event.metadata)
            if name_from_metadata:
                return name_from_metadata

        for env_key in ("CODEX_CWD", "CODEX_WORKDIR", "CODEX_WORKSPACE", "PWD", "OLDPWD"):
            name = self._extract_name(os.environ.get(env_key))
            if name:
                return name

        git_name = self._get_git_root_name()
        if git_name:
            return git_name

        try:
            cwd = Path.cwd()
            for candidate in (cwd, cwd.resolve()):
                name = self._extract_name(candidate)
                if name:
                    return name
        except Exception as exc:  # pragma: no cover - 极少触发
            self.logger.debug(f"Failed to determine project name from cwd: {exc}")

        return t("current_project")

    def _get_ide_tool_name(self, event: NotificationEvent) -> str:
        """从事件信息推断 IDE 工具名"""
        for candidate in (event.agent, event.tool_name):
            lower = (candidate or "").lower()
            if "claude" in lower:
                return "Claude Code"
            if "codex" in lower:
                return "Codex"

        return event.agent or event.tool_name or "IDE"

    def _get_agent_name(self, event: NotificationEvent) -> Optional[str]:
        """从事件信息推断 agent 名称。"""
        has_source = any(
            isinstance(candidate, str) and candidate.strip()
            for candidate in (event.agent, event.tool_name)
        )
        if not has_source:
            return None

        agent = self._get_ide_tool_name(event)
        return None if agent.lower() in {"ide", "unknown", "none"} else agent

    def _get_title_prefix(self, event: NotificationEvent) -> Optional[str]:
        """优先从 IDE 环境，其次从 agent 信息推断标题前缀。"""
        for key in HOST_CONTEXT_ENV_KEYS:
            value = os.environ.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        return self._get_agent_name(event)

    def _build_notification_title(self, event: NotificationEvent) -> str:
        """构建通知标题。"""
        prefix = self._get_title_prefix(event)
        if not prefix:
            prefix = DEFAULT_NOTIFICATION_TITLE

        return f"{prefix} - {self._get_project_name(event)}"

    def _get_event_message(self, event: NotificationEvent) -> Optional[str]:
        """从 parser 统一生成的事件字段中提取通知正文。"""
        for value in (event.message, event.summary):
            if isinstance(value, str) and value.strip():
                return value.strip()

        return None

    def build_notification_content(
        self,
        event: NotificationEvent,
        custom_title: Optional[str] = None,
        custom_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """构建通知内容"""
        # 根据事件类型决定通知级别
        level = NotificationLevel.SUCCESS if event.conversation_end else NotificationLevel.INFO

        # 组装固定展示内容
        title = custom_title or self._build_notification_title(event)
        message = (
            custom_message
            or self._get_event_message(event)
            or t("reply_finished")
        )
        subtitle = t("subtitle_ide", tool=self._get_ide_tool_name(event))

        # 截断过长的消息
        from .utils import truncate_text
        message = truncate_text(message, 240)

        content = {
            "title": title,
            "message": message,
            "subtitle": subtitle,
            "level": level
        }

        self.logger.debug(f"Built notification content: {content}")
        return content

    def build_error_notification(
        self,
        error: Exception,
        context: str = ""
    ) -> Dict[str, Any]:
        """构建错误通知内容"""
        title = t("error_title")
        message = f"{context}: {str(error)}" if context else str(error)
        subtitle = t("error_subtitle")

        content = {
            "title": title,
            "message": message,
            "subtitle": subtitle,
            "level": NotificationLevel.ERROR
        }

        self.logger.debug(f"Built error notification: {content}")
        return content
