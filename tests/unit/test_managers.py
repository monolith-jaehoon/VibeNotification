"""
测试管理器模块
"""

import os
import threading
import pytest
from unittest.mock import Mock, patch
from vibe_notification.models import NotificationConfig, NotificationEvent, NotificationLevel
from vibe_notification.managers import (
    ParserManager,
    NotifierManager,
    NotificationBuilder
)
from vibe_notification.parsers import BaseParser
from vibe_notification.parsers.codex import CodexParser
from vibe_notification.notifiers import BaseNotifier
from vibe_notification.exceptions import NotifierError
from tests.conftest import mock_config, sample_event, mock_platform_adapter


class TestParserManager:
    """测试解析器管理器"""

    def test_initialization(self):
        """测试初始化"""
        manager = ParserManager()
        assert len(manager.parsers) > 0
        assert any("CodexParser" in p.__class__.__name__ for p in manager.parsers)
        assert any("ClaudeCodeParser" in p.__class__.__name__ for p in manager.parsers)

    def test_get_available_parser(self):
        """测试获取可用解析器"""
        manager = ParserManager()
        with patch.object(manager, "detect_parser_type", return_value="codex"), \
             patch.object(CodexParser, "can_parse", return_value=True):
            parser = manager.get_available_parser()
        assert parser is not None
        assert isinstance(parser, BaseParser)

    def test_get_available_parser_only_checks_routed_parser(self, monkeypatch):
        """来源已判定后，只应检查对应 parser，不再让解析器相互探测。"""
        manager = ParserManager()

        claude_parser = Mock(spec=BaseParser)
        claude_parser.parser_type = "claude_code"
        claude_parser.can_parse.return_value = True

        codex_parser = Mock(spec=BaseParser)
        codex_parser.parser_type = "codex"
        codex_parser.can_parse.return_value = True

        manager.parsers = [claude_parser, codex_parser]
        manager.parsers_by_type = {
            "claude_code": claude_parser,
            "codex": codex_parser,
        }

        monkeypatch.setattr(manager, "detect_parser_type", lambda: "claude_code")

        parser = manager.get_available_parser()

        assert parser is claude_parser
        claude_parser.can_parse.assert_called_once()
        codex_parser.can_parse.assert_not_called()

    def test_add_parser(self):
        """测试添加解析器"""
        manager = ParserManager()
        initial_count = len(manager.parsers)

        # 创建模拟解析器
        mock_parser = Mock(spec=BaseParser)
        manager.add_parser(mock_parser)

        assert len(manager.parsers) == initial_count + 1
        assert mock_parser in manager.parsers

    def test_remove_parser(self):
        """测试移除解析器"""
        manager = ParserManager()
        initial_count = len(manager.parsers)

        # 移除第一个解析器
        parser_type = type(manager.parsers[0])
        manager.remove_parser(parser_type)

        assert len(manager.parsers) == initial_count - 1
        assert not any(isinstance(p, parser_type) for p in manager.parsers)

    def test_list_parsers(self):
        """测试列出解析器"""
        manager = ParserManager()
        parser_names = manager.list_parsers()
        assert len(parser_names) > 0
        assert all(isinstance(name, str) for name in parser_names)


class TestNotifierManager:
    """测试通知器管理器"""

    def test_initialization(self, mock_config, mock_platform_adapter):
        """测试初始化"""
        manager = NotifierManager(mock_config, mock_platform_adapter)
        assert len(manager.notifiers) > 0
        assert any("SoundNotifier" in n.__class__.__name__ for n in manager.notifiers)
        assert any("SystemNotifier" in n.__class__.__name__ for n in manager.notifiers)

    def test_send_notifications(self, mock_config, mock_platform_adapter):
        """测试发送通知"""
        # 创建模拟通知器
        mock_notifier = Mock(spec=BaseNotifier)
        mock_notifier.is_enabled.return_value = True

        manager = NotifierManager(mock_config, mock_platform_adapter)
        manager.notifiers = [mock_notifier]

        # 发送通知
        manager.send_notifications("Test Title", "Test Message", NotificationLevel.INFO)

        # 验证通知被发送
        mock_notifier.notify.assert_called_once_with(
            "Test Title", "Test Message", NotificationLevel.INFO, subtitle=""
        )

    def test_send_notifications_with_subtitle(self, mock_config, mock_platform_adapter):
        """测试发送带副标题的通知"""
        mock_notifier = Mock(spec=BaseNotifier)
        mock_notifier.is_enabled.return_value = True

        manager = NotifierManager(mock_config, mock_platform_adapter)
        manager.notifiers = [mock_notifier]

        # 发送带副标题的通知
        manager.send_notifications(
            "Title", "Message", NotificationLevel.INFO, subtitle="Subtitle"
        )

        mock_notifier.notify.assert_called_once_with(
            "Title", "Message", NotificationLevel.INFO, subtitle="Subtitle"
        )

    def test_send_notifications_disabled(self, mock_config, mock_platform_adapter):
        """测试发送通知时通知器被禁用"""
        mock_notifier = Mock(spec=BaseNotifier)
        mock_notifier.is_enabled.return_value = False

        manager = NotifierManager(mock_config, mock_platform_adapter)
        manager.notifiers = [mock_notifier]

        # 发送通知
        manager.send_notifications("Title", "Message", NotificationLevel.INFO)

        # 验证通知未被发送
        mock_notifier.notify.assert_not_called()

    def test_send_notifications_failure(self, mock_config, mock_platform_adapter):
        """测试发送通知失败"""
        mock_notifier = Mock(spec=BaseNotifier)
        mock_notifier.is_enabled.return_value = True
        mock_notifier.notify.side_effect = Exception("Test error")

        manager = NotifierManager(mock_config, mock_platform_adapter)
        manager.notifiers = [mock_notifier]

        # 发送通知应该抛出异常
        with pytest.raises(NotifierError):
            manager.send_notifications("Title", "Message", NotificationLevel.INFO)

    def test_send_notifications_stops_reporting_success_when_later_notifier_fails(self, mock_config, mock_platform_adapter):
        """后续通知器失败时，应明确抛错而不是误报全部成功。"""
        first = Mock(spec=BaseNotifier)
        first.is_enabled.return_value = True

        second = Mock(spec=BaseNotifier)
        second.is_enabled.return_value = True
        second.notify.side_effect = Exception("boom")

        manager = NotifierManager(mock_config, mock_platform_adapter)
        manager.notifiers = [first, second]

        with pytest.raises(NotifierError):
            manager.send_notifications("Title", "Message", NotificationLevel.INFO)

        first.notify.assert_called_once()
        second.notify.assert_called_once()

    def test_send_notifications_starts_enabled_notifiers_concurrently(self, mock_config, mock_platform_adapter):
        """声音与弹窗应并发启动，避免一个阻塞另一个。"""
        first = Mock(spec=BaseNotifier)
        first.is_enabled.return_value = True

        second = Mock(spec=BaseNotifier)
        second.is_enabled.return_value = True

        second_started = threading.Event()
        observed = {}

        def first_notify(*args, **kwargs):
            observed["second_started_before_first_return"] = second_started.wait(timeout=0.1)

        def second_notify(*args, **kwargs):
            second_started.set()

        first.notify.side_effect = first_notify
        second.notify.side_effect = second_notify

        manager = NotifierManager(mock_config, mock_platform_adapter)
        manager.notifiers = [first, second]

        manager.send_notifications("Title", "Message", NotificationLevel.INFO)

        assert observed["second_started_before_first_return"] is True

    def test_add_notifier(self, mock_config, mock_platform_adapter):
        """测试添加通知器"""
        manager = NotifierManager(mock_config, mock_platform_adapter)
        initial_count = len(manager.notifiers)

        # 创建模拟通知器
        mock_notifier = Mock(spec=BaseNotifier)
        manager.add_notifier(mock_notifier)

        assert len(manager.notifiers) == initial_count + 1
        assert mock_notifier in manager.notifiers

    def test_remove_notifier(self, mock_config, mock_platform_adapter):
        """测试移除通知器"""
        manager = NotifierManager(mock_config, mock_platform_adapter)
        initial_count = len(manager.notifiers)

        # 移除第一个通知器
        notifier_type = type(manager.notifiers[0])
        manager.remove_notifier(notifier_type)

        assert len(manager.notifiers) == initial_count - 1
        assert not any(isinstance(n, notifier_type) for n in manager.notifiers)

    def test_list_notifiers(self, mock_config, mock_platform_adapter):
        """测试列出通知器"""
        manager = NotifierManager(mock_config, mock_platform_adapter)
        notifier_names = manager.list_notifiers()
        assert len(notifier_names) > 0
        assert all(isinstance(name, str) for name in notifier_names)

    def test_get_enabled_notifiers(self, mock_config, mock_platform_adapter):
        """测试获取启用的通知器"""
        manager = NotifierManager(mock_config, mock_platform_adapter)

        # 设置第一个通知器为禁用
        if manager.notifiers:
            manager.notifiers[0].is_enabled = Mock(return_value=False)

        enabled_notifiers = manager.get_enabled_notifiers()
        assert len(enabled_notifiers) >= 0
        assert all(isinstance(name, str) for name in enabled_notifiers)


class TestNotificationBuilder:
    """测试通知内容构建器"""

    def _clear_host_env(self, monkeypatch):
        """清理宿主环境变量，避免宿主环境影响标题测试。"""
        for key in ("TERM_PROGRAM",):
            monkeypatch.delenv(key, raising=False)

    def test_build_notification_content_conversation_end(self, sample_event, monkeypatch):
        """测试构建会话结束通知内容"""
        self._clear_host_env(monkeypatch)
        builder = NotificationBuilder()
        expected_title = f"Claude Code - {builder._get_project_name(sample_event)}"
        content = builder.build_notification_content(sample_event)

        assert content["title"] == expected_title
        assert content["message"] == "会话已完成"
        assert content["subtitle"] == "IDE: Claude Code"
        assert content["level"] == NotificationLevel.SUCCESS

    def test_build_notification_content_operation_complete(self, sample_event, monkeypatch):
        """测试构建操作完成通知内容"""
        self._clear_host_env(monkeypatch)
        # 修改事件为非会话结束
        sample_event.conversation_end = False

        builder = NotificationBuilder()
        expected_title = f"Claude Code - {builder._get_project_name(sample_event)}"
        content = builder.build_notification_content(sample_event)

        assert content["title"] == expected_title
        assert content["message"] == "会话已完成"
        assert content["subtitle"] == "IDE: Claude Code"
        assert content["level"] == NotificationLevel.INFO

    def test_get_project_name_from_metadata_cwd(self, sample_event):
        """优先使用事件元数据中的 cwd"""
        sample_event.metadata = {"cwd": "/Users/tester/projects/demo-app"}

        builder = NotificationBuilder()
        assert builder._get_project_name(sample_event) == "demo-app"

    def test_get_project_name_from_environment_context(self, sample_event):
        """可以从 environment_context 中提取 cwd"""
        sample_event.metadata = {
            "environment_context": "<environment_context><cwd>/tmp/workspace/project-x</cwd></environment_context>"
        }

        builder = NotificationBuilder()
        assert builder._get_project_name(sample_event) == "project-x"

    def test_get_project_name_from_codex_env(self, sample_event, monkeypatch):
        """缺少元数据时回退到 Codex 相关环境变量"""
        monkeypatch.setenv("CODEX_CWD", "/opt/work/foo-project")

        builder = NotificationBuilder()
        assert builder._get_project_name(sample_event) == "foo-project"

    def test_build_notification_content_custom(self, sample_event):
        """测试构建自定义通知内容"""
        builder = NotificationBuilder()
        content = builder.build_notification_content(
            sample_event,
            custom_title="Custom Title",
            custom_message="Custom Message"
        )

        assert content["title"] == "Custom Title"
        assert content["message"] == "Custom Message"

    def test_build_notification_content_uses_host_title_prefix(self, sample_event, monkeypatch):
        """宿主环境标题优先于 agent 标题。"""
        self._clear_host_env(monkeypatch)
        monkeypatch.setenv("TERM_PROGRAM", "vscode")
        sample_event.agent = "codex"
        sample_event.tool_name = None
        sample_event.metadata = {"cwd": "/tmp/workspace/demo"}

        builder = NotificationBuilder()
        content = builder.build_notification_content(sample_event)

        assert content["title"] == "vscode - demo"
        assert content["subtitle"] == "IDE: Codex"

    def test_build_notification_content_uses_event_message(self, sample_event, monkeypatch):
        """Parser 生成的事件消息应作为通知正文。"""
        self._clear_host_env(monkeypatch)
        sample_event.agent = "codex"
        sample_event.message = "Done and verified."
        sample_event.tool_name = None
        sample_event.metadata = {"cwd": "/tmp/workspace/demo"}

        builder = NotificationBuilder()
        content = builder.build_notification_content(sample_event)

        assert content["title"] == "Codex - demo"
        assert content["message"] == "Done and verified."

    def test_build_notification_content_uses_default_message_without_event_message(
        self, monkeypatch
    ):
        """缺少事件消息时继续使用默认正文。"""
        self._clear_host_env(monkeypatch)
        event = NotificationEvent(
            type="conversation_end",
            agent="codex",
            message=None,
            summary=None,
            timestamp="2024-01-01T12:00:00",
            conversation_end=True,
            is_last_turn=True,
            metadata={"cwd": "/tmp/workspace/demo"},
        )

        builder = NotificationBuilder()
        content = builder.build_notification_content(event)

        assert content["title"] == "Codex - demo"
        assert content["message"] == "回复结束啦！"

    def test_build_notification_content_no_summary_or_message(self, monkeypatch):
        """测试构建通知内容时没有摘要或消息"""
        self._clear_host_env(monkeypatch)
        event = NotificationEvent(
            type="conversation_end",
            agent="test-agent",
            message=None,
            summary=None,
            timestamp="2024-01-01T12:00:00",
            conversation_end=True,
            is_last_turn=True
        )

        builder = NotificationBuilder()
        expected_title = f"test-agent - {builder._get_project_name(event)}"
        content = builder.build_notification_content(event)

        assert content["title"] == expected_title
        assert content["message"] == "回复结束啦！"
        assert content["subtitle"] == "IDE: test-agent"

    def test_build_notification_content_uses_default_prefix_without_source(self, monkeypatch):
        """缺少 IDE 和 agent 信息时使用默认标题前缀。"""
        self._clear_host_env(monkeypatch)
        event = NotificationEvent(
            type="conversation_end",
            agent="",
            message=None,
            summary=None,
            timestamp="2024-01-01T12:00:00",
            conversation_end=True,
            is_last_turn=True,
            tool_name=None,
            metadata={"cwd": "/tmp/workspace/demo"},
        )

        builder = NotificationBuilder()
        content = builder.build_notification_content(event)

        assert content["title"] == "VibeNotification - demo"
        assert content["message"] == "回复结束啦！"
        assert content["subtitle"] == "IDE: IDE"

    def test_build_error_notification(self):
        """测试构建错误通知内容"""
        builder = NotificationBuilder()
        error = Exception("Test error")

        content = builder.build_error_notification(error, "Test context")

        assert content["title"] == "VibeNotification — 错误"
        assert "Test context" in content["message"]
        assert "Test error" in content["message"]
        assert content["subtitle"] == "请检查配置或日志"
        assert content["level"] == NotificationLevel.ERROR

    def test_build_error_notification_no_context(self):
        """测试构建错误通知内容时没有上下文"""
        builder = NotificationBuilder()
        error = Exception("Test error")

        content = builder.build_error_notification(error)

        assert content["title"] == "VibeNotification — 错误"
        assert content["message"] == "Test error"
