"""Agent lifecycle management with worktree integration."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from iccc.isolation.worktree import WorktreeManager
from iccc.models.entities import Agent, AgentStatus, ModelTier

if TYPE_CHECKING:
    from iccc.db.repositories import AgentRepository

logger = logging.getLogger(__name__)


class AgentLifecycleManager:
    """
    Manages the complete lifecycle of agents including worktree creation and cleanup.

    This class integrates:
    - Agent creation with worktree setup
    - Agent state transitions
    - Worktree synchronization
    - Agent cleanup with worktree removal
    """

    def __init__(
        self,
        project_dir: str,
        agent_repository: AgentRepository | None = None,
    ) -> None:
        """
        Initialize the lifecycle manager.

        Args:
            project_dir: Path to the project directory
            agent_repository: Optional repository for agent persistence
        """
        self.project_dir = Path(project_dir)
        self.worktree_manager = WorktreeManager(project_dir)
        self.agent_repository = agent_repository
        self._active_agents: dict[str, Agent] = {}

    async def create_agent(
        self,
        agent_id: str,
        project_id: UUID,
        name: str,
        agent_type: str,
        model: ModelTier = ModelTier.SONNET,
        specialization: str | None = None,
        tools: list[str] | None = None,
        branch: str | None = None,
        create_worktree: bool = True,
    ) -> Agent:
        """
        Create a new agent with optional worktree.

        Args:
            agent_id: Unique identifier for the agent
            project_id: ID of the project this agent works on
            name: Human-readable name
            agent_type: Type of agent (e.g., "frontend-developer")
            model: Claude model tier to use
            specialization: Optional specialization area
            tools: List of available tools
            branch: Optional branch name for worktree
            create_worktree: Whether to create a Git worktree

        Returns:
            Created Agent instance

        Raises:
            RuntimeError: If agent creation fails
        """
        worktree_path: str | None = None

        # Create worktree if requested
        if create_worktree:
            try:
                wt_path = await self.worktree_manager.create_worktree(
                    agent_id, branch=branch
                )
                worktree_path = str(wt_path)
                logger.info(f"Created worktree for agent {agent_id} at {worktree_path}")
            except Exception as e:
                logger.error(
                    f"Failed to create worktree for agent {agent_id}",
                    exc_info=True,
                    extra={"agent_id": agent_id, "branch": branch},
                )
                raise RuntimeError(f"Failed to create worktree for agent {agent_id}: {e}") from e

        # Create agent instance
        agent = Agent(
            id=agent_id,
            project_id=project_id,
            name=name,
            agent_type=agent_type,
            model=model,
            specialization=specialization,
            status=AgentStatus.IDLE,
            worktree_path=worktree_path,
            tools=tools or [],
            created_at=datetime.now(),
            last_active=datetime.now(),
        )

        # Persist if repository available
        if self.agent_repository:
            await self.agent_repository.create(agent)

        # Track in memory
        self._active_agents[agent_id] = agent

        return agent

    async def start_agent(self, agent_id: str) -> Agent:
        """
        Start an agent and mark it as busy.

        Args:
            agent_id: ID of the agent to start

        Returns:
            Updated Agent instance

        Raises:
            ValueError: If agent not found
        """
        agent = await self._get_agent(agent_id)

        if agent.status == AgentStatus.BUSY:
            return agent  # Already busy

        agent.status = AgentStatus.BUSY
        agent.last_active = datetime.now()

        if self.agent_repository:
            await self.agent_repository.update(agent)

        return agent

    async def stop_agent(self, agent_id: str) -> Agent:
        """
        Stop an agent and mark it as idle.

        Args:
            agent_id: ID of the agent to stop

        Returns:
            Updated Agent instance

        Raises:
            ValueError: If agent not found
        """
        agent = await self._get_agent(agent_id)

        agent.status = AgentStatus.IDLE
        agent.last_active = datetime.now()

        if self.agent_repository:
            await self.agent_repository.update(agent)

        return agent

    async def mark_agent_error(self, agent_id: str, error_message: str) -> Agent:
        """
        Mark an agent as having an error.

        Args:
            agent_id: ID of the agent
            error_message: Error description

        Returns:
            Updated Agent instance
        """
        agent = await self._get_agent(agent_id)

        agent.status = AgentStatus.ERROR
        agent.last_active = datetime.now()
        agent.metadata["last_error"] = error_message
        agent.metadata["error_time"] = datetime.now().isoformat()

        if self.agent_repository:
            await self.agent_repository.update(agent)

        return agent

    async def sync_agent_worktree(
        self, agent_id: str, source_branch: str = "main"
    ) -> None:
        """
        Sync an agent's worktree with the source branch.

        Args:
            agent_id: ID of the agent
            source_branch: Branch to sync from

        Raises:
            ValueError: If agent not found
            RuntimeError: If agent has no worktree
        """
        agent = await self._get_agent(agent_id)

        if not agent.worktree_path:
            raise RuntimeError(f"Agent {agent_id} has no worktree")

        await self.worktree_manager.sync_worktree(agent_id, source_branch)

    async def commit_agent_changes(
        self, agent_id: str, message: str, files: list[str] | None = None
    ) -> bool:
        """
        Commit changes in an agent's worktree.

        Args:
            agent_id: ID of the agent
            message: Commit message
            files: Optional list of files to commit

        Returns:
            True if changes were committed

        Raises:
            ValueError: If agent not found
            RuntimeError: If agent has no worktree
        """
        agent = await self._get_agent(agent_id)

        if not agent.worktree_path:
            raise RuntimeError(f"Agent {agent_id} has no worktree")

        return await self.worktree_manager.commit_changes(agent_id, message, files)

    async def destroy_agent(self, agent_id: str, cleanup_worktree: bool = True) -> None:
        """
        Destroy an agent and optionally cleanup its worktree.

        Args:
            agent_id: ID of the agent to destroy
            cleanup_worktree: Whether to remove the worktree

        Raises:
            ValueError: If agent not found
        """
        agent = await self._get_agent(agent_id)

        # Mark as stopped
        agent.status = AgentStatus.STOPPED

        # Remove worktree if requested
        if cleanup_worktree and agent.worktree_path:
            try:
                await self.worktree_manager.remove_worktree(agent_id)
                logger.info(f"Removed worktree for agent {agent_id}")
            except Exception as e:
                logger.warning(
                    f"Failed to cleanup worktree for agent {agent_id}: {e}",
                    exc_info=True,
                    extra={"agent_id": agent_id, "worktree_path": agent.worktree_path},
                )

        # Remove from repository
        if self.agent_repository:
            await self.agent_repository.delete(agent.id)

        # Remove from memory
        self._active_agents.pop(agent_id, None)

    async def get_agent(self, agent_id: str) -> Agent | None:
        """
        Get an agent by ID.

        Args:
            agent_id: ID of the agent

        Returns:
            Agent instance or None if not found
        """
        try:
            return await self._get_agent(agent_id)
        except ValueError:
            return None

    async def list_agents(self) -> list[Agent]:
        """
        List all active agents.

        Returns:
            List of Agent instances
        """
        if self.agent_repository:
            return await self.agent_repository.list_all()

        return list(self._active_agents.values())

    async def get_agent_worktree_path(self, agent_id: str) -> Path | None:
        """
        Get the worktree path for an agent.

        Args:
            agent_id: ID of the agent

        Returns:
            Path to worktree or None
        """
        return await self.worktree_manager.get_worktree_path(agent_id)

    async def cleanup_all_agents(self) -> int:
        """
        Cleanup all agents and their worktrees.

        Returns:
            Number of agents cleaned up
        """
        agents = await self.list_agents()
        count = 0

        for agent in agents:
            try:
                await self.destroy_agent(agent.id, cleanup_worktree=True)
                count += 1
            except Exception as e:
                logger.error(
                    f"Failed to cleanup agent {agent.id}: {e}",
                    exc_info=True,
                    extra={"agent_id": agent.id},
                )

        logger.info(f"Cleaned up {count}/{len(agents)} agents")
        return count

    async def _get_agent(self, agent_id: str) -> Agent:
        """
        Get an agent by ID, raising error if not found.

        Args:
            agent_id: ID of the agent

        Returns:
            Agent instance

        Raises:
            ValueError: If agent not found
        """
        # Check memory first
        if agent_id in self._active_agents:
            return self._active_agents[agent_id]

        # Check repository
        if self.agent_repository:
            agent = await self.agent_repository.get_by_id(agent_id)
            if agent:
                self._active_agents[agent_id] = agent
                return agent

        raise ValueError(f"Agent {agent_id} not found")


class AgentPool:
    """
    Pool of agents for concurrent task execution.

    Manages a collection of agents with automatic scaling
    and load balancing capabilities.
    """

    def __init__(
        self,
        lifecycle_manager: AgentLifecycleManager,
        min_agents: int = 1,
        max_agents: int = 10,
    ) -> None:
        """
        Initialize the agent pool.

        Args:
            lifecycle_manager: Manager for agent lifecycle
            min_agents: Minimum number of agents to maintain
            max_agents: Maximum number of agents allowed
        """
        self.lifecycle_manager = lifecycle_manager
        self.min_agents = min_agents
        self.max_agents = max_agents
        self._available_agents: list[str] = []
        self._busy_agents: set[str] = set()

    async def acquire_agent(self) -> Agent | None:
        """
        Acquire an available agent from the pool.

        Returns:
            Agent instance or None if none available
        """
        if self._available_agents:
            agent_id = self._available_agents.pop(0)
            agent = await self.lifecycle_manager.start_agent(agent_id)
            self._busy_agents.add(agent_id)
            return agent

        return None

    async def release_agent(self, agent_id: str) -> None:
        """
        Release an agent back to the pool.

        Args:
            agent_id: ID of the agent to release
        """
        if agent_id in self._busy_agents:
            await self.lifecycle_manager.stop_agent(agent_id)
            self._busy_agents.discard(agent_id)
            self._available_agents.append(agent_id)

    async def add_agent(self, agent: Agent) -> None:
        """
        Add an agent to the pool.

        Args:
            agent: Agent to add
        """
        if len(self._available_agents) + len(self._busy_agents) < self.max_agents:
            self._available_agents.append(agent.id)

    @property
    def available_count(self) -> int:
        """Number of available agents."""
        return len(self._available_agents)

    @property
    def busy_count(self) -> int:
        """Number of busy agents."""
        return len(self._busy_agents)

    @property
    def total_count(self) -> int:
        """Total number of agents in pool."""
        return self.available_count + self.busy_count
