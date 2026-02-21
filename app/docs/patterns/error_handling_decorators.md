---
title: Error Handling Decorators - DRY Pattern Guide
updated: '2026-02-02'
category: patterns
related_skills:
- result-pattern
- ui-error-handling
related_docs: []
---
# Error Handling Decorators - DRY Pattern Guide
*Last updated: 2026-01-21* (Migration near-complete: 460+ decorator usages, ~250 preserved patterns)
## Related Skills

For implementation guidance, see:
- [@result-pattern](../../.claude/skills/result-pattern/SKILL.md)
- [@ui-error-handling](../../.claude/skills/ui-error-handling/SKILL.md)


## Overview

SKUEL provides decorators to eliminate repetitive try-except patterns. These decorators address a DRY violation that appeared 500+ times in the codebase.

**Philosophy: FAIL-FAST**

SKUEL follows a fail-fast philosophy. Errors should surface immediately, not be hidden. If an operation fails, it should fail loudly so bugs can be identified and fixed.

## Available Decorators

| Decorator | Purpose | Returns |
|-----------|---------|---------|
| `@with_error_handling` | Wrap service methods with automatic error handling | `Result[T]` |
| `@requires_graph_intelligence` | Validate graph_intel availability | `Result[T]` |
| `@safe_event_handler` | Wrap event handlers with structured logging | `None` |

## @with_error_handling

The primary decorator for eliminating repetitive try-except patterns.

### Basic Usage

```python
from core.utils.decorators import with_error_handling

# Before (manual pattern - repeated 500+ times)
async def search(self, query: str) -> Result[list[Task]]:
    try:
        result = await self.backend.execute_query(...)
        if result.is_error:
            return result
        return Result.ok(processed)
    except Exception as e:
        self.logger.error(f"Search failed: {e}")
        return Result.fail(Errors.database(operation="search", message=str(e)))

# After (decorator pattern)
@with_error_handling("search", error_type="database")
async def search(self, query: str) -> Result[list[Task]]:
    result = await self.backend.execute_query(...)
    if result.is_error:
        return result
    return Result.ok(processed)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `operation` | `str` | `"operation"` | Operation name for error messages and logging |
| `error_type` | `ErrorType` | `"auto"` | Force specific error type or auto-categorize |
| `uid_param` | `str \| None` | `None` | Extract UID from args for error context |

### Error Types

```python
ErrorType = Literal["database", "system", "validation", "not_found", "auto"]
```

- `"database"`: Always return `Errors.database()` - use for Neo4j/DB operations
- `"system"`: Always return `Errors.system()` - use for internal errors
- `"validation"`: Always return `Errors.validation()` - use for input validation
- `"not_found"`: Always return `Errors.not_found()` - use for missing resources
- `"auto"`: Intelligent categorization based on exception type (default)

### Auto-Categorization Logic

When `error_type="auto"`, the decorator categorizes exceptions:

1. `ValueError` → `Errors.validation()`
2. Neo4j exceptions (`Neo4j*`, `Driver*`, `Session*`) → `Errors.database()`
3. Error messages containing "not found" → `Errors.not_found()`
4. Error messages containing "database" or "neo4j" → `Errors.database()`
5. Error messages containing "validation" or "invalid" → `Errors.validation()`
6. All others → `Errors.system()`

### UID Context Extraction

Use `uid_param` to include UID in error details:

```python
@with_error_handling("get_task", error_type="database", uid_param="uid")
async def get(self, uid: str) -> Result[Task]:
    return await self.backend.get(uid)
    # On error: {"uid": "task:123"} included in error details
```

### Method Pattern

The decorator wraps the entire method, so validation that returns `Result.fail()` still works:

```python
@with_error_handling("search", error_type="database")
async def search(self, query: str) -> Result[list[Task]]:
    # Pre-validation still works - returns Result.fail() directly
    if not query:
        return Result.fail(Errors.validation(message="Query required", field="query"))

    # Configuration check still works
    if self._dto_class is None:
        return Result.fail(Errors.system(message="DTO class not configured", operation="search"))

    # Main logic - exceptions are caught by decorator
    result = await self.backend.execute_query(...)
    if result.is_error:
        return Result.fail(result.expect_error())

    return Result.ok(entities)
```

## @requires_graph_intelligence

For Phase 1-4 graph intelligence methods.

```python
from core.utils.decorators import requires_graph_intelligence

@requires_graph_intelligence("get_habit_with_context")
async def get_habit_with_context(self, uid: str) -> Result[HabitContext]:
    return await self.graph_intel.get_with_context(uid)
```

## @safe_event_handler

For event handlers that should log errors but not propagate them. Event handlers in event-driven systems intentionally don't propagate errors because:
- Event handlers run asynchronously
- The event bus may have multiple handlers for the same event
- One handler failing shouldn't prevent other handlers from running

```python
from core.utils.error_boundary import safe_event_handler

class KuService:
    @safe_event_handler("knowledge.applied_in_task")
    async def handle_knowledge_applied_in_task(self, event) -> None:
        """
        Handle KnowledgeAppliedInTask event.

        Increments: times_applied_in_tasks
        Updates: last_applied_date
        """
        await self.increment_substance_metric(
            ku_uid=event.knowledge_uid,
            metric="times_applied_in_tasks",
            timestamp_field="last_applied_date",
            timestamp=event.occurred_at,
        )
        self.logger.debug(
            f"Substance updated: {event.knowledge_uid} applied in task {event.task_uid}"
        )
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `event_name` | `str` | Event name for logging (e.g., `"knowledge.applied_in_task"`) |

### Behavior

On exception, the decorator:
1. Extracts event data from the second argument (after `self`)
2. Logs structured error with:
   - `event_name`: The event being handled
   - `error_type`: Exception class name
   - `error_message`: String representation
   - `handler`: Method name
   - `event_data`: Serialized event fields
3. Swallows the exception (returns `None`)

### When to Use

Use `@safe_event_handler` for:
- Event bus subscribers (e.g., `handle_knowledge_applied_in_task`)
- Fire-and-forget operations where caller doesn't need result
- Methods that return `None`, not `Result[T]`

### Files Using This Decorator

| File | Event Handlers |
|------|----------------|
| `core/services/ku_service.py` | 7 knowledge substance event handlers |

## Handling Optional Services (Fail-Fast Pattern)

When a service is optional (e.g., `ku_inference_service` may or may not be configured), use the following pattern:

```python
@with_error_handling("knowledge_inference", error_type="system")
async def _enhance_with_knowledge_inference(self, dto: TaskDTO) -> Result[TaskDTO | None]:
    """
    Returns Result.ok(None) if inference service not configured (feature disabled).
    Fails fast if inference service IS configured but fails.
    """
    if not self.ku_inference_service:
        # Feature not configured - this is OK, return None
        return Result.ok(None)

    # If service IS configured, it must work - fail fast on errors
    enhanced_dto = await self.ku_inference_service.enhance_task_dto_with_inference(dto)
    return Result.ok(enhanced_dto)

# Caller handles the Result
async def create_task(self, task_request: TaskCreateRequest) -> Result[Task]:
    dto = TaskDTO.create(...)

    inference_result = await self._enhance_with_knowledge_inference(dto)
    if inference_result.is_error:
        return Result.fail(inference_result.expect_error())  # Fail fast!
    if inference_result.value:
        dto = inference_result.value

    return await self.backend.create(dto)
```

**Why not graceful degradation?**

SKUEL's fail-fast philosophy means:
- If a service is configured, it should work
- Silent failures hide bugs
- Users should see real errors, not stale/incorrect data
- Debugging is easier when errors surface immediately

## Migration Guide

### When to Use Each Decorator

| Situation | Decorator | Error Type |
|-----------|-----------|------------|
| Database operations (queries, CRUD) | `@with_error_handling` | `"database"` |
| Internal system operations | `@with_error_handling` | `"system"` |
| Input validation | `@with_error_handling` | `"validation"` |
| Resource lookup | `@with_error_handling` | `"not_found"` or `"auto"` |
| Mixed operations | `@with_error_handling` | `"auto"` |
| Graph intelligence methods | `@requires_graph_intelligence` | N/A |

### Migration Steps

1. **Identify the pattern**: Look for try-except blocks that:
   - Catch `Exception as e`
   - Log with `self.logger.error()`
   - Return `Result.fail(Errors.*())`

2. **Add the decorator**: Apply `@with_error_handling` with appropriate parameters

3. **Remove the try-except**: Keep only the try block contents

4. **Verify behavior**: The decorator handles:
   - Logging (uses `self.logger.error()` if service has `HasLogger`)
   - Error categorization (based on `error_type` parameter)
   - UID extraction (if `uid_param` specified)

### What NOT to Migrate

Keep manual try-except for:
- **Event handlers**: Methods returning `None` (not `Result[T]`) use best-effort error logging
- **Specific exception types**: `except KeyError`, `except ValueError` for enum conversion
- **Feature detection fallbacks**: e.g., fulltext search → CONTAINS when index doesn't exist
- **Type introspection**: `except AttributeError` for polymorphic type handling
- **Loop iteration errors**: Where individual item failure should `continue`, not abort
- **Non-Result returns**: Methods that don't return `Result[T]`

## Current Adoption

*Last updated: 2025-12-05* (Migration near-complete)

**Statistics:**
- `@with_error_handling` decorator usages: **460+**
- Remaining try-except patterns: **~250** (legitimate patterns preserved)

| Component | Status | Methods Updated |
|-----------|--------|-----------------|
| **Activity Domains** | | |
| habits/ | ✅ Complete | 13 methods |
| tasks/ | ✅ Complete | 44 methods |
| goals/ | ✅ Complete | 16 methods |
| events/ | ✅ Complete | 12 methods |
| choices/ | ✅ Complete | 10 methods |
| principles/ | ✅ Complete | 24 methods |
| finance/ | ✅ Complete | 9 methods |
| **Curriculum Domains** | | |
| ku/ | ✅ Complete | 52 methods |
| lp/ | ✅ Complete | 17 methods |
| moc/ | ✅ Complete | 18 methods |
| **Foundation** | | |
| BaseService | ✅ Complete | 6 methods |
| AssignmentsQueryService | ✅ Complete | 7 methods |
| AssignmentSubmissionService | ✅ Complete | 5 methods |
| user/ | ✅ Complete | 21 methods |
| curriculum_base_service | ✅ Complete | 8 methods |
| **Infrastructure** | | |
| infrastructure/ | ✅ Complete | 12 methods |
| dsl/ | ✅ Complete | 31 methods |
| relationships/ | ✅ Complete | 14 methods |
| askesis/ | ✅ Complete | 9 methods |
| lp_intelligence/ | ✅ Complete | 9 methods |
| **Processing Services** | | |
| content_enrichment_service | ✅ Complete | 5 methods |
| transcription_service | ✅ Complete | 10 methods |
| assignment_service | ✅ Complete | 6 methods |
| yaml_ingestion_service | ✅ Complete | 11 methods |
| unified_ingestion_service | ✅ Complete | 1 method |
| **Analytics & Progress** | | |
| user_progress_service | ✅ Complete | 5 methods |
| unified_progress_service | ✅ Complete | 2 methods |
| semantic_analytics_service | ✅ Complete | 5 methods |
| ku_generation_service | ✅ Complete | 5 methods |
| ku_inference_service | ✅ Complete | 4 methods |
| event_logger_service | ✅ Complete | 5 methods |
| **Schema Services** | | |
| schema_service | ✅ Complete | 11 methods |
| schema_change_detector | ✅ Complete | 5 methods |
| **System Services** | | |
| system_service | ✅ Complete | 3 methods |
| **Preserved (Legitimate Patterns)** | | |
| llm_service | ✅ Preserved | External API calls |
| ai_service | ✅ Preserved | External API calls |
| embeddings_service | ✅ Preserved | OpenAI API calls |
| transcription_service | ✅ Preserved | Deepgram API calls via DeepgramAdapter |
| performance_optimization_service | ✅ Preserved | Graceful degradation |
| system_service_init | ✅ Preserved | Health checks |
| schema_mapping_service | ✅ Preserved | Type introspection |
| markdown_sync_service | ✅ Preserved | File I/O, enum parsing |
| adaptive_sel_service | ✅ Preserved | Graceful degradation |

## Best Practices

1. **Prefer specific error types**: Use `error_type="database"` for DB operations rather than `"auto"`

2. **Extract UIDs for context**: Use `uid_param` to include identifiers in error details

3. **Keep validation separate**: Pre-validation that returns `Result.fail()` works correctly with the decorator

4. **Fail fast**: If an operation should succeed, let it fail loudly when it doesn't

5. **Test error paths**: Verify that exceptions produce expected error types

## See Also

- `/docs/patterns/ERROR_HANDLING.md` - Result[T] error handling philosophy
- `/core/utils/decorators.py` - Decorator implementations
- `/adapters/inbound/boundary.py` + `/adapters/inbound/boundary.py` - Route-level boundary handlers
