"""Integration tests for database repositories."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from iccc.config import load_config
from iccc.db.repositories import (
    AgentRepository,
    GoalRepository,
    HookEventRepository,
    MongoDBClient,
    ProjectRepository,
    PromptTemplateRepository,
    SessionRepository,
    TaskRepository,
)
from iccc.models.entities import (
    Agent,
    AgentStatus,
    Goal,
    GoalStatus,
    HookEvent,
    ModelTier,
    Project,
    ProjectStatus,
    PromptTemplate,
    Session,
    Task,
    TaskStatus,
    TaskType,
)


@pytest.fixture
async def db_client():
    """Create and connect MongoDB client."""
    config = load_config()
    client = MongoDBClient(config.mongodb.uri)
    await client.connect()
    yield client
    await client.disconnect()


@pytest.fixture
async def clean_collections(db_client):
    """Clean all collections before and after each test."""
    if db_client.db is None:
        raise RuntimeError("Database not connected")

    # Clean before test
    await db_client.db.projects.delete_many({})
    await db_client.db.agents.delete_many({})
    await db_client.db.tasks.delete_many({})
    await db_client.db.sessions.delete_many({})
    await db_client.db.hook_events.delete_many({})
    await db_client.db.prompt_templates.delete_many({})
    await db_client.db.goals.delete_many({})

    yield

    # Clean after test
    await db_client.db.projects.delete_many({})
    await db_client.db.agents.delete_many({})
    await db_client.db.tasks.delete_many({})
    await db_client.db.sessions.delete_many({})
    await db_client.db.hook_events.delete_many({})
    await db_client.db.prompt_templates.delete_many({})
    await db_client.db.goals.delete_many({})


@pytest.mark.asyncio
@pytest.mark.integration
class TestProjectRepository:
    """Test ProjectRepository operations."""

    async def test_create_project(self, db_client, clean_collections):
        """Test creating a project."""
        repo = ProjectRepository(db_client)
        project = Project(
            id=uuid4(),
            name="Test Project",
            directory="/test/dir",
            status=ProjectStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
            metadata={"description": "A test project"},
        )

        created = await repo.create(project)
        assert created.id == project.id
        assert created.name == project.name

    async def test_get_project(self, db_client, clean_collections):
        """Test getting a project by ID."""
        repo = ProjectRepository(db_client)
        project = Project(
            id=uuid4(),
            name="Get Test",
            directory="/test",
            status=ProjectStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )

        await repo.create(project)
        retrieved = await repo.get(project.id)

        assert retrieved is not None
        assert retrieved.id == project.id
        assert retrieved.name == project.name

    async def test_get_project_by_name(self, db_client, clean_collections):
        """Test getting a project by name."""
        repo = ProjectRepository(db_client)
        project = Project(
            id=uuid4(),
            name="Unique Name",
            directory="/test",
            status=ProjectStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )

        await repo.create(project)
        retrieved = await repo.get_by_name("Unique Name")

        assert retrieved is not None
        assert retrieved.name == "Unique Name"

    async def test_update_project(self, db_client, clean_collections):
        """Test updating a project."""
        repo = ProjectRepository(db_client)
        project = Project(
            id=uuid4(),
            name="Update Test",
            directory="/test",
            status=ProjectStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )

        await repo.create(project)
        project.status = ProjectStatus.ARCHIVED
        updated = await repo.update(project)

        assert updated.status == ProjectStatus.ARCHIVED

    async def test_delete_project(self, db_client, clean_collections):
        """Test deleting a project."""
        repo = ProjectRepository(db_client)
        project = Project(
            id=uuid4(),
            name="Delete Test",
            directory="/test",
            status=ProjectStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )

        await repo.create(project)
        deleted = await repo.delete(project.id)

        assert deleted is True

        retrieved = await repo.get(project.id)
        assert retrieved is None

    async def test_list_all_projects(self, db_client, clean_collections):
        """Test listing all projects."""
        repo = ProjectRepository(db_client)

        # Create multiple projects
        for i in range(3):
            project = Project(
                id=uuid4(),
                name=f"Project {i}",
                directory=f"/test/{i}",
                status=ProjectStatus.ACTIVE,
                created_at=datetime.now(timezone.utc),
            )
            await repo.create(project)

        projects = await repo.list_all()
        assert len(projects) == 3


@pytest.mark.asyncio
@pytest.mark.integration
class TestAgentRepository:
    """Test AgentRepository operations."""

    async def test_create_agent(self, db_client, clean_collections):
        """Test creating an agent."""
        repo = AgentRepository(db_client)
        project_id = uuid4()

        agent = Agent(
            id="agent-001",
            project_id=project_id,
            name="Code Reviewer Agent",
            agent_type="code-reviewer",
            specialization="Python code review",
            model=ModelTier.SONNET,
            status=AgentStatus.IDLE,
            created_at=datetime.now(timezone.utc),
        )

        created = await repo.create(agent)
        assert created.id == agent.id
        assert created.agent_type == "code-reviewer"

    async def test_get_agent(self, db_client, clean_collections):
        """Test getting an agent by ID."""
        repo = AgentRepository(db_client)
        project_id = uuid4()

        agent = Agent(
            id="agent-002",
            project_id=project_id,
            name="Worker Agent",
            agent_type="worker",
            specialization="General coding",
            model=ModelTier.HAIKU,
            status=AgentStatus.IDLE,
            created_at=datetime.now(timezone.utc),
        )

        await repo.create(agent)
        retrieved = await repo.get("agent-002")

        assert retrieved is not None
        assert retrieved.id == "agent-002"

    async def test_list_by_status(self, db_client, clean_collections):
        """Test listing agents by status."""
        repo = AgentRepository(db_client)
        project_id = uuid4()

        # Create idle and busy agents
        for i in range(5):
            status = AgentStatus.IDLE if i % 2 == 0 else AgentStatus.BUSY
            agent = Agent(
                id=f"agent-{i}",
                project_id=project_id,
                name=f"Worker Agent {i}",
                agent_type="worker",
                specialization=f"Task {i}",
                model=ModelTier.HAIKU,
                status=status,
                created_at=datetime.now(timezone.utc),
            )
            await repo.create(agent)

        idle_agents = await repo.list_by_status(AgentStatus.IDLE.value)
        assert len(idle_agents) == 3  # agents 0, 2, 4

    async def test_list_by_project(self, db_client, clean_collections):
        """Test listing agents by project."""
        repo = AgentRepository(db_client)
        project1_id = uuid4()
        project2_id = uuid4()

        # Create agents for project 1
        for i in range(2):
            agent = Agent(
                id=f"p1-agent-{i}",
                project_id=project1_id,
                name=f"P1 Worker Agent {i}",
                agent_type="worker",
                specialization=f"Task {i}",
                model=ModelTier.HAIKU,
                status=AgentStatus.IDLE,
                created_at=datetime.now(timezone.utc),
            )
            await repo.create(agent)

        # Create agents for project 2
        for i in range(3):
            agent = Agent(
                id=f"p2-agent-{i}",
                project_id=project2_id,
                name=f"P2 Worker Agent {i}",
                agent_type="worker",
                specialization=f"Task {i}",
                model=ModelTier.HAIKU,
                status=AgentStatus.IDLE,
                created_at=datetime.now(timezone.utc),
            )
            await repo.create(agent)

        p1_agents = await repo.list_by_project(project1_id)
        assert len(p1_agents) == 2

        p2_agents = await repo.list_by_project(project2_id)
        assert len(p2_agents) == 3


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskRepository:
    """Test TaskRepository operations."""

    async def test_create_task(self, db_client, clean_collections):
        """Test creating a task."""
        repo = TaskRepository(db_client)
        project_id = uuid4()

        task = Task(
            id=uuid4(),
            project_id=project_id,
            description="Implement feature X",
            task_type=TaskType.FEATURE_IMPLEMENTATION,
            status=TaskStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        created = await repo.create(task)
        assert created.id == task.id
        assert created.description == task.description

    async def test_get_task(self, db_client, clean_collections):
        """Test getting a task by ID."""
        repo = TaskRepository(db_client)
        project_id = uuid4()

        task = Task(
            id=uuid4(),
            project_id=project_id,
            description="Test task",
            task_type=TaskType.GENERAL_CODING,
            status=TaskStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        await repo.create(task)
        retrieved = await repo.get(task.id)

        assert retrieved is not None
        assert retrieved.id == task.id

    async def test_list_by_project(self, db_client, clean_collections):
        """Test listing tasks by project."""
        repo = TaskRepository(db_client)
        project1_id = uuid4()
        project2_id = uuid4()

        # Create tasks for project 1
        for i in range(3):
            task = Task(
                id=uuid4(),
                project_id=project1_id,
                description=f"Task {i}",
                task_type=TaskType.GENERAL_CODING,
                status=TaskStatus.PENDING,
                created_at=datetime.now(timezone.utc),
            )
            await repo.create(task)

        # Create tasks for project 2
        for i in range(2):
            task = Task(
                id=uuid4(),
                project_id=project2_id,
                description=f"Task {i}",
                task_type=TaskType.GENERAL_CODING,
                status=TaskStatus.PENDING,
                created_at=datetime.now(timezone.utc),
            )
            await repo.create(task)

        p1_tasks = await repo.list_by_project(project1_id)
        assert len(p1_tasks) == 3

    async def test_list_by_status(self, db_client, clean_collections):
        """Test listing tasks by status."""
        repo = TaskRepository(db_client)
        project_id = uuid4()

        # Create tasks with different statuses
        for i in range(4):
            status = TaskStatus.PENDING if i < 2 else TaskStatus.IN_PROGRESS
            task = Task(
                id=uuid4(),
                project_id=project_id,
                description=f"Task {i}",
                task_type=TaskType.GENERAL_CODING,
                status=status,
                created_at=datetime.now(timezone.utc),
            )
            await repo.create(task)

        pending_tasks = await repo.list_by_status(TaskStatus.PENDING.value)
        assert len(pending_tasks) == 2

    async def test_list_by_agent(self, db_client, clean_collections):
        """Test listing tasks assigned to an agent."""
        repo = TaskRepository(db_client)
        project_id = uuid4()
        agent_id = "agent-001"

        # Create tasks assigned to agent
        for i in range(2):
            task = Task(
                id=uuid4(),
                project_id=project_id,
                description=f"Task {i}",
                task_type=TaskType.GENERAL_CODING,
                status=TaskStatus.IN_PROGRESS,
                assigned_agent_id=agent_id,
                created_at=datetime.now(timezone.utc),
            )
            await repo.create(task)

        # Create unassigned tasks
        for i in range(3):
            task = Task(
                id=uuid4(),
                project_id=project_id,
                description=f"Unassigned {i}",
                task_type=TaskType.GENERAL_CODING,
                status=TaskStatus.PENDING,
                created_at=datetime.now(timezone.utc),
            )
            await repo.create(task)

        agent_tasks = await repo.list_by_agent(agent_id)
        assert len(agent_tasks) == 2

    async def test_list_pending_tasks_with_dependencies(
        self, db_client, clean_collections
    ):
        """Test listing pending tasks respecting dependencies."""
        repo = TaskRepository(db_client)
        project_id = uuid4()

        # Create completed task
        task1 = Task(
            id=uuid4(),
            project_id=project_id,
            description="Completed task",
            task_type=TaskType.GENERAL_CODING,
            status=TaskStatus.COMPLETED,
            created_at=datetime.now(timezone.utc),
        )
        await repo.create(task1)

        # Create pending task with no dependencies
        task2 = Task(
            id=uuid4(),
            project_id=project_id,
            description="Ready task",
            task_type=TaskType.GENERAL_CODING,
            status=TaskStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        await repo.create(task2)

        # Create pending task with met dependencies
        task3 = Task(
            id=uuid4(),
            project_id=project_id,
            description="Dependent task (ready)",
            task_type=TaskType.GENERAL_CODING,
            status=TaskStatus.PENDING,
            dependencies=[task1.id],
            created_at=datetime.now(timezone.utc),
        )
        await repo.create(task3)

        # Create pending task with unmet dependencies
        task4 = Task(
            id=uuid4(),
            project_id=project_id,
            description="Dependent task (blocked)",
            task_type=TaskType.GENERAL_CODING,
            status=TaskStatus.PENDING,
            dependencies=[task2.id],  # task2 is still pending
            created_at=datetime.now(timezone.utc),
        )
        await repo.create(task4)

        ready_tasks = await repo.list_pending_tasks(project_id)
        ready_task_ids = {t.id for t in ready_tasks}

        # task2 and task3 should be ready
        assert task2.id in ready_task_ids
        assert task3.id in ready_task_ids
        # task4 should not be ready (dependency not met)
        assert task4.id not in ready_task_ids


@pytest.mark.asyncio
@pytest.mark.integration
class TestSessionRepository:
    """Test SessionRepository operations."""

    async def test_create_session(self, db_client, clean_collections):
        """Test creating a session."""
        repo = SessionRepository(db_client)

        session = Session(
            id=uuid4(),
            agent_id="agent-001",
            task_id=uuid4(),
            started_at=datetime.now(timezone.utc),
        )

        created = await repo.create(session)
        assert created.id == session.id

    async def test_get_session(self, db_client, clean_collections):
        """Test getting a session by ID."""
        repo = SessionRepository(db_client)

        session = Session(
            id=uuid4(),
            agent_id="agent-002",
            task_id=uuid4(),
            started_at=datetime.now(timezone.utc),
        )

        await repo.create(session)
        retrieved = await repo.get(session.id)

        assert retrieved is not None
        assert retrieved.id == session.id

    async def test_list_by_agent(self, db_client, clean_collections):
        """Test listing sessions by agent."""
        repo = SessionRepository(db_client)
        agent_id = "agent-003"

        # Create sessions for this agent
        for i in range(3):
            session = Session(
                id=uuid4(),
                agent_id=agent_id,
                task_id=uuid4(),
                started_at=datetime.now(timezone.utc),
            )
            await repo.create(session)

        # Create sessions for another agent
        for i in range(2):
            session = Session(
                id=uuid4(),
                agent_id="other-agent",
                task_id=uuid4(),
                started_at=datetime.now(timezone.utc),
            )
            await repo.create(session)

        agent_sessions = await repo.list_by_agent(agent_id)
        assert len(agent_sessions) == 3

    async def test_update_session(self, db_client, clean_collections):
        """Test updating a session."""
        repo = SessionRepository(db_client)

        session = Session(
            id=uuid4(),
            agent_id="agent-004",
            task_id=uuid4(),
            started_at=datetime.now(timezone.utc),
        )

        await repo.create(session)

        # End the session
        session.ended_at = datetime.now(timezone.utc)
        session.token_usage = {"input": 500, "output": 500, "total": 1000}
        updated = await repo.update(session)

        assert updated.ended_at is not None
        assert updated.token_usage["total"] == 1000


@pytest.mark.asyncio
@pytest.mark.integration
class TestHookEventRepository:
    """Test HookEventRepository operations."""

    async def test_create_hook_event(self, db_client, clean_collections):
        """Test creating a hook event."""
        repo = HookEventRepository(db_client)

        event = HookEvent(
            id=uuid4(),
            session_id=uuid4(),
            event_type="pre_tool_use",
            timestamp=datetime.now(timezone.utc),
            data={"tool": "Read", "args": {"file_path": "/test.py"}},
        )

        created = await repo.create(event)
        assert created.id == event.id

    async def test_list_by_session(self, db_client, clean_collections):
        """Test listing hook events by session."""
        repo = HookEventRepository(db_client)
        session_id = uuid4()

        # Create events for this session
        for i in range(3):
            event = HookEvent(
                id=uuid4(),
                session_id=session_id,
                event_type="pre_tool_use",
                timestamp=datetime.now(timezone.utc),
                data={"tool": "Read"},
            )
            await repo.create(event)

        session_events = await repo.list_by_session(session_id)
        assert len(session_events) == 3

    async def test_list_by_type(self, db_client, clean_collections):
        """Test listing hook events by type."""
        repo = HookEventRepository(db_client)

        # Create different types of events
        for i in range(2):
            event = HookEvent(
                id=uuid4(),
                session_id=uuid4(),
                event_type="pre_tool_use",
                timestamp=datetime.now(timezone.utc),
                data={},
            )
            await repo.create(event)

        for i in range(3):
            event = HookEvent(
                id=uuid4(),
                session_id=uuid4(),
                event_type="post_tool_use",
                timestamp=datetime.now(timezone.utc),
                data={},
            )
            await repo.create(event)

        pre_events = await repo.list_by_type("pre_tool_use")
        assert len(pre_events) == 2

        post_events = await repo.list_by_type("post_tool_use")
        assert len(post_events) == 3


@pytest.mark.asyncio
@pytest.mark.integration
class TestPromptTemplateRepository:
    """Test PromptTemplateRepository operations."""

    async def test_create_template(self, db_client, clean_collections):
        """Test creating a prompt template."""
        repo = PromptTemplateRepository(db_client)

        template = PromptTemplate(
            id=uuid4(),
            name="code_review_template",
            category="code_review",
            template="Review the following code:\n{code}",
            variables=["code"],
            created_at=datetime.now(timezone.utc),
        )

        created = await repo.create(template)
        assert created.id == template.id

    async def test_get_by_name(self, db_client, clean_collections):
        """Test getting a template by name."""
        repo = PromptTemplateRepository(db_client)

        template = PromptTemplate(
            id=uuid4(),
            name="test_template",
            category="testing",
            template="Test prompt",
            variables=[],
            created_at=datetime.now(timezone.utc),
        )

        await repo.create(template)
        retrieved = await repo.get_by_name("test_template")

        assert retrieved is not None
        assert retrieved.name == "test_template"

    async def test_list_by_category(self, db_client, clean_collections):
        """Test listing templates by category."""
        repo = PromptTemplateRepository(db_client)

        # Create templates in different categories
        for i in range(2):
            template = PromptTemplate(
                id=uuid4(),
                name=f"review_{i}",
                category="code_review",
                template=f"Review template {i}",
                variables=[],
                created_at=datetime.now(timezone.utc),
            )
            await repo.create(template)

        for i in range(3):
            template = PromptTemplate(
                id=uuid4(),
                name=f"refactor_{i}",
                category="refactoring",
                template=f"Refactor template {i}",
                variables=[],
                created_at=datetime.now(timezone.utc),
            )
            await repo.create(template)

        review_templates = await repo.list_by_category("code_review")
        assert len(review_templates) == 2

        refactor_templates = await repo.list_by_category("refactoring")
        assert len(refactor_templates) == 3


@pytest.mark.asyncio
@pytest.mark.integration
class TestGoalRepository:
    """Test GoalRepository operations."""

    async def test_create_goal(self, db_client, clean_collections):
        """Test creating a goal."""
        repo = GoalRepository(db_client)
        project_id = uuid4()

        goal = Goal(
            id=uuid4(),
            project_id=project_id,
            name="Authentication System",
            description="Implement authentication system",
            priority=1,
            status=GoalStatus.ACTIVE,
        )

        created = await repo.create(goal)
        assert created.id == goal.id

    async def test_list_by_project(self, db_client, clean_collections):
        """Test listing goals by project."""
        repo = GoalRepository(db_client)
        project_id = uuid4()

        # Create goals for project
        for i in range(3):
            goal = Goal(
                id=uuid4(),
                project_id=project_id,
                name=f"Goal {i}",
                description=f"Description for goal {i}",
                priority=i + 1,
                status=GoalStatus.ACTIVE,
            )
            await repo.create(goal)

        project_goals = await repo.list_by_project(project_id)
        assert len(project_goals) == 3

    async def test_list_by_priority(self, db_client, clean_collections):
        """Test listing goals by priority."""
        repo = GoalRepository(db_client)
        project_id = uuid4()

        # Create goals with different priorities
        # Note: priority should be 1-5, so we skip 8
        for priority in [1, 2, 3, 4, 5]:
            goal = Goal(
                id=uuid4(),
                project_id=project_id,
                name=f"Priority {priority} Goal",
                description=f"Goal with priority {priority}",
                priority=priority,
                status=GoalStatus.ACTIVE,
            )
            await repo.create(goal)

        # Get goals with priority <= 3
        high_priority_goals = await repo.list_by_priority(project_id, max_priority=3)
        assert len(high_priority_goals) == 3

    async def test_list_sub_goals(self, db_client, clean_collections):
        """Test listing sub-goals."""
        repo = GoalRepository(db_client)
        project_id = uuid4()

        # Create parent goal
        parent_goal = Goal(
            id=uuid4(),
            project_id=project_id,
            name="Parent Goal",
            description="Parent goal description",
            priority=1,
            status=GoalStatus.ACTIVE,
        )
        await repo.create(parent_goal)

        # Create sub-goals
        for i in range(2):
            sub_goal = Goal(
                id=uuid4(),
                project_id=project_id,
                name=f"Sub-goal {i}",
                description=f"Sub-goal {i} description",
                priority=2,
                status=GoalStatus.ACTIVE,
                parent_goal_id=parent_goal.id,
            )
            await repo.create(sub_goal)

        sub_goals = await repo.list_sub_goals(parent_goal.id)
        assert len(sub_goals) == 2
