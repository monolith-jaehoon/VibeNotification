try:
    from importlib import metadata
except ImportError:  # pragma: no cover - Python 3.7 compatibility
    import importlib_metadata as metadata

import vibe_notification


def test_resolve_version_prefers_pyproject_when_available(monkeypatch):
    """开发环境下应优先读取源码中的 pyproject 版本。"""
    monkeypatch.setattr(
        vibe_notification.metadata,
        "version",
        lambda name: "1.0.4",
    )

    assert vibe_notification._resolve_version() == vibe_notification._read_pyproject_version()
