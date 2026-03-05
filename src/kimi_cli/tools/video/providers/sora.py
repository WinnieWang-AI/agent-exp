"""Sora video generation provider (via Sora2Geneasy API)."""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import httpx

from kimi_cli.config import VideoProviderConfig
from kimi_cli.tools.video.providers.base import (
    GenerationRequest,
    VideoJobState,
    VideoJobStatus,
    VideoJobSubmission,
    VideoProvider,
)

# Aspect ratio → resolution mapping used by the Sora2Geneasy API.
_ASPECT_RATIO_TO_SIZE: dict[str, str] = {
    "16:9": "1280x720",
    "9:16": "720x1280",
    "1:1": "720x720",
}

_DEFAULT_MODEL = "sora-2"
_DEFAULT_BASE_URL = "https://api.geneasy.com"


class SoraVideoProvider(VideoProvider):
    """Sora video generation provider using the Sora2Geneasy API.

    API contract (derived from ace-backend-go):
      - Submit: POST {base_url}/v1/videos/generations
      - Poll:   GET  {base_url}/v1/videos/generations?model={model}&taskId={task_id}
      - Auth:   Authorization: Bearer {api_key}
      - States: PENDING → RUNNING → SUCCEEDED | FAILED
      - Result: ``data[].url`` (HTTP URL) or ``data[].b64_json`` (base-64 encoded video)
    """

    def __init__(self, config: VideoProviderConfig) -> None:
        self._base_url = (config.base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._api_key = config.api_key.get_secret_value()
        self._model = config.model_name or _DEFAULT_MODEL
        self._custom_headers = config.custom_headers or {}

    # ------------------------------------------------------------------
    # VideoProvider interface
    # ------------------------------------------------------------------

    async def submit_job(self, request: GenerationRequest) -> VideoJobSubmission:
        size = _ASPECT_RATIO_TO_SIZE.get(request.aspect_ratio, "1280x720")

        body: dict = {
            "model": self._model,
            "prompt": request.prompt,
            "durationSeconds": int(request.duration_seconds),
            "size": size,
        }

        # Image-to-video: attach reference image URL.
        if request.mode == "image_to_video" and request.reference_image_path:
            body["images"] = [{"url": request.reference_image_path}]

        async with self._client() as client:
            resp = await client.post("/v1/videos/generations", json=body)
            _raise_for_status(resp, "Sora submit")
            data = resp.json()

        task_id: str = data.get("task_id") or data.get("taskId", "")
        if not task_id:
            raise RuntimeError(f"Sora API did not return a task_id: {data}")

        return VideoJobSubmission(
            job_id=task_id,
            provider="sora",
            estimated_seconds=max(request.duration_seconds * 20, 60),
        )

    async def check_job(self, job_id: str) -> VideoJobStatus:
        async with self._client() as client:
            resp = await client.get(
                "/v1/videos/generations",
                params={"model": self._model, "taskId": job_id},
            )
            _raise_for_status(resp, "Sora poll")
            data = resp.json()

        status_str: str = (data.get("status") or "").upper()
        done: bool = data.get("done", False)

        # Check FAILED first — a completed-but-failed job also has done=True.
        if status_str == "FAILED":
            err = data.get("error") or {}
            message = err.get("message", "") if isinstance(err, dict) else str(err)
            return VideoJobStatus(
                job_id=job_id,
                state=VideoJobState.FAILED,
                error_message=message or "Sora generation failed",
            )

        if status_str == "SUCCEEDED" or done:
            result_url = ""
            video_items: list[dict] = data.get("data") or []
            if video_items:
                result_url = video_items[0].get("url", "")
                # If no direct URL, the API returned base64-encoded video data.
                # Persist it to a temp file so download_result can work statelessly
                # (the provider instance may be recreated between check and download).
                if not result_url and video_items[0].get("b64_json"):
                    result_url = _persist_b64_to_tempfile(video_items[0]["b64_json"])
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

        # Local file produced by _persist_b64_to_tempfile during check_job.
        if result_url.startswith("file://"):
            src = Path(result_url.removeprefix("file://"))
            if not src.exists():
                raise RuntimeError(f"Temp video file not found: {src}")
            Path(output_path).write_bytes(src.read_bytes())
            src.unlink(missing_ok=True)
            return

        # Normal HTTP download.
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
            resp = await client.get(result_url)
            _raise_for_status(resp, "Sora download")
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


def _persist_b64_to_tempfile(payload: str) -> str:
    """Decode a base64 video payload and write it to a temp file.

    Returns a ``file://`` URI pointing to the temp file so that
    ``download_result`` can pick it up without any in-memory state.
    """
    # Strip data-uri prefix if present (e.g. "data:video/mp4;base64,...").
    if "," in payload:
        payload = payload.split(",", 1)[1]
    video_bytes = base64.b64decode(payload)
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.write(video_bytes)
    tmp.close()
    return f"file://{tmp.name}"


def _raise_for_status(resp: httpx.Response, context: str) -> None:
    """Raise a readable RuntimeError on HTTP errors instead of raw httpx exceptions."""
    if resp.is_success:
        return
    try:
        detail = resp.json()
    except Exception:
        detail = resp.text[:200]
    raise RuntimeError(f"{context} failed (HTTP {resp.status_code}): {detail}")
