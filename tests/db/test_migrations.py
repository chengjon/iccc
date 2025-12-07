"""Tests for database migration system."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from iccc.db.migrations import (
    AddFilesModifiedToTaskMigration,
    AddTaskComplexityMigration,
    AddWorktreePathToAgentMigration,
    InitialSchemaMigration,
    MigrationRunner,
    get_all_migrations,
)
from iccc.db.repositories import MongoDBClient


@pytest.fixture
def mock_db_client():
    """Create a mock MongoDB client."""
    client = MagicMock(spec=MongoDBClient)
    client.db = MagicMock()
    client._create_indexes = AsyncMock()
    return client


class TestMigrationRunner:
    """Test MigrationRunner functionality."""

    @pytest.mark.asyncio
    async def test_register_migration(self, mock_db_client):
        """Test registering a migration."""
        runner = MigrationRunner(mock_db_client)
        migration = InitialSchemaMigration()

        runner.register(migration)

        assert len(runner.migrations) == 1
        assert runner.migrations[0] == migration

    @pytest.mark.asyncio
    async def test_get_applied_migrations_empty(self, mock_db_client):
        """Test getting applied migrations when none exist."""
        runner = MigrationRunner(mock_db_client)

        # Mock empty migrations collection
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_db_client.db.migrations.find = MagicMock(return_value=mock_cursor)

        applied = await runner.get_applied_migrations()

        assert applied == set()

    @pytest.mark.asyncio
    async def test_get_applied_migrations(self, mock_db_client):
        """Test getting applied migrations."""
        runner = MigrationRunner(mock_db_client)

        # Mock migrations collection with some entries
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {"version": "001_initial_schema"},
                {"version": "002_add_task_complexity"},
            ]
        )
        mock_db_client.db.migrations.find = MagicMock(return_value=mock_cursor)

        applied = await runner.get_applied_migrations()

        assert applied == {"001_initial_schema", "002_add_task_complexity"}

    @pytest.mark.asyncio
    async def test_run_pending_migrations(self, mock_db_client):
        """Test running pending migrations."""
        runner = MigrationRunner(mock_db_client)

        # Register migrations
        migration1 = InitialSchemaMigration()
        migration2 = AddTaskComplexityMigration()
        runner.register(migration1)
        runner.register(migration2)

        # Mock no applied migrations
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_db_client.db.migrations.find = MagicMock(return_value=mock_cursor)

        # Mock insert_one for recording migrations
        mock_db_client.db.migrations.insert_one = AsyncMock()

        # Mock update_many for AddTaskComplexityMigration
        mock_result = MagicMock()
        mock_result.modified_count = 0
        mock_db_client.db.tasks.update_many = AsyncMock(return_value=mock_result)

        # Run migrations
        applied = await runner.run_pending_migrations()

        assert len(applied) == 2
        assert "001_initial_schema" in applied
        assert "002_add_task_complexity" in applied

        # Verify migrations were recorded
        assert mock_db_client.db.migrations.insert_one.call_count == 2

    @pytest.mark.asyncio
    async def test_run_pending_migrations_skips_applied(self, mock_db_client):
        """Test that already applied migrations are skipped."""
        runner = MigrationRunner(mock_db_client)

        # Register migrations
        migration1 = InitialSchemaMigration()
        migration2 = AddTaskComplexityMigration()
        runner.register(migration1)
        runner.register(migration2)

        # Mock that first migration is already applied
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[{"version": "001_initial_schema"}]
        )
        mock_db_client.db.migrations.find = MagicMock(return_value=mock_cursor)

        # Mock insert_one for recording migrations
        mock_db_client.db.migrations.insert_one = AsyncMock()

        # Mock update_many for AddTaskComplexityMigration
        mock_result = MagicMock()
        mock_result.modified_count = 0
        mock_db_client.db.tasks.update_many = AsyncMock(return_value=mock_result)

        # Run migrations
        applied = await runner.run_pending_migrations()

        # Only second migration should be applied
        assert len(applied) == 1
        assert "002_add_task_complexity" in applied
        assert mock_db_client.db.migrations.insert_one.call_count == 1

    @pytest.mark.asyncio
    async def test_rollback_migration(self, mock_db_client):
        """Test rolling back a migration."""
        runner = MigrationRunner(mock_db_client)

        # Register migration
        migration = InitialSchemaMigration()
        runner.register(migration)

        # Mock delete_one
        mock_db_client.db.migrations.delete_one = AsyncMock()

        # Mock down method
        migration.down = AsyncMock()

        # Rollback
        await runner.rollback_migration("001_initial_schema")

        # Verify down was called and record was deleted
        migration.down.assert_called_once()
        mock_db_client.db.migrations.delete_one.assert_called_once_with(
            {"version": "001_initial_schema"}
        )


class TestInitialSchemaMigration:
    """Test initial schema migration."""

    @pytest.mark.asyncio
    async def test_up(self, mock_db_client):
        """Test applying initial schema migration."""
        migration = InitialSchemaMigration()

        await migration.up(mock_db_client)

        # Verify indexes were created
        mock_db_client._create_indexes.assert_called_once()

    @pytest.mark.asyncio
    async def test_down(self, mock_db_client):
        """Test rolling back initial schema migration."""
        migration = InitialSchemaMigration()

        # Mock drop methods
        mock_db_client.db.projects.drop = AsyncMock()
        mock_db_client.db.agents.drop = AsyncMock()
        mock_db_client.db.tasks.drop = AsyncMock()
        mock_db_client.db.sessions.drop = AsyncMock()
        mock_db_client.db.hook_events.drop = AsyncMock()

        await migration.down(mock_db_client)

        # Verify all collections were dropped
        mock_db_client.db.projects.drop.assert_called_once()
        mock_db_client.db.agents.drop.assert_called_once()
        mock_db_client.db.tasks.drop.assert_called_once()
        mock_db_client.db.sessions.drop.assert_called_once()
        mock_db_client.db.hook_events.drop.assert_called_once()


class TestAddTaskComplexityMigration:
    """Test task complexity field migration."""

    @pytest.mark.asyncio
    async def test_up(self, mock_db_client):
        """Test adding complexity field to tasks."""
        migration = AddTaskComplexityMigration()

        # Mock update_many result
        mock_result = MagicMock()
        mock_result.modified_count = 5
        mock_db_client.db.tasks.update_many = AsyncMock(return_value=mock_result)

        await migration.up(mock_db_client)

        # Verify update was called
        mock_db_client.db.tasks.update_many.assert_called_once_with(
            {"complexity": {"$exists": False}}, {"$set": {"complexity": None}}
        )

    @pytest.mark.asyncio
    async def test_down(self, mock_db_client):
        """Test removing complexity field from tasks."""
        migration = AddTaskComplexityMigration()

        mock_db_client.db.tasks.update_many = AsyncMock()

        await migration.down(mock_db_client)

        # Verify update was called
        mock_db_client.db.tasks.update_many.assert_called_once_with(
            {}, {"$unset": {"complexity": ""}}
        )


class TestAddFilesModifiedToTaskMigration:
    """Test files_modified field migration."""

    @pytest.mark.asyncio
    async def test_up(self, mock_db_client):
        """Test adding files_modified field to tasks."""
        migration = AddFilesModifiedToTaskMigration()

        # Mock update_many result
        mock_result = MagicMock()
        mock_result.modified_count = 3
        mock_db_client.db.tasks.update_many = AsyncMock(return_value=mock_result)

        await migration.up(mock_db_client)

        # Verify update was called
        mock_db_client.db.tasks.update_many.assert_called_once_with(
            {"files_modified": {"$exists": False}}, {"$set": {"files_modified": []}}
        )


class TestAddWorktreePathToAgentMigration:
    """Test worktree_path field migration."""

    @pytest.mark.asyncio
    async def test_up(self, mock_db_client):
        """Test adding worktree_path field to agents."""
        migration = AddWorktreePathToAgentMigration()

        # Mock update_many result
        mock_result = MagicMock()
        mock_result.modified_count = 2
        mock_db_client.db.agents.update_many = AsyncMock(return_value=mock_result)

        await migration.up(mock_db_client)

        # Verify update was called
        mock_db_client.db.agents.update_many.assert_called_once_with(
            {"worktree_path": {"$exists": False}}, {"$set": {"worktree_path": None}}
        )


def test_get_all_migrations():
    """Test getting all registered migrations."""
    from iccc.db.migrations import (
        AddGoalsCollectionMigration,
        AddPromptTemplatesCollectionMigration,
    )

    migrations = get_all_migrations()

    assert len(migrations) == 6
    assert isinstance(migrations[0], InitialSchemaMigration)
    assert isinstance(migrations[1], AddTaskComplexityMigration)
    assert isinstance(migrations[2], AddFilesModifiedToTaskMigration)
    assert isinstance(migrations[3], AddWorktreePathToAgentMigration)
    assert isinstance(migrations[4], AddPromptTemplatesCollectionMigration)
    assert isinstance(migrations[5], AddGoalsCollectionMigration)
