#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PORT="${PORT:-8080}"
HOST="${HOST:-0.0.0.0}"

cd "$PROJECT_ROOT"

# Source env.sh to get Nacos/Statsig credentials
if [ -f "$PROJECT_ROOT/env.sh" ]; then
    echo "[*] Loading env.sh ..."
    source "$PROJECT_ROOT/env.sh"
fi

# Check dependencies
python -c "import fastapi, uvicorn" 2>/dev/null || {
    echo "[*] Installing dependencies: fastapi uvicorn..."
    pip install fastapi uvicorn
}

echo ""
echo "========================================="
echo "  Video Agent Studio"
echo "  http://${HOST}:${PORT}"
echo "========================================="
echo ""
echo "Tabs:"
echo "  - Video Director:   chat directly with the director agent"
echo "  - Auto Evaluator:   chat directly with the auto-eval agent"
echo "  - Auto Interaction: watch auto-eval drive director autonomously"
echo ""

PYTHONPATH="src:$PYTHONPATH" exec python -m uvicorn web.server:app \
    --host "$HOST" \
    --port "$PORT" \
    --reload \
    --reload-dir web
