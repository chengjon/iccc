"""Unit tests for Brain Engine."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from iccc.brain.engine import BrainEngine
from iccc.models.entities import Message, ModelTier
from iccc.parsers.markdown_parser import MarkdownTaskParser


class TestBrainEngine:
    """Tests for BrainEngine core logic."""

    @pytest.fixture
    def mock_specs(self):
        """Mock SpecManager."""
        with patch("iccc.brain.engine.SpecManager") as mock:
            specs_instance = mock.return_value
            
            # Setup mock return values
            specs_instance.load_ideas.return_value.content = "# IDEAS"
            specs_instance.load_institution.return_value.content = "# INSTITUTION"
            specs_instance.load_maintask.return_value.content = "# MAINTASK"
            
            yield specs_instance

    @pytest.fixture
    def mock_client(self):
        """Mock ClaudeClient."""
        mock = MagicMock()
        mock.send_message = AsyncMock()
        return mock

    @pytest.fixture
    def engine(self, tmp_path, mock_client, mock_specs):
        """Create BrainEngine instance with mocks."""
        return BrainEngine(project_root=tmp_path, client=mock_client)

    @pytest.mark.asyncio
    async def test_run_cycle(self, engine, mock_client, mock_specs):
        """Test full cognitive cycle execution."""
        # Setup mock responses
        mock_client.send_message.side_effect = [
            {"content": "# Updated IDEAS\n- [ ] New Req"},  # _update_ideas
            {"content": "# Updated MAINTASK\n#### Task TASK-001: Test"}  # _update_maintask
        ]

        await engine.run_cycle(user_request="Add login")

        # Verify interactions
        assert mock_client.send_message.call_count == 2
        mock_specs.save_ideas.assert_called_once_with("# Updated IDEAS\n- [ ] New Req")
        mock_specs.save_maintask.assert_called_once_with("# Updated MAINTASK\n#### Task TASK-001: Test")

    @pytest.mark.asyncio
    async def test_update_ideas(self, engine, mock_client, mock_specs):
        """Test IDEAS.md update logic."""
        mock_client.send_message.return_value = {"content": "New IDEAS Content"}
        
        await engine._update_ideas("Fix bug")
        
        # Verify prompts
        call_args = mock_client.send_message.call_args
        messages = call_args[1]["messages"]
        assert "Fix bug" in messages[0].content
        assert "New IDEAS Content" in str(mock_specs.save_ideas.call_args)

    @pytest.mark.asyncio
    async def test_update_maintask_parsing(self, engine, mock_client, mock_specs):
        """Test MAINTASK generation and parsing."""
        md_content = """# MAINTASK
#### Task TASK-001: Implement Login
- **Description**: User login with JWT
- **Type**: backend
- **Assignee**: worker
"""
        mock_client.send_message.return_value = {"content": md_content}
        
        with patch("iccc.brain.engine.MarkdownTaskParser.parse") as mock_parse:
            mock_parse.return_value = [{"id": "TASK-001", "title": "Implement Login"}]
            
            await engine._update_maintask()
            
            mock_specs.save_maintask.assert_called_with(md_content)
            mock_parse.assert_called_once_with(md_content)
            
            # Check if JSON file was written (using engine.project_root which is tmp_path)
            json_path = engine.project_root / ".iccc" / ".plans" / "current_tasks.json"
            assert json_path.exists()
            with open(json_path) as f:
                data = json.load(f)
                assert data[0]["id"] == "TASK-001"

    def test_parse_tasks_from_md_valid(self):
        """Test parsing valid Markdown task list via MarkdownTaskParser."""
        md_content = """
# Plan

#### Task TASK-001: Setup Repo
- **Description**: Init git and config
- **Type**: general_coding
- **Assignee**: manager

#### Task TASK-002: Create API
- **Description**: FastAPI setup
- **Type**: backend
"""
        tasks = MarkdownTaskParser.parse(md_content)
        
        assert len(tasks) == 2
        assert tasks[0]["id"] == "TASK-001"
        assert tasks[0]["title"] == "Setup Repo"
        assert tasks[0]["description"] == "Init git and config"
        assert tasks[0]["task_type"] == "general_coding"
        assert tasks[0]["assignee"] == "manager"
        
        assert tasks[1]["id"] == "TASK-002"
        assert tasks[1]["task_type"] == "backend"
        # Default assignee check if omitted in MD? The parser defaults to "worker"
        # but in this test string it's omitted for TASK-002
        assert tasks[1]["assignee"] == "worker" 

    def test_parse_tasks_from_md_malformed(self):
        """Test parsing robustness with malformed data via MarkdownTaskParser."""
        md_content = """
#### Task TASK-001: Good Task
- **Description**: Good

#### Task: Bad Header
- **Description**: Bad

#### Task TASK-003: Another Good
- **Description**: Good
"""
        tasks = MarkdownTaskParser.parse(md_content)
        
        assert len(tasks) == 2
        assert tasks[0]["id"] == "TASK-001"
        assert tasks[1]["id"] == "TASK-003"
