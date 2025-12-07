"""Unit tests for Orchestrator task submission and execution."""

import asyncio
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from iccc.models.entities import Agent, AgentStatus, ModelTier, Task, TaskStatus, TaskType
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
        started_orchestrator.task_queue.enqueue.assert_called_once()

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

        mock_prim_task_3 = MagicMock()
        mock_prim_task_3.name = "test"
        mock_prim_task_3.estimated_complexity = 2

        started_orchestrator.task_decomposer.decompose_task = MagicMock(
            return_value=[mock_prim_task_1, mock_prim_task_2, mock_prim_task_3]
        )

        task_ids = await started_orchestrator.submit_task(
            description="Complex feature",
            task_type="general_coding",
            auto_decompose=True,
        )

        assert len(task_ids) == 3
        assert started_orchestrator.task_repo.create.call_count == 3
        assert started_orchestrator.task_queue.enqueue.call_count == 3

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
    async def test_submit_task_with_task_type(self, started_orchestrator):
        """Test submitting task with specific task type."""
        await started_orchestrator.submit_task(
            description="Test refactor",
            task_type="simple_refactor",
            auto_decompose=False,
        )

        call_args = started_orchestrator.task_repo.create.call_args
        created_task = call_args[0][0]
        assert created_task.task_type == "simple_refactor"

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
                orchestrator.task_queue.mark_completed = AsyncMock()
                orchestrator.task_queue.mark_failed = AsyncMock()
                orchestrator.file_lock_manager.connect = AsyncMock()
                orchestrator.file_lock_manager.disconnect = AsyncMock()
                orchestrator.claude_client.close = AsyncMock()

                # Mock Claude client response
                orchestrator.claude_client.send_message = AsyncMock(
                    return_value={
                        "content": "Task completed successfully",
                        "usage": {"input_tokens": 100, "output_tokens": 50},
                        "stop_reason": "end_turn",
                        "model": "claude-sonnet-4-20250514",
                    }
                )

                # Mock hook manager
                orchestrator.hook_manager.trigger = AsyncMock()

                await orchestrator.start()

                # Mock repositories after start
                orchestrator.agent_repo.update = AsyncMock()
                orchestrator.task_repo.update = AsyncMock()

                yield orchestrator

                await orchestrator.stop()

    @pytest.fixture
    def sample_agent(self, project_id, agent_id):
        """Create a sample agent for testing."""
        return Agent(
            id=agent_id,
            project_id=project_id,
            name="Test Agent",
            agent_type="general",
            model=ModelTier.SONNET,
            status=AgentStatus.IDLE,
            specialization="coding",
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
    async def test_execute_task_success(self, ready_orchestrator, sample_agent, sample_task):
        """Test successful task execution."""
        await ready_orchestrator._execute_task(sample_agent, sample_task)

        # Verify agent status was updated to BUSY then IDLE
        agent_updates = ready_orchestrator.agent_repo.update.call_args_list
        assert len(agent_updates) >= 2

        # Verify task status was updated
        task_updates = ready_orchestrator.task_repo.update.call_args_list
        assert len(task_updates) >= 2
        final_task = task_updates[-1][0][0]
        assert final_task.status == TaskStatus.COMPLETED
        assert final_task.result == "Task completed successfully"

        # Verify task was marked completed in queue
        ready_orchestrator.task_queue.mark_completed.assert_called_once_with(sample_task.id)

    @pytest.mark.asyncio
    async def test_execute_task_triggers_hooks(self, ready_orchestrator, sample_agent, sample_task):
        """Test that hooks are triggered during task execution."""
        await ready_orchestrator._execute_task(sample_agent, sample_task)

        # Verify PreToolUse and PostToolUse hooks were triggered
        hook_calls = ready_orchestrator.hook_manager.trigger.call_args_list
        assert len(hook_calls) == 2

        pre_hook = hook_calls[0]
        assert pre_hook[0][0] == "PreToolUse"

        post_hook = hook_calls[1]
        assert post_hook[0][0] == "PostToolUse"

    @pytest.mark.asyncio
    async def test_execute_task_sends_correct_message(self, ready_orchestrator, sample_agent, sample_task):
        """Test that correct message is sent to Claude."""
        await ready_orchestrator._execute_task(sample_agent, sample_task)

        send_call = ready_orchestrator.claude_client.send_message.call_args
        messages = send_call[1]["messages"]
        assert len(messages) == 1
        assert sample_task.description in messages[0].content
        assert "system" in send_call[1]
        assert sample_agent.name in send_call[1]["system"]

    @pytest.mark.asyncio
    async def test_execute_task_uses_model_selector(self, ready_orchestrator, sample_agent, sample_task):
        """Test that model is selected based on task type."""
        with patch("iccc.orchestrator.ModelSelector.select_model") as mock_selector:
            mock_selector.return_value = ModelTier.HAIKU
            await ready_orchestrator._execute_task(sample_agent, sample_task)

            mock_selector.assert_called_once_with(sample_task.task_type, sample_task.complexity)
            send_call = ready_orchestrator.claude_client.send_message.call_args
            assert send_call[1]["model"] == ModelTier.HAIKU

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
        await ready_orchestrator._execute_task(sample_agent, sample_task)

        task_updates = ready_orchestrator.task_repo.update.call_args_list
        # Find the IN_PROGRESS update
        in_progress_task = task_updates[0][0][0]
        assert in_progress_task.started_at is not None

        # Find the COMPLETED update
        completed_task = task_updates[1][0][0]
        assert completed_task.completed_at is not None

    @pytest.mark.asyncio
    async def test_execute_task_assigns_agent(self, ready_orchestrator, sample_agent, sample_task):
        """Test that task is assigned to agent."""
        await ready_orchestrator._execute_task(sample_agent, sample_task)

        task_updates = ready_orchestrator.task_repo.update.call_args_list
        in_progress_task = task_updates[0][0][0]
        assert in_progress_task.assigned_agent_id == sample_agent.id

    @pytest.mark.asyncio
    async def test_execute_task_agent_restored_to_idle(self, ready_orchestrator, sample_agent, sample_task):
        """Test that agent status is restored to IDLE after execution."""
        await ready_orchestrator._execute_task(sample_agent, sample_task)

        agent_updates = ready_orchestrator.agent_repo.update.call_args_list
        final_agent_update = agent_updates[-1][0][0]
        assert final_agent_update.status == AgentStatus.IDLE

    @pytest.mark.asyncio
    async def test_execute_task_agent_last_active_updated(self, ready_orchestrator, sample_agent, sample_task):
        """Test that agent last_active is updated."""
        await ready_orchestrator._execute_task(sample_agent, sample_task)

        agent_updates = ready_orchestrator.agent_repo.update.call_args_list
        final_agent_update = agent_updates[-1][0][0]
        assert final_agent_update.last_active is not None

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
            worktree_path="/tmp/worktree",
        )

        # Track dequeue calls
        dequeue_count = 0
        tasks_to_return = 15  # Return 15 tasks to trigger sync

        async def mock_dequeue(agent_id):
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
            worktree_path="/tmp/worktree",
        )

        # Make sync fail
        orchestrator_for_sync.worktree_manager.sync_worktree = AsyncMock(
            side_effect=Exception("Sync failed")
        )

        # Track dequeue calls
        dequeue_count = 0

        async def mock_dequeue(agent_id):
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
