from pathlib import Path

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.config import Config
from kimi_cli.soul.approval import Approval
from kimi_cli.tools import SkipThisTool
from kimi_cli.tools.utils import ToolResultBuilder, load_desc
from kimi_cli.tools.audio.providers import get_default_music_provider
from kimi_cli.tools.audio.providers.base import MusicGenerationRequest


class Params(BaseModel):
    prompt: str = Field(description="Description of the music to generate (mood, tempo, instruments, etc.)")
    music_style: str = Field(default="", description='Style tags (e.g. "pop, upbeat", "cinematic, orchestral")')
    lyrics: str = Field(default="", description="Lyrics for the song (leave empty for instrumental or auto-generated)")
    make_instrumental: bool = Field(default=False, description="Generate instrumental-only music (no vocals)")
    vocal_only: bool = Field(default=False, description="Generate vocals only (no accompaniment)")
    voice_id: str = Field(default="", description="Specific singer voice ID")
    provider: str = Field(default="", description="Provider name (uses default if empty)")


class GenerateMusic(CallableTool2[Params]):
    name: str = "GenerateMusic"
    params: type[Params] = Params

    def __init__(self, config: Config, approval: Approval):
        if not config.music_providers:
            raise SkipThisTool()
        super().__init__(description=load_desc(Path(__file__).parent / "generate_music.md"))
        self._config = config
        self._approval = approval

    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()

        approved = await self._approval.request(
            sender="GenerateMusic",
            action="generate_music",
            description=f"Generate music via API: {params.prompt[:100]}",
        )
        if not approved:
            return builder.error(message="Music generation rejected by user.", brief="Rejected")

        available = list(self._config.music_providers.keys())
        try:
            provider_name, provider = get_default_music_provider(
                self._config.music_providers, params.provider
            )
        except ValueError as e:
            return builder.error(
                message=f"{e}\nAvailable providers: {available}",
                brief="Provider error",
            )

        request = MusicGenerationRequest(
            prompt=params.prompt,
            music_style=params.music_style,
            lyrics=params.lyrics,
            make_instrumental=params.make_instrumental,
            vocal_only=params.vocal_only,
            voice_id=params.voice_id,
        )

        try:
            submission = await provider.submit_job(request)
        except Exception as e:
            return builder.error(
                message=f"Failed to submit music generation job: {e}",
                brief="Submission failed",
            )

        builder.write(f"Music generation job submitted successfully.\n")
        builder.write(f"  job_id: {submission.job_id}\n")
        builder.write(f"  provider: {provider_name}\n")
        builder.write(f"  estimated_seconds: {submission.estimated_seconds}\n")
        builder.write(f"  available_providers: {available}\n")
        builder.write(f"\nUse CheckMusicJob with this job_id to poll for completion.\n")
        return builder.ok(message=f"Job submitted: {submission.job_id}")
