#!/usr/bin/env bash
#
# Bug report generator.
#
# Scans all session directories for bugs.yaml, generates:
#   1. Daily report (today's bugs only)
#   2. Full report (all bugs across all sessions)
#
# Usage:
#   bash scripts/bug-report.sh [--sessions-dir DIR] [--output-dir DIR] [--date YYYY-MM-DD]
#
# Dependencies: python3, pyyaml

set -euo pipefail

SESSIONS_DIR="output/default/.sessions"
OUTPUT_DIR="reports/bugs"
TARGET_DATE="$(date +%Y-%m-%d)"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --sessions-dir) SESSIONS_DIR="$2"; shift 2 ;;
        --output-dir)   OUTPUT_DIR="$2";   shift 2 ;;
        --date)         TARGET_DATE="$2";  shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

mkdir -p "$OUTPUT_DIR"

python3 - "$SESSIONS_DIR" "$OUTPUT_DIR" "$TARGET_DATE" << 'PYEOF'
import sys
from pathlib import Path
from datetime import datetime

import yaml

sessions_dir = Path(sys.argv[1])
output_dir = Path(sys.argv[2])
target_date = sys.argv[3]

# ---------------------------------------------------------------------------
# Load all bugs from all sessions
# ---------------------------------------------------------------------------

all_bugs: list[dict] = []

for bugs_file in sorted(sessions_dir.glob("*/bugs.yaml")):
    try:
        data = yaml.safe_load(bugs_file.read_text(encoding="utf-8"))
        if isinstance(data, list):
            all_bugs.extend(data)
    except Exception as e:
        print(f"Warning: failed to read {bugs_file}: {e}", file=sys.stderr)

if not all_bugs:
    print("No bugs found.")
    # Write empty reports
    (output_dir / f"daily-{target_date}.md").write_text(
        f"# Bug Daily Report — {target_date}\n\nNo bugs found.\n", encoding="utf-8"
    )
    (output_dir / "full-report.md").write_text(
        "# Bug Full Report\n\nNo bugs found.\n", encoding="utf-8"
    )
    sys.exit(0)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fmt_bug(b: dict, idx: int) -> str:
    """Format a single bug entry as markdown."""
    bid = b.get("id", f"bug_{idx}")
    desc = b.get("description", "(no description)")
    user_inst = b.get("user_instruction", "")
    sys_out = b.get("system_output", "")
    source = b.get("source", {})
    session = source.get("session", "unknown")
    extracted = source.get("extracted_at", "")

    lines = [f"### {bid}", "", f"**Description**: {desc}", ""]
    if user_inst:
        lines += [f"**User instruction**: {user_inst}", ""]
    if sys_out:
        lines += [f"**System output**: {sys_out}", ""]
    lines += [f"**Session**: `{session}`  **Extracted**: {extracted}", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Daily report
# ---------------------------------------------------------------------------

today_bugs = [
    b for b in all_bugs
    if b.get("source", {}).get("extracted_at", "") == target_date
]

daily_lines = [
    f"# Bug Daily Report — {target_date}",
    "",
    f"Total: **{len(today_bugs)}** bugs extracted today.",
    "",
]

if today_bugs:
    for i, b in enumerate(today_bugs, 1):
        daily_lines.append(fmt_bug(b, i))
else:
    daily_lines.append("No new bugs today.")

daily_path = output_dir / f"daily-{target_date}.md"
daily_path.write_text("\n".join(daily_lines), encoding="utf-8")
print(f"Daily report: {daily_path} ({len(today_bugs)} bugs)")

# ---------------------------------------------------------------------------
# Full report
# ---------------------------------------------------------------------------

# Group by session
by_session: dict[str, list[dict]] = {}
for b in all_bugs:
    sid = b.get("source", {}).get("session", "unknown")
    by_session.setdefault(sid, []).append(b)

# Sort sessions by earliest extracted_at
def session_sort_key(sid: str) -> str:
    dates = [
        b.get("source", {}).get("extracted_at", "9999")
        for b in by_session[sid]
    ]
    return min(dates)

full_lines = [
    "# Bug Full Report",
    "",
    f"Generated: {target_date}",
    "",
    f"Total: **{len(all_bugs)}** bugs across **{len(by_session)}** sessions.",
    "",
    "---",
    "",
]

for sid in sorted(by_session, key=session_sort_key):
    bugs = by_session[sid]
    full_lines += [f"## Session `{sid}` ({len(bugs)} bugs)", ""]
    for i, b in enumerate(bugs, 1):
        full_lines.append(fmt_bug(b, i))
    full_lines.append("---\n")

full_path = output_dir / "full-report.md"
full_path.write_text("\n".join(full_lines), encoding="utf-8")
print(f"Full report:  {full_path} ({len(all_bugs)} bugs, {len(by_session)} sessions)")
PYEOF
