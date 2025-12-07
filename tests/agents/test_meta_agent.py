"""Tests for meta-agent configuration generation."""

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from iccc.agents.meta_agent import MetaAgent, generate_agent


class TestMetaAgent:
    """Tests for MetaAgent class."""

    def test_list_templates(self):
        """Should list available agent templates."""
        meta = MetaAgent()
        templates = meta.list_templates()

        assert "code-reviewer" in templates
        assert "frontend-expert" in templates
        assert "backend-expert" in templates
        assert "test-expert" in templates

    def test_load_template_success(self):
        """Should load existing template."""
        meta = MetaAgent()
        content = meta.load_template("code-reviewer")

        assert "# Code Reviewer Agent" in content
        assert "**Specialization**: Code Review" in content

    def test_load_template_not_found(self):
        """Should raise ValueError for nonexistent template."""
        meta = MetaAgent()

        with pytest.raises(ValueError, match="Template 'nonexistent' not found"):
            meta.load_template("nonexistent")

    def test_select_base_template_frontend(self):
        """Should select frontend template for frontend tasks."""
        meta = MetaAgent()

        assert meta._select_base_template("Frontend UI components") == "frontend-expert"
        assert meta._select_base_template("React development") == "frontend-expert"
        assert meta._select_base_template("Vue component creation") == "frontend-expert"

    def test_select_base_template_backend(self):
        """Should select backend template for backend tasks."""
        meta = MetaAgent()

        assert meta._select_base_template("Backend API development") == "backend-expert"
        assert meta._select_base_template("Database migrations") == "backend-expert"
        assert meta._select_base_template("Server-side logic") == "backend-expert"

    def test_select_base_template_test(self):
        """Should select test template for testing tasks."""
        meta = MetaAgent()

        assert meta._select_base_template("Test automation") == "test-expert"
        assert meta._select_base_template("QA and testing") == "test-expert"

    def test_select_base_template_review(self):
        """Should select review template for code review tasks."""
        meta = MetaAgent()

        assert meta._select_base_template("Code review and audit") == "code-reviewer"
        assert meta._select_base_template("Security audit") == "code-reviewer"

    def test_select_base_template_default(self):
        """Should default to code-reviewer for unknown tasks."""
        meta = MetaAgent()

        assert meta._select_base_template("Documentation") == "code-reviewer"

    @pytest.mark.asyncio
    async def test_generate_agent_config_no_client(self):
        """Should raise error if API client not initialized."""
        meta = MetaAgent(api_key=None)

        with pytest.raises(ValueError, match="Anthropic client not initialized"):
            await meta.generate_agent_config(
                name="test-agent", specialization="Testing"
            )

    @pytest.mark.asyncio
    async def test_generate_agent_config_success(self):
        """Should generate agent config using AI."""
        # Mock Anthropic client
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text="""# Test Agent

**Specialization**: Testing and QA

**Model**: claude-sonnet-4-20250514

**Task Types**:
- unit_test
- integration_test

## System Prompt

You are a testing expert..."""
            )
        ]
        mock_client.messages.create.return_value = mock_response

        meta = MetaAgent(api_key="test-key")
        meta.client = mock_client

        config = await meta.generate_agent_config(
            name="test-agent", specialization="Testing and QA"
        )

        # Should include metadata header
        assert "name: test-agent" in config
        assert "specialization: Testing and QA" in config
        assert "generated_by: meta-agent" in config

        # Should include generated content
        assert "# Test Agent" in config
        assert "You are a testing expert" in config

        # Should call API
        mock_client.messages.create.assert_called_once()

    def test_validate_config_valid(self):
        """Should validate correct agent config."""
        meta = MetaAgent()

        config = """# Test Agent

**Specialization**: Testing

**Model**: claude-sonnet-4-20250514

**Task Types**:
- test

## System Prompt

Test prompt

## Rate Limits
Max 50 requests

## File Access Permissions
Read: all

## Tools Available
- Read
- Write
"""

        result = meta.validate_config(config)

        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_validate_config_missing_sections(self):
        """Should detect missing required sections."""
        meta = MetaAgent()

        config = """# Test Agent

Some incomplete config
"""

        result = meta.validate_config(config)

        assert result["valid"] is False
        assert len(result["errors"]) > 0
        assert any("Missing required section" in err for err in result["errors"])

    def test_validate_config_warnings(self):
        """Should warn about missing optional sections."""
        meta = MetaAgent()

        config = """# Test Agent

**Specialization**: Testing

**Model**: claude-sonnet-4-20250514

**Task Types**:
- test

## System Prompt

Test prompt
"""

        result = meta.validate_config(config)

        assert len(result["warnings"]) > 0
        assert any("Missing rate limit" in warn for warn in result["warnings"])

    def test_write_config_file(self, tmp_path):
        """Should write config to file."""
        meta = MetaAgent()

        config = "# Test Agent\n\nTest content"
        output_dir = tmp_path / "agents"

        output_path = meta.write_config_file("test-agent", config, output_dir)

        assert output_path.exists()
        assert output_path.name == "test-agent.md"
        assert output_path.read_text() == config


@pytest.mark.asyncio
async def test_generate_agent_function(tmp_path):
    """Test generate_agent helper function."""
    # Mock MetaAgent
    with patch("iccc.agents.meta_agent.MetaAgent") as MockMetaAgent:
        mock_meta = MockMetaAgent.return_value

        # Mock generate_agent_config
        mock_meta.generate_agent_config = AsyncMock(
            return_value="""# API Documenter

**Specialization**: API Documentation

## System Prompt

Expert in API docs...
"""
        )

        # Mock validate_config
        mock_meta.validate_config.return_value = {
            "valid": True,
            "errors": [],
            "warnings": [],
        }

        # Mock write_config_file
        expected_path = tmp_path / "api-documenter.md"
        mock_meta.write_config_file.return_value = expected_path

        # Call generate_agent
        result_path = await generate_agent(
            name="api-documenter",
            specialization="API documentation",
            output_dir=tmp_path,
        )

        # Verify
        assert result_path == expected_path
        mock_meta.generate_agent_config.assert_called_once()
        mock_meta.validate_config.assert_called_once()
        mock_meta.write_config_file.assert_called_once()
