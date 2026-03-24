"""Shared Gemini VLM client for video analysis tools."""

from __future__ import annotations

import asyncio
from pathlib import Path

from google import genai
from google.genai import types

from kimi_cli.config import VLMProviderConfig

_DEFAULT_MODEL = "gemini-2.0-flash"


def _guess_video_mime(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".avi": "video/x-msvideo",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
    }.get(suffix, "video/mp4")


def _guess_image_mime(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }.get(suffix, "image/png")


class GeminiVLMClient:
    """Thin wrapper around Gemini for video understanding tasks.

    Supports two authentication modes:
    - API key: Simple Gemini Developer API access
    - Vertex AI: Service account credentials with project/location
    """

    _shared_semaphore: asyncio.Semaphore | None = None

    @classmethod
    def _get_semaphore(cls) -> asyncio.Semaphore:
        if cls._shared_semaphore is None:
            cls._shared_semaphore = asyncio.Semaphore(2)
        return cls._shared_semaphore

    def __init__(self, config: VLMProviderConfig) -> None:
        self._model = config.model_name or _DEFAULT_MODEL

        if config.credentials_json and config.project_id:
            # Vertex AI mode with service account
            import google.auth
            from google.auth import _default as auth_default
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
                "VLM provider requires either api_key or credentials_json + project_id"
            )

        self._semaphore = self._get_semaphore()

    async def analyze_image(
        self,
        image_paths: list[tuple[str, str]],
        prompt: str,
    ) -> str:
        """Send one or more labelled images + prompt to Gemini.

        Args:
            image_paths: List of (label, path) tuples. Each image is prefixed
                         with its label so the VLM can distinguish them.
            prompt: The analysis prompt.
        """
        parts: list[types.Part] = []
        for label, path in image_paths:
            image_bytes = Path(path).read_bytes()
            mime = _guess_image_mime(path)
            parts.append(types.Part.from_text(text=f"[{label}]"))
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
        parts.append(types.Part.from_text(text=prompt))

        async with self._semaphore:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=parts,
                config=types.GenerateContentConfig(response_modalities=["TEXT"]),
            )

        if not response.candidates:
            raise RuntimeError("Gemini returned no candidates")

        return response.text or ""

    async def analyze(self, video_path: str, prompt: str) -> str:
        """Send a single video + prompt to Gemini and return the text response."""
        video_bytes = Path(video_path).read_bytes()
        mime = _guess_video_mime(video_path)

        parts: list[types.Part] = [
            types.Part.from_bytes(data=video_bytes, mime_type=mime),
            types.Part.from_text(text=prompt),
        ]

        async with self._semaphore:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=parts,
                config=types.GenerateContentConfig(response_modalities=["TEXT"]),
            )

        if not response.candidates:
            raise RuntimeError("Gemini returned no candidates")

        return response.text or ""

    async def compare(
        self, original_path: str, generated_path: str, prompt: str
    ) -> str:
        """Send two videos + prompt to Gemini for comparison."""
        original_bytes = Path(original_path).read_bytes()
        generated_bytes = Path(generated_path).read_bytes()
        original_mime = _guess_video_mime(original_path)
        generated_mime = _guess_video_mime(generated_path)

        parts: list[types.Part] = [
            types.Part.from_text(text="Original reference video:"),
            types.Part.from_bytes(data=original_bytes, mime_type=original_mime),
            types.Part.from_text(text="Generated video to evaluate:"),
            types.Part.from_bytes(data=generated_bytes, mime_type=generated_mime),
            types.Part.from_text(text=prompt),
        ]

        async with self._semaphore:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=parts,
                config=types.GenerateContentConfig(response_modalities=["TEXT"]),
            )

        if not response.candidates:
            raise RuntimeError("Gemini returned no candidates")

        return response.text or ""
