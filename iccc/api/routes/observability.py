"""Observability API endpoints for events and monitoring."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from litestar import Controller, WebSocket, get, websocket
from litestar.di import Provide

from iccc.models.entities import HookEvent
from iccc.observability.collector import EventCollector
from iccc.observability.storage import MongoDBEventStorage

logger = logging.getLogger(__name__)

# Global collector instance and WebSocket connections
_event_collector: EventCollector | None = None
_websocket_connections: list[WebSocket] = []


async def get_or_create_collector() -> EventCollector:
    """Get or create the global EventCollector instance."""
    global _event_collector

    if _event_collector is None:
        # Create storage backend
        storage = MongoDBEventStorage()
        try:
            await storage.connect()
        except Exception as e:
            logger.warning(f"Failed to connect to MongoDB storage: {e}")
            # Use in-memory storage as fallback
            from iccc.observability.storage import InMemoryEventStorage

            storage = InMemoryEventStorage()
            await storage.connect()

        # Create collector with storage
        _event_collector = EventCollector(
            batch_size=100,
            batch_timeout=5,
            sample_rate=1.0,
            enable_ai_summaries=False,
            storage=storage,
        )

        # Register callback to broadcast events to WebSocket clients
        async def broadcast_to_websockets(events: list[HookEvent], summary: str | None = None) -> None:
            """Broadcast events to all connected WebSocket clients."""
            for event in events:
                await broadcast_event(event)

        _event_collector.register_flush_callback(broadcast_to_websockets)

        # Start collector
        await _event_collector.start()

    return _event_collector


async def broadcast_event(event: HookEvent) -> None:
    """Broadcast an event to all connected WebSocket clients."""
    # Remove disconnected clients
    disconnected = []
    for ws in _websocket_connections:
        try:
            await ws.send_json(
                {
                    "type": "event",
                    "event": event.model_dump(mode="json"),
                }
            )
        except Exception:
            disconnected.append(ws)

    # Clean up disconnected clients
    for ws in disconnected:
        _websocket_connections.remove(ws)


async def provide_event_collector() -> EventCollector:
    """Dependency injection for EventCollector."""
    return await get_or_create_collector()


class ObservabilityController(Controller):
    """Controller for observability and monitoring endpoints."""

    path = "/observability"
    tags = ["observability"]
    dependencies = {"collector": Provide(provide_event_collector)}

    @get("/events")
    async def get_recent_events(
        self,
        collector: EventCollector,
        session_id: UUID | None = None,
        event_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
        since: datetime | None = None,
    ) -> dict:
        """
        Get recent events with optional filtering and pagination.

        Args:
            collector: Event collector
            session_id: Filter by session ID
            event_type: Filter by event type
            limit: Maximum number of events (max 1000)
            offset: Pagination offset
            since: Only events after this time

        Returns:
            Dict with events, metadata, and pagination info
        """
        # Enforce limits
        limit = min(limit, 1000)

        # Calculate default time window (last hour)
        if since is None:
            since = datetime.now() - timedelta(hours=1)

        try:
            # Query events from storage
            events = await collector.query_events(
                session_id=session_id,
                event_type=event_type,
                start_time=since,
                limit=limit,
                offset=offset,
            )

            # Get total count for pagination
            total_count = await collector.count_events(
                session_id=session_id,
                event_type=event_type,
                start_time=since,
            )

            # Get collector stats
            stats = collector.get_stats()

            return {
                "events": [event.model_dump(mode="json") for event in events],
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "total": total_count,
                    "returned": len(events),
                    "has_more": offset + len(events) < total_count,
                },
                "filters": {
                    "session_id": str(session_id) if session_id else None,
                    "event_type": event_type,
                    "since": since.isoformat(),
                },
                "stats": stats,
            }

        except Exception as e:
            logger.error(f"Failed to query events: {e}")
            return {
                "events": [],
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "total": 0,
                    "returned": 0,
                    "has_more": False,
                },
                "error": str(e),
            }

    @get("/stats")
    async def get_stats(self, collector: EventCollector) -> dict:
        """
        Get current observability statistics.

        Args:
            collector: Event collector

        Returns:
            Statistics dictionary
        """
        return collector.get_stats()

    @websocket("/stream")
    async def stream_events(self, socket: WebSocket) -> None:
        """
        WebSocket endpoint for streaming real-time events.

        Protocol:
        - Client sends: {"type": "ping"} for keepalive
        - Server responds: {"type": "pong", "timestamp": "..."}
        - Server broadcasts: {"type": "event", "event": {...}} for each new event

        Args:
            socket: WebSocket connection
        """
        await socket.accept()

        # Add to global connections list
        _websocket_connections.append(socket)

        try:
            # Send welcome message
            await socket.send_json(
                {
                    "type": "connected",
                    "message": "Event stream connected",
                    "timestamp": datetime.now().isoformat(),
                }
            )

            # Keep connection alive and handle client messages
            while True:
                try:
                    # Wait for client messages with timeout
                    data = await asyncio.wait_for(socket.receive_json(), timeout=30.0)

                    if data.get("type") == "ping":
                        await socket.send_json(
                            {
                                "type": "pong",
                                "timestamp": datetime.now().isoformat(),
                            }
                        )

                except asyncio.TimeoutError:
                    # Send keepalive ping to client
                    await socket.send_json(
                        {
                            "type": "keepalive",
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            try:
                await socket.send_json(
                    {
                        "type": "error",
                        "error": str(e),
                    }
                )
            except Exception:
                pass

        finally:
            # Remove from connections list
            if socket in _websocket_connections:
                _websocket_connections.remove(socket)

            try:
                await socket.close()
            except Exception:
                pass


# Export router
observability_router = ObservabilityController
