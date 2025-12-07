"""API Key authentication and management."""

import logging
import os
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from iccc.config import get_config

logger = logging.getLogger(__name__)


class APIKeyMetadata(BaseModel):
    """Metadata for an API key."""

    key_id: str = Field(..., description="Unique identifier for the key")
    name: str | None = Field(None, description="Human-readable name for the key")
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime | None = Field(None, description="Expiration timestamp")
    permissions: list[str] = Field(default_factory=list, description="Allowed permissions")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("key_id")
    @classmethod
    def validate_key_id(cls, v: str) -> str:
        """Validate key_id is not empty."""
        if not v or not v.strip():
            raise ValueError("key_id cannot be empty")
        return v.strip()

    def is_expired(self) -> bool:
        """Check if the key has expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def has_permission(self, permission: str) -> bool:
        """Check if key has a specific permission."""
        if not self.permissions:
            # No permissions means full access
            return True
        return permission in self.permissions

    def mask_for_logging(self) -> str:
        """Return masked key ID for safe logging."""
        if len(self.key_id) <= 8:
            return "****"
        return f"{self.key_id[:4]}****{self.key_id[-4:]}"


class APIKeyManager:
    """
    Manages API key authentication.

    Supports loading keys from:
    1. Environment variable (ICCC_API_KEYS - comma-separated)
    2. MongoDB database (optional)
    3. In-memory cache for performance
    """

    def __init__(
        self,
        mongodb_client: Any | None = None,
        load_from_env: bool = True,
    ) -> None:
        """
        Initialize API Key Manager.

        Args:
            mongodb_client: Optional MongoDBClient for database storage
            load_from_env: Whether to load keys from environment variables
        """
        self.mongodb_client = mongodb_client
        self._env_keys: set[str] = set()
        self._key_metadata: dict[str, APIKeyMetadata] = {}

        if load_from_env:
            self._load_from_env()

    def _load_from_env(self) -> None:
        """Load API keys from environment variable."""
        env_keys = os.getenv("ICCC_API_KEYS", "")

        if not env_keys:
            logger.warning(
                "ICCC_API_KEYS environment variable not set. "
                "API authentication may not work properly."
            )
            return

        # Parse comma-separated keys
        keys = [key.strip() for key in env_keys.split(",") if key.strip()]

        if not keys:
            logger.warning(
                "ICCC_API_KEYS environment variable is empty after parsing. "
                "API authentication may not work properly."
            )
            return

        self._env_keys = set(keys)

        # Create basic metadata for environment keys
        for key in keys:
            # Use first 8 chars as key_id for env keys (or full key if shorter)
            key_id = key[:8] if len(key) > 8 else key
            self._key_metadata[key] = APIKeyMetadata(
                key_id=key_id,
                name="Environment Key",
                permissions=[],  # Empty means full access
            )

        logger.info(
            f"Loaded {len(self._env_keys)} API keys from environment",
            extra={"key_count": len(self._env_keys)},
        )

    async def validate_key(self, api_key: str) -> tuple[bool, APIKeyMetadata | None]:
        """
        Validate an API key.

        Args:
            api_key: The API key to validate

        Returns:
            Tuple of (is_valid, metadata)
        """
        if not api_key or not api_key.strip():
            return False, None

        api_key = api_key.strip()

        # Check cache first (includes both env keys and DB keys)
        if api_key in self._key_metadata:
            metadata = self._key_metadata[api_key]
            if metadata.is_expired():
                logger.warning(
                    f"API key expired: {metadata.mask_for_logging()}",
                    extra={"key_id": metadata.key_id},
                )
                return False, None
            # For env keys, also check membership
            if api_key in self._env_keys or self.mongodb_client is not None:
                return True, metadata

        # Check database if available and not in cache
        if self.mongodb_client is not None:
            try:
                metadata = await self._validate_from_db(api_key)
                if metadata:
                    # Cache the key for future lookups
                    self._key_metadata[api_key] = metadata

                    if metadata.is_expired():
                        logger.warning(
                            f"API key expired: {metadata.mask_for_logging()}",
                            extra={"key_id": metadata.key_id},
                        )
                        return False, None

                    return True, metadata
            except Exception as e:
                # Log error but don't fail - degrade gracefully
                logger.error(
                    f"Database validation failed: {e}",
                    extra={"error": str(e)},
                    exc_info=True,
                )

        # Key not found
        return False, None

    async def _validate_from_db(self, api_key: str) -> APIKeyMetadata | None:
        """
        Validate API key against database.

        Args:
            api_key: The API key to validate

        Returns:
            APIKeyMetadata if valid, None otherwise
        """
        if self.mongodb_client is None or self.mongodb_client.db is None:
            return None

        try:
            # Look up key in api_keys collection
            doc = await self.mongodb_client.db.api_keys.find_one(
                {"key": api_key, "active": True}
            )

            if not doc:
                return None

            # Parse metadata
            return APIKeyMetadata(
                key_id=doc.get("key_id", doc.get("_id", "unknown")),
                name=doc.get("name"),
                created_at=doc.get("created_at", datetime.now()),
                expires_at=doc.get("expires_at"),
                permissions=doc.get("permissions", []),
                metadata=doc.get("metadata", {}),
            )
        except Exception as e:
            logger.error(
                f"Error validating key from database: {e}",
                exc_info=True,
            )
            return None

    async def create_key(
        self,
        api_key: str,
        key_id: str,
        name: str | None = None,
        expires_at: datetime | None = None,
        permissions: list[str] | None = None,
    ) -> APIKeyMetadata:
        """
        Create a new API key in the database.

        Args:
            api_key: The actual API key value
            key_id: Unique identifier for the key
            name: Human-readable name
            expires_at: Optional expiration timestamp
            permissions: Optional list of permissions

        Returns:
            APIKeyMetadata for the created key

        Raises:
            RuntimeError: If database is not available
        """
        if self.mongodb_client is None or self.mongodb_client.db is None:
            raise RuntimeError("Database not available for key creation")

        metadata = APIKeyMetadata(
            key_id=key_id,
            name=name,
            created_at=datetime.now(),
            expires_at=expires_at,
            permissions=permissions or [],
        )

        # Store in database
        await self.mongodb_client.db.api_keys.insert_one(
            {
                "key_id": metadata.key_id,
                "key": api_key,
                "name": metadata.name,
                "created_at": metadata.created_at,
                "expires_at": metadata.expires_at,
                "permissions": metadata.permissions,
                "metadata": metadata.metadata,
                "active": True,
            }
        )

        # Cache it
        self._key_metadata[api_key] = metadata

        logger.info(
            f"Created new API key: {metadata.mask_for_logging()}",
            extra={"key_id": metadata.key_id},
        )

        return metadata

    async def revoke_key(self, api_key: str) -> bool:
        """
        Revoke an API key.

        Args:
            api_key: The API key to revoke

        Returns:
            True if revoked, False if not found
        """
        # Remove from environment cache
        if api_key in self._env_keys:
            logger.warning(
                "Cannot revoke environment-based API key. "
                "Remove from ICCC_API_KEYS environment variable instead."
            )
            return False

        # Remove from memory cache
        self._key_metadata.pop(api_key, None)

        # Mark as inactive in database
        if self.mongodb_client is not None and self.mongodb_client.db is not None:
            result = await self.mongodb_client.db.api_keys.update_one(
                {"key": api_key}, {"$set": {"active": False}}
            )
            return result.modified_count > 0

        return False

    def get_cached_metadata(self, api_key: str) -> APIKeyMetadata | None:
        """
        Get cached metadata for an API key.

        Args:
            api_key: The API key

        Returns:
            APIKeyMetadata if cached, None otherwise
        """
        return self._key_metadata.get(api_key)

    def clear_cache(self) -> None:
        """Clear the in-memory key cache (except environment keys)."""
        # Keep environment keys, clear everything else
        env_metadata = {k: v for k, v in self._key_metadata.items() if k in self._env_keys}
        self._key_metadata = env_metadata
        logger.info("Cleared API key cache")
