"""
Specification Management Core.
Handles parsing and generation of Spec-Driven documents (IDEAS, INSTITUTION, MAINTASK).
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


class SpecType(str, Enum):
    IDEAS = "IDEAS"
    INSTITUTION = "INSTITUTION"
    MAINTASK = "MAINTASK"


class BaseSpec(BaseModel):
    """Base class for all specifications."""
    
    version: str = Field(default="1.0.0")
    generated_at: datetime = Field(default_factory=datetime.now)
    content: str = ""

    def save(self, path: Path) -> None:
        """Save spec to file."""
        path.write_text(self.content, encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "BaseSpec":
        """Load spec from file."""
        if not path.exists():
            return cls(content="")
        content = path.read_text(encoding="utf-8")
        return cls(content=content)


class IdeasSpec(BaseSpec):
    """IDEAS.md - User Intent & Requirements."""
    
    requirements: list[dict[str, Any]] = Field(default_factory=list)
    
    def parse_requirements(self) -> list[dict[str, Any]]:
        """
        Parse requirements from markdown content.
        Looks for patterns like:
        #### Title
        **Description**: ...
        **Priority**: ...
        """
        # TODO: Implement robust regex parsing
        return self.requirements


class InstitutionSpec(BaseSpec):
    """INSTITUTION.md - Project Laws & Standards."""
    
    rules: list[str] = Field(default_factory=list)


class MainTaskSpec(BaseSpec):
    """MAINTASK.md - Task Distribution Plan."""
    
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    
    def parse_tasks(self) -> list[dict[str, Any]]:
        """
        Parse tasks from markdown content.
        Looks for:
        #### Task TASK-001: Title
        """
        # TODO: Implement robust regex parsing
        return self.tasks


class SpecManager:
    """Manager for handling spec file operations."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.ideas_path = project_root / "IDEAS.md"
        self.institution_path = project_root / "INSTITUTION.md"
        self.maintask_path = project_root / "MAINTASK.md"

    def load_ideas(self) -> IdeasSpec:
        return IdeasSpec.load(self.ideas_path)

    def load_institution(self) -> InstitutionSpec:
        return InstitutionSpec.load(self.institution_path)

    def load_maintask(self) -> MainTaskSpec:
        return MainTaskSpec.load(self.maintask_path)

    def save_ideas(self, content: str) -> None:
        IdeasSpec(content=content).save(self.ideas_path)

    def save_institution(self, content: str) -> None:
        InstitutionSpec(content=content).save(self.institution_path)

    def save_maintask(self, content: str) -> None:
        MainTaskSpec(content=content).save(self.maintask_path)
