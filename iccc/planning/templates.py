"""Predefined workflow templates for common software development tasks."""

from iccc.planning.htn import CompoundTask, HTNPlanner, PrimitiveTask


class WorkflowTemplates:
    """Predefined workflow templates."""

    @staticmethod
    def feature_development(
        feature_name: str, use_tdd: bool = True, needs_api: bool = False, needs_db: bool = False
    ) -> CompoundTask:
        """
        Template for implementing a new feature.

        Args:
            feature_name: Name of the feature
            use_tdd: Whether to use Test-Driven Development
            needs_api: Whether feature requires API endpoints
            needs_db: Whether feature requires database changes

        Returns:
            CompoundTask for feature implementation
        """
        return CompoundTask(
            name="implement_feature",
            parameters={
                "feature_name": feature_name,
                "use_tdd": use_tdd,
                "needs_api": needs_api,
                "needs_db": needs_db,
            },
        )

    @staticmethod
    def bug_fix(bug_description: str, root_cause_known: bool = False) -> CompoundTask:
        """
        Template for fixing a bug.

        Args:
            bug_description: Description of the bug
            root_cause_known: Whether root cause is already identified

        Returns:
            CompoundTask for bug fixing
        """
        return CompoundTask(
            name="fix_bug",
            parameters={
                "bug_description": bug_description,
                "root_cause_known": root_cause_known,
            },
        )

    @staticmethod
    def refactoring(target: str, has_tests: bool = True) -> CompoundTask:
        """
        Template for code refactoring.

        Args:
            target: What to refactor (e.g., "user authentication module")
            has_tests: Whether existing tests are available

        Returns:
            CompoundTask for refactoring
        """
        return CompoundTask(
            name="refactor_code",
            parameters={
                "target": target,
                "has_tests": has_tests,
            },
        )

    @staticmethod
    def api_endpoint_creation(
        endpoint_path: str,
        http_method: str,
        needs_auth: bool = True,
    ) -> CompoundTask:
        """
        Template for creating a new API endpoint.

        Args:
            endpoint_path: API path (e.g., "/users/:id")
            http_method: HTTP method (GET, POST, etc.)
            needs_auth: Whether authentication is required

        Returns:
            CompoundTask for API creation
        """
        return CompoundTask(
            name="create_api_endpoint",
            parameters={
                "endpoint_path": endpoint_path,
                "http_method": http_method,
                "needs_auth": needs_auth,
            },
        )

    @staticmethod
    def database_migration(
        migration_type: str,
        description: str,
    ) -> CompoundTask:
        """
        Template for database migrations.

        Args:
            migration_type: Type of migration ("add_field", "remove_field", "add_table", etc.)
            description: Migration description

        Returns:
            CompoundTask for database migration
        """
        return CompoundTask(
            name="database_migration",
            parameters={
                "type": migration_type,
                "description": description,
            },
        )


class TaskDecomposer:
    """High-level interface for decomposing tasks using HTN planning."""

    def __init__(self) -> None:
        self.planner = HTNPlanner(methods=HTNPlanner.create_software_dev_methods())

    def decompose_task(
        self, task_description: str, task_type: str = "implement_feature", **kwargs: bool | str
    ) -> list[PrimitiveTask]:
        """
        Decompose a high-level task into primitive tasks.

        Args:
            task_description: Description of the task
            task_type: Type of task (feature, bug_fix, refactor, etc.)
            **kwargs: Additional parameters for the task

        Returns:
            List of primitive tasks ready for execution
        """
        # Create appropriate compound task based on type
        if task_type == "feature" or task_type == "implement_feature":
            compound_task = WorkflowTemplates.feature_development(
                feature_name=task_description,
                use_tdd=kwargs.get("use_tdd", True),  # type: ignore
                needs_api=kwargs.get("needs_api", False),  # type: ignore
                needs_db=kwargs.get("needs_db", False),  # type: ignore
            )
        elif task_type == "bug_fix":
            compound_task = WorkflowTemplates.bug_fix(
                bug_description=task_description,
                root_cause_known=kwargs.get("root_cause_known", False),  # type: ignore
            )
        elif task_type == "refactor":
            compound_task = WorkflowTemplates.refactoring(
                target=task_description,
                has_tests=kwargs.get("has_tests", True),  # type: ignore
            )
        elif task_type == "api":
            compound_task = WorkflowTemplates.api_endpoint_creation(
                endpoint_path=task_description,
                http_method=str(kwargs.get("http_method", "GET")),
                needs_auth=kwargs.get("needs_auth", True),  # type: ignore
            )
        elif task_type == "migration":
            compound_task = WorkflowTemplates.database_migration(
                migration_type=str(kwargs.get("migration_type", "add_field")),
                description=task_description,
            )
        else:
            # Default to feature implementation
            compound_task = CompoundTask(name="implement_feature", parameters={"feature_name": task_description})

        # Decompose into primitive tasks
        return self.planner.decompose(compound_task)

    def estimate_effort(self, tasks: list[PrimitiveTask]) -> dict[str, int | float]:
        """
        Estimate effort for a list of tasks.

        Returns:
            Dictionary with effort estimates
        """
        from iccc.planning.htn import estimate_total_complexity

        total_complexity = estimate_total_complexity(tasks)

        # Rough estimates (adjust based on your team's velocity)
        hours_per_complexity_point = 1.5
        estimated_hours = total_complexity * hours_per_complexity_point

        return {
            "total_complexity": total_complexity,
            "estimated_hours": estimated_hours,
            "estimated_days": estimated_hours / 8,  # 8-hour workday
            "task_count": len(tasks),
        }
