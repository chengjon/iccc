"""Core data models for iCCC system."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_serializer


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
    description: str | None = None
    git_repo: str | None = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict()

    @field_serializer("id")
    def serialize_uuid(self, v: UUID) -> str:
        """Serialize UUID to string."""
        return str(v)

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, v: datetime) -> str:
        """Serialize datetime to ISO format."""
        return v.isoformat()


class Agent(BaseModel):
    """Agent entity representing a Claude instance."""

    id: str  # e.g., "agent-001"
    project_id: UUID
    name: str
    agent_type: str  # e.g., "frontend-developer", "backend-developer"
    model: ModelTier
    specialization: str | None = None  # e.g., "frontend", "backend", "testing"
    status: AgentStatus = AgentStatus.IDLE
    worktree_path: str | None = None
    tools: list[str] = Field(default_factory=list)  # Available tools
    created_at: datetime = Field(default_factory=datetime.now)
    last_active: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict()

    @field_serializer("project_id")
    def serialize_uuid(self, v: UUID) -> str:
        """Serialize UUID to string."""
        return str(v)

    @field_serializer("created_at", "last_active")
    def serialize_datetime(self, v: datetime) -> str:
        """Serialize datetime to ISO format."""
        return v.isoformat()


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
    complexity: TaskComplexity | None = None
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent_id: str | None = None
    dependencies: list[UUID] = Field(default_factory=list)  # Task IDs that must complete first
    result: str | None = None
    error: str | None = None
    files_modified: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict()

    @field_serializer("id", "project_id")
    def serialize_uuid(self, v: UUID) -> str:
        """Serialize UUID to string."""
        return str(v)

    @field_serializer("dependencies")
    def serialize_dependencies(self, v: list[UUID]) -> list[str]:
        """Serialize dependency UUIDs to strings."""
        return [str(dep) for dep in v]

    @field_serializer("created_at", "started_at", "completed_at")
    def serialize_datetime(self, v: datetime | None) -> str | None:
        """Serialize datetime to ISO format."""
        return v.isoformat() if v else None


class Message(BaseModel):
    """Single message in a conversation."""

    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict()

    @field_serializer("timestamp")
    def serialize_datetime(self, v: datetime) -> str:
        """Serialize datetime to ISO format."""
        return v.isoformat()


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
    ended_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict()

    @field_serializer("id", "task_id")
    def serialize_uuid(self, v: UUID) -> str:
        """Serialize UUID to string."""
        return str(v)

    @field_serializer("started_at", "ended_at")
    def serialize_datetime(self, v: datetime | None) -> str | None:
        """Serialize datetime to ISO format."""
        return v.isoformat() if v else None


class HookEvent(BaseModel):
    """Event captured by hook system."""

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    event_type: str  # PreToolUse, PostToolUse, Notification, etc.
    timestamp: datetime = Field(default_factory=datetime.now)
    data: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict()

    @field_serializer("id", "session_id")
    def serialize_uuid(self, v: UUID) -> str:
        """Serialize UUID to string."""
        return str(v)

    @field_serializer("timestamp")
    def serialize_datetime(self, v: datetime) -> str:
        """Serialize datetime to ISO format."""
        return v.isoformat()


class PromptTemplate(BaseModel):
    """Reusable prompt template for agent instructions."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    category: str  # e.g., "coding", "review", "testing", "documentation"
    template: str  # Template with placeholders like {task_description}
    variables: list[str] = Field(default_factory=list)  # Required variables
    model_tier: ModelTier | None = None  # Recommended model tier
    description: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict()

    @field_serializer("id")
    def serialize_uuid(self, v: UUID) -> str:
        """Serialize UUID to string."""
        return str(v)

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, v: datetime) -> str:
        """Serialize datetime to ISO format."""
        return v.isoformat()


class GoalStatus(str, Enum):
    """Goal lifecycle status for planning system."""

    PENDING = "pending"
    ACTIVE = "active"
    ACHIEVED = "achieved"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Goal(BaseModel):
    """Goal entity for HTN planning system."""

    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    name: str
    description: str
    status: GoalStatus = GoalStatus.PENDING
    priority: int = Field(default=1, ge=1, le=5)  # 1=highest, 5=lowest
    preconditions: dict[str, Any] = Field(default_factory=dict)  # State requirements
    effects: dict[str, Any] = Field(default_factory=dict)  # State changes when achieved
    parent_goal_id: UUID | None = None  # For hierarchical goals
    sub_task_ids: list[UUID] = Field(default_factory=list)  # Related tasks
    created_at: datetime = Field(default_factory=datetime.now)
    achieved_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict()

    @field_serializer("id", "project_id")
    def serialize_uuid(self, v: UUID) -> str:
        """Serialize UUID to string."""
        return str(v)

    @field_serializer("parent_goal_id")
    def serialize_parent_goal_id(self, v: UUID | None) -> str | None:
        """Serialize parent goal UUID to string."""
        return str(v) if v else None

    @field_serializer("sub_task_ids")
    def serialize_sub_task_ids(self, v: list[UUID]) -> list[str]:
        """Serialize sub task UUIDs to strings."""
        return [str(task_id) for task_id in v]

    @field_serializer("created_at", "achieved_at")
    def serialize_datetime(self, v: datetime | None) -> str | None:
        """Serialize datetime to ISO format."""
        return v.isoformat() if v else None
