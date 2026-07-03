"""
iCCC 配置模块

提供系统配置管理和常量定义。
"""

from .constants import *
from .settings import (
    ICCCConfig,
    get_config,
    load_config,
    reload_config,
    # Import other Pydantic models if needed, but be careful of conflicts
    MongoDBConfig,
    RedisConfig,
    AnthropicConfig,
    OrchestrationConfig,
    ObservabilityConfig,
    SecurityConfig,
    # RetryConfig and RateLimitConfig are skipped due to conflict with constants.py
    # or potential overlap. Users should use ICCCConfig.retry or ICCCConfig.rate_limit
)

__all__ = [
    # 来自 settings.py
    "ICCCConfig",
    "get_config",
    "load_config",
    "reload_config",
    "MongoDBConfig",
    "RedisConfig",
    "AnthropicConfig",
    "OrchestrationConfig",
    "ObservabilityConfig",
    "SecurityConfig",

    # 来自 constants.py (枚举)
    "SystemRoles",

    # 来自 constants.py (配置常量类)
    "QueueConfig",
    "TimeoutConfig",
    "RetryConfig",  # constants.py 版本
    "LimitConfig",
    "DefaultConfig",
    "EnvVarConfig",
    "PathConfig",
    "ToolConfig",

    # 来自 constants.py (辅助函数)
    "get_role_queue_prefix",
    "get_file_lock_key",
    "get_default_hooks_config",
]
