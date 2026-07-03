"""Unit tests for Redis task queue module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from iccc.models.entities import Task, TaskStatus, TaskType, RoleType
from iccc.queue.redis_queue import RedisTaskQueue


class TestRedisTaskQueueInit:
    """Tests for RedisTaskQueue initialization."""

    def test_init_default_url(self):
        """Test initialization with default Redis URL."""
        # Mock get_config to return default values
        with patch("iccc.queue.redis_queue.get_config") as mock_get_config:
            # Create a mock config object with redis attributes
            mock_config = MagicMock()
            mock_config.redis.host = "localhost"
            mock_config.redis.port = 6379
            mock_config.redis.db = 0
            mock_config.redis.password = None
            mock_get_config.return_value = mock_config

            with patch.dict("os.environ", {}, clear=True):
                queue = RedisTaskQueue()
                assert queue.redis_url == "redis://localhost:6379/0"

    def test_init_with_custom_url(self):
        """Test initialization with custom Redis URL."""
        queue = RedisTaskQueue(redis_url="redis://custom:6379/1")
        assert queue.redis_url == "redis://custom:6379/1"

    def test_init_with_env_var(self):
        """Test initialization with REDIS_URL environment variable."""
        with patch.dict("os.environ", {"REDIS_URL": "redis://env:6379/2"}):
            queue = RedisTaskQueue()
            assert queue.redis_url == "redis://env:6379/2"

    def test_init_client_is_none(self):
        """Test that client is None before connect."""
        queue = RedisTaskQueue()
        assert queue.client is None

    def test_init_queue_keys(self):
        """Test queue key initialization."""
        queue = RedisTaskQueue()
        assert queue.pending_queue_prefix == "iccc:tasks:pending"
        assert queue.in_progress_queue == "iccc:tasks:pending:in_progress"
        assert queue.completed_queue == "iccc:tasks:pending:completed"
        assert queue.task_data_prefix == "iccc:task:"


class TestRedisTaskQueueConnection:
    """Tests for connection management."""

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful Redis connection."""
        with patch("iccc.queue.redis_queue.redis.from_url") as mock_from_url:
            mock_client = AsyncMock()
            # from_url is awaited, so we need to return a coroutine
            mock_from_url.return_value = mock_client
            mock_from_url.side_effect = AsyncMock(return_value=mock_client)

            queue = RedisTaskQueue()
            await queue.connect()

            mock_from_url.assert_called_once_with(
                queue.redis_url, decode_responses=True
            )
            assert queue.client == mock_client

    @pytest.mark.asyncio
    async def test_disconnect_with_client(self):
        """Test disconnecting when client exists."""
        queue = RedisTaskQueue()
        queue.client = AsyncMock()

        await queue.disconnect()

        queue.client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_without_client(self):
        """Test disconnecting when no client exists."""
        queue = RedisTaskQueue()
        # Should not raise
        await queue.disconnect()


class TestRedisTaskQueueEnqueue:
    """Tests for enqueue method."""

    @pytest.fixture
    def connected_queue(self):
        """Create a connected queue with mock client."""
        queue = RedisTaskQueue()
        queue.client = AsyncMock()
        return queue

    @pytest.fixture
    def sample_task(self):
        """Create a sample task."""
        return Task(
            project_id=uuid4(),
            description="Test task",
            task_type=TaskType.SIMPLE_REFACTOR,
            status=TaskStatus.PENDING,
        )

    @pytest.mark.asyncio
    async def test_enqueue_success_default_role(self, connected_queue, sample_task):
        """Test successful task enqueue with default role (WORKER)."""
        await connected_queue.enqueue(sample_task)

        # Verify task data was stored
        connected_queue.client.set.assert_called_once()
        call_args = connected_queue.client.set.call_args
        assert str(sample_task.id) in call_args[0][0]

        # Verify task was added to WORKER queue
        connected_queue.client.zadd.assert_called_once()
        zadd_args = connected_queue.client.zadd.call_args
        assert zadd_args[0][0] == "iccc:tasks:pending:worker"

    @pytest.mark.asyncio
    async def test_enqueue_success_manager_role(self, connected_queue, sample_task):
        """Test successful task enqueue with MANAGER role."""
        await connected_queue.enqueue(sample_task, role=RoleType.MANAGER)

        connected_queue.client.zadd.assert_called_once()
        zadd_args = connected_queue.client.zadd.call_args
        assert zadd_args[0][0] == "iccc:tasks:pending:manager"

    @pytest.mark.asyncio
    async def test_enqueue_with_priority(self, connected_queue, sample_task):
        """Test enqueue with custom priority."""
        await connected_queue.enqueue(sample_task, priority=10)

        # Verify priority was used
        call_args = connected_queue.client.zadd.call_args
        assert call_args[0][1][str(sample_task.id)] == 10

    @pytest.mark.asyncio
    async def test_enqueue_without_connection_raises(self, sample_task):
        """Test enqueue without connection raises RuntimeError."""
        queue = RedisTaskQueue()

        with pytest.raises(RuntimeError, match="Redis client not connected"):
            await queue.enqueue(sample_task)


class TestRedisTaskQueueDequeue:
    """Tests for dequeue method."""

    @pytest.fixture
    def connected_queue(self):
        """Create a connected queue with mock client."""
        queue = RedisTaskQueue()
        queue.client = AsyncMock()
        return queue

    @pytest.mark.asyncio
    async def test_dequeue_success_worker(self, connected_queue):
        """Test successful task dequeue for WORKER role."""
        task_id = str(uuid4())
        task_data = {
            "id": task_id,
            "project_id": str(uuid4()),
            "description": "Test task",
            "task_type": "simple_refactor",
            "status": "pending",
        }

        # Mock zpopmax to return task ID
        connected_queue.client.zpopmax = AsyncMock(return_value=[(task_id, 10.0)])
        # Mock get to return task data
        connected_queue.client.get = AsyncMock(return_value=json.dumps(task_data))

        result = await connected_queue.dequeue("agent-1", role=RoleType.WORKER)

        assert result is not None
        assert result.description == "Test task"
        
        # Verify popped from correct queue
        zpop_args = connected_queue.client.zpopmax.call_args
        assert zpop_args[0][0] == "iccc:tasks:pending:worker"

        # Verify task was moved to in_progress
        connected_queue.client.hset.assert_called_once()

    @pytest.mark.asyncio
    async def test_dequeue_empty_queue(self, connected_queue):
        """Test dequeue from empty queue returns None."""
        connected_queue.client.zpopmax = AsyncMock(return_value=[])

        result = await connected_queue.dequeue("agent-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_dequeue_task_data_not_found(self, connected_queue):
        """Test dequeue when task data is missing."""
        task_id = str(uuid4())
        connected_queue.client.zpopmax = AsyncMock(return_value=[(task_id, 10.0)])
        connected_queue.client.get = AsyncMock(return_value=None)

        result = await connected_queue.dequeue("agent-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_dequeue_without_connection_raises(self):
        """Test dequeue without connection raises RuntimeError."""
        queue = RedisTaskQueue()

        with pytest.raises(RuntimeError, match="Redis client not connected"):
            await queue.dequeue("agent-1")


class TestRedisTaskQueueMarkCompleted:
    """Tests for mark_completed method."""

    @pytest.fixture
    def connected_queue(self):
        """Create a connected queue with mock client."""
        queue = RedisTaskQueue()
        queue.client = AsyncMock()
        return queue

    @pytest.mark.asyncio
    async def test_mark_completed_success(self, connected_queue):
        """Test marking task as completed."""
        task_id = uuid4()

        await connected_queue.mark_completed(task_id)

        # Verify removed from in_progress
        connected_queue.client.hdel.assert_called_once_with(
            connected_queue.in_progress_queue, str(task_id)
        )
        # Verify added to completed
        connected_queue.client.sadd.assert_called_once_with(
            connected_queue.completed_queue, str(task_id)
        )

    @pytest.mark.asyncio
    async def test_mark_completed_without_connection_raises(self):
        """Test mark_completed without connection raises RuntimeError."""
        queue = RedisTaskQueue()

        with pytest.raises(RuntimeError, match="Redis client not connected"):
            await queue.mark_completed(uuid4())


class TestRedisTaskQueueMarkFailed:
    """Tests for mark_failed method."""

    @pytest.fixture
    def connected_queue(self):
        """Create a connected queue with mock client."""
        queue = RedisTaskQueue()
        queue.client = AsyncMock()
        return queue

    @pytest.mark.asyncio
    async def test_mark_failed_success(self, connected_queue):
        """Test marking task as failed."""
        task_id = uuid4()

        await connected_queue.mark_failed(task_id, "Test error")

        # Verify removed from in_progress
        connected_queue.client.hdel.assert_called_once()
        # Verify error was stored
        connected_queue.client.set.assert_called_once()
        call_args = connected_queue.client.set.call_args
        assert "error" in call_args[0][0]
        assert call_args[0][1] == "Test error"
        # Verify added to failed set
        connected_queue.client.sadd.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_failed_without_connection_raises(self):
        """Test mark_failed without connection raises RuntimeError."""
        queue = RedisTaskQueue()

        with pytest.raises(RuntimeError, match="Redis client not connected"):
            await queue.mark_failed(uuid4(), "error")


class TestRedisTaskQueueGetTask:
    """Tests for get_task method."""

    @pytest.fixture
    def connected_queue(self):
        """Create a connected queue with mock client."""
        queue = RedisTaskQueue()
        queue.client = AsyncMock()
        return queue

    @pytest.mark.asyncio
    async def test_get_task_success(self, connected_queue):
        """Test getting task by ID."""
        task_id = uuid4()
        task_data = {
            "id": str(task_id),
            "project_id": str(uuid4()),
            "description": "Test task",
            "task_type": "simple_refactor",
            "status": "pending",
        }

        connected_queue.client.get = AsyncMock(return_value=json.dumps(task_data))

        result = await connected_queue.get_task(task_id)

        assert result is not None
        assert result.description == "Test task"

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, connected_queue):
        """Test getting non-existent task returns None."""
        connected_queue.client.get = AsyncMock(return_value=None)

        result = await connected_queue.get_task(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_task_without_connection_raises(self):
        """Test get_task without connection raises RuntimeError."""
        queue = RedisTaskQueue()

        with pytest.raises(RuntimeError, match="Redis client not connected"):
            await queue.get_task(uuid4())


class TestRedisTaskQueueGetQueueLength:
    """Tests for get_queue_length method."""

    @pytest.fixture
    def connected_queue(self):
        """Create a connected queue with mock client."""
        queue = RedisTaskQueue()
        queue.client = AsyncMock()
        return queue

    @pytest.mark.asyncio
    async def test_get_queue_length_success(self, connected_queue):
        """Test getting queue lengths."""
        # zcard for 3 roles
        connected_queue.client.zcard = AsyncMock(side_effect=[5, 3, 1])
        # hlen for in_progress
        connected_queue.client.hlen = AsyncMock(return_value=2)
        # scard for completed and failed
        connected_queue.client.scard = AsyncMock(side_effect=[10, 1])

        result = await connected_queue.get_queue_length()

        assert result["pending_worker"] == 5
        assert result["pending_manager"] == 3
        assert result["pending_brain"] == 1
        assert result["in_progress"] == 2
        assert result["completed"] == 10
        assert result["failed"] == 1

    @pytest.mark.asyncio
    async def test_get_queue_length_without_connection_raises(self):
        """Test get_queue_length without connection raises RuntimeError."""
        queue = RedisTaskQueue()

        with pytest.raises(RuntimeError, match="Redis client not connected"):
            await queue.get_queue_length()


class TestRedisTaskQueueGetAgentTasks:
    """Tests for get_agent_tasks method."""

    @pytest.fixture
    def connected_queue(self):
        """Create a connected queue with mock client."""
        queue = RedisTaskQueue()
        queue.client = AsyncMock()
        return queue

    @pytest.mark.asyncio
    async def test_get_agent_tasks_success(self, connected_queue):
        """Test getting tasks for an agent."""
        task_id_1 = str(uuid4())
        task_id_2 = str(uuid4())

        # Mock hscan_iter to yield task assignments
        async def mock_hscan_iter(*args):
            yield (task_id_1, "agent-1")
            yield (task_id_2, "agent-2")

        connected_queue.client.hscan_iter = mock_hscan_iter

        result = await connected_queue.get_agent_tasks("agent-1")

        assert len(result) == 1
        assert task_id_1 in result

    @pytest.mark.asyncio
    async def test_get_agent_tasks_empty(self, connected_queue):
        """Test getting tasks when agent has none."""
        async def mock_hscan_iter(*args):
            yield (str(uuid4()), "other-agent")

        connected_queue.client.hscan_iter = mock_hscan_iter

        result = await connected_queue.get_agent_tasks("agent-1")

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_agent_tasks_without_connection_raises(self):
        """Test get_agent_tasks without connection raises RuntimeError."""
        queue = RedisTaskQueue()

        with pytest.raises(RuntimeError, match="Redis client not connected"):
            await queue.get_agent_tasks("agent-1")


class TestRedisTaskQueueRequeueTask:
    """Tests for requeue_task method."""

    @pytest.fixture
    def connected_queue(self):
        """Create a connected queue with mock client."""
        queue = RedisTaskQueue()
        queue.client = AsyncMock()
        return queue

    @pytest.mark.asyncio
    async def test_requeue_task_success(self, connected_queue):
        """Test requeuing a task with default role."""
        task_id = uuid4()

        await connected_queue.requeue_task(task_id, priority=5)

        # Verify removed from in_progress
        connected_queue.client.hdel.assert_called_once()
        # Verify added back to pending with priority
        connected_queue.client.zadd.assert_called_once()
        call_args = connected_queue.client.zadd.call_args
        # Verify default is WORKER
        assert call_args[0][0] == "iccc:tasks:pending:worker"

    @pytest.mark.asyncio
    async def test_requeue_task_with_role(self, connected_queue):
        """Test requeuing a task with explicit role."""
        task_id = uuid4()

        await connected_queue.requeue_task(task_id, priority=5, role=RoleType.MANAGER)

        call_args = connected_queue.client.zadd.call_args
        assert call_args[0][0] == "iccc:tasks:pending:manager"

    @pytest.mark.asyncio
    async def test_requeue_task_without_connection_raises(self):
        """Test requeue_task without connection raises RuntimeError."""
        queue = RedisTaskQueue()

        with pytest.raises(RuntimeError, match="Redis client not connected"):
            await queue.requeue_task(uuid4())


class TestRedisTaskQueueCleanupStaleTasks:
    """Tests for cleanup_stale_tasks method."""

    @pytest.fixture
    def connected_queue(self):
        """Create a connected queue with mock client."""
        queue = RedisTaskQueue()
        queue.client = AsyncMock()
        return queue

    @pytest.mark.asyncio
    async def test_cleanup_stale_tasks_returns_zero(self, connected_queue):
        """Test cleanup_stale_tasks returns 0 (not implemented)."""
        result = await connected_queue.cleanup_stale_tasks()
        assert result == 0

    @pytest.mark.asyncio
    async def test_cleanup_stale_tasks_without_connection_raises(self):
        """Test cleanup_stale_tasks without connection raises RuntimeError."""
        queue = RedisTaskQueue()

        with pytest.raises(RuntimeError, match="Redis client not connected"):
            await queue.cleanup_stale_tasks()
