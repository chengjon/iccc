"""Core data models for iCCC system."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ModelTier(str, Enum):
    """Claude model tiers."""

    HAIKU = "claude-3-5-haiku-latest"
    SONNET = "claude-sonnet-4-20250514"
    OPUS = "claude-opus-4-20250514"


class ProjectStatus(str, Enum):
    """Project lifecycle status."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class AgentStatus(str, Enum):
    """Agent lifecycle status."""

    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    STOPPED = "stopped"


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class TaskType(str, Enum):
    """Task classification types for model selection (33 types)."""

    # Haiku tasks (fast, simple)
    FILE_RENAME = "file_rename"
    SIMPLE_REFACTOR = "simple_refactor"
    GENERATE_BOILERPLATE = "generate_boilerplate"
    FORMAT_CODE = "format_code"
    SIMPLE_DOCUMENTATION = "simple_documentation"
    ADD_COMMENTS = "add_comments"
    RENAME_VARIABLE = "rename_variable"
    ADD_TYPE_HINTS = "add_type_hints"
    GENERATE_GETTER_SETTER = "generate_getter_setter"
    CREATE_CONFIG_FILE = "create_config_file"

    # Sonnet tasks (balanced)
    GENERAL_CODING = "general_coding"
    CODE_REFACTOR = "code_refactor"
    BUG_FIX = "bug_fix"
    TEST_WRITING = "test_writing"
    API_IMPLEMENTATION = "api_implementation"
    DATABASE_QUERY = "database_query"
    UI_COMPONENT = "ui_component"
    DATA_PROCESSING = "data_processing"
    ERROR_HANDLING = "error_handling"
    LOGGING_IMPLEMENTATION = "logging_implementation"
    VALIDATION_LOGIC = "validation_logic"
    FEATURE_IMPLEMENTATION = "feature_implementation"
    CODE_REVIEW = "code_review"
    DEPENDENCY_UPDATE = "dependency_update"
    DOCUMENTATION_DETAILED = "documentation_detailed"

    # Opus tasks (complex, critical)
    ARCHITECTURE_DESIGN = "architecture_design"
    SECURITY_CRITICAL = "security_critical"
    COMPLEX_ALGORITHM = "complex_algorithm"
    SYSTEM_INTEGRATION = "system_integration"
    PRODUCTION_CRITICAL = "production_critical"
    PERFORMANCE_OPTIMIZATION = "performance_optimization"
    SCALABILITY_DESIGN = "scalability_design"
    DATABASE_SCHEMA_DESIGN = "database_schema_design"
    API_DESIGN = "api_design"
    SECURITY_AUDIT = "security_audit"
    DISTRIBUTED_SYSTEM_DESIGN = "distributed_system_design"
    MIGRATION_STRATEGY = "migration_strategy"
    DISASTER_RECOVERY_PLAN = "disaster_recovery_plan"


class Project(BaseModel):
    """Project entity representing a codebase being worked on."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    directory: str
    status: ProjectStatus = ProjectStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_encoders={UUID: str, datetime: lambda v: v.isoformat()}
    )


class Agent(BaseModel):
    """Agent entity representing a Claude instance."""

    id: str  # e.g., "agent-001"
    project_id: UUID
    name: str
    agent_type: str  # e.g., "frontend-developer", "backend-developer"
    model: ModelTier
    specialization: Optional[str] = None  # e.g., "frontend", "backend", "testing"
    status: AgentStatus = AgentStatus.IDLE
    worktree_path: Optional[str] = None
    tools: list[str] = Field(default_factory=list)  # Available tools
    created_at: datetime = Field(default_factory=datetime.now)
    last_active: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_encoders={UUID: str, datetime: lambda v: v.isoformat()}
    )


class TaskComplexity(BaseModel):
    """Task complexity scoring for model selection."""

    reasoning_depth: int = Field(ge=1, le=5, description="1-5: How much reasoning is needed")
    code_scope: int = Field(ge=1, le=5, description="1-5: How many files/components affected")
    critical_importance: int = Field(
        ge=1, le=5, description="1-5: Impact if done wrong (weighted 2x)"
    )
    context_needed: int = Field(ge=1, le=5, description="1-5: How much context to understand")

    def calculate_score(self) -> float:
        """Calculate complexity score (0-5 scale)."""
        return (
            self.reasoning_depth
            + self.code_scope
            + self.critical_importance * 2
            + self.context_needed
        ) / 5


class Task(BaseModel):
    """Task entity representing work to be done."""

    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    description: str
    task_type: TaskType = TaskType.GENERAL_CODING
    complexity: Optional[TaskComplexity] = None
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent_id: Optional[str] = None
    dependencies: list[UUID] = Field(default_factory=list)  # Task IDs that must complete first
    result: Optional[str] = None
    error: Optional[str] = None
    files_modified: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_encoders={UUID: str, datetime: lambda v: v.isoformat()}
    )


class Message(BaseModel):
    """Single message in a conversation."""

    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()}
    )


class Session(BaseModel):
    """Session entity representing a conversation between orchestrator and agent."""

    id: UUID = Field(default_factory=uuid4)
    agent_id: str
    task_id: UUID
    messages: list[Message] = Field(default_factory=list)
    token_usage: dict[str, int] = Field(
        default_factory=lambda: {"input": 0, "output": 0, "total": 0}
    )
    started_at: datetime = Field(default_factory=datetime.now)
    ended_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_encoders={UUID: str, datetime: lambda v: v.isoformat()}
    )


class HookEvent(BaseModel):
    """Event captured by hook system."""

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    event_type: str  # PreToolUse, PostToolUse, Notification, etc.
    timestamp: datetime = Field(default_factory=datetime.now)
    data: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_encoders={UUID: str, datetime: lambda v: v.isoformat()}
    )
