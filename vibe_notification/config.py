"""
配置管理模块

负责加载、保存和管理配置
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional
from .models import NotificationConfig


def get_config_path() -> Path:
    """获取配置文件路径"""
    # 优先使用用户配置目录
    config_dir = Path.home() / ".config" / "vibe-notification"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"


def load_config(config_path: Optional[os.PathLike | str] = None) -> NotificationConfig:
    """加载配置

    如果指定路径则使用提供的配置文件，否则读取默认位置。
    """
    config_path = Path(config_path) if config_path else get_config_path()

    if not config_path.exists():
        return NotificationConfig()

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        config = NotificationConfig.from_dict(data)
        # 兼容旧配置或手工编辑的语言字段
        lang = (getattr(config, "language", "zh") or "zh").lower()
        config.language = lang if lang in ("zh", "en") else "zh"
        return config
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        # 配置文件损坏，使用默认配置
        print(f"警告：配置文件损坏，使用默认配置: {e}")
        return NotificationConfig()


def save_config(config: NotificationConfig, config_path: Optional[os.PathLike | str] = None) -> None:
    """保存配置"""
    config_path = Path(config_path) if config_path else get_config_path()

    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"保存配置失败: {e}")


def get_env_config() -> NotificationConfig:
    """从环境变量获取配置"""
    config = load_config()

    # 覆盖环境变量
    if os.environ.get("VIBE_NOTIFICATION_SOUND") == "0":
        config.enable_sound = False
    if os.environ.get("VIBE_NOTIFICATION_NOTIFY") == "0":
        config.enable_notification = False
    if os.environ.get("VIBE_NOTIFICATION_LOG_LEVEL"):
        config.log_level = os.environ["VIBE_NOTIFICATION_LOG_LEVEL"]
    if os.environ.get("VIBE_NOTIFICATION_SOUND_VOLUME"):
        try:
            volume = float(os.environ["VIBE_NOTIFICATION_SOUND_VOLUME"])
            config.sound_volume = max(0.0, min(1.0, volume))
        except ValueError:
            pass
    if os.environ.get("VIBE_NOTIFICATION_SOUND_TYPE"):
        config.sound_type = os.environ["VIBE_NOTIFICATION_SOUND_TYPE"]

    if os.environ.get("VIBE_NOTIFICATION_LANGUAGE"):
        lang = os.environ["VIBE_NOTIFICATION_LANGUAGE"].lower()
        if lang in ("zh", "en"):
            config.language = lang

    if os.environ.get("VIBE_NOTIFICATION_SENDER_MODE"):
        sender_mode = os.environ["VIBE_NOTIFICATION_SENDER_MODE"].strip().lower()
        if sender_mode in {"auto", "off", "force"}:
            config.macos_sender_mode = sender_mode

    return config
