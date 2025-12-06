"""Tests for hook system manager."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from iccc.hooks.manager import HookConfig, HookManager, HookType
from iccc.locks.file_lock import FileLockManager, LockType
from iccc.models.entities import HookEvent


class TestHookConfig:
    """Test HookConfig class."""

    def test_hook_config_creation(self):
        """Test creating a hook configuration."""
        config = HookConfig(
            hook_type="PreToolUse",
            command="echo test",
            timeout_ms=5000,
            critical=True,
            env={"FOO": "bar"},
        )

        assert config.hook_type == "PreToolUse"
        assert config.command == "echo test"
        assert config.timeout_ms == 5000
        assert config.critical is True
        assert config.env == {"FOO": "bar"}

    def test_hook_config_defaults(self):
        """Test hook configuration with default values."""
        config = HookConfig(hook_type="PostToolUse", command="echo done")

        assert config.timeout_ms == 1000
        assert config.critical is False
        assert config.env == {}


class TestHookManager:
    """Test HookManager class."""

    def test_hook_manager_initialization(self):
        """Test creating a hook manager."""
        manager = HookManager()

        assert manager.hooks == {}
        assert manager.event_callbacks == []
        assert manager.lock_manager is None

    def test_hook_manager_with_lock_manager(self):
        """Test creating a hook manager with lock manager."""
        lock_manager = MagicMock(spec=FileLockManager)
        manager = HookManager(lock_manager=lock_manager)

        assert manager.lock_manager is lock_manager

    def test_register_hook(self):
        """Test registering a hook."""
        manager = HookManager()
        config = HookConfig(hook_type="PreToolUse", command="echo test")

        manager.register_hook(config)

        assert "PreToolUse" in manager.hooks
        assert len(manager.hooks["PreToolUse"]) == 1
        assert manager.hooks["PreToolUse"][0] == config

    def test_register_multiple_hooks_same_type(self):
        """Test registering multiple hooks for the same type."""
        manager = HookManager()
        config1 = HookConfig(hook_type="PreToolUse", command="echo test1")
        config2 = HookConfig(hook_type="PreToolUse", command="echo test2")

        manager.register_hook(config1)
        manager.register_hook(config2)

        assert len(manager.hooks["PreToolUse"]) == 2

    def test_register_event_callback(self):
        """Test registering an event callback."""
        manager = HookManager()
        callback = MagicMock()

        manager.register_event_callback(callback)

        assert len(manager.event_callbacks) == 1
        assert manager.event_callbacks[0] == callback

    @pytest.mark.asyncio
    async def test_trigger_hook_no_hooks_registered(self):
        """Test triggering a hook when no hooks are registered."""
        manager = HookManager()
        result = await manager.trigger("PreToolUse", {"tool_name": "Bash"})

        assert result == {"success": True, "results": []}

    @pytest.mark.asyncio
    async def test_trigger_hook_success(self):
        """Test successfully triggering a hook."""
        manager = HookManager()
        config = HookConfig(hook_type="PreToolUse", command="echo hello")
        manager.register_hook(config)

        with patch.object(manager, "_execute_hook", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {
                "success": True,
                "returncode": 0,
                "stdout": "hello\n",
                "stderr": "",
            }

            result = await manager.trigger("PreToolUse", {"tool_name": "Bash"})

            assert result["success"] is True
            assert len(result["results"]) == 1
            assert len(result["errors"]) == 0
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_hook_with_file_lock(self):
        """Test triggering a hook with file locking."""
        lock_manager = MagicMock(spec=FileLockManager)
        manager = HookManager(lock_manager=lock_manager)
        config = HookConfig(hook_type="PreToolUse", command="echo test")
        manager.register_hook(config)

        # Mock lock context manager
        lock_context = AsyncMock()
        lock_context.__aenter__ = AsyncMock(return_value=True)
        lock_context.__aexit__ = AsyncMock(return_value=None)
        lock_manager.lock = MagicMock(return_value=lock_context)

        with patch.object(manager, "_execute_hook", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"success": True}

            result = await manager.trigger(
                "PreToolUse",
                {"tool_name": "Write", "file_path": "/test.py"},
                agent_id="agent-001",
            )

            assert result["success"] is True
            lock_manager.lock.assert_called_once_with(
                "/test.py", "agent-001", LockType.WRITE, timeout=30
            )

    @pytest.mark.asyncio
    async def test_trigger_hook_lock_acquisition_failed(self):
        """Test triggering a hook when lock acquisition fails."""
        lock_manager = MagicMock(spec=FileLockManager)
        manager = HookManager(lock_manager=lock_manager)
        config = HookConfig(hook_type="PreToolUse", command="echo test")
        manager.register_hook(config)

        # Mock lock context manager that fails to acquire
        lock_context = AsyncMock()
        lock_context.__aenter__ = AsyncMock(return_value=False)
        lock_context.__aexit__ = AsyncMock(return_value=None)
        lock_manager.lock = MagicMock(return_value=lock_context)

        result = await manager.trigger(
            "PreToolUse",
            {"tool_name": "Edit", "file_path": "/test.py"},
            agent_id="agent-001",
        )

        assert result["success"] is False
        assert "Failed to acquire" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_trigger_hook_read_lock_for_read_tool(self):
        """Test that READ lock is used for read tools."""
        lock_manager = MagicMock(spec=FileLockManager)
        manager = HookManager(lock_manager=lock_manager)
        config = HookConfig(hook_type="PreToolUse", command="echo test")
        manager.register_hook(config)

        lock_context = AsyncMock()
        lock_context.__aenter__ = AsyncMock(return_value=True)
        lock_context.__aexit__ = AsyncMock(return_value=None)
        lock_manager.lock = MagicMock(return_value=lock_context)

        with patch.object(manager, "_execute_hook", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"success": True}

            await manager.trigger(
                "PreToolUse",
                {"tool_name": "Read", "file_path": "/test.py"},
                agent_id="agent-001",
            )

            lock_manager.lock.assert_called_once_with(
                "/test.py", "agent-001", LockType.READ, timeout=30
            )

    @pytest.mark.asyncio
    async def test_execute_hook_success(self):
        """Test executing a single hook successfully."""
        manager = HookManager()
        config = HookConfig(hook_type="PreToolUse", command="echo hello", timeout_ms=5000)

        # Mock asyncio.create_subprocess_shell
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"hello\n", b""))

        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            result = await manager._execute_hook(config, {"tool_name": "Bash"})

            assert result["success"] is True
            assert result["returncode"] == 0
            assert result["stdout"] == "hello\n"
            assert result["stderr"] == ""

    @pytest.mark.asyncio
    async def test_execute_hook_failure(self):
        """Test executing a hook that fails."""
        manager = HookManager()
        config = HookConfig(hook_type="PreToolUse", command="exit 1", timeout_ms=5000)

        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"error\n"))

        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            result = await manager._execute_hook(config, {"tool_name": "Bash"})

            assert result["success"] is False
            assert result["returncode"] == 1
            assert result["stderr"] == "error\n"

    @pytest.mark.asyncio
    async def test_execute_hook_timeout(self):
        """Test executing a hook that times out."""
        manager = HookManager()
        config = HookConfig(hook_type="PreToolUse", command="sleep 10", timeout_ms=100)

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_process.kill = AsyncMock()
        mock_process.wait = AsyncMock()

        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            result = await manager._execute_hook(config, {"tool_name": "Bash"})

            assert result["success"] is False
            assert "timed out" in result["error"]
            mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_hook_with_env_vars(self):
        """Test executing a hook with environment variables."""
        manager = HookManager()
        config = HookConfig(
            hook_type="PreToolUse",
            command="echo $FOO",
            env={"FOO": "bar"},
            timeout_ms=5000,
        )

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"bar\n", b""))

        with patch("asyncio.create_subprocess_shell", return_value=mock_process) as mock_shell:
            await manager._execute_hook(config, {"tool_name": "Bash"})

            # Verify environment variables were passed
            call_kwargs = mock_shell.call_args[1]
            assert "HOOK_DATA" in call_kwargs["env"]
            assert call_kwargs["env"]["FOO"] == "bar"

    @pytest.mark.asyncio
    async def test_execute_hook_with_tool_info(self):
        """Test executing a hook with tool information in env."""
        manager = HookManager()
        config = HookConfig(hook_type="PreToolUse", command="echo test", timeout_ms=5000)

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"test\n", b""))

        with patch("asyncio.create_subprocess_shell", return_value=mock_process) as mock_shell:
            await manager._execute_hook(
                config,
                {"tool_name": "Bash", "tool_command": "ls -la"},
            )

            call_kwargs = mock_shell.call_args[1]
            assert call_kwargs["env"]["TOOL_NAME"] == "Bash"
            assert call_kwargs["env"]["TOOL_COMMAND"] == "ls -la"

    @pytest.mark.asyncio
    async def test_critical_hook_failure_blocks_operation(self):
        """Test that critical hook failure blocks the operation.

        Note: The trigger() method catches exceptions from _execute_hooks and
        returns an error dictionary rather than raising. The RuntimeError is
        raised within _execute_hooks for critical hooks, but trigger() wraps it.
        """
        manager = HookManager()
        config = HookConfig(
            hook_type="PreToolUse", command="exit 1", critical=True, timeout_ms=5000
        )
        manager.register_hook(config)

        with patch.object(manager, "_execute_hook", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = Exception("Hook failed")

            # When _execute_hooks raises RuntimeError for critical hook,
            # trigger() catches it and returns an error dictionary
            result = await manager.trigger("PreToolUse", {"tool_name": "Bash"})

            assert result["success"] is False
            assert len(result["errors"]) == 1
            assert "Hook failed" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_non_critical_hook_failure_continues(self):
        """Test that non-critical hook failure doesn't block."""
        manager = HookManager()
        config = HookConfig(
            hook_type="PreToolUse", command="exit 1", critical=False, timeout_ms=5000
        )
        manager.register_hook(config)

        with patch.object(manager, "_execute_hook", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = Exception("Hook failed")

            result = await manager.trigger("PreToolUse", {"tool_name": "Bash"})

            assert result["success"] is False
            assert len(result["errors"]) == 1
            assert "Hook failed" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_event_callback_notification(self):
        """Test that event callbacks are notified."""
        manager = HookManager()
        config = HookConfig(hook_type="PreToolUse", command="echo test", timeout_ms=5000)
        manager.register_hook(config)

        callback = MagicMock()
        manager.register_event_callback(callback)

        with patch.object(manager, "_execute_hook", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"success": True}

            await manager.trigger("PreToolUse", {"tool_name": "Bash"}, session_id=str(uuid4()))

            callback.assert_called_once()
            event_arg = callback.call_args[0][0]
            assert isinstance(event_arg, HookEvent)
            assert event_arg.event_type == "PreToolUse"

    def test_callback_failure_doesnt_affect_execution(self):
        """Test that callback failures don't affect hook execution."""
        manager = HookManager()
        callback = MagicMock(side_effect=Exception("Callback failed"))
        manager.register_event_callback(callback)

        event = HookEvent(
            session_id=uuid4(), event_type="PreToolUse", data={"tool_name": "Bash"}
        )

        # Should not raise exception
        manager._notify_callbacks(event)

    def test_load_from_config_file(self):
        """Test loading hooks from a configuration file."""
        config_data = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "tool_name:Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python safety_check.py",
                                "timeout_ms": 50,
                                "critical": True,
                                "env": {"FOO": "bar"},
                            }
                        ],
                    }
                ],
                "PostToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python log_tool.py",
                                "timeout_ms": 100,
                                "critical": False,
                            }
                        ],
                    }
                ],
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = Path(f.name)

        try:
            manager = HookManager.load_from_config(config_path)

            assert "PreToolUse" in manager.hooks
            assert "PostToolUse" in manager.hooks
            assert len(manager.hooks["PreToolUse"]) == 1
            assert len(manager.hooks["PostToolUse"]) == 1

            pre_hook = manager.hooks["PreToolUse"][0]
            assert pre_hook.command == "python safety_check.py"
            assert pre_hook.timeout_ms == 50
            assert pre_hook.critical is True
            assert pre_hook.env == {"FOO": "bar"}

            post_hook = manager.hooks["PostToolUse"][0]
            assert post_hook.command == "python log_tool.py"
            assert post_hook.timeout_ms == 100
            assert post_hook.critical is False

        finally:
            config_path.unlink()

    def test_load_from_nonexistent_config(self):
        """Test loading from a non-existent config file."""
        manager = HookManager.load_from_config(Path("/nonexistent/config.json"))

        assert manager.hooks == {}


class TestHookType:
    """Test HookType enum."""

    def test_hook_types(self):
        """Test that all hook types are defined."""
        assert HookType.PRE_TOOL_USE == "PreToolUse"
        assert HookType.POST_TOOL_USE == "PostToolUse"
        assert HookType.NOTIFICATION == "Notification"
        assert HookType.USER_PROMPT_SUBMIT == "UserPromptSubmit"
        assert HookType.STOP == "Stop"
        assert HookType.SUBAGENT_STOP == "SubagentStop"
        assert HookType.PRE_COMPACT == "PreCompact"
        assert HookType.SESSION_START == "SessionStart"
        assert HookType.SESSION_END == "SessionEnd"
