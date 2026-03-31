"""Vidu video generation provider (via Shengshu API)."""

from __future__ import annotations

from pathlib import Path

import httpx

from kimi_cli.config import VideoProviderConfig
from kimi_cli.config import TOSConfig
from kimi_cli.tools.video.providers.base import (
    GenerationRequest,
    VideoJobState,
    VideoJobStatus,
    VideoJobSubmission,
    VideoProvider,
    resolve_image_to_url,
)

_DEFAULT_MODEL = "viduq3-pro"
_DEFAULT_BASE_URL = "https://api.vidu.com"

# Valid aspect ratios for Vidu.
_VALID_ASPECT_RATIOS = {"16:9", "9:16", "3:4", "4:3", "1:1"}


class ViduVideoProvider(VideoProvider):
    """Vidu video generation provider using the Shengshu API.

    API contract (derived from ace-backend-go):
      - T2V:    POST {base_url}/ent/v2/text2video
      - I2V:    POST {base_url}/ent/v2/img2video
      - Ref2V:  POST {base_url}/ent/v2/reference2video
      - SE2V:   POST {base_url}/ent/v2/start-end2video
      - Poll:   GET  {base_url}/ent/v2/tasks/{task_id}/creations
      - Auth:   Authorization: Token {api_key}
      - States: created → queueing → processing → success | failed
      - Result: ``creations[].url`` (HTTP URL, valid 24h)
    """

    def __init__(self, config: VideoProviderConfig, tos_config: TOSConfig | None = None) -> None:
        self._base_url = (config.base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._api_key = config.api_key.get_secret_value()
        self._model = config.model_name or _DEFAULT_MODEL
        self._custom_headers = config.custom_headers or {}
        self._tos_config = tos_config

    # ------------------------------------------------------------------
    # VideoProvider interface
    # ------------------------------------------------------------------

    def supports_audio(self, request: GenerationRequest) -> bool:
        """Vidu only supports audio with Q3 models.

        Ref2V hardcodes to viduq2 (no audio). Other modes use the configured
        model (default viduq3-pro, which supports audio).
        """
        if request.reference_images:
            model = "viduq2"  # Ref2V always uses viduq2
        else:
            model = self._model
        return "q3" in model

    async def submit_job(self, request: GenerationRequest) -> VideoJobSubmission:
        # Detect mode following ace-backend-go detectVideoMode logic:
        #   1. SE2V: requires BOTH first_frame AND last_frame
        #   2. Ref2V: has reference_images (character consistency)
        #   3. I2V: has a single source image (reference_image_path or first_frame_path)
        #   4. T2V: text only
        has_both_frames = bool(request.first_frame_path and request.last_frame_path)
        has_refs = bool(request.reference_images)
        # I2V source: explicit reference_image_path, or first_frame_path as fallback
        # (matches Go: only first_frame without last_frame → treated as I2V source)
        i2v_source = request.reference_image_path or request.first_frame_path

        if has_refs:
            endpoint = "/ent/v2/reference2video"
        elif has_both_frames:
            endpoint = "/ent/v2/start-end2video"
        elif i2v_source:
            endpoint = "/ent/v2/img2video"
        else:
            endpoint = "/ent/v2/text2video"

        # Ref2V hardcodes model to "viduq2" (Go: submitRef2VTask line 288).
        # SE2V: "viduq2" base not supported, upgrade to "viduq2-pro".
        if endpoint == "/ent/v2/reference2video":
            model = "viduq2"
        elif endpoint == "/ent/v2/start-end2video" and self._model == "viduq2":
            model = "viduq2-pro"
        else:
            model = self._model

        body: dict = {
            "model": model,
            "prompt": request.prompt,
            "duration": int(request.duration_seconds),
            "resolution": "720p",
        }

        # aspect_ratio is only supported by T2V and Ref2V.
        # I2V and SE2V derive aspect ratio from input images (no AspectRatio field
        # in ViduI2VRequest / ViduSE2VRequest structs).
        if endpoint in ("/ent/v2/text2video", "/ent/v2/reference2video"):
            aspect_ratio = request.aspect_ratio if request.aspect_ratio in _VALID_ASPECT_RATIOS else "16:9"
            body["aspect_ratio"] = aspect_ratio

        # Q3 models support audio-video sync by default.
        if "q3" in model:
            body["audio"] = True
            body["moderation"] = "disabled"

        # Build the "images" field based on the selected endpoint.
        if endpoint == "/ent/v2/reference2video":
            refs = request.reference_images[:7]
            body["images"] = [
                resolve_image_to_url(img, self._tos_config)
                for img in refs
            ]
        elif endpoint == "/ent/v2/start-end2video":
            # SE2V requires exactly 2 images: [start_frame_url, end_frame_url]
            body["images"] = [
                resolve_image_to_url(request.first_frame_path, self._tos_config),
                resolve_image_to_url(request.last_frame_path, self._tos_config),
            ]
        elif endpoint == "/ent/v2/img2video":
            body["images"] = [resolve_image_to_url(i2v_source, self._tos_config)]

        async with self._client() as client:
            resp = await client.post(endpoint, json=body)
            _raise_for_status(resp, "Vidu submit")
            data = resp.json()

        task_id: str = data.get("task_id", "")
        if not task_id:
            raise RuntimeError(f"Vidu API did not return a task_id: {data}")

        return VideoJobSubmission(
            job_id=task_id,
            provider="vidu",
            estimated_seconds=max(request.duration_seconds * 15, 30),
        )

    async def check_job(self, job_id: str) -> VideoJobStatus:
        async with self._client() as client:
            resp = await client.get(f"/ent/v2/tasks/{job_id}/creations")
            _raise_for_status(resp, "Vidu poll")
            data = resp.json()

        state_str: str = (data.get("state") or "").lower()

        if state_str == "success":
            creations: list[dict] = data.get("creations") or []
            result_url = creations[0].get("url", "") if creations else ""
            return VideoJobStatus(
                job_id=job_id,
                state=VideoJobState.COMPLETED,
                progress_percent=100.0,
                result_url=result_url,
            )

        if state_str == "failed":
            err_code = data.get("err_code", "")
            return VideoJobStatus(
                job_id=job_id,
                state=VideoJobState.FAILED,
                error_message=f"Vidu generation failed (err_code={err_code})",
            )

        # created / queueing / processing → PROCESSING with estimated progress.
        progress_map = {"created": 5.0, "queueing": 10.0, "processing": 50.0}
        progress = progress_map.get(state_str, 20.0)
        return VideoJobStatus(
            job_id=job_id,
            state=VideoJobState.PROCESSING,
            progress_percent=progress,
        )

    async def download_result(self, result_url: str, output_path: str) -> None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
            resp = await client.get(result_url)
            _raise_for_status(resp, "Vidu download")
            Path(output_path).write_bytes(resp.content)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _client(self) -> httpx.AsyncClient:
        headers = {
            "Authorization": f"Token {self._api_key}",
            "Content-Type": "application/json",
            **self._custom_headers,
        }
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=300,
            follow_redirects=True,
        )


def _raise_for_status(resp: httpx.Response, context: str) -> None:
    """Raise a readable RuntimeError on HTTP errors instead of raw httpx exceptions."""
    if resp.is_success:
        return
    try:
        detail = resp.json()
    except Exception:
        detail = resp.text[:200]
    raise RuntimeError(f"{context} failed (HTTP {resp.status_code}): {detail}")
