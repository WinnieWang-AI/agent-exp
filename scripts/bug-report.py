#!/usr/bin/env python3
"""
Bug report generator for video-agent-evolver.

Scans all session directories for bugs.yaml files, aggregates bug records,
and generates two reports:
  1. Daily report: bugs from the last 24 hours
  2. Full report: all unresolved bugs with frequency counts

Usage:
  python scripts/bug-report.py [--output-dir DIR] [--sessions-dir DIR]

Output:
  {output-dir}/bug-report-daily-{date}.md
  {output-dir}/bug-report-full-{date}.md
"""

import argparse
import datetime
import sys
from collections import Counter
from pathlib import Path

import yaml


def load_all_bugs(sessions_dir: Path) -> list[dict]:
    """Load all bug records from all sessions."""
    bugs = []
    for bugs_file in sessions_dir.glob("*/bugs.yaml"):
        try:
            data = yaml.safe_load(bugs_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                bugs.extend(data)
        except Exception as e:
            print(f"Warning: failed to read {bugs_file}: {e}", file=sys.stderr)
    return bugs


def generate_daily_report(bugs: list[dict], date: str) -> str:
    """Generate report for bugs extracted on a specific date."""
    daily = [b for b in bugs if b.get("source", {}).get("extracted_at") == date]
    lines = [
        f"# Bug Daily Report — {date}",
        "",
        f"New bugs: **{len(daily)}**",
        "",
    ]
    if daily:
        lines.append("| # | Description | Session |")
        lines.append("|---|-------------|---------|")
        for i, b in enumerate(daily, 1):
            desc = b.get("description", "")
            session = b.get("source", {}).get("session", "")[:8]
            lines.append(f"| {i} | {desc} | {session} |")
    else:
        lines.append("No new bugs.")
    return "\n".join(lines) + "\n"


def generate_full_report(bugs: list[dict], date: str) -> str:
    """Generate full unresolved bug report with frequency counts."""
    # Count by description (each occurrence counts independently)
    desc_counter = Counter(b.get("description", "") for b in bugs)
    sorted_descs = desc_counter.most_common()

    lines = [
        f"# Bug Full Report — {date}",
        "",
        f"Total bug occurrences: **{len(bugs)}**",
        f"Unique bug descriptions: **{len(sorted_descs)}**",
        "",
        "| # | Count | Description |",
        "|---|-------|-------------|",
    ]
    for i, (desc, count) in enumerate(sorted_descs, 1):
        lines.append(f"| {i} | {count} | {desc} |")

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Generate bug reports from evolver analysis")
    parser.add_argument("--sessions-dir", default="output/default/.sessions",
                        help="Path to sessions directory")
    parser.add_argument("--output-dir", default="output/reports",
                        help="Path to write reports")
    args = parser.parse_args()

    sessions_dir = Path(args.sessions_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.date.today().isoformat()

    bugs = load_all_bugs(sessions_dir)

    daily = generate_daily_report(bugs, today)
    full = generate_full_report(bugs, today)

    daily_path = output_dir / f"bug-report-daily-{today}.md"
    full_path = output_dir / f"bug-report-full-{today}.md"

    daily_path.write_text(daily, encoding="utf-8")
    full_path.write_text(full, encoding="utf-8")

    print(f"Daily report: {daily_path}")
    print(f"Full report:  {full_path}")
    print(f"Total bugs: {len(bugs)}, today: {sum(1 for b in bugs if b.get('source', {}).get('extracted_at') == today)}")


if __name__ == "__main__":
    main()
