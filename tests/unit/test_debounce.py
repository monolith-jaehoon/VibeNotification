"""测试 debounce 防抖模块"""

import json
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

from vibe_notification.debounce import (
    should_debounce,
    write_session_state,
    spawn_debounce_worker,
    handle_codex_turn_event,
    DEFAULT_COOLDOWN_SECONDS,
    SESSION_STATE_DIR,
)
from vibe_notification.models import NotificationEvent


def _make_turn_event(**overrides):
    """构造一个 Codex turn-complete 事件。"""
    base = {
        "type": "agent-turn-complete",
        "thread-id": "thread-1",
        "turn-id": "turn-1",
        "client": "codex-tui",
        "last-assistant-message": "Done and verified.",
    }
    base.update(overrides)
    return base


def _make_parsed_event(**overrides):
    """构造一个解析后的 NotificationEvent。"""
    base = NotificationEvent(
        type="agent-turn-complete",
        agent="codex",
        message="Done and verified.",
        summary="Done and verified.",
        timestamp="2026-04-06T12:00:00",
        conversation_end=True,
        is_last_turn=True,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


class TestShouldDebounce:
    """should_debounce 判断逻辑"""

    def test_codex_turn_complete_does_not_debounce_by_default(self):
        event = _make_parsed_event(type="agent-turn-complete", agent="codex")
        assert should_debounce(event) is False

    def test_codex_turn_complete_should_debounce_when_env_enabled(self):
        event = _make_parsed_event(type="agent-turn-complete", agent="codex")
        with patch.dict("os.environ", {"VIBE_DEBOUNCE_COOLDOWN": "8"}):
            assert should_debounce(event) is True

    def test_codex_turn_completed_should_debounce(self):
        event = _make_parsed_event(type="turn-completed", agent="codex")
        with patch.dict("os.environ", {"VIBE_DEBOUNCE_COOLDOWN": "8"}):
            assert should_debounce(event) is True

    def test_codex_app_server_turn_should_debounce(self):
        event = _make_parsed_event(type="turn/completed", agent="codex")
        with patch.dict("os.environ", {"VIBE_DEBOUNCE_COOLDOWN": "8"}):
            assert should_debounce(event) is True

    def test_session_end_bypasses_debounce(self):
        event = _make_parsed_event(type="session-end", agent="codex")
        assert should_debounce(event) is False

    def test_hook_events_bypass_debounce(self):
        for event_type in ("session-start", "user-prompt-submit", "stop-hook"):
            event = _make_parsed_event(type=event_type, agent="codex")
            assert should_debounce(event) is False, f"{event_type} should not debounce"

    def test_claude_code_events_bypass_debounce(self):
        event = _make_parsed_event(type="agent-turn-complete", agent="claude-code")
        assert should_debounce(event) is False

    def test_non_codex_agents_bypass_debounce(self):
        event = _make_parsed_event(type="agent-turn-complete", agent="cursor")
        assert should_debounce(event) is False


class TestWriteSessionState:
    """会话状态文件写入"""

    def test_default_state_dir_uses_tempdir(self):
        assert str(SESSION_STATE_DIR).startswith(tempfile.gettempdir())

    def test_writes_state_file(self, tmp_path):
        event_data = _make_turn_event()
        event = _make_parsed_event()

        with patch("vibe_notification.debounce.SESSION_STATE_DIR", tmp_path):
            state_path = write_session_state(event_data, event)

        assert state_path.exists()
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["event"]["type"] == "agent-turn-complete"
        assert state["cooldown"] == DEFAULT_COOLDOWN_SECONDS

    def test_uses_session_id_for_filename(self, tmp_path):
        event_data = _make_turn_event(session_id="sess-abc-123")
        event = _make_parsed_event()

        with patch("vibe_notification.debounce.SESSION_STATE_DIR", tmp_path):
            state_path = write_session_state(event_data, event)

        assert "sess-abc-123" in state_path.name

    def test_uses_thread_id_when_no_session_id(self, tmp_path):
        event_data = _make_turn_event(**{"thread-id": "thread-xyz"})
        event = _make_parsed_event()

        with patch("vibe_notification.debounce.SESSION_STATE_DIR", tmp_path):
            state_path = write_session_state(event_data, event)

        assert "thread-xyz" in state_path.name

    def test_cooldown_from_env(self, tmp_path):
        event_data = _make_turn_event()
        event = _make_parsed_event()

        with patch("vibe_notification.debounce.SESSION_STATE_DIR", tmp_path), \
             patch.dict("os.environ", {"VIBE_DEBOUNCE_COOLDOWN": "15"}):
            state_path = write_session_state(event_data, event)

        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["cooldown"] == 15


class TestSpawnDebounceWorker:
    """后台 worker 启动参数"""

    def test_passes_expected_state_mtime_to_worker(self, tmp_path):
        state_path = tmp_path / "state.json"
        state_path.write_text("{}", encoding="utf-8")
        expected_mtime_ns = state_path.stat().st_mtime_ns

        with patch("vibe_notification.debounce.subprocess.Popen") as mock_popen:
            spawn_debounce_worker(state_path, cooldown=3)

        mock_popen.assert_called_once()
        command = mock_popen.call_args[0][0]
        assert "--expected-mtime-ns" in command
        assert str(expected_mtime_ns) in command


class TestDebounceWorker:
    """后台 worker 发送前的状态文件新鲜度检查"""

    def _write_worker_state(self, state_path, message="Done and verified."):
        event = _make_parsed_event(message=message, summary=message)
        state = {
            "updated_at": "2026-04-06T12:00:00",
            "event": event.to_dict(),
            "raw": _make_turn_event(**{"last-assistant-message": message}),
            "cooldown": 1,
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")

    def test_worker_skips_when_state_file_changed(self, tmp_path, monkeypatch):
        from vibe_notification import _debounce_worker

        state_path = tmp_path / "thread.json"
        self._write_worker_state(state_path, "First event.")
        expected_mtime_ns = state_path.stat().st_mtime_ns

        self._write_worker_state(state_path, "Newer event.")
        os.utime(state_path, ns=(expected_mtime_ns + 1000, expected_mtime_ns + 1000))

        captured = {}

        class DummyNotifier:
            def process_event(self, event):
                captured["event"] = event

        monkeypatch.setattr(_debounce_worker.time, "sleep", lambda seconds: None)
        monkeypatch.setattr(_debounce_worker, "VibeNotifier", lambda: DummyNotifier())
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "_debounce_worker.py",
                "--state-path", str(state_path),
                "--cooldown", "1",
                "--expected-mtime-ns", str(expected_mtime_ns),
            ],
        )

        assert _debounce_worker.main() == 0
        assert "event" not in captured

    def test_worker_sends_when_state_file_is_current(self, tmp_path, monkeypatch):
        from vibe_notification import _debounce_worker

        state_path = tmp_path / "thread.json"
        self._write_worker_state(state_path)
        expected_mtime_ns = state_path.stat().st_mtime_ns
        captured = {}

        class DummyNotifier:
            def process_event(self, event):
                captured["event"] = event

        monkeypatch.setattr(_debounce_worker.time, "sleep", lambda seconds: None)
        monkeypatch.setattr(_debounce_worker, "VibeNotifier", lambda: DummyNotifier())
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "_debounce_worker.py",
                "--state-path", str(state_path),
                "--cooldown", "1",
                "--expected-mtime-ns", str(expected_mtime_ns),
            ],
        )

        assert _debounce_worker.main() == 0
        assert captured["event"].conversation_end is True
        assert captured["event"].is_last_turn is True
        assert not state_path.exists()


class TestHandleCodexTurnEvent:
    """handle_codex_turn_event 集成逻辑"""

    def test_debounces_codex_turn_event(self, tmp_path):
        event_data = _make_turn_event()
        event = _make_parsed_event()

        with patch("vibe_notification.debounce.SESSION_STATE_DIR", tmp_path), \
             patch("vibe_notification.debounce.spawn_debounce_worker") as mock_spawn, \
             patch.dict("os.environ", {"VIBE_DEBOUNCE_COOLDOWN": "8"}):
            result = handle_codex_turn_event(event_data, event)

        assert result is True
        mock_spawn.assert_called_once()

    def test_does_not_debounce_codex_turn_event_by_default(self, tmp_path):
        event_data = _make_turn_event()
        event = _make_parsed_event()

        with patch("vibe_notification.debounce.SESSION_STATE_DIR", tmp_path), \
             patch("vibe_notification.debounce.spawn_debounce_worker") as mock_spawn:
            result = handle_codex_turn_event(event_data, event)

        assert result is False
        mock_spawn.assert_not_called()

    def test_skips_non_codex_event(self, tmp_path):
        event_data = {"type": "session-end"}
        event = _make_parsed_event(type="session-end", agent="codex")

        with patch("vibe_notification.debounce.SESSION_STATE_DIR", tmp_path):
            result = handle_codex_turn_event(event_data, event)

        assert result is False

    def test_skips_claude_code_event(self, tmp_path):
        event_data = {"type": "agent-turn-complete", "agent": "claude-code"}
        event = _make_parsed_event(agent="claude-code")

        with patch("vibe_notification.debounce.SESSION_STATE_DIR", tmp_path):
            result = handle_codex_turn_event(event_data, event)

        assert result is False


class TestCodexParserStdin:
    """Codex 解析器的 stdin 读取支持"""

    def test_reads_event_from_stdin(self, monkeypatch):
        """当 argv 为空但 stdin 有 JSON 数据时，应从 stdin 读取。"""
        from vibe_notification.parsers.codex import CodexParser

        event = {
            "type": "agent-turn-complete",
            "thread-id": "thread-1",
            "client": "codex-tui",
            "last-assistant-message": "Finished work.",
        }

        monkeypatch.setattr(sys, "argv", ["python", "-m", "vibe_notification"])

        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        mock_stdin.read.return_value = json.dumps(event)
        monkeypatch.setattr(sys, "stdin", mock_stdin)

        # 重置 stdin 缓存以使用新的 mock stdin
        import vibe_notification.parsers._stdin as _stdin_mod
        monkeypatch.setattr(_stdin_mod, "_cache", _stdin_mod._UNREAD)

        parser = CodexParser()
        data = parser._load_event_data()

        assert data is not None
        assert data["type"] == "agent-turn-complete"
        assert data["last-assistant-message"] == "Finished work."

    def test_prefers_argv_over_stdin(self, monkeypatch):
        """当 argv 和 stdin 都有数据时，优先使用 argv。"""
        from vibe_notification.parsers.codex import CodexParser

        argv_event = {"type": "from-argv", "client": "codex-tui"}
        stdin_event = {"type": "from-stdin", "client": "codex-tui"}

        monkeypatch.setattr(
            sys, "argv",
            ["python", "-m", "vibe_notification", json.dumps(argv_event)],
        )

        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        mock_stdin.read.return_value = json.dumps(stdin_event)
        monkeypatch.setattr(sys, "stdin", mock_stdin)

        parser = CodexParser()
        data = parser._load_event_data()

        assert data is not None
        assert data["type"] == "from-argv"

    def test_returns_none_when_no_data(self, monkeypatch):
        """当 argv 和 stdin 都没有数据时，返回 None。"""
        from vibe_notification.parsers.codex import CodexParser

        monkeypatch.setattr(sys, "argv", ["python", "-m", "vibe_notification"])

        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        monkeypatch.setattr(sys, "stdin", mock_stdin)

        parser = CodexParser()
        data = parser._load_event_data()

        assert data is None


class TestNewHookEventNames:
    """新增 hook 事件名的识别"""

    def test_pretooluse_recognized_as_hook(self):
        from vibe_notification.detectors.conversation import detect_conversation_end

        event = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "cwd": "/tmp/project",
        }
        assert detect_conversation_end(event) is False

    def test_posttooluse_recognized_as_hook(self):
        from vibe_notification.detectors.conversation import detect_conversation_end

        event = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "cwd": "/tmp/project",
        }
        assert detect_conversation_end(event) is False

    def test_codex_parser_handles_pretooluse(self, monkeypatch):
        from vibe_notification.parsers.codex import CodexParser

        event = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "cwd": "/tmp/project",
        }
        monkeypatch.setattr(sys, "argv", ["python", "-m", "vibe_notification", json.dumps(event)])

        parser = CodexParser()
        parsed = parser.parse()

        assert parsed is not None
        assert parsed.type == "pre-tool-use"
        assert parsed.conversation_end is False

    def test_codex_parser_handles_posttooluse(self, monkeypatch):
        from vibe_notification.parsers.codex import CodexParser

        event = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "cwd": "/tmp/project",
        }
        monkeypatch.setattr(sys, "argv", ["python", "-m", "vibe_notification", json.dumps(event)])

        parser = CodexParser()
        parsed = parser.parse()

        assert parsed is not None
        assert parsed.type == "post-tool-use"
        assert parsed.conversation_end is False
