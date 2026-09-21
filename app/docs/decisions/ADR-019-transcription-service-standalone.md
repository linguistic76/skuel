---
title: "ADR-019: Transcription Service Simplification"
updated: 2026-09-21
status: accepted
category: decisions
tags: [adr, decisions, lsp, architecture, transcription, refactoring]
related: [ADR-014-unified-ingestion]
---

# ADR-019: Transcription Service Simplification

**Status:** Accepted

**Date:** 2025-12-06

**Decision Type:** Pattern/Practice + Refactoring

---

## Context

**What is the issue we're facing?**

The Transcription domain was over-engineered with multiple issues:

1. **LSP Violations:** TranscriptionService extended `BaseService` with incompatible method signatures
2. **Over-engineering:** Two services (997 + 846 = 1,843 lines) when one focused service sufficed
3. **Too many methods:** 42+ methods when 8 core methods handle all use cases
4. **Tight coupling:** Direct journal creation instead of event-driven decoupling
5. **Custom protocols:** TranscriptionOperations instead of standard BackendOperations

**The Core Job:**
```
Audio File → Deepgram API → Transcript Text
```

Everything else was accidental complexity.

---

## Decision

**What is the change we're proposing/making?**

Complete simplification of the Transcription domain:

1. **Merge into ONE service** - `TranscriptionService` (standalone, no BaseService)
2. **Thin Deepgram adapter** - `DeepgramAdapter` (API calls only, no business logic)
3. **Reduce methods** - From 42 → 8 focused methods
4. **Standard protocol** - Use `BackendOperations[Transcription]`
5. **Event-driven** - Publish `TranscriptionCompleted` instead of creating journals
6. **Clean model** - Single `Transcription` dataclass with Pydantic requests

---

## New Architecture

### File Structure

```
core/
├── models/transcription/
│   └── transcription.py          # Model + requests
├── services/transcription/
│   ├── __init__.py               # Module exports
│   └── transcription_service.py  # 8 methods
├── events/
│   └── transcription_events.py   # Events

adapters/
├── external/deepgram/
│   ├── __init__.py               # Protocols + exports
│   └── adapter.py                # Thin API wrapper
├── inbound/
│   ├── transcription_api.py      # 9 endpoints
│   └── transcription_routes.py   # DomainRouteConfig wiring
```

(Line counts at the decision are in the comparison table below; `wc -l` re-measures.)

### Service Methods (8 core methods)

```python
class TranscriptionService:
    # CRUD
    async def create(request, user_uid) -> Result[Transcription]
    async def get(uid) -> Result[Transcription | None]
    async def delete(uid) -> Result[bool]
    async def list(user_uid, status, limit, offset) -> Result[list[Transcription]]

    # Processing
    async def process(uid, options) -> Result[Transcription]  # Main: audio → Deepgram → text
    async def retry(uid) -> Result[Transcription]

    # Query
    async def search(query, user_uid, limit) -> Result[list[Transcription]]
    async def get_by_status(status, user_uid, limit) -> Result[list[Transcription]]
```

### Processing Flow

```
1. create(request, user_uid)     → Transcription (status: PENDING)
2. process(uid)                  → Deepgram API → Transcription (status: COMPLETED)
   └── Publishes TranscriptionCompleted event
3. Downstream services subscribe to event (e.g., journal creation)
```

### Route Endpoints (9 routes)

The target transcription rides as the `uid` query parameter, never a path segment
(`adapters/inbound/transcription_api.py`):

| Method | Endpoint | Service Method |
|--------|----------|----------------|
| POST | `/api/transcriptions` | create() |
| GET | `/api/transcriptions/get?uid=` | get() |
| DELETE | `/api/transcriptions/delete?uid=` | delete() |
| GET | `/api/transcriptions` | list() |
| POST | `/api/transcriptions/process?uid=` | process() |
| POST | `/api/transcriptions/retry?uid=` | retry() |
| GET | `/api/transcriptions/search?q=` | search() |
| GET | `/api/transcriptions/status?status=` | get_by_status() |
| GET | `/api/transcriptions/health` | (unauthenticated liveness) |

---

## Line Count Comparison (at the decision, 2025-12-06)

| Component | Before | After | Reduction |
|-----------|--------|-------|-----------|
| TranscriptionService | 997 | 435 | -56% |
| AudioTranscriptionServiceV2 | 846 | 0 | -100% |
| DeepgramAdapter | (embedded) | 201 | (extracted) |
| Model | ~200 | 208 | — |
| Routes | ~400 | 228 | -43% |
| Events | 0 | 91 | (new) |
| **Total** | **~1,843** | **~1,163** | **-37%** |

---

## Event-Driven Decoupling

**Before:** TranscriptionService directly created Journal entities (tight coupling)

**After:** TranscriptionService publishes events, downstream services subscribe

```python
# Events published
@dataclass(frozen=True)
class TranscriptionCompleted(BaseEvent):
    transcription_uid: str
    user_uid: str
    transcript_text: str
    audio_file_path: str
    confidence_score: float
    duration_seconds: float
    word_count: int

@dataclass(frozen=True)
class TranscriptionFailed(BaseEvent):
    transcription_uid: str
    user_uid: str
    error_message: str
    audio_file_path: str
```

---

## Bootstrap Wiring

```python
# In services_bootstrap.py

# Create DeepgramAdapter with API key
deepgram_adapter = DeepgramAdapter(deepgram_api_key) if deepgram_api_key else None

# Create backend with standard UniversalNeo4jBackend
transcription_backend = UniversalNeo4jBackend[Transcription](driver, "Transcription", Transcription)

# Create service
transcription_service = TranscriptionService(
    backend=transcription_backend,
    deepgram_adapter=deepgram_adapter,
    event_bus=event_bus,
)
```

---

## Alternatives Considered

### Alternative 1: Keep Both Services
**Why rejected:** Unnecessary complexity. One service handles all use cases.

### Alternative 2: ProcessingBaseService
**Why rejected:** Premature abstraction. Standalone service is simpler and clearer.

### Alternative 3: Keep BaseService Inheritance
**Why rejected:** LSP violations. TranscriptionService has fundamentally different semantics (processing pipeline vs activity domain).

---

## Consequences

### Positive
- Clear single responsibility: audio file → transcript text
- Event-driven decoupling from journals
- Standard BackendOperations protocol
- 37% code reduction
- Self-documenting architecture

### Negative
- Old services archived (a gitignored `zarchives/` — since gone; see Files Archived)
- Routes changed (v3 endpoints)
- Bootstrap wiring updated

### Neutral
- EntityType enum unchanged (correctly has no TRANSCRIPTION)
- Same core functionality preserved

---

## Files Archived

The four superseded files — `transcription_service.py` (997 lines),
`audio_transcription_service.py` (846 lines), `transcription_routes.py` (the old route
wiring) and the old 18-route `transcription_api.py` — went to a gitignored `zarchives/`
directory that predates this repository's first commit (2026-01-25) and no longer exists
on disk. Their pre-decision versions are in no commit; this ADR's line-count table is their
only record.

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2025-12-06 | Claude | Initial LSP fix | 1.0 |
| 2025-12-06 | Claude | Complete simplification | 2.0 |

---

## Appendix

### Service Categories in SKUEL

| Category | Examples | Base Class | Characteristics |
|----------|----------|------------|-----------------|
| Activity Domains (6) | Tasks, Goals, Habits, Events, Choices, Principles | BaseService | Direct CRUD, entity creation |
| Finance Domain (1) | Finance | Standalone facade | Admin-only, 5 sub-services |
| Curriculum Domains (3) | KU, PS, LP | Standalone facades | Knowledge organization |
| Content/Organization (3) | Journals, Assignments, MOC | Standalone | File upload, AI processing, navigation |
| **Transcription** | TranscriptionService | **Standalone** | Audio processing pipeline |

### Key Files

| File | Purpose |
|------|---------|
| `core/services/transcription/transcription_service.py` | Main service (8 methods) |
| `core/models/transcription/transcription.py` | Domain model + requests |
| `adapters/external/deepgram/adapter.py` | Thin Deepgram wrapper |
| `adapters/inbound/transcription_routes.py` | API routes (plus `transcription_api.py` and `batch_transcription_api.py`) |
| `core/events/transcription_events.py` | Domain events |

### Related Documentation
- **Implementation guide:** `/docs/patterns/STANDALONE_SERVICE_PATTERN.md` - How to create standalone services
