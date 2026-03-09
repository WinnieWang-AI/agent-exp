from __future__ import annotations

from pathlib import Path

import httpx

from kimi_cli.config import TTSProviderConfig
from kimi_cli.tools.audio.providers.base import (
    TTSProvider,
    TTSRequest,
    TTSResult,
)

DEFAULT_BASE_URL = "https://gcp-api.subsup.net/v1"
TTS_PATH = "/t2a_v2"


class MinimaxTTSProvider(TTSProvider):
    def __init__(self, config: TTSProviderConfig):
        self._config = config
        self._base_url = config.base_url or DEFAULT_BASE_URL
        self._api_key = config.api_key.get_secret_value()
        self._group_id = config.group_id
        self._model_name = config.model_name or "speech-01-tts"

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=30.0),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    async def generate_speech(self, request: TTSRequest) -> TTSResult:
        url = f"{self._base_url}{TTS_PATH}?GroupId={self._group_id}"
        payload = {
            "model": self._model_name,
            "text": request.text,
            "language": request.language,
            "output_format": "url",
            "voice_setting": {
                "voice_id": request.voice_id,
                "speed": request.speed,
                "vol": request.vol,
                "pitch": request.pitch,
            },
            "audio_setting": {
                "channel": 2,
                "format": "mp3",
                "sample_rate": 32000,
                "bit_rate": 128000,
            },
        }

        async with self._client() as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        base_resp = data.get("base_resp", {})
        if base_resp.get("status_code", 0) != 0:
            raise RuntimeError(
                f"Minimax TTS error: [{base_resp.get('status_code')}] {base_resp.get('status_msg', '')}"
            )

        audio_url = data.get("data", {}).get("audio", "")
        if not audio_url:
            raise RuntimeError("Minimax TTS returned empty audio URL")

        return TTSResult(audio_url=audio_url)

    async def download_audio(self, audio_url: str, output_path: str) -> None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        # Use a plain client without Authorization header for CDN downloads.
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=30.0)) as client:
            resp = await client.get(audio_url)
            resp.raise_for_status()
            Path(output_path).write_bytes(resp.content)
