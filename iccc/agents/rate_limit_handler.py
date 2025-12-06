"""Rate limit handler with model downgrading and caching."""

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from redis.asyncio import Redis

from iccc.agents.model_selector import ModelSelector
from iccc.models.entities import ModelTier, Task, TaskType

logger = logging.getLogger(__name__)


@dataclass
class UsageStats:
    """Current usage statistics for a model."""

    requests_this_minute: int
    tokens_this_minute: int
    tokens_today: int
    last_reset_minute: float
    last_reset_day: float


class RateLimitHandler:
    """
    Handles rate limiting with smart model downgrading and caching.

    Features:
    - Tracks usage per model tier
    - Automatically downgrades when approaching limits
    - Preserves critical tasks with original model
    - Caches results to reduce API calls
    - Provides usage statistics
    """

    def __init__(
        self,
        redis_client: Optional[Redis] = None,
        cache_ttl: int = 3600,  # 1 hour
        downgrade_threshold: float = 0.8,  # 80% of limit
    ) -> None:
        """
        Initialize rate limit handler.

        Args:
            redis_client: Redis client for caching
            cache_ttl: Cache time-to-live in seconds
            downgrade_threshold: Usage percentage to trigger downgrade (0.0-1.0)
        """
        self.redis = redis_client
        self.cache_ttl = cache_ttl
        self.downgrade_threshold = downgrade_threshold

        # In-memory usage tracking (fallback if Redis unavailable)
        self.usage: dict[ModelTier, UsageStats] = {}

        # Model tier hierarchy for downgrading
        self.tier_hierarchy = {
            ModelTier.OPUS: ModelTier.SONNET,
            ModelTier.SONNET: ModelTier.HAIKU,
            ModelTier.HAIKU: None,  # Cannot downgrade further
        }

    async def select_model_with_limits(
        self,
        task: Task,
        preferred_model: Optional[ModelTier] = None,
    ) -> ModelTier:
        """
        Select the best model considering rate limits.

        Args:
            task: Task to execute
            preferred_model: Preferred model (from ModelSelector)

        Returns:
            Selected model tier (possibly downgraded)
        """
        # Get preferred model from ModelSelector if not provided
        if not preferred_model:
            preferred_model = ModelSelector.select_model(
                task.task_type, task.complexity
            )

        # Check if task is critical (must use preferred model)
        if task.is_critical:
            logger.info(
                f"Task {task.id} is critical, preserving {preferred_model.value}"
            )
            return preferred_model

        # Check current usage
        is_approaching_limit = await self.is_approaching_limit(preferred_model)

        if not is_approaching_limit:
            return preferred_model

        # Try to downgrade
        downgraded_model = self._downgrade_model(preferred_model)

        if downgraded_model:
            logger.warning(
                f"Rate limit approaching for {preferred_model.value}, "
                f"downgrading to {downgraded_model.value} for task {task.id}"
            )
            return downgraded_model

        # No downgrade available, use preferred (will wait if needed)
        logger.warning(
            f"Cannot downgrade from {preferred_model.value}, "
            f"will wait for rate limit"
        )
        return preferred_model

    async def is_approaching_limit(
        self,
        model: ModelTier,
        metric: str = "tokens_per_minute",
    ) -> bool:
        """
        Check if usage is approaching rate limit.

        Args:
            model: Model tier to check
            metric: Metric to check (tokens_per_minute, tokens_per_day)

        Returns:
            True if approaching limit (>= downgrade_threshold)
        """
        usage = await self._get_usage(model)

        # Get limits for this model
        from iccc.agents.rate_limiter import MODEL_RATE_LIMITS

        limits = MODEL_RATE_LIMITS[model]

        if metric == "tokens_per_minute":
            current = usage.tokens_this_minute
            limit = limits.tokens_per_minute
        elif metric == "tokens_per_day":
            current = usage.tokens_today
            limit = limits.tokens_per_day
        else:
            current = usage.requests_this_minute
            limit = limits.requests_per_minute

        usage_ratio = current / limit if limit > 0 else 0

        return usage_ratio >= self.downgrade_threshold

    async def record_usage(
        self,
        model: ModelTier,
        tokens_used: int,
    ) -> None:
        """
        Record API usage.

        Args:
            model: Model that was used
            tokens_used: Number of tokens consumed
        """
        usage = await self._get_usage(model)

        current_time = time.time()

        # Reset counters if needed
        if current_time - usage.last_reset_minute >= 60:
            usage.requests_this_minute = 0
            usage.tokens_this_minute = 0
            usage.last_reset_minute = current_time

        if current_time - usage.last_reset_day >= 86400:  # 24 hours
            usage.tokens_today = 0
            usage.last_reset_day = current_time

        # Update counters
        usage.requests_this_minute += 1
        usage.tokens_this_minute += tokens_used
        usage.tokens_today += tokens_used

        # Store updated usage
        await self._set_usage(model, usage)

    async def check_cache(
        self,
        task: Task,
        model: ModelTier,
    ) -> Optional[Any]:
        """
        Check if cached result exists for this task.

        Args:
            task: Task to check
            model: Model tier

        Returns:
            Cached result if exists, None otherwise
        """
        if not self.redis:
            return None

        cache_key = self._get_cache_key(task, model)

        try:
            cached = await self.redis.get(cache_key)
            if cached:
                logger.info(f"Cache hit for task {task.id} with {model.value}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache check failed: {e}")

        return None

    async def set_cache(
        self,
        task: Task,
        model: ModelTier,
        result: Any,
    ) -> None:
        """
        Cache result for future use.

        Args:
            task: Task that was executed
            model: Model that was used
            result: Result to cache
        """
        if not self.redis:
            return

        cache_key = self._get_cache_key(task, model)

        try:
            await self.redis.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(result),
            )
            logger.debug(f"Cached result for task {task.id}")
        except Exception as e:
            logger.warning(f"Cache set failed: {e}")

    async def get_usage_summary(self) -> dict[str, Any]:
        """
        Get usage summary for all models.

        Returns:
            Dictionary with usage stats per model
        """
        from iccc.agents.rate_limiter import MODEL_RATE_LIMITS

        summary = {}

        for model in ModelTier:
            usage = await self._get_usage(model)
            limits = MODEL_RATE_LIMITS[model]

            summary[model.value] = {
                "requests_this_minute": usage.requests_this_minute,
                "requests_limit": limits.requests_per_minute,
                "requests_ratio": usage.requests_this_minute / limits.requests_per_minute,
                "tokens_this_minute": usage.tokens_this_minute,
                "tokens_minute_limit": limits.tokens_per_minute,
                "tokens_minute_ratio": usage.tokens_this_minute / limits.tokens_per_minute,
                "tokens_today": usage.tokens_today,
                "tokens_day_limit": limits.tokens_per_day,
                "tokens_day_ratio": usage.tokens_today / limits.tokens_per_day,
                "approaching_limit": await self.is_approaching_limit(model),
            }

        return summary

    def _downgrade_model(self, model: ModelTier) -> Optional[ModelTier]:
        """Get downgraded model tier."""
        return self.tier_hierarchy.get(model)

    def _get_cache_key(self, task: Task, model: ModelTier) -> str:
        """Generate cache key for task and model."""
        # Hash task description + model to create unique key
        task_hash = hashlib.md5(
            f"{task.description}:{task.task_type.value}:{model.value}".encode()
        ).hexdigest()

        return f"iccc:cache:task:{task_hash}"

    async def _get_usage(self, model: ModelTier) -> UsageStats:
        """Get current usage stats for a model."""
        if model not in self.usage:
            current_time = time.time()
            self.usage[model] = UsageStats(
                requests_this_minute=0,
                tokens_this_minute=0,
                tokens_today=0,
                last_reset_minute=current_time,
                last_reset_day=current_time,
            )

        return self.usage[model]

    async def _set_usage(self, model: ModelTier, usage: UsageStats) -> None:
        """Update usage stats for a model."""
        self.usage[model] = usage

        # Optionally persist to Redis
        if self.redis:
            try:
                await self.redis.hset(
                    f"iccc:usage:{model.value}",
                    mapping={
                        "requests_this_minute": str(usage.requests_this_minute),
                        "tokens_this_minute": str(usage.tokens_this_minute),
                        "tokens_today": str(usage.tokens_today),
                        "last_reset_minute": str(usage.last_reset_minute),
                        "last_reset_day": str(usage.last_reset_day),
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to persist usage to Redis: {e}")
