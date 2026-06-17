---
title: EntityTimestampMixin - Timestamp Property-Dict Helpers
updated: 2026-06-17
category: patterns
related_skills: []
related_docs: []
---

# EntityTimestampMixin — Timestamp Property-Dict Helpers

*Last updated: 2026-06-17*

## Overview

`EntityTimestampMixin` provides two static helpers that produce Neo4j property
dicts for timestamp fields.  The MOC service cluster that previously used the
broader metadata-building API was removed in bloat campaign 18; only
`update_properties()` survives with a live caller.

**Location:** `/core/services/entity_timestamp_mixin.py`

## Methods

| Method | Purpose | Returns |
|--------|---------|---------|
| `update_properties(use_utc=False)` | Timestamp dict for Neo4j updates | `{"updated_at": iso}` |
| `timestamp_properties(use_utc=False)` | Timestamp dict for Neo4j creation | `{"created_at": iso, "updated_at": iso}` |

## Usage

```python
from core.services.entity_timestamp_mixin import EntityTimestampMixin

class TranscriptionService(EntityTimestampMixin):

    async def mark_processing(self, uid: str) -> Result[None]:
        # Spread into the backend update dict
        return await self.backend.update(uid, {"status": "processing", **self.update_properties()})
```

`update_properties()` sits on the `backend.update` side of the ADR-066 boundary —
it produces a raw property dict, not a typed `*UpdateIntent`.  Mark with
`# raw-write: timestamp bump` when mixing with other property updates to make
the intent explicit.

## Services Using EntityTimestampMixin

| Service | File | Usage |
|---------|------|-------|
| `TranscriptionService` | `transcription/transcription_service.py` | `update_properties()` for status updates |

## UTC vs Local Time

Pass `use_utc=True` when timestamps will be read across timezones or stored in
audit/integration contexts.  Default is local time (matches user-facing
calendar/scheduling features).

## See Also

- Implementation: `/core/services/entity_timestamp_mixin.py`
- Timestamp helpers: `/core/utils/timestamp_helpers.py`
