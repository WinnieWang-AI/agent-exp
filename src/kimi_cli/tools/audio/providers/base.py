from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from pydantic import BaseModel


# ==============================================================================
# Music Generation (Suno)
# ==============================================================================


class MusicJobState(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class MusicGenerationRequest(BaseModel):
    """Request to generate music."""

    prompt: str
    lyrics: str = ""
    make_instrumental: bool = True


class MusicJobSubmission(BaseModel):
    """Result of submitting a music generation job."""

    job_id: str
    provider: str
    estimated_seconds: float = 120.0


class MusicSong(BaseModel):
    """A generated song."""

    audio_url: str
    title: str = ""
    duration_seconds: float = 0.0
    lyrics: str = ""
    style: str = ""


class MusicJobStatus(BaseModel):
    """Status of a music generation job."""

    job_id: str
    state: MusicJobState
    progress_percent: float = 0.0
    songs: list[MusicSong] = []
    error_message: str = ""


class MusicProvider(ABC):
    """Abstract base class for music generation providers."""

    @abstractmethod
    async def submit_job(self, request: MusicGenerationRequest) -> MusicJobSubmission:
        """Submit a music generation job. Returns immediately with a job ID."""
        ...

    @abstractmethod
    async def check_job(self, job_id: str) -> MusicJobStatus:
        """Check the status of a music generation job."""
        ...

    @abstractmethod
    async def download_audio(self, audio_url: str, output_path: str) -> None:
        """Download a generated audio file to the specified path."""
        ...


# ==============================================================================
# TTS (Minimax)
# ==============================================================================


class TTSRequest(BaseModel):
    """Request to generate speech from text."""

    text: str
    voice_id: str = "male-qn-qingse"
    speed: float = 1.0
    vol: float = 1.0
    pitch: int = 0
    language: str = "zh"


class TTSResult(BaseModel):
    """Result of TTS generation."""

    audio_url: str


class TTSProvider(ABC):
    """Abstract base class for TTS providers."""

    @abstractmethod
    async def generate_speech(self, request: TTSRequest) -> TTSResult:
        """Generate speech audio from the given text. Returns an audio URL."""
        ...

    @abstractmethod
    async def download_audio(self, audio_url: str, output_path: str) -> None:
        """Download audio to the specified path."""
        ...
