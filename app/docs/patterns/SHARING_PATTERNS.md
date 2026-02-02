# Content Sharing Patterns

**Status:** Phase 1 Complete (Assignments)
**Last Updated:** 2026-02-02
**See Also:** [ADR-038: Content Sharing Model](/docs/decisions/ADR-038-content-sharing-model.md)

---

## Overview

SKUEL's content sharing system enables users to share assignments and events with specific users (teachers, peers, mentors). Built on a three-level visibility model with Neo4j relationship-based access control.

**Current Support:** Assignments (Phase 1)
**Planned:** Events (Phase 2)

---

## Core Concepts

### Three-Level Visibility Model

```
PRIVATE (default) → Owner only
SHARED            → Owner + users with SHARES_WITH relationship
PUBLIC            → Anyone can view (portfolio showcase)
```

### Quality Control

**Only completed assignments can be shared.** This prevents:
- Sharing failed assignments
- Sharing assignments still processing
- Low-quality portfolio content

Enforced at service layer via `is_shareable()` method.

### Access Control Query Pattern

```cypher
MATCH (assignment:Assignment {uid: $uid})
WHERE assignment.user_uid = $current_user
   OR assignment.visibility = 'public'
   OR (assignment.visibility = 'shared' AND
       EXISTS(($current_user)-[:SHARES_WITH]->(assignment)))
RETURN assignment
```

**Key Features:**
- Owner always has access
- PUBLIC visible to everyone
- SHARED requires explicit relationship
- Returns 404 for both "not found" and "forbidden" (no information leakage)

---

## Usage Patterns

### Pattern 1: Student-Teacher Workflow

**Use Case:** Student submits assignment and shares with teacher for review.

```python
from core.services.assignments import AssignmentSharingService
from core.models.enums.metadata_enums import Visibility

# Student completes assignment (handled by submission service)
assignment_uid = "assignment_abc123"
student_uid = "user_alice"
teacher_uid = "user_teacher_bob"

# Step 1: Student sets visibility to SHARED
visibility_result = await sharing_service.set_visibility(
    assignment_uid=assignment_uid,
    owner_uid=student_uid,
    visibility=Visibility.SHARED,
)

# Step 2: Student shares with teacher
share_result = await sharing_service.share_assignment(
    assignment_uid=assignment_uid,
    owner_uid=student_uid,
    recipient_uid=teacher_uid,
    role="teacher",
)

# Step 3: Teacher fetches shared assignments
shared_assignments = await sharing_service.get_assignments_shared_with_me(
    user_uid=teacher_uid,
    limit=50,
)

# Step 4: Teacher views assignment (access control automatic)
assignment = await assignments_core_service.get_with_access_check(
    uid=assignment_uid,
    user_uid=teacher_uid,
)
```

**UI Flow:**
1. Student: `/assignments/{uid}` → Set visibility dropdown to "Shared"
2. Student: Click "Share with User" → Enter teacher UID → Submit
3. Teacher: Navigate to `/profile/shared` → See assignment in inbox
4. Teacher: Click "View" → Access assignment detail page

---

### Pattern 2: Public Portfolio Showcase

**Use Case:** Student showcases best work publicly.

```python
# Student sets assignment to PUBLIC
await sharing_service.set_visibility(
    assignment_uid="assignment_best_work",
    owner_uid="user_alice",
    visibility=Visibility.PUBLIC,
)

# Anyone can now view this assignment
# No SHARES_WITH relationship needed
access_result = await sharing_service.check_access(
    assignment_uid="assignment_best_work",
    user_uid="user_anyone",
)
assert access_result.value is True  # ✅ Public access
```

**API Endpoint:**
```http
GET /api/assignments/public?user_uid=user_alice&limit=10
```

Returns all public assignments for user's portfolio.

---

### Pattern 3: Peer Review

**Use Case:** Student shares assignment with classmates for feedback.

```python
# Share with multiple peers
peers = [
    ("user_charlie", "peer"),
    ("user_dana", "peer"),
    ("user_eve", "peer"),
]

# Set visibility to SHARED first
await sharing_service.set_visibility(
    assignment_uid=assignment_uid,
    owner_uid=student_uid,
    visibility=Visibility.SHARED,
)

# Share with each peer
for peer_uid, role in peers:
    await sharing_service.share_assignment(
        assignment_uid=assignment_uid,
        owner_uid=student_uid,
        recipient_uid=peer_uid,
        role=role,
    )

# List all users assignment is shared with
shared_users = await sharing_service.get_shared_with_users(
    assignment_uid=assignment_uid,
)
# Returns: [{"user_uid": "user_charlie", "role": "peer", ...}, ...]
```

---

### Pattern 4: Access Revocation

**Use Case:** Student removes teacher access after assignment is graded.

```python
# Unshare from teacher
unshare_result = await sharing_service.unshare_assignment(
    assignment_uid=assignment_uid,
    owner_uid=student_uid,
    recipient_uid=teacher_uid,
)

# Teacher immediately loses access
access_result = await sharing_service.check_access(
    assignment_uid=assignment_uid,
    user_uid=teacher_uid,
)
assert access_result.value is False  # ✅ Access revoked
```

---

### Pattern 5: Mentor Collaboration

**Use Case:** Student shares draft work with mentor for guidance.

```python
# Share with mentor (different role than teacher)
await sharing_service.share_assignment(
    assignment_uid="assignment_draft",
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

## API Reference

### Share Assignment

```http
POST /api/assignments/share
Content-Type: application/json

{
  "assignment_uid": "assignment_123",
  "recipient_uid": "user_teacher",
  "role": "teacher"
}
```

**Auth:** Owner only
**Quality Check:** Assignment must be completed
**Returns:** `{"success": true, "message": "..."}`

---

### Unshare Assignment

```http
POST /api/assignments/unshare
Content-Type: application/json

{
  "assignment_uid": "assignment_123",
  "recipient_uid": "user_teacher"
}
```

**Auth:** Owner only
**Returns:** `{"success": true, "message": "..."}`

---

### Set Visibility

```http
POST /api/assignments/set-visibility
Content-Type: application/json

{
  "assignment_uid": "assignment_123",
  "visibility": "public"
}
```

**Values:** `private`, `shared`, `public`
**Auth:** Owner only
**Quality Check:** SHARED/PUBLIC require completed status
**Returns:** `{"success": true, "visibility": "public"}`

---

### Get Shared With Me

```http
GET /api/assignments/shared-with-me?limit=50
```

**Auth:** Authenticated user
**Returns:** List of assignments shared with current user

```json
{
  "assignments": [
    {
      "uid": "assignment_123",
      "user_uid": "user_alice",
      "original_filename": "report.pdf",
      "status": "completed",
      "visibility": "shared",
      ...
    }
  ],
  "count": 5
}
```

---

### Get Shared Users

```http
GET /api/assignments/shared-users?uid=assignment_123
```

**Auth:** Owner only
**Returns:** List of users assignment is shared with

```json
{
  "users": [
    {
      "user_uid": "user_teacher",
      "user_name": "Teacher Bob",
      "role": "teacher",
      "shared_at": "2026-02-02T12:00:00"
    }
  ],
  "count": 1
}
```

---

### Browse Public Assignments

```http
GET /api/assignments/public?user_uid=user_alice&limit=10
```

**Auth:** None (public content)
**Returns:** Public assignments (optionally filtered by user)

---

## UI Components

### Sharing Section (Assignment Detail Page)

Located at `/assignments/{uid}`, visible only to owner.

**Components:**
1. **Visibility Dropdown** - Select PRIVATE/SHARED/PUBLIC
2. **Share Button** - Opens modal to share with user
3. **Shared Users List** - Shows who has access

**Usage:**
```python
from adapters.inbound.assignments_ui import _render_sharing_section

# In assignment detail route
sharing_section = _render_sharing_section(assignment)
```

**Features:**
- Alpine.js modal for sharing
- HTMX for instant updates
- DaisyUI styling
- Quality control: disabled for incomplete assignments

---

### "Shared With Me" Tab (Profile Hub)

Route: `/profile/shared`

**Features:**
- Card grid of shared assignments
- Filter tabs (All/Assignments/Events)
- Empty state message
- Owner info and metadata
- "View" button for each assignment

**Navigation:**
Accessible from profile hub sidebar (📥 icon).

---

## Service Layer

### AssignmentSharingService

```python
from core.services.assignments import AssignmentSharingService

class AssignmentSharingService:
    """Manages assignment sharing and access control."""

    async def share_assignment(
        self,
        assignment_uid: str,
        owner_uid: str,
        recipient_uid: str,
        role: str = "viewer",
    ) -> Result[bool]:
        """Share assignment with user."""

    async def unshare_assignment(
        self,
        assignment_uid: str,
        owner_uid: str,
        recipient_uid: str,
    ) -> Result[bool]:
        """Revoke sharing access."""

    async def set_visibility(
        self,
        assignment_uid: str,
        owner_uid: str,
        visibility: Visibility,
    ) -> Result[bool]:
        """Set visibility level."""

    async def check_access(
        self,
        assignment_uid: str,
        user_uid: str,
    ) -> Result[bool]:
        """Check if user can access assignment."""

    async def get_shared_with_users(
        self,
        assignment_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """Get users assignment is shared with."""

    async def get_assignments_shared_with_me(
        self,
        user_uid: str,
        limit: int = 50,
    ) -> Result[list[AssignmentDTO]]:
        """Get assignments shared with user."""
```

**Location:** `/core/services/assignments/assignment_sharing_service.py`

---

### Integration with Core Service

```python
from core.services.assignments import AssignmentsCoreService

# Access-controlled retrieval
assignment = await assignments_core_service.get_with_access_check(
    uid=assignment_uid,
    user_uid=current_user_uid,
)

# Returns 404 if:
# - Assignment doesn't exist
# - User doesn't have access (ownership or sharing)
```

**No information leakage:** Can't distinguish between "not found" and "no access".

---

## Database Schema

### Assignment Model

```python
@dataclass(frozen=True)
class Assignment:
    uid: str
    user_uid: str  # Owner
    visibility: Visibility = Visibility.PRIVATE  # NEW
    status: AssignmentStatus
    # ... other fields

    def is_shareable(self) -> bool:
        """Only completed assignments can be shared."""
        return self.status == AssignmentStatus.COMPLETED
```

### Relationship

```cypher
CREATE (user:User)-[r:SHARES_WITH {
    shared_at: datetime(),
    role: 'teacher'
}]->(assignment:Assignment)
```

**Properties:**
- `shared_at`: Timestamp when shared
- `role`: Recipient's role (teacher/peer/mentor/viewer)

---

## Security Considerations

### Ownership Verification

All mutation operations verify ownership:

```python
# Before sharing/unsharing/changing visibility
ownership_check = await self._verify_ownership(assignment_uid, owner_uid)
if ownership_check.is_error:
    return ownership_check  # Returns error if not owner
```

### Quality Control

```python
# Before sharing or setting visibility to SHARED/PUBLIC
shareable_check = await self._verify_shareable(assignment_uid)
if shareable_check.is_error:
    return shareable_check  # Only completed assignments can be shared
```

### Access Control

```python
# All read operations check access
access_check = await sharing_service.check_access(assignment_uid, user_uid)
if not access_check.value:
    return Result.fail(Errors.not_found("Assignment not found"))  # 404
```

**No information leakage:** Both "not found" and "forbidden" return 404.

---

## Testing Patterns

### Unit Tests (Mocked)

```python
@pytest.fixture
def mock_driver():
    driver = MagicMock()
    driver.execute_query = MagicMock()
    return driver

@pytest.mark.asyncio
async def test_share_assignment_success(sharing_service, mock_driver):
    mock_driver.execute_query.side_effect = [
        ([{"actual_owner": "user_owner"}], None, None),  # ownership check
        ([{"status": "completed"}], None, None),          # shareable check
        ([{"success": True}], None, None),                # share query
    ]

    result = await sharing_service.share_assignment(...)
    assert not result.is_error
```

### Integration Tests (Real Neo4j)

```python
@pytest.mark.integration
async def test_complete_sharing_workflow(sharing_service, test_assignment):
    # Set visibility → Share → Check access → Unshare → Verify revoked
    await sharing_service.set_visibility(...)
    await sharing_service.share_assignment(...)

    access = await sharing_service.check_access(...)
    assert access.value is True  # ✅ Has access

    await sharing_service.unshare_assignment(...)

    access = await sharing_service.check_access(...)
    assert access.value is False  # ✅ Access revoked
```

**See:** `/tests/unit/test_assignment_sharing_service.py`, `/tests/integration/test_sharing_workflows.py`

---

## Phase 2: Event Sharing (Planned)

Same infrastructure, different entity type.

**Changes Needed:**
1. Create `EventSharingService` (copy pattern from assignments)
2. Add `Event.visibility` field (already exists!)
3. Extend `/profile/shared` to include events
4. Calendar UI integration (show shared events)
5. Tests (unit + integration)

**Reusable Components:**
- Three-level visibility model
- SHARES_WITH relationship pattern
- Access control query pattern
- UI components (sharing section, inbox)

**Estimated Effort:** 4-6 hours (most work already done)

---

## Common Pitfalls

### ❌ Forgetting to Set Visibility

```python
# BAD: Sharing without setting visibility to SHARED
await sharing_service.share_assignment(...)  # Creates relationship
# But assignment visibility is still PRIVATE!
# User still can't access (access control checks visibility first)
```

```python
# GOOD: Set visibility first
await sharing_service.set_visibility(..., Visibility.SHARED)
await sharing_service.share_assignment(...)
```

### ❌ Sharing Incomplete Assignments

```python
# BAD: Trying to share processing assignment
assignment.status == "processing"
result = await sharing_service.share_assignment(...)
# Returns error: "Only completed assignments can be shared"
```

```python
# GOOD: Check is_shareable() first
if assignment.is_shareable():
    await sharing_service.share_assignment(...)
```

### ❌ Not Handling Result[T] Errors

```python
# BAD: Assuming success
result = await sharing_service.share_assignment(...)
# If result.is_error, accessing result.value will raise

# GOOD: Check for errors
result = await sharing_service.share_assignment(...)
if result.is_error:
    logger.error(f"Sharing failed: {result.error}")
    return  # Handle error
```

---

## Migration & Backward Compatibility

**Phase 1 Implementation (2026-02-02):**
- All existing assignments default to `visibility=PRIVATE`
- No breaking changes to existing routes
- Access control is additive (ownership still works)
- Service is optional (graceful degradation if not available)

**Data Migration:** None required (field has default value).

---

## References

### Implementation Files
- **Service:** `/core/services/assignments/assignment_sharing_service.py`
- **API Routes:** `/adapters/inbound/assignments_sharing_api.py`
- **UI Components:** `/adapters/inbound/assignments_ui.py`
- **Profile Tab:** `/adapters/inbound/user_profile_ui.py`
- **Model:** `/core/models/assignment/assignment.py`

### Documentation
- **ADR:** `/docs/decisions/ADR-038-content-sharing-model.md`
- **Implementation Summary:** `/PHASE1_ASSIGNMENT_SHARING_COMPLETE.md`
- **Test Documentation:** `/PHASE1_TESTS_COMPLETE.md`
- **Quick Reference:** `/CLAUDE.md` (Content Sharing section)

### Tests
- **Unit Tests:** `/tests/unit/test_assignment_sharing_service.py` (27 tests)
- **Integration Tests:** `/tests/integration/test_sharing_workflows.py` (17 tests)

---

**Last Updated:** 2026-02-02
**Status:** Phase 1 Complete ✅
**Next:** Phase 2 - Event Sharing
