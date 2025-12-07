"""Observability API endpoints for events and monitoring."""

from datetime import datetime, timedelta
from uuid import UUID

from litestar import Controller, WebSocket, get, websocket
from litestar.di import Provide

from iccc.observability.collector import EventCollector


async def provide_event_collector() -> EventCollector:
    """Dependency injection for EventCollector."""
    # In production, this would be a singleton instance
    collector = EventCollector(enable_ai_summaries=False)
    return collector


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
        since: datetime | None = None,
    ) -> dict:
        """
        Get recent events with optional filtering.

        Args:
            collector: Event collector
            session_id: Filter by session ID
            event_type: Filter by event type
            limit: Maximum number of events
            since: Only events after this time

        Returns:
            Dict with events and metadata
        """
        # Calculate default time window (last hour)
        if since is None:
            since = datetime.now() - timedelta(hours=1)

        # Get events from collector
        # Note: EventCollector doesn't have a query method yet,
        # so we'll return stats for now
        stats = collector.get_stats()

        return {
            "events": [],  # TODO: Implement event storage query
            "stats": stats,
            "filters": {
                "session_id": str(session_id) if session_id else None,
                "event_type": event_type,
                "since": since.isoformat(),
                "limit": limit,
            },
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

        Clients can connect to receive events as they occur.

        Args:
            socket: WebSocket connection
        """
        await socket.accept()

        try:
            # TODO: Implement actual event streaming
            # For now, send a welcome message
            await socket.send_json({
                "type": "connected",
                "message": "Event stream connected",
                "timestamp": datetime.now().isoformat(),
            })

            # Keep connection alive
            while True:
                # Wait for client messages (ping/pong)
                data = await socket.receive_json()

                if data.get("type") == "ping":
                    await socket.send_json({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat(),
                    })

        except Exception as e:
            await socket.send_json({
                "type": "error",
                "error": str(e),
            })
        finally:
            await socket.close()


# Export router
observability_router = ObservabilityController
