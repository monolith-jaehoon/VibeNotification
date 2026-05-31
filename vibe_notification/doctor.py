"""
本地集成诊断工具

帮助排查 Claude Code / Codex / VibeNotification 的接入语义是否匹配。
"""

from __future__ import annotations

import json
import platform
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from .config import load_config


@dataclass
class DoctorFinding:
    level: str
    scope: str
    summary: str
    recommendation: Optional[str] = None


def _load_json(path: Path) -> Optional[dict]:
    if not path.is_file():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _has_hook(data: dict, hook_name: str) -> bool:
    hooks = data.get("hooks")
    return isinstance(hooks, dict) and hook_name in hooks


def _analyze_claude_settings(path: Path) -> Iterable[DoctorFinding]:
    data = _load_json(path)
    if data is None:
        yield DoctorFinding(
            level="WARN",
            scope="claude",
            summary=f"未发现可解析的 Claude Code 配置: {path}",
            recommendation="如需“回复结束就通知”，请在 ~/.claude/settings.json 配置 Stop hook。",
        )
        return

    has_stop = _has_hook(data, "Stop")
    has_session_end = _has_hook(data, "SessionEnd")

    if has_stop:
        yield DoctorFinding(
            level="INFO",
            scope="claude",
            summary="Claude Code 已配置 Stop hook。",
            recommendation="Stop 是“每轮回复结束”而不是“整个会话退出”。",
        )
    else:
        yield DoctorFinding(
            level="WARN",
            scope="claude",
            summary="Claude Code 未配置 Stop hook。",
        )

    if has_session_end:
        yield DoctorFinding(
            level="WARN",
            scope="claude",
            summary="Claude Code 已配置 SessionEnd hook；VibeNotification 默认会忽略它。",
            recommendation="如果你只关心“某次回复结束”，建议移除 SessionEnd，只保留 Stop hook，避免多余调用。",
        )
    else:
        yield DoctorFinding(
            level="INFO",
            scope="claude",
            summary="Claude Code 未配置 SessionEnd hook（可选）。",
            recommendation="如果你只关心“某次回复结束”，当前的 Stop hook 就够了；无需配置 SessionEnd。",
        )


def _analyze_codex_config(path: Path) -> Iterable[DoctorFinding]:
    if not path.is_file():
        yield DoctorFinding(
            level="WARN",
            scope="codex",
            summary=f"未发现 Codex 配置文件: {path}",
            recommendation="如需通知，请在 ~/.codex/config.toml 配置 notify，或用 --wrap-codex 走 session-end 模式。",
        )
        return

    content = path.read_text(encoding="utf-8")
    has_notify = re.search(r"(?m)^\s*notify\s*=", content) is not None

    if has_notify:
        yield DoctorFinding(
            level="INFO",
            scope="codex",
            summary="Codex 已配置 notify 命令。",
            recommendation="按 OpenAI 当前文档，notify 只在 agent 完成一轮回复时触发，不等于整个 Codex 进程退出。",
        )
    else:
        yield DoctorFinding(
            level="WARN",
            scope="codex",
            summary="Codex 未配置 notify 命令。",
        )

    yield DoctorFinding(
        level="INFO",
        scope="codex",
        summary="如果你只想在 Codex 进程退出后通知，应使用 `python -m vibe_notification --wrap-codex` 包装启动 Codex。",
    )


def _analyze_vibe_runtime(path: Path) -> Iterable[DoctorFinding]:
    if not path.is_file():
        yield DoctorFinding(
            level="WARN",
            scope="vibe",
            summary=f"未发现 VibeNotification 日志文件: {path}",
        )
        return

    modified = datetime.fromtimestamp(path.stat().st_mtime)
    yield DoctorFinding(
        level="OK",
        scope="vibe",
        summary=f"VibeNotification 日志存在，最近更新时间: {modified.strftime('%Y-%m-%d %H:%M:%S')}",
    )


def _analyze_vibe_config(path: Path) -> Iterable[DoctorFinding]:
    config = load_config(path)

    if config.enable_notification:
        yield DoctorFinding(
            level="OK",
            scope="vibe",
            summary="VibeNotification 系统弹窗已启用。",
        )
    else:
        yield DoctorFinding(
            level="WARN",
            scope="vibe",
            summary="VibeNotification 系统弹窗当前被禁用。",
            recommendation="请在 ~/.config/vibe-notification/config.json 中把 enable_notification 设为 true，或移除 VIBE_NOTIFICATION_NOTIFY=0。",
        )

    if config.enable_sound:
        yield DoctorFinding(
            level="OK",
            scope="vibe",
            summary="VibeNotification 声音提醒已启用。",
        )


def _analyze_notification_backend() -> Iterable[DoctorFinding]:
    if platform.system() != "Darwin":
        return

    if shutil.which("terminal-notifier"):
        yield DoctorFinding(
            level="OK",
            scope="macos",
            summary="检测到 terminal-notifier，VibeNotification 将优先使用它发送弹窗。",
        )
        yield DoctorFinding(
            level="INFO",
            scope="macos",
            summary="Claude Code 场景默认不绑定 sender，以提高横幅弹窗稳定性。",
            recommendation="如需沿用宿主 App 图标/归属，可显式设置 VIBE_NOTIFICATION_SENDER_MODE=auto 或 force。",
        )
        yield DoctorFinding(
            level="INFO",
            scope="macos",
            summary="终端/CLI 宿主场景也会默认不绑定 sender，避免继承 VS Code / Terminal 等宿主 App 的通知样式。",
            recommendation="如果通知只进入通知中心，请到 系统设置 > 通知 检查 terminal-notifier 或宿主 App 的允许通知、横幅/提醒样式，以及专注模式/屏幕共享限制。",
        )
    elif shutil.which("osascript"):
        yield DoctorFinding(
            level="INFO",
            scope="macos",
            summary="未检测到 terminal-notifier，将回退到 osascript 发送弹窗。",
            recommendation="若通知命令执行成功但仍无横幅，请检查系统设置中的通知权限与专注模式。",
        )
    else:
        yield DoctorFinding(
            level="WARN",
            scope="macos",
            summary="既未检测到 terminal-notifier，也未检测到 osascript，无法发送 macOS 弹窗。",
        )


def run_doctor() -> List[DoctorFinding]:
    home = Path.home()
    findings: List[DoctorFinding] = []
    findings.extend(_analyze_claude_settings(home / ".claude" / "settings.json"))
    findings.extend(_analyze_codex_config(home / ".codex" / "config.toml"))
    findings.extend(_analyze_vibe_config(home / ".config" / "vibe-notification" / "config.json"))
    findings.extend(_analyze_notification_backend())
    findings.extend(_analyze_vibe_runtime(home / ".config" / "vibe-notification" / "vibe_notification.log"))
    return findings


def format_doctor_report(findings: List[DoctorFinding]) -> str:
    lines = ["VibeNotification Doctor", ""]

    for finding in findings:
        lines.append(f"[{finding.level}] {finding.scope}: {finding.summary}")
        if finding.recommendation:
            lines.append(f"  -> {finding.recommendation}")

    return "\n".join(lines)
