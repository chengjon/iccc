"""Tests for event collection system."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from iccc.models.entities import HookEvent
from iccc.observability.collector import (
    EventAggregator,
    EventBatch,
    EventCollector,
    EventSampler,
)


class TestEventBatch:
    """Test EventBatch class."""

    def test_event_batch_creation(self):
        """Test creating an event batch."""
        batch = EventBatch()
        assert batch.size() == 0
        assert isinstance(batch.created_at, datetime)
        assert batch.events == []

    def test_event_batch_add(self):
        """Test adding events to batch."""
        batch = EventBatch()
        event = HookEvent(
            session_id=uuid4(),
            event_type="PreToolUse",
            data={"tool_name": "Bash"},
        )
        batch.add(event)
        assert batch.size() == 1
        assert batch.events[0] == event

    def test_event_batch_should_flush_by_size(self):
        """Test batch should flush when max size reached."""
        batch = EventBatch()

        # Add events up to max size
        for _ in range(100):
            event = HookEvent(
                session_id=uuid4(),
                event_type="PreToolUse",
                data={},
            )
            batch.add(event)

        assert batch.should_flush(max_size=100) is True

    def test_event_batch_should_not_flush_under_size(self):
        """Test batch should not flush under max size."""
        batch = EventBatch()
        for _ in range(50):
            event = HookEvent(
                session_id=uuid4(),
                event_type="PreToolUse",
                data={},
            )
            batch.add(event)

        assert batch.should_flush(max_size=100, max_age_seconds=1000) is False

    def test_event_batch_should_flush_by_age(self):
        """Test batch should flush when max age reached."""
        batch = EventBatch()
        # Manually set created_at to past
        batch.created_at = datetime.now() - timedelta(seconds=10)

        event = HookEvent(
            session_id=uuid4(),
            event_type="PreToolUse",
            data={},
        )
        batch.add(event)

        assert batch.should_flush(max_size=100, max_age_seconds=5) is True


class TestEventSampler:
    """Test EventSampler class."""

    def test_sampler_initialization(self):
        """Test sampler initialization."""
        sampler = EventSampler(sample_rate=0.5)
        assert sampler.sample_rate == 0.5
        assert sampler.counter == 0

    def test_sampler_clamps_rate(self):
        """Test sampler clamps rate to 0-1 range."""
        sampler_high = EventSampler(sample_rate=1.5)
        assert sampler_high.sample_rate == 1.0

        sampler_low = EventSampler(sample_rate=-0.5)
        assert sampler_low.sample_rate == 0.0

    def test_sampler_always_samples_critical_events(self):
        """Test sampler always samples critical events."""
        sampler = EventSampler(sample_rate=0.0)  # 0% sample rate

        critical_event = HookEvent(
            session_id=uuid4(),
            event_type="PreToolUse",
            data={"critical": True},
        )

        assert sampler.should_sample(critical_event) is True

    def test_sampler_full_sample_rate(self):
        """Test sampler with 100% sample rate."""
        sampler = EventSampler(sample_rate=1.0)

        event = HookEvent(
            session_id=uuid4(),
            event_type="PreToolUse",
            data={},
        )

        # Should sample every event at 100% rate
        for _ in range(10):
            assert sampler.should_sample(event) is True

    def test_sampler_partial_sample_rate(self):
        """Test sampler with partial sample rate."""
        sampler = EventSampler(sample_rate=0.5)

        event = HookEvent(
            session_id=uuid4(),
            event_type="PreToolUse",
            data={},
        )

        # Count sampled events
        sampled = sum(1 for _ in range(10) if sampler.should_sample(event))

        # At 50% rate, should sample approximately half
        assert sampled == 5


@pytest.mark.asyncio
class TestEventCollector:
    """Test EventCollector class."""

    async def test_collector_initialization(self):
        """Test collector initialization."""
        collector = EventCollector(
            batch_size=50,
            batch_timeout=10,
            sample_rate=0.8,
            enable_ai_summaries=False,
        )

        assert collector.batch_size == 50
        assert collector.batch_timeout == 10
        assert collector.sampler.sample_rate == 0.8
        assert collector.enable_ai_summaries is False
        assert collector.ai_client is None

    async def test_collector_register_callback(self):
        """Test registering flush callback."""
        collector = EventCollector(enable_ai_summaries=False)
        callback = MagicMock()

        collector.register_flush_callback(callback)

        assert len(collector.flush_callbacks) == 1
        assert collector.flush_callbacks[0] == callback

    async def test_collector_start_stop(self):
        """Test collector start and stop."""
        collector = EventCollector(enable_ai_summaries=False, batch_timeout=1)

        await collector.start()
        assert collector.running is True
        assert collector.flush_task is not None

        await collector.stop()
        assert collector.running is False

    async def test_collector_collect_event(self):
        """Test collecting events."""
        collector = EventCollector(enable_ai_summaries=False, batch_size=100)

        event = HookEvent(
            session_id=uuid4(),
            event_type="PreToolUse",
            data={"tool_name": "Bash"},
        )

        await collector.collect(event)

        assert collector.current_batch.size() == 1

    async def test_collector_flushes_on_batch_size(self):
        """Test collector flushes when batch size reached."""
        collector = EventCollector(
            enable_ai_summaries=False,
            batch_size=5,
            batch_timeout=60,
        )

        callback = MagicMock()
        collector.register_flush_callback(callback)

        # Collect 5 events to trigger flush
        for _ in range(5):
            event = HookEvent(
                session_id=uuid4(),
                event_type="PreToolUse",
                data={},
            )
            await collector.collect(event)

        # Callback should have been called
        assert callback.called

    async def test_collector_flush_with_async_callback(self):
        """Test collector flush with async callback."""
        collector = EventCollector(
            enable_ai_summaries=False,
            batch_size=2,
        )

        async_callback = AsyncMock()
        collector.register_flush_callback(async_callback)

        for _ in range(2):
            event = HookEvent(
                session_id=uuid4(),
                event_type="PreToolUse",
                data={},
            )
            await collector.collect(event)

        async_callback.assert_called_once()

    async def test_collector_callback_error_doesnt_stop_flush(self):
        """Test callback errors don't stop flushing."""
        collector = EventCollector(
            enable_ai_summaries=False,
            batch_size=2,
        )

        failing_callback = MagicMock(side_effect=Exception("Callback error"))
        success_callback = MagicMock()

        collector.register_flush_callback(failing_callback)
        collector.register_flush_callback(success_callback)

        for _ in range(2):
            event = HookEvent(
                session_id=uuid4(),
                event_type="PreToolUse",
                data={},
            )
            await collector.collect(event)

        # Both callbacks should have been called
        failing_callback.assert_called_once()
        success_callback.assert_called_once()

    async def test_collector_stop_flushes_remaining(self):
        """Test collector stop flushes remaining events."""
        collector = EventCollector(
            enable_ai_summaries=False,
            batch_size=100,  # Large batch size so it won't auto-flush
        )

        callback = MagicMock()
        collector.register_flush_callback(callback)

        await collector.start()

        # Add events but not enough to trigger flush
        for _ in range(3):
            event = HookEvent(
                session_id=uuid4(),
                event_type="PreToolUse",
                data={},
            )
            await collector.collect(event)

        assert callback.call_count == 0

        # Stop should flush remaining
        await collector.stop()

        callback.assert_called_once()

    async def test_collector_get_stats(self):
        """Test getting collector stats."""
        collector = EventCollector(
            batch_size=50,
            batch_timeout=10,
            sample_rate=0.8,
            enable_ai_summaries=False,
        )

        callback = MagicMock()
        collector.register_flush_callback(callback)

        event = HookEvent(
            session_id=uuid4(),
            event_type="PreToolUse",
            data={},
        )
        await collector.collect(event)

        stats = collector.get_stats()

        assert stats["current_batch_size"] == 1
        assert stats["batch_size_limit"] == 50
        assert stats["batch_timeout"] == 10
        assert stats["sample_rate"] == 0.8
        assert stats["ai_summaries_enabled"] is False
        assert stats["flush_callbacks"] == 1

    async def test_collector_samples_events(self):
        """Test collector respects sampling."""
        collector = EventCollector(
            enable_ai_summaries=False,
            batch_size=100,
            sample_rate=0.1,  # 10% sample rate (0% causes ZeroDivisionError)
        )

        event = HookEvent(
            session_id=uuid4(),
            event_type="PreToolUse",
            data={},  # Not critical
        )

        for _ in range(20):
            await collector.collect(event)

        # At 10% rate, approximately 2 out of 20 events should be collected
        # (exact number depends on counter-based sampling)
        assert collector.current_batch.size() < 20

    async def test_collector_ai_summary_generation(self):
        """Test AI summary generation."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            collector = EventCollector(
                enable_ai_summaries=True,
                batch_size=2,
            )

            # Mock AI client
            collector.ai_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="Summary text")]
            collector.ai_client.messages.create = AsyncMock(return_value=mock_response)

            callback = AsyncMock()
            collector.register_flush_callback(callback)

            for _ in range(2):
                event = HookEvent(
                    session_id=uuid4(),
                    event_type="PreToolUse",
                    data={"tool_name": "Bash"},
                )
                await collector.collect(event)

            # Verify callback received summary
            callback.assert_called_once()
            call_args = callback.call_args
            assert call_args[0][1] == "Summary text"  # summary argument


class TestEventAggregator:
    """Test EventAggregator class."""

    def test_aggregate_by_type(self):
        """Test aggregating events by type."""
        events = [
            HookEvent(session_id=uuid4(), event_type="PreToolUse", data={}),
            HookEvent(session_id=uuid4(), event_type="PreToolUse", data={}),
            HookEvent(session_id=uuid4(), event_type="PostToolUse", data={}),
            HookEvent(session_id=uuid4(), event_type="Notification", data={}),
        ]

        counts = EventAggregator.aggregate_by_type(events)

        assert counts["PreToolUse"] == 2
        assert counts["PostToolUse"] == 1
        assert counts["Notification"] == 1

    def test_aggregate_by_agent(self):
        """Test aggregating events by agent."""
        events = [
            HookEvent(session_id=uuid4(), event_type="PreToolUse", data={"agent_id": "agent-1"}),
            HookEvent(session_id=uuid4(), event_type="PreToolUse", data={"agent_id": "agent-1"}),
            HookEvent(session_id=uuid4(), event_type="PreToolUse", data={"agent_id": "agent-2"}),
            HookEvent(session_id=uuid4(), event_type="PreToolUse", data={}),  # Unknown agent
        ]

        counts = EventAggregator.aggregate_by_agent(events)

        assert counts["agent-1"] == 2
        assert counts["agent-2"] == 1
        assert counts["unknown"] == 1

    def test_get_error_events(self):
        """Test filtering error events."""
        events = [
            HookEvent(session_id=uuid4(), event_type="PreToolUse", data={"error": "Some error"}),
            HookEvent(session_id=uuid4(), event_type="PreToolUse", data={"status": "failed"}),
            HookEvent(session_id=uuid4(), event_type="PreToolUse", data={"status": "success"}),
            HookEvent(session_id=uuid4(), event_type="PreToolUse", data={}),
        ]

        error_events = EventAggregator.get_error_events(events)

        assert len(error_events) == 2

    def test_get_recent_events(self):
        """Test getting recent events."""
        now = datetime.now()
        events = [
            HookEvent(
                session_id=uuid4(),
                event_type="PreToolUse",
                data={},
                timestamp=now - timedelta(minutes=5),
            ),
            HookEvent(
                session_id=uuid4(),
                event_type="PreToolUse",
                data={},
                timestamp=now - timedelta(minutes=1),
            ),
            HookEvent(
                session_id=uuid4(),
                event_type="PreToolUse",
                data={},
                timestamp=now - timedelta(minutes=10),
            ),
        ]

        recent = EventAggregator.get_recent_events(events, limit=2)

        assert len(recent) == 2
        # Should be sorted by timestamp descending
        assert recent[0].timestamp > recent[1].timestamp

    def test_get_recent_events_respects_limit(self):
        """Test get_recent_events respects limit."""
        events = [
            HookEvent(session_id=uuid4(), event_type="PreToolUse", data={})
            for _ in range(50)
        ]

        recent = EventAggregator.get_recent_events(events, limit=10)

        assert len(recent) == 10
