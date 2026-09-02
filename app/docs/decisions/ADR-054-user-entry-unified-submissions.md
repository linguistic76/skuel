---
updated: 2026-09-02
---

# ADR-054: UserEntry — Unified User-Authored Content

**Status:** Accepted
**Date:** 2026-04-14
**Supersedes:** The `Submission`/`ExerciseSubmission` and `JeInput`/`JeOutput`
entity type split. Revises the "learning loop" framing of ADR-040.
**Related:** [ADR-038 Content Sharing Model](ADR-038-content-sharing-model.md),
[ADR-040 Teacher Exercise Workflow](ADR-040-teacher-exercise-workflow.md),
[ADR-053 Groups First-Class and Unified Sharing](ADR-053-groups-first-class-and-unified-sharing.md)

> **Execution note (2026-04-17).** Executed as a disciplined commit sequence
> on the `adr-054-user-entry` branch. The three-phase rollout in
> §Rollout is superseded by One Path Forward — shims and label-inclusive
> reads were not built. Activity extraction from the journal pipeline was
> dropped; journals no longer auto-create Tasks/Goals via DSL.
>
> **The collapse is fully landed in code; see the [Postscript](#postscript-2026-06-02)
> for execution outcomes and one material divergence from §5 (rich journaling
> has since been abandoned). The body below is preserved as the decision record
> — its decision-time service/backend names (`SubmissionsBackend`,
> `submissions_processing_service.py`, …) were accurate when written and are
> deliberately not back-renamed.**

## Context

ADR-053 unified the teacher → student direction of curriculum sharing on a
single mechanism: `SHARED_WITH_GROUP`. Exercise, PathStep, and LearningPath
all reach students through `UnifiedSharingService`. The graph is symmetric at
the curriculum end.

The student → teacher direction is not. Today, a student who wants to turn
in work creates an `ExerciseSubmission` whose audience is implicit — inferred
by traversal from `(Submission)-[:FULFILLS_EXERCISE]->(Exercise)-[:SHARED_WITH_GROUP]->(Group)`
plus a route-level role check. Audience is never declared by the student.

Worse, the entity type hierarchy itself is cosmetic:

- `ExerciseSubmission` adds **zero unique fields** beyond `Submission`
  (`core/models/submissions/exercise_submission.py:29-35`).
- `Submission` adds 13 fields to `UserOwnedEntity` (4 file, 8 processing,
  `modality`, `revision_number`). But `JeInput` reimplements the same 13
  fields directly on `UserOwnedEntity` without a `Submission` base
  (`core/models/journal/je_input.py`). Two parallel code paths for the same <!-- historical -->
  concept: "user-authored content with files and optional processing."
- Processing dispatch in `submissions_processing_service.py:321` reads
  `entity_type == JE_INPUT` as a flag for "run the journal LLM" —
  the *only* place in submissions processing where the type discriminator
  drives behavior. Every other signal is `file_type` (MIME) or `instructions`
  dict.

The "learning loop" framing (Exercise → Submission → Report → RevisedExercise)
has been load-bearing in documentation but not in code. The Cypher queries
that implement it match on relationships, not type labels:

- `FULFILLS_EXERCISE` anchors a submission to an exercise — type-agnostic
- `REPORT_FOR` links a report to a submission — type-agnostic
- `RESPONDS_TO_REPORT` / `REVISES_EXERCISE` on revised exercises — type-agnostic
- `RECORDS` on interactions — type-agnostic

The loop exists in the graph as a set of edges. The entity type hierarchy is
scaffolding that was never load-bearing. SKUEL's bottom-up philosophy calls
for removing it.

## Decision

Introduce a single user-authored content type, **`UserEntry`**, that replaces
`Submission`, `ExerciseSubmission`, `JeInput`, and `JeOutput`. Dispatch and
audience become two independent dimensions, both encoded on the entry rather
than inferred from its type.

### 1. `UserEntry(UserOwnedEntity)` — one type for user-authored content

Fields (the union of the current Submission + JeInput carriers):

- **Identity + content:** inherited from Entity (uid, title, summary,
  description, content, metadata, tags, ...)
- **Ownership + visibility:** inherited from UserOwnedEntity (user_uid,
  visibility, priority)
- **File metadata fields:** `original_filename`, `file_path`, `file_size`, `file_type` —
  nullable; text-only entries omit them
- **Processing:** `pipeline` (new enum, see §2), `processing_started_at`,
  `processing_completed_at`, `processing_error`, `processed_content`,
  `processed_file_path`, `instructions`, `max_retention`
- **Modality:** `modality` is kept as a field — it describes *how* the
  content was entered (voice, text, upload), which affects UI rendering and
  is orthogonal to pipeline.
- **Lineage:** `revision_number` moves to a property on the
  `FULFILLS_EXERCISE` edge (`{revision: 2}`) instead of being a field on the
  entry. Revision count is a lineage concern, not a content concern.
- **Journal-specific metadata** (mood, energy level, source type, etc. that
  `JeInput` currently carries) moves into the generic `metadata` dict
  inherited from Entity. No information is lost; the dict is where
  type-specific extensions belong.

Entity type: `EntityType.USER_ENTRY`, NeoLabel `UserEntry`, UID prefix `ue`.
`EntityType.EXERCISE_SUBMISSION`, `EntityType.JE_INPUT`, and
`EntityType.JE_OUTPUT` are deleted — the enum shrinks by 2 net (3 removed,
1 added). `Submission` is a Python abstract base class, not an entity type;
deleting it is a code-level collapse, not an enum change.

**Scope note on `RevisedExercise`:** `RevisedExercise` (added in
ADR-053-era) stays as a separate entity type. It is teacher-authored
curriculum targeting a specific student's revision cycle — not user content
authored at submit time. Its relationships (`REVISES_EXERCISE`,
`RESPONDS_TO_REPORT`) continue to point at `UserEntry` nodes downstream,
just as they point at `ExerciseSubmission` nodes today. This ADR's collapse
and RevisedExercise's continued independence are the same principle applied
twice: **entity names are nouns, edges are verbs, variants are enums**; a new
EntityType is justified only when the name reads as a distinct kind-of-thing
*and* the hierarchy / ownership / `ContentOrigin` tier genuinely differs.
`UserEntry` failed the second test for the three collapsed types (same
hierarchy, same ownership) — hence the collapse. `RevisedExercise` passes
both tests. **See:** [`/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md § Naming Convention`](../architecture/ENTITY_TYPE_ARCHITECTURE.md#naming-convention).

**Scope note on `Interaction`:** `UserEntryService` inherits the current
behavior of `SubmissionsService`: an `Interaction` node is auto-created at
submit time, capturing `context_path_step_uid` + `context_learning_path_uid`
from `UserContext` via `RECORDS`/`INTERACTION_DURING`/`INTERACTION_WITHIN`
edges. The audit trail is unchanged.

### 2. Pipeline enum — what the system should *do* with the entry

`core/models/enums/pipeline.py` introduces:

```python
class Pipeline(StrEnum):
    NONE = "none"                              # passthrough, no processing
    TRANSCRIBE = "transcribe"                  # audio -> text (Deepgram)
    TRANSCRIBE_AND_STRUCTURE = "transcribe_and_structure"  # audio -> text -> journal LLM (legacy)
    LLM_SUMMARY = "llm_summary"                # text/file -> LLM summary
    TEACHER_REVIEW = "teacher_review"          # route to review queue, no processing
    EXTRACT_ACTIVITIES = "extract_activities"  # text -> DSL parse -> real entities (ADR-069)
    JOURNAL = "journal"                        # Journals domain; processed interactively in UI
```

The existing `ProcessorType` enum (`LLM`/`HUMAN`/`HYBRID`/`AUTOMATIC`) was
conflating two concerns: *what processing step happened* and *who/what
generated this*. This ADR splits them:

- **`Pipeline`** (new) — declares what `UserEntry` processing should do.
  Replaces `ProcessorType` for user-entry dispatch.
- **`ReportSource`** (new, `HUMAN` / `LLM` / `AUTOMATIC` / `HYBRID`) —
  describes the source of a `Report` (ExerciseReport, ActivityReport).
  Absorbs the remaining meaning of `ProcessorType`.

`ProcessorType` is deleted. All callers migrate to `Pipeline` or
`ReportSource` based on context.

Pipeline is chosen at submit time (a form field, a default on the Exercise
for ASSIGNED flows, or declared via YAML ingestion). The processing service
(`submissions_processing_service.py`) dispatches on `entry.pipeline` instead
of on `entity_type` + `file_type`.

### 3. Audience — declared at submit time as first-class edges

`UserEntry` is shared via `UnifiedSharingService` at creation time. The
submit form offers four audience options, any combination:

- **Teacher** (default for ASSIGNED exercises) — resolves to
  `SHARED_WITH_GROUP` with the Exercise's assigned groups.
- **Group** — direct `SHARED_WITH_GROUP` to one or more of the student's
  groups.
- **Peer** — `SHARED_WITH` to a specific user.
- **Public** — `visibility=PUBLIC`.

`UnifiedSharingService._check_shareable` admits `user_entry` at any
non-archived status. For ASSIGNED exercise flows, the submission pipeline
defaults `pipeline=TEACHER_REVIEW` and audience to the Exercise's groups;
the student can widen the audience but not silently submit to nobody.

**YAML ingestion (`/upload`) uses the same pipeline.** When
`ingest_file()` detects `type: user_entry`, it delegates to
`core/services/ingestion/user_entry_ingestion.py`, which builds a
`UserEntryCreateRequest` and calls `UserEntryService.create_entry()` —
the same entry point the `/submit` form uses. YAML files declare a
required `pipeline:` field and an optional `audience:` field:

| YAML `audience:` | Effect |
|------------------|--------|
| `teachers` (default) | Expand to the uploader's student-role group memberships via `AudienceResolver.resolve_default_teachers()`. Zero groups → no shares (no silent broadcast). |
| `group:<uid>` | `SHARED_WITH_GROUP` with one specific group. |
| `public` | `visibility=PUBLIC`. |
| `private` | No shares, no visibility change. |

*Amended 2026-09-02: `knowledge` (ADR-073's developed-files doorway) defaults to `private` when
`audience:` is omitted — `Pipeline.shares_by_default()`. The `teachers` default is submission
semantics and stays for the submission-shaped pipelines.*

`AudienceResolver` (`core/services/user_entry/audience_resolver.py`) is
the shared home for audience validation, share fan-out, and default-
teacher expansion. Both the form and the ingestion bridge hold the same
resolver instance — there is no second code path. Audio pipelines
(`TRANSCRIBE`, `TRANSCRIBE_AND_STRUCTURE`) are rejected by `/upload`
because the path is YAML-only; audio uploads keep the dedicated audio-
upload flow. Legacy type strings `exercise_submission` / `je_input` /
`je_output` are rejected in `detector.py` with an ADR-054 error — no
compat shim (One Path Forward).

### 4. Context edges — optional, type-agnostic

What an entry "is for" is encoded as optional outgoing relationships:

| Edge | Meaning |
|---|---|
| `FULFILLS_EXERCISE` | This entry responds to an Exercise (makes it a "submission") |
| `TRANSFORMS` | This entry is the processed output of another entry (journal input → output) |
| `ABOUT_PATH_STEP` | This entry is about a specific PathStep (study note, reflection) |
| (future) | Add edges as new contexts emerge — each one is opt-in |

No entry is required to have any of these. An entry with no context edges
and `visibility=PRIVATE` is just a personal note. An entry with
`FULFILLS_EXERCISE` + `SHARED_WITH_GROUP` is an exercise turn-in. An entry
with `TRANSFORMS` pointing at another entry is a processed output. Same type,
different meanings, encoded in the graph.

### 5. Journal input → output, preserved

The current `JeInput` → `TRANSFORMS` → `JeOutput` pattern survives the
collapse. Audio submission:

1. User creates `UserEntry` with `pipeline=TRANSCRIBE_AND_STRUCTURE`, audio
   file attached.
2. `UserEntryProcessingService` dispatches on pipeline: runs Deepgram,
   then runs the journal LLM, produces a **second** `UserEntry` (the
   structured output) with `pipeline=NONE`.
3. The processed entry is linked to the raw entry by
   `(output)-[:TRANSFORMS]->(input)`.

**Journal is PRIVATE by policy.** Preserving the historical
`JeInput`/`JeOutput` norm, a `UserEntry` on `pipeline=TRANSCRIBE_AND_STRUCTURE`
is not shareable at submit time. `Pipeline.allows_sharing()` encodes this:
it returns `False` only for `TRANSCRIBE_AND_STRUCTURE`. `_validate_audience`
rejects the create request if it carries `share_with_groups`,
`share_with_users`, `auto_share_to_exercise_groups=True`, or any
non-`PRIVATE` visibility. The `/submit` form hides the audience picker
client-side when the student selects the journal pipeline; the dedicated
`/journals/submit` form never offered one. The child `UserEntry` persisted
in phase 3 is explicitly `visibility=PRIVATE` and inherits nothing from
the source's (rejected) audience.

A student can still widen reach **after the fact** by sharing the
structured output entry through the normal `UnifiedSharingService` flow —
the policy gates the submit-time audience, not the entry's lifetime
audience. All other pipelines (`NONE`, `TRANSCRIBE`, `LLM_SUMMARY`,
`TEACHER_REVIEW`) are shareable at submit time.

Two `UserEntry` nodes, one `TRANSFORMS` edge. Same shape as today, half the
type surface.

### 6. Review queue and teacher authority, simplified

`SubmissionsBackend.get_review_queue()` becomes a single graph pattern
symmetric with ADR-053:

```cypher
MATCH (teacher:User {user_uid: $teacher_uid})-[:OWNS]->(g:Group)
MATCH (entry:Entity:UserEntry)-[:SHARED_WITH_GROUP]->(g)
WHERE entry.pipeline = 'teacher_review'
  AND entry.status IN ['submitted', 'needs_revision']
RETURN entry, g
```

`verify_teacher_authority()` collapses into `sharing_service.check_access()`.
Role gates remain on *write* operations (only teachers can create
`ExerciseReport` nodes) but not on visibility — visibility is
`SHARED_WITH_GROUP`.

### 7. Learning-loop chain preserved (as emergent relationships)

`FULFILLS_EXERCISE`, `RESPONDS_TO_REPORT`, `REVISES_EXERCISE`, `REPORT_FOR`,
and `RECORDS` remain unchanged. They now point at `UserEntry` nodes instead
of `ExerciseSubmission` nodes. Because the Cypher already matches on
relationships rather than types, the queries do not need logic changes —
only label updates.

`revision_number` moves from a field to an edge property on
`FULFILLS_EXERCISE` (`{revision: 2}`). More graph-honest: "which attempt is
this" is a property of the relationship to the exercise, not a property of
the content itself.

The `/explore/ps/{uid}` learning-loop UI fragments in `ui/learning_loop/`
keep working — they already traverse relationships, not types
(`submissions_section.py:6` uses
`(user)-[:OWNS]->(sub)-[:RECORDS]<-(interaction)-[:INTERACTION_DURING]->(ps)`,
type-agnostic).

## Consequences

### Positive

- **One type where there were four.** `Submission`, `ExerciseSubmission`,
  `JeInput`, `JeOutput` → `UserEntry`. Corresponding services, backends,
  DTOs, request models, events, tests collapse to a single surface.
- **Dispatch is explicit and data-driven.** `pipeline` field replaces a
  scattered mix of `entity_type` branches, `file_type` sniffs, and
  `instructions` dict flags.
- **Audience becomes a first-class choice.** Students can submit a work
  product to a teacher, share a reflection with a peer, and post to a group
  feed — all through the same mechanism, all at submit time.
- **Peer review, class posts, and public portfolios are free.** The edges
  and the `UnifiedSharingService` API already exist; they just weren't
  wired to submissions.
- **Learning loop becomes emergent.** The pedagogical loop exists as a
  pattern of optional relationships, not as an entity-type hierarchy. New
  pedagogical patterns can add new context edges without new types.
- **`ProcessorType` is split into two semantically-correct enums.**
  `Pipeline` (user-entry processing) and `ReportSource` (report provenance).
- **Graph is more honest.** The `JeInput`/`ExerciseSubmission` split was
  cosmetic; removing it matches what the Cypher already believed.

### Negative

- **Migration is the largest piece of code work.** Every
  `:Submission`/`:ExerciseSubmission`/`:JeInput`/`:JeOutput` node gets
  relabeled to `:UserEntry` with a `pipeline` field backfilled. One-shot
  Cypher script. Existing relationships (`FULFILLS_EXERCISE`, `TRANSFORMS`,
  `REPORT_FOR`, etc.) are preserved unchanged.
- **~50–60 files touched, ~10–15 with real logic changes.** Mostly imports,
  type hints, variable renames. Logic changes concentrated in:
  `submissions_processing_service.py` (dispatch on pipeline),
  `submissions_backend.py` mixins (query labels), `unified_sharing_service.py`
  (`_check_shareable` admits `user_entry`), `journal_*` services (collapse
  to user-entry service).
- **Review queue rewrite has regression risk.** The current role-gated path
  is conservative. The new graph-pattern path must be dual-run against the
  old one until parity is proven.
- **Multi-audience revision cycles need a default rule.** When a teacher
  requests a revision, the revised `UserEntry` inherits audience from its
  parent. Codified, not left implicit.
- **Removed types cascade through docs, memory, and skills.** CLAUDE.md
  entity table shrinks by 2 net (`EXERCISE_SUBMISSION`, `JE_INPUT`,
  `JE_OUTPUT` removed; `USER_ENTRY` added). Affected docs:
  CLAUDE.md "22 Entity Types" heading + table, `/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md`,
  `/docs/patterns/DOMAIN_PATTERNS_CATALOG.md`, and skill files referencing
  the old types.
- **UserContext MEGA-QUERY updates.** The ~250-field context query pulls
  `JeInput`/`JeOutput` counts and `ExerciseSubmission` states. Phase 2 must
  rewrite those subqueries to match the `:UserEntry` label + filter on
  `pipeline` and outgoing edges. `fetch_user_groups` stays unchanged.

## Rollout

Three phases, implemented in separate plans. This ADR is the decision record;
the phases are the execution.

### Phase 1 — Introduce `UserEntry` and flip new writes

**New writes go to `UserEntry` from day one of Phase 1.** Old `Submission`
and `JeInput` routes become thin shims that construct `UserEntry` nodes
with pre-filled `pipeline` defaults (e.g., the legacy `POST /submissions`
route defaults `pipeline=teacher_review`, the legacy journal audio route
defaults `pipeline=transcribe_and_structure`). Old reads fall back via
label-inclusive Cypher (`MATCH (n) WHERE n:UserEntry OR n:ExerciseSubmission
OR n:JeInput OR n:JeOutput`) until Phase 2 relabels historical nodes.

This avoids the dual-write anti-pattern: at no point are two kinds of data
being created in parallel. There is one source of truth for new data
(`UserEntry`), and one transition period for reading legacy data.

Phase 1 work:
- New model: `core/models/user_entry/user_entry.py`, DTO, request schemas
- New enums: `Pipeline` and `ReportSource` added; `ProcessorType` stays
  temporarily (deleted in Phase 3 after all callers migrate)
- Admit `user_entry` in `UnifiedSharingService._check_shareable`
- New service: `UserEntryService` (facade), backend, mixins (promoted from
  current `_submission_*_mixin.py` files, renamed and generalized)
- New API routes: `POST /api/user-entries` with audience + pipeline
- Legacy routes (`POST /submissions`, journal audio upload) become shims
  that construct `UserEntry` with default pipeline
- Submit UI: audience checkboxes + pipeline selector. Pipeline is hidden
  and defaulted to `TEACHER_REVIEW` for ASSIGNED exercise flows; visible
  and user-chosen elsewhere
- Label-inclusive read helpers so existing pages (HomeHub Submissions tab,
  GradeBook, journal history) keep working across the label transition
- **Tests:** unit tests for pipeline dispatch on each of the 5 values;
  integration test covering a full submit-through-review cycle end-to-end
  on a real Neo4j; contract tests ensuring legacy shims produce correct
  `UserEntry` nodes

### Phase 2 — Migration and query rewrites

- **One-shot Cypher migration** (`scripts/migrations/collapse_submissions_to_user_entry_2026_04.cypher`):
  - `:ExerciseSubmission` → `:UserEntry` with `pipeline='teacher_review'`;
    `FULFILLS_EXERCISE` edges preserved. Backfill `revision_number` from
    the node field onto the `FULFILLS_EXERCISE` edge, then drop the field.
  - `:JeInput` → `:UserEntry` with `pipeline='transcribe_and_structure'`
  - `:JeOutput` → `:UserEntry` with `pipeline='none'`; `TRANSFORMS` edges
    preserved
  - Entity-type property updated: `entity_type='exercise_submission'` →
    `'user_entry'` (same for je_input, je_output)
  - Migration script includes a dry-run mode that prints affected counts
    per label and a rollback script for staging verification
- **Query rewrites:**
  - Review queue → `SHARED_WITH_GROUP` + `pipeline='teacher_review'` filter
    (shown in §6 of this ADR)
  - `UserContext` MEGA-QUERY subqueries that count journal entries and
    submission states
  - All intelligence/analytics services that filter on
    `entity_type IN [...]`
  - `SEARCH_FIELD_CONFIG` gains `user_entry`; old entries removed in Phase 3
- **Parity verification.** The new review queue is dual-run against the
  legacy role-gated query in staging; Phase 2 does not complete until row
  counts match for a representative time window.
- **Neo4j indexes:** full-text (`exercise_submission_fulltext_idx`,
  `je_input_fulltext_idx`, `je_output_fulltext_idx`) are dropped; a single
  `user_entry_fulltext_idx` is created. Vector indexes receive the same
  treatment. Uid indexes are dropped + recreated on the new label.

### Phase 3 — Delete legacy types

- Delete `Submission`, `ExerciseSubmission`, `JeInput`, `JeOutput` models,
  DTOs, request schemas, services, backends, mixins specific to them, tests
- Delete `ProcessorType` enum (all callers now use `Pipeline` or
  `ReportSource`)
- Delete legacy route shims from Phase 1; user-entry routes are the single
  path
- Delete label-inclusive read helpers added in Phase 1 (no legacy labels
  left to match)
- Update CLAUDE.md entity table and the "22 Entity Types" heading
- Update or delete affected skills: any skill referencing the old types
- Update `docs/architecture/ENTITY_TYPE_ARCHITECTURE.md`,
  `docs/patterns/DOMAIN_PATTERNS_CATALOG.md`, and any tutorial that walks
  through a submission flow
- Confirm `./dev quality` passes (MyPy 0 errors, SKUEL linter clean)
- Confirm full test suite passes on real Neo4j

## Alternatives Considered

- **Do nothing.** Keep `Submission`/`ExerciseSubmission`/`JeInput`/`JeOutput`
  as four separate types. Rejected: the duplication is already hurting
  (parallel `_submission_*_mixin.py` and `journal_*_service.py` code paths,
  stale aspirational comments, implicit audience). The asymmetry between
  ADR-053's clean teacher → student sharing and the ad-hoc student → teacher
  direction will grow over time, not shrink.
- **Variant A (minimal collapse).** Delete `ExerciseSubmission` only; keep
  `Submission` as the file/processing base. Rejected: leaves the
  `JeInput`/`Submission` duplication in place, does not address the
  top-down learning-loop rigidity.
- **Variant C (no dedicated type).** Dissolve the discriminator entirely —
  user content is just `Entity` with a `ContentProcessingMixin`. Rejected:
  `entity_type` still earns its keep as a search/filter discriminator for
  "my entries" vs "my tasks." Removing it breaks the unified search path
  (SKUEL search architecture depends on per-type configs in
  `SEARCH_FIELD_CONFIG`).
- **Keep the learning-loop type hierarchy.** Rejected: the Cypher doesn't
  care about the types, the UI doesn't care about the types, and the
  hierarchy creates parallel code paths (Submission vs JeInput) that do the
  same thing. A top-down abstraction that is not earning its keep.
- **Collapse `RevisedExercise` into `UserEntry`.** Rejected: RevisedExercise
  is teacher-authored curriculum targeting a student's revision cycle, not
  user-authored content. Its `REVISES_EXERCISE` / `RESPONDS_TO_REPORT`
  relationships describe a curriculum revision, not a content submission.
  Keeping it separate preserves the admin/user ownership distinction.

## Decided Points (formerly open)

- **Default pipeline for unhinted submissions: `NONE`.** If a caller does
  not specify a pipeline, the default is no processing. Explicit is better
  than implicit; SKUEL does not value backwards compatibility; there is no
  silent file-type sniffing that might surprise a reader of the code.
- **`revision_number` moves to an edge property now.** `FULFILLS_EXERCISE
  {revision: N}` in Phase 2 migration. Field is dropped from the model.
  Keeping it as a field during migration would leave a dead field on
  `UserEntry` that the ADR says has no business being there.

## Open Questions

1. **Exercise version pinning at submit time.** Today `ExerciseSubmission`
   does not pin the exact version of the `Exercise` it answers — edits to
   the exercise after submission are silently reflected in teacher review.
   `FormSubmission` solved this with `template_schema_hash`. Should
   `UserEntry` with `pipeline=TEACHER_REVIEW` pin an `exercise_version_hash`
   on the `FULFILLS_EXERCISE` edge? Out of scope for Phase 1; flag for a
   follow-up ADR if the lack bites us.
2. **Audience inheritance on `TRANSFORMS` output.** When a
   `TRANSCRIBE_AND_STRUCTURE` pipeline produces a derived `UserEntry`, does
   the derived entry inherit the input's audience by default, or start
   `PRIVATE`? Leaning: start `PRIVATE`, because the derived entry is the
   "polished" output the user may want to share differently from the raw
   input. Confirm at Phase 1 UI review.

## Postscript (2026-06-02)

The collapse is fully executed in code, and a documentation de-stale campaign
has brought every *reference* doc and skill into line with the landed shape.
This addendum records the actual outcomes and the points where reality diverged
from the body above. The body is kept verbatim as the decision record.

### What landed

- **One type, as decided.** `EntityType.EXERCISE_SUBMISSION` / `JE_INPUT` /
  `JE_OUTPUT` are deleted; `EntityType.USER_ENTRY` (NeoLabel `UserEntry`, UID
  prefix `ue`) is the single user-authored content type. The three legacy
  strings survive only as `from_string()` aliases mapping to `USER_ENTRY` (pure
  dict lookup — ingestion/DSL backward read), not as live types.
- **Services/backends renamed and collapsed.** The decision-time names in the
  body map to current code as: `submissions_processing_service.py` →
  `core/services/user_entry/user_entry_processing_service.py`;
  `SubmissionsService` → `UserEntryService`
  (`core/services/user_entry/user_entry_service.py`); `SubmissionsBackend` →
  `UserEntryBackend` (`adapters/persistence/neo4j/backends/user_entry_backend.py`,
  composed from `_user_entry_*_mixin.py`). No standalone `submissions/` or
  `journal_*` service files remain.
- **`Pipeline` / `ReportSource` split** (`core/models/enums/pipeline.py`) shipped;
  `ProcessorType` is gone. `ReportSource` carries four values incl. `HYBRID`.
- **Review queue** is the group-symmetric pattern of §6: backend method
  `get_review_queue_by_groups()` (matches `:UserEntry`-`SHARED_WITH_GROUP`→
  teacher-owned `Group`, `pipeline='teacher_review'`), wrapped by the service's
  `get_review_queue()`. Not an OWNS-the-exercise gate.
- **Read-filter bug fixed (#182).** The §Rollout "label-inclusive reads were not
  built" note left ~15 read queries filtering only the *deleted*
  `entity_type='exercise_submission'` — after migration relabelled everything
  to `user_entry`, they matched nothing (teacher review, assessment, ZPD, group
  counts silently dead). Fixed to match the `:UserEntry` label + canonical
  turn-in predicate. Fixing the dead filters activated the latent bugs they had
  masked (cross-user/cross-teacher leaks, count inflation) — all closed in #182.

### Material divergence from §5 — rich journaling abandoned

§5 ("Journal input → output, preserved") and Open Question 2 present journaling
as a live, forward-looking feature. **It is not.** Mike confirmed rich
journaling is abandoned, and the journal→KU DSL connector was wired into no live
path. Consequently:

- The rich-journal data model (`mood`, `energy_level`, `key_topics`,
  `entry_date`) was dropped from `UserEntry`.
- The ZPD `je_input` engagement signal was removed — it could never match, so
  `ZoneEvidence.journal_application` was permanently `False` (#183). Compound
  evidence now counts three signal types, not four.
- Content-enrichment rich-journal fields (`recent_journals`, `recent_topics`,
  `mood_trends`) were stripped from `EnrichmentContext`; the journal-context
  helpers were rewritten goals-only (#185). The `mood_trends` dict was a truthy
  hollow value that had been injecting a junk "Average Energy 0.0/10" block into
  every enrichment LLM prompt.

The `Pipeline.TRANSCRIBE_AND_STRUCTURE` *mechanism* (audio → transcribed entry →
LLM-structured second `UserEntry` linked by `TRANSFORMS`) and the
`/journals/submit` route still exist, and the PRIVATE-by-policy rule
(`Pipeline.allows_sharing()` returns `False` only for this pipeline) still holds —
so §5 is **mechanically** intact but no longer feeds any intelligence consumer.
Open Question 2 is effectively decided: the derived entry persists
`visibility=PRIVATE`.

### Still open / remaining cleanup

- **Open Question 1 (exercise version pinning at submit time)** was never
  addressed — no `exercise_version_hash` on `FULFILLS_EXERCISE`. Still open.
- **Phase 3 "delete label-inclusive read helpers" — completed 2026-09-02.** The last
  defensive label-inclusive read (the MEGA-QUERY's submission/feedback block in
  `user_context_queries.py`, which still listed the three retired
  `entity_type` strings) now matches `entity_type = 'user_entry'` only. The
  retired names survive solely where they are *rejected*: the ingestion
  detector's legacy-alias error and the lint catalog's stale-identifier rule.
