# VibeNotification 配置指南

## 交互式配置

运行以下命令进入交互式配置模式：

```bash
python -m vibe_notification --config
```

### 配置流程

1. **选择语言** / Select Language

   ```text
   ==================================================
   请选择语言 / Please select language:
   1. 中文
   2. English
   ==================================================
   ```

2. **查看当前配置**

   ```text
   === VibeNotification 配置 ===
   按 Esc 键退出配置
   按 Enter 跳过此项

   当前配置
     [声音通知]  : 启用
     [系统通知]  : 启用
     [日志级别]  : INFO
     [通知超时]  : 10000 ms
     [声音类型]  : Glass
     [声音大小]  : 0.1

   是否修改配置？ (y/n):
   ```

3. **修改配置**（可选）
   - 按 `Enter` 跳过，保留当前值
   - 按 `Esc` 退出配置

   ```text
   --- 是否修改配置？ ---

   声音通知 (y/n) [启用]:
   系统通知 (y/n) [启用]:

   日志级别 (DEBUG/INFO/WARNING/ERROR) [INFO]: DEBUG

   通知超时 (ms) [10000]: 5000

   声音类型 (Glass/Ping/Pop/Tink/Basso) [Glass]: Ping

   声音大小 (0.0-1.0) [0.1]: 0.5

   配置已保存！
   ```

### 配置项说明

| 配置项 | 说明 | 默认值 | 可选值 |
|--------|------|--------|--------|
| 声音通知 | 是否播放声音提示 | 启用 | 启用/禁用 |
| 系统通知 | 是否显示系统通知 | 启用 | 启用/禁用 |
| 日志级别 | 记录日志的详细程度 | INFO | DEBUG/INFO/WARNING/ERROR |
| 通知超时 | 系统通知显示时间(毫秒) | 10000 | 1000-60000 |
| 声音类型 | 通知提示音类型 | Glass | Glass/Ping/Pop/Tink/Basso |
| 声音大小 | 音量大小(0.0-1.0) | 0.1 | 0.0-1.0 |
| macOS sender 模式 | 是否给 terminal-notifier 绑定宿主 App sender | auto | auto/off/force |

### 快捷键

- `Enter` - 跳过当前配置项，保留默认值
- `Esc` - 退出整个配置过程
- `Y/N` - 在是/否问题中选择

## 命令行参数

也可以通过命令行参数直接设置配置：

```bash
# 启用/禁用声音
python -m vibe_notification --sound 1    # 启用
python -m vibe_notification --sound 0    # 禁用

# 启用/禁用系统通知
python -m vibe_notification --notification 1    # 启用
python -m vibe_notification --notification 0    # 禁用

# 设置日志级别
python -m vibe_notification --log-level DEBUG

# macOS：若 Claude Code 有日志但没有横幅，可显式关闭 sender 绑定
VIBE_NOTIFICATION_SENDER_MODE=off python -m vibe_notification --test

# 测试通知
python -m vibe_notification --test
```

## 配置文件位置

配置会自动保存到用户主目录下的 `.config/vibe-notification` 目录：
- macOS/Linux: `~/.config/vibe-notification/config.json`
- Windows: `%USERPROFILE%\.config\vibe-notification\config.json`
