from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from kimi_cli.tools.video.providers.base import (
    GenerationRequest,
    VideoJobState,
    VideoJobStatus,
    VideoJobSubmission,
    VideoProvider,
)


class MockVideoProvider(VideoProvider):
    """Mock video provider for development and testing.

    Simulates async video generation with fake job IDs and generates
    simple test videos using FFmpeg.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, _MockJob] = {}

    async def submit_job(self, request: GenerationRequest) -> VideoJobSubmission:
        job_id = f"mock_{uuid.uuid4().hex[:12]}"
        self._jobs[job_id] = _MockJob(request=request, check_count=0)
        return VideoJobSubmission(
            job_id=job_id,
            provider="mock",
            estimated_seconds=3.0,
        )

    async def check_job(self, job_id: str) -> VideoJobStatus:
        job = self._jobs.get(job_id)
        if job is None:
            return VideoJobStatus(
                job_id=job_id,
                state=VideoJobState.FAILED,
                error_message=f"Job not found: {job_id}",
            )

        job.check_count += 1
        # First check: processing; second check onwards: completed
        if job.check_count < 2:
            return VideoJobStatus(
                job_id=job_id,
                state=VideoJobState.PROCESSING,
                progress_percent=50.0,
            )

        return VideoJobStatus(
            job_id=job_id,
            state=VideoJobState.COMPLETED,
            progress_percent=100.0,
            result_url=f"mock://result/{job_id}",
        )

    async def download_result(self, result_url: str, output_path: str) -> None:
        """Generate a simple test video using FFmpeg."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        job_id = result_url.split("/")[-1] if "/" in result_url else "unknown"
        prompt = ""
        job = self._jobs.get(job_id)
        if job is not None:
            prompt = job.request.prompt[:60]

        # Generate a 3-second test video with text overlay
        display_text = prompt.replace("'", "\\'") if prompt else "Mock Video"
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x1a1a2e:s=1280x720:d=3:r=24",
            "-vf", (
                f"drawtext=text='{display_text}'"
                ":fontcolor=white:fontsize=36"
                ":x=(w-text_w)/2:y=(h-text_h)/2"
            ),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            # Fallback: create an empty file so the path exists
            Path(output_path).touch()


class _MockJob:
    __slots__ = ("request", "check_count")

    def __init__(self, request: GenerationRequest, check_count: int) -> None:
        self.request = request
        self.check_count = check_count
