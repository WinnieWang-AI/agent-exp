"""Tests for audio tools (GenerateMusic, CheckMusicJob, GenerateSpeech)."""

from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from pydantic import SecretStr

from kimi_cli.config import Config, MusicProviderConfig, TTSProviderConfig, get_default_config
from kimi_cli.tools.audio.providers.base import (
    MusicGenerationRequest,
    MusicJobState,
    MusicSong,
    TTSRequest,
)


@contextmanager
def _tool_call_context(tool_name: str) -> Generator[None]:
    """Create a tool call context for testing tools that require approval."""
    from kimi_cli.soul.toolset import current_tool_call
    from kimi_cli.wire.types import ToolCall

    token = current_tool_call.set(
        ToolCall(id="test", function=ToolCall.FunctionBody(name=tool_name, arguments=None))
    )
    try:
        yield
    finally:
        current_tool_call.reset(token)


# ==============================================================================
# Suno Music Provider Tests
# ==============================================================================


class TestSunoMusicProvider:
    """Tests for the Suno music provider (using httpx mock)."""

    def test_provider_init(self):
        from kimi_cli.tools.audio.providers.suno import SunoMusicProvider

        config = MusicProviderConfig(
            type="suno",
            api_key=SecretStr("test-suno-key"),
            base_url="https://api.musicgpt.com",
        )
        provider = SunoMusicProvider(config)
        assert provider._base_url == "https://api.musicgpt.com"
        assert provider._api_key == "test-suno-key"

    def test_provider_defaults(self):
        from kimi_cli.tools.audio.providers.suno import SunoMusicProvider

        config = MusicProviderConfig(type="suno", api_key=SecretStr("k"))
        provider = SunoMusicProvider(config)
        assert provider._base_url == "https://api.musicgpt.com"

    @pytest.mark.asyncio
    async def test_submit_job(self, httpx_mock):
        from kimi_cli.tools.audio.providers.suno import SunoMusicProvider

        httpx_mock.add_response(
            url="https://api.musicgpt.com/api/public/v1/MusicAI",
            method="POST",
            json={
                "success": True,
                "task_id": "suno_task_123",
                "conversion_type": "MUSIC_AI",
                "eta": 90,
            },
        )

        config = MusicProviderConfig(type="suno", api_key=SecretStr("test-key"))
        provider = SunoMusicProvider(config)
        request = MusicGenerationRequest(
            prompt="upbeat pop song",
            music_style="pop, energetic",
            make_instrumental=True,
        )
        submission = await provider.submit_job(request)

        assert submission.job_id == "suno_task_123:MUSIC_AI"
        assert submission.provider == "suno"
        assert submission.estimated_seconds == 90.0

        # Verify request body
        sent = httpx_mock.get_request()
        body = json.loads(sent.content)
        assert body["prompt"] == "upbeat pop song"
        assert body["music_style"] == "pop, energetic"
        assert body["make_instrumental"] is True
        assert sent.headers["authorization"] == "test-key"

    @pytest.mark.asyncio
    async def test_submit_job_failure(self, httpx_mock):
        from kimi_cli.tools.audio.providers.suno import SunoMusicProvider

        httpx_mock.add_response(
            url="https://api.musicgpt.com/api/public/v1/MusicAI",
            method="POST",
            json={
                "success": False,
                "message": "Content blocked",
                "is_flagged": True,
                "reason": "sensitive content",
            },
        )

        config = MusicProviderConfig(type="suno", api_key=SecretStr("k"))
        provider = SunoMusicProvider(config)
        request = MusicGenerationRequest(prompt="test")

        with pytest.raises(RuntimeError, match="Content blocked.*flagged"):
            await provider.submit_job(request)

    @pytest.mark.asyncio
    async def test_check_job_completed(self, httpx_mock):
        from kimi_cli.tools.audio.providers.suno import SunoMusicProvider

        httpx_mock.add_response(
            json={
                "success": True,
                "task_id": "suno_task_123",
                "data": [
                    {
                        "id": "song_1",
                        "audio_url": "https://cdn.suno.com/song1.mp3",
                        "title": "Summer Vibes",
                        "duration": 120,
                        "lyric": "La la la...",
                        "style": "pop",
                    },
                    {
                        "id": "song_2",
                        "audio_url": "https://cdn.suno.com/song2.mp3",
                        "title": "Summer Vibes 2",
                        "duration": 115,
                        "lyric": "Do do do...",
                        "style": "pop",
                    },
                ],
                "conversion": {"status": "COMPLETED", "message": ""},
            },
        )

        config = MusicProviderConfig(type="suno", api_key=SecretStr("k"))
        provider = SunoMusicProvider(config)
        status = await provider.check_job("suno_task_123:MUSIC_AI")

        assert status.state == MusicJobState.COMPLETED
        assert status.progress_percent == 100.0
        assert len(status.songs) == 2
        assert status.songs[0].title == "Summer Vibes"
        assert status.songs[0].audio_url == "https://cdn.suno.com/song1.mp3"
        assert status.songs[0].duration_seconds == 120.0
        assert status.songs[1].title == "Summer Vibes 2"

    @pytest.mark.asyncio
    async def test_check_job_processing(self, httpx_mock):
        from kimi_cli.tools.audio.providers.suno import SunoMusicProvider

        httpx_mock.add_response(
            json={
                "success": True,
                "task_id": "suno_task_123",
                "data": [],
                "conversion": {"status": "IN_PROGRESS", "message": "Generating..."},
            },
        )

        config = MusicProviderConfig(type="suno", api_key=SecretStr("k"))
        provider = SunoMusicProvider(config)
        status = await provider.check_job("suno_task_123:MUSIC_AI")

        assert status.state == MusicJobState.PROCESSING
        assert status.progress_percent == 50.0
        assert len(status.songs) == 0

    @pytest.mark.asyncio
    async def test_check_job_pending(self, httpx_mock):
        from kimi_cli.tools.audio.providers.suno import SunoMusicProvider

        httpx_mock.add_response(
            json={
                "success": True,
                "data": [],
                "conversion": {"status": "IN_QUEUE"},
            },
        )

        config = MusicProviderConfig(type="suno", api_key=SecretStr("k"))
        provider = SunoMusicProvider(config)
        status = await provider.check_job("suno_task_123:MUSIC_AI")

        assert status.state == MusicJobState.PENDING
        assert status.progress_percent == 10.0

    @pytest.mark.asyncio
    async def test_check_job_failed(self, httpx_mock):
        from kimi_cli.tools.audio.providers.suno import SunoMusicProvider

        httpx_mock.add_response(
            json={
                "success": True,
                "data": [],
                "conversion": {"status": "FAILED", "message": "Generation timed out"},
            },
        )

        config = MusicProviderConfig(type="suno", api_key=SecretStr("k"))
        provider = SunoMusicProvider(config)
        status = await provider.check_job("suno_task_123:MUSIC_AI")

        assert status.state == MusicJobState.FAILED
        assert "timed out" in status.error_message

    @pytest.mark.asyncio
    async def test_check_job_fallback_to_conversion_urls(self, httpx_mock):
        """When data array has < 2 songs, fall back to conversion paths."""
        from kimi_cli.tools.audio.providers.suno import SunoMusicProvider

        httpx_mock.add_response(
            json={
                "success": True,
                "data": [],
                "conversion": {
                    "status": "COMPLETED",
                    "conversion_path_1": "https://cdn.suno.com/conv1.mp3",
                    "conversion_duration_1": 100.5,
                    "title_1": "Song A",
                    "lyrics_1": "Hey hey...",
                    "conversion_path_2": "https://cdn.suno.com/conv2.mp3",
                    "conversion_duration_2": 95.0,
                    "title_2": "Song B",
                    "lyrics_2": "Yo yo...",
                },
            },
        )

        config = MusicProviderConfig(type="suno", api_key=SecretStr("k"))
        provider = SunoMusicProvider(config)
        status = await provider.check_job("task:MUSIC_AI")

        assert status.state == MusicJobState.COMPLETED
        assert len(status.songs) == 2
        assert status.songs[0].audio_url == "https://cdn.suno.com/conv1.mp3"
        assert status.songs[0].title == "Song A"
        assert status.songs[0].duration_seconds == 100.5
        assert status.songs[1].audio_url == "https://cdn.suno.com/conv2.mp3"

    @pytest.mark.asyncio
    async def test_download_audio(self, httpx_mock, tmp_path):
        from kimi_cli.tools.audio.providers.suno import SunoMusicProvider

        httpx_mock.add_response(
            url="https://cdn.suno.com/song.mp3",
            content=b"fake-audio-bytes",
        )

        config = MusicProviderConfig(type="suno", api_key=SecretStr("k"))
        provider = SunoMusicProvider(config)
        out = str(tmp_path / "song.mp3")
        await provider.download_audio("https://cdn.suno.com/song.mp3", out)

        assert Path(out).read_bytes() == b"fake-audio-bytes"

    @pytest.mark.asyncio
    async def test_submit_job_http_error(self, httpx_mock):
        from kimi_cli.tools.audio.providers.suno import SunoMusicProvider

        httpx_mock.add_response(status_code=401, json={"error": "invalid api key"})

        config = MusicProviderConfig(type="suno", api_key=SecretStr("bad"))
        provider = SunoMusicProvider(config)
        request = MusicGenerationRequest(prompt="test")
        with pytest.raises(Exception):
            await provider.submit_job(request)


# ==============================================================================
# Minimax TTS Provider Tests
# ==============================================================================


class TestMinimaxTTSProvider:
    """Tests for the Minimax TTS provider (using httpx mock)."""

    def test_provider_init(self):
        from kimi_cli.tools.audio.providers.minimax import MinimaxTTSProvider

        config = TTSProviderConfig(
            type="minimax",
            api_key=SecretStr("test-minimax-key"),
            group_id="grp-001",
            model_name="speech-2.5-turbo-preview",
        )
        provider = MinimaxTTSProvider(config)
        assert provider._api_key == "test-minimax-key"
        assert provider._group_id == "grp-001"
        assert provider._model_name == "speech-2.5-turbo-preview"

    def test_provider_defaults(self):
        from kimi_cli.tools.audio.providers.minimax import MinimaxTTSProvider

        config = TTSProviderConfig(type="minimax", api_key=SecretStr("k"), group_id="g")
        provider = MinimaxTTSProvider(config)
        assert provider._model_name == "speech-01-tts"
        assert "subsup.net" in provider._base_url

    @pytest.mark.asyncio
    async def test_generate_speech_success(self, httpx_mock):
        from kimi_cli.tools.audio.providers.minimax import MinimaxTTSProvider

        httpx_mock.add_response(
            method="POST",
            json={
                "data": {"audio": "https://cdn.minimax.com/audio_123.mp3"},
                "base_resp": {"status_code": 0, "status_msg": "success"},
            },
        )

        config = TTSProviderConfig(
            type="minimax",
            api_key=SecretStr("test-key"),
            group_id="grp-001",
            model_name="speech-01-tts",
        )
        provider = MinimaxTTSProvider(config)
        request = TTSRequest(
            text="Hello world",
            voice_id="male-qn-qingse",
            speed=1.0,
            language="zh",
        )
        result = await provider.generate_speech(request)

        assert result.audio_url == "https://cdn.minimax.com/audio_123.mp3"

        # Verify request body
        sent = httpx_mock.get_request()
        body = json.loads(sent.content)
        assert body["model"] == "speech-01-tts"
        assert body["text"] == "Hello world"
        assert body["language"] == "zh"
        assert body["voice_setting"]["voice_id"] == "male-qn-qingse"
        assert body["voice_setting"]["speed"] == 1.0
        assert body["audio_setting"]["format"] == "mp3"
        assert "GroupId=grp-001" in str(sent.url)
        assert sent.headers["authorization"] == "Bearer test-key"

    @pytest.mark.asyncio
    async def test_generate_speech_business_error(self, httpx_mock):
        from kimi_cli.tools.audio.providers.minimax import MinimaxTTSProvider

        httpx_mock.add_response(
            method="POST",
            json={
                "data": {"audio": ""},
                "base_resp": {"status_code": 1001, "status_msg": "Invalid voice_id"},
            },
        )

        config = TTSProviderConfig(
            type="minimax", api_key=SecretStr("k"), group_id="g"
        )
        provider = MinimaxTTSProvider(config)
        request = TTSRequest(text="test", voice_id="bad-voice")

        with pytest.raises(RuntimeError, match="1001.*Invalid voice_id"):
            await provider.generate_speech(request)

    @pytest.mark.asyncio
    async def test_generate_speech_empty_audio(self, httpx_mock):
        from kimi_cli.tools.audio.providers.minimax import MinimaxTTSProvider

        httpx_mock.add_response(
            method="POST",
            json={
                "data": {"audio": ""},
                "base_resp": {"status_code": 0, "status_msg": ""},
            },
        )

        config = TTSProviderConfig(
            type="minimax", api_key=SecretStr("k"), group_id="g"
        )
        provider = MinimaxTTSProvider(config)
        request = TTSRequest(text="test")

        with pytest.raises(RuntimeError, match="empty audio URL"):
            await provider.generate_speech(request)

    @pytest.mark.asyncio
    async def test_download_audio(self, httpx_mock, tmp_path):
        from kimi_cli.tools.audio.providers.minimax import MinimaxTTSProvider

        httpx_mock.add_response(
            url="https://cdn.minimax.com/audio.mp3",
            content=b"tts-audio-bytes",
        )

        config = TTSProviderConfig(
            type="minimax", api_key=SecretStr("k"), group_id="g"
        )
        provider = MinimaxTTSProvider(config)
        out = str(tmp_path / "speech.mp3")
        await provider.download_audio("https://cdn.minimax.com/audio.mp3", out)

        assert Path(out).read_bytes() == b"tts-audio-bytes"

    @pytest.mark.asyncio
    async def test_generate_speech_http_error(self, httpx_mock):
        from kimi_cli.tools.audio.providers.minimax import MinimaxTTSProvider

        httpx_mock.add_response(status_code=500, text="Internal Server Error")

        config = TTSProviderConfig(
            type="minimax", api_key=SecretStr("k"), group_id="g"
        )
        provider = MinimaxTTSProvider(config)
        request = TTSRequest(text="test")

        with pytest.raises(Exception):
            await provider.generate_speech(request)


# ==============================================================================
# Provider Factory Tests
# ==============================================================================


class TestProviderFactory:
    """Tests for audio provider factory functions."""

    def test_create_music_provider_suno(self):
        from kimi_cli.tools.audio.providers import create_music_provider
        from kimi_cli.tools.audio.providers.suno import SunoMusicProvider

        config = MusicProviderConfig(type="suno", api_key=SecretStr("k"))
        provider = create_music_provider(config)
        assert isinstance(provider, SunoMusicProvider)

    def test_create_music_provider_unknown(self):
        from kimi_cli.tools.audio.providers import create_music_provider

        config = MusicProviderConfig(type="unknown", api_key=SecretStr("k"))
        with pytest.raises(ValueError, match="Unknown music provider"):
            create_music_provider(config)

    def test_create_tts_provider_minimax(self):
        from kimi_cli.tools.audio.providers import create_tts_provider
        from kimi_cli.tools.audio.providers.minimax import MinimaxTTSProvider

        config = TTSProviderConfig(type="minimax", api_key=SecretStr("k"), group_id="g")
        provider = create_tts_provider(config)
        assert isinstance(provider, MinimaxTTSProvider)

    def test_create_tts_provider_unknown(self):
        from kimi_cli.tools.audio.providers import create_tts_provider

        config = TTSProviderConfig(type="unknown", api_key=SecretStr("k"))
        with pytest.raises(ValueError, match="Unknown TTS provider"):
            create_tts_provider(config)

    def test_get_default_music_provider(self):
        from kimi_cli.tools.audio.providers import get_default_music_provider

        providers = {
            "suno": MusicProviderConfig(type="suno", api_key=SecretStr("k")),
        }
        name, provider = get_default_music_provider(providers)
        assert name == "suno"

    def test_get_default_music_provider_empty(self):
        from kimi_cli.tools.audio.providers import get_default_music_provider

        with pytest.raises(ValueError, match="No music providers"):
            get_default_music_provider({})

    def test_get_default_tts_provider(self):
        from kimi_cli.tools.audio.providers import get_default_tts_provider

        providers = {
            "minimax": TTSProviderConfig(type="minimax", api_key=SecretStr("k"), group_id="g"),
        }
        name, provider = get_default_tts_provider(providers)
        assert name == "minimax"

    def test_get_default_tts_provider_empty(self):
        from kimi_cli.tools.audio.providers import get_default_tts_provider

        with pytest.raises(ValueError, match="No TTS providers"):
            get_default_tts_provider({})


# ==============================================================================
# GenerateMusic Tool Tests
# ==============================================================================


class TestGenerateMusicTool:
    """Tests for the GenerateMusic tool."""

    def test_skip_when_no_music_providers(self, approval):
        from kimi_cli.tools import SkipThisTool
        from kimi_cli.tools.audio.generate_music import GenerateMusic

        config = get_default_config()
        assert config.music_providers == {}
        with pytest.raises(SkipThisTool):
            GenerateMusic(config, approval)

    def test_init_with_music_providers(self, approval):
        from kimi_cli.tools.audio.generate_music import GenerateMusic

        config = get_default_config()
        config.music_providers = {
            "suno": MusicProviderConfig(type="suno", api_key=SecretStr("k")),
        }
        tool = GenerateMusic(config, approval)
        assert tool.name == "GenerateMusic"

    @pytest.mark.asyncio
    async def test_generate_music_rejected(self, approval):
        from unittest.mock import AsyncMock, patch

        from kimi_cli.tools.audio.generate_music import GenerateMusic, Params

        config = get_default_config()
        config.music_providers = {
            "suno": MusicProviderConfig(type="suno", api_key=SecretStr("k")),
        }
        tool = GenerateMusic(config, approval)

        with _tool_call_context("GenerateMusic"), patch.object(
            approval, "request", new=AsyncMock(return_value=False)
        ):
            result = await tool(Params(prompt="test music"))
        assert "rejected" in str(result).lower() or "Rejected" in str(result)

    @pytest.mark.asyncio
    async def test_generate_music_success(self, approval):
        from unittest.mock import AsyncMock, patch

        from kimi_cli.tools.audio.generate_music import GenerateMusic, Params
        from kimi_cli.tools.audio.providers.base import MusicJobSubmission

        config = get_default_config()
        config.music_providers = {
            "suno": MusicProviderConfig(type="suno", api_key=SecretStr("k")),
        }
        tool = GenerateMusic(config, approval)

        mock_submission = MusicJobSubmission(
            job_id="suno_123:MUSIC_AI", provider="suno", estimated_seconds=90.0
        )

        with _tool_call_context("GenerateMusic"), patch(
            "kimi_cli.tools.audio.generate_music.get_default_music_provider"
        ) as mock_get:
            mock_provider = AsyncMock()
            mock_provider.submit_job.return_value = mock_submission
            mock_get.return_value = ("suno", mock_provider)

            result = await tool(Params(prompt="upbeat pop", music_style="pop"))

        output = str(result)
        assert "suno_123" in output
        assert "submitted" in output.lower() or "Job submitted" in output

    @pytest.mark.asyncio
    async def test_generate_music_provider_error(self, approval):
        from unittest.mock import AsyncMock, patch

        from kimi_cli.tools.audio.generate_music import GenerateMusic, Params

        config = get_default_config()
        config.music_providers = {
            "suno": MusicProviderConfig(type="suno", api_key=SecretStr("k")),
        }
        tool = GenerateMusic(config, approval)

        with _tool_call_context("GenerateMusic"), patch(
            "kimi_cli.tools.audio.generate_music.get_default_music_provider"
        ) as mock_get:
            mock_provider = AsyncMock()
            mock_provider.submit_job.side_effect = RuntimeError("API error")
            mock_get.return_value = ("suno", mock_provider)

            result = await tool(Params(prompt="test"))

        assert "failed" in str(result).lower() or "error" in str(result).lower()


# ==============================================================================
# CheckMusicJob Tool Tests
# ==============================================================================


class TestCheckMusicJobTool:
    """Tests for the CheckMusicJob tool."""

    def test_skip_when_no_music_providers(self):
        from kimi_cli.tools import SkipThisTool
        from kimi_cli.tools.audio.check_music_job import CheckMusicJob

        config = get_default_config()
        with pytest.raises(SkipThisTool):
            CheckMusicJob(config)

    @pytest.mark.asyncio
    async def test_check_job_completed_with_download(self, tmp_path):
        from unittest.mock import AsyncMock, patch

        from kimi_cli.tools.audio.check_music_job import CheckMusicJob, Params
        from kimi_cli.tools.audio.providers.base import MusicJobStatus

        config = get_default_config()
        config.music_providers = {
            "suno": MusicProviderConfig(type="suno", api_key=SecretStr("k")),
        }
        tool = CheckMusicJob(config)

        mock_status = MusicJobStatus(
            job_id="suno_123:MUSIC_AI",
            state=MusicJobState.COMPLETED,
            progress_percent=100.0,
            songs=[
                MusicSong(
                    audio_url="https://cdn.suno.com/song1.mp3",
                    title="Summer Vibes",
                    duration_seconds=120.0,
                    lyrics="La la la",
                    style="pop",
                ),
                MusicSong(
                    audio_url="https://cdn.suno.com/song2.mp3",
                    title="Summer Vibes 2",
                    duration_seconds=115.0,
                ),
            ],
        )

        download_dir = str(tmp_path / "music")

        with patch("kimi_cli.tools.audio.check_music_job.create_music_provider") as mock_create:
            mock_provider = AsyncMock()
            mock_provider.check_job.return_value = mock_status
            mock_create.return_value = mock_provider

            result = await tool(Params(
                job_id="suno_123:MUSIC_AI",
                provider="suno",
                download_dir=download_dir,
            ))

        output = str(result)
        assert "completed" in output.lower() or "COMPLETED" in output
        assert "Summer Vibes" in output
        assert "120" in output
        # download_audio should be called for each song
        assert mock_provider.download_audio.call_count == 2

    @pytest.mark.asyncio
    async def test_check_job_processing(self):
        from unittest.mock import AsyncMock, patch

        from kimi_cli.tools.audio.check_music_job import CheckMusicJob, Params
        from kimi_cli.tools.audio.providers.base import MusicJobStatus

        config = get_default_config()
        config.music_providers = {
            "suno": MusicProviderConfig(type="suno", api_key=SecretStr("k")),
        }
        tool = CheckMusicJob(config)

        mock_status = MusicJobStatus(
            job_id="suno_123",
            state=MusicJobState.PROCESSING,
            progress_percent=50.0,
        )

        with patch("kimi_cli.tools.audio.check_music_job.create_music_provider") as mock_create:
            mock_provider = AsyncMock()
            mock_provider.check_job.return_value = mock_status
            mock_create.return_value = mock_provider

            result = await tool(Params(job_id="suno_123", provider="suno"))

        output = str(result)
        assert "processing" in output.lower() or "50%" in output

    @pytest.mark.asyncio
    async def test_check_job_failed(self):
        from unittest.mock import AsyncMock, patch

        from kimi_cli.tools.audio.check_music_job import CheckMusicJob, Params
        from kimi_cli.tools.audio.providers.base import MusicJobStatus

        config = get_default_config()
        config.music_providers = {
            "suno": MusicProviderConfig(type="suno", api_key=SecretStr("k")),
        }
        tool = CheckMusicJob(config)

        mock_status = MusicJobStatus(
            job_id="suno_fail",
            state=MusicJobState.FAILED,
            error_message="Generation timed out",
        )

        with patch("kimi_cli.tools.audio.check_music_job.create_music_provider") as mock_create:
            mock_provider = AsyncMock()
            mock_provider.check_job.return_value = mock_status
            mock_create.return_value = mock_provider

            result = await tool(Params(job_id="suno_fail", provider="suno"))

        output = str(result)
        assert "failed" in output.lower() or "timed out" in output

    @pytest.mark.asyncio
    async def test_check_job_unknown_provider(self):
        from kimi_cli.tools.audio.check_music_job import CheckMusicJob, Params

        config = get_default_config()
        config.music_providers = {
            "suno": MusicProviderConfig(type="suno", api_key=SecretStr("k")),
        }
        tool = CheckMusicJob(config)

        result = await tool(Params(job_id="xxx", provider="nonexistent"))
        assert "not found" in str(result).lower()


# ==============================================================================
# GenerateSpeech Tool Tests
# ==============================================================================


class TestGenerateSpeechTool:
    """Tests for the GenerateSpeech tool."""

    def test_skip_when_no_tts_providers(self, approval):
        from kimi_cli.tools import SkipThisTool
        from kimi_cli.tools.audio.generate_speech import GenerateSpeech

        config = get_default_config()
        assert config.tts_providers == {}
        with pytest.raises(SkipThisTool):
            GenerateSpeech(config, approval)

    def test_init_with_tts_providers(self, approval):
        from kimi_cli.tools.audio.generate_speech import GenerateSpeech

        config = get_default_config()
        config.tts_providers = {
            "minimax": TTSProviderConfig(
                type="minimax", api_key=SecretStr("k"), group_id="g"
            ),
        }
        tool = GenerateSpeech(config, approval)
        assert tool.name == "GenerateSpeech"

    @pytest.mark.asyncio
    async def test_generate_speech_rejected(self, approval):
        from unittest.mock import AsyncMock, patch

        from kimi_cli.tools.audio.generate_speech import GenerateSpeech, Params

        config = get_default_config()
        config.tts_providers = {
            "minimax": TTSProviderConfig(
                type="minimax", api_key=SecretStr("k"), group_id="g"
            ),
        }
        tool = GenerateSpeech(config, approval)

        with _tool_call_context("GenerateSpeech"), patch.object(
            approval, "request", new=AsyncMock(return_value=False)
        ):
            result = await tool(Params(text="test", output_path="/tmp/test.mp3"))
        assert "rejected" in str(result).lower() or "Rejected" in str(result)

    @pytest.mark.asyncio
    async def test_generate_speech_success(self, tmp_path, approval):
        from unittest.mock import AsyncMock, patch

        from kimi_cli.tools.audio.generate_speech import GenerateSpeech, Params
        from kimi_cli.tools.audio.providers.base import TTSResult

        config = get_default_config()
        config.tts_providers = {
            "minimax": TTSProviderConfig(
                type="minimax", api_key=SecretStr("k"), group_id="g"
            ),
        }
        tool = GenerateSpeech(config, approval)
        output_path = str(tmp_path / "speech.mp3")

        mock_result = TTSResult(audio_url="https://cdn.minimax.com/audio.mp3")

        with _tool_call_context("GenerateSpeech"), patch(
            "kimi_cli.tools.audio.generate_speech.get_default_tts_provider"
        ) as mock_get:
            mock_provider = AsyncMock()
            mock_provider.generate_speech.return_value = mock_result
            mock_get.return_value = ("minimax", mock_provider)

            result = await tool(Params(
                text="Hello world",
                output_path=output_path,
                voice_id="male-qn-qingse",
                language="zh",
            ))

        output = str(result)
        assert "speech.mp3" in output or "saved" in output.lower()
        # Verify generate_speech was called with correct params
        call_args = mock_provider.generate_speech.call_args[0][0]
        assert call_args.text == "Hello world"
        assert call_args.voice_id == "male-qn-qingse"
        assert call_args.language == "zh"
        # Verify download was called
        mock_provider.download_audio.assert_called_once_with(
            "https://cdn.minimax.com/audio.mp3", output_path
        )

    @pytest.mark.asyncio
    async def test_generate_speech_tts_error(self, tmp_path, approval):
        from unittest.mock import AsyncMock, patch

        from kimi_cli.tools.audio.generate_speech import GenerateSpeech, Params

        config = get_default_config()
        config.tts_providers = {
            "minimax": TTSProviderConfig(
                type="minimax", api_key=SecretStr("k"), group_id="g"
            ),
        }
        tool = GenerateSpeech(config, approval)

        with _tool_call_context("GenerateSpeech"), patch(
            "kimi_cli.tools.audio.generate_speech.get_default_tts_provider"
        ) as mock_get:
            mock_provider = AsyncMock()
            mock_provider.generate_speech.side_effect = RuntimeError("TTS API error")
            mock_get.return_value = ("minimax", mock_provider)

            result = await tool(Params(
                text="test", output_path=str(tmp_path / "out.mp3")
            ))

        assert "failed" in str(result).lower() or "error" in str(result).lower()

    @pytest.mark.asyncio
    async def test_generate_speech_download_error(self, tmp_path, approval):
        from unittest.mock import AsyncMock, patch

        from kimi_cli.tools.audio.generate_speech import GenerateSpeech, Params
        from kimi_cli.tools.audio.providers.base import TTSResult

        config = get_default_config()
        config.tts_providers = {
            "minimax": TTSProviderConfig(
                type="minimax", api_key=SecretStr("k"), group_id="g"
            ),
        }
        tool = GenerateSpeech(config, approval)

        mock_result = TTSResult(audio_url="https://cdn.minimax.com/audio.mp3")

        with _tool_call_context("GenerateSpeech"), patch(
            "kimi_cli.tools.audio.generate_speech.get_default_tts_provider"
        ) as mock_get:
            mock_provider = AsyncMock()
            mock_provider.generate_speech.return_value = mock_result
            mock_provider.download_audio.side_effect = RuntimeError("Download failed")
            mock_get.return_value = ("minimax", mock_provider)

            result = await tool(Params(
                text="test", output_path=str(tmp_path / "out.mp3")
            ))

        assert "download" in str(result).lower() and "failed" in str(result).lower()
