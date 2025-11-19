# Set the script's directory as the current location
Set-Location $PSScriptRoot

Write-Host "Starting Docker Compose stack..."
docker compose up -d

if ($LASTEXITCODE -eq 0) {
    Write-Host "Docker Compose started successfully."
    
    # Locate Python executable
    $VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    $PythonExe = "python"
    
    if (Test-Path $VenvPython) {
        $PythonExe = $VenvPython
        Write-Host "Using virtual environment Python: $PythonExe"
    } else {
        Write-Host "Virtual environment not found, using system Python."
    }

    # Install dependencies
    Write-Host "Installing dependencies from project.toml..."
    & $PythonExe -m pip install .[dev]
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Dependency installation failed. Attempting to proceed anyway..."
    }

    # Path to the Flask app entry point
    $FlaskApp = Join-Path $PSScriptRoot "glance\custom_api_extension\host_flask.py"

    if (Test-Path $FlaskApp) {
        Write-Host "Starting Flask server..."
        & $PythonExe $FlaskApp
    } else {
        Write-Error "Flask application file not found at: $FlaskApp"
        exit 1
    }
} else {
    Write-Error "Failed to start Docker Compose. Exiting."
    exit $LASTEXITCODE
}
