"""Custom exception hierarchy for iCCC."""

from typing import Any, Optional
from uuid import UUID


class ICCCError(Exception):
    """Base exception for all iCCC errors."""

    def __init__(self, message: str, context: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}


# ==================== Agent Errors ====================


class AgentError(ICCCError):
    """Base class for agent-related errors."""

    pass


class AgentNotFoundError(AgentError):
    """Agent not found in database."""

    def __init__(self, agent_id: str) -> None:
        super().__init__(
            f"Agent not found: {agent_id}", context={"agent_id": agent_id}
        )
        self.agent_id = agent_id


class AgentBusyError(AgentError):
    """Agent is already executing a task."""

    def __init__(self, agent_id: str, current_task_id: UUID) -> None:
        super().__init__(
            f"Agent {agent_id} is busy with task {current_task_id}",
            context={"agent_id": agent_id, "current_task_id": str(current_task_id)},
        )
        self.agent_id = agent_id
        self.current_task_id = current_task_id


class AgentCrashedError(AgentError):
    """Agent process crashed unexpectedly."""

    def __init__(self, agent_id: str, exit_code: int, stderr: str) -> None:
        super().__init__(
            f"Agent {agent_id} crashed with exit code {exit_code}",
            context={"agent_id": agent_id, "exit_code": exit_code, "stderr": stderr},
        )
        self.agent_id = agent_id
        self.exit_code = exit_code
        self.stderr = stderr


# ==================== Task Errors ====================


class TaskError(ICCCError):
    """Base class for task-related errors."""

    pass


class TaskNotFoundError(TaskError):
    """Task not found in database."""

    def __init__(self, task_id: UUID) -> None:
        super().__init__(f"Task not found: {task_id}", context={"task_id": str(task_id)})
        self.task_id = task_id


class TaskDependencyError(TaskError):
    """Task has unmet dependencies."""

    def __init__(self, task_id: UUID, unmet_dependencies: list[UUID]) -> None:
        super().__init__(
            f"Task {task_id} has unmet dependencies: {unmet_dependencies}",
            context={
                "task_id": str(task_id),
                "unmet_dependencies": [str(d) for d in unmet_dependencies],
            },
        )
        self.task_id = task_id
        self.unmet_dependencies = unmet_dependencies


class TaskTimeoutError(TaskError):
    """Task execution exceeded timeout."""

    def __init__(self, task_id: UUID, timeout_seconds: float) -> None:
        super().__init__(
            f"Task {task_id} timed out after {timeout_seconds}s",
            context={"task_id": str(task_id), "timeout_seconds": timeout_seconds},
        )
        self.task_id = task_id
        self.timeout_seconds = timeout_seconds


class TaskExecutionError(TaskError):
    """Task execution failed."""

    def __init__(
        self, task_id: UUID, agent_id: str, original_error: Exception
    ) -> None:
        super().__init__(
            f"Task {task_id} failed during execution by {agent_id}: {original_error}",
            context={
                "task_id": str(task_id),
                "agent_id": agent_id,
                "error_type": type(original_error).__name__,
                "error_message": str(original_error),
            },
        )
        self.task_id = task_id
        self.agent_id = agent_id
        self.original_error = original_error


# ==================== Planning Errors ====================


class PlanningError(ICCCError):
    """Base class for planning-related errors."""

    pass


class PlanningFailedError(PlanningError):
    """Planner failed to find a solution."""

    def __init__(self, reason: str, initial_state: dict, goal_state: dict) -> None:
        super().__init__(
            f"Planning failed: {reason}",
            context={
                "reason": reason,
                "initial_state": initial_state,
                "goal_state": goal_state,
            },
        )
        self.reason = reason


class DecompositionFailedError(PlanningError):
    """HTN decomposition failed."""

    def __init__(self, task_description: str, reason: str) -> None:
        super().__init__(
            f"Task decomposition failed for '{task_description}': {reason}",
            context={"task_description": task_description, "reason": reason},
        )
        self.task_description = task_description
        self.reason = reason


# ==================== Lock Errors ====================


class LockError(ICCCError):
    """Base class for locking errors."""

    pass


class LockAcquisitionError(LockError):
    """Failed to acquire lock."""

    def __init__(
        self, file_path: str, lock_type: str, holder: Optional[str] = None
    ) -> None:
        holder_msg = f" (held by {holder})" if holder else ""
        super().__init__(
            f"Failed to acquire {lock_type} lock for {file_path}{holder_msg}",
            context={"file_path": file_path, "lock_type": lock_type, "holder": holder},
        )
        self.file_path = file_path
        self.lock_type = lock_type
        self.holder = holder


class LockTimeoutError(LockError):
    """Lock acquisition timed out."""

    def __init__(self, file_path: str, timeout_seconds: float) -> None:
        super().__init__(
            f"Lock acquisition timed out for {file_path} after {timeout_seconds}s",
            context={"file_path": file_path, "timeout_seconds": timeout_seconds},
        )
        self.file_path = file_path
        self.timeout_seconds = timeout_seconds


# ==================== Git/Worktree Errors ====================


class WorktreeError(ICCCError):
    """Base class for worktree errors."""

    pass


class WorktreeCreationError(WorktreeError):
    """Failed to create Git worktree."""

    def __init__(self, agent_id: str, reason: str) -> None:
        super().__init__(
            f"Failed to create worktree for {agent_id}: {reason}",
            context={"agent_id": agent_id, "reason": reason},
        )
        self.agent_id = agent_id
        self.reason = reason


class WorktreeMergeConflictError(WorktreeError):
    """Merge conflict detected in worktree."""

    def __init__(
        self, agent_id: str, conflicting_files: list[str], conflict_details: str
    ) -> None:
        super().__init__(
            f"Merge conflict in worktree for {agent_id}: {len(conflicting_files)} files",
            context={
                "agent_id": agent_id,
                "conflicting_files": conflicting_files,
                "conflict_details": conflict_details,
            },
        )
        self.agent_id = agent_id
        self.conflicting_files = conflicting_files
        self.conflict_details = conflict_details


# ==================== API Errors ====================


class APIError(ICCCError):
    """Base class for API-related errors."""

    pass


class RateLimitError(APIError):
    """API rate limit exceeded."""

    def __init__(
        self, service: str, retry_after: Optional[float] = None, quota_info: Optional[dict] = None
    ) -> None:
        retry_msg = f" (retry after {retry_after}s)" if retry_after else ""
        super().__init__(
            f"Rate limit exceeded for {service}{retry_msg}",
            context={
                "service": service,
                "retry_after": retry_after,
                "quota_info": quota_info,
            },
        )
        self.service = service
        self.retry_after = retry_after
        self.quota_info = quota_info


class ModelOverloadedError(APIError):
    """Claude model is overloaded."""

    def __init__(self, model: str, retry_after: Optional[float] = None) -> None:
        super().__init__(
            f"Model {model} is overloaded",
            context={"model": model, "retry_after": retry_after},
        )
        self.model = model
        self.retry_after = retry_after


# ==================== Queue Errors ====================


class QueueError(ICCCError):
    """Base class for queue errors."""

    pass


class QueueEmptyError(QueueError):
    """Task queue is empty."""

    def __init__(self) -> None:
        super().__init__("Task queue is empty")


class QueueConnectionError(QueueError):
    """Failed to connect to queue backend."""

    def __init__(self, backend: str, reason: str) -> None:
        super().__init__(
            f"Failed to connect to {backend} queue: {reason}",
            context={"backend": backend, "reason": reason},
        )
        self.backend = backend
        self.reason = reason


# ==================== Quality Gate Errors ====================


class QualityGateError(ICCCError):
    """Base class for quality gate errors."""

    pass


class QualityGateFailedError(QualityGateError):
    """Required quality gate failed."""

    def __init__(
        self, gate_name: str, output: str, issues_count: int
    ) -> None:
        super().__init__(
            f"Quality gate '{gate_name}' failed with {issues_count} issues",
            context={
                "gate_name": gate_name,
                "output": output,
                "issues_count": issues_count,
            },
        )
        self.gate_name = gate_name
        self.output = output
        self.issues_count = issues_count


# ==================== Configuration Errors ====================


class ConfigError(ICCCError):
    """Base class for configuration errors."""

    pass


class ConfigNotFoundError(ConfigError):
    """Configuration file not found."""

    def __init__(self, config_path: str) -> None:
        super().__init__(
            f"Configuration file not found: {config_path}",
            context={"config_path": config_path},
        )
        self.config_path = config_path


class ConfigValidationError(ConfigError):
    """Configuration validation failed."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__(
            f"Configuration validation failed: {len(errors)} errors",
            context={"errors": errors},
        )
        self.errors = errors
