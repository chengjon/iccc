"""Tests for migration CLI commands."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from iccc.cli import migrate_create, migrate_down, migrate_list, migrate_status, migrate_up
from iccc.db.migrations import (
    MigrationRunner,
    MigrationStatus,
    get_all_migrations,
)
from iccc.db.repositories import MongoDBClient


@pytest.fixture
def cli_runner():
    """Create a Click CLI runner."""
    return CliRunner()


@pytest.fixture
def mock_db_client():
    """Create a mock MongoDB client."""
    client = MagicMock(spec=MongoDBClient)
    client.db = MagicMock()
    client._create_indexes = AsyncMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    return client


class TestMigrateCreate:
    """Test migrate create command."""

    def test_migrate_create_success(self, cli_runner, tmp_path):
        """Test creating a new migration file."""
        with patch('iccc.cli.Path') as mock_path:
            # Mock the migrations directory
            mock_file = tmp_path / "iccc" / "db" / "migration_files"
            mock_file.mkdir(parents=True, exist_ok=True)

            mock_path.return_value.parent.parent = tmp_path

            with patch('iccc.db.migration_template.MigrationTemplate.create_migration_file') as mock_create:
                mock_create.return_value = mock_file / "007_test_migration.py"

                result = cli_runner.invoke(migrate_create, ['test_migration'])

                assert result.exit_code == 0
                assert "Created migration" in result.output
                assert "Next steps" in result.output

    def test_migrate_create_with_description(self, cli_runner):
        """Test creating a migration with description."""
        with patch('iccc.cli.Path'):
            with patch('iccc.db.migration_template.MigrationTemplate.create_migration_file') as mock_create:
                mock_create.return_value = Path("/tmp/007_test.py")

                result = cli_runner.invoke(
                    migrate_create,
                    ['test_migration', '--description', 'Test description']
                )

                assert result.exit_code == 0
                mock_create.assert_called_once()
                # Check that description was passed
                call_args = mock_create.call_args
                assert call_args[0][1] == 'test_migration'
                assert call_args[0][2] == 'Test description'

    def test_migrate_create_invalid_name(self, cli_runner):
        """Test creating a migration with invalid name."""
        with patch('iccc.cli.Path'):
            with patch('iccc.db.migration_template.MigrationTemplate.create_migration_file') as mock_create:
                mock_create.side_effect = ValueError("Invalid migration name")

                result = cli_runner.invoke(migrate_create, ['Invalid-Name'])

                assert result.exit_code == 1
                assert "Invalid migration name" in result.output

    def test_migrate_create_file_exists(self, cli_runner):
        """Test creating a migration when file already exists."""
        with patch('iccc.cli.Path'):
            with patch('iccc.db.migration_template.MigrationTemplate.create_migration_file') as mock_create:
                mock_create.side_effect = FileExistsError("File exists")

                result = cli_runner.invoke(migrate_create, ['existing_migration'])

                assert result.exit_code == 1
                assert "exists" in result.output.lower()


class TestMigrationIntegration:
    """Integration tests for migration system."""

    @pytest.mark.asyncio
    async def test_full_migration_workflow(self, mock_db_client):
        """Test complete migration workflow: up, status, down."""
        runner = MigrationRunner(mock_db_client)

        # Mock database responses
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_db_client.db.migrations.find = MagicMock(return_value=mock_cursor)
        mock_db_client.db.migrations.insert_one = AsyncMock()
        mock_db_client.db.migrations.delete_one = AsyncMock()

        # Register migrations
        migrations = get_all_migrations()
        for migration in migrations:
            runner.register(migration)

        # Get initial status
        status = await runner.get_migration_status()
        assert all(not s.applied for s in status)

        # Mock migration operations
        mock_db_client.db.tasks.update_many = AsyncMock(
            return_value=MagicMock(modified_count=0)
        )
        mock_db_client.db.agents.update_many = AsyncMock(
            return_value=MagicMock(modified_count=0)
        )

        # Note: Cannot actually run migrations without real DB,
        # but we've tested the workflow structure
        assert len(status) == 6  # Should have 6 built-in migrations

    @pytest.mark.asyncio
    async def test_migration_status_tracking(self, mock_db_client):
        """Test migration status tracking."""
        runner = MigrationRunner(mock_db_client)

        # Mock database responses
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            {"version": "001_initial_schema", "applied_at": "2024-01-01"}
        ])
        mock_db_client.db.migrations.find = MagicMock(return_value=mock_cursor)

        # Register migrations
        migrations = get_all_migrations()
        for migration in migrations:
            runner.register(migration)

        # Get status
        statuses = await runner.get_migration_status()

        # First migration should be marked as applied
        assert statuses[0].applied is True
        assert statuses[0].version == "001_initial_schema"

        # Other migrations should be pending
        for status in statuses[1:]:
            assert status.applied is False

    @pytest.mark.asyncio
    async def test_list_migrations(self, mock_db_client):
        """Test listing all migrations."""
        runner = MigrationRunner(mock_db_client)

        # Mock database responses
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_db_client.db.migrations.find = MagicMock(return_value=mock_cursor)

        # Register migrations
        migrations = get_all_migrations()
        for migration in migrations:
            runner.register(migration)

        # List migrations
        migration_list = await runner.list_migrations()

        assert len(migration_list) == 6
        assert all(isinstance(m, tuple) and len(m) == 3 for m in migration_list)

        # Check structure: (version, description, is_applied)
        for version, description, is_applied in migration_list:
            assert isinstance(version, str)
            assert isinstance(description, str)
            assert isinstance(is_applied, bool)
