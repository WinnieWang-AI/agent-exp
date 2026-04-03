"""Vidu video generation provider (via Shengshu API)."""

from __future__ import annotations

from pathlib import Path

import httpx

from kimi_cli.config import VideoProviderConfig
from kimi_cli.config import TOSConfig
from kimi_cli.tools.video.providers.base import (
    GenerationRequest,
    Subject,
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
        """Vidu supports audio with Q3 models, and Ref2V-Audio mode (subjects).

        Ref2V-Audio (subjects) always has audio.
        Ref2V pure: Q3 supports audio, Q2 does not.
        """
        if request.subjects:
            return True
        if request.reference_images:
            return self._model.startswith("viduq3")
        return "q3" in self._model

    async def submit_job(self, request: GenerationRequest) -> VideoJobSubmission:
        # Detect mode following ace-backend-go detectVideoMode logic:
        #   1. SE2V: requires BOTH first_frame AND last_frame
        #   2. Ref2V-Audio: has subjects (character consistency + audio)
        #   3. Ref2V: has reference_images (character consistency, pure video)
        #   4. I2V: has a single source image (reference_image_path or first_frame_path)
        #   5. T2V: text only
        has_both_frames = bool(request.first_frame_path and request.last_frame_path)
        has_subjects = bool(request.subjects)
        has_refs = bool(request.reference_images)
        i2v_source = request.reference_image_path or request.first_frame_path

        if has_subjects:
            mode = "reference2video-audio"
        elif has_refs:
            mode = "reference2video"
        elif has_both_frames:
            mode = "start-end2video"
        elif i2v_source:
            mode = "img2video"
        else:
            mode = "text2video"

        # Model selection per mode.
        model = self._model
        is_q3 = model.startswith("viduq3")
        if mode == "reference2video-audio":
            # Ref2V-Audio still locked to viduq2 per Vidu API constraint.
            model = "viduq2"
        elif mode == "reference2video":
            # Ref2V: viduq3-pro not supported, use viduq3 (higher quality than turbo); Q2 falls back to viduq2.
            if is_q3:
                model = "viduq3"
            else:
                model = "viduq2"
        elif mode == "start-end2video" and model == "viduq2":
            model = "viduq2-pro"

        endpoint = f"/ent/v2/{mode if mode != 'reference2video-audio' else 'reference2video'}"

        body: dict = {
            "model": model,
            "prompt": request.prompt,
            "duration": int(request.duration_seconds),
            "resolution": "1080p",
        }

        # aspect_ratio is supported by T2V, Ref2V, and Ref2V-Audio.
        if mode in ("text2video", "reference2video", "reference2video-audio"):
            aspect_ratio = request.aspect_ratio if request.aspect_ratio in _VALID_ASPECT_RATIOS else "16:9"
            body["aspect_ratio"] = aspect_ratio

        # Q3 models support audio-video sync by default.
        if "q3" in model:
            body["audio"] = True
            body["moderation"] = "disabled"

        # Ref2V-Audio: use subjects structure (with audio always on).
        if mode == "reference2video-audio":
            body["audio"] = True
            body["subjects"] = [
                self._build_subject(subj) for subj in request.subjects
            ]
        elif mode == "reference2video":
            refs = request.reference_images[:7]
            body["images"] = [
                resolve_image_to_url(img, self._tos_config)
                for img in refs
            ]
        elif mode == "start-end2video":
            body["images"] = [
                resolve_image_to_url(request.first_frame_path, self._tos_config),
                resolve_image_to_url(request.last_frame_path, self._tos_config),
            ]
        elif mode == "img2video":
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

    def _build_subject(self, subj: Subject) -> dict:
        """Build a subject dict for the Ref2V-Audio API."""
        result: dict = {
            "id": subj.id,
            "images": [
                resolve_image_to_url(img, self._tos_config)
                for img in subj.images[:3]
            ],
        }
        if subj.voice_id:
            result["voice_id"] = subj.voice_id
        return result

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
