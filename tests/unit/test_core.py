from unittest.mock import Mock
import io
import json
import sys

from vibe_notification.core import VibeNotifier
from vibe_notification.models import NotificationConfig, NotificationEvent


def test_process_event_skips_non_terminal_event_when_detection_enabled():
    """默认只在会话结束时通知，中间事件应跳过。"""
    config = NotificationConfig(
        enable_sound=True,
        enable_notification=True,
        detect_conversation_end=True,
    )
    notifier = VibeNotifier(config)
    notifier.notification_builder = Mock(
        build_notification_content=Mock(
            return_value={
                "title": "Demo",
                "message": "Reply finished!",
                "level": "INFO",
                "subtitle": "IDE: Codex",
            }
        )
    )
    notifier.notifier_manager = Mock()

    event = NotificationEvent(
        type="assistant-message",
        agent="codex",
        message="working",
        summary="",
        timestamp="2026-03-21T00:00:00",
        conversation_end=False,
        is_last_turn=False,
    )

    notifier.process_event(event)

    notifier.notification_builder.build_notification_content.assert_not_called()
    notifier.notifier_manager.send_notifications.assert_not_called()


def test_process_event_allows_non_terminal_event_when_detection_disabled():
    """关闭结束检测后，允许按旧行为发送通知。"""
    config = NotificationConfig(
        enable_sound=True,
        enable_notification=True,
        detect_conversation_end=False,
    )
    notifier = VibeNotifier(config)
    notifier.notification_builder = Mock(
        build_notification_content=Mock(
            return_value={
                "title": "Demo",
                "message": "Reply finished!",
                "level": "INFO",
                "subtitle": "IDE: Codex",
            }
        )
    )
    notifier.notifier_manager = Mock()

    event = NotificationEvent(
        type="assistant-message",
        agent="codex",
        message="working",
        summary="",
        timestamp="2026-03-21T00:00:00",
        conversation_end=False,
        is_last_turn=False,
    )

    notifier.process_event(event)

    notifier.notification_builder.build_notification_content.assert_called_once_with(event)
    notifier.notifier_manager.send_notifications.assert_called_once_with(
        title="Demo",
        message="Reply finished!",
        level="INFO",
        subtitle="IDE: Codex",
    )


def test_process_event_passes_metadata_cwd_as_focus_path():
    """Codex 事件中的 cwd 应传给系统通知点击聚焦路径。"""
    config = NotificationConfig(
        enable_sound=True,
        enable_notification=True,
        detect_conversation_end=True,
    )
    notifier = VibeNotifier(config)
    notifier.notification_builder = Mock(
        build_notification_content=Mock(
            return_value={
                "title": "Demo",
                "message": "Reply finished!",
                "level": "INFO",
                "subtitle": "IDE: Codex",
            }
        )
    )
    notifier.notifier_manager = Mock()

    event = NotificationEvent(
        type="agent-turn-complete",
        agent="codex",
        message="done",
        summary="done",
        timestamp="2026-03-21T00:00:00",
        conversation_end=True,
        is_last_turn=True,
        metadata={"cwd": " /tmp/codex workspace "},
    )

    notifier.process_event(event)

    notifier.notifier_manager.send_notifications.assert_called_once_with(
        title="Demo",
        message="Reply finished!",
        level="INFO",
        subtitle="IDE: Codex",
        focus_path="/tmp/codex workspace",
    )


def test_run_skips_codex_stop_hook_payload_from_stdin(monkeypatch):
    """Codex Stop hook 与 notify 同时存在时，不应提前发送第一条通知。"""
    event = {
        "hook_event_name": "Stop",
        "cwd": "/tmp/project",
        "model": "gpt-5-codex",
        "permission_mode": "default",
        "last_assistant_message": "Working on it",
        "session_id": "session-1",
        "stop_hook_active": False,
        "transcript_path": None,
    }
    monkeypatch.setattr(sys, "argv", ["python", "-m", "vibe_notification"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))

    import vibe_notification.parsers._stdin as _stdin_mod
    monkeypatch.setattr(_stdin_mod, "_cache", _stdin_mod._UNREAD)

    notifier = VibeNotifier(
        NotificationConfig(
            enable_sound=True,
            enable_notification=True,
            detect_conversation_end=True,
        )
    )
    notifier.notification_builder = Mock(
        build_notification_content=Mock(
            return_value={
                "title": "Demo",
                "message": "Reply finished!",
                "level": "INFO",
                "subtitle": "IDE: Codex",
            }
        )
    )
    notifier.notifier_manager = Mock()

    notifier.run()

    notifier.notification_builder.build_notification_content.assert_not_called()
    notifier.notifier_manager.send_notifications.assert_not_called()


def test_run_skips_codex_acknowledgement_turn_complete_payload(monkeypatch):
    """Codex 刚接到用户消息时的确认语，不应触发通知。"""
    event = {
        "type": "agent-turn-complete",
        "thread-id": "thread-1",
        "turn-id": "turn-1",
        "cwd": "/tmp/project",
        "client": "codex-tui",
        "input-messages": ["please fix this bug"],
        "last-assistant-message": "Sure, I will inspect the repository first.",
    }
    monkeypatch.setattr(sys, "argv", ["python", "-m", "vibe_notification", json.dumps(event)])

    notifier = VibeNotifier(
        NotificationConfig(
            enable_sound=True,
            enable_notification=True,
            detect_conversation_end=True,
        )
    )
    notifier.notification_builder = Mock(
        build_notification_content=Mock(
            return_value={
                "title": "Demo",
                "message": "Reply finished!",
                "level": "INFO",
                "subtitle": "IDE: Codex",
            }
        )
    )
    notifier.notifier_manager = Mock()

    notifier.run()

    notifier.notification_builder.build_notification_content.assert_not_called()
    notifier.notifier_manager.send_notifications.assert_not_called()


def test_run_skips_claude_session_end_hook(monkeypatch):
    """Claude SessionEnd 不是回复完成，默认结束检测应跳过。"""
    monkeypatch.setenv("CLAUDE_HOOK_EVENT", "SessionEnd")

    notifier = VibeNotifier(
        NotificationConfig(
            enable_sound=True,
            enable_notification=True,
            detect_conversation_end=True,
        )
    )
    notifier.notification_builder = Mock(
        build_notification_content=Mock(
            return_value={
                "title": "Demo",
                "message": "Reply finished!",
                "level": "INFO",
                "subtitle": "IDE: Claude",
            }
        )
    )
    notifier.notifier_manager = Mock()

    notifier.run()

    notifier.notification_builder.build_notification_content.assert_not_called()
    notifier.notifier_manager.send_notifications.assert_not_called()


def test_run_skips_codex_completed_commentary_payload(monkeypatch):
    """Codex 接收消息后的 completed/commentary 事件不应触发提示音。"""
    event = {
        "method": "turn/completed",
        "client": "codex-app-server",
        "data": {
            "turn": {
                "id": "turn-1",
                "status": "completed",
            },
            "item": {
                "agentMessage": {
                    "id": "msg-1",
                    "text": "好的，我先检查仓库结构。",
                    "phase": "commentary",
                }
            },
        },
    }
    monkeypatch.setattr(sys, "argv", ["python", "-m", "vibe_notification", json.dumps(event)])

    notifier = VibeNotifier(
        NotificationConfig(
            enable_sound=True,
            enable_notification=True,
            detect_conversation_end=True,
        )
    )
    notifier.notification_builder = Mock(
        build_notification_content=Mock(
            return_value={
                "title": "Demo",
                "message": "Reply finished!",
                "level": "INFO",
                "subtitle": "IDE: Codex",
            }
        )
    )
    notifier.notifier_manager = Mock()

    notifier.run()

    notifier.notification_builder.build_notification_content.assert_not_called()
    notifier.notifier_manager.send_notifications.assert_not_called()
