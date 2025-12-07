"""Hierarchical Task Network (HTN) planner for task decomposition."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class PrimitiveTask:
    """A primitive (atomic) task that can be directly executed."""

    name: str
    parameters: dict[str, Any]
    estimated_complexity: int = 3  # 1-5 scale

    def __repr__(self) -> str:
        return f"PrimitiveTask({self.name})"


@dataclass
class CompoundTask:
    """A compound task that can be decomposed into subtasks."""

    name: str
    parameters: dict[str, Any]

    def __repr__(self) -> str:
        return f"CompoundTask({self.name})"


@dataclass
class Method:
    """A method for decomposing a compound task."""

    name: str
    task_name: str  # Which compound task this method applies to
    preconditions: Callable[[dict[str, Any]], bool]
    subtasks: list[PrimitiveTask | CompoundTask]

    def is_applicable(self, task: CompoundTask) -> bool:
        """Check if this method can decompose the given task."""
        return task.name == self.task_name and self.preconditions(task.parameters)


class HTNPlanner:
    """Hierarchical Task Network planner."""

    def __init__(self, methods: list[Method]) -> None:
        self.methods = methods

    def decompose(
        self, task: CompoundTask | PrimitiveTask, max_depth: int = 10
    ) -> list[PrimitiveTask]:
        """
        Decompose a task into primitive tasks.

        Args:
            task: Task to decompose
            max_depth: Maximum recursion depth

        Returns:
            List of primitive tasks
        """
        if isinstance(task, PrimitiveTask):
            return [task]

        if max_depth <= 0:
            raise RecursionError(f"Maximum decomposition depth reached for task: {task}")

        # Find applicable method
        for method in self.methods:
            if method.is_applicable(task):
                # Decompose using this method
                result = []
                for subtask in method.subtasks:
                    result.extend(self.decompose(subtask, max_depth - 1))
                return result

        raise ValueError(f"No applicable method found for task: {task}")

    @staticmethod
    def create_software_dev_methods() -> list[Method]:
        """Create HTN methods for common software development tasks."""
        return [
            # Feature implementation
            Method(
                name="implement_feature_tdd",
                task_name="implement_feature",
                preconditions=lambda p: p.get("use_tdd", True),
                subtasks=[
                    PrimitiveTask("write_failing_test", {}, estimated_complexity=3),
                    PrimitiveTask("implement_minimal_code", {}, estimated_complexity=4),
                    PrimitiveTask("run_test_verify_pass", {}, estimated_complexity=2),
                    PrimitiveTask("refactor_code", {}, estimated_complexity=3),
                ],
            ),
            Method(
                name="implement_feature_direct",
                task_name="implement_feature",
                preconditions=lambda p: not p.get("use_tdd", True),
                subtasks=[
                    PrimitiveTask("implement_feature_code", {}, estimated_complexity=5),
                    PrimitiveTask("manual_testing", {}, estimated_complexity=2),
                ],
            ),
            # Bug fix
            Method(
                name="fix_bug_investigated",
                task_name="fix_bug",
                preconditions=lambda p: p.get("root_cause_known", False),
                subtasks=[
                    PrimitiveTask("write_regression_test", {}, estimated_complexity=3),
                    PrimitiveTask("fix_implementation", {}, estimated_complexity=4),
                    PrimitiveTask("verify_fix", {}, estimated_complexity=2),
                ],
            ),
            Method(
                name="fix_bug_unknown",
                task_name="fix_bug",
                preconditions=lambda p: not p.get("root_cause_known", False),
                subtasks=[
                    PrimitiveTask("reproduce_bug", {}, estimated_complexity=3),
                    PrimitiveTask("investigate_root_cause", {}, estimated_complexity=5),
                    CompoundTask("fix_bug", {"root_cause_known": True}),
                ],
            ),
            # Code refactoring
            Method(
                name="refactor_with_tests",
                task_name="refactor_code",
                preconditions=lambda p: p.get("has_tests", True),
                subtasks=[
                    PrimitiveTask("run_existing_tests", {}, estimated_complexity=2),
                    PrimitiveTask("perform_refactoring", {}, estimated_complexity=4),
                    PrimitiveTask("verify_tests_still_pass", {}, estimated_complexity=2),
                ],
            ),
            Method(
                name="refactor_without_tests",
                task_name="refactor_code",
                preconditions=lambda p: not p.get("has_tests", True),
                subtasks=[
                    PrimitiveTask("write_characterization_tests", {}, estimated_complexity=4),
                    CompoundTask("refactor_code", {"has_tests": True}),
                ],
            ),
            # Add documentation
            Method(
                name="document_feature",
                task_name="add_documentation",
                preconditions=lambda p: True,
                subtasks=[
                    PrimitiveTask("write_docstrings", {}, estimated_complexity=2),
                    PrimitiveTask("update_readme", {}, estimated_complexity=2),
                    PrimitiveTask("add_usage_examples", {}, estimated_complexity=3),
                ],
            ),
            # API implementation
            Method(
                name="implement_api_endpoint",
                task_name="create_api_endpoint",
                preconditions=lambda p: True,
                subtasks=[
                    PrimitiveTask("define_request_schema", {}, estimated_complexity=2),
                    PrimitiveTask("define_response_schema", {}, estimated_complexity=2),
                    PrimitiveTask("implement_handler", {}, estimated_complexity=4),
                    PrimitiveTask("add_validation", {}, estimated_complexity=3),
                    PrimitiveTask("write_api_tests", {}, estimated_complexity=3),
                    PrimitiveTask("update_api_docs", {}, estimated_complexity=2),
                ],
            ),
            # Database migration
            Method(
                name="add_database_field",
                task_name="database_migration",
                preconditions=lambda p: p.get("type") == "add_field",
                subtasks=[
                    PrimitiveTask("create_migration_file", {}, estimated_complexity=2),
                    PrimitiveTask("write_upgrade_logic", {}, estimated_complexity=3),
                    PrimitiveTask("write_downgrade_logic", {}, estimated_complexity=2),
                    PrimitiveTask("test_migration", {}, estimated_complexity=3),
                ],
            ),
        ]


def estimate_total_complexity(tasks: list[PrimitiveTask]) -> int:
    """Calculate total complexity of a task list."""
    return sum(task.estimated_complexity for task in tasks)


def group_tasks_by_complexity(
    tasks: list[PrimitiveTask], threshold: int = 10
) -> list[list[PrimitiveTask]]:
    """
    Group tasks into chunks based on complexity threshold.

    Useful for distributing work across multiple agents.

    Args:
        tasks: List of primitive tasks
        threshold: Maximum complexity per group

    Returns:
        List of task groups
    """
    groups: list[list[PrimitiveTask]] = []
    current_group: list[PrimitiveTask] = []
    current_complexity = 0

    for task in tasks:
        if current_complexity + task.estimated_complexity > threshold and current_group:
            # Start new group
            groups.append(current_group)
            current_group = [task]
            current_complexity = task.estimated_complexity
        else:
            current_group.append(task)
            current_complexity += task.estimated_complexity

    if current_group:
        groups.append(current_group)

    return groups
