---
title: Content Sharing Patterns
updated: '2026-09-26'
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
# field, a vault note's `audience:` (on the frozen copy `status: submitted`
# files — the note itself is a draft, R9) — and a person is `user:<username>`.
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

# Step 3: The recipient's Shared page lists it
# Each item is a SharedWithMeItem (core/ports/query_types): the entity DTO,
# who shared it (its owner — shared_by / sharer_uid), when, and the via-list
# (via_direct, via_groups). /profile/shared renders the R6 card from this
# shape: title, description, from, date, badge, link — never feedback.
# Optional entity_type (EntityType) / sharer_uid / via ("direct" or a group
# uid) narrow the list; the /groups hub is this reader with via=<group_uid>.
shared = await sharing_service.get_shared_with_me(
    user_uid=teacher_uid,
    limit=50,
)

# The teacher's read of the entry itself goes through the edge-only search
# visibility clause (ADR-085); the report the teacher then writes is the
# STUDENT's to open (an owner read — see Access Control).
```

**UI Flow:**
1. Student: `/submissions/submit` → pick the audience (Teacher / a group / Private; Portfolio is
   disabled, "Coming soon") → submit — or, any time later, the **Share** button on the
   entry's `/gradebook/{uid}` page (and on each version in the exchange thread), which posts
   the same vocabulary to `POST /api/user-entries/{uid}/share` (R2: anything, any time)
2. Recipient: `/profile/shared` → *Shared with you* → open it (the R6 card)
3. Owner: `/profile/shared` → *Your wall* → × Stop sharing (`POST /api/user-entries/{uid}/unshare`)

Form submissions have their own post-submit door, `POST /api/form-submissions/share`
(`FormSubmissionService.share_submission` → `share` / `share_with_group`). A vault note is a
draft and is never shared (R9): its `audience:` applies to the frozen copy `status: submitted`
files, and an idle re-sync files nothing — so nothing needs retracting on a re-sync, and a
Stop sharing on a copy stays durable (the vault door compares the fingerprint stamped at filing,
never the copy's live links).

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
from core.models.user_entry.user_entry_request import UserEntryCreateRequest

# PUBLIC is written at creation: the Submit page's audience=public, the JSON
# body's, and a vault note's copy all map to Visibility.PUBLIC, TEACHER-gated
# (UserEntryService._require_teacher_for_public).
request = UserEntryCreateRequest(title="Best work", content="...", audience="public")

# … but nothing LISTS public entities, and the search visibility clause is edge-only
# (no read honours the property), so a PUBLIC entry reaches no one.
```

**Where this stands:** the Submit page's (`/submissions/submit`) Portfolio destination renders disabled ("Coming
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

# Who has access is Your wall — get_shared_by_me(owner_uid) lists every owned
# entry with its audience (users + groups); entity_uid narrows it to one entry.
```

---

### Pattern 5: Stop Sharing (R7)

**Use Case:** The owner takes a share back — a person's or a group's.

The door is the × on an audience chip on *Your wall* (`/profile/shared`), posting
`POST /api/user-entries/{uid}/unshare` with one vocabulary value (`user:<username>` or
`group:<uid>`) → `EntrySharingService.unshare` → `unshare` / `unshare_from_group`. The delete
never touches a feedback request (`SUBMITTED_TO_GROUP` is a different link kind, ADR-088 §2).

```python
# Stop sharing with one person — by username, no co-membership needed (an owner
# may always take back what they gave)
unshare_result = await sharing_service.unshare(
    entity_uid=entity_uid,
    owner_uid=student_uid,
    recipient_username="teacher_bob",
)

# The SHARES_WITH edge is gone — and the edge is the grant, so every
# edge-gated read refuses the recipient from here on.
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

# A member reads what is shared with ONE group: the /groups hub is the
# Shared-with-you reader narrowed to that group (a listed entry opens at
# /gradebook/{uid})
group_content = await sharing_service.get_shared_with_me(
    user_uid=member_uid,
    via="group_class_2026",
)
# A group OWNER reads feedback requests across all their groups through the
# review queue (get_review_queue_by_groups) — there is no cross-group member
# aggregate beyond the Shared page itself.

# The owner's access list is Your wall; Stop sharing with the group:
await sharing_service.unshare_from_group(entity_uid, owner_uid, "group_class_2026")
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

Sharing has two doors of its own on a UserEntry — Share and Stop sharing — beside the
audience-at-submit doors that carry the rest of the writes. Every route below is registered;
the six `/api/submissions/*` sharing endpoints and the three group-sharing endpoints ADR-038
records left with the submissions API (2026-04-17) and have no successors.

| Door | What it does | Sharing method reached |
|------|--------------|------------------------|
| `POST /api/user-entries/upload` (the Submit page, `/submissions/submit`) and `POST /api/user-entries` (JSON `UserEntryCreateRequest`) — one `audience` in the one vocabulary: `teachers` / `teacher:<group_uid>` / `group:<uid>` / `user:<username>` / `public` / `private` (ADR-088) | Declares the audience at submit; `UserEntryService.create_entry` → `AudienceResolver.validate_references` (every target checked first) → `resolve_and_share` | `share`, `share_with_group`, `submit_to_group` |
| `POST /api/user-entries/{uid}/share` — `audience` = `group:<uid>` / `user:<username>` values (form, JSON or query) | The owner shares an entry they already have (R2 — any status); the Share panel on `/gradebook/{uid}` and the exchange thread's per-version Share link post here; `EntrySharingService.share` runs the create path's target checks, then the same guarded writes; a new person share publishes `EntryShared` (the recipient's bell) | `share`, `share_with_group` |
| `POST /api/user-entries/{uid}/unshare` — one `audience` value | Stop sharing (R7): × on a *Your wall* chip; never a feedback request | `unshare`, `unshare_from_group` |
| `GET /gradebook/{uid}/share-panel` | The Share panel's body: candidate groups (joined as a student or owned, active) and people (R8 co-members), the entry's current audience marked; `?preselect=reviewers` (the GradeBook nudge) checks the offered groups the entry was submitted to for feedback | `get_share_candidate_people`, `get_shared_by_me(entity_uid=…)` |
| Vault door (`./dev vault-sync`, the Sync buttons) — a note's `audience:` frontmatter + `status: submitted` | The note is a draft, never shared (R9); `status: submitted` files a frozen copy through the same request, built by `user_entry_ingestion.py`, to that audience — once per authored snapshot (the fingerprint) | `share`, `share_with_group`, `submit_to_group` |
| `POST /api/form-submissions/share` — `{uid, group_uid?, recipient_uids?, share_with_admin?}` | The forms' post-submit widening door | `share`, `share_with_group` |
| Exercise assignment (ADR-040, `ExerciseService`) | Auto-shares an ASSIGNED exercise with its group | `share_with_group` |
| `GET /profile/shared`, `GET /profile/shared/list-fragment` | The Shared page — *Shared with you* (Type · Shared by · Via filters) and *Your wall* | `get_shared_with_me`, `get_shared_by_me` |
| `GET /api/groups/{group_uid}/shared/preview`, `GET /groups/{group_uid}` | A member's read of one group's shared entries — the same reader narrowed by `via` | `get_shared_with_me(via=group_uid)` |
| `GET /gradebook/{uid}`, `GET /gradebook/{uid}/download` | The owner's page (with the Share button), or a recipient's card / `.md` file | none — `UserEntryService.get_visible_to_user` composes the audience fragment (ADR-088 §5) |

**No door:** `set_visibility` and a listing of `visibility = 'public'` — the publish /
unpublish writer waits on the PUBLIC reader
([`/docs/roadmap/sharing-http-door.md`](../roadmap/sharing-http-door.md)).

---

## UI Components

### The Submit page (`/submissions/submit`)

`ui/user_entry/forms.py` asks two questions (Submit & Share arc PR 7). **Ask for feedback?**
Teacher — the default, with or without an exercise (`teachers`, or `teacher:<group_uid>` from the
"Which class?" select a student in several classes gets when no exercise names its own) / AI —
only with an exercise, and the form says the next step is the entry page's "Request AI feedback"
button (submit never summons the reviewer) / No. **Share with** (optional, collapsed) — the
student's groups and R8 co-members as `group:<uid>` / `user:<username>` checkboxes (the Share
panel's own rows, `AudienceCheckbox`, from the same read, `EntrySharingService.targets`) plus
Portfolio (rendered disabled, "Coming soon" — `portfolio_mode="coming_soon"`, no caller passes
`active`). The pipeline and the feedback value ride as Alpine-bound hidden fields; every value
lands in the one repeated `audience` field the upload door parses. The Title field is optional:
the title is the student's, and an untitled turn-in is titled "<exercise> v<N>" by the writer.

### The Share Panel (`/gradebook/{uid}`)

`ui/gradebook/share_panel.py` — the owner's **Share** button opens an Alpine modal whose body
is HTMX-loaded from `GET /gradebook/{uid}/share-panel`: server-rendered checkboxes, one per
candidate group and person (`group:<uid>` / `user:<username>` values), the ones the entry
already reaches checked and disabled, posting to `POST /api/user-entries/{uid}/share`. The
exchange thread's per-version "Share →" link opens the page with the panel open (`?share=1`).
There is no visibility dropdown — publication waits on the PUBLIC reader.

---

### The Shared Page

Route: `/profile/shared` (`ui/profile/shared_view.py`) — two sides (R7):

- **Shared with you** — the R6 card per item (title, description, from, date, the "Shared with
  you" badge, the derived review badges, via chips, an Open link); a FilterBar (Type · Shared by · Via, options derived
  from the live list) filters server-side through the `/profile/shared/list-fragment` HTMX
  fragment (`get_shared_with_me(entity_type=..., sharer_uid=..., via=...)` — additive,
  parameterized WHERE filters). Feedback never appears here (R3).
- **Your wall** — one row per shared entry with its review badges and an audience chip per
  person and group, each with × Stop sharing (the chip posts `/api/user-entries/{uid}/unshare`
  and swaps the row). Visible to its owner only.

### Derived review badges and the nudge (R2)

The encouraged route — submit → feedback → revise → share — is promoted, never enforced
(ADR-088 §1). Two derived facts, never stored, authored once as
`build_review_standing_subquery` (`adapters/persistence/neo4j/query/cypher/learning_loop_fragments.py`)
and composed by every reader that badges an entry — the two Shared-page list statements, the
GradeBook summaries statement (on the exchange's latest entry) and the recipient card's
one-entry read (`ReportRelationshipService.get_entry_review_standing`):

- **Reviewed · Teacher / AI** — an outcome-bearing report stands on the entry (`reviewed_by` =
  the newest one's `ReportSource`).
- **Revised after feedback** — an earlier entry of the same owner in the same exchange
  (`turn_in_exercise_uid`) carries such a report older than this entry. The entry stamp is an
  ISO string and the report stamp a native datetime, so the predicate parses the entry side
  (`prior_report.created_at < datetime(entry.created_at)`) — a raw `<` is NULL.

`ui/gradebook/review_badges.py` renders them on the Shared-with-you card, the wall row and the
recipient card. The **nudge** is the GradeBook exchange line's "Share your revised work" link,
shown while the latest entry is a post-feedback revision with no share link yet
(`latest_entry_revised_after_feedback` / `latest_entry_shared`); it opens
`/gradebook/{uid}?share=1&preselect=reviewers` — the Share panel with the groups the entry was
submitted to for feedback (`ShareCandidates.reviewer_group_uids`,
`get_feedback_request_group_uids`) checked among the offered groups.

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
    async def share(entity_uid, owner_uid, recipient_uid, role, share_version, *, require_co_membership=True) -> Result[bool]  # created
    async def unshare(entity_uid, owner_uid, recipient_username) -> Result[bool]
    async def resolve_co_member(owner_uid, username) -> Result[str | None]
    async def shares_group_with(owner_uid, recipient_uid) -> Result[bool]
    async def reachable_groups(user_uid, group_uids) -> Result[frozenset[str]]
    async def set_visibility(entity_uid, owner_uid, visibility) -> Result[bool]                   # PLANNED — waits on the PUBLIC reader

    # Group sharing / the feedback request
    async def share_with_group(entity_uid, owner_uid, group_uid, share_version) -> Result[bool]
    async def unshare_from_group(entity_uid, owner_uid, group_uid) -> Result[bool]
    async def submit_to_group(entity_uid, owner_uid, group_uid) -> Result[bool]                   # created

    # The share links as the record (ADR-088 §3, §6)
    async def get_shared_with_me(user_uid, limit=50, entity_type=None, sharer_uid=None, via=None) -> Result[list[SharedWithMeItem]]
    async def get_shared_by_me(user_uid, limit=100, entity_uid=None) -> Result[list[SharedByMeItem]]
    async def get_share_candidate_people(owner_uid) -> Result[list[ShareCandidatePerson]]
```

`set_visibility` is the one `PLANNED` member (`scripts/detect_bloat.py` `PLANNED_METHODS`), ruled
in [`/docs/roadmap/sharing-http-door.md`](../roadmap/sharing-http-door.md). The shareable rule
is `_check_shareable()`, a staticmethod applied inside every mutation: a UserEntry shares in
**any** status (R2) and refuses only on `private: true` or a private pipeline.
`EntrySharingService` (`core/services/user_entry/entry_sharing_service.py`) is the Share /
Stop-sharing door over this service for a UserEntry.

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

A UserEntry shares in **any** status (R2 — anyone may share anything, any time; the encouraged
route is promoted by a badge and a nudge, never enforced) and refuses only the privacy rules.
Activity entities share when `ACTIVE` or `COMPLETED`, curriculum in any status but `ARCHIVED`,
everything else when `COMPLETED`. Enforced at the service layer inside
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

**See:** `tests/unit/test_unified_sharing_service.py`,
`tests/unit/services/user_entry/test_entry_sharing_service.py`,
`tests/integration/test_sharing_workflows.py` (the Shared-with-you union, the wall, the candidates)

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
- **Sharing at creation and after:** `adapters/inbound/user_entry_api.py` — entries are shared via the `audience` declared on create (`core/models/user_entry/audience.py`, the one vocabulary) and by `POST /api/user-entries/{uid}/share` / `/unshare` (`core/services/user_entry/entry_sharing_service.py`)
- **R8 co-membership:** `SharingBackend.build_co_membership_fragment` — the one predicate, composed by the co-member reads and the guarded person-share MERGE; the default group is named by `DEFAULT_GROUP_UID_PREFIX` (`core/models/group/group.py`)
- **Group sharing routes:** `adapters/inbound/groups_hub_routes.py` (`/api/groups/{group_uid}/shared/preview`, `/groups/{group_uid}`)
- **Audience fragment:** `adapters/persistence/neo4j/query/cypher/crud_queries.py` — `build_audience_fragment`, composed by `build_search_visibility_clause` for `OWNER_OR_AUDIENCE`
- **UI Routes:** `adapters/inbound/user_entry_ui.py` (`/gradebook/{uid}` viewer-aware with the Share button, `/gradebook/{uid}/share-panel`, `/gradebook/{uid}/download`); the recipient card in `ui/gradebook/recipient_card.py`, the Share panel in `ui/gradebook/share_panel.py`, the derived badges in `ui/gradebook/review_badges.py` and the GradeBook nudge in `ui/gradebook/summary.py`
- **UI Components:** `ui/user_entry/forms.py` (the Submit page's form — `submit_page_href()` is the one spelling of its URL)
- **The Shared page:** `adapters/inbound/user_profile_ui.py`, `ui/profile/shared_view.py`
- **The recipient's bell:** `core/events/handlers/share_notification_handler.py` (`EntryShared` → `shared_with_you`)
- **The teacher's bell:** `core/events/handlers/submission_notification_handler.py` (`UserEntryCreated.submitted_group_uids` — the created `SUBMITTED_TO_GROUP` subset — → `submission_for_review` for every owning teacher of those groups, once each, the submitter excluded; the card opens `/teaching/review/{uid}`)

### Documentation
- **ADR-038:** `/docs/decisions/ADR-038-content-sharing-model.md` — original sharing decision
- **ADR-040:** `/docs/decisions/ADR-040-teacher-exercise-workflow.md` — teacher exercise workflow (OWNS-based review)
- **ADR-042:** `/docs/decisions/ADR-042-privacy-as-first-class-citizen.md` — UnifiedSharingService + group sharing
- **Sharing door ruling:** `/docs/roadmap/sharing-http-door.md` — the per-method PLANNED / deleted table, and why the door operates on existing edges
