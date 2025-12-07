"""Tests for subagent configuration loading."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from iccc.agents.subagent import SubagentConfig, SubagentLoader
from iccc.models.entities import ModelTier

class TestSubagentConfig:
    """Tests for SubagentConfig class."""

    def test_init_defaults(self):
        """Test initialization with default values."""
        config = SubagentConfig(
            name="test-agent",
            description="A test agent",
            model=ModelTier.SONNET,
            system_prompt="You are a test agent."
        )
        assert config.name == "test-agent"
        assert config.description == "A test agent"
        assert config.model == ModelTier.SONNET
        assert config.system_prompt == "You are a test agent."
        assert config.tools == []
        assert config.specialization is None
        assert config.metadata == {}

    def test_init_custom(self):
        """Test initialization with custom values."""
        config = SubagentConfig(
            name="custom-agent",
            description="Custom agent",
            model=ModelTier.HAIKU,
            system_prompt="Custom prompt",
            tools=["Read", "Write"],
            specialization="custom",
            metadata={"key": "value"}
        )
        assert config.tools == ["Read", "Write"]
        assert config.specialization == "custom"
        assert config.metadata == {"key": "value"}


class TestSubagentLoader:
    """Tests for SubagentLoader class."""

    @pytest.fixture
    def mock_agent_file(self, tmp_path):
        """Create a mock agent definition file."""
        agent_dir = tmp_path / "agents"
        agent_dir.mkdir()
        file_path = agent_dir / "test-agent.md"
        
        content = """---
name: test-agent
description: A test agent from file
model: haiku
tools:
  - Read
  - Glob
specialization: testing
metadata:
  version: 1.0
---

# System Prompt

You are a file-based test agent.
"""
        file_path.write_text(content)
        return file_path

    def test_load_from_file_valid(self, mock_agent_file):
        """Test loading configuration from a valid file."""
        config = SubagentLoader._load_from_file(mock_agent_file)
        
        assert config.name == "test-agent"
        assert config.description == "A test agent from file"
        assert config.model == ModelTier.HAIKU
        assert config.tools == ["Read", "Glob"]
        assert config.specialization == "testing"
        assert config.metadata == {"version": 1.0}
        assert "You are a file-based test agent." in config.system_prompt
        assert "# System Prompt" in config.system_prompt

    def test_load_from_file_no_frontmatter(self, tmp_path):
        """Test loading from a file without frontmatter."""
        file_path = tmp_path / "simple.md"
        file_path.write_text("Just a prompt.")
        
        config = SubagentLoader._load_from_file(file_path)
        
        assert config.name == "simple"  # Should default to stem
        assert config.description == ""
        assert config.model == ModelTier.SONNET  # Default
        assert config.system_prompt == "Just a prompt."

    def test_load_from_file_invalid_frontmatter(self, tmp_path):
        """Test loading from a file with invalid frontmatter format."""
        file_path = tmp_path / "invalid.md"
        file_path.write_text("---\ninvalid yaml\n---\nprompt")
        
        # This implementation might just load empty dict or fail depending on yaml parser
        # The code manually splits on "---", so let's test the split logic check
        file_path_broken = tmp_path / "broken.md"
        file_path_broken.write_text("---\nonly start\n")
        
        # If it doesn't have 3 parts after split, it should fail or treat as text?
        # Looking at code: if content.startswith("---"): parts = content.split("---", 2)
        # If len(parts) < 3, it raises ValueError.
        
        with pytest.raises(ValueError, match="Invalid frontmatter format"):
            SubagentLoader._load_from_file(file_path_broken)

    @patch("iccc.agents.subagent.SubagentLoader._load_from_file")
    def test_load_config_cli_priority(self, mock_load, tmp_path):
        """Test that CLI path takes priority."""
        mock_config = MagicMock(spec=SubagentConfig)
        mock_load.return_value = mock_config
        
        dummy_path = tmp_path / "cli_agent.md"
        dummy_path.touch()
        
        config = SubagentLoader.load_config("any-name", cli_path=str(dummy_path))
        
        assert config == mock_config
        mock_load.assert_called_once_with(dummy_path)

    @patch("iccc.agents.preset_agents.PresetAgents.get_config")
    @patch("iccc.agents.preset_agents.PresetAgents.PRESETS", {"preset-agent": {}})
    def test_load_config_preset_fallback(self, mock_get_config):
        """Test fallback to preset agents."""
        mock_config = MagicMock(spec=SubagentConfig)
        mock_get_config.return_value = mock_config
        
        # Ensure SEARCH_PATHS are empty or don't match to force fallback
        with patch.object(SubagentLoader, 'SEARCH_PATHS', []):
            config = SubagentLoader.load_config("preset-agent")
            
        assert config == mock_config
        mock_get_config.assert_called_once_with("preset-agent")

    def test_load_config_not_found(self):
        """Test error when config is not found anywhere."""
        with patch.object(SubagentLoader, 'SEARCH_PATHS', []):
             with pytest.raises(FileNotFoundError, match="not found in any location"):
                SubagentLoader.load_config("non-existent")

    def test_list_available_agents(self, tmp_path):
        """Test listing all available agents."""
        # Create some dummy files in a temp dir
        agent_dir = tmp_path / "agents"
        agent_dir.mkdir()
        (agent_dir / "custom1.md").touch()
        (agent_dir / "custom2.md").touch()
        
        # Patch SEARCH_PATHS to include our temp dir
        with patch.object(SubagentLoader, 'SEARCH_PATHS', [str(agent_dir)]):
            agents = SubagentLoader.list_available_agents()
            
            assert "custom1" in agents
            assert "custom2" in agents
            assert "frontend-developer" in agents  # From presets

