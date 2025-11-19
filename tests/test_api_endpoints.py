"""
Tests for the custom API extension Flask endpoints.
"""
import pytest
from unittest.mock import MagicMock


def test_index_endpoint(client):
    """Test the index endpoint returns correct response."""
    response = client.get('/')
    assert response.status_code == 200
    assert b'Hello, World!' in response.data


def test_index_rate_limiting_enforced(app, client):
    """Ensure the limiter blocks requests when enabled."""
    app.config['RATELIMIT_ENABLED'] = True
    try:
        for _ in range(5):
            assert client.get('/').status_code == 200
        response = client.get('/')
        assert response.status_code == 429
    finally:
        app.config['RATELIMIT_ENABLED'] = False


def test_shutdown_endpoint_without_token(client):
    """Test shutdown endpoint without token returns 403."""
    response = client.post('/shutdown')
    assert response.status_code == 403
    assert b'Token is missing!' in response.data


def test_shutdown_endpoint_with_invalid_token(client):
    """Test shutdown endpoint with invalid token returns 403."""
    response = client.post('/shutdown', headers={'Authorization': 'Bearer invalid_token'})
    assert response.status_code == 403
    assert b'Invalid token!' in response.data


def test_shutdown_endpoint_with_valid_token(client, mock_token_env, mock_platform_detection, mock_subprocess):
    """Test shutdown endpoint with valid token and successful command execution."""
    mock_platform_detection.return_value = 'linux-ubuntu'
    mock_subprocess.return_value = MagicMock(returncode=0, stdout="Shutdown successful")

    response = client.post('/shutdown', headers={'Authorization': 'Bearer test_token'})
    assert response.status_code == 200
    data = response.get_json()
    assert data['message'] == 'Shutdown command issued'
    assert data['platform'] == 'linux-ubuntu'


def test_shutdown_endpoint_with_invalid_platform(client, mock_token_env, mock_platform_detection):
    """Test shutdown endpoint with unsupported platform."""
    mock_platform_detection.return_value = 'unsupported-platform'

    response = client.post('/shutdown', headers={'Authorization': 'Bearer test_token'})
    assert response.status_code == 400
    data = response.get_json()
    assert 'Unsupported platform' in data['message']


def test_shutdown_endpoint_with_failed_command(client, mock_token_env, mock_platform_detection, mock_subprocess):
    """Test shutdown endpoint with failed command execution."""
    mock_platform_detection.return_value = 'linux-ubuntu'
    mock_subprocess.return_value = MagicMock(returncode=1, stdout="Failed to shutdown")

    response = client.post('/shutdown', headers={'Authorization': 'Bearer test_token'})
    assert response.status_code == 500
    data = response.get_json()
    assert data['message'] == 'Failed to shut down'


def test_restart_endpoint_without_token(client):
    """Test restart endpoint without token returns 403."""
    response = client.post('/restart')
    assert response.status_code == 403
    assert b'Token is missing!' in response.data


def test_restart_endpoint_with_invalid_token(client):
    """Test restart endpoint with invalid token returns 403."""
    response = client.post('/restart', headers={'Authorization': 'Bearer invalid_token'})
    assert response.status_code == 403
    assert b'Invalid token!' in response.data


def test_restart_endpoint_with_valid_token(client, mock_token_env, mock_platform_detection, mock_subprocess):
    """Test restart endpoint with valid token and successful command execution."""
    mock_platform_detection.return_value = 'linux-ubuntu'
    mock_subprocess.return_value = MagicMock(returncode=0, stdout="Restart successful")

    response = client.post('/restart', headers={'Authorization': 'Bearer test_token'})
    assert response.status_code == 200
    data = response.get_json()
    assert data['message'] == 'Restart command issued'
    assert data['platform'] == 'linux-ubuntu'


def test_restart_endpoint_with_invalid_platform(client, mock_token_env, mock_platform_detection):
    """Test restart endpoint with unsupported platform."""
    mock_platform_detection.return_value = 'unsupported-platform'

    response = client.post('/restart', headers={'Authorization': 'Bearer test_token'})
    assert response.status_code == 400
    data = response.get_json()
    assert 'Unsupported platform' in data['message']


def test_restart_endpoint_with_failed_command(client, mock_token_env, mock_platform_detection, mock_subprocess):
    """Test restart endpoint with failed command execution."""
    mock_platform_detection.return_value = 'linux-ubuntu'
    mock_subprocess.return_value = MagicMock(returncode=1, stdout="Failed to restart")

    response = client.post('/restart', headers={'Authorization': 'Bearer test_token'})
    assert response.status_code == 500
    data = response.get_json()
    assert data['message'] == 'Failed to restart'


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {"headers": {'Authorization': 'Bearer test_token'}},
        {"data": {'token': 'test_token'}},
        {"query_string": {'token': 'test_token'}},
    ],
)
def test_shutdown_endpoint_accepts_multiple_token_sources(client, mock_token_env, mock_platform_detection, mock_subprocess, request_kwargs):
    """Ensure token_required accepts header, form, and query tokens."""
    mock_platform_detection.return_value = 'linux-ubuntu'
    mock_subprocess.return_value = MagicMock(returncode=0, stdout="Shutdown successful")

    response = client.post('/shutdown', **request_kwargs)
    assert response.status_code == 200


@pytest.mark.parametrize("auth_header", ["Bearer test_token", "test_token"])
def test_shutdown_endpoint_accepts_authorization_header_formats(client, mock_token_env, mock_platform_detection, mock_subprocess, auth_header):
    """Support Bearer-prefixed and raw Authorization headers."""
    mock_platform_detection.return_value = 'linux-ubuntu'
    mock_subprocess.return_value = MagicMock(returncode=0, stdout="Shutdown successful")

    response = client.post('/shutdown', headers={'Authorization': auth_header})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "platform_id,expected_command",
    [
        ("linux-ubuntu", "sudo shutdown -h now"),
        ("wsl", "sudo shutdown -h now"),
        ("darwin", "sudo shutdown -h now"),
        ("windows", "shutdown /s /t 0"),
    ],
)
def test_shutdown_endpoint_invokes_platform_specific_command(client, mock_token_env, mock_platform_detection, mock_subprocess, platform_id, expected_command):
    """Verify shutdown command sent to subprocess matches the platform."""
    mock_platform_detection.return_value = platform_id
    mock_subprocess.return_value = MagicMock(returncode=0, stdout="Shutdown successful")

    response = client.post('/shutdown', headers={'Authorization': 'Bearer test_token'})
    assert response.status_code == 200

    mock_subprocess.assert_called_once()
    called_command = mock_subprocess.call_args.args[0]
    assert called_command == expected_command


@pytest.mark.parametrize(
    "platform_id,expected_command",
    [
        ("linux-ubuntu", "shutdown -r now"),
        ("wsl", "shutdown -r now"),
        ("darwin", "shutdown -r now"),
        ("windows", "shutdown /r /t 0"),
    ],
)
def test_restart_endpoint_invokes_platform_specific_command(client, mock_token_env, mock_platform_detection, mock_subprocess, platform_id, expected_command):
    """Verify restart command sent to subprocess matches the platform."""
    mock_platform_detection.return_value = platform_id
    mock_subprocess.return_value = MagicMock(returncode=0, stdout="Restart successful")

    response = client.post('/restart', headers={'Authorization': 'Bearer test_token'})
    assert response.status_code == 200

    mock_subprocess.assert_called_once()
    called_command = mock_subprocess.call_args.args[0]
    assert called_command == expected_command
