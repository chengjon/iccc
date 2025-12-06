"""Adaptive replanning system that adjusts plans based on failures and feedback."""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from iccc.models.entities import ModelTier, Task, TaskType
from iccc.planning.htn import CompoundTask, HTNPlanner, PrimitiveTask
from iccc.planning.strips import STRIPSPlanner
from iccc.planning.templates import WorkflowTemplates

logger = logging.getLogger(__name__)


class FailurePattern(str, Enum):
    """Types of failure patterns detected."""

    QUALITY_GATE_FAILED = "quality_gate_failed"
    TIMEOUT = "timeout"
    MODEL_OVERLOAD = "model_overload"
    DEPENDENCY_CONFLICT = "dependency_conflict"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    REPEATED_FAILURE = "repeated_failure"
    UNKNOWN = "unknown"


@dataclass
class TaskFailure:
    """Record of a task failure."""

    task_id: UUID
    task_type: TaskType
    model_used: ModelTier
    failure_pattern: FailurePattern
    error_message: str
    attempt_number: int
    context: dict


class ReplanStrategy(BaseModel):
    """Strategy for replanning after a failure."""

    action: str = Field(description="Action to take (redecompose, change_model, etc.)")
    reasoning: str = Field(description="Why this strategy was chosen")
    new_model: Optional[ModelTier] = None
    new_task_type: Optional[TaskType] = None
    adjust_complexity: Optional[int] = None  # -1, 0, +1
    metadata: dict = Field(default_factory=dict)


class AdaptivePlanner:
    """Adaptive planner that learns from failures and adjusts strategies."""

    def __init__(
        self, strips_planner: STRIPSPlanner, htn_planner: HTNPlanner
    ) -> None:
        self.strips_planner = strips_planner
        self.htn_planner = htn_planner
        self.failure_history: list[TaskFailure] = []

    async def analyze_failure(
        self, task: Task, error: Exception, context: dict
    ) -> FailurePattern:
        """Analyze a task failure to identify the pattern."""
        error_msg = str(error).lower()

        # Pattern matching on error types
        if "quality" in error_msg or "lint" in error_msg or "test" in error_msg:
            return FailurePattern.QUALITY_GATE_FAILED

        if "timeout" in error_msg or "timed out" in error_msg:
            return FailurePattern.TIMEOUT

        if "overload" in error_msg or "capacity" in error_msg:
            return FailurePattern.MODEL_OVERLOAD

        if "conflict" in error_msg or "lock" in error_msg:
            return FailurePattern.DEPENDENCY_CONFLICT

        # Check for repeated failures (same task failed multiple times)
        similar_failures = [
            f
            for f in self.failure_history
            if f.task_type == task.task_type and f.attempt_number > 1
        ]
        if len(similar_failures) >= 2:
            return FailurePattern.REPEATED_FAILURE

        return FailurePattern.UNKNOWN

    async def generate_replan_strategy(
        self, failure: TaskFailure
    ) -> ReplanStrategy:
        """Generate a replanning strategy based on the failure pattern."""

        if failure.failure_pattern == FailurePattern.QUALITY_GATE_FAILED:
            # Quality issues - might need better model or different approach
            return self._strategy_for_quality_failure(failure)

        elif failure.failure_pattern == FailurePattern.TIMEOUT:
            # Task taking too long - break into smaller pieces
            return self._strategy_for_timeout(failure)

        elif failure.failure_pattern == FailurePattern.MODEL_OVERLOAD:
            # Model overloaded - downgrade or wait
            return self._strategy_for_overload(failure)

        elif failure.failure_pattern == FailurePattern.DEPENDENCY_CONFLICT:
            # File lock conflict - adjust task ordering
            return self._strategy_for_conflict(failure)

        elif failure.failure_pattern == FailurePattern.REPEATED_FAILURE:
            # Repeated failures - try completely different approach
            return self._strategy_for_repeated_failure(failure)

        else:
            # Unknown failure - generic retry with stronger model
            return ReplanStrategy(
                action="upgrade_model",
                reasoning="Unknown failure pattern, trying stronger model",
                new_model=self._upgrade_model(failure.model_used),
            )

    def _strategy_for_quality_failure(
        self, failure: TaskFailure
    ) -> ReplanStrategy:
        """Strategy when quality gates fail."""
        # Check if already using strongest model
        if failure.model_used == ModelTier.OPUS:
            # Already at max - need to redecompose with more detailed steps
            return ReplanStrategy(
                action="redecompose_detailed",
                reasoning="Quality issues with Opus - need more detailed subtasks",
                metadata={
                    "add_validation_steps": True,
                    "increase_review_depth": True,
                },
            )

        # Upgrade model
        return ReplanStrategy(
            action="upgrade_model",
            reasoning="Quality gate failed - using stronger model for better output",
            new_model=self._upgrade_model(failure.model_used),
        )

    def _strategy_for_timeout(self, failure: TaskFailure) -> ReplanStrategy:
        """Strategy when task times out."""
        return ReplanStrategy(
            action="redecompose_parallel",
            reasoning="Task timed out - breaking into smaller parallel subtasks",
            adjust_complexity=-1,  # Simpler subtasks
            metadata={"enable_parallelization": True, "reduce_scope": True},
        )

    def _strategy_for_overload(self, failure: TaskFailure) -> ReplanStrategy:
        """Strategy when model is overloaded."""
        # Try to downgrade model
        downgraded = self._downgrade_model(failure.model_used)

        if downgraded != failure.model_used:
            return ReplanStrategy(
                action="downgrade_model",
                reasoning="Model overloaded - using cheaper alternative",
                new_model=downgraded,
            )

        # Already at cheapest - just retry with backoff
        return ReplanStrategy(
            action="retry_with_backoff",
            reasoning="Model overloaded but already at cheapest tier - wait and retry",
            metadata={"backoff_seconds": 60},
        )

    def _strategy_for_conflict(self, failure: TaskFailure) -> ReplanStrategy:
        """Strategy when dependency conflict occurs."""
        return ReplanStrategy(
            action="reorder_dependencies",
            reasoning="File lock conflict - adjusting task dependencies",
            metadata={
                "serialize_conflicting_files": True,
                "add_dependency_delays": True,
            },
        )

    def _strategy_for_repeated_failure(
        self, failure: TaskFailure
    ) -> ReplanStrategy:
        """Strategy when same task fails repeatedly."""
        # Try completely different task type if possible
        alternative_type = self._find_alternative_task_type(failure.task_type)

        return ReplanStrategy(
            action="change_approach",
            reasoning=f"Task failed {failure.attempt_number} times - trying different approach",
            new_task_type=alternative_type,
            new_model=ModelTier.OPUS,  # Use strongest model for hard cases
            metadata={"use_alternative_workflow": True},
        )

    def _upgrade_model(self, current_model: ModelTier) -> ModelTier:
        """Upgrade to a stronger model."""
        upgrades = {
            ModelTier.HAIKU: ModelTier.SONNET,
            ModelTier.SONNET: ModelTier.OPUS,
            ModelTier.OPUS: ModelTier.OPUS,  # Already at max
        }
        return upgrades.get(current_model, ModelTier.SONNET)

    def _downgrade_model(self, current_model: ModelTier) -> ModelTier:
        """Downgrade to a cheaper model."""
        downgrades = {
            ModelTier.OPUS: ModelTier.SONNET,
            ModelTier.SONNET: ModelTier.HAIKU,
            ModelTier.HAIKU: ModelTier.HAIKU,  # Already at min
        }
        return downgrades.get(current_model, ModelTier.HAIKU)

    def _find_alternative_task_type(self, current_type: TaskType) -> TaskType:
        """Find an alternative task type that might work better."""
        alternatives = {
            TaskType.GENERAL_CODING: TaskType.REFACTORING,
            TaskType.REFACTORING: TaskType.GENERAL_CODING,
            TaskType.BUG_FIX: TaskType.DEBUGGING,
            TaskType.DEBUGGING: TaskType.BUG_FIX,
            TaskType.TEST_WRITING: TaskType.CODE_REVIEW,
        }
        return alternatives.get(current_type, current_type)

    async def replan_task(
        self, original_task: Task, strategy: ReplanStrategy
    ) -> list[Task]:
        """
        Replan a failed task according to the strategy.

        Returns:
            List of new tasks to attempt
        """
        logger.info(
            f"Replanning task {original_task.id} with strategy: {strategy.action}"
        )

        if strategy.action == "upgrade_model":
            # Same task, different model
            new_task = original_task.model_copy()
            new_task.metadata = new_task.metadata or {}
            new_task.metadata["preferred_model"] = strategy.new_model.value
            return [new_task]

        elif strategy.action == "downgrade_model":
            new_task = original_task.model_copy()
            new_task.metadata = new_task.metadata or {}
            new_task.metadata["preferred_model"] = strategy.new_model.value
            return [new_task]

        elif strategy.action == "redecompose_detailed":
            # Break task into more detailed subtasks
            return await self._redecompose_detailed(original_task)

        elif strategy.action == "redecompose_parallel":
            # Break into parallel subtasks
            return await self._redecompose_parallel(original_task)

        elif strategy.action == "reorder_dependencies":
            # Adjust dependencies to avoid conflicts
            return await self._reorder_dependencies(original_task)

        elif strategy.action == "change_approach":
            # Try a completely different approach
            new_task = original_task.model_copy()
            new_task.task_type = strategy.new_task_type or original_task.task_type
            new_task.metadata = new_task.metadata or {}
            new_task.metadata["preferred_model"] = strategy.new_model.value
            new_task.metadata["alternative_approach"] = True
            return [new_task]

        else:
            # Default: just retry the original task
            return [original_task]

    async def _redecompose_detailed(self, task: Task) -> list[Task]:
        """Break task into more detailed subtasks."""
        # Use HTN to decompose with more granular methods
        compound = CompoundTask(
            name=task.description,
            parameters={
                "description": task.description,
                "task_type": task.task_type.value,
                "detail_level": "high",  # Request more detailed decomposition
            },
        )

        primitives = self.htn_planner.decompose(compound)

        # Convert primitives to Tasks
        subtasks = []
        for i, prim in enumerate(primitives):
            subtask = Task(
                description=f"{prim.name}: {task.description}",
                task_type=task.task_type,
                project_id=task.project_id,
                metadata={
                    "parent_task_id": str(task.id),
                    "subtask_index": i,
                    "total_subtasks": len(primitives),
                },
            )

            # Add dependencies (sequential)
            if i > 0:
                subtask.dependencies = [subtasks[i - 1].id]

            subtasks.append(subtask)

        return subtasks

    async def _redecompose_parallel(self, task: Task) -> list[Task]:
        """Break task into parallel subtasks."""
        compound = CompoundTask(
            name=task.description,
            parameters={
                "description": task.description,
                "task_type": task.task_type.value,
                "parallelization": "high",  # Request parallel decomposition
            },
        )

        primitives = self.htn_planner.decompose(compound)

        # Convert to tasks without dependencies (parallel)
        subtasks = []
        for i, prim in enumerate(primitives):
            subtask = Task(
                description=f"{prim.name}: {task.description}",
                task_type=task.task_type,
                project_id=task.project_id,
                metadata={
                    "parent_task_id": str(task.id),
                    "subtask_index": i,
                    "total_subtasks": len(primitives),
                    "parallel": True,
                },
            )
            subtasks.append(subtask)

        return subtasks

    async def _reorder_dependencies(self, task: Task) -> list[Task]:
        """Adjust task dependencies to avoid conflicts."""
        # This would analyze file dependencies and reorder
        # For now, just return original task with updated metadata
        new_task = task.model_copy()
        new_task.metadata = new_task.metadata or {}
        new_task.metadata["reordered"] = True
        new_task.metadata["acquire_locks_early"] = True
        return [new_task]

    def record_failure(
        self,
        task: Task,
        model_used: ModelTier,
        pattern: FailurePattern,
        error: Exception,
        attempt: int,
        context: dict,
    ) -> None:
        """Record a task failure for learning."""
        failure = TaskFailure(
            task_id=task.id,
            task_type=task.task_type,
            model_used=model_used,
            failure_pattern=pattern,
            error_message=str(error),
            attempt_number=attempt,
            context=context,
        )
        self.failure_history.append(failure)

        # Keep history bounded
        if len(self.failure_history) > 1000:
            self.failure_history = self.failure_history[-500:]

    def get_failure_stats(self) -> dict:
        """Get statistics about failures."""
        if not self.failure_history:
            return {}

        pattern_counts = {}
        for failure in self.failure_history:
            pattern = failure.failure_pattern.value
            pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

        model_failure_rates = {}
        for failure in self.failure_history:
            model = failure.model_used.value
            if model not in model_failure_rates:
                model_failure_rates[model] = {"failures": 0, "attempts": 0}
            model_failure_rates[model]["failures"] += 1
            model_failure_rates[model]["attempts"] = failure.attempt_number

        return {
            "total_failures": len(self.failure_history),
            "pattern_distribution": pattern_counts,
            "model_failure_rates": model_failure_rates,
        }
