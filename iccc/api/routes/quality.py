"""Quality gate management API endpoints."""

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from litestar import Controller, get, post
from litestar.di import Provide
from litestar.exceptions import NotFoundException

from iccc.api.schemas import (
    QualityCheckCreate,
    QualityCheckResponse,
    QualityGateInfo,
    GateResultSchema,
)
from iccc.db.repositories import (
    MongoDBClient,
    ProjectRepository,
    QualityCheckRepository,
)
from iccc.models.entities import (
    GateResultData,
    QualityCheck,
    QualityCheckStatus,
)
from iccc.quality.gates import (
    LintGate,
    QualityGateRunner,
    SecurityGate,
    TestGate,
    TypeCheckGate,
)

logger = logging.getLogger(__name__)


async def provide_project_repo() -> ProjectRepository:
    """Dependency injection for ProjectRepository."""
    db_client = MongoDBClient()
    await db_client.connect()
    return ProjectRepository(db_client)


async def provide_quality_check_repo() -> QualityCheckRepository:
    """Dependency injection for QualityCheckRepository."""
    db_client = MongoDBClient()
    await db_client.connect()
    return QualityCheckRepository(db_client)


class QualityController(Controller):
    """Controller for quality gate endpoints."""

    path = "/quality"
    tags = ["quality"]
    dependencies = {
        "project_repo": Provide(provide_project_repo),
        "quality_repo": Provide(provide_quality_check_repo),
    }

    @post("/check", status_code=201)
    async def run_quality_check(
        self,
        data: QualityCheckCreate,
        project_repo: ProjectRepository,
        quality_repo: QualityCheckRepository,
    ) -> QualityCheckResponse:
        """
        Run quality gates for a project.

        Args:
            data: Quality check configuration
            project_repo: Project repository
            quality_repo: Quality check repository

        Returns:
            Quality check results

        Raises:
            NotFoundException: If project not found
        """
        # Verify project exists
        project = await project_repo.get(data.project_id)
        if not project:
            raise NotFoundException(detail=f"Project {data.project_id} not found")

        logger.info(
            f"Running quality checks for project {data.project_id} "
            f"(gates: {data.gate_names or 'all'})"
        )

        # Create quality check entity
        check_id = uuid4()
        quality_check = QualityCheck(
            id=check_id,
            project_id=data.project_id,
            task_id=data.task_id,
            status=QualityCheckStatus.RUNNING,
            gate_results=[],
            passed=False,
            created_at=datetime.now(timezone.utc),
            metadata={},
        )

        # Save initial state
        await quality_repo.create(quality_check)

        # Determine which gates to run
        gate_name_to_class = {
            "Lint": LintGate,
            "TypeCheck": TypeCheckGate,
            "Test": TestGate,
            "Security": SecurityGate,
        }

        gates = []
        if data.gate_names:
            # Run specific gates
            for gate_name in data.gate_names:
                if gate_name in gate_name_to_class:
                    gate_class = gate_name_to_class[gate_name]
                    gates.append(gate_class())
                else:
                    logger.warning(f"Unknown gate name: {gate_name}")
        else:
            # Run all default gates
            gates = QualityGateRunner.default_gates()

        # Run the gates
        start_time = time.time()
        runner = QualityGateRunner(gates)
        project_dir = Path(project.directory)

        try:
            gate_results = await runner.run_all(project_dir)

            # Convert GateResult to GateResultData
            gate_results_data = [
                GateResultData(
                    gate_name=result.gate_name,
                    status=result.status.value,
                    message=result.message,
                    details=result.details,
                )
                for result in gate_results
            ]

            # Check overall status
            passed = runner.check_passing(gate_results)

            # Update quality check
            quality_check.gate_results = gate_results_data
            quality_check.passed = passed
            quality_check.status = (
                QualityCheckStatus.PASSED if passed else QualityCheckStatus.FAILED
            )
            quality_check.completed_at = datetime.now(timezone.utc)
            quality_check.duration_seconds = time.time() - start_time

            await quality_repo.update(quality_check)

            logger.info(
                f"Quality check {check_id} completed: "
                f"{'PASSED' if passed else 'FAILED'} "
                f"({quality_check.duration_seconds:.2f}s)"
            )

        except Exception as e:
            logger.error(f"Quality check {check_id} failed with error: {e}", exc_info=True)
            quality_check.status = QualityCheckStatus.FAILED
            quality_check.passed = False
            quality_check.completed_at = datetime.now(timezone.utc)
            quality_check.duration_seconds = time.time() - start_time
            quality_check.metadata["error"] = str(e)
            await quality_repo.update(quality_check)

        return QualityCheckResponse.model_validate(quality_check)

    @get("/check/{check_id:uuid}")
    async def get_quality_check(
        self, check_id: UUID, quality_repo: QualityCheckRepository
    ) -> QualityCheckResponse:
        """
        Get quality check results by ID.

        Args:
            check_id: Quality check UUID
            quality_repo: Quality check repository

        Returns:
            Quality check details

        Raises:
            NotFoundException: If check not found
        """
        quality_check = await quality_repo.get(check_id)
        if not quality_check:
            raise NotFoundException(detail=f"Quality check {check_id} not found")

        return QualityCheckResponse.model_validate(quality_check)

    @get("/checks")
    async def list_quality_checks(
        self,
        quality_repo: QualityCheckRepository,
        project_id: UUID | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[QualityCheckResponse]:
        """
        List quality checks with optional filtering.

        Args:
            quality_repo: Quality check repository
            project_id: Filter by project ID
            status: Filter by status (running/passed/failed)
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of quality checks
        """
        if project_id is None:
            # If no project_id, return empty list (could list all if needed)
            return []

        # Validate status filter
        if status and status not in ["running", "passed", "failed"]:
            status = None

        checks = await quality_repo.list_by_project(
            project_id=project_id, status=status, limit=limit, offset=offset
        )

        return [QualityCheckResponse.model_validate(check) for check in checks]

    @get("/gates")
    async def list_quality_gates(self) -> list[QualityGateInfo]:
        """
        List available quality gates with metadata.

        Returns:
            List of quality gate information
        """
        gates = QualityGateRunner.default_gates()

        gate_descriptions = {
            "Lint": "Code linting and style checking (ruff)",
            "TypeCheck": "Static type checking (mypy)",
            "Test": "Unit and integration tests (pytest)",
            "Security": "Security vulnerability scanning (bandit)",
        }

        return [
            QualityGateInfo(
                name=gate.name,
                required=gate.required,
                description=gate_descriptions.get(gate.name, ""),
            )
            for gate in gates
        ]


# Export router
quality_router = QualityController
