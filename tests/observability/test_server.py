"""Tests for observability server."""

import json
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from iccc.models.entities import HookEvent

# Try to import litestar-dependent modules
try:
    from iccc.observability.server import EventStore
    LITESTAR_AVAILABLE = True
except ImportError:
    LITESTAR_AVAILABLE = False
    EventStore = None


pytestmark = pytest.mark.skipif(
    not LITESTAR_AVAILABLE, reason="litestar not installed"
)


class TestEventStore:
    """Test EventStore class."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield str(Path(tmpdir) / "test_events.db")

    def test_event_store_initialization(self, temp_db_path):
        """Test EventStore initialization."""
        store = EventStore(db_path=temp_db_path)
        assert store.db_path == temp_db_path
        assert store.conn is None

    def test_event_store_connect(self, temp_db_path):
        """Test connecting to database."""
        store = EventStore(db_path=temp_db_path)
        store.connect()

        assert store.conn is not None

        # Verify tables were created
        cursor = store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
        )
        assert cursor.fetchone() is not None

        store.disconnect()

    def test_event_store_disconnect(self, temp_db_path):
        """Test disconnecting from database."""
        store = EventStore(db_path=temp_db_path)
        store.connect()
        store.disconnect()

        # Connection should be closed (trying to use it would raise)
        # We just verify no exception during disconnect

    def test_event_store_insert_events(self, temp_db_path):
        """Test inserting events."""
        store = EventStore(db_path=temp_db_path)
        store.connect()

        events = [
            HookEvent(
                session_id=uuid4(),
                event_type="PreToolUse",
                data={"tool_name": "Bash"},
            ),
            HookEvent(
                session_id=uuid4(),
                event_type="PostToolUse",
                data={"tool_name": "Read"},
            ),
        ]

        store.insert_events(events, ai_summary="Test summary")

        # Verify events were inserted
        cursor = store.conn.execute("SELECT COUNT(*) FROM events")
        count = cursor.fetchone()[0]
        assert count == 2

        store.disconnect()

    def test_event_store_insert_events_no_connection(self, temp_db_path):
        """Test inserting events without connection does nothing."""
        store = EventStore(db_path=temp_db_path)

        events = [
            HookEvent(
                session_id=uuid4(),
                event_type="PreToolUse",
                data={},
            )
        ]

        # Should not raise
        store.insert_events(events)

    def test_event_store_get_recent_events(self, temp_db_path):
        """Test getting recent events."""
        store = EventStore(db_path=temp_db_path)
        store.connect()

        # Insert events
        events = [
            HookEvent(
                session_id=uuid4(),
                event_type="PreToolUse",
                data={"tool_name": "Bash"},
            ),
            HookEvent(
                session_id=uuid4(),
                event_type="PostToolUse",
                data={"tool_name": "Read"},
            ),
        ]
        store.insert_events(events, ai_summary="Test summary")

        # Get recent events
        recent = store.get_recent_events(limit=10)

        assert len(recent) == 2
        assert recent[0]["event_type"] in ["PreToolUse", "PostToolUse"]
        assert recent[0]["ai_summary"] == "Test summary"

        store.disconnect()

    def test_event_store_get_recent_events_no_connection(self, temp_db_path):
        """Test getting recent events without connection returns empty."""
        store = EventStore(db_path=temp_db_path)

        events = store.get_recent_events()
        assert events == []

    def test_event_store_get_events_by_session(self, temp_db_path):
        """Test getting events by session."""
        store = EventStore(db_path=temp_db_path)
        store.connect()

        session_id = uuid4()

        # Insert events for specific session
        events = [
            HookEvent(
                session_id=session_id,
                event_type="PreToolUse",
                data={"tool_name": "Bash"},
            ),
            HookEvent(
                session_id=session_id,
                event_type="PostToolUse",
                data={"tool_name": "Read"},
            ),
            HookEvent(
                session_id=uuid4(),  # Different session
                event_type="PreToolUse",
                data={"tool_name": "Write"},
            ),
        ]
        store.insert_events(events)

        # Get events for specific session
        session_events = store.get_events_by_session(session_id)

        assert len(session_events) == 2
        for event in session_events:
            assert event["session_id"] == str(session_id)

        store.disconnect()

    def test_event_store_get_events_by_session_no_connection(self, temp_db_path):
        """Test getting session events without connection returns empty."""
        store = EventStore(db_path=temp_db_path)

        events = store.get_events_by_session(uuid4())
        assert events == []

    def test_event_store_get_stats(self, temp_db_path):
        """Test getting database stats."""
        store = EventStore(db_path=temp_db_path)
        store.connect()

        # Insert events of different types
        events = [
            HookEvent(session_id=uuid4(), event_type="PreToolUse", data={}),
            HookEvent(session_id=uuid4(), event_type="PreToolUse", data={}),
            HookEvent(session_id=uuid4(), event_type="PostToolUse", data={}),
            HookEvent(session_id=uuid4(), event_type="Notification", data={}),
        ]
        store.insert_events(events)

        stats = store.get_stats()

        assert stats["total_events"] == 4
        assert stats["event_types"]["PreToolUse"] == 2
        assert stats["event_types"]["PostToolUse"] == 1
        assert stats["event_types"]["Notification"] == 1

        store.disconnect()

    def test_event_store_get_stats_no_connection(self, temp_db_path):
        """Test getting stats without connection returns empty."""
        store = EventStore(db_path=temp_db_path)

        stats = store.get_stats()
        assert stats == {}

    def test_event_store_creates_directory(self):
        """Test EventStore creates parent directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "nested" / "dir" / "events.db")
            store = EventStore(db_path=db_path)

            # Directory should be created during init
            assert Path(db_path).parent.exists()

    def test_event_store_handles_empty_data(self, temp_db_path):
        """Test EventStore handles events with empty data."""
        store = EventStore(db_path=temp_db_path)
        store.connect()

        events = [
            HookEvent(
                session_id=uuid4(),
                event_type="PreToolUse",
                data={},
            )
        ]
        store.insert_events(events)

        recent = store.get_recent_events()
        assert len(recent) == 1
        assert recent[0]["data"] == {}

        store.disconnect()

    def test_event_store_respects_limit(self, temp_db_path):
        """Test EventStore respects limit parameter."""
        store = EventStore(db_path=temp_db_path)
        store.connect()

        # Insert 20 events
        events = [
            HookEvent(session_id=uuid4(), event_type="PreToolUse", data={})
            for _ in range(20)
        ]
        store.insert_events(events)

        # Get only 5
        recent = store.get_recent_events(limit=5)
        assert len(recent) == 5

        store.disconnect()

    def test_event_store_upsert_events(self, temp_db_path):
        """Test EventStore upserts events with same ID."""
        store = EventStore(db_path=temp_db_path)
        store.connect()

        event = HookEvent(
            session_id=uuid4(),
            event_type="PreToolUse",
            data={"version": 1},
        )

        # Insert first time
        store.insert_events([event])

        # Update data and insert again (same ID)
        event.data = {"version": 2}
        store.insert_events([event])

        # Should still be 1 event, but with updated data
        recent = store.get_recent_events()
        assert len(recent) == 1
        assert recent[0]["data"]["version"] == 2

        store.disconnect()


@pytest.mark.asyncio
class TestObservabilityAPIRoutes:
    """Test observability API route handlers."""

    async def test_index_route(self):
        """Test index route."""
        from iccc.observability.server import index

        result = await index()
        assert result["name"] == "iCCC Observability API"
        assert result["version"] == "0.1.0"
        assert result["docs"] == "/schema"

    async def test_health_route(self):
        """Test health route."""
        from iccc.observability.server import health

        result = await health()
        assert result["status"] == "healthy"
        assert "timestamp" in result

    async def test_get_events_route_no_store(self):
        """Test get events when store is None."""
        from iccc.observability import server

        # Temporarily set store to None
        original_store = server.event_store
        server.event_store = None

        try:
            result = await server.get_events()
            assert result["events"] == []
        finally:
            server.event_store = original_store

    async def test_get_events_route_with_store(self):
        """Test get events with store."""
        from iccc.observability import server

        # Create a mock store
        mock_store = MagicMock()
        mock_store.get_recent_events.return_value = [
            {
                "id": "test-id",
                "session_id": "session-1",
                "event_type": "PreToolUse",
                "timestamp": datetime.now().isoformat(),
                "data": {"tool_name": "Bash"},
                "ai_summary": None,
            }
        ]

        original_store = server.event_store
        server.event_store = mock_store

        try:
            result = await server.get_events(limit=50)
            assert result["count"] == 1
            assert len(result["events"]) == 1
            mock_store.get_recent_events.assert_called_once_with(50)
        finally:
            server.event_store = original_store

    async def test_get_session_events_route_no_store(self):
        """Test get session events when store is None."""
        from iccc.observability import server

        original_store = server.event_store
        server.event_store = None

        try:
            result = await server.get_session_events(uuid4())
            assert result["events"] == []
        finally:
            server.event_store = original_store

    async def test_get_session_events_route_with_store(self):
        """Test get session events with store."""
        from iccc.observability import server

        session_id = uuid4()
        mock_store = MagicMock()
        mock_store.get_events_by_session.return_value = [
            {
                "id": "test-id",
                "session_id": str(session_id),
                "event_type": "PreToolUse",
                "timestamp": datetime.now().isoformat(),
                "data": {},
                "ai_summary": None,
            }
        ]

        original_store = server.event_store
        server.event_store = mock_store

        try:
            result = await server.get_session_events(session_id, limit=25)
            assert result["count"] == 1
            mock_store.get_events_by_session.assert_called_once_with(session_id, 25)
        finally:
            server.event_store = original_store

    async def test_get_stats_route(self):
        """Test get stats route."""
        from iccc.observability import server

        # Mock both store and collector
        mock_store = MagicMock()
        mock_store.get_stats.return_value = {"total_events": 100}

        mock_collector = MagicMock()
        mock_collector.get_stats.return_value = {"current_batch_size": 5}

        original_store = server.event_store
        original_collector = server.event_collector
        server.event_store = mock_store
        server.event_collector = mock_collector

        try:
            result = await server.get_stats()
            assert result["storage"]["total_events"] == 100
            assert result["collector"]["current_batch_size"] == 5
        finally:
            server.event_store = original_store
            server.event_collector = original_collector

    async def test_get_stats_route_no_components(self):
        """Test get stats when components are None."""
        from iccc.observability import server

        original_store = server.event_store
        original_collector = server.event_collector
        server.event_store = None
        server.event_collector = None

        try:
            result = await server.get_stats()
            assert "storage" not in result
            assert "collector" not in result
        finally:
            server.event_store = original_store
            server.event_collector = original_collector
