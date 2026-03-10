from __future__ import annotations

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

    mode: Literal["text_to_video", "image_to_video"] = "text_to_video"
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


def resolve_image_to_url(path_or_url: str, tos_config: TOSConfig | None = None) -> str:
    """Resolve a local file path to a public URL by uploading to TOS.

    If *path_or_url* is already an HTTP(S) URL it is returned as-is.
    If it is a local file path, the file is uploaded to TOS and the
    resulting public URL is returned.

    Args:
        path_or_url: A local path or URL string.
        tos_config: TOS configuration.  Required when *path_or_url* is a
            local file; raises ``RuntimeError`` if not provided.
    """
    if not path_or_url:
        return path_or_url
    # Already a URL — pass through.
    if path_or_url.startswith(("http://", "https://", "data:")):
        return path_or_url
    # Local file — upload to TOS.
    p = Path(path_or_url)
    if not p.is_file():
        raise FileNotFoundError(f"Reference image not found: {path_or_url}")
    if tos_config is None or not tos_config.is_configured:
        raise RuntimeError(
            f"Cannot convert local file '{path_or_url}' to URL: "
            "TOS is not configured. Please add [tos] section to your config."
        )
    from kimi_cli.tools.video.providers.tos_upload import upload_file

    return upload_file(tos_config, path_or_url)


class VideoProvider(ABC):
    """Abstract base class for video generation providers."""

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
