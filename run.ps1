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

# .env 파일이 있으면 현재 프로세스 환경변수로 로드
$envFile = Join-Path $projectRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#') -and $line -match '=') {
            $parts = $line -split '=', 2
            [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), 'Process')
        }
    }
    Write-Host "[.env] Loaded environment variables from .env"
}

Write-Host "[3/3] Starting API server at http://127.0.0.1:8000"
& $venvPython -m uvicorn server:app --reload
