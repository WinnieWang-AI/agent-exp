from __future__ import annotations

from pathlib import Path

from google import genai
from google.genai import types

from kimi_cli.config import ImageProviderConfig
from kimi_cli.tools.video.providers.image_base import (
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageProvider,
)

_DEFAULT_MODEL = "gemini-2.0-flash-exp"


class GeminiImageProvider(ImageProvider):
    """Image generation provider using Google Gemini API."""

    def __init__(self, config: ImageProviderConfig) -> None:
        api_key = config.api_key.get_secret_value()
        http_options: types.HttpOptionsDict | None = None
        if config.base_url:
            http_options = {"base_url": config.base_url}
        self._client = genai.Client(api_key=api_key, http_options=http_options)
        self._model = config.model_name or _DEFAULT_MODEL

    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        parts: list[types.Part] = []

        # Add reference images if provided
        for ref_path in request.reference_image_paths:
            image_bytes = Path(ref_path).read_bytes()
            mime = _guess_mime(ref_path)
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))

        # Build the text prompt
        prompt_text = request.prompt
        if request.style:
            prompt_text += f"\nStyle: {request.style}"
        if request.negative_prompt:
            prompt_text += f"\nAvoid: {request.negative_prompt}"
        if request.aspect_ratio and request.aspect_ratio != "1:1":
            prompt_text += f"\nAspect ratio: {request.aspect_ratio}"
        parts.append(types.Part.from_text(text=prompt_text))

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=parts,
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )

        # Extract image from response
        if not response.candidates:
            raise RuntimeError("Gemini returned no candidates")

        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                return ImageGenerationResult(
                    image_bytes=part.inline_data.data,
                    mime_type=part.inline_data.mime_type or "image/png",
                )

        raise RuntimeError("Gemini response contained no image data")


def _guess_mime(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "image/png")
