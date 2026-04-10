from __future__ import annotations

from kimi_cli.config import ImageProviderConfig, TOSConfig, VideoProviderConfig
from kimi_cli.tools.video.providers.base import VideoProvider
from kimi_cli.tools.video.providers.image_base import ImageProvider


def create_provider(
    config: VideoProviderConfig, tos_config: TOSConfig | None = None
) -> VideoProvider:
    """Factory function to create a video provider from configuration."""
    provider_type = config.type.lower()
    if provider_type == "mock":
        from kimi_cli.tools.video.providers.mock import MockVideoProvider

        return MockVideoProvider()
    if provider_type == "vidu":
        from kimi_cli.tools.video.providers.vidu import ViduVideoProvider

        return ViduVideoProvider(config, tos_config)
    if provider_type == "kling":
        from kimi_cli.tools.video.providers.kling import KlingVideoProvider

        return KlingVideoProvider(config, tos_config)
    if provider_type == "seedance":
        from kimi_cli.tools.video.providers.seedance import SeedanceVideoProvider

        return SeedanceVideoProvider(config, tos_config)
    raise ValueError(f"Unknown video provider type: {config.type}")


def get_default_provider(
    providers: dict[str, VideoProviderConfig],
    preferred: str = "",
    tos_config: TOSConfig | None = None,
) -> tuple[str, VideoProvider]:
    """Get a video provider by name, or the first available one.

    Returns:
        Tuple of (provider_name, provider_instance).

    Raises:
        ValueError: If no providers are configured or preferred provider not found.
    """
    if not providers:
        raise ValueError("No video providers configured")
    if preferred:
        if preferred in providers:
            return preferred, create_provider(providers[preferred], tos_config)
        raise ValueError(
            f'Unknown video provider "{preferred}". '
            f"Available providers: {list(providers.keys())}. "
            f"Use a provider name, not a model name."
        )
    name = next(iter(providers))
    return name, create_provider(providers[name], tos_config)


def create_image_provider(
    config: ImageProviderConfig, tos_config: TOSConfig | None = None
) -> ImageProvider:
    """Factory function to create an image provider from configuration."""
    provider_type = config.type.lower()
    if provider_type == "gemini":
        from kimi_cli.tools.video.providers.gemini import GeminiImageProvider

        return GeminiImageProvider(config)
    if provider_type == "seedream":
        from kimi_cli.tools.video.providers.seedream import SeedreamImageProvider

        return SeedreamImageProvider(config, tos_config)
    raise ValueError(f"Unknown image provider type: {config.type}")


def get_default_image_provider(
    providers: dict[str, ImageProviderConfig],
    preferred: str = "",
    tos_config: TOSConfig | None = None,
) -> tuple[str, ImageProvider]:
    """Get an image provider by name, or the first available one.

    Returns:
        Tuple of (provider_name, provider_instance).

    Raises:
        ValueError: If no providers are configured or preferred provider not found.
    """
    if not providers:
        raise ValueError("No image providers configured")
    if preferred:
        if preferred in providers:
            return preferred, create_image_provider(providers[preferred], tos_config)
        raise ValueError(
            f'Unknown image provider "{preferred}". '
            f"Available providers: {list(providers.keys())}. "
            f"Use a provider name, not a model name."
        )
    name = next(iter(providers))
    return name, create_image_provider(providers[name], tos_config)
