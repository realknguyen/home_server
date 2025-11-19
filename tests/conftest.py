"""
Test configuration and fixtures for the custom API extension.
"""
import pytest
from unittest.mock import patch
import os

# Import the app using a lazy import to avoid module-level import issues
@pytest.fixture
def app():
    """Create the Flask app."""
    from glance.custom_api_extension.host_flask import app
    return app

@pytest.fixture
def app_context(app):
    """Create an application context for testing."""
    with app.app_context() as ctx:
        yield ctx

@pytest.fixture
def client(app):
    """Create a test client for the Flask app."""
    app.config['TESTING'] = True
    app.config['RATELIMIT_ENABLED'] = False  # avoid hitting limiter during most tests
    with app.test_client() as client:
        yield client

@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Ensure rate limits don't leak between tests."""
    from glance.custom_api_extension.host_flask import limiter
    limiter.reset()

@pytest.fixture
def mock_token_env():
    """Mock the environment variable for the token."""
    with patch.dict(os.environ, {'MY_SECRET_TOKEN': 'test_token'}):
        yield

@pytest.fixture
def mock_platform_detection():
    """Mock platform detection for different OS types."""
    # Patch the function where it's looked up (host_flask), otherwise the
    # module-level reference keeps calling the real OS detector.
    with patch('glance.custom_api_extension.host_flask.detect_platform') as mock_detect:
        yield mock_detect

@pytest.fixture
def mock_subprocess():
    """Mock subprocess for command execution."""
    with patch('glance.custom_api_extension.flask_utils.subprocess.run') as mock_run:
        yield mock_run

@pytest.fixture
def mock_distro_import():
    """Mock the distro import for testing."""
    with patch('glance.custom_api_extension.flask_utils.get_distro_id', return_value='ubuntu'):
        yield
