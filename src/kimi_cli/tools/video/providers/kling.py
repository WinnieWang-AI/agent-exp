"""Kling (可灵) video generation provider (via Kling26 API)."""

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

_DEFAULT_MODEL = "kling-video-o3"
_DEFAULT_BASE_URL = "https://api.klingai.com"


class KlingVideoProvider(VideoProvider):
    """Kling video generation provider using the Kling26 API.

    API contract (derived from ace-backend-go):
      - Submit: POST {base_url}/v1/videos/generations
      - Poll:   GET  {base_url}/v1/videos/generations?model={model}&taskId={task_id}
      - Auth:   Authorization: Bearer {api_key}
      - States: PENDING → RUNNING → SUCCEEDED | FAILED
      - Result: ``data[].url`` (HTTP URL)
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

    async def submit_job(self, request: GenerationRequest) -> VideoJobSubmission:
        body: dict = {
            "model": self._model,
            "prompt": request.prompt,
            "durationSeconds": int(request.duration_seconds),
            "aspectRatio": request.aspect_ratio,
            "generateAudio": True,
        }

        # Image-to-video: attach single reference image as starting frame.
        if request.mode == "image_to_video" and request.reference_image_path:
            body["image"] = {"url": resolve_image_to_url(request.reference_image_path, self._tos_config)}

        # Multi-reference images (max 4) for reference_to_video and image_to_video modes.
        # Referenced in prompt as <<<image_1>>>, <<<image_2>>> etc.
        if request.mode in ("reference_to_video", "image_to_video") and request.reference_images:
            images = request.reference_images[:4]
            body["images"] = [
                {"url": resolve_image_to_url(img, self._tos_config)}
                for img in images
            ]

        # First-last-frame (FLF) mode.
        if request.first_frame_path:
            body["firstFrame"] = resolve_image_to_url(request.first_frame_path, self._tos_config)
        if request.last_frame_path:
            body["lastFrame"] = resolve_image_to_url(request.last_frame_path, self._tos_config)

        async with self._client() as client:
            resp = await client.post("/v1/videos/generations", json=body)
            _raise_for_status(resp, "Kling submit")
            data = resp.json()

        task_id: str = data.get("taskId") or data.get("task_id", "")
        if not task_id:
            raise RuntimeError(f"Kling API did not return a taskId: {data}")

        return VideoJobSubmission(
            job_id=task_id,
            provider="kling",
            estimated_seconds=max(request.duration_seconds * 20, 60),
        )

    async def check_job(self, job_id: str) -> VideoJobStatus:
        async with self._client() as client:
            resp = await client.get(
                "/v1/videos/generations",
                params={"model": self._model, "taskId": job_id},
            )
            _raise_for_status(resp, "Kling poll")
            data = resp.json()

        status_str: str = (data.get("status") or "").upper()
        done: bool = data.get("done", False)

        # Check FAILED first — a completed-but-failed job also has done=True.
        if status_str == "FAILED":
            err = data.get("error") or {}
            code = err.get("code", "") if isinstance(err, dict) else ""
            message = err.get("message", "") if isinstance(err, dict) else str(err)
            return VideoJobStatus(
                job_id=job_id,
                state=VideoJobState.FAILED,
                error_message=message or f"Kling generation failed (code={code})",
            )

        if status_str == "SUCCEEDED" or done:
            result_url = ""
            video_items: list[dict] = data.get("data") or []
            if video_items:
                result_url = video_items[0].get("url", "")
            return VideoJobStatus(
                job_id=job_id,
                state=VideoJobState.COMPLETED,
                progress_percent=100.0,
                result_url=result_url,
            )

        # PENDING or RUNNING → map to our states.
        progress = 10.0 if status_str == "PENDING" else 50.0
        return VideoJobStatus(
            job_id=job_id,
            state=VideoJobState.PROCESSING,
            progress_percent=progress,
        )

    async def download_result(self, result_url: str, output_path: str) -> None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        # Kling video URLs are publicly accessible (no auth header needed).
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
            resp = await client.get(result_url)
            _raise_for_status(resp, "Kling download")
            Path(output_path).write_bytes(resp.content)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _client(self) -> httpx.AsyncClient:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
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
