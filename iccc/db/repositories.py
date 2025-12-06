"""MongoDB repositories for data access."""

import os
from typing import Any, Optional
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from iccc.models.entities import Agent, HookEvent, Project, Session, Task


class MongoDBClient:
    """MongoDB client wrapper."""

    def __init__(self, mongodb_url: Optional[str] = None) -> None:
        self.mongodb_url = mongodb_url or os.getenv(
            "MONGODB_URL", "mongodb://localhost:27017/iccc"
        )
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None

    async def connect(self) -> None:
        """Establish database connection."""
        self.client = AsyncIOMotorClient(self.mongodb_url)
        self.db = self.client.get_database()

        # Create indexes
        await self._create_indexes()

    async def disconnect(self) -> None:
        """Close database connection."""
        if self.client:
            self.client.close()

    async def _create_indexes(self) -> None:
        """Create database indexes for performance."""
        if not self.db:
            return

        # Projects indexes
        await self.db.projects.create_index([("name", ASCENDING)], unique=True)
        await self.db.projects.create_index([("status", ASCENDING)])

        # Agents indexes
        await self.db.agents.create_index([("project_id", ASCENDING)])
        await self.db.agents.create_index([("status", ASCENDING)])
        await self.db.agents.create_index([("id", ASCENDING)], unique=True)

        # Tasks indexes
        await self.db.tasks.create_index([("project_id", ASCENDING)])
        await self.db.tasks.create_index([("status", ASCENDING)])
        await self.db.tasks.create_index([("assigned_agent_id", ASCENDING)])
        await self.db.tasks.create_index([("created_at", DESCENDING)])

        # Sessions indexes
        await self.db.sessions.create_index([("agent_id", ASCENDING)])
        await self.db.sessions.create_index([("task_id", ASCENDING)])

        # HookEvents indexes
        await self.db.hook_events.create_index([("session_id", ASCENDING)])
        await self.db.hook_events.create_index([("event_type", ASCENDING)])
        await self.db.hook_events.create_index([("timestamp", DESCENDING)])


class ProjectRepository:
    """Repository for Project entities."""

    def __init__(self, db_client: MongoDBClient) -> None:
        self.db_client = db_client

    @property
    def collection(self) -> Any:
        """Get projects collection."""
        if not self.db_client.db:
            raise RuntimeError("Database not connected")
        return self.db_client.db.projects

    async def create(self, project: Project) -> Project:
        """Create a new project."""
        await self.collection.insert_one(project.model_dump(mode="json"))
        return project

    async def get(self, project_id: UUID) -> Optional[Project]:
        """Get project by ID."""
        doc = await self.collection.find_one({"id": str(project_id)})
        if not doc:
            return None
        # Convert string UUIDs back to UUID objects
        doc["id"] = UUID(doc["id"])
        return Project(**doc)

    async def get_by_name(self, name: str) -> Optional[Project]:
        """Get project by name."""
        doc = await self.collection.find_one({"name": name})
        if not doc:
            return None
        doc["id"] = UUID(doc["id"])
        return Project(**doc)

    async def list_all(self) -> list[Project]:
        """List all projects."""
        cursor = self.collection.find()
        docs = await cursor.to_list(length=None)
        for doc in docs:
            if isinstance(doc["id"], str):
                doc["id"] = UUID(doc["id"])
        return [Project(**doc) for doc in docs]

    async def update(self, project: Project) -> Project:
        """Update an existing project."""
        await self.collection.update_one(
            {"id": str(project.id)}, {"$set": project.model_dump(mode="json")}
        )
        return project

    async def delete(self, project_id: UUID) -> bool:
        """Delete a project."""
        result = await self.collection.delete_one({"id": str(project_id)})
        return result.deleted_count > 0


class AgentRepository:
    """Repository for Agent entities."""

    def __init__(self, db_client: MongoDBClient) -> None:
        self.db_client = db_client

    @property
    def collection(self) -> Any:
        """Get agents collection."""
        if not self.db_client.db:
            raise RuntimeError("Database not connected")
        return self.db_client.db.agents

    async def create(self, agent: Agent) -> Agent:
        """Create a new agent."""
        await self.collection.insert_one(agent.model_dump(mode="json"))
        return agent

    async def get(self, agent_id: str) -> Optional[Agent]:
        """Get agent by ID."""
        doc = await self.collection.find_one({"id": agent_id})
        if not doc:
            return None
        doc["project_id"] = UUID(doc["project_id"])
        return Agent(**doc)

    async def list_by_project(self, project_id: UUID) -> list[Agent]:
        """List all agents for a project."""
        cursor = self.collection.find({"project_id": str(project_id)})
        docs = await cursor.to_list(length=None)
        for doc in docs:
            if isinstance(doc["project_id"], str):
                doc["project_id"] = UUID(doc["project_id"])
        return [Agent(**doc) for doc in docs]

    async def list_by_status(self, status: str) -> list[Agent]:
        """List agents by status."""
        cursor = self.collection.find({"status": status})
        docs = await cursor.to_list(length=None)
        for doc in docs:
            if isinstance(doc["project_id"], str):
                doc["project_id"] = UUID(doc["project_id"])
        return [Agent(**doc) for doc in docs]

    async def update(self, agent: Agent) -> Agent:
        """Update an existing agent."""
        await self.collection.update_one(
            {"id": agent.id}, {"$set": agent.model_dump(mode="json")}
        )
        return agent

    async def delete(self, agent_id: str) -> bool:
        """Delete an agent."""
        result = await self.collection.delete_one({"id": agent_id})
        return result.deleted_count > 0


class TaskRepository:
    """Repository for Task entities."""

    def __init__(self, db_client: MongoDBClient) -> None:
        self.db_client = db_client

    @property
    def collection(self) -> Any:
        """Get tasks collection."""
        if not self.db_client.db:
            raise RuntimeError("Database not connected")
        return self.db_client.db.tasks

    async def create(self, task: Task) -> Task:
        """Create a new task."""
        await self.collection.insert_one(task.model_dump(mode="json"))
        return task

    def _convert_task_doc(self, doc: dict) -> dict:
        """Convert MongoDB document to Task-compatible format."""
        if isinstance(doc["id"], str):
            doc["id"] = UUID(doc["id"])
        if isinstance(doc["project_id"], str):
            doc["project_id"] = UUID(doc["project_id"])
        if doc.get("dependencies"):
            doc["dependencies"] = [UUID(dep) if isinstance(dep, str) else dep for dep in doc["dependencies"]]
        return doc

    async def get(self, task_id: UUID) -> Optional[Task]:
        """Get task by ID."""
        doc = await self.collection.find_one({"id": str(task_id)})
        if not doc:
            return None
        return Task(**self._convert_task_doc(doc))

    async def list_by_project(self, project_id: UUID) -> list[Task]:
        """List all tasks for a project."""
        cursor = self.collection.find({"project_id": str(project_id)})
        docs = await cursor.to_list(length=None)
        return [Task(**self._convert_task_doc(doc)) for doc in docs]

    async def list_by_status(self, status: str) -> list[Task]:
        """List tasks by status."""
        cursor = self.collection.find({"status": status})
        docs = await cursor.to_list(length=None)
        return [Task(**self._convert_task_doc(doc)) for doc in docs]

    async def list_by_agent(self, agent_id: str) -> list[Task]:
        """List tasks assigned to an agent."""
        cursor = self.collection.find({"assigned_agent_id": agent_id})
        docs = await cursor.to_list(length=None)
        return [Task(**self._convert_task_doc(doc)) for doc in docs]

    async def list_pending_tasks(self, project_id: UUID) -> list[Task]:
        """List pending tasks that have no unmet dependencies."""
        cursor = self.collection.find({"project_id": str(project_id), "status": "pending"})
        tasks = [Task(**self._convert_task_doc(doc)) async for doc in cursor]

        # Filter for tasks with no unmet dependencies
        ready_tasks = []
        for task in tasks:
            if not task.dependencies:
                ready_tasks.append(task)
                continue

            # Check if all dependencies are completed
            all_completed = True
            for dep_id in task.dependencies:
                dep_task = await self.get(dep_id)
                if not dep_task or dep_task.status != "completed":
                    all_completed = False
                    break

            if all_completed:
                ready_tasks.append(task)

        return ready_tasks

    async def update(self, task: Task) -> Task:
        """Update an existing task."""
        await self.collection.update_one(
            {"id": str(task.id)}, {"$set": task.model_dump(mode="json")}
        )
        return task

    async def delete(self, task_id: UUID) -> bool:
        """Delete a task."""
        result = await self.collection.delete_one({"id": str(task_id)})
        return result.deleted_count > 0


class SessionRepository:
    """Repository for Session entities."""

    def __init__(self, db_client: MongoDBClient) -> None:
        self.db_client = db_client

    @property
    def collection(self) -> Any:
        """Get sessions collection."""
        if not self.db_client.db:
            raise RuntimeError("Database not connected")
        return self.db_client.db.sessions

    async def create(self, session: Session) -> Session:
        """Create a new session."""
        await self.collection.insert_one(session.model_dump(mode="json"))
        return session

    def _convert_session_doc(self, doc: dict) -> dict:
        """Convert MongoDB document to Session-compatible format."""
        if isinstance(doc["id"], str):
            doc["id"] = UUID(doc["id"])
        if isinstance(doc["task_id"], str):
            doc["task_id"] = UUID(doc["task_id"])
        return doc

    async def get(self, session_id: UUID) -> Optional[Session]:
        """Get session by ID."""
        doc = await self.collection.find_one({"id": str(session_id)})
        if not doc:
            return None
        return Session(**self._convert_session_doc(doc))

    async def list_by_agent(self, agent_id: str) -> list[Session]:
        """List sessions for an agent."""
        cursor = self.collection.find({"agent_id": agent_id})
        docs = await cursor.to_list(length=None)
        return [Session(**self._convert_session_doc(doc)) for doc in docs]

    async def update(self, session: Session) -> Session:
        """Update an existing session."""
        await self.collection.update_one(
            {"id": str(session.id)}, {"$set": session.model_dump(mode="json")}
        )
        return session


class HookEventRepository:
    """Repository for HookEvent entities."""

    def __init__(self, db_client: MongoDBClient) -> None:
        self.db_client = db_client

    @property
    def collection(self) -> Any:
        """Get hook_events collection."""
        if not self.db_client.db:
            raise RuntimeError("Database not connected")
        return self.db_client.db.hook_events

    def _convert_hook_event_doc(self, doc: dict) -> dict:
        """Convert MongoDB document to HookEvent-compatible format."""
        if isinstance(doc["id"], str):
            doc["id"] = UUID(doc["id"])
        if isinstance(doc["session_id"], str):
            doc["session_id"] = UUID(doc["session_id"])
        return doc

    async def create(self, hook_event: HookEvent) -> HookEvent:
        """Create a new hook event."""
        await self.collection.insert_one(hook_event.model_dump(mode="json"))
        return hook_event

    async def get(self, event_id: UUID) -> Optional[HookEvent]:
        """Get hook event by ID."""
        doc = await self.collection.find_one({"id": str(event_id)})
        if not doc:
            return None
        return HookEvent(**self._convert_hook_event_doc(doc))

    async def list_by_session(self, session_id: UUID) -> list[HookEvent]:
        """List hook events for a session."""
        cursor = self.collection.find({"session_id": str(session_id)})
        docs = await cursor.to_list(length=None)
        return [HookEvent(**self._convert_hook_event_doc(doc)) for doc in docs]

    async def list_by_type(self, event_type: str) -> list[HookEvent]:
        """List hook events by type."""
        cursor = self.collection.find({"event_type": event_type})
        docs = await cursor.to_list(length=None)
        return [HookEvent(**self._convert_hook_event_doc(doc)) for doc in docs]

    async def delete_old_events(self, before_timestamp: Any) -> int:
        """Delete hook events older than the specified timestamp."""
        result = await self.collection.delete_many(
            {"timestamp": {"$lt": before_timestamp.isoformat()}}
        )
        return result.deleted_count
