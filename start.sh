#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
DASHBOARD_DIR="$SCRIPT_DIR/dashboard"
VENV_PYTHON=""

kill_port() {
  local port="$1"

  if command -v lsof >/dev/null 2>&1; then
    lsof -ti tcp:"$port" | xargs -r kill -9
    return 0
  fi

  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" >/dev/null 2>&1 || true
    return 0
  fi

  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command "\$ids = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique); if (\$ids.Count -gt 0) { Stop-Process -Id \$ids -Force -ErrorAction SilentlyContinue }" >/dev/null
    return 0
  fi

  echo "Could not stop existing process on port $port automatically." >&2
  return 1
}

echo "Starting AI Dev Automation Dashboard..."

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed or not on PATH." >&2
  echo "Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is not installed or not on PATH." >&2
  echo "Install Node.js LTS and reopen the terminal." >&2
  exit 1
fi

echo "Stopping existing processes on ports 8001 and 3000..."
kill_port 8001
kill_port 3000

# Backend (.venv Python managed by uv)
cd "$BACKEND_DIR"
uv sync --extra dev

if [ -x "$BACKEND_DIR/.venv/bin/python" ]; then
  VENV_PYTHON="$BACKEND_DIR/.venv/bin/python"
elif [ -x "$BACKEND_DIR/.venv/Scripts/python.exe" ]; then
  VENV_PYTHON="$BACKEND_DIR/.venv/Scripts/python.exe"
else
  echo "Expected virtual environment Python was not created under $BACKEND_DIR/.venv" >&2
  exit 1
fi

echo "Preparing dashboard dependencies..."
cd "$DASHBOARD_DIR"
if [ -f "package-lock.json" ]; then
  if [ ! -d "node_modules" ]; then
    npm ci
  else
    npm install
  fi
else
  npm install
fi

cd "$BACKEND_DIR"
"$VENV_PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port 8001 &
BACKEND_PID=$!

# Frontend
cd "$DASHBOARD_DIR"
npm run dev &
FRONTEND_PID=$!

echo "Backend: http://localhost:8001"
echo "Dashboard: http://localhost:3000"
echo "Backend Python: $VENV_PYTHON"
echo "Press Ctrl+C to stop"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
