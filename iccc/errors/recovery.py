"""Error recovery strategies for iCCC."""

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from iccc.errors.exceptions import (
    AgentCrashedError,
    LockAcquisitionError,
    ModelOverloadedError,
    QualityGateFailedError,
    RateLimitError,
    TaskExecutionError,
    WorktreeMergeConflictError,
)

logger = logging.getLogger(__name__)


class RecoveryAction(str, Enum):
    """Types of recovery actions."""

    RETRY = "retry"
    REASSIGN = "reassign"
    DOWNGRADE_MODEL = "downgrade_model"
    SKIP = "skip"
    FAIL = "fail"
    MANUAL_INTERVENTION = "manual_intervention"
    REPLAN = "replan"
    MERGE_CONFLICT_RESOLUTION = "merge_conflict_resolution"


class RecoveryStrategy(BaseModel):
    """Configuration for error recovery."""

    action: RecoveryAction
    max_attempts: int = Field(default=3, ge=1)
    delay_seconds: float = Field(default=5.0, ge=0)
    fallback_strategy: Optional["RecoveryStrategy"] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecoveryResult(BaseModel):
    """Result of a recovery attempt."""

    success: bool
    action_taken: RecoveryAction
    message: str
    should_retry: bool = False
    delay_before_retry: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ErrorRecoveryHandler(ABC):
    """Base class for error recovery handlers."""

    @abstractmethod
    async def can_handle(self, error: Exception) -> bool:
        """Check if this handler can handle the error."""
        pass

    @abstractmethod
    async def recover(
        self, error: Exception, context: dict[str, Any]
    ) -> RecoveryResult:
        """Attempt to recover from the error."""
        pass


class RateLimitRecoveryHandler(ErrorRecoveryHandler):
    """Handle API rate limit errors."""

    async def can_handle(self, error: Exception) -> bool:
        return isinstance(error, RateLimitError)

    async def recover(
        self, error: Exception, context: dict[str, Any]
    ) -> RecoveryResult:
        assert isinstance(error, RateLimitError)

        # Use retry_after from error if available
        delay = error.retry_after or 60.0

        logger.warning(
            f"Rate limit hit for {error.service}. Waiting {delay}s before retry"
        )

        return RecoveryResult(
            success=True,
            action_taken=RecoveryAction.RETRY,
            message=f"Will retry after {delay}s due to rate limit",
            should_retry=True,
            delay_before_retry=delay,
            metadata={"service": error.service, "quota_info": error.quota_info},
        )


class ModelOverloadRecoveryHandler(ErrorRecoveryHandler):
    """Handle model overload by downgrading to cheaper model."""

    MODEL_DOWNGRADE_PATH = [
        "claude-opus-4-20250514",
        "claude-sonnet-4-20250514",
        "claude-3-5-haiku-latest",
    ]

    async def can_handle(self, error: Exception) -> bool:
        return isinstance(error, ModelOverloadedError)

    async def recover(
        self, error: Exception, context: dict[str, Any]
    ) -> RecoveryResult:
        assert isinstance(error, ModelOverloadedError)

        current_model = error.model
        current_idx = None

        # Find current model in downgrade path
        for idx, model in enumerate(self.MODEL_DOWNGRADE_PATH):
            if model == current_model:
                current_idx = idx
                break

        # Try to downgrade
        if current_idx is not None and current_idx < len(self.MODEL_DOWNGRADE_PATH) - 1:
            downgraded_model = self.MODEL_DOWNGRADE_PATH[current_idx + 1]
            logger.info(f"Downgrading model from {current_model} to {downgraded_model}")

            return RecoveryResult(
                success=True,
                action_taken=RecoveryAction.DOWNGRADE_MODEL,
                message=f"Downgraded model to {downgraded_model}",
                should_retry=True,
                delay_before_retry=5.0,
                metadata={"new_model": downgraded_model},
            )

        # Already at lowest tier, just retry with delay
        logger.warning(f"Model {current_model} overloaded, retrying after delay")
        return RecoveryResult(
            success=True,
            action_taken=RecoveryAction.RETRY,
            message="Already at lowest model tier, will retry",
            should_retry=True,
            delay_before_retry=error.retry_after or 30.0,
        )


class AgentCrashRecoveryHandler(ErrorRecoveryHandler):
    """Handle agent crashes by reassigning tasks."""

    async def can_handle(self, error: Exception) -> bool:
        return isinstance(error, AgentCrashedError)

    async def recover(
        self, error: Exception, context: dict[str, Any]
    ) -> RecoveryResult:
        assert isinstance(error, AgentCrashedError)

        task_id = context.get("task_id")

        logger.error(
            f"Agent {error.agent_id} crashed (exit code {error.exit_code}). "
            f"Reassigning task {task_id}"
        )

        return RecoveryResult(
            success=True,
            action_taken=RecoveryAction.REASSIGN,
            message="Task will be reassigned to another agent",
            should_retry=True,
            delay_before_retry=10.0,
            metadata={
                "crashed_agent_id": error.agent_id,
                "exit_code": error.exit_code,
                "stderr": error.stderr[:500],  # Truncate
            },
        )


class LockConflictRecoveryHandler(ErrorRecoveryHandler):
    """Handle file lock conflicts."""

    async def can_handle(self, error: Exception) -> bool:
        return isinstance(error, LockAcquisitionError)

    async def recover(
        self, error: Exception, context: dict[str, Any]
    ) -> RecoveryResult:
        assert isinstance(error, LockAcquisitionError)

        attempt = context.get("attempt", 1)
        max_attempts = 5

        if attempt < max_attempts:
            delay = min(2 ** attempt, 30)  # Exponential backoff, max 30s
            logger.info(
                f"Lock conflict on {error.file_path} held by {error.holder}. "
                f"Retry attempt {attempt}/{max_attempts} after {delay}s"
            )

            return RecoveryResult(
                success=True,
                action_taken=RecoveryAction.RETRY,
                message=f"Will retry lock acquisition after {delay}s",
                should_retry=True,
                delay_before_retry=delay,
                metadata={"attempt": attempt + 1},
            )

        logger.error(
            f"Failed to acquire lock on {error.file_path} after {max_attempts} attempts"
        )
        return RecoveryResult(
            success=False,
            action_taken=RecoveryAction.FAIL,
            message="Lock acquisition failed after max attempts",
            should_retry=False,
        )


class MergeConflictRecoveryHandler(ErrorRecoveryHandler):
    """Handle Git merge conflicts."""

    async def can_handle(self, error: Exception) -> bool:
        return isinstance(error, WorktreeMergeConflictError)

    async def recover(
        self, error: Exception, context: dict[str, Any]
    ) -> RecoveryResult:
        assert isinstance(error, WorktreeMergeConflictError)

        # For now, merge conflicts require manual intervention
        # Future: Could attempt automatic resolution for simple conflicts

        logger.error(
            f"Merge conflict in worktree for {error.agent_id}. "
            f"Conflicting files: {error.conflicting_files}"
        )

        return RecoveryResult(
            success=False,
            action_taken=RecoveryAction.MANUAL_INTERVENTION,
            message="Merge conflict requires manual resolution",
            should_retry=False,
            metadata={
                "agent_id": error.agent_id,
                "conflicting_files": error.conflicting_files,
                "conflict_details": error.conflict_details,
            },
        )


class QualityGateRecoveryHandler(ErrorRecoveryHandler):
    """Handle quality gate failures."""

    async def can_handle(self, error: Exception) -> bool:
        return isinstance(error, QualityGateFailedError)

    async def recover(
        self, error: Exception, context: dict[str, Any]
    ) -> RecoveryResult:
        assert isinstance(error, QualityGateFailedError)

        attempt = context.get("attempt", 1)
        max_attempts = 2

        if attempt < max_attempts:
            # Try to replan task to fix quality issues
            logger.warning(
                f"Quality gate '{error.gate_name}' failed with {error.issues_count} issues. "
                f"Attempting replan (attempt {attempt}/{max_attempts})"
            )

            return RecoveryResult(
                success=True,
                action_taken=RecoveryAction.REPLAN,
                message=f"Will replan to fix {error.issues_count} quality issues",
                should_retry=True,
                delay_before_retry=5.0,
                metadata={
                    "gate_name": error.gate_name,
                    "issues_count": error.issues_count,
                    "output_preview": error.output[:500],  # Truncate
                    "attempt": attempt + 1,
                },
            )

        logger.error(
            f"Quality gate '{error.gate_name}' still failing after {max_attempts} attempts"
        )
        return RecoveryResult(
            success=False,
            action_taken=RecoveryAction.FAIL,
            message="Quality gate failed after max replan attempts",
            should_retry=False,
            metadata={"final_output": error.output},
        )


class TaskExecutionRecoveryHandler(ErrorRecoveryHandler):
    """Handle general task execution errors."""

    async def can_handle(self, error: Exception) -> bool:
        return isinstance(error, TaskExecutionError)

    async def recover(
        self, error: Exception, context: dict[str, Any]
    ) -> RecoveryResult:
        assert isinstance(error, TaskExecutionError)

        attempt = context.get("attempt", 1)
        max_attempts = 3

        if attempt < max_attempts:
            logger.warning(
                f"Task {error.task_id} execution failed: {error.original_error}. "
                f"Retry attempt {attempt}/{max_attempts}"
            )

            return RecoveryResult(
                success=True,
                action_taken=RecoveryAction.RETRY,
                message=f"Will retry task execution (attempt {attempt + 1})",
                should_retry=True,
                delay_before_retry=10.0,
                metadata={
                    "task_id": str(error.task_id),
                    "agent_id": error.agent_id,
                    "error_type": type(error.original_error).__name__,
                    "attempt": attempt + 1,
                },
            )

        logger.error(
            f"Task {error.task_id} failed after {max_attempts} attempts. Reassigning."
        )
        return RecoveryResult(
            success=True,
            action_taken=RecoveryAction.REASSIGN,
            message="Task will be reassigned after max retry attempts",
            should_retry=True,
            delay_before_retry=30.0,
            metadata={
                "task_id": str(error.task_id),
                "failed_agent_id": error.agent_id,
            },
        )


class ErrorRecoveryManager:
    """Manages error recovery across the system."""

    def __init__(self) -> None:
        self.handlers: list[ErrorRecoveryHandler] = [
            RateLimitRecoveryHandler(),
            ModelOverloadRecoveryHandler(),
            AgentCrashRecoveryHandler(),
            LockConflictRecoveryHandler(),
            MergeConflictRecoveryHandler(),
            QualityGateRecoveryHandler(),
            TaskExecutionRecoveryHandler(),
        ]

    async def recover(
        self, error: Exception, context: dict[str, Any] | None = None
    ) -> RecoveryResult:
        """Attempt to recover from an error."""
        _context = context or {}

        # Find appropriate handler
        for handler in self.handlers:
            if await handler.can_handle(error):
                logger.info(
                    f"Using {handler.__class__.__name__} to recover from "
                    f"{type(error).__name__}"
                )
                return await handler.recover(error, _context)

        # No handler found - generic error
        logger.error(f"No recovery handler for {type(error).__name__}: {error}")
        return RecoveryResult(
            success=False,
            action_taken=RecoveryAction.FAIL,
            message=f"No recovery strategy available for {type(error).__name__}",
            should_retry=False,
            metadata={"error_type": type(error).__name__, "error_message": str(error)},
        )
