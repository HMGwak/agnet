#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SIDECAR_DIR="$REPO_DIR/runtime/codex/sidecar"
CODEX_HOME_DIR="$REPO_DIR/project/codex-home"
APPDATA_DIR="$CODEX_HOME_DIR/AppData/Roaming"
LOCALAPPDATA_DIR="$CODEX_HOME_DIR/AppData/Local"
CONFIG_FILE="$CODEX_HOME_DIR/config.toml"
CODEX_BIN="$SIDECAR_DIR/node_modules/.bin/codex"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is not installed or not on PATH." >&2
  exit 1
fi

cd "$SIDECAR_DIR"
if [ ! -d "node_modules" ]; then
  npm install
fi

mkdir -p "$APPDATA_DIR" "$LOCALAPPDATA_DIR"
cat >"$CONFIG_FILE" <<'EOF'
cli_auth_credentials_store = "file"
forced_login_method = "chatgpt"
EOF

if [ ! -x "$CODEX_BIN" ] && [ -x "$SIDECAR_DIR/node_modules/.bin/codex.cmd" ]; then
  CODEX_BIN="$SIDECAR_DIR/node_modules/.bin/codex.cmd"
fi

if [ ! -e "$CODEX_BIN" ]; then
  echo "Local Codex runtime not found under $SIDECAR_DIR/node_modules/.bin" >&2
  exit 1
fi

HOME="$CODEX_HOME_DIR" \
USERPROFILE="$CODEX_HOME_DIR" \
APPDATA="$APPDATA_DIR" \
LOCALAPPDATA="$LOCALAPPDATA_DIR" \
CODEX_HOME="$CODEX_HOME_DIR" \
OPENAI_API_KEY="" \
CODEX_API_KEY="" \
OPENAI_BASE_URL="" \
"$CODEX_BIN" login --device-auth

if [ ! -f "$CODEX_HOME_DIR/auth.json" ]; then
  echo "Codex OAuth login did not create auth.json under $CODEX_HOME_DIR" >&2
  exit 1
fi

echo "Project-local Codex OAuth login complete: $CODEX_HOME_DIR/auth.json"
