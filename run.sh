#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Load env
if [ -f "$SCRIPT_DIR/env.sh" ]; then
    source "$SCRIPT_DIR/env.sh"
fi

# Default: reproduce killbill.mp4
VIDEO="${1:-video_sample/killbill.mp4}"
PROJECT="${2:-killbill_repro}"

echo "========================================="
echo "  Video Auto-Eval"
echo "  Video:   $VIDEO"
echo "  Project: output/$PROJECT"
echo "========================================="
echo ""

PYTHONPATH="src:$PYTHONPATH" exec kimi --agent video-auto-eval --yolo \
    -p "请复现视频 ${VIDEO}，项目名为 ${PROJECT}"
