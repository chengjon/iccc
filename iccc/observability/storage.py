"""Event storage backends for observability system."""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import DESCENDING

from iccc.config import get_config
from iccc.models.entities import HookEvent

logger = logging.getLogger(__name__)


class EventStorage(ABC):
    """Abstract base class for event storage backends."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to storage backend."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to storage backend."""
        pass

    @abstractmethod
    async def store_events(self, events: list[HookEvent]) -> None:
        """
        Store a batch of events.

        Args:
            events: List of events to store
        """
        pass

    @abstractmethod
    async def query_events(
        self,
        session_id: UUID | None = None,
        event_type: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[HookEvent]:
        """
        Query events with filtering and pagination.

        Args:
            session_id: Filter by session ID
            event_type: Filter by event type
            start_time: Filter events after this time
            end_time: Filter events before this time
            limit: Maximum number of events to return
            offset: Number of events to skip

        Returns:
            List of matching events
        """
        pass

    @abstractmethod
    async def count_events(
        self,
        session_id: UUID | None = None,
        event_type: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int:
        """
        Count events matching filters.

        Args:
            session_id: Filter by session ID
            event_type: Filter by event type
            start_time: Filter events after this time
            end_time: Filter events before this time

        Returns:
            Number of matching events
        """
        pass

    @abstractmethod
    async def delete_old_events(self, before: datetime) -> int:
        """
        Delete events older than specified time.

        Args:
            before: Delete events before this timestamp

        Returns:
            Number of events deleted
        """
        pass


class MongoDBEventStorage(EventStorage):
    """MongoDB implementation of event storage."""

    def __init__(
        self,
        mongodb_url: str | None = None,
        database_name: str | None = None,
        collection_name: str = "hook_events",
    ) -> None:
        """
        Initialize MongoDB event storage.

        Args:
            mongodb_url: MongoDB connection URL
            database_name: Database name
            collection_name: Collection name for events
        """
        config = get_config()
        self.mongodb_url = mongodb_url or config.mongodb.uri
        self.database_name = database_name or config.mongodb.database
        self.collection_name = collection_name
        self.client: AsyncIOMotorClient[Any] | None = None
        self.db: AsyncIOMotorDatabase[Any] | None = None

    async def connect(self) -> None:
        """Establish MongoDB connection and create indexes."""
        try:
            self.client = AsyncIOMotorClient(self.mongodb_url)
            self.db = self.client[self.database_name]

            # Create indexes for efficient querying
            collection = self.db[self.collection_name]

            # Index for session_id queries
            await collection.create_index([("session_id", DESCENDING)])

            # Index for event_type queries
            await collection.create_index([("event_type", DESCENDING)])

            # Compound index for timestamp-based queries
            await collection.create_index([("timestamp", DESCENDING)])

            # TTL index for automatic cleanup (30 days retention)
            await collection.create_index(
                [("timestamp", DESCENDING)],
                expireAfterSeconds=30 * 24 * 60 * 60,  # 30 days
                name="ttl_index",
            )

            logger.info(
                f"MongoDB event storage connected to {self.database_name}.{self.collection_name}"
            )
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    async def disconnect(self) -> None:
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("MongoDB event storage disconnected")

    @property
    def collection(self) -> Any:
        """Get events collection."""
        if self.db is None:
            raise RuntimeError("Database not connected")
        return self.db[self.collection_name]

    async def store_events(self, events: list[HookEvent]) -> None:
        """
        Store a batch of events to MongoDB.

        Args:
            events: List of events to store
        """
        if not events:
            return

        try:
            # Convert events to documents
            documents = [event.model_dump(mode="json") for event in events]

            # Insert in bulk
            await self.collection.insert_many(documents, ordered=False)

            logger.debug(f"Stored {len(events)} events to MongoDB")
        except Exception as e:
            logger.error(f"Failed to store events: {e}")
            # Don't raise - storage failures shouldn't break the system

    async def query_events(
        self,
        session_id: UUID | None = None,
        event_type: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[HookEvent]:
        """
        Query events from MongoDB with filtering and pagination.

        Args:
            session_id: Filter by session ID
            event_type: Filter by event type
            start_time: Filter events after this time
            end_time: Filter events before this time
            limit: Maximum number of events to return
            offset: Number of events to skip

        Returns:
            List of matching events
        """
        try:
            # Build query filter
            query: dict[str, Any] = {}

            if session_id:
                query["session_id"] = str(session_id)

            if event_type:
                query["event_type"] = event_type

            if start_time or end_time:
                timestamp_filter: dict[str, Any] = {}
                if start_time:
                    timestamp_filter["$gte"] = start_time.isoformat()
                if end_time:
                    timestamp_filter["$lte"] = end_time.isoformat()
                query["timestamp"] = timestamp_filter

            # Execute query with pagination
            cursor = (
                self.collection.find(query)
                .sort("timestamp", DESCENDING)
                .skip(offset)
                .limit(limit)
            )

            documents = await cursor.to_list(length=limit)

            # Convert documents back to HookEvent objects
            events = []
            for doc in documents:
                # Convert string UUIDs back to UUID objects
                if isinstance(doc["id"], str):
                    doc["id"] = UUID(doc["id"])
                if isinstance(doc["session_id"], str):
                    doc["session_id"] = UUID(doc["session_id"])

                events.append(HookEvent(**doc))

            logger.debug(f"Retrieved {len(events)} events from MongoDB")
            return events

        except Exception as e:
            logger.error(f"Failed to query events: {e}")
            return []

    async def count_events(
        self,
        session_id: UUID | None = None,
        event_type: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int:
        """
        Count events matching filters.

        Args:
            session_id: Filter by session ID
            event_type: Filter by event type
            start_time: Filter events after this time
            end_time: Filter events before this time

        Returns:
            Number of matching events
        """
        try:
            # Build query filter (same as query_events)
            query: dict[str, Any] = {}

            if session_id:
                query["session_id"] = str(session_id)

            if event_type:
                query["event_type"] = event_type

            if start_time or end_time:
                timestamp_filter: dict[str, Any] = {}
                if start_time:
                    timestamp_filter["$gte"] = start_time.isoformat()
                if end_time:
                    timestamp_filter["$lte"] = end_time.isoformat()
                query["timestamp"] = timestamp_filter

            count = await self.collection.count_documents(query)
            return int(count)

        except Exception as e:
            logger.error(f"Failed to count events: {e}")
            return 0

    async def delete_old_events(self, before: datetime) -> int:
        """
        Delete events older than specified time.

        Note: With TTL index, this is automatic, but this method
        allows manual cleanup if needed.

        Args:
            before: Delete events before this timestamp

        Returns:
            Number of events deleted
        """
        try:
            result = await self.collection.delete_many(
                {"timestamp": {"$lt": before.isoformat()}}
            )
            deleted = int(result.deleted_count)
            logger.info(f"Deleted {deleted} old events")
            return deleted

        except Exception as e:
            logger.error(f"Failed to delete old events: {e}")
            return 0


class InMemoryEventStorage(EventStorage):
    """In-memory implementation for testing and development."""

    def __init__(self, max_events: int = 10000) -> None:
        """
        Initialize in-memory storage.

        Args:
            max_events: Maximum number of events to keep
        """
        self.max_events = max_events
        self.events: list[HookEvent] = []
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """No connection needed for in-memory storage."""
        logger.info("In-memory event storage initialized")

    async def disconnect(self) -> None:
        """No disconnection needed for in-memory storage."""
        self.events.clear()
        logger.info("In-memory event storage cleared")

    async def store_events(self, events: list[HookEvent]) -> None:
        """Store events in memory."""
        async with self._lock:
            self.events.extend(events)

            # Trim to max_events (keep most recent)
            if len(self.events) > self.max_events:
                self.events = self.events[-self.max_events :]

            logger.debug(f"Stored {len(events)} events in memory (total: {len(self.events)})")

    async def query_events(
        self,
        session_id: UUID | None = None,
        event_type: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[HookEvent]:
        """Query events from memory."""
        async with self._lock:
            # Filter events
            filtered = self.events

            if session_id:
                filtered = [e for e in filtered if e.session_id == session_id]

            if event_type:
                filtered = [e for e in filtered if e.event_type == event_type]

            if start_time:
                filtered = [e for e in filtered if e.timestamp >= start_time]

            if end_time:
                filtered = [e for e in filtered if e.timestamp <= end_time]

            # Sort by timestamp descending
            filtered = sorted(filtered, key=lambda e: e.timestamp, reverse=True)

            # Apply pagination
            return filtered[offset : offset + limit]

    async def count_events(
        self,
        session_id: UUID | None = None,
        event_type: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int:
        """Count events in memory."""
        async with self._lock:
            # Filter events (same as query_events)
            filtered = self.events

            if session_id:
                filtered = [e for e in filtered if e.session_id == session_id]

            if event_type:
                filtered = [e for e in filtered if e.event_type == event_type]

            if start_time:
                filtered = [e for e in filtered if e.timestamp >= start_time]

            if end_time:
                filtered = [e for e in filtered if e.timestamp <= end_time]

            return len(filtered)

    async def delete_old_events(self, before: datetime) -> int:
        """Delete old events from memory."""
        async with self._lock:
            original_count = len(self.events)
            self.events = [e for e in self.events if e.timestamp >= before]
            deleted = original_count - len(self.events)
            logger.info(f"Deleted {deleted} old events from memory")
            return deleted
