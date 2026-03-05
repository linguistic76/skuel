---
title: Ownership Verification Pattern
updated: '2026-03-05'
category: patterns
related_skills:
- activity-domains
- curriculum-domains
related_docs: []
---
# Ownership Verification Pattern

*Last updated: 2026-03-05*

## Quick Start

**Skills:** [@activity-domains](../../.claude/skills/activity-domains/SKILL.md), [@curriculum-domains](../../.claude/skills/curriculum-domains/SKILL.md)

For hands-on implementation:
1. Invoke `@activity-domains` for USER_OWNED verification patterns
2. Invoke `@curriculum-domains` for SHARED content patterns
3. See [AUTH_PATTERNS.md](AUTH_PATTERNS.md) for authentication decorators
4. Continue below for complete ownership verification patterns

**Related Documentation:**
- [ROUTE_FACTORIES.md](ROUTE_FACTORIES.md) - ContentScope configuration in route factories

---

## Status: ✅ Complete

**All 42 manual routes across 7 API files now have ownership verification.**

| API | Routes Secured | Key Operations |
|-----|----------------|----------------|
| Goals | 3 | Habit linking (link, unlink, get) |
| Habits | 7 | Track, untrack, streak, progress, reminders |
| Tasks | 8 | Complete, assign, dependencies, context, impact |
| Events | 9 | Status, attendees, recurrence, conflicts |
| Choices | 4 | Decide, options CRUD, evaluate |
| Principles | 7 | Expressions, alignment, links, related |
| Finance | 4 | Clear, reconcile, receipt, recalculate |

Factory-generated routes (CRUD, status, query) automatically include ownership verification.

## Overview

SKUEL implements multi-tenant security through **ownership verification** - ensuring users can only access entities they own. This prevents IDOR (Insecure Direct Object Reference) attacks where an attacker guesses or discovers UIDs belonging to other users.

## Core Principle

> "Return 'not found' for entities the user doesn't own - never reveal that a UID exists."

This design prevents information leakage. An attacker can't determine if a UID exists or if they simply don't have access.

## Architecture

### Three Layers of Protection

```
┌─────────────────────────────────────────────────────────────────────┐
│  1. AUTHENTICATION (Session Layer)                                   │
│     require_authenticated_user(request) → user_uid                  │
│     Raises 401 if not logged in                                     │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│  2. OWNERSHIP VERIFICATION (Service Layer)                           │
│     service.verify_ownership(uid, user_uid) → Result[Entity]        │
│     Returns 404 if user doesn't own entity                          │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│  3. DATA FILTERING (Database Layer)                                  │
│     Entities have user_uid property, queries filter by it           │
└─────────────────────────────────────────────────────────────────────┘
```

## Implementation

### BaseService Methods

```python
# core/services/base_service.py

async def verify_ownership(self, uid: str, user_uid: str) -> Result[T]:
    """Verify entity exists AND belongs to user. Returns entity or NotFound."""

async def get_for_user(self, uid: str, user_uid: str) -> Result[T]:
    """Get entity only if owned by user."""

async def update_for_user(self, uid: str, updates: dict, user_uid: str) -> Result[T]:
    """Update entity only if owned by user."""

async def delete_for_user(self, uid: str, user_uid: str) -> Result[bool]:
    """Delete entity only if owned by user."""
```

### CRUDRouteFactory

The factory automatically verifies ownership based on `scope` parameter:

```python
from core.models.enums import ContentScope

# Activity domains (user-owned) - default behavior
crud_factory = CRUDRouteFactory(
    service=tasks_service,
    domain_name="tasks",
    create_schema=TaskCreateRequest,
    update_schema=TaskUpdateRequest,
    scope=ContentScope.USER_OWNED,  # Default - enforces ownership
)

# Curriculum domains (shared) - no ownership verification
crud_factory = CRUDRouteFactory(
    service=ku_service,
    domain_name="ku",
    create_schema=CurriculumCreateRequest,
    update_schema=EntityUpdateRequest,
    scope=ContentScope.SHARED,  # KU is shared, not user-owned
)
```

### StatusRouteFactory

For status change operations (activate, pause, complete, archive), use StatusRouteFactory:

```python
from adapters.inbound.route_factories import StatusRouteFactory, StatusTransition
from core.models.enums import ContentScope

status_factory = StatusRouteFactory(
    service=goals_service,
    domain_name="goals",
    transitions={
        "activate": StatusTransition(
            target_status="active",
            method_name="activate_goal",
        ),
        "pause": StatusTransition(
            target_status="paused",
            requires_body=True,
            body_fields=["reason", "until_date"],
            method_name="pause_goal",
        ),
        "complete": StatusTransition(
            target_status="completed",
            requires_body=True,
            body_fields=["notes", "date"],
            method_name="complete_goal",
        ),
    },
    scope=ContentScope.USER_OWNED,  # Default - enforces ownership
)
status_factory.register_routes(app, rt)
```

**For services using typed request objects** (like HabitsService), use `request_builder`:

```python
status_factory = StatusRouteFactory(
    service=habits_service,
    domain_name="habits",
    transitions={
        "pause": StatusTransition(
            target_status="paused",
            requires_body=True,
            body_fields=["reason", "until_date"],
            request_builder=lambda uid, fields: PauseHabitRequest(
                habit_uid=uid,
                reason=fields.get("reason", "Paused"),
                until_date=fields.get("until_date"),
            ),
            method_name="pause_habit",
        ),
    },
)
```

### Manual Routes

For routes not generated by the factory, use this pattern:

```python
from adapters.inbound.auth import require_authenticated_user

@rt("/api/goals/{uid}/progress")
@boundary_handler()
async def update_goal_progress(request: Request) -> Result[dict]:
    """Update goal progress (requires ownership)."""
    uid = request.path_params["uid"]
    user_uid = require_authenticated_user(request)

    # Verify user owns this goal
    ownership = await goals_service.verify_ownership(uid, user_uid)
    if ownership.is_error:
        return ownership  # Returns 404

    # Safe to proceed - user owns this goal
    body = await request.json()
    return await goals_service.update_goal_progress(uid, body["progress"])
```

### with_ownership Decorator (Alternative)

For simpler routes, use the decorator:

```python
from adapters.inbound.auth import with_ownership

@rt("/api/goals/{uid}/progress")
@with_ownership(lambda: goals_service)
@boundary_handler()
async def update_goal_progress(request, user_uid: str, entity: Goal):
    """Entity is pre-verified to belong to user_uid."""
    body = await request.json()
    return await goals_service.update_goal_progress(entity.uid, body["progress"])
```

### Standalone Services (Non-BaseService)

Standalone services (e.g. `TranscriptionService`) don't inherit from `BaseService`,
so they implement `verify_ownership()` directly — same logic, same error semantics:

```python
# core/services/transcription/transcription_service.py
async def verify_ownership(self, uid: str, user_uid: str) -> Result[Transcription]:
    result = await self.get(uid)
    if result.is_error:
        return Result.fail(result.expect_error())
    if not result.value:
        return Result.fail(Errors.not_found("Transcription", uid))
    if result.value.user_uid != user_uid:
        return Result.fail(Errors.not_found("Transcription", uid))
    return Result.ok(result.value)
```

See: `/docs/patterns/STANDALONE_SERVICE_PATTERN.md`

### Cross-Domain Services (UnifiedSharingService)

`UnifiedSharingService` is entity-agnostic, backed by `SharingBackend(UniversalNeo4jBackend[Entity])`.
It combines ownership + shareable status in a single Cypher round trip via
`_verify_owned_and_shareable()`. This mirrors the mixin's error semantics — returns
`not_found` for both missing entities and ownership mismatches.

See: `/docs/patterns/SHARING_PATTERNS.md`

## Entity Requirements

Entities supporting ownership must have a `user_uid` field:

```python
@dataclass(frozen=True)
class Task:
    uid: str
    user_uid: str  # REQUIRED for ownership verification
    title: str
    # ...
```

## Domains by Ownership Type

### User-Owned Domains (scope=ContentScope.USER_OWNED)

| Domain | Entity | Notes |
|--------|--------|-------|
| Tasks | Task | User's work items |
| Goals | Goal | User's objectives |
| Habits | Habit | User's recurring behaviors |
| Events | Event | User's calendar items |
| Choices | Choice | User's decisions |
| Principles | Principle | User's values |
| Submissions | Submission | User's submissions and reflections |

### Shared Domains (scope=ContentScope.SHARED)

| Domain | Entity | Notes |
|--------|--------|-------|
| KU | KnowledgeUnit | Shared knowledge base |
| LS | LearningStep | Shared learning content |
| LP | LearningPath | Shared curricula |

**NOTE (January 2026):** MOC is now KU-based - a KU "is" a MOC when it has
outgoing ORGANIZES relationships. No separate MapOfContent entity exists.

### Admin-Only Domains (role-gated, no ContentScope)

| Domain | Entity | Notes |
|--------|--------|-------|
| Finance | Expense | Admin-only bookkeeping — `@require_admin` on routes, no ownership checks |

### ContentScope Enum

```python
from core.models.enums import ContentScope

class ContentScope(str, Enum):
    USER_OWNED = "user_owned"  # User-specific with ownership checks
    SHARED = "shared"           # Public/shared, no ownership required
```

The `scope` parameter replaces the boolean `verify_ownership` parameter for type-safe ownership patterns.

## Security Benefits

1. **IDOR Prevention**: Users cannot access other users' data by guessing UIDs
2. **Information Hiding**: Attackers can't enumerate valid UIDs
3. **Consistent Behavior**: Same 404 for "doesn't exist" and "not yours"
4. **Defense in Depth**: Multiple verification layers

## Migration Guide

### Updating Existing Routes

**Before (Vulnerable):**
```python
@rt("/api/goals/{uid}/progress")
async def update_progress(request):
    uid = request.path_params["uid"]  # Anyone with UID can access!
    return await service.update_progress(uid, ...)
```

**After (Secure):**
```python
@rt("/api/goals/{uid}/progress")
async def update_progress(request):
    uid = request.path_params["uid"]
    user_uid = require_authenticated_user(request)

    ownership = await service.verify_ownership(uid, user_uid)
    if ownership.is_error:
        return ownership

    return await service.update_progress(uid, ...)
```

### Routes Updated (Complete)

All manual routes operating on user-owned entities by UID now have ownership verification:

**Goals API (`goals_api.py`):**
- `POST /api/goals/{uid}/habits` - Link habit to goal
- `DELETE /api/goals/{uid}/habits/{habit_uid}` - Unlink habit from goal
- `GET /api/goals/{uid}/habits` - Get goal's habits

**Habits API (`habits_api.py`):**
- `POST /api/habits/{uid}/track` - Track habit completion
- `POST /api/habits/{uid}/untrack` - Remove tracking entry
- `GET /api/habits/{uid}/streak` - Get streak information
- `GET /api/habits/{uid}/progress` - Get habit progress
- `POST /api/habits/{uid}/reminder` - Set reminder
- `GET /api/habits/{uid}/reminders` - Get reminders
- `DELETE /api/habits/{uid}/reminders/{reminder_uid}` - Delete reminder

**Tasks API (`tasks_api.py`):**
- `POST /api/tasks/{uid}/complete` - Complete task
- `POST /api/tasks/{uid}/uncomplete` - Uncomplete task
- `POST /api/tasks/{uid}/assign` - Assign task to user
- `GET /api/tasks/{uid}/dependencies` - Get dependencies
- `POST /api/tasks/{uid}/dependencies` - Create dependency
- `GET /api/tasks/{uid}/context` - Get task context
- `GET /api/tasks/{uid}/impact` - Get completion impact
- `GET /api/tasks/{uid}/practice-opportunities` - Get practice opportunities

**Events API (`events_api.py`):**
- `PUT /api/events/{uid}/status` - Update event status
- `POST /api/events/{uid}/start` - Start event
- `POST /api/events/{uid}/complete` - Complete event
- `POST /api/events/{uid}/cancel` - Cancel event
- `GET /api/events/{uid}/conflicts` - Check conflicts
- `POST /api/events/{uid}/recurrence` - Create recurring instances
- `POST /api/events/{uid}/attendees` - Add attendee
- `DELETE /api/events/{uid}/attendees/{attendee_uid}` - Remove attendee
- `GET /api/events/{uid}/attendees` - Get attendees

**Choices API (`choice_api.py`):**
- `POST /api/choices/{choice_uid}/decide` - Make decision
- `POST /api/choices/{choice_uid}/options` - Create option
- `PUT /api/choices/{choice_uid}/options/{option_uid}` - Update option
- `POST /api/choices/{choice_uid}/evaluate` - Evaluate outcome

**Principles API (`principles_api.py`):**
- `POST /api/principles/{principle_uid}/expressions` - Create expression
- `GET /api/principles/{principle_uid}/expressions` - Get expressions
- `POST /api/principles/{principle_uid}/alignment` - Assess alignment
- `GET /api/principles/{principle_uid}/alignment` - Get alignment history
- `POST /api/principles/{principle_uid}/links` - Create link
- `GET /api/principles/{principle_uid}/links` - Get links
- `GET /api/principles/{principle_uid}/related` - Get related principles

**Finance API (`finance_api.py`):**
- `POST /api/expenses/{uid}/clear` - Clear expense
- `POST /api/expenses/{uid}/reconcile` - Reconcile expense
- `POST /api/expenses/{uid}/receipt` - Attach receipt
- `POST /api/budgets/{uid}/recalculate` - Recalculate budget

## Testing Ownership

```python
async def test_ownership_prevents_cross_user_access():
    """User A cannot access User B's goal."""
    # Create goal for User A
    goal = await service.create(Goal(user_uid="user.alice", title="Alice's Goal"))

    # User B tries to access it
    result = await service.get_for_user(goal.uid, "user.bob")

    # Should return NotFound (not AccessDenied)
    assert result.is_error
    assert "not found" in result.expect_error().message.lower()
```

## See Also

- `/core/services/base_service.py` - Ownership methods
- `/core/auth/session.py` - `with_ownership` decorator
- `/adapters/inbound/route_factories/crud_route_factory.py` - Factory implementation
- `/docs/patterns/ERROR_HANDLING.md` - Result[T] pattern
