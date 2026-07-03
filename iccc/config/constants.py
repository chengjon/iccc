"""
iCCC 系统常量配置

集中管理所有硬编码的值，包括角色名称、队列前缀、超时设置等。
"""

# 角色定义
from enum import Enum

class SystemRoles(str, Enum):
    """系统角色枚举 - 替代硬编码字符串"""
    WORKER = "worker"
    MANAGER = "manager"
    BRAIN = "brain"

# 队列配置
class QueueConfig:
    """队列相关配置"""
    PENDING_QUEUE_PREFIX = "iccc:tasks:pending"
    LOCK_PREFIX = "file_lock:"
    EVENT_STREAM = "iccc_events"
    PUBSUB_CHANNEL = "agent_events"

    # 队列TTL设置
    QUEUE_TTL_SECONDS = 3600  # 1小时
    LOCK_EXPIRY_SECONDS = 300  # 5分钟

# 超时配置
class TimeoutConfig:
    """超时相关配置"""
    # 文件锁超时
    FILE_LOCK_ACQUIRE_TIMEOUT = 30  # 秒
    FILE_LOCK_RETRY_INTERVAL = 0.5  # 秒

    # MCP服务超时
    MCP_INSTALL_TIMEOUT = 300  # 5分钟
    MCP_START_TIMEOUT = 60  # 1分钟
    MCP_HEALTH_CHECK_TIMEOUT = 10  # 10秒

    # API超时
    API_REQUEST_TIMEOUT = 30  # 30秒

    # 数据库操作超时
    DB_OPERATION_TIMEOUT = 60  # 1分钟

# 重试配置
class RetryConfig:
    """重试相关配置"""
    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY = 1  # 秒
    MAX_RETRY_DELAY = 60  # 秒
    BACKOFF_MULTIPLIER = 2

# 限制配置
class LimitConfig:
    """系统限制配置"""
    MAX_TASKS_PER_AGENT = 10
    MAX_CONCURRENT_PROJECTS = 100
    MAX_FILE_SIZE_MB = 10
    MAX_EVENT_RETENTION_DAYS = 30

    # API限制
    MAX_REQUEST_SIZE_MB = 1
    RATE_LIMIT_REQUESTS = 1000
    RATE_LIMIT_WINDOW = 60  # 秒

# 默认值配置
class DefaultConfig:
    """默认值配置"""
    DEFAULT_MODEL_TIER = "SONNET"
    DEFAULT_AGENT_MAX_TASKS = 3
    DEFAULT_PROJECT_DIR = "."
    DEFAULT_CONFIG_DIR = ".iccc/config"

    # 默认超时
    DEFAULT_TIMEOUT = 30  # 秒

    # 默认重试
    DEFAULT_MAX_RETRIES = 3

# 环境变量映射
class EnvVarConfig:
    """环境变量配置"""

    # 必需环境变量
    ANTHROPIC_API_KEY = "ANTHROPIC_API_KEY"
    MONGODB_URL = "MONGODB_URL"
    REDIS_URL = "REDIS_URL"

    # 可选环境变量
    AGENT_ID = "AGENT_ID"
    PROJECT_ROOT = "ICCC_PROJECT_ROOT"
    CONFIG_DIR = "ICCC_CONFIG_DIR"
    LOG_LEVEL = "LOG_LEVEL"

    # API配置
    API_KEYS = "ICCC_API_KEYS"
    RATE_LIMIT_REQUESTS = "ICCC_RATE_LIMIT_REQUESTS"
    RATE_LIMIT_WINDOW = "ICCC_RATE_LIMIT_WINDOW"
    ENABLE_METRICS = "ICCC_ENABLE_METRICS"

    # MCP服务配置
    MCP_SERVICES_DIR = "ICCC_MCP_SERVICES_DIR"
    MCP_TIMEOUT = "ICCC_MCP_TIMEOUT"

# 文件路径配置
class PathConfig:
    """文件路径配置"""

    # 项目相关路径
    PROJECT_CONFIG_FILE = "project.json"
    AGENTS_CONFIG_FILE = "agents.json"
    WORKFLOWS_CONFIG_FILE = "workflows.json"
    HOOKS_CONFIG_FILE = "hooks.json"

    # Hook脚本路径
    HOOK_SCRIPTS_DIR = "scripts"
    AUTO_TEST_SCRIPT = "auto_test.py"
    AGENT_COORDINATOR_SCRIPT = "agent_coordinator.py"
    SAFETY_CHECK_SCRIPT = "safety_check.py"

    # 数据库路径
    SQLITE_EVENTS_DB = "events.db"

    # 日志路径
    LOG_DIR = "logs"
    LOG_FILE = "iccc.log"

# 工具名称配置
class ToolConfig:
    """工具名称配置"""

    # 文件修改工具
    FILE_MODIFICATION_TOOLS = ["Write", "Edit", "MultiEdit"]

    # 测试工具
    TESTING_TOOLS = ["Test", "mypy", "pytest"]

    # 安全检查工具
    SECURITY_TOOLS = ["security_scan", "bandit", "semgrep"]

# 获取配置的辅助函数
def get_role_queue_prefix(role: SystemRoles) -> str:
    """根据角色获取队列前缀"""
    return f"{QueueConfig.PENDING_QUEUE_PREFIX}:{role.value}"

def get_file_lock_key(file_path: str) -> str:
    """获取文件锁的Redis键名"""
    return f"{QueueConfig.LOCK_PREFIX}{file_path}"

def get_default_hooks_config() -> dict:
    """获取默认的Hook配置"""
    return {
        "PreToolUse": {
            "command": f"python {PathConfig.HOOK_SCRIPTS_DIR}/{PathConfig.AGENT_COORDINATOR_SCRIPT} pre",
            "critical": True
        },
        "PostToolUse": {
            "command": f"python {PathConfig.HOOK_SCRIPTS_DIR}/{PathConfig.AGENT_COORDINATOR_SCRIPT} post",
            "critical": False
        },
        "SubagentStop": {
            "command": f"python {PathConfig.HOOK_SCRIPTS_DIR}/{PathConfig.AGENT_COORDINATOR_SCRIPT} subagent_stop",
            "critical": False
        }
    }

# 导出所有配置
__all__ = [
    # 枚举
    "SystemRoles",

    # 配置类
    "QueueConfig",
    "TimeoutConfig",
    "RetryConfig",
    "LimitConfig",
    "DefaultConfig",
    "EnvVarConfig",
    "PathConfig",
    "ToolConfig",

    # 辅助函数
    "get_role_queue_prefix",
    "get_file_lock_key",
    "get_default_hooks_config",
]