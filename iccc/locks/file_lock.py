"""Redis-based file locking for multi-agent coordination."""

import asyncio
import os
from contextlib import asynccontextmanager
from enum import Enum
from typing import AsyncIterator, Optional

import redis.asyncio as redis


class LockType(str, Enum):
    """File lock types."""

    READ = "read"  # Shared lock
    WRITE = "write"  # Exclusive lock


class FileLockManager:
    """Redis-based distributed file locking."""

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.client: Optional[redis.Redis] = None

        # Lock key prefix
        self.lock_prefix = "iccc:lock:"
        self.read_lock_suffix = ":readers"
        self.write_lock_suffix = ":writer"

    async def connect(self) -> None:
        """Establish Redis connection."""
        self.client = await redis.from_url(self.redis_url, decode_responses=True)

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self.client:
            await self.client.close()

    async def acquire_read_lock(
        self, file_path: str, agent_id: str, timeout: int = 30
    ) -> bool:
        """
        Acquire a shared read lock on a file.

        Multiple agents can hold read locks simultaneously,
        but not if a write lock exists.

        Args:
            file_path: Path to the file
            agent_id: ID of the agent acquiring the lock
            timeout: Lock timeout in seconds

        Returns:
            True if lock acquired, False otherwise
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        lock_key = f"{self.lock_prefix}{file_path}"
        write_lock_key = f"{lock_key}{self.write_lock_suffix}"
        read_lock_key = f"{lock_key}{self.read_lock_suffix}"

        # Check if write lock exists
        has_write_lock = await self.client.exists(write_lock_key)
        if has_write_lock:
            return False

        # Add to read lock set with expiry
        await self.client.sadd(read_lock_key, agent_id)
        await self.client.expire(read_lock_key, timeout)

        return True

    async def acquire_write_lock(
        self, file_path: str, agent_id: str, timeout: int = 30
    ) -> bool:
        """
        Acquire an exclusive write lock on a file.

        Only one agent can hold a write lock, and no read locks can exist.

        Args:
            file_path: Path to the file
            agent_id: ID of the agent acquiring the lock
            timeout: Lock timeout in seconds

        Returns:
            True if lock acquired, False otherwise
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        lock_key = f"{self.lock_prefix}{file_path}"
        write_lock_key = f"{lock_key}{self.write_lock_suffix}"
        read_lock_key = f"{lock_key}{self.read_lock_suffix}"

        # Use Lua script for atomic check-and-set
        lua_script = """
        local write_lock_key = KEYS[1]
        local read_lock_key = KEYS[2]
        local agent_id = ARGV[1]
        local timeout = ARGV[2]

        -- Check if any locks exist
        if redis.call('exists', write_lock_key) == 1 then
            return 0
        end
        if redis.call('exists', read_lock_key) == 1 then
            return 0
        end

        -- Acquire write lock
        redis.call('set', write_lock_key, agent_id, 'EX', timeout)
        return 1
        """

        result = await self.client.eval(
            lua_script, 2, write_lock_key, read_lock_key, agent_id, str(timeout)
        )

        return bool(result)

    async def release_read_lock(self, file_path: str, agent_id: str) -> None:
        """
        Release a read lock.

        Args:
            file_path: Path to the file
            agent_id: ID of the agent releasing the lock
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        lock_key = f"{self.lock_prefix}{file_path}"
        read_lock_key = f"{lock_key}{self.read_lock_suffix}"

        await self.client.srem(read_lock_key, agent_id)

        # Clean up if no more readers
        count = await self.client.scard(read_lock_key)
        if count == 0:
            await self.client.delete(read_lock_key)

    async def release_write_lock(self, file_path: str, agent_id: str) -> None:
        """
        Release a write lock.

        Args:
            file_path: Path to the file
            agent_id: ID of the agent releasing the lock
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        lock_key = f"{self.lock_prefix}{file_path}"
        write_lock_key = f"{lock_key}{self.write_lock_suffix}"

        # Only delete if this agent owns the lock
        current_owner = await self.client.get(write_lock_key)
        if current_owner == agent_id:
            await self.client.delete(write_lock_key)

    @asynccontextmanager
    async def lock(
        self, file_path: str, agent_id: str, lock_type: LockType = LockType.WRITE, timeout: int = 30
    ) -> AsyncIterator[bool]:
        """
        Context manager for file locking.

        Usage:
            async with lock_manager.lock('file.py', 'agent-1', LockType.WRITE):
                # Perform file operations
                pass

        Args:
            file_path: Path to the file
            agent_id: ID of the agent
            lock_type: Type of lock (READ or WRITE)
            timeout: Lock timeout in seconds

        Yields:
            True if lock acquired
        """
        acquired = False

        try:
            if lock_type == LockType.READ:
                acquired = await self.acquire_read_lock(file_path, agent_id, timeout)
            else:
                acquired = await self.acquire_write_lock(file_path, agent_id, timeout)

            if not acquired:
                # Wait and retry
                await asyncio.sleep(0.5)
                if lock_type == LockType.READ:
                    acquired = await self.acquire_read_lock(file_path, agent_id, timeout)
                else:
                    acquired = await self.acquire_write_lock(file_path, agent_id, timeout)

            yield acquired

        finally:
            if acquired:
                if lock_type == LockType.READ:
                    await self.release_read_lock(file_path, agent_id)
                else:
                    await self.release_write_lock(file_path, agent_id)

    async def check_lock_owner(self, file_path: str) -> Optional[str]:
        """
        Check who owns the write lock for a file.

        Args:
            file_path: Path to the file

        Returns:
            Agent ID owning the lock, or None if no lock
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        lock_key = f"{self.lock_prefix}{file_path}"
        write_lock_key = f"{lock_key}{self.write_lock_suffix}"

        owner = await self.client.get(write_lock_key)
        return owner

    async def detect_deadlocks(self) -> list[dict]:
        """
        Detect potentially deadlocked file locks.

        A lock is considered potentially deadlocked if:
        - It has been held for longer than expected
        - TTL is approaching 0 but lock is still held

        Returns:
            List of potentially deadlocked locks
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        deadlocks = []

        # Scan for all lock keys
        async for key in self.client.scan_iter(match=f"{self.lock_prefix}*{self.write_lock_suffix}"):
            ttl = await self.client.ttl(key)
            owner = await self.client.get(key)

            # If TTL < 5 seconds and lock still held, potential deadlock
            if ttl > 0 and ttl < 5 and owner:
                file_path = key.replace(self.lock_prefix, "").replace(self.write_lock_suffix, "")
                deadlocks.append({
                    "file_path": file_path,
                    "owner": owner,
                    "ttl_seconds": ttl,
                })

        return deadlocks

    async def force_release(self, file_path: str) -> bool:
        """
        Force release a lock (admin operation).

        Args:
            file_path: Path to the file

        Returns:
            True if lock was released
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        lock_key = f"{self.lock_prefix}{file_path}"
        write_lock_key = f"{lock_key}{self.write_lock_suffix}"
        read_lock_key = f"{lock_key}{self.read_lock_suffix}"

        # Delete both locks
        write_deleted = await self.client.delete(write_lock_key)
        read_deleted = await self.client.delete(read_lock_key)

        return bool(write_deleted or read_deleted)

    async def get_lock_status(self, file_path: str) -> dict:
        """
        Get the current lock status for a file.

        Returns:
            Dictionary with lock information
        """
        if not self.client:
            raise RuntimeError("Redis client not connected")

        lock_key = f"{self.lock_prefix}{file_path}"
        write_lock_key = f"{lock_key}{self.write_lock_suffix}"
        read_lock_key = f"{lock_key}{self.read_lock_suffix}"

        write_owner = await self.client.get(write_lock_key)
        readers = await self.client.smembers(read_lock_key)

        return {
            "file_path": file_path,
            "write_lock": write_owner,
            "read_locks": list(readers) if readers else [],
            "is_locked": bool(write_owner or readers),
        }
