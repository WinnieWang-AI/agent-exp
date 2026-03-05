"""ApiYi video generation provider (SSE Chat Completions protocol).

ApiYi (apiyi.com) proxies video-generation models through the standard
OpenAI Chat Completions endpoint with ``stream=true``.  Unlike other
providers that use an async task/poll model, ApiYi streams the full result
in a single SSE response, so ``submit_job`` blocks until the video URL is
available (or a timeout is reached).
"""

from __future__ import annotations

import json
import re
import uuid
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

_DEFAULT_BASE_URL = "https://api.apiyi.com"
_DEFAULT_MODEL = "sora"

# Regex to extract the video URL from the markdown link in the SSE content.
# The assistant typically returns: [点击这里](https://...)
_URL_PATTERN = re.compile(r"\[点击这里\]\((https?://[^\)]+)\)")

# Maximum time (seconds) to wait for the SSE stream to deliver the video URL.
_STREAM_TIMEOUT = 600


class ApiYiVideoProvider(VideoProvider):
    """ApiYi SSE-based video generation provider.

    Flow
    ----
    1. ``submit_job`` sends a streaming Chat Completions request and consumes
       the SSE stream until a video URL is found (or the stream ends / times out).
    2. The result is stored in ``self._results[job_id]``.
    3. ``check_job`` simply looks up ``self._results`` and returns COMPLETED.
    4. ``download_result`` performs a plain HTTP GET to fetch the video file.
    """

    def __init__(self, config: VideoProviderConfig) -> None:
        self._base_url = (config.base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._api_key = config.api_key.get_secret_value()
        self._model = config.model_name or _DEFAULT_MODEL
        self._custom_headers = config.custom_headers or {}
        # job_id → video URL (populated by submit_job)
        self._results: dict[str, str] = {}

    # ------------------------------------------------------------------
    # VideoProvider interface
    # ------------------------------------------------------------------

    async def submit_job(self, request: GenerationRequest) -> VideoJobSubmission:
        job_id = f"apiyi_{uuid.uuid4().hex[:12]}"

        prompt = request.prompt
        if request.mode == "image_to_video" and request.reference_image_path:
            prompt = f"{prompt}\nReference image: {request.reference_image_path}"

        body = {
            "model": self._model,
            "stream": True,
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }

        collected = ""
        video_url = ""

        async with self._client() as client:
            async with client.stream(
                "POST",
                "/v1/chat/completions",
                json=body,
                timeout=_STREAM_TIMEOUT,
            ) as resp:
                if not resp.is_success:
                    await resp.aread()
                    _raise_for_status(resp, "ApiYi submit")
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[len("data: "):]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    delta = (
                        chunk.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content", "")
                    )
                    collected += delta

                    match = _URL_PATTERN.search(collected)
                    if match:
                        video_url = match.group(1)
                        break

        if not video_url:
            raise RuntimeError(
                f"ApiYi stream finished without returning a video URL. "
                f"Collected content: {collected[:500]}"
            )

        self._results[job_id] = video_url

        return VideoJobSubmission(
            job_id=job_id,
            provider="apiyi",
            estimated_seconds=0,  # already done
        )

    async def check_job(self, job_id: str) -> VideoJobStatus:
        url = self._results.get(job_id)
        if url:
            return VideoJobStatus(
                job_id=job_id,
                state=VideoJobState.COMPLETED,
                progress_percent=100.0,
                result_url=url,
            )
        return VideoJobStatus(
            job_id=job_id,
            state=VideoJobState.FAILED,
            error_message=f"No result found for job {job_id}",
        )

    async def download_result(self, result_url: str, output_path: str) -> None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
            resp = await client.get(result_url)
            _raise_for_status(resp, "ApiYi download")
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
            timeout=_STREAM_TIMEOUT,
            follow_redirects=True,
        )


def _raise_for_status(resp: httpx.Response, context: str) -> None:
    """Raise a readable RuntimeError on HTTP errors."""
    if resp.is_success:
        return
    try:
        detail = resp.json()
    except Exception:
        detail = resp.text[:200]
    raise RuntimeError(f"{context} failed (HTTP {resp.status_code}): {detail}")
