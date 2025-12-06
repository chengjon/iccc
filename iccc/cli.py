"""Command-line interface for iCCC."""

import asyncio
import sys
from pathlib import Path
from typing import Optional
from uuid import UUID

import click

from iccc.agents.model_selector import ModelSelector
from iccc.agents.subagent import SubagentLoader
from iccc.db.repositories import (
    AgentRepository,
    MongoDBClient,
    ProjectRepository,
    TaskRepository,
)
from iccc.models.entities import Agent, AgentStatus, Project, Task, TaskStatus, TaskType


@click.group()
@click.version_option(version="0.1.0")
def cli() -> None:
    """iCCC - Multi-agent orchestration system for AI CLI instances."""
    pass


@cli.group()
def project() -> None:
    """Manage projects."""
    pass


@project.command("init")
@click.argument("directory", type=click.Path())
@click.option("--name", help="Project name (defaults to directory name)")
def project_init(directory: str, name: Optional[str]) -> None:
    """Initialize a new project."""
    async def _init() -> None:
        client = MongoDBClient()
        await client.connect()

        repo = ProjectRepository(client)

        dir_path = Path(directory).absolute()
        project_name = name or dir_path.name

        project_obj = Project(
            name=project_name,
            directory=str(dir_path),
        )

        await repo.create(project_obj)
        await client.disconnect()

        click.echo(f"✅ Project '{project_name}' initialized")
        click.echo(f"   ID: {project_obj.id}")
        click.echo(f"   Directory: {dir_path}")

    asyncio.run(_init())


@project.command("list")
def project_list() -> None:
    """List all projects."""
    async def _list() -> None:
        client = MongoDBClient()
        await client.connect()

        repo = ProjectRepository(client)
        projects = await repo.list_all()
        await client.disconnect()

        if not projects:
            click.echo("No projects found")
            return

        click.echo("Projects:")
        for proj in projects:
            click.echo(f"  • {proj.name} ({proj.status})")
            click.echo(f"    ID: {proj.id}")
            click.echo(f"    Directory: {proj.directory}")

    asyncio.run(_list())


@cli.group()
def agent() -> None:
    """Manage agents."""
    pass


@agent.command("create")
@click.option("--name", required=True, help="Agent name")
@click.option("--project", "project_name", required=True, help="Project name")
@click.option("--type", "agent_type", default="general", help="Agent type or preset")
@click.option("--model", type=click.Choice(["haiku", "sonnet", "opus"]), help="Model tier")
def agent_create(name: str, project_name: str, agent_type: str, model: Optional[str]) -> None:
    """Create a new agent."""
    async def _create() -> None:
        client = MongoDBClient()
        await client.connect()

        # Find project
        project_repo = ProjectRepository(client)
        project_obj = await project_repo.get_by_name(project_name)
        if not project_obj:
            await client.disconnect()
            click.echo(f"❌ Project '{project_name}' not found", err=True)
            sys.exit(1)

        # Load agent configuration
        try:
            config = SubagentLoader.load_config(agent_type)
            selected_model = config.model
            specialization = config.specialization
            tools = config.tools
        except FileNotFoundError:
            # Use generic agent
            selected_model = {"haiku": "claude-3-5-haiku-latest", "sonnet": "claude-sonnet-4-20250514", "opus": "claude-opus-4-20250514"}.get(model or "sonnet", "claude-sonnet-4-20250514")
            specialization = None
            tools = []

        # Create agent
        agent_repo = AgentRepository(client)
        agent_obj = Agent(
            id=f"agent-{name}",
            project_id=project_obj.id,
            name=name,
            agent_type=agent_type,
            model=selected_model,
            specialization=specialization,
            tools=tools,
            status=AgentStatus.IDLE,
        )

        await agent_repo.create(agent_obj)
        await client.disconnect()

        click.echo(f"✅ Agent '{name}' created")
        click.echo(f"   ID: {agent_obj.id}")
        click.echo(f"   Type: {agent_type}")
        click.echo(f"   Model: {selected_model}")

    asyncio.run(_create())


@agent.command("list")
@click.option("--project", "project_name", help="Filter by project")
def agent_list(project_name: Optional[str]) -> None:
    """List agents."""
    async def _list() -> None:
        client = MongoDBClient()
        await client.connect()

        agent_repo = AgentRepository(client)

        if project_name:
            project_repo = ProjectRepository(client)
            project_obj = await project_repo.get_by_name(project_name)
            if not project_obj:
                await client.disconnect()
                click.echo(f"❌ Project '{project_name}' not found", err=True)
                sys.exit(1)
            agents = await agent_repo.list_by_project(project_obj.id)
        else:
            agents = await agent_repo.list_by_status(AgentStatus.IDLE)
            agents.extend(await agent_repo.list_by_status(AgentStatus.BUSY))

        await client.disconnect()

        if not agents:
            click.echo("No agents found")
            return

        click.echo("Agents:")
        for ag in agents:
            click.echo(f"  • {ag.name} ({ag.status})")
            click.echo(f"    ID: {ag.id}")
            click.echo(f"    Model: {ag.model}")

    asyncio.run(_list())


@cli.group()
def task() -> None:
    """Manage tasks."""
    pass


@task.command("create")
@click.option("--project", "project_name", required=True, help="Project name")
@click.option("--description", required=True, help="Task description")
@click.option("--type", "task_type", default="general_coding", help="Task type")
def task_create(project_name: str, description: str, task_type: str) -> None:
    """Create a new task."""
    async def _create() -> None:
        client = MongoDBClient()
        await client.connect()

        # Find project
        project_repo = ProjectRepository(client)
        project_obj = await project_repo.get_by_name(project_name)
        if not project_obj:
            await client.disconnect()
            click.echo(f"❌ Project '{project_name}' not found", err=True)
            sys.exit(1)

        # Create task
        task_repo = TaskRepository(client)
        task_obj = Task(
            project_id=project_obj.id,
            description=description,
            task_type=TaskType(task_type),
            status=TaskStatus.PENDING,
        )

        await task_repo.create(task_obj)
        await client.disconnect()

        # Show recommended model
        recommended_model = ModelSelector.select_model(task_obj.task_type)

        click.echo(f"✅ Task created")
        click.echo(f"   ID: {task_obj.id}")
        click.echo(f"   Type: {task_type}")
        click.echo(f"   Recommended model: {recommended_model}")

    asyncio.run(_create())


@task.command("list")
@click.option("--project", "project_name", required=True, help="Project name")
@click.option("--status", type=click.Choice(["pending", "in_progress", "completed", "failed"]))
def task_list(project_name: str, status: Optional[str]) -> None:
    """List tasks."""
    async def _list() -> None:
        client = MongoDBClient()
        await client.connect()

        # Find project
        project_repo = ProjectRepository(client)
        project_obj = await project_repo.get_by_name(project_name)
        if not project_obj:
            await client.disconnect()
            click.echo(f"❌ Project '{project_name}' not found", err=True)
            sys.exit(1)

        task_repo = TaskRepository(client)
        if status:
            tasks = await task_repo.list_by_status(status)
            tasks = [t for t in tasks if t.project_id == project_obj.id]
        else:
            tasks = await task_repo.list_by_project(project_obj.id)

        await client.disconnect()

        if not tasks:
            click.echo("No tasks found")
            return

        click.echo("Tasks:")
        for t in tasks:
            click.echo(f"  • [{t.status}] {t.description[:60]}...")
            click.echo(f"    ID: {t.id}")
            click.echo(f"    Type: {t.task_type}")

    asyncio.run(_list())


@cli.command("presets")
def list_presets() -> None:
    """List available agent presets."""
    agents = SubagentLoader.list_available_agents()

    if not agents:
        click.echo("No agent presets found")
        return

    click.echo("Available agent presets:")
    for agent_name in agents:
        click.echo(f"  • {agent_name}")


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
