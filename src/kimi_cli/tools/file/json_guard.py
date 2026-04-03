"""Pre-write validation for JSON files.

Provides syntax checking for all .json files.  If validation fails the
caller should reject the write and return the ToolError to the agent.
"""

from __future__ import annotations

import json

from kosong.tooling import ToolError


def validate_json_before_write(file_path: str, content: str) -> ToolError | None:
    """Validate *content* before it is written to *file_path*.

    Returns a ``ToolError`` if the content is invalid, or ``None`` if it is safe
    to proceed with the write.
    """
    if not file_path.endswith(".json"):
        return None

    # Syntax check (all JSON files)
    try:
        json.loads(content)
    except json.JSONDecodeError as e:
        return ToolError(
            message=(
                f"Write rejected: the result is not valid JSON ({e}). "
                f"The file was NOT modified. Please check your content."
            ),
            brief="Invalid JSON",
        )

    return None
