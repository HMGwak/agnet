#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "Starting AI Dev Automation Dashboard..."

# Backend (uv)
cd "$SCRIPT_DIR/backend"
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Frontend
cd "$SCRIPT_DIR/dashboard"
npm run dev &
FRONTEND_PID=$!

echo "Backend: http://localhost:8000"
echo "Dashboard: http://localhost:3000"
echo "Press Ctrl+C to stop"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
