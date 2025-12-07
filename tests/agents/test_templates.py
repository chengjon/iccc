"""Tests for agent template loading and validation."""

from pathlib import Path

import pytest

from iccc.agents.meta_agent import MetaAgent


class TestAgentTemplates:
    """Tests for agent template files."""

    @pytest.fixture
    def meta_agent(self):
        """Create MetaAgent instance."""
        return MetaAgent()

    @pytest.fixture
    def template_dir(self):
        """Get template directory path."""
        return Path(__file__).parent.parent.parent / "iccc" / "agents" / "templates"

    def test_template_directory_exists(self, template_dir):
        """Template directory should exist."""
        assert template_dir.exists()
        assert template_dir.is_dir()

    def test_all_templates_exist(self, template_dir, meta_agent):
        """All declared templates should have corresponding files."""
        for template_name, filename in meta_agent.TEMPLATES.items():
            template_file = template_dir / filename
            assert template_file.exists(), f"Template file missing: {filename}"

    def test_code_reviewer_template_structure(self, meta_agent):
        """Code reviewer template should have required structure."""
        content = meta_agent.load_template("code-reviewer")

        # Title
        assert "# Code Reviewer Agent" in content

        # Required metadata
        assert "**Specialization**:" in content
        assert "**Model**:" in content
        assert "**Task Types**:" in content

        # Required sections
        assert "## System Prompt" in content
        assert "## Review Checklist" in content
        assert "## Output Format" in content
        assert "## Rate Limits" in content
        assert "## File Access Permissions" in content
        assert "## Tools Available" in content
        assert "## Example Invocation" in content

        # Key content
        assert "Code Quality" in content
        assert "Security" in content
        assert "Performance" in content
        assert "Testing" in content

    def test_frontend_expert_template_structure(self, meta_agent):
        """Frontend expert template should have required structure."""
        content = meta_agent.load_template("frontend-expert")

        # Title
        assert "# Frontend Expert Agent" in content

        # Required sections
        assert "## System Prompt" in content
        assert "## Development Guidelines" in content
        assert "## Technology Stack Preferences" in content
        assert "## Quality Gates" in content

        # Key content
        assert "React" in content
        assert "TypeScript" in content
        assert "Accessibility" in content
        assert "Performance" in content

    def test_backend_expert_template_structure(self, meta_agent):
        """Backend expert template should have required structure."""
        content = meta_agent.load_template("backend-expert")

        # Title
        assert "# Backend Expert Agent" in content

        # Required sections
        assert "## System Prompt" in content
        assert "## Development Guidelines" in content
        assert "## Architecture Patterns" in content
        assert "## Quality Gates" in content

        # Key content
        assert "API Design" in content
        assert "Database" in content
        assert "Authentication" in content
        assert "Security" in content

    def test_test_expert_template_structure(self, meta_agent):
        """Test expert template should have required structure."""
        content = meta_agent.load_template("test-expert")

        # Title
        assert "# Test Expert Agent" in content

        # Required sections
        assert "## System Prompt" in content
        assert "## Development Guidelines" in content
        assert "## Test Coverage Goals" in content
        assert "## Quality Gates" in content

        # Key content
        assert "Test-Driven Development" in content
        assert "pytest" in content
        assert "Coverage" in content

    def test_all_templates_have_rate_limits(self, meta_agent):
        """All templates should specify rate limits."""
        for template_name in meta_agent.TEMPLATES.keys():
            content = meta_agent.load_template(template_name)
            assert "## Rate Limits" in content, f"{template_name} missing rate limits"

    def test_all_templates_have_file_permissions(self, meta_agent):
        """All templates should specify file access permissions."""
        for template_name in meta_agent.TEMPLATES.keys():
            content = meta_agent.load_template(template_name)
            assert (
                "## File Access Permissions" in content
            ), f"{template_name} missing file permissions"

    def test_all_templates_have_tools(self, meta_agent):
        """All templates should specify available tools."""
        for template_name in meta_agent.TEMPLATES.keys():
            content = meta_agent.load_template(template_name)
            assert (
                "## Tools Available" in content
            ), f"{template_name} missing tools section"

    def test_all_templates_have_examples(self, meta_agent):
        """All templates should have usage examples."""
        for template_name in meta_agent.TEMPLATES.keys():
            content = meta_agent.load_template(template_name)
            assert (
                "## Example Invocation" in content
                or "Example:" in content
                or "```bash" in content
            ), f"{template_name} missing examples"

    def test_template_validation(self, meta_agent):
        """All templates should pass validation."""
        for template_name in meta_agent.TEMPLATES.keys():
            content = meta_agent.load_template(template_name)
            result = meta_agent.validate_config(content)

            # Should be valid (no errors)
            assert result["valid"], f"{template_name} validation failed: {result['errors']}"

            # Warnings are acceptable but should be minimal
            assert len(result["warnings"]) == 0, f"{template_name} has warnings: {result['warnings']}"
