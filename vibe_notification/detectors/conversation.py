"""
会话结束检测器

检测会话是否结束
"""

import re
from typing import Any, Dict

# 定义常见的“本轮完成”事件类型关键字
TURN_COMPLETE_TYPES = {
    "agent-turn-complete",
    "turn-complete",
    "assistant-turn-complete",
    "assistant-message-complete",
    "assistant_turn_complete",
    "turn_complete",
}

# 常见结束原因字段
FINISH_REASONS = {"stop", "end", "complete", "completed", "done"}

CODEX_NOTIFY_EVENT_TYPES = {
    "agent-turn-complete",
    "turn-completed",
    "session-end",
}

CODEX_APP_SERVER_METHODS = {"turn/completed"}

CODEX_HOOK_EVENT_NAMES = {"sessionstart", "userpromptsubmit", "pretooluse", "posttooluse", "stop"}

CODEX_TERMINAL_PHASES = {"final-answer", "final_answer"}

CODEX_NON_TERMINAL_PHASES = {"commentary"}

CODEX_TERMINAL_STATUSES = {
    "completed",
    "complete",
    "finished",
    "done",
    "cancelled",
    "canceled",
    "interrupted",
    "failed",
    "error",
    "errored",
}

CODEX_NON_TERMINAL_STATUSES = {
    "created",
    "pending",
    "queued",
    "started",
    "running",
    "streaming",
    "in-progress",
    "in_progress",
    "continuing",
}

CODEX_PROGRESS_MESSAGE_PREFIXES = (
    "working on it",
    "let me",
    "i'll",
    "i will",
    "i am starting",
    "i'm starting",
    "starting to",
    "checking",
    "looking into",
    "reading",
    "first, i'll",
    "first i'll",
    "first i will",
    "我来",
    "我先",
    "我会先",
    "我会",
    "我将",
    "让我",
    "先读取",
    "先查看",
    "先检查",
    "先分析",
    "先看",
    "正在",
    "开始",
)

CODEX_ACKNOWLEDGEMENT_PREFIXES = (
    "ok",
    "okay",
    "sure",
    "got it",
    "understood",
    "sounds good",
    "好的",
    "好",
    "收到",
    "明白",
    "明白了",
    "行",
    "可以",
    "没问题",
)

CODEX_TERMINAL_MESSAGE_KEYWORDS = (
    "done",
    "fixed",
    "implemented",
    "updated",
    "verified",
    "completed",
    "finished",
    "resolved",
    "refactored",
    "root cause",
    "here is",
    "here's",
    "what i changed",
    "what i found",
    "the issue was",
    "the bug was",
    "原因是",
    "根因",
    "结论",
    "总结",
    "如下",
    "已完成",
    "完成了",
    "已修复",
    "修复了",
    "已更新",
    "更新了",
    "已验证",
    "验证通过",
    "处理好了",
    "已定位",
    "定位到",
)

CODEX_TERMINAL_MESSAGE_PATTERNS = (
    r"\b(i|we)\s+(fixed|implemented|updated|verified|completed|finished|resolved|refactored|changed|found)\b",
    r"\b(the issue|the bug|root cause)\s+(is|was)\b",
    r"\bhere(?:'s| is)\b",
    r"(已|已经).{0,8}(修复|完成|更新|验证|定位|处理)",
    r"(原因|根因).{0,8}(是|在于)",
)

_LEADING_PUNCTUATION = " \t\r\n,.;:!?，。；：！？-"


def _normalize_event_name(value: Any) -> str:
    """标准化事件名，统一比较格式。"""
    if not isinstance(value, str):
        return ""
    return value.replace("_", "-").strip().lower()


def _iter_nested_dicts(value: Any):
    """递归遍历嵌套字典，兼容 app-server 新负载。"""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_nested_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_nested_dicts(child)


def _looks_like_codex_payload(event: Dict[str, Any]) -> bool:
    """判断事件是否像 Codex CLI / hook / app-server 负载。"""
    codex_keys = {
        "thread-id", "thread_id",
        "turn-id", "turn_id",
        "input-messages", "input_messages",
        "last-assistant-message", "last_assistant_message",
        "hook_event_name", "session_id", "permission_mode",
        "stop_hook_active", "client",
    }

    if any(key in event for key in codex_keys):
        return True

    event_type = _normalize_event_name(event.get("type") or event.get("event"))
    if event_type in CODEX_NOTIFY_EVENT_TYPES:
        return True

    method = _normalize_event_name(event.get("method"))
    if method in CODEX_APP_SERVER_METHODS:
        return True

    for key in ("agent", "client"):
        value = event.get(key)
        if isinstance(value, str) and "codex" in value.lower():
            return True

    return False


def _extract_codex_assistant_message(event: Dict[str, Any]) -> str:
    """提取 Codex 负载中的 assistant 文本。"""
    for payload in _iter_nested_dicts(event):
        for key in ("last-assistant-message", "last_assistant_message"):
            value = payload.get(key)
            if isinstance(value, str):
                text = value.strip()
                if text:
                    return text

    for payload in _iter_nested_dicts(event):
        for key in ("agentMessage", "agent_message"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                value = nested.get("text")
                if isinstance(value, str):
                    text = value.strip()
                    if text:
                        return text

    value = event.get("message")
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text

    return ""


def _looks_like_codex_progress_message(message: str) -> bool:
    """判断 assistant 文本是否更像中间进度播报而非最终答复。"""
    if not isinstance(message, str):
        return False

    normalized = " ".join(message.strip().lower().split())
    if not normalized:
        return False

    if normalized in CODEX_ACKNOWLEDGEMENT_PREFIXES:
        return True

    candidate = normalized

    changed = True
    while changed and candidate:
        changed = False
        for prefix in CODEX_ACKNOWLEDGEMENT_PREFIXES:
            if candidate.startswith(prefix):
                remainder = candidate[len(prefix):]
                if not remainder or remainder[0] in _LEADING_PUNCTUATION:
                    candidate = remainder.lstrip(_LEADING_PUNCTUATION)
                    changed = True
                    break

    if not candidate:
        return True

    return any(candidate.startswith(prefix) for prefix in CODEX_PROGRESS_MESSAGE_PREFIXES)


def _looks_like_codex_terminal_message(message: str) -> bool:
    """判断 assistant 文本是否包含足够强的最终答复信号。"""
    if not isinstance(message, str):
        return False

    stripped = message.strip()
    if not stripped:
        return False

    normalized = " ".join(stripped.lower().split())

    if "```" in stripped or "\n" in stripped:
        return True

    if re.search(r"(?m)^\s*[-*]\s+\S", stripped):
        return True

    if any(keyword in normalized for keyword in CODEX_TERMINAL_MESSAGE_KEYWORDS):
        return True

    if any(re.search(pattern, normalized) for pattern in CODEX_TERMINAL_MESSAGE_PATTERNS):
        return True

    return len(stripped) >= 120


def _codex_turn_complete_has_terminal_content(event: Dict[str, Any]) -> bool:
    """判断 Codex turn-complete 事件是否带有更像最终回复的内容。"""
    assistant_message = _extract_codex_assistant_message(event)
    if not assistant_message:
        return False

    if _looks_like_codex_progress_message(assistant_message):
        return False

    return _looks_like_codex_terminal_message(assistant_message)


def _contains_codex_hook_event(event: Dict[str, Any]) -> bool:
    """检查负载任意层是否携带 Codex hook 事件。"""
    for payload in _iter_nested_dicts(event):
        hook_event_name = payload.get("hook_event_name") or payload.get("hookEventName")
        if _normalize_event_name(hook_event_name) in CODEX_HOOK_EVENT_NAMES:
            return True
    return False


def _collect_codex_phases(event: Dict[str, Any]) -> set[str]:
    """收集 Codex 响应 phase。"""
    phases = set()
    for payload in _iter_nested_dicts(event):
        phase = payload.get("phase")
        normalized = _normalize_event_name(phase)
        if normalized:
            phases.add(normalized)
    return phases


def _has_codex_terminal_phase(event: Dict[str, Any]) -> bool:
    """判断负载是否明确包含最终答复 phase。"""
    return any(phase in CODEX_TERMINAL_PHASES for phase in _collect_codex_phases(event))


def _collect_codex_statuses(event: Dict[str, Any]) -> set[str]:
    """收集 Codex turn/session status。"""
    statuses = set()
    for payload in _iter_nested_dicts(event):
        for key in ("status", "turn_status", "turnStatus", "state"):
            normalized = _normalize_event_name(payload.get(key))
            if normalized:
                statuses.add(normalized)

        for container_key in ("turn", "thread", "session", "conversation"):
            sub = payload.get(container_key)
            if not isinstance(sub, dict):
                continue
            for key in ("status", "turn_status", "turnStatus", "state"):
                normalized = _normalize_event_name(sub.get(key))
                if normalized:
                    statuses.add(normalized)
    return statuses


def _codex_structured_terminal_signal(event: Dict[str, Any]) -> bool | None:
    """读取结构化 phase/status 信号，True=终态，False=中间态，None=无结论。"""
    phases = _collect_codex_phases(event)
    statuses = _collect_codex_statuses(event)

    if any(status in CODEX_NON_TERMINAL_STATUSES for status in statuses):
        return False

    if any(phase in CODEX_TERMINAL_PHASES for phase in phases):
        return True

    if any(phase in CODEX_NON_TERMINAL_PHASES for phase in phases):
        return False

    if any(status in CODEX_TERMINAL_STATUSES for status in statuses):
        return True

    return None


def _detect_codex_conversation_end(event: Dict[str, Any]) -> bool:
    """基于 Codex 官方事件形状判断是否为真实 turn 结束。"""
    if _contains_codex_hook_event(event):
        return False

    event_type = _normalize_event_name(event.get("type") or event.get("event"))
    method = _normalize_event_name(event.get("method"))
    structured_signal = _codex_structured_terminal_signal(event)

    if event_type == "session-end":
        return False

    for key in ("is_last_turn", "conversation_end", "conversation_finished", "final", "closed"):
        if key in event and bool(event.get(key)):
            if structured_signal is False:
                return False
            return True

    if event_type in CODEX_NOTIFY_EVENT_TYPES or method in CODEX_APP_SERVER_METHODS:
        if structured_signal is False:
            return False
        if _has_codex_terminal_phase(event):
            return True
        if structured_signal is True:
            return _codex_turn_complete_has_terminal_content(event)
        return _codex_turn_complete_has_terminal_content(event)

    for container_key in ("payload", "metadata", "data", "details"):
        sub = event.get(container_key)
        if not isinstance(sub, dict):
            continue

        nested_type = _normalize_event_name(sub.get("type") or sub.get("event"))
        if nested_type == "session-end":
            return False

        for key in ("conversation_end", "conversation_finished", "is_last_turn", "final", "closed"):
            if key in sub and bool(sub.get(key)):
                nested_signal = _codex_structured_terminal_signal(sub)
                if nested_signal is False:
                    return False
                return True

        if nested_type in CODEX_NOTIFY_EVENT_TYPES:
            nested_signal = _codex_structured_terminal_signal(sub)
            if nested_signal is False:
                return False
            if _has_codex_terminal_phase(sub):
                return True
            if nested_signal is True:
                return _codex_turn_complete_has_terminal_content(sub)
            return _codex_turn_complete_has_terminal_content(sub)

        nested_method = _normalize_event_name(sub.get("method"))
        if nested_method in CODEX_APP_SERVER_METHODS:
            nested_signal = _codex_structured_terminal_signal(sub)
            if nested_signal is False:
                return False
            if _has_codex_terminal_phase(sub):
                return True
            if nested_signal is True:
                return _codex_turn_complete_has_terminal_content(sub)
            return _codex_turn_complete_has_terminal_content(sub)

    return False


def detect_conversation_end_from_hook(hook_data: Dict[str, Any]) -> bool:
    """从钩子数据检测会话结束"""
    # 复用通用检测逻辑
    if detect_conversation_end(hook_data):
        return True

    tool_name = hook_data.get("toolName", "") or hook_data.get("tool_name", "")

    # Claude/Codex 钩子是在模型完成一轮输出后触发的，默认视为该轮对话结束
    if tool_name:
        return True

    return False


def detect_conversation_end(event: Dict[str, Any]) -> bool:
    """检测会话是否结束"""
    if not isinstance(event, dict):
        return False

    if _looks_like_codex_payload(event):
        return _detect_codex_conversation_end(event)

    # 直接布尔标志
    for key in ("is_last_turn", "conversation_end", "conversation_finished", "final", "closed"):
        if key in event and bool(event.get(key)):
            return True

    # 事件类型语义：模型完成一轮输出
    event_type = _normalize_event_name(event.get("type") or event.get("event"))
    if event_type:
        if event_type in TURN_COMPLETE_TYPES or ("turn" in event_type and "complete" in event_type):
            return True

    # 结束/停止原因
    for key in ("finish_reason", "stop_reason", "stopReason", "reason"):
        reason = event.get(key)
        if isinstance(reason, str) and reason.lower() in FINISH_REASONS:
            return True

    # 检查嵌套字典
    for container_key in ("payload", "metadata", "data", "details"):
        sub = event.get(container_key)
        if isinstance(sub, dict):
            # 嵌套布尔标志
            for key in ("conversation_end", "conversation_finished", "is_last_turn", "final"):
                if key in sub and bool(sub.get(key)):
                    return True
            # 嵌套事件类型
            nested_type = _normalize_event_name(sub.get("type") or sub.get("event"))
            if nested_type:
                if nested_type in TURN_COMPLETE_TYPES or ("turn" in nested_type and "complete" in nested_type):
                    return True
            for key in ("finish_reason", "stop_reason", "reason"):
                reason = sub.get(key)
                if isinstance(reason, str) and reason.lower() in FINISH_REASONS:
                    return True

    # 状态字符串
    state = event.get("conversation_state") or event.get("state")
    if isinstance(state, str):
        if state.lower() in ("finished", "ended", "closed", "complete"):
            return True

    # turn/total 启发式
    try:
        turn = event.get("turn")
        total = event.get("total_turns") or event.get("turns_total") or event.get("total_turns_estimate")
        if isinstance(turn, int) and isinstance(total, int) and turn >= total:
            return True
    except Exception:
        pass

    return False
