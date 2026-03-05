---
title: Content Sharing Patterns
updated: '2026-03-05'
category: patterns
related_skills:
- pytest
related_docs: []
---
# Content Sharing Patterns

**Status:** All phases complete — `UnifiedSharingService` active (2026-03-01)
**See Also:** [ADR-038: Content Sharing Model](/docs/decisions/ADR-038-content-sharing-model.md), [ADR-042: Privacy as First-Class Citizen](/docs/decisions/ADR-042-privacy-as-first-class-citizen.md)

---
## Related Skills

For implementation guidance, see:
- [@pytest](../../.claude/skills/pytest/SKILL.md)


## Overview

SKUEL's content sharing system enables users to share entities with specific users (teachers, peers, mentors) or with entire groups. Built on a three-level visibility model with Neo4j relationship-based access control.

**Service:** `UnifiedSharingService` — entity-agnostic, works across all EntityTypes.
**Protocol:** `SharingOperations` — `core/ports/sharing_protocols.py`

---

## Core Concepts

### Three-Level Visibility Model

```
PRIVATE (default) → Owner only
SHARED            → Owner + users with SHARES_WITH or SHARED_WITH_GROUP relationship
PUBLIC            → Anyone can view (portfolio showcase)
```

### Quality Control

**Only completed entities can be shared.** This prevents:
- Sharing failed entities
- Sharing entities still processing
- Low-quality portfolio content

Enforced at service layer via `verify_shareable()` method.

### Access Control Query Pattern

```cypher
MATCH (entity:Entity {uid: $uid})
OPTIONAL MATCH (viewer:User {uid: $viewer_uid})-[:SHARES_WITH]->(entity)
OPTIONAL MATCH (viewer2:User {uid: $viewer_uid})-[:MEMBER_OF]->(g:Group)<-[:SHARED_WITH_GROUP]-(entity)
WHERE entity.user_uid = $viewer_uid
   OR entity.visibility = 'public'
   OR (entity.visibility = 'shared' AND
       (count(viewer) > 0 OR count(viewer2) > 0))
RETURN entity
```

**Key Features:**
- Owner always has access
- PUBLIC visible to everyone
- SHARED requires explicit `SHARES_WITH` relationship OR group membership via `SHARED_WITH_GROUP`
- Returns 404 for both "not found" and "forbidden" (no information leakage)

---

## Usage Patterns

### Pattern 1: Student-Teacher Workflow

**Use Case:** Student submits report and shares with teacher for review.

```python
from core.services.sharing import UnifiedSharingService
from core.models.enums.metadata_enums import Visibility

entity_uid = "ku_assignment_abc123"
student_uid = "user_alice"
teacher_uid = "user_teacher_bob"

# Step 1: Student sets visibility to SHARED
visibility_result = await sharing_service.set_visibility(
    entity_uid=entity_uid,
    owner_uid=student_uid,
    visibility=Visibility.SHARED,
)

# Step 2: Student shares with teacher
share_result = await sharing_service.share(
    entity_uid=entity_uid,
    owner_uid=student_uid,
    recipient_uid=teacher_uid,
    role="teacher",
)

# Step 3: Teacher fetches shared entities
shared = await sharing_service.get_shared_with_me(
    user_uid=teacher_uid,
    limit=50,
)

# Step 4: Teacher checks access
access = await sharing_service.check_access(
    entity_uid=entity_uid,
    user_uid=teacher_uid,
)
```

**UI Flow:**
1. Student: `/submissions/{uid}` → Set visibility dropdown to "Shared"
2. Student: Click "Share with User" → Enter teacher UID → Submit
3. Teacher: Navigate to `/profile/shared` → See entity in inbox
4. Teacher: Click "View" → Access entity detail page

---

### Pattern 2: Teacher Assignment Auto-Sharing (ADR-040)

**Use Case:** Teacher assigns work to a group. When a student submits, the entity is automatically shared with the assigning teacher.

```python
# Step 1: Teacher creates assigned Exercise (targets a group)
# (handled by ExerciseService with scope=ASSIGNED)

# Step 2: Student submits against assigned Exercise
# Auto-sharing happens inside SubmissionsCoreService
await submissions_core_service.process_assignment_submission(
    submission_uid=submission_uid,
    exercise_uid=exercise_uid,
    student_uid=student_uid,
)
# This automatically:
# - Creates FULFILLS_EXERCISE relationship (submission → exercise)
# - Creates SHARES_WITH {role: "teacher"} relationship (teacher → submission)
# - Sets status to MANUAL_REVIEW for HUMAN processor types

# Step 3: Teacher views review queue
queue_result = await teacher_review.get_review_queue(teacher_uid)

# Step 4: Teacher provides feedback
await teacher_review.submit_feedback(submission_uid, teacher_uid, "Great work!")
```

**Graph Pattern:**
```cypher
// Exercise structure
(teacher:User)-[:OWNS]->(group:Group)
(student:User)-[:MEMBER_OF]->(group:Group)
(exercise:Exercise {scope: "assigned"})-[:FOR_GROUP]->(group:Group)

// On student submission (auto-created)
(submission:Entity)-[:FULFILLS_EXERCISE]->(exercise:Exercise)
(teacher:User)-[:SHARES_WITH {role: "teacher", share_version: "original"}]->(submission:Entity)
```

**Key Differences from Manual Sharing:**
- No explicit `share()` call — auto-created on submission
- Visibility is NOT changed to SHARED — teacher access is via SHARES_WITH regardless
- Entity ownership stays with the student
- Teacher's review queue = `SHARES_WITH` filtered by `role="teacher"` and pending status

**See:** `/docs/decisions/ADR-040-teacher-assignment-workflow.md`

---

### Pattern 3: Public Portfolio Showcase

**Use Case:** Student showcases best work publicly.

```python
# Student sets entity to PUBLIC
await sharing_service.set_visibility(
    entity_uid="ku_best_work",
    owner_uid="user_alice",
    visibility=Visibility.PUBLIC,
)

# Anyone can now view this entity
# No SHARES_WITH relationship needed
access_result = await sharing_service.check_access(
    entity_uid="ku_best_work",
    user_uid="user_anyone",
)
assert access_result.value is True  # ✅ Public access
```

**API Endpoint:**
```http
GET /api/submissions/public?user_uid=user_alice&limit=10
```

Returns only `visibility=PUBLIC` entities. Visibility filter and `limit` are both applied at query time via `SubmissionsCoreService.get_public_submissions()` — callers always receive up to `limit` public results.

---

### Pattern 4: Peer Review

**Use Case:** Student shares work with classmates for feedback.

```python
# Share with multiple peers
peers = [
    ("user_charlie", "peer"),
    ("user_dana", "peer"),
    ("user_eve", "peer"),
]

# Set visibility to SHARED first
await sharing_service.set_visibility(
    entity_uid=entity_uid,
    owner_uid=student_uid,
    visibility=Visibility.SHARED,
)

for peer_uid, role in peers:
    await sharing_service.share(
        entity_uid=entity_uid,
        owner_uid=student_uid,
        recipient_uid=peer_uid,
        role=role,
    )

# List all users entity is shared with
shared_users = await sharing_service.get_shared_with(entity_uid=entity_uid)
# Returns: [{"user_uid": "user_charlie", "role": "peer", ...}, ...]
```

---

### Pattern 5: Access Revocation

**Use Case:** Student removes teacher access after entity is graded.

```python
# Unshare from teacher
unshare_result = await sharing_service.unshare(
    entity_uid=entity_uid,
    owner_uid=student_uid,
    recipient_uid=teacher_uid,
)

# Teacher immediately loses access
access_result = await sharing_service.check_access(
    entity_uid=entity_uid,
    user_uid=teacher_uid,
)
assert access_result.value is False  # ✅ Access revoked
```

---

### Pattern 6: Mentor Collaboration

**Use Case:** Student shares draft work with mentor for guidance.

```python
# Share with mentor (different role than teacher)
await sharing_service.share(
    entity_uid="ku_draft",
    owner_uid=student_uid,
    recipient_uid="user_mentor",
    role="mentor",  # Distinguishes from teacher role
)
```

**Role Types:**
- `teacher` - Academic instructor
- `peer` - Classmate/colleague
- `mentor` - External advisor
- `viewer` - Read-only access

Roles are stored in relationship metadata for future feature expansion (e.g., role-based permissions).

---

### Pattern 7: Group Sharing (Phase 4)

**Use Case:** Share an entity with all current (and future) members of a group in one operation.

```python
# Share with entire group — access granted to all current members
result = await sharing_service.share_with_group(
    entity_uid="ku_project_abc",
    owner_uid=student_uid,
    group_uid="group_class_2026",
    share_version="original",
)

# New members added later automatically gain access — no re-share needed
# Removed members automatically lose access

# Check what's shared via group membership
group_content = await sharing_service.get_shared_with_me_via_groups(
    user_uid=member_uid,
    limit=50,
)

# Get groups an entity is shared with
groups = await sharing_service.get_groups_shared_with(entity_uid="ku_project_abc")

# Revoke group-level access
await sharing_service.unshare_from_group(
    entity_uid="ku_project_abc",
    owner_uid=student_uid,
    group_uid="group_class_2026",
)
```

**Graph Pattern:**
```cypher
(entity:Entity)-[:SHARED_WITH_GROUP {shared_at: datetime, share_version: 'original'}]->(group:Group)
(member:User)-[:MEMBER_OF]->(group:Group)
// → member has access to entity automatically
```

**Key advantage:** Membership changes propagate automatically — no per-user re-sharing required when the group roster changes.

---

## API Reference

### Share with User

```http
POST /api/submissions/share
Content-Type: application/json

{
  "entity_uid": "ku_123",
  "recipient_uid": "user_teacher",
  "role": "teacher",
  "share_version": "original"
}
```

**Auth:** Owner only | **Quality Check:** Entity must be completed

---

### Unshare from User

```http
POST /api/submissions/unshare
Content-Type: application/json

{
  "entity_uid": "ku_123",
  "recipient_uid": "user_teacher"
}
```

**Auth:** Owner only

---

### Share with Group

```http
POST /api/share/group
Content-Type: application/json

{
  "entity_uid": "ku_123",
  "group_uid": "group_class_2026",
  "share_version": "original"
}
```

**Auth:** Owner only

---

### Unshare from Group

```http
POST /api/share/ungroup
Content-Type: application/json

{
  "entity_uid": "ku_123",
  "group_uid": "group_class_2026"
}
```

**Auth:** Owner only

---

### Set Visibility

```http
POST /api/submissions/set-visibility
Content-Type: application/json

{
  "entity_uid": "ku_123",
  "visibility": "public"
}
```

**Values:** `private`, `shared`, `public`
**Auth:** Owner only | **Quality Check:** SHARED/PUBLIC require completed status

---

### Get Shared With Me (direct)

```http
GET /api/submissions/shared-with-me?limit=50
```

**Auth:** Authenticated user — returns entities directly shared via `SHARES_WITH`

---

### Get Shared With Me (via groups)

```http
GET /api/shared-with-me/groups?limit=50
```

**Auth:** Authenticated user — returns entities shared via `SHARED_WITH_GROUP` group membership

---

### Get Shared Users

```http
GET /api/submissions/shared-users?uid=ku_123
```

**Auth:** Owner only — returns list of users entity is shared with

---

### Browse Public Entities

```http
GET /api/submissions/public?user_uid=user_alice&limit=10
```

**Auth:** None (public content)

---

## UI Components

### Sharing Section (Entity Detail Page)

Located at `/submissions/{uid}`, visible only to owner.

**Components:**
1. **Visibility Dropdown** - Select PRIVATE/SHARED/PUBLIC
2. **Share with User Button** - Opens modal to share with individual
3. **Share with Group Button** - Opens modal to share with group
4. **Shared Users List** - Shows who has individual access
5. **Shared Groups List** - Shows which groups have access

---

### "Shared With Me" Tab (Profile Hub)

Route: `/profile/shared`

**Features:**
- Card grid of shared entities (direct shares)
- Filter tabs (All/Submissions/Activity Reports)
- Empty state message
- Owner info and metadata

---

## Service Layer

### UnifiedSharingService

```python
from core.services.sharing import UnifiedSharingService

class UnifiedSharingService:
    """Entity-agnostic sharing and visibility control.

    Works across all EntityTypes — delegates Cypher to SharingBackend,
    handles validation logic (ownership, shareable status).
    """

    # Individual sharing
    async def share(entity_uid, owner_uid, recipient_uid, role, share_version) -> Result[bool]
    async def unshare(entity_uid, owner_uid, recipient_uid) -> Result[bool]
    async def get_shared_with(entity_uid) -> Result[list[dict]]
    async def get_shared_with_me(user_uid, limit=50) -> Result[list[Any]]
    async def set_visibility(entity_uid, owner_uid, visibility) -> Result[bool]
    async def check_access(entity_uid, user_uid) -> Result[bool]
    async def verify_shareable(entity_uid) -> Result[bool]

    # Group sharing
    async def share_with_group(entity_uid, owner_uid, group_uid, share_version) -> Result[bool]
    async def unshare_from_group(entity_uid, owner_uid, group_uid) -> Result[bool]
    async def get_groups_shared_with(entity_uid) -> Result[list[dict]]
    async def get_shared_with_me_via_groups(user_uid, limit=50) -> Result[list[Any]]
```

**Location:** `core/services/sharing/unified_sharing_service.py`
**Backend:** `adapters/persistence/neo4j/domain_backends.py` — `SharingBackend(UniversalNeo4jBackend[Entity])`
**Protocol:** `core/ports/sharing_protocols.py` — `SharingOperations`
**Services field:** `services.sharing`

---

## Database Schema

### Relationship Types

```cypher
// Individual sharing
(user:User)-[:SHARES_WITH {
    shared_at: datetime(),
    role: 'teacher',
    share_version: 'original'  // 'original' | 'annotation' | 'revision' | 'both'
}]->(entity:Entity)

// Group sharing
(entity:Entity)-[:SHARED_WITH_GROUP {
    shared_at: datetime(),
    share_version: 'original'
}]->(group:Group)
```

**SHARES_WITH properties:**
- `shared_at`: Timestamp when shared
- `role`: Recipient's role (teacher/peer/mentor/viewer)
- `share_version`: What content version is shared (`"original"` | `"annotation"` | `"revision"` | `"both"`)

**SHARED_WITH_GROUP properties:**
- `shared_at`: Timestamp when shared
- `share_version`: Content version shared (same values as above)

---

## Security Considerations

### Ownership Verification

All mutation operations verify ownership before proceeding. Ownership and shareable
status are checked in a single Cypher round trip via `_verify_owned_and_shareable()`.
This mirrors the logic in `CrudOperationsMixin.verify_ownership` — returns `not_found`
for both missing entities and ownership mismatches to prevent UID enumeration.

For operations that don't need a shareable check (unshare, unshare_from_group,
set_visibility to PRIVATE), the method is called with `require_shareable=False`.

### Quality Control

Only `COMPLETED` entities can be shared (activity entities also allow `ACTIVE`).
Enforced at service layer — `verify_shareable()` for standalone checks,
or as part of the combined `_verify_owned_and_shareable()` for mutation operations.

### Access Control

All read operations use `check_access()`. Both "not found" and "forbidden" return 404 — no information leakage.

### Public Endpoint Visibility Enforcement

`GET /api/submissions/public` is unauthenticated. The route enforces `visibility == Visibility.PUBLIC` server-side — it never returns PRIVATE or SHARED submissions. Users must explicitly set an entity to PUBLIC before it appears in public listings.

### Admin Routes

`/api/activity-review/snapshot` and `/api/activity-review/submit` require `@require_admin`. The `/api/activity-review/history` route is always scoped to the calling user's own UID (no `subject_uid` override).

---

## Testing Patterns

### Unit Tests (Mocked)

```python
@pytest.fixture
def mock_backend():
    return MagicMock()

@pytest.fixture
def sharing_service(mock_backend):
    return UnifiedSharingService(backend=mock_backend)

@pytest.mark.asyncio
async def test_share_success(mock_backend, sharing_service):
    mock_backend.query_ownership_and_status = AsyncMock(
        return_value=Result.ok(
            [{"actual_owner": "user_owner", "status": "completed", "ku_type": "submission"}]
        )
    )
    mock_backend.create_share = AsyncMock(return_value=Result.ok([{"success": True}]))

    result = await sharing_service.share(...)
    assert not result.is_error
```

### Integration Tests (Real Neo4j)

```python
@pytest.mark.integration
async def test_complete_sharing_workflow(sharing_service, test_entity):
    # Set visibility → Share → Check access → Unshare → Verify revoked
    await sharing_service.set_visibility(...)
    await sharing_service.share(...)

    access = await sharing_service.check_access(...)
    assert access.value is True  # ✅ Has access

    await sharing_service.unshare(...)

    access = await sharing_service.check_access(...)
    assert access.value is False  # ✅ Access revoked
```

**See:** `tests/unit/test_unified_sharing_service.py`

---

## Common Pitfalls

### Forgetting to Set Visibility

```python
# BAD: Sharing without setting visibility to SHARED
await sharing_service.share(...)  # Creates relationship
# But entity visibility is still PRIVATE!
# User still can't access (access control checks visibility first)

# GOOD: Set visibility first
await sharing_service.set_visibility(..., Visibility.SHARED)
await sharing_service.share(...)
```

### Sharing Incomplete Entities

```python
# BAD: Trying to share a processing entity
# Returns error: "Only completed entities can be shared"
result = await sharing_service.share(...)

# GOOD: Check via verify_shareable() first
shareable = await sharing_service.verify_shareable(entity_uid)
if not shareable.is_error:
    await sharing_service.share(...)
```

### Not Handling Result[T] Errors

```python
# BAD: Assuming success
result = await sharing_service.share(...)

# GOOD: Check for errors
result = await sharing_service.share(...)
if result.is_error:
    logger.error(f"Sharing failed: {result.error}")
    return
```

---

## References

### Implementation Files
- **Backend:** `adapters/persistence/neo4j/domain_backends.py` — `SharingBackend`
- **Service:** `core/services/sharing/unified_sharing_service.py`
- **Protocol:** `core/ports/sharing_protocols.py`
- **API Routes:** `adapters/inbound/submissions_sharing_api.py`
- **Group sharing routes:** `adapters/inbound/submissions_sharing_api.py`
- **UI Components:** `adapters/inbound/submissions_ui.py`
- **Profile Tab:** `adapters/inbound/user_profile_ui.py`

### Documentation
- **ADR-038:** `/docs/decisions/ADR-038-content-sharing-model.md` — original sharing decision
- **ADR-040:** `/docs/decisions/ADR-040-teacher-assignment-workflow.md` — teacher auto-sharing
- **ADR-042:** `/docs/decisions/ADR-042-privacy-as-first-class-citizen.md` — UnifiedSharingService + group sharing
