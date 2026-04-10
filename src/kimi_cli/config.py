from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal, Self

import tomlkit
from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    SecretStr,
    ValidationError,
    field_serializer,
    model_validator,
)
from tomlkit.exceptions import TOMLKitError

from kimi_cli.exception import ConfigError
from kimi_cli.llm import ModelCapability, ProviderType
from kimi_cli.share import get_share_dir
from kimi_cli.utils.logging import logger


class OAuthRef(BaseModel):
    """Reference to OAuth credentials stored outside the config file."""

    storage: Literal["keyring", "file"] = "file"
    """Credential storage backend."""
    key: str
    """Storage key to locate OAuth credentials."""


class LLMProvider(BaseModel):
    """LLM provider configuration."""

    type: ProviderType
    """Provider type"""
    base_url: str
    """API base URL"""
    api_key: SecretStr
    """API key"""
    env: dict[str, str] | None = None
    """Environment variables to set before creating the provider instance"""
    custom_headers: dict[str, str] | None = None
    """Custom headers to include in API requests"""
    oauth: OAuthRef | None = None
    """OAuth credential reference (do not store tokens here)."""

    @field_serializer("api_key", when_used="json")
    def dump_secret(self, v: SecretStr):
        return v.get_secret_value()


class LLMModel(BaseModel):
    """LLM model configuration."""

    provider: str
    """Provider name"""
    model: str
    """Model name"""
    max_context_size: int
    """Maximum context size (unit: tokens)"""
    capabilities: set[ModelCapability] | None = None
    """Model capabilities"""


class LoopControl(BaseModel):
    """Agent loop control configuration."""

    max_steps_per_turn: int = Field(
        default=100,
        ge=1,
        validation_alias=AliasChoices("max_steps_per_turn", "max_steps_per_run"),
    )
    """Maximum number of steps in one turn"""
    max_retries_per_step: int = Field(default=3, ge=1)
    """Maximum number of retries in one step"""
    max_ralph_iterations: int = Field(default=0, ge=-1)
    """Extra iterations after the first turn in Ralph mode. Use -1 for unlimited."""
    reserved_context_size: int = Field(default=50_000, ge=1000)
    """Reserved token count for LLM response generation. Auto-compaction triggers when
    context_tokens + reserved_context_size >= max_context_size. Default is 50000."""


class MoonshotSearchConfig(BaseModel):
    """Moonshot Search configuration."""

    base_url: str
    """Base URL for Moonshot Search service."""
    api_key: SecretStr
    """API key for Moonshot Search service."""
    custom_headers: dict[str, str] | None = None
    """Custom headers to include in API requests."""
    oauth: OAuthRef | None = None
    """OAuth credential reference (do not store tokens here)."""

    @field_serializer("api_key", when_used="json")
    def dump_secret(self, v: SecretStr):
        return v.get_secret_value()


class MoonshotFetchConfig(BaseModel):
    """Moonshot Fetch configuration."""

    base_url: str
    """Base URL for Moonshot Fetch service."""
    api_key: SecretStr
    """API key for Moonshot Fetch service."""
    custom_headers: dict[str, str] | None = None
    """Custom headers to include in API requests."""
    oauth: OAuthRef | None = None
    """OAuth credential reference (do not store tokens here)."""

    @field_serializer("api_key", when_used="json")
    def dump_secret(self, v: SecretStr):
        return v.get_secret_value()


class Services(BaseModel):
    """Services configuration."""

    moonshot_search: MoonshotSearchConfig | None = None
    """Moonshot Search configuration."""
    moonshot_fetch: MoonshotFetchConfig | None = None
    """Moonshot Fetch configuration."""


class MCPClientConfig(BaseModel):
    """MCP client configuration."""

    tool_call_timeout_ms: int = 60000
    """Timeout for tool calls in milliseconds."""


class MCPConfig(BaseModel):
    """MCP configuration."""

    client: MCPClientConfig = Field(
        default_factory=MCPClientConfig, description="MCP client configuration"
    )


class VideoProviderConfig(BaseModel):
    """Video generation provider configuration."""

    type: str
    """Provider type: "mock", "vidu", "kling", etc."""
    base_url: str = ""
    """API base URL."""
    api_key: SecretStr = SecretStr("")
    """API key."""
    model_name: str = ""
    """Model name override (provider-specific, e.g. "viduq3-pro")."""
    custom_headers: dict[str, str] | None = None
    """Custom headers to include in API requests."""

    @field_serializer("api_key", when_used="json")
    def dump_secret(self, v: SecretStr):
        return v.get_secret_value()


class ImageProviderConfig(BaseModel):
    """Image generation provider configuration."""

    type: str
    """Provider type: "gemini", etc."""
    api_key: SecretStr = SecretStr("")
    """API key."""
    model_name: str = ""
    """Model name (e.g. "gemini-2.5-flash-image")."""
    base_url: str = ""
    """Optional base URL."""
    project_id: str = ""
    """Google Cloud project ID (for Vertex AI)."""
    location: str = "global"
    """Vertex AI location."""
    credentials_json: str = ""
    """Path to service account JSON file (for Vertex AI)."""
    custom_headers: dict[str, str] | None = None
    """Custom headers to include in API requests."""

    @field_serializer("api_key", when_used="json")
    def dump_secret(self, v: SecretStr):
        return v.get_secret_value()


class VLMProviderConfig(BaseModel):
    """VLM (vision-language model) provider configuration."""

    type: str = "gemini"
    """Provider type: "gemini"."""
    api_key: SecretStr = SecretStr("")
    """API key (for Gemini Developer API)."""
    model_name: str = ""
    """Model name (e.g. "gemini-2.0-flash")."""
    base_url: str = ""
    """Optional base URL override."""
    project_id: str = ""
    """Google Cloud project ID (for Vertex AI)."""
    location: str = "global"
    """Vertex AI location."""
    credentials_json: str = ""
    """Path to service account JSON file (for Vertex AI)."""

    @field_serializer("api_key", when_used="json")
    def dump_secret(self, v: SecretStr):
        return v.get_secret_value()


class MusicProviderConfig(BaseModel):
    """Music generation provider configuration."""

    type: str
    """Provider type: "suno", etc."""
    api_key: SecretStr = SecretStr("")
    """API key."""
    base_url: str = ""
    """API base URL."""
    model_name: str = ""
    """Model name override."""

    @field_serializer("api_key", when_used="json")
    def dump_secret(self, v: SecretStr):
        return v.get_secret_value()


class TTSProviderConfig(BaseModel):
    """TTS (text-to-speech) provider configuration."""

    type: str
    """Provider type: "minimax", etc."""
    api_key: SecretStr = SecretStr("")
    """API key."""
    base_url: str = ""
    """API base URL."""
    group_id: str = ""
    """Group ID (required for Minimax)."""
    model_name: str = ""
    """Model name (e.g. "speech-01-tts")."""

    @field_serializer("api_key", when_used="json")
    def dump_secret(self, v: SecretStr):
        return v.get_secret_value()


class TOSConfig(BaseModel):
    """TOS (Volcengine Object Storage) configuration."""

    ak: SecretStr = SecretStr("")
    """Access key."""
    sk: SecretStr = SecretStr("")
    """Secret key."""
    region: str = ""
    """Region (e.g. "ap-southeast-1")."""
    bucket: str = ""
    """Bucket name."""
    domain: str = ""
    """Public access domain (e.g. "ace.tos-s3-accelerate.volces.com")."""
    prefix: str = "agent_exp/test_2026_03"
    """Object key prefix for uploads."""

    @field_serializer("ak", "sk", when_used="json")
    def dump_secret(self, v: SecretStr):
        return v.get_secret_value()

    @property
    def is_configured(self) -> bool:
        return bool(self.ak.get_secret_value() and self.sk.get_secret_value() and self.region and self.bucket and self.domain)


class NacosSettings(BaseModel):
    """Nacos configuration center connection settings."""

    server_addr: str = ""
    """Nacos server address (e.g. ``http://101.47.165.90:8848``)."""
    namespace: str = ""
    """Nacos namespace / tenant ID."""
    username: str = ""
    """Nacos login username."""
    password: str = ""
    """Nacos login password."""
    group: str = "DEFAULT_GROUP"
    """Nacos configuration group."""


class Config(BaseModel):
    """Main configuration structure."""

    is_from_default_location: bool = Field(
        default=False,
        description="Whether the config was loaded from the default location",
        exclude=True,
    )
    default_model: str = Field(default="", description="Default model to use")
    default_thinking: bool = Field(default=False, description="Default thinking mode")
    default_yolo: bool = Field(default=False, description="Default yolo (auto-approve) mode")
    models: dict[str, LLMModel] = Field(default_factory=dict, description="List of LLM models")
    providers: dict[str, LLMProvider] = Field(
        default_factory=dict, description="List of LLM providers"
    )
    loop_control: LoopControl = Field(default_factory=LoopControl, description="Agent loop control")
    services: Services = Field(default_factory=Services, description="Services configuration")
    mcp: MCPConfig = Field(default_factory=MCPConfig, description="MCP configuration")
    video_providers: dict[str, VideoProviderConfig] = Field(
        default_factory=dict, description="Video generation provider configurations"
    )
    image_providers: dict[str, ImageProviderConfig] = Field(
        default_factory=dict, description="Image generation provider configurations"
    )
    vlm_providers: dict[str, VLMProviderConfig] = Field(
        default_factory=dict, description="VLM (vision-language model) provider configurations"
    )
    music_providers: dict[str, MusicProviderConfig] = Field(
        default_factory=dict, description="Music generation provider configurations"
    )
    tts_providers: dict[str, TTSProviderConfig] = Field(
        default_factory=dict, description="TTS (text-to-speech) provider configurations"
    )
    tos: TOSConfig = Field(default_factory=TOSConfig, description="TOS object storage configuration")
    nacos: NacosSettings | None = Field(
        default=None, description="Nacos configuration center settings"
    )

    @model_validator(mode="after")
    def validate_model(self) -> Self:
        if self.default_model and self.default_model not in self.models:
            raise ValueError(f"Default model {self.default_model} not found in models")
        for model in self.models.values():
            if model.provider not in self.providers:
                raise ValueError(f"Provider {model.provider} not found in providers")
        return self


def get_config_file() -> Path:
    """Get the configuration file path."""
    return get_share_dir() / "config.toml"


def get_default_config() -> Config:
    """Get the default configuration."""
    return Config(
        default_model="",
        models={},
        providers={},
        services=Services(),
    )


def load_config(config_file: Path | None = None) -> Config:
    """
    Load configuration from config file.
    If the config file does not exist, create it with default configuration.

    Args:
        config_file (Path | None): Path to the configuration file. If None, use default path.

    Returns:
        Validated Config object.

    Raises:
        ConfigError: If the configuration file is invalid.
    """
    default_config_file = get_config_file()
    if config_file is None:
        config_file = default_config_file
    is_default_config_file = config_file.expanduser().resolve(
        strict=False
    ) == default_config_file.expanduser().resolve(strict=False)
    logger.debug("Loading config from file: {file}", file=config_file)

    # If the user hasn't provided an explicit config path, migrate legacy JSON config once.
    if is_default_config_file and not config_file.exists():
        _migrate_json_config_to_toml()

    if not config_file.exists():
        config = get_default_config()
        logger.debug("No config file found, creating default config: {config}", config=config)
        save_config(config, config_file)
        config.is_from_default_location = is_default_config_file
        _merge_nacos_configs(config)
        return config

    try:
        config_text = config_file.read_text(encoding="utf-8")
        if config_file.suffix.lower() == ".json":
            data = json.loads(config_text)
        else:
            data = tomlkit.loads(config_text)
        config = Config.model_validate(data)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in configuration file {config_file}: {e}") from e
    except TOMLKitError as e:
        raise ConfigError(f"Invalid TOML in configuration file {config_file}: {e}") from e
    except ValidationError as e:
        raise ConfigError(f"Invalid configuration file {config_file}: {e}") from e
    config.is_from_default_location = is_default_config_file
    _merge_nacos_configs(config)
    return config


def load_config_from_string(config_string: str) -> Config:
    """
    Load configuration from a TOML or JSON string.

    Args:
        config_string (str): TOML or JSON configuration text.

    Returns:
        Validated Config object.

    Raises:
        ConfigError: If the configuration text is invalid.
    """
    if not config_string.strip():
        raise ConfigError("Configuration text cannot be empty")

    json_error: json.JSONDecodeError | None = None
    try:
        data = json.loads(config_string)
    except json.JSONDecodeError as exc:
        json_error = exc
        data = None

    if data is None:
        try:
            data = tomlkit.loads(config_string)
        except TOMLKitError as toml_error:
            raise ConfigError(
                f"Invalid configuration text: {json_error}; {toml_error}"
            ) from toml_error

    try:
        config = Config.model_validate(data)
    except ValidationError as e:
        raise ConfigError(f"Invalid configuration text: {e}") from e
    config.is_from_default_location = False
    return config


def save_config(config: Config, config_file: Path | None = None):
    """
    Save configuration to config file.

    Args:
        config (Config): Config object to save.
        config_file (Path | None): Path to the configuration file. If None, use default path.
    """
    config_file = config_file or get_config_file()
    logger.debug("Saving config to file: {file}", file=config_file)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_data = config.model_dump(mode="json", exclude_none=True)
    with open(config_file, "w", encoding="utf-8") as f:
        if config_file.suffix.lower() == ".json":
            f.write(json.dumps(config_data, ensure_ascii=False, indent=2))
        else:
            f.write(tomlkit.dumps(config_data))  # type: ignore[reportUnknownMemberType]


def _migrate_json_config_to_toml() -> None:
    old_json_config_file = get_share_dir() / "config.json"
    new_toml_config_file = get_share_dir() / "config.toml"

    if not old_json_config_file.exists():
        return
    if new_toml_config_file.exists():
        return

    logger.info(
        "Migrating legacy config file from {old} to {new}",
        old=old_json_config_file,
        new=new_toml_config_file,
    )

    try:
        with open(old_json_config_file, encoding="utf-8") as f:
            data = json.load(f)
        config = Config.model_validate(data)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in legacy configuration file: {e}") from e
    except ValidationError as e:
        raise ConfigError(f"Invalid legacy configuration file: {e}") from e

    # Write new TOML config, then keep a backup of the original JSON file.
    save_config(config, new_toml_config_file)
    backup_path = old_json_config_file.with_name("config.json.bak")
    old_json_config_file.replace(backup_path)
    logger.info("Legacy config backed up to {file}", file=backup_path)


def _resolve_nacos_settings(config: Config) -> NacosSettings | None:
    """Build NacosSettings from config.toml ``[nacos]`` section or env vars.

    Environment variables take precedence over the TOML section.
    Returns ``None`` if no Nacos coordinates are available.
    """
    env_ip = os.environ.get("NACOS_IP", "")
    if env_ip:
        port = os.environ.get("NACOS_PORT", "8848")
        return NacosSettings(
            server_addr=f"http://{env_ip}:{port}",
            namespace=os.environ.get("NACOS_NAMESPACE", ""),
            username=os.environ.get("NACOS_USERNAME", ""),
            password=os.environ.get("NACOS_PASSWORD", ""),
            group=os.environ.get("NACOS_GROUP", "DEFAULT_GROUP"),
        )

    if config.nacos and config.nacos.server_addr:
        return config.nacos

    return None


def _merge_nacos_configs(config: Config) -> None:
    """Fetch remote configs from Nacos and merge into *config* in-place.

    Mapping
    -------
    * ``openai_config`` → ``providers["main"]`` + ``models["default"]`` (only
      when the local config does not already define them)
    * ``suno_config`` → ``music_providers["suno"]`` (type ``suno``)
    * ``minimax_config`` → ``tts_providers["minimax"]`` (type ``minimax``)

    Errors are logged as warnings and never block startup.
    """
    settings = _resolve_nacos_settings(config)
    if settings is None:
        return

    from kimi_cli.nacos import NacosClient

    client = NacosClient(
        server_addr=settings.server_addr,
        namespace=settings.namespace,
        username=settings.username,
        password=settings.password,
        group=settings.group,
    )
    client.login()

    # --- openai_config → providers["main"] + models["default"] ---
    if "main" not in config.providers:
        openai = client.get_config("openai_config")
        if openai:
            api_key = openai.get("api_key") or openai.get("apiKey") or ""
            base_url = openai.get("base_url") or openai.get("baseUrl") or ""
            # model name can be at top-level or nested in llm.chat.default_model
            llm_section = openai.get("llm") or {}
            chat_section = llm_section.get("chat") or {} if isinstance(llm_section, dict) else {}
            model = (
                openai.get("model")
                or openai.get("model_name")
                or chat_section.get("default_model")
                or ""
            )
            if api_key and base_url:
                config.providers["main"] = LLMProvider(
                    type="openai_legacy",
                    base_url=base_url,
                    api_key=SecretStr(api_key),
                )
                if model and "default" not in config.models:
                    config.models["default"] = LLMModel(
                        provider="main",
                        model=model,
                        max_context_size=128_000,
                    )
                    if not config.default_model:
                        config.default_model = "default"
                logger.debug("Nacos: merged openai_config into providers['main']")

    # --- gemini → vlm_providers["gemini"] (type=gemini, Vertex AI) ---
    if "gemini" not in config.vlm_providers:
        gemini = client.get_config("gemini")
        if gemini:
            api_key_url = gemini.get("api_key_url", "")
            # Nacos model_name is for image generation; VLM uses a different model
            model_name = "gemini-2.5-flash"
            project_id = gemini.get("project_id", "")
            location = gemini.get("location", "global")

            credentials_json = ""
            if api_key_url:
                try:
                    import httpx as _httpx

                    resp = _httpx.get(api_key_url, timeout=10)
                    resp.raise_for_status()
                    # Save service account JSON to a temp file
                    creds_file = Path(get_share_dir()) / "gemini_sa.json"
                    creds_file.write_text(resp.text, encoding="utf-8")
                    credentials_json = str(creds_file)
                except Exception as exc:
                    logger.warning(
                        "Nacos: failed to fetch Gemini credentials from {url}: {exc}",
                        url=api_key_url,
                        exc=exc,
                    )

            if credentials_json or project_id:
                config.vlm_providers["gemini"] = VLMProviderConfig(
                    type="gemini",
                    model_name=model_name,
                    project_id=project_id,
                    location=location,
                    credentials_json=credentials_json,
                )
                logger.debug("Nacos: merged gemini into vlm_providers['gemini']")

                # Also configure Gemini as image provider (using same Vertex AI credentials)
                if "gemini" not in config.image_providers:
                    config.image_providers["gemini"] = ImageProviderConfig(
                        type="gemini",
                        project_id=project_id,
                        location=location,
                        credentials_json=credentials_json,
                    )
                    logger.debug("Nacos: merged gemini into image_providers['gemini']")

    # --- suno_config → music_providers["suno"] (type=suno) ---
    if "suno" not in config.music_providers:
        suno = client.get_config("suno_config")
        if suno:
            api_key = suno.get("api_key") or ""
            base_url = suno.get("base_url") or ""
            if api_key:
                config.music_providers["suno"] = MusicProviderConfig(
                    type="suno",
                    api_key=SecretStr(api_key),
                    base_url=base_url,
                )
                logger.debug("Nacos: merged suno_config into music_providers['suno']")

    # --- minimax_config → tts_providers["minimax"] (type=minimax) ---
    if "minimax" not in config.tts_providers:
        minimax = client.get_config("minimax_config")
        if minimax:
            api_key = minimax.get("api_key") or ""
            group_id = minimax.get("group_id") or ""
            # Pick the first audio model name as the default model
            audio_models = minimax.get("audio") or {}
            model_name = ""
            if audio_models and isinstance(audio_models, dict):
                first_key = next(iter(audio_models))
                model_cfg = audio_models[first_key]
                model_name = (
                    model_cfg.get("model_name") or first_key
                    if isinstance(model_cfg, dict)
                    else first_key
                )
            if api_key and group_id:
                config.tts_providers["minimax"] = TTSProviderConfig(
                    type="minimax",
                    api_key=SecretStr(api_key),
                    group_id=group_id,
                    model_name=model_name,
                )
                logger.debug("Nacos: merged minimax_config into tts_providers['minimax']")

    # --- tos_config → tos (TOS object storage) ---
    if not config.tos.is_configured:
        tos_data = client.get_config("tos_config")
        if tos_data:
            ak = tos_data.get("ak", "")
            sk = tos_data.get("sk", "")
            region = tos_data.get("region", "")
            bucket = tos_data.get("bucket", "")
            domain = tos_data.get("domain", "")
            if ak and sk and region and bucket and domain:
                config.tos = TOSConfig(
                    ak=SecretStr(ak),
                    sk=SecretStr(sk),
                    region=region,
                    bucket=bucket,
                    domain=domain,
                )
                logger.debug("Nacos: merged tos_config into tos")

    # --- Statsig: shengshu → video_providers["vidu"] (type=vidu) ---
    _merge_statsig_configs(config)


def _merge_statsig_configs(config: Config) -> None:
    """Fetch dynamic configs from Statsig and merge into *config* in-place.

    Mapping
    -------
    * ``bytedance`` → ``video_providers["seedance"]`` (type ``seedance``)
    * ``kling26`` → ``video_providers["kling"]`` (type ``kling``)
    * ``shengshu`` → ``video_providers["vidu"]`` (type ``vidu``)

    Seedance is inserted first so it becomes the default provider.

    Requires ``STATSIG_SK`` environment variable.
    Errors are logged as warnings and never block startup.
    """
    statsig_sk = os.environ.get("STATSIG_SK", "")
    if not statsig_sk:
        return

    try:
        from statsig import statsig, StatsigOptions, StatsigUser

        statsig.initialize(statsig_sk, StatsigOptions(tier="development"))
        try:
            user = StatsigUser(user_id="kimi_cli")

            # --- bytedance → video_providers["seedance"] (type=seedance) ---
            if "seedance" not in config.video_providers:
                bytedance = statsig.get_config(user, "bytedance").get_value()
                logger.info(
                    "Statsig: bytedance config fetched, keys={keys}",
                    keys=list(bytedance.keys()) if bytedance else "empty",
                )
                if bytedance:
                    api_key = bytedance.get("api_key", "")
                    base_url = bytedance.get("base_url", "https://ark.cn-beijing.volces.com")
                    # Pick the preferred model from the video config map.
                    model_name = ""
                    video_cfgs = bytedance.get("video", {})
                    for key in ("dreamina-seedance-2-0-fast-260128", "dreamina-seedance-2-0-260128"):
                        if key in video_cfgs:
                            model_name = video_cfgs[key].get("model_name", key)
                            break
                    if not model_name and video_cfgs:
                        first = next(iter(video_cfgs.values()))
                        model_name = first.get("model_name", "")
                    if api_key:
                        # Insert seedance at the front so it is the default provider.
                        old = config.video_providers.copy()
                        config.video_providers.clear()
                        config.video_providers["seedance"] = VideoProviderConfig(
                            type="seedance",
                            api_key=SecretStr(api_key),
                            base_url=base_url,
                            model_name=model_name,
                        )
                        config.video_providers.update(old)
                        logger.info("Statsig: merged bytedance into video_providers['seedance'], model={model}", model=model_name)
                    else:
                        logger.warning("Statsig: bytedance config has no api_key, skipping seedance")
                else:
                    logger.warning("Statsig: bytedance config is empty, seedance not loaded")

            # --- kling26 → video_providers["kling"] (type=kling) ---
            if "kling" not in config.video_providers:
                kling26 = statsig.get_config(user, "kling26").get_value()
                if kling26:
                    api_key = kling26.get("api_key", "")
                    base_url = kling26.get("base_url", "https://api.klingai.com")
                    model_name = kling26.get("model_name", "")
                    if api_key:
                        config.video_providers["kling"] = VideoProviderConfig(
                            type="kling",
                            api_key=SecretStr(api_key),
                            base_url=base_url,
                            model_name=model_name,
                        )
                        logger.debug("Statsig: merged kling26 into video_providers['kling']")

            # --- shengshu → video_providers["vidu"] (type=vidu) ---
            if "vidu" not in config.video_providers:
                shengshu = statsig.get_config(user, "shengshu").get_value()
                if shengshu:
                    api_key = shengshu.get("api_key", "")
                    base_url = shengshu.get("base_url", "https://api.vidu.com")
                    model_name = shengshu.get("model_name", "")
                    if api_key:
                        config.video_providers["vidu"] = VideoProviderConfig(
                            type="vidu",
                            api_key=SecretStr(api_key),
                            base_url=base_url,
                            model_name=model_name,
                        )
                        logger.debug("Statsig: merged shengshu into video_providers['vidu']")
        finally:
            statsig.shutdown()
    except Exception as exc:
        logger.warning("Statsig config fetch failed: {exc}", exc=exc)
