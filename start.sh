#!/bin/bash
echo "Starting AI Dev Automation Dashboard..."

# Backend
cd /home/planee/python/task_manager/backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Frontend
cd /home/planee/python/task_manager/dashboard
npm run dev &
FRONTEND_PID=$!

echo "Backend: http://localhost:8000"
echo "Dashboard: http://localhost:3000"
echo "Press Ctrl+C to stop"

trap "kill $BACKEND_PID $FRONTEND_PID" EXIT
wait
