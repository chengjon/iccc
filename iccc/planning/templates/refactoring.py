"""Code refactoring workflow template with safety checks."""

from typing import Any

from iccc.planning.htn import Method, PrimitiveTask


def create_refactoring_tasks(
    target: str,
    has_tests: bool = True,
) -> list[PrimitiveTask]:
    """
    Create the 5 primitive tasks for safe refactoring.

    Standard refactoring workflow:
    1. Ensure test coverage (if tests exist)
    2. Identify code smells and create refactoring plan
    3. Apply refactoring incrementally
    4. Run tests after each change
    5. Final verification and cleanup

    Args:
        target: What to refactor (e.g., "user authentication module")
        has_tests: Whether existing tests are available

    Returns:
        List of 5 primitive tasks in execution order
    """
    tasks = []

    # Task 1: Ensure Test Coverage
    if has_tests:
        tasks.append(
            PrimitiveTask(
                name="ensure_test_coverage",
                parameters={
                    "target": target,
                    "actions": [
                        "Run coverage report",
                        "Add tests for untested paths",
                        "Ensure >80% coverage before refactoring",
                    ],
                    "safety": "Tests prevent regressions during refactoring",
                },
                estimated_complexity=3,
            )
        )
    else:
        tasks.append(
            PrimitiveTask(
                name="create_safety_tests",
                parameters={
                    "target": target,
                    "actions": [
                        "Write characterization tests",
                        "Document current behavior",
                        "Create test harness",
                    ],
                    "safety": "Tests created from scratch to enable safe refactoring",
                },
                estimated_complexity=4,
            )
        )

    # Task 2: Identify Code Smells and Plan
    tasks.append(
        PrimitiveTask(
            name="identify_and_plan",
            parameters={
                "target": target,
                "code_smells": [
                    "Long methods",
                    "Duplicate code",
                    "Large classes",
                    "Long parameter lists",
                    "Divergent change",
                ],
                "deliverable": "Refactoring plan with prioritized changes",
            },
            estimated_complexity=2,
        )
    )

    # Task 3: Apply Refactoring Incrementally
    tasks.append(
        PrimitiveTask(
            name="apply_refactoring",
            parameters={
                "target": target,
                "principles": [
                    "Extract method",
                    "Extract class",
                    "Rename for clarity",
                    "Remove duplication",
                    "Simplify conditionals",
                ],
                "approach": "Small, atomic commits for each refactoring",
            },
            estimated_complexity=4,
        )
    )

    # Task 4: Run Tests After Each Change
    tasks.append(
        PrimitiveTask(
            name="continuous_testing",
            parameters={
                "target": target,
                "frequency": "After each atomic refactoring step",
                "requirements": [
                    "All tests must pass before next refactoring",
                    "Revert if tests fail",
                    "No behavioral changes allowed",
                ],
            },
            estimated_complexity=2,
        )
    )

    # Task 5: Final Verification and Cleanup
    tasks.append(
        PrimitiveTask(
            name="final_verification",
            parameters={
                "target": target,
                "checks": [
                    "Full test suite passes",
                    "Code coverage maintained or improved",
                    "No dead code remaining",
                    "Documentation updated",
                    "Performance benchmarks (if applicable)",
                ],
            },
            estimated_complexity=2,
        )
    )

    return tasks


def create_refactoring_method() -> Method:
    """
    Create HTN method for code refactoring.

    Preconditions:
    - tests_exist OR willingness to create characterization tests

    Constraints:
    1. ensure_test_coverage must come first
    2. identify_and_plan must come before apply_refactoring
    3. apply_refactoring must come before continuous_testing
    4. continuous_testing runs throughout (parallel with refactoring)
    5. final_verification must come last

    Returns:
        Method for decomposing "refactor_code" compound task
    """

    def preconditions(params: dict[str, Any]) -> bool:
        """
        Refactoring is safe if tests exist or we're willing to create them.

        For production code, having tests is strongly recommended.
        """
        # Always allowed - we can create characterization tests if needed
        return True

    return Method(
        name="safe_refactoring",
        task_name="refactor_code",
        preconditions=preconditions,
        subtasks=[],  # Will be populated dynamically
    )


def get_task_constraints() -> list[tuple[str, str]]:
    """
    Get ordering constraints for refactoring tasks.

    Returns:
        List of (before, after) task name tuples
    """
    return [
        ("ensure_test_coverage", "identify_and_plan"),
        ("create_safety_tests", "identify_and_plan"),  # Alternative path
        ("identify_and_plan", "apply_refactoring"),
        ("apply_refactoring", "continuous_testing"),
        ("continuous_testing", "final_verification"),
    ]
