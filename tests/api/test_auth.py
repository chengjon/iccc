"""Tests for API authentication system."""

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from iccc.api.auth import APIKeyManager, APIKeyMetadata


class TestAPIKeyMetadata:
    """Tests for APIKeyMetadata model."""

    def test_create_basic_metadata(self):
        """Test creating basic metadata."""
        metadata = APIKeyMetadata(key_id="test-key-001")
        assert metadata.key_id == "test-key-001"
        assert metadata.name is None
        assert metadata.expires_at is None
        assert metadata.permissions == []
        assert not metadata.is_expired()

    def test_create_with_all_fields(self):
        """Test creating metadata with all fields."""
        expires = datetime.now() + timedelta(days=30)
        metadata = APIKeyMetadata(
            key_id="test-key-002",
            name="Test Key",
            expires_at=expires,
            permissions=["read", "write"],
            metadata={"owner": "admin"},
        )
        assert metadata.key_id == "test-key-002"
        assert metadata.name == "Test Key"
        assert metadata.expires_at == expires
        assert metadata.permissions == ["read", "write"]
        assert metadata.metadata == {"owner": "admin"}

    def test_is_expired_future(self):
        """Test is_expired with future expiration."""
        metadata = APIKeyMetadata(
            key_id="test-key-003",
            expires_at=datetime.now() + timedelta(days=1),
        )
        assert not metadata.is_expired()

    def test_is_expired_past(self):
        """Test is_expired with past expiration."""
        metadata = APIKeyMetadata(
            key_id="test-key-004",
            expires_at=datetime.now() - timedelta(days=1),
        )
        assert metadata.is_expired()

    def test_has_permission_empty_list(self):
        """Test has_permission with empty permissions (full access)."""
        metadata = APIKeyMetadata(key_id="test-key-005", permissions=[])
        assert metadata.has_permission("read")
        assert metadata.has_permission("write")
        assert metadata.has_permission("delete")

    def test_has_permission_specific(self):
        """Test has_permission with specific permissions."""
        metadata = APIKeyMetadata(
            key_id="test-key-006",
            permissions=["read", "write"],
        )
        assert metadata.has_permission("read")
        assert metadata.has_permission("write")
        assert not metadata.has_permission("delete")

    def test_mask_for_logging_short_key(self):
        """Test masking short key IDs."""
        metadata = APIKeyMetadata(key_id="short")
        assert metadata.mask_for_logging() == "****"

    def test_mask_for_logging_long_key(self):
        """Test masking long key IDs."""
        metadata = APIKeyMetadata(key_id="abcdef1234567890")
        masked = metadata.mask_for_logging()
        assert masked.startswith("abcd")
        assert masked.endswith("7890")
        assert "****" in masked

    def test_validate_key_id_empty(self):
        """Test validation rejects empty key_id."""
        with pytest.raises(ValueError, match="key_id cannot be empty"):
            APIKeyMetadata(key_id="")

    def test_validate_key_id_whitespace(self):
        """Test validation rejects whitespace-only key_id."""
        with pytest.raises(ValueError, match="key_id cannot be empty"):
            APIKeyMetadata(key_id="   ")


class TestAPIKeyManager:
    """Tests for APIKeyManager."""

    @pytest.fixture(autouse=True)
    def clear_env(self):
        """Clear ICCC_API_KEYS from environment before each test."""
        original = os.environ.get("ICCC_API_KEYS")
        if "ICCC_API_KEYS" in os.environ:
            del os.environ["ICCC_API_KEYS"]
        yield
        # Restore original value
        if original:
            os.environ["ICCC_API_KEYS"] = original
        elif "ICCC_API_KEYS" in os.environ:
            del os.environ["ICCC_API_KEYS"]

    def test_init_without_env(self):
        """Test initialization without environment variable."""
        manager = APIKeyManager(load_from_env=True)
        assert len(manager._env_keys) == 0

    def test_init_with_env_single_key(self):
        """Test initialization with single key in environment."""
        os.environ["ICCC_API_KEYS"] = "test-key-001"
        manager = APIKeyManager(load_from_env=True)
        assert "test-key-001" in manager._env_keys
        assert len(manager._env_keys) == 1

    def test_init_with_env_multiple_keys(self):
        """Test initialization with multiple keys in environment."""
        os.environ["ICCC_API_KEYS"] = "key1,key2,key3"
        manager = APIKeyManager(load_from_env=True)
        assert "key1" in manager._env_keys
        assert "key2" in manager._env_keys
        assert "key3" in manager._env_keys
        assert len(manager._env_keys) == 3

    def test_init_with_env_whitespace(self):
        """Test initialization handles whitespace properly."""
        os.environ["ICCC_API_KEYS"] = " key1 , key2 ,  key3  "
        manager = APIKeyManager(load_from_env=True)
        assert "key1" in manager._env_keys
        assert "key2" in manager._env_keys
        assert "key3" in manager._env_keys
        assert " key1 " not in manager._env_keys

    def test_init_with_env_empty_entries(self):
        """Test initialization ignores empty entries."""
        os.environ["ICCC_API_KEYS"] = "key1,,key2,,,key3"
        manager = APIKeyManager(load_from_env=True)
        assert len(manager._env_keys) == 3
        assert "" not in manager._env_keys

    @pytest.mark.asyncio
    async def test_validate_key_empty(self):
        """Test validation of empty key."""
        manager = APIKeyManager(load_from_env=False)
        is_valid, metadata = await manager.validate_key("")
        assert not is_valid
        assert metadata is None

    @pytest.mark.asyncio
    async def test_validate_key_whitespace(self):
        """Test validation of whitespace-only key."""
        manager = APIKeyManager(load_from_env=False)
        is_valid, metadata = await manager.validate_key("   ")
        assert not is_valid
        assert metadata is None

    @pytest.mark.asyncio
    async def test_validate_key_from_env_valid(self):
        """Test validation of valid environment key."""
        os.environ["ICCC_API_KEYS"] = "valid-key-001"
        manager = APIKeyManager(load_from_env=True)
        is_valid, metadata = await manager.validate_key("valid-key-001")
        assert is_valid
        assert metadata is not None
        assert metadata.key_id == "valid-ke"  # First 8 chars

    @pytest.mark.asyncio
    async def test_validate_key_from_env_invalid(self):
        """Test validation of invalid key."""
        os.environ["ICCC_API_KEYS"] = "valid-key-001"
        manager = APIKeyManager(load_from_env=True)
        is_valid, metadata = await manager.validate_key("invalid-key")
        assert not is_valid
        assert metadata is None

    @pytest.mark.asyncio
    async def test_validate_key_expired(self):
        """Test validation rejects expired keys."""
        os.environ["ICCC_API_KEYS"] = "expired-key"
        manager = APIKeyManager(load_from_env=True)

        # Manually set expiration to past
        manager._key_metadata["expired-key"].expires_at = datetime.now() - timedelta(days=1)

        is_valid, metadata = await manager.validate_key("expired-key")
        assert not is_valid
        assert metadata is None

    @pytest.mark.asyncio
    async def test_validate_key_from_database_valid(self):
        """Test validation from database with valid key."""
        # Mock MongoDB client
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.api_keys = mock_collection

        # Mock find_one to return a valid key
        mock_collection.find_one = AsyncMock(
            return_value={
                "key_id": "db-key-001",
                "key": "database-key-001",
                "name": "Database Key",
                "created_at": datetime.now(),
                "expires_at": None,
                "permissions": ["read"],
                "metadata": {},
                "active": True,
            }
        )

        mock_client = MagicMock()
        mock_client.db = mock_db

        manager = APIKeyManager(mongodb_client=mock_client, load_from_env=False)
        is_valid, metadata = await manager.validate_key("database-key-001")

        assert is_valid
        assert metadata is not None
        assert metadata.key_id == "db-key-001"
        assert metadata.name == "Database Key"
        assert metadata.permissions == ["read"]

    @pytest.mark.asyncio
    async def test_validate_key_from_database_not_found(self):
        """Test validation from database with non-existent key."""
        # Mock MongoDB client
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.api_keys = mock_collection
        mock_collection.find_one = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.db = mock_db

        manager = APIKeyManager(mongodb_client=mock_client, load_from_env=False)
        is_valid, metadata = await manager.validate_key("nonexistent-key")

        assert not is_valid
        assert metadata is None

    @pytest.mark.asyncio
    async def test_validate_key_database_error_graceful_degradation(self):
        """Test that database errors don't crash validation."""
        # Mock MongoDB client that raises exception
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.api_keys = mock_collection
        mock_collection.find_one = AsyncMock(side_effect=Exception("Database error"))

        mock_client = MagicMock()
        mock_client.db = mock_db

        manager = APIKeyManager(mongodb_client=mock_client, load_from_env=False)
        is_valid, metadata = await manager.validate_key("test-key")

        # Should not raise, should return invalid
        assert not is_valid
        assert metadata is None

    @pytest.mark.asyncio
    async def test_validate_key_caches_database_results(self):
        """Test that database results are cached."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.api_keys = mock_collection
        mock_collection.find_one = AsyncMock(
            return_value={
                "key_id": "cached-key",
                "key": "cache-test-key",
                "name": "Cached Key",
                "created_at": datetime.now(),
                "expires_at": None,
                "permissions": [],
                "metadata": {},
                "active": True,
            }
        )

        mock_client = MagicMock()
        mock_client.db = mock_db

        manager = APIKeyManager(mongodb_client=mock_client, load_from_env=False)

        # First validation - should hit database
        is_valid1, metadata1 = await manager.validate_key("cache-test-key")
        assert is_valid1
        assert mock_collection.find_one.call_count == 1

        # Second validation - should use cache
        is_valid2, metadata2 = await manager.validate_key("cache-test-key")
        assert is_valid2
        # Should still only have called database once
        assert mock_collection.find_one.call_count == 1

    @pytest.mark.asyncio
    async def test_create_key(self):
        """Test creating a new API key."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.api_keys = mock_collection
        mock_collection.insert_one = AsyncMock()

        mock_client = MagicMock()
        mock_client.db = mock_db

        manager = APIKeyManager(mongodb_client=mock_client, load_from_env=False)

        metadata = await manager.create_key(
            api_key="new-key-001",
            key_id="new-001",
            name="New Key",
            permissions=["read", "write"],
        )

        assert metadata.key_id == "new-001"
        assert metadata.name == "New Key"
        assert metadata.permissions == ["read", "write"]
        assert mock_collection.insert_one.called

    @pytest.mark.asyncio
    async def test_create_key_without_database(self):
        """Test creating key without database raises error."""
        manager = APIKeyManager(load_from_env=False)

        with pytest.raises(RuntimeError, match="Database not available"):
            await manager.create_key("key", "key-id")

    @pytest.mark.asyncio
    async def test_revoke_key_env_key_fails(self):
        """Test revoking environment key is not allowed."""
        os.environ["ICCC_API_KEYS"] = "env-key-001"
        manager = APIKeyManager(load_from_env=True)

        result = await manager.revoke_key("env-key-001")
        assert not result
        # Key should still be valid
        is_valid, _ = await manager.validate_key("env-key-001")
        assert is_valid

    @pytest.mark.asyncio
    async def test_revoke_key_database_key(self):
        """Test revoking database key."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.api_keys = mock_collection

        # Mock update_one to return modified count
        mock_result = MagicMock()
        mock_result.modified_count = 1
        mock_collection.update_one = AsyncMock(return_value=mock_result)

        mock_client = MagicMock()
        mock_client.db = mock_db

        manager = APIKeyManager(mongodb_client=mock_client, load_from_env=False)

        # Add key to cache first
        manager._key_metadata["db-key-001"] = APIKeyMetadata(key_id="db-001")

        result = await manager.revoke_key("db-key-001")
        assert result
        assert "db-key-001" not in manager._key_metadata
        assert mock_collection.update_one.called

    def test_get_cached_metadata(self):
        """Test retrieving cached metadata."""
        os.environ["ICCC_API_KEYS"] = "cached-key"
        manager = APIKeyManager(load_from_env=True)

        metadata = manager.get_cached_metadata("cached-key")
        assert metadata is not None
        assert metadata.key_id == "cached-k"  # First 8 chars

    def test_get_cached_metadata_not_found(self):
        """Test retrieving non-existent cached metadata."""
        manager = APIKeyManager(load_from_env=False)
        metadata = manager.get_cached_metadata("nonexistent")
        assert metadata is None

    def test_clear_cache(self):
        """Test clearing cache keeps environment keys."""
        os.environ["ICCC_API_KEYS"] = "env-key"
        manager = APIKeyManager(load_from_env=True)

        # Add a non-env key to cache
        manager._key_metadata["other-key"] = APIKeyMetadata(key_id="other")

        assert len(manager._key_metadata) == 2

        manager.clear_cache()

        # Environment key should remain
        assert "env-key" in manager._key_metadata
        # Other key should be removed
        assert "other-key" not in manager._key_metadata
        assert len(manager._key_metadata) == 1
