"""Pytest configuration and fixtures."""

import os
from uuid import uuid4

import pytest


@pytest.fixture(scope="session")
def test_mongodb_url():
    """MongoDB URL for testing."""
    return os.getenv("MONGODB_URL", "mongodb://iccc:test_password@localhost:27017/iccc_test")


@pytest.fixture(scope="session")
def test_redis_url():
    """Redis URL for testing."""
    return os.getenv("REDIS_URL", "redis://localhost:6379/1")


@pytest.fixture
def project_id():
    """Generate a test project ID."""
    return uuid4()


@pytest.fixture
def agent_id():
    """Generate a test agent ID."""
    return f"agent-test-{uuid4().hex[:8]}"


@pytest.fixture
async def redis_client():
    """Create a mock Redis client for testing."""
    from unittest.mock import AsyncMock
    import redis.asyncio as redis

    mock_client = AsyncMock(spec=redis.Redis)

    # Storage for task queue testing
    task_store = {}
    task_queue = []

    async def mock_set(key, value):
        task_store[key] = value
        return True

    async def mock_get(key):
        return task_store.get(key)

    async def mock_zadd(key, mapping):
        for task_id, score in mapping.items():
            task_queue.append((task_id, score))
        return len(mapping)

    async def mock_zpopmax(key):
        if not task_queue:
            return None
        # Sort by score (priority) and pop the highest
        task_queue.sort(key=lambda x: x[1])
        task_id, score = task_queue.pop(0)
        return [(task_id, score)]

    # Mock Redis operations
    mock_client.set = AsyncMock(side_effect=mock_set)
    mock_client.get = AsyncMock(side_effect=mock_get)
    mock_client.zadd = AsyncMock(side_effect=mock_zadd)
    mock_client.zpopmax = AsyncMock(side_effect=mock_zpopmax)
    mock_client.hset = AsyncMock(return_value=1)
    mock_client.delete = AsyncMock(return_value=1)
    mock_client.zrem = AsyncMock(return_value=1)
    mock_client.zcard = AsyncMock(return_value=0)

    return mock_client
