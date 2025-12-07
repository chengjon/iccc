"""Tests for Redis-based rate limiting."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis.asyncio as redis

from iccc.api.rate_limiter import RateLimitResult, RedisRateLimiter


class TestRateLimitResult:
    """Test RateLimitResult class."""

    def test_result_initialization(self) -> None:
        """Test rate limit result initialization."""
        result = RateLimitResult(
            allowed=True,
            limit=100,
            remaining=50,
            reset_timestamp=time.time() + 60,
        )

        assert result.allowed is True
        assert result.limit == 100
        assert result.remaining == 50
        assert result.reset_timestamp > time.time()

    def test_reset_after_seconds(self) -> None:
        """Test reset_after_seconds calculation."""
        future_time = time.time() + 30
        result = RateLimitResult(
            allowed=True,
            limit=100,
            remaining=50,
            reset_timestamp=future_time,
        )

        # Should be approximately 30 seconds (allow small variance)
        assert 25 <= result.reset_after_seconds <= 35

    def test_reset_after_seconds_past(self) -> None:
        """Test reset_after_seconds returns 0 for past timestamps."""
        past_time = time.time() - 10
        result = RateLimitResult(
            allowed=True,
            limit=100,
            remaining=50,
            reset_timestamp=past_time,
        )

        assert result.reset_after_seconds == 0


class TestRedisRateLimiter:
    """Test RedisRateLimiter class."""

    @pytest.fixture
    async def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        mock_client = AsyncMock(spec=redis.Redis)
        mock_client.pipeline = MagicMock(return_value=AsyncMock())
        return mock_client

    @pytest.fixture
    async def rate_limiter(self, mock_redis: AsyncMock) -> RedisRateLimiter:
        """Create rate limiter with mock Redis client."""
        limiter = RedisRateLimiter(
            redis_client=mock_redis,
            requests_per_window=10,
            window_seconds=60,
        )
        limiter._connected = True
        return limiter

    def test_initialization(self) -> None:
        """Test rate limiter initialization."""
        limiter = RedisRateLimiter(
            requests_per_window=100,
            window_seconds=60,
            key_prefix="test",
        )

        assert limiter.requests_per_window == 100
        assert limiter.window_seconds == 60
        assert limiter.key_prefix == "test"

    def test_build_redis_url_from_config(self) -> None:
        """Test Redis URL building from config."""
        with patch("iccc.api.rate_limiter.get_config") as mock_config:
            mock_config.return_value.redis.host = "testhost"
            mock_config.return_value.redis.port = 6379
            mock_config.return_value.redis.db = 1
            mock_config.return_value.redis.password = None

            limiter = RedisRateLimiter()
            assert limiter.redis_url == "redis://testhost:6379/1"

    def test_build_redis_url_with_password(self) -> None:
        """Test Redis URL building with password."""
        with patch("iccc.api.rate_limiter.get_config") as mock_config:
            mock_config.return_value.redis.host = "testhost"
            mock_config.return_value.redis.port = 6379
            mock_config.return_value.redis.db = 1
            mock_config.return_value.redis.password = "secret"

            limiter = RedisRateLimiter()
            assert limiter.redis_url == "redis://:secret@testhost:6379/1"

    async def test_connect(self) -> None:
        """Test Redis connection establishment."""
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_client = AsyncMock()
            mock_from_url.return_value = mock_client

            limiter = RedisRateLimiter(redis_url="redis://localhost:6379/0")
            await limiter.connect()

            assert limiter.client == mock_client
            assert limiter._connected is True
            mock_from_url.assert_called_once()

    async def test_disconnect(self, rate_limiter: RedisRateLimiter) -> None:
        """Test Redis disconnection."""
        # Make close async
        rate_limiter.client.close = AsyncMock()
        await rate_limiter.disconnect()
        rate_limiter.client.close.assert_called_once()
        assert rate_limiter._connected is False

    async def test_check_rate_limit_allowed(
        self, rate_limiter: RedisRateLimiter
    ) -> None:
        """Test rate limit check when request is allowed."""
        # Mock pipeline execution
        mock_pipeline = rate_limiter.client.pipeline.return_value
        # Results: [zremrangebyscore, zcard, zadd, expire]
        mock_pipeline.execute.return_value = [0, 5, 1, True]

        result = await rate_limiter.check_rate_limit("test_key", increment=True)

        assert result.allowed is True
        assert result.limit == 10
        assert result.remaining == 4  # 10 - (5 + 1)
        assert result.reset_timestamp > time.time()

        # Verify Redis operations
        mock_pipeline.zremrangebyscore.assert_called_once()
        mock_pipeline.zcard.assert_called_once()
        mock_pipeline.zadd.assert_called_once()
        mock_pipeline.expire.assert_called_once()

    async def test_check_rate_limit_exceeded(
        self, rate_limiter: RedisRateLimiter
    ) -> None:
        """Test rate limit check when limit is exceeded."""
        # Mock pipeline execution - 10 existing requests
        mock_pipeline = rate_limiter.client.pipeline.return_value
        mock_pipeline.execute.return_value = [0, 10, 1, True]

        result = await rate_limiter.check_rate_limit("test_key", increment=True)

        assert result.allowed is False
        assert result.limit == 10
        assert result.remaining == 0
        assert result.reset_timestamp > time.time()

    async def test_check_rate_limit_no_increment(
        self, rate_limiter: RedisRateLimiter
    ) -> None:
        """Test rate limit check without incrementing counter."""
        # Mock pipeline execution
        mock_pipeline = rate_limiter.client.pipeline.return_value
        mock_pipeline.execute.return_value = [0, 3, 0, True]

        result = await rate_limiter.check_rate_limit("test_key", increment=False)

        assert result.allowed is True
        assert result.remaining == 7  # 10 - 3
        # Should not call zadd when increment=False
        mock_pipeline.zadd.assert_not_called()

    async def test_check_rate_limit_redis_error(
        self, rate_limiter: RedisRateLimiter
    ) -> None:
        """Test graceful handling of Redis errors (fail open)."""
        # Mock Redis error
        rate_limiter.client.pipeline.side_effect = redis.RedisError("Connection failed")

        result = await rate_limiter.check_rate_limit("test_key", increment=True)

        # Should fail open (allow request)
        assert result.allowed is True
        assert result.limit == 10
        assert result.remaining == 10

    async def test_check_rate_limit_not_connected(self) -> None:
        """Test error when client is not connected."""
        limiter = RedisRateLimiter()

        with pytest.raises(RuntimeError, match="Redis client not connected"):
            await limiter.check_rate_limit("test_key")

    async def test_get_remaining(self, rate_limiter: RedisRateLimiter) -> None:
        """Test getting remaining requests without incrementing."""
        # Mock pipeline execution
        mock_pipeline = rate_limiter.client.pipeline.return_value
        mock_pipeline.execute.return_value = [0, 4, 0, True]

        remaining, reset_after = await rate_limiter.get_remaining("test_key")

        assert remaining == 6  # 10 - 4
        assert reset_after >= 0

    async def test_reset_limit(self, rate_limiter: RedisRateLimiter) -> None:
        """Test resetting rate limit for a key."""
        rate_limiter.client.delete = AsyncMock()
        await rate_limiter.reset_limit("test_key")

        rate_limiter.client.delete.assert_called_once_with("ratelimit:test_key")

    async def test_reset_limit_redis_error(
        self, rate_limiter: RedisRateLimiter
    ) -> None:
        """Test reset limit with Redis error."""
        rate_limiter.client.delete.side_effect = redis.RedisError("Delete failed")

        with pytest.raises(redis.RedisError):
            await rate_limiter.reset_limit("test_key")

    async def test_clear_all(self, rate_limiter: RedisRateLimiter) -> None:
        """Test clearing all rate limit keys."""
        # Mock scan_iter to return some keys
        async def mock_scan_iter(match: str):
            for key in [b"ratelimit:key1", b"ratelimit:key2"]:
                yield key

        rate_limiter.client.scan_iter = mock_scan_iter
        rate_limiter.client.delete = AsyncMock(return_value=2)

        deleted = await rate_limiter.clear_all()

        assert deleted == 2
        rate_limiter.client.delete.assert_called_once()

    async def test_clear_all_no_keys(self, rate_limiter: RedisRateLimiter) -> None:
        """Test clearing when no keys exist."""

        async def mock_scan_iter(match: str):
            return
            yield  # Make it a generator

        rate_limiter.client.scan_iter = mock_scan_iter

        deleted = await rate_limiter.clear_all()

        assert deleted == 0
        rate_limiter.client.delete.assert_not_called()

    async def test_sliding_window_accuracy(
        self, rate_limiter: RedisRateLimiter
    ) -> None:
        """Test sliding window maintains accurate count over time."""
        # Simulate requests over time
        current = time.time()

        # Mock pipeline for multiple requests
        mock_pipeline = rate_limiter.client.pipeline.return_value

        # First request: 0 existing
        mock_pipeline.execute.return_value = [0, 0, 1, True]
        result1 = await rate_limiter.check_rate_limit("test_key")
        assert result1.allowed is True
        assert result1.remaining == 9

        # Second request: 1 existing
        mock_pipeline.execute.return_value = [0, 1, 1, True]
        result2 = await rate_limiter.check_rate_limit("test_key")
        assert result2.allowed is True
        assert result2.remaining == 8

        # Tenth request: 9 existing
        mock_pipeline.execute.return_value = [0, 9, 1, True]
        result10 = await rate_limiter.check_rate_limit("test_key")
        assert result10.allowed is True
        assert result10.remaining == 0

        # Eleventh request: 10 existing (should be blocked)
        mock_pipeline.execute.return_value = [0, 10, 1, True]
        result11 = await rate_limiter.check_rate_limit("test_key")
        assert result11.allowed is False
        assert result11.remaining == 0

    async def test_multiple_keys_isolated(
        self, rate_limiter: RedisRateLimiter
    ) -> None:
        """Test that different keys have isolated rate limits."""
        mock_pipeline = rate_limiter.client.pipeline.return_value

        # Key 1: 5 requests
        mock_pipeline.execute.return_value = [0, 5, 1, True]
        result1 = await rate_limiter.check_rate_limit("key1")
        assert result1.remaining == 4

        # Key 2: 2 requests (independent)
        mock_pipeline.execute.return_value = [0, 2, 1, True]
        result2 = await rate_limiter.check_rate_limit("key2")
        assert result2.remaining == 7

        # Keys should have different limits
        assert result1.remaining != result2.remaining


class TestRateLimiterIntegration:
    """Integration tests with real Redis (requires Redis running)."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_redis_integration(self) -> None:
        """
        Test with real Redis instance.

        Skip if Redis is not available.
        """
        try:
            limiter = RedisRateLimiter(
                redis_url="redis://localhost:6379/15",  # Use test DB
                requests_per_window=5,
                window_seconds=2,
                key_prefix="test_ratelimit",
            )
            await limiter.connect()

            # Clear any existing test data
            await limiter.clear_all()

            test_key = "integration_test"

            # Make 5 requests (should all succeed)
            for i in range(5):
                result = await limiter.check_rate_limit(test_key)
                assert result.allowed is True, f"Request {i+1} should be allowed"
                assert result.remaining == 4 - i, f"Remaining should be {4-i}"

            # 6th request should be blocked
            result = await limiter.check_rate_limit(test_key)
            assert result.allowed is False, "Request 6 should be blocked"
            assert result.remaining == 0

            # Wait for window to expire
            await asyncio.sleep(2.5)

            # Should be able to make requests again
            result = await limiter.check_rate_limit(test_key)
            assert result.allowed is True, "Request after window should be allowed"

            # Cleanup
            await limiter.clear_all()
            await limiter.disconnect()

        except redis.ConnectionError:
            pytest.skip("Redis not available for integration test")
