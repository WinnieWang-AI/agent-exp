import asyncio
import json
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

        # Get objective metadata via ffprobe (duration, resolution, fps, audio).
        meta = await self._probe_metadata(params.video_path)

        try:
            result = await self._client.analyze(params.video_path, params.prompt)
        except Exception as e:
            return builder.error(
                message=f"VLM analysis failed: {e}",
                brief="Analysis failed",
            )

        # Prepend objective metadata so the LLM doesn't need to guess.
        if meta:
            builder.write("[Video Metadata (from ffprobe)]\n")
            for k, v in meta.items():
                builder.write(f"  {k}: {v}\n")
            builder.write("\n[VLM Analysis]\n")
        builder.write(result)
        return builder.ok(message="Video analysis complete.")

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
