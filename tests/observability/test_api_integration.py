"""Integration tests for observability API endpoints."""

import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from litestar.testing import AsyncTestClient

from iccc.models.entities import HookEvent
from iccc.observability.storage import InMemoryEventStorage


def create_test_app():
    """Create app for testing (avoid import-time app creation)."""
    from iccc.api.app import create_app

    return create_app(enable_auth=False, enable_rate_limit=False)


@pytest.mark.asyncio
async def test_get_events_endpoint() -> None:
    """Test the GET /observability/events endpoint."""
    app = create_test_app()

    async with AsyncTestClient(app=app) as client:
        # Get events (should be empty initially)
        response = await client.get("/observability/events")
        assert response.status_code == 200

        data = response.json()
        assert "events" in data
        assert "pagination" in data
        assert "stats" in data
        assert isinstance(data["events"], list)


@pytest.mark.asyncio
async def test_get_events_with_filters() -> None:
    """Test the GET /observability/events endpoint with filters."""
    app = create_test_app()

    async with AsyncTestClient(app=app) as client:
        # Test with session_id filter
        session_id = uuid4()
        response = await client.get(f"/observability/events?session_id={session_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["filters"]["session_id"] == str(session_id)

        # Test with event_type filter
        response = await client.get("/observability/events?event_type=pre_tool_use")
        assert response.status_code == 200

        data = response.json()
        assert data["filters"]["event_type"] == "pre_tool_use"

        # Test with limit and offset
        response = await client.get("/observability/events?limit=50&offset=10")
        assert response.status_code == 200

        data = response.json()
        assert data["pagination"]["limit"] == 50
        assert data["pagination"]["offset"] == 10


@pytest.mark.asyncio
async def test_get_stats_endpoint() -> None:
    """Test the GET /observability/stats endpoint."""
    app = create_test_app()

    async with AsyncTestClient(app=app) as client:
        response = await client.get("/observability/stats")
        assert response.status_code == 200

        data = response.json()
        assert "current_batch_size" in data
        assert "batch_size_limit" in data
        assert "batch_timeout" in data
        assert "sample_rate" in data
        assert "storage_enabled" in data


@pytest.mark.asyncio
async def test_websocket_stream() -> None:
    """Test the WebSocket /observability/stream endpoint."""
    app = create_test_app()

    async with AsyncTestClient(app=app) as client:
        # Connect to WebSocket
        async with client.websocket_connect("/observability/stream") as ws:
            # Should receive welcome message
            welcome = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
            assert welcome["type"] == "connected"
            assert "timestamp" in welcome

            # Send ping
            await ws.send_json({"type": "ping"})

            # Should receive pong
            pong = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
            assert pong["type"] == "pong"
            assert "timestamp" in pong


@pytest.mark.asyncio
async def test_event_collection_and_retrieval() -> None:
    """Test full flow: collect events, query them via API."""
    # This test demonstrates the full integration
    from iccc.observability.collector import EventCollector

    # Create in-memory storage
    storage = InMemoryEventStorage()
    await storage.connect()

    # Create collector with storage
    collector = EventCollector(
        batch_size=10,
        batch_timeout=1,
        enable_ai_summaries=False,
        storage=storage,
    )
    await collector.start()

    # Collect some events
    session_id = uuid4()
    events = [
        HookEvent(
            session_id=session_id,
            event_type="pre_tool_use",
            timestamp=datetime.now(),
            data={"tool": "bash", "command": "ls"},
        ),
        HookEvent(
            session_id=session_id,
            event_type="post_tool_use",
            timestamp=datetime.now(),
            data={"tool": "bash", "result": "success"},
        ),
    ]

    for event in events:
        await collector.collect(event)

    # Force flush
    await collector.stop()

    # Query events
    retrieved_events = await collector.query_events(session_id=session_id)
    assert len(retrieved_events) == 2
    assert all(e.session_id == session_id for e in retrieved_events)

    # Count events
    count = await collector.count_events(session_id=session_id)
    assert count == 2

    # Cleanup
    await storage.disconnect()


@pytest.mark.asyncio
async def test_pagination_works_correctly() -> None:
    """Test that pagination returns correct results."""
    from iccc.observability.collector import EventCollector

    # Create storage with many events
    storage = InMemoryEventStorage()
    await storage.connect()

    # Store 50 events
    events = [
        HookEvent(
            session_id=uuid4(),
            event_type="test",
            timestamp=datetime.now() - timedelta(seconds=i),
            data={"index": i},
        )
        for i in range(50)
    ]
    await storage.store_events(events)

    # Create collector
    collector = EventCollector(storage=storage, enable_ai_summaries=False)

    # Test pagination
    page1 = await collector.query_events(limit=20, offset=0)
    assert len(page1) == 20

    page2 = await collector.query_events(limit=20, offset=20)
    assert len(page2) == 20

    page3 = await collector.query_events(limit=20, offset=40)
    assert len(page3) == 10

    # Verify no overlap
    page1_ids = {e.id for e in page1}
    page2_ids = {e.id for e in page2}
    page3_ids = {e.id for e in page3}

    assert page1_ids.isdisjoint(page2_ids)
    assert page2_ids.isdisjoint(page3_ids)
    assert page1_ids.isdisjoint(page3_ids)

    await storage.disconnect()
