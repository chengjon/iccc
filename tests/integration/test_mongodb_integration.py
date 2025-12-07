"""Integration tests for MongoDB with real database."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from iccc.config import load_config
from iccc.models.entities import (
    Agent,
    AgentStatus,
    ModelTier,
    Project,
    ProjectStatus,
    Task,
    TaskStatus,
    TaskType,
)


@pytest.fixture
async def mongo_client():
    """Create MongoDB client."""
    config = load_config()
    client = AsyncIOMotorClient(
        config.mongodb.uri,
        serverSelectionTimeoutMS=config.mongodb.timeout_ms,
    )
    yield client
    client.close()


@pytest.fixture
async def db(mongo_client):
    """Get database."""
    config = load_config()
    return mongo_client[config.mongodb.database]


@pytest.fixture
async def clean_db(db):
    """Clean database before and after each test."""
    # Clean before test
    await db.projects.delete_many({})
    await db.agents.delete_many({})
    await db.tasks.delete_many({})
    await db.sessions.delete_many({})
    await db.events.delete_many({})

    yield db

    # Clean after test
    await db.projects.delete_many({})
    await db.agents.delete_many({})
    await db.tasks.delete_many({})
    await db.sessions.delete_many({})
    await db.events.delete_many({})


@pytest.mark.asyncio
@pytest.mark.integration
class TestMongoDBConnection:
    """Test MongoDB connection and basic operations."""

    async def test_connection(self, mongo_client):
        """Test MongoDB connection."""
        # Ping server
        result = await mongo_client.admin.command("ping")
        assert result["ok"] == 1.0

    async def test_database_exists(self, db):
        """Test that database exists."""
        collections = await db.list_collection_names()
        assert len(collections) > 0
        assert "projects" in collections
        assert "agents" in collections
        assert "tasks" in collections

    async def test_indexes_exist(self, db):
        """Test that indexes are created."""
        # Projects indexes
        project_indexes = await db.projects.index_information()
        assert "name_1" in project_indexes
        assert "status_1" in project_indexes

        # Agents indexes
        agent_indexes = await db.agents.index_information()
        assert "type_1" in agent_indexes
        assert "status_1" in agent_indexes

        # Tasks indexes
        task_indexes = await db.tasks.index_information()
        assert "project_id_1" in task_indexes
        assert "status_1" in task_indexes


@pytest.mark.asyncio
@pytest.mark.integration
class TestProjectCRUD:
    """Test Project CRUD operations."""

    async def test_create_project(self, clean_db):
        """Test creating a project."""
        project_id = uuid4()
        project_data = {
            "id": str(project_id),
            "name": "Test Project",
            "directory": "/test/dir",
            "status": ProjectStatus.ACTIVE.value,
            "created_at": datetime.now(timezone.utc),
            "metadata": {"description": "A test project"},
        }

        result = await clean_db.projects.insert_one(project_data)
        assert result.inserted_id is not None

        # Verify insertion
        project = await clean_db.projects.find_one({"id": str(project_id)})
        assert project is not None
        assert project["name"] == "Test Project"
        assert project["status"] == ProjectStatus.ACTIVE.value

    async def test_read_project(self, clean_db):
        """Test reading a project."""
        project_id = uuid4()
        project_data = {
            "id": str(project_id),
            "name": "Read Test",
            "directory": "/test",
            "status": ProjectStatus.ACTIVE.value,
            "created_at": datetime.now(timezone.utc),
        }

        await clean_db.projects.insert_one(project_data)

        # Read project
        project = await clean_db.projects.find_one({"id": str(project_id)})
        assert project["name"] == "Read Test"

    async def test_update_project(self, clean_db):
        """Test updating a project."""
        project_id = uuid4()
        project_data = {
            "id": str(project_id),
            "name": "Update Test",
            "directory": "/test",
            "status": ProjectStatus.ACTIVE.value,
            "created_at": datetime.now(timezone.utc),
        }

        await clean_db.projects.insert_one(project_data)

        # Update project
        result = await clean_db.projects.update_one(
            {"id": str(project_id)}, {"$set": {"status": ProjectStatus.ARCHIVED.value}}
        )

        assert result.modified_count == 1

        # Verify update
        project = await clean_db.projects.find_one({"id": str(project_id)})
        assert project["status"] == ProjectStatus.ARCHIVED.value

    async def test_delete_project(self, clean_db):
        """Test deleting a project."""
        project_id = uuid4()
        project_data = {
            "id": str(project_id),
            "name": "Delete Test",
            "directory": "/test",
            "status": ProjectStatus.ACTIVE.value,
            "created_at": datetime.now(timezone.utc),
        }

        await clean_db.projects.insert_one(project_data)

        # Delete project
        result = await clean_db.projects.delete_one({"id": str(project_id)})
        assert result.deleted_count == 1

        # Verify deletion
        project = await clean_db.projects.find_one({"id": str(project_id)})
        assert project is None

    async def test_unique_project_name(self, clean_db):
        """Test that project names are unique."""
        project1_id = uuid4()
        project2_id = uuid4()

        project1 = {
            "id": str(project1_id),
            "name": "Unique Name",
            "directory": "/test1",
            "status": ProjectStatus.ACTIVE.value,
            "created_at": datetime.now(timezone.utc),
        }

        project2 = {
            "id": str(project2_id),
            "name": "Unique Name",  # Same name
            "directory": "/test2",
            "status": ProjectStatus.ACTIVE.value,
            "created_at": datetime.now(timezone.utc),
        }

        await clean_db.projects.insert_one(project1)

        # Try to insert duplicate name
        with pytest.raises(Exception):  # Should raise duplicate key error
            await clean_db.projects.insert_one(project2)


@pytest.mark.asyncio
@pytest.mark.integration
class TestAgentCRUD:
    """Test Agent CRUD operations."""

    async def test_create_agent(self, clean_db):
        """Test creating an agent."""
        agent_id = "agent-001"
        agent_data = {
            "id": agent_id,
            "type": "code-reviewer",
            "specialization": "Python code review",
            "model": ModelTier.SONNET.value,
            "status": AgentStatus.IDLE.value,
            "created_at": datetime.now(timezone.utc),
        }

        result = await clean_db.agents.insert_one(agent_data)
        assert result.inserted_id is not None

        # Verify insertion
        agent = await clean_db.agents.find_one({"id": agent_id})
        assert agent is not None
        assert agent["type"] == "code-reviewer"
        assert agent["model"] == ModelTier.SONNET.value

    async def test_query_agents_by_status(self, clean_db):
        """Test querying agents by status."""
        # Create multiple agents
        agents_data = [
            {
                "id": f"agent-{i}",
                "type": "worker",
                "specialization": f"Task {i}",
                "model": ModelTier.HAIKU.value,
                "status": AgentStatus.IDLE.value if i % 2 == 0 else AgentStatus.BUSY.value,
                "created_at": datetime.now(timezone.utc),
            }
            for i in range(5)
        ]

        await clean_db.agents.insert_many(agents_data)

        # Query idle agents
        idle_agents = await clean_db.agents.find({"status": AgentStatus.IDLE.value}).to_list(
            length=100
        )

        assert len(idle_agents) == 3  # agents 0, 2, 4

    async def test_query_agents_by_model(self, clean_db):
        """Test querying agents by model tier."""
        agents_data = [
            {
                "id": "agent-haiku",
                "type": "worker",
                "specialization": "Simple tasks",
                "model": ModelTier.HAIKU.value,
                "status": AgentStatus.IDLE.value,
                "created_at": datetime.now(timezone.utc),
            },
            {
                "id": "agent-sonnet",
                "type": "worker",
                "specialization": "Complex tasks",
                "model": ModelTier.SONNET.value,
                "status": AgentStatus.IDLE.value,
                "created_at": datetime.now(timezone.utc),
            },
        ]

        await clean_db.agents.insert_many(agents_data)

        # Query Sonnet agents
        sonnet_agents = await clean_db.agents.find(
            {"model": ModelTier.SONNET.value}
        ).to_list(length=100)

        assert len(sonnet_agents) == 1
        assert sonnet_agents[0]["id"] == "agent-sonnet"


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskCRUD:
    """Test Task CRUD operations."""

    async def test_create_task(self, clean_db):
        """Test creating a task."""
        project_id = uuid4()
        task_id = uuid4()

        task_data = {
            "id": str(task_id),
            "project_id": str(project_id),
            "description": "Implement feature X",
            "task_type": TaskType.FEATURE_IMPLEMENTATION.value,
            "status": TaskStatus.PENDING.value,
            "created_at": datetime.now(timezone.utc),
        }

        result = await clean_db.tasks.insert_one(task_data)
        assert result.inserted_id is not None

        # Verify insertion
        task = await clean_db.tasks.find_one({"id": str(task_id)})
        assert task is not None
        assert task["description"] == "Implement feature X"

    async def test_query_tasks_by_project(self, clean_db):
        """Test querying tasks by project."""
        project1_id = uuid4()
        project2_id = uuid4()

        # Create tasks for project 1
        tasks_p1 = [
            {
                "id": str(uuid4()),
                "project_id": str(project1_id),
                "description": f"Task {i}",
                "task_type": TaskType.GENERAL_CODING.value,
                "status": TaskStatus.PENDING.value,
                "created_at": datetime.now(timezone.utc),
            }
            for i in range(3)
        ]

        # Create tasks for project 2
        tasks_p2 = [
            {
                "id": str(uuid4()),
                "project_id": str(project2_id),
                "description": f"Task {i}",
                "task_type": TaskType.GENERAL_CODING.value,
                "status": TaskStatus.PENDING.value,
                "created_at": datetime.now(timezone.utc),
            }
            for i in range(2)
        ]

        await clean_db.tasks.insert_many(tasks_p1 + tasks_p2)

        # Query project 1 tasks
        p1_tasks = await clean_db.tasks.find({"project_id": str(project1_id)}).to_list(
            length=100
        )

        assert len(p1_tasks) == 3

    async def test_query_tasks_by_status(self, clean_db):
        """Test querying tasks by status."""
        project_id = uuid4()

        tasks_data = [
            {
                "id": str(uuid4()),
                "project_id": str(project_id),
                "description": f"Task {i}",
                "task_type": TaskType.GENERAL_CODING.value,
                "status": (
                    TaskStatus.PENDING.value
                    if i < 2
                    else TaskStatus.IN_PROGRESS.value
                ),
                "created_at": datetime.now(timezone.utc),
            }
            for i in range(4)
        ]

        await clean_db.tasks.insert_many(tasks_data)

        # Query pending tasks
        pending_tasks = await clean_db.tasks.find(
            {"status": TaskStatus.PENDING.value}
        ).to_list(length=100)

        assert len(pending_tasks) == 2

    async def test_query_tasks_by_project_and_status(self, clean_db):
        """Test compound index query."""
        project_id = uuid4()

        tasks_data = [
            {
                "id": str(uuid4()),
                "project_id": str(project_id),
                "description": f"Task {i}",
                "task_type": TaskType.GENERAL_CODING.value,
                "status": TaskStatus.PENDING.value if i % 2 == 0 else TaskStatus.COMPLETED.value,
                "created_at": datetime.now(timezone.utc),
            }
            for i in range(6)
        ]

        await clean_db.tasks.insert_many(tasks_data)

        # Query using compound index
        pending_tasks = await clean_db.tasks.find(
            {"project_id": str(project_id), "status": TaskStatus.PENDING.value}
        ).to_list(length=100)

        assert len(pending_tasks) == 3


@pytest.mark.asyncio
@pytest.mark.integration
class TestRelationships:
    """Test relationships between collections."""

    async def test_project_tasks_relationship(self, clean_db):
        """Test querying tasks for a project."""
        # Create project
        project_id = uuid4()
        project_data = {
            "id": str(project_id),
            "name": "Test Project",
            "directory": "/test",
            "status": ProjectStatus.ACTIVE.value,
            "created_at": datetime.now(timezone.utc),
        }
        await clean_db.projects.insert_one(project_data)

        # Create tasks
        tasks_data = [
            {
                "id": str(uuid4()),
                "project_id": str(project_id),
                "description": f"Task {i}",
                "task_type": TaskType.GENERAL_CODING.value,
                "status": TaskStatus.PENDING.value,
                "created_at": datetime.now(timezone.utc),
            }
            for i in range(3)
        ]
        await clean_db.tasks.insert_many(tasks_data)

        # Query tasks for project
        tasks = await clean_db.tasks.find({"project_id": str(project_id)}).to_list(
            length=100
        )

        assert len(tasks) == 3

    async def test_agent_tasks_relationship(self, clean_db):
        """Test querying tasks assigned to an agent."""
        # Create agent
        agent_id = "agent-001"
        agent_data = {
            "id": agent_id,
            "type": "worker",
            "specialization": "Coding",
            "model": ModelTier.SONNET.value,
            "status": AgentStatus.BUSY.value,
            "created_at": datetime.now(timezone.utc),
        }
        await clean_db.agents.insert_one(agent_data)

        # Create tasks
        tasks_data = [
            {
                "id": str(uuid4()),
                "project_id": str(uuid4()),
                "description": f"Task {i}",
                "task_type": TaskType.GENERAL_CODING.value,
                "status": TaskStatus.IN_PROGRESS.value,
                "assigned_agent_id": agent_id if i < 2 else None,
                "created_at": datetime.now(timezone.utc),
            }
            for i in range(4)
        ]
        await clean_db.tasks.insert_many(tasks_data)

        # Query tasks for agent
        agent_tasks = await clean_db.tasks.find({"assigned_agent_id": agent_id}).to_list(
            length=100
        )

        assert len(agent_tasks) == 2
