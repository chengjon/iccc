#!/usr/bin/env python3
"""
Multi-agent coordination hook for managing file locks and agent communication.

This script coordinates multiple agents working in parallel by:
- Acquiring file locks before tool execution (PreToolUse)
- Releasing file locks after tool execution (PostToolUse)
- Publishing completion events when subagents finish (SubagentStop)

This ensures that agents don't conflict when modifying the same files.

Usage:
    Register in Claude Code hooks configuration:
    {
      "PreToolUse": {
        "command": "python iccc/hooks/scripts/agent_coordinator.py pre",
        "critical": true
      },
      "PostToolUse": {
        "command": "python iccc/hooks/scripts/agent_coordinator.py post",
        "critical": false
      },
      "SubagentStop": {
        "command": "python iccc/hooks/scripts/agent_coordinator.py subagent_stop",
        "critical": false
      }
    }

Environment variables:
    - AGENT_ID: Unique identifier for this agent
    - TOOL_NAME: Name of tool being executed
    - FILE_PATH: Path to file being modified
    - REDIS_URL: Redis connection URL (default: redis://localhost:6379)
"""

import json
import os
import sys
import time
from pathlib import Path


def get_agent_id() -> str:
    """Get current agent ID."""
    return os.environ.get("AGENT_ID", "unknown-agent")


def get_file_path() -> Path | None:
    """Extract file path from hook data."""
    hook_data_str = os.environ.get("HOOK_DATA", "{}")
    try:
        hook_data = json.loads(hook_data_str)
        file_path = hook_data.get("file_path")
        if file_path:
            return Path(file_path)
    except json.JSONDecodeError:
        pass

    # Fallback to FILE_PATH env var
    file_path = os.environ.get("FILE_PATH")
    if file_path:
        return Path(file_path)

    return None


def get_redis_client():
    """
    Get Redis client for distributed locking.

    Returns:
        Redis client or None if not available
    """
    try:
        import redis

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        return redis.from_url(redis_url, decode_responses=True)
    except ImportError:
        print("⚠️  Redis not available - file locking disabled")
        return None
    except Exception as e:
        print(f"⚠️  Redis connection failed: {e}")
        return None


def acquire_file_lock(file_path: Path, agent_id: str, timeout: int = 30) -> bool:
    """
    Acquire exclusive lock on a file.

    Args:
        file_path: File to lock
        agent_id: Agent requesting lock
        timeout: Max wait time in seconds

    Returns:
        True if lock acquired, False otherwise
    """
    redis_client = get_redis_client()
    if not redis_client:
        # If Redis unavailable, allow operation (degraded mode)
        return True

    lock_key = f"file_lock:{file_path}"
    start_time = time.time()

    print(f"🔒 [{agent_id}] Acquiring lock for: {file_path}")

    while time.time() - start_time < timeout:
        # Try to set lock with NX (only if not exists)
        acquired = redis_client.set(
            lock_key,
            agent_id,
            nx=True,
            ex=300,  # Lock expires after 5 minutes
        )

        if acquired:
            print(f"✅ [{agent_id}] Lock acquired: {file_path}")
            return True

        # Lock held by another agent
        current_owner = redis_client.get(lock_key)
        print(f"⏳ [{agent_id}] Waiting for lock (held by {current_owner})...")

        time.sleep(0.5)  # Wait before retry

    print(f"❌ [{agent_id}] Lock timeout for: {file_path}")
    return False


def release_file_lock(file_path: Path, agent_id: str) -> bool:
    """
    Release lock on a file.

    Args:
        file_path: File to unlock
        agent_id: Agent releasing lock

    Returns:
        True if lock released, False otherwise
    """
    redis_client = get_redis_client()
    if not redis_client:
        return True

    lock_key = f"file_lock:{file_path}"

    # Check ownership before releasing
    current_owner = redis_client.get(lock_key)
    if current_owner != agent_id:
        if current_owner:
            print(f"⚠️  [{agent_id}] Cannot release lock owned by {current_owner}")
        return False

    # Release lock
    redis_client.delete(lock_key)
    print(f"🔓 [{agent_id}] Lock released: {file_path}")
    return True


def publish_completion_event(agent_id: str, status: str, metadata: dict) -> None:
    """
    Publish agent completion event to Redis pub/sub.

    Args:
        agent_id: Agent that finished
        status: Completion status (success/error)
        metadata: Additional event data
    """
    redis_client = get_redis_client()
    if not redis_client:
        return

    event = {
        "agent_id": agent_id,
        "status": status,
        "timestamp": time.time(),
        "metadata": metadata,
    }

    channel = "agent_events"
    redis_client.publish(channel, json.dumps(event))
    print(f"📢 [{agent_id}] Published completion event: {status}")


def handle_pre_tool_use() -> int:
    """
    Handle PreToolUse hook - acquire file locks.

    Returns:
        0 if lock acquired, 1 to block tool execution
    """
    tool_name = os.environ.get("TOOL_NAME", "")
    agent_id = get_agent_id()

    # Only lock for file modification tools
    if tool_name not in ["Write", "Edit", "MultiEdit"]:
        return 0

    file_path = get_file_path()
    if not file_path:
        return 0

    # Try to acquire lock
    if acquire_file_lock(file_path, agent_id):
        return 0  # Allow tool execution
    else:
        print(f"🚫 [{agent_id}] Tool execution blocked - lock unavailable")
        return 1  # Block tool execution


def handle_post_tool_use() -> int:
    """
    Handle PostToolUse hook - release file locks.

    Returns:
        0 (always succeeds)
    """
    tool_name = os.environ.get("TOOL_NAME", "")
    agent_id = get_agent_id()

    # Only release locks for file modification tools
    if tool_name not in ["Write", "Edit", "MultiEdit"]:
        return 0

    file_path = get_file_path()
    if not file_path:
        return 0

    release_file_lock(file_path, agent_id)
    return 0


def handle_subagent_stop() -> int:
    """
    Handle SubagentStop hook - publish completion event.

    Returns:
        0 (always succeeds)
    """
    agent_id = get_agent_id()
    hook_data_str = os.environ.get("HOOK_DATA", "{}")

    try:
        hook_data = json.loads(hook_data_str)
    except json.JSONDecodeError:
        hook_data = {}

    # Extract status from hook data
    status = "success" if hook_data.get("success", False) else "error"

    publish_completion_event(agent_id, status, hook_data)
    return 0


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: agent_coordinator.py <pre|post|subagent_stop>")
        return 1

    mode = sys.argv[1]

    if mode == "pre":
        return handle_pre_tool_use()
    elif mode == "post":
        return handle_post_tool_use()
    elif mode == "subagent_stop":
        return handle_subagent_stop()
    else:
        print(f"Unknown mode: {mode}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
