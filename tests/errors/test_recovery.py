"""Tests for error recovery strategies."""

from uuid import uuid4

import pytest

from iccc.errors.exceptions import (
    AgentCrashedError,
    LockAcquisitionError,
    ModelOverloadedError,
    QualityGateFailedError,
    RateLimitError,
    TaskExecutionError,
    WorktreeMergeConflictError,
)
from iccc.errors.recovery import (
    AgentCrashRecoveryHandler,
    ErrorRecoveryManager,
    LockConflictRecoveryHandler,
    MergeConflictRecoveryHandler,
    ModelOverloadRecoveryHandler,
    QualityGateRecoveryHandler,
    RateLimitRecoveryHandler,
    RecoveryAction,
    RecoveryResult,
    RecoveryStrategy,
    TaskExecutionRecoveryHandler,
)


class TestRecoveryStrategy:
    """Test RecoveryStrategy configuration."""

    def test_recovery_strategy_defaults(self):
        """Test RecoveryStrategy with default values."""
        strategy = RecoveryStrategy(action=RecoveryAction.RETRY)
        assert strategy.action == RecoveryAction.RETRY
        assert strategy.max_attempts == 3
        assert strategy.delay_seconds == 5.0
        assert strategy.fallback_strategy is None
        assert strategy.metadata == {}

    def test_recovery_strategy_custom(self):
        """Test RecoveryStrategy with custom values."""
        fallback = RecoveryStrategy(action=RecoveryAction.FAIL)
        strategy = RecoveryStrategy(
            action=RecoveryAction.RETRY,
            max_attempts=5,
            delay_seconds=10.0,
            fallback_strategy=fallback,
            metadata={"key": "value"},
        )
        assert strategy.action == RecoveryAction.RETRY
        assert strategy.max_attempts == 5
        assert strategy.delay_seconds == 10.0
        assert strategy.fallback_strategy == fallback
        assert strategy.metadata == {"key": "value"}


class TestRecoveryResult:
    """Test RecoveryResult model."""

    def test_recovery_result_defaults(self):
        """Test RecoveryResult with default values."""
        result = RecoveryResult(
            success=True,
            action_taken=RecoveryAction.RETRY,
            message="Will retry",
        )
        assert result.success is True
        assert result.action_taken == RecoveryAction.RETRY
        assert result.message == "Will retry"
        assert result.should_retry is False
        assert result.delay_before_retry == 0.0
        assert result.metadata == {}

    def test_recovery_result_full(self):
        """Test RecoveryResult with all fields."""
        result = RecoveryResult(
            success=True,
            action_taken=RecoveryAction.RETRY,
            message="Will retry",
            should_retry=True,
            delay_before_retry=30.0,
            metadata={"attempt": 2},
        )
        assert result.success is True
        assert result.should_retry is True
        assert result.delay_before_retry == 30.0
        assert result.metadata == {"attempt": 2}


@pytest.mark.asyncio
class TestRateLimitRecoveryHandler:
    """Test RateLimitRecoveryHandler."""

    async def test_can_handle_rate_limit_error(self):
        """Test handler recognizes RateLimitError."""
        handler = RateLimitRecoveryHandler()
        error = RateLimitError(service="claude", retry_after=60.0)
        assert await handler.can_handle(error) is True

    async def test_cannot_handle_other_error(self):
        """Test handler rejects non-rate-limit errors."""
        handler = RateLimitRecoveryHandler()
        error = ValueError("Not a rate limit error")
        assert await handler.can_handle(error) is False

    async def test_recover_with_retry_after(self):
        """Test recovery uses retry_after from error."""
        handler = RateLimitRecoveryHandler()
        error = RateLimitError(service="claude", retry_after=60.0, quota_info={"limit": 1000})

        result = await handler.recover(error, {})

        assert result.success is True
        assert result.action_taken == RecoveryAction.RETRY
        assert result.should_retry is True
        assert result.delay_before_retry == 60.0
        assert result.metadata["service"] == "claude"

    async def test_recover_without_retry_after(self):
        """Test recovery defaults to 60s when retry_after is None."""
        handler = RateLimitRecoveryHandler()
        error = RateLimitError(service="claude")

        result = await handler.recover(error, {})

        assert result.success is True
        assert result.delay_before_retry == 60.0


@pytest.mark.asyncio
class TestModelOverloadRecoveryHandler:
    """Test ModelOverloadRecoveryHandler."""

    async def test_can_handle_model_overload_error(self):
        """Test handler recognizes ModelOverloadedError."""
        handler = ModelOverloadRecoveryHandler()
        error = ModelOverloadedError(model="opus-4")
        assert await handler.can_handle(error) is True

    async def test_downgrade_from_opus_to_sonnet(self):
        """Test downgrading from Opus to Sonnet."""
        handler = ModelOverloadRecoveryHandler()
        error = ModelOverloadedError(model="claude-opus-4-20250514")

        result = await handler.recover(error, {})

        assert result.success is True
        assert result.action_taken == RecoveryAction.DOWNGRADE_MODEL
        assert result.should_retry is True
        assert result.metadata["new_model"] == "claude-sonnet-4-20250514"

    async def test_downgrade_from_sonnet_to_haiku(self):
        """Test downgrading from Sonnet to Haiku."""
        handler = ModelOverloadRecoveryHandler()
        error = ModelOverloadedError(model="claude-sonnet-4-20250514")

        result = await handler.recover(error, {})

        assert result.success is True
        assert result.action_taken == RecoveryAction.DOWNGRADE_MODEL
        assert result.metadata["new_model"] == "claude-3-5-haiku-latest"

    async def test_retry_when_at_lowest_tier(self):
        """Test retry when already at Haiku tier."""
        handler = ModelOverloadRecoveryHandler()
        error = ModelOverloadedError(model="claude-3-5-haiku-latest", retry_after=30.0)

        result = await handler.recover(error, {})

        assert result.success is True
        assert result.action_taken == RecoveryAction.RETRY
        assert result.should_retry is True
        assert result.delay_before_retry == 30.0


@pytest.mark.asyncio
class TestAgentCrashRecoveryHandler:
    """Test AgentCrashRecoveryHandler."""

    async def test_can_handle_agent_crash(self):
        """Test handler recognizes AgentCrashedError."""
        handler = AgentCrashRecoveryHandler()
        error = AgentCrashedError(agent_id="agent-123", exit_code=1, stderr="Error")
        assert await handler.can_handle(error) is True

    async def test_recover_reassigns_task(self):
        """Test recovery reassigns task to another agent."""
        handler = AgentCrashRecoveryHandler()
        task_id = uuid4()
        error = AgentCrashedError(
            agent_id="agent-123", exit_code=1, stderr="Segmentation fault"
        )

        result = await handler.recover(error, {"task_id": task_id})

        assert result.success is True
        assert result.action_taken == RecoveryAction.REASSIGN
        assert result.should_retry is True
        assert result.delay_before_retry == 10.0
        assert result.metadata["crashed_agent_id"] == "agent-123"
        assert result.metadata["exit_code"] == 1


@pytest.mark.asyncio
class TestLockConflictRecoveryHandler:
    """Test LockConflictRecoveryHandler."""

    async def test_can_handle_lock_error(self):
        """Test handler recognizes LockAcquisitionError."""
        handler = LockConflictRecoveryHandler()
        error = LockAcquisitionError(
            file_path="/test.py", lock_type="WRITE", holder="agent-123"
        )
        assert await handler.can_handle(error) is True

    async def test_retry_with_exponential_backoff(self):
        """Test retry with exponential backoff."""
        handler = LockConflictRecoveryHandler()
        error = LockAcquisitionError(
            file_path="/test.py", lock_type="WRITE", holder="agent-123"
        )

        # Attempt 1: 2^1 = 2s
        result1 = await handler.recover(error, {"attempt": 1})
        assert result1.success is True
        assert result1.action_taken == RecoveryAction.RETRY
        assert result1.delay_before_retry == 2
        assert result1.metadata["attempt"] == 2

        # Attempt 2: 2^2 = 4s
        result2 = await handler.recover(error, {"attempt": 2})
        assert result2.delay_before_retry == 4

        # Attempt 3: 2^3 = 8s
        result3 = await handler.recover(error, {"attempt": 3})
        assert result3.delay_before_retry == 8

    async def test_fail_after_max_attempts(self):
        """Test failure after max attempts."""
        handler = LockConflictRecoveryHandler()
        error = LockAcquisitionError(
            file_path="/test.py", lock_type="WRITE", holder="agent-123"
        )

        result = await handler.recover(error, {"attempt": 5})

        assert result.success is False
        assert result.action_taken == RecoveryAction.FAIL
        assert result.should_retry is False


@pytest.mark.asyncio
class TestMergeConflictRecoveryHandler:
    """Test MergeConflictRecoveryHandler."""

    async def test_can_handle_merge_conflict(self):
        """Test handler recognizes WorktreeMergeConflictError."""
        handler = MergeConflictRecoveryHandler()
        error = WorktreeMergeConflictError(
            agent_id="agent-123",
            conflicting_files=["/test.py"],
            conflict_details="conflict",
        )
        assert await handler.can_handle(error) is True

    async def test_requires_manual_intervention(self):
        """Test merge conflicts require manual intervention."""
        handler = MergeConflictRecoveryHandler()
        error = WorktreeMergeConflictError(
            agent_id="agent-123",
            conflicting_files=["/test.py", "/main.py"],
            conflict_details="<<<<<<< HEAD\ncode\n=======",
        )

        result = await handler.recover(error, {})

        assert result.success is False
        assert result.action_taken == RecoveryAction.MANUAL_INTERVENTION
        assert result.should_retry is False
        assert result.metadata["agent_id"] == "agent-123"
        assert len(result.metadata["conflicting_files"]) == 2


@pytest.mark.asyncio
class TestQualityGateRecoveryHandler:
    """Test QualityGateRecoveryHandler."""

    async def test_can_handle_quality_gate_error(self):
        """Test handler recognizes QualityGateFailedError."""
        handler = QualityGateRecoveryHandler()
        error = QualityGateFailedError(
            gate_name="pre-commit", output="lint errors", issues_count=3
        )
        assert await handler.can_handle(error) is True

    async def test_replan_on_first_failure(self):
        """Test replanning on first quality gate failure."""
        handler = QualityGateRecoveryHandler()
        error = QualityGateFailedError(
            gate_name="pre-commit", output="lint: 3 errors", issues_count=3
        )

        result = await handler.recover(error, {"attempt": 1})

        assert result.success is True
        assert result.action_taken == RecoveryAction.REPLAN
        assert result.should_retry is True
        assert result.delay_before_retry == 5.0
        assert result.metadata["attempt"] == 2
        assert result.metadata["issues_count"] == 3

    async def test_fail_after_max_replans(self):
        """Test failure after max replan attempts."""
        handler = QualityGateRecoveryHandler()
        error = QualityGateFailedError(
            gate_name="pre-commit", output="lint: 3 errors", issues_count=3
        )

        result = await handler.recover(error, {"attempt": 2})

        assert result.success is False
        assert result.action_taken == RecoveryAction.FAIL
        assert result.should_retry is False


@pytest.mark.asyncio
class TestTaskExecutionRecoveryHandler:
    """Test TaskExecutionRecoveryHandler."""

    async def test_can_handle_task_execution_error(self):
        """Test handler recognizes TaskExecutionError."""
        handler = TaskExecutionRecoveryHandler()
        task_id = uuid4()
        error = TaskExecutionError(
            task_id=task_id,
            agent_id="agent-123",
            original_error=ValueError("Test error"),
        )
        assert await handler.can_handle(error) is True

    async def test_retry_on_early_attempts(self):
        """Test retry on early attempts."""
        handler = TaskExecutionRecoveryHandler()
        task_id = uuid4()
        error = TaskExecutionError(
            task_id=task_id,
            agent_id="agent-123",
            original_error=ValueError("Test error"),
        )

        result = await handler.recover(error, {"attempt": 1})

        assert result.success is True
        assert result.action_taken == RecoveryAction.RETRY
        assert result.should_retry is True
        assert result.delay_before_retry == 10.0
        assert result.metadata["attempt"] == 2

    async def test_reassign_after_max_attempts(self):
        """Test reassignment after max retry attempts."""
        handler = TaskExecutionRecoveryHandler()
        task_id = uuid4()
        error = TaskExecutionError(
            task_id=task_id,
            agent_id="agent-123",
            original_error=ValueError("Test error"),
        )

        result = await handler.recover(error, {"attempt": 3})

        assert result.success is True
        assert result.action_taken == RecoveryAction.REASSIGN
        assert result.should_retry is True
        assert result.delay_before_retry == 30.0
        assert result.metadata["failed_agent_id"] == "agent-123"


@pytest.mark.asyncio
class TestErrorRecoveryManager:
    """Test ErrorRecoveryManager."""

    async def test_manager_initialization(self):
        """Test manager initializes with all handlers."""
        manager = ErrorRecoveryManager()
        assert len(manager.handlers) == 7

    async def test_recover_rate_limit_error(self):
        """Test manager routes RateLimitError to correct handler."""
        manager = ErrorRecoveryManager()
        error = RateLimitError(service="claude", retry_after=60.0)

        result = await manager.recover(error)

        assert result.success is True
        assert result.action_taken == RecoveryAction.RETRY
        assert result.delay_before_retry == 60.0

    async def test_recover_agent_crash(self):
        """Test manager routes AgentCrashedError to correct handler."""
        manager = ErrorRecoveryManager()
        task_id = uuid4()
        error = AgentCrashedError(
            agent_id="agent-123", exit_code=1, stderr="Error"
        )

        result = await manager.recover(error, {"task_id": task_id})

        assert result.success is True
        assert result.action_taken == RecoveryAction.REASSIGN

    async def test_recover_unknown_error(self):
        """Test manager handles unknown errors."""
        manager = ErrorRecoveryManager()
        error = RuntimeError("Unknown error")

        result = await manager.recover(error)

        assert result.success is False
        assert result.action_taken == RecoveryAction.FAIL
        assert result.should_retry is False
        assert "RuntimeError" in result.metadata["error_type"]

    async def test_recover_with_context(self):
        """Test manager passes context to handlers."""
        manager = ErrorRecoveryManager()
        error = LockAcquisitionError(
            file_path="/test.py", lock_type="WRITE", holder="agent-123"
        )

        result = await manager.recover(error, {"attempt": 2})

        assert result.metadata["attempt"] == 3  # Handler incremented

    async def test_recover_without_context(self):
        """Test manager handles None context."""
        manager = ErrorRecoveryManager()
        error = RateLimitError(service="claude")

        result = await manager.recover(error, None)

        assert result.success is True
