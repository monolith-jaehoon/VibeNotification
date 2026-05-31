<div align="center">

# VibeNotification

[![PyPI](https://img.shields.io/pypi/v/vibe-notification.svg)](https://pypi.org/project/vibe-notification/)
[![Python](https://img.shields.io/pypi/pyversions/vibe-notification.svg)](https://pypi.org/project/vibe-notification/)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)](#%E5%AE%89%E8%A3%85)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

[English](README.md) | 中文

<strong>在 Claude Code 或 Codex 回复结束时自动弹窗+提示音的轻量工具，让你不用守着终端等结果。</strong>

[博客教程：AI应用系列 一个简单的 Vibe coding 的通知系统](https://blognas.hwb0307.com/ai/6659)

</div>

![image-20251221214216954](https://chevereto.hwb0307.com/images/2025/12/21/image-20251221214216954.png)

## 安装

- 稳定版（PyPI）：`pip install vibe-notification`
- 开发版：`pip install -e .`
- 可选虚拟环境：`python -m venv venv && source venv/bin/activate`
- 验证：`python -m vibe_notification --test`（如已启用会弹窗+响铃）
- 交互式配置：`python -m vibe_notification --config`
  - 默认配置文件：`~/.config/vibe-notification/config.json`
  - 请确保声音通知和系统通知均为开启状态

## 快速开始

### Claude Code

- 推荐钩子：`Stop`（每次主回复完成）。
- 如果你要的是“某个回复结束就通知”，直接用 `Stop`，这也是默认且唯一推荐的钩子。
- 不建议把通知命令挂到 `SessionEnd` 或 `SubagentStop`：VibeNotification 默认会忽略它们，避免会话退出、子代理完成或工具链事件造成重复提示。
- 在 macOS 下，VibeNotification 现在会在 Claude Code hook 场景和终端宿主 CLI 场景默认关闭 `sender` 绑定，以提高横幅弹窗稳定性；如需沿用宿主 App 图标/归属，可设置 `VIBE_NOTIFICATION_SENDER_MODE=auto`。
- 如果通知只进入通知中心，请到 `系统设置 > 通知` 检查当前生效的应用（`sender=off` 时通常是 `terminal-notifier`，`auto/force` 时通常是 VS Code / Terminal 等宿主 App），确认“允许通知”已打开、样式为横幅/提醒，且没有被专注模式压制。
- 在 `~/.claude/settings.json` 添加 Stop 钩子：

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

- 示例完整配置片段：

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

在 `~/.codex/config.toml` 中添加通知命令，让 Codex 在代理真实完成一轮回复时（`agent-turn-complete`）调用 VibeNotification：

```toml
notify = ["python3", "-m", "vibe_notification"]
```

注意：这里的 `notify` 是“每轮回复结束”触发，不是“整个 Codex 会话退出”触发。
按 2026 年 4 月 14 日 OpenAI 当前文档，Codex 的 `notify` 以及 `Stop`/hook 类事件仍然是 turn 语义，不是整个进程退出语义。

如果你只希望在整个 Codex 会话退出后再通知，不要依赖 `notify`，改用内置 wrapper：

```bash
python -m vibe_notification --wrap-codex
```

如果你平时会带参数启动 Codex，也可以原样透传：

```bash
python -m vibe_notification --wrap-codex -- --help
python -m vibe_notification --wrap-codex -- -C /path/to/project
```

想把它当成日常入口的话，可以在 shell 里加一个别名，例如：

```bash
alias codexn='python3 -m vibe_notification --wrap-codex --'
```

之后直接用 `codexn` 启动；这样只有当 Codex 进程真正退出时，VibeNotification 才会发送一次通知。

想快速检查本机接入状态，也可以运行：

```bash
python -m vibe_notification --doctor
```

典型配置位置：

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

## 配置示例

### 只弹窗不响铃

- Codex `~/.codex/config.toml`：

```toml
notify = ["python3", "-m", "vibe_notification", "--sound", "0"]
```

- Claude Code `~/.claude/settings.json`：

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

- 测试：

```bash
python -m vibe_notification --sound 0 --test
```

### 只响铃不弹窗

- Codex：

```toml
notify = ["python3", "-m", "vibe_notification", "--notification", "0"]
```

- Claude Code：

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

- 测试：

```bash
python -m vibe_notification --notification 0 --test
```

### 临时控制（环境变量）

- `VIBE_NOTIFICATION_SOUND=0`：临时禁用声音
- `VIBE_NOTIFICATION_NOTIFY=0`：临时禁用弹窗
- `VIBE_NOTIFICATION_LOG_LEVEL=DEBUG`：启用调试日志；Codex 原始 payload 会额外写入 `~/.config/vibe-notification/debug/codex-events.jsonl`
- `VIBE_NOTIFICATION_SENDER_MODE=off|auto|force`：控制 macOS `terminal-notifier` 是否绑定 sender；Claude Code hook 和终端宿主 CLI 默认使用 `off`

Codex 示例：

```toml
# 静音
notify = ["env", "VIBE_NOTIFICATION_SOUND=0", "python3", "-m", "vibe_notification"]

# 完全禁用通知
notify = ["env", "VIBE_NOTIFICATION_NOTIFY=0", "VIBE_NOTIFICATION_SOUND=0", "python3", "-m", "vibe_notification"]

# 调试日志
notify = ["env", "VIBE_NOTIFICATION_LOG_LEVEL=DEBUG", "python3", "-m", "vibe_notification"]
```

Claude Code 示例：

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

测试命令：

```bash
VIBE_NOTIFICATION_SOUND=0 python -m vibe_notification --test
VIBE_NOTIFICATION_SOUND=0 VIBE_NOTIFICATION_NOTIFY=0 python -m vibe_notification --test
VIBE_NOTIFICATION_LOG_LEVEL=DEBUG python -m vibe_notification --test
VIBE_NOTIFICATION_SENDER_MODE=off python -m vibe_notification --test
```

### 声音类型

可选（macOS 内置）：`Glass`（默认）、`Ping`、`Pop`、`Tink`、`Basso`。

```toml
notify = ["env", "VIBE_NOTIFICATION_SOUND_TYPE=Ping", "python3", "-m", "vibe_notification"]
# 低音
notify = ["env", "VIBE_NOTIFICATION_SOUND_TYPE=Basso", "python3", "-m", "vibe_notification"]
```

Claude Code：

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

声音测试：

```bash
VIBE_NOTIFICATION_SOUND_TYPE=Tink python -m vibe_notification --test
VIBE_NOTIFICATION_SOUND_TYPE=Ping python -m vibe_notification --test
```

### 音量控制

范围 `0.0–1.0`：

```toml
notify = ["env", "VIBE_NOTIFICATION_SOUND_VOLUME=0.2", "python3", "-m", "vibe_notification"]
notify = ["env", "VIBE_NOTIFICATION_SOUND_VOLUME=0.5", "python3", "-m", "vibe_notification"]
notify = ["env", "VIBE_NOTIFICATION_SOUND_VOLUME=0", "python3", "-m", "vibe_notification"] # 静音
```

Claude Code：

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

快速测试：

```bash
VIBE_NOTIFICATION_SOUND_VOLUME=0.1 python -m vibe_notification --test
VIBE_NOTIFICATION_SOUND_VOLUME=0.8 python -m vibe_notification --test
```

### 通知时长

编辑 `~/.config/vibe-notification/config.json`：

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

- `5000`：5 秒自动消失
- `10000`：10 秒（默认）
- `30000`：30 秒
- `0`：不自动消失

或使用交互式配置：

```bash
python -m vibe_notification --config
```

### 组合模式

专注模式（低音量 + 仅弹窗 + 短时显示）：

```toml
notify = ["env", "VIBE_NOTIFICATION_SOUND_VOLUME=0.1", "VIBE_NOTIFICATION_SOUND_TYPE=Basso", "python3", "-m", "vibe_notification"]
```

会议模式（只响铃 + 较高音量 + 特定音色）：

```toml
notify = ["env", "VIBE_NOTIFICATION_NOTIFY=0", "VIBE_NOTIFICATION_SOUND_VOLUME=0.7", "VIBE_NOTIFICATION_SOUND_TYPE=Ping", "python3", "-m", "vibe_notification"]
```

调试模式（全启用 + 调试日志）：

```toml
notify = ["env", "VIBE_NOTIFICATION_LOG_LEVEL=DEBUG", "python3", "-m", "vibe_notification"]
```

## CLI 参考

### 命令行参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `event_json` | 位置参数 | - | 可选的 Codex 事件 JSON |
| `--test` | 标志 | - | 发送测试通知 |
| `--config` | 标志 | - | 交互式配置 |
| `--sound {0,1}` | 选项 | 配置值 | 0 关闭/1 开启声音 |
| `--notification {0,1}` | 选项 | 配置值 | 0 关闭/1 开启弹窗 |
| `--log-level {DEBUG,INFO,WARNING,ERROR}` | 选项 | 配置值 | 设置日志级别 |
| `--version` | 标志 | - | 显示版本 |

### 配置文件

位置：`~/.config/vibe-notification/config.json`

| 键 | 类型 | 默认值 | 说明 |
|----|------|--------|------|
| `enable_sound` | 布尔 | `true` | 启用声音 |
| `enable_notification` | 布尔 | `true` | 启用系统通知 |
| `notification_timeout` | 整数 | `10000` | 显示时长（毫秒） |
| `sound_type` | 字符串 | `"default"` | 声音类型 |
| `sound_volume` | 浮点 | `0.1` | 音量大小 |
| `log_level` | 字符串 | `"INFO"` | 日志级别 |
| `detect_conversation_end` | 布尔 | `true` | 检测会话结束 |
| `macos_sender_mode` | 字符串 | `"auto"` | macOS sender 模式：`auto`、`off`、`force` |

### 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `VIBE_NOTIFICATION_SOUND` | 覆盖声音设置 | `VIBE_NOTIFICATION_SOUND=0` |
| `VIBE_NOTIFICATION_NOTIFY` | 覆盖弹窗设置 | `VIBE_NOTIFICATION_NOTIFY=0` |
| `VIBE_NOTIFICATION_LOG_LEVEL` | 覆盖日志级别 | `VIBE_NOTIFICATION_LOG_LEVEL=DEBUG` |
| `VIBE_NOTIFICATION_SENDER_MODE` | 覆盖 macOS sender 模式 | `VIBE_NOTIFICATION_SENDER_MODE=off` |

### 常用命令

```bash
# 测试（弹窗+声音）
python -m vibe_notification --test

# 仅弹窗
python -m vibe_notification --sound 0 --test

# 仅声音
python -m vibe_notification --notification 0 --test

# 调试日志
python -m vibe_notification --log-level DEBUG --test
```

### 钩子示例

Claude Code：

```bash
echo '{"toolName": "Bash"}' | python -m vibe_notification
VIBE_NOTIFICATION_SOUND=0 echo '{"toolName": "Task"}' | python -m vibe_notification
VIBE_NOTIFICATION_NOTIFY=0 python -m vibe_notification
```

Codex：

```bash
python -m vibe_notification '{"type":"agent-turn-complete","thread-id":"thread-1","turn-id":"turn-1","cwd":"/tmp/project","input-messages":["fix tests"],"last-assistant-message":"Done"}'
python -m vibe_notification '{"type":"agent-turn-complete","thread-id":"thread-1","turn-id":"turn-1","cwd":"/tmp/project","input-messages":["fix tests"],"last-assistant-message":"Done"}' --notification 1 --sound 0
VIBE_NOTIFICATION_SOUND=1 VIBE_NOTIFICATION_NOTIFY=1 python -m vibe_notification '{"type":"agent-turn-complete","thread-id":"thread-1","turn-id":"turn-1","cwd":"/tmp/project","input-messages":["fix tests"],"last-assistant-message":"Done"}'
```

## 发布到 PyPI

1. 更新版本号：仅修改 `pyproject.toml`（唯一来源）。
2. 安装工具：`python -m pip install --upgrade build twine`。
3. 构建：`python -m build`（生成 `dist/` 下 `.tar.gz` 与 `.whl`）。
4. 校验：`python -m twine check dist/*`。
5. 上传：`TWINE_USERNAME=__token__ TWINE_PASSWORD=<pypi-token> python -m twine upload dist/*`（先验证可用 `--repository testpypi`）。
6. 安装验证：`pip install -U vibe-notification` 后运行 `python -m vibe_notification --test`。
