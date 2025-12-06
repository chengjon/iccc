"""Integration tests for multi-agent orchestration."""

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest

from iccc.db.repositories import AgentRepository, MongoDBClient, ProjectRepository, TaskRepository
from iccc.models.entities import Agent, AgentStatus, ModelTier, Project, Task, TaskType
from iccc.orchestrator import Orchestrator
from iccc.planning.templates import TaskDecomposer
from iccc.queue.redis_queue import RedisTaskQueue


@pytest.mark.asyncio
@pytest.mark.integration
async def test_task_queue_basic_operations():
    """Test basic Redis task queue operations."""
    queue = RedisTaskQueue()
    await queue.connect()

    try:
        # Create a test task
        task = Task(
            project_id=uuid4(),
            description="Test task",
            task_type=TaskType.GENERAL_CODING,
        )

        # Enqueue
        await queue.enqueue(task, priority=5)

        # Check queue length
        lengths = await queue.get_queue_length()
        assert lengths["pending"] >= 1

        # Dequeue
        dequeued_task = await queue.dequeue("test-agent")
        assert dequeued_task is not None
        assert dequeued_task.id == task.id

        # Mark completed
        await queue.mark_completed(task.id)

        lengths = await queue.get_queue_length()
        assert lengths["completed"] >= 1

    finally:
        await queue.disconnect()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_task_decomposition():
    """Test HTN task decomposition."""
    decomposer = TaskDecomposer()

    # Decompose a feature implementation task
    tasks = decomposer.decompose_task(
        "User login feature",
        task_type="feature",
        use_tdd=True,
    )

    assert len(tasks) > 0
    assert all(hasattr(task, "name") for task in tasks)
    assert all(hasattr(task, "estimated_complexity") for task in tasks)

    # Check effort estimation
    effort = decomposer.estimate_effort(tasks)
    assert "total_complexity" in effort
    assert "estimated_hours" in effort
    assert effort["total_complexity"] > 0


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("MONGODB_URL"), reason="MongoDB not available in test environment"
)
async def test_full_orchestration_flow():
    """Test full orchestration flow (requires MongoDB and Redis)."""
    # Setup
    db_client = MongoDBClient()
    await db_client.connect()

    project_repo = ProjectRepository(db_client)
    agent_repo = AgentRepository(db_client)
    task_repo = TaskRepository(db_client)

    try:
        # Create test project
        project = Project(name=f"test-project-{uuid4().hex[:8]}", directory="/tmp/test")
        await project_repo.create(project)

        # Create test agent
        agent = Agent(
            id=f"test-agent-{uuid4().hex[:8]}",
            project_id=project.id,
            name="Test Agent",
            agent_type="general",
            model=ModelTier.HAIKU,
        )
        await agent_repo.create(agent)

        # Create orchestrator
        orchestrator = Orchestrator(
            project_id=project.id,
            project_dir=str(project.directory),
        )
        await orchestrator.start()

        # Submit a task
        task_ids = await orchestrator.submit_task(
            description="Test task",
            task_type="general_coding",
            auto_decompose=False,
        )

        assert len(task_ids) == 1

        # Verify task created
        task = await task_repo.get(task_ids[0])
        assert task is not None
        assert task.description == "Test task"

        # Get status
        status = await orchestrator.get_status()
        assert status["status"] == "running"

        await orchestrator.stop()

    finally:
        # Cleanup
        await db_client.disconnect()


@pytest.mark.asyncio
async def test_quality_gates():
    """Test quality gate system."""
    from iccc.quality.gates import QualityGateRunner

    runner = QualityGateRunner()

    # Run gates on current project
    project_dir = Path(__file__).parent.parent.parent
    results = await runner.run_all(project_dir)

    assert len(results) > 0

    # Check report formatting
    report = runner.format_report(results)
    assert "Quality Gate Report" in report
    assert "Overall:" in report
