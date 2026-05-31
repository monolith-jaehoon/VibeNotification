import json
import sys

from vibe_notification.detectors.conversation import detect_conversation_end
from vibe_notification.parsers.codex import CodexParser


def test_detect_conversation_end_ignores_assistant_message_event():
    """assistant-message 只是消息事件，不应直接视为本轮结束。"""
    event = {
        "type": "assistant-message",
        "agent": "codex",
        "message": "I am starting to work on this task.",
    }

    assert detect_conversation_end(event) is False


def test_detect_conversation_end_ignores_codex_user_prompt_submit_hook():
    """Codex 的 UserPromptSubmit hook 只是收到指令，不应通知。"""
    event = {
        "hook_event_name": "UserPromptSubmit",
        "cwd": "/tmp/project",
        "model": "gpt-5-codex",
        "permission_mode": "default",
        "prompt": "please fix this bug",
        "session_id": "session-1",
        "transcript_path": None,
    }

    assert detect_conversation_end(event) is False


def test_detect_conversation_end_ignores_codex_session_end_event():
    """SessionEnd/session-end 不是某次回复完成，不应触发通知。"""
    event = {
        "type": "session-end",
        "client": "codex-tui",
        "thread-id": "thread-1",
        "conversation_end": True,
    }

    assert detect_conversation_end(event) is False


def test_detect_conversation_end_ignores_nested_codex_session_end_event():
    """嵌套 session-end 即使带 conversation_end 标记也不应触发。"""
    event = {
        "client": "codex-tui",
        "thread-id": "thread-1",
        "data": {
            "type": "session-end",
            "conversation_end": True,
        },
    }

    assert detect_conversation_end(event) is False


def test_detect_conversation_end_ignores_codex_stop_hook_payload():
    """Codex Stop hook 输入不是 notify 事件，不应直接通知。"""
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

    assert detect_conversation_end(event) is False


def test_codex_parser_marks_official_agent_turn_complete_as_terminal(monkeypatch):
    """Codex 官方 legacy notify payload 应视为真实 turn 结束。"""
    event = {
        "type": "agent-turn-complete",
        "thread-id": "thread-1",
        "turn-id": "turn-1",
        "cwd": "/tmp/project",
        "client": "codex-tui",
        "input-messages": ["fix the tests"],
        "last-assistant-message": "Done and verified.",
    }
    monkeypatch.setattr(sys, "argv", ["python", "-m", "vibe_notification", json.dumps(event)])

    parser = CodexParser()
    parsed = parser.parse()

    assert parsed is not None
    assert parsed.type == "agent-turn-complete"
    assert parsed.message == "Done and verified."
    assert parsed.conversation_end is True
    assert parsed.is_last_turn is True


def test_detect_conversation_end_ignores_codex_turn_complete_without_final_message():
    """缺少最终 assistant 文本时，不应仅凭 turn-complete 就通知。"""
    event = {
        "type": "agent-turn-complete",
        "thread-id": "thread-1",
        "turn-id": "turn-1",
        "client": "codex-tui",
        "input-messages": ["fix the tests"],
    }

    assert detect_conversation_end(event) is False


def test_detect_conversation_end_rejects_legacy_codex_short_ack_reply():
    """legacy turn-complete 里的裸确认语过于歧义，不应仅凭文本触发通知。"""
    event = {
        "type": "agent-turn-complete",
        "thread-id": "thread-1",
        "turn-id": "turn-1",
        "client": "codex-tui",
        "input-messages": ["reply with exactly OK"],
        "last-assistant-message": "OK",
    }

    assert detect_conversation_end(event) is False


def test_detect_conversation_end_accepts_codex_short_final_reply_with_explicit_flag():
    """若 provider 明确给出 final 标记，短回复也应视为终态。"""
    event = {
        "type": "agent-turn-complete",
        "thread-id": "thread-1",
        "turn-id": "turn-1",
        "client": "codex-tui",
        "input-messages": ["reply with exactly OK"],
        "last-assistant-message": "OK",
        "final": True,
    }

    assert detect_conversation_end(event) is True


def test_detect_conversation_end_ignores_codex_progress_style_turn_complete():
    """provider 若提前发出进度播报，不应被当作最终回复。"""
    event = {
        "type": "agent-turn-complete",
        "thread-id": "thread-1",
        "turn-id": "turn-1",
        "client": "codex-tui",
        "input-messages": ["fix the tests"],
        "last-assistant-message": "Working on it",
    }

    assert detect_conversation_end(event) is False


def test_detect_conversation_end_ignores_codex_progress_style_turn_complete_in_chinese():
    """中文进度播报同样不应触发最终通知。"""
    event = {
        "type": "agent-turn-complete",
        "thread-id": "thread-1",
        "turn-id": "turn-1",
        "client": "codex-tui",
        "input-messages": ["fix the tests"],
        "last-assistant-message": "先读取仓库的 README，再确认问题位置。",
    }

    assert detect_conversation_end(event) is False


def test_detect_conversation_end_ignores_codex_acknowledgement_style_turn_complete_in_chinese():
    """收到用户消息后的确认语，不应被误判为最终通知。"""
    event = {
        "type": "agent-turn-complete",
        "thread-id": "thread-1",
        "turn-id": "turn-1",
        "client": "codex-tui",
        "input-messages": ["fix the tests"],
        "last-assistant-message": "好的，我来处理。先检查一下仓库。",
    }

    assert detect_conversation_end(event) is False


def test_detect_conversation_end_ignores_codex_acknowledgement_style_turn_complete_in_english():
    """英文确认语同样不应被误判为最终通知。"""
    event = {
        "type": "agent-turn-complete",
        "thread-id": "thread-1",
        "turn-id": "turn-1",
        "client": "codex-tui",
        "input-messages": ["fix the tests"],
        "last-assistant-message": "Sure, I will inspect the repository first.",
    }

    assert detect_conversation_end(event) is False


def test_detect_conversation_end_ignores_bare_codex_acknowledgement_in_chinese():
    """纯中文确认语本身不应触发最终通知。"""
    event = {
        "type": "agent-turn-complete",
        "thread-id": "thread-1",
        "turn-id": "turn-1",
        "client": "codex-tui",
        "input-messages": ["fix the tests"],
        "last-assistant-message": "好的",
    }

    assert detect_conversation_end(event) is False


def test_detect_conversation_end_ignores_bare_codex_acknowledgement_in_english():
    """纯英文确认语本身不应触发最终通知。"""
    event = {
        "type": "agent-turn-complete",
        "thread-id": "thread-1",
        "turn-id": "turn-1",
        "client": "codex-tui",
        "input-messages": ["fix the tests"],
        "last-assistant-message": "Sure",
    }

    assert detect_conversation_end(event) is False


def test_codex_parser_accepts_hook_payload_but_marks_it_non_terminal(monkeypatch):
    """误把 VibeNotification 接到 Codex hook 时，应静默跳过而不是误报。"""
    event = {
        "hook_event_name": "UserPromptSubmit",
        "cwd": "/tmp/project",
        "model": "gpt-5-codex",
        "permission_mode": "default",
        "prompt": "please fix this bug",
        "session_id": "session-1",
        "transcript_path": None,
    }
    monkeypatch.setattr(sys, "argv", ["python", "-m", "vibe_notification", json.dumps(event)])

    parser = CodexParser()

    assert parser.can_parse() is True

    parsed = parser.parse()

    assert parsed is not None
    assert parsed.type == "user-prompt-submit"
    assert parsed.message == "Codex 已接收用户指令"
    assert parsed.conversation_end is False
    assert parsed.is_last_turn is False


def test_codex_parser_accepts_codex_stop_hook_payload_from_stdin(monkeypatch):
    """与 Claude 同名的 Codex Stop hook 也应由 CodexParser 识别并静默跳过。"""
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

    class _MockStdin:
        def isatty(self):
            return False

        def read(self):
            return json.dumps(event)

    monkeypatch.setattr(sys, "stdin", _MockStdin())

    import vibe_notification.parsers._stdin as _stdin_mod
    monkeypatch.setattr(_stdin_mod, "_cache", _stdin_mod._UNREAD)

    parser = CodexParser()

    assert parser.can_parse() is True

    parsed = parser.parse()

    assert parsed is not None
    assert parsed.type == "stop-hook"
    assert parsed.agent == "codex-hook"
    assert parsed.conversation_end is False
    assert parsed.is_last_turn is False


def test_detect_conversation_end_ignores_codex_app_server_non_terminal_turn_completed():
    """新版 app-server 的中间态 turn/completed 不应被当作最终结束。"""
    event = {
        "method": "turn/completed",
        "client": "codex-app-server",
        "data": {
            "turn": {
                "id": "turn-1",
                "status": "in_progress",
            },
            "item": {
                "agentMessage": {
                    "id": "msg-1",
                    "text": "I've received your instructions and will inspect the repository first.",
                    "phase": "commentary",
                }
            },
        },
    }

    assert detect_conversation_end(event) is False


def test_detect_conversation_end_ignores_completed_commentary_without_final_answer():
    """completed 状态若只携带 commentary，仍不是最终答复。"""
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

    assert detect_conversation_end(event) is False


def test_codex_parser_marks_codex_app_server_terminal_turn_completed(monkeypatch):
    """新版 app-server 终态 turn/completed 应被识别为真实结束。"""
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
                    "text": "Finished the requested changes and verified the tests.",
                    "phase": "final_answer",
                }
            },
        },
    }
    monkeypatch.setattr(sys, "argv", ["python", "-m", "vibe_notification", json.dumps(event)])

    parser = CodexParser()
    parsed = parser.parse()

    assert parsed is not None
    assert parsed.type == "turn/completed"
    assert parsed.message == "Finished the requested changes and verified the tests."
    assert parsed.conversation_end is True
    assert parsed.is_last_turn is True


def test_detect_conversation_end_accepts_codex_app_server_short_final_reply():
    """结构化 final_answer/status 明确时，短回复也应视为终态。"""
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
                    "text": "OK",
                    "phase": "final_answer",
                }
            },
        },
    }

    assert detect_conversation_end(event) is True


def test_codex_parser_prefers_final_answer_over_commentary(monkeypatch):
    """同一 payload 同时有 commentary 和 final_answer 时，应优先取最终答复。"""
    event = {
        "method": "turn/completed",
        "client": "codex-app-server",
        "data": {
            "turn": {
                "id": "turn-1",
                "status": "completed",
            },
            "items": [
                {
                    "agentMessage": {
                        "id": "msg-1",
                        "text": "I'll inspect the repository first.",
                        "phase": "commentary",
                    }
                },
                {
                    "agentMessage": {
                        "id": "msg-2",
                        "text": "Implemented the fix and verified the workflow.",
                        "phase": "final_answer",
                    }
                },
            ],
        },
    }
    monkeypatch.setattr(sys, "argv", ["python", "-m", "vibe_notification", json.dumps(event)])

    parser = CodexParser()
    parsed = parser.parse()

    assert parsed is not None
    assert parsed.message == "Implemented the fix and verified the workflow."
    assert parsed.conversation_end is True


def test_codex_parser_captures_debug_payload_when_debug_enabled(monkeypatch, tmp_path, caplog):
    """DEBUG 模式下应记录原始 Codex payload，便于定位 provider 差异。"""
    event = {
        "type": "agent-turn-complete",
        "thread-id": "thread-1",
        "turn-id": "turn-1",
        "client": "codex-tui",
        "input-messages": ["fix the tests"],
        "last-assistant-message": "Done and verified.",
    }
    capture_path = tmp_path / "codex-events.jsonl"

    monkeypatch.setattr(sys, "argv", ["python", "-m", "vibe_notification", json.dumps(event)])
    monkeypatch.setattr(CodexParser, "DEBUG_CAPTURE_PATH", capture_path)
    caplog.set_level("DEBUG")

    parser = CodexParser()
    parsed = parser.parse()

    assert parsed is not None
    assert capture_path.exists() is True
    assert '"thread-id": "thread-1"' in capture_path.read_text(encoding="utf-8")
