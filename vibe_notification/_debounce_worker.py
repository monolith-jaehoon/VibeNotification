#!/usr/bin/env python3
"""
Codex 防抖后台 Worker

由 debounce.py 以子进程方式启动。等待冷却期结束后，
检查会话状态文件是否仍指向本次事件；若是，则发送通知。
"""

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

# 将项目根目录加入 sys.path 以便导入 vibe_notification
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from vibe_notification.models import NotificationEvent
from vibe_notification.core import VibeNotifier


def _user_temp_root() -> Path:
    if hasattr(os, "getuid"):
        token = str(os.getuid())
    else:
        value = os.environ.get("USERNAME") or os.environ.get("USER") or "default"
        token = "".join(c if c.isalnum() or c in "-_." else "_" for c in value) or "default"

    return Path(tempfile.gettempdir()) / f"vibe-notification-{token}"


def _worker_log_path() -> Path:
    return _user_temp_root() / "debounce-worker.log"


def main() -> int:
    parser = argparse.ArgumentParser(description="VibeNotification debounce worker")
    parser.add_argument("--state-path", required=True, help="会话状态文件路径")
    parser.add_argument("--cooldown", required=True, type=int, help="冷却期（秒）")
    parser.add_argument(
        "--expected-mtime-ns",
        required=True,
        type=int,
        help="worker 启动时观察到的状态文件 mtime_ns",
    )
    args = parser.parse_args()

    state_path = Path(args.state_path)
    cooldown = args.cooldown
    expected_mtime_ns = args.expected_mtime_ns

    # 等待冷却期
    time.sleep(cooldown)

    # 冷却结束后检查会话文件
    if not state_path.exists():
        return 0

    try:
        current_mtime_ns = state_path.stat().st_mtime_ns
    except OSError:
        return 0

    if current_mtime_ns != expected_mtime_ns:
        return 0

    try:
        with state_path.open("r", encoding="utf-8") as fp:
            state = json.load(fp)
    except (json.JSONDecodeError, OSError):
        return 1

    event_dict = state.get("event", {})

    if not event_dict:
        return 0

    # 如果状态文件仍然存在且未被替换，说明这是最后一个事件，发送通知
    # 但标记 conversation_end 为 True，因为这是「确认的最终 turn」
    event_dict["conversation_end"] = True
    event_dict["is_last_turn"] = True

    try:
        event = NotificationEvent.from_dict(event_dict)
    except Exception:
        return 1

    try:
        notifier = VibeNotifier()
        notifier.process_event(event)
    except Exception as exc:
        # worker 在后台运行，只能写日志
        log_path = _worker_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=str(log_path),
            level=logging.DEBUG,
        )
        logging.getLogger(__name__).error("Worker 发送通知失败: %s", exc, exc_info=True)
        return 1

    # 发送完成后清理状态文件
    try:
        state_path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
