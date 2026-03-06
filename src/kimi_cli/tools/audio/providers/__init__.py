from __future__ import annotations

from kimi_cli.config import MusicProviderConfig, TTSProviderConfig
from kimi_cli.tools.audio.providers.base import MusicProvider, TTSProvider


def create_music_provider(config: MusicProviderConfig) -> MusicProvider:
    """Factory function to create a music provider from configuration."""
    provider_type = config.type.lower()
    if provider_type == "suno":
        from kimi_cli.tools.audio.providers.suno import SunoMusicProvider

        return SunoMusicProvider(config)
    raise ValueError(f"Unknown music provider type: {config.type}")


def get_default_music_provider(
    providers: dict[str, MusicProviderConfig], preferred: str = ""
) -> tuple[str, MusicProvider]:
    if not providers:
        raise ValueError("No music providers configured")
    if preferred and preferred in providers:
        return preferred, create_music_provider(providers[preferred])
    name = next(iter(providers))
    return name, create_music_provider(providers[name])


def create_tts_provider(config: TTSProviderConfig) -> TTSProvider:
    """Factory function to create a TTS provider from configuration."""
    provider_type = config.type.lower()
    if provider_type == "minimax":
        from kimi_cli.tools.audio.providers.minimax import MinimaxTTSProvider

        return MinimaxTTSProvider(config)
    raise ValueError(f"Unknown TTS provider type: {config.type}")


def get_default_tts_provider(
    providers: dict[str, TTSProviderConfig], preferred: str = ""
) -> tuple[str, TTSProvider]:
    if not providers:
        raise ValueError("No TTS providers configured")
    if preferred and preferred in providers:
        return preferred, create_tts_provider(providers[preferred])
    name = next(iter(providers))
    return name, create_tts_provider(providers[name])
