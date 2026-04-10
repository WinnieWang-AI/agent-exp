#!/usr/bin/env python3
"""
Knowledge online monitoring script.

Aggregates knowledge-feedback.yaml from all sessions, accumulates
negative feedback counts per knowledge entry, and auto-deprecates
entries that exceed the negative threshold.

Data flow:
  Session running → Task injects knowledge → writes knowledge-injected.yaml
  Session ends → evolver reads injected + chat.jsonl → writes knowledge-feedback.yaml
  Periodic → THIS SCRIPT aggregates all feedback → updates knowledge status

Usage:
  python scripts/knowledge-monitor.py [--sessions-dir DIR] [--knowledge-dir DIR]
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import yaml


# Negative feedback threshold: if a knowledge entry receives this many
# negative feedbacks, it is automatically deprecated.
NEGATIVE_THRESHOLD = 3

# Minimum total feedback count before making deprecation decisions.
# Avoids deprecating entries based on a single bad session.
MIN_FEEDBACK_COUNT = 3


def load_all_feedback(sessions_dir: Path) -> list[dict]:
    """Load knowledge-feedback.yaml from all sessions."""
    feedback: list[dict] = []
    for f in sessions_dir.glob("*/knowledge-feedback.yaml"):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            if isinstance(data, list):
                feedback.extend(data)
        except Exception as e:
            print(f"Warning: failed to read {f}: {e}", file=sys.stderr)
    return feedback


def aggregate_feedback(feedback: list[dict]) -> dict[str, dict]:
    """Aggregate feedback by knowledge_id.

    Returns dict: knowledge_id -> {
        role, rule,
        positive_count, negative_count, neutral_count,
        total_count, sessions, latest_evidence
    }
    """
    agg: dict[str, dict] = {}

    for fb in feedback:
        kid = fb.get("knowledge_id")
        if not kid:
            continue

        if kid not in agg:
            agg[kid] = {
                "knowledge_id": kid,
                "role": fb.get("role", ""),
                "rule": fb.get("rule", ""),
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0,
                "total_count": 0,
                "sessions": [],
                "latest_evidence": "",
            }

        entry = agg[kid]
        result = fb.get("feedback", "neutral")
        if result == "positive":
            entry["positive_count"] += 1
        elif result == "negative":
            entry["negative_count"] += 1
            entry["latest_evidence"] = fb.get("evidence", "")
        else:
            entry["neutral_count"] += 1

        entry["total_count"] += 1

        session_id = fb.get("session", "")
        if session_id and session_id not in entry["sessions"]:
            entry["sessions"].append(session_id)

    return agg


def load_knowledge_entry(
    knowledge_id: str, role: str, knowledge_dir: Path
) -> tuple[dict | None, Path | None, int | None]:
    """Find a knowledge entry by ID in the knowledge library.

    Searches public/{role}.yaml and users/*/{role}.yaml.
    Returns (entry, file_path, index_in_list) or (None, None, None).
    """
    search_paths = [knowledge_dir / "public" / f"{role}.yaml"]
    users_dir = knowledge_dir / "users"
    if users_dir.exists():
        for user_dir in users_dir.iterdir():
            if user_dir.is_dir():
                search_paths.append(user_dir / f"{role}.yaml")

    for p in search_paths:
        if not p.exists():
            continue
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                continue
            for i, entry in enumerate(data):
                if entry.get("id") == knowledge_id:
                    return entry, p, i
        except Exception:
            continue

    return None, None, None


def deprecate_entry(file_path: Path, index: int) -> None:
    """Set an entry's status to 'deprecated' in its YAML file."""
    try:
        data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        if isinstance(data, list) and 0 <= index < len(data):
            data[index]["status"] = "deprecated"
            file_path.write_text(
                yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
                encoding="utf-8",
            )
    except Exception as e:
        print(f"Error deprecating entry in {file_path}: {e}", file=sys.stderr)


def run_monitor(sessions_dir: Path, knowledge_dir: Path) -> None:
    """Main monitoring logic."""
    print("Loading feedback from all sessions...")
    all_feedback = load_all_feedback(sessions_dir)
    if not all_feedback:
        print("No feedback records found.")
        return

    print(f"Found {len(all_feedback)} feedback records.\n")

    agg = aggregate_feedback(all_feedback)

    deprecated_count = 0
    print(f"{'ID':<25} {'Role':<12} {'+':<4} {'-':<4} {'~':<4} {'Status'}")
    print("-" * 70)

    for kid, stats in sorted(agg.items()):
        pos = stats["positive_count"]
        neg = stats["negative_count"]
        neu = stats["neutral_count"]
        role = stats["role"]
        total = stats["total_count"]

        # Determine action
        action = ""
        if total >= MIN_FEEDBACK_COUNT and neg >= NEGATIVE_THRESHOLD:
            # Auto-deprecate
            entry, fpath, idx = load_knowledge_entry(kid, role, knowledge_dir)
            if entry and fpath is not None and idx is not None:
                current_status = entry.get("status", "")
                if current_status == "online":
                    deprecate_entry(fpath, idx)
                    action = "→ DEPRECATED"
                    deprecated_count += 1
                elif current_status == "deprecated":
                    action = "(already deprecated)"
                else:
                    action = f"(status={current_status}, skip)"
            else:
                action = "(not found in library)"
        elif neg > 0:
            action = f"watching ({neg}/{NEGATIVE_THRESHOLD})"

        print(f"{kid:<25} {role:<12} {pos:<4} {neg:<4} {neu:<4} {action}")

    print(f"\nSummary: {len(agg)} entries tracked, {deprecated_count} newly deprecated.")

    # Write aggregated report
    report_path = knowledge_dir / "monitor-report.yaml"
    report = []
    for kid, stats in sorted(agg.items()):
        report.append({
            "knowledge_id": stats["knowledge_id"],
            "role": stats["role"],
            "rule": stats["rule"],
            "positive_count": stats["positive_count"],
            "negative_count": stats["negative_count"],
            "neutral_count": stats["neutral_count"],
            "total_count": stats["total_count"],
            "session_count": len(stats["sessions"]),
        })

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        yaml.dump(report, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    print(f"Report written to {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Monitor knowledge effectiveness from user feedback"
    )
    parser.add_argument(
        "--sessions-dir", default="output/default/.sessions",
        help="Path to sessions directory",
    )
    parser.add_argument(
        "--knowledge-dir", default="knowledge",
        help="Path to knowledge directory",
    )
    args = parser.parse_args()

    run_monitor(
        sessions_dir=Path(args.sessions_dir),
        knowledge_dir=Path(args.knowledge_dir),
    )


if __name__ == "__main__":
    main()
