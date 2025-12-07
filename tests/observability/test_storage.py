"""Tests for event storage backends."""

import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from iccc.models.entities import HookEvent
from iccc.observability.storage import InMemoryEventStorage, MongoDBEventStorage


class TestInMemoryEventStorage:
    """Tests for InMemoryEventStorage."""

    @pytest.fixture
    async def storage(self) -> InMemoryEventStorage:
        """Create in-memory storage instance."""
        storage = InMemoryEventStorage(max_events=100)
        await storage.connect()
        yield storage
        await storage.disconnect()

    @pytest.fixture
    def sample_events(self) -> list[HookEvent]:
        """Create sample events for testing."""
        session_id = uuid4()
        return [
            HookEvent(
                session_id=session_id,
                event_type="pre_tool_use",
                timestamp=datetime.now() - timedelta(minutes=10),
                data={"tool": "bash", "args": ["ls"]},
            ),
            HookEvent(
                session_id=session_id,
                event_type="post_tool_use",
                timestamp=datetime.now() - timedelta(minutes=9),
                data={"tool": "bash", "result": "success"},
            ),
            HookEvent(
                session_id=uuid4(),
                event_type="notification",
                timestamp=datetime.now() - timedelta(minutes=5),
                data={"message": "Task started"},
            ),
        ]

    @pytest.mark.asyncio
    async def test_store_and_query_events(self, storage: InMemoryEventStorage, sample_events: list[HookEvent]) -> None:
        """Test storing and querying events."""
        # Store events
        await storage.store_events(sample_events)

        # Query all events
        events = await storage.query_events()
        assert len(events) == 3

        # Verify events are sorted by timestamp descending
        assert events[0].timestamp >= events[1].timestamp >= events[2].timestamp

    @pytest.mark.asyncio
    async def test_filter_by_session_id(self, storage: InMemoryEventStorage, sample_events: list[HookEvent]) -> None:
        """Test filtering by session ID."""
        await storage.store_events(sample_events)

        # Filter by first session
        session_id = sample_events[0].session_id
        events = await storage.query_events(session_id=session_id)

        assert len(events) == 2
        assert all(e.session_id == session_id for e in events)

    @pytest.mark.asyncio
    async def test_filter_by_event_type(self, storage: InMemoryEventStorage, sample_events: list[HookEvent]) -> None:
        """Test filtering by event type."""
        await storage.store_events(sample_events)

        # Filter by event type
        events = await storage.query_events(event_type="pre_tool_use")

        assert len(events) == 1
        assert events[0].event_type == "pre_tool_use"

    @pytest.mark.asyncio
    async def test_filter_by_time_range(self, storage: InMemoryEventStorage, sample_events: list[HookEvent]) -> None:
        """Test filtering by time range."""
        await storage.store_events(sample_events)

        # Filter events in last 7 minutes
        start_time = datetime.now() - timedelta(minutes=7)
        events = await storage.query_events(start_time=start_time)

        assert len(events) == 1
        assert events[0].event_type == "notification"

    @pytest.mark.asyncio
    async def test_pagination(self, storage: InMemoryEventStorage, sample_events: list[HookEvent]) -> None:
        """Test pagination with limit and offset."""
        await storage.store_events(sample_events)

        # Get first page
        page1 = await storage.query_events(limit=2, offset=0)
        assert len(page1) == 2

        # Get second page
        page2 = await storage.query_events(limit=2, offset=2)
        assert len(page2) == 1

        # Verify no overlap
        page1_ids = {e.id for e in page1}
        page2_ids = {e.id for e in page2}
        assert page1_ids.isdisjoint(page2_ids)

    @pytest.mark.asyncio
    async def test_count_events(self, storage: InMemoryEventStorage, sample_events: list[HookEvent]) -> None:
        """Test counting events with filters."""
        await storage.store_events(sample_events)

        # Count all events
        total = await storage.count_events()
        assert total == 3

        # Count by session
        session_id = sample_events[0].session_id
        count = await storage.count_events(session_id=session_id)
        assert count == 2

        # Count by type
        count = await storage.count_events(event_type="pre_tool_use")
        assert count == 1

    @pytest.mark.asyncio
    async def test_delete_old_events(self, storage: InMemoryEventStorage, sample_events: list[HookEvent]) -> None:
        """Test deleting old events."""
        await storage.store_events(sample_events)

        # Delete events older than 6 minutes
        cutoff = datetime.now() - timedelta(minutes=6)
        deleted = await storage.delete_old_events(cutoff)

        assert deleted == 2

        # Verify only recent event remains
        events = await storage.query_events()
        assert len(events) == 1
        assert events[0].event_type == "notification"

    @pytest.mark.asyncio
    async def test_max_events_limit(self, storage: InMemoryEventStorage) -> None:
        """Test that storage respects max_events limit."""
        # Create more events than max_events (100)
        events = [
            HookEvent(
                session_id=uuid4(),
                event_type="test",
                timestamp=datetime.now(),
                data={"index": i},
            )
            for i in range(150)
        ]

        await storage.store_events(events)

        # Verify only last 100 are kept
        stored = await storage.query_events(limit=200)
        assert len(stored) == 100

        # Verify most recent are kept
        assert stored[0].data["index"] == 149


class TestMongoDBEventStorage:
    """Tests for MongoDBEventStorage."""

    @pytest.fixture
    async def storage(self) -> MongoDBEventStorage:
        """
        Create MongoDB storage instance.

        Note: This requires a running MongoDB instance.
        Tests will be skipped if connection fails.
        """
        storage = MongoDBEventStorage(collection_name="test_hook_events")
        try:
            await storage.connect()
            # Clean up any existing test data
            await storage.collection.delete_many({})
            yield storage
            # Clean up after tests
            await storage.collection.delete_many({})
            await storage.disconnect()
        except Exception as e:
            pytest.skip(f"MongoDB not available: {e}")

    @pytest.fixture
    def sample_events(self) -> list[HookEvent]:
        """Create sample events for testing."""
        session_id = uuid4()
        return [
            HookEvent(
                session_id=session_id,
                event_type="pre_tool_use",
                timestamp=datetime.now() - timedelta(minutes=10),
                data={"tool": "bash", "args": ["ls"]},
            ),
            HookEvent(
                session_id=session_id,
                event_type="post_tool_use",
                timestamp=datetime.now() - timedelta(minutes=9),
                data={"tool": "bash", "result": "success"},
            ),
            HookEvent(
                session_id=uuid4(),
                event_type="notification",
                timestamp=datetime.now() - timedelta(minutes=5),
                data={"message": "Task started"},
            ),
        ]

    @pytest.mark.asyncio
    async def test_store_and_query_events(self, storage: MongoDBEventStorage, sample_events: list[HookEvent]) -> None:
        """Test storing and querying events in MongoDB."""
        # Store events
        await storage.store_events(sample_events)

        # Give MongoDB a moment to index
        await asyncio.sleep(0.1)

        # Query all events
        events = await storage.query_events()
        assert len(events) == 3

        # Verify event structure
        assert all(isinstance(e, HookEvent) for e in events)

    @pytest.mark.asyncio
    async def test_filter_by_session_id(self, storage: MongoDBEventStorage, sample_events: list[HookEvent]) -> None:
        """Test filtering by session ID in MongoDB."""
        await storage.store_events(sample_events)
        await asyncio.sleep(0.1)

        # Filter by session
        session_id = sample_events[0].session_id
        events = await storage.query_events(session_id=session_id)

        assert len(events) == 2
        assert all(e.session_id == session_id for e in events)

    @pytest.mark.asyncio
    async def test_filter_by_event_type(self, storage: MongoDBEventStorage, sample_events: list[HookEvent]) -> None:
        """Test filtering by event type in MongoDB."""
        await storage.store_events(sample_events)
        await asyncio.sleep(0.1)

        # Filter by type
        events = await storage.query_events(event_type="pre_tool_use")

        assert len(events) == 1
        assert events[0].event_type == "pre_tool_use"

    @pytest.mark.asyncio
    async def test_pagination(self, storage: MongoDBEventStorage, sample_events: list[HookEvent]) -> None:
        """Test pagination in MongoDB."""
        await storage.store_events(sample_events)
        await asyncio.sleep(0.1)

        # Get first page
        page1 = await storage.query_events(limit=2, offset=0)
        assert len(page1) == 2

        # Get second page
        page2 = await storage.query_events(limit=2, offset=2)
        assert len(page2) == 1

    @pytest.mark.asyncio
    async def test_count_events(self, storage: MongoDBEventStorage, sample_events: list[HookEvent]) -> None:
        """Test counting events in MongoDB."""
        await storage.store_events(sample_events)
        await asyncio.sleep(0.1)

        # Count all
        total = await storage.count_events()
        assert total == 3

        # Count by filter
        session_id = sample_events[0].session_id
        count = await storage.count_events(session_id=session_id)
        assert count == 2

    @pytest.mark.asyncio
    async def test_delete_old_events(self, storage: MongoDBEventStorage, sample_events: list[HookEvent]) -> None:
        """Test deleting old events from MongoDB."""
        await storage.store_events(sample_events)
        await asyncio.sleep(0.1)

        # Delete old events
        cutoff = datetime.now() - timedelta(minutes=6)
        deleted = await storage.delete_old_events(cutoff)

        assert deleted == 2

        # Verify only recent event remains
        events = await storage.query_events()
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_concurrent_storage(self, storage: MongoDBEventStorage) -> None:
        """Test concurrent event storage."""
        # Create multiple batches
        batches = [
            [
                HookEvent(
                    session_id=uuid4(),
                    event_type="test",
                    timestamp=datetime.now(),
                    data={"batch": i, "event": j},
                )
                for j in range(10)
            ]
            for i in range(5)
        ]

        # Store concurrently
        await asyncio.gather(*[storage.store_events(batch) for batch in batches])

        await asyncio.sleep(0.1)

        # Verify all stored
        total = await storage.count_events()
        assert total == 50


@pytest.mark.asyncio
async def test_storage_graceful_degradation() -> None:
    """Test that storage failures don't crash the system."""
    from iccc.observability.collector import EventCollector

    # Create collector with storage that will fail
    class FailingStorage:
        async def connect(self) -> None:
            pass

        async def disconnect(self) -> None:
            pass

        async def store_events(self, events: list[HookEvent]) -> None:
            raise Exception("Storage failed!")

        async def query_events(self, **kwargs) -> list[HookEvent]:
            return []

        async def count_events(self, **kwargs) -> int:
            return 0

    storage = FailingStorage()
    collector = EventCollector(storage=storage)
    await collector.start()

    # This should not raise even though storage fails
    event = HookEvent(
        session_id=uuid4(),
        event_type="test",
        timestamp=datetime.now(),
        data={},
    )

    await collector.collect(event)
    await collector.stop()

    # Collector should continue working
    assert collector.running is False
