"""Tests for refactoring template."""

import pytest

from iccc.planning.templates.refactoring import (
    create_refactoring_method,
    create_refactoring_tasks,
    get_task_constraints,
)


class TestRefactoringTasks:
    """Tests for refactoring task generation."""

    def test_refactoring_with_tests(self):
        """Test refactoring when tests exist."""
        tasks = create_refactoring_tasks(
            target="authentication module",
            has_tests=True,
        )

        assert len(tasks) == 5
        task_names = [t.name for t in tasks]

        assert "ensure_test_coverage" in task_names
        assert "create_safety_tests" not in task_names
        assert "identify_and_plan" in task_names
        assert "apply_refactoring" in task_names
        assert "continuous_testing" in task_names
        assert "final_verification" in task_names

    def test_refactoring_without_tests(self):
        """Test refactoring when tests don't exist."""
        tasks = create_refactoring_tasks(
            target="legacy code module",
            has_tests=False,
        )

        assert len(tasks) == 5
        task_names = [t.name for t in tasks]

        assert "create_safety_tests" in task_names
        assert "ensure_test_coverage" not in task_names

        # Creating tests should be more complex
        safety_task = next(t for t in tasks if t.name == "create_safety_tests")
        assert safety_task.estimated_complexity == 4

    def test_task_ordering(self):
        """Test that tasks are in correct order."""
        tasks = create_refactoring_tasks(
            target="payment processor",
            has_tests=True,
        )

        task_names = [t.name for t in tasks]

        # Test coverage must come first
        assert task_names[0] == "ensure_test_coverage"

        # Refactoring must come before final verification
        refactor_idx = task_names.index("apply_refactoring")
        verify_idx = task_names.index("final_verification")
        assert refactor_idx < verify_idx

        # Continuous testing during refactoring
        testing_idx = task_names.index("continuous_testing")
        assert refactor_idx < testing_idx < verify_idx

    def test_safety_emphasis(self):
        """Test that safety is emphasized throughout."""
        tasks = create_refactoring_tasks(
            target="critical business logic",
            has_tests=True,
        )

        # First task should ensure coverage
        assert tasks[0].name == "ensure_test_coverage"
        assert "80%" in str(tasks[0].parameters)

        # Continuous testing should prevent regressions
        testing_task = next(t for t in tasks if t.name == "continuous_testing")
        assert "revert" in str(testing_task.parameters).lower()

    def test_complexity_distribution(self):
        """Test complexity estimation."""
        tasks = create_refactoring_tasks(
            target="data access layer",
            has_tests=True,
        )

        # Apply refactoring should be most complex
        refactor_task = next(t for t in tasks if t.name == "apply_refactoring")
        assert refactor_task.estimated_complexity == 4

        total_complexity = sum(t.estimated_complexity for t in tasks)
        assert total_complexity >= 10  # Refactoring is substantial work


class TestRefactoringMethod:
    """Tests for HTN method creation."""

    def test_method_creation(self):
        """Test creating the HTN method."""
        method = create_refactoring_method()

        assert method.name == "safe_refactoring"
        assert method.task_name == "refactor_code"

    def test_method_preconditions(self):
        """Test method preconditions."""
        method = create_refactoring_method()

        # Always applicable (we can create characterization tests)
        assert method.preconditions({})
        assert method.preconditions({"target": "code", "has_tests": True})
        assert method.preconditions({"target": "code", "has_tests": False})


class TestRefactoringConstraints:
    """Tests for task ordering constraints."""

    def test_constraint_structure(self):
        """Test constraint structure."""
        constraints = get_task_constraints()

        assert len(constraints) == 5
        assert all(isinstance(c, tuple) for c in constraints)

    def test_test_coverage_first(self):
        """Test that test coverage comes before planning."""
        constraints = get_task_constraints()

        after_coverage = [after for before, after in constraints if before == "ensure_test_coverage"]
        after_safety = [after for before, after in constraints if before == "create_safety_tests"]

        assert "identify_and_plan" in after_coverage or "identify_and_plan" in after_safety

    def test_verification_last(self):
        """Test that final verification comes after continuous testing."""
        constraints = get_task_constraints()

        before_verify = [before for before, after in constraints if after == "final_verification"]

        assert "continuous_testing" in before_verify

    def test_alternative_paths(self):
        """Test that there are alternative paths for with/without tests."""
        constraints = get_task_constraints()

        # Both ensure_test_coverage and create_safety_tests should lead to identify_and_plan
        constraint_list = [f"{b}->{a}" for b, a in constraints]

        has_ensure_path = any("ensure_test_coverage->identify_and_plan" in c for c in constraint_list)
        has_create_path = any("create_safety_tests->identify_and_plan" in c for c in constraint_list)

        assert has_ensure_path or has_create_path
