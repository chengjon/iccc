"""Event collection system with batching, sampling, and AI summaries."""

import asyncio
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from anthropic import AsyncAnthropic

from iccc.models.entities import HookEvent
from iccc.config import get_config


@dataclass
class EventBatch:
    """Batch of events for efficient processing."""

    events: list[HookEvent] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def size(self) -> int:
        """Get number of events in batch."""
        return len(self.events)

    def add(self, event: HookEvent) -> None:
        """Add an event to the batch."""
        self.events.append(event)

    def should_flush(self, max_size: int = 100, max_age_seconds: int = 5) -> bool:
        """Check if batch should be flushed."""
        if self.size() >= max_size:
            return True

        age = (datetime.now() - self.created_at).total_seconds()
        return age >= max_age_seconds


class EventSampler:
    """Sample events to reduce overhead."""

    def __init__(self, sample_rate: float = 1.0) -> None:
        """
        Initialize sampler.

        Args:
            sample_rate: Fraction of events to keep (0.0 to 1.0)
        """
        self.sample_rate = max(0.0, min(1.0, sample_rate))
        self.counter = 0

    def should_sample(self, event: HookEvent) -> bool:
        """Decide if an event should be sampled."""
        # Always sample critical events
        if event.data.get("critical", False):
            return True

        # Sample based on rate
        self.counter += 1
        return (self.counter % int(1 / self.sample_rate)) == 0


class EventCollector:
    """Collects and processes events from hooks."""

    def __init__(
        self,
        batch_size: int = 100,
        batch_timeout: int = 5,
        sample_rate: float = 1.0,
        enable_ai_summaries: bool = True,
    ) -> None:
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.sampler = EventSampler(sample_rate)
        self.enable_ai_summaries = enable_ai_summaries

        # Current batch
        self.current_batch = EventBatch()

        # Callbacks for flushed batches
        self.flush_callbacks: list[Callable[[list[HookEvent]], None]] = []

        # AI client for summaries
        self.ai_client: AsyncAnthropic | None = None
        if enable_ai_summaries:
            api_key = get_config().anthropic.api_key
            if api_key:
                self.ai_client = AsyncAnthropic(api_key=api_key)

        # Background flush task
        self.flush_task: asyncio.Task[None] | None = None
        self.running = False

    def register_flush_callback(self, callback: Callable[[list[HookEvent]], None]) -> None:
        """Register a callback to be called when batch is flushed."""
        self.flush_callbacks.append(callback)

    async def start(self) -> None:
        """Start the collector background tasks."""
        self.running = True
        self.flush_task = asyncio.create_task(self._periodic_flush())

    async def stop(self) -> None:
        """Stop the collector and flush remaining events."""
        self.running = False

        if self.flush_task:
            self.flush_task.cancel()
            try:
                await self.flush_task
            except asyncio.CancelledError:
                pass

        # Flush any remaining events
        if self.current_batch.size() > 0:
            await self._flush_batch()

    async def collect(self, event: HookEvent) -> None:
        """
        Collect an event.

        Args:
            event: Event to collect
        """
        # Apply sampling
        if not self.sampler.should_sample(event):
            return

        # Add to current batch
        self.current_batch.add(event)

        # Check if batch should be flushed
        if self.current_batch.should_flush(self.batch_size, self.batch_timeout):
            await self._flush_batch()

    async def _periodic_flush(self) -> None:
        """Periodically flush batches."""
        while self.running:
            await asyncio.sleep(self.batch_timeout)

            if self.current_batch.size() > 0:
                if self.current_batch.should_flush(self.batch_size, self.batch_timeout):
                    await self._flush_batch()

    async def _flush_batch(self) -> None:
        """Flush the current batch."""
        if self.current_batch.size() == 0:
            return

        # Get events
        events = self.current_batch.events

        # Create new batch
        self.current_batch = EventBatch()

        # Generate AI summary if enabled
        summary = None
        if self.enable_ai_summaries and self.ai_client:
            summary = await self._generate_ai_summary(events)

        # Call flush callbacks
        for callback in self.flush_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(events, summary)
                else:
                    callback(events, summary)
            except Exception as e:
                # Don't let callback failures stop flushing
                print(f"Flush callback error: {e}")

    async def _generate_ai_summary(self, events: list[HookEvent]) -> str | None:
        """
        Generate AI-powered summary of events using Haiku.

        Args:
            events: List of events to summarize

        Returns:
            Summary text or None if failed
        """
        if not self.ai_client or len(events) == 0:
            return None

        try:
            # Format events for AI
            event_descriptions = []
            for event in events[:50]:  # Limit to 50 events for context
                event_descriptions.append(
                    f"- [{event.event_type}] at {event.timestamp.strftime('%H:%M:%S')}: "
                    f"{json.dumps(event.data)[:100]}"
                )

            prompt = f"""Summarize the following agent activity events in 2-3 concise sentences:

{chr(10).join(event_descriptions)}

Focus on: what tasks were attempted, any errors/warnings, and overall progress."""

            response = await self.ai_client.messages.create(
                model="claude-3-5-haiku-latest",
                max_tokens=200,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}],
            )

            if response.content and len(response.content) > 0:
                return response.content[0].text

        except Exception as e:
            print(f"AI summary generation failed: {e}")

        return None

    def get_stats(self) -> dict[str, Any]:
        """Get collector statistics."""
        return {
            "current_batch_size": self.current_batch.size(),
            "batch_size_limit": self.batch_size,
            "batch_timeout": self.batch_timeout,
            "sample_rate": self.sampler.sample_rate,
            "ai_summaries_enabled": self.enable_ai_summaries,
            "flush_callbacks": len(self.flush_callbacks),
        }


class EventAggregator:
    """Aggregate events for dashboard display."""

    @staticmethod
    def aggregate_by_type(events: list[HookEvent]) -> dict[str, int]:
        """Count events by type."""
        counts: dict[str, int] = {}
        for event in events:
            counts[event.event_type] = counts.get(event.event_type, 0) + 1
        return counts

    @staticmethod
    def aggregate_by_agent(events: list[HookEvent]) -> dict[str, int]:
        """Count events by agent."""
        counts: dict[str, int] = {}
        for event in events:
            agent_id = event.data.get("agent_id", "unknown")
            counts[agent_id] = counts.get(agent_id, 0) + 1
        return counts

    @staticmethod
    def get_error_events(events: list[HookEvent]) -> list[HookEvent]:
        """Filter error events."""
        return [
            e
            for e in events
            if e.data.get("error") or e.data.get("status") == "failed"
        ]

    @staticmethod
    def get_recent_events(events: list[HookEvent], limit: int = 20) -> list[HookEvent]:
        """Get most recent events."""
        sorted_events = sorted(events, key=lambda e: e.timestamp, reverse=True)
        return sorted_events[:limit]
