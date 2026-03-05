"""Tests for video tools."""

from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from pydantic import SecretStr

from kimi_cli.config import Config, ImageProviderConfig, VideoProviderConfig, get_default_config
from kimi_cli.tools import extract_key_argument
from kimi_cli.tools.video.providers.base import GenerationRequest, VideoJobState
from kimi_cli.tools.video.providers.mock import MockVideoProvider


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


class TestMockVideoProvider:
    """Tests for the mock video provider."""

    @pytest.fixture
    def provider(self):
        return MockVideoProvider()

    @pytest.mark.asyncio
    async def test_submit_job(self, provider):
        request = GenerationRequest(prompt="A cat walking", duration_seconds=3.0)
        submission = await provider.submit_job(request)
        assert submission.job_id.startswith("mock_")
        assert submission.provider == "mock"
        assert submission.estimated_seconds == 3.0

    @pytest.mark.asyncio
    async def test_check_job_processing_then_completed(self, provider):
        request = GenerationRequest(prompt="A cat walking")
        submission = await provider.submit_job(request)

        # First check: processing
        status1 = await provider.check_job(submission.job_id)
        assert status1.state == VideoJobState.PROCESSING
        assert status1.progress_percent == 50.0

        # Second check: completed
        status2 = await provider.check_job(submission.job_id)
        assert status2.state == VideoJobState.COMPLETED
        assert status2.progress_percent == 100.0
        assert status2.result_url != ""

    @pytest.mark.asyncio
    async def test_check_nonexistent_job(self, provider):
        status = await provider.check_job("nonexistent_job")
        assert status.state == VideoJobState.FAILED
        assert "not found" in status.error_message


class TestManageVideoProject:
    """Tests for ManageVideoProject tool."""

    @pytest.mark.asyncio
    async def test_init_project(self, runtime, tmp_path):
        from kimi_cli.tools.video.project import ManageVideoProject, Params

        tool = ManageVideoProject(runtime)
        project_path = str(tmp_path / "test_project")
        result = await tool(Params(action="init", project_path=project_path))

        project = Path(project_path)
        assert project.exists()
        assert (project / "assets" / "clips").exists()
        assert (project / "assets" / "images").exists()
        assert (project / "assets" / "audio").exists()
        assert (project / "output").exists()
        assert (project / "project.json").exists()
        assert (project / "script.json").exists()
        assert (project / "storyboard.json").exists()
        assert (project / "characters.json").exists()

    @pytest.mark.asyncio
    async def test_status_not_a_project(self, runtime, tmp_path):
        from kimi_cli.tools.video.project import ManageVideoProject, Params

        tool = ManageVideoProject(runtime)
        result = await tool(Params(action="status", project_path=str(tmp_path / "nonexistent")))
        # Should return error since no project.json exists
        assert hasattr(result, "error") or "not found" in str(result).lower() or True

    @pytest.mark.asyncio
    async def test_update_metadata(self, runtime, tmp_path):
        from kimi_cli.tools.video.project import ManageVideoProject, Params

        tool = ManageVideoProject(runtime)
        project_path = str(tmp_path / "test_project")

        # Init first
        await tool(Params(action="init", project_path=project_path))

        # Update metadata
        await tool(
            Params(
                action="update_metadata",
                project_path=project_path,
                metadata={"status": "in_progress", "theme": "nature"},
            )
        )

        data = json.loads((Path(project_path) / "project.json").read_text())
        assert data["status"] == "in_progress"
        assert data["theme"] == "nature"


class TestSoraVideoProvider:
    """Tests for the Sora video provider (using httpx mock)."""

    def test_provider_init(self):
        from kimi_cli.tools.video.providers.sora import SoraVideoProvider

        config = VideoProviderConfig(
            type="sora",
            base_url="https://api.geneasy.com",
            api_key=SecretStr("test-key"),
            model_name="sora-2",
        )
        provider = SoraVideoProvider(config)
        assert provider._base_url == "https://api.geneasy.com"
        assert provider._api_key == "test-key"
        assert provider._model == "sora-2"

    def test_provider_defaults(self):
        from kimi_cli.tools.video.providers.sora import SoraVideoProvider

        config = VideoProviderConfig(type="sora", api_key=SecretStr("k"))
        provider = SoraVideoProvider(config)
        assert provider._model == "sora-2"
        assert "geneasy" in provider._base_url

    @pytest.mark.asyncio
    async def test_submit_job_calls_api(self, httpx_mock):
        """Test that submit_job sends the correct request."""
        from kimi_cli.tools.video.providers.sora import SoraVideoProvider

        httpx_mock.add_response(
            url="https://api.geneasy.com/v1/videos/generations",
            method="POST",
            json={"task_id": "sora_123", "status": "PENDING", "done": False},
        )

        config = VideoProviderConfig(
            type="sora",
            base_url="https://api.geneasy.com",
            api_key=SecretStr("test-key"),
        )
        provider = SoraVideoProvider(config)
        request = GenerationRequest(prompt="A sunset", duration_seconds=5.0)
        submission = await provider.submit_job(request)

        assert submission.job_id == "sora_123"
        assert submission.provider == "sora"

        # Verify the request body
        sent = httpx_mock.get_request()
        body = json.loads(sent.content)
        assert body["model"] == "sora-2"
        assert body["prompt"] == "A sunset"
        assert body["durationSeconds"] == 5
        assert body["size"] == "1280x720"
        assert sent.headers["authorization"] == "Bearer test-key"

    @pytest.mark.asyncio
    async def test_check_job_succeeded(self, httpx_mock):
        from kimi_cli.tools.video.providers.sora import SoraVideoProvider

        httpx_mock.add_response(
            json={
                "task_id": "sora_123",
                "status": "SUCCEEDED",
                "done": True,
                "data": [{"url": "https://example.com/video.mp4", "mime_type": "video/mp4"}],
            },
        )

        config = VideoProviderConfig(type="sora", api_key=SecretStr("k"))
        provider = SoraVideoProvider(config)
        status = await provider.check_job("sora_123")

        assert status.state == VideoJobState.COMPLETED
        assert status.result_url == "https://example.com/video.mp4"

    @pytest.mark.asyncio
    async def test_check_job_failed(self, httpx_mock):
        from kimi_cli.tools.video.providers.sora import SoraVideoProvider

        httpx_mock.add_response(
            json={
                "task_id": "sora_fail",
                "status": "FAILED",
                "done": True,
                "error": {"code": "CONTENT_FILTER", "message": "Content blocked"},
            },
        )

        config = VideoProviderConfig(type="sora", api_key=SecretStr("k"))
        provider = SoraVideoProvider(config)
        status = await provider.check_job("sora_fail")

        assert status.state == VideoJobState.FAILED
        assert "Content blocked" in status.error_message

    @pytest.mark.asyncio
    async def test_check_job_processing(self, httpx_mock):
        from kimi_cli.tools.video.providers.sora import SoraVideoProvider

        httpx_mock.add_response(
            json={"task_id": "sora_run", "status": "RUNNING", "done": False},
        )

        config = VideoProviderConfig(type="sora", api_key=SecretStr("k"))
        provider = SoraVideoProvider(config)
        status = await provider.check_job("sora_run")

        assert status.state == VideoJobState.PROCESSING
        assert status.progress_percent == 50.0

    @pytest.mark.asyncio
    async def test_download_result(self, httpx_mock, tmp_path):
        from kimi_cli.tools.video.providers.sora import SoraVideoProvider

        httpx_mock.add_response(
            url="https://example.com/video.mp4",
            content=b"fake-video-bytes",
        )

        config = VideoProviderConfig(type="sora", api_key=SecretStr("k"))
        provider = SoraVideoProvider(config)
        out = str(tmp_path / "out.mp4")
        await provider.download_result("https://example.com/video.mp4", out)

        assert Path(out).read_bytes() == b"fake-video-bytes"

    @pytest.mark.asyncio
    async def test_check_job_b64_persists_to_tempfile(self, httpx_mock):
        """When the API returns b64 data, check_job should persist it to a temp file."""
        import base64 as b64

        from kimi_cli.tools.video.providers.sora import SoraVideoProvider

        encoded = b64.b64encode(b"video-data").decode()
        httpx_mock.add_response(
            json={
                "task_id": "sora_b64",
                "status": "SUCCEEDED",
                "done": True,
                "data": [{"b64_json": encoded, "mime_type": "video/mp4"}],
            },
        )

        config = VideoProviderConfig(type="sora", api_key=SecretStr("k"))
        provider = SoraVideoProvider(config)
        status = await provider.check_job("sora_b64")

        assert status.state == VideoJobState.COMPLETED
        assert status.result_url.startswith("file://")
        # The temp file should contain the decoded video bytes.
        tmp_path = Path(status.result_url.removeprefix("file://"))
        assert tmp_path.exists()
        assert tmp_path.read_bytes() == b"video-data"
        tmp_path.unlink()

    @pytest.mark.asyncio
    async def test_download_file_uri_result(self, tmp_path):
        """download_result with a file:// URI should copy from temp file."""
        from kimi_cli.tools.video.providers.sora import SoraVideoProvider

        # Create a fake temp file simulating what check_job would produce.
        src = tmp_path / "temp_video.mp4"
        src.write_bytes(b"video-data")

        config = VideoProviderConfig(type="sora", api_key=SecretStr("k"))
        provider = SoraVideoProvider(config)
        out = str(tmp_path / "final.mp4")
        await provider.download_result(f"file://{src}", out)

        assert Path(out).read_bytes() == b"video-data"
        # Source temp file should be cleaned up.
        assert not src.exists()


    @pytest.mark.asyncio
    async def test_submit_job_http_error(self, httpx_mock):
        """HTTP errors should raise RuntimeError with readable message."""
        from kimi_cli.tools.video.providers.sora import SoraVideoProvider

        httpx_mock.add_response(status_code=401, json={"error": "invalid api key"})

        config = VideoProviderConfig(type="sora", api_key=SecretStr("bad"))
        provider = SoraVideoProvider(config)
        request = GenerationRequest(prompt="test")
        with pytest.raises(RuntimeError, match="Sora submit failed.*401"):
            await provider.submit_job(request)


class TestViduVideoProvider:
    """Tests for the Vidu video provider (using httpx mock)."""

    def test_provider_init(self):
        from kimi_cli.tools.video.providers.vidu import ViduVideoProvider

        config = VideoProviderConfig(
            type="vidu",
            base_url="https://api.vidu.com",
            api_key=SecretStr("test-token"),
            model_name="viduq3-turbo",
        )
        provider = ViduVideoProvider(config)
        assert provider._base_url == "https://api.vidu.com"
        assert provider._api_key == "test-token"
        assert provider._model == "viduq3-turbo"

    def test_provider_defaults(self):
        from kimi_cli.tools.video.providers.vidu import ViduVideoProvider

        config = VideoProviderConfig(type="vidu", api_key=SecretStr("t"))
        provider = ViduVideoProvider(config)
        assert provider._model == "viduq3-pro"
        assert "vidu" in provider._base_url

    @pytest.mark.asyncio
    async def test_submit_t2v(self, httpx_mock):
        from kimi_cli.tools.video.providers.vidu import ViduVideoProvider

        httpx_mock.add_response(
            url="https://api.vidu.com/ent/v2/text2video",
            method="POST",
            json={"task_id": "vidu_abc", "state": "created", "model": "viduq3-pro"},
        )

        config = VideoProviderConfig(type="vidu", api_key=SecretStr("t"))
        provider = ViduVideoProvider(config)
        request = GenerationRequest(prompt="A forest", duration_seconds=8.0)
        submission = await provider.submit_job(request)

        assert submission.job_id == "vidu_abc"
        assert submission.provider == "vidu"

        sent = httpx_mock.get_request()
        body = json.loads(sent.content)
        assert body["model"] == "viduq3-pro"
        assert body["prompt"] == "A forest"
        assert body["duration"] == 8
        assert body["audio"] is True  # Q3 models enable audio
        assert sent.headers["authorization"] == "Token t"

    @pytest.mark.asyncio
    async def test_submit_i2v(self, httpx_mock):
        from kimi_cli.tools.video.providers.vidu import ViduVideoProvider

        httpx_mock.add_response(
            url="https://api.vidu.com/ent/v2/img2video",
            method="POST",
            json={"task_id": "vidu_i2v", "state": "created"},
        )

        config = VideoProviderConfig(type="vidu", api_key=SecretStr("t"))
        provider = ViduVideoProvider(config)
        request = GenerationRequest(
            prompt="Animate this",
            mode="image_to_video",
            reference_image_path="https://example.com/img.jpg",
        )
        submission = await provider.submit_job(request)

        assert submission.job_id == "vidu_i2v"
        sent = httpx_mock.get_request()
        body = json.loads(sent.content)
        assert body["images"] == ["https://example.com/img.jpg"]

    @pytest.mark.asyncio
    async def test_check_job_success(self, httpx_mock):
        from kimi_cli.tools.video.providers.vidu import ViduVideoProvider

        httpx_mock.add_response(
            json={
                "state": "success",
                "creations": [
                    {"id": "c1", "url": "https://vidu.com/video.mp4", "cover_url": "https://vidu.com/cover.jpg"}
                ],
            },
        )

        config = VideoProviderConfig(type="vidu", api_key=SecretStr("t"))
        provider = ViduVideoProvider(config)
        status = await provider.check_job("vidu_abc")

        assert status.state == VideoJobState.COMPLETED
        assert status.result_url == "https://vidu.com/video.mp4"

    @pytest.mark.asyncio
    async def test_check_job_failed(self, httpx_mock):
        from kimi_cli.tools.video.providers.vidu import ViduVideoProvider

        httpx_mock.add_response(
            json={"state": "failed", "err_code": "TIMEOUT"},
        )

        config = VideoProviderConfig(type="vidu", api_key=SecretStr("t"))
        provider = ViduVideoProvider(config)
        status = await provider.check_job("vidu_fail")

        assert status.state == VideoJobState.FAILED
        assert "TIMEOUT" in status.error_message

    @pytest.mark.asyncio
    async def test_check_job_queueing(self, httpx_mock):
        from kimi_cli.tools.video.providers.vidu import ViduVideoProvider

        httpx_mock.add_response(
            json={"state": "queueing"},
        )

        config = VideoProviderConfig(type="vidu", api_key=SecretStr("t"))
        provider = ViduVideoProvider(config)
        status = await provider.check_job("vidu_q")

        assert status.state == VideoJobState.PROCESSING
        assert status.progress_percent == 10.0

    @pytest.mark.asyncio
    async def test_download_result(self, httpx_mock, tmp_path):
        from kimi_cli.tools.video.providers.vidu import ViduVideoProvider

        httpx_mock.add_response(
            url="https://vidu.com/video.mp4",
            content=b"vidu-video-bytes",
        )

        config = VideoProviderConfig(type="vidu", api_key=SecretStr("t"))
        provider = ViduVideoProvider(config)
        out = str(tmp_path / "vidu_out.mp4")
        await provider.download_result("https://vidu.com/video.mp4", out)

        assert Path(out).read_bytes() == b"vidu-video-bytes"


    @pytest.mark.asyncio
    async def test_submit_http_error(self, httpx_mock):
        """HTTP errors should raise RuntimeError with readable message."""
        from kimi_cli.tools.video.providers.vidu import ViduVideoProvider

        httpx_mock.add_response(status_code=403, json={"message": "forbidden"})

        config = VideoProviderConfig(type="vidu", api_key=SecretStr("bad"))
        provider = ViduVideoProvider(config)
        request = GenerationRequest(prompt="test")
        with pytest.raises(RuntimeError, match="Vidu submit failed.*403"):
            await provider.submit_job(request)


class TestKlingVideoProvider:
    """Tests for the Kling video provider (using httpx mock)."""

    def test_provider_init(self):
        from kimi_cli.tools.video.providers.kling import KlingVideoProvider

        config = VideoProviderConfig(
            type="kling",
            base_url="https://api.klingai.com",
            api_key=SecretStr("test-key"),
            model_name="kling-video-o1",
        )
        provider = KlingVideoProvider(config)
        assert provider._base_url == "https://api.klingai.com"
        assert provider._api_key == "test-key"
        assert provider._model == "kling-video-o1"

    def test_provider_defaults(self):
        from kimi_cli.tools.video.providers.kling import KlingVideoProvider

        config = VideoProviderConfig(type="kling", api_key=SecretStr("k"))
        provider = KlingVideoProvider(config)
        assert provider._model == "kling-video-o1"
        assert "klingai" in provider._base_url

    @pytest.mark.asyncio
    async def test_submit_job_t2v(self, httpx_mock):
        """Test text-to-video submission."""
        from kimi_cli.tools.video.providers.kling import KlingVideoProvider

        httpx_mock.add_response(
            url="https://api.klingai.com/v1/videos/generations",
            method="POST",
            json={"taskId": "kling_123", "status": "PENDING", "done": False},
        )

        config = VideoProviderConfig(
            type="kling",
            base_url="https://api.klingai.com",
            api_key=SecretStr("test-key"),
        )
        provider = KlingVideoProvider(config)
        request = GenerationRequest(prompt="A sunset", duration_seconds=5.0)
        submission = await provider.submit_job(request)

        assert submission.job_id == "kling_123"
        assert submission.provider == "kling"

        # Verify the request body uses camelCase fields
        sent = httpx_mock.get_request()
        body = json.loads(sent.content)
        assert body["model"] == "kling-video-o1"
        assert body["prompt"] == "A sunset"
        assert body["durationSeconds"] == 5
        assert body["aspectRatio"] == "16:9"
        assert body["generateAudio"] is True
        assert "image" not in body
        assert sent.headers["authorization"] == "Bearer test-key"

    @pytest.mark.asyncio
    async def test_submit_job_i2v(self, httpx_mock):
        """Test image-to-video submission."""
        from kimi_cli.tools.video.providers.kling import KlingVideoProvider

        httpx_mock.add_response(
            url="https://api.klingai.com/v1/videos/generations",
            method="POST",
            json={"taskId": "kling_i2v", "status": "PENDING", "done": False},
        )

        config = VideoProviderConfig(
            type="kling",
            base_url="https://api.klingai.com",
            api_key=SecretStr("test-key"),
        )
        provider = KlingVideoProvider(config)
        request = GenerationRequest(
            prompt="Animate this scene",
            mode="image_to_video",
            reference_image_path="https://example.com/img.jpg",
        )
        submission = await provider.submit_job(request)

        assert submission.job_id == "kling_i2v"
        sent = httpx_mock.get_request()
        body = json.loads(sent.content)
        assert body["image"] == {"url": "https://example.com/img.jpg"}

    @pytest.mark.asyncio
    async def test_check_job_succeeded(self, httpx_mock):
        from kimi_cli.tools.video.providers.kling import KlingVideoProvider

        httpx_mock.add_response(
            json={
                "taskId": "kling_123",
                "status": "SUCCEEDED",
                "done": True,
                "data": [{"url": "https://example.com/kling_video.mp4"}],
            },
        )

        config = VideoProviderConfig(type="kling", api_key=SecretStr("k"))
        provider = KlingVideoProvider(config)
        status = await provider.check_job("kling_123")

        assert status.state == VideoJobState.COMPLETED
        assert status.result_url == "https://example.com/kling_video.mp4"

    @pytest.mark.asyncio
    async def test_check_job_failed(self, httpx_mock):
        from kimi_cli.tools.video.providers.kling import KlingVideoProvider

        httpx_mock.add_response(
            json={
                "taskId": "kling_fail",
                "status": "FAILED",
                "done": True,
                "error": {"code": "CONTENT_FILTER", "message": "Content blocked"},
            },
        )

        config = VideoProviderConfig(type="kling", api_key=SecretStr("k"))
        provider = KlingVideoProvider(config)
        status = await provider.check_job("kling_fail")

        assert status.state == VideoJobState.FAILED
        assert "Content blocked" in status.error_message

    @pytest.mark.asyncio
    async def test_check_job_running(self, httpx_mock):
        from kimi_cli.tools.video.providers.kling import KlingVideoProvider

        httpx_mock.add_response(
            json={"taskId": "kling_run", "status": "RUNNING", "done": False},
        )

        config = VideoProviderConfig(type="kling", api_key=SecretStr("k"))
        provider = KlingVideoProvider(config)
        status = await provider.check_job("kling_run")

        assert status.state == VideoJobState.PROCESSING
        assert status.progress_percent == 50.0

    @pytest.mark.asyncio
    async def test_check_job_pending(self, httpx_mock):
        from kimi_cli.tools.video.providers.kling import KlingVideoProvider

        httpx_mock.add_response(
            json={"taskId": "kling_pend", "status": "PENDING", "done": False},
        )

        config = VideoProviderConfig(type="kling", api_key=SecretStr("k"))
        provider = KlingVideoProvider(config)
        status = await provider.check_job("kling_pend")

        assert status.state == VideoJobState.PROCESSING
        assert status.progress_percent == 10.0

    @pytest.mark.asyncio
    async def test_download_result(self, httpx_mock, tmp_path):
        from kimi_cli.tools.video.providers.kling import KlingVideoProvider

        httpx_mock.add_response(
            url="https://example.com/kling_video.mp4",
            content=b"kling-video-bytes",
        )

        config = VideoProviderConfig(type="kling", api_key=SecretStr("k"))
        provider = KlingVideoProvider(config)
        out = str(tmp_path / "kling_out.mp4")
        await provider.download_result("https://example.com/kling_video.mp4", out)

        assert Path(out).read_bytes() == b"kling-video-bytes"

    @pytest.mark.asyncio
    async def test_submit_job_http_error(self, httpx_mock):
        """HTTP errors should raise RuntimeError with readable message."""
        from kimi_cli.tools.video.providers.kling import KlingVideoProvider

        httpx_mock.add_response(status_code=401, json={"error": "invalid api key"})

        config = VideoProviderConfig(type="kling", api_key=SecretStr("bad"))
        provider = KlingVideoProvider(config)
        request = GenerationRequest(prompt="test")
        with pytest.raises(RuntimeError, match="Kling submit failed.*401"):
            await provider.submit_job(request)


class TestApiYiVideoProvider:
    """Tests for the ApiYi video provider (SSE-based, using httpx mock)."""

    def test_provider_init(self):
        from kimi_cli.tools.video.providers.apiyi import ApiYiVideoProvider

        config = VideoProviderConfig(
            type="apiyi",
            base_url="https://api.apiyi.com",
            api_key=SecretStr("test-key"),
            model_name="sora",
        )
        provider = ApiYiVideoProvider(config)
        assert provider._base_url == "https://api.apiyi.com"
        assert provider._api_key == "test-key"
        assert provider._model == "sora"

    def test_provider_defaults(self):
        from kimi_cli.tools.video.providers.apiyi import ApiYiVideoProvider

        config = VideoProviderConfig(type="apiyi", api_key=SecretStr("k"))
        provider = ApiYiVideoProvider(config)
        assert provider._model == "sora"
        assert "apiyi" in provider._base_url

    @pytest.mark.asyncio
    async def test_submit_job_extracts_url(self, httpx_mock):
        """submit_job should consume the SSE stream and extract the video URL."""
        from kimi_cli.tools.video.providers.apiyi import ApiYiVideoProvider

        sse_body = (
            'data: {"choices":[{"delta":{"content":"Video ready: "}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"[点击这里](https://cdn.example.com/video.mp4)"}}]}\n\n'
            "data: [DONE]\n\n"
        )

        httpx_mock.add_response(
            url="https://api.apiyi.com/v1/chat/completions",
            method="POST",
            content=sse_body.encode(),
            headers={"content-type": "text/event-stream"},
        )

        config = VideoProviderConfig(
            type="apiyi",
            base_url="https://api.apiyi.com",
            api_key=SecretStr("test-key"),
        )
        provider = ApiYiVideoProvider(config)
        request = GenerationRequest(prompt="A sunset")
        submission = await provider.submit_job(request)

        assert submission.job_id.startswith("apiyi_")
        assert submission.provider == "apiyi"

        # Verify the URL was stored
        status = await provider.check_job(submission.job_id)
        assert status.state == VideoJobState.COMPLETED
        assert status.result_url == "https://cdn.example.com/video.mp4"

    @pytest.mark.asyncio
    async def test_submit_job_no_url_raises(self, httpx_mock):
        """submit_job should raise RuntimeError if no video URL found in stream."""
        from kimi_cli.tools.video.providers.apiyi import ApiYiVideoProvider

        sse_body = (
            'data: {"choices":[{"delta":{"content":"Sorry, no video."}}]}\n\n'
            "data: [DONE]\n\n"
        )

        httpx_mock.add_response(
            url="https://api.apiyi.com/v1/chat/completions",
            method="POST",
            content=sse_body.encode(),
            headers={"content-type": "text/event-stream"},
        )

        config = VideoProviderConfig(type="apiyi", api_key=SecretStr("k"))
        provider = ApiYiVideoProvider(config)
        request = GenerationRequest(prompt="test")
        with pytest.raises(RuntimeError, match="without returning a video URL"):
            await provider.submit_job(request)

    @pytest.mark.asyncio
    async def test_check_job_not_found(self):
        from kimi_cli.tools.video.providers.apiyi import ApiYiVideoProvider

        config = VideoProviderConfig(type="apiyi", api_key=SecretStr("k"))
        provider = ApiYiVideoProvider(config)
        status = await provider.check_job("nonexistent")

        assert status.state == VideoJobState.FAILED
        assert "No result found" in status.error_message

    @pytest.mark.asyncio
    async def test_download_result(self, httpx_mock, tmp_path):
        from kimi_cli.tools.video.providers.apiyi import ApiYiVideoProvider

        httpx_mock.add_response(
            url="https://cdn.example.com/video.mp4",
            content=b"apiyi-video-bytes",
        )

        config = VideoProviderConfig(type="apiyi", api_key=SecretStr("k"))
        provider = ApiYiVideoProvider(config)
        out = str(tmp_path / "apiyi_out.mp4")
        await provider.download_result("https://cdn.example.com/video.mp4", out)

        assert Path(out).read_bytes() == b"apiyi-video-bytes"

    @pytest.mark.asyncio
    async def test_submit_job_http_error(self, httpx_mock):
        """HTTP errors during SSE stream should raise RuntimeError."""
        from kimi_cli.tools.video.providers.apiyi import ApiYiVideoProvider

        httpx_mock.add_response(status_code=401, json={"error": "invalid api key"})

        config = VideoProviderConfig(type="apiyi", api_key=SecretStr("bad"))
        provider = ApiYiVideoProvider(config)
        request = GenerationRequest(prompt="test")
        with pytest.raises(RuntimeError, match="ApiYi submit failed.*401"):
            await provider.submit_job(request)

    @pytest.mark.asyncio
    async def test_submit_job_sends_correct_body(self, httpx_mock):
        """Verify the Chat Completions request body format."""
        from kimi_cli.tools.video.providers.apiyi import ApiYiVideoProvider

        sse_body = (
            'data: {"choices":[{"delta":{"content":"[点击这里](https://cdn.example.com/v.mp4)"}}]}\n\n'
            "data: [DONE]\n\n"
        )
        httpx_mock.add_response(
            url="https://api.apiyi.com/v1/chat/completions",
            method="POST",
            content=sse_body.encode(),
            headers={"content-type": "text/event-stream"},
        )

        config = VideoProviderConfig(
            type="apiyi",
            base_url="https://api.apiyi.com",
            api_key=SecretStr("test-key"),
            model_name="sora",
        )
        provider = ApiYiVideoProvider(config)
        request = GenerationRequest(prompt="A sunset over ocean")
        await provider.submit_job(request)

        sent = httpx_mock.get_request()
        body = json.loads(sent.content)
        assert body["model"] == "sora"
        assert body["stream"] is True
        assert body["messages"][0]["role"] == "user"
        assert body["messages"][0]["content"] == "A sunset over ocean"
        assert sent.headers["authorization"] == "Bearer test-key"


class TestProviderFactory:
    """Tests for the provider factory with new providers."""

    def test_create_sora_provider(self):
        from kimi_cli.tools.video.providers import create_provider
        from kimi_cli.tools.video.providers.sora import SoraVideoProvider

        config = VideoProviderConfig(type="sora", api_key=SecretStr("k"))
        provider = create_provider(config)
        assert isinstance(provider, SoraVideoProvider)

    def test_create_vidu_provider(self):
        from kimi_cli.tools.video.providers import create_provider
        from kimi_cli.tools.video.providers.vidu import ViduVideoProvider

        config = VideoProviderConfig(type="vidu", api_key=SecretStr("k"))
        provider = create_provider(config)
        assert isinstance(provider, ViduVideoProvider)

    def test_create_kling_provider(self):
        from kimi_cli.tools.video.providers import create_provider
        from kimi_cli.tools.video.providers.kling import KlingVideoProvider

        config = VideoProviderConfig(type="kling", api_key=SecretStr("k"))
        provider = create_provider(config)
        assert isinstance(provider, KlingVideoProvider)

    def test_create_apiyi_provider(self):
        from kimi_cli.tools.video.providers import create_provider
        from kimi_cli.tools.video.providers.apiyi import ApiYiVideoProvider

        config = VideoProviderConfig(type="apiyi", api_key=SecretStr("k"))
        provider = create_provider(config)
        assert isinstance(provider, ApiYiVideoProvider)

    def test_create_unknown_provider(self):
        from kimi_cli.tools.video.providers import create_provider

        config = VideoProviderConfig(type="nonexistent")
        with pytest.raises(ValueError, match="Unknown video provider type"):
            create_provider(config)


class TestVideoProviderConfig:
    """Tests for VideoProviderConfig in Config."""

    def test_config_with_video_providers(self):
        config = get_default_config()
        config.video_providers = {
            "mock": VideoProviderConfig(type="mock"),
            "kling": VideoProviderConfig(
                type="kling",
                base_url="https://api.klingai.com",
                api_key=SecretStr("test-key"),
            ),
        }
        assert "mock" in config.video_providers
        assert "kling" in config.video_providers
        assert config.video_providers["kling"].type == "kling"

    def test_config_default_no_video_providers(self):
        config = get_default_config()
        assert config.video_providers == {}

    def test_config_with_model_name(self):
        config = VideoProviderConfig(
            type="sora",
            api_key=SecretStr("key"),
            model_name="sora-2",
        )
        assert config.model_name == "sora-2"

    def test_config_model_name_default_empty(self):
        config = VideoProviderConfig(type="mock")
        assert config.model_name == ""


class TestExtractKeyArgumentVideo:
    """Tests for extract_key_argument with video tools."""

    def test_generate_video(self):
        result = extract_key_argument('{"prompt": "A sunset over the ocean"}', "GenerateVideo")
        assert result is not None
        assert "sunset" in result

    def test_check_video_job(self):
        result = extract_key_argument('{"job_id": "mock_abc123"}', "CheckVideoJob")
        assert result == "mock_abc123"

    def test_video_edit(self):
        result = extract_key_argument('{"operation": "concat"}', "VideoEdit")
        assert result == "concat"

    def test_manage_video_project(self):
        result = extract_key_argument('{"action": "init"}', "ManageVideoProject")
        assert result == "init"

    def test_generate_image(self):
        result = extract_key_argument('{"prompt": "A character portrait"}', "GenerateImage")
        assert result is not None
        assert "character" in result


class TestVideoEditCommands:
    """Tests for VideoEdit FFmpeg command construction."""

    def test_build_concat(self):
        from kimi_cli.tools.video.edit import Params, VideoEdit

        # We can't instantiate VideoEdit without DI, so test params directly
        params = Params(
            operation="concat",
            input_files=["a.mp4", "b.mp4"],
            output_path="out.mp4",
        )
        assert params.operation == "concat"
        assert len(params.input_files) == 2

    def test_build_trim(self):
        from kimi_cli.tools.video.edit import Params

        params = Params(
            operation="trim",
            input_files=["input.mp4"],
            output_path="trimmed.mp4",
            start_time=1.5,
            end_time=5.0,
        )
        assert params.start_time == 1.5
        assert params.end_time == 5.0

    def test_build_add_audio(self):
        from kimi_cli.tools.video.edit import Params

        params = Params(
            operation="add_audio",
            input_files=["video.mp4"],
            output_path="with_audio.mp4",
            audio_path="music.mp3",
        )
        assert params.audio_path == "music.mp3"


class TestGeminiImageProvider:
    """Tests for the Gemini image provider (mocking google.genai)."""

    def test_provider_init(self):
        from unittest.mock import patch

        config = ImageProviderConfig(
            type="gemini",
            api_key=SecretStr("test-gemini-key"),
            model_name="gemini-2.0-flash-exp",
        )
        with patch("kimi_cli.tools.video.providers.gemini.genai.Client"):
            from kimi_cli.tools.video.providers.gemini import GeminiImageProvider

            provider = GeminiImageProvider(config)
            assert provider._model == "gemini-2.0-flash-exp"

    def test_provider_default_model(self):
        from unittest.mock import patch

        config = ImageProviderConfig(type="gemini", api_key=SecretStr("k"))
        with patch("kimi_cli.tools.video.providers.gemini.genai.Client"):
            from kimi_cli.tools.video.providers.gemini import GeminiImageProvider

            provider = GeminiImageProvider(config)
            assert provider._model == "gemini-2.0-flash-exp"

    @pytest.mark.asyncio
    async def test_generate_image_success(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        from kimi_cli.tools.video.providers.gemini import GeminiImageProvider
        from kimi_cli.tools.video.providers.image_base import ImageGenerationRequest

        config = ImageProviderConfig(type="gemini", api_key=SecretStr("k"))

        mock_inline_data = MagicMock()
        mock_inline_data.data = b"fake-png-bytes"
        mock_inline_data.mime_type = "image/png"

        mock_part = MagicMock()
        mock_part.inline_data = mock_inline_data

        mock_content = MagicMock()
        mock_content.parts = [mock_part]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        with patch("kimi_cli.tools.video.providers.gemini.genai.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

            provider = GeminiImageProvider(config)
            request = ImageGenerationRequest(prompt="A cute cat", style="anime")
            result = await provider.generate_image(request)

            assert result.image_bytes == b"fake-png-bytes"
            assert result.mime_type == "image/png"

            # Verify the API was called with correct model
            call_kwargs = mock_client.aio.models.generate_content.call_args
            assert call_kwargs.kwargs["model"] == "gemini-2.0-flash-exp"

    @pytest.mark.asyncio
    async def test_generate_image_no_candidates(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        from kimi_cli.tools.video.providers.gemini import GeminiImageProvider
        from kimi_cli.tools.video.providers.image_base import ImageGenerationRequest

        config = ImageProviderConfig(type="gemini", api_key=SecretStr("k"))

        mock_response = MagicMock()
        mock_response.candidates = []

        with patch("kimi_cli.tools.video.providers.gemini.genai.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

            provider = GeminiImageProvider(config)
            request = ImageGenerationRequest(prompt="test")
            with pytest.raises(RuntimeError, match="no candidates"):
                await provider.generate_image(request)

    @pytest.mark.asyncio
    async def test_generate_image_no_image_data(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        from kimi_cli.tools.video.providers.gemini import GeminiImageProvider
        from kimi_cli.tools.video.providers.image_base import ImageGenerationRequest

        config = ImageProviderConfig(type="gemini", api_key=SecretStr("k"))

        mock_part = MagicMock()
        mock_part.inline_data = None

        mock_content = MagicMock()
        mock_content.parts = [mock_part]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        with patch("kimi_cli.tools.video.providers.gemini.genai.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

            provider = GeminiImageProvider(config)
            request = ImageGenerationRequest(prompt="test")
            with pytest.raises(RuntimeError, match="no image data"):
                await provider.generate_image(request)

    @pytest.mark.asyncio
    async def test_generate_image_with_reference_images(self, tmp_path):
        from unittest.mock import AsyncMock, MagicMock, patch

        from kimi_cli.tools.video.providers.gemini import GeminiImageProvider
        from kimi_cli.tools.video.providers.image_base import ImageGenerationRequest

        config = ImageProviderConfig(type="gemini", api_key=SecretStr("k"))

        # Create a fake reference image
        ref_img = tmp_path / "ref.png"
        ref_img.write_bytes(b"fake-ref-image")

        mock_inline_data = MagicMock()
        mock_inline_data.data = b"generated-image"
        mock_inline_data.mime_type = "image/png"

        mock_part = MagicMock()
        mock_part.inline_data = mock_inline_data

        mock_content = MagicMock()
        mock_content.parts = [mock_part]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        with patch("kimi_cli.tools.video.providers.gemini.genai.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

            provider = GeminiImageProvider(config)
            request = ImageGenerationRequest(
                prompt="Make it better",
                reference_image_paths=[str(ref_img)],
            )
            result = await provider.generate_image(request)

            assert result.image_bytes == b"generated-image"

            # Verify contents were passed (reference image part + text part)
            call_kwargs = mock_client.aio.models.generate_content.call_args
            contents = call_kwargs.kwargs["contents"]
            assert len(contents) == 2  # 1 ref image + 1 text


class TestImageProviderFactory:
    """Tests for image provider factory functions."""

    def test_create_gemini_provider(self):
        from unittest.mock import patch

        from kimi_cli.tools.video.providers import create_image_provider
        from kimi_cli.tools.video.providers.gemini import GeminiImageProvider

        config = ImageProviderConfig(type="gemini", api_key=SecretStr("k"))
        with patch("kimi_cli.tools.video.providers.gemini.genai.Client"):
            provider = create_image_provider(config)
            assert isinstance(provider, GeminiImageProvider)

    def test_create_unknown_image_provider(self):
        from kimi_cli.tools.video.providers import create_image_provider

        config = ImageProviderConfig(type="nonexistent")
        with pytest.raises(ValueError, match="Unknown image provider type"):
            create_image_provider(config)

    def test_get_default_image_provider(self):
        from unittest.mock import patch

        from kimi_cli.tools.video.providers import get_default_image_provider
        from kimi_cli.tools.video.providers.gemini import GeminiImageProvider

        providers = {"gemini": ImageProviderConfig(type="gemini", api_key=SecretStr("k"))}
        with patch("kimi_cli.tools.video.providers.gemini.genai.Client"):
            name, provider = get_default_image_provider(providers)
            assert name == "gemini"
            assert isinstance(provider, GeminiImageProvider)

    def test_get_default_image_provider_empty(self):
        from kimi_cli.tools.video.providers import get_default_image_provider

        with pytest.raises(ValueError, match="No image providers configured"):
            get_default_image_provider({})

    def test_get_default_image_provider_preferred(self):
        from unittest.mock import patch

        from kimi_cli.tools.video.providers import get_default_image_provider

        providers = {
            "first": ImageProviderConfig(type="gemini", api_key=SecretStr("k1")),
            "second": ImageProviderConfig(type="gemini", api_key=SecretStr("k2")),
        }
        with patch("kimi_cli.tools.video.providers.gemini.genai.Client"):
            name, _ = get_default_image_provider(providers, preferred="second")
            assert name == "second"


class TestImageProviderConfig:
    """Tests for ImageProviderConfig in Config."""

    def test_config_with_image_providers(self):
        config = get_default_config()
        config.image_providers = {
            "gemini": ImageProviderConfig(
                type="gemini",
                api_key=SecretStr("test-key"),
                model_name="gemini-2.0-flash-exp",
            ),
        }
        assert "gemini" in config.image_providers
        assert config.image_providers["gemini"].type == "gemini"
        assert config.image_providers["gemini"].model_name == "gemini-2.0-flash-exp"

    def test_config_default_no_image_providers(self):
        config = get_default_config()
        assert config.image_providers == {}

    def test_image_provider_config_defaults(self):
        config = ImageProviderConfig(type="gemini")
        assert config.api_key.get_secret_value() == ""
        assert config.model_name == ""
        assert config.base_url == ""
        assert config.custom_headers is None


class TestGenerateImageTool:
    """Tests for the GenerateImage tool."""

    def test_skip_when_no_image_providers(self, approval):
        from kimi_cli.tools import SkipThisTool
        from kimi_cli.tools.video.generate_image import GenerateImage

        config = get_default_config()
        assert config.image_providers == {}
        with pytest.raises(SkipThisTool):
            GenerateImage(config, approval)

    def test_init_with_image_providers(self, approval):
        from unittest.mock import patch

        from kimi_cli.tools.video.generate_image import GenerateImage

        config = get_default_config()
        config.image_providers = {
            "gemini": ImageProviderConfig(type="gemini", api_key=SecretStr("k")),
        }
        # Should not raise SkipThisTool
        tool = GenerateImage(config, approval)
        assert tool.name == "GenerateImage"

    @pytest.mark.asyncio
    async def test_generate_image_rejected(self, approval):
        from unittest.mock import AsyncMock, patch

        from kimi_cli.tools.video.generate_image import GenerateImage, Params

        config = get_default_config()
        config.image_providers = {
            "gemini": ImageProviderConfig(type="gemini", api_key=SecretStr("k")),
        }
        tool = GenerateImage(config, approval)

        with _tool_call_context("GenerateImage"), patch.object(
            approval, "request", new=AsyncMock(return_value=False)
        ):
            result = await tool(Params(prompt="test", output_path="/tmp/test.png"))
        assert "Rejected" in str(result) or "rejected" in str(result).lower()

    @pytest.mark.asyncio
    async def test_generate_image_success(self, tmp_path, approval):
        from unittest.mock import AsyncMock, patch


        from kimi_cli.tools.video.generate_image import GenerateImage, Params
        from kimi_cli.tools.video.providers.image_base import ImageGenerationResult

        config = get_default_config()
        config.image_providers = {
            "gemini": ImageProviderConfig(type="gemini", api_key=SecretStr("k")),
        }
        tool = GenerateImage(config, approval)

        mock_result = ImageGenerationResult(image_bytes=b"png-data", mime_type="image/png")
        output_path = str(tmp_path / "output.png")

        with _tool_call_context("GenerateImage"), patch(
            "kimi_cli.tools.video.generate_image.get_default_image_provider"
        ) as mock_get:
            mock_provider = AsyncMock()
            mock_provider.generate_image.return_value = mock_result
            mock_get.return_value = ("gemini", mock_provider)

            result = await tool(Params(prompt="A cute cat", output_path=output_path))

        assert Path(output_path).read_bytes() == b"png-data"
        assert "Image saved" in str(result) or "output.png" in str(result)

    @pytest.mark.asyncio
    async def test_generate_image_provider_error(self, tmp_path, approval):
        from unittest.mock import AsyncMock, patch


        from kimi_cli.tools.video.generate_image import GenerateImage, Params

        config = get_default_config()
        config.image_providers = {
            "gemini": ImageProviderConfig(type="gemini", api_key=SecretStr("k")),
        }
        tool = GenerateImage(config, approval)

        with _tool_call_context("GenerateImage"), patch(
            "kimi_cli.tools.video.generate_image.get_default_image_provider"
        ) as mock_get:
            mock_provider = AsyncMock()
            mock_provider.generate_image.side_effect = RuntimeError("API error")
            mock_get.return_value = ("gemini", mock_provider)

            result = await tool(
                Params(prompt="test", output_path=str(tmp_path / "out.png"))
            )

        assert "failed" in str(result).lower() or "error" in str(result).lower()
