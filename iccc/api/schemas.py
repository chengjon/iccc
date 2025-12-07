"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# Project Schemas
class ProjectCreate(BaseModel):
    """Schema for creating a new project."""

    name: str = Field(..., min_length=1, max_length=200, description="Project name")
    directory: str = Field(..., description="Project root directory path")
    description: str | None = Field(None, max_length=1000, description="Project description")
    git_repo: str | None = Field(None, description="Git repository URL")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ProjectUpdate(BaseModel):
    """Schema for updating a project."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    status: str | None = Field(None, pattern="^(active|paused|completed|archived)$")
    metadata: dict[str, Any] | None = None


class ProjectResponse(BaseModel):
    """Schema for project response."""

    id: UUID
    name: str
    directory: str
    description: str | None
    git_repo: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any]

    class Config:
        from_attributes = True


# Agent Schemas
class AgentCreate(BaseModel):
    """Schema for creating/registering an agent."""

    agent_id: str = Field(..., min_length=1, max_length=100, description="Unique agent identifier")
    agent_type: str = Field(..., description="Agent type (master/worker)")
    model: str = Field(..., description="Claude model (haiku/sonnet/opus)")
    specialization: str | None = Field(None, description="Agent specialization area")
    worktree_path: str | None = Field(None, description="Git worktree path")
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentUpdate(BaseModel):
    """Schema for updating agent status."""

    status: str | None = Field(None, pattern="^(idle|busy|error|stopped)$")
    current_task_id: UUID | None = None
    metadata: dict[str, Any] | None = None


class AgentResponse(BaseModel):
    """Schema for agent response."""

    id: UUID
    agent_id: str
    agent_type: str
    model: str
    specialization: str | None
    status: str
    worktree_path: str | None
    current_task_id: UUID | None
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any]

    class Config:
        from_attributes = True


# Task Schemas
class TaskCreate(BaseModel):
    """Schema for creating a new task."""

    project_id: UUID = Field(..., description="Parent project ID")
    description: str = Field(..., min_length=1, max_length=2000)
    task_type: str = Field(..., description="Task type (feature/bug_fix/refactor/etc)")
    priority: int = Field(default=3, ge=1, le=5, description="Priority (1=highest, 5=lowest)")
    dependencies: list[UUID] = Field(default_factory=list, description="Dependent task IDs")
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskUpdate(BaseModel):
    """Schema for updating a task."""

    status: str | None = Field(None, pattern="^(pending|in_progress|completed|failed|cancelled)$")
    assigned_agent_id: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None


class TaskResponse(BaseModel):
    """Schema for task response."""

    id: UUID
    project_id: UUID
    description: str
    task_type: str
    status: str
    priority: int
    assigned_agent_id: str | None
    dependencies: list[UUID]
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    metadata: dict[str, Any]

    class Config:
        from_attributes = True


# Prompt Schemas
class PromptCreate(BaseModel):
    """Schema for creating a prompt template."""

    name: str = Field(..., min_length=1, max_length=200)
    template: str = Field(..., min_length=1, description="Prompt template with placeholders")
    category: str = Field(..., description="Prompt category (feature/bug_fix/review/etc)")
    variables: list[str] = Field(default_factory=list, description="Required template variables")
    metadata: dict[str, Any] = Field(default_factory=dict)


class PromptResponse(BaseModel):
    """Schema for prompt response."""

    id: UUID
    name: str
    template: str
    category: str
    variables: list[str]
    created_at: datetime
    metadata: dict[str, Any]

    class Config:
        from_attributes = True


# Error Response Schema
class ErrorResponse(BaseModel):
    """Standard error response schema."""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] | None = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.now)


# Pagination Schema
class PaginatedResponse(BaseModel):
    """Generic paginated response."""

    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int
