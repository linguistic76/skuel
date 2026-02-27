---
title: Content Sharing Patterns
updated: '2026-02-06'
category: patterns
related_skills:
- pytest
related_docs: []
---
# Content Sharing Patterns

**Status:** Phase 1 Complete (Reports)
**Last Updated:** 2026-02-06
**See Also:** [ADR-038: Content Sharing Model](/docs/decisions/ADR-038-content-sharing-model.md)

---
## Related Skills

For implementation guidance, see:
- [@pytest](../../.claude/skills/pytest/SKILL.md)


## Overview

SKUEL's content sharing system enables users to share reports and events with specific users (teachers, peers, mentors). Built on a three-level visibility model with Neo4j relationship-based access control.

**Current Support:** Reports (Phase 1)
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

**Only completed reports can be shared.** This prevents:
- Sharing failed reports
- Sharing reports still processing
- Low-quality portfolio content

Enforced at service layer via `is_shareable()` method.

### Access Control Query Pattern

```cypher
MATCH (report:Report {uid: $uid})
WHERE report.user_uid = $current_user
   OR report.visibility = 'public'
   OR (report.visibility = 'shared' AND
       EXISTS(($current_user)-[:SHARES_WITH]->(report)))
RETURN report
```

**Key Features:**
- Owner always has access
- PUBLIC visible to everyone
- SHARED requires explicit relationship
- Returns 404 for both "not found" and "forbidden" (no information leakage)

---

## Usage Patterns

### Pattern 1: Student-Teacher Workflow

**Use Case:** Student submits report and shares with teacher for review.

```python
from core.services.reports import ReportSharingService
from core.models.enums.metadata_enums import Visibility

# Student completes report (handled by submission service)
report_uid = "report_abc123"
student_uid = "user_alice"
teacher_uid = "user_teacher_bob"

# Step 1: Student sets visibility to SHARED
visibility_result = await sharing_service.set_visibility(
    report_uid=report_uid,
    owner_uid=student_uid,
    visibility=Visibility.SHARED,
)

# Step 2: Student shares with teacher
share_result = await sharing_service.share_report(
    report_uid=report_uid,
    owner_uid=student_uid,
    recipient_uid=teacher_uid,
    role="teacher",
)

# Step 3: Teacher fetches shared reports
shared_reports = await sharing_service.get_reports_shared_with_me(
    user_uid=teacher_uid,
    limit=50,
)

# Step 4: Teacher views report (access control automatic)
report = await reports_core_service.get_with_access_check(
    uid=report_uid,
    user_uid=teacher_uid,
)
```

**UI Flow:**
1. Student: `/submissions/{uid}` → Set visibility dropdown to "Shared"
2. Student: Click "Share with User" → Enter teacher UID → Submit
3. Teacher: Navigate to `/profile/shared` → See report in inbox
4. Teacher: Click "View" → Access report detail page

---

### Pattern 2: Teacher Assignment Auto-Sharing (ADR-040)

**Use Case:** Teacher assigns work to a group. When a student submits, the report is automatically shared with the assigning teacher.

```python
from core.services.reports import SubmissionsCoreService, TeacherReviewService

# Step 1: Teacher creates assigned Assignment (targets a group)
# (handled by AssignmentService.create_project with scope=ASSIGNED)

# Step 2: Student submits report against assigned project
# Auto-sharing happens inside process_assignment_submission()
await reports_core_service.process_assignment_submission(
    report_uid=report_uid,
    project_uid=project_uid,
    student_uid=student_uid,
)
# This automatically:
# - Creates FULFILLS_PROJECT relationship (report → project)
# - Creates SHARES_WITH {role: "teacher"} relationship (teacher → report)
# - Sets status to MANUAL_REVIEW for HUMAN/HYBRID processor types

# Step 3: Teacher views review queue
queue_result = await teacher_review.get_review_queue(teacher_uid)

# Step 4: Teacher provides feedback
await teacher_review.submit_feedback(report_uid, teacher_uid, "Great work!")
# OR
await teacher_review.request_revision(report_uid, teacher_uid, "Please expand section 2")
# OR
await teacher_review.approve_report(report_uid, teacher_uid)
```

**Graph Pattern:**
```cypher
// Assignment structure
(teacher:User)-[:OWNS]->(group:Group)
(student:User)-[:MEMBER_OF]->(group:Group)
(project:Assignment {scope: "assigned"})-[:FOR_GROUP]->(group:Group)

// On student submission (auto-created)
(report:Entity)-[:FULFILLS_PROJECT]->(project:Assignment)
(teacher:User)-[:SHARES_WITH {role: "teacher"}]->(report:Report)
```

**Key Differences from Manual Sharing:**
- No explicit `share_report()` call — auto-created on submission
- Visibility is NOT changed to SHARED — teacher access is via SHARES_WITH regardless
- Report ownership stays with the student
- Teacher's review queue = `SHARES_WITH` filtered by `role="teacher"` and pending status

**See:** `/docs/decisions/ADR-040-teacher-assignment-workflow.md`

---

### Pattern 3: Public Portfolio Showcase

**Use Case:** Student showcases best work publicly.

```python
# Student sets report to PUBLIC
await sharing_service.set_visibility(
    report_uid="report_best_work",
    owner_uid="user_alice",
    visibility=Visibility.PUBLIC,
)

# Anyone can now view this report
# No SHARES_WITH relationship needed
access_result = await sharing_service.check_access(
    report_uid="report_best_work",
    user_uid="user_anyone",
)
assert access_result.value is True  # ✅ Public access
```

**API Endpoint:**
```http
GET /api/submissions/public?user_uid=user_alice&limit=10
```

Returns all public reports for user's portfolio.

---

### Pattern 4: Peer Review

**Use Case:** Student shares report with classmates for feedback.

```python
# Share with multiple peers
peers = [
    ("user_charlie", "peer"),
    ("user_dana", "peer"),
    ("user_eve", "peer"),
]

# Set visibility to SHARED first
await sharing_service.set_visibility(
    report_uid=report_uid,
    owner_uid=student_uid,
    visibility=Visibility.SHARED,
)

# Share with each peer
for peer_uid, role in peers:
    await sharing_service.share_report(
        report_uid=report_uid,
        owner_uid=student_uid,
        recipient_uid=peer_uid,
        role=role,
    )

# List all users report is shared with
shared_users = await sharing_service.get_shared_with_users(
    report_uid=report_uid,
)
# Returns: [{"user_uid": "user_charlie", "role": "peer", ...}, ...]
```

---

### Pattern 5: Access Revocation

**Use Case:** Student removes teacher access after report is graded.

```python
# Unshare from teacher
unshare_result = await sharing_service.unshare_report(
    report_uid=report_uid,
    owner_uid=student_uid,
    recipient_uid=teacher_uid,
)

# Teacher immediately loses access
access_result = await sharing_service.check_access(
    report_uid=report_uid,
    user_uid=teacher_uid,
)
assert access_result.value is False  # ✅ Access revoked
```

---

### Pattern 6: Mentor Collaboration

**Use Case:** Student shares draft work with mentor for guidance.

```python
# Share with mentor (different role than teacher)
await sharing_service.share_report(
    report_uid="report_draft",
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

### Share Report

```http
POST /api/submissions/share
Content-Type: application/json

{
  "report_uid": "report_123",
  "recipient_uid": "user_teacher",
  "role": "teacher"
}
```

**Auth:** Owner only
**Quality Check:** Report must be completed
**Returns:** `{"success": true, "message": "..."}`

---

### Unshare Report

```http
POST /api/submissions/unshare
Content-Type: application/json

{
  "report_uid": "report_123",
  "recipient_uid": "user_teacher"
}
```

**Auth:** Owner only
**Returns:** `{"success": true, "message": "..."}`

---

### Set Visibility

```http
POST /api/submissions/set-visibility
Content-Type: application/json

{
  "report_uid": "report_123",
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
GET /api/submissions/shared-with-me?limit=50
```

**Auth:** Authenticated user
**Returns:** List of reports shared with current user

```json
{
  "reports": [
    {
      "uid": "report_123",
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
GET /api/submissions/shared-users?uid=report_123
```

**Auth:** Owner only
**Returns:** List of users report is shared with

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

### Browse Public Reports

```http
GET /api/submissions/public?user_uid=user_alice&limit=10
```

**Auth:** None (public content)
**Returns:** Public reports (optionally filtered by user)

---

## UI Components

### Sharing Section (Report Detail Page)

Located at `/submissions/{uid}`, visible only to owner.

**Components:**
1. **Visibility Dropdown** - Select PRIVATE/SHARED/PUBLIC
2. **Share Button** - Opens modal to share with user
3. **Shared Users List** - Shows who has access

**Usage:**
```python
from adapters.inbound.reports_ui import _render_sharing_section

# In report detail route
sharing_section = _render_sharing_section(report)
```

**Features:**
- Alpine.js modal for sharing
- HTMX for instant updates
- DaisyUI styling
- Quality control: disabled for incomplete reports

---

### "Shared With Me" Tab (Profile Hub)

Route: `/profile/shared`

**Features:**
- Card grid of shared reports
- Filter tabs (All/Reports/Events)
- Empty state message
- Owner info and metadata
- "View" button for each report

**Navigation:**
Accessible from profile hub sidebar (icon).

---

## Service Layer

### ReportSharingService

```python
from core.services.reports import ReportSharingService

class ReportSharingService:
    """Manages report sharing and access control."""

    async def share_report(
        self,
        report_uid: str,
        owner_uid: str,
        recipient_uid: str,
        role: str = "viewer",
    ) -> Result[bool]:
        """Share report with user."""

    async def unshare_report(
        self,
        report_uid: str,
        owner_uid: str,
        recipient_uid: str,
    ) -> Result[bool]:
        """Revoke sharing access."""

    async def set_visibility(
        self,
        report_uid: str,
        owner_uid: str,
        visibility: Visibility,
    ) -> Result[bool]:
        """Set visibility level."""

    async def check_access(
        self,
        report_uid: str,
        user_uid: str,
    ) -> Result[bool]:
        """Check if user can access report."""

    async def get_shared_with_users(
        self,
        report_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """Get users report is shared with."""

    async def get_reports_shared_with_me(
        self,
        user_uid: str,
        limit: int = 50,
    ) -> Result[list[ReportDTO]]:
        """Get reports shared with user."""
```

**Location:** `/core/services/submissions/ + core/services/feedback/report_sharing_service.py`

---

### Integration with Core Service

```python
from core.services.reports import SubmissionsCoreService

# Access-controlled retrieval
report = await reports_core_service.get_with_access_check(
    uid=report_uid,
    user_uid=current_user_uid,
)

# Returns 404 if:
# - Report doesn't exist
# - User doesn't have access (ownership or sharing)
```

**No information leakage:** Can't distinguish between "not found" and "no access".

---

## Database Schema

### Report Model

```python
@dataclass(frozen=True)
class Report:
    uid: str
    user_uid: str  # Owner
    visibility: Visibility = Visibility.PRIVATE  # NEW
    status: ReportStatus
    # ... other fields

    def is_shareable(self) -> bool:
        """Only completed reports can be shared."""
        return self.status == ReportStatus.COMPLETED
```

### Relationship

```cypher
CREATE (user:User)-[r:SHARES_WITH {
    shared_at: datetime(),
    role: 'teacher'
}]->(report:Report)
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
ownership_check = await self._verify_ownership(report_uid, owner_uid)
if ownership_check.is_error:
    return ownership_check  # Returns error if not owner
```

### Quality Control

```python
# Before sharing or setting visibility to SHARED/PUBLIC
shareable_check = await self._verify_shareable(report_uid)
if shareable_check.is_error:
    return shareable_check  # Only completed reports can be shared
```

### Access Control

```python
# All read operations check access
access_check = await sharing_service.check_access(report_uid, user_uid)
if not access_check.value:
    return Result.fail(Errors.not_found("Report not found"))  # 404
```

**No information leakage:** Both "not found" and "forbidden" return 404.

---

## Testing Patterns

### Unit Tests (Mocked)

```python
@pytest.fixture
def mock_driver():
    driver = MagicMock()
    driver.execute_query = AsyncMock()  # AsyncMock required — service awaits execute_query
    return driver

@pytest.mark.asyncio
async def test_share_report_success(sharing_service, mock_driver):
    mock_driver.execute_query.side_effect = [
        ([{"actual_owner": "user_owner"}], None, None),  # ownership check
        ([{"status": "completed"}], None, None),          # shareable check
        ([{"success": True}], None, None),                # share query
    ]

    result = await sharing_service.share_report(...)
    assert not result.is_error
```

### Integration Tests (Real Neo4j)

```python
@pytest.mark.integration
async def test_complete_sharing_workflow(sharing_service, test_report):
    # Set visibility → Share → Check access → Unshare → Verify revoked
    await sharing_service.set_visibility(...)
    await sharing_service.share_report(...)

    access = await sharing_service.check_access(...)
    assert access.value is True  # ✅ Has access

    await sharing_service.unshare_report(...)

    access = await sharing_service.check_access(...)
    assert access.value is False  # ✅ Access revoked
```

**See:** `/tests/unit/test_report_sharing_service.py`, `/tests/integration/test_sharing_workflows.py`

---

## Phase 2: Event Sharing (Planned)

Same infrastructure, different entity type.

**Changes Needed:**
1. Create `EventSharingService` (copy pattern from reports)
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

### Forgetting to Set Visibility

```python
# BAD: Sharing without setting visibility to SHARED
await sharing_service.share_report(...)  # Creates relationship
# But report visibility is still PRIVATE!
# User still can't access (access control checks visibility first)
```

```python
# GOOD: Set visibility first
await sharing_service.set_visibility(..., Visibility.SHARED)
await sharing_service.share_report(...)
```

### Sharing Incomplete Reports

```python
# BAD: Trying to share processing report
report.status == "processing"
result = await sharing_service.share_report(...)
# Returns error: "Only completed reports can be shared"
```

```python
# GOOD: Check is_shareable() first
if report.is_shareable():
    await sharing_service.share_report(...)
```

### Not Handling Result[T] Errors

```python
# BAD: Assuming success
result = await sharing_service.share_report(...)
# If result.is_error, accessing result.value will raise

# GOOD: Check for errors
result = await sharing_service.share_report(...)
if result.is_error:
    logger.error(f"Sharing failed: {result.error}")
    return  # Handle error
```

---

## Migration & Backward Compatibility

**Phase 1 Implementation (2026-02-02):**
- All existing reports default to `visibility=PRIVATE`
- No breaking changes to existing routes
- Access control is additive (ownership still works)
- Service is optional (graceful degradation if not available)

**Data Migration:** None required (field has default value).

---

## References

### Implementation Files
- **Service:** `/core/services/submissions/ + core/services/feedback/report_sharing_service.py`
- **API Routes:** `/adapters/inbound/reports_sharing_api.py`
- **UI Components:** `/adapters/inbound/reports_ui.py`
- **Profile Tab:** `/adapters/inbound/user_profile_ui.py`
- **Model:** `/core/models/report/report.py`

### Documentation
- **ADR:** `/docs/decisions/ADR-038-content-sharing-model.md`
- **Implementation Summary:** `/PHASE1_REPORT_SHARING_COMPLETE.md`
- **Test Documentation:** `/PHASE1_TESTS_COMPLETE.md`
- **Quick Reference:** `/CLAUDE.md` (Content Sharing section)

### Tests
- **Unit Tests:** `/tests/unit/test_report_sharing_service.py` (27 tests)
- **Integration Tests:** `/tests/integration/test_sharing_workflows.py` (12 tests)

---

**Last Updated:** 2026-02-06
**Status:** Phase 1 Complete
**Next:** Phase 2 - Event Sharing
