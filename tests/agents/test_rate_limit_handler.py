"""Unit tests for rate limit handler module."""

import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from iccc.agents.rate_limit_handler import RateLimitHandler, UsageStats
from iccc.models.entities import ModelTier, TaskType


class TestUsageStats:
    """Tests for UsageStats dataclass."""

    def test_usage_stats_creation(self):
        """Test creating UsageStats."""
        current_time = time.time()
        stats = UsageStats(
            requests_this_minute=10,
            tokens_this_minute=5000,
            tokens_today=100000,
            last_reset_minute=current_time,
            last_reset_day=current_time,
        )
        assert stats.requests_this_minute == 10
        assert stats.tokens_this_minute == 5000
        assert stats.tokens_today == 100000
        assert stats.last_reset_minute == current_time
        assert stats.last_reset_day == current_time

    def test_usage_stats_default_values(self):
        """Test UsageStats with zero values."""
        stats = UsageStats(
            requests_this_minute=0,
            tokens_this_minute=0,
            tokens_today=0,
            last_reset_minute=0.0,
            last_reset_day=0.0,
        )
        assert stats.requests_this_minute == 0
        assert stats.tokens_this_minute == 0
        assert stats.tokens_today == 0


class TestRateLimitHandlerInit:
    """Tests for RateLimitHandler initialization."""

    def test_init_default(self):
        """Test default initialization."""
        handler = RateLimitHandler()
        assert handler.redis is None
        assert handler.cache_ttl == 3600
        assert handler.downgrade_threshold == 0.8
        assert handler.usage == {}

    def test_init_with_redis(self):
        """Test initialization with Redis client."""
        mock_redis = MagicMock()
        handler = RateLimitHandler(redis_client=mock_redis)
        assert handler.redis == mock_redis

    def test_init_with_custom_ttl(self):
        """Test initialization with custom cache TTL."""
        handler = RateLimitHandler(cache_ttl=7200)
        assert handler.cache_ttl == 7200

    def test_init_with_custom_threshold(self):
        """Test initialization with custom downgrade threshold."""
        handler = RateLimitHandler(downgrade_threshold=0.9)
        assert handler.downgrade_threshold == 0.9

    def test_tier_hierarchy(self):
        """Test tier hierarchy is properly configured."""
        handler = RateLimitHandler()
        assert handler.tier_hierarchy[ModelTier.OPUS] == ModelTier.SONNET
        assert handler.tier_hierarchy[ModelTier.SONNET] == ModelTier.HAIKU
        assert handler.tier_hierarchy[ModelTier.HAIKU] is None


class TestSelectModelWithLimits:
    """Tests for select_model_with_limits method."""

    @pytest.fixture
    def handler(self):
        """Create handler for testing."""
        return RateLimitHandler()

    @pytest.fixture
    def sample_task(self):
        """Create a mock task with is_critical attribute."""
        mock_task = MagicMock()
        mock_task.id = uuid4()
        mock_task.task_type = TaskType.SIMPLE_REFACTOR
        mock_task.complexity = None
        mock_task.is_critical = False
        return mock_task

    @pytest.mark.asyncio
    async def test_select_model_uses_model_selector(self, handler, sample_task):
        """Test that ModelSelector is used when no preferred model given."""
        with patch.object(handler, "is_approaching_limit", return_value=False):
            with patch(
                "iccc.agents.rate_limit_handler.ModelSelector.select_model",
                return_value=ModelTier.SONNET,
            ) as mock_selector:
                result = await handler.select_model_with_limits(sample_task)
                mock_selector.assert_called_once()
                assert result == ModelTier.SONNET

    @pytest.mark.asyncio
    async def test_select_model_preserves_critical_task(self, handler, sample_task):
        """Test that critical tasks keep preferred model."""
        sample_task.is_critical = True

        with patch.object(handler, "is_approaching_limit", return_value=True):
            result = await handler.select_model_with_limits(
                sample_task, preferred_model=ModelTier.OPUS
            )
            assert result == ModelTier.OPUS

    @pytest.mark.asyncio
    async def test_select_model_no_downgrade_when_ok(self, handler, sample_task):
        """Test no downgrade when not approaching limit."""
        with patch.object(handler, "is_approaching_limit", return_value=False):
            result = await handler.select_model_with_limits(
                sample_task, preferred_model=ModelTier.OPUS
            )
            assert result == ModelTier.OPUS

    @pytest.mark.asyncio
    async def test_select_model_downgrades_when_approaching_limit(
        self, handler, sample_task
    ):
        """Test downgrade when approaching limit."""
        with patch.object(handler, "is_approaching_limit", return_value=True):
            result = await handler.select_model_with_limits(
                sample_task, preferred_model=ModelTier.OPUS
            )
            assert result == ModelTier.SONNET

    @pytest.mark.asyncio
    async def test_select_model_no_downgrade_available(self, handler, sample_task):
        """Test when no further downgrade is available."""
        with patch.object(handler, "is_approaching_limit", return_value=True):
            result = await handler.select_model_with_limits(
                sample_task, preferred_model=ModelTier.HAIKU
            )
            # Can't downgrade from HAIKU, returns original
            assert result == ModelTier.HAIKU


class TestIsApproachingLimit:
    """Tests for is_approaching_limit method."""

    @pytest.fixture
    def handler(self):
        """Create handler for testing."""
        return RateLimitHandler(downgrade_threshold=0.8)

    @pytest.mark.asyncio
    async def test_approaching_limit_tokens_per_minute(self, handler):
        """Test detecting approaching minute token limit."""
        # Set usage at 85% of limit
        current_time = time.time()
        handler.usage[ModelTier.SONNET] = UsageStats(
            requests_this_minute=0,
            tokens_this_minute=34000,  # 85% of 40000
            tokens_today=0,
            last_reset_minute=current_time,
            last_reset_day=current_time,
        )

        result = await handler.is_approaching_limit(
            ModelTier.SONNET, metric="tokens_per_minute"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_not_approaching_limit(self, handler):
        """Test when not approaching limit."""
        current_time = time.time()
        handler.usage[ModelTier.SONNET] = UsageStats(
            requests_this_minute=0,
            tokens_this_minute=10000,  # 25% of 40000
            tokens_today=0,
            last_reset_minute=current_time,
            last_reset_day=current_time,
        )

        result = await handler.is_approaching_limit(ModelTier.SONNET)
        assert result is False

    @pytest.mark.asyncio
    async def test_approaching_limit_tokens_per_day(self, handler):
        """Test detecting approaching daily token limit."""
        current_time = time.time()
        handler.usage[ModelTier.SONNET] = UsageStats(
            requests_this_minute=0,
            tokens_this_minute=0,
            tokens_today=4500000,  # 90% of 5000000
            last_reset_minute=current_time,
            last_reset_day=current_time,
        )

        result = await handler.is_approaching_limit(
            ModelTier.SONNET, metric="tokens_per_day"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_approaching_limit_requests(self, handler):
        """Test detecting approaching request limit."""
        current_time = time.time()
        handler.usage[ModelTier.SONNET] = UsageStats(
            requests_this_minute=45,  # 90% of 50
            tokens_this_minute=0,
            tokens_today=0,
            last_reset_minute=current_time,
            last_reset_day=current_time,
        )

        result = await handler.is_approaching_limit(
            ModelTier.SONNET, metric="requests_per_minute"
        )
        assert result is True


class TestRecordUsage:
    """Tests for record_usage method."""

    @pytest.fixture
    def handler(self):
        """Create handler for testing."""
        return RateLimitHandler()

    @pytest.mark.asyncio
    async def test_record_usage_creates_stats(self, handler):
        """Test that recording usage creates stats if not exist."""
        await handler.record_usage(ModelTier.SONNET, tokens_used=1000)

        assert ModelTier.SONNET in handler.usage
        assert handler.usage[ModelTier.SONNET].tokens_this_minute == 1000
        assert handler.usage[ModelTier.SONNET].tokens_today == 1000
        assert handler.usage[ModelTier.SONNET].requests_this_minute == 1

    @pytest.mark.asyncio
    async def test_record_usage_accumulates(self, handler):
        """Test that usage accumulates."""
        await handler.record_usage(ModelTier.SONNET, tokens_used=1000)
        await handler.record_usage(ModelTier.SONNET, tokens_used=500)

        assert handler.usage[ModelTier.SONNET].tokens_this_minute == 1500
        assert handler.usage[ModelTier.SONNET].tokens_today == 1500
        assert handler.usage[ModelTier.SONNET].requests_this_minute == 2

    @pytest.mark.asyncio
    async def test_record_usage_resets_minute_counter(self, handler):
        """Test that minute counters reset after 60 seconds."""
        # Set up usage with old timestamp
        handler.usage[ModelTier.SONNET] = UsageStats(
            requests_this_minute=10,
            tokens_this_minute=5000,
            tokens_today=10000,
            last_reset_minute=time.time() - 120,  # 2 minutes ago
            last_reset_day=time.time(),
        )

        await handler.record_usage(ModelTier.SONNET, tokens_used=1000)

        # Minute counters should have reset before adding new usage
        assert handler.usage[ModelTier.SONNET].requests_this_minute == 1
        assert handler.usage[ModelTier.SONNET].tokens_this_minute == 1000
        # Daily counter should accumulate
        assert handler.usage[ModelTier.SONNET].tokens_today == 11000

    @pytest.mark.asyncio
    async def test_record_usage_resets_daily_counter(self, handler):
        """Test that daily counters reset after 24 hours."""
        handler.usage[ModelTier.SONNET] = UsageStats(
            requests_this_minute=0,
            tokens_this_minute=0,
            tokens_today=100000,
            last_reset_minute=time.time(),
            last_reset_day=time.time() - 90000,  # > 24 hours ago
        )

        await handler.record_usage(ModelTier.SONNET, tokens_used=1000)

        # Daily counter should have reset
        assert handler.usage[ModelTier.SONNET].tokens_today == 1000


class TestCaching:
    """Tests for cache methods."""

    @pytest.fixture
    def handler_with_redis(self):
        """Create handler with mock Redis."""
        mock_redis = AsyncMock()
        return RateLimitHandler(redis_client=mock_redis)

    @pytest.fixture
    def sample_task(self):
        """Create a mock task for caching tests."""
        mock_task = MagicMock()
        mock_task.id = uuid4()
        mock_task.description = "Test task"
        mock_task_type = MagicMock()
        mock_task_type.value = "simple_refactor"
        mock_task.task_type = mock_task_type
        return mock_task

    @pytest.mark.asyncio
    async def test_check_cache_without_redis(self, sample_task):
        """Test check_cache returns None without Redis."""
        handler = RateLimitHandler()
        result = await handler.check_cache(sample_task, ModelTier.SONNET)
        assert result is None

    @pytest.mark.asyncio
    async def test_check_cache_hit(self, handler_with_redis, sample_task):
        """Test cache hit returns cached value."""
        handler_with_redis.redis.get = AsyncMock(return_value='{"result": "cached"}')

        result = await handler_with_redis.check_cache(sample_task, ModelTier.SONNET)

        assert result == {"result": "cached"}

    @pytest.mark.asyncio
    async def test_check_cache_miss(self, handler_with_redis, sample_task):
        """Test cache miss returns None."""
        handler_with_redis.redis.get = AsyncMock(return_value=None)

        result = await handler_with_redis.check_cache(sample_task, ModelTier.SONNET)

        assert result is None

    @pytest.mark.asyncio
    async def test_check_cache_error_returns_none(self, handler_with_redis, sample_task):
        """Test cache error returns None."""
        handler_with_redis.redis.get = AsyncMock(side_effect=Exception("Redis error"))

        result = await handler_with_redis.check_cache(sample_task, ModelTier.SONNET)

        assert result is None

    @pytest.mark.asyncio
    async def test_set_cache_without_redis(self, sample_task):
        """Test set_cache does nothing without Redis."""
        handler = RateLimitHandler()
        # Should not raise
        await handler.set_cache(sample_task, ModelTier.SONNET, {"result": "value"})

    @pytest.mark.asyncio
    async def test_set_cache_success(self, handler_with_redis, sample_task):
        """Test successful cache set."""
        await handler_with_redis.set_cache(
            sample_task, ModelTier.SONNET, {"result": "value"}
        )

        handler_with_redis.redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_cache_error_handled(self, handler_with_redis, sample_task):
        """Test cache set error is handled gracefully."""
        handler_with_redis.redis.setex = AsyncMock(side_effect=Exception("Redis error"))

        # Should not raise
        await handler_with_redis.set_cache(
            sample_task, ModelTier.SONNET, {"result": "value"}
        )


class TestGetUsageSummary:
    """Tests for get_usage_summary method."""

    @pytest.fixture
    def handler(self):
        """Create handler for testing."""
        return RateLimitHandler()

    @pytest.mark.asyncio
    async def test_get_usage_summary_empty(self, handler):
        """Test usage summary with no usage."""
        summary = await handler.get_usage_summary()

        assert len(summary) == len(ModelTier)
        for model in ModelTier:
            assert model.value in summary
            assert summary[model.value]["requests_this_minute"] == 0
            assert summary[model.value]["tokens_this_minute"] == 0
            assert summary[model.value]["tokens_today"] == 0

    @pytest.mark.asyncio
    async def test_get_usage_summary_with_data(self, handler):
        """Test usage summary with recorded usage."""
        await handler.record_usage(ModelTier.SONNET, tokens_used=5000)

        summary = await handler.get_usage_summary()

        assert summary[ModelTier.SONNET.value]["tokens_this_minute"] == 5000
        assert summary[ModelTier.SONNET.value]["requests_this_minute"] == 1


class TestDowngradeModel:
    """Tests for _downgrade_model method."""

    def test_downgrade_opus(self):
        """Test downgrading from Opus."""
        handler = RateLimitHandler()
        result = handler._downgrade_model(ModelTier.OPUS)
        assert result == ModelTier.SONNET

    def test_downgrade_sonnet(self):
        """Test downgrading from Sonnet."""
        handler = RateLimitHandler()
        result = handler._downgrade_model(ModelTier.SONNET)
        assert result == ModelTier.HAIKU

    def test_downgrade_haiku_returns_none(self):
        """Test that Haiku cannot be downgraded."""
        handler = RateLimitHandler()
        result = handler._downgrade_model(ModelTier.HAIKU)
        assert result is None


class TestGetCacheKey:
    """Tests for _get_cache_key method."""

    def _create_mock_task(self, description="Test task"):
        """Create a mock task for cache key tests."""
        mock_task = MagicMock()
        mock_task.description = description
        mock_task.task_type = MagicMock()
        mock_task.task_type.value = "simple_refactor"
        return mock_task

    def test_cache_key_format(self):
        """Test cache key format."""
        handler = RateLimitHandler()
        task = self._create_mock_task()

        key = handler._get_cache_key(task, ModelTier.SONNET)

        assert key.startswith("iccc:cache:task:")
        assert len(key) > len("iccc:cache:task:")

    def test_cache_key_deterministic(self):
        """Test cache key is deterministic."""
        handler = RateLimitHandler()
        task = self._create_mock_task()

        key1 = handler._get_cache_key(task, ModelTier.SONNET)
        key2 = handler._get_cache_key(task, ModelTier.SONNET)

        assert key1 == key2

    def test_cache_key_different_for_different_models(self):
        """Test cache key differs for different models."""
        handler = RateLimitHandler()
        task = self._create_mock_task()

        key_sonnet = handler._get_cache_key(task, ModelTier.SONNET)
        key_opus = handler._get_cache_key(task, ModelTier.OPUS)

        assert key_sonnet != key_opus
