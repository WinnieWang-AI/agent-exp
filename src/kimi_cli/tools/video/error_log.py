"""Persistent error logging for video generation tools.

Appends structured JSON records to ``output/video_errors.jsonl`` (relative to
the current working directory).  Each line is a self-contained JSON object that
can be replayed or analysed later.
"""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path
from typing import Any

from kimi_cli.utils.logging import logger

_LOG_FILENAME = "video_errors.jsonl"


def _default_log_dir() -> Path:
    """Return ``<cwd>/output``."""
    return Path.cwd() / "output"


def record_error(
    *,
    tool: str,
    provider: str = "",
    model: str = "",
    job_id: str = "",
    prompt: str = "",
    error: str,
    extra: dict[str, Any] | None = None,
    log_dir: Path | None = None,
) -> None:
    """Append a single error record to the JSONL log file.

    Parameters
    ----------
    tool:
        Tool name that encountered the error (e.g. ``GenerateVideo``).
    provider:
        Provider name (e.g. ``kling``, ``vidu``).
    model:
        Model name used for the request.
    job_id:
        Job / task ID (if available).
    prompt:
        The generation prompt (may be truncated for readability).
    error:
        Human-readable error description.
    extra:
        Arbitrary extra data to include in the record.
    log_dir:
        Directory to write the log file into.  Defaults to ``<cwd>/output``.
    """
    record: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "unix_ts": time.time(),
        "tool": tool,
    }
    if provider:
        record["provider"] = provider
    if model:
        record["model"] = model
    if job_id:
        record["job_id"] = job_id
    if prompt:
        record["prompt"] = prompt[:500]
    record["error"] = error
    if extra:
        record["extra"] = extra

    target_dir = log_dir or _default_log_dir()
    target_file = target_dir / _LOG_FILENAME

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        with open(target_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        logger.warning(
            "Failed to write video error log to {path}: {tb}",
            path=target_file,
            tb=traceback.format_exc(),
        )
