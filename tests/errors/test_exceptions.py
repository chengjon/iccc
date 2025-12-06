"""Tests for custom exception hierarchy."""

import pytest
from uuid import uuid4

from iccc.errors.exceptions import (
    # Base
    ICCCError,
    # Agent errors
    AgentError,
    AgentNotFoundError,
    AgentBusyError,
    AgentCrashedError,
    # Task errors
    TaskError,
    TaskNotFoundError,
    TaskDependencyError,
    TaskTimeoutError,
    TaskExecutionError,
    # Planning errors
    PlanningError,
    PlanningFailedError,
    DecompositionFailedError,
    # Lock errors
    LockError,
    LockAcquisitionError,
    LockTimeoutError,
    # Worktree errors
    WorktreeError,
    WorktreeCreationError,
    WorktreeMergeConflictError,
    # API errors
    APIError,
    RateLimitError,
    ModelOverloadedError,
    # Queue errors
    QueueError,
    QueueEmptyError,
    QueueConnectionError,
    # Quality gate errors
    QualityGateError,
    QualityGateFailedError,
    # Config errors
    ConfigError,
    ConfigNotFoundError,
    ConfigValidationError,
)


class TestICCCError:
    """Test base ICCCError class."""

    def test_base_error_creation(self):
        """Test creating base error with message and context."""
        error = ICCCError("Test error", context={"key": "value"})
        assert error.message == "Test error"
        assert error.context == {"key": "value"}
        assert str(error) == "Test error"

    def test_base_error_no_context(self):
        """Test creating base error without context."""
        error = ICCCError("Test error")
        assert error.message == "Test error"
        assert error.context == {}


class TestAgentErrors:
    """Test agent-related errors."""

    def test_agent_not_found_error(self):
        """Test AgentNotFoundError creation."""
        error = AgentNotFoundError(agent_id="agent-123")
        assert error.agent_id == "agent-123"
        assert "agent-123" in str(error)
        assert error.context["agent_id"] == "agent-123"
        assert isinstance(error, AgentError)

    def test_agent_busy_error(self):
        """Test AgentBusyError creation."""
        task_id = uuid4()
        error = AgentBusyError(agent_id="agent-123", current_task_id=task_id)
        assert error.agent_id == "agent-123"
        assert error.current_task_id == task_id
        assert "agent-123" in str(error)
        assert str(task_id) in str(error)
        assert isinstance(error, AgentError)

    def test_agent_crashed_error(self):
        """Test AgentCrashedError creation."""
        error = AgentCrashedError(
            agent_id="agent-123", exit_code=1, stderr="Error output"
        )
        assert error.agent_id == "agent-123"
        assert error.exit_code == 1
        assert error.stderr == "Error output"
        assert "agent-123" in str(error)
        assert "exit code 1" in str(error)
        assert isinstance(error, AgentError)


class TestTaskErrors:
    """Test task-related errors."""

    def test_task_not_found_error(self):
        """Test TaskNotFoundError creation."""
        task_id = uuid4()
        error = TaskNotFoundError(task_id=task_id)
        assert error.task_id == task_id
        assert str(task_id) in str(error)
        assert isinstance(error, TaskError)

    def test_task_dependency_error(self):
        """Test TaskDependencyError creation."""
        task_id = uuid4()
        dep1 = uuid4()
        dep2 = uuid4()
        error = TaskDependencyError(task_id=task_id, unmet_dependencies=[dep1, dep2])
        assert error.task_id == task_id
        assert error.unmet_dependencies == [dep1, dep2]
        assert str(task_id) in str(error)
        assert isinstance(error, TaskError)

    def test_task_timeout_error(self):
        """Test TaskTimeoutError creation."""
        task_id = uuid4()
        error = TaskTimeoutError(task_id=task_id, timeout_seconds=30.0)
        assert error.task_id == task_id
        assert error.timeout_seconds == 30.0
        assert str(task_id) in str(error)
        assert "30.0" in str(error)
        assert isinstance(error, TaskError)

    def test_task_execution_error(self):
        """Test TaskExecutionError creation."""
        task_id = uuid4()
        original_error = ValueError("Test error")
        error = TaskExecutionError(
            task_id=task_id, agent_id="agent-123", original_error=original_error
        )
        assert error.task_id == task_id
        assert error.agent_id == "agent-123"
        assert error.original_error is original_error
        assert str(task_id) in str(error)
        assert "agent-123" in str(error)
        assert isinstance(error, TaskError)


class TestPlanningErrors:
    """Test planning-related errors."""

    def test_planning_failed_error(self):
        """Test PlanningFailedError creation."""
        initial = {"status": "pending"}
        goal = {"status": "completed"}
        error = PlanningFailedError(
            reason="No valid path", initial_state=initial, goal_state=goal
        )
        assert error.reason == "No valid path"
        assert "No valid path" in str(error)
        assert error.context["initial_state"] == initial
        assert error.context["goal_state"] == goal
        assert isinstance(error, PlanningError)

    def test_decomposition_failed_error(self):
        """Test DecompositionFailedError creation."""
        error = DecompositionFailedError(
            task_description="Build feature", reason="No applicable methods"
        )
        assert error.task_description == "Build feature"
        assert error.reason == "No applicable methods"
        assert "Build feature" in str(error)
        assert isinstance(error, PlanningError)


class TestLockErrors:
    """Test lock-related errors."""

    def test_lock_acquisition_error(self):
        """Test LockAcquisitionError creation."""
        error = LockAcquisitionError(
            file_path="/test.py", lock_type="WRITE", holder="agent-123"
        )
        assert error.file_path == "/test.py"
        assert error.lock_type == "WRITE"
        assert error.holder == "agent-123"
        assert "/test.py" in str(error)
        assert "WRITE" in str(error)
        assert "agent-123" in str(error)
        assert isinstance(error, LockError)

    def test_lock_acquisition_error_no_holder(self):
        """Test LockAcquisitionError without holder."""
        error = LockAcquisitionError(file_path="/test.py", lock_type="READ")
        assert error.file_path == "/test.py"
        assert error.lock_type == "READ"
        assert error.holder is None
        assert isinstance(error, LockError)

    def test_lock_timeout_error(self):
        """Test LockTimeoutError creation."""
        error = LockTimeoutError(file_path="/test.py", timeout_seconds=30.0)
        assert error.file_path == "/test.py"
        assert error.timeout_seconds == 30.0
        assert "/test.py" in str(error)
        assert "30.0" in str(error)
        assert isinstance(error, LockError)


class TestWorktreeErrors:
    """Test worktree-related errors."""

    def test_worktree_creation_error(self):
        """Test WorktreeCreationError creation."""
        error = WorktreeCreationError(agent_id="agent-123", reason="Branch exists")
        assert error.agent_id == "agent-123"
        assert error.reason == "Branch exists"
        assert "agent-123" in str(error)
        assert "Branch exists" in str(error)
        assert isinstance(error, WorktreeError)

    def test_worktree_merge_conflict_error(self):
        """Test WorktreeMergeConflictError creation."""
        files = ["/test.py", "/main.py"]
        conflict = "<<<<<<< HEAD\ncode\n======="
        error = WorktreeMergeConflictError(
            agent_id="agent-123", conflicting_files=files, conflict_details=conflict
        )
        assert error.agent_id == "agent-123"
        assert error.conflicting_files == files
        assert error.conflict_details == conflict
        assert "agent-123" in str(error)
        assert "2 files" in str(error)
        assert isinstance(error, WorktreeError)


class TestAPIErrors:
    """Test API-related errors."""

    def test_rate_limit_error(self):
        """Test RateLimitError creation."""
        quota = {"limit": 1000, "remaining": 0}
        error = RateLimitError(
            service="claude", retry_after=60.0, quota_info=quota
        )
        assert error.service == "claude"
        assert error.retry_after == 60.0
        assert error.quota_info == quota
        assert "claude" in str(error)
        assert "60.0" in str(error)
        assert isinstance(error, APIError)

    def test_rate_limit_error_minimal(self):
        """Test RateLimitError with minimal args."""
        error = RateLimitError(service="claude")
        assert error.service == "claude"
        assert error.retry_after is None
        assert error.quota_info is None
        assert isinstance(error, APIError)

    def test_model_overloaded_error(self):
        """Test ModelOverloadedError creation."""
        error = ModelOverloadedError(model="opus-4", retry_after=30.0)
        assert error.model == "opus-4"
        assert error.retry_after == 30.0
        assert "opus-4" in str(error)
        assert isinstance(error, APIError)

    def test_model_overloaded_error_minimal(self):
        """Test ModelOverloadedError with minimal args."""
        error = ModelOverloadedError(model="opus-4")
        assert error.model == "opus-4"
        assert error.retry_after is None
        assert isinstance(error, APIError)


class TestQueueErrors:
    """Test queue-related errors."""

    def test_queue_empty_error(self):
        """Test QueueEmptyError creation."""
        error = QueueEmptyError()
        assert "empty" in str(error).lower()
        assert isinstance(error, QueueError)

    def test_queue_connection_error(self):
        """Test QueueConnectionError creation."""
        error = QueueConnectionError(backend="redis", reason="Connection refused")
        assert error.backend == "redis"
        assert error.reason == "Connection refused"
        assert "redis" in str(error)
        assert "Connection refused" in str(error)
        assert isinstance(error, QueueError)


class TestQualityGateErrors:
    """Test quality gate errors."""

    def test_quality_gate_failed_error(self):
        """Test QualityGateFailedError creation."""
        output = "lint: 3 errors\ntest: 2 failures"
        error = QualityGateFailedError(
            gate_name="pre-commit", output=output, issues_count=5
        )
        assert error.gate_name == "pre-commit"
        assert error.output == output
        assert error.issues_count == 5
        assert "pre-commit" in str(error)
        assert "5 issues" in str(error)
        assert isinstance(error, QualityGateError)


class TestConfigErrors:
    """Test configuration errors."""

    def test_config_not_found_error(self):
        """Test ConfigNotFoundError creation."""
        error = ConfigNotFoundError(config_path="/config.json")
        assert error.config_path == "/config.json"
        assert "/config.json" in str(error)
        assert isinstance(error, ConfigError)

    def test_config_validation_error(self):
        """Test ConfigValidationError creation."""
        errors = ["Field 'name' is required", "Field 'port' must be integer"]
        error = ConfigValidationError(errors=errors)
        assert error.errors == errors
        assert "2 errors" in str(error)
        assert isinstance(error, ConfigError)


class TestExceptionInheritance:
    """Test exception inheritance hierarchy."""

    def test_all_inherit_from_iccc_error(self):
        """Verify all custom exceptions inherit from ICCCError."""
        exceptions = [
            AgentError,
            AgentNotFoundError,
            TaskError,
            TaskNotFoundError,
            PlanningError,
            LockError,
            WorktreeError,
            APIError,
            RateLimitError,
            QueueError,
            QualityGateError,
            ConfigError,
        ]
        for exc_class in exceptions:
            assert issubclass(exc_class, ICCCError)

    def test_category_inheritance(self):
        """Test category-specific inheritance."""
        # Agent errors
        assert issubclass(AgentNotFoundError, AgentError)
        assert issubclass(AgentBusyError, AgentError)
        assert issubclass(AgentCrashedError, AgentError)

        # Task errors
        assert issubclass(TaskNotFoundError, TaskError)
        assert issubclass(TaskDependencyError, TaskError)
        assert issubclass(TaskTimeoutError, TaskError)
        assert issubclass(TaskExecutionError, TaskError)

        # Planning errors
        assert issubclass(PlanningFailedError, PlanningError)
        assert issubclass(DecompositionFailedError, PlanningError)

        # Lock errors
        assert issubclass(LockAcquisitionError, LockError)
        assert issubclass(LockTimeoutError, LockError)

        # API errors
        assert issubclass(RateLimitError, APIError)
        assert issubclass(ModelOverloadedError, APIError)

        # Config errors
        assert issubclass(ConfigNotFoundError, ConfigError)
        assert issubclass(ConfigValidationError, ConfigError)
