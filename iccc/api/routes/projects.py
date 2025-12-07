"""Project management API endpoints."""

from uuid import UUID

from litestar import Controller, delete, get, post, put
from litestar.di import Provide
from litestar.exceptions import NotFoundException

from iccc.api.schemas import ErrorResponse, ProjectCreate, ProjectResponse, ProjectUpdate
from iccc.db.repositories import ProjectRepository


async def provide_project_repo() -> ProjectRepository:
    """Dependency injection for ProjectRepository."""
    # In production, this would get the repo from a connection pool
    # For now, create a new instance
    return ProjectRepository()


class ProjectController(Controller):
    """Controller for project management endpoints."""

    path = "/projects"
    tags = ["projects"]
    dependencies = {"repo": Provide(provide_project_repo)}

    @post("/")
    async def create_project(
        self, data: ProjectCreate, repo: ProjectRepository
    ) -> ProjectResponse:
        """
        Create a new project.

        Args:
            data: Project creation data
            repo: Project repository

        Returns:
            Created project

        Raises:
            HTTPException: If creation fails
        """
        project = await repo.create_project(
            name=data.name,
            directory=data.directory,
            description=data.description,
            git_repo=data.git_repo,
            metadata=data.metadata,
        )
        return ProjectResponse.model_validate(project)

    @get("/")
    async def list_projects(
        self,
        repo: ProjectRepository,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProjectResponse]:
        """
        List all projects with optional filtering.

        Args:
            repo: Project repository
            status: Filter by status (active/paused/completed/archived)
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of projects
        """
        # TODO: Implement filtering and pagination in repository
        projects = await repo.get_all_projects()

        # Client-side filtering for now
        if status:
            projects = [p for p in projects if p.status == status]

        # Apply pagination
        projects = projects[offset : offset + limit]

        return [ProjectResponse.model_validate(p) for p in projects]

    @get("/{project_id:uuid}")
    async def get_project(
        self, project_id: UUID, repo: ProjectRepository
    ) -> ProjectResponse:
        """
        Get a specific project by ID.

        Args:
            project_id: Project UUID
            repo: Project repository

        Returns:
            Project details

        Raises:
            NotFoundException: If project not found
        """
        project = await repo.get_project(project_id)
        if not project:
            raise NotFoundException(detail=f"Project {project_id} not found")

        return ProjectResponse.model_validate(project)

    @put("/{project_id:uuid}")
    async def update_project(
        self, project_id: UUID, data: ProjectUpdate, repo: ProjectRepository
    ) -> ProjectResponse:
        """
        Update a project.

        Args:
            project_id: Project UUID
            data: Update data
            repo: Project repository

        Returns:
            Updated project

        Raises:
            NotFoundException: If project not found
        """
        # Check project exists
        existing = await repo.get_project(project_id)
        if not existing:
            raise NotFoundException(detail=f"Project {project_id} not found")

        # Build update dict (only include provided fields)
        updates = {}
        if data.name is not None:
            updates["name"] = data.name
        if data.description is not None:
            updates["description"] = data.description
        if data.status is not None:
            updates["status"] = data.status
        if data.metadata is not None:
            updates["metadata"] = data.metadata

        project = await repo.update_project(project_id, **updates)
        return ProjectResponse.model_validate(project)

    @delete("/{project_id:uuid}", status_code=204)
    async def delete_project(self, project_id: UUID, repo: ProjectRepository) -> None:
        """
        Delete a project.

        Args:
            project_id: Project UUID
            repo: Project repository

        Raises:
            NotFoundException: If project not found
        """
        success = await repo.delete_project(project_id)
        if not success:
            raise NotFoundException(detail=f"Project {project_id} not found")


# Export router
project_router = ProjectController
