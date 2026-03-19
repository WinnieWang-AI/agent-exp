from pathlib import Path
from typing import Optional

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.config import Config
from kimi_cli.tools import SkipThisTool
from kimi_cli.tools.utils import ToolResultBuilder, load_desc
from kimi_cli.tools.video.vlm_client import GeminiVLMClient


class ImageInput(BaseModel):
    label: str = Field(description="A label to identify this image in the analysis (e.g. 'entity_ref', 'state_ref', 'first_frame')")
    path: str = Field(description="Path to the image file")


class Params(BaseModel):
    images: list[ImageInput] = Field(
        description="One or more images to analyze. Each has a label and path. "
        "For single image analysis, provide one item. "
        "For comparison (e.g. entity vs state reference), provide multiple items."
    )
    prompt: str = Field(
        description="What to analyze about the image(s). Be specific about aspects to focus on. "
        "Reference images by their labels."
    )


class AnalyzeImage(CallableTool2[Params]):
    name: str = "AnalyzeImage"
    params: type[Params] = Params

    def __init__(self, config: Config):
        if not config.vlm_providers:
            raise SkipThisTool()
        super().__init__(description=load_desc(Path(__file__).parent / "analyze_image.md"))
        self._config = config
        self._client = self._create_client()

    def _create_client(self) -> GeminiVLMClient:
        _name, provider_config = next(iter(self._config.vlm_providers.items()))
        return GeminiVLMClient(provider_config)

    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()

        image_paths: list[tuple[str, str]] = []
        for img in params.images:
            p = Path(img.path)
            if not p.exists():
                return builder.error(
                    message=f"Image file not found: {img.path}",
                    brief="File not found",
                )
            image_paths.append((img.label, img.path))

        try:
            result = await self._client.analyze_image(image_paths, params.prompt)
        except Exception as e:
            return builder.error(
                message=f"VLM image analysis failed: {e}",
                brief="Analysis failed",
            )

        builder.write(result)
        return builder.ok(message="Image analysis complete.")
