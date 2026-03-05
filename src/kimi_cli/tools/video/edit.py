import asyncio
from pathlib import Path

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.soul.approval import Approval
from kimi_cli.tools.utils import ToolResultBuilder, load_desc
from kimi_cli.utils.environment import Environment


class Params(BaseModel):
    operation: str = Field(
        description='Operation: "concat", "trim", "add_audio", "add_subtitles", or "transition"'
    )
    input_files: list[str] = Field(
        default_factory=list, description="Input video file paths"
    )
    output_path: str = Field(description="Output video file path")
    start_time: float = Field(default=0, description="Start time in seconds (for trim)")
    end_time: float = Field(default=0, description="End time in seconds (for trim)")
    audio_path: str = Field(default="", description="Audio file path (for add_audio)")
    subtitle_path: str = Field(default="", description="SRT subtitle file path (for add_subtitles)")
    transition_type: str = Field(default="fade", description="Transition type (for transition)")
    transition_duration: float = Field(
        default=0.5, description="Transition duration in seconds (for transition)"
    )


class VideoEdit(CallableTool2[Params]):
    name: str = "VideoEdit"
    params: type[Params] = Params

    def __init__(self, approval: Approval, environment: Environment):
        super().__init__(description=load_desc(Path(__file__).parent / "edit.md"))
        self._approval = approval
        self._environment = environment

    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()

        try:
            cmd = self._build_ffmpeg_command(params)
        except ValueError as e:
            return builder.error(message=str(e), brief="Invalid params")

        cmd_str = " ".join(cmd)
        approved = await self._approval.request(
            sender="VideoEdit",
            action="video_edit",
            description=f"Run FFmpeg: {cmd_str[:200]}",
        )
        if not approved:
            return builder.error(message="Video edit rejected by user.", brief="Rejected")

        Path(params.output_path).parent.mkdir(parents=True, exist_ok=True)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            err_msg = stderr.decode(errors="replace")[-500:]
            builder.write(f"FFmpeg failed (exit code {process.returncode}):\n{err_msg}\n")
            return builder.error(message="FFmpeg command failed.", brief="FFmpeg error")

        builder.write(f"Operation: {params.operation}\n")
        builder.write(f"Output: {params.output_path}\n")
        if stdout:
            builder.write(f"stdout: {stdout.decode(errors='replace')[:500]}\n")
        return builder.ok(message=f"Video edit ({params.operation}) completed.")

    def _build_ffmpeg_command(self, params: Params) -> list[str]:
        match params.operation:
            case "concat":
                return self._build_concat(params)
            case "trim":
                return self._build_trim(params)
            case "add_audio":
                return self._build_add_audio(params)
            case "add_subtitles":
                return self._build_add_subtitles(params)
            case "transition":
                return self._build_transition(params)
            case _:
                raise ValueError(
                    f'Unknown operation: "{params.operation}". '
                    'Use "concat", "trim", "add_audio", "add_subtitles", or "transition".'
                )

    def _build_concat(self, params: Params) -> list[str]:
        if len(params.input_files) < 2:
            raise ValueError("concat requires at least 2 input files")
        # Use concat demuxer via filter_complex for reliability
        inputs: list[str] = []
        filter_parts: list[str] = []
        for i, f in enumerate(params.input_files):
            inputs.extend(["-i", f])
            filter_parts.append(f"[{i}:v:0][{i}:a:0]")
        filter_str = "".join(filter_parts) + f"concat=n={len(params.input_files)}:v=1:a=1[outv][outa]"
        return [
            "ffmpeg", "-y", *inputs,
            "-filter_complex", filter_str,
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-c:a", "aac",
            params.output_path,
        ]

    def _build_trim(self, params: Params) -> list[str]:
        if not params.input_files:
            raise ValueError("trim requires at least 1 input file")
        cmd = ["ffmpeg", "-y", "-i", params.input_files[0]]
        if params.start_time > 0:
            cmd.extend(["-ss", str(params.start_time)])
        if params.end_time > 0:
            cmd.extend(["-to", str(params.end_time)])
        cmd.extend(["-c:v", "libx264", "-c:a", "aac", params.output_path])
        return cmd

    def _build_add_audio(self, params: Params) -> list[str]:
        if not params.input_files:
            raise ValueError("add_audio requires at least 1 input video file")
        if not params.audio_path:
            raise ValueError("add_audio requires audio_path")
        return [
            "ffmpeg", "-y",
            "-i", params.input_files[0],
            "-i", params.audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0", "-map", "1:a:0",
            "-shortest",
            params.output_path,
        ]

    def _build_add_subtitles(self, params: Params) -> list[str]:
        if not params.input_files:
            raise ValueError("add_subtitles requires at least 1 input video file")
        if not params.subtitle_path:
            raise ValueError("add_subtitles requires subtitle_path (SRT file)")
        return [
            "ffmpeg", "-y",
            "-i", params.input_files[0],
            "-vf", f"subtitles={params.subtitle_path}",
            "-c:v", "libx264", "-c:a", "copy",
            params.output_path,
        ]

    def _build_transition(self, params: Params) -> list[str]:
        if len(params.input_files) < 2:
            raise ValueError("transition requires at least 2 input files")
        dur = params.transition_duration
        # Simple crossfade between two clips
        return [
            "ffmpeg", "-y",
            "-i", params.input_files[0],
            "-i", params.input_files[1],
            "-filter_complex",
            f"[0:v][1:v]xfade=transition={params.transition_type}:duration={dur}:offset=0[outv];"
            f"[0:a][1:a]acrossfade=d={dur}[outa]",
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-c:a", "aac",
            params.output_path,
        ]
