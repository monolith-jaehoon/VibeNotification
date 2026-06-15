"""
测试平台适配器模块
"""

import sys

import pytest
from unittest.mock import Mock, patch
from vibe_notification.adapters import (
    DefaultCommandExecutor,
    MacOSAdapter,
    LinuxAdapter,
    WindowsAdapter,
    ProcessResult,
    create_platform_adapter,
    UnsupportedPlatformError
)
from vibe_notification.exceptions import CommandExecutionError
from vibe_notification.models import NotificationConfig
from tests.conftest import command_result_success, command_result_failure


class TestProcessResult:
    """测试命令执行结果"""

    def test_success(self):
        """测试成功结果"""
        result = ProcessResult(0, "output", "error")
        assert result.success is True
        assert result.return_code == 0
        assert result.stdout == "output"
        assert result.stderr == "error"

    def test_failure(self):
        """测试失败结果"""
        result = ProcessResult(1, "output", "error")
        assert result.success is False
        assert result.return_code == 1


class TestDefaultCommandExecutor:
    """测试默认命令执行器"""

    def test_execute_success(self):
        """测试成功执行命令"""
        executor = DefaultCommandExecutor()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="success",
                stderr=""
            )

            result = executor.execute(["echo", "test"])

            assert result.success is True
            assert result.stdout == "success"
            mock_run.assert_called_once_with(
                ["echo", "test"],
                shell=False,
                capture_output=True,
                text=True,
                check=False
            )

    def test_execute_failure(self):
        """测试执行命令失败"""
        executor = DefaultCommandExecutor()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=1,
                stdout="",
                stderr="error"
            )

            result = executor.execute(["false"])

            assert result.success is False
            assert result.return_code == 1

    def test_execute_with_timeout_success(self):
        """测试带超时的成功执行"""
        executor = DefaultCommandExecutor()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="success",
                stderr=""
            )

            result = executor.execute_with_timeout(["echo", "test"], 5.0)

            assert result.success is True
            mock_run.assert_called_once_with(
                ["echo", "test"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5.0
            )

    def test_execute_shell(self):
        """测试 shell 执行"""
        executor = DefaultCommandExecutor()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="success",
                stderr=""
            )

            executor.execute("echo test", shell=True)

            mock_run.assert_called_once_with(
                "echo test",
                shell=True,
                capture_output=True,
                text=True,
                check=False
            )


class TestMacOSAdapter:
    """测试 macOS 适配器"""

    def test_play_sound_default(self, mock_executor):
        """测试播放默认声音"""
        adapter = MacOSAdapter(mock_executor)

        adapter.play_sound(sound_type="default")

        # 验证调用参数
        mock_executor.execute_with_timeout.assert_called_once()
        args = mock_executor.execute_with_timeout.call_args[0][0]
        assert "afplay" in args
        assert any("Ping" in arg for arg in args)

    def test_play_sound_success(self, mock_executor):
        """测试播放成功声音"""
        adapter = MacOSAdapter(mock_executor)

        adapter.play_sound(sound_type="success")

        args = mock_executor.execute_with_timeout.call_args[0][0]
        assert any("Glass" in arg for arg in args)

    def test_play_sound_file(self, mock_executor):
        """测试播放声音文件"""
        adapter = MacOSAdapter(mock_executor)
        sound_file = "/path/to/sound.wav"

        with patch('pathlib.Path.exists', return_value=True):
            adapter.play_sound(sound_file=sound_file)

        mock_executor.execute_with_timeout.assert_called_once()
        args, timeout = mock_executor.execute_with_timeout.call_args[0]
        assert args == ["afplay", "--volume", "100", sound_file]
        assert timeout > 0

    def test_play_sound_raises_on_command_failure(self, mock_executor):
        """底层命令失败时应抛出异常，避免误报成功。"""
        mock_executor.execute_with_timeout.return_value = ProcessResult(
            return_code=1,
            stdout="",
            stderr="afplay boom"
        )
        adapter = MacOSAdapter(mock_executor)

        with pytest.raises(CommandExecutionError):
            adapter.play_sound(sound_type="Glass", volume=0.1)

    def test_show_notification(self, mock_executor):
        """测试显示通知"""
        adapter = MacOSAdapter(mock_executor)

        with patch('vibe_notification.adapters.check_command', side_effect=lambda cmd: cmd == "terminal-notifier"), \
             patch.object(adapter, "_detect_sender_bundle_id", return_value="com.microsoft.VSCode"):
            adapter.show_notification("Title", "Message")

        mock_executor.execute_with_timeout.assert_called_once()
        command = mock_executor.execute_with_timeout.call_args[0][0]
        assert command[:7] == [
            "terminal-notifier",
            "-title",
            "Title",
            "-message",
            "Message",
            "-sender",
            "com.microsoft.VSCode",
        ]

    def test_show_notification_skips_sender_in_claude_context_by_default(self, mock_executor, monkeypatch):
        """Claude Code 场景默认不绑定 sender，避免横幅被宿主 App 通知策略吞掉。"""
        adapter = MacOSAdapter(mock_executor)
        monkeypatch.setenv("CLAUDE_HOOK_EVENT", "Stop")

        with patch('vibe_notification.adapters.check_command', side_effect=lambda cmd: cmd == "terminal-notifier"), \
             patch.object(adapter, "_detect_sender_bundle_id", return_value="com.microsoft.VSCode"):
            adapter.show_notification("Title", "Message")

        mock_executor.execute_with_timeout.assert_called_once()
        command = mock_executor.execute_with_timeout.call_args[0][0]
        assert "-sender" not in command

    def test_show_notification_uses_sender_when_explicitly_enabled_for_claude(self, mock_executor, monkeypatch):
        """允许通过环境变量显式恢复 sender。"""
        adapter = MacOSAdapter(mock_executor)
        monkeypatch.setenv("CLAUDE_HOOK_EVENT", "Stop")
        monkeypatch.setenv("VIBE_NOTIFICATION_SENDER_MODE", "auto")

        with patch('vibe_notification.adapters.check_command', side_effect=lambda cmd: cmd == "terminal-notifier"), \
             patch.object(adapter, "_detect_sender_bundle_id", return_value="com.microsoft.VSCode"):
            adapter.show_notification("Title", "Message")

        mock_executor.execute_with_timeout.assert_called_once()
        command = mock_executor.execute_with_timeout.call_args[0][0]
        assert command[:7] == [
            "terminal-notifier",
            "-title",
            "Title",
            "-message",
            "Message",
            "-sender",
            "com.microsoft.VSCode",
        ]

    def test_show_notification_respects_config_sender_mode(self, mock_executor):
        """配置文件中的 macos_sender_mode 也应生效。"""
        adapter = MacOSAdapter(
            mock_executor,
            config=NotificationConfig(macos_sender_mode="off"),
        )

        with patch('vibe_notification.adapters.check_command', side_effect=lambda cmd: cmd == "terminal-notifier"), \
             patch.object(adapter, "_detect_sender_bundle_id", return_value="com.microsoft.VSCode"):
            adapter.show_notification("Title", "Message")

        mock_executor.execute_with_timeout.assert_called_once()
        command = mock_executor.execute_with_timeout.call_args[0][0]
        assert "-sender" not in command

    def test_show_notification_skips_sender_in_terminal_host_context_by_default(self, mock_executor):
        """终端/CLI 宿主场景默认不绑定 sender，避免继承宿主 App 的通知样式。"""
        adapter = MacOSAdapter(mock_executor)

        with patch('vibe_notification.adapters.check_command', side_effect=lambda cmd: cmd == "terminal-notifier"), \
             patch.object(
                 adapter,
                 "_iter_parent_commands",
                 return_value=[
                     "python",
                     "/opt/homebrew/bin/codex",
                     "/Applications/Visual Studio Code.app/Contents/MacOS/Electron",
                 ],
             ), \
             patch.object(adapter, "_detect_sender_bundle_id", return_value="com.microsoft.VSCode"):
            adapter.show_notification("Title", "Message")

        mock_executor.execute_with_timeout.assert_called_once()
        command = mock_executor.execute_with_timeout.call_args[0][0]
        assert "-sender" not in command

    def test_show_notification_skips_sender_in_plain_terminal_shell_context(self, mock_executor):
        """普通 Terminal -> shell -> python 链路也应默认关闭 sender。"""
        adapter = MacOSAdapter(mock_executor)

        with patch('vibe_notification.adapters.check_command', side_effect=lambda cmd: cmd == "terminal-notifier"), \
             patch.object(
                 adapter,
                 "_iter_parent_commands",
                 return_value=[
                     "python",
                     "zsh",
                     "/System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal",
                 ],
             ), \
             patch.object(adapter, "_detect_sender_bundle_id", return_value="com.apple.Terminal"):
            adapter.show_notification("Title", "Message")

        mock_executor.execute_with_timeout.assert_called_once()
        command = mock_executor.execute_with_timeout.call_args[0][0]
        assert "-sender" not in command

    def test_show_notification_with_subtitle(self, mock_executor):
        """测试显示带副标题的通知"""
        adapter = MacOSAdapter(mock_executor)

        with patch('vibe_notification.adapters.check_command', return_value=False):
            adapter.show_notification("Title", 'Message "quoted" \\ path', "Subtitle")

        mock_executor.execute_with_timeout.assert_called_once()
        command = mock_executor.execute_with_timeout.call_args[0][0]
        assert command[0] == "osascript"
        assert '\\"quoted\\"' in command[2]
        assert "\\\\ path" in command[2]
        assert 'subtitle "Subtitle"' in command[2]

    def test_show_notification_adds_vscode_click_action_without_sender(self, mock_executor):
        """VS Code 场景且未绑定 sender 时，点击通知应聚焦当前工作区。"""
        adapter = MacOSAdapter(
            mock_executor,
            config=NotificationConfig(macos_sender_mode="off"),
        )

        with patch('vibe_notification.adapters.check_command', side_effect=lambda cmd: cmd in {"terminal-notifier", "code"}), \
             patch.object(adapter, "_is_vscode_context", return_value=True), \
             patch("vibe_notification.adapters._current_workdir", return_value="/tmp/demo project"):
            adapter.show_notification("Title", "Message")

        mock_executor.execute_with_timeout.assert_called_once()
        command = mock_executor.execute_with_timeout.call_args[0][0]
        assert "-execute" in command
        execute_value = command[command.index("-execute") + 1]
        assert execute_value == "code -r '/tmp/demo project'"

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS .app bundle detection")
    def test_detect_sender_bundle_id_from_parent_process_chain(self, mock_executor):
        adapter = MacOSAdapter(mock_executor)

        parent_ps = [
            ProcessResult(0, "100 90 python3\n"),
            ProcessResult(0, "90 80 /opt/homebrew/bin/codex\n"),
            ProcessResult(0, "80 70 /Applications/Visual Studio Code.app/Contents/MacOS/Electron\n"),
            ProcessResult(0, ""),
        ]
        defaults_result = ProcessResult(0, "com.microsoft.VSCode\n")
        mock_executor.execute.side_effect = [*parent_ps, defaults_result]

        with patch("pathlib.Path.exists", return_value=True):
            sender_bundle_id = adapter._detect_sender_bundle_id()

        assert sender_bundle_id == "com.microsoft.VSCode"

    def test_show_notification_raises_on_command_failure(self, mock_executor):
        """底层命令失败时应抛出异常，避免误报成功。"""
        mock_executor.execute_with_timeout.return_value = ProcessResult(
            return_code=1,
            stdout="",
            stderr="osascript boom"
        )
        adapter = MacOSAdapter(mock_executor)

        with pytest.raises(CommandExecutionError):
            adapter.show_notification("Title", "Message", "Subtitle")

    @patch('vibe_notification.adapters.check_command')
    def test_is_sound_available(self, mock_check_command):
        """测试检查声音功能可用性"""
        mock_check_command.return_value = True
        adapter = MacOSAdapter(Mock())

        assert adapter.is_sound_available() is True
        mock_check_command.assert_called_with("afplay")

    @patch('vibe_notification.adapters.check_command')
    def test_is_notification_available(self, mock_check_command):
        """测试检查通知功能可用性"""
        mock_check_command.side_effect = lambda cmd: cmd == "terminal-notifier"
        adapter = MacOSAdapter(Mock())

        assert adapter.is_notification_available() is True
        assert mock_check_command.call_args_list[0].args == ("terminal-notifier",)


class TestLinuxAdapter:
    """测试 Linux 适配器"""

    @patch('vibe_notification.adapters.check_command')
    def test_play_sound_default(self, mock_check_command, mock_executor):
        """测试播放默认声音"""
        mock_check_command.side_effect = lambda cmd: cmd == "paplay"
        adapter = LinuxAdapter(mock_executor)

        adapter.play_sound()

        # 验证调用了 paplay 或 aplay
        mock_executor.execute.assert_called_once()
        args = mock_executor.execute.call_args[0][0]
        assert args[0] in ["paplay", "aplay"]

    @patch('vibe_notification.adapters.check_command')
    def test_play_sound_file(self, mock_check_command, mock_executor):
        """测试播放声音文件"""
        mock_check_command.side_effect = lambda cmd: cmd == "paplay"
        adapter = LinuxAdapter(mock_executor)
        sound_file = "/path/to/sound.wav"

        with patch('pathlib.Path.exists', return_value=True):
            adapter.play_sound(sound_file=sound_file)

        mock_executor.execute.assert_called()
        args = mock_executor.execute.call_args[0][0]
        assert sound_file in " ".join(args)

    @patch('vibe_notification.adapters.check_command', return_value=False)
    def test_show_notification(self, mock_check_command, mock_executor):
        """测试显示通知"""
        adapter = LinuxAdapter(mock_executor)

        adapter.show_notification("Title", "Message")

        mock_executor.execute.assert_called_once()
        args = mock_executor.execute.call_args[0][0]
        assert "notify-send" in args
        assert "--expire-time" in args
        assert "10000" in args
        assert "Title" in args
        assert "Message" in args

    @patch('vibe_notification.adapters.check_command', return_value=False)
    def test_show_notification_uses_configured_timeout(self, mock_check_command, mock_executor):
        """Linux notify-send 应使用配置的 notification_timeout。"""
        adapter = LinuxAdapter(
            mock_executor,
            config=NotificationConfig(notification_timeout=5000),
        )

        adapter.show_notification("Title", "Message")

        args = mock_executor.execute.call_args[0][0]
        assert args[:3] == ["notify-send", "--expire-time", "5000"]

    def test_show_notification_focuses_vscode_when_wait_returns_before_timeout(self, mock_executor):
        """notify-send 在超时前返回时，视为点击并聚焦 VS Code 工作区。"""
        adapter = LinuxAdapter(
            mock_executor,
            config=NotificationConfig(notification_timeout=5000),
        )

        with patch.object(adapter, "_is_vscode_context", return_value=True), \
             patch("vibe_notification.adapters.check_command", side_effect=lambda cmd: cmd == "code"), \
             patch("vibe_notification.adapters._current_workdir", return_value="/tmp/project"), \
             patch("vibe_notification.adapters.time.monotonic", side_effect=[0.0, 1.0]):
            adapter.show_notification("Title", "Message")

        notify_command, notify_timeout = mock_executor.execute_with_timeout.call_args_list[0][0]
        assert notify_command[:4] == ["notify-send", "--expire-time", "5000", "--wait"]
        assert notify_timeout == 6.0

        focus_command, focus_timeout = mock_executor.execute_with_timeout.call_args_list[1][0]
        assert focus_command == ["code", "-r", "/tmp/project"]
        assert focus_timeout == 3.0

    def test_show_notification_does_not_focus_vscode_when_wait_reaches_timeout(self, mock_executor):
        """notify-send 执行时间达到配置超时时，不视为点击。"""
        adapter = LinuxAdapter(
            mock_executor,
            config=NotificationConfig(notification_timeout=5000),
        )

        with patch.object(adapter, "_is_vscode_context", return_value=True), \
             patch("vibe_notification.adapters.check_command", side_effect=lambda cmd: cmd == "code"), \
             patch("vibe_notification.adapters.time.monotonic", side_effect=[0.0, 5.0]):
            adapter.show_notification("Title", "Message")

        mock_executor.execute_with_timeout.assert_called_once()

    @patch('vibe_notification.adapters.check_command')
    def test_is_sound_available_paplay(self, mock_check_command):
        """测试检查声音功能可用性 - paplay"""
        mock_check_command.side_effect = lambda cmd: cmd == "paplay"
        adapter = LinuxAdapter(Mock())

        assert adapter.is_sound_available() is True

    @patch('vibe_notification.adapters.check_command')
    def test_is_sound_available_aplay(self, mock_check_command):
        """测试检查声音功能可用性 - aplay"""
        mock_check_command.side_effect = lambda cmd: cmd == "aplay"
        adapter = LinuxAdapter(Mock())

        assert adapter.is_sound_available() is True

    @patch('vibe_notification.adapters.check_command')
    def test_is_sound_available_none(self, mock_check_command):
        """测试检查声音功能可用性 - 无"""
        mock_check_command.return_value = False
        adapter = LinuxAdapter(Mock())

        assert adapter.is_sound_available() is False


class TestWindowsAdapter:
    """测试 Windows 适配器"""

    def test_play_sound_default(self, mock_executor):
        """测试播放默认声音"""
        adapter = WindowsAdapter(mock_executor)

        adapter.play_sound()

        mock_executor.execute.assert_called_once()
        command = mock_executor.execute.call_args[0][0]
        assert "powershell.exe" in command

    def test_play_sound_file(self, mock_executor):
        """测试播放声音文件"""
        adapter = WindowsAdapter(mock_executor)
        sound_file = "C:\\path\\to\\sound.wav"

        with patch('pathlib.Path.exists', return_value=True):
            adapter.play_sound(sound_file=sound_file)

        command = mock_executor.execute.call_args[0][0]
        assert sound_file in " ".join(command)

    def test_show_notification(self, mock_executor):
        """测试显示通知"""
        adapter = WindowsAdapter(mock_executor)

        adapter.show_notification("Title", "Message")

        mock_executor.execute.assert_called_once()
        command = mock_executor.execute.call_args[0][0]
        assert "powershell.exe" in command
        assert "Title" in " ".join(command)
        assert "Message" in " ".join(command)

    @patch('vibe_notification.adapters.check_command')
    def test_is_sound_available(self, mock_check_command):
        """测试检查声音功能可用性"""
        mock_check_command.return_value = True
        adapter = WindowsAdapter(Mock())

        assert adapter.is_sound_available() is True
        mock_check_command.assert_called_with("powershell.exe")


@patch('vibe_notification.adapters.get_platform_info')
def test_create_platform_adapter(mock_get_platform_info):
    """测试创建平台适配器"""
    mock_get_platform_info.return_value = {"system": "Darwin"}
    mock_executor = Mock()

    adapter = create_platform_adapter(mock_executor)

    assert isinstance(adapter, MacOSAdapter)
