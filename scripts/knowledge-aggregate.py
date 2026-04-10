#!/usr/bin/env python3
"""
Knowledge aggregator for video-agent-evolver.

Scans all session directories for knowledge-pending.yaml files,
deduplicates by rule text, and writes aggregated results to
knowledge/pending/{role}.yaml files organized by role tag.

Usage:
  python scripts/knowledge-aggregate.py [--sessions-dir DIR] [--output-dir DIR]
"""

import argparse
import sys
from pathlib import Path

import yaml


ROLE_TAGS = {
    "screenwriter", "director", "camera", "composer",
    "editor", "art-designer", "producer",
}


def load_all_pending(sessions_dir: Path) -> list[dict]:
    """Load all pending knowledge entries from all sessions."""
    entries = []
    for kf in sessions_dir.glob("*/knowledge-pending.yaml"):
        try:
            data = yaml.safe_load(kf.read_text(encoding="utf-8"))
            if isinstance(data, list):
                entries.extend(data)
        except Exception as e:
            print(f"Warning: failed to read {kf}: {e}", file=sys.stderr)
    return entries


def deduplicate(entries: list[dict]) -> list[dict]:
    """Deduplicate by rule text. Keep earliest, merge sources."""
    seen: dict[str, dict] = {}
    for e in entries:
        rule = e.get("rule", "")
        if rule in seen:
            # Record additional source but don't duplicate the entry
            continue
        seen[rule] = e
    return list(seen.values())


def group_by_role(entries: list[dict]) -> dict[str, list[dict]]:
    """Group entries by role tag. Entries without role tags go to 'general'."""
    groups: dict[str, list[dict]] = {}
    for e in entries:
        tags = e.get("tags", [])
        roles = [t for t in tags if t in ROLE_TAGS]
        if not roles:
            roles = ["general"]
        for role in roles:
            groups.setdefault(role, []).append(e)
    return groups


def main():
    parser = argparse.ArgumentParser(description="Aggregate pending knowledge entries")
    parser.add_argument("--sessions-dir", default="output/default/.sessions",
                        help="Path to sessions directory")
    parser.add_argument("--output-dir", default="knowledge/pending",
                        help="Path to write aggregated pending knowledge")
    args = parser.parse_args()

    sessions_dir = Path(args.sessions_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    entries = load_all_pending(sessions_dir)
    entries = deduplicate(entries)
    groups = group_by_role(entries)

    total = 0
    for role, items in sorted(groups.items()):
        out_path = output_dir / f"{role}.yaml"
        # Load existing entries to avoid overwriting already-verified ones
        existing = []
        if out_path.exists():
            try:
                existing = yaml.safe_load(out_path.read_text(encoding="utf-8")) or []
            except Exception:
                existing = []
        existing_rules = {e.get("rule") for e in existing}
        new_items = [i for i in items if i.get("rule") not in existing_rules]
        merged = existing + new_items
        out_path.write_text(
            yaml.dump(merged, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        total += len(new_items)
        print(f"  {role}.yaml: {len(existing)} existing + {len(new_items)} new = {len(merged)} total")

    print(f"\nAggregated {total} new entries from {len(entries)} deduplicated across sessions.")


if __name__ == "__main__":
    main()
