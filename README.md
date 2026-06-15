<div align="center">

# VibeNotification

[![PyPI](https://img.shields.io/pypi/v/vibe-notification.svg)](https://pypi.org/project/vibe-notification/)
[![Python](https://img.shields.io/pypi/pyversions/vibe-notification.svg)](https://pypi.org/project/vibe-notification/)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)](#installation)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

English | [中文](README.zh.md)

<strong> Stop waiting when vibe coding — Give a notification when Claude Code or Codex finishes replies — </strong>

[Blog walkthrough (Chinese): AI应用系列 一个简单的Vibe coding的通知系统](https://blognas.hwb0307.com/ai/6659)

</div>

![image-20251221214216954](https://chevereto.hwb0307.com/images/2025/12/21/image-20251221214216954.png)

## Installation

- Stable (PyPI): `pip install vibe-notification`
- Dev: `pip install -e .`
- Optional venv: `python -m venv venv && source venv/bin/activate`
- Verify: `python -m vibe_notification --test` (should toast and chime when enabled)
- Interactive setup: `python -m vibe_notification --config`
  - Default config file: `~/.config/vibe-notification/config.json`
  - Make sure both sound and system notifications are enabled

## Quick Start

### Claude Code

- Recommended hook: `Stop` (when each main reply completes).
- If what you want is "notify me when this reply is done", use `Stop`. That is the default and the only recommended hook.
- Do not attach the notifier command to `SessionEnd` or `SubagentStop`: VibeNotification ignores them by default to avoid duplicate alerts from session-exit, subagent, or tool-chain lifecycle events.
- On macOS, VibeNotification now defaults to `sender` off in Claude Code hook contexts and terminal-hosted CLI contexts for more reliable banners. If you explicitly want host-app attribution/icon, set `VIBE_NOTIFICATION_SENDER_MODE=auto`.
- If a notification appears only in Notification Center, check `System Settings > Notifications` for the effective app (`terminal-notifier` when sender is off, or the host app such as VS Code / Terminal when sender is auto/force). Make sure notifications are allowed, banner/alert style is enabled, and Focus is not suppressing them.
- Edit `~/.claude/settings.json` and add a Stop hook:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "env VIBE_NOTIFICATION_SENDER_MODE=off python -m vibe_notification"
          }
        ]
      }
    ]
  }
}
```

- Example full settings snippet with environment variables:

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "xxx",
    "ANTHROPIC_BASE_URL": "https://open.bigmodel.cn/api/anthropic",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-4.6",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-4.6",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-4.6",
    "ANTHROPIC_MODEL": "glm-4.6",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "DISABLE_ERROR_REPORTING": "1",
    "DISABLE_TELEMETRY": "1",
    "MCP_TIMEOUT": "60000"
  },
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "command": "env VIBE_NOTIFICATION_SENDER_MODE=off python -m vibe_notification",
            "type": "command"
          }
        ]
      }
    ]
  },
  "includeCoAuthoredBy": false,
  "outputStyle": "engineer-professional"
}
```

### Codex CLI

Add a notifier command to `~/.codex/config.toml` so Codex triggers VibeNotification when the agent actually finishes a turn (`agent-turn-complete`):

```toml
notify = ["python3", "-m", "vibe_notification"]
```

Note: `notify` is turn-based, not session-exit-based.
As of April 14, 2026, OpenAI's current Codex docs still describe `notify` and `Stop`/hook-style events as turn-scoped rather than whole-process-exit signals.

If you only want one notification after the whole Codex session exits, do not rely on `notify`. Use the built-in wrapper:

```bash
python -m vibe_notification --wrap-codex
```

You can pass normal Codex arguments through unchanged:

```bash
python -m vibe_notification --wrap-codex -- --help
python -m vibe_notification --wrap-codex -- -C /path/to/project
```

If you want this as your everyday entrypoint, add a shell alias such as:

```bash
alias codexn='python3 -m vibe_notification --wrap-codex --'
```

Then launch `codexn`; VibeNotification will fire only once, after the Codex process actually exits.

To inspect your local integration and spot config/semantic mismatches quickly:

```bash
python -m vibe_notification --doctor
```

Typical placement in `config.toml`:

```toml
model_provider = "xxx"
model = "gpt-5.1-codex-max"
model_reasoning_effort = "medium"
disable_response_storage = true
notify = ["python3", "-m", "vibe_notification"]

[model_providers.xxx]
name = "xxx"
base_url = "https://xxx/v1"
wire_api = "responses"
requires_openai_auth = true

[tui]
notifications = true
```

## Configuration Recipes

### Visual only (no sound)

- Codex `~/.codex/config.toml`:

```toml
notify = ["python3", "-m", "vibe_notification", "--sound", "0"]
```

- Claude Code `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python -m vibe_notification --sound 0"
          }
        ]
      }
    ]
  }
}
```

- Quick test:

```bash
python -m vibe_notification --sound 0 --test
```

### Sound only (no system toast)

- Codex:

```toml
notify = ["python3", "-m", "vibe_notification", "--notification", "0"]
```

- Claude Code:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python -m vibe_notification --notification 0"
          }
        ]
      }
    ]
  }
}
```

- Quick test:

```bash
python -m vibe_notification --notification 0 --test
```

### Temporary toggles (environment variables)

- `VIBE_NOTIFICATION_SOUND=0` — mute sound
- `VIBE_NOTIFICATION_NOTIFY=0` — disable system notification
- `VIBE_NOTIFICATION_LOG_LEVEL=DEBUG` — enable debug logging; raw Codex payloads are also appended to `~/.config/vibe-notification/debug/codex-events.jsonl`
- `VIBE_NOTIFICATION_SENDER_MODE=off|auto|force` — control macOS `terminal-notifier` sender binding; Claude Code hooks and terminal-hosted CLI contexts default to `off`

Codex examples:

```toml
# Temporarily mute sound
notify = ["env", "VIBE_NOTIFICATION_SOUND=0", "python3", "-m", "vibe_notification"]

# Disable all notifications (for debugging)
notify = ["env", "VIBE_NOTIFICATION_NOTIFY=0", "VIBE_NOTIFICATION_SOUND=0", "python3", "-m", "vibe_notification"]

# Enable debug logging
notify = ["env", "VIBE_NOTIFICATION_LOG_LEVEL=DEBUG", "python3", "-m", "vibe_notification"]
```

Claude Code example:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "env VIBE_NOTIFICATION_SOUND=0 VIBE_NOTIFICATION_SENDER_MODE=off python -m vibe_notification"
          }
        ]
      }
    ]
  }
}
```

CLI tests:

```bash
VIBE_NOTIFICATION_SOUND=0 python -m vibe_notification --test
VIBE_NOTIFICATION_SOUND=0 VIBE_NOTIFICATION_NOTIFY=0 python -m vibe_notification --test
VIBE_NOTIFICATION_LOG_LEVEL=DEBUG python -m vibe_notification --test
VIBE_NOTIFICATION_SENDER_MODE=off python -m vibe_notification --test
```

### Sound type

Available macOS sound types: `Glass` (default), `Ping`, `Pop`, `Tink`, `Basso`.

```toml
notify = ["env", "VIBE_NOTIFICATION_SOUND_TYPE=Ping", "python3", "-m", "vibe_notification"]
# Low tone
notify = ["env", "VIBE_NOTIFICATION_SOUND_TYPE=Basso", "python3", "-m", "vibe_notification"]
```

Claude Code:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "env VIBE_NOTIFICATION_SOUND_TYPE=Pop python -m vibe_notification"
          }
        ]
      }
    ]
  }
}
```

Test different sounds:

```bash
VIBE_NOTIFICATION_SOUND_TYPE=Tink python -m vibe_notification --test
VIBE_NOTIFICATION_SOUND_TYPE=Ping python -m vibe_notification --test
```

### Volume control

Volume range is `0.0–1.0`.

```toml
notify = ["env", "VIBE_NOTIFICATION_SOUND_VOLUME=0.2", "python3", "-m", "vibe_notification"]
notify = ["env", "VIBE_NOTIFICATION_SOUND_VOLUME=0.5", "python3", "-m", "vibe_notification"]
notify = ["env", "VIBE_NOTIFICATION_SOUND_VOLUME=0", "python3", "-m", "vibe_notification"] # mute
```

Claude Code:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "env VIBE_NOTIFICATION_SOUND_VOLUME=0.3 python -m vibe_notification"
          }
        ]
      }
    ]
  }
}
```

Quick test:

```bash
VIBE_NOTIFICATION_SOUND_VOLUME=0.1 python -m vibe_notification --test
VIBE_NOTIFICATION_SOUND_VOLUME=0.8 python -m vibe_notification --test
```

### Notification timeout

Edit `~/.config/vibe-notification/config.json`:

```json
{
  "enable_sound": true,
  "enable_notification": true,
  "notification_timeout": 5000,
  "sound_type": "Glass",
  "sound_volume": 0.1,
  "log_level": "INFO"
}
```

- `5000` = 5s auto-dismiss
- `10000` = 10s (default)
- `30000` = 30s
- `0` = sticky, manual close

`notification_timeout` controls display duration on supported platform notifiers.
It is currently applied to Linux `notify-send --expire-time` and the Windows
NotifyIcon fallback. The current macOS notification backends do not expose an
equivalent timeout setting.

When VibeNotification detects a VS Code integrated terminal on Linux and the
`code` CLI is available, it waits for `notify-send --wait` to return. Closing
before the configured timeout is treated as a click and runs `code -r` to focus
the workspace.

On macOS, VS Code click-to-focus is available through `terminal-notifier` when the
`code` CLI is installed and sender binding is not in use. Windows toast click
activation is not supported by the current one-shot PowerShell notifier.

Or use the interactive config:

```bash
python -m vibe_notification --config
```

### Prebuilt combos

Focus mode (low volume + toast only + short display):

```toml
notify = ["env", "VIBE_NOTIFICATION_SOUND_VOLUME=0.1", "VIBE_NOTIFICATION_SOUND_TYPE=Basso", "python3", "-m", "vibe_notification"]
```

Meeting mode (sound only, louder, specific tone):

```toml
notify = ["env", "VIBE_NOTIFICATION_NOTIFY=0", "VIBE_NOTIFICATION_SOUND_VOLUME=0.7", "VIBE_NOTIFICATION_SOUND_TYPE=Ping", "python3", "-m", "vibe_notification"]
```

Debug mode (all on + debug logs):

```toml
notify = ["env", "VIBE_NOTIFICATION_LOG_LEVEL=DEBUG", "python3", "-m", "vibe_notification"]
```

## CLI Reference

### Command-line options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `event_json` | positional | - | Optional Codex event JSON string |
| `--test` | flag | - | Send a test notification |
| `--config` | flag | - | Interactive configuration |
| `--sound {0,1}` | choice | config value | Enable/disable sound (0=off, 1=on) |
| `--notification {0,1}` | choice | config value | Enable/disable system notification (0=off, 1=on) |
| `--log-level {DEBUG,INFO,WARNING,ERROR}` | choice | config value | Set log level |
| `--version` | flag | - | Show version |

### Config file

Location: `~/.config/vibe-notification/config.json`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enable_sound` | bool | `true` | Enable sound |
| `enable_notification` | bool | `true` | Enable system notification |
| `notification_timeout` | int | `10000` | Duration in ms for supported platform notifiers |
| `sound_type` | string | `"default"` | Sound type |
| `sound_volume` | float | `0.1` | Sound volume |
| `log_level` | string | `"INFO"` | Log level |
| `detect_conversation_end` | bool | `true` | Detect end of conversation |
| `macos_sender_mode` | string | `"auto"` | Sender mode for macOS: `auto`, `off`, or `force` |

### Environment variables

| Env | Description | Example |
|-----|-------------|---------|
| `VIBE_NOTIFICATION_SOUND` | Override sound setting | `VIBE_NOTIFICATION_SOUND=0` |
| `VIBE_NOTIFICATION_NOTIFY` | Override notification setting | `VIBE_NOTIFICATION_NOTIFY=0` |
| `VIBE_NOTIFICATION_LOG_LEVEL` | Override log level | `VIBE_NOTIFICATION_LOG_LEVEL=DEBUG` |
| `VIBE_NOTIFICATION_SENDER_MODE` | Override macOS sender binding mode | `VIBE_NOTIFICATION_SENDER_MODE=off` |

### Typical commands

```bash
# Test (toast + sound)
python -m vibe_notification --test

# Toast only
python -m vibe_notification --sound 0 --test

# Sound only
python -m vibe_notification --notification 0 --test

# Debug logs
python -m vibe_notification --log-level DEBUG --test
```

### Hook usage examples

Claude Code:

```bash
echo '{"toolName": "Bash"}' | python -m vibe_notification
VIBE_NOTIFICATION_SOUND=0 echo '{"toolName": "Task"}' | python -m vibe_notification
VIBE_NOTIFICATION_NOTIFY=0 python -m vibe_notification
```

Codex:

```bash
python -m vibe_notification '{"type":"agent-turn-complete","thread-id":"thread-1","turn-id":"turn-1","cwd":"/tmp/project","input-messages":["fix tests"],"last-assistant-message":"Done"}'
python -m vibe_notification '{"type":"agent-turn-complete","thread-id":"thread-1","turn-id":"turn-1","cwd":"/tmp/project","input-messages":["fix tests"],"last-assistant-message":"Done"}' --notification 1 --sound 0
VIBE_NOTIFICATION_SOUND=1 VIBE_NOTIFICATION_NOTIFY=1 python -m vibe_notification '{"type":"agent-turn-complete","thread-id":"thread-1","turn-id":"turn-1","cwd":"/tmp/project","input-messages":["fix tests"],"last-assistant-message":"Done"}'
```

## Publishing to PyPI

1. Bump the version in `pyproject.toml` (single source of truth).
2. Install tooling: `python -m pip install --upgrade build twine`.
3. Build: `python -m build` (creates `.tar.gz` and `.whl` under `dist/`).
4. Validate: `python -m twine check dist/*`.
5. Upload: `TWINE_USERNAME=__token__ TWINE_PASSWORD=<pypi-token> python -m twine upload dist/*` (use `--repository testpypi` to dry run).
6. Install + verify: `pip install -U vibe-notification` then `python -m vibe_notification --test`.
