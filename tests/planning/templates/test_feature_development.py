"""Tests for feature development template."""

import pytest

from iccc.planning.templates.feature_development import (
    create_feature_development_method,
    create_feature_tasks,
    get_task_constraints,
)


class TestFeatureDevelopmentTasks:
    """Tests for feature development task generation."""

    def test_basic_feature_tasks(self):
        """Test basic feature without TDD, API, or DB."""
        tasks = create_feature_tasks(
            feature_name="export feature",
            use_tdd=False,
            needs_api=False,
            needs_db=False,
        )

        # Should have: research, models, core logic, tests, docs
        assert len(tasks) >= 5
        task_names = [t.name for t in tasks]
        assert "research_and_design" in task_names
        assert "update_data_models" in task_names
        assert "implement_core_logic" in task_names
        assert "run_tests_and_fix" in task_names
        assert "code_review_and_docs" in task_names

    def test_feature_with_tdd(self):
        """Test feature with TDD enabled."""
        tasks = create_feature_tasks(
            feature_name="user login",
            use_tdd=True,
            needs_api=False,
            needs_db=False,
        )

        task_names = [t.name for t in tasks]
        assert "write_failing_tests" in task_names

        # TDD: tests should come before implementation
        test_idx = task_names.index("write_failing_tests")
        impl_idx = task_names.index("implement_core_logic")
        assert test_idx < impl_idx

    def test_feature_with_api(self):
        """Test feature with API endpoints."""
        tasks = create_feature_tasks(
            feature_name="search API",
            use_tdd=True,
            needs_api=True,
            needs_db=False,
        )

        task_names = [t.name for t in tasks]
        assert "implement_api_endpoints" in task_names

        # API should come after core logic
        api_idx = task_names.index("implement_api_endpoints")
        core_idx = task_names.index("implement_core_logic")
        assert api_idx > core_idx

    def test_feature_with_database(self):
        """Test feature with database changes."""
        tasks = create_feature_tasks(
            feature_name="user profiles",
            use_tdd=True,
            needs_api=True,
            needs_db=True,
        )

        # Should have all 7 tasks
        assert len(tasks) == 7

        # Verify specific DB task
        models_task = next(t for t in tasks if t.name == "update_data_models")
        assert "migration" in str(models_task.parameters)
        assert models_task.estimated_complexity == 4  # Higher for DB work

    def test_full_feature_complexity(self):
        """Test complexity estimation for full feature."""
        tasks = create_feature_tasks(
            feature_name="payment system",
            use_tdd=True,
            needs_api=True,
            needs_db=True,
        )

        total_complexity = sum(t.estimated_complexity for t in tasks)
        assert total_complexity >= 20  # Full feature is complex
        assert all(1 <= t.estimated_complexity <= 5 for t in tasks)


class TestFeatureDevelopmentMethod:
    """Tests for HTN method creation."""

    def test_method_creation(self):
        """Test creating the HTN method."""
        method = create_feature_development_method()

        assert method.name == "standard_feature_development"
        assert method.task_name == "implement_feature"

    def test_method_preconditions(self):
        """Test method preconditions (always applicable)."""
        method = create_feature_development_method()

        # Should work with any parameters
        assert method.preconditions({})
        assert method.preconditions({"feature_name": "test"})
        assert method.preconditions({"use_tdd": False, "needs_api": True})


class TestTaskConstraints:
    """Tests for task ordering constraints."""

    def test_constraint_structure(self):
        """Test constraint structure."""
        constraints = get_task_constraints()

        assert len(constraints) == 7
        assert all(isinstance(c, tuple) for c in constraints)
        assert all(len(c) == 2 for c in constraints)

    def test_research_comes_first(self):
        """Test that research comes before everything."""
        constraints = get_task_constraints()

        research_before = [after for before, after in constraints if before == "research_and_design"]

        assert "update_data_models" in research_before
        assert "write_failing_tests" in research_before

    def test_docs_comes_last(self):
        """Test that docs come after testing."""
        constraints = get_task_constraints()

        before_docs = [before for before, after in constraints if after == "code_review_and_docs"]

        assert "run_tests_and_fix" in before_docs

    def test_logical_ordering(self):
        """Test logical task ordering."""
        constraints = get_task_constraints()
        constraint_dict = {before: after for before, after in constraints}

        # Core logic should come before API
        assert any(
            before == "implement_core_logic" and after == "implement_api_endpoints"
            for before, after in constraints
        )

        # Tests should come before review
        assert any(
            before == "run_tests_and_fix" and after == "code_review_and_docs"
            for before, after in constraints
        )
