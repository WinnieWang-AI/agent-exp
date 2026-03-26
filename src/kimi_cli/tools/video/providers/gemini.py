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

_DEFAULT_MODEL = "gemini-2.5-flash-image"


class GeminiImageProvider(ImageProvider):
    """Image generation provider using Google Gemini API.

    Supports two authentication modes:
    - API key: Simple Gemini Developer API access
    - Vertex AI: Service account credentials with project/location
    """

    def __init__(self, config: ImageProviderConfig) -> None:
        self._model = config.model_name or _DEFAULT_MODEL

        if config.credentials_json and config.project_id:
            # Vertex AI mode with service account
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_file(
                config.credentials_json,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            self._client = genai.Client(
                vertexai=True,
                credentials=credentials,
                project=config.project_id,
                location=config.location or "global",
            )
        elif config.api_key.get_secret_value():
            # Simple API key mode
            http_options: types.HttpOptionsDict | None = None
            if config.base_url:
                http_options = {"base_url": config.base_url}
            self._client = genai.Client(
                api_key=config.api_key.get_secret_value(),
                http_options=http_options,
            )
        else:
            raise ValueError(
                "Image provider requires either api_key or credentials_json + project_id"
            )

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
        parts.append(types.Part.from_text(text=prompt_text))

        image_config = types.ImageConfig(
            aspect_ratio=request.aspect_ratio or "1:1",
        )
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=parts,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=image_config,
            ),
        )

        # Extract image from response
        if not response.candidates:
            raise RuntimeError("Gemini returned no candidates")

        candidate = response.candidates[0]

        # Check finish_reason for content safety or other rejections
        finish_reason = getattr(candidate, "finish_reason", None)
        if finish_reason and str(finish_reason) not in ("STOP", "0", "FinishReason.STOP"):
            raise RuntimeError(
                f"Gemini generation blocked (finish_reason={finish_reason}). "
                f"This may be due to content safety filters or model policy."
            )

        content = getattr(candidate, "content", None)
        if content is None or content.parts is None:
            raise RuntimeError(
                "Gemini response contained no content. "
                f"finish_reason={finish_reason}"
            )

        for part in content.parts:
            if part.inline_data and part.inline_data.data:
                return ImageGenerationResult(
                    image_bytes=part.inline_data.data,
                    mime_type=part.inline_data.mime_type or "image/png",
                )

        raise RuntimeError("Gemini response contained no image data in parts")


def _guess_mime(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "image/png")
