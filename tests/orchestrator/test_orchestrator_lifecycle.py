"""Tests for Orchestrator lifecycle and agent management."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from iccc.models.entities import Agent, AgentStatus, ModelTier, Task, TaskStatus, TaskType
from iccc.orchestrator import Orchestrator


class TestOrchestratorLifecycle:
    """Test Orchestrator lifecycle operations."""

    @pytest.fixture
    async def mock_orchestrator(self, project_id):
        """Create a mock orchestrator for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("iccc.orchestrator.ClaudeClient"):
                orchestrator = Orchestrator(
                    project_id=project_id,
                    project_dir=tmpdir,
                    mongodb_url="mongodb://localhost/test",
                    redis_url="redis://localhost/1",
                )

                # Mock all external dependencies
                orchestrator.db_client.connect = AsyncMock()
                orchestrator.db_client.disconnect = AsyncMock()
                orchestrator.task_queue.connect = AsyncMock()
                orchestrator.task_queue.disconnect = AsyncMock()
                orchestrator.file_lock_manager.connect = AsyncMock()
                orchestrator.file_lock_manager.disconnect = AsyncMock()
                orchestrator.claude_client.close = AsyncMock()

                # Mock repositories
                orchestrator.agent_repo = MagicMock()
                orchestrator.agent_repo.get = AsyncMock()
                orchestrator.agent_repo.update = AsyncMock()
                orchestrator.agent_repo.list_by_project = AsyncMock(return_value=[])

                orchestrator.task_repo = MagicMock()
                orchestrator.task_repo.create = AsyncMock()
                orchestrator.task_repo.update = AsyncMock()
                orchestrator.task_repo.get = AsyncMock()

                yield orchestrator

    @pytest.mark.asyncio
    async def test_orchestrator_start(self, mock_orchestrator):
        """Test orchestrator start process."""
        await mock_orchestrator.start()

        # Verify all connections were established
        mock_orchestrator.db_client.connect.assert_called_once()
        mock_orchestrator.task_queue.connect.assert_called_once()
        mock_orchestrator.file_lock_manager.connect.assert_called_once()

        # Verify repositories were initialized
        assert mock_orchestrator.agent_repo is not None
        assert mock_orchestrator.task_repo is not None

    @pytest.mark.asyncio
    async def test_orchestrator_stop(self, mock_orchestrator):
        """Test orchestrator stop process."""
        await mock_orchestrator.start()

        # Create a mock running agent task
        agent_task = asyncio.create_task(asyncio.sleep(10))
        mock_orchestrator.running_agents["test-agent"] = agent_task

        await mock_orchestrator.stop()

        # Verify agent task was cancelled
        assert agent_task.cancelled()

        # Verify all connections were closed
        mock_orchestrator.db_client.disconnect.assert_called_once()
        mock_orchestrator.task_queue.disconnect.assert_called_once()
        mock_orchestrator.file_lock_manager.disconnect.assert_called_once()
        mock_orchestrator.claude_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_orchestrator_stop_without_running_agents(self, mock_orchestrator):
        """Test orchestrator stop when no agents are running."""
        await mock_orchestrator.start()
        await mock_orchestrator.stop()

        # Should not raise any exceptions
        mock_orchestrator.db_client.disconnect.assert_called_once()


class TestAgentLifecycle:
    """Test agent lifecycle management."""

    @pytest.fixture
    async def orchestrator_with_mocks(self, project_id):
        """Create orchestrator with mocked dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("iccc.orchestrator.ClaudeClient"):
                orchestrator = Orchestrator(
                    project_id=project_id,
                    project_dir=tmpdir,
                )

                # Mock components
                orchestrator.db_client.connect = AsyncMock()
                orchestrator.db_client.disconnect = AsyncMock()
                orchestrator.task_queue.connect = AsyncMock()
                orchestrator.task_queue.disconnect = AsyncMock()
                orchestrator.task_queue.dequeue = AsyncMock(return_value=None)
                orchestrator.file_lock_manager.connect = AsyncMock()
                orchestrator.file_lock_manager.disconnect = AsyncMock()
                orchestrator.claude_client.close = AsyncMock()

                # Mock worktree manager
                orchestrator.worktree_manager.create_worktree = AsyncMock(return_value=Path(tmpdir) / "worktree")
                orchestrator.worktree_manager.remove_worktree = AsyncMock()
                orchestrator.worktree_manager.sync_worktree = AsyncMock()

                # Mock repositories
                orchestrator.agent_repo = MagicMock()
                orchestrator.task_repo = MagicMock()

                await orchestrator.start()

                yield orchestrator

                await orchestrator.stop()

    @pytest.mark.asyncio
    async def test_start_agent_success(self, orchestrator_with_mocks, agent_id):
        """Test successfully starting an agent."""
        agent = Agent(
            id=agent_id,
            project_id=orchestrator_with_mocks.project_id,
            name="Test Agent",
            agent_type="general",
            model=ModelTier.HAIKU,
            status=AgentStatus.STOPPED,
        )

        orchestrator_with_mocks.agent_repo.get = AsyncMock(return_value=agent)
        orchestrator_with_mocks.agent_repo.update = AsyncMock()

        await orchestrator_with_mocks.start_agent(agent_id)

        # Verify worktree was created
        orchestrator_with_mocks.worktree_manager.create_worktree.assert_called_once_with(agent_id)

        # Verify agent status was updated
        assert orchestrator_with_mocks.agent_repo.update.called
        updated_agent = orchestrator_with_mocks.agent_repo.update.call_args[0][0]
        assert updated_agent.status == AgentStatus.IDLE
        assert updated_agent.worktree_path is not None

        # Verify worker task was created
        assert agent_id in orchestrator_with_mocks.running_agents

    @pytest.mark.asyncio
    async def test_start_agent_not_found(self, orchestrator_with_mocks, agent_id):
        """Test starting an agent that doesn't exist."""
        orchestrator_with_mocks.agent_repo.get = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match=f"Agent {agent_id} not found"):
            await orchestrator_with_mocks.start_agent(agent_id)

    @pytest.mark.asyncio
    async def test_stop_agent_success(self, orchestrator_with_mocks, agent_id):
        """Test successfully stopping an agent."""
        agent = Agent(
            id=agent_id,
            project_id=orchestrator_with_mocks.project_id,
            name="Test Agent",
            agent_type="general",
            model=ModelTier.HAIKU,
            status=AgentStatus.IDLE,
        )

        # Start the agent first
        orchestrator_with_mocks.agent_repo.get = AsyncMock(return_value=agent)
        orchestrator_with_mocks.agent_repo.update = AsyncMock()
        await orchestrator_with_mocks.start_agent(agent_id)

        # Now stop it
        await orchestrator_with_mocks.stop_agent(agent_id)

        # Verify agent was removed from running agents
        assert agent_id not in orchestrator_with_mocks.running_agents

        # Verify agent status was updated
        updated_agent = orchestrator_with_mocks.agent_repo.update.call_args[0][0]
        assert updated_agent.status == AgentStatus.STOPPED

        # Verify worktree was removed
        orchestrator_with_mocks.worktree_manager.remove_worktree.assert_called_with(agent_id)

    @pytest.mark.asyncio
    async def test_stop_agent_not_running(self, orchestrator_with_mocks, agent_id):
        """Test stopping an agent that isn't running."""
        # Should not raise any exceptions
        await orchestrator_with_mocks.stop_agent(agent_id)

    @pytest.mark.asyncio
    async def test_agent_worker_loop(self, orchestrator_with_mocks, agent_id):
        """Test the agent worker loop processes tasks."""
        agent = Agent(
            id=agent_id,
            project_id=orchestrator_with_mocks.project_id,
            name="Test Agent",
            agent_type="general",
            model=ModelTier.HAIKU,
            status=AgentStatus.IDLE,
            worktree_path="/tmp/worktree",
        )

        task = Task(
            project_id=orchestrator_with_mocks.project_id,
            description="Test task",
            task_type=TaskType.GENERAL_CODING,
            status=TaskStatus.PENDING,
        )

        # Mock dequeue to return a task once, then None
        call_count = 0

        async def mock_dequeue(agent_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return task
            return None

        orchestrator_with_mocks.task_queue.dequeue = mock_dequeue

        # Mock _execute_task
        orchestrator_with_mocks._execute_task = AsyncMock()

        # Start worker and let it run briefly
        worker_task = asyncio.create_task(orchestrator_with_mocks._agent_worker(agent))

        # Give it time to process one task
        await asyncio.sleep(0.1)

        # Cancel the worker
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

        # Verify task was executed
        orchestrator_with_mocks._execute_task.assert_called_once_with(agent, task)

    @pytest.mark.asyncio
    async def test_agent_worker_handles_exceptions(self, orchestrator_with_mocks, agent_id):
        """Test agent worker continues after exceptions."""
        agent = Agent(
            id=agent_id,
            project_id=orchestrator_with_mocks.project_id,
            name="Test Agent",
            agent_type="general",
            model=ModelTier.HAIKU,
            status=AgentStatus.IDLE,
            worktree_path="/tmp/worktree",
        )

        # Mock dequeue to raise exception then return None
        call_count = 0

        async def mock_dequeue(agent_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Dequeue error")
            return None

        orchestrator_with_mocks.task_queue.dequeue = mock_dequeue

        # Start worker
        worker_task = asyncio.create_task(orchestrator_with_mocks._agent_worker(agent))

        # Give it time to handle exception and continue
        await asyncio.sleep(6)

        # Cancel the worker
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

        # Verify it attempted to dequeue multiple times (recovered from error)
        assert call_count > 1


class TestOrchestratorStatus:
    """Test orchestrator status reporting."""

    @pytest.mark.asyncio
    async def test_get_status_not_started(self, project_id):
        """Test get_status when orchestrator not started."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("iccc.orchestrator.ClaudeClient"):
                orchestrator = Orchestrator(
                    project_id=project_id,
                    project_dir=tmpdir,
                )

                status = await orchestrator.get_status()
                assert status["status"] == "not_started"

    @pytest.mark.asyncio
    async def test_get_status_running(self, project_id, agent_id):
        """Test get_status when orchestrator is running."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("iccc.orchestrator.ClaudeClient"):
                orchestrator = Orchestrator(
                    project_id=project_id,
                    project_dir=tmpdir,
                )

                # Mock dependencies
                orchestrator.db_client.connect = AsyncMock()
                orchestrator.db_client.disconnect = AsyncMock()
                orchestrator.task_queue.connect = AsyncMock()
                orchestrator.task_queue.disconnect = AsyncMock()
                orchestrator.task_queue.get_queue_length = AsyncMock(
                    return_value={"pending": 5, "in_progress": 2, "completed": 10}
                )
                orchestrator.file_lock_manager.connect = AsyncMock()
                orchestrator.file_lock_manager.disconnect = AsyncMock()
                orchestrator.claude_client.close = AsyncMock()

                agent = Agent(
                    id=agent_id,
                    project_id=project_id,
                    name="Test Agent",
                    agent_type="general",
                    model=ModelTier.HAIKU,
                    status=AgentStatus.IDLE,
                )

                await orchestrator.start()

                # Note: start() creates new repositories, so we must mock AFTER start()
                agent_repo_mock = MagicMock()
                agent_repo_mock.list_by_project = AsyncMock(return_value=[agent])
                orchestrator.agent_repo = agent_repo_mock
                orchestrator.task_repo = MagicMock()

                # Add a running agent
                orchestrator.running_agents[agent_id] = asyncio.create_task(asyncio.sleep(10))

                status = await orchestrator.get_status()

                assert status["status"] == "running"
                assert status["running_agents"] == 1
                assert agent_id in status["agents"]
                assert status["agents"][agent_id] == AgentStatus.IDLE
                assert status["tasks"]["pending"] == 5
                assert status["tasks"]["completed"] == 10

                # Cleanup
                orchestrator.running_agents[agent_id].cancel()
                await orchestrator.stop()
