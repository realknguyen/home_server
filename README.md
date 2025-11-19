# Local LLM Home Stack

This repository contains everything needed to stand up a privacy-friendly home lab for large language models and personal search. It combines reproducible Docker services (Ollama, Open WebUI, SearxNG, and Glance), opinionated Glance configuration, and a small Flask extension that lets you send authenticated shutdown/restart commands to the host directly from the dashboard. The Python code is fully covered by tests so you can evolve the automation safely.

---

## At a Glance

| Component            | Location                         | Purpose                                                                                                         |
| -------------------- | -------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Docker stack         | `docker-compose.yml`             | Boots Ollama (models), Open WebUI (chat UI), Glance (dashboard), and SearxNG (meta search).                     |
| Dashboard config     | `glance/config`, `glance/assets` | Home page layouts, widgets, and CSS overrides for Glance.                                                       |
| Custom API extension | `glance/custom_api_extension`    | Flask service that Glance calls to restart or power down the host with per-platform commands and rate limiting. |
| Persistent data      | `data/`                          | Docker bind mounts for Ollama models, Open WebUI, and SearxNG. Ignored from Git to keep the repo lean.          |
| Automated tests      | `tests/`                         | Pytest suite validating every Flask endpoint, the token guard, rate limiting, and OS detection helpers.         |

---

## Requirements

| Category       | Details                                                                                                                                          |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Host OS        | Linux or Windows with WSL2 (compose file is tuned for WSL GPU passthrough).                                                                      |
| Containers     | Docker 24+ and Docker Compose plugin. NVIDIA Container Toolkit if you want GPU acceleration.                                                     |
| Python tooling | Python 3.11+ plus `pip` for running/tests of the Flask extension.                                                                                |
| Secrets        | `.env` file defining at least `MY_SECRET_TOKEN` (shared between Glance and the Flask app) and `MY_PASSWORD` (hashed password for the Glance UI). |

Optional but recommended: `just` or `make` for custom scripts, and a virtual environment manager such as `uv`, `pyenv`, or `rye`.

---

## Repository Layout

```
local_llm/
├── config/                 # Extra configuration blobs consumed by services (e.g., SearxNG)
├── data/                   # Docker volumes for Ollama/OpenWebUI/SearxNG (ignored from Git)
├── glance/
│   ├── assets/             # Custom icons and CSS used by Glance
│   ├── config/             # Glance YAML configuration (home + start pages)
│   └── custom_api_extension/
│       ├── host_flask.py   # Flask entry point exposed to Glance
│       ├── flask_utils.py  # Platform detection + safe command runner
│       └── tests/...       # (See top-level tests/)
├── tests/                  # Pytest suite for the Flask extension
├── docker-compose.yml      # Multi-service stack definition
├── docker-compose.gpu.yml  # Optional GPU overrides auto-selected when NVIDIA runtime exists
├── project.toml            # PEP 621 metadata & dev dependency lock-in
└── README.md               # You are here
```

---

## Quick Start

1. **Clone the repository**

   ```bash
   git clone https://github.com/your-user/local_llm.git
   cd local_llm
   ```

2. **Create an `.env` file**

   ```dotenv
   # Shared secret for Glance auth + Flask token_required decorator
   MY_SECRET_TOKEN=change-me
   # PBKDF2 hash or bcrypt hash – generate with `python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-password'))"`
   MY_PASSWORD=pbkdf2:sha256:600000$...
   ```

   Keep this file out of source control (it's already ignored).

3. **Launch everything with the orchestration script**

   ```bash
   python manage_stack.py
   ```

   Each run:

   - Installs Python dependencies from `project.toml` (core + optional groups listed under `[tool.manage_stack.optional_dependency_groups]`).
   - Bootstraps `pip` automatically with `ensurepip` if your Python interpreter was installed without it.
   - Verifies `.env` exists before touching Docker.
   - Recreates the Docker Compose stack, automatically layering in `docker-compose.gpu.yml` when `docker info` reports an NVIDIA runtime.
   - Boots the Flask API (`glance/custom_api_extension/host_flask.py`) once containers are healthy.

   The script now creates/uses a project-local virtual environment (`.venv` by default) so dependency installs never touch the system Python that Debian/Ubuntu marks as "externally managed" (PEP 668). Customize the location or disable this behavior via `[tool.manage_stack] use_virtualenv` / `virtualenv_path` in `project.toml`.

   > **WSL tip:** Ubuntu images sometimes ship without `pip`/`ensurepip`. If the script fails during the bootstrap step, run `sudo apt-get update && sudo apt-get install python3-pip python3-venv` and rerun `python manage_stack.py`.
   > :warning: Avoid `sudo python manage_stack.py` or the `.venv` directory will be owned by root and unusable from your normal user.

4. **Prefer manual control?** (optional)

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install -r glance/custom_api_extension/requirements.txt
   # or, if your tooling consumes `project.toml` / `pyproject.toml`:
   python -m pip install -e .[dev]
   docker compose up -d
   # GPU-enabled manual launch:
   docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
   ```

   | Service    | URL                      | Notes                                             |
   | ---------- | ------------------------ | ------------------------------------------------- |
   | Ollama     | `http://localhost:11434` | Model runtime and embedding server.               |
   | Open WebUI | `http://localhost:8081`  | Web UI proxied to Ollama, RAG enabled via FAISS.  |
   | Glance     | `http://localhost:8090`  | Dashboard configured by `glance/config`.          |
   | SearxNG    | `http://localhost:8082`  | Self-hosted metasearch for RAG or manual queries. |

   Health checks on Ollama gate Open WebUI startup. GPU passthrough is now opt-in via `docker-compose.gpu.yml`; include it only if your host exposes NVIDIA runtimes.

---

## Stack Automation Script

`manage_stack.py` is the recommended way to (re)start the entire stack:

- Installs dependencies declared in `project.toml`.
- Ensures `.env` exists before issuing Docker commands.
- Detects NVIDIA runtimes via `docker info` and automatically merges `docker-compose.gpu.yml` when available.
- Stops any running containers, recreates the stack, and finally launches the Flask API in the foreground so you can see its logs.

Behaviour is configurable from `[tool.manage_stack]` inside `project.toml`:

```toml
[tool.manage_stack]
base_compose_file = "docker-compose.yml"
gpu_compose_file = "docker-compose.gpu.yml"
optional_dependency_groups = ["dev"]
auto_install_dependencies = true
use_virtualenv = true
virtualenv_path = ".venv"
```

Set `auto_install_dependencies = false` to skip the pip step, change `optional_dependency_groups` if you only want a subset of extras, or point `virtualenv_path` somewhere else (or set `use_virtualenv = false`) if you prefer to manage environments yourself.

### Command-Line Arguments

```bash
# Normal full restart
python manage_stack.py

# Skip dependency installation for faster restarts
python manage_stack.py --skip-deps

# Skip 'docker compose down' to preserve container state
python manage_stack.py --restart-only

# Force clean shutdown (stops containers with all compose file combinations)
python manage_stack.py --clean-shutdown

# View all options
python manage_stack.py --help
```

### Windows Startup Script

For Windows users, `start_services.ps1` is provided for use with Task Scheduler to auto-start services on boot:

```powershell
# Run manually
.\start_services.ps1

# Add to Task Scheduler
# Action: Start a program
# Program: powershell.exe
# Arguments: -ExecutionPolicy Bypass -File "C:\path\to\home_server\start_services.ps1"
# Start in: C:\path\to\home_server
```

The script automatically:

- Starts the Docker Compose stack
- Installs Python dependencies from `pyproject.toml`
- Launches the Flask API server
- Logs all output to `flask_service.log` for troubleshooting

---

## Custom Flask API Extension

Located in `glance/custom_api_extension`, this mini-service exposes authenticated endpoints that Glance widgets can call to control the host.

### Running Locally

1. **Install dependencies**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install -r glance/custom_api_extension/requirements.txt
   # or, to honor the dependency lists inside `project.toml`:
   python -m pip install -e .[dev]
   ```

2. **Start the server**

   ```bash
   export FLASK_APP=glance.custom_api_extension.host_flask
   export MY_SECRET_TOKEN=change-me  # or read from .env via `python -m flask run --env-file .env`
   python -m flask run --host=0.0.0.0 --port=5001
   # direct alternative:
   python glance/custom_api_extension/host_flask.py
   ```

- Rate limiting: default limit is `5 per minute` per IP enforced by `flask-limiter`.
- Auth: `token_required` accepts `Authorization: Bearer <token>`, `Authorization: <token>`, `token` form fields, or `?token=` query params.

### Endpoints

| Route       | Method | Description                                                                       | Platform-specific behavior                                                                                          |
| ----------- | ------ | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `/`         | GET    | Health check returning `Hello, World!`. Protected by the rate limiter.            | –                                                                                                                   |
| `/shutdown` | POST   | Issues `sudo shutdown -h now`, `shutdown /s /t 0`, or equivalent depending on OS. | Linux/WSL/macOS use `sudo shutdown -h now`; Windows uses `shutdown /s /t 0`; unsupported platforms return HTTP 400. |
| `/restart`  | POST   | Issues safe restart command for the active platform.                              | Linux/WSL/macOS use `shutdown -r now`; Windows uses `shutdown /r /t 0`.                                             |

Commands are executed via `run_command()` which captures output and surfaces failures with HTTP 500 responses plus stderr payloads. Platform detection logic leans on `platform`, `distro.id`, and heuristics for WSL to keep commands accurate.

---

## Configuration Reference

| File/Dir                                   | Purpose                                                                                                             |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| `glance/config/glance.yml`                 | Registers pages, auth strategy, and proxies dashboard env vars from `.env`.                                         |
| `glance/config/home.yml` / `startpage.yml` | Widget layout, RSS feeds, weather, markets, Twitch, and utility groups. Use them as templates for additional pages. |
| `glance/assets/user.css`                   | Brand the dashboard. Clear your browser cache (Ctrl+F5) after editing due to caching.                               |
| `config/searxng-config`                    | Passed-through config directory for SearxNG container.                                                              |
| `data/<service>`                           | Docker bind mounts that retain models, indexes, and user data between restarts.                                     |
| `docker-compose.gpu.yml`                   | NVIDIA device reservations layered on top of `docker-compose.yml` when GPU acceleration is available.               |
| `manage_stack.py`                          | Automation entry point that installs deps, restarts Compose, and launches the Flask API.                            |

Feel free to add more compose services (e.g., `qdrant`, `postgres`) – just extend `docker-compose.yml` and Glance labels for discovery.

---

## Testing & Quality

- **Unit tests**: Run `pytest` from the repo root. The suite (36 tests) covers endpoint auth flows, rate limiting, platform branching, and subprocess error handling.
- **Formatting**: `black` keeps code style consistent (`black .`).
- **Linting**: `ruff` (optional) catches import order and logical issues early (`ruff check .`).

CI is not bundled, but the commands above are what the project expects before pushing changes.

---

## Maintenance & Troubleshooting

| Issue                                   | Fix                                                                                                                                                                                                                    |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Rate limiter blocking tests             | The default pytest client fixture disables the limiter; toggle `app.config['RATELIMIT_ENABLED'] = True` inside a test to cover limiter behavior (see `tests/test_api_endpoints.py:test_index_rate_limiting_enforced`). |
| Permission errors on shutdown/restart   | Ensure the user that runs the Flask API has sudo rights without a password prompt or adjust `run_command` to call privileged helper scripts.                                                                           |
| GPU not visible inside Ollama container | Install the NVIDIA Container Toolkit, verify `docker info                                                                                                                                                              | grep -i nvidia`, then either run `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d`or rerun`python manage_stack.py` so the GPU overrides are applied. |
| Glance auth failing                     | Regenerate `MY_PASSWORD` hash with Werkzeug and keep `MY_SECRET_TOKEN` identical across `.env` and any widgets hitting the Flask API.                                                                                  |

---

## Changelog

### Recent Updates

#### Port Configuration

- Changed Glance from port 8080 to 8090 (avoids conflict with Windows AgentService.exe)
- Updated all references in docker-compose.yml and documentation

#### CORS & LAN Control

- Added `flask-cors` dependency for cross-origin requests
- Configured Private Network Access headers for Chrome compatibility
- Changed API URLs from `localhost` to `falconnet.local` for remote control from mobile/laptop

#### Windows Support

- Created `start_services.ps1` PowerShell script for Windows Task Scheduler
- Redirects Flask output to `flask_service.log` for monitoring
- Auto-installs dependencies and starts Docker + Flask

#### Enhanced manage_stack.py

- `--skip-deps`: Skip dependency installation for faster restarts
- `--restart-only`: Preserve container state (skip `docker compose down`)
- `--clean-shutdown`: Stop all containers and exit without restarting
- `--upgrade`: Always upgrade pip dependencies to latest versions

#### Verified Working

- ✅ All 36 tests passing
- ✅ Port 8090 for Glance (HTTP)
- ✅ Port 5001 for Flask API (HTTP)
- ✅ CORS enabled for cross-origin requests
- ✅ Windows shutdown/restart commands correct
- ✅ LAN hostname (`falconnet.local`) configured
- ✅ GPU detection and docker-compose.gpu.yml working

---

## Contributing

1. Fork and branch from `main`.
2. Run `pip install -e .[dev]` and `pytest` before committing.
3. Follow the conventions in `tests/` when adding Flask endpoints: write fixtures, mock external systems, and assert command invocations explicitly.
4. Open a pull request with a summary of Docker/service changes plus any dashboard screenshots if UI changes are involved.

---

## License

Licensed under the MIT License. See [`LICENSE`](LICENSE) for the full text.
