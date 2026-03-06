from pathlib import Path

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.config import Config
from kimi_cli.soul.approval import Approval
from kimi_cli.tools import SkipThisTool
from kimi_cli.tools.utils import ToolResultBuilder, load_desc
from kimi_cli.tools.audio.providers import get_default_tts_provider
from kimi_cli.tools.audio.providers.base import TTSRequest


class Params(BaseModel):
    text: str = Field(description="The text to convert to speech")
    output_path: str = Field(description="Path to save the generated audio file (e.g. assets/audio/narration.mp3)")
    voice_id: str = Field(default="male-qn-qingse", description="Voice identifier")
    speed: float = Field(default=1.0, description="Speech speed (0.5-2.0)")
    vol: float = Field(default=1.0, description="Volume (0.1-10.0)")
    pitch: int = Field(default=0, description="Pitch adjustment (-12 to 12)")
    language: str = Field(default="zh", description='Language code: "zh" or "en"')
    provider: str = Field(default="", description="Provider name (uses default if empty)")


class GenerateSpeech(CallableTool2[Params]):
    name: str = "GenerateSpeech"
    params: type[Params] = Params

    def __init__(self, config: Config, approval: Approval):
        if not config.tts_providers:
            raise SkipThisTool()
        super().__init__(description=load_desc(Path(__file__).parent / "generate_speech.md"))
        self._config = config
        self._approval = approval

    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()

        approved = await self._approval.request(
            sender="GenerateSpeech",
            action="generate_speech",
            description=f"Generate speech via TTS: {params.text[:100]}",
        )
        if not approved:
            return builder.error(message="Speech generation rejected by user.", brief="Rejected")

        try:
            provider_name, provider = get_default_tts_provider(
                self._config.tts_providers, params.provider
            )
        except ValueError as e:
            return builder.error(message=str(e), brief="Provider error")

        request = TTSRequest(
            text=params.text,
            voice_id=params.voice_id,
            speed=params.speed,
            vol=params.vol,
            pitch=params.pitch,
            language=params.language,
        )

        try:
            result = await provider.generate_speech(request)
        except Exception as e:
            return builder.error(
                message=f"TTS generation failed: {e}",
                brief="Generation failed",
            )

        try:
            await provider.download_audio(result.audio_url, params.output_path)
        except Exception as e:
            return builder.error(
                message=f"Audio download failed: {e}",
                brief="Download failed",
            )

        builder.write(f"Speech generated successfully.\n")
        builder.write(f"  output: {params.output_path}\n")
        builder.write(f"  provider: {provider_name}\n")
        builder.write(f"  voice: {params.voice_id}\n")
        builder.write(f"  language: {params.language}\n")
        builder.write(f"  text_length: {len(params.text)} chars\n")
        return builder.ok(message=f"Audio saved to {params.output_path}")
