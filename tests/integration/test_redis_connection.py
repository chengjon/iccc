"""Integration tests for Redis connection using remote configuration."""

import os

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from iccc.config import load_config


@pytest.fixture
def config():
    """Load configuration from environment."""
    return load_config()


@pytest.mark.asyncio
@pytest.mark.integration
class TestRedisIntegration:
    """Integration tests for Redis with remote configuration."""

    async def test_redis_connection(self, config):
        """Test basic Redis connection."""
        redis_client = Redis(
            host=config.redis.host,
            port=config.redis.port,
            db=config.redis.db,
            password=config.redis.password if config.redis.password else None,
            decode_responses=True,
        )

        try:
            # Test connection
            result = await redis_client.ping()
            assert result is True

            # Close connection
            await redis_client.aclose()

        except RedisConnectionError:
            pytest.skip(
                f"Redis not accessible at {config.redis.host}:{config.redis.port}"
            )

    async def test_redis_set_and_get(self, config):
        """Test Redis set and get operations."""
        redis_client = Redis(
            host=config.redis.host,
            port=config.redis.port,
            db=config.redis.db,
            password=config.redis.password if config.redis.password else None,
            decode_responses=True,
        )

        try:
            # Set a value
            test_key = "iccc:test:integration"
            test_value = "integration_test_value"

            await redis_client.set(test_key, test_value, ex=60)

            # Get the value
            result = await redis_client.get(test_key)
            assert result == test_value

            # Clean up
            await redis_client.delete(test_key)

            # Verify deletion
            result = await redis_client.get(test_key)
            assert result is None

            await redis_client.aclose()

        except RedisConnectionError:
            pytest.skip(
                f"Redis not accessible at {config.redis.host}:{config.redis.port}"
            )

    async def test_redis_database_isolation(self, config):
        """Test that different Redis databases are isolated."""
        # Connect to configured DB
        redis_db = Redis(
            host=config.redis.host,
            port=config.redis.port,
            db=config.redis.db,
            password=config.redis.password if config.redis.password else None,
            decode_responses=True,
        )

        # Connect to a different DB (if not already at max)
        other_db_num = (config.redis.db + 1) % 16
        redis_other = Redis(
            host=config.redis.host,
            port=config.redis.port,
            db=other_db_num,
            password=config.redis.password if config.redis.password else None,
            decode_responses=True,
        )

        try:
            test_key = "iccc:test:isolation"
            test_value = "isolated_value"

            # Set in configured DB
            await redis_db.set(test_key, test_value, ex=60)

            # Should exist in configured DB
            result = await redis_db.get(test_key)
            assert result == test_value

            # Should NOT exist in other DB
            result = await redis_other.get(test_key)
            assert result is None

            # Clean up
            await redis_db.delete(test_key)

            await redis_db.aclose()
            await redis_other.aclose()

        except RedisConnectionError:
            pytest.skip(
                f"Redis not accessible at {config.redis.host}:{config.redis.port}"
            )

    async def test_redis_expiration(self, config):
        """Test Redis key expiration."""
        import asyncio

        redis_client = Redis(
            host=config.redis.host,
            port=config.redis.port,
            db=config.redis.db,
            password=config.redis.password if config.redis.password else None,
            decode_responses=True,
        )

        try:
            test_key = "iccc:test:expiration"
            test_value = "expires_soon"

            # Set with 2 second expiration
            await redis_client.set(test_key, test_value, ex=2)

            # Should exist immediately
            result = await redis_client.get(test_key)
            assert result == test_value

            # Wait for expiration
            await asyncio.sleep(3)

            # Should be expired
            result = await redis_client.get(test_key)
            assert result is None

            await redis_client.aclose()

        except RedisConnectionError:
            pytest.skip(
                f"Redis not accessible at {config.redis.host}:{config.redis.port}"
            )

    async def test_redis_list_operations(self, config):
        """Test Redis list operations."""
        redis_client = Redis(
            host=config.redis.host,
            port=config.redis.port,
            db=config.redis.db,
            password=config.redis.password if config.redis.password else None,
            decode_responses=True,
        )

        try:
            test_key = "iccc:test:list"

            # Push items
            await redis_client.rpush(test_key, "item1", "item2", "item3")

            # Get list length
            length = await redis_client.llen(test_key)
            assert length == 3

            # Get all items
            items = await redis_client.lrange(test_key, 0, -1)
            assert items == ["item1", "item2", "item3"]

            # Pop item
            item = await redis_client.lpop(test_key)
            assert item == "item1"

            # Clean up
            await redis_client.delete(test_key)

            await redis_client.aclose()

        except RedisConnectionError:
            pytest.skip(
                f"Redis not accessible at {config.redis.host}:{config.redis.port}"
            )

    async def test_redis_hash_operations(self, config):
        """Test Redis hash operations."""
        redis_client = Redis(
            host=config.redis.host,
            port=config.redis.port,
            db=config.redis.db,
            password=config.redis.password if config.redis.password else None,
            decode_responses=True,
        )

        try:
            test_key = "iccc:test:hash"

            # Set hash fields
            await redis_client.hset(
                test_key,
                mapping={"field1": "value1", "field2": "value2", "field3": "value3"},
            )

            # Get single field
            value = await redis_client.hget(test_key, "field1")
            assert value == "value1"

            # Get all fields
            all_fields = await redis_client.hgetall(test_key)
            assert all_fields == {
                "field1": "value1",
                "field2": "value2",
                "field3": "value3",
            }

            # Delete field
            await redis_client.hdel(test_key, "field2")

            # Verify deletion
            value = await redis_client.hget(test_key, "field2")
            assert value is None

            # Clean up
            await redis_client.delete(test_key)

            await redis_client.aclose()

        except RedisConnectionError:
            pytest.skip(
                f"Redis not accessible at {config.redis.host}:{config.redis.port}"
            )


@pytest.mark.integration
class TestRedisConfiguration:
    """Test Redis configuration loading."""

    def test_redis_config_from_env(self):
        """Test that Redis configuration is loaded from environment variables."""
        config = load_config()

        # Check that Redis config is loaded
        assert config.redis is not None

        # Verify it matches environment variables
        expected_host = os.getenv("REDIS_HOST", "localhost")
        expected_port = int(os.getenv("REDIS_PORT", "6379"))
        expected_db = int(os.getenv("REDIS_DB", "0"))

        assert config.redis.host == expected_host
        assert config.redis.port == expected_port
        assert config.redis.db == expected_db

    def test_redis_password_handling(self):
        """Test that empty Redis password is handled correctly."""
        config = load_config()

        # Empty password should be None or empty string
        password = config.redis.password
        assert password is None or password == ""
