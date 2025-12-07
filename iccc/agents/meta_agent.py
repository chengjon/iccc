#!/usr/bin/env python3
"""
Meta-agent for generating new agent configurations.

This module provides the MetaAgent class which can generate new agent
configurations based on specialization requirements. It uses templates
and AI-powered generation to create well-structured agent definitions.
"""

import os
from pathlib import Path
from typing import Any

import yaml
from anthropic import AsyncAnthropic


class MetaAgent:
    """Meta-agent that generates new agent configurations."""

    TEMPLATE_DIR = Path(__file__).parent / "templates"
    AGENT_DIR = Path(".claude/agents")

    # Agent template categories
    TEMPLATES = {
        "code-reviewer": "code_reviewer.md",
        "frontend-expert": "frontend_expert.md",
        "backend-expert": "backend_expert.md",
        "test-expert": "test_expert.md",
    }

    # Model recommendations by task complexity
    MODEL_RECOMMENDATIONS = {
        "simple": "claude-3-5-haiku-latest",  # Fast tasks, file ops
        "moderate": "claude-sonnet-4-20250514",  # General coding
        "complex": "claude-opus-4-20250514",  # Architecture, critical work
    }

    def __init__(self, api_key: str | None = None):
        """
        Initialize meta-agent.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if self.api_key:
            self.client = AsyncAnthropic(api_key=self.api_key)
        else:
            self.client = None

    def list_templates(self) -> list[str]:
        """
        List available agent templates.

        Returns:
            List of template names
        """
        return list(self.TEMPLATES.keys())

    def load_template(self, template_name: str) -> str:
        """
        Load agent template content.

        Args:
            template_name: Name of template to load

        Returns:
            Template file content

        Raises:
            ValueError: If template not found
        """
        if template_name not in self.TEMPLATES:
            raise ValueError(
                f"Template '{template_name}' not found. "
                f"Available templates: {', '.join(self.TEMPLATES.keys())}"
            )

        template_file = self.TEMPLATE_DIR / self.TEMPLATES[template_name]
        return template_file.read_text()

    async def generate_agent_config(
        self,
        name: str,
        specialization: str,
        base_template: str | None = None,
        complexity: str = "moderate",
        custom_requirements: str | None = None,
    ) -> str:
        """
        Generate a new agent configuration using AI.

        Args:
            name: Agent name (e.g., "api-documenter")
            specialization: Agent specialization (e.g., "API documentation")
            base_template: Base template to use (default: auto-select)
            complexity: Task complexity (simple/moderate/complex)
            custom_requirements: Additional requirements for the agent

        Returns:
            Generated agent configuration in markdown format

        Raises:
            ValueError: If client not initialized or invalid parameters
        """
        if not self.client:
            raise ValueError(
                "Anthropic client not initialized. "
                "Provide API key or set ANTHROPIC_API_KEY environment variable."
            )

        # Auto-select base template if not provided
        if not base_template:
            base_template = self._select_base_template(specialization)

        # Load template content
        template_content = self.load_template(base_template)

        # Select model based on complexity
        model = self.MODEL_RECOMMENDATIONS.get(complexity, "claude-sonnet-4-20250514")

        # Generate agent config using AI
        prompt = self._build_generation_prompt(
            name=name,
            specialization=specialization,
            template_content=template_content,
            custom_requirements=custom_requirements,
        )

        response = await self.client.messages.create(
            model="claude-sonnet-4-20250514",  # Use Sonnet for meta-reasoning
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )

        config = response.content[0].text

        # Add metadata header
        metadata = f"""---
name: {name}
specialization: {specialization}
base_template: {base_template}
recommended_model: {model}
complexity: {complexity}
generated_by: meta-agent
---

"""
        return metadata + config

    def validate_config(self, config: str) -> dict[str, Any]:
        """
        Validate agent configuration.

        Args:
            config: Agent configuration in markdown format

        Returns:
            Validation result with errors and warnings

        Example:
            {
                "valid": True,
                "errors": [],
                "warnings": ["Missing rate limit specification"]
            }
        """
        errors = []
        warnings = []

        # Check required sections
        required_sections = [
            "# ",  # Title
            "**Specialization**:",
            "**Model**:",
            "**Task Types**:",
            "## System Prompt",
        ]

        for section in required_sections:
            if section not in config:
                errors.append(f"Missing required section: {section}")

        # Check for rate limits
        if "Rate Limits" not in config:
            warnings.append("Missing rate limit specification")

        # Check for file permissions
        if "File Access Permissions" not in config:
            warnings.append("Missing file access permissions")

        # Check for tools specification
        if "Tools Available" not in config:
            warnings.append("Missing tools specification")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def write_config_file(self, name: str, config: str, output_dir: Path | None = None) -> Path:
        """
        Write agent configuration to file.

        Args:
            name: Agent name
            config: Agent configuration content
            output_dir: Output directory (default: .claude/agents)

        Returns:
            Path to written file
        """
        output_dir = output_dir or self.AGENT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"{name}.md"
        output_file.write_text(config)

        return output_file

    def _select_base_template(self, specialization: str) -> str:
        """
        Auto-select base template based on specialization.

        Args:
            specialization: Agent specialization

        Returns:
            Best matching template name
        """
        spec_lower = specialization.lower()

        # Keyword-based template selection
        if any(kw in spec_lower for kw in ["frontend", "ui", "react", "vue", "component"]):
            return "frontend-expert"
        elif any(kw in spec_lower for kw in ["backend", "api", "database", "server"]):
            return "backend-expert"
        elif any(kw in spec_lower for kw in ["test", "qa", "quality"]):
            return "test-expert"
        elif any(kw in spec_lower for kw in ["review", "audit", "security"]):
            return "code-reviewer"
        else:
            # Default to code reviewer for general tasks
            return "code-reviewer"

    def _build_generation_prompt(
        self,
        name: str,
        specialization: str,
        template_content: str,
        custom_requirements: str | None,
    ) -> str:
        """
        Build prompt for agent config generation.

        Args:
            name: Agent name
            specialization: Agent specialization
            template_content: Base template content
            custom_requirements: Additional requirements

        Returns:
            Generation prompt
        """
        prompt = f"""Generate a new AI agent configuration for a specialized agent.

**Agent Details:**
- Name: {name}
- Specialization: {specialization}

**Base Template:**
{template_content}

**Instructions:**
1. Adapt the base template to the new specialization
2. Update the system prompt to reflect the specific expertise
3. Add relevant task types and examples
4. Include appropriate tools and permissions
5. Define quality gates specific to this specialization
6. Keep the same markdown structure and formatting

"""

        if custom_requirements:
            prompt += f"""
**Additional Requirements:**
{custom_requirements}

"""

        prompt += """
**Output Format:**
Provide the complete agent configuration in markdown format, ready to be saved to a .md file.
Do NOT include the YAML frontmatter (metadata header) - I will add that automatically.
Start directly with the agent title (# Agent Name).
"""

        return prompt


async def generate_agent(
    name: str,
    specialization: str,
    base_template: str | None = None,
    complexity: str = "moderate",
    output_dir: Path | None = None,
) -> Path:
    """
    Generate and save a new agent configuration.

    Args:
        name: Agent name (e.g., "api-documenter")
        specialization: Agent specialization
        base_template: Base template to use (optional)
        complexity: Task complexity (simple/moderate/complex)
        output_dir: Output directory (default: .claude/agents)

    Returns:
        Path to generated agent config file

    Example:
        >>> path = await generate_agent(
        ...     name="api-documenter",
        ...     specialization="API documentation and OpenAPI specs"
        ... )
        >>> print(f"Generated agent at: {path}")
    """
    meta = MetaAgent()

    # Generate config
    config = await meta.generate_agent_config(
        name=name,
        specialization=specialization,
        base_template=base_template,
        complexity=complexity,
    )

    # Validate
    validation = meta.validate_config(config)
    if not validation["valid"]:
        raise ValueError(f"Invalid config: {validation['errors']}")

    if validation["warnings"]:
        print("⚠️  Warnings:")
        for warning in validation["warnings"]:
            print(f"  - {warning}")

    # Write to file
    output_path = meta.write_config_file(name, config, output_dir)
    print(f"✅ Generated agent config: {output_path}")

    return output_path
