"""Hook system manager for event-driven workflows."""

import asyncio
import json
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from iccc.locks.file_lock import FileLockManager, LockType
from iccc.models.entities import HookEvent


class HookType(str, Enum):
    """Types of hooks supported."""

    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    NOTIFICATION = "Notification"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    STOP = "Stop"
    SUBAGENT_STOP = "SubagentStop"
    PRE_COMPACT = "PreCompact"
    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"


class HookConfig:
    """Configuration for a single hook."""

    def __init__(
        self,
        hook_type: str,
        command: str,
        timeout_ms: int = 1000,
        critical: bool = False,
        env: dict[str, str] | None = None,
    ) -> None:
        self.hook_type = hook_type
        self.command = command
        self.timeout_ms = timeout_ms
        self.critical = critical
        self.env = env or {}


class HookManager:
    """Manages and executes hooks for various events."""

    def __init__(self, lock_manager: FileLockManager | None = None) -> None:
        self.hooks: dict[str, list[HookConfig]] = {}
        self.event_callbacks: list[Callable[[HookEvent], None]] = []
        self.lock_manager = lock_manager

    def register_hook(self, config: HookConfig) -> None:
        """Register a hook configuration."""
        hook_type = config.hook_type
        if hook_type not in self.hooks:
            self.hooks[hook_type] = []
        self.hooks[hook_type].append(config)

    def register_event_callback(self, callback: Callable[[HookEvent], None]) -> None:
        """Register a callback to be notified of hook events."""
        self.event_callbacks.append(callback)

    async def trigger(
        self,
        hook_type: str,
        data: dict[str, Any],
        session_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Trigger all hooks of a given type.

        Args:
            hook_type: Type of hook to trigger
            data: Data to pass to hooks
            session_id: Optional session ID for event tracking
            agent_id: Optional agent ID for file locking

        Returns:
            Dictionary with results and any errors
        """
        if hook_type not in self.hooks:
            return {"success": True, "results": []}

        # Check if file locking is needed
        file_path = data.get("file_path")
        lock_acquired = False

        try:
            # Acquire file lock if file path is provided and lock manager available
            if file_path and self.lock_manager and agent_id:
                # Determine lock type based on tool
                tool_name = data.get("tool_name", "")
                lock_type = (
                    LockType.WRITE if tool_name in ["Write", "Edit", "MultiEdit"] else LockType.READ
                )

                # Acquire lock
                async with self.lock_manager.lock(
                    file_path, agent_id, lock_type, timeout=30
                ) as acquired:
                    lock_acquired = acquired
                    if not acquired:
                        return {
                            "success": False,
                            "results": [],
                            "errors": [
                                f"Failed to acquire {lock_type.value} lock on {file_path}"
                            ],
                        }

                    # Execute hooks while holding the lock
                    return await self._execute_hooks(hook_type, data, session_id)
            else:
                # No file locking needed, execute hooks directly
                return await self._execute_hooks(hook_type, data, session_id)

        except Exception as e:
            return {
                "success": False,
                "results": [],
                "errors": [f"Hook execution failed: {str(e)}"],
            }

    async def _execute_hooks(
        self, hook_type: str, data: dict[str, Any], session_id: str | None = None
    ) -> dict[str, Any]:
        """
        Execute all hooks for a given type.

        Args:
            hook_type: Type of hook
            data: Data to pass to hooks
            session_id: Optional session ID

        Returns:
            Results dictionary
        """
        results = []
        errors = []

        for hook_config in self.hooks[hook_type]:
            try:
                result = await self._execute_hook(hook_config, data)
                results.append(result)

                # Create hook event
                if session_id:
                    event = HookEvent(
                        session_id=session_id,
                        event_type=hook_type,
                        timestamp=datetime.now(),
                        data={
                            "hook_command": hook_config.command,
                            "result": result,
                            "critical": hook_config.critical,
                        },
                    )
                    self._notify_callbacks(event)

            except Exception as e:
                error_msg = f"Hook '{hook_config.command}' failed: {str(e)}"
                errors.append(error_msg)

                if hook_config.critical:
                    # Critical hook failure blocks the operation
                    raise RuntimeError(error_msg)

        return {"success": len(errors) == 0, "results": results, "errors": errors}

    async def _execute_hook(self, config: HookConfig, data: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a single hook.

        Args:
            config: Hook configuration
            data: Data to pass to the hook

        Returns:
            Result dictionary
        """
        # Prepare environment variables
        env = {**config.env}
        env["HOOK_DATA"] = json.dumps(data)

        # For tool use hooks, add specific tool information
        if "tool_name" in data:
            env["TOOL_NAME"] = data["tool_name"]
        if "tool_command" in data:
            env["TOOL_COMMAND"] = data["tool_command"]

        timeout_seconds = config.timeout_ms / 1000

        try:
            # Execute command with timeout
            process = await asyncio.create_subprocess_shell(
                config.command,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout_seconds
                )

                return {
                    "success": process.returncode == 0,
                    "returncode": process.returncode,
                    "stdout": stdout.decode("utf-8") if stdout else "",
                    "stderr": stderr.decode("utf-8") if stderr else "",
                }

            except TimeoutError:
                process.kill()
                await process.wait()
                raise RuntimeError(
                    f"Hook timed out after {timeout_seconds}s: {config.command}"
                )

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def _notify_callbacks(self, event: HookEvent) -> None:
        """Notify registered callbacks of a hook event."""
        for callback in self.event_callbacks:
            try:
                callback(event)
            except Exception:
                # Don't let callback failures affect hook execution
                pass

    @classmethod
    def load_from_config(cls, config_path: Path) -> "HookManager":
        """
        Load hook configuration from a JSON file.

        Expected format:
        {
          "hooks": {
            "PreToolUse": [{
              "matcher": "tool_name:Bash",
              "hooks": [{
                "type": "command",
                "command": "python ~/.iccc/hooks/safety_check.py",
                "timeout_ms": 50,
                "critical": true,
                "env": {"TOOL_COMMAND": "${TOOL_COMMAND}"}
              }]
            }],
            "PostToolUse": [...]
          }
        }
        """
        manager = cls()

        if not config_path.exists():
            return manager

        import json

        with open(config_path) as f:
            config_data = json.load(f)

        hooks_config = config_data.get("hooks", {})

        for hook_type, hook_list in hooks_config.items():
            for hook_entry in hook_list:
                for hook_def in hook_entry.get("hooks", []):
                    hook_config = HookConfig(
                        hook_type=hook_type,
                        command=hook_def["command"],
                        timeout_ms=hook_def.get("timeout_ms", 1000),
                        critical=hook_def.get("critical", False),
                        env=hook_def.get("env", {}),
                    )
                    manager.register_hook(hook_config)

        return manager
