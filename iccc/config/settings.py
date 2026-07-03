"""Configuration management for iCCC."""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

from iccc.errors.exceptions import ConfigNotFoundError, ConfigValidationError

# Load .env file at module import time
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)


class MongoDBConfig(BaseModel):
    """MongoDB connection configuration."""

    uri: str = Field(default="mongodb://localhost:27017")
    database: str = Field(default="iccc")
    max_pool_size: int = Field(default=10, ge=1)
    timeout_ms: int = Field(default=5000, ge=1000)


class RedisConfig(BaseModel):
    """Redis connection configuration."""

    host: str = Field(default="localhost")
    port: int = Field(default=6379, ge=1, le=65535)
    db: int = Field(default=0, ge=0)
    password: str | None = None
    max_connections: int = Field(default=50, ge=1)


class AnthropicConfig(BaseModel):
    """Anthropic API configuration."""

    api_key: str = Field(default="")
    default_model: str = Field(default="claude-sonnet-4-20250514")
    max_tokens: int = Field(default=8000, ge=100, le=200000)
    temperature: float = Field(default=1.0, ge=0.0, le=2.0)
    enable_rate_limiting: bool = Field(default=True)

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Validate API key is present."""
        if not v:
            # Try to get from environment
            env_key = os.getenv("ANTHROPIC_API_KEY", "")
            if not env_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY must be set in config or environment"
                )
            return env_key
        return v


class OrchestrationConfig(BaseModel):
    """Orchestration system configuration."""

    max_concurrent_agents: int = Field(default=5, ge=1, le=20)
    task_timeout_seconds: int = Field(default=3600, ge=60)
    enable_quality_gates: bool = Field(default=True)
    enable_adaptive_replanning: bool = Field(default=True)
    worktree_dir: str = Field(default=".worktrees")
    enable_file_locking: bool = Field(default=True)


class ObservabilityConfig(BaseModel):
    """Observability system configuration."""

    enable_event_collection: bool = Field(default=True)
    batch_size: int = Field(default=100, ge=1, le=1000)
    batch_timeout_seconds: float = Field(default=5.0, ge=0.1)
    sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    enable_ai_summaries: bool = Field(default=True)
    server_host: str = Field(default="0.0.0.0")
    server_port: int = Field(default=8000, ge=1, le=65535)
    sqlite_path: str = Field(default="./data/events.db")
    enable_metrics: bool = Field(default=True)


class RetryConfig(BaseModel):
    """Retry and error handling configuration."""

    max_attempts: int = Field(default=3, ge=1, le=10)
    initial_delay_seconds: float = Field(default=1.0, ge=0.1)
    max_delay_seconds: float = Field(default=60.0, ge=1.0)
    exponential_base: float = Field(default=2.0, ge=1.1)
    enable_circuit_breaker: bool = Field(default=True)
    circuit_breaker_threshold: int = Field(default=5, ge=1)


class SecurityConfig(BaseModel):
    """Security configuration."""

    enable_pre_tool_hooks: bool = Field(default=True)
    dangerous_patterns_file: str | None = None
    max_wildcard_count: int = Field(default=3, ge=0)
    block_production_changes: bool = Field(default=True)
    allowed_tools: list[str] = Field(
        default_factory=lambda: [
            "Read",
            "Write",
            "Edit",
            "Glob",
            "Grep",
            "Bash",
            "Task",
        ]
    )


class RateLimitConfig(BaseModel):
    """Rate limiting configuration."""

    enabled: bool = Field(default=True)
    requests_per_window: int = Field(default=100, ge=1)
    window_seconds: int = Field(default=60, ge=1)
    # Per-tier overrides (if implementing tiered rate limits)
    tier_limits: dict[str, int] = Field(default_factory=dict)
    # Endpoints to exempt from rate limiting
    exempt_paths: list[str] = Field(
        default_factory=lambda: ["/", "/health", "/schema", "/schema/openapi.json"]
    )


class ICCCConfig(BaseModel):
    """Complete iCCC configuration."""

    mongodb: MongoDBConfig = Field(default_factory=MongoDBConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    anthropic: AnthropicConfig = Field(default_factory=AnthropicConfig)
    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)

    # Global settings
    log_level: str = Field(default="INFO")
    data_dir: str = Field(default="./data")
    enable_telemetry: bool = Field(default=False)

    @classmethod
    def from_yaml(cls, path: Path) -> "ICCCConfig":
        """Load configuration from YAML file."""
        if not path.exists():
            raise ConfigNotFoundError(str(path))

        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        except Exception as e:
            raise ConfigValidationError([str(e)]) from e

    @classmethod
    def from_env(cls) -> "ICCCConfig":
        """Load configuration from environment variables."""
        config_dict: dict[str, Any] = {}

        # MongoDB - support both ICCC_ prefix and direct env vars
        mongo_host = os.getenv("MONGODB_HOST") or os.getenv("ICCC_MONGODB_HOST")
        mongo_port = os.getenv("MONGODB_PORT") or os.getenv("ICCC_MONGODB_PORT")
        mongo_username = os.getenv("MONGODB_USERNAME") or os.getenv("ICCC_MONGODB_USERNAME")
        mongo_password = os.getenv("MONGODB_PASSWORD") or os.getenv("ICCC_MONGODB_PASSWORD")
        mongo_dbname = os.getenv("MONGODB_DBNAME") or os.getenv("ICCC_MONGODB_DATABASE")

        # Build MongoDB URI from components or use full URI
        # Priority: MONGODB_URL > components > ICCC_MONGODB_URI
        mongo_url = os.getenv("MONGODB_URL")
        if mongo_url:
            config_dict.setdefault("mongodb", {})["uri"] = mongo_url
            if mongo_dbname:
                config_dict.setdefault("mongodb", {})["database"] = mongo_dbname
        elif mongo_uri := os.getenv("ICCC_MONGODB_URI"):
            config_dict.setdefault("mongodb", {})["uri"] = mongo_uri
            if mongo_db := (os.getenv("ICCC_MONGODB_DATABASE") or os.getenv("MONGODB_DBNAME")):
                config_dict.setdefault("mongodb", {})["database"] = mongo_db
        elif mongo_host and mongo_dbname:
            # Build URI from components
            port = mongo_port or "27017"
            if mongo_username and mongo_password:
                mongo_uri = f"mongodb://{mongo_username}:{mongo_password}@{mongo_host}:{port}/{mongo_dbname}"
            else:
                mongo_uri = f"mongodb://{mongo_host}:{port}/{mongo_dbname}"
            config_dict.setdefault("mongodb", {})["uri"] = mongo_uri
            config_dict.setdefault("mongodb", {})["database"] = mongo_dbname
        elif mongo_db := os.getenv("ICCC_MONGODB_DATABASE"):
            config_dict.setdefault("mongodb", {})["database"] = mongo_db

        # Redis - support both formats
        redis_host = os.getenv("REDIS_HOST") or os.getenv("ICCC_REDIS_HOST")
        redis_port = os.getenv("REDIS_PORT") or os.getenv("ICCC_REDIS_PORT")
        redis_password = os.getenv("REDIS_PASSWORD") or os.getenv("ICCC_REDIS_PASSWORD")
        redis_db = os.getenv("REDIS_DB") or os.getenv("ICCC_REDIS_DB")

        if redis_host:
            config_dict.setdefault("redis", {})["host"] = redis_host
        if redis_port:
            config_dict.setdefault("redis", {})["port"] = int(redis_port)
        if redis_password:
            config_dict.setdefault("redis", {})["password"] = redis_password
        if redis_db:
            config_dict.setdefault("redis", {})["db"] = int(redis_db)

        # Anthropic
        if api_key := os.getenv("ANTHROPIC_API_KEY"):
            config_dict.setdefault("anthropic", {})["api_key"] = api_key
        if model := os.getenv("ICCC_DEFAULT_MODEL"):
            config_dict.setdefault("anthropic", {})["default_model"] = model

        # Orchestration
        if max_agents := os.getenv("ICCC_MAX_CONCURRENT_AGENTS"):
            config_dict.setdefault("orchestration", {})[
                "max_concurrent_agents"
            ] = int(max_agents)
        if timeout := os.getenv("ICCC_TASK_TIMEOUT"):
            config_dict.setdefault("orchestration", {})[
                "task_timeout_seconds"
            ] = int(timeout)

        # Observability
        if server_port := os.getenv("ICCC_OBSERVABILITY_PORT"):
            config_dict.setdefault("observability", {})["server_port"] = int(
                server_port
            )
        if enable_ai := os.getenv("ICCC_ENABLE_AI_SUMMARIES"):
            config_dict.setdefault("observability", {})[
                "enable_ai_summaries"
            ] = enable_ai.lower() in ("true", "1", "yes")

        # Global
        if log_level := os.getenv("ICCC_LOG_LEVEL"):
            config_dict["log_level"] = log_level
        if data_dir := os.getenv("ICCC_DATA_DIR"):
            config_dict["data_dir"] = data_dir

        return cls(**config_dict)

    def to_yaml(self, path: Path) -> None:
        """Save configuration to YAML file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.safe_dump(self.model_dump(), f, default_flow_style=False)

    def merge_env_overrides(self) -> "ICCCConfig":
        """Merge environment variable overrides into config."""
        updates: dict[str, Any] = {}

        # MongoDB overrides - support both formats
        mongo_host = os.getenv("MONGODB_HOST") or os.getenv("ICCC_MONGODB_HOST")
        mongo_port = os.getenv("MONGODB_PORT") or os.getenv("ICCC_MONGODB_PORT")
        mongo_username = os.getenv("MONGODB_USERNAME") or os.getenv("ICCC_MONGODB_USERNAME")
        mongo_password = os.getenv("MONGODB_PASSWORD") or os.getenv("ICCC_MONGODB_PASSWORD")
        mongo_dbname = os.getenv("MONGODB_DBNAME") or os.getenv("ICCC_MONGODB_DATABASE")

        if mongo_uri := (os.getenv("MONGODB_URL") or os.getenv("ICCC_MONGODB_URI")):
            updates.setdefault("mongodb", {})["uri"] = mongo_uri
            # Also allow overriding database if provided explicitly
            if mongo_db := (os.getenv("MONGODB_DBNAME") or os.getenv("ICCC_MONGODB_DATABASE")):
                updates.setdefault("mongodb", {})["database"] = mongo_db
        elif mongo_host and mongo_dbname:
            port = mongo_port or "27017"
            if mongo_username and mongo_password:
                mongo_uri = f"mongodb://{mongo_username}:{mongo_password}@{mongo_host}:{port}/{mongo_dbname}"
            else:
                mongo_uri = f"mongodb://{mongo_host}:{port}/{mongo_dbname}"
            updates.setdefault("mongodb", {})["uri"] = mongo_uri
            updates.setdefault("mongodb", {})["database"] = mongo_dbname
        elif mongo_db := os.getenv("ICCC_MONGODB_DATABASE"):
            updates.setdefault("mongodb", {})["database"] = mongo_db

        # Redis overrides - support both formats
        redis_host = os.getenv("REDIS_HOST") or os.getenv("ICCC_REDIS_HOST")
        redis_port = os.getenv("REDIS_PORT") or os.getenv("ICCC_REDIS_PORT")
        redis_password = os.getenv("REDIS_PASSWORD") or os.getenv("ICCC_REDIS_PASSWORD")
        redis_db = os.getenv("REDIS_DB") or os.getenv("ICCC_REDIS_DB")

        if redis_host:
            updates.setdefault("redis", {})["host"] = redis_host
        if redis_port:
            updates.setdefault("redis", {})["port"] = int(redis_port)
        if redis_password:
            updates.setdefault("redis", {})["password"] = redis_password
        if redis_db:
            updates.setdefault("redis", {})["db"] = int(redis_db)

        # Anthropic overrides
        if api_key := os.getenv("ANTHROPIC_API_KEY"):
            updates.setdefault("anthropic", {})["api_key"] = api_key
        if model := os.getenv("ICCC_DEFAULT_MODEL"):
            updates.setdefault("anthropic", {})["default_model"] = model

        # Orchestration overrides
        if max_agents := os.getenv("ICCC_MAX_CONCURRENT_AGENTS"):
            updates.setdefault("orchestration", {})["max_concurrent_agents"] = int(
                max_agents
            )
        if timeout := os.getenv("ICCC_TASK_TIMEOUT"):
            updates.setdefault("orchestration", {})["task_timeout_seconds"] = int(
                timeout
            )

        # Observability overrides
        if server_port := os.getenv("ICCC_OBSERVABILITY_PORT"):
            updates.setdefault("observability", {})["server_port"] = int(server_port)
        if enable_ai := os.getenv("ICCC_ENABLE_AI_SUMMARIES"):
            updates.setdefault("observability", {})[
                "enable_ai_summaries"
            ] = enable_ai.lower() in ("true", "1", "yes")

        # Rate limit overrides
        if rate_enabled := os.getenv("ICCC_RATE_LIMIT_ENABLED"):
            updates.setdefault("rate_limit", {})[
                "enabled"
            ] = rate_enabled.lower() in ("true", "1", "yes")
        if rate_requests := os.getenv("ICCC_RATE_LIMIT_REQUESTS_PER_WINDOW"):
            updates.setdefault("rate_limit", {})["requests_per_window"] = int(
                rate_requests
            )
        if rate_window := os.getenv("ICCC_RATE_LIMIT_WINDOW_SECONDS"):
            updates.setdefault("rate_limit", {})["window_seconds"] = int(rate_window)

        # Global setting overrides
        if log_level := os.getenv("ICCC_LOG_LEVEL"):
            updates["log_level"] = log_level
        if data_dir := os.getenv("ICCC_DATA_DIR"):
            updates["data_dir"] = data_dir

        if not updates:
            return self

        # Create new config with merged values
        current = self.model_dump()
        for section, values in updates.items():
            if isinstance(values, dict) and section in current:
                current[section].update(values)
            else:
                current[section] = values

        return ICCCConfig(**current)


# Global configuration instance
_config: ICCCConfig | None = None


def load_config(
    config_path: Path | None = None, use_env: bool = True
) -> ICCCConfig:
    """
    Load configuration with environment overrides.

    Args:
        config_path: Path to YAML config file (optional)
        use_env: Whether to apply environment variable overrides

    Returns:
        Loaded and merged configuration
    """
    global _config

    # Start with defaults
    if config_path and config_path.exists():
        config = ICCCConfig.from_yaml(config_path)
    else:
        config = ICCCConfig()

    # Apply environment overrides
    if use_env:
        config = config.merge_env_overrides()

    _config = config
    return config


def get_config() -> ICCCConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config(config_path: Path | None = None) -> ICCCConfig:
    """Reload configuration from file and environment."""
    global _config
    _config = None
    return load_config(config_path)
