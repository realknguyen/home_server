"""Utility functions for platform detection and command execution.

This module provides cross-platform utilities for:
- Detecting the operating system and distribution
- Safely executing shell commands with error handling
"""

import platform
import subprocess
from typing import Tuple

try:
    from distro import id as get_distro_id
except ImportError:  # pragma: no cover
    get_distro_id = None


def detect_platform() -> str:
    """Detect the current operating system and return a normalized identifier.
    
    Returns:
        str: Platform identifier such as:
            - 'linux-ubuntu', 'linux-debian', etc. for Linux distributions
            - 'wsl' for Windows Subsystem for Linux
            - 'windows' for Windows
            - 'darwin' for macOS
            - 'freebsd', 'openbsd', 'netbsd' for BSD variants
    
    Examples:
        >>> detect_platform()  # On Ubuntu
        'linux-ubuntu'
        >>> detect_platform()  # On Windows
        'windows'
    """
    system = platform.system().lower()
    release = platform.release().lower()
    
    if system == "linux":
        # Check if running under WSL
        if "microsoft" in release:
            return "wsl"
        
        # Try to get Linux distribution name
        if get_distro_id:
            distro = get_distro_id()
        else:
            # Fallback to platform.platform() parsing
            distro = platform.platform().split("-")[0]
        
        return f"linux-{distro}" if distro else "linux"
    
    # For non-Linux systems, return the system name directly
    return system


def run_command(command: str) -> Tuple[str, int]:
    """Execute a shell command and return its output and exit code.
    
    Args:
        command: Shell command to execute
        
    Returns:
        tuple: (stdout_output, return_code)
            - stdout_output (str): Command output or error message
            - return_code (int): 0 for success, non-zero for errors
    
    Examples:
        >>> run_command('echo "hello"')
        ('hello\\n', 0)
        >>> run_command('exit 1')
        ('...', 1)
    
    Note:
        Uses shell=True for command execution. Be careful with user input.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout, result.returncode
        
    except subprocess.CalledProcessError as e:
        # Command executed but returned non-zero exit code  
        # Return the error string representation (includes command and exit status)
        return str(e), e.returncode
        
    except Exception as e:
        # Other errors (e.g., command not found)
        return str(e), 1
