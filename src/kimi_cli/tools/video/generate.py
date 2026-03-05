from pathlib import Path
from typing import Literal

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.config import Config
from kimi_cli.soul.approval import Approval
from kimi_cli.tools import SkipThisTool
from kimi_cli.tools.utils import ToolResultBuilder, load_desc
from kimi_cli.tools.video.providers import get_default_provider
from kimi_cli.tools.video.providers.base import GenerationRequest


class Params(BaseModel):
    prompt: str = Field(description="Detailed description of the video to generate")
    mode: Literal["text_to_video", "image_to_video"] = Field(
        default="text_to_video",
        description="Generation mode: text_to_video or image_to_video",
    )
    duration_seconds: float = Field(default=5.0, description="Target video duration in seconds")
    aspect_ratio: str = Field(default="16:9", description='Aspect ratio (e.g. "16:9", "9:16", "1:1")')
    provider: str = Field(default="", description="Provider name (uses default if empty)")
    reference_image_path: str = Field(
        default="", description="Path to reference image (required for image_to_video mode)"
    )
    style: str = Field(default="", description='Style hint (e.g. "cinematic", "anime", "realistic")')
    negative_prompt: str = Field(default="", description="What to avoid in the generated video")


class GenerateVideo(CallableTool2[Params]):
    name: str = "GenerateVideo"
    params: type[Params] = Params

    def __init__(self, config: Config, approval: Approval):
        if not config.video_providers:
            raise SkipThisTool()
        super().__init__(description=load_desc(Path(__file__).parent / "generate.md"))
        self._config = config
        self._approval = approval

    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()

        # Request approval before calling paid API
        approved = await self._approval.request(
            sender="GenerateVideo",
            action="generate_video",
            description=f"Generate video via API: {params.prompt[:100]}",
        )
        if not approved:
            return builder.error(message="Video generation rejected by user.", brief="Rejected")

        try:
            provider_name, provider = get_default_provider(
                self._config.video_providers, params.provider
            )
        except ValueError as e:
            return builder.error(message=str(e), brief="Provider error")

        request = GenerationRequest(
            mode=params.mode,
            prompt=params.prompt,
            duration_seconds=params.duration_seconds,
            aspect_ratio=params.aspect_ratio,
            reference_image_path=params.reference_image_path,
            style=params.style,
            negative_prompt=params.negative_prompt,
        )

        try:
            submission = await provider.submit_job(request)
        except Exception as e:
            return builder.error(
                message=f"Failed to submit video generation job: {e}",
                brief="Submission failed",
            )

        builder.write(f"Video generation job submitted successfully.\n")
        builder.write(f"  job_id: {submission.job_id}\n")
        builder.write(f"  provider: {provider_name}\n")
        builder.write(f"  estimated_seconds: {submission.estimated_seconds}\n")
        builder.write(f"\nUse CheckVideoJob with this job_id to poll for completion.\n")
        return builder.ok(message=f"Job submitted: {submission.job_id}")
