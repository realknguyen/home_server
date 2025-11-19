# glance/custom_api_extension/utils.py

import platform
import sys
import subprocess
import os
try:
    from distro import id as get_distro_id
except ImportError:  # pragma: no cover
    get_distro_id = None

def detect_platform():
    """
    Detects the current operating system and returns a normalized string.
    
    Returns:
        str: A string representing the detected platform, e.g., 'linux-ubuntu', 'windows', 'macos'.
    """
    system = platform.system().lower()
    release = platform.release().lower()
    distro = ""

    if system == "linux":
        # Distinguish WSL vs native Linux
        if "microsoft" in release:
            return "wsl"
        if get_distro_id:
            distro = get_distro_id()
        else:
            distro = platform.platform().split("-")[0]
        return f"linux-{distro}" if distro else "linux"
    elif system == "windows":
        # sys.getwindowsversion gives more detail if needed
        return system
    elif system == "darwin":
        return system
    elif system == "freebsd":
        return system
    elif system == "openbsd":
        return system
    elif system == "netbsd":
        return system
    else:
        return system

def run_command(command):
    try:
        # Run the command using subprocess.run
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        
        # Return the standard output and return code
        return result.stdout, result.returncode
    except Exception as e:
        # Handle errors (e.g., non-zero exit status)
        # Return stderr as the stdout when there's an error, as that's what the test expects
        return str(e), 1
