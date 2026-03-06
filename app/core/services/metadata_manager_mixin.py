"""
Metadata Manager Mixin
======================

Reusable mixin for services that need to manage entity metadata and timestamps.
Eliminates duplication of metadata handling logic across services.

DRY Principle:
- Standard metadata field setting
- Consistent timestamp management
- Source tracking (api, system, ingestion)
- Version management

Services Using This Mixin (as of January 2026):
- YamlIngestionService - Entity creation metadata
- MocContentService - update_properties() for MOC updates
- MocSectionService - timestamp_properties() + update_properties()
- MocCoreService - update_properties() for MOC metadata updates
- TranscriptionService - update_properties() for transcription updates
- ArticleCoreService - timestamp_properties(use_utc=True) for KU creation/updates

Usage:
    from core.services.metadata_manager_mixin import MetadataManagerMixin

    class TasksCoreService(BaseService, MetadataManagerMixin):
        async def create(self, task: Task, user_uid: str) -> Result[Task]:
            task = self.set_entity_metadata(task, user_uid=user_uid, source="api")
            return await self.backend.create(task)

    async def update(self, uid: str, updates: dict) -> Result[Task]:
        # Use mixin for update timestamp
        return await self.backend.update(uid, self.update_properties())

See Also:
    - CLAUDE.md: "MetadataManagerMixin - Consistent Timestamp & Metadata Handling"
"""

from typing import Any, TypeVar

from core.utils.timestamp_helpers import now_local, now_utc

T = TypeVar("T")


class MetadataManagerMixin:
    """
    Mixin providing standard metadata management for services.

    Handles:
    - Setting created_at/updated_at timestamps
    - Setting metadata dict with source, version, etc.
    - Updating timestamps on entity modifications
    - Building metadata dicts for various use cases
    """

    # ==========================================================================
    # ENTITY METADATA METHODS
    # ==========================================================================

    @staticmethod
    def set_entity_metadata(
        entity: T,
        user_uid: str | None = None,
        source: str = "api",
        version: int = 1,
        use_utc: bool = False,
        additional_metadata: dict[str, Any] | None = None,
    ) -> T:
        """
        Set standard metadata on a frozen dataclass entity.

        Sets created_at, updated_at, and metadata dict.

        Args:
            entity: Frozen dataclass entity to update
            user_uid: User who created/owns the entity (optional)
            source: Source of creation ("api", "system", "ingestion", etc.)
            version: Metadata version (default: 1)
            use_utc: Whether to use UTC timestamps (default: False)
            additional_metadata: Extra metadata fields to include

        Returns:
            Same entity with metadata set

        Example:
            task = self.set_entity_metadata(
                task,
                user_uid="user:123",
                source="api",
                additional_metadata={"imported_from": "csv"}
            )
        """
        current_time = now_utc() if use_utc else now_local()

        # Set timestamps
        if getattr(entity, "created_at", None) is None:
            object.__setattr__(entity, "created_at", current_time)
        object.__setattr__(entity, "updated_at", current_time)

        # Build metadata dict
        metadata = {
            "source": source,
            "version": version,
        }
        if user_uid:
            metadata["created_by"] = user_uid

        # Merge additional metadata
        if additional_metadata:
            metadata.update(additional_metadata)

        # Merge with existing metadata if present
        existing_metadata = getattr(entity, "metadata", None)
        if existing_metadata and isinstance(existing_metadata, dict):
            # Preserve existing, override with new
            merged = {**existing_metadata, **metadata}
            object.__setattr__(entity, "metadata", merged)
        else:
            object.__setattr__(entity, "metadata", metadata)

        return entity

    @staticmethod
    def update_entity_timestamp(entity: T, use_utc: bool = False) -> T:
        """
        Update the updated_at timestamp on a frozen dataclass entity.

        Args:
            entity: Frozen dataclass entity to update
            use_utc: Whether to use UTC timestamp (default: False)

        Returns:
            Same entity with updated_at refreshed

        Example:
            task = self.update_entity_timestamp(task)
        """
        current_time = now_utc() if use_utc else now_local()
        object.__setattr__(entity, "updated_at", current_time)
        return entity

    @staticmethod
    def set_entity_user(entity: T, user_uid: str) -> T:
        """
        Set the user_uid on a frozen dataclass entity.

        Args:
            entity: Frozen dataclass entity to update
            user_uid: User UID to set

        Returns:
            Same entity with user_uid set

        Example:
            task = self.set_entity_user(task, "user:123")
        """
        object.__setattr__(entity, "user_uid", user_uid)
        return entity

    # ==========================================================================
    # METADATA DICT BUILDERS
    # ==========================================================================

    @staticmethod
    def build_creation_metadata(
        user_uid: str | None = None,
        source: str = "api",
        version: int = 1,
        use_utc: bool = False,
        **extra: Any,
    ) -> dict[str, Any]:
        """
        Build a metadata dict for entity creation.

        Args:
            user_uid: User creating the entity (optional)
            source: Source of creation
            version: Metadata version
            use_utc: Whether to use UTC timestamp
            **extra: Additional metadata fields

        Returns:
            Metadata dict with standard fields

        Example:
            metadata = self.build_creation_metadata(
                user_uid="user:123",
                source="api",
                imported_from="csv"
            )
        """
        current_time = now_utc() if use_utc else now_local()

        metadata: dict[str, Any] = {
            "source": source,
            "version": version,
            "created_at_iso": current_time.isoformat(),
        }

        if user_uid:
            metadata["created_by"] = user_uid

        metadata.update(extra)
        return metadata

    @staticmethod
    def build_update_metadata(
        user_uid: str | None = None,
        reason: str | None = None,
        use_utc: bool = False,
        **extra: Any,
    ) -> dict[str, Any]:
        """
        Build a metadata dict for entity updates.

        Args:
            user_uid: User performing the update (optional)
            reason: Reason for update (optional)
            use_utc: Whether to use UTC timestamp
            **extra: Additional metadata fields

        Returns:
            Metadata dict for update operation

        Example:
            update_meta = self.build_update_metadata(
                user_uid="user:123",
                reason="Status change"
            )
        """
        current_time = now_utc() if use_utc else now_local()

        metadata: dict[str, Any] = {
            "updated_at_iso": current_time.isoformat(),
        }

        if user_uid:
            metadata["updated_by"] = user_uid

        if reason:
            metadata["update_reason"] = reason

        metadata.update(extra)
        return metadata

    @staticmethod
    def build_relationship_metadata(
        source: str = "explicit",
        confidence: float = 0.9,
        created_by: str | None = None,
        use_utc: bool = False,
        **extra: Any,
    ) -> dict[str, Any]:
        """
        Build metadata for graph relationships.

        Args:
            source: Source type ("explicit", "inferred", "system")
            confidence: Confidence score (0.0-1.0)
            created_by: User/service that created the relationship
            use_utc: Whether to use UTC timestamp
            **extra: Additional metadata fields

        Returns:
            Metadata dict for relationship

        Example:
            rel_meta = self.build_relationship_metadata(
                source="inferred",
                confidence=0.75,
                method="embedding_similarity"
            )
        """
        current_time = now_utc() if use_utc else now_local()

        metadata: dict[str, Any] = {
            "source": source,
            "confidence": confidence,
            "created_at": current_time.isoformat(),
        }

        if created_by:
            metadata["created_by"] = created_by

        metadata.update(extra)
        return metadata

    # ==========================================================================
    # AUDIT TRAIL HELPERS
    # ==========================================================================

    @staticmethod
    def build_audit_entry(
        action: str,
        entity_uid: str,
        user_uid: str | None = None,
        details: dict[str, Any] | None = None,
        use_utc: bool = False,
    ) -> dict[str, Any]:
        """
        Build an audit trail entry.

        Args:
            action: Action performed ("create", "update", "delete", etc.)
            entity_uid: UID of affected entity
            user_uid: User who performed action (optional)
            details: Additional details about the action
            use_utc: Whether to use UTC timestamp

        Returns:
            Audit entry dict

        Example:
            audit = self.build_audit_entry(
                action="status_change",
                entity_uid="task:123",
                user_uid="user:456",
                details={"old_status": "pending", "new_status": "completed"}
            )
        """
        current_time = now_utc() if use_utc else now_local()

        entry: dict[str, Any] = {
            "action": action,
            "entity_uid": entity_uid,
            "timestamp": current_time.isoformat(),
        }

        if user_uid:
            entry["user_uid"] = user_uid

        if details:
            entry["details"] = details

        return entry

    # ==========================================================================
    # VERSION MANAGEMENT
    # ==========================================================================

    @staticmethod
    def increment_version(entity: T) -> T:
        """
        Increment the version in entity metadata.

        Args:
            entity: Frozen dataclass entity with metadata

        Returns:
            Same entity with incremented version

        Example:
            task = self.increment_version(task)
        """
        metadata = getattr(entity, "metadata", None)
        if metadata and isinstance(metadata, dict):
            current_version = metadata.get("version", 1)
            new_metadata = {**metadata, "version": current_version + 1}
            object.__setattr__(entity, "metadata", new_metadata)
        return entity

    @staticmethod
    def get_version(entity: T) -> int:
        """
        Get the version from entity metadata.

        Args:
            entity: Entity to check

        Returns:
            Version number (default: 1)

        Example:
            version = self.get_version(task)
        """
        metadata = getattr(entity, "metadata", None)
        if metadata and isinstance(metadata, dict):
            return metadata.get("version", 1)
        return 1

    # ==========================================================================
    # TIMESTAMP PROPERTY DICT
    # ==========================================================================

    @staticmethod
    def timestamp_properties(use_utc: bool = False) -> dict[str, str]:
        """
        Create timestamp properties dict for Neo4j operations.

        Args:
            use_utc: Whether to use UTC timestamps

        Returns:
            Dict with created_at and updated_at ISO strings

        Example:
            props = {
                "uid": uid,
                "title": title,
                **self.timestamp_properties()
            }
        """
        current_time = now_utc() if use_utc else now_local()
        iso_str = current_time.isoformat()
        return {
            "created_at": iso_str,
            "updated_at": iso_str,
        }

    @staticmethod
    def update_properties(use_utc: bool = False) -> dict[str, str]:
        """
        Create update timestamp properties dict for Neo4j updates.

        Args:
            use_utc: Whether to use UTC timestamp

        Returns:
            Dict with updated_at ISO string

        Example:
            updates = {
                "title": new_title,
                **self.update_properties()
            }
        """
        current_time = now_utc() if use_utc else now_local()
        return {"updated_at": current_time.isoformat()}
