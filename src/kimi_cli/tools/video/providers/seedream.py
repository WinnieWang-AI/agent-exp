"""Seedream image generation provider (ByteDance Ark API)."""

from __future__ import annotations

import base64
from pathlib import Path

import httpx

from kimi_cli.config import ImageProviderConfig, TOSConfig
from kimi_cli.tools.video.providers.base import resolve_image_to_url
from kimi_cli.tools.video.providers.image_base import (
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageProvider,
)

_DEFAULT_MODEL = "doubao-seedream-4-0-250828"
_DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com"

# Aspect ratio → pixel size mapping (matching ace-backend-go defaults).
_SIZE_MAP: dict[str, str] = {
    "1:1": "1024x1024",
    "16:9": "2560x1440",
    "9:16": "1440x2560",
    "3:4": "1440x2560",
    "4:3": "2560x1440",
    "3:2": "2560x1440",
    "2:3": "1440x2560",
}


class SeedreamImageProvider(ImageProvider):
    """Image generation provider using ByteDance Seedream via Ark API.

    API contract (derived from ace-backend-go):
      - Endpoint: POST {base_url}/api/v3/images/generations
      - Auth:     Authorization: Bearer {api_key}
      - Request:  { model, prompt, size, image?, sequential_image_generation? }
      - Response: { data: [{ url?, b64_json? }], error? }
    """

    def __init__(self, config: ImageProviderConfig, tos_config: TOSConfig | None = None) -> None:
        self._base_url = (config.base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._api_key = config.api_key.get_secret_value()
        self._model = config.model_name or _DEFAULT_MODEL
        self._custom_headers = config.custom_headers or {}
        self._tos_config = tos_config

    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        # Build prompt: append aspect ratio as Seedream convention
        prompt = request.prompt
        if request.style:
            prompt += f", {request.style}"
        if request.negative_prompt:
            prompt += f". Avoid: {request.negative_prompt}"
        if request.aspect_ratio:
            prompt += f" -ar {request.aspect_ratio}"

        size = _SIZE_MAP.get(request.aspect_ratio, "1024x1024")

        body: dict = {
            "model": self._model,
            "prompt": prompt,
            "size": size,
            "watermark": False,
        }

        # Reference images: upload to TOS and pass URLs
        if request.reference_image_paths:
            urls = [
                resolve_image_to_url(p, self._tos_config)
                for p in request.reference_image_paths
            ]
            if len(urls) == 1:
                body["image"] = urls[0]
            else:
                body["image"] = urls
                body["sequential_image_generation"] = "auto"

        async with self._client() as client:
            resp = await client.post("/api/v3/images/generations", json=body)
            _raise_for_status(resp, "Seedream generate")
            data = resp.json()

        # Check for API error
        if data.get("error"):
            err = data["error"]
            msg = err.get("message", "") if isinstance(err, dict) else str(err)
            raise RuntimeError(f"Seedream API error: {msg}")

        # Extract image from response
        items = data.get("data", [])
        if not items:
            raise RuntimeError(f"Seedream returned no image data: {data}")

        item = items[0]

        # Prefer b64_json (avoids extra download), fall back to URL
        if item.get("b64_json"):
            image_bytes = base64.b64decode(item["b64_json"])
            return ImageGenerationResult(image_bytes=image_bytes, mime_type="image/png")

        if item.get("url"):
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as dl_client:
                dl_resp = await dl_client.get(item["url"])
                _raise_for_status(dl_resp, "Seedream download")
                return ImageGenerationResult(
                    image_bytes=dl_resp.content,
                    mime_type=dl_resp.headers.get("content-type", "image/png"),
                )

        raise RuntimeError(f"Seedream response contained no url or b64_json: {item}")

    def _client(self) -> httpx.AsyncClient:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._custom_headers,
        }
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=120,
            follow_redirects=True,
        )


def _raise_for_status(resp: httpx.Response, context: str) -> None:
    if resp.is_success:
        return
    try:
        detail = resp.json()
    except Exception:
        detail = resp.text[:300]
    raise RuntimeError(f"{context} failed (HTTP {resp.status_code}): {detail}")
