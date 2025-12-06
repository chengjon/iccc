"""Rate limiting for Claude API with token bucket algorithm."""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

from redis.asyncio import Redis

from iccc.models.entities import ModelTier
from iccc.errors.exceptions import RateLimitError

logger = logging.getLogger(__name__)


@dataclass
class ModelLimits:
    """Rate limits for a specific model tier."""

    requests_per_minute: int
    tokens_per_minute: int
    tokens_per_day: int


# Claude API rate limits (as of 2025-12)
# https://docs.anthropic.com/en/api/rate-limits
MODEL_RATE_LIMITS = {
    ModelTier.HAIKU: ModelLimits(
        requests_per_minute=50,
        tokens_per_minute=50_000,
        tokens_per_day=5_000_000,
    ),
    ModelTier.SONNET: ModelLimits(
        requests_per_minute=50,
        tokens_per_minute=40_000,
        tokens_per_day=5_000_000,
    ),
    ModelTier.OPUS: ModelLimits(
        requests_per_minute=10,
        tokens_per_minute=10_000,
        tokens_per_day=1_000_000,
    ),
}


class TokenBucket:
    """Token bucket algorithm for rate limiting."""

    def __init__(
        self, capacity: int, refill_rate: float, redis_client: Optional[Redis] = None
    ) -> None:
        """
        Initialize token bucket.

        Args:
            capacity: Maximum tokens in bucket
            refill_rate: Tokens added per second
            redis_client: Optional Redis client for distributed rate limiting
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.redis_client = redis_client

        # Local state (fallback if Redis unavailable)
        self._tokens = float(capacity)
        self._last_refill = time.time()
        self._lock = asyncio.Lock()

    async def consume(self, tokens: int, timeout: float = 30.0) -> bool:
        """
        Attempt to consume tokens from bucket.

        Args:
            tokens: Number of tokens to consume
            timeout: Max time to wait for tokens (seconds)

        Returns:
            True if tokens consumed, False if timeout

        Raises:
            RateLimitError: If rate limit exceeded and can't wait
        """
        if self.redis_client:
            return await self._consume_redis(tokens, timeout)
        return await self._consume_local(tokens, timeout)

    async def _consume_local(self, tokens: int, timeout: float) -> bool:
        """Local (in-memory) token consumption."""
        start_time = time.time()

        async with self._lock:
            while True:
                # Refill tokens
                now = time.time()
                elapsed = now - self._last_refill
                refill_amount = elapsed * self.refill_rate
                self._tokens = min(self.capacity, self._tokens + refill_amount)
                self._last_refill = now

                # Check if we have enough tokens
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True

                # Check timeout
                if time.time() - start_time >= timeout:
                    wait_time = (tokens - self._tokens) / self.refill_rate
                    logger.warning(
                        f"Rate limit reached. Need {tokens} tokens, have {self._tokens:.2f}. "
                        f"Would need to wait {wait_time:.2f}s"
                    )
                    return False

                # Wait a bit and retry
                wait_time = min(1.0, (tokens - self._tokens) / self.refill_rate)
                await asyncio.sleep(wait_time)

    async def _consume_redis(self, tokens: int, timeout: float) -> bool:
        """Distributed token consumption using Redis."""
        assert self.redis_client is not None

        # Redis Lua script for atomic token bucket operation
        lua_script = """
        local key = KEYS[1]
        local capacity = tonumber(ARGV[1])
        local refill_rate = tonumber(ARGV[2])
        local tokens_needed = tonumber(ARGV[3])
        local now = tonumber(ARGV[4])

        -- Get current state
        local state = redis.call('HMGET', key, 'tokens', 'last_refill')
        local current_tokens = tonumber(state[1]) or capacity
        local last_refill = tonumber(state[2]) or now

        -- Refill tokens
        local elapsed = now - last_refill
        local refill_amount = elapsed * refill_rate
        current_tokens = math.min(capacity, current_tokens + refill_amount)

        -- Try to consume
        if current_tokens >= tokens_needed then
            current_tokens = current_tokens - tokens_needed
            redis.call('HMSET', key, 'tokens', current_tokens, 'last_refill', now)
            redis.call('EXPIRE', key, 3600)  -- 1 hour TTL
            return 1  -- Success
        else
            -- Update state even on failure (to track refills)
            redis.call('HMSET', key, 'tokens', current_tokens, 'last_refill', now)
            redis.call('EXPIRE', key, 3600)
            return 0  -- Not enough tokens
        end
        """

        start_time = time.time()
        key = f"iccc:ratelimit:bucket:{id(self)}"

        while True:
            now = time.time()
            result = await self.redis_client.eval(
                lua_script,
                1,
                key,
                str(self.capacity),
                str(self.refill_rate),
                str(tokens),
                str(now),
            )

            if result == 1:
                return True

            # Check timeout
            if time.time() - start_time >= timeout:
                logger.warning(f"Rate limit timeout after {timeout}s")
                return False

            # Wait and retry
            await asyncio.sleep(0.5)


class RateLimiter:
    """Rate limiter for Claude API with per-model limits."""

    def __init__(self, redis_client: Optional[Redis] = None) -> None:
        self.redis_client = redis_client
        self._buckets: dict[str, dict[str, TokenBucket]] = {}

        # Initialize buckets for each model
        for model, limits in MODEL_RATE_LIMITS.items():
            self._buckets[model.value] = {
                "requests": TokenBucket(
                    capacity=limits.requests_per_minute,
                    refill_rate=limits.requests_per_minute / 60.0,
                    redis_client=redis_client,
                ),
                "tokens_minute": TokenBucket(
                    capacity=limits.tokens_per_minute,
                    refill_rate=limits.tokens_per_minute / 60.0,
                    redis_client=redis_client,
                ),
                "tokens_day": TokenBucket(
                    capacity=limits.tokens_per_day,
                    refill_rate=limits.tokens_per_day / 86400.0,
                    redis_client=redis_client,
                ),
            }

    async def acquire(
        self,
        model: ModelTier,
        estimated_tokens: int = 1000,
        timeout: float = 30.0,
    ) -> None:
        """
        Acquire rate limit permission before API call.

        Args:
            model: Claude model to use
            estimated_tokens: Estimated token count for request
            timeout: Max time to wait for rate limit

        Raises:
            RateLimitError: If rate limit exceeded
        """
        buckets = self._buckets.get(model.value)
        if not buckets:
            logger.warning(f"No rate limits configured for {model.value}")
            return

        # Check request limit
        if not await buckets["requests"].consume(1, timeout):
            raise RateLimitError(
                service="anthropic",
                retry_after=60.0,
                quota_info={"model": model.value, "limit_type": "requests_per_minute"},
            )

        # Check minute token limit
        if not await buckets["tokens_minute"].consume(estimated_tokens, timeout):
            raise RateLimitError(
                service="anthropic",
                retry_after=60.0,
                quota_info={
                    "model": model.value,
                    "limit_type": "tokens_per_minute",
                    "estimated_tokens": estimated_tokens,
                },
            )

        # Check daily token limit
        if not await buckets["tokens_day"].consume(estimated_tokens, timeout):
            # Daily limit is more serious - longer retry time
            raise RateLimitError(
                service="anthropic",
                retry_after=3600.0,  # Wait 1 hour
                quota_info={
                    "model": model.value,
                    "limit_type": "tokens_per_day",
                    "estimated_tokens": estimated_tokens,
                },
            )

        logger.debug(
            f"Rate limit check passed for {model.value} ({estimated_tokens} tokens)"
        )

    async def get_quota_status(
        self, model: ModelTier
    ) -> dict[str, dict[str, float]]:
        """Get current quota status for a model."""
        buckets = self._buckets.get(model.value)
        if not buckets:
            return {}

        # This is approximate - would need to read from Redis for exact values
        status = {}
        for limit_type, bucket in buckets.items():
            if hasattr(bucket, "_tokens"):
                status[limit_type] = {
                    "available": bucket._tokens,
                    "capacity": bucket.capacity,
                    "refill_rate": bucket.refill_rate,
                    "utilization_pct": (
                        100 - (bucket._tokens / bucket.capacity * 100)
                    ),
                }

        return status


class AdaptiveRateLimiter(RateLimiter):
    """Rate limiter that adapts based on API responses."""

    def __init__(self, redis_client: Optional[Redis] = None) -> None:
        super().__init__(redis_client)
        self._backoff_until: dict[str, float] = {}

    async def acquire(
        self,
        model: ModelTier,
        estimated_tokens: int = 1000,
        timeout: float = 30.0,
    ) -> None:
        """Acquire with adaptive backoff."""
        # Check if we're in backoff period
        if model.value in self._backoff_until:
            backoff_until = self._backoff_until[model.value]
            now = time.time()
            if now < backoff_until:
                wait_time = backoff_until - now
                logger.info(f"Model {model.value} in backoff. Waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                del self._backoff_until[model.value]

        # Normal rate limit check
        await super().acquire(model, estimated_tokens, timeout)

    def record_rate_limit_hit(self, model: ModelTier, retry_after: float) -> None:
        """Record a rate limit hit from API response."""
        backoff_until = time.time() + retry_after
        self._backoff_until[model.value] = backoff_until
        logger.warning(
            f"Rate limit hit for {model.value}. Backing off for {retry_after}s"
        )

    def record_overloaded(self, model: ModelTier, retry_after: float = 60.0) -> None:
        """Record model overload."""
        backoff_until = time.time() + retry_after
        self._backoff_until[model.value] = backoff_until
        logger.warning(
            f"Model {model.value} overloaded. Backing off for {retry_after}s"
        )


# Global rate limiter instance
_rate_limiter: Optional[AdaptiveRateLimiter] = None


def get_rate_limiter(redis_client: Optional[Redis] = None) -> AdaptiveRateLimiter:
    """Get or create global rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = AdaptiveRateLimiter(redis_client)
    return _rate_limiter
