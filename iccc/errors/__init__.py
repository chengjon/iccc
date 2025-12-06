"""Error handling and recovery for iCCC."""

from iccc.errors.exceptions import (
    AgentBusyError,
    AgentCrashedError,
    AgentError,
    AgentNotFoundError,
    APIError,
    ConfigError,
    ConfigNotFoundError,
    ConfigValidationError,
    DecompositionFailedError,
    ICCCError,
    LockAcquisitionError,
    LockError,
    LockTimeoutError,
    ModelOverloadedError,
    PlanningError,
    PlanningFailedError,
    QualityGateError,
    QualityGateFailedError,
    QueueConnectionError,
    QueueEmptyError,
    QueueError,
    RateLimitError,
    TaskDependencyError,
    TaskError,
    TaskExecutionError,
    TaskNotFoundError,
    TaskTimeoutError,
    WorktreeCreationError,
    WorktreeError,
    WorktreeMergeConflictError,
)
from iccc.errors.recovery import (
    ErrorRecoveryManager,
    RecoveryAction,
    RecoveryResult,
    RecoveryStrategy,
)
from iccc.errors.retry import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitBreakerState,
    RetryConfig,
    RetryExecutor,
    RetryExhaustedError,
    RetryStrategy,
    get_circuit_breaker,
    with_circuit_breaker,
    with_retry,
)

__all__ = [
    # Base exceptions
    "ICCCError",
    # Agent errors
    "AgentError",
    "AgentNotFoundError",
    "AgentBusyError",
    "AgentCrashedError",
    # Task errors
    "TaskError",
    "TaskNotFoundError",
    "TaskDependencyError",
    "TaskTimeoutError",
    "TaskExecutionError",
    # Planning errors
    "PlanningError",
    "PlanningFailedError",
    "DecompositionFailedError",
    # Lock errors
    "LockError",
    "LockAcquisitionError",
    "LockTimeoutError",
    # Worktree errors
    "WorktreeError",
    "WorktreeCreationError",
    "WorktreeMergeConflictError",
    # API errors
    "APIError",
    "RateLimitError",
    "ModelOverloadedError",
    # Queue errors
    "QueueError",
    "QueueEmptyError",
    "QueueConnectionError",
    # Quality errors
    "QualityGateError",
    "QualityGateFailedError",
    # Config errors
    "ConfigError",
    "ConfigNotFoundError",
    "ConfigValidationError",
    # Recovery
    "RecoveryAction",
    "RecoveryStrategy",
    "RecoveryResult",
    "ErrorRecoveryManager",
    # Retry
    "RetryStrategy",
    "RetryConfig",
    "RetryExecutor",
    "RetryExhaustedError",
    "with_retry",
    # Circuit breaker
    "CircuitBreakerState",
    "CircuitBreakerConfig",
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "get_circuit_breaker",
    "with_circuit_breaker",
]
