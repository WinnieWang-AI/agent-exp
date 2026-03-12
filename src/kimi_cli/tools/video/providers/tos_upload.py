"""Upload local files to Volcengine TOS and return public URLs."""

from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path

import tos as tos_sdk

from kimi_cli.config import TOSConfig
from kimi_cli.utils.logging import logger

_client_cache: dict[str, tos_sdk.TosClientV2] = {}


def _get_client(config: TOSConfig) -> tos_sdk.TosClientV2:
    """Get or create a cached TOS client."""
    cache_key = f"{config.region}:{config.bucket}"
    if cache_key not in _client_cache:
        endpoint = f"https://tos-{config.region}.volces.com"
        _client_cache[cache_key] = tos_sdk.TosClientV2(
            ak=config.ak.get_secret_value(),
            sk=config.sk.get_secret_value(),
            endpoint=endpoint,
            region=config.region,
        )
    return _client_cache[cache_key]


def upload_file(config: TOSConfig, local_path: str) -> str:
    """Upload a local file to TOS and return its public URL.

    Args:
        config: TOS configuration.
        local_path: Path to the local file.

    Returns:
        Public HTTPS URL for the uploaded file.

    Raises:
        FileNotFoundError: If the local file does not exist.
        RuntimeError: If the upload fails.
    """
    p = Path(local_path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {local_path}")

    ext = p.suffix.lower() or ".bin"
    content_type, _ = mimetypes.guess_type(str(p))
    if not content_type:
        content_type = "application/octet-stream"

    object_key = f"{config.prefix}/{uuid.uuid4().hex}{ext}"

    logger.info(
        "Uploading to TOS: {local_path} -> {object_key}",
        local_path=local_path,
        object_key=object_key,
    )

    client = _get_client(config)
    try:
        with open(p, "rb") as f:
            client.put_object(
                bucket=config.bucket,
                key=object_key,
                content=f,
                content_type=content_type,
            )
    except Exception as e:
        raise RuntimeError(f"TOS upload failed for {local_path}: {e}") from e

    url = f"https://{config.domain}/{object_key}"
    logger.info("Uploaded to TOS: {url}", url=url)
    return url
