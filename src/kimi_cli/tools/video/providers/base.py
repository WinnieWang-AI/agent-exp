from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Literal

from pydantic import BaseModel


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
