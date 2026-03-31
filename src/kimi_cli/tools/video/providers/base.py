from __future__ import annotations

import base64
import mimetypes
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from kimi_cli.config import TOSConfig


class VideoJobState(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class GenerationRequest(BaseModel):
    """Request to generate a video."""

    mode: Literal["text_to_video", "reference_to_video", "image_to_video"] = "text_to_video"
    prompt: str
    duration_seconds: float = 5.0
    aspect_ratio: str = "16:9"
    reference_image_path: str = ""
    reference_images: list[str] = []
    first_frame_path: str = ""
    last_frame_path: str = ""
    style: str = ""
    negative_prompt: str = ""


class VideoJobSubmission(BaseModel):
    """Result of submitting a video generation job."""

    job_id: str
    provider: str
    estimated_seconds: float


class VideoJobStatus(BaseModel):
    """Status of a video generation job."""

    job_id: str
    state: VideoJobState
    progress_percent: float = 0.0
    result_url: str = ""
    error_message: str = ""


def _file_to_data_uri(path: Path) -> str:
    """Read a local file and return a base64 data URI."""
    mime, _ = mimetypes.guess_type(str(path))
    if not mime:
        mime = "application/octet-stream"
    data = path.read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def is_data_uri(value: str) -> bool:
    """Check if a string is a base64 data URI."""
    return value.startswith("data:")


def parse_data_uri(data_uri: str) -> tuple[str, str]:
    """Parse a data URI into (media_type, base64_data).

    Returns:
        Tuple of (media_type, raw_base64_string).
    """
    # data:<media_type>;base64,<data>
    header, _, data = data_uri.partition(",")
    media_type = header.split(";")[0].removeprefix("data:")
    return media_type, data


def resolve_image_to_url(path_or_url: str, tos_config: TOSConfig | None = None) -> str:
    """Resolve a local file path to a public URL (via TOS) or a base64 data URI.

    If *path_or_url* is already an HTTP(S) URL or data URI it is returned as-is.
    If it is a local file path:
      - Uploads to TOS and returns the public URL (when TOS is configured).
      - Falls back to a base64 data URI (when TOS is not configured).

    Args:
        path_or_url: A local path or URL string.
        tos_config: TOS configuration.  When not provided or not configured,
            local files are encoded as base64 data URIs.
    """
    if not path_or_url:
        return path_or_url
    # Already a URL or data URI — pass through.
    if path_or_url.startswith(("http://", "https://", "data:")):
        return path_or_url
    # Local file — upload to TOS or encode as base64.
    p = Path(path_or_url)
    if not p.is_absolute():
        # Relative paths are fragile (depend on cwd). Resolve and warn.
        p = p.resolve()
        import logging
        logging.getLogger(__name__).warning(
            "resolve_image_to_url received a relative path '%s' — resolved to '%s'. "
            "Use absolute paths to avoid cwd-dependent failures.",
            path_or_url, p,
        )
    if not p.is_file():
        raise FileNotFoundError(
            f"Reference image not found: {path_or_url} (resolved: {p}). "
            f"Ensure the file exists and the path is absolute."
        )
    if tos_config is not None and tos_config.is_configured:
        from kimi_cli.tools.video.providers.tos_upload import upload_file

        return upload_file(tos_config, str(p))
    # Fallback: base64 data URI so providers can use their base64 input path.
    return _file_to_data_uri(p)


class VideoProvider(ABC):
    """Abstract base class for video generation providers."""

    def supports_audio(self, request: GenerationRequest) -> bool:
        """Whether this provider generates audio for the given request.

        Default: True. Subclasses override for mode/model-specific behavior.
        """
        return True

    @abstractmethod
    async def submit_job(self, request: GenerationRequest) -> VideoJobSubmission:
        """Submit a video generation job. Returns immediately with a job ID."""
        ...

    @abstractmethod
    async def check_job(self, job_id: str) -> VideoJobStatus:
        """Check the status of a video generation job."""
        ...

    @abstractmethod
    async def download_result(self, result_url: str, output_path: str) -> None:
        """Download the generated video to the specified path."""
        ...
