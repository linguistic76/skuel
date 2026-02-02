---
title: Standalone Service Pattern
updated: 2026-01-07
category: patterns
related_skills:
- base-analytics-service
related_docs:
- /docs/decisions/ADR-019-transcription-service-standalone.md
---

# Standalone Service Pattern

When to use a standalone service instead of extending `BaseService`.

**Decision context:** See [ADR-019](/docs/decisions/ADR-019-transcription-service-standalone.md) for the transcription service case study.

---
## Related Skills

For implementation guidance, see:
- [@base-analytics-service](../../.claude/skills/base-analytics-service/SKILL.md)


## When to Use Standalone Services

Use a standalone service (no `BaseService` inheritance) when:

1. **Processing pipeline** - The service transforms data (audio → text, file → entity)
2. **Different semantics** - Service doesn't fit CRUD entity pattern
3. **External integration** - Primary job is calling external APIs
4. **LSP violations** - Extending BaseService would require incompatible method signatures

### Service Categories in SKUEL

| Category | Base Class | Characteristics | Examples |
|----------|------------|-----------------|----------|
| **Activity Domains (6)** | BaseService | Direct CRUD, entity creation | Tasks, Goals, Habits, Events, Choices, Principles |
| **Finance Domain (1)** | Standalone facade | Admin-only, 5 sub-services | Finance |
| **Curriculum Domains (3)** | Standalone facades | Knowledge organization | KU, LS, LP |
| **Content/Organization (3)** | Standalone | File upload, AI processing, navigation | Journals, Assignments, MOC |
| **Transcription** | **Standalone** | Audio processing pipeline | TranscriptionService |

---

## Standalone Service Structure

### File Organization

```
core/
├── models/{domain}/
│   └── {domain}.py              # Domain model + Pydantic requests
├── services/{domain}/
│   ├── __init__.py              # Module exports
│   └── {domain}_service.py      # Main service (focused methods)
├── events/
│   └── {domain}_events.py       # Domain events

adapters/
├── external/{provider}/
│   ├── __init__.py              # Protocols + exports
│   └── adapter.py               # Thin API wrapper
├── inbound/
│   └── {domain}_routes.py       # API routes
```

### Example: Transcription Service

```python
class TranscriptionService:
    """Standalone processing service - no BaseService inheritance."""

    def __init__(
        self,
        backend: BackendOperations[Transcription],
        deepgram_adapter: DeepgramAdapter | None,
        event_bus: EventBus | None,
    ):
        self.backend = backend
        self.deepgram = deepgram_adapter
        self.event_bus = event_bus

    # CRUD - focused, minimal
    async def create(self, request: TranscriptionCreateRequest, user_uid: str) -> Result[Transcription]: ...
    async def get(self, uid: str) -> Result[Transcription | None]: ...
    async def delete(self, uid: str) -> Result[bool]: ...
    async def list(self, user_uid: str, status: str | None, limit: int, offset: int) -> Result[list[Transcription]]: ...

    # Processing - the core job
    async def process(self, uid: str, options: ProcessingOptions | None) -> Result[Transcription]: ...
    async def retry(self, uid: str) -> Result[Transcription]: ...

    # Query
    async def search(self, query: str, user_uid: str, limit: int) -> Result[list[Transcription]]: ...
    async def get_by_status(self, status: str, user_uid: str, limit: int) -> Result[list[Transcription]]: ...
```

---

## Key Principles

### 1. Focus on Core Job

Identify the core job and eliminate everything else:

```
TranscriptionService Core Job:
Audio File → Deepgram API → Transcript Text
```

Everything else (journal creation, user notifications) is handled via events.

### 2. Thin External Adapters

Keep external API adapters thin - no business logic:

```python
class DeepgramAdapter:
    """Thin wrapper - API calls only, no business logic."""

    async def transcribe_audio(self, audio_path: Path, options: TranscriptionOptions) -> Result[TranscriptionResult]:
        """Call Deepgram API and return raw result."""
        # Direct API call, no business logic
        response = await self.client.transcribe(audio_path, options)
        return Result.ok(TranscriptionResult.from_response(response))
```

### 3. Event-Driven Decoupling

Don't create entities from other domains directly. Publish events instead:

```python
# DON'T - Tight coupling
async def process(self, uid: str) -> Result[Transcription]:
    # ... process audio ...
    # DON'T create journal here
    journal = await self.journal_service.create(...)  # TIGHT COUPLING

# DO - Event-driven
async def process(self, uid: str) -> Result[Transcription]:
    # ... process audio ...
    # Publish event, let downstream services handle it
    await self.event_bus.publish(TranscriptionCompleted(
        transcription_uid=uid,
        user_uid=user_uid,
        transcript_text=result.text,
        # ... other data ...
    ))
```

### 4. Standard Backend Protocol

Even standalone services use `BackendOperations[T]`:

```python
# In services_bootstrap.py
transcription_backend = UniversalNeo4jBackend[Transcription](
    driver, "Transcription", Transcription
)

transcription_service = TranscriptionService(
    backend=transcription_backend,
    deepgram_adapter=deepgram_adapter,
    event_bus=event_bus,
)
```

---

## Events Pattern

Define domain events for downstream processing:

```python
# core/events/transcription_events.py
from dataclasses import dataclass
from core.events.base_event import BaseEvent

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

Downstream services subscribe:

```python
# Journal service subscribes to transcription events
event_bus.subscribe(TranscriptionCompleted, journal_service.handle_transcription_completed)
```

---

## Processing Flow

Standard flow for processing services:

```
1. create(request, user_uid)     → Entity (status: PENDING)
2. process(uid, options)         → External API → Entity (status: COMPLETED)
   └── Publishes {Domain}Completed event
3. Downstream services subscribe to event
```

### Status States

```python
class ProcessingStatus(str, Enum):
    PENDING = "pending"       # Created, awaiting processing
    PROCESSING = "processing" # Currently being processed
    COMPLETED = "completed"   # Successfully processed
    FAILED = "failed"         # Processing failed
```

---

## Route Endpoints

Standard pattern for processing services:

| Method | Endpoint | Service Method | Purpose |
|--------|----------|----------------|---------|
| POST | `/api/{domain}` | create() | Create new entity |
| GET | `/api/{domain}/{uid}` | get() | Get entity |
| DELETE | `/api/{domain}/{uid}` | delete() | Delete entity |
| GET | `/api/{domain}` | list() | List entities |
| POST | `/api/{domain}/{uid}/process` | process() | **Trigger processing** |
| POST | `/api/{domain}/{uid}/retry` | retry() | Retry failed processing |
| GET | `/api/{domain}/search` | search() | Search entities |
| GET | `/api/{domain}/status/{status}` | get_by_status() | Filter by status |
| GET | `/api/{domain}/health` | - | Health check |

---

## Bootstrap Wiring

```python
# In services_bootstrap.py

# 1. Create external adapter (optional, may be None)
deepgram_adapter = DeepgramAdapter(api_key) if api_key else None

# 2. Create backend with standard UniversalNeo4jBackend
transcription_backend = UniversalNeo4jBackend[Transcription](
    driver, "Transcription", Transcription
)

# 3. Create service
transcription_service = TranscriptionService(
    backend=transcription_backend,
    deepgram_adapter=deepgram_adapter,
    event_bus=event_bus,
)
```

---

## Comparison: Standalone vs BaseService

| Aspect | BaseService | Standalone |
|--------|-------------|------------|
| **Use case** | Activity domains, CRUD entities | Processing pipelines, external integrations |
| **Inheritance** | Extends BaseService[B, T] | No inheritance |
| **Methods** | 20+ inherited methods | 6-10 focused methods |
| **Configuration** | Class attributes | Constructor params |
| **Ownership** | Built-in (verify_ownership) | Manual if needed |
| **Search** | Inherited graph-aware search | Manual implementation |
| **Graph enrichment** | Automatic via _config | Manual if needed |

---

## See Also

- **Decision context:** [ADR-019](/docs/decisions/ADR-019-transcription-service-standalone.md) - Transcription simplification
- **Event-driven architecture:** `/docs/patterns/event_driven_architecture.md`
- **BaseService pattern:** `/docs/patterns/CONFIGURATION_DRIVEN_SERVICE_ARCHITECTURE.md`
