$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$venvPath = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$venvPip = Join-Path $venvPath "Scripts\pip.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "[1/3] Creating virtual environment..."
    py -3 -m venv $venvPath
}

Write-Host "[2/3] Installing dependencies..."
& $venvPip install -r requirements.txt

Write-Host "[3/3] Starting API server at http://127.0.0.1:8000"
& $venvPython -m uvicorn server:app --reload
