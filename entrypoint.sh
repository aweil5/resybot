#!/bin/bash
set -e

echo "=============================================="
echo "  RESYBOT - Starting"
echo "=============================================="

# Run verification
echo "[STARTUP] Running verification..."
if ! uv run python scripts/verify.py; then
    echo "[STARTUP] Verification failed"
    exit 1
fi

echo "[STARTUP] Starting bot..."
exec uv run python scripts/run.py
