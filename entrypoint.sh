#!/bin/bash
set -e

SERVER_HOST="${SERVER_HOST:-127.0.0.1}"
SERVER_PORT="${SERVER_PORT:-8000}"

echo "=============================================="
echo "  RESYBOT - Starting"
echo "=============================================="

# Start FastAPI server
echo "[STARTUP] Starting server on port ${SERVER_PORT}..."
uv run uvicorn src.server.main:app --host 0.0.0.0 --port ${SERVER_PORT} &
SERVER_PID=$!

# Wait for server health
echo "[STARTUP] Waiting for server..."
for i in {1..30}; do
    if curl -s -f "http://${SERVER_HOST}:${SERVER_PORT}/" > /dev/null 2>&1; then
        echo "[STARTUP] Server ready"
        break
    fi
    sleep 2
done

# Run verification
echo "[STARTUP] Running verification..."
if ! uv run python scripts/verify.py; then
    echo "[STARTUP] Verification failed"
    kill $SERVER_PID 2>/dev/null || true
    exit 1
fi

echo "[STARTUP] Starting bot..."
exec uv run python scripts/run.py
