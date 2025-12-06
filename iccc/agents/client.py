"""Claude API client wrapper."""

import logging
import os
from typing import Any, AsyncIterator, Optional

from anthropic import Anthropic, AsyncAnthropic
from redis.asyncio import Redis

from iccc.agents.model_selector import ModelSelector
from iccc.agents.rate_limiter import AdaptiveRateLimiter, get_rate_limiter
from iccc.errors.exceptions import ModelOverloadedError, RateLimitError
from iccc.models.entities import Message, ModelTier

logger = logging.getLogger(__name__)


class ClaudeClient:
    """Wrapper for Claude API interactions."""

    def __init__(
        self, api_key: Optional[str] = None, redis_client: Optional[Redis] = None
    ) -> None:
        """
        Initialize Claude client.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            redis_client: Optional Redis client for distributed rate limiting
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not provided")

        self.client = AsyncAnthropic(api_key=self.api_key)
        self.sync_client = Anthropic(api_key=self.api_key)
        self.rate_limiter = get_rate_limiter(redis_client)

    async def send_message(
        self,
        messages: list[Message],
        model: ModelTier = ModelTier.SONNET,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 1.0,
    ) -> dict[str, Any]:
        """
        Send messages to Claude and get response.

        Args:
            messages: Conversation history
            model: Model tier to use
            system: System prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            Response dict with content, usage, etc.

        Raises:
            RateLimitError: If rate limit exceeded
            ModelOverloadedError: If model is overloaded
        """
        config = ModelSelector.get_model_config(model)

        if max_tokens is None:
            max_tokens = config["max_tokens"]

        # Estimate tokens for rate limiting
        input_text = " ".join(msg.content for msg in messages)
        if system:
            input_text += " " + system
        estimated_tokens = self.count_tokens(input_text) + max_tokens

        # Check rate limits before making request
        await self.rate_limiter.acquire(model, estimated_tokens)

        # Convert Message objects to API format
        api_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        try:
            response = await self.client.messages.create(
                model=config["model"],
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=api_messages,
            )

            return {
                "content": response.content[0].text if response.content else "",
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
                "stop_reason": response.stop_reason,
                "model": response.model,
            }

        except Exception as e:
            # Parse error response for rate limit or overload
            error_msg = str(e).lower()

            if "rate" in error_msg and "limit" in error_msg:
                # Extract retry_after if present
                retry_after = 60.0  # Default
                self.rate_limiter.record_rate_limit_hit(model, retry_after)
                raise RateLimitError(
                    service="anthropic",
                    retry_after=retry_after,
                    quota_info={"model": model.value},
                ) from e

            if "overload" in error_msg:
                retry_after = 30.0
                self.rate_limiter.record_overloaded(model, retry_after)
                raise ModelOverloadedError(model=model.value, retry_after=retry_after) from e

            # Unknown error - re-raise
            raise

    async def stream_message(
        self,
        messages: list[Message],
        model: ModelTier = ModelTier.SONNET,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 1.0,
    ) -> AsyncIterator[str]:
        """
        Stream messages from Claude.

        Args:
            messages: Conversation history
            model: Model tier to use
            system: System prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Yields:
            Text chunks as they arrive

        Raises:
            RateLimitError: If rate limit exceeded
            ModelOverloadedError: If model is overloaded
        """
        config = ModelSelector.get_model_config(model)

        if max_tokens is None:
            max_tokens = config["max_tokens"]

        # Estimate tokens for rate limiting
        input_text = " ".join(msg.content for msg in messages)
        if system:
            input_text += " " + system
        estimated_tokens = self.count_tokens(input_text) + max_tokens

        # Check rate limits before making request
        await self.rate_limiter.acquire(model, estimated_tokens)

        api_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        try:
            async with self.client.messages.stream(
                model=config["model"],
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=api_messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield text

        except Exception as e:
            # Parse error response for rate limit or overload
            error_msg = str(e).lower()

            if "rate" in error_msg and "limit" in error_msg:
                retry_after = 60.0
                self.rate_limiter.record_rate_limit_hit(model, retry_after)
                raise RateLimitError(
                    service="anthropic",
                    retry_after=retry_after,
                    quota_info={"model": model.value},
                ) from e

            if "overload" in error_msg:
                retry_after = 30.0
                self.rate_limiter.record_overloaded(model, retry_after)
                raise ModelOverloadedError(model=model.value, retry_after=retry_after) from e

            raise

    def count_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Args:
            text: Text to count

        Returns:
            Approximate token count
        """
        # Rough estimation: ~4 chars per token
        return len(text) // 4

    async def close(self) -> None:
        """Close the client connection."""
        await self.client.close()
