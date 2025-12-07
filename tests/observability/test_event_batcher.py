"""Tests for event batching."""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from iccc.models.entities import HookEvent
from iccc.observability.event_batcher import (
    Batch,
    EventBatcher,
    PriorityBatcher,
    RetentionManager,
)


@pytest.fixture
def sample_event():
    """Create a sample event."""
    return HookEvent(
        id=uuid4(),
        session_id=uuid4(),
        event_type="PostToolUse",
        timestamp=datetime.now(),
        data={"tool_name": "Write", "status": "success"},
    )


@pytest.fixture
def error_event():
    """Create an error event."""
    return HookEvent(
        id=uuid4(),
        session_id=uuid4(),
        event_type="Error",
        timestamp=datetime.now(),
        data={"error": "Connection failed"},
    )


class TestBatch:
    """Tests for Batch dataclass."""

    def test_batch_creation(self):
        """Test batch creation."""
        batch = Batch()

        assert batch.size() == 0
        assert batch.is_empty() is True

    def test_batch_age(self):
        """Test batch age calculation."""
        batch = Batch()

        age = batch.age_seconds()

        assert age >= 0
        assert age < 1  # Should be very recent


class TestEventBatcher:
    """Tests for EventBatcher."""

    def test_initialization(self):
        """Test batcher initialization."""
        batcher = EventBatcher(
            max_batch_size=50,
            flush_interval_seconds=10.0,
        )

        assert batcher.max_batch_size == 50
        assert batcher.flush_interval_seconds == 10.0

    def test_add_event(self, sample_event):
        """Test adding single event."""
        batcher = EventBatcher()

        batcher.add_event(sample_event)

        assert batcher._current_batch.size() == 1
        assert batcher.stats.total_events_received == 1

    def test_add_events(self, sample_event):
        """Test adding multiple events."""
        batcher = EventBatcher()

        batcher.add_events([sample_event, sample_event, sample_event])

        assert batcher._current_batch.size() == 3

    def test_auto_finalize_on_max_size(self, sample_event):
        """Test that batch is finalized when max size reached."""
        batcher = EventBatcher(max_batch_size=5)

        for _ in range(6):
            batcher.add_event(sample_event)

        # First batch should be finalized and in pending
        assert len(batcher._pending_batches) == 1
        assert batcher._current_batch.size() == 1

    def test_force_flush(self, sample_event):
        """Test force flush."""
        batcher = EventBatcher()
        batcher.add_event(sample_event)

        batcher.force_flush()

        assert len(batcher._pending_batches) == 1
        assert batcher._current_batch.is_empty()

    @pytest.mark.asyncio
    async def test_flush_batch(self, sample_event):
        """Test flushing batches."""
        batcher = EventBatcher(max_batch_size=5)

        # Add events and force finalize
        for _ in range(5):
            batcher.add_event(sample_event)

        # Flush
        flushed = await batcher.flush_batch()

        assert flushed == 5
        assert len(batcher._pending_batches) == 0
        assert batcher.stats.total_batches_flushed == 1

    @pytest.mark.asyncio
    async def test_flush_callback(self, sample_event):
        """Test flush callbacks are called."""
        batcher = EventBatcher(max_batch_size=5)

        callback_called = False
        received_events = []

        async def callback(events):
            nonlocal callback_called, received_events
            callback_called = True
            received_events = events

        batcher.register_callback(callback)

        # Add and flush
        for _ in range(5):
            batcher.add_event(sample_event)
        await batcher.flush_batch()

        assert callback_called is True
        assert len(received_events) == 5

    @pytest.mark.asyncio
    async def test_sync_callback(self, sample_event):
        """Test sync callbacks work too."""
        batcher = EventBatcher(max_batch_size=5)

        callback_called = False

        def sync_callback(events):
            nonlocal callback_called
            callback_called = True

        batcher.register_callback(sync_callback)

        for _ in range(5):
            batcher.add_event(sample_event)
        await batcher.flush_batch()

        assert callback_called is True

    def test_unregister_callback(self):
        """Test unregistering callback."""
        batcher = EventBatcher()

        def callback(events):
            pass

        batcher.register_callback(callback)
        assert len(batcher._flush_callbacks) == 1

        batcher.unregister_callback(callback)
        assert len(batcher._flush_callbacks) == 0

    @pytest.mark.asyncio
    async def test_start_stop(self, sample_event):
        """Test start and stop lifecycle."""
        batcher = EventBatcher(flush_interval_seconds=0.1)

        await batcher.start()
        assert batcher._running is True
        assert batcher._flush_task is not None

        batcher.add_event(sample_event)

        await batcher.stop()
        assert batcher._running is False

        # Events should have been flushed
        assert batcher.stats.total_events_flushed == 1

    def test_get_stats(self, sample_event):
        """Test statistics retrieval."""
        batcher = EventBatcher()
        batcher.add_event(sample_event)

        stats = batcher.get_stats()

        assert stats["total_events_received"] == 1
        assert stats["current_batch_size"] == 1
        assert "pending_batches" in stats

    def test_max_pending_batches(self, sample_event):
        """Test max pending batches limit."""
        batcher = EventBatcher(max_batch_size=1, max_pending_batches=3)

        # Add 5 events (each creates a batch)
        for _ in range(5):
            batcher.add_event(sample_event)

        # Should only keep 3 pending batches
        assert len(batcher._pending_batches) <= 3


class TestPriorityBatcher:
    """Tests for PriorityBatcher."""

    def test_initialization(self):
        """Test priority batcher initialization."""
        batcher = PriorityBatcher()

        assert "Error" in batcher.priority_event_types
        assert "Stop" in batcher.priority_event_types

    def test_priority_event_immediate_queue(self, error_event):
        """Test that priority events are queued immediately."""
        batcher = PriorityBatcher(max_batch_size=100)

        batcher.add_event(error_event)

        # Should be in pending batches immediately
        assert len(batcher._pending_batches) == 1

    def test_normal_event_batched(self, sample_event):
        """Test that normal events are batched normally."""
        batcher = PriorityBatcher(max_batch_size=100)

        batcher.add_event(sample_event)

        # Should be in current batch, not pending
        assert len(batcher._pending_batches) == 0
        assert batcher._current_batch.size() == 1

    def test_critical_flag_is_priority(self, sample_event):
        """Test that critical flag marks event as priority."""
        batcher = PriorityBatcher(max_batch_size=100)

        critical_event = HookEvent(
            id=uuid4(),
            session_id=uuid4(),
            event_type="PostToolUse",
            timestamp=datetime.now(),
            data={"critical": True},
        )

        batcher.add_event(critical_event)

        assert len(batcher._pending_batches) == 1

    def test_custom_priority_types(self, sample_event):
        """Test custom priority event types."""
        batcher = PriorityBatcher(
            priority_event_types={"CustomPriority"},
            max_batch_size=100,
        )

        priority_event = HookEvent(
            id=uuid4(),
            session_id=uuid4(),
            event_type="CustomPriority",
            timestamp=datetime.now(),
            data={},
        )

        batcher.add_event(priority_event)

        assert len(batcher._pending_batches) == 1


class TestRetentionManager:
    """Tests for RetentionManager."""

    def test_initialization(self):
        """Test retention manager initialization."""
        manager = RetentionManager(retention_days=14)

        assert manager.retention_days == 14
        assert manager.cleanup_interval_hours == 24

    @pytest.mark.asyncio
    async def test_cleanup_callback(self):
        """Test cleanup callback is called."""
        manager = RetentionManager(retention_days=7)

        callback_called = False
        cutoff_received = None

        async def cleanup_callback(cutoff):
            nonlocal callback_called, cutoff_received
            callback_called = True
            cutoff_received = cutoff
            return 100  # 100 events deleted

        manager.register_cleanup_callback(cleanup_callback)

        deleted = await manager.cleanup()

        assert callback_called is True
        assert cutoff_received is not None
        assert deleted == 100
        assert manager._total_deleted == 100

    @pytest.mark.asyncio
    async def test_cleanup_multiple_callbacks(self):
        """Test multiple cleanup callbacks."""
        manager = RetentionManager()

        async def callback1(cutoff):
            return 50

        async def callback2(cutoff):
            return 30

        manager.register_cleanup_callback(callback1)
        manager.register_cleanup_callback(callback2)

        deleted = await manager.cleanup()

        assert deleted == 80

    @pytest.mark.asyncio
    async def test_cleanup_error_handling(self):
        """Test cleanup handles errors gracefully."""
        manager = RetentionManager()

        async def failing_callback(cutoff):
            raise Exception("Database error")

        async def working_callback(cutoff):
            return 10

        manager.register_cleanup_callback(failing_callback)
        manager.register_cleanup_callback(working_callback)

        # Should not raise, and should still count working callback
        deleted = await manager.cleanup()

        assert deleted == 10

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Test start and stop lifecycle."""
        manager = RetentionManager(cleanup_interval_hours=24)

        await manager.start()
        assert manager._running is True
        assert manager._cleanup_task is not None

        await manager.stop()
        assert manager._running is False

    def test_get_stats(self):
        """Test statistics retrieval."""
        manager = RetentionManager(retention_days=7)

        stats = manager.get_stats()

        assert stats["retention_days"] == 7
        assert stats["cleanup_interval_hours"] == 24
        assert stats["total_deleted"] == 0
