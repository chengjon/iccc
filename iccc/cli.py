"""Command-line interface for iCCC."""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


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
def project_init(directory: str, name: str | None) -> None:
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
def agent_create(name: str, project_name: str, agent_type: str, model: str | None) -> None:
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
def agent_list(project_name: str | None) -> None:
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

        click.echo("✅ Task created")
        click.echo(f"   ID: {task_obj.id}")
        click.echo(f"   Type: {task_type}")
        click.echo(f"   Recommended model: {recommended_model}")

    asyncio.run(_create())


@task.command("list")
@click.option("--project", "project_name", required=True, help="Project name")
@click.option("--status", type=click.Choice(["pending", "in_progress", "completed", "failed"]))
def task_list(project_name: str, status: str | None) -> None:
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


@cli.command("start")
@click.option("--project", "project_name", required=True, help="Project name to orchestrate.")
def start_orchestrator(project_name: str) -> None:
    """Start the multi-agent orchestration engine for a project."""
    from iccc.orchestrator import Orchestrator

    async def _start() -> None:
        client = MongoDBClient()
        await client.connect()

        project_repo = ProjectRepository(client)
        project_obj = await project_repo.get_by_name(project_name)

        if not project_obj:
            await client.disconnect()
            click.echo(f"❌ Project '{project_name}' not found", err=True)
            sys.exit(1)

        orchestrator = Orchestrator(
            project_id=project_obj.id,
            project_dir=project_obj.directory,
        )

        try:
            click.echo(f"✨ Starting orchestrator for project '{project_name}'...")
            await orchestrator.start()

            # Start all agents associated with this project
            agent_repo = AgentRepository(client)
            agents = await agent_repo.list_by_project(project_obj.id)
            if not agents:
                click.echo(f"⚠️ No agents found for project '{project_name}'. Create agents using 'iccc agent create'.", err=True)
            else:
                for agent in agents:
                    click.echo(f"🚀 Starting agent '{agent.name}' ({agent.id})...")
                    await orchestrator.start_agent(agent.id)

            click.echo("Orchestrator and agents started. Press Ctrl+C to stop.")
            # Keep the orchestrator running
            while True:
                await asyncio.sleep(1) # Keep event loop alive
        except asyncio.CancelledError:
            click.echo("\n👋 Orchestrator stopped by user.")
        except Exception as e:
            click.echo(f"❌ An error occurred: {e}", err=True)
            sys.exit(1)
        finally:
            await orchestrator.stop()
            await client.disconnect()

    asyncio.run(_start())


@cli.group()
def migrate() -> None:
    """Database migration management."""
    pass


@migrate.command("up")
@click.option(
    "--mongodb-url",
    envvar="MONGODB_URL",
    help="MongoDB connection URL (default: from env or localhost)"
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show which migrations would be applied without applying them"
)
def migrate_up(mongodb_url: str | None, dry_run: bool) -> None:
    """Run pending migrations."""
    from iccc.db.migrations import MigrationRunner, get_all_migrations

    async def _run() -> None:
        client = MongoDBClient(mongodb_url)
        try:
            await client.connect()

            runner = MigrationRunner(client)

            # Register all migrations
            for migration in get_all_migrations():
                runner.register(migration)

            # Get status
            statuses = await runner.get_migration_status()
            pending = [s for s in statuses if not s.applied]

            if not pending:
                click.echo(click.style("✓ All migrations up to date", fg="green"))
                return

            if dry_run:
                click.echo(click.style("[DRY RUN] Would apply migrations:", fg="yellow"))
                for status in pending:
                    click.echo(f"  • {status.version}: {status.description}")
                return

            click.echo(click.style("Running pending migrations...", fg="cyan"))
            start_time = time.time()

            applied = await runner.run_pending_migrations(dry_run=False)

            elapsed = time.time() - start_time

            if applied:
                click.echo(
                    click.style(
                        f"\n✓ Applied {len(applied)} migration(s) successfully in {elapsed:.2f}s",
                        fg="green"
                    )
                )
                for version in applied:
                    click.echo(f"  ✓ {version}")
            else:
                click.echo(click.style("✓ All migrations up to date", fg="green"))

        except Exception as e:
            click.echo(click.style(f"✗ Migration failed: {e}", fg="red"), err=True)
            sys.exit(1)
        finally:
            await client.disconnect()

    asyncio.run(_run())


@migrate.command("down")
@click.option(
    "--mongodb-url",
    envvar="MONGODB_URL",
    help="MongoDB connection URL (default: from env or localhost)"
)
@click.option(
    "--version",
    help="Specific migration version to rollback (default: last applied)"
)
def migrate_down(mongodb_url: str | None, version: str | None) -> None:
    """Rollback the last migration or a specific migration."""
    from iccc.db.migrations import MigrationRunner, get_all_migrations

    async def _rollback() -> None:
        client = MongoDBClient(mongodb_url)
        try:
            await client.connect()

            runner = MigrationRunner(client)

            # Register all migrations
            for migration in get_all_migrations():
                runner.register(migration)

            # Get applied migrations
            applied = await runner.get_applied_migrations()

            if not applied:
                click.echo(click.style("No migrations to rollback", fg="yellow"))
                return

            # Determine version to rollback
            rollback_version = version or max(applied)

            # Confirm
            if not version:
                click.echo(
                    f"Will rollback last applied migration: "
                    f"{click.style(rollback_version, fg='yellow')}"
                )
            else:
                click.echo(f"Will rollback migration: {click.style(version, fg='yellow')}")

            if not click.confirm("Continue?"):
                click.echo("Rollback cancelled")
                return

            click.echo(click.style("Rolling back migration...", fg="cyan"))
            start_time = time.time()

            rolled_back = await runner.rollback_migration(rollback_version)

            elapsed = time.time() - start_time

            click.echo(
                click.style(
                    f"\n✓ Rolled back migration {rolled_back} in {elapsed:.2f}s",
                    fg="green"
                )
            )

        except ValueError as e:
            click.echo(click.style(f"✗ {e}", fg="red"), err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(click.style(f"✗ Rollback failed: {e}", fg="red"), err=True)
            sys.exit(1)
        finally:
            await client.disconnect()

    asyncio.run(_rollback())


@migrate.command("status")
@click.option(
    "--mongodb-url",
    envvar="MONGODB_URL",
    help="MongoDB connection URL (default: from env or localhost)"
)
def migrate_status(mongodb_url: str | None) -> None:
    """Show migration status."""
    from iccc.db.migrations import MigrationRunner, get_all_migrations

    async def _status() -> None:
        client = MongoDBClient(mongodb_url)
        try:
            await client.connect()

            runner = MigrationRunner(client)

            # Register all migrations
            for migration in get_all_migrations():
                runner.register(migration)

            # Get status
            statuses = await runner.get_migration_status()

            if not statuses:
                click.echo("No migrations registered")
                return

            applied = [s for s in statuses if s.applied]
            pending = [s for s in statuses if not s.applied]

            click.echo(click.style("Database Migrations Status", fg="cyan", bold=True))
            click.echo("=" * 50)

            if applied:
                click.echo(click.style(f"\nApplied ({len(applied)}):", fg="green"))
                for status in applied:
                    applied_date = ""
                    if status.applied_at:
                        # Format the ISO datetime to be more readable
                        applied_date = f" (applied: {status.applied_at[:10]})"
                    click.echo(f"  ✓ {status.version}: {status.description}{applied_date}")

            if pending:
                click.echo(click.style(f"\nPending ({len(pending)}):", fg="yellow"))
                for status in pending:
                    click.echo(f"  • {status.version}: {status.description}")
            else:
                click.echo(click.style("\n✓ All migrations applied", fg="green"))

        except Exception as e:
            click.echo(click.style(f"✗ Failed to get status: {e}", fg="red"), err=True)
            sys.exit(1)
        finally:
            await client.disconnect()

    asyncio.run(_status())


@migrate.command("list")
@click.option(
    "--mongodb-url",
    envvar="MONGODB_URL",
    help="MongoDB connection URL (default: from env or localhost)"
)
def migrate_list(mongodb_url: str | None) -> None:
    """List all migrations."""
    from iccc.db.migrations import MigrationRunner, get_all_migrations

    async def _list() -> None:
        client = MongoDBClient(mongodb_url)
        try:
            await client.connect()

            runner = MigrationRunner(client)

            # Register all migrations
            for migration in get_all_migrations():
                runner.register(migration)

            # Get migrations
            migrations = await runner.list_migrations()

            if not migrations:
                click.echo("No migrations registered")
                return

            click.echo(click.style("All Migrations", fg="cyan", bold=True))
            click.echo("=" * 50)

            for version, description, is_applied in migrations:
                status_icon = "✓" if is_applied else "•"
                status_color = "green" if is_applied else "white"
                status_text = "applied" if is_applied else "pending"

                click.echo(
                    f"  {click.style(status_icon, fg=status_color)} "
                    f"{click.style(version, bold=True)}: {description} "
                    f"({click.style(status_text, fg=status_color)})"
                )

        except Exception as e:
            click.echo(click.style(f"✗ Failed to list migrations: {e}", fg="red"), err=True)
            sys.exit(1)
        finally:
            await client.disconnect()

    asyncio.run(_list())


@migrate.command("create")
@click.argument("name")
@click.option(
    "--description",
    help="Migration description"
)
def migrate_create(name: str, description: str | None) -> None:
    """Create a new migration file."""
    from iccc.db.migration_template import MigrationTemplate

    try:
        # Determine migrations directory
        # Look for migrations in iccc/db/migration_files/ directory
        project_root = Path(__file__).parent.parent
        migrations_dir = project_root / "iccc" / "db" / "migration_files"

        # Create migration file
        filepath = MigrationTemplate.create_migration_file(
            migrations_dir,
            name,
            description or f"Migration: {name}"
        )

        click.echo(click.style(f"✓ Created migration: {filepath}", fg="green"))
        click.echo(
            click.style(
                "\nNext steps:",
                fg="cyan",
                bold=True
            )
        )
        click.echo("  1. Edit the migration file and implement up() and down() methods")
        click.echo("  2. Add the migration to get_all_migrations() in iccc/db/migrations.py")
        click.echo("  3. Test the migration with: iccc migrate up --dry-run")
        click.echo("  4. Apply the migration with: iccc migrate up")

    except ValueError as e:
        click.echo(click.style(f"✗ Invalid migration name: {e}", fg="red"), err=True)
        sys.exit(1)
    except FileExistsError as e:
        click.echo(click.style(f"✗ {e}", fg="red"), err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(click.style(f"✗ Failed to create migration: {e}", fg="red"), err=True)
        sys.exit(1)


def main() -> None:
    """Entry point for the CLI."""
    cli()



if __name__ == "__main__":
    main()
