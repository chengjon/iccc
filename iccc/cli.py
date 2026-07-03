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
from iccc.core.instruction_processor import process_instruction
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


@task.command("import")
@click.option("--project", "project_name", required=True, help="Project name")
@click.option("--file", "file_path", default=".iccc/.plans/current_tasks.json", help="Path to tasks JSON file")
def task_import(project_name: str, file_path: str) -> None:
    """Import tasks from a JSON plan file."""
    import json
    from iccc.queue.redis_queue import RedisTaskQueue
    from iccc.models.entities import RoleType

    async def _import() -> None:
        path = Path(file_path)
        if not path.exists():
            click.echo(f"❌ File not found: {path}", err=True)
            return

        try:
            with open(path, "r") as f:
                tasks_data = json.load(f)
        except json.JSONDecodeError:
            click.echo(f"❌ Invalid JSON in file: {path}", err=True)
            return

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
        task_queue = RedisTaskQueue()
        await task_queue.connect()

        count = 0
        for item in tasks_data:
            try:
                # Map string type to enum
                t_type_str = item.get("task_type", "general_coding").lower()
                try:
                    t_type = TaskType(t_type_str)
                except ValueError:
                    t_type = TaskType.GENERAL_CODING

                task = Task(
                    project_id=project_obj.id,
                    description=f"{item.get('title')}: {item.get('description')}",
                    task_type=t_type,
                    status=TaskStatus.PENDING,
                    metadata={"original_id": item.get("id")}
                )
                
                await task_repo.create(task)

                # Determine role
                role = RoleType.WORKER
                if t_type in [TaskType.CODE_REVIEW, TaskType.ARCHITECTURE_DESIGN, TaskType.SECURITY_AUDIT]:
                    role = RoleType.MANAGER
                
                await task_queue.enqueue(task, role=role)
                count += 1
                click.echo(f"  • Imported: {task.description[:50]}... -> {role}")

            except Exception as e:
                click.echo(f"  ⚠️ Failed to import task: {e}")

        await client.disconnect()
        await task_queue.disconnect()
        click.echo(f"✅ Successfully imported {count} tasks.")

    asyncio.run(_import())


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


@cli.group()
def iccc() -> None:
    """iCCC 指令系统 - 多CLI协作平台的核心指令集合"""
    pass


@iccc.command("workflow")
@click.argument("description")
def workflow_command(description: str) -> None:
    """执行标准工作流（中等复杂度功能开发）"""
    async def _execute() -> None:
        try:
            command = f"/iccc/workflow {description}"
            instruction = await process_instruction(command)

            click.echo(f"✅ 指令执行成功")
            click.echo(f"   指令ID: {instruction.id}")
            click.echo(f"   指令类型: {instruction.type.value}")
            click.echo(f"   状态: {instruction.status.value}")

            if hasattr(instruction, 'result') and instruction.result:
                click.echo(f"   结果: {instruction.result}")

        except Exception as e:
            click.echo(f"❌ 指令执行失败: {e}", err=True)
            sys.exit(1)

    asyncio.run(_execute())


@iccc.command("multi-workflow")
@click.argument("description")
def multi_workflow_command(description: str) -> None:
    """执行复杂工作流（高复杂度多代理协同开发）"""
    async def _execute() -> None:
        try:
            command = f"/iccc/multi-workflow {description}"
            instruction = await process_instruction(command)

            click.echo(f"✅ 多代理工作流执行成功")
            click.echo(f"   指令ID: {instruction.id}")
            click.echo(f"   指令类型: {instruction.type.value}")
            click.echo(f"   状态: {instruction.status.value}")

            if hasattr(instruction, 'result') and instruction.result:
                click.echo(f"   结果: {instruction.result}")

        except Exception as e:
            click.echo(f"❌ 多代理工作流执行失败: {e}", err=True)
            sys.exit(1)

    asyncio.run(_execute())


@iccc.command("spec")
@click.argument("description")
@click.option("--output", "-o", help="规格输出文件名")
def spec_command(description: str, output: str | None) -> None:
    """创建详细规格文档"""
    async def _create() -> None:
        try:
            command = f"/iccc/spec {description}"
            instruction = await process_instruction(command)

            click.echo(f"✅ 规格文档创建成功")
            click.echo(f"   指令ID: {instruction.id}")

            if hasattr(instruction, 'result') and instruction.result:
                result = instruction.result
                if "spec_file" in result:
                    click.echo(f"   规格文件: {result['spec_file']}")

        except Exception as e:
            click.echo(f"❌ 创建规格文档失败: {e}", err=True)
            sys.exit(1)

    asyncio.run(_create())


@iccc.command("ultra")
@click.argument("analysis_target")
def ultra_command(analysis_target: str) -> None:
    """深度分析复杂技术问题"""
    async def _analyze() -> None:
        try:
            command = f"/iccc/ultra {analysis_target}"
            instruction = await process_instruction(command)

            click.echo(f"✅ 深度分析完成")
            click.echo(f"   指令ID: {instruction.id}")

            if hasattr(instruction, 'result') and instruction.result:
                result = instruction.result
                click.echo(f"   分析类型: {result.get('analysis_type', '未知')}")
                click.echo(f"   分析深度: {result.get('depth', '未知')}")
                click.echo(f"   状态: {result.get('status', '未知')}")

        except Exception as e:
            click.echo(f"❌ 深度分析失败: {e}", err=True)
            sys.exit(1)

    asyncio.run(_analyze())


@iccc.command("reflection")
@click.argument("target")
def reflection_command(target: str) -> None:
    """工作反思与改进建议"""
    async def _reflect() -> None:
        try:
            command = f"/iccc/reflection {target}"
            instruction = await process_instruction(command)

            click.echo(f"✅ 反思分析完成")
            click.echo(f"   指令ID: {instruction.id}")

            if hasattr(instruction, 'result') and instruction.result:
                result = instruction.result
                click.echo(f"   分析状态: {result.get('status', '未知')}")

        except Exception as e:
            click.echo(f"❌ 反思分析失败: {e}", err=True)
            sys.exit(1)

    asyncio.run(_reflect())


@iccc.command("review")
@click.argument("target")
@click.option("--type", "review_type", default="code", help="审查类型: code, security, performance")
def review_command(target: str, review_type: str) -> None:
    """代码质量审查"""
    async def _review() -> None:
        try:
            if review_type == "code":
                command = f"/iccc/review {target}"
            else:
                command = f"/iccc/review --type {review_type} {target}"

            instruction = await process_instruction(command)

            click.echo(f"✅ {review_type}审查完成")
            click.echo(f"   指令ID: {instruction.id}")

            if hasattr(instruction, 'result') and instruction.result:
                result = instruction.result
                click.echo(f"   审查状态: {result.get('status', '未知')}")

        except Exception as e:
            click.echo(f"❌ 审查失败: {e}", err=True)
            sys.exit(1)

    asyncio.run(_review())


@iccc.command("status")
@click.option("--instruction-id", help="查看指定指令状态")
def status_command(instruction_id: str | None) -> None:
    """查看指令执行状态"""
    async def _show_status() -> None:
        try:
            if instruction_id:
                command = f"/iccc/status {instruction_id}"
                instruction = await process_instruction(command)

                click.echo(f"✅ 指令状态查询")
                click.echo(f"   指令ID: {instruction.id}")
                click.echo(f"   状态: {instruction.status.value}")
                click.echo(f"   创建时间: {instruction.created_at}")
                click.echo(f"   开始时间: {instruction.started_at or '未开始'}")
                click.echo(f"   完成时间: {instruction.completed_at or '未完成'}")
            else:
                command = "/iccc/status show"
                instruction = await process_instruction(command)

                click.echo("✅ 系统状态查询")

        except Exception as e:
            click.echo(f"❌ 状态查询失败: {e}", err=True)
            sys.exit(1)

    asyncio.run(_show_status())


@iccc.command("config")
@click.argument("action")
@click.option("--key", help="配置键")
@click.option("--value", help="配置值")
def config_command(action: str, key: str | None, value: str | None) -> None:
    """系统配置管理"""
    async def _config() -> None:
        try:
            if action in ["set", "get"] and key:
                if action == "set" and value:
                    command = f"/iccc config set {key} {value}"
                else:
                    command = f"/iccc config get {key}"
            else:
                command = f"/iccc config {action}"

            instruction = await process_instruction(command)

            click.echo(f"✅ 配置操作完成")
            click.echo(f"   操作: {action}")
            click.echo(f"   状态: {instruction.status.value}")

            if hasattr(instruction, 'result') and instruction.result:
                result = instruction.result
                if "config_values" in result:
                    click.echo(f"   配置值: {result['config_values']}")

        except Exception as e:
            click.echo(f"❌ 配置操作失败: {e}", err=True)
            sys.exit(1)

    asyncio.run(_config())


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


@cli.group()
def brain() -> None:
    """Manage the Brain agent (Spec-Driven Development)."""
    pass


@brain.command("cycle")
@click.option("--request", help="Optional user request/input")
def brain_cycle(request: str | None) -> None:
    """Run a Brain cognitive cycle (Think -> Spec -> Plan)."""
    from iccc.brain.engine import BrainEngine

    async def _run() -> None:
        try:
            # Assume running from current working directory which should be project root
            project_root = Path.cwd()
            
            click.echo(click.style("🧠 Brain is thinking...", fg="cyan"))
            engine = BrainEngine(project_root)
            await engine.run_cycle(user_request=request or "")
            
            click.echo(click.style("✅ Brain cycle completed successfully.", fg="green"))
            click.echo("Updated documents:")
            click.echo("  • IDEAS.md")
            click.echo("  • MAINTASK.md")
            
        except Exception as e:
            click.echo(click.style(f"❌ Brain cycle failed: {e}", fg="red"), err=True)
            sys.exit(1)

    asyncio.run(_run())


def main() -> None:
    """Entry point for the CLI."""
    cli()



if __name__ == "__main__":
    main()
