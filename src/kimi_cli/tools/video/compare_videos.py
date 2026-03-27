from pathlib import Path

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.config import Config
from kimi_cli.tools import SkipThisTool
from kimi_cli.tools.utils import ToolResultBuilder, load_desc, warn_if_relative_path
from kimi_cli.tools.video.analyze_video import AnalyzeVideo
from kimi_cli.tools.video.vlm_client import GeminiVLMClient

_DEFAULT_CRITERIA = """\
Compare the original reference video with the generated video. Evaluate across these dimensions, scoring each from 1-10:

1. **Composition**: Camera angles, framing, spatial layout, scene structure
2. **Color & Lighting**: Color palette, contrast, lighting direction, atmosphere
3. **Motion & Dynamics**: Movement speed, direction, fluidity, character actions
4. **Timing & Rhythm**: Scene duration, transition timing, pacing, beats
5. **Content Fidelity**: Does the content match? Characters, objects, settings

For each dimension, provide:
- A score (1-10)
- Specific observations about what matches and what differs

Then provide:
- An **overall score** (1-10, average of all dimensions)
- A **verdict**: APPROVED if overall >= 9, otherwise NEEDS_REVISION
- **Specific actionable feedback** for improvement (if NEEDS_REVISION)

Format your response as a structured evaluation report."""


class Params(BaseModel):
    original_path: str = Field(description="Path to the original reference video")
    generated_path: str = Field(description="Path to the generated video to evaluate")
    criteria: str = Field(
        default="",
        description="Evaluation criteria/focus. Leave empty for comprehensive default comparison.",
    )


class CompareVideos(CallableTool2[Params]):
    name: str = "CompareVideos"
    params: type[Params] = Params

    def __init__(self, config: Config):
        if not config.vlm_providers:
            raise SkipThisTool()
        super().__init__(description=load_desc(Path(__file__).parent / "compare_videos.md"))
        self._config = config
        self._client = self._create_client()

    def _create_client(self) -> GeminiVLMClient:
        _name, provider_config = next(iter(self._config.vlm_providers.items()))
        return GeminiVLMClient(provider_config)

    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()

        original_path = warn_if_relative_path(params.original_path, param_name="original_path", tool_name="CompareVideos")
        generated_path = warn_if_relative_path(params.generated_path, param_name="generated_path", tool_name="CompareVideos")

        for label, path in [
            ("Original", original_path),
            ("Generated", generated_path),
        ]:
            if not Path(path).exists():
                return builder.error(
                    message=f"{label} video not found: {path}",
                    brief=f"{label} not found",
                )

        prompt = params.criteria if params.criteria else _DEFAULT_CRITERIA

        # Get objective metadata for both videos.
        orig_meta = await AnalyzeVideo._probe_metadata(original_path)
        gen_meta = await AnalyzeVideo._probe_metadata(generated_path)

        try:
            result = await self._client.compare(
                original_path, generated_path, prompt
            )
        except Exception as e:
            return builder.error(
                message=f"VLM comparison failed: {e}",
                brief="Comparison failed",
            )

        if orig_meta or gen_meta:
            builder.write("[Video Metadata (from ffprobe)]\n")
            if orig_meta:
                builder.write(f"  Original: {orig_meta}\n")
            if gen_meta:
                builder.write(f"  Generated: {gen_meta}\n")
            builder.write("\n[VLM Comparison]\n")
        builder.write(result)
        return builder.ok(message="Video comparison complete.")
