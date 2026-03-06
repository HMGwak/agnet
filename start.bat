@echo off
echo Starting AI Dev Automation Dashboard...

set SCRIPT_DIR=%~dp0

:: Backend (uv)
start "Backend" cmd /c "cd /d %SCRIPT_DIR%backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"

:: Frontend
start "Dashboard" cmd /c "cd /d %SCRIPT_DIR%dashboard && npm run dev"

echo.
echo Backend:   http://localhost:8000
echo Dashboard: http://localhost:3000
echo.
echo Close the Backend / Dashboard windows to stop.
pause
