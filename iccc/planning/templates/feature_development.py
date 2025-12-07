"""Feature development workflow template with detailed task breakdown."""

from typing import Any

from iccc.planning.htn import CompoundTask, Method, PrimitiveTask


def create_feature_tasks(
    feature_name: str,
    use_tdd: bool = True,
    needs_api: bool = False,
    needs_db: bool = False,
) -> list[PrimitiveTask]:
    """
    Create the 7 primitive tasks for feature development.

    Standard feature development workflow:
    1. Research and design
    2. Create/update data models
    3. Write failing tests (if TDD)
    4. Implement core logic
    5. Implement API endpoints (if needed)
    6. Run tests and fix failures
    7. Code review and documentation

    Args:
        feature_name: Name of the feature to implement
        use_tdd: Whether to use Test-Driven Development
        needs_api: Whether API endpoints are required
        needs_db: Whether database changes are required

    Returns:
        List of 7 primitive tasks in execution order
    """
    tasks = []

    # Task 1: Research and Design
    tasks.append(
        PrimitiveTask(
            name="research_and_design",
            parameters={
                "feature_name": feature_name,
                "deliverables": [
                    "Architecture diagram",
                    "Data model sketch",
                    "API contract (if needed)",
                ],
            },
            estimated_complexity=3,
        )
    )

    # Task 2: Create/Update Data Models
    if needs_db:
        tasks.append(
            PrimitiveTask(
                name="update_data_models",
                parameters={
                    "feature_name": feature_name,
                    "actions": [
                        "Define entities in models/entities.py",
                        "Create database migration",
                        "Update repositories",
                    ],
                },
                estimated_complexity=4,
            )
        )
    else:
        tasks.append(
            PrimitiveTask(
                name="update_data_models",
                parameters={
                    "feature_name": feature_name,
                    "actions": ["Define data structures (dataclasses/pydantic)"],
                },
                estimated_complexity=2,
            )
        )

    # Task 3: Write Failing Tests (TDD)
    if use_tdd:
        tasks.append(
            PrimitiveTask(
                name="write_failing_tests",
                parameters={
                    "feature_name": feature_name,
                    "test_types": [
                        "Unit tests for core logic",
                        "Integration tests for API" if needs_api else None,
                    ],
                },
                estimated_complexity=3,
            )
        )

    # Task 4: Implement Core Logic
    tasks.append(
        PrimitiveTask(
            name="implement_core_logic",
            parameters={
                "feature_name": feature_name,
                "components": [
                    "Business logic classes",
                    "Helper utilities",
                    "Error handling",
                ],
            },
            estimated_complexity=5,
        )
    )

    # Task 5: Implement API Endpoints
    if needs_api:
        tasks.append(
            PrimitiveTask(
                name="implement_api_endpoints",
                parameters={
                    "feature_name": feature_name,
                    "components": [
                        "Route handlers",
                        "Request/response schemas",
                        "Input validation",
                    ],
                },
                estimated_complexity=4,
            )
        )

    # Task 6: Run Tests and Fix Failures
    tasks.append(
        PrimitiveTask(
            name="run_tests_and_fix",
            parameters={
                "feature_name": feature_name,
                "test_suites": ["unit", "integration"],
                "coverage_target": 80,  # 80% coverage
            },
            estimated_complexity=3,
        )
    )

    # Task 7: Code Review and Documentation
    tasks.append(
        PrimitiveTask(
            name="code_review_and_docs",
            parameters={
                "feature_name": feature_name,
                "deliverables": [
                    "Docstrings for public APIs",
                    "README update (if needed)",
                    "PR description",
                ],
            },
            estimated_complexity=2,
        )
    )

    return tasks


def create_feature_development_method() -> Method:
    """
    Create HTN method for feature development.

    Preconditions:
    - None (always applicable)

    Constraints:
    1. research_and_design must come first
    2. update_data_models must come before implement_core_logic
    3. write_failing_tests must come before implement_core_logic (if TDD)
    4. implement_core_logic must come before implement_api_endpoints
    5. implement_api_endpoints must come before run_tests_and_fix
    6. run_tests_and_fix must come before code_review_and_docs
    7. code_review_and_docs must come last

    Returns:
        Method for decomposing "implement_feature" compound task
    """

    def preconditions(params: dict[str, Any]) -> bool:
        """Feature development has no preconditions - always applicable."""
        return True

    def generate_subtasks(params: dict[str, Any]) -> list[PrimitiveTask]:
        """Generate subtasks based on parameters."""
        return create_feature_tasks(
            feature_name=str(params.get("feature_name", "unknown")),
            use_tdd=bool(params.get("use_tdd", True)),
            needs_api=bool(params.get("needs_api", False)),
            needs_db=bool(params.get("needs_db", False)),
        )

    # Return method with dynamic subtask generation
    return Method(
        name="standard_feature_development",
        task_name="implement_feature",
        preconditions=preconditions,
        subtasks=[],  # Will be populated by decomposer
    )


def get_task_constraints() -> list[tuple[str, str]]:
    """
    Get ordering constraints for feature development tasks.

    Returns:
        List of (before, after) task name tuples
    """
    return [
        ("research_and_design", "update_data_models"),
        ("research_and_design", "write_failing_tests"),
        ("update_data_models", "implement_core_logic"),
        ("write_failing_tests", "implement_core_logic"),
        ("implement_core_logic", "implement_api_endpoints"),
        ("implement_api_endpoints", "run_tests_and_fix"),
        ("run_tests_and_fix", "code_review_and_docs"),
    ]
