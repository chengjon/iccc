"""Integration tests for CLI commands."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from iccc.cli import cli, task_import
from iccc.models.entities import Project, TaskType, RoleType

class TestCliBrain:
    """Tests for 'brain' command group."""

    def test_brain_cycle_success(self):
        """Test 'brain cycle' command success."""
        runner = CliRunner()
        
        with patch("iccc.brain.engine.BrainEngine") as MockEngine:
            # Setup mock
            engine_instance = MockEngine.return_value
            engine_instance.run_cycle = AsyncMock()
            
            result = runner.invoke(cli, ["brain", "cycle", "--request", "Add feature"])
            
            assert result.exit_code == 0
            assert "Brain is thinking..." in result.output
            assert "Brain cycle completed successfully" in result.output
            
            engine_instance.run_cycle.assert_called_once_with(user_request="Add feature")

    def test_brain_cycle_failure(self):
        """Test 'brain cycle' command handling errors."""
        runner = CliRunner()
        
        with patch("iccc.brain.engine.BrainEngine") as MockEngine:
            engine_instance = MockEngine.return_value
            engine_instance.run_cycle = AsyncMock(side_effect=Exception("Brain freeze"))
            
            result = runner.invoke(cli, ["brain", "cycle"])
            
            assert result.exit_code == 1
            assert "Brain cycle failed: Brain freeze" in result.output


class TestCliTaskImport:
    """Tests for 'task import' command."""

    @pytest.fixture
    def task_file(self, tmp_path):
        """Create a temporary task JSON file."""
        tasks = [
            {
                "id": "TASK-1",
                "title": "Worker Task",
                "description": "Simple task",
                "task_type": "general_coding"
            },
            {
                "id": "TASK-2",
                "title": "Manager Task",
                "description": "Complex task",
                "task_type": "architecture_design"
            }
        ]
        p = tmp_path / "tasks.json"
        with open(p, "w") as f:
            json.dump(tasks, f)
        return p

    def test_task_import_success(self, task_file):
        """Test successful task import."""
        runner = CliRunner()
        
        # Patch classes where they are USED (iccc.cli namespace for top-level imports)
        # RedisTaskQueue is imported locally inside function, so we patch source
        with patch("iccc.cli.MongoDBClient") as MockDB, \
             patch("iccc.cli.ProjectRepository") as MockProjectRepo, \
             patch("iccc.cli.TaskRepository") as MockTaskRepo, \
             patch("iccc.queue.redis_queue.RedisTaskQueue") as MockQueue:
             
            # Setup DB/Repo mocks
            db_client = MockDB.return_value
            db_client.connect = AsyncMock()
            db_client.disconnect = AsyncMock()
            
            proj_repo = MockProjectRepo.return_value
            proj_repo.get_by_name = AsyncMock(return_value=Project(
                id="123e4567-e89b-12d3-a456-426614174000",
                name="test-project",
                directory="/tmp"
            ))
            
            task_repo = MockTaskRepo.return_value
            task_repo.create = AsyncMock()
            
            queue = MockQueue.return_value
            queue.connect = AsyncMock()
            queue.disconnect = AsyncMock()
            queue.enqueue = AsyncMock()
            
            result = runner.invoke(cli, [
                "task", "import", 
                "--project", "test-project", 
                "--file", str(task_file)
            ])
            
            assert result.exit_code == 0
            assert "Successfully imported 2 tasks" in result.output
            
            # Verify Enqueue calls
            assert queue.enqueue.call_count == 2
            
            # Verify roles
            # Call args are (task, role=RoleType.XXX)
            args_list = queue.enqueue.call_args_list
            
            # First task (General Coding) -> Worker
            assert args_list[0][1]['role'] == RoleType.WORKER
            # Second task (Architecture) -> Manager
            assert args_list[1][1]['role'] == RoleType.MANAGER

    def test_task_import_file_not_found(self):
        """Test import with missing file."""
        runner = CliRunner()
        result = runner.invoke(cli, ["task", "import", "--project", "p", "--file", "missing.json"])
        assert "File not found" in result.output

    def test_task_import_project_not_found(self, task_file):
        """Test import when project doesn't exist."""
        runner = CliRunner()
        
        with patch("iccc.cli.MongoDBClient") as MockDB, \
             patch("iccc.cli.ProjectRepository") as MockProjectRepo:
             
            # Must mock async methods on DB client
            db_client = MockDB.return_value
            db_client.connect = AsyncMock()
            db_client.disconnect = AsyncMock()
             
            proj_repo = MockProjectRepo.return_value
            proj_repo.get_by_name = AsyncMock(return_value=None)
            
            result = runner.invoke(cli, [
                "task", "import", 
                "--project", "missing-project", 
                "--file", str(task_file)
            ])
            
            assert result.exit_code == 1
            assert "Project 'missing-project' not found" in result.output
