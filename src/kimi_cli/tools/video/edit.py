import asyncio
from pathlib import Path

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.soul.approval import Approval
from kimi_cli.tools.utils import ToolResultBuilder, load_desc, warn_if_relative_path
from kimi_cli.utils.environment import Environment


class AudioSegment(BaseModel):
    path: str = Field(description="Audio file path")
    start: float = Field(default=0, description="Start time in the output timeline (seconds)")
    end: float = Field(default=0, description="End time in the output timeline (seconds). 0 means play to the end of the audio file.")


class Params(BaseModel):
    operation: str = Field(
        description='Operation: "concat", "trim", "add_audio", "add_subtitles", "transition", or "mix_audio". '
        "For add_audio, set audio_loop=true to loop short BGM. "
        "For mix_audio, provide audio_segments with crossfade_duration to merge multiple audio files with crossfade into one output file."
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
    audio_role: str = Field(
        default="",
        description='Role of the audio being added (for add_audio). '
        'Determines target loudness for automatic volume normalization. '
        'Values: "dialogue" (-16 LUFS, loudest), "sfx" (-20 LUFS), '
        '"bgm" (-28 LUFS, quietest), "voiceover" (-18 LUFS). '
        'Leave empty to skip auto-normalization and use audio_volume instead.',
    )
    audio_volume: float = Field(
        default=1.0,
        description="Manual volume multiplier for the new audio (for add_audio). "
        "Only used when audio_role is empty. 1.0 = original volume.",
    )
    audio_loop: bool = Field(
        default=False,
        description="If true, loop the audio to match video duration (for add_audio). Useful when BGM is shorter than the video.",
    )
    audio_segments: list[AudioSegment] = Field(
        default_factory=list,
        description="Audio segments to mix (for mix_audio). Each segment specifies a file path, "
        "start time, and end time in the output timeline. Segments are trimmed/padded to fit their time range "
        "and crossfaded at overlap points.",
    )
    crossfade_duration: float = Field(
        default=2.0,
        description="Crossfade duration in seconds between consecutive audio segments (for mix_audio).",
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

        # Resolve all relative paths before building ffmpeg command
        _w = lambda p, n: warn_if_relative_path(p, param_name=n, tool_name="VideoEdit")
        updates: dict = {
            "output_path": _w(params.output_path, "output_path"),
            "input_files": [_w(f, f"input_files[{i}]") for i, f in enumerate(params.input_files)],
        }
        if params.audio_path:
            updates["audio_path"] = _w(params.audio_path, "audio_path")
        if params.subtitle_path:
            updates["subtitle_path"] = _w(params.subtitle_path, "subtitle_path")
        if params.audio_segments:
            updates["audio_segments"] = [
                seg.model_copy(update={"path": _w(seg.path, f"audio_segments[{i}].path")})
                for i, seg in enumerate(params.audio_segments)
            ]
        params = params.model_copy(update=updates)

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

        # Probe output metadata so the agent can verify each step
        out_meta = await self._probe_output_metadata(params.output_path)
        if out_meta:
            builder.write(f"Output metadata: {out_meta}\n")

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
            case "mix_audio":
                return self._build_mix_audio(params)
            case _:
                raise ValueError(
                    f'Unknown operation: "{params.operation}". '
                    'Use "concat", "trim", "add_audio", "add_subtitles", "transition", or "mix_audio".'
                )

    def _build_concat(self, params: Params) -> list[str]:
        if len(params.input_files) < 2:
            raise ValueError("concat requires at least 2 input files")
        # Normalize all inputs to the same resolution/SAR before concatenating.
        # Use the first input's resolution as the target to preserve aspect ratio.
        # For clips without audio, generate a silent audio track so concat works.
        target_w, target_h = self._probe_resolution(params.input_files[0])
        n = len(params.input_files)
        inputs: list[str] = []
        filter_parts: list[str] = []
        concat_parts: list[str] = []
        for i, f in enumerate(params.input_files):
            inputs.extend(["-i", f])
            filter_parts.append(
                f"[{i}:v:0]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}];"
            )
            if self._probe_has_audio(f):
                filter_parts.append(
                    f"[{i}:a:0]aformat=sample_rates=44100:channel_layouts=stereo[a{i}];"
                )
            else:
                # No audio stream — generate silent audio matching the video duration.
                dur = self._probe_duration(f)
                filter_parts.append(
                    f"anullsrc=r=44100:cl=stereo[null{i}];"
                    f"[null{i}]atrim=duration={dur}[a{i}];"
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

        # When audio_loop is enabled, use -stream_loop -1 on the audio input
        # so ffmpeg repeats it indefinitely; the video duration acts as the cutoff.
        audio_input_args = (
            ["-stream_loop", "-1", "-i", params.audio_path]
            if params.audio_loop
            else ["-i", params.audio_path]
        )

        if params.audio_mix and has_audio:
            # Mix new audio with existing audio, output length = video length.
            # normalize=0: disable amix's default 1/N normalization so both tracks
            # keep their original volume.  Without this, each serial add_audio call
            # halves the existing audio (-6 dB per pass).
            delay_ms = int(params.audio_offset * 1000)
            vol_filter = self._compute_volume_filter(params.audio_role, params.audio_volume, params.audio_path)

            # Apply volume adjustment to the new audio before mixing.
            if delay_ms > 0:
                delay_chain = f"adelay={delay_ms}|{delay_ms}" + (f",{vol_filter}" if vol_filter else "")
                af = f"[1:a]{delay_chain}[delayed];[0:a][delayed]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
            else:
                if vol_filter:
                    af = f"[1:a]{vol_filter}[adj];[0:a][adj]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
                else:
                    af = "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
            return [
                "ffmpeg", "-y",
                "-i", video_input,
                *audio_input_args,
                "-filter_complex", af,
                "-map", "0:v:0", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac",
                params.output_path,
            ]
        else:
            # No existing audio or replace mode: add audio track to video.
            # Use apad to pad short audio with silence to match video duration,
            # and -shortest to stop when the video ends (not when audio loops forever).
            vol_filter = self._compute_volume_filter(params.audio_role, params.audio_volume, params.audio_path)
            vol_prefix = f"{vol_filter}," if vol_filter else ""
            delay_ms = int(params.audio_offset * 1000)
            if delay_ms > 0:
                af = f"[1:a]{vol_prefix}adelay={delay_ms}|{delay_ms},apad[aout]"
            else:
                af = f"[1:a]{vol_prefix}apad[aout]"
            return [
                "ffmpeg", "-y",
                "-i", video_input,
                *audio_input_args,
                "-filter_complex", af,
                "-map", "0:v:0", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac",
                "-shortest",
                params.output_path,
            ]

    # Target loudness (LUFS) per audio role.
    # Dialogue is loudest; BGM sits well below to avoid masking speech.
    _ROLE_TARGET_LUFS: dict[str, float] = {
        "dialogue":  -16,
        "voiceover": -18,
        "sfx":       -20,
        "bgm":       -28,
    }

    def _compute_volume_filter(self, audio_role: str, audio_volume: float, audio_path: str) -> str:
        """Return an ffmpeg volume filter string to normalize the audio.

        If audio_role is set, probe the file's loudness and compute the dB
        adjustment needed to hit that role's target LUFS.
        Otherwise fall back to the manual audio_volume multiplier.
        """
        if audio_role:
            target = self._ROLE_TARGET_LUFS.get(audio_role)
            if target is not None:
                measured = self._probe_loudness(audio_path)
                if measured is not None:
                    adj = target - measured
                    adj = max(-30, min(12, adj))  # clamp
                    return f"volume={adj}dB"
        # Manual fallback
        if audio_volume != 1.0:
            return f"volume={audio_volume}"
        return ""

    @staticmethod
    def _probe_loudness(path: str) -> float | None:
        """Measure integrated loudness (LUFS) of an audio/video file via ffmpeg loudnorm."""
        import subprocess
        try:
            result = subprocess.run(
                ["ffmpeg", "-i", path, "-af", "loudnorm=print_format=json", "-f", "null", "-"],
                capture_output=True, text=True, timeout=30,
            )
            # loudnorm prints JSON to stderr
            import json as _json
            import re
            # Find the JSON block in stderr
            m = re.search(r'\{[^}]*"input_i"[^}]*\}', result.stderr)
            if m:
                info = _json.loads(m.group())
                val = float(info["input_i"])
                return val if val > -70 else None  # treat near-silence as no signal
        except Exception:
            pass
        return None

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

    def _build_mix_audio(self, params: Params) -> list[str]:
        """Mix multiple audio segments into one file with crossfade transitions.

        Each segment is trimmed to its [start, end) range in the output timeline.
        Consecutive segments are crossfaded at their overlap point.
        acrossfade consumes crossfade_duration per transition, so non-last
        segments are extended by that amount to keep the total duration correct.
        """
        segments = params.audio_segments
        if len(segments) < 2:
            raise ValueError("mix_audio requires at least 2 audio_segments")

        cf = params.crossfade_duration
        inputs: list[str] = []
        filter_parts: list[str] = []

        for i, seg in enumerate(segments):
            inputs.extend(["-i", seg.path])
            seg_duration = (seg.end - seg.start) if seg.end > 0 else 0
            if seg_duration > 0:
                # Extend non-last segments by crossfade duration to compensate
                # for the time acrossfade consumes at each transition.
                effective = seg_duration + cf if i < len(segments) - 1 else seg_duration
                filter_parts.append(f"[{i}:a]atrim=0:{effective},asetpts=PTS-STARTPTS[a{i}];")
            else:
                filter_parts.append(f"[{i}:a]asetpts=PTS-STARTPTS[a{i}];")

        # Chain acrossfade between consecutive segments
        # [a0][a1]acrossfade=d=cf[m0]; [m0][a2]acrossfade=d=cf[m1]; ...
        current = "a0"
        for i in range(1, len(segments)):
            out_label = f"m{i - 1}" if i < len(segments) - 1 else "out"
            filter_parts.append(f"[{current}][a{i}]acrossfade=d={cf}[{out_label}];")
            current = out_label

        # Remove trailing semicolon
        filter_str = "".join(filter_parts).rstrip(";")

        # Pick codec based on output format instead of hardcoding aac
        ext = params.output_path.rsplit(".", 1)[-1].lower() if "." in params.output_path else ""
        codec_args: list[str] = []
        if ext == "mp3":
            codec_args = ["-c:a", "libmp3lame"]
        elif ext == "wav":
            codec_args = ["-c:a", "pcm_s16le"]
        else:
            codec_args = ["-c:a", "aac"]

        return [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_str,
            "-map", f"[{current}]",
            *codec_args,
            params.output_path,
        ]

    @staticmethod
    async def _probe_output_metadata(path: str) -> str:
        """Return a short summary of output file metadata for verification."""
        import subprocess
        parts = []
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration,size",
                 "-show_entries", "stream=width,height,codec_type",
                 "-of", "json", path],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                import json as _json
                info = _json.loads(r.stdout)
                fmt = info.get("format", {})
                if "duration" in fmt:
                    parts.append(f"duration={float(fmt['duration']):.2f}s")
                if "size" in fmt:
                    size_mb = int(fmt["size"]) / (1024 * 1024)
                    parts.append(f"size={size_mb:.1f}MB")
                has_video = has_audio = False
                for s in info.get("streams", []):
                    ct = s.get("codec_type", "")
                    if ct == "video":
                        has_video = True
                        parts.append(f"resolution={s.get('width','?')}x{s.get('height','?')}")
                    elif ct == "audio":
                        has_audio = True
                parts.append(f"audio={'yes' if has_audio else 'no'}")
        except Exception:
            pass
        return ", ".join(parts) if parts else ""

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

    @staticmethod
    def _probe_resolution(path: str) -> tuple[int, int]:
        """Get video width and height via ffprobe."""
        import subprocess
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height",
                 "-of", "csv=p=0:s=x", path],
                capture_output=True, text=True, timeout=10,
            )
            w, h = result.stdout.strip().split("x")
            return int(w), int(h)
        except Exception:
            return 1920, 1080
