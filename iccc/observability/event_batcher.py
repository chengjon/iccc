"""Event batching for efficient processing and storage."""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Callable, Coroutine

if TYPE_CHECKING:
    from iccc.models.entities import HookEvent


@dataclass
class Batch:
    """A batch of events for processing."""

    events: list[HookEvent] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    batch_id: int = 0

    def size(self) -> int:
        """Get number of events in batch."""
        return len(self.events)

    def is_empty(self) -> bool:
        """Check if batch is empty."""
        return len(self.events) == 0

    def age_seconds(self) -> float:
        """Get age of batch in seconds."""
        return (datetime.now() - self.created_at).total_seconds()


@dataclass
class BatcherStats:
    """Statistics for batching operations."""

    total_events_received: int = 0
    total_batches_flushed: int = 0
    total_events_flushed: int = 0
    flush_errors: int = 0
    avg_batch_size: float = 0.0
    last_flush_time: datetime | None = None

    def update_avg_batch_size(self, batch_size: int) -> None:
        """Update running average batch size."""
        if self.total_batches_flushed == 0:
            self.avg_batch_size = float(batch_size)
        else:
            # Exponential moving average
            self.avg_batch_size = 0.9 * self.avg_batch_size + 0.1 * batch_size


# Type alias for flush callbacks
FlushCallback = Callable[[list["HookEvent"]], Coroutine[Any, Any, None] | None]


class EventBatcher:
    """
    Batches events for efficient processing.

    Features:
    - Configurable batch size and timeout
    - Automatic periodic flushing
    - Multiple flush callbacks
    - Thread-safe operation
    - Statistics tracking
    """

    def __init__(
        self,
        max_batch_size: int = 100,
        flush_interval_seconds: float = 5.0,
        max_pending_batches: int = 10,
    ) -> None:
        """
        Initialize the event batcher.

        Args:
            max_batch_size: Maximum events per batch before auto-flush
            flush_interval_seconds: Maximum time before auto-flush
            max_pending_batches: Maximum pending batches before blocking
        """
        self.max_batch_size = max_batch_size
        self.flush_interval_seconds = flush_interval_seconds
        self.max_pending_batches = max_pending_batches

        # Current batch
        self._current_batch = Batch()
        self._batch_counter = 0

        # Pending batches ready for flush
        self._pending_batches: list[Batch] = []

        # Flush callbacks
        self._flush_callbacks: list[FlushCallback] = []

        # Thread safety
        self._lock = threading.RLock()

        # Background flusher
        self._flush_task: asyncio.Task[None] | None = None
        self._running = False

        # Statistics
        self.stats = BatcherStats()

    def add_event(self, event: HookEvent) -> None:
        """
        Add an event to the current batch.

        Args:
            event: Event to add
        """
        with self._lock:
            self.stats.total_events_received += 1
            self._current_batch.events.append(event)

            # Check if batch should be finalized
            if self._current_batch.size() >= self.max_batch_size:
                self._finalize_current_batch()

    def add_events(self, events: list[HookEvent]) -> None:
        """
        Add multiple events to the current batch.

        Args:
            events: Events to add
        """
        for event in events:
            self.add_event(event)

    def _finalize_current_batch(self) -> None:
        """Move current batch to pending and create new batch."""
        if self._current_batch.is_empty():
            return

        self._batch_counter += 1
        self._current_batch.batch_id = self._batch_counter
        self._pending_batches.append(self._current_batch)
        self._current_batch = Batch()

        # Warn if too many pending batches
        if len(self._pending_batches) > self.max_pending_batches:
            # Drop oldest batch
            dropped = self._pending_batches.pop(0)
            print(f"Warning: Dropped batch {dropped.batch_id} with {dropped.size()} events")

    async def flush_batch(self) -> int:
        """
        Flush pending batches to callbacks.

        Returns:
            Number of events flushed
        """
        batches_to_flush: list[Batch] = []

        with self._lock:
            # Check if current batch should be flushed (by age)
            if (
                not self._current_batch.is_empty()
                and self._current_batch.age_seconds() >= self.flush_interval_seconds
            ):
                self._finalize_current_batch()

            # Get all pending batches
            batches_to_flush = self._pending_batches.copy()
            self._pending_batches.clear()

        if not batches_to_flush:
            return 0

        # Combine all batches
        all_events: list[HookEvent] = []
        for batch in batches_to_flush:
            all_events.extend(batch.events)

        # Call flush callbacks
        for callback in self._flush_callbacks:
            try:
                result = callback(all_events)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                self.stats.flush_errors += 1
                print(f"Flush callback error: {e}")

        # Update stats
        events_flushed = len(all_events)
        self.stats.total_batches_flushed += len(batches_to_flush)
        self.stats.total_events_flushed += events_flushed
        self.stats.last_flush_time = datetime.now()
        self.stats.update_avg_batch_size(events_flushed // len(batches_to_flush) if batches_to_flush else 0)

        return events_flushed

    def register_callback(self, callback: FlushCallback) -> None:
        """
        Register a callback to be called on flush.

        Args:
            callback: Async or sync function taking list of events
        """
        self._flush_callbacks.append(callback)

    def unregister_callback(self, callback: FlushCallback) -> None:
        """
        Unregister a flush callback.

        Args:
            callback: Callback to remove
        """
        if callback in self._flush_callbacks:
            self._flush_callbacks.remove(callback)

    async def start(self) -> None:
        """Start the background flush task."""
        if self._running:
            return

        self._running = True
        self._flush_task = asyncio.create_task(self._periodic_flush())

    async def stop(self) -> None:
        """Stop the batcher and flush remaining events."""
        self._running = False

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Final flush
        with self._lock:
            if not self._current_batch.is_empty():
                self._finalize_current_batch()

        await self.flush_batch()

    async def _periodic_flush(self) -> None:
        """Background task for periodic flushing."""
        while self._running:
            await asyncio.sleep(self.flush_interval_seconds)
            await self.flush_batch()

    def get_stats(self) -> dict[str, Any]:
        """Get batching statistics."""
        with self._lock:
            return {
                "total_events_received": self.stats.total_events_received,
                "total_batches_flushed": self.stats.total_batches_flushed,
                "total_events_flushed": self.stats.total_events_flushed,
                "flush_errors": self.stats.flush_errors,
                "avg_batch_size": f"{self.stats.avg_batch_size:.1f}",
                "current_batch_size": self._current_batch.size(),
                "current_batch_age": f"{self._current_batch.age_seconds():.1f}s",
                "pending_batches": len(self._pending_batches),
                "callbacks_registered": len(self._flush_callbacks),
                "running": self._running,
                "last_flush": (
                    self.stats.last_flush_time.isoformat()
                    if self.stats.last_flush_time
                    else None
                ),
            }

    def force_flush(self) -> None:
        """Force finalize current batch for flushing."""
        with self._lock:
            self._finalize_current_batch()


class PriorityBatcher(EventBatcher):
    """
    Event batcher with priority support.

    High-priority events are flushed immediately,
    while normal events follow standard batching.
    """

    def __init__(
        self,
        priority_event_types: set[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialize priority batcher.

        Args:
            priority_event_types: Event types that should be flushed immediately
            **kwargs: Passed to parent EventBatcher
        """
        super().__init__(**kwargs)
        self.priority_event_types = priority_event_types or {
            "Error",
            "Stop",
            "SubagentStop",
        }

        # Separate queue for priority events
        self._priority_batch = Batch()

    def add_event(self, event: HookEvent) -> None:
        """
        Add an event, handling priority events specially.

        Args:
            event: Event to add
        """
        if self._is_priority(event):
            with self._lock:
                self.stats.total_events_received += 1
                self._priority_batch.events.append(event)

                # Immediately finalize priority batch if it has events
                if not self._priority_batch.is_empty():
                    self._batch_counter += 1
                    self._priority_batch.batch_id = self._batch_counter
                    self._pending_batches.insert(0, self._priority_batch)  # Insert at front
                    self._priority_batch = Batch()
        else:
            super().add_event(event)

    def _is_priority(self, event: HookEvent) -> bool:
        """Check if event is high priority."""
        if event.event_type in self.priority_event_types:
            return True
        if event.data.get("critical", False):
            return True
        if event.data.get("error"):
            return True
        return False


class RetentionManager:
    """
    Manages data retention for events.

    Features:
    - Configurable retention period
    - Automatic cleanup scheduling
    - Support for multiple storage backends
    """

    def __init__(
        self,
        retention_days: int = 7,
        cleanup_interval_hours: int = 24,
    ) -> None:
        """
        Initialize retention manager.

        Args:
            retention_days: Number of days to retain events
            cleanup_interval_hours: How often to run cleanup
        """
        self.retention_days = retention_days
        self.cleanup_interval_hours = cleanup_interval_hours

        self._cleanup_callbacks: list[Callable[[datetime], Coroutine[Any, Any, int]]] = []
        self._cleanup_task: asyncio.Task[None] | None = None
        self._running = False
        self._last_cleanup: datetime | None = None
        self._total_deleted = 0

    def register_cleanup_callback(
        self,
        callback: Callable[[datetime], Coroutine[Any, Any, int]],
    ) -> None:
        """
        Register a cleanup callback.

        Args:
            callback: Async function taking cutoff datetime, returns count deleted
        """
        self._cleanup_callbacks.append(callback)

    async def cleanup(self) -> int:
        """
        Run cleanup on all registered backends.

        Returns:
            Total number of events deleted
        """
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        total_deleted = 0

        for callback in self._cleanup_callbacks:
            try:
                deleted = await callback(cutoff)
                total_deleted += deleted
            except Exception as e:
                print(f"Cleanup callback error: {e}")

        self._last_cleanup = datetime.now()
        self._total_deleted += total_deleted
        return total_deleted

    async def start(self) -> None:
        """Start the background cleanup task."""
        if self._running:
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def stop(self) -> None:
        """Stop the retention manager."""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _periodic_cleanup(self) -> None:
        """Background task for periodic cleanup."""
        while self._running:
            await asyncio.sleep(self.cleanup_interval_hours * 3600)
            await self.cleanup()

    def get_stats(self) -> dict[str, Any]:
        """Get retention statistics."""
        return {
            "retention_days": self.retention_days,
            "cleanup_interval_hours": self.cleanup_interval_hours,
            "last_cleanup": (
                self._last_cleanup.isoformat() if self._last_cleanup else None
            ),
            "total_deleted": self._total_deleted,
            "callbacks_registered": len(self._cleanup_callbacks),
            "running": self._running,
        }
