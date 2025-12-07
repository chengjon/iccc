"""Redis-based rate limiting using sliding window algorithm."""

import logging
import time
from typing import Optional, Tuple

import redis.asyncio as redis

from iccc.config import get_config

logger = logging.getLogger(__name__)


class RateLimitResult:
    """Result of a rate limit check."""

    def __init__(
        self,
        allowed: bool,
        limit: int,
        remaining: int,
        reset_timestamp: float,
    ) -> None:
        """
        Initialize rate limit result.

        Args:
            allowed: Whether the request is allowed
            limit: Maximum requests allowed in the window
            remaining: Number of requests remaining in the window
            reset_timestamp: Unix timestamp when the window resets
        """
        self.allowed = allowed
        self.limit = limit
        self.remaining = remaining
        self.reset_timestamp = reset_timestamp

    @property
    def reset_after_seconds(self) -> int:
        """Calculate seconds until window reset."""
        return max(0, int(self.reset_timestamp - time.time()))


class RedisRateLimiter:
    """
    Redis-based rate limiter using sliding window algorithm.

    Uses Redis sorted sets to track request timestamps within a time window.
    Implements the sliding window algorithm for accurate rate limiting.
    """

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        redis_url: Optional[str] = None,
        requests_per_window: int = 100,
        window_seconds: int = 60,
        key_prefix: str = "ratelimit",
    ) -> None:
        """
        Initialize rate limiter.

        Args:
            redis_client: Existing Redis client (optional)
            redis_url: Redis URL for creating new client (optional)
            requests_per_window: Maximum requests allowed per window
            window_seconds: Time window duration in seconds
            key_prefix: Prefix for Redis keys
        """
        self.client = redis_client
        self.redis_url = redis_url or self._build_redis_url_from_config()
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.key_prefix = key_prefix
        self._connected = False

    def _build_redis_url_from_config(self) -> str:
        """Build Redis URL from configuration."""
        config = get_config().redis
        if config.password:
            return f"redis://:{config.password}@{config.host}:{config.port}/{config.db}"
        return f"redis://{config.host}:{config.port}/{config.db}"

    async def connect(self) -> None:
        """Establish Redis connection if not already connected."""
        if not self.client:
            self.client = await redis.from_url(
                self.redis_url,
                decode_responses=False,  # We need bytes for ZREMRANGEBYSCORE
                encoding="utf-8",
            )
        self._connected = True

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self.client and self._connected:
            await self.client.close()
            self._connected = False

    async def check_rate_limit(
        self, key: str, increment: bool = True
    ) -> RateLimitResult:
        """
        Check if a request is within rate limits.

        Args:
            key: Unique identifier for the rate limit bucket (e.g., API key, IP address)
            increment: Whether to increment the counter (set to False for read-only check)

        Returns:
            RateLimitResult with limit status and metadata

        Raises:
            RuntimeError: If Redis client is not connected
        """
        if not self.client:
            raise RuntimeError("Redis client not connected. Call connect() first.")

        current_time = time.time()
        window_start = current_time - self.window_seconds
        redis_key = f"{self.key_prefix}:{key}"

        try:
            # Use pipeline for atomic operations
            pipe = self.client.pipeline()

            # Remove requests older than the window
            pipe.zremrangebyscore(redis_key, 0, window_start)

            # Count requests in current window
            pipe.zcard(redis_key)

            # Add current request timestamp if incrementing
            if increment:
                pipe.zadd(redis_key, {str(current_time): current_time})

            # Set expiration to window duration (cleanup old keys)
            pipe.expire(redis_key, self.window_seconds)

            # Execute pipeline
            results = await pipe.execute()

            # Get count (index 1 in results)
            current_count = results[1]

            # If we incremented, the count includes the new request
            # If we didn't increment, the count is accurate as-is
            if increment:
                # Count after increment already includes the new request
                requests_used = current_count + 1  # +1 for the request we just added
            else:
                requests_used = current_count

            # Calculate remaining requests
            remaining = max(0, self.requests_per_window - requests_used)

            # Calculate reset timestamp (end of current window)
            reset_timestamp = current_time + self.window_seconds

            # Determine if request is allowed
            allowed = requests_used <= self.requests_per_window

            logger.debug(
                f"Rate limit check for key '{key}': "
                f"used={requests_used}/{self.requests_per_window}, "
                f"remaining={remaining}, allowed={allowed}"
            )

            return RateLimitResult(
                allowed=allowed,
                limit=self.requests_per_window,
                remaining=remaining,
                reset_timestamp=reset_timestamp,
            )

        except redis.RedisError as e:
            logger.error(
                f"Redis error during rate limit check for key '{key}': {e}",
                exc_info=True,
            )
            # Fail open: allow request but log the error
            logger.warning(
                f"Rate limiting disabled due to Redis error - allowing request for key '{key}'"
            )
            return RateLimitResult(
                allowed=True,
                limit=self.requests_per_window,
                remaining=self.requests_per_window,
                reset_timestamp=current_time + self.window_seconds,
            )

    async def get_remaining(self, key: str) -> Tuple[int, int]:
        """
        Get remaining requests without incrementing counter.

        Args:
            key: Unique identifier for the rate limit bucket

        Returns:
            Tuple of (remaining_requests, seconds_until_reset)
        """
        result = await self.check_rate_limit(key, increment=False)
        return result.remaining, result.reset_after_seconds

    async def reset_limit(self, key: str) -> None:
        """
        Reset rate limit for a specific key.

        Args:
            key: Unique identifier for the rate limit bucket
        """
        if not self.client:
            raise RuntimeError("Redis client not connected. Call connect() first.")

        redis_key = f"{self.key_prefix}:{key}"
        try:
            await self.client.delete(redis_key)
            logger.info(f"Rate limit reset for key '{key}'")
        except redis.RedisError as e:
            logger.error(f"Failed to reset rate limit for key '{key}': {e}")
            raise

    async def clear_all(self) -> int:
        """
        Clear all rate limit keys.

        Returns:
            Number of keys deleted

        Warning:
            This will delete ALL rate limit data. Use with caution.
        """
        if not self.client:
            raise RuntimeError("Redis client not connected. Call connect() first.")

        try:
            pattern = f"{self.key_prefix}:*"
            keys = []
            async for key in self.client.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                deleted = await self.client.delete(*keys)
                logger.warning(f"Cleared {deleted} rate limit keys")
                return deleted
            return 0
        except redis.RedisError as e:
            logger.error(f"Failed to clear rate limit keys: {e}")
            raise
