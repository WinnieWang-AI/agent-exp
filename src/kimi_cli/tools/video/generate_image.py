from pathlib import Path

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.config import Config
from kimi_cli.soul.approval import Approval
from kimi_cli.tools import SkipThisTool
from kimi_cli.tools.utils import ToolResultBuilder, load_desc, warn_if_relative_path
from kimi_cli.tools.video.providers import get_default_image_provider
from kimi_cli.tools.video.providers.image_base import ImageGenerationRequest
from kimi_cli.utils.logging import logger


class Params(BaseModel):
    prompt: str = Field(description="Detailed description of the image to generate")
    style: str = Field(default="", description='Style hint (e.g. "anime", "realistic", "watercolor")')
    aspect_ratio: str = Field(default="1:1", description='Aspect ratio (e.g. "1:1", "16:9", "9:16")')
    output_path: str = Field(description="Path to save the generated image")
    negative_prompt: str = Field(default="", description="What to avoid in the generated image")
    reference_image_paths: list[str] = Field(
        default_factory=list, description="Paths to reference images for guided generation"
    )
    provider: str = Field(default="", description="Provider name (uses default if empty)")


class GenerateImage(CallableTool2[Params]):
    name: str = "GenerateImage"
    params: type[Params] = Params

    def __init__(self, config: Config, approval: Approval):
        if not config.image_providers:
            raise SkipThisTool()
        super().__init__(description=load_desc(Path(__file__).parent / "generate_image.md"))
        self._config = config
        self._approval = approval

    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()

        approved = await self._approval.request(
            sender="GenerateImage",
            action="generate_image",
            description=f"Generate image: {params.prompt[:100]}",
        )
        if not approved:
            return builder.error(message="Image generation rejected by user.", brief="Rejected")

        tos_config = self._config.tos if self._config.tos.is_configured else None
        available = list(self._config.image_providers.keys())

        try:
            provider_name, provider = get_default_image_provider(
                self._config.image_providers, params.provider, tos_config
            )
        except ValueError as e:
            return builder.error(message=str(e), brief="Provider error")

        request = ImageGenerationRequest(
            prompt=params.prompt,
            aspect_ratio=params.aspect_ratio,
            style=params.style,
            negative_prompt=params.negative_prompt,
            reference_image_paths=params.reference_image_paths,
        )

        # Try primary provider, then fallback to others on failure
        result = None
        primary_error = None
        try:
            result = await provider.generate_image(request)
        except Exception as e:
            primary_error = e
            logger.warning(
                "Image generation failed with {provider}, trying fallback: {error}",
                provider=provider_name,
                error=str(e),
            )

        # Fallback: try other configured providers
        if result is None:
            for fallback_name, fallback_config in self._config.image_providers.items():
                if fallback_name == provider_name:
                    continue
                try:
                    _, fallback_provider = get_default_image_provider(
                        self._config.image_providers, fallback_name, tos_config
                    )
                    result = await fallback_provider.generate_image(request)
                    builder.write(f"Primary provider '{provider_name}' failed: {primary_error}\n")
                    builder.write(f"Fallback to '{fallback_name}' succeeded.\n")
                    provider_name = fallback_name
                    break
                except Exception as fallback_e:
                    logger.warning(
                        "Fallback provider {provider} also failed: {error}",
                        provider=fallback_name,
                        error=str(fallback_e),
                    )

        if result is None:
            return builder.error(
                message=f"Image generation failed with all providers.\n"
                        f"  primary ({provider_name}): {primary_error}\n"
                        f"  available_providers: {available}",
                brief="All providers failed",
            )

        output_path = warn_if_relative_path(params.output_path, param_name="output_path", tool_name="GenerateImage")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(result.image_bytes)

        builder.write(f"Image generated: {output_path}\n")
        builder.write(f"Provider: {provider_name}\n")
        builder.write(f"Prompt: {params.prompt}\n")
        if params.style:
            builder.write(f"Style: {params.style}\n")
        builder.write(f"Format: {result.mime_type}\n")
        builder.write(f"Size: {len(result.image_bytes)} bytes\n")
        return builder.ok(message=f"Image saved to {output_path}")
