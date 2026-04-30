#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

cleanup() {
    echo ""
    echo "正在停止服务..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    wait $BACKEND_PID 2>/dev/null || true
    wait $FRONTEND_PID 2>/dev/null || true
    echo "已停止。"
    exit 0
}
trap cleanup SIGINT SIGTERM

# Backend
echo "=== 启动后端 (FastAPI :8000) ==="
source .venv/bin/activate
python main.py server --no-browser &
BACKEND_PID=$!

# Wait for backend to be ready
echo "等待后端就绪..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8000/docs > /dev/null 2>&1; then
        break
    fi
    sleep 0.5
done
echo "后端已就绪。"

# Frontend
echo "=== 启动前端 (Vite :5173) ==="
cd frontend
npx vite --host &
FRONTEND_PID=$!

sleep 2
echo ""
echo "=================================="
echo "  后端:  http://localhost:8000"
echo "  前端:  http://localhost:5173"
echo "  按 Ctrl+C 停止所有服务"
echo "=================================="

# Open browser
if command -v open &> /dev/null; then
    open http://localhost:5173
elif command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:5173
fi

wait
