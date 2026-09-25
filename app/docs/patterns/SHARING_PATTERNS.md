---
title: Content Sharing Patterns
updated: '2026-09-25'
category: patterns
related_skills:
- pytest
related_docs: []
---
# Content Sharing Patterns

**See Also:** [ADR-038: Content Sharing Model](../decisions/ADR-038-content-sharing-model.md), [ADR-042: Privacy as First-Class Citizen](../decisions/ADR-042-privacy-as-first-class-citizen.md)

---
## Related Skills

For implementation guidance, see:
- [@pytest](../../.claude/skills/pytest/SKILL.md)

## Overview

SKUEL's content sharing system enables users to share entities with specific users (teachers, peers, mentors) or with entire groups. The share links are the one record of who sees what (ADR-088 §4); `visibility` says only whether an entity is published.

**Service:** `UnifiedSharingService` — entity-agnostic, works across all EntityTypes.
**Protocol:** `SharingOperations` — `core/ports/sharing_protocols.py`

---

## Core Concepts

### Visibility Is Public-or-Not (ADR-088 §4)

```
PRIVATE (default) → Not published — the owner opens it, and whoever a share link names
PUBLIC            → Published (portfolio showcase; TEACHER-gated; no reader yet)
```

`Visibility` has exactly these two members. A share never writes the property: the
`SHARES_WITH` / `SHARED_WITH_GROUP` edge is the whole grant, and every read composes its
audience from those edges (`build_search_visibility_clause`, ADR-085). A spawned PS-engagement
instance is PRIVATE whatever its template's `visibility` says (`_spawn_orchestrator.py`
manages the field), and the migration
`scripts/migrations/collapse_visibility_to_public_or_not_2026_09.py` (census by default,
`--confirm` to write) rewrote the retired `shared` / `team` rows to `private`.

### Two Verbs, Two Group-Link Kinds (ADR-088)

Sharing and asking for feedback are different acts on different edges, read by different
readers that are never crossed:

```
entry ──SUBMITTED_TO_GROUP {submitted_at}──▶ Group ◀─OWNS── teacher   feedback request → review queue only
entry ──SHARED_WITH_GROUP {shared_at, share_version}──▶ Group ◀─MEMBER_OF|OWNS─   share → every member
```

- `submit_to_group()` files a feedback request. Only a `pipeline=TEACHER_REVIEW` entry writes
  one (`AudienceResolver` gates it), so the link and the pipeline always agree; on any other
  pipeline a feedback target (`teachers`, the exercise auto-target) writes **no link**. Every
  FormSubmission group target is a feedback request. The returned bool is `created` — a
  re-filed request is a success, not zero reach; only the created subset rings a teacher.
- `share_with_group()` shares with every member and owner of an active group. It never puts an
  entry in a queue.
- A teacher-side reader (the review queue and its detail, the dashboard counts, the teaching
  group pages, the exchange in teacher mode, the forms gate) reads `SUBMITTED_TO_GROUP` under
  `(teacher)-[:OWNS]->(g:Group {is_active: true})`. A member reader (`/groups`) reads
  `SHARED_WITH_GROUP` under `MEMBER_OF`. A direct `SHARES_WITH` from a teacher is a share, never
  a review grant.
- Migration: `scripts/migrations/split_submissions_from_shares_2026_09.py` (census by default,
  `--confirm` to re-type; it refuses to run while a non-`teacher_review` UserEntry still carries
  the old kind — a person rules on those rows first, deleting the edge or keeping it as a share
  with `--keep-share <entry_uid> <group_uid>`).

### Quality Control

**Only completed entities can be shared.** This prevents:
- Sharing failed entities
- Sharing entities still processing
- Low-quality portfolio content

Enforced at the service layer by `_check_shareable()` (status + entity type), applied inside
every mutation through `_verify_owned_and_shareable()` — there is no standalone pre-flight; a
mutation on an unshareable entity returns the validation error.

### Access Control — the link is the grant

There is no standalone access check. Every read composes its audience from the one
ownership/visibility chokepoint, `build_search_visibility_clause()` (ADR-085): search
strategies and by-uid visible reads admit by **edge** — `:OWNS`, `:SHARES_WITH`,
`MEMBER_OF ← SHARED_WITH_GROUP` — and the `visibility` property is never a grant. An
EntryReport is an **owner read** (ADR-088 §3): `EntryReportService.get_for_user` →
`EntryReportBackend.get_for_owner`, the OWNER_ONLY clause on the report's `user_uid` (the
student it was written for; teachers read their own artifacts on the teaching surfaces).

**Key Features:**
- Owner always has access
- A share edge grants exactly what its reader reads (a feedback request grants members
  nothing — ADR-088 §2)
- Returns 404 for both "not found" and "not yours" (no information leakage)

---

## Usage Patterns

### Pattern 1: Student-Teacher Workflow (direct share)

**Use Case:** Student submits an entry and shares it with one named person.

The audience is declared **at submit time** (ADR-054) and resolved into edges by
`AudienceResolver` — there is no separate "share" step after the entry exists, and no
visibility change: the search visibility clause admits by edge, so `share()` alone is the
grant.

```python
from core.models.user_entry.user_entry_request import UserEntryCreateRequest

student_uid = "user_alice"
teacher_uid = "user_teacher_bob"

# Step 1: Student submits with the recipient on the request. Every door builds a
# UserEntryCreateRequest and lands in UserEntryService.create_entry — the one
# convergence point. The audience is one vocabulary (AudienceSpec, ADR-088)
# on every door — the JSON body's `audience`, the /submit form's `audience`
# field, the vault's `audience:` — and a person is named `user:<username>`.
request = UserEntryCreateRequest(
    title="Assignment 3",
    content="...",
    audience=["user:teacher_bob"],
)
created = await user_entry_service.create_entry(request, user_uid=student_uid)

# Step 2 (inside create_entry): AudienceResolver.validate_references resolves
# the username to a uid and checks R8 co-membership BEFORE the entry is
# written; then resolve_and_share calls
#   sharing_service.share(entity_uid, owner_uid=student_uid, recipient_uid=teacher_uid)
# for each user: target — a SHARES_WITH edge whose MERGE re-checks
# co-membership in the statement; created_by stamped.

# Step 3: Teacher fetches shared entities
# Each item is a SharedWithMeItem (core/ports/query_types): entity DTO +
# share-edge metadata (shared_by/sharer_uid/shared_at/role/share_version) +
# resolved subject context (subject_exercise_uid/title, subject_ps_uid/title —
# which exercise the feedback is about, and its PathStep when linked). The
# /profile/shared inbox renders type-aware cards from this shape. Optional
# entity_type (EntityType) / sharer_uid narrow the inbox (arc 2 C4 filters).
shared = await sharing_service.get_shared_with_me(
    user_uid=teacher_uid,
    limit=50,
)

# The teacher's read of the entry itself goes through the edge-only search
# visibility clause (ADR-085); the report the teacher then writes is the
# STUDENT's to open (an owner read — see Access Control).
```

**UI Flow:**
1. Student: `/submit` → pick the audience (Teacher / a group / Private; Portfolio is
   disabled, "Coming soon") → submit
2. Teacher: `/profile/shared` → see the entry in the inbox → open it

Form submissions have one post-submit widening door, `POST /api/form-submissions/share`
(`FormSubmissionService.share_submission` → `share` / `share_with_group`). UserEntries have
none: a vault note widens its audience by re-syncing with a wider `audience:`, and nothing
narrows one — the revoke door is PLANNED
([`/docs/roadmap/sharing-http-door.md`](../roadmap/sharing-http-door.md)).

---

### Pattern 2: Teacher Assignment Auto-Sharing (ADR-040)

**Use Case:** Teacher assigns work to a group. When a student submits, the entry is automatically shared with the relevant group(s) so it lands in the teacher's review queue.

```python
# Step 1: Teacher creates assigned Exercise (targets a group)
# (handled by ExerciseService with scope=ASSIGNED)

# Step 2: Student submits against assigned Exercise
# UserEntryService.create_entry() → AudienceResolver auto-shares at submit time:
# - An explicit teacher:<group_uid> names the one group the request goes to
# - Otherwise (teachers, or nothing named), pipeline=teacher_review +
#   fulfills_exercise_uid files the request with the
#   INTERSECTION of the exercise's assigned groups and the submitter's memberships
#   (query_exercise_groups_for_member — prevents leaking a submission to a group
#   the submitter has no relationship with)
# - NEW 2026-07-04: when that intersection is empty AND the exercise is
#   CURRICULUM-scope (vault-authored, never group-ASSIGNED), share to the
#   submitter's default group(s) (query_default_groups_for_curriculum_submission,
#   scope-gated in Cypher so personal exercises can never leak)
# - A RevisedExercise target resolves to the exercise it revises in both lookups,
#   so a turn-in against a revision reaches the root exercise's reviewers

# Step 3: Teacher views review queue (SUBMITTED_TO_GROUP over ACTIVE groups the teacher OWNS)
queue_result = await teacher_review.get_review_queue(teacher_uid)
# → get_review_queue_by_groups: entries SUBMITTED_TO_GROUP an owned active group,
#   filtered pipeline='teacher_review'

# Step 4: Teacher provides feedback
await teacher_review.submit_report(submission_uid, teacher_uid, "Great work!")
```

**Graph Pattern:**
```cypher
// Exercise structure
(teacher:User)-[:OWNS]->(group:Group)
(student:User)-[:MEMBER_OF]->(group:Group)
(exercise:Exercise {scope: "assigned"})-[:SHARED_WITH_GROUP]->(group:Group)

// On student submission (the feedback request, filed by AudienceResolver — ADR-088 §2)
(submission:Entity)-[:FULFILLS_EXERCISE]->(exercise:Exercise)
(submission:Entity)-[:SUBMITTED_TO_GROUP {submitted_at}]->(group:Group)
```

**Key Differences from Manual Sharing:**
- No user-level `share()` / `SHARES_WITH` call — `AudienceResolver` files
  `SUBMITTED_TO_GROUP` feedback requests at submit time (never a share: classmates see
  nothing); the teacher discovers submissions via `get_review_queue()`
  (`SUBMITTED_TO_GROUP` over active groups the teacher `OWNS`, filtered
  `pipeline='teacher_review'`)
- Visibility is NOT changed — teacher access is group-relationship-gated
- Entity ownership stays with the student
- `verify_teacher_has_group_access()` — the review-write gate — requires the entry's own feedback request: `(teacher)-[:OWNS]->(g:Group {is_active:true})<-[:SUBMITTED_TO_GROUP]-(submission)` (ADR-088 §2). Sharing a classroom with the *student* is not enough; a teacher writes on exactly what the queue and the detail read let them open. Others get 404

**CLI alternative:** Teachers can bypass the web UI entirely. `scripts/export_submissions.py --teacher-uid <uid>` exports the review queue to `~/skuel-reviews/pending/<uid>.md`; after writing reports to `done/`, `scripts/import_reports.py` posts them back via the same service methods. See ADR-040.

**See:** `/docs/decisions/ADR-040-teacher-exercise-workflow.md`

---

### Pattern 3: Public Portfolio Showcase

**Use Case:** Student showcases best work publicly.

```python
from core.models.enums.metadata_enums import Visibility

# PUBLIC is written at creation: the /submit door maps audience=public and the
# vault door maps ``audience: public`` to Visibility.PUBLIC, both TEACHER-gated
# (UserEntryService._require_teacher_for_public).
request = UserEntryCreateRequest(title="Best work", content="...", visibility=Visibility.PUBLIC)

# … but nothing LISTS public entities, and the search visibility clause is edge-only
# (no read honours the property), so a PUBLIC entry reaches no one.
```

**Where this stands:** the `/submit` form's Portfolio destination renders disabled ("Coming
soon"); there is no public-listing route (ADR-038 § API Layer records the retired one). The
post-hoc writer `set_visibility()` exists and has no caller — it is PLANNED together with the
PUBLIC reader, because a visibility control without a listing writes a value nothing honours
([`/docs/roadmap/sharing-http-door.md`](../roadmap/sharing-http-door.md) § The visibility
ladder).

---

### Pattern 4: Peer Review

**Use Case:** Student shares work with classmates for feedback.

```python
# Peers are named on the create request as user:<username> (the one vocabulary,
# every door); each must share a group with the student (R8, ADR-088 §7 —
# the default group's roster does not count, its owner does). AudienceResolver
# resolves and checks every name before the entry is written, then writes one
# SHARES_WITH edge per recipient. No visibility change — the edge is the grant.
request = UserEntryCreateRequest(
    title="Draft for review",
    content="...",
    audience=["user:charlie", "user:dana", "user:eve"],
)
await user_entry_service.create_entry(request, user_uid=student_uid)

# Listing who has access — get_shared_with(entity_uid) — is written and tested but
# has no caller: it is the read half of the PLANNED revoke door.
```

---

### Pattern 5: Access Revocation (PLANNED — no door yet)

**Use Case:** Student removes teacher access after entity is graded.

`unshare()` is written and tested (`tests/integration/test_sharing_workflows.py`) but nothing
in production calls it: no route, no UI, and a vault re-sync that narrows `audience:` does not
call it either (`deferred-work.md` § Vault Re-Sync Never Retracts a Share). The door is an
operation on the existing edge — a revoke control beside the access list — never a second
share form. Ruling and trigger: [`/docs/roadmap/sharing-http-door.md`](../roadmap/sharing-http-door.md).

```python
# Unshare from teacher
unshare_result = await sharing_service.unshare(
    entity_uid=entity_uid,
    owner_uid=student_uid,
    recipient_uid=teacher_uid,
)

# The SHARES_WITH edge is gone — and the edge is the grant, so every
# edge-gated read refuses the teacher from here on.
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

# A member reads what is shared with ONE group (the groups hub —
# /api/groups/{group_uid}/shared/preview; a listed entry opens at /gradebook/{uid})
group_content = await sharing_service.get_user_entries_shared_with_group(
    user_uid=member_uid,
    group_uid="group_class_2026",
)
# A group OWNER reads across all their groups through the review queue
# (get_review_queue_by_groups) — there is no cross-group member aggregate.

# PLANNED, no caller: the owner's group access list and its revoke —
#   get_groups_shared_with(entity_uid) / unshare_from_group(entity_uid, owner_uid, group_uid)
# (/docs/roadmap/sharing-http-door.md)
```

**Graph Pattern:**
```cypher
(entity:Entity)-[:SHARED_WITH_GROUP {shared_at: datetime, share_version: 'original'}]->(group:Group)
(member:User)-[:MEMBER_OF]->(group:Group)
// → member has access to entity automatically
```

**Key advantage:** Membership changes propagate automatically — no per-user re-sharing required when the group roster changes.

**Opening what was shared (ADR-088 §3, §5):** a UserEntry opens at `/gradebook/{uid}` for
its owner or a recipient through the one by-UID read, `get_visible_to_user`, under the
domain's `read_visibility` of `OWNER_OR_AUDIENCE` — the owner arm OR the **audience
fragment** (`build_audience_fragment`): a direct `SHARES_WITH`, or `MEMBER_OF` / `OWNS` of
an **active** group the entry is `SHARED_WITH_GROUP` to. A feedback request
(`SUBMITTED_TO_GROUP`) admits nobody through it. A recipient sees the R6 card and the `.md`
download, never the status, the processed body, feedback or the exchange.

---

## API Reference

Sharing has **one** HTTP route of its own, and the audience-at-submit doors carry the rest of
the writes. Every route below is registered; the six `/api/submissions/*` sharing endpoints
and the three group-sharing endpoints ADR-038 records left with the submissions API
(2026-04-17) and have no successors.

| Door | What it does | Sharing method reached |
|------|--------------|------------------------|
| `POST /api/user-entries/upload` (the `/submit` form) and `POST /api/user-entries` (JSON `UserEntryCreateRequest`) — one `audience` in the one vocabulary: `teachers` / `teacher:<group_uid>` / `group:<uid>` / `user:<username>` / `public` / `private` (ADR-088) | Declares the audience at submit; `UserEntryService.create_entry` → `AudienceResolver.validate_references` (every target checked first) → `resolve_and_share` | `share`, `share_with_group`, `submit_to_group` |
| Vault door (`./dev vault-sync`, the Sync buttons) — a note's `audience:` frontmatter | Same request, built by `user_entry_ingestion.py`; re-sync re-declares (widens only) | `share`, `share_with_group` |
| `POST /api/form-submissions/share` — `{uid, group_uid?, recipient_uids?, share_with_admin?}` | The one post-submit widening door (form submissions only) | `share`, `share_with_group` |
| Exercise assignment (ADR-040, `ExerciseService`) | Auto-shares an ASSIGNED exercise with its group | `share_with_group` |
| `GET /profile/shared`, `GET /profile/shared/list-fragment` | The Shared-With-Me inbox (direct shares) | `get_shared_with_me` |
| `GET /api/groups/{group_uid}/shared/preview`, `GET /groups/{group_uid}` | A member's read of one group's shared entries | `get_user_entries_shared_with_group` |
| `GET /gradebook/{uid}`, `GET /gradebook/{uid}/download` | The owner's page, or a recipient's card / `.md` file | none — `UserEntryService.get_visible_to_user` composes the audience fragment (ADR-088 §5) |

**No door:** `unshare`, `unshare_from_group`, `get_shared_with`, `get_groups_shared_with`,
`set_visibility`, and a listing of `visibility = 'public'`. Ruled 2026-09-21 PLANNED as a door
that operates on the edges the rows above wrote — an access list with revoke controls, and share
reconciliation on vault re-sync — never a second share form; `set_visibility` waits on the PUBLIC
reader. [`/docs/roadmap/sharing-http-door.md`](../roadmap/sharing-http-door.md).

---

## UI Components

### Audience Selector (the `/submit` form)

`ui/user_entry/forms.py` — one destination per submission: Teacher (auto-share to the
exercise's groups), a specific group, Private (default), or Portfolio (rendered disabled,
"Coming soon" — `portfolio_mode="coming_soon"`, no caller passes `active`). This is the whole
sharing UI for a UserEntry; there is no per-entity sharing panel, no visibility dropdown and no
access list on any detail page — that surface is the PLANNED door
([`/docs/roadmap/sharing-http-door.md`](../roadmap/sharing-http-door.md)).

---

### "Shared With Me" Inbox

Route: `/profile/shared`

**Features:**
- Card grid of shared entities (direct shares), framed as a reviewing inbox
  ("shared with you for your attention" — feedback-loop UX arc 2 C4)
- FilterBar (Type · Shared by) with options derived from the live inbox,
  filtering server-side via the `/profile/shared/list-fragment` HTMX fragment
  (`get_shared_with_me(entity_type=..., sharer_uid=...)` — additive,
  parameterized WHERE filters)
- Empty state message ("no match" line when a filter empties a non-empty inbox)
- Sharer info and metadata

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
    async def unshare(entity_uid, owner_uid, recipient_uid) -> Result[bool]                       # PLANNED — no caller
    async def get_shared_with(entity_uid) -> Result[list[dict]]                                   # PLANNED — no caller
    async def get_shared_with_me(user_uid, limit=50, entity_type=None, sharer_uid=None) -> Result[list[SharedWithMeItem]]
    async def set_visibility(entity_uid, owner_uid, visibility) -> Result[bool]                   # PLANNED — waits on the PUBLIC reader

    # Group sharing
    async def share_with_group(entity_uid, owner_uid, group_uid, share_version) -> Result[bool]
    async def unshare_from_group(entity_uid, owner_uid, group_uid) -> Result[bool]               # PLANNED — no caller
    async def get_groups_shared_with(entity_uid) -> Result[list[dict]]                            # PLANNED — no caller
    async def get_user_entries_shared_with_group(user_uid, group_uid, limit=20) -> Result[list[dict]]
```

The five `PLANNED` members are registered in `scripts/detect_bloat.py` (`PLANNED_METHODS`) and
ruled in [`/docs/roadmap/sharing-http-door.md`](../roadmap/sharing-http-door.md). The
shareable rule is `_check_shareable()`, a staticmethod applied inside every mutation.

**Location:** `core/services/sharing/unified_sharing_service.py`
**Backend:** `adapters/persistence/neo4j/backends/sharing_backend.py` — `SharingBackend(UniversalNeo4jBackend[Entity])`
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

**SUBMITTED_TO_GROUP properties** (the feedback request, ADR-088 §2 — `(entry)-[:SUBMITTED_TO_GROUP]->(group)`):
- `submitted_at`: Timestamp of the first filing (a re-filed request keeps it; the MERGE returns `created = false`)

---

## Security Considerations

### Ownership Verification

All mutation operations verify ownership before proceeding. Ownership and shareable
status are checked in a single Cypher round trip via `_verify_owned_and_shareable()`.
This mirrors the logic in `CrudOperationsMixin.verify_ownership` — returns `not_found`
for both missing entities and ownership mismatches to prevent UID enumeration.

For operations that don't need a shareable check (unshare, unshare_from_group,
set_visibility to PRIVATE — the unpublish), the method is called with `require_shareable=False`.

### Quality Control

Only `COMPLETED` entities can be shared (activity entities also allow `ACTIVE`; user entries
and curriculum, any status but `ARCHIVED`). Enforced at the service layer inside
`_verify_owned_and_shareable()` on every mutation — `_check_shareable()` is the rule, and there
is no standalone pre-flight.

### Access Control

There is no standalone access check: every read composes its audience from
`build_search_visibility_clause()` (ADR-085), and an EntryReport is an owner read
(`EntryReportService.get_for_user`). Both "not found" and "not yours" return 404 — no
information leakage.

### PUBLIC Visibility

`PUBLIC` is the one published state — written at creation (TEACHER-gated at every door) or
by `set_visibility()`, which is PUBLIC-only (publish / unpublish) and has no door and no
TEACHER gate of its own yet. No read honours it: no route lists public entities — there is
no `/api/submissions/public` (ADR-038 § API Layer records the retired listing and its absent
successor).

### Admin Routes

The admin activity-review track is HTMX pages, every one `@require_admin`:
`/activity-review/queue`, `/activity-review/new`, `/activity-review/snapshot-fragment`
and `POST /activity-review/submit-feedback` (`activity_review_ui.py`). The admin names the
reviewed user through the form's `subject_uid`; `/activity-review` itself redirects to the
queue.

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
            [{"actual_owner": "user_owner", "status": "completed", "entity_type": "submission"}]
        )
    )
    mock_backend.create_share = AsyncMock(return_value=Result.ok([{"success": True}]))

    result = await sharing_service.share(...)
    assert not result.is_error
```

### Integration Tests (Real Neo4j)

```python
@pytest.mark.integration
async def test_complete_sharing_workflow(sharing_service, test_entity, neo4j_driver):
    # Share → the edge exists → Unshare → the edge is gone (no visibility step: the edge is the grant)
    await sharing_service.share(...)

    # The SHARES_WITH edge is the one record of the share (ADR-088 §3):
    # count it with Cypher — 1 after share() …
    await sharing_service.unshare(...)
    # … and 0 after unshare(). Nothing else records who was given the entity.
```

**See:** `tests/unit/test_unified_sharing_service.py`

---

## Common Pitfalls

### Assuming the `visibility` Property Is the Grant

No read honours the property. `build_search_visibility_clause()` (ADR-085 — search
strategies and by-uid visible reads) admits by **edge only**: `:OWNS`, `:SHARES_WITH`,
`MEMBER_OF ← SHARED_WITH_GROUP`; an EntryReport is an owner read (ADR-088 §3). Setting
`visibility` grants nothing to anyone — the property is public-or-not, and `PUBLIC` waits
on its first reader (a portfolio listing; `/docs/roadmap/sharing-http-door.md`).

```python
# A share() alone is the grant for every edge-gated read — no visibility change needed.
await sharing_service.share(...)

# The EntryReport writer stamps visibility: 'private' beside the student's own
# SHARES_WITH; neither is what admits the student — ownership (user_uid) is.
```

### Sharing Incomplete Entities

```python
# Sharing a processing entity returns a validation error from the mutation itself —
# _verify_owned_and_shareable() applies the rule before any write.
result = await sharing_service.share(...)
if result.is_error:
    ...  # "Only completed Ku can be shared. Current status: processing"
# There is no pre-flight to call first: a caller that already holds the entity's
# status and type can read the answer off them; the service re-checks regardless.
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
- **Backend:** `adapters/persistence/neo4j/backends/sharing_backend.py` — `SharingBackend`
- **Service:** `core/services/sharing/unified_sharing_service.py`
- **Protocol:** `core/ports/sharing_protocols.py`
- **Sharing at creation:** `adapters/inbound/user_entry_api.py` — entries are shared via the `audience` declared on create (`core/models/user_entry/audience.py`, the one vocabulary; no standalone sharing-management routes yet)
- **R8 co-membership:** `SharingBackend.build_co_membership_fragment` — the one predicate, composed by the co-member reads and the guarded person-share MERGE; the default group is named by `DEFAULT_GROUP_UID_PREFIX` (`core/models/group/group.py`)
- **Group sharing routes:** `adapters/inbound/groups_hub_routes.py` (`/api/groups/{group_uid}/shared/preview`, `/groups/{group_uid}`)
- **Audience fragment:** `adapters/persistence/neo4j/query/cypher/crud_queries.py` — `build_audience_fragment`, composed by `build_search_visibility_clause` for `OWNER_OR_AUDIENCE`
- **UI Routes:** `adapters/inbound/user_entry_ui.py` (`/gradebook/{uid}` viewer-aware, `/gradebook/{uid}/download`); the recipient card in `ui/gradebook/recipient_card.py`
- **UI Components:** `ui/user_entry/forms.py` (the audience selector on the submit form)
- **Profile Tab:** `adapters/inbound/user_profile_ui.py`

### Documentation
- **ADR-038:** `/docs/decisions/ADR-038-content-sharing-model.md` — original sharing decision
- **ADR-040:** `/docs/decisions/ADR-040-teacher-exercise-workflow.md` — teacher exercise workflow (OWNS-based review)
- **ADR-042:** `/docs/decisions/ADR-042-privacy-as-first-class-citizen.md` — UnifiedSharingService + group sharing
- **Sharing door ruling:** `/docs/roadmap/sharing-http-door.md` — the per-method PLANNED / deleted table, and why the door operates on existing edges
