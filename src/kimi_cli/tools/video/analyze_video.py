import asyncio
import json
from pathlib import Path

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.config import Config
from kimi_cli.tools import SkipThisTool
from kimi_cli.tools.utils import ToolResultBuilder, load_desc
from kimi_cli.tools.video.vlm_client import GeminiVLMClient

_CAPTION_PROMPT = """Describe this video in detail. Include:
- Scene: what is happening, the narrative/action sequence from start to end
- Characters/subjects: who appears, their appearance, clothing, actions, expressions
- Setting/environment: location, objects, background elements
- Camera work: shot type, angle, movement (pan, zoom, static, etc.)
- Visual style: art style, color palette, lighting, mood/atmosphere
- Audio (if perceivable): music, dialogue, sound effects
- Timing: pacing, key moments, transitions

Be specific and objective. Describe the progression of events chronologically. Output in Chinese."""


class Params(BaseModel):
    video_path: str = Field(description="Path to the video file to caption.")


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

        meta = await self._probe_metadata(params.video_path)

        try:
            result = await self._client.analyze(params.video_path, _CAPTION_PROMPT)
        except Exception as e:
            return builder.error(
                message=f"VLM video captioning failed: {e}",
                brief="Captioning failed",
            )

        if meta:
            builder.write("[Video Metadata]\n")
            for k, v in meta.items():
                builder.write(f"  {k}: {v}\n")
            builder.write("\n[Caption]\n")
        builder.write(result)
        return builder.ok(message="Video caption complete.")

    @staticmethod
    async def _probe_metadata(video_path: str) -> dict[str, str]:
        """Extract objective video metadata via ffprobe."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                video_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                return {}
            info = json.loads(stdout)
            meta: dict[str, str] = {}
            fmt = info.get("format", {})
            if "duration" in fmt:
                meta["duration"] = f"{float(fmt['duration']):.2f}s"
            if "size" in fmt:
                meta["file_size"] = f"{int(fmt['size']) // 1024}KB"
            for stream in info.get("streams", []):
                if stream.get("codec_type") == "video":
                    w = stream.get("width", "?")
                    h = stream.get("height", "?")
                    meta["resolution"] = f"{w}x{h}"
                    fps = stream.get("r_frame_rate", "")
                    if fps and "/" in fps:
                        num, den = fps.split("/")
                        try:
                            meta["fps"] = f"{int(num) / int(den):.1f}"
                        except (ValueError, ZeroDivisionError):
                            meta["fps"] = fps
                elif stream.get("codec_type") == "audio":
                    meta["audio_codec"] = stream.get("codec_name", "unknown")
                    meta["audio_sample_rate"] = stream.get("sample_rate", "unknown")
            return meta
        except Exception:
            return {}
