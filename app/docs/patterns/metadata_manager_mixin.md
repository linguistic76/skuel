---
title: MetadataManagerMixin - Consistent Timestamp & Metadata Handling
updated: 2026-01-20
status: current
category: patterns
tags: [manager, metadata, mixin, patterns]
related: []
---

# MetadataManagerMixin - Consistent Timestamp & Metadata Handling

*Last updated: 2026-01-20*

## Core Principle

> "DRY timestamp and metadata handling across all services"

SKUEL uses `MetadataManagerMixin` to eliminate duplicate timestamp/metadata handling code across services.

**Location:** `/core/services/metadata_manager_mixin.py`

## Key Methods

| Method | Purpose | Returns |
|--------|---------|---------|
| `timestamp_properties(use_utc=False)` | Create timestamps for entity creation | `{"created_at": iso, "updated_at": iso}` |
| `update_properties(use_utc=False)` | Create timestamp for updates | `{"updated_at": iso}` |
| `set_entity_metadata(entity, ...)` | Set metadata on frozen dataclass | Entity with metadata |
| `update_entity_timestamp(entity)` | Update only updated_at on entity | Entity with new timestamp |
| `set_entity_user(entity, user_uid)` | Set user_uid on entity | Entity with user set |
| `build_creation_metadata(...)` | Build metadata dict for creation | Metadata dict |
| `build_update_metadata(...)` | Build metadata dict for updates | Metadata dict |
| `build_relationship_metadata(...)` | Build metadata for graph edges | Metadata dict |
| `build_audit_entry(...)` | Build audit trail entry | Audit dict |
| `increment_version(entity)` | Increment version in metadata | Entity with incremented version |
| `get_version(entity)` | Get current version from metadata | int |

## Usage Patterns

### Pattern 1: Entity Creation with Timestamps

```python
from core.services.metadata_manager_mixin import MetadataManagerMixin

class MyService(MetadataManagerMixin):

    async def create(self, data: dict) -> Result[Entity]:
        # Use mixin for consistent timestamps
        timestamps = self.timestamp_properties(use_utc=True)
        entity_data = {
            "uid": uid,
            "title": data["title"],
            "created_at": timestamps["created_at"],
            "updated_at": timestamps["updated_at"],
        }
        return await self.backend.create(entity_data)
```

### Pattern 2: Entity Updates

```python
class MyService(MetadataManagerMixin):

    async def update(self, uid: str, updates: dict) -> Result[Entity]:
        # Use mixin for update timestamp
        update_result = await self.backend.update(uid, self.update_properties())
        return update_result
```

### Pattern 3: Setting Metadata on Frozen Dataclasses

```python
class MyService(MetadataManagerMixin):

    async def create(self, entity: Task, user_uid: str) -> Result[Task]:
        # Set metadata on frozen dataclass (uses object.__setattr__)
        entity = self.set_entity_metadata(
            entity,
            user_uid=user_uid,
            source="api",
            additional_metadata={"imported_from": "csv"}
        )
        return await self.backend.create(entity)
```

### Pattern 4: Building Relationship Metadata

```python
class MyService(MetadataManagerMixin):

    async def create_relationship(self, source_uid: str, target_uid: str) -> Result[None]:
        rel_metadata = self.build_relationship_metadata(
            source="inferred",
            confidence=0.85,
            created_by="system",
            method="embedding_similarity"
        )
        return await self.backend.create_edge(source_uid, target_uid, rel_metadata)
```

### Pattern 5: Audit Trail

```python
class MyService(MetadataManagerMixin):

    async def update_status(self, uid: str, new_status: str) -> Result[Entity]:
        # Build audit entry
        audit = self.build_audit_entry(
            action="status_change",
            entity_uid=uid,
            user_uid=user_uid,
            details={"old_status": old_status, "new_status": new_status}
        )
        # Store audit entry...
        return await self.backend.update(uid, {"status": new_status})
```

## Services Using MetadataManagerMixin

| Service | File | Usage |
|---------|------|-------|
| `YamlIngestionService` | `yaml_ingestion_service.py` | Entity creation metadata |
| `MocContentService` | `moc/moc_content_service.py` | `update_properties()` for MOC updates |
| `MocSectionService` | `moc/moc_section_service.py` | `timestamp_properties()` + `update_properties()` |
| `MocCoreService` | `moc/moc_core_service.py` | `update_properties()` for MOC metadata updates |
| `TranscriptionService` | `transcription/transcription_service.py` | `update_properties()` for transcription updates |
| `KuCoreService` | `ku/ku_core_service.py` | `timestamp_properties(use_utc=True)` for KU creation/updates |

## Method Details

### timestamp_properties()

Creates both `created_at` and `updated_at` timestamps as ISO strings.

```python
timestamps = self.timestamp_properties(use_utc=True)
# Returns: {"created_at": "2025-11-28T10:30:00+00:00", "updated_at": "2025-11-28T10:30:00+00:00"}
```

### update_properties()

Creates only `updated_at` timestamp for update operations.

```python
updates = self.update_properties()
# Returns: {"updated_at": "2025-11-28T10:30:00"}
```

### set_entity_metadata()

Sets metadata on frozen dataclasses using `object.__setattr__()`.

Parameters:
- `entity`: Frozen dataclass to modify
- `user_uid`: Optional user who created entity
- `source`: Source of creation ("api", "system", "ingestion")
- `version`: Metadata version (default: 1)
- `use_utc`: Use UTC timestamps
- `additional_metadata`: Extra fields to include

### build_relationship_metadata()

Creates metadata dict for Neo4j graph relationships.

Parameters:
- `source`: Source type ("explicit", "inferred", "system")
- `confidence`: Confidence score (0.0-1.0)
- `created_by`: User/service that created relationship
- `**extra`: Additional fields

## Benefits

1. **DRY** - No duplicate `datetime.now()` patterns across services
2. **Consistency** - Same timestamp format (ISO 8601) everywhere
3. **UTC Control** - `use_utc=True` for services needing UTC timestamps
4. **Versioning** - Built-in version increment/get support
5. **Audit Trail** - Standard `build_audit_entry()` method
6. **Frozen Dataclass Support** - Handles immutable entities correctly

## Migration Guide

### Before (Inline datetime handling)

```python
from datetime import datetime

class MyService:
    async def create(self, data: dict) -> Result[Entity]:
        entity_data = {
            "uid": uid,
            "title": data["title"],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        return await self.backend.create(entity_data)

    async def update(self, uid: str) -> Result[Entity]:
        updates = {"updated_at": datetime.now()}
        return await self.backend.update(uid, updates)
```

### After (Using MetadataManagerMixin)

```python
from core.services.metadata_manager_mixin import MetadataManagerMixin

class MyService(MetadataManagerMixin):
    async def create(self, data: dict) -> Result[Entity]:
        timestamps = self.timestamp_properties()
        entity_data = {
            "uid": uid,
            "title": data["title"],
            **timestamps,  # Spread operator for clean code
        }
        return await self.backend.create(entity_data)

    async def update(self, uid: str) -> Result[Entity]:
        return await self.backend.update(uid, self.update_properties())
```

## UTC vs Local Time

By default, methods use local time. Pass `use_utc=True` for UTC:

```python
# Local time (default)
self.timestamp_properties()  # Uses now_local()

# UTC time
self.timestamp_properties(use_utc=True)  # Uses now_utc()
```

**When to use UTC:**
- Knowledge units (KuCoreService) - Content may be accessed globally
- External API integrations
- Audit logs that may span timezones

**When to use local:**
- User-facing timestamps
- Calendar/scheduling features
- Local reports

## See Also

- Implementation: `/core/services/metadata_manager_mixin.py`
- Timestamp helpers: `/core/utils/timestamp_helpers.py`
- CLAUDE.md: Brief reference in main documentation
