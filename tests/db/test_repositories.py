"""Tests for MongoDB repositories."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from iccc.db.repositories import (
    AgentRepository,
    HookEventRepository,
    MongoDBClient,
    ProjectRepository,
    SessionRepository,
    TaskRepository,
)
from iccc.models.entities import (
    Agent,
    AgentStatus,
    HookEvent,
    Message,
    ModelTier,
    Project,
    ProjectStatus,
    Session,
    Task,
    TaskComplexity,
    TaskStatus,
    TaskType,
)


@pytest.fixture
def mock_db_client():
    """Create a mock MongoDB client."""
    client = MagicMock(spec=MongoDBClient)
    client.db = MagicMock()
    return client


@pytest.fixture
def sample_project():
    """Create a sample project."""
    return Project(
        id=uuid4(),
        name="Test Project",
        directory="/test/project",
        status=ProjectStatus.ACTIVE,
    )


@pytest.fixture
def sample_agent(sample_project):
    """Create a sample agent."""
    return Agent(
        id="agent-001",
        project_id=sample_project.id,
        name="Test Agent",
        agent_type="frontend-developer",
        model=ModelTier.SONNET,
        status=AgentStatus.IDLE,
    )


@pytest.fixture
def sample_task(sample_project):
    """Create a sample task with complexity."""
    return Task(
        id=uuid4(),
        project_id=sample_project.id,
        description="Test task",
        task_type=TaskType.GENERAL_CODING,
        complexity=TaskComplexity(
            reasoning_depth=3,
            code_scope=2,
            critical_importance=4,
            context_needed=3,
        ),
        status=TaskStatus.PENDING,
    )


@pytest.fixture
def sample_session(sample_agent, sample_task):
    """Create a sample session."""
    return Session(
        id=uuid4(),
        agent_id=sample_agent.id,
        task_id=sample_task.id,
        messages=[
            Message(role="user", content="Test message"),
        ],
    )


@pytest.fixture
def sample_hook_event(sample_session):
    """Create a sample hook event."""
    return HookEvent(
        id=uuid4(),
        session_id=sample_session.id,
        event_type="PreToolUse",
        timestamp=datetime.now(),
        data={"tool": "Write", "file": "test.py"},
    )


# ProjectRepository Tests


@pytest.mark.asyncio
async def test_project_create(mock_db_client, sample_project):
    """Test creating a project."""
    repo = ProjectRepository(mock_db_client)
    mock_db_client.db.projects.insert_one = AsyncMock()

    result = await repo.create(sample_project)

    assert result == sample_project
    mock_db_client.db.projects.insert_one.assert_called_once()


@pytest.mark.asyncio
async def test_project_get(mock_db_client, sample_project):
    """Test getting a project by ID."""
    repo = ProjectRepository(mock_db_client)

    # Mock MongoDB document with string UUID
    doc = sample_project.model_dump(mode="json")
    mock_db_client.db.projects.find_one = AsyncMock(return_value=doc)

    result = await repo.get(sample_project.id)

    assert result is not None
    assert result.id == sample_project.id
    assert result.name == sample_project.name


@pytest.mark.asyncio
async def test_project_get_not_found(mock_db_client):
    """Test getting a non-existent project."""
    repo = ProjectRepository(mock_db_client)
    mock_db_client.db.projects.find_one = AsyncMock(return_value=None)

    result = await repo.get(uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_project_list_all(mock_db_client, sample_project):
    """Test listing all projects."""
    repo = ProjectRepository(mock_db_client)

    # Mock cursor
    doc = sample_project.model_dump(mode="json")
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[doc, doc])
    mock_db_client.db.projects.find = MagicMock(return_value=mock_cursor)

    results = await repo.list_all()

    assert len(results) == 2
    assert all(isinstance(p, Project) for p in results)


# AgentRepository Tests


@pytest.mark.asyncio
async def test_agent_create(mock_db_client, sample_agent):
    """Test creating an agent."""
    repo = AgentRepository(mock_db_client)
    mock_db_client.db.agents.insert_one = AsyncMock()

    result = await repo.create(sample_agent)

    assert result == sample_agent
    mock_db_client.db.agents.insert_one.assert_called_once()


@pytest.mark.asyncio
async def test_agent_get(mock_db_client, sample_agent):
    """Test getting an agent by ID."""
    repo = AgentRepository(mock_db_client)

    doc = sample_agent.model_dump(mode="json")
    mock_db_client.db.agents.find_one = AsyncMock(return_value=doc)

    result = await repo.get(sample_agent.id)

    assert result is not None
    assert result.id == sample_agent.id
    assert result.project_id == sample_agent.project_id


@pytest.mark.asyncio
async def test_agent_list_by_project(mock_db_client, sample_agent):
    """Test listing agents by project."""
    repo = AgentRepository(mock_db_client)

    doc = sample_agent.model_dump(mode="json")
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[doc])
    mock_db_client.db.agents.find = MagicMock(return_value=mock_cursor)

    results = await repo.list_by_project(sample_agent.project_id)

    assert len(results) == 1
    assert results[0].id == sample_agent.id


# TaskRepository Tests


@pytest.mark.asyncio
async def test_task_create_with_complexity(mock_db_client, sample_task):
    """Test creating a task with complexity."""
    repo = TaskRepository(mock_db_client)
    mock_db_client.db.tasks.insert_one = AsyncMock()

    result = await repo.create(sample_task)

    assert result == sample_task
    assert result.complexity is not None
    assert result.complexity.reasoning_depth == 3


@pytest.mark.asyncio
async def test_task_get_with_complexity(mock_db_client, sample_task):
    """Test getting a task with complexity."""
    repo = TaskRepository(mock_db_client)

    doc = sample_task.model_dump(mode="json")
    mock_db_client.db.tasks.find_one = AsyncMock(return_value=doc)

    result = await repo.get(sample_task.id)

    assert result is not None
    assert result.id == sample_task.id
    assert result.complexity is not None
    assert isinstance(result.complexity, TaskComplexity)
    assert result.complexity.reasoning_depth == 3


@pytest.mark.asyncio
async def test_task_with_dependencies(mock_db_client, sample_project):
    """Test task with dependencies."""
    repo = TaskRepository(mock_db_client)

    # Create tasks with dependencies
    task1_id = uuid4()
    task2_id = uuid4()

    task = Task(
        id=uuid4(),
        project_id=sample_project.id,
        description="Task with deps",
        task_type=TaskType.GENERAL_CODING,
        status=TaskStatus.PENDING,
        dependencies=[task1_id, task2_id],
    )

    doc = task.model_dump(mode="json")
    mock_db_client.db.tasks.find_one = AsyncMock(return_value=doc)

    result = await repo.get(task.id)

    assert result is not None
    assert len(result.dependencies) == 2
    assert all(isinstance(dep, UUID) for dep in result.dependencies)
    assert task1_id in result.dependencies


@pytest.mark.asyncio
async def test_task_list_pending(mock_db_client, sample_project):
    """Test listing pending tasks."""
    repo = TaskRepository(mock_db_client)

    # Create two tasks, one with no deps, one with completed dep
    task1 = Task(
        id=uuid4(),
        project_id=sample_project.id,
        description="Task 1",
        task_type=TaskType.GENERAL_CODING,
        status=TaskStatus.PENDING,
    )

    task2 = Task(
        id=uuid4(),
        project_id=sample_project.id,
        description="Task 2",
        task_type=TaskType.GENERAL_CODING,
        status=TaskStatus.PENDING,
        dependencies=[task1.id],
    )

    # Mock the get method for dependency check
    async def mock_get(task_id):
        if task_id == task1.id:
            completed_task = task1.model_copy()
            completed_task.status = TaskStatus.COMPLETED
            return completed_task
        return None

    repo.get = AsyncMock(side_effect=mock_get)

    # Mock find to return both tasks
    docs = [task1.model_dump(mode="json"), task2.model_dump(mode="json")]

    async def async_generator():
        for doc in docs:
            yield doc

    mock_cursor = MagicMock()
    mock_cursor.__aiter__ = lambda self: async_generator()
    mock_db_client.db.tasks.find = MagicMock(return_value=mock_cursor)

    results = await repo.list_pending_tasks(sample_project.id)

    # Both tasks should be ready (task1 has no deps, task2's dep is completed)
    assert len(results) == 2


# SessionRepository Tests


@pytest.mark.asyncio
async def test_session_create(mock_db_client, sample_session):
    """Test creating a session."""
    repo = SessionRepository(mock_db_client)
    mock_db_client.db.sessions.insert_one = AsyncMock()

    result = await repo.create(sample_session)

    assert result == sample_session


@pytest.mark.asyncio
async def test_session_get(mock_db_client, sample_session):
    """Test getting a session."""
    repo = SessionRepository(mock_db_client)

    doc = sample_session.model_dump(mode="json")
    mock_db_client.db.sessions.find_one = AsyncMock(return_value=doc)

    result = await repo.get(sample_session.id)

    assert result is not None
    assert result.id == sample_session.id
    assert result.task_id == sample_session.task_id
    assert len(result.messages) == 1


# HookEventRepository Tests


@pytest.mark.asyncio
async def test_hook_event_create(mock_db_client, sample_hook_event):
    """Test creating a hook event."""
    repo = HookEventRepository(mock_db_client)
    mock_db_client.db.hook_events.insert_one = AsyncMock()

    result = await repo.create(sample_hook_event)

    assert result == sample_hook_event


@pytest.mark.asyncio
async def test_hook_event_get(mock_db_client, sample_hook_event):
    """Test getting a hook event."""
    repo = HookEventRepository(mock_db_client)

    doc = sample_hook_event.model_dump(mode="json")
    mock_db_client.db.hook_events.find_one = AsyncMock(return_value=doc)

    result = await repo.get(sample_hook_event.id)

    assert result is not None
    assert result.id == sample_hook_event.id
    assert result.session_id == sample_hook_event.session_id
    assert result.event_type == "PreToolUse"


@pytest.mark.asyncio
async def test_hook_event_list_by_session(mock_db_client, sample_hook_event):
    """Test listing hook events by session."""
    repo = HookEventRepository(mock_db_client)

    doc = sample_hook_event.model_dump(mode="json")
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[doc, doc])
    mock_db_client.db.hook_events.find = MagicMock(return_value=mock_cursor)

    results = await repo.list_by_session(sample_hook_event.session_id)

    assert len(results) == 2
    assert all(e.session_id == sample_hook_event.session_id for e in results)


@pytest.mark.asyncio
async def test_hook_event_delete_old(mock_db_client):
    """Test deleting old hook events."""
    repo = HookEventRepository(mock_db_client)

    mock_result = MagicMock()
    mock_result.deleted_count = 5
    mock_db_client.db.hook_events.delete_many = AsyncMock(return_value=mock_result)

    deleted_count = await repo.delete_old_events(datetime.now())

    assert deleted_count == 5
