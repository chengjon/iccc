"""Subagent configuration loading system."""

import os
from pathlib import Path
from typing import Any, Optional

import yaml

from iccc.models.entities import ModelTier


class SubagentConfig:
    """Subagent configuration."""

    def __init__(
        self,
        name: str,
        description: str,
        model: ModelTier,
        system_prompt: str,
        tools: Optional[list[str]] = None,
        specialization: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        self.name = name
        self.description = description
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools or []  # Empty list means inherit all tools
        self.specialization = specialization
        self.metadata = metadata or {}


class SubagentLoader:
    """Load subagent configurations from multiple locations."""

    # Configuration search paths (priority order)
    SEARCH_PATHS = [
        # 1. CLI argument (handled externally)
        # 2. Project-level
        ".claude/agents",
        # 3. User-level
        str(Path.home() / ".claude" / "agents"),
        # 4. Built-in presets (handled by preset_agents.py)
    ]

    @classmethod
    def load_config(cls, agent_name: str, cli_path: Optional[str] = None) -> SubagentConfig:
        """
        Load agent configuration from first matching location.

        Args:
            agent_name: Name of the agent to load
            cli_path: Optional path provided via CLI argument (highest priority)

        Returns:
            SubagentConfig object

        Raises:
            FileNotFoundError: If config not found in any location
        """
        # Priority 1: CLI path
        if cli_path:
            config_path = Path(cli_path)
            if config_path.exists():
                return cls._load_from_file(config_path)

        # Priority 2-3: Search paths
        for search_dir in cls.SEARCH_PATHS:
            config_path = Path(search_dir) / f"{agent_name}.md"
            if config_path.exists():
                return cls._load_from_file(config_path)

        # Priority 4: Try built-in presets
        from iccc.agents.preset_agents import PresetAgents

        if agent_name in PresetAgents.PRESETS:
            return PresetAgents.get_config(agent_name)

        raise FileNotFoundError(
            f"Agent config '{agent_name}' not found in any location: {cls.SEARCH_PATHS}"
        )

    @classmethod
    def _load_from_file(cls, file_path: Path) -> SubagentConfig:
        """
        Load configuration from a markdown file with YAML frontmatter.

        Expected format:
        ```markdown
        ---
        name: frontend-dev
        description: Frontend development expert
        model: sonnet
        tools:
          - Read
          - Write
          - Edit
        specialization: frontend
        ---

        # System Prompt

        You are a frontend development expert specializing in React, Vue, and modern CSS...
        ```

        Args:
            file_path: Path to the config file

        Returns:
            SubagentConfig object
        """
        content = file_path.read_text()

        # Split YAML frontmatter from Markdown content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                yaml_content = parts[1].strip()
                markdown_content = parts[2].strip()
            else:
                raise ValueError(f"Invalid frontmatter format in {file_path}")
        else:
            # No frontmatter, use defaults
            yaml_content = ""
            markdown_content = content

        # Parse YAML frontmatter
        if yaml_content:
            config_dict = yaml.safe_load(yaml_content)
        else:
            config_dict = {}

        # Extract fields
        name = config_dict.get("name", file_path.stem)
        description = config_dict.get("description", "")
        model_str = config_dict.get("model", "sonnet")

        # Map model string to ModelTier
        model_map = {
            "haiku": ModelTier.HAIKU,
            "sonnet": ModelTier.SONNET,
            "opus": ModelTier.OPUS,
        }
        model = model_map.get(model_str.lower(), ModelTier.SONNET)

        tools = config_dict.get("tools", [])
        specialization = config_dict.get("specialization")
        metadata = config_dict.get("metadata", {})

        return SubagentConfig(
            name=name,
            description=description,
            model=model,
            system_prompt=markdown_content,
            tools=tools,
            specialization=specialization,
            metadata=metadata,
        )

    @classmethod
    def list_available_agents(cls) -> list[str]:
        """List all available agent configurations."""
        agents = set()

        # Search all paths
        for search_dir in cls.SEARCH_PATHS:
            search_path = Path(search_dir)
            if search_path.exists():
                for file_path in search_path.glob("*.md"):
                    agents.add(file_path.stem)

        # Add built-in presets
        from iccc.agents.preset_agents import PresetAgents

        agents.update(PresetAgents.PRESETS.keys())

        return sorted(agents)
