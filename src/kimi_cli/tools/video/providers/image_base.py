from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class ImageGenerationRequest(BaseModel):
    """Request to generate an image."""

    prompt: str
    aspect_ratio: str = "1:1"
    style: str = ""
    negative_prompt: str = ""
    reference_image_paths: list[str] = []


class ImageGenerationResult(BaseModel):
    """Result of image generation."""

    image_bytes: bytes
    mime_type: str = "image/png"


class ImageProvider(ABC):
    """Abstract base class for image generation providers."""

    @abstractmethod
    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        """Generate an image from the given request."""
        ...
