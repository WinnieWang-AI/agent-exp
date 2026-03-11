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
    audio_offset: float = Field(
        default=0, description="Offset in seconds to place the audio in the video timeline (for add_audio). 0 means start of video."
    )
    audio_mix: bool = Field(
        default=True,
        description="If true, mix the new audio with existing audio tracks. If false, replace the audio track entirely (for add_audio).",
    )
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
        # Normalize all inputs to the same resolution/SAR before concatenating.
        # For clips without audio, generate a silent audio track so concat works.
        n = len(params.input_files)
        inputs: list[str] = []
        filter_parts: list[str] = []
        concat_parts: list[str] = []
        for i, f in enumerate(params.input_files):
            inputs.extend(["-i", f])
            filter_parts.append(
                f"[{i}:v:0]scale=1920:1080:force_original_aspect_ratio=decrease,"
                f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}];"
            )
            if self._probe_has_audio(f):
                filter_parts.append(
                    f"[{i}:a:0]aformat=sample_rates=44100:channel_layouts=stereo[a{i}];"
                )
            else:
                # No audio stream — generate silent audio matching the video duration.
                filter_parts.append(
                    f"anullsrc=r=44100:cl=stereo[null{i}];"
                    f"[null{i}]atrim=duration=60[a{i}];"
                )
            concat_parts.append(f"[v{i}][a{i}]")
        filter_str = "".join(filter_parts) + "".join(concat_parts) + f"concat=n={n}:v=1:a=1[outv][outa]"
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

        video_input = params.input_files[0]
        has_audio = self._probe_has_audio(video_input)

        if params.audio_mix and has_audio:
            # Mix new audio with existing audio, output length = video length.
            # adelay: offset the new audio by audio_offset seconds (in ms).
            # amix: combine both audio streams; duration=first keeps video's length.
            delay_ms = int(params.audio_offset * 1000)
            if delay_ms > 0:
                af = f"[1:a]adelay={delay_ms}|{delay_ms}[delayed];[0:a][delayed]amix=inputs=2:duration=first:dropout_transition=0[aout]"
            else:
                af = "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=0[aout]"
            return [
                "ffmpeg", "-y",
                "-i", video_input,
                "-i", params.audio_path,
                "-filter_complex", af,
                "-map", "0:v:0", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac",
                params.output_path,
            ]
        else:
            # No existing audio or replace mode: add audio track to video.
            # Do NOT use -shortest (it truncates video to audio length).
            delay_ms = int(params.audio_offset * 1000)
            if delay_ms > 0:
                # Delay the audio and pad to video length.
                af = f"[1:a]adelay={delay_ms}|{delay_ms},apad[aout]"
                return [
                    "ffmpeg", "-y",
                    "-i", video_input,
                    "-i", params.audio_path,
                    "-filter_complex", af,
                    "-map", "0:v:0", "-map", "[aout]",
                    "-c:v", "copy", "-c:a", "aac",
                    params.output_path,
                ]
            else:
                return [
                    "ffmpeg", "-y",
                    "-i", video_input,
                    "-i", params.audio_path,
                    "-c:v", "copy", "-c:a", "aac",
                    "-map", "0:v:0", "-map", "1:a:0",
                    params.output_path,
                ]

    @staticmethod
    def _probe_has_audio(path: str) -> bool:
        """Check if a video file has an audio stream."""
        import subprocess
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-select_streams", "a",
                 "-show_entries", "stream=index", "-of", "csv=p=0", path],
                capture_output=True, text=True, timeout=10,
            )
            return bool(result.stdout.strip())
        except Exception:
            return False

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
        # xfade offset = first clip duration - transition duration.
        # Probe the first clip to get its duration.
        offset = self._probe_duration(params.input_files[0]) - dur
        if offset < 0:
            offset = 0
        # Handle clips that may lack audio tracks.
        has_a0 = self._probe_has_audio(params.input_files[0])
        has_a1 = self._probe_has_audio(params.input_files[1])
        video_filter = f"[0:v][1:v]xfade=transition={params.transition_type}:duration={dur}:offset={offset}[outv]"
        if has_a0 and has_a1:
            audio_filter = f";[0:a][1:a]acrossfade=d={dur}[outa]"
            audio_map = ["-map", "[outa]"]
        else:
            audio_filter = ""
            audio_map = []
        return [
            "ffmpeg", "-y",
            "-i", params.input_files[0],
            "-i", params.input_files[1],
            "-filter_complex", video_filter + audio_filter,
            "-map", "[outv]", *audio_map,
            "-c:v", "libx264", "-c:a", "aac",
            params.output_path,
        ]

    @staticmethod
    def _probe_duration(path: str) -> float:
        """Get video duration in seconds via ffprobe."""
        import subprocess
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", path],
                capture_output=True, text=True, timeout=10,
            )
            return float(result.stdout.strip())
        except Exception:
            return 5.0
