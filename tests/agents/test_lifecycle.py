"""Tests for agent lifecycle management."""

import asyncio
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from iccc.agents.lifecycle import AgentLifecycleManager, AgentPool
from iccc.models.entities import Agent, AgentStatus, ModelTier


@pytest.fixture
async def temp_git_repo():
    """Create a temporary git repository for testing."""
    temp_dir = Path(tempfile.mkdtemp())

    try:
        # Initialize git repo
        proc = await asyncio.create_subprocess_exec(
            "git", "init",
            cwd=str(temp_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        # Configure git
        proc = await asyncio.create_subprocess_exec(
            "git", "config", "user.name", "Test User",
            cwd=str(temp_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        proc = await asyncio.create_subprocess_exec(
            "git", "config", "user.email", "test@example.com",
            cwd=str(temp_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        # Create initial commit
        readme = temp_dir / "README.md"
        readme.write_text("# Test Repo")

        proc = await asyncio.create_subprocess_exec(
            "git", "add", "README.md",
            cwd=str(temp_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        proc = await asyncio.create_subprocess_exec(
            "git", "commit", "-m", "Initial commit",
            cwd=str(temp_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        yield temp_dir

    finally:
        # Cleanup
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


@pytest.fixture
def mock_agent_repository():
    """Create a mock agent repository."""
    repo = AsyncMock()
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.list_all = AsyncMock(return_value=[])
    return repo


# ============================================================================
# AgentLifecycleManager Tests
# ============================================================================


class TestAgentLifecycleManager:
    """Tests for AgentLifecycleManager."""

    @pytest.mark.asyncio
    async def test_create_agent_with_worktree(self, temp_git_repo):
        """Test creating an agent with worktree."""
        manager = AgentLifecycleManager(str(temp_git_repo))
        project_id = uuid4()

        agent = await manager.create_agent(
            agent_id="agent-001",
            project_id=project_id,
            name="Test Agent",
            agent_type="frontend-developer",
            model=ModelTier.SONNET,
            create_worktree=True,
        )

        assert agent.id == "agent-001"
        assert agent.project_id == project_id
        assert agent.name == "Test Agent"
        assert agent.agent_type == "frontend-developer"
        assert agent.model == ModelTier.SONNET
        assert agent.status == AgentStatus.IDLE
        assert agent.worktree_path is not None
        assert Path(agent.worktree_path).exists()

        # Cleanup
        await manager.destroy_agent("agent-001")

    @pytest.mark.asyncio
    async def test_create_agent_without_worktree(self, temp_git_repo):
        """Test creating an agent without worktree."""
        manager = AgentLifecycleManager(str(temp_git_repo))
        project_id = uuid4()

        agent = await manager.create_agent(
            agent_id="agent-002",
            project_id=project_id,
            name="Test Agent",
            agent_type="reviewer",
            create_worktree=False,
        )

        assert agent.id == "agent-002"
        assert agent.worktree_path is None

    @pytest.mark.asyncio
    async def test_create_agent_with_repository(self, temp_git_repo, mock_agent_repository):
        """Test that agent is persisted to repository."""
        manager = AgentLifecycleManager(
            str(temp_git_repo), agent_repository=mock_agent_repository
        )
        project_id = uuid4()

        agent = await manager.create_agent(
            agent_id="agent-003",
            project_id=project_id,
            name="Test Agent",
            agent_type="backend-developer",
            create_worktree=False,
        )

        mock_agent_repository.create.assert_called_once_with(agent)

    @pytest.mark.asyncio
    async def test_start_agent(self, temp_git_repo):
        """Test starting an agent."""
        manager = AgentLifecycleManager(str(temp_git_repo))
        project_id = uuid4()

        await manager.create_agent(
            agent_id="agent-004",
            project_id=project_id,
            name="Test Agent",
            agent_type="developer",
            create_worktree=False,
        )

        agent = await manager.start_agent("agent-004")

        assert agent.status == AgentStatus.BUSY

    @pytest.mark.asyncio
    async def test_stop_agent(self, temp_git_repo):
        """Test stopping an agent."""
        manager = AgentLifecycleManager(str(temp_git_repo))
        project_id = uuid4()

        await manager.create_agent(
            agent_id="agent-005",
            project_id=project_id,
            name="Test Agent",
            agent_type="developer",
            create_worktree=False,
        )

        await manager.start_agent("agent-005")
        agent = await manager.stop_agent("agent-005")

        assert agent.status == AgentStatus.IDLE

    @pytest.mark.asyncio
    async def test_mark_agent_error(self, temp_git_repo):
        """Test marking an agent with error."""
        manager = AgentLifecycleManager(str(temp_git_repo))
        project_id = uuid4()

        await manager.create_agent(
            agent_id="agent-006",
            project_id=project_id,
            name="Test Agent",
            agent_type="developer",
            create_worktree=False,
        )

        agent = await manager.mark_agent_error("agent-006", "Test error")

        assert agent.status == AgentStatus.ERROR
        assert agent.metadata["last_error"] == "Test error"

    @pytest.mark.asyncio
    async def test_destroy_agent_with_worktree(self, temp_git_repo):
        """Test destroying an agent removes worktree."""
        manager = AgentLifecycleManager(str(temp_git_repo))
        project_id = uuid4()

        agent = await manager.create_agent(
            agent_id="agent-007",
            project_id=project_id,
            name="Test Agent",
            agent_type="developer",
            create_worktree=True,
        )

        worktree_path = Path(agent.worktree_path)
        assert worktree_path.exists()

        await manager.destroy_agent("agent-007", cleanup_worktree=True)

        assert not worktree_path.exists()
        assert await manager.get_agent("agent-007") is None

    @pytest.mark.asyncio
    async def test_get_agent(self, temp_git_repo):
        """Test getting an agent."""
        manager = AgentLifecycleManager(str(temp_git_repo))
        project_id = uuid4()

        await manager.create_agent(
            agent_id="agent-008",
            project_id=project_id,
            name="Test Agent",
            agent_type="developer",
            create_worktree=False,
        )

        agent = await manager.get_agent("agent-008")
        assert agent is not None
        assert agent.id == "agent-008"

        # Non-existent agent
        agent = await manager.get_agent("non-existent")
        assert agent is None

    @pytest.mark.asyncio
    async def test_list_agents(self, temp_git_repo):
        """Test listing all agents."""
        manager = AgentLifecycleManager(str(temp_git_repo))
        project_id = uuid4()

        await manager.create_agent(
            agent_id="agent-009",
            project_id=project_id,
            name="Agent 1",
            agent_type="developer",
            create_worktree=False,
        )

        await manager.create_agent(
            agent_id="agent-010",
            project_id=project_id,
            name="Agent 2",
            agent_type="tester",
            create_worktree=False,
        )

        agents = await manager.list_agents()

        assert len(agents) == 2
        assert any(a.id == "agent-009" for a in agents)
        assert any(a.id == "agent-010" for a in agents)

    @pytest.mark.asyncio
    async def test_get_agent_worktree_path(self, temp_git_repo):
        """Test getting agent worktree path."""
        manager = AgentLifecycleManager(str(temp_git_repo))
        project_id = uuid4()

        await manager.create_agent(
            agent_id="agent-011",
            project_id=project_id,
            name="Test Agent",
            agent_type="developer",
            create_worktree=True,
        )

        path = await manager.get_agent_worktree_path("agent-011")
        assert path is not None
        assert path.exists()

        # Cleanup
        await manager.destroy_agent("agent-011")

    @pytest.mark.asyncio
    async def test_sync_agent_worktree(self, temp_git_repo):
        """Test syncing agent worktree."""
        manager = AgentLifecycleManager(str(temp_git_repo))
        project_id = uuid4()

        await manager.create_agent(
            agent_id="agent-012",
            project_id=project_id,
            name="Test Agent",
            agent_type="developer",
            create_worktree=True,
        )

        # This should not raise (no remote, but fetch will just do nothing)
        try:
            await manager.sync_agent_worktree("agent-012", "master")
        except RuntimeError:
            pass  # Expected if no master branch

        # Cleanup
        await manager.destroy_agent("agent-012")

    @pytest.mark.asyncio
    async def test_sync_worktree_no_worktree_raises(self, temp_git_repo):
        """Test that syncing without worktree raises error."""
        manager = AgentLifecycleManager(str(temp_git_repo))
        project_id = uuid4()

        await manager.create_agent(
            agent_id="agent-013",
            project_id=project_id,
            name="Test Agent",
            agent_type="developer",
            create_worktree=False,
        )

        with pytest.raises(RuntimeError, match="has no worktree"):
            await manager.sync_agent_worktree("agent-013")

    @pytest.mark.asyncio
    async def test_cleanup_all_agents(self, temp_git_repo):
        """Test cleaning up all agents."""
        manager = AgentLifecycleManager(str(temp_git_repo))
        project_id = uuid4()

        await manager.create_agent(
            agent_id="agent-014",
            project_id=project_id,
            name="Agent 1",
            agent_type="developer",
            create_worktree=True,
        )

        await manager.create_agent(
            agent_id="agent-015",
            project_id=project_id,
            name="Agent 2",
            agent_type="tester",
            create_worktree=True,
        )

        count = await manager.cleanup_all_agents()

        assert count == 2
        assert await manager.get_agent("agent-014") is None
        assert await manager.get_agent("agent-015") is None


# ============================================================================
# AgentPool Tests
# ============================================================================


class TestAgentPool:
    """Tests for AgentPool."""

    @pytest.mark.asyncio
    async def test_pool_initialization(self, temp_git_repo):
        """Test pool initialization."""
        manager = AgentLifecycleManager(str(temp_git_repo))
        pool = AgentPool(manager, min_agents=2, max_agents=5)

        assert pool.min_agents == 2
        assert pool.max_agents == 5
        assert pool.available_count == 0
        assert pool.busy_count == 0

    @pytest.mark.asyncio
    async def test_add_and_acquire_agent(self, temp_git_repo):
        """Test adding and acquiring agents from pool."""
        manager = AgentLifecycleManager(str(temp_git_repo))
        pool = AgentPool(manager, min_agents=1, max_agents=3)
        project_id = uuid4()

        # Create and add agent to pool
        agent = await manager.create_agent(
            agent_id="pool-agent-001",
            project_id=project_id,
            name="Pool Agent 1",
            agent_type="developer",
            create_worktree=False,
        )

        await pool.add_agent(agent)

        assert pool.available_count == 1
        assert pool.total_count == 1

        # Acquire agent
        acquired = await pool.acquire_agent()

        assert acquired is not None
        assert acquired.id == "pool-agent-001"
        assert acquired.status == AgentStatus.BUSY
        assert pool.available_count == 0
        assert pool.busy_count == 1

    @pytest.mark.asyncio
    async def test_release_agent(self, temp_git_repo):
        """Test releasing an agent back to pool."""
        manager = AgentLifecycleManager(str(temp_git_repo))
        pool = AgentPool(manager, min_agents=1, max_agents=3)
        project_id = uuid4()

        # Create and add agent
        agent = await manager.create_agent(
            agent_id="pool-agent-002",
            project_id=project_id,
            name="Pool Agent",
            agent_type="developer",
            create_worktree=False,
        )
        await pool.add_agent(agent)

        # Acquire and release
        await pool.acquire_agent()
        assert pool.busy_count == 1

        await pool.release_agent("pool-agent-002")

        assert pool.busy_count == 0
        assert pool.available_count == 1

    @pytest.mark.asyncio
    async def test_acquire_from_empty_pool(self, temp_git_repo):
        """Test acquiring from empty pool returns None."""
        manager = AgentLifecycleManager(str(temp_git_repo))
        pool = AgentPool(manager)

        agent = await pool.acquire_agent()

        assert agent is None

    @pytest.mark.asyncio
    async def test_pool_max_agents_limit(self, temp_git_repo):
        """Test that pool respects max agents limit."""
        manager = AgentLifecycleManager(str(temp_git_repo))
        pool = AgentPool(manager, min_agents=1, max_agents=2)
        project_id = uuid4()

        # Add 3 agents (max is 2)
        for i in range(3):
            agent = await manager.create_agent(
                agent_id=f"pool-agent-{i+10}",
                project_id=project_id,
                name=f"Pool Agent {i}",
                agent_type="developer",
                create_worktree=False,
            )
            await pool.add_agent(agent)

        # Only 2 should be in pool
        assert pool.total_count == 2

    @pytest.mark.asyncio
    async def test_pool_counters(self, temp_git_repo):
        """Test pool counter properties."""
        manager = AgentLifecycleManager(str(temp_git_repo))
        pool = AgentPool(manager, max_agents=5)
        project_id = uuid4()

        # Add multiple agents
        for i in range(3):
            agent = await manager.create_agent(
                agent_id=f"pool-agent-{i+20}",
                project_id=project_id,
                name=f"Pool Agent {i}",
                agent_type="developer",
                create_worktree=False,
            )
            await pool.add_agent(agent)

        assert pool.available_count == 3
        assert pool.busy_count == 0
        assert pool.total_count == 3

        # Acquire 2
        await pool.acquire_agent()
        await pool.acquire_agent()

        assert pool.available_count == 1
        assert pool.busy_count == 2
        assert pool.total_count == 3
