"""MongoDB repositories for data access."""

import os
from typing import Any
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from iccc.models.entities import (
    Agent,
    Goal,
    HookEvent,
    Project,
    PromptTemplate,
    Session,
    Task,
)
from iccc.config import get_config


class MongoDBClient:
    """MongoDB client wrapper."""

    def __init__(self, mongodb_url: str | None = None) -> None:
        self.mongodb_url = mongodb_url or get_config().mongodb.uri
        self.client: AsyncIOMotorClient[Any] | None = None
        self.db: AsyncIOMotorDatabase[Any] | None = None

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

    async def get(self, project_id: UUID) -> Project | None:
        """Get project by ID."""
        doc = await self.collection.find_one({"id": str(project_id)})
        if not doc:
            return None
        # Convert string UUIDs back to UUID objects
        doc["id"] = UUID(doc["id"])
        return Project(**doc)

    async def get_by_name(self, name: str) -> Project | None:
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
        return bool(result.deleted_count > 0)


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

    async def get(self, agent_id: str) -> Agent | None:
        """Get agent by ID."""
        doc = await self.collection.find_one({"id": agent_id})
        if not doc:
            return None
        doc["project_id"] = UUID(doc["project_id"])
        return Agent(**doc)

    async def get_by_id(self, agent_id: str) -> Agent | None:
        """Get agent by ID (alias for get)."""
        return await self.get(agent_id)

    async def list_all(self) -> list[Agent]:
        """List all agents."""
        cursor = self.collection.find()
        docs = await cursor.to_list(length=None)
        for doc in docs:
            if isinstance(doc["project_id"], str):
                doc["project_id"] = UUID(doc["project_id"])
        return [Agent(**doc) for doc in docs]

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
        return bool(result.deleted_count > 0)


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

    def _convert_task_doc(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Convert MongoDB document to Task-compatible format."""
        if isinstance(doc["id"], str):
            doc["id"] = UUID(doc["id"])
        if isinstance(doc["project_id"], str):
            doc["project_id"] = UUID(doc["project_id"])
        if doc.get("dependencies"):
            doc["dependencies"] = [UUID(dep) if isinstance(dep, str) else dep for dep in doc["dependencies"]]
        return doc

    async def get(self, task_id: UUID) -> Task | None:
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
        return bool(result.deleted_count > 0)


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

    def _convert_session_doc(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Convert MongoDB document to Session-compatible format."""
        if isinstance(doc["id"], str):
            doc["id"] = UUID(doc["id"])
        if isinstance(doc["task_id"], str):
            doc["task_id"] = UUID(doc["task_id"])
        return doc

    async def get(self, session_id: UUID) -> Session | None:
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

    def _convert_hook_event_doc(self, doc: dict[str, Any]) -> dict[str, Any]:
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

    async def get(self, event_id: UUID) -> HookEvent | None:
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
        return int(result.deleted_count)


class PromptTemplateRepository:
    """Repository for PromptTemplate entities."""

    def __init__(self, db_client: MongoDBClient) -> None:
        self.db_client = db_client

    @property
    def collection(self) -> Any:
        """Get prompt_templates collection."""
        if not self.db_client.db:
            raise RuntimeError("Database not connected")
        return self.db_client.db.prompt_templates

    def _convert_doc(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Convert MongoDB document to PromptTemplate-compatible format."""
        if isinstance(doc["id"], str):
            from uuid import UUID

            doc["id"] = UUID(doc["id"])
        return doc

    async def create(self, template: PromptTemplate) -> PromptTemplate:
        """Create a new prompt template."""
        await self.collection.insert_one(template.model_dump(mode="json"))
        return template

    async def get(self, template_id: UUID) -> PromptTemplate | None:
        """Get prompt template by ID."""
        doc = await self.collection.find_one({"id": str(template_id)})
        if not doc:
            return None
        return PromptTemplate(**self._convert_doc(doc))

    async def get_by_name(self, name: str) -> PromptTemplate | None:
        """Get prompt template by name."""
        doc = await self.collection.find_one({"name": name})
        if not doc:
            return None
        return PromptTemplate(**self._convert_doc(doc))

    async def list_by_category(self, category: str) -> list[PromptTemplate]:
        """List prompt templates by category."""
        cursor = self.collection.find({"category": category})
        docs = await cursor.to_list(length=None)
        return [PromptTemplate(**self._convert_doc(doc)) for doc in docs]

    async def list_all(self) -> list[PromptTemplate]:
        """List all prompt templates."""
        cursor = self.collection.find()
        docs = await cursor.to_list(length=None)
        return [PromptTemplate(**self._convert_doc(doc)) for doc in docs]

    async def update(self, template: PromptTemplate) -> PromptTemplate:
        """Update an existing prompt template."""
        await self.collection.update_one(
            {"id": str(template.id)}, {"$set": template.model_dump(mode="json")}
        )
        return template

    async def delete(self, template_id: UUID) -> bool:
        """Delete a prompt template."""
        result = await self.collection.delete_one({"id": str(template_id)})
        return bool(result.deleted_count > 0)


class GoalRepository:
    """Repository for Goal entities (HTN planning system)."""

    def __init__(self, db_client: MongoDBClient) -> None:
        self.db_client = db_client

    @property
    def collection(self) -> Any:
        """Get goals collection."""
        if not self.db_client.db:
            raise RuntimeError("Database not connected")
        return self.db_client.db.goals

    def _convert_doc(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Convert MongoDB document to Goal-compatible format."""
        from uuid import UUID as UUIDType

        if isinstance(doc["id"], str):
            doc["id"] = UUIDType(doc["id"])
        if isinstance(doc["project_id"], str):
            doc["project_id"] = UUIDType(doc["project_id"])
        if doc.get("parent_goal_id") and isinstance(doc["parent_goal_id"], str):
            doc["parent_goal_id"] = UUIDType(doc["parent_goal_id"])
        if doc.get("sub_task_ids"):
            doc["sub_task_ids"] = [
                UUIDType(tid) if isinstance(tid, str) else tid
                for tid in doc["sub_task_ids"]
            ]
        return doc

    async def create(self, goal: Goal) -> Goal:
        """Create a new goal."""
        await self.collection.insert_one(goal.model_dump(mode="json"))
        return goal

    async def get(self, goal_id: UUID) -> Goal | None:
        """Get goal by ID."""
        doc = await self.collection.find_one({"id": str(goal_id)})
        if not doc:
            return None
        return Goal(**self._convert_doc(doc))

    async def list_by_project(self, project_id: UUID) -> list[Goal]:
        """List goals for a project."""
        cursor = self.collection.find({"project_id": str(project_id)})
        docs = await cursor.to_list(length=None)
        return [Goal(**self._convert_doc(doc)) for doc in docs]

    async def list_by_status(self, status: str) -> list[Goal]:
        """List goals by status."""
        cursor = self.collection.find({"status": status})
        docs = await cursor.to_list(length=None)
        return [Goal(**self._convert_doc(doc)) for doc in docs]

    async def list_sub_goals(self, parent_goal_id: UUID) -> list[Goal]:
        """List sub-goals of a parent goal."""
        cursor = self.collection.find({"parent_goal_id": str(parent_goal_id)})
        docs = await cursor.to_list(length=None)
        return [Goal(**self._convert_doc(doc)) for doc in docs]

    async def list_by_priority(
        self, project_id: UUID, max_priority: int = 5
    ) -> list[Goal]:
        """List goals by priority (1=highest)."""
        cursor = self.collection.find(
            {"project_id": str(project_id), "priority": {"$lte": max_priority}}
        ).sort("priority", ASCENDING)
        docs = await cursor.to_list(length=None)
        return [Goal(**self._convert_doc(doc)) for doc in docs]

    async def update(self, goal: Goal) -> Goal:
        """Update an existing goal."""
        await self.collection.update_one(
            {"id": str(goal.id)}, {"$set": goal.model_dump(mode="json")}
        )
        return goal

    async def delete(self, goal_id: UUID) -> bool:
        """Delete a goal."""
        result = await self.collection.delete_one({"id": str(goal_id)})
        return bool(result.deleted_count > 0)
