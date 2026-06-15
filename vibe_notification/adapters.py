"""
平台适配层

提供跨平台的统一接口
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from pathlib import Path
import os
import shlex
import subprocess
import logging
import time
from .exceptions import CommandExecutionError, UnsupportedPlatformError
from .models import NotificationConfig
from .utils import get_platform_info, check_command, escape_for_osascript

MACOS_SOUND_TIMEOUT_SECONDS = 3.0
MACOS_NOTIFICATION_TIMEOUT_SECONDS = 3.0
FOCUS_COMMAND_TIMEOUT_SECONDS = 3.0
NOTIFY_SEND_WAIT_GRACE_SECONDS = 1.0
DEFAULT_NOTIFICATION_TIMEOUT_MS = 10000
VSCODE_ENV_KEYS = (
    "VSCODE_PID",
    "VSCODE_CWD",
    "VSCODE_IPC_HOOK_CLI",
    "VSCODE_GIT_IPC_HANDLE",
)


def _notification_timeout_ms(config: Optional[NotificationConfig]) -> int:
    """返回配置的通知超时时间（毫秒）。"""
    if config is None:
        return DEFAULT_NOTIFICATION_TIMEOUT_MS

    try:
        return int(getattr(config, "notification_timeout", DEFAULT_NOTIFICATION_TIMEOUT_MS))
    except (TypeError, ValueError):
        return DEFAULT_NOTIFICATION_TIMEOUT_MS


def _current_workdir() -> str:
    """返回当前工作目录的绝对路径。"""
    try:
        return str(Path.cwd().resolve())
    except OSError:
        return str(Path.cwd())


def _is_vscode_environment() -> bool:
    """检测 VS Code 集成终端环境变量。"""
    if os.environ.get("TERM_PROGRAM", "").strip().lower() == "vscode":
        return True

    return any(os.environ.get(name) for name in VSCODE_ENV_KEYS)


def _resolve_vscode_cli() -> Optional[str]:
    """解析用于聚焦当前工作区的 VS Code CLI 命令。"""
    for command in ("code", "vscode"):
        if check_command(command):
            return command
    return None


class ProcessResult:
    """命令执行结果"""
    def __init__(self, return_code: int, stdout: str, stderr: str = ""):
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr
        self.success = return_code == 0


class CommandExecutor(ABC):
    """命令执行器抽象基类"""

    @abstractmethod
    def execute(self, command: List[str], shell: bool = False) -> ProcessResult:
        """执行命令并返回结果"""
        pass

    @abstractmethod
    def execute_with_timeout(self, command: List[str], timeout: float) -> ProcessResult:
        """执行命令并设置超时"""
        pass


class DefaultCommandExecutor(CommandExecutor):
    """默认命令执行器实现"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def execute(self, command: List[str], shell: bool = False) -> ProcessResult:
        """执行命令"""
        try:
            self.logger.debug(f"Executing command: {' '.join(command)}")
            result = subprocess.run(
                command,
                shell=shell,
                capture_output=True,
                text=True,
                check=False
            )
            return ProcessResult(
                return_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr
            )
        except Exception as e:
            raise CommandExecutionError(command, -1, str(e))

    def execute_with_timeout(self, command: List[str], timeout: float) -> ProcessResult:
        """执行命令并设置超时"""
        try:
            self.logger.debug(f"Executing command with timeout {timeout}s: {' '.join(command)}")
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout
            )
            return ProcessResult(
                return_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr
            )
        except subprocess.TimeoutExpired as e:
            raise CommandExecutionError(command, -1, f"Timeout after {timeout}s")
        except Exception as e:
            raise CommandExecutionError(command, -1, str(e))


class PlatformAdapter(ABC):
    """平台适配器抽象基类"""

    @abstractmethod
    def play_sound(self, sound_file: Optional[str] = None, sound_type: str = "default", volume: float = 1.0) -> None:
        """播放声音"""
        pass

    @abstractmethod
    def show_notification(self, title: str, message: str, subtitle: str = "") -> None:
        """显示系统通知"""
        pass

    @abstractmethod
    def is_sound_available(self) -> bool:
        """检查声音功能是否可用"""
        pass

    @abstractmethod
    def is_notification_available(self) -> bool:
        """检查通知功能是否可用"""
        pass


class MacOSAdapter(PlatformAdapter):
    """macOS 平台适配器"""

    SENDER_MODES = {"auto", "off", "force"}
    TERMINAL_HOST_HINTS = (
        "visual studio code.app",
        "code helper",
        "cursor.app",
        "windsurf.app",
        "zed.app",
        "terminal.app",
        "iterm",
        "warp.app",
        "wezterm.app",
        "alacritty.app",
        "kitty.app",
        "ghostty.app",
    )
    CLI_PROCESS_NAMES = (
        "codex",
        "claude",
        "python",
        "python3",
        "bash",
        "zsh",
        "fish",
        "sh",
        "node",
        "tmux",
    )

    def _normalize_sender_mode(self, value: Optional[str]) -> str:
        if not isinstance(value, str):
            return "auto"

        normalized = value.strip().lower()
        return normalized if normalized in self.SENDER_MODES else "auto"

    def _is_claude_hook_context(self) -> bool:
        """Claude Code hook 场景优先稳定展示横幅，而不是继承宿主 App 身份。"""
        return any(
            os.environ.get(name)
            for name in ("CLAUDE_HOOK_EVENT", "CLAUDE_HOOK_COMMAND", "CLAUDE_HOOK_TOOL_NAME")
        )

    def _is_terminal_host_context(self) -> bool:
        """检测当前是否运行在终端/CLI 宿主中。"""
        commands = self._iter_parent_commands()
        if not commands:
            return False

        saw_cli_process = False
        saw_terminal_host = False

        for command in commands:
            normalized = command.strip().lower()
            if not normalized:
                continue

            executable = normalized.split()[0]
            executable_name = Path(executable).name.lower()
            if executable_name in self.CLI_PROCESS_NAMES:
                saw_cli_process = True

            if ".app/" in normalized or normalized.endswith(".app"):
                if any(hint in normalized for hint in self.TERMINAL_HOST_HINTS):
                    saw_terminal_host = True

        return saw_cli_process and saw_terminal_host

    def _get_sender_mode(self) -> str:
        env_mode = self._normalize_sender_mode(os.environ.get("VIBE_NOTIFICATION_SENDER_MODE"))
        if os.environ.get("VIBE_NOTIFICATION_SENDER_MODE"):
            return env_mode

        if self.config is not None:
            config_mode = self._normalize_sender_mode(getattr(self.config, "macos_sender_mode", "auto"))
            if config_mode != "auto":
                return config_mode

        if self._is_claude_hook_context():
            return "off"

        if self._is_terminal_host_context():
            return "off"

        return "auto"

    def _iter_parent_commands(self, max_depth: int = 8) -> List[str]:
        """读取当前进程的父进程链命令。"""
        commands: List[str] = []
        current_pid = os.getpid()

        for _ in range(max_depth):
            result = self.executor.execute(["ps", "-o", "pid=,ppid=,comm=", "-p", str(current_pid)])
            if not result.success:
                break

            line = result.stdout.strip()
            if not line:
                break

            try:
                _, ppid_text, command = line.split(None, 2)
            except ValueError:
                break

            commands.append(command.strip())

            try:
                current_pid = int(ppid_text)
            except ValueError:
                break

            if current_pid <= 1:
                break

        return commands

    def _extract_host_app_path(self, command: str) -> Optional[Path]:
        """从进程命令中提取最外层 .app 路径。"""
        if ".app/" not in command and not command.endswith(".app"):
            return None

        prefix, _, _ = command.partition(".app")
        app_path = Path(prefix + ".app")
        return app_path if app_path.exists() else None

    def _read_bundle_identifier(self, app_path: Path) -> Optional[str]:
        """读取 .app 的 bundle identifier。"""
        info_plist = app_path / "Contents" / "Info"
        result = self.executor.execute(["defaults", "read", str(info_plist), "CFBundleIdentifier"])
        if not result.success:
            return None

        bundle_id = result.stdout.strip()
        return bundle_id or None

    def _detect_sender_bundle_id(self) -> Optional[str]:
        """检测最合适的通知 sender。"""
        for command in self._iter_parent_commands():
            app_path = self._extract_host_app_path(command)
            if app_path is None:
                continue

            bundle_id = self._read_bundle_identifier(app_path)
            if bundle_id:
                return bundle_id

        return None

    def _build_terminal_notifier_command(
        self,
        title: str,
        message: str,
        subtitle: str = "",
        sender_bundle_id: Optional[str] = None,
        execute_command: Optional[str] = None,
    ) -> List[str]:
        """构建 terminal-notifier 命令。"""
        command = ["terminal-notifier", "-title", title, "-message", message]
        if subtitle:
            command.extend(["-subtitle", subtitle])
        if sender_bundle_id:
            command.extend(["-sender", sender_bundle_id])
        if execute_command:
            command.extend(["-execute", execute_command])
        return command

    def _build_osascript_command(self, title: str, message: str, subtitle: str = "") -> List[str]:
        """构建 osascript 命令，确保文本被正确转义。"""
        escaped_title = escape_for_osascript(title)
        escaped_message = escape_for_osascript(message)
        applescript = f'display notification "{escaped_message}" with title "{escaped_title}"'

        if subtitle:
            escaped_subtitle = escape_for_osascript(subtitle)
            applescript += f' subtitle "{escaped_subtitle}"'

        return ["osascript", "-e", applescript]

    def _resolve_sender_bundle_id(self) -> Optional[str]:
        """根据配置与上下文决定是否绑定 sender。"""
        mode = self._get_sender_mode()
        if mode == "off":
            self.logger.debug("Skipping macOS sender binding because sender mode is off")
            return None

        env_sender = os.environ.get("VIBE_NOTIFICATION_SENDER_BUNDLE_ID")
        if env_sender:
            sender_bundle_id = env_sender.strip() or None
            if sender_bundle_id:
                self.logger.debug("Using sender bundle id from environment override: %s", sender_bundle_id)
            return sender_bundle_id

        sender_bundle_id = self._detect_sender_bundle_id()
        if sender_bundle_id:
            self.logger.debug(
                "Resolved sender bundle id %s with sender mode %s",
                sender_bundle_id,
                mode,
            )
        else:
            self.logger.debug("No sender bundle id resolved with sender mode %s", mode)
        return sender_bundle_id

    def _is_vscode_context(self) -> bool:
        """检测当前通知是否来自 VS Code 宿主上下文。"""
        if _is_vscode_environment():
            return True

        for command in self._iter_parent_commands():
            normalized = command.strip().lower()
            if "visual studio code.app" in normalized or "code helper" in normalized:
                return True

        return False

    def _build_vscode_focus_shell_command(self) -> Optional[str]:
        """构建点击通知后聚焦当前 VS Code 工作区的 shell 命令。"""
        vscode_cli = _resolve_vscode_cli()
        if not vscode_cli:
            return None

        return f"{shlex.quote(vscode_cli)} -r {shlex.quote(_current_workdir())}"

    def __init__(self, executor: CommandExecutor, config: Optional[NotificationConfig] = None):
        self.executor = executor
        self.config = config
        self.logger = logging.getLogger(__name__)

    def play_sound(self, sound_file: Optional[str] = None, sound_type: str = "default", volume: float = 1.0) -> None:
        """使用 afplay 播放声音"""
        # 确保 volume 在 0.0-1.0 范围内
        volume = max(0.0, min(1.0, volume))

        if sound_file and Path(sound_file).exists():
            command = ["afplay", "--volume", str(int(volume * 100)), sound_file]
        else:
            # 使用内置系统声音
            sound_map = {
                "default": "Ping",
                "success": "Glass",
                "error": "Basso",
                "warning": "Tink",
                "ping": "Ping",
                "pop": "Pop",
                "Glass": "Glass"
            }
            sound_name = sound_map.get(sound_type, "Ping")
            command = ["afplay", "--volume", str(int(volume * 100)), "/System/Library/Sounds/" + sound_name + ".aiff"]

        result = self.executor.execute_with_timeout(command, MACOS_SOUND_TIMEOUT_SECONDS)
        if not result.success:
            raise CommandExecutionError(command, result.return_code, result.stderr)

    def show_notification(self, title: str, message: str, subtitle: str = "") -> None:
        """优先使用 terminal-notifier，回退到 osascript 显示通知。"""
        if check_command("terminal-notifier"):
            sender_bundle_id = self._resolve_sender_bundle_id()
            execute_command = None
            if sender_bundle_id is None and self._is_vscode_context():
                execute_command = self._build_vscode_focus_shell_command()
            command = self._build_terminal_notifier_command(
                title,
                message,
                subtitle,
                sender_bundle_id=sender_bundle_id,
                execute_command=execute_command,
            )
            if sender_bundle_id:
                self.logger.debug(
                    "Using terminal-notifier for macOS notification with sender %s",
                    sender_bundle_id,
                )
            elif execute_command:
                self.logger.debug(
                    "Using terminal-notifier for macOS notification with VS Code click action"
                )
            else:
                self.logger.debug("Using terminal-notifier for macOS notification without sender")
        else:
            command = self._build_osascript_command(title, message, subtitle)
            self.logger.debug("Using osascript fallback for macOS notification")

        result = self.executor.execute_with_timeout(command, MACOS_NOTIFICATION_TIMEOUT_SECONDS)
        if not result.success:
            if command[0] == "terminal-notifier" and check_command("osascript"):
                self.logger.warning(
                    "terminal-notifier failed (%s), falling back to osascript",
                    result.stderr or result.return_code,
                )
                fallback_command = self._build_osascript_command(title, message, subtitle)
                fallback_result = self.executor.execute_with_timeout(
                    fallback_command,
                    MACOS_NOTIFICATION_TIMEOUT_SECONDS,
                )
                if fallback_result.success:
                    return
                raise CommandExecutionError(
                    fallback_command,
                    fallback_result.return_code,
                    fallback_result.stderr,
                )

            raise CommandExecutionError(command, result.return_code, result.stderr)

    def is_sound_available(self) -> bool:
        """检查 afplay 是否可用"""
        return check_command("afplay")

    def is_notification_available(self) -> bool:
        """检查通知功能是否可用"""
        return check_command("terminal-notifier") or check_command("osascript")


class LinuxAdapter(PlatformAdapter):
    """Linux 平台适配器"""

    def __init__(self, executor: CommandExecutor, config: Optional[NotificationConfig] = None):
        self.executor = executor
        self.config = config
        self.logger = logging.getLogger(__name__)

    def play_sound(self, sound_file: Optional[str] = None, sound_type: str = "default", volume: float = 1.0) -> None:
        """使用 aplay 或 paplay 播放声音"""
        # 确保 volume 在 0.0-1.0 范围内
        volume = max(0.0, min(1.0, volume))

        if sound_file and Path(sound_file).exists():
            # 优先使用 paplay（PulseAudio），否则使用 aplay（ALSA）
            if check_command("paplay"):
                command = ["paplay", "--volume", str(int(volume * 65536)), sound_file]
            elif check_command("aplay"):
                # aplay 不支持音量控制，需要通过 amixer
                if volume < 1.0:
                    # 设置系统音量（临时）
                    self._set_system_volume(volume)
                command = ["aplay", sound_file]
            else:
                self.logger.warning("No sound player available (paplay or aplay)")
                return
        else:
            # 使用系统默认声音
            if check_command("paplay"):
                command = ["paplay", "--volume", str(int(volume * 65536)), "/usr/share/sounds/alsa/Front_Left.wav"]
            elif check_command("aplay"):
                if volume < 1.0:
                    self._set_system_volume(volume)
                command = ["aplay", "/usr/share/sounds/alsa/Front_Left.wav"]
            else:
                self.logger.warning("No sound player available")
                return

        result = self.executor.execute(command)
        if not result.success:
            raise CommandExecutionError(command, result.return_code, result.stderr)

    def _set_system_volume(self, volume: float) -> None:
        """设置系统音量（仅对 aplay 有效）"""
        try:
            # 获取当前音量
            get_vol_cmd = ["amixer", "get", "Master"]
            current_result = self.executor.execute(get_vol_cmd)

            if current_result.success:
                # 计算新音量值（百分比）
                volume_percent = int(volume * 100)
                set_vol_cmd = ["amixer", "set", "Master", f"{volume_percent}%"]
                self.executor.execute(set_vol_cmd)
        except Exception as e:
            self.logger.warning(f"Failed to set system volume: {e}")

    def show_notification(self, title: str, message: str, subtitle: str = "") -> None:
        """使用 notify-send 显示通知"""
        timeout_ms = _notification_timeout_ms(self.config)
        vscode_cli = _resolve_vscode_cli()
        should_wait_for_click = timeout_ms > 0 and vscode_cli is not None and self._is_vscode_context()
        command = ["notify-send"]
        if timeout_ms >= 0:
            command.extend(["--expire-time", str(timeout_ms)])
        if should_wait_for_click:
            command.append("--wait")
        if subtitle:
            command.extend(["-h", f"string:x-canonical-private-synchronous: {subtitle}"])
        command.extend([title, message])

        started_at = time.monotonic()
        try:
            if should_wait_for_click:
                wait_timeout = (timeout_ms / 1000.0) + NOTIFY_SEND_WAIT_GRACE_SECONDS
                result = self.executor.execute_with_timeout(command, wait_timeout)
            else:
                result = self.executor.execute(command)
        except CommandExecutionError:
            if should_wait_for_click and self._elapsed_ms(started_at) >= timeout_ms:
                self.logger.debug("notify-send wait reached configured timeout; treating as no click")
                return
            raise

        if not result.success:
            raise CommandExecutionError(command, result.return_code, result.stderr)

        if should_wait_for_click and self._elapsed_ms(started_at) < timeout_ms:
            self._focus_vscode_workspace(vscode_cli)

    def _is_vscode_context(self) -> bool:
        """检测当前通知是否来自 VS Code 集成终端。"""
        return _is_vscode_environment()

    def _focus_vscode_workspace(self, vscode_cli: str) -> None:
        """点击通知后聚焦当前 VS Code 工作区。"""
        command = [vscode_cli, "-r", _current_workdir()]
        result = self.executor.execute_with_timeout(command, FOCUS_COMMAND_TIMEOUT_SECONDS)
        if not result.success:
            raise CommandExecutionError(command, result.return_code, result.stderr)

    def _elapsed_ms(self, started_at: float) -> float:
        return (time.monotonic() - started_at) * 1000.0

    def is_sound_available(self) -> bool:
        """检查声音播放器是否可用"""
        return check_command("paplay") or check_command("aplay")

    def is_notification_available(self) -> bool:
        """检查 notify-send 是否可用"""
        return check_command("notify-send")


class WindowsAdapter(PlatformAdapter):
    """Windows 平台适配器"""

    def __init__(self, executor: CommandExecutor, config: Optional[NotificationConfig] = None):
        self.executor = executor
        self.config = config
        self.logger = logging.getLogger(__name__)

    def play_sound(self, sound_file: Optional[str] = None, sound_type: str = "default", volume: float = 1.0) -> None:
        """使用 PowerShell 播放声音"""
        # 确保 volume 在 0.0-1.0 范围内
        volume = max(0.0, min(1.0, volume))

        if sound_file and Path(sound_file).exists():
            # 对于自定义音频文件，设置音量并播放
            ps_command = f'''
            $player = New-Object Media.SoundPlayer "{sound_file}";
            $player.PlaySync();
            '''
        else:
            # 使用系统默认声音
            sound_map = {
                "default": "Asterisk",
                "success": "Asterisk",
                "error": "Exclamation",
                "warning": "Exclamation",
                "Glass": "Asterisk"
            }
            sound_name = sound_map.get(sound_type, "Asterisk")
            ps_command = f'[system.media.systemsounds]::{sound_name}.Play();'

        # 添加音量控制（通过设置系统音量）
        if volume < 1.0:
            volume_cmd = f'''
            [audio]::Volume = {volume};
            '''
            ps_command = volume_cmd + ps_command

        command = ["powershell.exe", "-Command", ps_command]
        result = self.executor.execute(command)
        if not result.success:
            raise CommandExecutionError(command, result.return_code, result.stderr)

    def show_notification(self, title: str, message: str, subtitle: str = "") -> None:
        """使用 Windows Toast 通知"""
        full_title = f"{title} - {subtitle}" if subtitle else title

        # 先尝试使用Toast通知（Windows 10/11）
        ps_command_toast = f'''
        try {{
            Add-Type -AssemblyName System.Runtime.WindowsRuntime
            $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where {{ $_.Name -eq 'AsTask' }} | Where {{$_.GetParameters().Count -eq 1}})[0]
            Function Await($WinRtTask, $ResultSig) {{
                $asTask = $asTaskGeneric.MakeGenericMethod($ResultSig)
                $netTask = $asTask.Invoke($null, @($WinRtTask))
                $netTask.Wait(-1) | Out-Null
            }}
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            [Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null
            $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
            $xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>{full_title}</text><text>{message}</text></binding></visual></toast>")
            $toast = New-Object Windows.UI.Notifications.ToastNotification($xml)
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("VibeNotification").Show($toast)
        }} catch {{
            exit 1
        }}
        '''

        # 尝试执行Toast通知
        self.logger.debug(f"Attempting to send Toast notification: {full_title}")
        command = ["powershell.exe", "-Command", ps_command_toast]
        result = self.executor.execute(command)

        if result.stdout:
            self.logger.debug(f"Toast stdout: {result.stdout.strip()}")
        if result.stderr:
            self.logger.debug(f"Toast stderr: {result.stderr.strip()}")

        # 如果Toast失败，回退到NotifyIcon
        if not result.success:
            self.logger.warning("Toast notification failed, falling back to NotifyIcon")
            ps_command = f'''
            Add-Type -AssemblyName System.Windows.Forms;
            Add-Type -AssemblyName System.Drawing;
            $notification = New-Object System.Windows.Forms.NotifyIcon;
            $notification.Icon = [System.Drawing.SystemIcons]::Information;
            $notification.BalloonTipTitle = "{full_title}";
            $notification.BalloonTipText = "{message}";
            $notification.Visible = $true;
            $notification.ShowBalloonTip({_notification_timeout_ms(self.config)});
            Write-Host "NotifyIcon notification sent"
            Start-Sleep 2;
            $notification.Dispose();
            '''

            command = ["powershell.exe", "-Command", ps_command]
            result = self.executor.execute(command)
            if result.success:
                self.logger.info("NotifyIcon fallback succeeded")
            else:
                raise CommandExecutionError(command, result.return_code, result.stderr)
        else:
            self.logger.info("Toast notification sent successfully")

    def is_sound_available(self) -> bool:
        """检查 PowerShell 是否可用"""
        return check_command("powershell.exe")

    def is_notification_available(self) -> bool:
        """检查 PowerShell 是否可用"""
        return check_command("powershell.exe")


def create_platform_adapter(
    executor: CommandExecutor,
    config: Optional[NotificationConfig] = None,
) -> PlatformAdapter:
    """创建平台适配器"""
    platform_info = get_platform_info()

    # 检查是否在WSL环境中
    is_wsl = False
    if platform_info["system"] == "Linux":
        try:
            with open("/proc/version", "r") as f:
                version_info = f.read().lower()
                if "microsoft" in version_info or "wsl" in version_info:
                    is_wsl = True
        except:
            pass

    if platform_info["system"] == "Darwin":
        return MacOSAdapter(executor, config=config)
    elif is_wsl or platform_info["system"] == "Windows":
        # WSL环境使用Windows适配器
        return WindowsAdapter(executor, config=config)
    elif platform_info["system"] == "Linux":
        return LinuxAdapter(executor, config=config)
    else:
        raise UnsupportedPlatformError(platform_info["system"])
