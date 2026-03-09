from __future__ import annotations

from pathlib import Path

import httpx

from kimi_cli.config import MusicProviderConfig
from kimi_cli.tools.audio.providers.base import (
    MusicGenerationRequest,
    MusicJobState,
    MusicJobStatus,
    MusicJobSubmission,
    MusicProvider,
    MusicSong,
)

# API paths (relative to base_url)
GENERATE_PATH = "/api/public/v1/MusicAI"
QUERY_PATH = "/api/public/v1/byId"
DEFAULT_CONVERSION_TYPE = "MUSIC_AI"


def _normalize_base_url(base_url: str) -> str:
    """Strip trailing path components so we always get the root URL.

    Nacos may return ``https://api.musicgpt.com/api/public/v1`` while the
    provider code appends ``/api/public/v1/...`` itself.  Normalise to the
    scheme + host (+ optional port) only.
    """
    base_url = base_url.rstrip("/")
    for suffix in ("/api/public/v1", "/api/public"):
        if base_url.endswith(suffix):
            base_url = base_url[: -len(suffix)]
            break
    return base_url


class SunoMusicProvider(MusicProvider):
    def __init__(self, config: MusicProviderConfig):
        self._config = config
        self._base_url = _normalize_base_url(config.base_url or "https://api.musicgpt.com")
        self._api_key = config.api_key.get_secret_value()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=30.0),
            headers={
                "Authorization": self._api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    async def submit_job(self, request: MusicGenerationRequest) -> MusicJobSubmission:
        payload = {
            "prompt": request.prompt,
            "make_instrumental": request.make_instrumental,
        }
        if request.lyrics:
            payload["lyrics"] = request.lyrics

        url = self._base_url + GENERATE_PATH
        async with self._client() as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        if not data.get("success"):
            reason = data.get("reason", "")
            message = data.get("message", "Unknown error")
            raise RuntimeError(
                f"Suno generate failed: {message}"
                + (f" (flagged: {reason})" if data.get("is_flagged") else "")
            )

        task_id = data.get("task_id", "")
        if not task_id:
            raise RuntimeError("Suno returned empty task_id")

        conversion_type = data.get("conversion_type") or DEFAULT_CONVERSION_TYPE
        # Encode conversion_type into job_id so we can use it during polling
        job_id = f"{task_id}:{conversion_type}"

        eta = data.get("eta", 120)
        return MusicJobSubmission(
            job_id=job_id,
            provider="suno",
            estimated_seconds=float(eta),
        )

    async def check_job(self, job_id: str) -> MusicJobStatus:
        # Parse task_id and conversion_type
        if ":" in job_id:
            task_id, conversion_type = job_id.split(":", 1)
        else:
            task_id = job_id
            conversion_type = DEFAULT_CONVERSION_TYPE

        url = f"{self._base_url}{QUERY_PATH}?task_id={task_id}&conversionType={conversion_type}"
        async with self._client() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        # Status is in conversion.status
        conversion = data.get("conversion") or {}
        status = conversion.get("status", "")

        # Map to our state
        state_map = {
            "IN_QUEUE": MusicJobState.PENDING,
            "PENDING": MusicJobState.PENDING,
            "IN_PROGRESS": MusicJobState.PROCESSING,
            "COMPLETED": MusicJobState.COMPLETED,
            "FAILED": MusicJobState.FAILED,
        }
        state = state_map.get(status, MusicJobState.PROCESSING)

        # Collect songs from data array
        songs: list[MusicSong] = []
        for song_data in data.get("data", []):
            audio_url = song_data.get("audio_url", "")
            if audio_url:
                songs.append(MusicSong(
                    audio_url=audio_url,
                    title=song_data.get("title", ""),
                    duration_seconds=float(song_data.get("duration", 0)),
                    lyrics=song_data.get("lyric", ""),
                    style=song_data.get("style", ""),
                ))

        # Fallback: collect from conversion paths if data is sparse
        if len(songs) < 2 and conversion:
            conv_songs = _collect_from_conversion(conversion)
            if len(conv_songs) > len(songs):
                songs = conv_songs

        progress = 0.0
        if state == MusicJobState.COMPLETED:
            progress = 100.0
        elif state == MusicJobState.PROCESSING:
            progress = 50.0
        elif state == MusicJobState.PENDING:
            progress = 10.0

        error_message = ""
        if state == MusicJobState.FAILED:
            error_message = conversion.get("message", "") or data.get("message", "Generation failed")

        return MusicJobStatus(
            job_id=job_id,
            state=state,
            progress_percent=progress,
            songs=songs,
            error_message=error_message,
        )

    async def download_audio(self, audio_url: str, output_path: str) -> None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        # Use a plain client without Authorization header — the audio URLs
        # are on third-party CDNs (e.g. S3) that reject unknown auth headers.
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=30.0)) as client:
            resp = await client.get(audio_url)
            resp.raise_for_status()
            Path(output_path).write_bytes(resp.content)


def _collect_from_conversion(conv: dict) -> list[MusicSong]:
    songs: list[MusicSong] = []
    for suffix in ("1", "2"):
        mp3 = conv.get(f"conversion_path_{suffix}", "")
        wav = conv.get(f"conversion_path_wav_{suffix}", "")
        url = mp3 or wav
        if url:
            songs.append(MusicSong(
                audio_url=url,
                title=conv.get(f"title_{suffix}", "") or conv.get("title", ""),
                duration_seconds=float(conv.get(f"conversion_duration_{suffix}", 0)),
                lyrics=conv.get(f"lyrics_{suffix}", "") or conv.get("lyrics", ""),
            ))
    return songs
