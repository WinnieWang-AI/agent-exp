from __future__ import annotations

from kimi_cli.config import ImageProviderConfig, VideoProviderConfig
from kimi_cli.tools.video.providers.base import VideoProvider
from kimi_cli.tools.video.providers.image_base import ImageProvider


def create_provider(config: VideoProviderConfig) -> VideoProvider:
    """Factory function to create a video provider from configuration."""
    provider_type = config.type.lower()
    if provider_type == "mock":
        from kimi_cli.tools.video.providers.mock import MockVideoProvider

        return MockVideoProvider()
    if provider_type == "sora":
        from kimi_cli.tools.video.providers.sora import SoraVideoProvider

        return SoraVideoProvider(config)
    if provider_type == "vidu":
        from kimi_cli.tools.video.providers.vidu import ViduVideoProvider

        return ViduVideoProvider(config)
    if provider_type == "kling":
        from kimi_cli.tools.video.providers.kling import KlingVideoProvider

        return KlingVideoProvider(config)
    if provider_type == "apiyi":
        from kimi_cli.tools.video.providers.apiyi import ApiYiVideoProvider

        return ApiYiVideoProvider(config)
    raise ValueError(f"Unknown video provider type: {config.type}")


def get_default_provider(
    providers: dict[str, VideoProviderConfig], preferred: str = ""
) -> tuple[str, VideoProvider]:
    """Get a video provider by name, or the first available one.

    Returns:
        Tuple of (provider_name, provider_instance).

    Raises:
        ValueError: If no providers are configured or preferred provider not found.
    """
    if not providers:
        raise ValueError("No video providers configured")
    if preferred and preferred in providers:
        return preferred, create_provider(providers[preferred])
    name = next(iter(providers))
    return name, create_provider(providers[name])


def create_image_provider(config: ImageProviderConfig) -> ImageProvider:
    """Factory function to create an image provider from configuration."""
    provider_type = config.type.lower()
    if provider_type == "gemini":
        from kimi_cli.tools.video.providers.gemini import GeminiImageProvider

        return GeminiImageProvider(config)
    raise ValueError(f"Unknown image provider type: {config.type}")


def get_default_image_provider(
    providers: dict[str, ImageProviderConfig], preferred: str = ""
) -> tuple[str, ImageProvider]:
    """Get an image provider by name, or the first available one.

    Returns:
        Tuple of (provider_name, provider_instance).

    Raises:
        ValueError: If no providers are configured or preferred provider not found.
    """
    if not providers:
        raise ValueError("No image providers configured")
    if preferred and preferred in providers:
        return preferred, create_image_provider(providers[preferred])
    name = next(iter(providers))
    return name, create_image_provider(providers[name])
