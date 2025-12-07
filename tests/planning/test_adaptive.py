"""Tests for adaptive replanning system."""

import pytest
from uuid import uuid4

from iccc.models.entities import ModelTier, Task, TaskType, TaskStatus
from iccc.planning.adaptive import (
    AdaptivePlanner,
    FailurePattern,
    TaskFailure,
    ReplanStrategy,
)
from iccc.planning.htn import HTNPlanner
from iccc.planning.strips import STRIPSPlanner


class TestFailurePattern:
    """Tests for failure pattern detection."""

    @pytest.fixture
    def planner(self):
        """Create adaptive planner."""
        strips = STRIPSPlanner()
        htn = HTNPlanner(methods=[])
        return AdaptivePlanner(strips, htn)

    @pytest.fixture
    def task(self):
        """Create sample task."""
        return Task(
            id=uuid4(),
            project_id=uuid4(),
            task_type=TaskType.CODE_REVIEW,
            description="Review pull request",
            status=TaskStatus.PENDING,
        )

    @pytest.mark.asyncio
    async def test_detect_quality_gate_failure(self, planner, task):
        """Should detect quality gate failures."""
        error = Exception("Quality gate failed: lint errors found")
        pattern = await planner.analyze_failure(task, error, {})

        assert pattern == FailurePattern.QUALITY_GATE_FAILED

    @pytest.mark.asyncio
    async def test_detect_timeout_failure(self, planner, task):
        """Should detect timeout failures."""
        error = Exception("Task timed out after 300 seconds")
        pattern = await planner.analyze_failure(task, error, {})

        assert pattern == FailurePattern.TIMEOUT

    @pytest.mark.asyncio
    async def test_detect_model_overload_failure(self, planner, task):
        """Should detect model overload failures."""
        error = Exception("Model overloaded, capacity exceeded")
        pattern = await planner.analyze_failure(task, error, {})

        assert pattern == FailurePattern.MODEL_OVERLOAD

    @pytest.mark.asyncio
    async def test_detect_dependency_conflict_failure(self, planner, task):
        """Should detect dependency conflicts."""
        error = Exception("Lock conflict: file locked by another agent")
        pattern = await planner.analyze_failure(task, error, {})

        assert pattern == FailurePattern.DEPENDENCY_CONFLICT

    @pytest.mark.asyncio
    async def test_detect_repeated_failure(self, planner, task):
        """Should detect repeated failures of same task type."""
        # Add failure history
        planner.failure_history = [
            TaskFailure(
                task_id=uuid4(),
                task_type=TaskType.CODE_REVIEW,
                model_used=ModelTier.HAIKU,
                failure_pattern=FailurePattern.UNKNOWN,
                error_message="First failure",
                attempt_number=2,
                context={},
            ),
            TaskFailure(
                task_id=uuid4(),
                task_type=TaskType.CODE_REVIEW,
                model_used=ModelTier.SONNET,
                failure_pattern=FailurePattern.UNKNOWN,
                error_message="Second failure",
                attempt_number=3,
                context={},
            ),
        ]

        error = Exception("Generic error")
        pattern = await planner.analyze_failure(task, error, {})

        assert pattern == FailurePattern.REPEATED_FAILURE

    @pytest.mark.asyncio
    async def test_detect_unknown_failure(self, planner, task):
        """Should default to unknown for unrecognized errors."""
        error = Exception("Some obscure error message")
        pattern = await planner.analyze_failure(task, error, {})

        assert pattern == FailurePattern.UNKNOWN


class TestReplanStrategy:
    """Tests for replan strategy generation."""

    @pytest.fixture
    def planner(self):
        """Create adaptive planner."""
        strips = STRIPSPlanner()
        htn = HTNPlanner(methods=[])
        return AdaptivePlanner(strips, htn)

    @pytest.mark.asyncio
    async def test_quality_failure_upgrade_model(self, planner):
        """Should upgrade model for quality failures."""
        failure = TaskFailure(
            task_id=uuid4(),
            task_type=TaskType.CODE_REVIEW,
            model_used=ModelTier.HAIKU,
            failure_pattern=FailurePattern.QUALITY_GATE_FAILED,
            error_message="Quality gate failed",
            attempt_number=1,
            context={},
        )

        strategy = await planner.generate_replan_strategy(failure)

        assert strategy.action == "upgrade_model"
        assert strategy.new_model == ModelTier.SONNET

    @pytest.mark.asyncio
    async def test_quality_failure_with_opus_redecompose(self, planner):
        """Should redecompose when quality fails even with Opus."""
        failure = TaskFailure(
            task_id=uuid4(),
            task_type=TaskType.CODE_REVIEW,
            model_used=ModelTier.OPUS,
            failure_pattern=FailurePattern.QUALITY_GATE_FAILED,
            error_message="Quality gate failed",
            attempt_number=1,
            context={},
        )

        strategy = await planner.generate_replan_strategy(failure)

        assert strategy.action == "redecompose_detailed"
        assert strategy.metadata.get("add_validation_steps") is True

    @pytest.mark.asyncio
    async def test_timeout_failure_break_down(self, planner):
        """Should break down task for timeout failures."""
        failure = TaskFailure(
            task_id=uuid4(),
            task_type=TaskType.API_IMPLEMENTATION,
            model_used=ModelTier.SONNET,
            failure_pattern=FailurePattern.TIMEOUT,
            error_message="Task timed out",
            attempt_number=1,
            context={},
        )

        strategy = await planner.generate_replan_strategy(failure)

        assert strategy.action == "redecompose_parallel"
        assert "timed out" in strategy.reasoning.lower()

    @pytest.mark.asyncio
    async def test_model_overload_downgrade(self, planner):
        """Should downgrade model or wait for overload."""
        failure = TaskFailure(
            task_id=uuid4(),
            task_type=TaskType.TEST_WRITING,
            model_used=ModelTier.OPUS,
            failure_pattern=FailurePattern.MODEL_OVERLOAD,
            error_message="Model overloaded",
            attempt_number=1,
            context={},
        )

        strategy = await planner.generate_replan_strategy(failure)

        # Should downgrade from Opus to Sonnet
        assert strategy.action == "downgrade_model"
        assert strategy.new_model == ModelTier.SONNET

    @pytest.mark.asyncio
    async def test_dependency_conflict_reorder(self, planner):
        """Should adjust task ordering for conflicts."""
        failure = TaskFailure(
            task_id=uuid4(),
            task_type=TaskType.API_IMPLEMENTATION,
            model_used=ModelTier.SONNET,
            failure_pattern=FailurePattern.DEPENDENCY_CONFLICT,
            error_message="Lock conflict",
            attempt_number=1,
            context={},
        )

        strategy = await planner.generate_replan_strategy(failure)

        assert strategy.action == "reorder_dependencies"
        assert "conflict" in strategy.reasoning.lower()

    @pytest.mark.asyncio
    async def test_repeated_failure_alternative_approach(self, planner):
        """Should try alternative approach for repeated failures."""
        failure = TaskFailure(
            task_id=uuid4(),
            task_type=TaskType.TEST_WRITING,  # Use existing TaskType
            model_used=ModelTier.SONNET,
            failure_pattern=FailurePattern.REPEATED_FAILURE,
            error_message="Repeated failure",
            attempt_number=3,
            context={},
        )

        strategy = await planner.generate_replan_strategy(failure)

        # Should upgrade to Opus and change approach
        assert strategy.action == "change_approach"
        assert strategy.new_model == ModelTier.OPUS

    @pytest.mark.asyncio
    async def test_unknown_failure_upgrade(self, planner):
        """Should upgrade model for unknown failures."""
        failure = TaskFailure(
            task_id=uuid4(),
            task_type=TaskType.SIMPLE_DOCUMENTATION,
            model_used=ModelTier.HAIKU,
            failure_pattern=FailurePattern.UNKNOWN,
            error_message="Unknown error",
            attempt_number=1,
            context={},
        )

        strategy = await planner.generate_replan_strategy(failure)

        assert strategy.action == "upgrade_model"
        assert strategy.new_model == ModelTier.SONNET


class TestModelUpgrade:
    """Tests for model tier upgrades."""

    def test_upgrade_from_haiku(self):
        """Should upgrade Haiku to Sonnet."""
        strips = STRIPSPlanner()
        htn = HTNPlanner(methods=[])
        planner = AdaptivePlanner(strips, htn)

        upgraded = planner._upgrade_model(ModelTier.HAIKU)
        assert upgraded == ModelTier.SONNET

    def test_upgrade_from_sonnet(self):
        """Should upgrade Sonnet to Opus."""
        strips = STRIPSPlanner()
        htn = HTNPlanner(methods=[])
        planner = AdaptivePlanner(strips, htn)

        upgraded = planner._upgrade_model(ModelTier.SONNET)
        assert upgraded == ModelTier.OPUS

    def test_upgrade_from_opus(self):
        """Should stay at Opus (highest tier)."""
        strips = STRIPSPlanner()
        htn = HTNPlanner(methods=[])
        planner = AdaptivePlanner(strips, htn)

        upgraded = planner._upgrade_model(ModelTier.OPUS)
        assert upgraded == ModelTier.OPUS


class TestModelDowngrade:
    """Tests for model tier downgrades."""

    def test_downgrade_from_opus(self):
        """Should downgrade Opus to Sonnet."""
        strips = STRIPSPlanner()
        htn = HTNPlanner(methods=[])
        planner = AdaptivePlanner(strips, htn)

        downgraded = planner._downgrade_model(ModelTier.OPUS)
        assert downgraded == ModelTier.SONNET

    def test_downgrade_from_sonnet(self):
        """Should downgrade Sonnet to Haiku."""
        strips = STRIPSPlanner()
        htn = HTNPlanner(methods=[])
        planner = AdaptivePlanner(strips, htn)

        downgraded = planner._downgrade_model(ModelTier.SONNET)
        assert downgraded == ModelTier.HAIKU

    def test_downgrade_from_haiku(self):
        """Should stay at Haiku (lowest tier)."""
        strips = STRIPSPlanner()
        htn = HTNPlanner(methods=[])
        planner = AdaptivePlanner(strips, htn)

        downgraded = planner._downgrade_model(ModelTier.HAIKU)
        assert downgraded == ModelTier.HAIKU


class TestFailureHistory:
    """Tests for failure history tracking."""

    @pytest.fixture
    def planner(self):
        """Create adaptive planner."""
        strips = STRIPSPlanner()
        htn = HTNPlanner(methods=[])
        return AdaptivePlanner(strips, htn)

    def test_initial_failure_history_empty(self, planner):
        """Initial failure history should be empty."""
        assert len(planner.failure_history) == 0

    def test_record_failure(self, planner):
        """Should record task failures."""
        failure = TaskFailure(
            task_id=uuid4(),
            task_type=TaskType.TEST_WRITING,
            model_used=ModelTier.HAIKU,
            failure_pattern=FailurePattern.TIMEOUT,
            error_message="Task timed out",
            attempt_number=1,
            context={"test_file": "test_example.py"},
        )

        planner.failure_history.append(failure)

        assert len(planner.failure_history) == 1
        assert planner.failure_history[0] == failure

    def test_failure_history_accumulation(self, planner):
        """Failure history should accumulate over time."""
        # Add multiple failures
        for i in range(5):
            failure = TaskFailure(
                task_id=uuid4(),
                task_type=TaskType.CODE_REVIEW,
                model_used=ModelTier.HAIKU,
                failure_pattern=FailurePattern.QUALITY_GATE_FAILED,
                error_message=f"Failure {i}",
                attempt_number=i + 1,
                context={},
            )
            planner.failure_history.append(failure)

        assert len(planner.failure_history) == 5
