from pathlib import Path

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.config import Config
from kimi_cli.tools import SkipThisTool
from kimi_cli.tools.utils import ToolResultBuilder, load_desc, warn_if_relative_path
from kimi_cli.tools.audio.providers import create_music_provider
from kimi_cli.tools.audio.providers.base import MusicJobState


class Params(BaseModel):
    job_id: str = Field(description="The job ID returned by GenerateMusic")
    provider: str = Field(description="The provider name that generated this job")
    download_dir: str = Field(
        default="",
        description="If provided, download all completed songs to this directory",
    )
    download_filename: str = Field(
        default="",
        description="Custom filename for the downloaded song (e.g. 'astate_bgm_warm_start.mp3'). "
        "If empty, defaults to 'song_{index}.mp3'. Only used when download_dir is set.",
    )


class CheckMusicJob(CallableTool2[Params]):
    name: str = "CheckMusicJob"
    params: type[Params] = Params

    def __init__(self, config: Config):
        if not config.music_providers:
            raise SkipThisTool()
        super().__init__(description=load_desc(Path(__file__).parent / "check_music_job.md"))
        self._config = config

    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()

        provider_config = self._config.music_providers.get(params.provider)
        if provider_config is None:
            return builder.error(
                message=f"Provider not found: {params.provider}",
                brief="Provider not found",
            )

        provider = create_music_provider(provider_config)

        try:
            status = await provider.check_job(params.job_id)
        except Exception as e:
            return builder.error(
                message=f"Failed to check job status: {e}",
                brief="Check failed",
            )

        builder.write(f"Job: {status.job_id}\n")
        builder.write(f"State: {status.state.value}\n")
        builder.write(f"Progress: {status.progress_percent:.0f}%\n")

        if status.state == MusicJobState.FAILED:
            builder.write(f"Error: {status.error_message}\n")
            return builder.error(
                message=f"Job failed: {status.error_message}",
                brief="Job failed",
            )

        if status.songs:
            builder.write(f"\nSongs ({len(status.songs)}):\n")
            for i, song in enumerate(status.songs):
                builder.write(f"  [{i}] {song.title or 'Untitled'}\n")
                builder.write(f"      duration: {song.duration_seconds:.0f}s\n")
                if song.style:
                    builder.write(f"      style: {song.style}\n")
                if song.lyrics:
                    preview = song.lyrics[:80].replace("\n", " ")
                    builder.write(f"      lyrics: {preview}...\n")
                builder.write(f"      url: {song.audio_url}\n")

        # Download if requested and completed
        if status.state == MusicJobState.COMPLETED and params.download_dir and status.songs:
            if not params.download_filename:
                builder.write(
                    "\nWARNING: download_filename not specified — defaulting to 'song_{i}.mp3'. "
                    "This may not match the expected naming convention '{audio_state_id}.mp3'. "
                    "Always pass download_filename to ensure correct file naming.\n"
                )
            resolved_dir = warn_if_relative_path(params.download_dir, param_name="download_dir", tool_name="CheckMusicJob")
            download_dir = Path(resolved_dir)
            download_dir.mkdir(parents=True, exist_ok=True)
            builder.write(f"\nDownloading {len(status.songs)} song(s)...\n")
            for i, song in enumerate(status.songs):
                if params.download_filename and i == 0:
                    # First song uses the exact requested filename
                    filename = params.download_filename
                elif params.download_filename:
                    # Additional songs get numbered suffixes as alternatives
                    stem = Path(params.download_filename).stem
                    suffix = Path(params.download_filename).suffix or ".mp3"
                    filename = f"{stem}_{i}{suffix}"
                else:
                    filename = f"song_{i}.mp3"
                output_path = str(download_dir / filename)
                try:
                    await provider.download_audio(song.audio_url, output_path)
                    builder.write(f"  Downloaded: {output_path}\n")
                except Exception as e:
                    builder.write(f"  Download failed for song {i}: {e}\n")

        if status.state == MusicJobState.COMPLETED:
            if not params.download_dir and status.songs:
                builder.write(
                    "\nWARNING: Job completed but download_dir was not provided — "
                    "audio was NOT downloaded. Call again with download_dir and "
                    "download_filename to save the file.\n"
                )
                return builder.ok(
                    message="Job completed but audio was NOT downloaded (no download_dir).",
                )
            return builder.ok(message="Job completed.")
        return builder.ok(message=f"Job {status.state.value} ({status.progress_percent:.0f}%)")
