"""Main orchestrator for coordinating multiple agents."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from iccc.agents.client import ClaudeClient
from iccc.agents.model_selector import ModelSelector
from iccc.db.repositories import AgentRepository, MongoDBClient, TaskRepository
from iccc.hooks.manager import HookManager
from iccc.isolation.worktree import WorktreeManager
from iccc.locks.file_lock import FileLockManager
from iccc.models.entities import Agent, AgentStatus, Message, Task, TaskStatus, TaskType
from iccc.planning.templates import TaskDecomposer  # Import from templates.py module
from iccc.queue.redis_queue import RedisTaskQueue

logger = logging.getLogger(__name__)


class Orchestrator:
    """Main orchestrator for multi-agent coordination."""

    def __init__(
        self,
        project_id: UUID,
        project_dir: str,
        mongodb_url: str | None = None,
        redis_url: str | None = None,
        anthropic_api_key: str | None = None,
    ) -> None:
        self.project_id = project_id
        self.project_dir = project_dir

        # Initialize components
        self.db_client = MongoDBClient(mongodb_url)
        self.task_queue = RedisTaskQueue(redis_url)
        self.file_lock_manager = FileLockManager(redis_url)
        self.worktree_manager = WorktreeManager(project_dir)
        self.claude_client = ClaudeClient(anthropic_api_key)
        self.hook_manager = HookManager(lock_manager=self.file_lock_manager)
        self.task_decomposer = TaskDecomposer()

        # Repositories
        self.agent_repo: AgentRepository | None = None
        self.task_repo: TaskRepository | None = None

        # Running agents
        self.running_agents: dict[str, asyncio.Task[None]] = {}

    async def start(self) -> None:
        """Start the orchestrator."""
        await self.db_client.connect()
        await self.task_queue.connect()
        await self.file_lock_manager.connect()

        self.agent_repo = AgentRepository(self.db_client)
        self.task_repo = TaskRepository(self.db_client)

    async def stop(self) -> None:
        """Stop the orchestrator and cleanup."""
        # Stop all running agents
        for agent_id, agent_task in self.running_agents.items():
            agent_task.cancel()
            try:
                await agent_task
            except asyncio.CancelledError:
                pass

        # Cleanup connections
        await self.db_client.disconnect()
        await self.task_queue.disconnect()
        await self.file_lock_manager.disconnect()
        await self.claude_client.close()

    async def submit_task(
        self,
        description: str,
        task_type: str = "implement_feature",
        auto_decompose: bool = True,
        **kwargs: bool | str,
    ) -> list[UUID]:
        """
        Submit a high-level task for execution.

        Args:
            description: Task description
            task_type: Type of task
            auto_decompose: Whether to automatically decompose into subtasks
            **kwargs: Additional task parameters

        Returns:
            List of task IDs created
        """
        if not self.task_repo:
            raise RuntimeError("Orchestrator not started")

        task_ids: list[UUID] = []

        # Ensure task_type is a valid TaskType enum member, default to GENERAL_CODING if invalid
        try:
            # Try to match enum value (e.g., "general_coding")
            enum_task_type = TaskType(task_type)
        except ValueError:
            # Fallback default
            enum_task_type = TaskType.GENERAL_CODING

        if auto_decompose:
            # Decompose into primitive tasks
            primitive_tasks = self.task_decomposer.decompose_task(
                description, task_type, **kwargs
            )

            # Create database tasks
            for i, prim_task in enumerate(primitive_tasks):
                task = Task(
                    project_id=self.project_id,
                    description=f"{prim_task.name}: {description}",
                    task_type=enum_task_type,
                    status=TaskStatus.PENDING,
                    metadata={"primitive_task": prim_task.name, "complexity": prim_task.estimated_complexity},
                )

                # Add dependencies (sequential for now)
                if i > 0:
                    task.dependencies = [task_ids[i - 1]]

                await self.task_repo.create(task)
                await self.task_queue.enqueue(task, priority=prim_task.estimated_complexity)
                task_ids.append(task.id)
        else:
            # Create single task
            task = Task(
                project_id=self.project_id,
                description=description,
                task_type=enum_task_type,
                status=TaskStatus.PENDING,
            )
            await self.task_repo.create(task)
            await self.task_queue.enqueue(task)
            task_ids.append(task.id)

        return task_ids

    async def start_agent(self, agent_id: str) -> None:
        """
        Start an agent worker.

        Args:
            agent_id: ID of the agent to start
        """
        if not self.agent_repo:
            raise RuntimeError("Orchestrator not started")

        # Get agent from database
        agent = await self.agent_repo.get(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Create worktree for agent
        worktree_path = await self.worktree_manager.create_worktree(agent_id)
        agent.worktree_path = str(worktree_path)
        agent.status = AgentStatus.IDLE
        await self.agent_repo.update(agent)

        # Start agent worker task
        worker_task = asyncio.create_task(self._agent_worker(agent))
        self.running_agents[agent_id] = worker_task

    async def stop_agent(self, agent_id: str) -> None:
        """
        Stop an agent worker.

        Args:
            agent_id: ID of the agent to stop
        """
        if agent_id not in self.running_agents:
            return

        # Cancel worker task
        self.running_agents[agent_id].cancel()
        del self.running_agents[agent_id]

        # Update agent status
        if self.agent_repo:
            agent = await self.agent_repo.get(agent_id)
            if agent:
                agent.status = AgentStatus.STOPPED
                await self.agent_repo.update(agent)

        # Remove worktree
        await self.worktree_manager.remove_worktree(agent_id)

    async def _agent_worker(self, agent: Agent) -> None:
        """
        Agent worker loop.

        Args:
            agent: Agent to run
        """
        task_count = 0
        sync_interval = 10  # Sync worktree every 10 tasks

        while True:
            try:
                # Periodically sync worktree with main branch
                if task_count > 0 and task_count % sync_interval == 0:
                    try:
                        await self.worktree_manager.sync_worktree(agent.id)
                        logger.debug(f"Synced worktree for agent {agent.id}")
                    except Exception as e:
                        logger.warning(
                            f"Failed to sync worktree for agent {agent.id}: {e}",
                            exc_info=True,
                            extra={"agent_id": agent.id, "task_count": task_count},
                        )

                # Dequeue a task
                task = await self.task_queue.dequeue(agent.id)

                if not task:
                    # No tasks available, wait
                    await asyncio.sleep(1)
                    continue

                # Execute task
                await self._execute_task(agent, task)
                task_count += 1

            except asyncio.CancelledError:
                logger.info(f"Agent {agent.id} worker cancelled")
                break
            except Exception as e:
                logger.error(
                    f"Agent {agent.id} worker error: {e}",
                    exc_info=True,
                    extra={"agent_id": agent.id, "task_count": task_count},
                )
                await asyncio.sleep(5)

    async def _execute_task(self, agent: Agent, task: Task) -> None:
        """
        Execute a task with an agent.

        Args:
            agent: Agent executing the task
            task: Task to execute
        """
        if not self.task_repo or not self.agent_repo:
            return

        try:
            # Update agent and task status
            agent.status = AgentStatus.BUSY
            await self.agent_repo.update(agent)

            task.status = TaskStatus.IN_PROGRESS
            task.assigned_agent_id = agent.id
            task.started_at = datetime.now()
            await self.task_repo.update(task)

            # Prepare conversation
            messages = [
                Message(
                    role="user",
                    content=f"Task: {task.description}\n\nPlease complete this task.",
                )
            ]

            # Select model based on task
            model = ModelSelector.select_model(task.task_type, task.complexity)

            # Execute with hooks
            await self.hook_manager.trigger(
                "PreToolUse",
                {"task_id": str(task.id), "agent_id": agent.id},
                agent_id=agent.id,
            )

            # Call Claude API
            response = await self.claude_client.send_message(
                messages=messages,
                model=model,
                system=f"You are {agent.name}, a specialized agent for {agent.specialization or 'general'} tasks.",
            )

            # Store result
            task.result = response["content"]
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            await self.task_repo.update(task)

            # Mark task as completed in queue
            await self.task_queue.mark_completed(task.id)

            # Trigger post-execution hooks
            await self.hook_manager.trigger(
                "PostToolUse",
                {"task_id": str(task.id), "agent_id": agent.id, "result": response["content"]},
                agent_id=agent.id,
            )

        except Exception as e:
            logger.error(
                f"Task {task.id} execution failed: {e}",
                exc_info=True,
                extra={
                    "task_id": str(task.id),
                    "agent_id": agent.id,
                    "task_type": task.task_type,
                    "description": task.description,
                },
            )
            # Mark task as failed
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now()
            await self.task_repo.update(task)

            await self.task_queue.mark_failed(task.id, str(e))

        finally:
            # Update agent status
            agent.status = AgentStatus.IDLE
            agent.last_active = datetime.now()
            await self.agent_repo.update(agent)

    async def get_status(self) -> dict[str, Any]:
        """Get orchestrator status."""
        if not self.agent_repo:
            return {"status": "not_started"}

        # Get queue lengths
        queue_status = await self.task_queue.get_queue_length()

        # Get agent statuses
        agents = await self.agent_repo.list_by_project(self.project_id)
        agent_statuses = {agent.id: agent.status for agent in agents}

        return {
            "status": "running",
            "agents": agent_statuses,
            "tasks": queue_status,
            "running_agents": len(self.running_agents),
        }
