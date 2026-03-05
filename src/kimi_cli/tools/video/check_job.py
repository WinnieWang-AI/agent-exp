from pathlib import Path

from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.config import Config
from kimi_cli.tools import SkipThisTool
from kimi_cli.tools.utils import ToolResultBuilder, load_desc
from kimi_cli.tools.video.providers import create_provider
from kimi_cli.tools.video.providers.base import VideoJobState


class Params(BaseModel):
    job_id: str = Field(description="The job ID returned by GenerateVideo")
    provider: str = Field(description="The provider name that generated this job")
    download_path: str = Field(
        default="",
        description="If provided, automatically download the result to this path when completed",
    )


class CheckVideoJob(CallableTool2[Params]):
    name: str = "CheckVideoJob"
    params: type[Params] = Params

    def __init__(self, config: Config):
        if not config.video_providers:
            raise SkipThisTool()
        super().__init__(description=load_desc(Path(__file__).parent / "check_job.md"))
        self._config = config

    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()

        provider_config = self._config.video_providers.get(params.provider)
        if provider_config is None:
            return builder.error(
                message=f"Provider not found: {params.provider}",
                brief="Provider not found",
            )

        provider = create_provider(provider_config)

        try:
            status = await provider.check_job(params.job_id)
        except Exception as e:
            return builder.error(
                message=f"Failed to check job status: {e}",
                brief="Check failed",
            )

        builder.write(f"Job: {status.job_id}\n")
        builder.write(f"State: {status.state.value}\n")
        builder.write(f"Progress: {status.progress_percent:.0f}%\n")

        if status.state == VideoJobState.FAILED:
            builder.write(f"Error: {status.error_message}\n")
            return builder.error(
                message=f"Job failed: {status.error_message}",
                brief="Job failed",
            )

        if status.state == VideoJobState.COMPLETED and params.download_path:
            try:
                await provider.download_result(status.result_url, params.download_path)
                builder.write(f"Downloaded to: {params.download_path}\n")
            except Exception as e:
                builder.write(f"Download failed: {e}\n")
                return builder.error(
                    message=f"Job completed but download failed: {e}",
                    brief="Download failed",
                )

        if status.state == VideoJobState.COMPLETED:
            return builder.ok(message="Job completed.")
        return builder.ok(message=f"Job {status.state.value} ({status.progress_percent:.0f}%)")
