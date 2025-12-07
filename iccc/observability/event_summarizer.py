"""AI-powered event summarization using Claude Haiku."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from anthropic import AsyncAnthropic

if TYPE_CHECKING:
    from iccc.models.entities import HookEvent


@dataclass
class SummaryCache:
    """Cache for event summaries to avoid redundant API calls."""

    cache: dict[str, tuple[str, datetime]] = field(default_factory=dict)
    max_age: timedelta = field(default_factory=lambda: timedelta(minutes=30))
    max_size: int = 1000

    def _generate_key(self, events_data: str) -> str:
        """Generate cache key from events data."""
        return hashlib.md5(events_data.encode()).hexdigest()

    def get(self, events_data: str) -> str | None:
        """Get cached summary if available and not expired."""
        key = self._generate_key(events_data)
        if key not in self.cache:
            return None

        summary, timestamp = self.cache[key]
        if datetime.now() - timestamp > self.max_age:
            del self.cache[key]
            return None

        return summary

    def set(self, events_data: str, summary: str) -> None:
        """Cache a summary."""
        # Evict oldest entries if at capacity
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.cache, key=lambda k: self.cache[k][1])
            del self.cache[oldest_key]

        key = self._generate_key(events_data)
        self.cache[key] = (summary, datetime.now())

    def clear(self) -> None:
        """Clear all cached summaries."""
        self.cache.clear()


@dataclass
class SummaryStats:
    """Statistics for summarization operations."""

    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    errors: int = 0
    total_tokens_used: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0


class EventSummarizer:
    """
    AI-powered event summarizer using Claude Haiku.

    Features:
    - Generates concise summaries of agent events
    - Caches summaries to avoid redundant API calls
    - Handles errors gracefully (silent failure mode)
    - Supports different summary styles
    """

    # Summary style templates
    SUMMARY_PROMPTS = {
        "concise": """Summarize these agent events in 1-2 short sentences (max 20 words):

{events}

Focus on: main actions taken and any errors.""",
        "detailed": """Provide a detailed summary of these agent activity events:

{events}

Include:
1. Tasks attempted and their outcomes
2. Any errors or warnings
3. Overall progress assessment
4. Recommended next steps (if any issues)""",
        "technical": """Generate a technical summary of these agent events:

{events}

Format as:
- Actions: [list key actions]
- Status: [success/partial/failed]
- Issues: [any errors or warnings]""",
        "dashboard": """Create a dashboard-friendly summary (max 50 words):

{events}

Format: "[Status emoji] Brief description of activity and outcome." """,
    }

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-3-5-haiku-latest",
        enable_cache: bool = True,
        silent_failures: bool = True,
        max_events_per_summary: int = 50,
    ) -> None:
        """
        Initialize the event summarizer.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model: Claude model to use (default: Haiku for speed/cost)
            enable_cache: Whether to cache summaries
            silent_failures: If True, return None on errors instead of raising
            max_events_per_summary: Maximum events to include in a single summary
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.silent_failures = silent_failures
        self.max_events_per_summary = max_events_per_summary

        # Initialize AI client
        self.client: AsyncAnthropic | None = None
        if self.api_key:
            self.client = AsyncAnthropic(api_key=self.api_key)

        # Initialize cache
        self.cache = SummaryCache() if enable_cache else None

        # Statistics
        self.stats = SummaryStats()

        # Rate limiting
        self._last_request_time: datetime | None = None
        self._min_request_interval = timedelta(milliseconds=100)

    def _format_events(self, events: list[HookEvent]) -> str:
        """Format events for the AI prompt."""
        formatted = []
        for event in events[: self.max_events_per_summary]:
            timestamp = event.timestamp.strftime("%H:%M:%S")
            event_type = event.event_type

            # Extract key data
            data_summary = self._summarize_event_data(event.data)

            formatted.append(f"- [{timestamp}] {event_type}: {data_summary}")

        return "\n".join(formatted)

    def _summarize_event_data(self, data: dict[str, Any]) -> str:
        """Create a brief summary of event data."""
        parts = []

        # Tool information
        if "tool_name" in data:
            parts.append(f"tool={data['tool_name']}")

        # Status/result
        if "status" in data:
            parts.append(f"status={data['status']}")
        elif "result" in data:
            result = str(data["result"])[:50]
            parts.append(f"result={result}")

        # Errors
        if "error" in data:
            error = str(data["error"])[:50]
            parts.append(f"error={error}")

        # Agent info
        if "agent_id" in data:
            parts.append(f"agent={data['agent_id']}")

        # File operations
        if "file_path" in data:
            parts.append(f"file={data['file_path']}")

        if not parts:
            # Fallback to JSON snippet
            return json.dumps(data)[:80]

        return ", ".join(parts)

    async def summarize_event(
        self,
        event: HookEvent,
        style: str = "concise",
    ) -> str | None:
        """
        Generate a summary for a single event.

        Args:
            event: The event to summarize
            style: Summary style (concise, detailed, technical, dashboard)

        Returns:
            Summary string or None if failed
        """
        return await self.summarize_events([event], style)

    async def summarize_events(
        self,
        events: list[HookEvent],
        style: str = "concise",
    ) -> str | None:
        """
        Generate a summary for a batch of events.

        Args:
            events: List of events to summarize
            style: Summary style (concise, detailed, technical, dashboard)

        Returns:
            Summary string or None if failed
        """
        if not events:
            return None

        if not self.client:
            if self.silent_failures:
                return None
            raise RuntimeError("Anthropic client not initialized - check API key")

        self.stats.total_requests += 1

        # Format events
        events_text = self._format_events(events)

        # Check cache
        if self.cache:
            cached = self.cache.get(events_text + style)
            if cached:
                self.stats.cache_hits += 1
                return cached
            self.stats.cache_misses += 1

        # Rate limiting
        await self._apply_rate_limit()

        try:
            # Get prompt template
            prompt_template = self.SUMMARY_PROMPTS.get(style, self.SUMMARY_PROMPTS["concise"])
            prompt = prompt_template.format(events=events_text)

            # Call API
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=300,
                temperature=0.5,
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract summary
            if response.content and len(response.content) > 0:
                first_block = response.content[0]
                if hasattr(first_block, "text"):
                    summary = first_block.text

                    # Track token usage
                    if hasattr(response, "usage"):
                        self.stats.total_tokens_used += (
                            response.usage.input_tokens + response.usage.output_tokens
                        )

                    # Cache result
                    if self.cache:
                        self.cache.set(events_text + style, summary)

                    return summary

        except Exception as e:
            self.stats.errors += 1
            if self.silent_failures:
                return None
            raise RuntimeError(f"Summary generation failed: {e}") from e

        return None

    async def summarize_by_agent(
        self,
        events: list[HookEvent],
        style: str = "concise",
    ) -> dict[str, str | None]:
        """
        Generate summaries grouped by agent.

        Args:
            events: List of events to summarize
            style: Summary style

        Returns:
            Dict mapping agent_id to summary
        """
        # Group events by agent
        by_agent: dict[str, list[HookEvent]] = {}
        for event in events:
            agent_id = event.data.get("agent_id", "unknown")
            if agent_id not in by_agent:
                by_agent[agent_id] = []
            by_agent[agent_id].append(event)

        # Generate summaries in parallel
        tasks = {
            agent_id: self.summarize_events(agent_events, style)
            for agent_id, agent_events in by_agent.items()
        }

        results = {}
        for agent_id, task in tasks.items():
            results[agent_id] = await task

        return results

    async def summarize_by_type(
        self,
        events: list[HookEvent],
        style: str = "concise",
    ) -> dict[str, str | None]:
        """
        Generate summaries grouped by event type.

        Args:
            events: List of events to summarize
            style: Summary style

        Returns:
            Dict mapping event_type to summary
        """
        # Group events by type
        by_type: dict[str, list[HookEvent]] = {}
        for event in events:
            event_type = event.event_type
            if event_type not in by_type:
                by_type[event_type] = []
            by_type[event_type].append(event)

        # Generate summaries in parallel
        tasks = {
            event_type: self.summarize_events(type_events, style)
            for event_type, type_events in by_type.items()
        }

        results = {}
        for event_type, task in tasks.items():
            results[event_type] = await task

        return results

    async def _apply_rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        if self._last_request_time:
            elapsed = datetime.now() - self._last_request_time
            if elapsed < self._min_request_interval:
                await asyncio.sleep(
                    (self._min_request_interval - elapsed).total_seconds()
                )
        self._last_request_time = datetime.now()

    def get_stats(self) -> dict[str, Any]:
        """Get summarization statistics."""
        return {
            "total_requests": self.stats.total_requests,
            "cache_hits": self.stats.cache_hits,
            "cache_misses": self.stats.cache_misses,
            "cache_hit_rate": f"{self.stats.hit_rate:.1%}",
            "errors": self.stats.errors,
            "total_tokens_used": self.stats.total_tokens_used,
            "model": self.model,
            "cache_enabled": self.cache is not None,
        }

    def clear_cache(self) -> None:
        """Clear the summary cache."""
        if self.cache:
            self.cache.clear()


# Convenience function for quick summaries
async def quick_summarize(
    events: list[HookEvent],
    style: str = "concise",
    api_key: str | None = None,
) -> str | None:
    """
    Quick helper to summarize events without creating a summarizer instance.

    Args:
        events: Events to summarize
        style: Summary style
        api_key: Optional API key

    Returns:
        Summary or None
    """
    summarizer = EventSummarizer(api_key=api_key, enable_cache=False)
    return await summarizer.summarize_events(events, style)
