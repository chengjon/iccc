"""Configuration management for iCCC."""

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

from iccc.errors.exceptions import ConfigNotFoundError, ConfigValidationError


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
    password: Optional[str] = None
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
    dangerous_patterns_file: Optional[str] = None
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


class ICCCConfig(BaseModel):
    """Complete iCCC configuration."""

    mongodb: MongoDBConfig = Field(default_factory=MongoDBConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    anthropic: AnthropicConfig = Field(default_factory=AnthropicConfig)
    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)

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

        # MongoDB
        if mongo_uri := os.getenv("ICCC_MONGODB_URI"):
            config_dict.setdefault("mongodb", {})["uri"] = mongo_uri
        if mongo_db := os.getenv("ICCC_MONGODB_DATABASE"):
            config_dict.setdefault("mongodb", {})["database"] = mongo_db

        # Redis
        if redis_host := os.getenv("ICCC_REDIS_HOST"):
            config_dict.setdefault("redis", {})["host"] = redis_host
        if redis_port := os.getenv("ICCC_REDIS_PORT"):
            config_dict.setdefault("redis", {})["port"] = int(redis_port)
        if redis_password := os.getenv("ICCC_REDIS_PASSWORD"):
            config_dict.setdefault("redis", {})["password"] = redis_password

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
        env_config = self.from_env()

        # Merge non-default values from env_config
        merged_data = self.model_dump()

        for section, section_data in env_config.model_dump().items():
            if isinstance(section_data, dict):
                for key, value in section_data.items():
                    # Only override if value is different from default
                    default_section = getattr(ICCCConfig(), section)
                    if isinstance(default_section, BaseModel):
                        default_value = getattr(default_section, key, None)
                        if value != default_value:
                            merged_data.setdefault(section, {})[key] = value
            else:
                # Top-level setting
                if value != getattr(ICCCConfig(), section):
                    merged_data[section] = value

        return ICCCConfig(**merged_data)


# Global configuration instance
_config: Optional[ICCCConfig] = None


def load_config(
    config_path: Optional[Path] = None, use_env: bool = True
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


def reload_config(config_path: Optional[Path] = None) -> ICCCConfig:
    """Reload configuration from file and environment."""
    global _config
    _config = None
    return load_config(config_path)
