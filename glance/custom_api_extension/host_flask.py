"""Flask application for host control API.

This module provides authenticated endpoints for shutting down and restarting
the host system. It includes CORS support, rate limiting, and logging.
"""

import logging
import os
import re
import sys
from functools import wraps
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

try:
    from glance.custom_api_extension.flask_utils import detect_platform, run_command
except ImportError:  # pragma: no cover
    # Fallback for running this file directly without installing the package.
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    from glance.custom_api_extension.flask_utils import detect_platform, run_command


# ============================================================================
# Logging Configuration
# ============================================================================


class NoColorFormatter(logging.Formatter):
    """Custom formatter that strips ANSI color codes from log messages."""

    ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    def format(self, record):
        """Format the log record and remove ANSI escape sequences."""
        message = super().format(record)
        return self.ANSI_ESCAPE.sub("", message)


def configure_logging():
    """Configure file and console logging handlers."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # File handler (no colors)
    log_dir = os.path.join(os.path.dirname(__file__), "..", "..")
    log_file = os.path.join(log_dir, "host_flask.log")
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=3  # 10MB
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(NoColorFormatter(log_format))

    # Console handler (with colors)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))

    # Configure root logger
    logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])


configure_logging()


# ============================================================================
# Flask Application Setup
# ============================================================================

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# CORS configuration for Private Network Access (Chrome)
CORS(
    app,
    resources={
        r"/*": {
            "origins": "*",
            "allow_headers": ["Content-Type", "Authorization"],
            "expose_headers": ["Access-Control-Allow-Private-Network"],
            "supports_credentials": False,
        }
    },
)

# Rate limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["20 per minute"],
    storage_uri="memory://",
)


# ============================================================================
# Middleware
# ============================================================================


@app.after_request
def add_private_network_header(response):
    """Add Private Network Access header for Chrome compatibility."""
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


def token_required(f):
    """Decorator to validate authentication token.

    Supports token in:
    - Authorization header (with or without 'Bearer ' prefix)
    - Form data (token field)
    - Query parameter (token field)
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token_from_request()

        if not token:
            return jsonify({"message": "Token is missing!"}), 403

        valid_token = os.getenv("MY_SECRET_TOKEN", "")
        if token != valid_token:
            return jsonify({"message": "Invalid token!"}), 403

        return f(*args, **kwargs)

    return decorated


def _extract_token_from_request():
    """Extract authentication token from request."""
    # Try Authorization header first
    auth_header = request.headers.get("Authorization", "")
    if auth_header:
        if auth_header.lower().startswith("bearer "):
            return auth_header.split(" ", 1)[1].strip()
        return auth_header.strip()

    # Fall back to form data or query params
    return request.form.get("token") or request.args.get("token")


# ============================================================================
# Helper Functions
# ============================================================================


def _stop_docker_compose():
    """Stop Docker Compose stack gracefully.

    Returns:
        bool: True if successful, False otherwise
    """
    app.logger.info("Stopping Docker Compose stack...")
    stdout, returncode = run_command("docker compose down")

    if returncode != 0:
        app.logger.warning("Failed to stop Docker Compose: %s", stdout.strip())
        return False

    app.logger.info("Docker Compose stopped successfully")
    return True


def _get_shutdown_command(platform_id):
    """Get the appropriate shutdown command for the platform.

    Args:
        platform_id: Platform identifier from detect_platform()

    Returns:
        str or None: Shutdown command, or None if unsupported
    """
    if platform_id in ("linux", "wsl", "darwin") or platform_id.startswith("linux"):
        return "sudo shutdown -h now"
    if platform_id == "windows":
        # /s = shutdown, /f = force close apps, /t 0 = immediate
        return "shutdown /s /f /t 0"
    return None


def _get_restart_command(platform_id):
    """Get the appropriate restart command for the platform.

    Args:
        platform_id: Platform identifier from detect_platform()

    Returns:
        str or None: Restart command, or None if unsupported
    """
    if platform_id in ("linux", "wsl", "darwin") or platform_id.startswith("linux"):
        return "shutdown -r now"
    if platform_id == "windows":
        # /r = restart, /f = force close apps, /t 0 = immediate
        return "shutdown /r /f /t 0"
    return None


# ============================================================================
# API Routes
# ============================================================================


@app.route("/")
@limiter.limit("5 per minute")
def index():
    """Simple health check endpoint."""
    return "Hello, World!"


@app.route("/shutdown", methods=["POST"])
@token_required
@limiter.limit("5 per minute")
def shutdown():
    """Shutdown the host system.

    Note: For production use, consider adding docker compose down before
    shutdown to gracefully stop containers. This is omitted here to keep
    the function focused and testable.
    """
    platform_id = detect_platform()
    app.logger.info("Shutdown requested for platform: %s", platform_id)

    # Get and execute shutdown command
    command = _get_shutdown_command(platform_id)
    if not command:
        app.logger.error("Unsupported platform: %s", platform_id)
        return jsonify({"message": f"Unsupported platform: {platform_id}"}), 400
    
    if _stop_docker_compose():
        app.logger.info("Docker Compose stack stopped successfully")
    else:
        app.logger.error("Proceeding with shutdown despite Docker Compose stop failure")

    stdout, returncode = run_command(command)
    if returncode != 0:
        app.logger.error("Shutdown failed: %s", stdout.strip())
        return jsonify({"message": "Failed to shut down", "error": stdout.strip()}), 500

    app.logger.info("Shutdown command issued successfully")
    return jsonify({"message": "Shutdown command issued", "platform": platform_id})


@app.route("/restart", methods=["POST"])
@token_required
@limiter.limit("5 per minute")
def restart():
    """Restart the host system.

    Note: For production use, consider adding docker compose down before
    restart to gracefully stop containers. This is omitted here to keep
    the function focused and testable.
    """
    platform_id = detect_platform()
    app.logger.info("Restart requested for platform: %s", platform_id)

    # Get and execute restart command
    command = _get_restart_command(platform_id)
    if not command:
        app.logger.error("Unsupported platform: %s", platform_id)
        return jsonify({"message": f"Unsupported platform: {platform_id}"}), 400

    if _stop_docker_compose():
        app.logger.info("Docker Compose stack stopped successfully")
    else:
        app.logger.error("Proceeding with shutdown despite Docker Compose stop failure")

    stdout, returncode = run_command(command)
    if returncode != 0:
        app.logger.error("Restart failed: %s", stdout.strip())
        return jsonify({"message": "Failed to restart", "error": stdout.strip()}), 500

    app.logger.info("Restart command issued successfully")
    return jsonify({"message": "Restart command issued", "platform": platform_id})


# ============================================================================
# Application Entry Point
# ============================================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, load_dotenv=True)
