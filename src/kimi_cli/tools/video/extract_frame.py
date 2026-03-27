import asyncio
import json
from pathlib import Path

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.tools.utils import ToolResultBuilder, load_desc, warn_if_relative_path


class Params(BaseModel):
    video_path: str = Field(description="Path to the source video file")
    output_path: str = Field(description="Path to save the extracted frame image")
    position: str = Field(
        default="last",
        description='Frame position: "last", "first", or a timestamp in seconds (e.g. "2.5")',
    )


class ExtractFrame(CallableTool2[Params]):
    name: str = "ExtractFrame"
    params: type[Params] = Params

    def __init__(self):
        super().__init__(description=load_desc(Path(__file__).parent / "extract_frame.md"))

    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()

        video_path = warn_if_relative_path(params.video_path, param_name="video_path", tool_name="ExtractFrame")
        output_path = warn_if_relative_path(params.output_path, param_name="output_path", tool_name="ExtractFrame")

        video = Path(video_path)
        if not video.exists():
            return builder.error(
                message=f"Video file not found: {video_path}",
                brief="File not found",
            )

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        position = params.position.strip().lower()

        if position == "first":
            cmd = self._build_first_frame_cmd(video_path, output_path)
        elif position == "last":
            duration = await self._get_duration(video_path)
            if duration is None:
                return builder.error(
                    message="Failed to determine video duration.",
                    brief="Probe failed",
                )
            # Seek to a small offset before the end to grab the last frame.
            seek = max(duration - 0.05, 0)
            cmd = self._build_seek_cmd(video_path, output_path, seek)
        else:
            try:
                ts = float(position)
            except ValueError:
                return builder.error(
                    message=f'Invalid position: "{params.position}". Use "first", "last", or a number in seconds.',
                    brief="Invalid position",
                )
            cmd = self._build_seek_cmd(video_path, output_path, ts)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            err_msg = stderr.decode(errors="replace")[-500:]
            return builder.error(
                message=f"FFmpeg failed (exit code {process.returncode}):\n{err_msg}",
                brief="FFmpeg error",
            )

        if not Path(output_path).exists():
            return builder.error(
                message="FFmpeg ran successfully but output file was not created.",
                brief="No output",
            )

        builder.write(f"Frame extracted successfully.\n")
        builder.write(f"  source: {video_path}\n")
        builder.write(f"  position: {params.position}\n")
        builder.write(f"  output: {output_path}\n")
        return builder.ok(message=f"Frame saved to {output_path}")

    @staticmethod
    async def _get_duration(video_path: str) -> float | None:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            video_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return None
        try:
            info = json.loads(stdout)
            return float(info["format"]["duration"])
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    @staticmethod
    def _build_first_frame_cmd(video_path: str, output_path: str) -> list[str]:
        return [
            "ffmpeg", "-y",
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "2",
            output_path,
        ]

    @staticmethod
    def _build_seek_cmd(video_path: str, output_path: str, seek_seconds: float) -> list[str]:
        return [
            "ffmpeg", "-y",
            "-ss", f"{seek_seconds:.3f}",
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "2",
            output_path,
        ]
