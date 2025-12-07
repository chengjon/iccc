"""Database migration system for schema evolution."""

import asyncio
from datetime import datetime

from iccc.db.repositories import MongoDBClient


class Migration:
    """Base class for database migrations."""

    def __init__(self, version: str, description: str) -> None:
        self.version = version
        self.description = description
        self.applied_at: datetime | None = None

    async def up(self, db_client: MongoDBClient) -> None:
        """Apply the migration."""
        raise NotImplementedError

    async def down(self, db_client: MongoDBClient) -> None:
        """Rollback the migration."""
        raise NotImplementedError


class MigrationRunner:
    """Runs database migrations in order."""

    def __init__(self, db_client: MongoDBClient) -> None:
        self.db_client = db_client
        self.migrations: list[Migration] = []

    def register(self, migration: Migration) -> None:
        """Register a migration."""
        self.migrations.append(migration)

    async def get_applied_migrations(self) -> set[str]:
        """Get list of already applied migrations."""
        if not self.db_client.db:
            raise RuntimeError("Database not connected")

        migrations_col = self.db_client.db.migrations
        cursor = migrations_col.find({}, {"version": 1})
        docs = await cursor.to_list(length=None)
        return {doc["version"] for doc in docs}

    async def run_pending_migrations(self) -> list[str]:
        """Run all pending migrations."""
        if not self.db_client.db:
            raise RuntimeError("Database not connected")

        applied = await self.get_applied_migrations()
        pending = [m for m in self.migrations if m.version not in applied]

        # Sort by version
        pending.sort(key=lambda m: m.version)

        applied_versions = []
        for migration in pending:
            print(f"Running migration {migration.version}: {migration.description}")
            try:
                await migration.up(self.db_client)

                # Record migration
                await self.db_client.db.migrations.insert_one(
                    {
                        "version": migration.version,
                        "description": migration.description,
                        "applied_at": datetime.now().isoformat(),
                    }
                )
                applied_versions.append(migration.version)
                print(f"✓ Migration {migration.version} applied successfully")
            except Exception as e:
                print(f"✗ Migration {migration.version} failed: {e}")
                raise

        return applied_versions

    async def rollback_migration(self, version: str) -> None:
        """Rollback a specific migration."""
        if not self.db_client.db:
            raise RuntimeError("Database not connected")

        migration = next((m for m in self.migrations if m.version == version), None)
        if not migration:
            raise ValueError(f"Migration {version} not found")

        print(f"Rolling back migration {version}: {migration.description}")
        try:
            await migration.down(self.db_client)

            # Remove migration record
            await self.db_client.db.migrations.delete_one({"version": version})
            print(f"✓ Migration {version} rolled back successfully")
        except Exception as e:
            print(f"✗ Rollback of {version} failed: {e}")
            raise


# Built-in Migrations


class InitialSchemaMigration(Migration):
    """Initial database schema setup."""

    def __init__(self) -> None:
        super().__init__("001_initial_schema", "Create initial collections and indexes")

    async def up(self, db_client: MongoDBClient) -> None:
        """Create initial schema."""
        if not db_client.db:
            raise RuntimeError("Database not connected")

        db = db_client.db

        # This migration is handled by MongoDBClient._create_indexes()
        # Just ensure indexes are created
        await db_client._create_indexes()

    async def down(self, db_client: MongoDBClient) -> None:
        """Drop all collections."""
        if not db_client.db:
            raise RuntimeError("Database not connected")

        db = db_client.db

        # Drop collections
        await db.projects.drop()
        await db.agents.drop()
        await db.tasks.drop()
        await db.sessions.drop()
        await db.hook_events.drop()


class AddTaskComplexityMigration(Migration):
    """Add complexity field to existing tasks."""

    def __init__(self) -> None:
        super().__init__(
            "002_add_task_complexity", "Add complexity field to Task documents"
        )

    async def up(self, db_client: MongoDBClient) -> None:
        """Add complexity field to tasks that don't have it."""
        if not db_client.db:
            raise RuntimeError("Database not connected")

        db = db_client.db

        # Update tasks without complexity field
        result = await db.tasks.update_many(
            {"complexity": {"$exists": False}}, {"$set": {"complexity": None}}
        )

        print(f"  Updated {result.modified_count} tasks")

    async def down(self, db_client: MongoDBClient) -> None:
        """Remove complexity field from tasks."""
        if not db_client.db:
            raise RuntimeError("Database not connected")

        db = db_client.db

        # Remove complexity field
        await db.tasks.update_many({}, {"$unset": {"complexity": ""}})


class AddFilesModifiedToTaskMigration(Migration):
    """Add files_modified field to tasks."""

    def __init__(self) -> None:
        super().__init__(
            "003_add_files_modified", "Add files_modified field to Task documents"
        )

    async def up(self, db_client: MongoDBClient) -> None:
        """Add files_modified field."""
        if not db_client.db:
            raise RuntimeError("Database not connected")

        db = db_client.db

        # Update tasks without files_modified field
        result = await db.tasks.update_many(
            {"files_modified": {"$exists": False}}, {"$set": {"files_modified": []}}
        )

        print(f"  Updated {result.modified_count} tasks")

    async def down(self, db_client: MongoDBClient) -> None:
        """Remove files_modified field."""
        if not db_client.db:
            raise RuntimeError("Database not connected")

        db = db_client.db

        await db.tasks.update_many({}, {"$unset": {"files_modified": ""}})


class AddWorktreePathToAgentMigration(Migration):
    """Add worktree_path field to agents."""

    def __init__(self) -> None:
        super().__init__(
            "004_add_worktree_path", "Add worktree_path field to Agent documents"
        )

    async def up(self, db_client: MongoDBClient) -> None:
        """Add worktree_path field."""
        if not db_client.db:
            raise RuntimeError("Database not connected")

        db = db_client.db

        # Update agents without worktree_path field
        result = await db.agents.update_many(
            {"worktree_path": {"$exists": False}}, {"$set": {"worktree_path": None}}
        )

        print(f"  Updated {result.modified_count} agents")

    async def down(self, db_client: MongoDBClient) -> None:
        """Remove worktree_path field."""
        if not db_client.db:
            raise RuntimeError("Database not connected")

        db = db_client.db

        await db.agents.update_many({}, {"$unset": {"worktree_path": ""}})


class AddPromptTemplatesCollectionMigration(Migration):
    """Add prompt_templates collection for reusable prompts."""

    def __init__(self) -> None:
        super().__init__(
            "005_add_prompt_templates",
            "Create prompt_templates collection with indexes",
        )

    async def up(self, db_client: MongoDBClient) -> None:
        """Create prompt_templates collection with indexes."""
        if not db_client.db:
            raise RuntimeError("Database not connected")

        db = db_client.db

        # Create indexes for prompt_templates
        await db.prompt_templates.create_index("id", unique=True)
        await db.prompt_templates.create_index("name", unique=True)
        await db.prompt_templates.create_index("category")

        print("  Created prompt_templates collection with indexes")

    async def down(self, db_client: MongoDBClient) -> None:
        """Drop prompt_templates collection."""
        if not db_client.db:
            raise RuntimeError("Database not connected")

        await db_client.db.prompt_templates.drop()


class AddGoalsCollectionMigration(Migration):
    """Add goals collection for HTN planning system."""

    def __init__(self) -> None:
        super().__init__(
            "006_add_goals",
            "Create goals collection with indexes for planning system",
        )

    async def up(self, db_client: MongoDBClient) -> None:
        """Create goals collection with indexes."""
        if not db_client.db:
            raise RuntimeError("Database not connected")

        db = db_client.db

        # Create indexes for goals
        await db.goals.create_index("id", unique=True)
        await db.goals.create_index("project_id")
        await db.goals.create_index("status")
        await db.goals.create_index("priority")
        await db.goals.create_index("parent_goal_id")

        print("  Created goals collection with indexes")

    async def down(self, db_client: MongoDBClient) -> None:
        """Drop goals collection."""
        if not db_client.db:
            raise RuntimeError("Database not connected")

        await db_client.db.goals.drop()


def get_all_migrations() -> list[Migration]:
    """Get all registered migrations."""
    return [
        InitialSchemaMigration(),
        AddTaskComplexityMigration(),
        AddFilesModifiedToTaskMigration(),
        AddWorktreePathToAgentMigration(),
        AddPromptTemplatesCollectionMigration(),
        AddGoalsCollectionMigration(),
    ]


async def run_migrations(mongodb_url: str | None = None) -> None:
    """Run all pending migrations."""
    db_client = MongoDBClient(mongodb_url)
    await db_client.connect()

    try:
        runner = MigrationRunner(db_client)

        # Register all migrations
        for migration in get_all_migrations():
            runner.register(migration)

        # Run pending migrations
        applied = await runner.run_pending_migrations()

        if applied:
            print(f"\n✓ Applied {len(applied)} migration(s)")
        else:
            print("\n✓ All migrations up to date")

    finally:
        await db_client.disconnect()


async def rollback_last_migration(mongodb_url: str | None = None) -> None:
    """Rollback the last applied migration."""
    db_client = MongoDBClient(mongodb_url)
    await db_client.connect()

    try:
        runner = MigrationRunner(db_client)

        # Register all migrations
        for migration in get_all_migrations():
            runner.register(migration)

        # Get applied migrations
        applied = await runner.get_applied_migrations()

        if not applied:
            print("No migrations to rollback")
            return

        # Find latest migration
        latest_version = max(applied)

        # Rollback
        await runner.rollback_migration(latest_version)

    finally:
        await db_client.disconnect()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        asyncio.run(rollback_last_migration())
    else:
        asyncio.run(run_migrations())
