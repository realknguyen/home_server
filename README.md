# Local LLM Home Stack

This repository contains everything needed to stand up a privacy-friendly home lab for large language models and personal search. It combines reproducible Docker services (Ollama, Open WebUI, SearxNG, and Glance), opinionated Glance configuration, and a small Flask extension that lets you send authenticated shutdown/restart commands to the host directly from the dashboard. The Python code is fully covered by tests so you can evolve the automation safely.

---

## At a Glance

| Component | Location | Purpose |
| --------- | -------- | ------- |
| Docker stack | `docker-compose.yml` | Boots Ollama (models), Open WebUI (chat UI), Glance (dashboard), and SearxNG (meta search). |
| Dashboard config | `glance/config`, `glance/assets` | Home page layouts, widgets, and CSS overrides for Glance. |
| Custom API extension | `glance/custom_api_extension` | Flask service that Glance calls to restart or power down the host with per-platform commands and rate limiting. |
| Persistent data | `data/` | Docker bind mounts for Ollama models, Open WebUI, and SearxNG. Ignored from Git to keep the repo lean. |
| Automated tests | `tests/` | Pytest suite validating every Flask endpoint, the token guard, rate limiting, and OS detection helpers. |

---

## Requirements

| Category | Details |
| -------- | ------- |
| Host OS | Linux or Windows with WSL2 (compose file is tuned for WSL GPU passthrough). |
| Containers | Docker 24+ and Docker Compose plugin. NVIDIA Container Toolkit if you want GPU acceleration. |
| Python tooling | Python 3.11+ plus `pip` for running/tests of the Flask extension. |
| Secrets | `.env` file defining at least `MY_SECRET_TOKEN` (shared between Glance and the Flask app) and `MY_PASSWORD` (hashed password for the Glance UI). |

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

3. **Provision Python tooling (optional but recommended for working on the Flask API)**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r glance/custom_api_extension/requirements.txt
   # or, if your tooling reads `project.toml` (or a copy named `pyproject.toml`):
   pip install -e .[dev]
   ```

4. **Launch the container stack**

   ```bash
   docker compose up -d
   ```

   | Service | URL | Notes |
   | ------- | --- | ----- |
   | Ollama | `http://localhost:11434` | Model runtime and embedding server. |
   | Open WebUI | `http://localhost:8081` | Web UI proxied to Ollama, RAG enabled via FAISS. |
   | Glance | `http://localhost:8080` | Dashboard configured by `glance/config`. |
   | SearxNG | `http://localhost:8082` | Self-hosted metasearch for RAG or manual queries. |

   Health checks on Ollama gate Open WebUI startup. GPU passthrough is enabled by default through `deploy.resources`.

---

## Custom Flask API Extension

Located in `glance/custom_api_extension`, this mini-service exposes authenticated endpoints that Glance widgets can call to control the host.

### Running Locally

```bash
source .venv/bin/activate
export FLASK_APP=glance.custom_api_extension.host_flask
export MY_SECRET_TOKEN=change-me
python -m flask run --host=0.0.0.0 --port=5001
```

* Rate limiting: default limit is `5 per minute` per IP enforced by `flask-limiter`.
* Auth: `token_required` accepts `Authorization: Bearer <token>`, `Authorization: <token>`, `token` form fields, or `?token=` query params.

### Endpoints

| Route | Method | Description | Platform-specific behavior |
| ----- | ------ | ----------- | -------------------------- |
| `/` | GET | Health check returning `Hello, World!`. Protected by the rate limiter. | – |
| `/shutdown` | POST | Issues `sudo shutdown -h now`, `shutdown /s /t 0`, or equivalent depending on OS. | Linux/WSL/macOS use `sudo shutdown -h now`; Windows uses `shutdown /s /t 0`; unsupported platforms return HTTP 400. |
| `/restart` | POST | Issues safe restart command for the active platform. | Linux/WSL/macOS use `shutdown -r now`; Windows uses `shutdown /r /t 0`. |

Commands are executed via `run_command()` which captures output and surfaces failures with HTTP 500 responses plus stderr payloads. Platform detection logic leans on `platform`, `distro.id`, and heuristics for WSL to keep commands accurate.

---

## Configuration Reference

| File/Dir | Purpose |
| -------- | ------- |
| `glance/config/glance.yml` | Registers pages, auth strategy, and proxies dashboard env vars from `.env`. |
| `glance/config/home.yml` / `startpage.yml` | Widget layout, RSS feeds, weather, markets, Twitch, and utility groups. Use them as templates for additional pages. |
| `glance/assets/user.css` | Brand the dashboard. Clear your browser cache (Ctrl+F5) after editing due to caching. |
| `config/searxng-config` | Passed-through config directory for SearxNG container. |
| `data/<service>` | Docker bind mounts that retain models, indexes, and user data between restarts. |

Feel free to add more compose services (e.g., `qdrant`, `postgres`) – just extend `docker-compose.yml` and Glance labels for discovery.

---

## Testing & Quality

* **Unit tests**: Run `pytest` from the repo root. The suite (36 tests) covers endpoint auth flows, rate limiting, platform branching, and subprocess error handling.
* **Formatting**: `black` keeps code style consistent (`black .`).
* **Linting**: `ruff` (optional) catches import order and logical issues early (`ruff check .`).

CI is not bundled, but the commands above are what the project expects before pushing changes.

---

## Maintenance & Troubleshooting

| Issue | Fix |
| ----- | --- |
| Rate limiter blocking tests | The default pytest client fixture disables the limiter; toggle `app.config['RATELIMIT_ENABLED'] = True` inside a test to cover limiter behavior (see `tests/test_api_endpoints.py:test_index_rate_limiting_enforced`). |
| Permission errors on shutdown/restart | Ensure the user that runs the Flask API has sudo rights without a password prompt or adjust `run_command` to call privileged helper scripts. |
| GPU not visible inside Ollama container | Install the NVIDIA Container Toolkit and verify `docker info | grep -i nvidia` before starting the stack. |
| Glance auth failing | Regenerate `MY_PASSWORD` hash with Werkzeug and keep `MY_SECRET_TOKEN` identical across `.env` and any widgets hitting the Flask API. |

---

## Contributing

1. Fork and branch from `main`.
2. Run `pip install -e .[dev]` and `pytest` before committing.
3. Follow the conventions in `tests/` when adding Flask endpoints: write fixtures, mock external systems, and assert command invocations explicitly.
4. Open a pull request with a summary of Docker/service changes plus any dashboard screenshots if UI changes are involved.

---

## License

Licensed under the MIT License. See [`LICENSE`](LICENSE) for the full text.
