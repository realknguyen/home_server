# Local LLM Home Stack

Self-hosted home lab for private LLM chat/search with a Glance dashboard and a secured Flask control API. The stack ships production defaults, GPU-aware docker-compose overlays, and CI that enforces lint + tests from `pyproject.toml` only.

---

## What’s Inside

| Component                | Path                         | Notes |
| ------------------------ | ---------------------------- | ----- |
| Docker stack             | `docker-compose.yml` + optional `docker-compose.gpu.yml` | Ollama, Open WebUI, Glance, SearxNG; GPU overlay auto-applied when NVIDIA runtime is detected. |
| Dashboard config         | `glance/config`, `glance/assets`                         | Glance layouts, widgets, CSS. |
| Control API              | `glance/custom_api_extension`                            | Flask app with token auth, rate limits, rotating logs, platform-aware shutdown/restart. |
| Automation script        | `manage_stack.py`                                         | Creates venv, installs deps from `project.toml`, manages Compose, launches Flask API. |
| Tests                    | `tests/`                                                  | 36 pytest cases covering endpoints, auth, platform detection, subprocess handling. |
| Docs                     | `docs/`                                                   | `gpu-optimization.md`, `windows-autostart.md` (moved from repo root). |
| CI workflows             | `.github/workflows/python-app.yml`, `.github/workflows/pylint.yml` | Ruff + pytest matrix; separate Pylint gate. |

---

## Documentation

- GPU tuning and model tables: `docs/gpu-optimization.md`
- Windows autostart (Task Scheduler + PowerShell): `docs/windows-autostart.md`
- High-volume WebSocket server reference: `docs/websocket_implementation_guide.md`

---

## High-Volume WebSocket Pattern

Need to fan out more than 500 concurrent subscriptions (for example, market data streams) without starving the rest of the stack? Start with the asynchronous pattern captured in `docs/websocket_implementation_guide.md` and layer it into your own service.

**Core architecture**
- `asyncio` + `websockets` server that registers clients, tracks subscriptions in a `defaultdict(set)`, and keeps per-client background tasks for message handling.
- Subscription-aware broadcaster that routes market updates to either the full client set or the narrow exchange/symbol audience.
- Background data processor (async task or external producer) pushing real-time payloads into the broadcaster while the main event loop services heartbeats.

**Operational guidance**
- Tune `ping_interval`, `ping_timeout`, `close_timeout`, and `max_size` when calling `websockets.serve` to keep latencies predictable under load; increase `read_limit`/`write_limit` for very chatty feeds.
- Monitor memory by pruning dead sockets and canceling long-running tasks whenever clients disconnect; batch sends with `asyncio.gather` to avoid head-of-line blocking.
- Back the service with system-level limits (`ulimit -n 65536`), TLS, and authentication, plus deployment runners such as Uvicorn/FastAPI or a load balancer when you need horizontal scale.

**Background service hook**
Use the `--background` flag pattern from the guide to fork a child process, persist its PID, and keep the WebSocket pump alive outside terminal sessions. Instrument both the parent and child paths so `manage_stack.py` (or your supervisor) can detect failures and restart the feed automatically.

---

## Prerequisites

- Python ≥ 3.11 (for tests/CLI) with `pip`
- Docker 24+ with Compose plugin
- NVIDIA Container Toolkit (if using GPU)
- `.env` with at least:
  - `MY_SECRET_TOKEN` (shared with Glance widgets)
  - `MY_PASSWORD` (Werkzeug hash for Glance login)

---

## Fast Start (recommended)

```bash
git clone https://github.com/your-user/local_llm.git
cd local_llm
python manage_stack.py
```

What `manage_stack.py` does:
- Creates/uses `.venv` (configurable via `[tool.manage_stack]` in `project.toml`).
- Installs core + optional dependency groups (`optional_dependency_groups = ["dev"]`).
- Ensures `.env` exists.
- Picks GPU overrides automatically when `docker info` reports an NVIDIA runtime.
- Restarts Docker Compose and launches the Flask API in the foreground for visible logs.

Useful flags:
- `--skip-deps` to skip pip install on restarts
- `--restart-only` to avoid `docker compose down`
- `--clean-shutdown` to stop everything and exit

---

## Manual Bring-up

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
docker compose up -d               # CPU
# or GPU
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

Service endpoints:
- Ollama: `http://localhost:11434`
- Open WebUI: `http://localhost:8081`
- Glance: `http://localhost:8090`
- SearxNG: `http://localhost:8082`
- Flask control API: `http://localhost:5001`

---

## Flask Control API (glance/custom_api_extension)

- Token auth: `Authorization: Bearer <token>`, `Authorization: <token>`, form `token`, or `?token=` query.
- Rate limits: default `20/min` global plus `5/min` per endpoint.
- Logging: rotating file `host_flask.log` with ANSI-stripping formatter.
- Platform-aware commands:
  - Shutdown: Linux/WSL/macOS → `sudo shutdown -h now`; Windows → `shutdown /s /f /t 0`
  - Restart: Linux/WSL/macOS → `shutdown -r now`; Windows → `shutdown /r /f /t 0`

Endpoints:
| Route | Method | Description |
| --- | --- | --- |
| `/` | GET | Health check (rate limited) |
| `/shutdown` | POST | Authenticated host shutdown |
| `/restart` | POST | Authenticated host restart |

---

## CI & Quality Gates

- `.github/workflows/python-app.yml`: Ruff lint + pytest on Python 3.11 & 3.12 with coverage artifacts. Dependencies installed from `pyproject.toml` via `pip install -e '.[dev]'` (no `requirements.txt`).
- `.github/workflows/pylint.yml`: Dedicated Pylint job on `glance/` and `manage_stack.py`; add `fail-under` in `pyproject.toml` to enforce a minimum score (e.g., `[tool.pylint.main] fail-under = 9.5`).
- Local commands: `ruff check .`, `pytest`, `pylint glance manage_stack.py`.

---

## Windows Autostart

Bring the stack up before anyone logs in by running `start_services.ps1` from Task Scheduler. The script installs Python deps, starts Docker Compose, launches the Flask API, and writes to `flask_service.log`.

**Prereqs**
- Windows 10/11 with admin rights
- Docker Desktop set to start on boot
- Python + repo deps already installed

**Task Scheduler recipe** (full screenshots live in `docs/windows-autostart.md`)
1. Create a new task (not basic) named `Home Server Auto Start`, select "Run whether user is logged on or not" and "Run with highest privileges", and target Windows 10/11.
2. Add a trigger: `At startup`, delayed 30s so Docker is ready, leave it enabled.
3. Add an action: `Start a program` → `powershell.exe` with arguments `-ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\path\to\home_server\start_services.ps1"` and `Start in` pointed at the repo directory.
4. Conditions: uncheck "Start only if on AC power" and optionally enable "Wake the computer".
5. Settings: allow on-demand runs, run ASAP if missed, do **not** stop after a duration, and set "If already running" to "Do not start a new instance".
6. Save, enter your password, right-click → Run to verify, then inspect `flask_service.log` for success.

**Verify shutdown/restart permissions**
```bash
curl -X POST http://YOUR_SERVER_IP:5001/shutdown \
  -H "Authorization: Bearer YOUR_SECRET_TOKEN"
```
If you see "Access Denied", re-check highest-privileges + "Run whether user is logged on or not".

**Firewall**
```powershell
New-NetFirewallRule -DisplayName "Flask API" -Direction Inbound -LocalPort 5001 -Protocol TCP -Action Allow
New-NetFirewallRule -DisplayName "Glance Dashboard" -Direction Inbound -LocalPort 8090 -Protocol TCP -Action Allow
```

Advanced users can convert the Flask API into a Windows Service via NSSM; the exact commands remain in `docs/windows-autostart.md`.

---

## GPU Optimization

See `docs/gpu-optimization.md` for RTX 5080 defaults, VRAM tables, throughput/context presets, and troubleshooting. The GPU compose overlay is auto-applied when an NVIDIA runtime is detected.

---

## Development Notes

- Code style: `black`, `ruff`
- Lint: `pylint` (scoped to shipped code; extend targets if you want tests linted too)
- Tests: `pytest` (36 passing)
- Packaging: PEP 621 metadata in `project.toml`/`pyproject.toml`; dev extras include `ruff`, `black`, `pylint`, `pytest-cov`, `pip-tools`, `build`.

---

## Changelog (high level)

- CI split into Ruff+pytest and dedicated Pylint workflows; both install from `pyproject.toml`.
- Flask API hardened: clearer logging, rate limits, platform-specific commands, narrowed exception handling.
- `manage_stack.py`: explicit `subprocess.run(check=False)`, docstrings, venv management, GPU auto-detect, configurable flags.
- Docs consolidated under `docs/`; README refreshed.

---

## License

MIT — see `LICENSE`.
