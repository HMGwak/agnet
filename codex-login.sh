#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_CODEX_HOME="$SCRIPT_DIR/.codex"

mkdir -p "$PROJECT_CODEX_HOME"
if [ ! -f "$PROJECT_CODEX_HOME/auth.json" ] && [ -f "$HOME/.codex/auth.json" ] && [ "$PROJECT_CODEX_HOME" != "$HOME/.codex" ]; then
  cp "$HOME/.codex/auth.json" "$PROJECT_CODEX_HOME/auth.json"
fi

export CODEX_HOME="$PROJECT_CODEX_HOME"
echo "Using project Codex home: $CODEX_HOME"
exec codex login
