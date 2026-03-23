from pathlib import Path

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.config import Config
from kimi_cli.tools import SkipThisTool
from kimi_cli.tools.utils import ToolResultBuilder, load_desc
from kimi_cli.tools.video.vlm_client import GeminiVLMClient

_CAPTION_PROMPT = """Describe this image in detail. Include:
- Main subject(s): who/what is depicted, their appearance, pose, expression, clothing
- Setting/background: environment, location, objects
- Visual style: art style, color palette, lighting, mood/atmosphere
- Composition: framing, perspective, layout
- Any text or symbols visible

Be specific and objective. Output in the same language as any text in the image, otherwise use Chinese."""


class Params(BaseModel):
    image_path: str = Field(
        description="Path to the image file to caption."
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

        p = Path(params.image_path)
        if not p.exists():
            return builder.error(
                message=f"Image file not found: {params.image_path}",
                brief="File not found",
            )

        try:
            result = await self._client.analyze_image(
                [("image", params.image_path)], _CAPTION_PROMPT
            )
        except Exception as e:
            return builder.error(
                message=f"VLM image captioning failed: {e}",
                brief="Captioning failed",
            )

        builder.write(result)
        return builder.ok(message="Image caption complete.")
