@echo off
setlocal

set "ROOT=%~dp0"
cd /d "%ROOT%"

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating virtual environment...
    py -3 -m venv .venv
)

echo [2/3] Installing dependencies...
".venv\Scripts\pip.exe" install -r requirements.txt
if errorlevel 1 exit /b 1

echo [3/3] Starting API server at http://127.0.0.1:8000
".venv\Scripts\python.exe" -m uvicorn server:app --reload
