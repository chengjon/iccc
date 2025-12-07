"""Bug fix workflow template with root cause analysis."""

from typing import Any

from iccc.planning.htn import Method, PrimitiveTask


def create_bug_fix_tasks(
    bug_description: str,
    root_cause_known: bool = False,
) -> list[PrimitiveTask]:
    """
    Create the 5 primitive tasks for bug fixing.

    Standard bug fix workflow:
    1. Reproduce the bug
    2. Root cause analysis (if not known)
    3. Write failing test that captures the bug
    4. Implement fix
    5. Verify fix and check for regressions

    Args:
        bug_description: Description of the bug
        root_cause_known: Whether root cause is already identified

    Returns:
        List of 5 primitive tasks in execution order
    """
    tasks = []

    # Task 1: Reproduce the Bug
    tasks.append(
        PrimitiveTask(
            name="reproduce_bug",
            parameters={
                "bug_description": bug_description,
                "steps": [
                    "Create minimal reproduction case",
                    "Document environment and inputs",
                    "Capture error messages/logs",
                ],
            },
            estimated_complexity=2,
        )
    )

    # Task 2: Root Cause Analysis (if needed)
    if not root_cause_known:
        tasks.append(
            PrimitiveTask(
                name="root_cause_analysis",
                parameters={
                    "bug_description": bug_description,
                    "techniques": [
                        "Stack trace analysis",
                        "Debug logging",
                        "Code inspection",
                        "Git blame for recent changes",
                    ],
                    "deliverable": "Root cause explanation",
                },
                estimated_complexity=4,
            )
        )

    # Task 3: Write Failing Test
    tasks.append(
        PrimitiveTask(
            name="write_failing_test",
            parameters={
                "bug_description": bug_description,
                "test_type": "regression test",
                "purpose": "Ensure bug doesn't reoccur",
            },
            estimated_complexity=2,
        )
    )

    # Task 4: Implement Fix
    tasks.append(
        PrimitiveTask(
            name="implement_fix",
            parameters={
                "bug_description": bug_description,
                "requirements": [
                    "Fix root cause (not symptoms)",
                    "Maintain backward compatibility",
                    "Add defensive checks if needed",
                ],
            },
            estimated_complexity=3,
        )
    )

    # Task 5: Verify Fix and Check Regressions
    tasks.append(
        PrimitiveTask(
            name="verify_fix_and_test",
            parameters={
                "bug_description": bug_description,
                "checks": [
                    "Regression test now passes",
                    "All existing tests still pass",
                    "Manual testing of reproduction case",
                    "Check for similar bugs elsewhere",
                ],
            },
            estimated_complexity=2,
        )
    )

    return tasks


def create_bug_fix_method() -> Method:
    """
    Create HTN method for bug fixing.

    Preconditions:
    - None (always applicable)

    Constraints (linear ordering):
    1. reproduce_bug must come first
    2. root_cause_analysis must come before write_failing_test
    3. write_failing_test must come before implement_fix
    4. implement_fix must come before verify_fix_and_test
    5. verify_fix_and_test must come last

    Returns:
        Method for decomposing "fix_bug" compound task
    """

    def preconditions(params: dict[str, Any]) -> bool:
        """Bug fixes have no preconditions - always applicable."""
        return True

    return Method(
        name="standard_bug_fix",
        task_name="fix_bug",
        preconditions=preconditions,
        subtasks=[],  # Will be populated dynamically
    )


def get_task_constraints() -> list[tuple[str, str]]:
    """
    Get ordering constraints for bug fix tasks.

    Returns:
        List of (before, after) task name tuples
    """
    return [
        ("reproduce_bug", "root_cause_analysis"),
        ("reproduce_bug", "write_failing_test"),
        ("root_cause_analysis", "write_failing_test"),
        ("write_failing_test", "implement_fix"),
        ("implement_fix", "verify_fix_and_test"),
    ]
