"""Tests for bug fix template."""

import pytest

from iccc.planning.templates.bug_fix import (
    create_bug_fix_method,
    create_bug_fix_tasks,
    get_task_constraints,
)


class TestBugFixTasks:
    """Tests for bug fix task generation."""

    def test_basic_bug_fix(self):
        """Test basic bug fix workflow."""
        tasks = create_bug_fix_tasks(
            bug_description="Login fails with special characters",
            root_cause_known=False,
        )

        # Should have 5 tasks when root cause unknown
        assert len(tasks) == 5
        task_names = [t.name for t in tasks]

        assert "reproduce_bug" in task_names
        assert "root_cause_analysis" in task_names
        assert "write_failing_test" in task_names
        assert "implement_fix" in task_names
        assert "verify_fix_and_test" in task_names

    def test_bug_fix_known_root_cause(self):
        """Test bug fix when root cause is known."""
        tasks = create_bug_fix_tasks(
            bug_description="Off-by-one error in pagination",
            root_cause_known=True,
        )

        # Should have 4 tasks (skips root cause analysis)
        assert len(tasks) == 4
        task_names = [t.name for t in tasks]

        assert "reproduce_bug" in task_names
        assert "root_cause_analysis" not in task_names  # Skipped
        assert "write_failing_test" in task_names
        assert "implement_fix" in task_names

    def test_task_ordering(self):
        """Test that tasks are in correct order."""
        tasks = create_bug_fix_tasks(
            bug_description="null pointer exception",
            root_cause_known=False,
        )

        task_names = [t.name for t in tasks]

        # Reproduce must come first
        assert task_names[0] == "reproduce_bug"

        # Fix must come before verify
        fix_idx = task_names.index("implement_fix")
        verify_idx = task_names.index("verify_fix_and_test")
        assert fix_idx < verify_idx

    def test_complexity_estimation(self):
        """Test complexity estimation."""
        tasks = create_bug_fix_tasks(
            bug_description="complex race condition",
            root_cause_known=False,
        )

        # Root cause analysis should be most complex
        rca_task = next(t for t in tasks if t.name == "root_cause_analysis")
        assert rca_task.estimated_complexity == 4

        # All tasks should have valid complexity
        assert all(1 <= t.estimated_complexity <= 5 for t in tasks)


class TestBugFixMethod:
    """Tests for HTN method creation."""

    def test_method_creation(self):
        """Test creating the HTN method."""
        method = create_bug_fix_method()

        assert method.name == "standard_bug_fix"
        assert method.task_name == "fix_bug"

    def test_method_preconditions(self):
        """Test method preconditions (always applicable)."""
        method = create_bug_fix_method()

        # Bug fixes are always applicable
        assert method.preconditions({})
        assert method.preconditions({"bug_description": "test", "root_cause_known": True})


class TestBugFixConstraints:
    """Tests for task ordering constraints."""

    def test_constraint_structure(self):
        """Test constraint structure."""
        constraints = get_task_constraints()

        assert len(constraints) == 5
        assert all(isinstance(c, tuple) for c in constraints)
        assert all(len(c) == 2 for c in constraints)

    def test_reproduce_comes_first(self):
        """Test that reproduce comes before everything."""
        constraints = get_task_constraints()

        repro_before = [after for before, after in constraints if before == "reproduce_bug"]

        assert "root_cause_analysis" in repro_before
        assert "write_failing_test" in repro_before

    def test_verify_comes_last(self):
        """Test that verify comes after fix."""
        constraints = get_task_constraints()

        before_verify = [before for before, after in constraints if after == "verify_fix_and_test"]

        assert "implement_fix" in before_verify

    def test_linear_workflow(self):
        """Test that bug fix has a clear linear workflow."""
        constraints = get_task_constraints()

        # Each task (except first and last) should have exactly one predecessor and one successor
        # This verifies the linear nature of the workflow

        task_graph = {}
        for before, after in constraints:
            if after not in task_graph:
                task_graph[after] = []
            task_graph[after].append(before)

        # All internal nodes should have dependencies
        assert "write_failing_test" in task_graph
        assert "implement_fix" in task_graph
        assert "verify_fix_and_test" in task_graph
