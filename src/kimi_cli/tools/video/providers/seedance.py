"""Seedance (ByteDance Ark) video generation provider.

Supports Seedance 1.x (legacy) and Dreamina Seedance 2.0 models.

API contract (derived from ace-backend-go):
  - Submit: POST {base_url}/api/v3/contents/generations/tasks
  - Poll:   GET  {base_url}/api/v3/contents/generations/tasks/{task_id}
  - Auth:   Authorization: Bearer {api_key}
  - States: queued → running → succeeded | failed | expired
  - Result: content.video_url (HTTP URL)

Dreamina Seedance 2.0 differences:
  - Parameters (resolution, ratio, duration, etc.) are independent JSON fields
  - Legacy models embed parameters as text commands in prompt (--resolution, --duration, etc.)
  - Supports multimodal content: video_url, audio_url, image_url
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from kimi_cli.config import TOSConfig, VideoProviderConfig
from kimi_cli.tools.video.providers.base import (
    GenerationRequest,
    VideoJobState,
    VideoJobStatus,
    VideoJobSubmission,
    VideoProvider,
    resolve_image_to_url,
)

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "dreamina-seedance-2-0-fast"
_DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com"


def _is_dreamina_20(model_name: str) -> bool:
    return model_name.startswith("dreamina-seedance-2")


class SeedanceVideoProvider(VideoProvider):
    """Seedance video generation provider using the ByteDance Ark API."""

    def __init__(self, config: VideoProviderConfig, tos_config: TOSConfig | None = None) -> None:
        self._base_url = (config.base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._api_key = config.api_key.get_secret_value()
        self._model = config.model_name or _DEFAULT_MODEL
        self._custom_headers = config.custom_headers or {}
        self._tos_config = tos_config

    # ------------------------------------------------------------------
    # VideoProvider interface
    # ------------------------------------------------------------------

    async def submit_job(self, request: GenerationRequest) -> VideoJobSubmission:
        content = self._build_content(request)
        body: dict = {
            "model": self._model,
            "content": content,
        }

        if _is_dreamina_20(self._model):
            self._apply_dreamina20_params(body, request)
        else:
            self._apply_legacy_params(body, content, request)

        async with self._client() as client:
            resp = await client.post("/api/v3/contents/generations/tasks", json=body)
            _raise_for_status(resp, "Seedance submit")
            data = resp.json()

        task_id: str = data.get("id", "")
        if not task_id:
            raise RuntimeError(f"Seedance API did not return a task id: {data}")

        return VideoJobSubmission(
            job_id=task_id,
            provider="seedance",
            estimated_seconds=max(request.duration_seconds * 20, 60),
        )

    async def check_job(self, job_id: str) -> VideoJobStatus:
        async with self._client() as client:
            resp = await client.get(f"/api/v3/contents/generations/tasks/{job_id}")
            _raise_for_status(resp, "Seedance poll")
            data = resp.json()

        status: str = data.get("status", "")

        if status == "failed":
            err = data.get("error") or {}
            message = err.get("message", "") if isinstance(err, dict) else str(err)
            code = err.get("code", "") if isinstance(err, dict) else ""
            return VideoJobStatus(
                job_id=job_id,
                state=VideoJobState.FAILED,
                error_message=message or f"Seedance generation failed (code={code})",
            )

        if status == "expired":
            return VideoJobStatus(
                job_id=job_id,
                state=VideoJobState.FAILED,
                error_message="Seedance generation task expired",
            )

        if status == "succeeded":
            result_url = ""
            content = data.get("content")
            if isinstance(content, dict):
                result_url = content.get("video_url", "")
            return VideoJobStatus(
                job_id=job_id,
                state=VideoJobState.COMPLETED,
                progress_percent=100.0,
                result_url=result_url,
            )

        # queued or running
        progress = 10.0 if status == "queued" else 50.0
        return VideoJobStatus(
            job_id=job_id,
            state=VideoJobState.PROCESSING,
            progress_percent=progress,
        )

    async def download_result(self, result_url: str, output_path: str) -> None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        # Seedance video download requires auth header.
        async with self._client(timeout=300) as client:
            resp = await client.get(result_url)
            _raise_for_status(resp, "Seedance download")
            Path(output_path).write_bytes(resp.content)

    # ------------------------------------------------------------------
    # Content building
    # ------------------------------------------------------------------

    def _build_content(self, request: GenerationRequest) -> list[dict]:
        """Build the content array for the Seedance API request."""
        content: list[dict] = []

        # Text prompt is always first.
        prompt = request.prompt
        if request.style:
            prompt += f", {request.style}"
        if request.negative_prompt:
            prompt += f". Avoid: {request.negative_prompt}"

        content.append({"type": "text", "text": prompt})

        # First-last frame mode (FLF).
        if request.first_frame_path:
            first_url = resolve_image_to_url(request.first_frame_path, self._tos_config)
            content.append({
                "type": "image_url",
                "image_url": {"url": first_url},
                "role": "first_frame",
            })
            if request.last_frame_path:
                last_url = resolve_image_to_url(request.last_frame_path, self._tos_config)
                content.append({
                    "type": "image_url",
                    "image_url": {"url": last_url},
                    "role": "last_frame",
                })
        elif request.reference_image_path:
            # Single reference image as first frame (I2V).
            ref_url = resolve_image_to_url(request.reference_image_path, self._tos_config)
            content.append({
                "type": "image_url",
                "image_url": {"url": ref_url},
                "role": "first_frame",
            })
        elif request.reference_images:
            # Multi-reference images.
            for img in request.reference_images:
                img_url = resolve_image_to_url(img, self._tos_config)
                content.append({
                    "type": "image_url",
                    "image_url": {"url": img_url},
                    "role": "reference_image",
                })

        return content

    # ------------------------------------------------------------------
    # Parameter application
    # ------------------------------------------------------------------

    def _apply_dreamina20_params(self, body: dict, request: GenerationRequest) -> None:
        """Apply Dreamina Seedance 2.0 independent JSON parameters."""
        body["resolution"] = "720p"
        body["ratio"] = request.aspect_ratio
        body["duration"] = int(request.duration_seconds)
        body["generate_audio"] = True
        body["watermark"] = False

    def _apply_legacy_params(
        self, body: dict, content: list[dict], request: GenerationRequest
    ) -> None:
        """Apply legacy model parameters as text commands embedded in prompt."""
        if not content:
            return
        prompt = content[0].get("text", "")
        prompt += " --resolution 720p"
        prompt += f" --ratio {request.aspect_ratio}"
        prompt += f" --duration {int(request.duration_seconds)}"
        prompt += " --watermark false"
        content[0]["text"] = prompt

        body["generate_audio"] = True

    # ------------------------------------------------------------------
    # HTTP client
    # ------------------------------------------------------------------

    def _client(self, timeout: int = 60) -> httpx.AsyncClient:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._custom_headers,
        }
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )


def _raise_for_status(resp: httpx.Response, context: str) -> None:
    if resp.is_success:
        return
    try:
        detail = resp.json()
    except Exception:
        detail = resp.text[:200]
    raise RuntimeError(f"{context} failed (HTTP {resp.status_code}): {detail}")
