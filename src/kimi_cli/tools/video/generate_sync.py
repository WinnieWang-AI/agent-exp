import asyncio
from pathlib import Path
from typing import Literal

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.config import Config
from kimi_cli.soul.approval import Approval
from kimi_cli.tools import SkipThisTool
from kimi_cli.tools.utils import ToolResultBuilder, load_desc, warn_if_relative_path
from kimi_cli.tools.video.error_log import record_error
from kimi_cli.tools.video.providers import get_default_provider
from kimi_cli.tools.video.providers.base import GenerationRequest, VideoJobState


class Params(BaseModel):
    prompt: str = Field(description="Detailed description of the video to generate")
    mode: Literal["text_to_video", "reference_to_video", "image_to_video"] = Field(
        default="text_to_video",
        description='Generation mode: "text_to_video" (pure text, no images), '
        '"reference_to_video" (with reference images for character consistency), '
        'or "image_to_video" (with a starting frame image)',
    )
    duration_seconds: float = Field(default=5.0, description="Target video duration in seconds")
    aspect_ratio: str = Field(default="16:9", description='Aspect ratio (e.g. "16:9", "9:16", "1:1")')
    provider: str = Field(default="", description="Provider name (uses default if empty)")
    reference_image_path: str = Field(
        default="", description="Path to reference image for image_to_video mode"
    )
    reference_images: list[str] = Field(
        default=[],
        description="Paths to reference images for multi-reference video generation. Max 4 images. "
        "In prompts, reference them as <<<image_1>>>, <<<image_2>>>, etc.",
    )
    first_frame_path: str = Field(
        default="",
        description="Path to the first frame image for first-last-frame (FLF) video generation.",
    )
    last_frame_path: str = Field(
        default="",
        description="Path to the last frame image for first-last-frame (FLF) video generation.",
    )
    style: str = Field(default="", description='Style hint (e.g. "cinematic", "anime")')
    negative_prompt: str = Field(default="", description="What to avoid in the generated video")
    download_path: str = Field(
        description="Path to save the generated video file (required)",
    )
    poll_interval_seconds: float = Field(
        default=10.0,
        description="Seconds between status checks (default 10)",
    )
    timeout_seconds: float = Field(
        default=600.0,
        description="Maximum seconds to wait for completion (default 600)",
    )


# Polling constants
_MIN_POLL = 5.0
_MAX_POLL = 30.0


class GenerateVideoSync(CallableTool2[Params]):
    """Submit a video generation job, poll until done, and download — all in one call.

    This tool is designed for **parallel execution**: call it multiple times in
    a single response to generate several clips concurrently.
    """

    name: str = "GenerateVideoSync"
    params: type[Params] = Params

    def __init__(self, config: Config, approval: Approval):
        if not config.video_providers:
            raise SkipThisTool()
        super().__init__(description=load_desc(Path(__file__).parent / "generate_sync.md"))
        self._config = config
        self._approval = approval

    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()

        # --- Approval ---
        approved = await self._approval.request(
            sender="GenerateVideoSync",
            action="generate_video",
            description=f"Generate video via API: {params.prompt[:100]}",
        )
        if not approved:
            return builder.error(message="Video generation rejected by user.", brief="Rejected")

        # --- Resolve provider ---
        available = list(self._config.video_providers.keys())
        tos_config = self._config.tos if self._config.tos.is_configured else None
        try:
            provider_name, provider = get_default_provider(
                self._config.video_providers, params.provider, tos_config
            )
        except ValueError as e:
            record_error(tool="GenerateVideoSync", error=str(e), prompt=params.prompt,
                         extra={"available_providers": available})
            return builder.error(
                message=f"{e}\nAvailable providers: {available}",
                brief="Provider error",
            )

        model_name = self._config.video_providers[provider_name].model_name or "(default)"

        # --- Submit ---
        request = GenerationRequest(
            mode=params.mode,
            prompt=params.prompt,
            duration_seconds=params.duration_seconds,
            aspect_ratio=params.aspect_ratio,
            reference_image_path=params.reference_image_path,
            reference_images=params.reference_images,
            first_frame_path=params.first_frame_path,
            last_frame_path=params.last_frame_path,
            style=params.style,
            negative_prompt=params.negative_prompt,
        )

        try:
            submission = await provider.submit_job(request)
        except Exception as e:
            record_error(tool="GenerateVideoSync", provider=provider_name, model=model_name,
                         prompt=params.prompt, error=str(e))
            return builder.error(
                message=f"Failed to submit job.\n  provider: {provider_name}\n  error: {e}\n  available_providers: {available}",
                brief="Submission failed",
            )

        job_id = submission.job_id
        builder.write(f"Job submitted: {job_id} (provider: {provider_name}, model: {model_name})\n")

        # --- Poll ---
        poll = max(_MIN_POLL, min(params.poll_interval_seconds, _MAX_POLL))
        deadline = asyncio.get_event_loop().time() + params.timeout_seconds
        last_progress = 0.0

        while True:
            await asyncio.sleep(poll)

            try:
                status = await provider.check_job(job_id)
            except Exception as e:
                record_error(tool="GenerateVideoSync", provider=provider_name, model=model_name,
                             job_id=job_id, error=str(e))
                return builder.error(
                    message=f"Failed to check job status.\n  job_id: {job_id}\n  error: {e}\n  available_providers: {available}",
                    brief="Check failed",
                )

            if status.state == VideoJobState.FAILED:
                record_error(tool="GenerateVideoSync", provider=provider_name, model=model_name,
                             job_id=job_id, error=status.error_message or "unknown")
                return builder.error(
                    message=f"Job failed.\n  job_id: {job_id}\n  error: {status.error_message}\n  available_providers: {available}",
                    brief="Job failed",
                )

            if status.state == VideoJobState.COMPLETED:
                builder.write(f"Job completed (100%).\n")
                break

            # Progress update (only log significant changes)
            if status.progress_percent - last_progress >= 10:
                builder.write(f"Progress: {status.progress_percent:.0f}%\n")
                last_progress = status.progress_percent

            if asyncio.get_event_loop().time() > deadline:
                return builder.error(
                    message=f"Timed out after {params.timeout_seconds}s.\n  job_id: {job_id}\n  progress: {status.progress_percent:.0f}%\n  available_providers: {available}",
                    brief="Timeout",
                )

        # --- Download ---
        download_path = warn_if_relative_path(params.download_path, param_name="download_path", tool_name="GenerateVideoSync")
        try:
            await provider.download_result(status.result_url, download_path)
            builder.write(f"Downloaded to: {download_path}\n")
        except Exception as e:
            record_error(tool="GenerateVideoSync", provider=provider_name, model=model_name,
                         job_id=job_id, error=f"Download failed: {e}")
            return builder.error(
                message=f"Job completed but download failed.\n  job_id: {job_id}\n  error: {e}\n  available_providers: {available}",
                brief="Download failed",
            )

        return builder.ok(message=f"Video saved to {download_path}")
