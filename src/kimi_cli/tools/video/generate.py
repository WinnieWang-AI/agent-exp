from pathlib import Path
from typing import Literal

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.config import Config
from kimi_cli.soul.approval import Approval
from kimi_cli.tools import SkipThisTool
from kimi_cli.tools.utils import ToolResultBuilder, load_desc
from kimi_cli.tools.video.error_log import record_error
from kimi_cli.tools.video.providers import get_default_provider
from kimi_cli.tools.video.providers.base import GenerationRequest


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
        default="", description="Path to reference image for image_to_video mode (single image as video starting point)"
    )
    reference_images: list[str] = Field(
        default=[],
        description="Paths to reference images (character, environment, etc.) for multi-reference video generation. "
        "The video model uses these to maintain visual consistency. Max 4 images. "
        "In prompts, reference them as <<<image_1>>>, <<<image_2>>>, etc.",
    )
    first_frame_path: str = Field(
        default="",
        description="Path to the first frame image. Used with last_frame_path for first-last-frame (FLF) video generation.",
    )
    last_frame_path: str = Field(
        default="",
        description="Path to the last frame image. Used with first_frame_path for first-last-frame (FLF) video generation.",
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

        available = list(self._config.video_providers.keys())
        tos_config = self._config.tos if self._config.tos.is_configured else None
        try:
            provider_name, provider = get_default_provider(
                self._config.video_providers, params.provider, tos_config
            )
        except ValueError as e:
            record_error(
                tool="GenerateVideo",
                error=str(e),
                prompt=params.prompt,
                extra={"available_providers": available},
            )
            return builder.error(
                message=f"{e}\nAvailable providers: {available}",
                brief="Provider error",
            )

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

        model_name = self._config.video_providers[provider_name].model_name or "(default)"

        try:
            submission = await provider.submit_job(request)
        except Exception as e:
            record_error(
                tool="GenerateVideo",
                provider=provider_name,
                model=model_name,
                prompt=params.prompt,
                error=str(e),
                extra={
                    "mode": params.mode,
                    "duration_seconds": params.duration_seconds,
                    "aspect_ratio": params.aspect_ratio,
                },
            )
            return builder.error(
                message=(
                    f"Failed to submit video generation job.\n"
                    f"  provider: {provider_name}\n"
                    f"  model: {model_name}\n"
                    f"  error: {e}"
                ),
                brief="Submission failed",
            )

        builder.write(f"Video generation job submitted successfully.\n")
        builder.write(f"  job_id: {submission.job_id}\n")
        builder.write(f"  provider: {provider_name}\n")
        builder.write(f"  model: {model_name}\n")
        builder.write(f"  estimated_seconds: {submission.estimated_seconds}\n")
        builder.write(f"  available_providers: {available}\n")
        builder.write(f"\nUse CheckVideoJob with this job_id to poll for completion.\n")
        return builder.ok(message=f"Job submitted: {submission.job_id}")
