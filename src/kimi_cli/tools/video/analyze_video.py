from pathlib import Path

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.config import Config
from kimi_cli.tools import SkipThisTool
from kimi_cli.tools.utils import ToolResultBuilder, load_desc
from kimi_cli.tools.video.vlm_client import GeminiVLMClient


class Params(BaseModel):
    video_path: str = Field(description="Path to the video file to analyze")
    prompt: str = Field(
        description="What to analyze about the video. Be specific about aspects to focus on."
    )


class AnalyzeVideo(CallableTool2[Params]):
    name: str = "AnalyzeVideo"
    params: type[Params] = Params

    def __init__(self, config: Config):
        if not config.vlm_providers:
            raise SkipThisTool()
        super().__init__(description=load_desc(Path(__file__).parent / "analyze_video.md"))
        self._config = config
        self._client = self._create_client()

    def _create_client(self) -> GeminiVLMClient:
        _name, provider_config = next(iter(self._config.vlm_providers.items()))
        return GeminiVLMClient(provider_config)

    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()

        video_path = Path(params.video_path)
        if not video_path.exists():
            return builder.error(
                message=f"Video file not found: {params.video_path}",
                brief="File not found",
            )

        try:
            result = await self._client.analyze(params.video_path, params.prompt)
        except Exception as e:
            return builder.error(
                message=f"VLM analysis failed: {e}",
                brief="Analysis failed",
            )

        builder.write(result)
        return builder.ok(message="Video analysis complete.")
