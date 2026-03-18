"""Pre-write validation for JSON files.

Provides syntax checking for all .json files and structural validation
for known schemas (e.g. story-graph.json).  If validation fails the
caller should reject the write and return the ToolError to the agent.
"""

from __future__ import annotations

import json
from pathlib import Path

from kosong.tooling import ToolError


def validate_json_before_write(file_path: str, content: str) -> ToolError | None:
    """Validate *content* before it is written to *file_path*.

    Returns a ``ToolError`` if the content is invalid, or ``None`` if it is safe
    to proceed with the write.
    """
    if not file_path.endswith(".json"):
        return None

    # --- 1. Syntax check (all JSON files) ---
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return ToolError(
            message=(
                f"Write rejected: the result is not valid JSON ({e}). "
                f"The file was NOT modified. Please check your content."
            ),
            brief="Invalid JSON",
        )

    # --- 2. Structural checks for known schemas ---
    basename = Path(file_path).name

    if basename == "story-graph.json":
        return _validate_story_graph(data, file_path)

    return None


def _validate_story_graph(data: dict, file_path: str) -> ToolError | None:
    """Run structural validation on a story-graph.json before writing."""
    # Lazy import to avoid circular dependency at module level.
    from kimi_cli.tools.story_graph import validate_story_graph

    project_dir = str(Path(file_path).parent)
    issues = validate_story_graph(data, project_dir)

    if not issues:
        return None

    # Collect all issue messages
    lines: list[str] = []
    for category, items in issues.items():
        for item in items:
            lines.append(f"[{category}] {item}")

    total = sum(len(v) for v in issues.values())
    summary = "; ".join(lines[:5])
    if total > 5:
        summary += f" ... and {total - 5} more issue(s)"

    return ToolError(
        message=(
            f"Write rejected: story-graph.json has {total} structural issue(s). "
            f"The file was NOT modified. Issues: {summary}"
        ),
        brief=f"Story graph invalid: {total} issues",
    )
