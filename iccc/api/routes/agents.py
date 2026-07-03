"""Agent management API endpoints."""

from uuid import UUID

from litestar import Controller, get, post, put
from litestar.datastructures import State
from litestar.di import Provide
from litestar.exceptions import NotFoundException

from iccc.api.schemas import AgentCreate, AgentResponse, AgentUpdate
from iccc.db.repositories import AgentRepository


async def provide_agent_repo(state: State) -> AgentRepository:
    """Dependency injection for AgentRepository."""
    return AgentRepository(db_client=state.db_client)


class AgentController(Controller):
    """Controller for agent management endpoints."""

    path = "/agents"
    tags = ["agents"]
    dependencies = {"repo": Provide(provide_agent_repo)}

    @post("/")
    async def register_agent(
        self, data: AgentCreate, repo: AgentRepository
    ) -> AgentResponse:
        """
        Register a new agent.

        Args:
            data: Agent registration data
            repo: Agent repository

        Returns:
            Registered agent
        """
        agent = await repo.create_agent(
            agent_id=data.agent_id,
            agent_type=data.agent_type,
            model=data.model,
            specialization=data.specialization,
            worktree_path=data.worktree_path,
            metadata=data.metadata,
        )
        return AgentResponse.model_validate(agent)

    @get("/")
    async def list_agents(
        self,
        repo: AgentRepository,
        status: str | None = None,
        agent_type: str | None = None,
    ) -> list[AgentResponse]:
        """
        List all agents with optional filtering.

        Args:
            repo: Agent repository
            status: Filter by status (idle/busy/error/stopped)
            agent_type: Filter by type (master/worker)

        Returns:
            List of agents
        """
        agents = await repo.get_all_agents()

        # Client-side filtering
        if status:
            agents = [a for a in agents if a.status == status]
        if agent_type:
            agents = [a for a in agents if a.agent_type == agent_type]

        return [AgentResponse.model_validate(a) for a in agents]

    @get("/{agent_id:uuid}")
    async def get_agent(self, agent_id: UUID, repo: AgentRepository) -> AgentResponse:
        """
        Get a specific agent by ID.

        Args:
            agent_id: Agent UUID
            repo: Agent repository

        Returns:
            Agent details

        Raises:
            NotFoundException: If agent not found
        """
        agent = await repo.get_agent(agent_id)
        if not agent:
            raise NotFoundException(detail=f"Agent {agent_id} not found")

        return AgentResponse.model_validate(agent)

    @put("/{agent_id:uuid}")
    async def update_agent(
        self, agent_id: UUID, data: AgentUpdate, repo: AgentRepository
    ) -> AgentResponse:
        """
        Update agent status or assignment.

        Args:
            agent_id: Agent UUID
            data: Update data
            repo: Agent repository

        Returns:
            Updated agent

        Raises:
            NotFoundException: If agent not found
        """
        # Check agent exists
        existing = await repo.get_agent(agent_id)
        if not existing:
            raise NotFoundException(detail=f"Agent {agent_id} not found")

        # Build update dict
        updates = {}
        if data.status is not None:
            updates["status"] = data.status
        if data.current_task_id is not None:
            updates["current_task_id"] = data.current_task_id
        if data.metadata is not None:
            updates["metadata"] = data.metadata

        agent = await repo.update_agent(agent_id, **updates)
        return AgentResponse.model_validate(agent)


# Export router
agent_router = AgentController
