import os
import sys

# Allow running this file directly (python glance/custom_api_extension/host_flask.py)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, request, jsonify
from functools import wraps
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from glance.custom_api_extension.flask_utils import detect_platform, run_command
import logging

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["20 per minute"],  # global fallback
    storage_uri="memory://"  # explicit backend to avoid runtime warnings
)
app.logger.setLevel(logging.INFO)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Support either Authorization header (optionally Bearer) or form/query token
        raw_header = request.headers.get('Authorization', '')
        token = ''
        if raw_header:
            if raw_header.lower().startswith('bearer '):
                token = raw_header.split(' ', 1)[1].strip()
            else:
                token = raw_header.strip()
        if not token:
            token = request.form.get('token') or request.args.get('token')
        if not token:
            return jsonify({'message': 'Token is missing!'}), 403
        valid_token = os.getenv('MY_SECRET_TOKEN', '')
        if token != valid_token:
            return jsonify({'message': 'Invalid token!'}), 403
        return f(*args, **kwargs)
    return decorated

@app.route('/')
@limiter.limit("5 per minute")
def index():
    return 'Hello, World!'

@app.route('/shutdown', methods=['POST'])
@token_required
@limiter.limit("5 per minute")
def shutdown():
    platform_id = detect_platform()
    app.logger.info("Shutdown button pressed on %s", platform_id)
    command = None
    if platform_id.startswith('linux') or platform_id == 'wsl' or platform_id == 'darwin':
        command = 'sudo shutdown -h now'
    elif platform_id == 'windows':
        command = 'shutdown /s /t 0'
    else:
        return jsonify({"message": f"Unsupported platform: {platform_id}"}), 400

    stdout, returncode = run_command(command)
    if returncode != 0:
        return jsonify({"message": "Failed to shut down", "error": stdout.strip()}), 500
    return jsonify({"message": "Shutdown command issued", "platform": platform_id})

@app.route('/restart', methods=['POST'])
@token_required
@limiter.limit("5 per minute")
def restart():
    platform_id = detect_platform()
    app.logger.info("Restart button pressed on %s", platform_id)
    command = None
    if platform_id.startswith('linux') or platform_id == 'wsl' or platform_id == 'darwin':
        command = 'shutdown -r now'
    elif platform_id == 'windows':
        command = 'shutdown /r /t 0'
    else:
        return jsonify({"message": f"Unsupported platform: {platform_id}"}), 400

    stdout, returncode = run_command(command)
    if returncode != 0:
        return jsonify({"message": "Failed to restart", "error": stdout.strip()}), 500
    return jsonify({"message": "Restart command issued", "platform": platform_id})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, load_dotenv=True)
