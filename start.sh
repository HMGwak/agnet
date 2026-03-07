#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
DASHBOARD_DIR="$SCRIPT_DIR/dashboard"
SIDECAR_DIR="$SCRIPT_DIR/codex-sidecar"
CODEX_SDK_DIR="$SCRIPT_DIR/.codex-sdk"
CODEX_HOME_DIR="$CODEX_SDK_DIR/home"
CODEX_AUTH_FILE="$CODEX_HOME_DIR/auth.json"
CODEX_CONFIG_FILE="$CODEX_HOME_DIR/config.toml"
VENV_PYTHON=""

ensure_codex_auth() {
  local auth_file="$1"
  local login_script="$2"

  if [ -f "$auth_file" ]; then
    return 0
  fi

  echo "Project-local Codex OAuth login is required."
  echo "Launching login flow..."
  "$login_script"

  if [ ! -f "$auth_file" ]; then
    echo "Codex OAuth login did not create auth.json: $auth_file" >&2
    exit 1
  fi
}

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

echo "Stopping existing processes on ports 8001, 3000 and 8765..."
kill_port 8001
kill_port 3000
kill_port 8765

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

echo "Preparing Codex sidecar dependencies..."
cd "$SIDECAR_DIR"
if [ -f "package-lock.json" ]; then
  if [ ! -d "node_modules" ]; then
    npm ci
  else
    npm install
  fi
else
  npm install
fi

mkdir -p "$CODEX_HOME_DIR"
if [ ! -f "$CODEX_CONFIG_FILE" ]; then
  cat >"$CODEX_CONFIG_FILE" <<'EOF'
cli_auth_credentials_store = "file"
forced_login_method = "chatgpt"
EOF
fi

ensure_codex_auth "$CODEX_AUTH_FILE" "$SCRIPT_DIR/codex-login.sh"

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
echo "Codex auth cache: $CODEX_AUTH_FILE"
echo "Press Ctrl+C to stop"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
