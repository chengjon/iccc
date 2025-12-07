"""Tests for preset agents configuration."""

import pytest
from iccc.agents.preset_agents import PresetAgents
from iccc.models.entities import ModelTier

def test_list_presets():
    """Test listing available preset agents."""
    presets = PresetAgents.list_presets()
    assert isinstance(presets, list)
    assert len(presets) >= 5
    expected_presets = {
        "frontend-developer",
        "backend-developer",
        "test-engineer",
        "code-reviewer",
        "docs-writer",
    }
    assert expected_presets.issubset(set(presets))

def test_get_config_valid():
    """Test getting a valid preset configuration."""
    config = PresetAgents.get_config("frontend-developer")
    
    assert config.name == "frontend-developer"
    assert config.specialization == "frontend"
    assert config.model == ModelTier.SONNET
    assert "Read" in config.tools
    assert "React" in config.system_prompt
    assert "Vue.js" in config.system_prompt

def test_get_config_backend():
    """Test getting backend developer preset."""
    config = PresetAgents.get_config("backend-developer")
    assert config.name == "backend-developer"
    assert config.specialization == "backend"
    assert "API design" in config.system_prompt

def test_get_config_code_reviewer():
    """Test getting code reviewer preset."""
    config = PresetAgents.get_config("code-reviewer")
    assert config.name == "code-reviewer"
    assert config.model == ModelTier.OPUS
    assert "Write" not in config.tools
    assert "Edit" not in config.tools

def test_get_config_invalid():
    """Test getting an invalid preset configuration."""
    with pytest.raises(ValueError, match="Unknown preset agent"):
        PresetAgents.get_config("non-existent-agent")
