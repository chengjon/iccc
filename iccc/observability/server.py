"""Litestar API server for observability with SQLite storage and WebSocket."""

import json
import os
import sqlite3
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from litestar import Litestar, WebSocket, get, websocket
from litestar.channels import ChannelsPlugin
from litestar.channels.backends.memory import MemoryChannelsBackend
from litestar.config.cors import CORSConfig

from iccc.models.entities import HookEvent
from iccc.observability.collector import EventCollector
from iccc.config import get_config


class EventStore:
    """SQLite-based event storage."""

    def __init__(self, db_path: str = "./data/events.db") -> None:
        self.db_path = db_path
        self.conn: sqlite3.Connection | None = None

        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> None:
        """Connect to SQLite database."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._create_tables()

    def disconnect(self) -> None:
        """Disconnect from database."""
        if self.conn:
            self.conn.close()

    def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        if not self.conn:
            return

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                event_type TEXT,
                timestamp TEXT,
                data TEXT,
                ai_summary TEXT
            )
            """
        )

        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_events_timestamp
            ON events(timestamp DESC)
            """
        )

        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_events_session
            ON events(session_id)
            """
        )

        self.conn.commit()

    def insert_events(self, events: list[HookEvent], ai_summary: str | None = None) -> None:
        """Insert a batch of events."""
        if not self.conn:
            return

        for event in events:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO events
                (id, session_id, event_type, timestamp, data, ai_summary)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.id),
                    str(event.session_id),
                    event.event_type,
                    event.timestamp.isoformat(),
                    json.dumps(event.data),
                    ai_summary,
                ),
            )

        self.conn.commit()

    def get_recent_events(self, limit: int = 100) -> list[dict]:
        """Get recent events."""
        if not self.conn:
            return []

        cursor = self.conn.execute(
            """
            SELECT id, session_id, event_type, timestamp, data, ai_summary
            FROM events
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        )

        events = []
        for row in cursor.fetchall():
            events.append(
                {
                    "id": row[0],
                    "session_id": row[1],
                    "event_type": row[2],
                    "timestamp": row[3],
                    "data": json.loads(row[4]) if row[4] else {},
                    "ai_summary": row[5],
                }
            )

        return events

    def get_events_by_session(self, session_id: UUID, limit: int = 100) -> list[dict]:
        """Get events for a specific session."""
        if not self.conn:
            return []

        cursor = self.conn.execute(
            """
            SELECT id, session_id, event_type, timestamp, data, ai_summary
            FROM events
            WHERE session_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (str(session_id), limit),
        )

        events = []
        for row in cursor.fetchall():
            events.append(
                {
                    "id": row[0],
                    "session_id": row[1],
                    "event_type": row[2],
                    "timestamp": row[3],
                    "data": json.loads(row[4]) if row[4] else {},
                    "ai_summary": row[5],
                }
            )

        return events

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics."""
        if not self.conn:
            return {}

        cursor = self.conn.execute("SELECT COUNT(*) FROM events")
        total_events = cursor.fetchone()[0]

        cursor = self.conn.execute(
            """
            SELECT event_type, COUNT(*) as count
            FROM events
            GROUP BY event_type
            ORDER BY count DESC
            """
        )
        event_type_counts = {row[0]: row[1] for row in cursor.fetchall()}

        return {
            "total_events": total_events,
            "event_types": event_type_counts,
        }


# Global state
event_store: EventStore | None = None
event_collector: EventCollector | None = None
channels_backend = MemoryChannelsBackend()


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    global event_store, event_collector

    # Initialize event store
    db_path = get_config().observability.sqlite_path
    event_store = EventStore(db_path)
    event_store.connect()

    # Initialize event collector
    event_collector = EventCollector(
        batch_size=100,
        batch_timeout=5,
        sample_rate=1.0,
        enable_ai_summaries=True,
    )

    # Register flush callback
    async def on_flush(events: list[HookEvent], summary: str | None) -> None:
        if event_store:
            event_store.insert_events(events, summary)

        # Broadcast to WebSocket clients
        await channels_backend.publish(
            json.dumps(
                {
                    "type": "events_batch",
                    "count": len(events),
                    "summary": summary,
                    "events": [
                        {
                            "id": str(e.id),
                            "event_type": e.event_type,
                            "timestamp": e.timestamp.isoformat(),
                            "data": e.data,
                        }
                        for e in events[:10]  # Send first 10 events
                    ],
                }
            ),
            "events",
        )

    event_collector.register_flush_callback(on_flush)
    await event_collector.start()

    yield

    # Cleanup
    await event_collector.stop()
    event_store.disconnect()


# API Routes


@get("/")
async def index() -> dict[str, str]:
    """API root endpoint."""
    return {
        "name": "iCCC Observability API",
        "version": "0.1.0",
        "docs": "/schema",
    }


@get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@get("/events")
async def get_events(limit: int = 100) -> dict[str, Any]:
    """Get recent events."""
    if not event_store:
        return {"events": []}

    events = event_store.get_recent_events(limit)
    return {"events": events, "count": len(events)}


@get("/events/session/{session_id:uuid}")
async def get_session_events(session_id: UUID, limit: int = 100) -> dict[str, Any]:
    """Get events for a specific session."""
    if not event_store:
        return {"events": []}

    events = event_store.get_events_by_session(session_id, limit)
    return {"events": events, "count": len(events)}


@get("/stats")
async def get_stats() -> dict[str, Any]:
    """Get statistics."""
    stats = {}

    if event_store:
        stats["storage"] = event_store.get_stats()

    if event_collector:
        stats["collector"] = event_collector.get_stats()

    return stats


@websocket("/ws")
async def websocket_handler(socket: WebSocket) -> None:
    """WebSocket endpoint for real-time event streaming."""
    await socket.accept()

    # Subscribe to events channel
    async with channels_backend.start_subscription(["events"]) as subscriber:
        try:
            # Send initial connection message
            await socket.send_json(
                {
                    "type": "connected",
                    "message": "Connected to iCCC event stream",
                    "timestamp": datetime.now().isoformat(),
                }
            )

            # Stream events
            async for event_data in subscriber.iter_events():
                await socket.send_text(event_data)

        except Exception as e:
            print(f"WebSocket error: {e}")
        finally:
            await socket.close()


# Create app
cors_config = CORSConfig(
    allow_origins=["http://localhost:5173", "http://localhost:8080"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app = Litestar(
    route_handlers=[
        index,
        health,
        get_events,
        get_session_events,
        get_stats,
        websocket_handler,
    ],
    cors_config=cors_config,
    lifespan=[lifespan],
    plugins=[ChannelsPlugin(backend=channels_backend, arbitrary_channels_allowed=True)],
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
