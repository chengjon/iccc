"""Redis-based task queue for multi-agent coordination."""

import json
import os
from typing import Any, Optional
from uuid import UUID

import redis.asyncio as redis

from iccc.models.entities import Task


class RedisTaskQueue:
    """Redis-based task queue with priority support."""

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.client: Optional[redis.Redis] = None

        # Queue keys
        self.pending_queue = "iccc:tasks:pending"
        self.in_progress_queue = "iccc:tasks:in_progress"
        self.completed_queue = "iccc:tasks:completed"
        self.task_data_prefix = "iccc:task:"

    async def connect(self) -> None:
        """Establish Redis connection."""
        self.client = await redis.from_url(self.redis_url, decode_responses=True)

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self.client:
            await self.client.close()

    async def enqueue(self, task: Task, priority: int = 0) -> None:
        """
        Add a task to the pending queue.

        Args:
            task: Task to enqueue
            priority: Priority score (higher = more urgent), default 0
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        task_id = str(task.id)

        # Store task data
        task_key = f"{self.task_data_prefix}{task_id}"
        await self.client.set(task_key, task.model_dump_json())

        # Add to pending queue with priority
        await self.client.zadd(self.pending_queue, {task_id: -priority})  # Negative for DESC order

    async def dequeue(self, agent_id: str) -> Optional[Task]:
        """
        Dequeue the highest priority task.

        Args:
            agent_id: ID of the agent claiming the task

        Returns:
            Task object or None if queue is empty
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        # Atomic pop from pending queue (highest priority first)
        result = await self.client.zpopmax(self.pending_queue)

        if not result:
            return None

        task_id, _ = result[0]

        # Move to in_progress queue
        await self.client.hset(self.in_progress_queue, task_id, agent_id)

        # Retrieve task data
        task_key = f"{self.task_data_prefix}{task_id}"
        task_json = await self.client.get(task_key)

        if not task_json:
            return None

        return Task(**json.loads(task_json))

    async def mark_completed(self, task_id: UUID) -> None:
        """
        Mark a task as completed.

        Args:
            task_id: Task ID to mark as completed
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        task_id_str = str(task_id)

        # Remove from in_progress
        await self.client.hdel(self.in_progress_queue, task_id_str)

        # Add to completed set
        await self.client.sadd(self.completed_queue, task_id_str)

    async def mark_failed(self, task_id: UUID, error: str) -> None:
        """
        Mark a task as failed.

        Args:
            task_id: Task ID
            error: Error message
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        task_id_str = str(task_id)

        # Remove from in_progress
        await self.client.hdel(self.in_progress_queue, task_id_str)

        # Store error information
        error_key = f"iccc:task:error:{task_id_str}"
        await self.client.set(error_key, error)

        # Add to failed set
        await self.client.sadd("iccc:tasks:failed", task_id_str)

    async def get_task(self, task_id: UUID) -> Optional[Task]:
        """Retrieve a task by ID."""
        if not self.client:
            raise RuntimeError("Redis client not connected")

        task_key = f"{self.task_data_prefix}{str(task_id)}"
        task_json = await self.client.get(task_key)

        if not task_json:
            return None

        return Task(**json.loads(task_json))

    async def get_queue_length(self) -> dict[str, int]:
        """Get the length of all queues."""
        if not self.client:
            raise RuntimeError("Redis client not connected")

        return {
            "pending": await self.client.zcard(self.pending_queue),
            "in_progress": await self.client.hlen(self.in_progress_queue),
            "completed": await self.client.scard(self.completed_queue),
            "failed": await self.client.scard("iccc:tasks:failed"),
        }

    async def get_agent_tasks(self, agent_id: str) -> list[str]:
        """Get all tasks currently assigned to an agent."""
        if not self.client:
            raise RuntimeError("Redis client not connected")

        # Scan in_progress queue for this agent
        task_ids = []
        async for task_id, assigned_agent_id in self.client.hscan_iter(self.in_progress_queue):
            if assigned_agent_id == agent_id:
                task_ids.append(task_id)

        return task_ids

    async def requeue_task(self, task_id: UUID, priority: int = 0) -> None:
        """
        Return a task to the pending queue.

        Args:
            task_id: Task ID to requeue
            priority: New priority (default 0)
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        task_id_str = str(task_id)

        # Remove from in_progress
        await self.client.hdel(self.in_progress_queue, task_id_str)

        # Add back to pending
        await self.client.zadd(self.pending_queue, {task_id_str: -priority})

    async def cleanup_stale_tasks(self, timeout_seconds: int = 3600) -> int:
        """
        Requeue tasks that have been in_progress for too long.

        Args:
            timeout_seconds: Time before considering a task stale

        Returns:
            Number of tasks requeued
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        # This is a simplified version - in production, you'd want to track
        # timestamps for each task in progress
        # For now, we'll just return 0
        return 0
