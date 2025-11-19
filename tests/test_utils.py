"""
Tests for the custom API extension utility functions.
"""
from unittest.mock import patch, MagicMock
import subprocess

from glance.custom_api_extension.flask_utils import detect_platform, run_command


def test_detect_platform_linux_native():
    """Test platform detection for native Linux systems."""
    with patch('platform.system') as mock_system, \
         patch('platform.release') as mock_release, \
         patch('glance.custom_api_extension.flask_utils.get_distro_id', return_value='ubuntu'):
        mock_system.return_value = 'Linux'
        mock_release.return_value = '5.4.0-123-generic'
        
        result = detect_platform()
        assert result == 'linux-ubuntu'


def test_detect_platform_wsl():
    """Test platform detection for WSL systems."""
    with patch('platform.system') as mock_system, \
         patch('platform.release') as mock_release:
        mock_system.return_value = 'Linux'
        mock_release.return_value = 'Microsoft-WSL'
        
        result = detect_platform()
        assert result == 'wsl'


def test_detect_platform_windows():
    """Test platform detection for Windows systems."""
    with patch('platform.system') as mock_system:
        mock_system.return_value = 'Windows'
        
        result = detect_platform()
        assert result == 'windows'


def test_detect_platform_macos():
    """Test platform detection for macOS systems."""
    with patch('platform.system') as mock_system:
        mock_system.return_value = 'Darwin'
        
        result = detect_platform()
        assert result == 'darwin'


def test_detect_platform_freebsd():
    """Test platform detection for FreeBSD systems."""
    with patch('platform.system') as mock_system:
        mock_system.return_value = 'FreeBSD'
        
        result = detect_platform()
        assert result == 'freebsd'


def test_detect_platform_openbsd():
    """Test platform detection for OpenBSD systems."""
    with patch('platform.system') as mock_system:
        mock_system.return_value = 'OpenBSD'
        
        result = detect_platform()
        assert result == 'openbsd'


def test_detect_platform_netbsd():
    """Test platform detection for NetBSD systems."""
    with patch('platform.system') as mock_system:
        mock_system.return_value = 'NetBSD'
        
        result = detect_platform()
        assert result == 'netbsd'


def test_detect_platform_unsupported():
    """Test platform detection for unsupported systems."""
    with patch('platform.system') as mock_system:
        mock_system.return_value = 'UnsupportedOS'
        
        result = detect_platform()
        assert result == 'unsupportedos'


def test_run_command_success():
    """Test successful command execution."""
    with patch('subprocess.run') as mock_run:
        mock_result = MagicMock(returncode=0, stdout="Command output", stderr="")
        mock_run.return_value = mock_result

        stdout, returncode = run_command("echo test")
        mock_run.assert_called_once_with("echo test", shell=True, check=True, capture_output=True, text=True)
        assert stdout == "Command output"
        assert returncode == 0


def test_run_command_failure_returns_error_text():
    """Test failed command execution via CalledProcessError."""
    error = subprocess.CalledProcessError(1, 'invalid_command', output='Error occurred', stderr='boom')
    with patch('subprocess.run', side_effect=error) as mock_run:
        stdout, returncode = run_command("invalid_command")

    mock_run.assert_called_once()
    assert returncode == 1
    # str(error) is exposed back to the caller
    assert "returned non-zero exit status" in stdout


def test_run_command_exception_bubbles_message():
    """Test command execution with unexpected exception."""
    with patch('subprocess.run', side_effect=RuntimeError("Process error")) as mock_run:
        stdout, returncode = run_command("some_command")

    mock_run.assert_called_once()
    assert returncode == 1
    assert stdout == "Process error"
