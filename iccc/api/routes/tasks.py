"""Task management API endpoints."""

from uuid import UUID

from litestar import Controller, get, post, put
from litestar.di import Provide
from litestar.exceptions import NotFoundException

from iccc.api.schemas import TaskCreate, TaskResponse, TaskUpdate
from iccc.db.repositories import TaskRepository


async def provide_task_repo() -> TaskRepository:
    """Dependency injection for TaskRepository."""
    return TaskRepository()


class TaskController(Controller):
    """Controller for task management endpoints."""

    path = "/tasks"
    tags = ["tasks"]
    dependencies = {"repo": Provide(provide_task_repo)}

    @post("/")
    async def create_task(self, data: TaskCreate, repo: TaskRepository) -> TaskResponse:
        """
        Create a new task.

        Args:
            data: Task creation data
            repo: Task repository

        Returns:
            Created task
        """
        task = await repo.create_task(
            project_id=data.project_id,
            description=data.description,
            task_type=data.task_type,
            priority=data.priority,
            dependencies=data.dependencies,
            metadata=data.metadata,
        )
        return TaskResponse.model_validate(task)

    @get("/")
    async def list_tasks(
        self,
        repo: TaskRepository,
        project_id: UUID | None = None,
        status: str | None = None,
        assigned_agent_id: str | None = None,
    ) -> list[TaskResponse]:
        """
        List tasks with optional filtering.

        Args:
            repo: Task repository
            project_id: Filter by project
            status: Filter by status
            assigned_agent_id: Filter by assigned agent

        Returns:
            List of tasks
        """
        if project_id:
            tasks = await repo.get_tasks_by_project(project_id)
        else:
            tasks = await repo.get_all_tasks()

        # Client-side filtering
        if status:
            tasks = [t for t in tasks if t.status == status]
        if assigned_agent_id:
            tasks = [t for t in tasks if t.assigned_agent_id == assigned_agent_id]

        return [TaskResponse.model_validate(t) for t in tasks]

    @get("/{task_id:uuid}")
    async def get_task(self, task_id: UUID, repo: TaskRepository) -> TaskResponse:
        """
        Get a specific task by ID.

        Args:
            task_id: Task UUID
            repo: Task repository

        Returns:
            Task details

        Raises:
            NotFoundException: If task not found
        """
        task = await repo.get_task(task_id)
        if not task:
            raise NotFoundException(detail=f"Task {task_id} not found")

        return TaskResponse.model_validate(task)

    @put("/{task_id:uuid}")
    async def update_task(
        self, task_id: UUID, data: TaskUpdate, repo: TaskRepository
    ) -> TaskResponse:
        """
        Update task status or assignment.

        Args:
            task_id: Task UUID
            data: Update data
            repo: Task repository

        Returns:
            Updated task

        Raises:
            NotFoundException: If task not found
        """
        # Check task exists
        existing = await repo.get_task(task_id)
        if not existing:
            raise NotFoundException(detail=f"Task {task_id} not found")

        # Build update dict
        updates = {}
        if data.status is not None:
            updates["status"] = data.status
        if data.assigned_agent_id is not None:
            updates["assigned_agent_id"] = data.assigned_agent_id
        if data.result is not None:
            updates["result"] = data.result
        if data.error is not None:
            updates["error"] = data.error
        if data.metadata is not None:
            updates["metadata"] = data.metadata

        task = await repo.update_task(task_id, **updates)
        return TaskResponse.model_validate(task)


# Export router
task_router = TaskController
