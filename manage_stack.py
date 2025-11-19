#!/usr/bin/env python3
"""Utility script to (re)start the Docker stack and Flask API."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import tomllib

PROJECT_ROOT = Path(__file__).resolve().parent
COMPOSE_CMD = ["docker", "compose"]
FLASK_ENTRYPOINT = PROJECT_ROOT / "glance" / "custom_api_extension" / "host_flask.py"
DOTENV_PATH = PROJECT_ROOT / ".env"


def load_project_metadata() -> Dict[str, Any]:
    project_file = PROJECT_ROOT / "project.toml"
    if not project_file.exists():
        return {}
    return tomllib.loads(project_file.read_text())


PROJECT_METADATA = load_project_metadata()
MANAGE_STACK_SETTINGS = (
    (PROJECT_METADATA.get("tool") or {}).get("manage_stack") or {}
)
BASE_COMPOSE_FILE = PROJECT_ROOT / MANAGE_STACK_SETTINGS.get(
    "base_compose_file", "docker-compose.yml"
)
GPU_COMPOSE_FILE = PROJECT_ROOT / MANAGE_STACK_SETTINGS.get(
    "gpu_compose_file", "docker-compose.gpu.yml"
)
OPTIONAL_DEP_GROUPS: List[str] = MANAGE_STACK_SETTINGS.get(
    "optional_dependency_groups", ["dev"]
)
AUTO_INSTALL_DEPENDENCIES: bool = MANAGE_STACK_SETTINGS.get(
    "auto_install_dependencies", True
)
USE_VIRTUALENV: bool = MANAGE_STACK_SETTINGS.get("use_virtualenv", True)


def resolve_virtualenv_path() -> Path:
    configured_path = MANAGE_STACK_SETTINGS.get("virtualenv_path", ".venv")
    path_obj = Path(configured_path).expanduser()
    if not path_obj.is_absolute():
        path_obj = PROJECT_ROOT / path_obj
    return path_obj


VIRTUALENV_PATH = resolve_virtualenv_path()


def run_with_output(command: list[str], description: str) -> None:
    """Execute a command while streaming its stdout/stderr."""
    print(f"\n==> {description}")
    result = subprocess.run(command, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command {' '.join(command)} failed with exit code {result.returncode}"
        )


def _virtualenv_python_candidates() -> list[Path]:
    """Return ordered list of python executables inside the venv."""
    if os.name == "nt":
        return [VIRTUALENV_PATH / "Scripts" / "python.exe"]
    bin_dir = VIRTUALENV_PATH / "bin"
    return [bin_dir / "python3", bin_dir / "python"]


def locate_virtualenv_python() -> Path:
    for candidate in _virtualenv_python_candidates():
        if candidate.exists():
            return candidate
    # Default to the first candidate even if it doesn't exist yet.
    return _virtualenv_python_candidates()[0]


def create_virtualenv() -> None:
    base_python = sys.executable or shutil.which("python3") or "python3"
    VIRTUALENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    run_with_output(
        [base_python, "-m", "venv", str(VIRTUALENV_PATH)],
        f"Creating virtual environment at {VIRTUALENV_PATH}",
    )


def ensure_virtualenv_python() -> Path:
    python_path = locate_virtualenv_python()
    if python_path.exists():
        return python_path
    create_virtualenv()
    python_path = locate_virtualenv_python()
    if not python_path.exists():
        raise RuntimeError(
            f"Unable to find python executable inside virtualenv at {VIRTUALENV_PATH}"
        )
    return python_path


def resolve_python_interpreter() -> str:
    if not USE_VIRTUALENV:
        return sys.executable or shutil.which("python3") or "python3"
    return str(ensure_virtualenv_python())


def compose_is_running(include_gpu_override: bool) -> bool:
    """Return True if any containers in this compose project are running."""
    check_cmd = build_compose_command(["ps", "-q"], include_gpu_override)
    result = subprocess.run(
        check_cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"'docker compose ps' failed: {result.stderr.strip() or 'unknown error'}"
        )
    return bool(result.stdout.strip())


def ensure_flask_entrypoint() -> None:
    if not FLASK_ENTRYPOINT.exists():
        raise FileNotFoundError(
            f"Expected Flask entry point at {FLASK_ENTRYPOINT} but it does not exist."
        )


def start_flask_server(python_executable: str) -> None:
    ensure_flask_entrypoint()
    run_with_output(
        [python_executable, str(FLASK_ENTRYPOINT)],
        "Starting Flask server",
    )


def ensure_env_file() -> None:
    """Verify the .env file exists before launching containers."""
    if DOTENV_PATH.exists():
        return
    raise FileNotFoundError(
        f"Required environment file missing: {DOTENV_PATH}. "
        "Create it (see README secrets section) or point Compose at a different env file."
    )


def collect_project_dependencies() -> list[str]:
    """Read Python dependencies from project.toml."""
    if not PROJECT_METADATA:
        print("project.toml not found; skipping dependency installation.")
        return []
    project_section = PROJECT_METADATA.get("project", {}) or {}
    optional_section = project_section.get("optional-dependencies", {}) or {}
    deps: list[str] = list(project_section.get("dependencies", []) or [])
    for group in OPTIONAL_DEP_GROUPS:
        extras = optional_section.get(group, []) or []
        deps.extend(extras)

    ordered: list[str] = []
    seen: set[str] = set()
    for dep in deps:
        dep = dep.strip()
        if not dep or dep in seen:
            continue
        ordered.append(dep)
        seen.add(dep)
    return ordered


def install_python_dependencies(python_executable: str, skip: bool = False) -> None:
    if skip:
        print("Skipping dependency installation (--skip-deps flag).")
        return
    if not AUTO_INSTALL_DEPENDENCIES:
        print("Dependency auto-install disabled via project.toml.")
        return
    packages = collect_project_dependencies()
    if not packages:
        return
    ensure_pip_installed(python_executable)
    cmd = [python_executable, "-m", "pip", "install", "--upgrade", *packages]
    run_with_output(cmd, "Installing Python dependencies from project.toml")


def ensure_pip_installed(python_executable: str) -> None:
    """Guarantee pip is available for the selected interpreter."""
    check = subprocess.run(
        [python_executable, "-m", "pip", "--version"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if check.returncode == 0:
        return
    print("pip not found for current interpreter; attempting ensurepip bootstrap.")
    try:
        run_with_output(
            [python_executable, "-m", "ensurepip", "--upgrade"],
            "Bootstrapping pip via ensurepip",
        )
    except RuntimeError as err:
        raise RuntimeError(
            "Unable to bootstrap pip automatically. On Debian/Ubuntu/WSL run "
            "`sudo apt-get update && sudo apt-get install python3-pip python3-venv`, "
            "or disable dependency auto-installation via `[tool.manage_stack]`."
        ) from err
    post_check = subprocess.run(
        [python_executable, "-m", "pip", "--version"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if post_check.returncode != 0:
        raise RuntimeError(
            "Unable to install pip automatically; please install pip for this Python interpreter."
        )


def gpu_runtime_available() -> bool:
    """Return True if Docker reports the NVIDIA runtime."""
    info_cmd = ["docker", "info", "--format", "{{json .Runtimes.nvidia}}"]
    result = subprocess.run(
        info_cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        payload = (result.stdout or "").strip()
        if payload and payload not in {"null", "{}"}:
            return True
    # Fallback to checking for nvidia-smi in PATH (WSL/Linux setups)
    return shutil.which("nvidia-smi") is not None


def build_compose_command(extra_args: list[str], include_gpu_override: bool) -> list[str]:
    files = [BASE_COMPOSE_FILE]
    if include_gpu_override and GPU_COMPOSE_FILE.exists():
        files.append(GPU_COMPOSE_FILE)
    cmd: list[str] = COMPOSE_CMD.copy()
    for compose_file in files:
        cmd.extend(["-f", str(compose_file)])
    cmd.extend(extra_args)
    return cmd


def should_use_gpu_override() -> bool:
    if not GPU_COMPOSE_FILE.exists():
        return False
    if gpu_runtime_available():
        print("NVIDIA runtime detected; enabling docker-compose.gpu.yml overrides.")
        return True
    print("No NVIDIA runtime detected; running without GPU overrides.")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage the Docker stack and Flask API server."
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="Skip dependency installation for faster restarts",
    )
    parser.add_argument(
        "--restart-only",
        action="store_true",
        help="Skip 'docker compose down' step to preserve container state",
    )
    parser.add_argument(
        "--clean-shutdown",
        action="store_true",
        help="Force stop containers with both base and GPU compose files to avoid port conflicts",
    )
    args = parser.parse_args()

    python_executable = resolve_python_interpreter()
    use_gpu_override = should_use_gpu_override()
    try:
        install_python_dependencies(python_executable, skip=args.skip_deps)
    except RuntimeError as err:
        print(err, file=sys.stderr)
        sys.exit(1)

    try:
        running = compose_is_running(use_gpu_override)
    except RuntimeError as err:
        print(err, file=sys.stderr)
        sys.exit(1)

    try:
        ensure_env_file()
        
        # Clean shutdown: stop containers with both compose file combinations
        if args.clean_shutdown:
            print("Performing clean shutdown (stopping with all compose file combinations)...")
            # Try stopping with GPU file first
            if GPU_COMPOSE_FILE.exists():
                try:
                    run_with_output(
                        build_compose_command(["down"], include_gpu_override=True),
                        "Stopping Docker Compose stack (with GPU overrides)",
                    )
                except RuntimeError:
                    print("Warning: Failed to stop with GPU compose file, continuing...")
            # Then stop with base file only
            try:
                run_with_output(
                    build_compose_command(["down"], include_gpu_override=False),
                    "Stopping Docker Compose stack (base only)",
                )
            except RuntimeError:
                print("Warning: Failed to stop with base compose file, continuing...")
        elif running and not args.restart_only:
            run_with_output(
                build_compose_command(["down"], use_gpu_override),
                "Stopping running Docker Compose stack",
            )
        elif running and args.restart_only:
            print("Skipping 'docker compose down' (--restart-only flag).")
        else:
            print("No running Docker Compose stack detected.")

        run_with_output(
            build_compose_command(["up", "-d"], use_gpu_override),
            "Starting Docker Compose stack",
        )
    except RuntimeError as err:
        print(err, file=sys.stderr)
        sys.exit(1)

    try:
        start_flask_server(python_executable)
    except (RuntimeError, FileNotFoundError) as err:
        print(err, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
