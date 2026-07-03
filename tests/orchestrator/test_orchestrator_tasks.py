"""Unit tests for Orchestrator task submission and execution."""

import asyncio
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from iccc.models.entities import Agent, AgentStatus, ModelTier, Task, TaskStatus, TaskType, RoleType
from iccc.orchestrator import Orchestrator


class TestOrchestratorInit:
    """Tests for Orchestrator initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        project_id = uuid4()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("iccc.orchestrator.ClaudeClient"):
                orchestrator = Orchestrator(
                    project_id=project_id,
                    project_dir=tmpdir,
                )

                assert orchestrator.project_id == project_id
                assert orchestrator.project_dir == tmpdir
                assert orchestrator.agent_repo is None
                assert orchestrator.task_repo is None
                assert orchestrator.running_agents == {}

    def test_init_with_custom_urls(self):
        """Test initialization with custom MongoDB and Redis URLs."""
        project_id = uuid4()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("iccc.orchestrator.ClaudeClient"):
                orchestrator = Orchestrator(
                    project_id=project_id,
                    project_dir=tmpdir,
                    mongodb_url="mongodb://custom:27017/db",
                    redis_url="redis://custom:6379/0",
                )

                assert orchestrator.db_client is not None
                assert orchestrator.task_queue is not None

    def test_init_creates_components(self):
        """Test that all components are created during init."""
        project_id = uuid4()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("iccc.orchestrator.ClaudeClient"):
                orchestrator = Orchestrator(
                    project_id=project_id,
                    project_dir=tmpdir,
                )

                assert orchestrator.db_client is not None
                assert orchestrator.task_queue is not None
                assert orchestrator.file_lock_manager is not None
                assert orchestrator.worktree_manager is not None
                assert orchestrator.claude_client is not None
                assert orchestrator.hook_manager is not None
                assert orchestrator.task_decomposer is not None


class TestSubmitTask:
    """Tests for submit_task method."""

    @pytest.fixture
    async def started_orchestrator(self, project_id):
        """Create a started orchestrator with mocked dependencies."""
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
                orchestrator.task_queue.enqueue = AsyncMock()
                orchestrator.file_lock_manager.connect = AsyncMock()
                orchestrator.file_lock_manager.disconnect = AsyncMock()
                orchestrator.claude_client.close = AsyncMock()

                await orchestrator.start()

                # Mock repositories after start
                orchestrator.task_repo.create = AsyncMock()
                orchestrator.task_repo.update = AsyncMock()

                yield orchestrator

                await orchestrator.stop()

    @pytest.mark.asyncio
    async def test_submit_task_not_started_raises(self, project_id):
        """Test submitting task when orchestrator not started raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("iccc.orchestrator.ClaudeClient"):
                orchestrator = Orchestrator(
                    project_id=project_id,
                    project_dir=tmpdir,
                )

                with pytest.raises(RuntimeError, match="Orchestrator not started"):
                    await orchestrator.submit_task("Test task")

    @pytest.mark.asyncio
    async def test_submit_task_single_task(self, started_orchestrator):
        """Test submitting a single task without auto_decompose."""
        task_ids = await started_orchestrator.submit_task(
            description="Test task",
            task_type="simple_refactor",
            auto_decompose=False,
        )

        assert len(task_ids) == 1
        started_orchestrator.task_repo.create.assert_called_once()
        # Verify default role is WORKER for simple_refactor
        enqueue_call = started_orchestrator.task_queue.enqueue.call_args
        assert enqueue_call[1]["role"] == RoleType.WORKER

    @pytest.mark.asyncio
    async def test_submit_task_with_auto_decompose(self, started_orchestrator):
        """Test submitting task with auto decomposition."""
        # Mock task decomposer to return multiple primitive tasks
        mock_prim_task_1 = MagicMock()
        mock_prim_task_1.name = "analyze"
        mock_prim_task_1.estimated_complexity = 1

        mock_prim_task_2 = MagicMock()
        mock_prim_task_2.name = "implement"
        mock_prim_task_2.estimated_complexity = 3

        started_orchestrator.task_decomposer.decompose_task = MagicMock(
            return_value=[mock_prim_task_1, mock_prim_task_2]
        )

        task_ids = await started_orchestrator.submit_task(
            description="Complex feature",
            task_type="general_coding",
            auto_decompose=True,
        )

        assert len(task_ids) == 2
        assert started_orchestrator.task_repo.create.call_count == 2
        # Only the first task (no dependencies) is enqueued
        assert started_orchestrator.task_queue.enqueue.call_count == 1

    @pytest.mark.asyncio
    async def test_submit_task_with_dependencies(self, started_orchestrator):
        """Test that decomposed tasks have correct dependencies."""
        mock_prim_task_1 = MagicMock()
        mock_prim_task_1.name = "step1"
        mock_prim_task_1.estimated_complexity = 1

        mock_prim_task_2 = MagicMock()
        mock_prim_task_2.name = "step2"
        mock_prim_task_2.estimated_complexity = 2

        started_orchestrator.task_decomposer.decompose_task = MagicMock(
            return_value=[mock_prim_task_1, mock_prim_task_2]
        )

        task_ids = await started_orchestrator.submit_task(
            description="Feature with dependencies",
            task_type="general_coding",
            auto_decompose=True,
        )

        assert len(task_ids) == 2
        # Second task should have dependency on first
        calls = started_orchestrator.task_repo.create.call_args_list
        second_task = calls[1][0][0]
        assert second_task.dependencies == [task_ids[0]]

    @pytest.mark.asyncio
    async def test_submit_task_with_priority(self, started_orchestrator):
        """Test that tasks are enqueued with correct priority."""
        mock_prim_task = MagicMock()
        mock_prim_task.name = "task"
        mock_prim_task.estimated_complexity = 5

        started_orchestrator.task_decomposer.decompose_task = MagicMock(
            return_value=[mock_prim_task]
        )

        await started_orchestrator.submit_task(
            description="Priority task",
            task_type="general_coding",
            auto_decompose=True,
        )

        enqueue_call = started_orchestrator.task_queue.enqueue.call_args
        assert enqueue_call[1]["priority"] == 5


class TestExecuteTask:
    """Tests for _execute_task method."""

    @pytest.fixture
    async def ready_orchestrator(self, project_id):
        """Create an orchestrator ready for task execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("iccc.orchestrator.ClaudeClient") as mock_claude:
                orchestrator = Orchestrator(
                    project_id=project_id,
                    project_dir=tmpdir,
                )

                # Mock components
                orchestrator.db_client.connect = AsyncMock()
                orchestrator.db_client.disconnect = AsyncMock()
                orchestrator.task_queue.connect = AsyncMock()
                orchestrator.task_queue.disconnect = AsyncMock()
                orchestrator.task_queue.enqueue = AsyncMock()
                orchestrator.task_queue.mark_completed = AsyncMock()
                orchestrator.task_queue.mark_failed = AsyncMock()
                orchestrator.file_lock_manager.connect = AsyncMock()
                orchestrator.file_lock_manager.disconnect = AsyncMock()
                orchestrator.claude_client.close = AsyncMock()

                # Mock hook manager
                orchestrator.hook_manager.trigger = AsyncMock()

                await orchestrator.start()

                # Mock repositories after start
                orchestrator.agent_repo.update = AsyncMock()
                orchestrator.agent_repo.get = AsyncMock()
                orchestrator.task_repo.update = AsyncMock()
                orchestrator.task_repo.get = AsyncMock()
                orchestrator.task_repo.list_by_status = AsyncMock(return_value=[])

                yield orchestrator

                await orchestrator.stop()

    @pytest.fixture
    def sample_agent(self, project_id, agent_id):
        """Create a sample WORKER agent for testing."""
        return Agent(
            id=agent_id,
            project_id=project_id,
            name="Test Worker",
            agent_type="general",
            role=RoleType.WORKER,
            model=ModelTier.SONNET,
            status=AgentStatus.IDLE,
            specialization="coding",
        )
    
    @pytest.fixture
    def manager_agent(self, project_id):
        """Create a sample MANAGER agent for testing."""
        return Agent(
            id=f"manager-{uuid4()}",
            project_id=project_id,
            name="Test Manager",
            agent_type="manager",
            role=RoleType.MANAGER,
            model=ModelTier.OPUS,
            status=AgentStatus.IDLE,
            specialization="review",
        )

    @pytest.fixture
    def sample_task(self, project_id):
        """Create a sample task for testing."""
        return Task(
            project_id=project_id,
            description="Test task description",
            task_type=TaskType.SIMPLE_REFACTOR,
            status=TaskStatus.PENDING,
        )

    @pytest.mark.asyncio
    async def test_execute_task_worker_flow(self, ready_orchestrator, sample_agent, sample_task):
        """
        Test typical worker flow:
        1. Worker executes task.
        2. Task result is saved.
        3. Task status becomes REVIEW_NEEDED (not COMPLETED yet).
        4. Task is requeued to MANAGER.
        """
        # Mock Claude success response
        ready_orchestrator.claude_client.send_message = AsyncMock(
            return_value={"content": "Implementation Done"}
        )

        await ready_orchestrator._execute_task(sample_agent, sample_task)

        # Verify task update
        task_updates = ready_orchestrator.task_repo.update.call_args_list
        final_task = task_updates[-1][0][0]
        
        assert final_task.result == "Implementation Done"
        assert final_task.status == TaskStatus.REVIEW_NEEDED
        
        # Verify requeue to MANAGER
        ready_orchestrator.task_queue.enqueue.assert_called_once()
        enqueue_args = ready_orchestrator.task_queue.enqueue.call_args
        assert enqueue_args[1]["role"] == RoleType.MANAGER
        assert enqueue_args[0][0].id == sample_task.id

    @pytest.mark.asyncio
    async def test_execute_task_review_approve(self, ready_orchestrator, manager_agent, sample_task):
        """
        Test manager review flow (Approval):
        1. Task is in REVIEW_NEEDED state.
        2. Manager reviews and says 'APPROVED'.
        3. Task status becomes COMPLETED.
        """
        sample_task.status = TaskStatus.REVIEW_NEEDED
        sample_task.result = "Good implementation"

        # Mock Claude approving
        ready_orchestrator.claude_client.send_message = AsyncMock(
            return_value={"content": "APPROVED: Looks good."}
        )

        await ready_orchestrator._execute_task(manager_agent, sample_task)

        # Verify completion
        task_updates = ready_orchestrator.task_repo.update.call_args_list
        final_task = task_updates[-1][0][0]
        
        assert final_task.status == TaskStatus.COMPLETED
        assert final_task.completed_at is not None
        
        # Verify marked completed in queue
        ready_orchestrator.task_queue.mark_completed.assert_called_once_with(sample_task.id)

    @pytest.mark.asyncio
    async def test_execute_task_review_changes_requested(self, ready_orchestrator, manager_agent, sample_task):
        """
        Test manager review flow (Rejection):
        1. Task is in REVIEW_NEEDED state.
        2. Manager reviews and says 'CHANGES REQUESTED'.
        3. Task status becomes CHANGES_REQUESTED.
        4. Task is requeued to WORKER.
        """
        sample_task.status = TaskStatus.REVIEW_NEEDED
        sample_task.result = "Bad implementation"

        # Mock Claude rejecting
        ready_orchestrator.claude_client.send_message = AsyncMock(
            return_value={"content": "CHANGES REQUESTED: Fix the bugs."}
        )

        await ready_orchestrator._execute_task(manager_agent, sample_task)

        # Verify status update
        task_updates = ready_orchestrator.task_repo.update.call_args_list
        final_task = task_updates[-1][0][0]
        
        assert final_task.status == TaskStatus.CHANGES_REQUESTED
        assert final_task.review_feedback == "CHANGES REQUESTED: Fix the bugs."
        
        # Verify requeue to WORKER
        ready_orchestrator.task_queue.enqueue.assert_called_once()
        enqueue_args = ready_orchestrator.task_queue.enqueue.call_args
        assert enqueue_args[1]["role"] == RoleType.WORKER

    @pytest.mark.asyncio
    async def test_execute_task_failure(self, ready_orchestrator, sample_agent, sample_task):
        """Test task execution failure handling."""
        ready_orchestrator.claude_client.send_message = AsyncMock(
            side_effect=Exception("API error")
        )

        await ready_orchestrator._execute_task(sample_agent, sample_task)

        # Verify task was marked as failed
        task_updates = ready_orchestrator.task_repo.update.call_args_list
        final_task = task_updates[-1][0][0]
        assert final_task.status == TaskStatus.FAILED
        assert "API error" in final_task.error

        # Verify task was marked failed in queue
        ready_orchestrator.task_queue.mark_failed.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_task_updates_timestamps(self, ready_orchestrator, sample_agent, sample_task):
        """Test that timestamps are updated during execution."""
        # Setup for successful worker execution
        ready_orchestrator.claude_client.send_message = AsyncMock(
             return_value={"content": "Done"}
        )
        
        await ready_orchestrator._execute_task(sample_agent, sample_task)

        task_updates = ready_orchestrator.task_repo.update.call_args_list
        # Find the IN_PROGRESS update
        in_progress_task = task_updates[0][0][0]
        assert in_progress_task.started_at is not None

    @pytest.mark.asyncio
    async def test_execute_task_without_repos_returns_early(self, project_id, agent_id):
        """Test _execute_task returns early if repos not initialized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("iccc.orchestrator.ClaudeClient"):
                orchestrator = Orchestrator(
                    project_id=project_id,
                    project_dir=tmpdir,
                )
                
                agent = Agent(
                    id=agent_id,
                    project_id=project_id,
                    name="Test",
                    agent_type="general",
                    model=ModelTier.HAIKU,
                    status=AgentStatus.IDLE,
                    role=RoleType.WORKER
                )

                task = Task(
                    project_id=project_id,
                    description="Test",
                    task_type=TaskType.SIMPLE_REFACTOR,
                    status=TaskStatus.PENDING,
                )

                # Should not raise
                await orchestrator._execute_task(agent, task)


class TestAgentWorkerSync:
    """Tests for agent worker worktree sync behavior."""

    @pytest.fixture
    async def orchestrator_for_sync(self, project_id):
        """Create orchestrator for testing worktree sync."""
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
                orchestrator.file_lock_manager.connect = AsyncMock()
                orchestrator.file_lock_manager.disconnect = AsyncMock()
                orchestrator.claude_client.close = AsyncMock()

                # Mock worktree manager
                orchestrator.worktree_manager.sync_worktree = AsyncMock()

                await orchestrator.start()

                yield orchestrator

                await orchestrator.stop()

    @pytest.mark.asyncio
    async def test_agent_worker_syncs_periodically(self, orchestrator_for_sync, project_id, agent_id):
        """Test that agent worker syncs worktree every 10 tasks."""
        agent = Agent(
            id=agent_id,
            project_id=project_id,
            name="Test",
            agent_type="general",
            model=ModelTier.HAIKU,
            status=AgentStatus.IDLE,
            role=RoleType.WORKER,
            worktree_path="/tmp/worktree",
        )

        # Track dequeue calls
        dequeue_count = 0
        tasks_to_return = 15  # Return 15 tasks to trigger sync

        async def mock_dequeue(agent_id, role):
            nonlocal dequeue_count
            dequeue_count += 1
            if dequeue_count <= tasks_to_return:
                return Task(
                    project_id=project_id,
                    description=f"Task {dequeue_count}",
                    task_type=TaskType.SIMPLE_REFACTOR,
                    status=TaskStatus.PENDING,
                )
            return None

        orchestrator_for_sync.task_queue.dequeue = mock_dequeue
        orchestrator_for_sync._execute_task = AsyncMock()

        # Start worker
        worker_task = asyncio.create_task(orchestrator_for_sync._agent_worker(agent))

        # Wait for processing
        await asyncio.sleep(0.5)

        # Cancel
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

        # Verify sync was called (at task 10)
        assert orchestrator_for_sync.worktree_manager.sync_worktree.call_count >= 1

    @pytest.mark.asyncio
    async def test_agent_worker_handles_sync_failure(self, orchestrator_for_sync, project_id, agent_id):
        """Test that agent worker continues after sync failure."""
        agent = Agent(
            id=agent_id,
            project_id=project_id,
            name="Test",
            agent_type="general",
            model=ModelTier.HAIKU,
            status=AgentStatus.IDLE,
            role=RoleType.WORKER,
            worktree_path="/tmp/worktree",
        )

        # Make sync fail
        orchestrator_for_sync.worktree_manager.sync_worktree = AsyncMock(
            side_effect=Exception("Sync failed")
        )

        # Track dequeue calls
        dequeue_count = 0

        async def mock_dequeue(agent_id, role):
            nonlocal dequeue_count
            dequeue_count += 1
            if dequeue_count <= 12:  # Enough to trigger sync
                return Task(
                    project_id=project_id,
                    description=f"Task {dequeue_count}",
                    task_type=TaskType.SIMPLE_REFACTOR,
                    status=TaskStatus.PENDING,
                )
            return None

        orchestrator_for_sync.task_queue.dequeue = mock_dequeue
        orchestrator_for_sync._execute_task = AsyncMock()

        # Start worker
        worker_task = asyncio.create_task(orchestrator_for_sync._agent_worker(agent))

        # Wait for processing
        await asyncio.sleep(0.5)

        # Cancel
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

        # Worker should have continued processing after sync failure
        assert dequeue_count > 10