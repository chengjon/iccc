"""Tests for agent_coordinator hook script."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis_mock = MagicMock()
    redis_mock.set.return_value = True
    redis_mock.get.return_value = None
    redis_mock.delete.return_value = True
    redis_mock.publish.return_value = 1
    return redis_mock


class TestAgentCoordinator:
    """Tests for agent_coordinator.py hook script."""

    def test_get_agent_id(self):
        """Test agent ID extraction."""
        from iccc.hooks.scripts.agent_coordinator import get_agent_id

        with patch.dict(os.environ, {"AGENT_ID": "agent-123"}):
            assert get_agent_id() == "agent-123"

        with patch.dict(os.environ, {}, clear=True):
            assert get_agent_id() == "unknown-agent"

    def test_get_file_path_from_env(self):
        """Test file path extraction."""
        from iccc.hooks.scripts.agent_coordinator import get_file_path

        test_path = "/tmp/test.py"
        with patch.dict(os.environ, {"FILE_PATH": test_path}):
            result = get_file_path()
            assert result == Path(test_path)

    def test_get_file_path_from_hook_data(self):
        """Test file path from HOOK_DATA."""
        from iccc.hooks.scripts.agent_coordinator import get_file_path

        hook_data = {"file_path": "/tmp/test.py"}
        with patch.dict(os.environ, {"HOOK_DATA": json.dumps(hook_data)}):
            result = get_file_path()
            assert result == Path("/tmp/test.py")

    def test_acquire_file_lock_success(self, mock_redis):
        """Test successful lock acquisition."""
        from iccc.hooks.scripts.agent_coordinator import acquire_file_lock

        with patch("iccc.hooks.scripts.agent_coordinator.get_redis_client", return_value=mock_redis):
            result = acquire_file_lock(Path("/tmp/test.py"), "agent-1")
            assert result is True
            mock_redis.set.assert_called_once()

    def test_acquire_file_lock_no_redis(self):
        """Test lock acquisition without Redis (degraded mode)."""
        from iccc.hooks.scripts.agent_coordinator import acquire_file_lock

        with patch("iccc.hooks.scripts.agent_coordinator.get_redis_client", return_value=None):
            result = acquire_file_lock(Path("/tmp/test.py"), "agent-1")
            assert result is True  # Should succeed in degraded mode

    def test_release_file_lock(self, mock_redis):
        """Test lock release."""
        from iccc.hooks.scripts.agent_coordinator import release_file_lock

        mock_redis.get.return_value = "agent-1"  # Lock owned by agent-1

        with patch("iccc.hooks.scripts.agent_coordinator.get_redis_client", return_value=mock_redis):
            result = release_file_lock(Path("/tmp/test.py"), "agent-1")
            assert result is True
            mock_redis.delete.assert_called_once()

    def test_release_file_lock_wrong_owner(self, mock_redis):
        """Test lock release by non-owner."""
        from iccc.hooks.scripts.agent_coordinator import release_file_lock

        mock_redis.get.return_value = "agent-2"  # Lock owned by different agent

        with patch("iccc.hooks.scripts.agent_coordinator.get_redis_client", return_value=mock_redis):
            result = release_file_lock(Path("/tmp/test.py"), "agent-1")
            assert result is False
            mock_redis.delete.assert_not_called()

    def test_publish_completion_event(self, mock_redis):
        """Test publishing completion event."""
        from iccc.hooks.scripts.agent_coordinator import publish_completion_event

        with patch("iccc.hooks.scripts.agent_coordinator.get_redis_client", return_value=mock_redis):
            publish_completion_event("agent-1", "success", {"task_id": "123"})
            mock_redis.publish.assert_called_once()

            # Verify event structure
            call_args = mock_redis.publish.call_args
            assert call_args[0][0] == "agent_events"
            event_data = json.loads(call_args[0][1])
            assert event_data["agent_id"] == "agent-1"
            assert event_data["status"] == "success"

    def test_handle_pre_tool_use_non_write_tool(self):
        """Test PreToolUse for non-write tools."""
        from iccc.hooks.scripts.agent_coordinator import handle_pre_tool_use

        with patch.dict(os.environ, {"TOOL_NAME": "Read"}):
            result = handle_pre_tool_use()
            assert result == 0  # Should allow execution

    def test_main_invalid_mode(self):
        """Test main with invalid mode."""
        from iccc.hooks.scripts.agent_coordinator import main

        with patch("sys.argv", ["script.py", "invalid"]):
            result = main()
            assert result == 1
