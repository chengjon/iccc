"""Tests for auto_test hook script."""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_test_file(tmp_path):
    """Create a temporary test file."""
    test_file = tmp_path / "test_example.py"
    test_file.write_text("""
def test_example():
    assert True
""")
    return test_file


@pytest.fixture
def temp_ts_file(tmp_path):
    """Create a temporary TypeScript file."""
    ts_file = tmp_path / "example.ts"
    ts_file.write_text("""
const x: number = 42;
export default x;
""")
    return ts_file


class TestAutoTestScript:
    """Tests for auto_test.py hook script."""

    def test_is_typescript_file(self, temp_ts_file):
        """Test TypeScript file detection."""
        from iccc.hooks.scripts.auto_test import is_typescript_file

        assert is_typescript_file(temp_ts_file) is True
        assert is_typescript_file(Path("test.py")) is False

    def test_is_python_file(self, temp_test_file):
        """Test Python file detection."""
        from iccc.hooks.scripts.auto_test import is_python_file

        assert is_python_file(temp_test_file) is True
        assert is_python_file(Path("test.ts")) is False

    def test_is_test_file(self, temp_test_file):
        """Test test file detection."""
        from iccc.hooks.scripts.auto_test import is_test_file

        assert is_test_file(temp_test_file) is True
        assert is_test_file(Path("example.py")) is False
        assert is_test_file(Path("tests/test_foo.py")) is True

    def test_get_file_path_from_env(self, temp_test_file):
        """Test extracting file path from environment."""
        from iccc.hooks.scripts.auto_test import get_file_path

        # Test with FILE_PATH env var
        with patch.dict(os.environ, {"FILE_PATH": str(temp_test_file)}):
            result = get_file_path()
            assert result == temp_test_file

    def test_get_file_path_from_hook_data(self, temp_test_file):
        """Test extracting file path from HOOK_DATA."""
        from iccc.hooks.scripts.auto_test import get_file_path

        hook_data = {"file_path": str(temp_test_file)}
        with patch.dict(os.environ, {"HOOK_DATA": json.dumps(hook_data)}):
            result = get_file_path()
            assert result == temp_test_file

    @patch("subprocess.run")
    def test_run_command_success(self, mock_run):
        """Test successful command execution."""
        from iccc.hooks.scripts.auto_test import run_command

        mock_run.return_value = subprocess.CompletedProcess(
            args=["test"],
            returncode=0,
            stdout="Success",
            stderr="",
        )

        result = run_command(["test"], "Test command")
        assert result is True

    @patch("subprocess.run")
    def test_run_command_failure(self, mock_run):
        """Test failed command execution."""
        from iccc.hooks.scripts.auto_test import run_command

        mock_run.return_value = subprocess.CompletedProcess(
            args=["test"],
            returncode=1,
            stdout="",
            stderr="Error",
        )

        result = run_command(["test"], "Test command")
        assert result is False

    def test_trigger_tests_skip_non_write_tool(self):
        """Test that non-write tools are skipped."""
        # Import main function
        from iccc.hooks.scripts.auto_test import main

        with patch.dict(os.environ, {"TOOL_NAME": "Read"}):
            result = main()
            assert result == 0  # Should exit without running tests
