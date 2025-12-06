"""Tests for Redis-based file locking system."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis.asyncio as redis

from iccc.locks.file_lock import FileLockManager, LockType


@pytest.fixture
async def mock_redis():
    """Create a mock Redis client for testing."""
    mock_client = AsyncMock(spec=redis.Redis)

    # Mock basic Redis operations
    mock_client.exists = AsyncMock(return_value=0)
    mock_client.sadd = AsyncMock(return_value=1)
    mock_client.expire = AsyncMock(return_value=True)
    mock_client.srem = AsyncMock(return_value=1)
    mock_client.scard = AsyncMock(return_value=0)
    mock_client.delete = AsyncMock(return_value=1)
    mock_client.get = AsyncMock(return_value=None)
    mock_client.eval = AsyncMock(return_value=1)
    mock_client.smembers = AsyncMock(return_value=set())
    mock_client.ttl = AsyncMock(return_value=-1)

    # scan_iter needs to return an async iterator directly, not wrapped in AsyncMock
    def create_scan_iter(match=None):
        return AsyncIteratorMock([])

    mock_client.scan_iter = MagicMock(side_effect=create_scan_iter)

    return mock_client


class AsyncIteratorMock:
    """Mock async iterator for Redis scan_iter."""

    def __init__(self, items):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item


@pytest.mark.asyncio
async def test_acquire_read_lock_success(mock_redis):
    """Test successfully acquiring a read lock."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # No write lock exists
    mock_redis.exists.return_value = 0

    success = await lock_manager.acquire_read_lock("/test.py", "agent-1")

    assert success is True
    mock_redis.sadd.assert_called_once()
    mock_redis.expire.assert_called_once()


@pytest.mark.asyncio
async def test_acquire_read_lock_blocked_by_write(mock_redis):
    """Test read lock blocked when write lock exists."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # Write lock exists
    mock_redis.exists.return_value = 1

    success = await lock_manager.acquire_read_lock("/test.py", "agent-1")

    assert success is False
    mock_redis.sadd.assert_not_called()


@pytest.mark.asyncio
async def test_acquire_write_lock_success(mock_redis):
    """Test successfully acquiring a write lock."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # Lua script returns 1 (success)
    mock_redis.eval.return_value = 1

    success = await lock_manager.acquire_write_lock("/test.py", "agent-1")

    assert success is True
    mock_redis.eval.assert_called_once()


@pytest.mark.asyncio
async def test_acquire_write_lock_blocked_by_read(mock_redis):
    """Test write lock blocked when read lock exists."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # Lua script returns 0 (blocked)
    mock_redis.eval.return_value = 0

    success = await lock_manager.acquire_write_lock("/test.py", "agent-1")

    assert success is False


@pytest.mark.asyncio
async def test_acquire_write_lock_blocked_by_write(mock_redis):
    """Test write lock blocked when another write lock exists."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # Lua script returns 0 (another write lock exists)
    mock_redis.eval.return_value = 0

    success = await lock_manager.acquire_write_lock("/test.py", "agent-2")

    assert success is False


@pytest.mark.asyncio
async def test_release_read_lock(mock_redis):
    """Test releasing a read lock."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # After removal, no more readers
    mock_redis.scard.return_value = 0

    await lock_manager.release_read_lock("/test.py", "agent-1")

    mock_redis.srem.assert_called_once()
    mock_redis.delete.assert_called_once()


@pytest.mark.asyncio
async def test_release_read_lock_with_other_readers(mock_redis):
    """Test releasing a read lock when other readers exist."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # Still have other readers
    mock_redis.scard.return_value = 2

    await lock_manager.release_read_lock("/test.py", "agent-1")

    mock_redis.srem.assert_called_once()
    mock_redis.delete.assert_not_called()


@pytest.mark.asyncio
async def test_release_write_lock(mock_redis):
    """Test releasing a write lock."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # Agent owns the lock
    mock_redis.get.return_value = "agent-1"

    await lock_manager.release_write_lock("/test.py", "agent-1")

    mock_redis.delete.assert_called_once()


@pytest.mark.asyncio
async def test_release_write_lock_not_owner(mock_redis):
    """Test releasing a write lock when not the owner."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # Different agent owns the lock
    mock_redis.get.return_value = "agent-2"

    await lock_manager.release_write_lock("/test.py", "agent-1")

    # Should not delete if not owner
    mock_redis.delete.assert_not_called()


@pytest.mark.asyncio
async def test_lock_context_manager_write_success(mock_redis):
    """Test write lock context manager with successful acquisition."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # Successful write lock acquisition
    mock_redis.eval.return_value = 1
    mock_redis.get.return_value = "agent-1"

    async with lock_manager.lock("/test.py", "agent-1", LockType.WRITE) as acquired:
        assert acquired is True

    # Should have released the lock
    mock_redis.delete.assert_called_once()


@pytest.mark.asyncio
async def test_lock_context_manager_read_success(mock_redis):
    """Test read lock context manager with successful acquisition."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # Successful read lock acquisition
    mock_redis.exists.return_value = 0
    mock_redis.scard.return_value = 0

    async with lock_manager.lock("/test.py", "agent-1", LockType.READ) as acquired:
        assert acquired is True

    # Should have released the lock
    mock_redis.delete.assert_called_once()


@pytest.mark.asyncio
async def test_lock_context_manager_with_retry(mock_redis):
    """Test lock context manager retries once."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # First attempt fails, second succeeds
    mock_redis.eval.side_effect = [0, 1]
    mock_redis.get.return_value = "agent-1"

    async with lock_manager.lock("/test.py", "agent-1", LockType.WRITE) as acquired:
        assert acquired is True


@pytest.mark.asyncio
async def test_lock_context_manager_both_attempts_fail(mock_redis):
    """Test lock context manager when both attempts fail."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # Both attempts fail
    mock_redis.eval.return_value = 0

    async with lock_manager.lock("/test.py", "agent-1", LockType.WRITE) as acquired:
        assert acquired is False

    # Should not try to release since lock wasn't acquired
    mock_redis.delete.assert_not_called()


@pytest.mark.asyncio
async def test_check_lock_owner(mock_redis):
    """Test checking lock owner."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    mock_redis.get.return_value = "agent-1"

    owner = await lock_manager.check_lock_owner("/test.py")

    assert owner == "agent-1"


@pytest.mark.asyncio
async def test_check_lock_owner_no_lock(mock_redis):
    """Test checking lock owner when no lock exists."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    mock_redis.get.return_value = None

    owner = await lock_manager.check_lock_owner("/test.py")

    assert owner is None


@pytest.mark.asyncio
async def test_detect_deadlocks_none(mock_redis):
    """Test deadlock detection when no deadlocks exist."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # No locks - already set in fixture
    deadlocks = await lock_manager.detect_deadlocks()

    assert len(deadlocks) == 0


@pytest.mark.asyncio
async def test_detect_deadlocks_found(mock_redis):
    """Test deadlock detection when deadlocks exist."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # Lock with low TTL
    lock_key = "iccc:lock:/test.py:writer"
    mock_redis.scan_iter = MagicMock(return_value=AsyncIteratorMock([lock_key]))
    mock_redis.ttl.return_value = 3  # 3 seconds left
    mock_redis.get.return_value = "agent-1"

    deadlocks = await lock_manager.detect_deadlocks()

    assert len(deadlocks) == 1
    assert deadlocks[0]["file_path"] == "/test.py"
    assert deadlocks[0]["owner"] == "agent-1"
    assert deadlocks[0]["ttl_seconds"] == 3


@pytest.mark.asyncio
async def test_detect_deadlocks_ignores_healthy_locks(mock_redis):
    """Test deadlock detection ignores locks with healthy TTL."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # Lock with healthy TTL
    lock_key = "iccc:lock:/test.py:writer"
    mock_redis.scan_iter = MagicMock(return_value=AsyncIteratorMock([lock_key]))
    mock_redis.ttl.return_value = 25  # 25 seconds left (healthy)
    mock_redis.get.return_value = "agent-1"

    deadlocks = await lock_manager.detect_deadlocks()

    # Should not be flagged as deadlock
    assert len(deadlocks) == 0


@pytest.mark.asyncio
async def test_force_release(mock_redis):
    """Test force releasing a lock."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # Both locks deleted
    mock_redis.delete.side_effect = [1, 1]

    result = await lock_manager.force_release("/test.py")

    assert result is True
    assert mock_redis.delete.call_count == 2


@pytest.mark.asyncio
async def test_force_release_no_locks(mock_redis):
    """Test force releasing when no locks exist."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # No locks deleted
    mock_redis.delete.side_effect = [0, 0]

    result = await lock_manager.force_release("/test.py")

    assert result is False


@pytest.mark.asyncio
async def test_get_lock_status_unlocked(mock_redis):
    """Test getting lock status for unlocked file."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    mock_redis.get.return_value = None
    mock_redis.smembers.return_value = set()

    status = await lock_manager.get_lock_status("/test.py")

    assert status["file_path"] == "/test.py"
    assert status["write_lock"] is None
    assert status["read_locks"] == []
    assert status["is_locked"] is False


@pytest.mark.asyncio
async def test_get_lock_status_write_locked(mock_redis):
    """Test getting lock status for write-locked file."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    mock_redis.get.return_value = "agent-1"
    mock_redis.smembers.return_value = set()

    status = await lock_manager.get_lock_status("/test.py")

    assert status["file_path"] == "/test.py"
    assert status["write_lock"] == "agent-1"
    assert status["read_locks"] == []
    assert status["is_locked"] is True


@pytest.mark.asyncio
async def test_get_lock_status_read_locked(mock_redis):
    """Test getting lock status for read-locked file."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    mock_redis.get.return_value = None
    mock_redis.smembers.return_value = {"agent-1", "agent-2"}

    status = await lock_manager.get_lock_status("/test.py")

    assert status["file_path"] == "/test.py"
    assert status["write_lock"] is None
    assert set(status["read_locks"]) == {"agent-1", "agent-2"}
    assert status["is_locked"] is True


@pytest.mark.asyncio
async def test_concurrent_read_locks(mock_redis):
    """Test multiple agents can hold read locks simultaneously."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # No write lock exists
    mock_redis.exists.return_value = 0

    # Both agents should acquire read lock
    success1 = await lock_manager.acquire_read_lock("/test.py", "agent-1")
    success2 = await lock_manager.acquire_read_lock("/test.py", "agent-2")

    assert success1 is True
    assert success2 is True
    assert mock_redis.sadd.call_count == 2


@pytest.mark.asyncio
async def test_write_lock_prevents_read_lock(mock_redis):
    """Test that write lock prevents read locks."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # Write lock exists
    mock_redis.exists.return_value = 1

    success = await lock_manager.acquire_read_lock("/test.py", "agent-2")

    assert success is False


@pytest.mark.asyncio
async def test_read_lock_prevents_write_lock(mock_redis):
    """Test that read locks prevent write lock."""
    lock_manager = FileLockManager()
    lock_manager.client = mock_redis

    # Read lock exists (Lua script returns 0)
    mock_redis.eval.return_value = 0

    success = await lock_manager.acquire_write_lock("/test.py", "agent-2")

    assert success is False
