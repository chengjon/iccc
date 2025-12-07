"""Unit tests for rate limiter module."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from iccc.agents.rate_limiter import (
    MODEL_RATE_LIMITS,
    AdaptiveRateLimiter,
    ModelLimits,
    RateLimiter,
    TokenBucket,
    get_rate_limiter,
)
from iccc.errors.exceptions import RateLimitError
from iccc.models.entities import ModelTier


class TestModelLimits:
    """Tests for ModelLimits dataclass."""

    def test_model_limits_creation(self):
        """Test creating ModelLimits."""
        limits = ModelLimits(
            requests_per_minute=50,
            tokens_per_minute=40000,
            tokens_per_day=5000000,
        )
        assert limits.requests_per_minute == 50
        assert limits.tokens_per_minute == 40000
        assert limits.tokens_per_day == 5000000

    def test_model_rate_limits_contains_all_tiers(self):
        """Test that MODEL_RATE_LIMITS contains all model tiers."""
        assert ModelTier.HAIKU in MODEL_RATE_LIMITS
        assert ModelTier.SONNET in MODEL_RATE_LIMITS
        assert ModelTier.OPUS in MODEL_RATE_LIMITS

    def test_model_rate_limits_values(self):
        """Test MODEL_RATE_LIMITS values are reasonable."""
        for model, limits in MODEL_RATE_LIMITS.items():
            assert limits.requests_per_minute > 0
            assert limits.tokens_per_minute > 0
            assert limits.tokens_per_day > 0
            # Daily should be greater than per-minute
            assert limits.tokens_per_day > limits.tokens_per_minute


class TestTokenBucket:
    """Tests for TokenBucket class."""

    def test_init_local(self):
        """Test TokenBucket initialization without Redis."""
        bucket = TokenBucket(capacity=100, refill_rate=10.0)
        assert bucket.capacity == 100
        assert bucket.refill_rate == 10.0
        assert bucket.redis_client is None
        assert bucket._tokens == 100.0

    def test_init_with_redis(self):
        """Test TokenBucket initialization with Redis."""
        mock_redis = MagicMock()
        bucket = TokenBucket(capacity=100, refill_rate=10.0, redis_client=mock_redis)
        assert bucket.redis_client == mock_redis

    @pytest.mark.asyncio
    async def test_consume_local_success(self):
        """Test successful local token consumption."""
        bucket = TokenBucket(capacity=100, refill_rate=10.0)

        result = await bucket.consume(50, timeout=1.0)

        assert result is True
        assert bucket._tokens == 50.0

    @pytest.mark.asyncio
    async def test_consume_local_insufficient_tokens(self):
        """Test consumption with insufficient tokens (timeout)."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)

        # Try to consume more than available with short timeout
        result = await bucket.consume(50, timeout=0.1)

        assert result is False

    @pytest.mark.asyncio
    async def test_consume_local_waits_for_refill(self):
        """Test that consume waits for token refill."""
        bucket = TokenBucket(capacity=100, refill_rate=100.0)  # Fast refill

        # Consume all tokens
        await bucket.consume(100)
        assert bucket._tokens == 0.0

        # Wait and consume more (should refill)
        await asyncio.sleep(0.1)  # 10 tokens should refill
        result = await bucket.consume(5, timeout=0.5)

        assert result is True

    @pytest.mark.asyncio
    async def test_consume_local_respects_capacity(self):
        """Test that refill respects capacity limit."""
        bucket = TokenBucket(capacity=100, refill_rate=1000.0)

        # Wait a bit - should not exceed capacity
        await asyncio.sleep(0.1)
        await bucket.consume(1)  # Trigger refill calculation

        assert bucket._tokens <= bucket.capacity

    @pytest.mark.asyncio
    async def test_consume_redis_success(self):
        """Test Redis-based token consumption."""
        mock_redis = AsyncMock()
        mock_redis.eval = AsyncMock(return_value=1)  # Success

        bucket = TokenBucket(capacity=100, refill_rate=10.0, redis_client=mock_redis)

        result = await bucket.consume(50, timeout=1.0)

        assert result is True
        mock_redis.eval.assert_called()

    @pytest.mark.asyncio
    async def test_consume_redis_timeout(self):
        """Test Redis consumption timeout."""
        mock_redis = AsyncMock()
        mock_redis.eval = AsyncMock(return_value=0)  # Not enough tokens

        bucket = TokenBucket(capacity=100, refill_rate=10.0, redis_client=mock_redis)

        result = await bucket.consume(50, timeout=0.1)

        assert result is False


class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_init(self):
        """Test RateLimiter initialization."""
        limiter = RateLimiter()
        assert limiter.redis_client is None
        assert len(limiter._buckets) == len(MODEL_RATE_LIMITS)

    def test_init_with_redis(self):
        """Test RateLimiter initialization with Redis."""
        mock_redis = MagicMock()
        limiter = RateLimiter(redis_client=mock_redis)
        assert limiter.redis_client == mock_redis

    def test_init_creates_buckets_for_all_models(self):
        """Test that buckets are created for all model tiers."""
        limiter = RateLimiter()

        for model in ModelTier:
            assert model.value in limiter._buckets
            assert "requests" in limiter._buckets[model.value]
            assert "tokens_minute" in limiter._buckets[model.value]
            assert "tokens_day" in limiter._buckets[model.value]

    @pytest.mark.asyncio
    async def test_acquire_success(self):
        """Test successful rate limit acquisition."""
        limiter = RateLimiter()

        # Should succeed with fresh limiter
        await limiter.acquire(ModelTier.SONNET, estimated_tokens=100)

    @pytest.mark.asyncio
    async def test_acquire_unknown_model_warning(self):
        """Test acquire with unknown model logs warning."""
        limiter = RateLimiter()
        limiter._buckets = {}  # Clear all buckets

        # Should not raise, just log warning
        await limiter.acquire(ModelTier.SONNET, estimated_tokens=100)

    @pytest.mark.asyncio
    async def test_acquire_request_limit_exceeded(self):
        """Test RateLimitError when request limit exceeded."""
        limiter = RateLimiter()

        # Mock bucket to return False
        limiter._buckets[ModelTier.SONNET.value]["requests"].consume = AsyncMock(
            return_value=False
        )

        with pytest.raises(RateLimitError) as exc_info:
            await limiter.acquire(ModelTier.SONNET)

        assert "requests_per_minute" in str(exc_info.value.quota_info)

    @pytest.mark.asyncio
    async def test_acquire_minute_token_limit_exceeded(self):
        """Test RateLimitError when minute token limit exceeded."""
        limiter = RateLimiter()

        # Request succeeds but minute tokens fail
        limiter._buckets[ModelTier.SONNET.value]["requests"].consume = AsyncMock(
            return_value=True
        )
        limiter._buckets[ModelTier.SONNET.value]["tokens_minute"].consume = AsyncMock(
            return_value=False
        )

        with pytest.raises(RateLimitError) as exc_info:
            await limiter.acquire(ModelTier.SONNET, estimated_tokens=1000)

        assert "tokens_per_minute" in str(exc_info.value.quota_info)

    @pytest.mark.asyncio
    async def test_acquire_daily_token_limit_exceeded(self):
        """Test RateLimitError when daily token limit exceeded."""
        limiter = RateLimiter()

        # Request and minute tokens succeed but daily fails
        limiter._buckets[ModelTier.SONNET.value]["requests"].consume = AsyncMock(
            return_value=True
        )
        limiter._buckets[ModelTier.SONNET.value]["tokens_minute"].consume = AsyncMock(
            return_value=True
        )
        limiter._buckets[ModelTier.SONNET.value]["tokens_day"].consume = AsyncMock(
            return_value=False
        )

        with pytest.raises(RateLimitError) as exc_info:
            await limiter.acquire(ModelTier.SONNET, estimated_tokens=1000)

        assert "tokens_per_day" in str(exc_info.value.quota_info)
        # Daily limit should have longer retry
        assert exc_info.value.retry_after == 3600.0

    @pytest.mark.asyncio
    async def test_get_quota_status(self):
        """Test getting quota status."""
        limiter = RateLimiter()

        status = await limiter.get_quota_status(ModelTier.SONNET)

        assert "requests" in status
        assert "tokens_minute" in status
        assert "tokens_day" in status
        for limit_type, info in status.items():
            assert "available" in info
            assert "capacity" in info
            assert "refill_rate" in info
            assert "utilization_pct" in info

    @pytest.mark.asyncio
    async def test_get_quota_status_unknown_model(self):
        """Test getting quota status for unknown model."""
        limiter = RateLimiter()
        limiter._buckets = {}

        status = await limiter.get_quota_status(ModelTier.SONNET)

        assert status == {}


class TestAdaptiveRateLimiter:
    """Tests for AdaptiveRateLimiter class."""

    def test_init(self):
        """Test AdaptiveRateLimiter initialization."""
        limiter = AdaptiveRateLimiter()
        assert limiter._backoff_until == {}

    @pytest.mark.asyncio
    async def test_acquire_no_backoff(self):
        """Test acquire without backoff."""
        limiter = AdaptiveRateLimiter()

        await limiter.acquire(ModelTier.SONNET, estimated_tokens=100)

    @pytest.mark.asyncio
    async def test_acquire_with_backoff(self):
        """Test acquire respects backoff period."""
        limiter = AdaptiveRateLimiter()

        # Set backoff for 0.1 seconds
        limiter._backoff_until[ModelTier.SONNET.value] = time.time() + 0.1

        start = time.time()
        await limiter.acquire(ModelTier.SONNET, estimated_tokens=100)
        elapsed = time.time() - start

        # Should have waited for backoff
        assert elapsed >= 0.08  # Allow small margin

    @pytest.mark.asyncio
    async def test_acquire_backoff_expired(self):
        """Test acquire when backoff has expired."""
        limiter = AdaptiveRateLimiter()

        # Set expired backoff
        limiter._backoff_until[ModelTier.SONNET.value] = time.time() - 1.0

        # Should succeed immediately
        await limiter.acquire(ModelTier.SONNET, estimated_tokens=100)

    def test_record_rate_limit_hit(self):
        """Test recording rate limit hit."""
        limiter = AdaptiveRateLimiter()

        limiter.record_rate_limit_hit(ModelTier.SONNET, retry_after=60.0)

        assert ModelTier.SONNET.value in limiter._backoff_until
        # Backoff should be roughly 60 seconds from now
        expected = time.time() + 60.0
        assert abs(limiter._backoff_until[ModelTier.SONNET.value] - expected) < 1.0

    def test_record_overloaded(self):
        """Test recording model overloaded."""
        limiter = AdaptiveRateLimiter()

        limiter.record_overloaded(ModelTier.OPUS, retry_after=30.0)

        assert ModelTier.OPUS.value in limiter._backoff_until
        expected = time.time() + 30.0
        assert abs(limiter._backoff_until[ModelTier.OPUS.value] - expected) < 1.0

    def test_record_overloaded_default_retry(self):
        """Test recording model overloaded with default retry."""
        limiter = AdaptiveRateLimiter()

        limiter.record_overloaded(ModelTier.OPUS)

        assert ModelTier.OPUS.value in limiter._backoff_until
        expected = time.time() + 60.0  # Default
        assert abs(limiter._backoff_until[ModelTier.OPUS.value] - expected) < 1.0


class TestGetRateLimiter:
    """Tests for get_rate_limiter function."""

    def test_get_rate_limiter_creates_singleton(self):
        """Test that get_rate_limiter creates singleton."""
        # Reset global
        import iccc.agents.rate_limiter

        iccc.agents.rate_limiter._rate_limiter = None

        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()

        assert limiter1 is limiter2

    def test_get_rate_limiter_with_redis(self):
        """Test get_rate_limiter with Redis client."""
        import iccc.agents.rate_limiter

        iccc.agents.rate_limiter._rate_limiter = None

        mock_redis = MagicMock()
        limiter = get_rate_limiter(mock_redis)

        assert isinstance(limiter, AdaptiveRateLimiter)

    def test_get_rate_limiter_returns_adaptive(self):
        """Test that get_rate_limiter returns AdaptiveRateLimiter."""
        import iccc.agents.rate_limiter

        iccc.agents.rate_limiter._rate_limiter = None

        limiter = get_rate_limiter()

        assert isinstance(limiter, AdaptiveRateLimiter)
