"""
Tests for the manage_stack utility script.
"""

import sys
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import manage_stack


def test_load_project_metadata_missing_file(monkeypatch, tmp_path):
    """Return empty dict when project.toml is absent."""
    monkeypatch.setattr(manage_stack, "PROJECT_ROOT", tmp_path)
    assert manage_stack.load_project_metadata() == {}


def test_load_project_metadata_reads_file(monkeypatch, tmp_path):
    """Parse project.toml contents when file exists."""
    monkeypatch.setattr(manage_stack, "PROJECT_ROOT", tmp_path)
    project_file = tmp_path / "project.toml"
    project_file.write_text(
        '[project]\nname = "demo"\n[tool.manage_stack]\nbase_compose_file = "base.yml"\n'
    )

    metadata = manage_stack.load_project_metadata()

    assert metadata["project"]["name"] == "demo"
    assert metadata["tool"]["manage_stack"]["base_compose_file"] == "base.yml"


def test_resolve_virtualenv_path_relative_and_absolute(monkeypatch, tmp_path):
    """Resolve venv path from settings and project root."""
    monkeypatch.setattr(manage_stack, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        manage_stack, "MANAGE_STACK_SETTINGS", {"virtualenv_path": "envs/app"}
    )
    assert manage_stack.resolve_virtualenv_path() == tmp_path / "envs" / "app"

    absolute_target = tmp_path / "absenv"
    monkeypatch.setattr(
        manage_stack, "MANAGE_STACK_SETTINGS", {"virtualenv_path": str(absolute_target)}
    )
    assert manage_stack.resolve_virtualenv_path() == absolute_target


def test_run_with_output_success(monkeypatch):
    """run_with_output passes through successful commands."""
    calls = []

    def fake_run(command, cwd, check):
        calls.append((command, cwd, check))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(manage_stack.subprocess, "run", fake_run)

    manage_stack.run_with_output(["echo", "hi"], "test command")
    assert calls and calls[0][0] == ["echo", "hi"]


def test_run_with_output_raises_on_failure(monkeypatch):
    """run_with_output raises RuntimeError when return code is non-zero."""
    monkeypatch.setattr(
        manage_stack.subprocess, "run", lambda *_, **__: SimpleNamespace(returncode=1)
    )
    with pytest.raises(RuntimeError):
        manage_stack.run_with_output(["false"], "failing command")


def test_locate_virtualenv_python_prefers_existing_candidate(monkeypatch, tmp_path):
    """Return first existing python executable."""
    python_bin = tmp_path / "bin" / "python3"
    python_bin.parent.mkdir(parents=True)
    python_bin.touch()

    monkeypatch.setattr(
        manage_stack,
        "_virtualenv_python_candidates",
        lambda: [python_bin, python_bin.parent / "python"],
    )

    assert manage_stack.locate_virtualenv_python() == python_bin


def test_locate_virtualenv_python_falls_back_to_first_candidate(monkeypatch):
    """Return first candidate even when none exist."""
    path = Path("/nonexistent/venv/bin/python3")
    monkeypatch.setattr(
        manage_stack, "_virtualenv_python_candidates", lambda: [path, path.with_name("python")]
    )

    assert manage_stack.locate_virtualenv_python() == path


def test_create_virtualenv_invokes_python_venv(monkeypatch, tmp_path):
    """Create virtualenv uses configured python executable."""
    commands = []
    monkeypatch.setattr(manage_stack, "VIRTUALENV_PATH", tmp_path / "venv")
    monkeypatch.setattr(manage_stack.sys, "executable", "python-test")

    def fake_run_with_output(cmd, desc):
        commands.append((cmd, desc))

    monkeypatch.setattr(manage_stack, "run_with_output", fake_run_with_output)

    manage_stack.create_virtualenv()

    assert commands[0][0] == ["python-test", "-m", "venv", str(tmp_path / "venv")]


def test_ensure_virtualenv_python_creates_when_missing(monkeypatch, tmp_path):
    """create_virtualenv is called when python executable is absent."""
    candidate = tmp_path / "venv" / "bin" / "python3"
    monkeypatch.setattr(manage_stack, "VIRTUALENV_PATH", tmp_path / "venv")
    monkeypatch.setattr(
        manage_stack,
        "_virtualenv_python_candidates",
        lambda: [candidate, candidate.with_name("python")],
    )

    def fake_create_virtualenv():
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.touch()

    monkeypatch.setattr(manage_stack, "create_virtualenv", fake_create_virtualenv)

    python_path = manage_stack.ensure_virtualenv_python()
    assert python_path == candidate


def test_resolve_python_interpreter_skips_virtualenv(monkeypatch):
    """Return system Python when virtualenv usage disabled."""
    monkeypatch.setattr(manage_stack, "USE_VIRTUALENV", False)
    monkeypatch.setattr(manage_stack.sys, "executable", "sys-python")

    assert manage_stack.resolve_python_interpreter() == "sys-python"


def test_resolve_python_interpreter_uses_virtualenv(monkeypatch):
    """Return ensured virtualenv interpreter when enabled."""
    monkeypatch.setattr(manage_stack, "USE_VIRTUALENV", True)
    monkeypatch.setattr(manage_stack, "ensure_virtualenv_python", lambda: Path("/tmp/venv/bin/python"))

    assert manage_stack.resolve_python_interpreter() == "/tmp/venv/bin/python"


def test_compose_is_running_returns_bool(monkeypatch):
    """True when docker compose ps returns stdout; False when empty."""
    monkeypatch.setattr(manage_stack, "build_compose_command", lambda args, include_gpu_override: ["compose", *args])

    def fake_run(_cmd, cwd, capture_output, text, check):
        return SimpleNamespace(returncode=0, stdout="container\n")

    monkeypatch.setattr(manage_stack.subprocess, "run", fake_run)
    assert manage_stack.compose_is_running(True) is True

    def fake_run_empty(_cmd, cwd, capture_output, text, check):
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(manage_stack.subprocess, "run", fake_run_empty)
    assert manage_stack.compose_is_running(False) is False


def test_compose_is_running_raises_on_error(monkeypatch):
    """Raise RuntimeError on docker compose ps failure."""
    monkeypatch.setattr(manage_stack, "build_compose_command", lambda args, include_gpu_override: ["compose", *args])
    monkeypatch.setattr(
        manage_stack.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stderr="boom"),
    )
    with pytest.raises(RuntimeError):
        manage_stack.compose_is_running(False)


def test_ensure_flask_entrypoint_checks_existence(monkeypatch, tmp_path):
    """Raise when Flask entrypoint missing."""
    monkeypatch.setattr(manage_stack, "FLASK_ENTRYPOINT", tmp_path / "missing.py")
    with pytest.raises(FileNotFoundError):
        manage_stack.ensure_flask_entrypoint()

    existing = tmp_path / "exists.py"
    existing.touch()
    monkeypatch.setattr(manage_stack, "FLASK_ENTRYPOINT", existing)
    manage_stack.ensure_flask_entrypoint()


def test_start_flask_server_invokes_python(monkeypatch, tmp_path):
    """start_flask_server calls run_with_output after entrypoint check."""
    entrypoint = tmp_path / "host_flask.py"
    entrypoint.touch()
    monkeypatch.setattr(manage_stack, "FLASK_ENTRYPOINT", entrypoint)
    calls = []
    monkeypatch.setattr(manage_stack, "run_with_output", lambda cmd, desc: calls.append((cmd, desc)))

    manage_stack.start_flask_server("python-bin")

    assert calls[0][0] == ["python-bin", str(entrypoint)]


def test_ensure_env_file(monkeypatch, tmp_path):
    """Verify .env existence check."""
    dotenv_missing = tmp_path / ".env"
    monkeypatch.setattr(manage_stack, "DOTENV_PATH", dotenv_missing)
    with pytest.raises(FileNotFoundError):
        manage_stack.ensure_env_file()

    dotenv_missing.touch()
    manage_stack.ensure_env_file()


def test_collect_project_dependencies_merges_and_deduplicates(monkeypatch):
    """Combine base dependencies, optional groups, and drop duplicates."""
    metadata = {
        "project": {
            "dependencies": ["flask", "pytest", "flask"],
            "optional-dependencies": {
                "dev": ["pytest", "black"],
                "extras": ["black", "ruff"],
            },
        }
    }
    monkeypatch.setattr(manage_stack, "PROJECT_METADATA", metadata)
    monkeypatch.setattr(manage_stack, "OPTIONAL_DEP_GROUPS", ["dev", "extras"])

    deps = manage_stack.collect_project_dependencies()
    assert deps == ["flask", "pytest", "black", "ruff"]


def test_install_python_dependencies_respects_flags(monkeypatch):
    """Skip installation when skip flag or auto-install disabled."""
    calls: list[str] = []
    monkeypatch.setattr(manage_stack, "AUTO_INSTALL_DEPENDENCIES", True)
    monkeypatch.setattr(manage_stack, "collect_project_dependencies", lambda: ["pkg"])
    monkeypatch.setattr(manage_stack, "ensure_pip_installed", lambda *_: calls.append("pip"))
    monkeypatch.setattr(manage_stack, "run_with_output", lambda *_args, **_kwargs: calls.append("run"))

    manage_stack.install_python_dependencies("python", skip=True)
    assert calls == []

    monkeypatch.setattr(manage_stack, "AUTO_INSTALL_DEPENDENCIES", False)
    manage_stack.install_python_dependencies("python", skip=False)
    assert calls == []


def test_install_python_dependencies_no_packages(monkeypatch):
    """Do nothing when dependency list is empty."""
    monkeypatch.setattr(manage_stack, "AUTO_INSTALL_DEPENDENCIES", True)
    monkeypatch.setattr(manage_stack, "collect_project_dependencies", lambda: [])
    manage_stack.install_python_dependencies("python")


def test_install_python_dependencies_runs_pip(monkeypatch):
    """Install dependencies via pip when available."""
    commands = []
    monkeypatch.setattr(manage_stack, "AUTO_INSTALL_DEPENDENCIES", True)
    monkeypatch.setattr(manage_stack, "collect_project_dependencies", lambda: ["pkg1", "pkg2"])
    monkeypatch.setattr(manage_stack, "ensure_pip_installed", lambda _exe: commands.append("ensure_pip"))
    monkeypatch.setattr(
        manage_stack, "run_with_output", lambda cmd, desc: commands.append(cmd)
    )

    manage_stack.install_python_dependencies("python-bin")

    expected = ["python-bin", "-m", "pip", "install", "--upgrade", "pkg1", "pkg2"]
    assert expected in commands
    assert "ensure_pip" in commands


def test_ensure_pip_installed_short_circuit(monkeypatch):
    """No bootstrap when pip already installed."""
    monkeypatch.setattr(
        manage_stack.subprocess, "run", lambda *_, **__: SimpleNamespace(returncode=0)
    )
    monkeypatch.setattr(
        manage_stack, "run_with_output", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError)
    )

    manage_stack.ensure_pip_installed("python")


def test_ensure_pip_installed_bootstraps(monkeypatch):
    """Bootstrap pip with ensurepip when initial check fails."""
    calls = []

    checks = iter(
        [
            SimpleNamespace(returncode=1),
            SimpleNamespace(returncode=0),
        ]
    )
    monkeypatch.setattr(manage_stack.subprocess, "run", lambda *_, **__: next(checks))
    monkeypatch.setattr(
        manage_stack, "run_with_output", lambda cmd, desc: calls.append((cmd, desc))
    )

    manage_stack.ensure_pip_installed("python")
    assert calls and "ensurepip" in calls[0][0]


def test_ensure_pip_installed_raises_when_still_missing(monkeypatch):
    """Raise if pip is still unavailable after ensurepip."""
    checks = iter(
        [
            SimpleNamespace(returncode=1),
            SimpleNamespace(returncode=1),
        ]
    )
    monkeypatch.setattr(manage_stack.subprocess, "run", lambda *_, **__: next(checks))
    monkeypatch.setattr(manage_stack, "run_with_output", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError):
        manage_stack.ensure_pip_installed("python")


def test_gpu_runtime_available_from_docker_info(monkeypatch):
    """True when docker info reports NVIDIA runtime."""
    monkeypatch.setattr(
        manage_stack.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout='{"nvidia":"present"}\n'),
    )
    monkeypatch.setattr(manage_stack.shutil, "which", lambda *_: None)
    assert manage_stack.gpu_runtime_available() is True


def test_gpu_runtime_available_from_nvidia_smi(monkeypatch):
    """Fallback to nvidia-smi detection when docker info fails."""
    monkeypatch.setattr(
        manage_stack.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout=""),
    )
    monkeypatch.setattr(manage_stack.shutil, "which", lambda *_: "/usr/bin/nvidia-smi")
    assert manage_stack.gpu_runtime_available() is True


def test_gpu_runtime_unavailable(monkeypatch):
    """False when neither docker nor nvidia-smi report runtime."""
    monkeypatch.setattr(
        manage_stack.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout=""),
    )
    monkeypatch.setattr(manage_stack.shutil, "which", lambda *_: None)
    assert manage_stack.gpu_runtime_available() is False


def test_build_compose_command_includes_gpu_file(monkeypatch, tmp_path):
    """Include GPU compose file when requested and present."""
    base = tmp_path / "base.yml"
    gpu = tmp_path / "gpu.yml"
    base.touch()
    gpu.touch()

    monkeypatch.setattr(manage_stack, "COMPOSE_CMD", ["dc"])
    monkeypatch.setattr(manage_stack, "BASE_COMPOSE_FILE", base)
    monkeypatch.setattr(manage_stack, "GPU_COMPOSE_FILE", gpu)

    cmd = manage_stack.build_compose_command(["up"], include_gpu_override=True)
    assert cmd == ["dc", "-f", str(base), "-f", str(gpu), "up"]


def test_build_compose_command_omits_gpu_when_missing(monkeypatch, tmp_path):
    """Ignore GPU compose override when file not present."""
    base = tmp_path / "base.yml"
    base.touch()
    missing_gpu = tmp_path / "gpu.yml"

    monkeypatch.setattr(manage_stack, "COMPOSE_CMD", ["docker", "compose"])
    monkeypatch.setattr(manage_stack, "BASE_COMPOSE_FILE", base)
    monkeypatch.setattr(manage_stack, "GPU_COMPOSE_FILE", missing_gpu)

    cmd = manage_stack.build_compose_command(["ps"], include_gpu_override=True)
    assert "-f" in cmd and str(missing_gpu) not in cmd


def test_should_use_gpu_override(monkeypatch, tmp_path):
    """Enable GPU overrides only when file exists and runtime available."""
    gpu_file = tmp_path / "gpu.yml"
    monkeypatch.setattr(manage_stack, "GPU_COMPOSE_FILE", gpu_file)
    monkeypatch.setattr(manage_stack, "gpu_runtime_available", lambda: True)
    assert manage_stack.should_use_gpu_override() is False

    gpu_file.touch()
    assert manage_stack.should_use_gpu_override() is True

    monkeypatch.setattr(manage_stack, "gpu_runtime_available", lambda: False)
    assert manage_stack.should_use_gpu_override() is False


def test_main_clean_shutdown(monkeypatch, tmp_path):
    """Clean shutdown stops stacks with and without GPU overrides then exits."""
    base = tmp_path / "base.yml"
    gpu = tmp_path / "gpu.yml"
    base.touch()
    gpu.touch()

    monkeypatch.setattr(manage_stack, "BASE_COMPOSE_FILE", base)
    monkeypatch.setattr(manage_stack, "GPU_COMPOSE_FILE", gpu)
    monkeypatch.setattr(sys, "argv", ["manage_stack.py", "--clean-shutdown"])

    commands = []
    monkeypatch.setattr(
        manage_stack,
        "build_compose_command",
        lambda extra_args, include_gpu_override: ["cmd", "gpu" if include_gpu_override else "base", *extra_args],
    )
    monkeypatch.setattr(
        manage_stack, "run_with_output", lambda cmd, desc: commands.append((cmd, desc))
    )
    monkeypatch.setattr(manage_stack, "should_use_gpu_override", lambda: True)

    with pytest.raises(SystemExit) as exit_info:
        manage_stack.main()

    assert exit_info.value.code == 0
    # Two down commands: GPU then base
    assert any(cmd[0][1] == "gpu" for cmd in commands)
    assert any(cmd[0][1] == "base" for cmd in commands)


def test_main_restart_only_skips_down(monkeypatch):
    """When restart-only flag is set, skip compose down but start up."""
    monkeypatch.setattr(sys, "argv", ["manage_stack.py", "--restart-only"])
    monkeypatch.setattr(manage_stack, "resolve_python_interpreter", lambda: "python")
    monkeypatch.setattr(manage_stack, "should_use_gpu_override", lambda: False)
    monkeypatch.setattr(manage_stack, "install_python_dependencies", lambda *_, **__: None)
    monkeypatch.setattr(manage_stack, "compose_is_running", lambda *_: True)
    monkeypatch.setattr(manage_stack, "ensure_env_file", lambda: None)

    commands = []
    monkeypatch.setattr(
        manage_stack,
        "build_compose_command",
        lambda extra_args, include_gpu_override: ["cmd", *extra_args, str(include_gpu_override)],
    )
    monkeypatch.setattr(manage_stack, "run_with_output", lambda cmd, desc: commands.append(cmd))
    monkeypatch.setattr(manage_stack, "start_flask_server", lambda *_: None)

    manage_stack.main()

    assert commands == [["cmd", "up", "-d", "False"]]


def test_main_stops_and_starts_when_running(monkeypatch):
    """When stack is running, perform down then up sequence."""
    monkeypatch.setattr(sys, "argv", ["manage_stack.py"])
    monkeypatch.setattr(manage_stack, "resolve_python_interpreter", lambda: "python")
    monkeypatch.setattr(manage_stack, "should_use_gpu_override", lambda: True)
    monkeypatch.setattr(manage_stack, "install_python_dependencies", lambda *_, **__: None)
    monkeypatch.setattr(manage_stack, "compose_is_running", lambda *_: True)
    monkeypatch.setattr(manage_stack, "ensure_env_file", lambda: None)

    commands = []
    monkeypatch.setattr(
        manage_stack,
        "build_compose_command",
        lambda extra_args, include_gpu_override: ["cmd", *extra_args, str(include_gpu_override)],
    )
    monkeypatch.setattr(manage_stack, "run_with_output", lambda cmd, desc: commands.append(cmd))
    monkeypatch.setattr(manage_stack, "start_flask_server", lambda *_: None)

    manage_stack.main()

    # Expect down then up
    assert commands[0] == ["cmd", "down", "True"]
    assert commands[1] == ["cmd", "up", "-d", "True"]


def test_main_handles_no_running_stack(monkeypatch):
    """Skip down when nothing is running."""
    monkeypatch.setattr(sys, "argv", ["manage_stack.py"])
    monkeypatch.setattr(manage_stack, "resolve_python_interpreter", lambda: "python")
    monkeypatch.setattr(manage_stack, "should_use_gpu_override", lambda: False)
    monkeypatch.setattr(manage_stack, "install_python_dependencies", lambda *_, **__: None)
    monkeypatch.setattr(manage_stack, "compose_is_running", lambda *_: False)
    monkeypatch.setattr(manage_stack, "ensure_env_file", lambda: None)

    commands = []
    monkeypatch.setattr(
        manage_stack,
        "build_compose_command",
        lambda extra_args, include_gpu_override: ["cmd", *extra_args, str(include_gpu_override)],
    )
    monkeypatch.setattr(manage_stack, "run_with_output", lambda cmd, desc: commands.append(cmd))
    monkeypatch.setattr(manage_stack, "start_flask_server", lambda *_: None)

    manage_stack.main()

    assert commands == [["cmd", "up", "-d", "False"]]


def test_main_exits_on_dependency_install_error(monkeypatch):
    """Exit with code 1 when dependency installation fails."""
    monkeypatch.setattr(sys, "argv", ["manage_stack.py"])
    monkeypatch.setattr(manage_stack, "resolve_python_interpreter", lambda: "python")
    monkeypatch.setattr(manage_stack, "should_use_gpu_override", lambda: False)

    def failing_install(*_, **__):
        raise RuntimeError("install error")

    monkeypatch.setattr(manage_stack, "install_python_dependencies", failing_install)

    with pytest.raises(SystemExit) as exit_info:
        manage_stack.main()

    assert exit_info.value.code == 1


def test_main_exits_on_compose_ps_error(monkeypatch):
    """Exit with code 1 when compose_is_running raises."""
    monkeypatch.setattr(sys, "argv", ["manage_stack.py"])
    monkeypatch.setattr(manage_stack, "resolve_python_interpreter", lambda: "python")
    monkeypatch.setattr(manage_stack, "should_use_gpu_override", lambda: False)
    monkeypatch.setattr(manage_stack, "install_python_dependencies", lambda *_, **__: None)
    monkeypatch.setattr(
        manage_stack, "compose_is_running", lambda *_: (_ for _ in ()).throw(RuntimeError("ps error"))
    )

    with pytest.raises(SystemExit) as exit_info:
        manage_stack.main()

    assert exit_info.value.code == 1


def test_main_exits_on_missing_env(monkeypatch):
    """Exit with code 1 when .env is absent."""
    monkeypatch.setattr(sys, "argv", ["manage_stack.py"])
    monkeypatch.setattr(manage_stack, "resolve_python_interpreter", lambda: "python")
    monkeypatch.setattr(manage_stack, "should_use_gpu_override", lambda: False)
    monkeypatch.setattr(manage_stack, "install_python_dependencies", lambda *_, **__: None)
    monkeypatch.setattr(manage_stack, "compose_is_running", lambda *_: False)
    monkeypatch.setattr(
        manage_stack, "ensure_env_file", lambda: (_ for _ in ()).throw(RuntimeError("missing env"))
    )

    with pytest.raises(SystemExit) as exit_info:
        manage_stack.main()

    assert exit_info.value.code == 1


def test_main_exits_on_flask_start_error(monkeypatch):
    """Exit with code 1 when starting Flask server fails."""
    monkeypatch.setattr(sys, "argv", ["manage_stack.py"])
    monkeypatch.setattr(manage_stack, "resolve_python_interpreter", lambda: "python")
    monkeypatch.setattr(manage_stack, "should_use_gpu_override", lambda: False)
    monkeypatch.setattr(manage_stack, "install_python_dependencies", lambda *_, **__: None)
    monkeypatch.setattr(manage_stack, "compose_is_running", lambda *_: False)
    monkeypatch.setattr(manage_stack, "ensure_env_file", lambda: None)
    monkeypatch.setattr(manage_stack, "run_with_output", lambda *_: None)

    def failing_start(*_):
        raise RuntimeError("flask start error")

    monkeypatch.setattr(manage_stack, "start_flask_server", failing_start)

    with pytest.raises(SystemExit) as exit_info:
        manage_stack.main()

    assert exit_info.value.code == 1
