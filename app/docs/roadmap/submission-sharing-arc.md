---
title: "Submit & Share Arc — Rulings & Contract"
updated: 2026-09-25
status: "active"
registered: 2026-09-24
ruled: 2026-09-24
---

# Submit & Share Arc — Rulings & Contract

**Status:** ACTIVE — ruled 2026-09-24 (founder rulings R1–R14; four refinements signed off with the
plan). Thirteen PRs, **one per fresh context**. From PR 0 on, this document is the single source of
truth for the arc: nothing depends on the planning conversation. The **Status** column of the
[PR contract table](#pr-plan-contract) is the progress ledger — a session resumes at the first row
that is not `merged`.
**Decision record:** [ADR-088 — Submit and Share](../decisions/ADR-088-submit-and-share.md) (the
two verbs, the two group-link kinds, links as the only audience record, `visibility` = public or
not, `read_visibility`, the derived wall, R8 co-membership, `teacher:<group_uid>`).
**Related:** [ADR-038](../decisions/ADR-038-content-sharing-model.md),
[ADR-040](../decisions/ADR-040-teacher-exercise-workflow.md),
[ADR-042](../decisions/ADR-042-privacy-as-first-class-citizen.md) §7,
[ADR-053](../decisions/ADR-053-groups-first-class-and-unified-sharing.md) §1,
[ADR-054](../decisions/ADR-054-user-entry-unified-submissions.md) §3/§5/§6,
[ADR-085](../decisions/ADR-085-ownership-read-enforcement-contract.md) §2 (the records ADR-088
amends), [`sharing-http-door.md`](sharing-http-door.md) (the 2026-09-21 ruling ADR-088 amends),
[`vault-resync-never-retracts-a-share.md`](vault-resync-never-retracts-a-share.md) (closed by PR 8),
[`feedback-loop-staged-directions.md`](feedback-loop-staged-directions.md) §1 (peer feedback — the
next arc, R14), [`form-submission-recipient-read.md`](form-submission-recipient-read.md) (deferred
by this arc), [`done/calendar-priority-lens-arc.md`](done/calendar-priority-lens-arc.md) (this
document's skeleton).

---

## Intent

This started with a question about the GradeBook's "Other feedback" section and widened into a
redesign of how SKUEL users submit work for feedback and share it with others. Today one edge,
`SHARED_WITH_GROUP`, means both "for my teacher" and "for my class"; access is recorded twice (the
share links and the `visibility` property) and the two records disagree; the student's own feedback
sits on the Shared page beside other people's work; and a share cannot be taken back. The arc
separates the two acts:

- **Submit** asks for feedback — a teacher's or AI's. It is private; the feedback lands in the
  GradeBook.
- **Share** lets groups or people see your work. The Shared page holds what was shared with you and
  what you shared (your wall), with Stop sharing.
- The share links are the one record of who sees what; `visibility` keeps only "public".
- The encouraged route — submit → feedback → revise → share — is promoted (a nudge, a derived
  "reviewed" badge), never enforced.

Along the way it fixes the defects the redesign exposed: the bells that link to the wrong page, the
activity reports their student cannot open, the exercise-less vault note that is one mutable node,
and the exchanges orphaned when an exercise is deleted.

## Founder rulings (2026-09-24 — do not re-litigate)

| # | Ruling |
|---|---|
| R1 | **Two verbs.** **Submit** = ask for feedback (teacher or AI); it is private and the feedback lands in the GradeBook. **Share** = let groups or people see your work. There is no "post". |
| R2 | **Anyone may share anything, any time.** The encouraged route (submit → feedback → revise → share) is promoted by a nudge and a derived "reviewed" badge, never enforced. |
| R3 | **Split by feedback.** The teacher's queue holds only feedback requests. The Shared page holds only shares. Feedback on your own work (reports, revision requests, activity reports) lives only in the GradeBook. |
| R4 | **Share links are the one record of who sees what, and a link alone grants access.** `visibility` keeps only "public". |
| R5 | **Teacher-only and all-members are distinct.** Work sent to a teacher is hidden from classmates unless it is also shared. A teacher-only link means exactly one thing: a feedback request. |
| R6 | **Recipients see a basic card:** title, description, from, date, badge, and a link to open the file. Never the feedback, the exchange, or the teacher's verdict. |
| R7 | **The Shared page has two sides:** *Shared with you* and *Your wall* (what you shared, with whom, Stop sharing). Your wall is visible to you only, for now. |
| R8 | **You can share with people in your groups.** In the vault: `audience: user:<username>`. |
| R9 | **Vault notes are drafts.** `audience:` does nothing until `status: submitted` files a frozen copy. This applies with or without an exercise. |
| R10 | **Bells ring for:** a student when an admin writes their activity report; a teacher when a student submits; a person when something is shared with them. Group-share notifications, unread counts and topic subscriptions are future work. |
| R11 | **Activity reports stay in the GradeBook.** An admin-written report is owned by its student. |
| R12 | **Exchanges survive exercise deletion.** The title is snapshotted at submission, and orphans show as "exercise removed" lines, apart from Other feedback. Deletion stays allowed. |
| R13 | **Other feedback subtitle:** "Feedback on work that isn't tied to an exercise." |
| R14 | **Peer responses are the next arc.** That arc also revisits the Aug-2026 ruling "Peer is a GradeBook Source" ([`feedback-loop-staged-directions.md`](feedback-loop-staged-directions.md) §1: peer feedback joins the existing Source filters). |

## Refinements (signed off with the plan; recorded in ADR-088)

1. **R5 is two link kinds, not a marker.** `SUBMITTED_TO_GROUP` = a feedback request;
   `SHARED_WITH_GROUP` = all members.
   - `delete_group_share` (`sharing_backend.py:401`) deletes any `SHARED_WITH_GROUP` between an
     entity and a group, with no predicate on the relationship. With a marker, Stop sharing would
     silently cancel the feedback request; with two kinds it can't. (Its only caller,
     `unshare_from_group`, is PLANNED with no door — the risk arrives with PR 6b's door.)
   - A reader that forgets to switch now fails closed (hides) instead of leaking.
   - Relationships are verbs.
2. **Per-teacher targeting is kept.** A multi-class student can already send to one teacher's
   group: today it is spelled `audience=group:<uid>` on both doors (`user_entry_api.py:186-190`,
   `user_entry_ingestion.py:320-322`) and writes an ordinary `SHARED_WITH_GROUP`; the read side is
   pinned by `test_review_queue_copy_collapse.py:100`. It becomes `teacher:<group_uid>`, next to
   `teachers` (all my teachers).
3. **Person candidates exclude the default group's roster (keeping its owner).** Every enrolled
   student auto-joins `group_default_{admin}` — "enrolled" meaning they marked any PathStep in
   progress (`ps_mastery_service.py:155` publishes `PathStepEnrolled`;
   `path_step_enrollment_handler.py:47-57` joins the oldest admin's default group) — so "people in
   my groups" would list the whole enrolled platform. The default group is still offered as a
   *group* target. The default group records its owner only through its `:OWNS` edge (it has no
   `owner_uid` property), and it is recognised today only by the uid prefix
   `STARTS WITH 'group_default_'` (`sharing_backend.py:337`); PR 6a names the mechanism.
4. **UserEntry search stays owner-only; opening follows the audience.** DomainConfig gains a
   declared `read_visibility` (default = `search_visibility`). UserEntry's is `OWNER_OR_AUDIENCE`.
   - Reason: widening search would put others' entries, including `status` (the teacher's verdict)
     and `processed_content` (a search field, `user_entry_service.py:97`), into search results.
     That violates R6.
   - Shared items are discovered on the Shared page.
   - This amends ADR-085 §2 ("a direct read and a search of the same domain agree by
     construction"). It adds no third mechanism: the same clause builder, a declared member.
   - UserEntry's `OWNER_ONLY` today is derived (from `user_ownership_relationship=OWNS`,
     `domain_config.py` `get_search_visibility`), not declared.

## Architecture (target)

```
entry ──SUBMITTED_TO_GROUP──▶ Group ◀─OWNS── teacher      feedback request → review queue only
entry ──SHARED_WITH_GROUP───▶ Group ◀─MEMBER_OF|OWNS─     share → Shared with you / Your wall / /groups
user  ──SHARES_WITH─────────▶ entry                       person share → Shared with you + bell
entry.visibility ∈ {private, public}                      public = portfolio (no reader yet)
```

**One audience vocabulary** (`AudienceSpec`), used by the web, the JSON API and the vault:

| Value | Meaning |
|---|---|
| `teachers` | SUBMITTED_TO_GROUP to the exercise's groups I belong to — for a curriculum exercise (never assigned to a group), my default group (the 2026-07-04 fallback, kept); with no exercise, to all my student groups |
| `teacher:<group_uid>` | SUBMITTED_TO_GROUP to one group |
| `group:<uid>` | SHARED_WITH_GROUP |
| `user:<username>` | SHARES_WITH, only with a co-member |
| `public` | Visibility public (TEACHER-gated) |
| `private` | No links — exclusive: combined with any other value it is a parse error |

- A feedback request requires pipeline TEACHER_REVIEW, so the edge and the pipeline always agree.
- **One audience predicate fragment** checks `(viewer)-[:MEMBER_OF|OWNS]->(g:Group)<-[:SHARED_WITH_GROUP]-(n)`
  with `g.is_active = true` (strict), or a direct `SHARES_WITH`. It is shared by the read clause, the
  Shared-with-you group half and the `/groups` list, so whatever is listed can be opened. It holds
  no owner arm: the `OWNER_OR_AUDIENCE` clause ORs it with the owner arm (`ownership_property`), and
  the list readers use it alone. It is one function, never a copy (ADR-088 §5).
- `group:<uid>` is always a share; a feedback request is only ever `teachers` / `teacher:<group_uid>`.
  - **It does not exist yet — PR 5 creates it.** The nearest existing arm, SCOPE_AWARE's group arm
    (`crud_queries.py:410-411`), joins `MEMBER_OF` only with no `is_active` check, and the `/groups`
    readers (`sharing_backend.py:456-457`) join `MEMBER_OF` only, strict.
  - **Strict `is_active` is deliberate.** The codebase is split (~24 adapter sites) between strict
    `is_active = true` and lenient `coalesce(g.is_active, true) = true`; both group writers set it
    true on create, so strict loses nothing and a deactivated group grants nothing.

## Verified ground truth (2026-09-24 — code read on `d65f624fd` + live graph)

The plan was checked adversarially against the code by 7 read-only verifiers while it was being
written, and again at PR 0 by 10 (one per claim family: the defects, the refinements, the amended
records, the docs tooling, and every file:line in the six PR groups). What follows is what the PR 0
pass confirmed or corrected.

**Live census (AuraDB, read-only session, 2026-09-24):**
- **`SHARED_WITH_GROUP`: 2 edges**, both UserEntry `teacher_review` → `group_default_user_admin`:
  ue_65688cb7 ("small_steps_design.md", completed) and ue_bd5ce4a1 ("gentle_return_response.md",
  revision_requested — the Gentle Return turn-in on `/teaching/queue`). No FormSubmission edge, no
  other pipeline. `SUBMITTED_TO_GROUP` is unknown to the database.
- **`SHARES_WITH`: 3 edges** — 2 student self-shares on the student's own EntryReports, and 1
  RevisedExercise → student grant (re_c4e92951, admin-owned).
- **`visibility`**: `shared` on exactly 2 nodes (the 2 EntryReports; outcomes `approved` and
  `needs_revision`, both `processor_type = human`); `team` on 0; `public` on 0 (so no spawned
  user-owned node carries it). Every other carrier is `private`: UserEntry 78, Task 75, Choice 8,
  Interaction 6, Event 5, Habit 4, Goal 2, Principle 1, FormSubmission 1, RevisedExercise 1.
- **ActivityReport: 0 nodes.**
- **Notifications: 3** — `feedback_received` and `revision_requested` (source_type
  `entry_report`), `revised_exercise_created` (`revised_exercise`).
- **Turn-ins: 4 UserEntries** carry a direct `FULFILLS_EXERCISE` edge to a live Exercise
  (2 `teacher_review`, 2 `llm_summary`); only 1 carries the `fulfills_exercise_uid` property.
  `FULFILLS_REVISED_EXERCISE` is unknown to the database. All 4 are recoverable by PR 4a's backfill.
- **UserEntry by pipeline:** none 38, extract_activities 22, knowledge 14, llm_summary 2,
  teacher_review 2. **Share edges on vault-file-backed (living) UserEntries: 0.**
- **Groups: 1** — `group_default_user_admin` (active; `OWNS` from user_admin; 1 `MEMBER_OF`,
  linguistic76). **Users: 6** (linguistic76 is the one member; user_uxsmoke is registered and in
  no group). **FormSubmission: 1**, with 0 group and 0 person edges.

**What's wrong today (the seven defects):**
1. **Privacy leak.** Classmates see every turn-in shared to a group on `/groups`:
   query_user_entries_shared_with_group and the single-entry peer read (`sharing_backend.py:439-510`)
   gate on `MEMBER_OF` + `is_active` with no pipeline or status filter, and the review queue reads the
   same edge under the teacher's `OWNS` (`_user_entry_assessment_mixin.py:110-113`). Curriculum
   turn-ins with no exercise group fall back to `group_default_{admin}`
   (`audience_resolver.py:302-310` → `sharing_backend.py:316-345`), which every enrolled student
   joins. **A second path into the same group:** in the vault, an absent `audience:` defaults to
   `teachers` on every pipeline where Pipeline.shares_by_default holds that the vault door accepts
   (NONE, LLM_SUMMARY, TEACHER_REVIEW — TRANSCRIBE satisfies it too, but the door rejects audio
   pipelines before `audience:` is read, `user_entry_ingestion.py:44`), and `teachers` expands to
   every student group
   (`user_entry_ingestion.py:298-319`, `audience_resolver.py:351`) — the default group included —
   with or without an exercise.
2. **Access is recorded three ways, and they disagree.** The EntryReport access check
   (`unified_sharing_service.py:192-235`) admits a non-owner only on `visibility = public`, or on
   `visibility = shared` **and** a share link (direct or group), so a link alone never grants access; its one live caller is the EntryReport
   detail (`user_entry_orchestrator.py:297`). The UserEntry detail read (`/gradebook/{uid}` →
   `user_entry_service.py:441-451`) ignores both and admits only the owner, so an entry shared with
   a person (JSON `share_with_users`) appears on the recipient's Shared page and opens as a
   rendered "Submission Not Found" page (not an HTTP 404 status). The `/groups` peer reads are a
   third rule. `share()` and `share_with_group()` never write `visibility`. `TEAM` is written by the
   Events form (`events_form.py:44,75` via `EventCreateRequest`) and read nowhere; the
   `UserOwnedEntity` visibility check (can_view in `user_owned_entity.py`) has zero callers.
3. **Admin-written activity reports can't be opened by their student.** `submit_report`
   (`activity_report_service.py:351`) makes the admin the owner (`:411`) and the student the
   subject; the list reads by subject (`misc_backends.py:84`), while the detail, the download and
   the annotation reads are owner-scoped (`misc_backends.py:47`).
4. **3 of the 4 bell notification types link to the wrong page.** `ui/notifications/cards.py:55`
   links every notification to `/gradebook/{source_uid}` and ignores `source_type`.
   `submission_approved` carries the entry uid (correct); `feedback_received` and
   `revision_requested` carry an EntryReport uid and `revised_exercise_created` a RevisedExercise
   uid (all three wrong). `entity_detail_href` (`entity_links.py:24-43`) already maps all three
   source types to the right pages.
5. **The web can't send to a teacher without an exercise, and `teachers` means different things
   on the two doors.** The `/submit` form disables Teacher without an exercise
   (`ui/user_entry/forms.py:98,162`) and never emits `group:`. Web `teachers` = the exercise's
   groups ∩ my memberships, plus the curriculum default-group fallback (`user_entry_api.py:185-186`).
   Without an exercise it fails validation on `teacher_review` (`audience_resolver.py:121-133`) and
   on every other shareable pipeline passes and silently shares nothing (`audience_resolver.py:286`;
   the request model calls it "silently noop"). Vault `teachers` = every group I am a student of,
   exercise or not. (The HTTP API can already reach the queue
   without an exercise: `/api/user-entries/upload` with `audience=group:<uid>` and
   `pipeline=teacher_review`, or JSON `share_with_groups`.)
6. **An exercise-less `teacher_review` vault note is one mutable node.** No frozen copy is filed
   without an exercise — the gate is `submit_signal` (`user_entry_ingestion.py:597-599`), with the
   prior-uid reuse gate at `:463-469`. The note takes the upsert branch, which refreshes every
   property but `created_at` (`_user_entry_crud_mixin.py:120`), and `create_entry` stamps
   `submitted` on a teacher_review entry, so every edited sync resets the teacher's verdict.
7. **Deleting an exercise orphans its exchange into Other feedback, under a false label.** The
   CRUD delete is a hard `DETACH DELETE` (`_crud_mixin.py:955-960`), stripping `FULFILLS_EXERCISE`;
   the GradeBook exchange grouping needs the edge (`_user_entry_report_query_mixin.py:266-276`); the
   orphan lands under "Feedback you received outside an exercise exchange."
   (`ui/gradebook/summary.py:222`). The entry keeps a dangling `fulfills_exercise_uid` property that
   nothing reads for grouping.

**Stale records this arc inherits — do not copy them as current truth:**
- ADR-054 §5 says `allows_sharing` is False "only for TRANSCRIBE_AND_STRUCTURE"; it is also False
  for REFERENCE (`pipeline.py:88-91`).
- ADR-054 §6 says teacher authority "collapses into" the EntryReport access check; it never did —
  `verify_teacher_authority` still exists (`teacher_review_service.py:941`).
- ADR-054 §3 lists "four audience options, any combination" and a "Peer — SHARED_WITH" edge; the
  web form is one destination (`ui/user_entry/forms.py:9-12`) and the edge is `SHARES_WITH`.
- ADR-054 §3 labels its YAML table "`/upload`": no YAML upload door exists. The per-file HTTP door
  was deleted (ADR-070 Decision 9, amended 2026-09-22); `ingest_user_entry`'s one caller is
  `UnifiedIngestionService.ingest_file()`, and a relative path reaches it only from scripts and
  tests.
- `sharing-http-door.md` says TEAM "has no writer and no reader anywhere"; the Events form writes
  it.
- ADR-085 §2's own file:line cites have drifted (`_crud_mixin.py` def now `:330`,
  `base_protocols.py` member now `:499`).

## Amendments by record (the standing records this arc changes)

ADR-088 lists these; **no record is edited in PR 0**. Each gets its "amended by ADR-088" note in the
PR whose code makes the change true.

| Record | Was | Now | Note lands in |
|---|---|---|---|
| ADR-038 — Content Sharing Model | A three-level model over a four-value enum (TEAM reserved); non-owner access = `visibility` SHARED **and** a link; revoke/access-list half with no door; "never a second share form" (2026-09-21); no notifications | Two levels (PR 2a); the access check retired (PR 2b); a link alone grants access (PR 5); a Share / Stop-sharing door, the access list is Your wall, a person share rings a bell (PR 6b) | PR 2a, PR 2b, PR 5, PR 6b |
| ADR-040 — Teacher Exercise Workflow | Header note: the queue is `SHARED_WITH_GROUP` + `pipeline='teacher_review'`; TEAM a future phase | The queue reads `SUBMITTED_TO_GROUP` under the teacher's `OWNS`; TEAM deleted | PR 1 (queue — added at PR 0: the plan listed ADR-040 only under PR 2a, but PR 1 falsifies the queue sentence), PR 2a (TEAM) |
| ADR-042 §7 — Group sharing, membership-level access | Each current member gets access | A feedback request grants members nothing; a share reaches members **and** owners of an active group | PR 1 (split), PR 5 (fragment) |
| ADR-053 §1 — Retire FOR_GROUP, unify on SHARED_WITH_GROUP | §1: the one teacher→group curriculum mechanism; the header's ADR-054 note extends it symmetrically to turn-ins | The curriculum half unchanged; turn-ins get their own kind — the note lands beside that header note | PR 1 |
| ADR-054 §3 — Audience (+ the YAML `audience:` table) | Four options in any combination; `teachers` (default) → every student group on every submission-shaped pipeline | Two verbs; teacher → `SUBMITTED_TO_GROUP`; `teacher:<group_uid>`; co-member `user:<username>`; one vocabulary; a vault note's audience applies only to the frozen copy | PR 1, PR 6a (rows), PR 8 (drafts) |
| ADR-054 §5 — Journal input → output | The pipeline gate covers the submit-time audience, "not the entry's lifetime audience" | The share door applies it for the entry's lifetime and refuses `private: true` entries — reversing the documented rule that `private` is orthogonal to sharing (`user_entry.py:108-113`, `user_entry_request.py:73-80`) | PR 6a |
| ADR-054 §6 — Review queue and teacher authority | Queue on `SHARED_WITH_GROUP` + pipeline; authority "collapses into" the access check | Queue on `SUBMITTED_TO_GROUP`; the access check retired | PR 1, PR 2b |
| ADR-085 §2 — `get_visible_to_user` | Callers pass `search_visibility`; a direct read and a search agree by construction | Callers pass `read_visibility` (default `search_visibility`); UserEntry diverges by declaration | PR 5 |
| `sharing-http-door.md` — the 2026-09-21 ruling | Revoke / access-list half PLANNED as a door on existing edges, never a second share form; `set_visibility` waits on the PUBLIC reader | Share + Stop sharing on a user entry; both revoke methods live; the two access-list methods deleted; `set_visibility` PLANNED, PUBLIC-only; re-sync reconciliation dissolved by R9's drafts | PR 2a, PR 6b, PR 8 |

**Also contradicted (found at PR 0; each lands with the PR that falsifies it):** ADR-042 §3
("`SHARES_WITH` is the sole access gate") and §8 (names the access check and the access-list method)
— PR 2b / PR 6b; ADR-054 §4 ("`FULFILLS_EXERCISE` + `SHARED_WITH_GROUP` is an exercise turn-in"),
its Consequences ("post to a group feed") and its Postscript (the queue on `SHARED_WITH_GROUP`) —
PR 1 / PR 6a; ADR-038 §4 ("Only Completed Reports Shareable") — for a UserEntry the share gate
(`_check_shareable`, `unified_sharing_service.py:476`) refuses only `archived` — R2 ("any time")
lifts that in PR 6b (settled at PR 0 review).

## Choices — per PR

Every file:line below was checked on `d65f624fd` at PR 0 and is a **hint**: re-verify by grepping
the symbol, never trust the number. **Verified at PR 0** bullets are findings the plan did not
carry — folded in as contract; the ones that change the plan say "settled at PR 0 review".

### PR 0 — Arc record (docs only)

- This document, on the calendar-priority-lens-arc skeleton, and [ADR-088](../decisions/ADR-088-submit-and-share.md).
- `docs/INDEX.md` rows; the deferred item
  [`form-submission-recipient-read.md`](form-submission-recipient-read.md) (a form shared with you
  still 404s) with its `deferred-work.md` MOC entry. Every existing `deferred-work.md` heading is
  unchanged.
- ADR-088 is linked back from the learning-loop, security and search-architecture skills
  (`related_adrs`), and `CROSS_REFERENCE_INDEX.md` is regenerated.
- `./dev health` was red on `main` before this PR (a backticked deleted class name in
  `field-name-guarding-in-cypher.md:144`); fixed here by writing it in prose.
- Codex summoned explicitly (a docs-only PR auto-passes the gate).

### PR 1 — Feedback requests get their own link (closes the classmate leak for turn-ins)

- **The link kind:** `RelationshipName.SUBMITTED_TO_GROUP`, beside `SHARED_WITH_GROUP`
  (`relationship_names.py:342`). There is no registry entry. Regenerate GRAPH_CONTRACT
  (170 → 171 relationships, contract null).
- **Writer:** `UnifiedSharingService.submit_to_group` + backend `create_group_submission`
  (MERGE…ON CREATE, returning `created`), with protocol members in `core/ports/sharing_protocols.py`
  (`:99`, `:236`).
  - Verified at PR 0: returning `created` is a new shape — the sibling `create_group_share`
    (`sharing_backend.py:246-277`) returns `success`. Copy its membership guard (`:265-273`:
    `MEMBER_OF` or `OWNS`, group active). **Success is the guard row:** a row comes back whenever
    the guard passes and `created` rides in it; only a no-row result is a forbidden failure, and
    `created = false` (an existing edge) is a success — never copy `share_with_group`'s
    `if not result.value` check onto the `created` bool. PR 7's teacher bell depends on `created`.
- **The request side:**
  - `UserEntryCreateRequest.submit_to_groups` (new).
  - The vault `teachers` expansion and the exercise auto-share / curriculum fallback fill it
    (`user_entry_ingestion.py:316-322`, `audience_resolver.py:282-337`).
  - For TEACHER_REVIEW requests, explicit `share_with_groups` go to `submit_to_groups`. This keeps
    today's per-teacher targeting until PR 6a names it.
  - `validate()` counts only exercise / `submit_to_groups` as a TEACHER_REVIEW audience.
  - `ShareOutcome` gains `submitted_groups`, counted in `any_success` and `to_payload`. Without that,
    vault copies are compensated away and the SHARED_WITH_TEACHER Interaction is skipped.
    Verified at PR 0: `submitted_groups` = every group the MERGE matched, created or not (it is
    success); `newly_submitted_groups` = the `created` subset, which feeds PR 7's bell — mirroring
    PR 6b's `newly_shared_users`. A created-only `submitted_groups` would make every idle re-sync of a
    living `teacher_review` note read as zero reach once PR 7 moves the compensation.
  - **Reach is judged by the link kind the entry needs** (settled at PR 0 review): for a
    TEACHER_REVIEW entry, step 5a's zero-reach check reads `submitted_groups` specifically — a person
    or group share that succeeds while every `SUBMITTED_TO_GROUP` write fails (a membership change, a
    deactivated group) does not make the request reach a queue, so the entry is compensated as today.
    `any_success` stays the aggregate for every other caller. PR 7 moves this rule, unchanged, into
    `create_entry`.
  - **Verified at PR 0 — the pipeline gap (contract, settled at PR 0 review).** Neither path is
    TEACHER_REVIEW-only today: the vault's absent-`audience:` default is `teachers` on NONE, LLM_SUMMARY and
    TEACHER_REVIEW (Pipeline.shares_by_default, `user_entry_ingestion.py:298-319`; TRANSCRIBE is
    rejected at the door), and web
    `audience=teachers` sets `auto_share_to_exercise_groups` on any pipeline
    (`user_entry_api.py:185-186`), after which the resolver auto-shares to the exercise's groups
    whatever the pipeline (`audience_resolver.py:283-286`; the auto-share block writes edges
    directly, it does not fill a request field). The Architecture's rule — a feedback request
    requires TEACHER_REVIEW — means `submit_to_groups` is gated on TEACHER_REVIEW, and so **on any
    pipeline other than TEACHER_REVIEW, `teachers` writes no group link** — the vault value
    (defaulted or explicit) and the web auto-share, curriculum fallback included. This is what the
    plan's "the vault `teachers` expansion fills `submit_to_groups`" produces once that field is
    gated; it only narrows access, and it matches R5, R9 and ADR-054 §3's 2026-09-02 amendment (the
    `teachers` default is submission semantics). The live census (0 such edges) cannot protect
    against new writes, so it is an acceptance case, not a choice. An explicit vault `teachers` on such a note logs an ingest warning
    (never a silent drop) pointing at `group:<uid>` for a share or `pipeline: teacher_review` for
    feedback; update `test_user_entry_ingestion.py:166` and add a none/llm_summary absent-audience
    case asserting no group link. The rejected alternative — leave it a `SHARED_WITH_GROUP` share —
    would keep defect 1's second path open to classmates until PR 8 beside the new submission
    semantics.
- **Forms:** every FormSubmission group target is a feedback request.
  - These writers switch: `share_with_default_audience` (`forms_backends.py:404`) and the group
    branch of `_share_on_submit` (`form_submission_service.py:206`). `/api/form-submissions/share`
    is not a separate writer — it goes through `share_submission` → `_share_on_submit`
    (`form_submission_service.py:408`), so it switches with it (it needs a test, not a change).
  - The no-audience guards (`forms_backends.py:342,469`) check both kinds.
  - The granting OPTIONAL MATCH (`forms_backends.py:516`) switches.
  - `_teacher_audience_predicate` (`forms_backends.py:61`): its `SHARED_WITH_GROUP<-OWNS` arm switches
    to `SUBMITTED_TO_GROUP<-OWNS`, and its direct `SHARES_WITH` arm (a teacher named in
    `recipient_uids`) **leaves the gate**: a person share is a share, never a review grant (R3, R5,
    ADR-088 §3 — the two readers are never crossed). Verified at PR 0: that arm is pinned by
    `test_form_submission_access_gate.py:211,294`, which flip to not-found. Cost: until the form
    recipient read ([`form-submission-recipient-read.md`](form-submission-recipient-read.md)) is
    built, a teacher named by person has no door to the form — note it in that case file. The
    `verify_teacher_access` docstring and refusal wording (`form_submission_service.py:321-346`,
    `teaching_forms_ui.py:385`) then match the gate; reword them to name `SUBMITTED_TO_GROUP`.
- **Teacher readers switch to `SUBMITTED_TO_GROUP<-OWNS`:**
  - `_user_entry_assessment_mixin.py` (lines 112, 126, 236, 261, 296, 344, 390, 399, 407);
  - `_user_entry_report_query_mixin.py:188`;
  - `collab_backends.py:191,216`;
  - `exercise_backends.py:527`.
  - **Every switched arm also requires an active group** (`g.is_active = true` — ADR-088 §3's
    teacher gate is an *active* owned group; settled at PR 0 review). Verified at PR 0: the queue and
    detail already check it, but `_user_entry_assessment_mixin.py:236,261`, `collab_backends.py:191,216`
    and `exercise_backends.py:527` do not, so today the exercise list, the students summary and the
    teaching group/dashboard counts still count a deactivated group's work. Put the predicate on the
    `SUBMITTED_TO_GROUP` arm, so an inactive group still lists (with nothing pending) where a page
    lists groups.
- **These stay as they are:** the membership gates; the curriculum readers; the member readers
  (`sharing_backend.py:458,495`), which are now correct by construction. Verified at PR 0: the reader
  census is complete — every other UserEntry/FormSubmission `SHARED_WITH_GROUP` reader is a
  curriculum reader, a membership gate, the caller-less query_groups_shared_with, or the
  retract_defaulted_vault_note_shares script (which targets KNOWLEDGE and EXTRACT_ACTIVITIES only).
- **Migration** `scripts/migrations/split_submissions_from_shares_2026_09.py`, dry-run census by default:
  - Reports UserEntry `SHARED_WITH_GROUP` counts by pipeline, and **fails loudly on
    non-teacher_review rows** — a census stop-and-look: an explicit `group:` share on another
    pipeline is legitimate, and a row made before PR 1 cannot be traced to its source (the vault
    `teachers` default or an explicit `group:`), so a non-zero count is ruled on by a person before
    `--confirm`.
  - `--confirm` re-types teacher_review UserEntry edges and **all** FormSubmission edges, using the
    no-APOC MERGE + copy + DELETE pattern (`migrate_supports_habit_to_reinforces_habit_2026_08.cypher`).
  - **The teacher_review rows are listed too, for a person to confirm** (settled at PR 0 review): the
    old edge meant both "for my teacher" and "for my class" and records no intent. The migration reads
    a teacher_review edge as a feedback request — Refinement 2: `group:` on TEACHER_REVIEW *was* the
    per-teacher route — which only narrows access; an owner who meant a class share re-shares through
    PR 6b's door. Live 2026-09-24: 2 rows, both curriculum-fallback turn-ins to the default group.
  - It only narrows access. Live census 2026-09-24: 2 UserEntry edges (both teacher_review), 0
    FormSubmission edges. Deploy order: § Standing conventions → Migrations (the new queue reads
    `SUBMITTED_TO_GROUP` while the old code writes `SHARED_WITH_GROUP`).
- **Tests:**
  - Re-type the `SHARED_WITH_GROUP` turn-in/form fixtures in `test_exchange_thread.py:193`,
    `test_review_queue_copy_collapse.py:232`, `test_teacher_report_read_scope.py:213`,
    `test_forms_backend_classroom_scope.py:97`, `test_form_submission_access_gate.py:77,285,371`,
    `test_teacher_review_idor_isolation.py:83,188`, and `tests/manual/seed_idor_smoke_fixture.py:125`.
  - Verified at PR 0: `test_form_submission_access_gate.py:455` is not a fixture but the
    `_shared_groups` assertion helper (~15 tests read through it) — it switches with the writer;
    the `:507` docstring needs a wording pass.
  - Update the assertions at `test_submit_to_review_cycle.py:87` and `test_vault_exercise_channel.py:253`.
  - Update the unit mocks in `test_audience_resolver.py`, `test_user_entry_service.py`,
    `test_user_entry_ingestion.py`, `test_form_submission_service.py` and `test_unified_sharing_service.py`.
  - Exercise→group fixtures (`tests/integration/user_entry/conftest.py:167` etc.) **stay**.
  - New integration test: `/groups` hides turn-ins and still shows shares, and the queue still lists them.
- **Docs:** CLAUDE.md § Content Sharing graph line; SHARING_PATTERNS § schema;
  `docs/domains/user_entry.md:40,171`; OWNERSHIP_VERIFICATION:417; REPORT_ARCHITECTURE:122,150;
  `form-submissions.md:131,228`; ROUTE_MAP `/groups`; the "amended by ADR-088" notes on ADR-040
  (the header's queue sentence), ADR-042 §7 (the split), ADR-053 (beside its header's ADR-054 note)
  and ADR-054 §3 / §4 / §6 and its Postscript (the queue and the turn-in edge); the learning-loop
  and cypher-patterns skills.
- **Docstrings:** `pipeline.py:35`, `user_entry_request.py:124,133`, `user_entry_protocols.py:16,253,352,424`
  (keep the lint anchor at `test_lint_skuel.py:6946`), `teacher_review_service.py:108,735`,
  `user_entry_orchestrator.py:215`, and the stale_names reason at `stale_names.py:265`.
- **Ruled (PR 1 session, 2026-09-24 — engineering choices the census found unsettled; none touches
  a ruling):**
  - The interim per-teacher route lives at the two legacy doors, not on the request model: the web
    `audience=group:<uid>` parser and the vault `audience: group:<uid>` parser fill
    `submit_to_groups` on TEACHER_REVIEW and `share_with_groups` otherwise. The JSON body speaks
    the two fields literally — `share_with_groups` on a TEACHER_REVIEW request stays a share, and
    without a feedback target it is refused by `validate()` (never silently re-typed; Codex P2 on
    #1414 — a model-level mapping swallowed an explicit share sent beside `submit_to_groups`).
    PR 6a retires the door mapping with `teacher:<group_uid>`.
  - `SUBMITTED_TO_GROUP` carries `submitted_at` only (stamped on create; a re-file keeps it).
    The migration maps the old edge's `shared_at` onto it and does **not** carry `share_version`
    — a share concept, `original` on every live row; a feedback request has no versions.
  - The new writer's group guard is strict (`is_active = true`), the ADR-088 §3 rule, not the
    sibling's `coalesce` — nothing is lost (both group writers set it on create).
  - Step 5b (the `SHARED_WITH_TEACHER` Interaction) reads `submitted_groups`, like 5a: reach is
    the link kind the entry needs, so a person share alone records no teacher transition.
  - The vault door resolves `teachers` only on TEACHER_REVIEW and skips the group lookup on other
    pipelines (same behaviour as "fill then gate", one query fewer); the explicit-value warning is
    a `logger.warning` on the ingest, keyed on `data["audience"]` being present.
  - The migration's stop-and-look has a door: a person's "keep it as a share" ruling on an
    off-pipeline row is passed as `--keep-share <entry_uid> <group_uid>` (repeatable); the row is
    left untouched and excluded from the stop, and a ruling naming no live row is itself a stop
    (Codex P2 on #1414 — without it a kept share blocked the re-type forever).
  - **The review-write gate is the entry's own feedback request** (Codex P1 on #1414). "These
    stay as they are: the membership gates" above named `verify_teacher_has_group_access`, which
    gated `submit_report` / `request_revision` / `approve_report` / the teacher delete on the
    teacher sharing *some* active group with the owner — wider than the queue and detail reads it
    claimed to match, so a second teacher of a multi-class student could write on a submission
    sent only to the first. It now requires `(submission)-[:SUBMITTED_TO_GROUP]->(g:Group
    {is_active: true})<-[:OWNS]-(teacher)`: a teacher writes on exactly what they can open. The
    student-level authority (`verify_teacher_authority`, `get_report_file_path`, the revision-chain
    read) is untouched — it gates reads of the teacher's own artifacts, which PR 2b / PR 5 revisit.

### PR 2b — Feedback is identified by its outcome; the EntryReport access check retires

**Runs before PR 2a (reordered at PR 0).** Two verified hazards in the plan's 2a → 2b order:
(1) PR 2a's migration rewrites the two live `shared` EntryReports to `private`, but the GradeBook
and exchange discriminator `coalesce(r.visibility,'shared') <> 'private'` is replaced only here —
between the two deploys received feedback disappears, and new reports would too once 2a's writers
stop writing `shared`; (2) the enum shrink breaks the still-live access check, which reads
Visibility.SHARED (`unified_sharing_service.py:231`). This PR depends on nothing in 2a, so landing
it first removes both.

- **The received-feedback discriminator** is `r.assessment_outcome IS NOT NULL`: every feedback
  writer sets it (APPROVED / NEEDS_REVISION / AI_EVALUATED) and journal reflections don't. It
  replaces `coalesce(r.visibility,'shared') <> 'private'` at `_user_entry_report_query_mixin.py:211,279,302`.
  Live: both EntryReports carry an outcome.
- **Retire** check_access / query_access / check_report_access plus their protocol members.
  - Protocol members: `sharing_protocols.py:228` (service) and `:75` (backend); the module docstring
    (`:19-20`, `:26`) names both. check_report_access (`user_entry_orchestrator.py:280`) is already
    dead — no caller, no protocol member.
  - `get_entry_report_view` becomes an owner read (the check's one live caller,
    `user_entry_orchestrator.py:297`). A report is student-owned whenever the submission has an
    `OWNS` owner (`exercise_backends.py:984`, `:1072`; otherwise the author owns it), and today only
    the owner passes.
  - Remove the now-unused `sharing_service` from `UserEntryOrchestrator` (`compose.py:1544`, the test fixture).
- **Tests:**
  - Add `assessment_outcome` to the feedback fixtures in `test_gradebook_summaries.py:83-164` and
    `test_exchange_thread.py:138-174` (reflections stay null).
  - Pin: a null outcome is excluded.
  - Delete the six access-check unit tests in `test_unified_sharing_service.py` (`:448`, `:474`,
    `:500`, `:526`, `:552`, `:593`) — **not** the whole 448-610 span: `test_share_database_error`
    (`:570-590`) stays.
  - In `test_sharing_workflows.py` only five tests call the check: the complete-workflow test (`:114`;
    trim its check steps at `:158`, `:175`, keep the rest), the private-visibility (`:266`),
    public-visibility (`:292`), shared-visibility (`:317`) and nonexistent-report (`:576`) tests. The
    other eight tests in 158-580 stay.
  - New: `/entry-reports/detail` gives the owner 200 and the authoring teacher 404.
- **Docs:** PROTOCOL_REFERENCE:466, RELATIONSHIPS_ARCHITECTURE:187, the ui-orchestrator skill:112,
  `feedback-loop-staged-directions.md:68,74`, `sharing-http-door.md:23,75`. Verified at PR 0, also:
  CLAUDE.md § Content Sharing (its "live:" list names the check), SHARING_PATTERNS (~12 lines: 117,
  203-204, 260, 349, 408, 480, 484, 533, 538, 552, 559, 562), `.claude/skills/learning-loop/reference.md:332`,
  and the `_SHARING_VISIBILITY_LADDER` reason in `detect_bloat.py`. Add the retired names as
  stale_names DELETED rows, with ALLOWED_OCCURRENCES for frozen ADR text (ADR-038, ADR-042, ADR-054)
  and `DOMAIN_BACKENDS_POSITION_2_COMPLETE_2026-03-01.md:69` (stale_names has no directory exclusion).
  The "amended by ADR-088" notes this PR lands: ADR-038 (the access check retired), ADR-042 §3 and §8
  (the check), ADR-054 §6 (authority never collapsed into the check; report detail is an owner read).
- **Ruled (PR 2b session, 2026-09-24 — engineering choices the census found unsettled; none touches
  a ruling):**
  - The owner read is `EntryReportService.get_for_user` → `EntryReportBackend.get_for_owner`: the
    typed report fetch (it keeps `get`'s `subject_uid` projection, which the generic
    `get_visible_to_user` would drop) behind the OWNER_ONLY clause that
    `build_search_visibility_clause` composes — ADR-085's first chokepoint, not a Python owner
    compare after a bare `get`. Absent and not-owned are one `Result.ok(None)` → one not-found.
  - `/entry-reports/detail` refuses through `refuse(...)`, so a non-owner gets the rendered
    not-found page at a real HTTP 404 (it was a 200 with a "Report not found" banner); the
    "service unavailable" branch is unchanged.
  - The fixtures pin the discriminator, not the writer's visibility value: in
    `test_gradebook_summaries.py` and `test_exchange_thread.py` one feedback report carries
    `visibility: 'private'` with an outcome (counted — PR 2a's post-migration shape) and the
    reflection carries `visibility: 'shared'` with no outcome (excluded), so a reader that
    still consulted the property fails in both directions.
  - The complete-workflow integration test replaces its two check steps with a Cypher count of
    the `SHARES_WITH` edge (1 after `share`, 0 after `unshare`) — the edge is the one record
    (ADR-088 §3); the four visibility/nonexistent access tests are deleted with the check.
  - The learning-loop skill's EntryReport graph sketch said `(teacher)-[:OWNS]->(report)`; the
    writer makes the student the owner (`COALESCE(student, author)`), so the sketch now says so.
  - No unscoped sibling survives beside the owner read (Codex P2 on #1415): the orchestrator's
    caller-less get_entry_report wrapper and the service's bare get (its only caller) are deleted
    with the backend protocol's get member; `EntryReportBackend.get` stays as the typed override of
    the universal by-UID member (its `subject_uid` projection serves the generic mixin paths).

### PR 2a — `visibility` means public-or-not

- **Deploy order: run the migration on AuraDB with the app stopped, before the new code serves**
  (§ Standing conventions → Migrations). The old code accepts `private`; the new code can't parse
  `shared`/`team` (`dto_helpers.py:110-129`), and until the restart the post-2b code still writes
  `shared`.
  - The migration is label-agnostic: `MATCH (n:Entity) WHERE n.visibility IN ['shared','team'] SET n.visibility = 'private'`.
  - Live 2026-09-24: 2 nodes carry `shared` (both EntryReports — safe once PR 2b's discriminator
    is live); 0 carry `team`. Census all labels.
- **The enum:** `Visibility` → `{PRIVATE, PUBLIC}`. Delete is_restricted, both can_view
  (`entity.py`, `user_owned_entity.py` — zero callers), and the unused EntityUpdateRequest /
  EntityResponse / EntityListResponse / EventResponse / EventListResponse (plus the
  `core/models/event/__init__.py` exports). Add stale_names DELETED rows.
- **Writers stop writing `'shared'`:** `exercise_backends.py:652` (a RevisedExercise, in
  `auto_share_with_student`) and `:1060` (a literal in `create_report_and_revised_exercise`);
  `exercise_backends.py:969` is the parameterised `visibility: $visibility` — its values come from
  `teacher_review_service.py:207,295` and `entry_report_service.py:492` (the journal path passes
  `private` at `:316`); reword the `:922-924` docstring. `set_visibility`
  (`unified_sharing_service.py:165`) becomes PUBLIC-only, with the missing TEACHER gate stated in
  the reworded `_SHARING_VISIBILITY_LADDER` reason.
- **Events:** remove the Visibility field from `events_form.py:41-45,72-76,104`,
  `EventCreateRequest`/`EventUpdateRequest`/`to_intent`/`EventUpdateIntent`, and
  `events_core_service.py:572`. Nothing reads it.
- **Spawn fix:** PS-engagement spawn copies a template's `public` onto student-owned instances.
  Add `visibility` to the managed set (`_spawn_orchestrator.py:366`); the migration also resets
  `public` on spawned user-owned nodes (live 2026-09-24: 0). Add a pin test.
- Delete the duplicate ingestion PUBLIC gate (`user_entry_ingestion.py:323-327,499-530`);
  `create_entry` already gates every door.
- **Tests:** `test_events_core_operations.py:359`, `test_event_update_intent_pipeline.py:181`,
  `test_activity_forms_render.py:276,286`, `tests/integration/user_entry/conftest.py:154`,
  `test_entry_report_ai_path.py:318`, the model default pins. Verified at PR 0, also whatever of
  these survives PR 2b — re-derived after it: `test_sharing_workflows.py:134,309,426`
  (visibility=Visibility.SHARED; the three surviving sites — the complete-workflow, unshare-owner
  and shared-with-list tests) and its `:202` fixture (the `test_unified_sharing_service.py`
  `visibility: "shared"` mock went with the access-check tests in PR 2b).
- **Docs:** CLAUDE.md § Content Sharing, SHARING_PATTERNS, REPORT_ARCHITECTURE, ENUM_ARCHITECTURE,
  the ADR-038 and ADR-040 (TEAM) notes, the learning-loop skill, `how-your-content-is-used.md`,
  PLACEHOLDER_INDEX:452, and `sharing-http-door.md` (its visibility-ladder section and the false
  "TEAM has no writer" line). Re-derive the stale_names anchors.
- **Ruled (PR 2a session, 2026-09-24 — engineering choices the census found unsettled; none touches
  a ruling):**
  - `create_report_node` takes no `visibility` parameter: every report writer stamps `private`
    (the one value a report can have — PUBLIC is a portfolio act the owner takes, never the
    writer's), so a parameter with one value at every call site is deleted rather than kept.
    The RevisedExercise grant (`auto_share_with_student`) writes its `SHARES_WITH` edge and
    no property.
  - `set_visibility` keeps its `Visibility` parameter and is PUBLIC-only by the enum: publishing
    requires a shareable entity, unpublishing (PRIVATE) never does. It still has no TEACHER
    gate of its own; the creation doors' gate (`create_entry`) is the only one, stated in the
    `_SHARING_VISIBILITY_LADDER` reason, `sharing-http-door.md` and ADR-038's note, so the door
    that reaches it adds one.
  - The ingestion `user_service` is deleted end to end — `build_user_entry_request`,
    `ingest_user_entry`, `UnifiedIngestionService.__init__` and the composition root — with
    the duplicate gate: it served nothing else, and a parameter that serves nothing reads as a
    second gate.
  - The migration is `collapse_visibility_to_public_or_not_2026_09.py`: label-agnostic on
    `shared` / `team`, and its spawned-`public` reset is scoped by the `SPAWNED_FROM` edge plus
    a `user_uid`, so a TEACHER's deliberate `public` on an authored entry is never touched.
  - The route fixtures keep pinning the discriminator in both directions with the two values
    that remain: the counted feedback carries `private` + an outcome, the excluded reflection
    `public` + none; the owner-read refusal seeds `public` (the writer's is `private`) so it
    proves the property is no grant either way.
  - The Events form section is "Type & Priority" (create) / the same name with `status` (edit);
    no form field, request field, intent field or service kwarg carries `visibility` for an
    Event — the model keeps the user-owned default.
  - `UpdateRequestBase` / `ResponseBase` / `ListResponseBase` stay: the deleted entity-wide
    classes were not their only inheritors (`TaskUpdateRequest`, `TaskResponse`, the template
    update requests).

### PR 3 — Bells that work + activity reports reach the student (B)

- **`NotificationType` StrEnum** (`core/models/enums/notification_enums.py`):
  - values, icon, a badge-variant string and a label;
  - the 4 existing members + `activity_report_received`, `submission_for_review`, `shared_with_you`;
  - typed through the model, protocol and service; an unknown stored value falls back to a generic bell.
- **Card links** go through `entity_detail_href(source_type, source_uid)` (`ui/patterns/entity_links.py:46`),
  with an override only for `submission_for_review` → `/teaching/review/{uid}`. This fixes 3 of 4
  broken links today. Remove the unreachable `revision_requested` fallback with its wrong source_type
  (`report_notification_handler.py:122-137`).
- **`submit_report`** (`activity_report_service.py:351`):
  - owner := subject, `created_by` := admin (a pass-through kwarg on `ActivityReport.create`);
  - drop `metadata.reviewed_by`;
  - no share edge (R3);
  - publish a new `ActivityReportWritten` (not ReportSubmitted) → a handler rings the student
    (`_event_wiring.py:214-240`; export in `core/events/__init__.py`).
- **Subject validation:** `ActivityReviewOrchestrator.submit_report` checks the subject exists via
  `_user_service.get_user` and returns `Errors.validation(field='subject_uid')`. Verified at PR 0:
  `get_user` returns `Result[User | None]` — handle `ok(None)`.
- **Generated-report reads keep excluding admin reports.** The filter is
  `coalesce(processor_type,'') <> 'human'` (null-safe; the fixtures lack processor_type).
  - Applied in `find_by_period` (`misc_backends.py:53`), `check_cooldown` (`:260`) and
    `get_previous_annotation` (`:298`), and in the comparison's `get_history` call
    (`progress_report_generator.py:469`). Verified at PR 0: `get_history` also feeds the student's
    GradeBook activity-report list (`user_entry_orchestrator.py:320`) — scope the exclusion to the
    comparison call only.
  - Also inside the **OPTIONAL MATCH WHERE** of both reads of the latest report: `user_context_queries.py:812`
    (LEARNER_STATE_QUERY, a MEGA-QUERY statement) and `:1113` (CONSOLIDATED_QUERY, the standard
    `build()`).
  - Run `test_user_context_plan_cache.py` on the edited statements (it covers both).
- `get_admin_snapshots` reads `created_by`.
- The detail page gets a "From <display name>" line. Admin read-back: none (ADR-042 strict), but the
  success fragment echoes what was sent and to whom. No migration (live 2026-09-24: 0 ActivityReports).
- **Tests:**
  - a NotificationType pin + a cards link test;
  - an `ActivityReportWritten` handler test;
  - `submit_report` owner, created_by, validation and event;
  - HUMAN fixtures in `test_created_at_window_coercion.py` and `test_rich_context_statement_equivalence.py`;
  - the golden `_expected_handler_counts` (`test_compose_execution.py:53`; the report-events rows
    sit near `:184`).
- **Docs:** REPORT_ARCHITECTURE:223-245,522 (+ fictional routes in touched sections); the
  learning-loop skill's `.claude/skills/learning-loop/reference.md:493` ("planned" → live — already stale: four handlers exist);
  docstrings `misc_backends.py:56`, `activity_report_service.py:364`.
- **Ruled (PR 3 session, 2026-09-24 — engineering choices the census found unsettled; none touches
  a ruling):**
  - The model carries `notification_type: NotificationType | None` — `None` is a stored value this
    build does not know (`NotificationType.from_string`), and the card renders it as a generic bell
    that still opens its source. The stored column stays the string value; only the writer's
    parameter and the read model are typed. `source_type` keeps its strict read (an unknown one is
    schema drift — only the service writes it).
  - The card's link is `notification_href` (`ui/notifications/cards.py`): `entity_detail_href`
    over the source, the `submission_for_review` override, and **no View link** when the source
    type has no detail page — never a `#` href.
  - The `revision_requested` handler refuses (logs an error, writes nothing) when the event carries
    no `metadata["report_uid"]` — both publishers always set it, so the deleted fallback (the entry
    uid under an ENTRY_REPORT source) was a bell that opened nothing.
  - The comparison's history exclusion is a `generated_only` flag on `get_history` (backend,
    protocol, service), so the GradeBook list keeps the admin's report and the comparison drops it
    at the query — not a Python filter over a `LIMIT 5` the admin's row could fill.
  - The human predicate is parameterised everywhere: `$human` (`ReportSource.HUMAN.value`) in
    the backends, and `$human_report_source` in the two user-context statements through the
    shared `STATUS_PARAMS` both statement families spread (Codex P2 on #1417 — the enum stays the
    one source of the value).
  - `ActivityReportWritten` carries `report_uid`, `subject_uid`, `author_uid`, `time_period`
    (`event_type = "activity.report_written"`); the handler's message names the period token.
  - The detail page resolves "From <display name>" in the route (the orchestrator's user service,
    `created_by` ≠ `user_uid`), falling back to the username; an unresolvable author renders no
    line rather than an error. The admin confirmation fragment echoes the subject uid, the period
    and the full text sent.
  - **Both fallbacks stand** (Codex P2 ×2 on #1417, rejected): the unknown-kind `None` because the
    notification list read is all-or-nothing — one unknown row would blank the page — and the
    null-safe human predicate because `ActivityReport.processor_type` is `ReportSource | None`,
    so a positive `IN [...]` would drop a legal row; it tightens when the model does.

### PR 4a — Exchanges survive exercise deletion (R12, R13)

- **Snapshot:** UserEntry gains `turn_in_exercise_uid` + `turn_in_exercise_title` (model + DTO).
  - They are SET in `create_with_exercise_link`'s link statement (`_user_entry_lifecycle_mixin.py:117-136`)
    with root = `coalesce(original.uid, exercise.original_exercise_uid, exercise.uid)`.
  - The values are RETURNed, and the created model is updated from them.
  - Verified at PR 0: the field name collides with a local in `user_entry_service.py:229` that means
    the submitted-against uid — rename the local, so the model field owns the name.
- **Backfill** (census/`--confirm`): root = coalesce(the direct FULFILLS_EXERCISE target,
  FULFILLS_REVISED_EXERCISE→REVISES_EXERCISE, RE.original_exercise_uid, **the entry's retained
  `fulfills_exercise_uid` property** — resolved through a RevisedExercise's `original_exercise_uid`
  when it names one). The property is the only trace of an exchange whose exercise was deleted
  before this PR (`DETACH DELETE` removes the edge, not the property), so it is the fallback that lets
  those exchanges satisfy R12 too; with no live exercise the title is the "exercise removed"
  placeholder (settled at PR 0 review). Count what stays unrecoverable (live 2026-09-24: 4 turn-ins,
  all with a direct edge to a live Exercise — all recoverable).
  It runs before the new code serves (§ Standing conventions → Migrations): un-backfilled turn-ins
  would drop out of their exchanges into Other feedback — the defect this PR fixes.
- **The snapshot becomes the exchange key.** `get_student_exchange_summaries_raw` and
  `get_exchange_thread_raw` group on `e.turn_in_exercise_uid`.
  - They OPTIONAL MATCH the exercise for the live title, with `exercise_removed = ex IS NULL`.
  - This deletes the UNION, the duplicate-resubmit rows bug (`_user_entry_report_query_mixin.py:193-208`),
    and any special fallback.
  - Keep PR 2b's `r.assessment_outcome IS NOT NULL` filter in both rewritten queries (the Other
    feedback half included).
  - The teacher mode keeps its per-entry gate.
  - `ExchangeThread`/`StudentExchangeSummary` gain `exercise_removed`.
- **GradeBook and `/exchange` UI:**
  - an "Exercise removed" badge on exchange lines;
  - Other feedback excludes snapshot-bearing entries;
  - the thread drops the exercise link when the exercise is removed (`exchange_thread.py:197`);
  - R13 subtitle (`ui/gradebook/summary.py:222`) + pin test.
- **Also in this PR:**
  - The queue copy-collapse and its dashboard twin key their lineage on the snapshot
    (`_user_entry_assessment_mixin.py:119-131,398-412`).
  - Report titles coalesce the snapshot (`exercise_backends.py:935-947,1036-1046`, and the
    duplicate rule in `retitle_entry_reports.py`).
  - `/submissions/history` keeps orphans (`_user_entry_content_mixin.py:159`).
  - The `/gradebook/{uid}` "Fulfills exercise" badge and the PS "Exchange →" link use the snapshot.
  - The UI label "Revised Exercise" becomes "Revision request" (label only; the entity stays).
    Verified at PR 0: the string is EntityType's core display name (`entity_enums.py:284`, read by
    `get_display_name()`), and some UI sites already say "Revision Request" (`report_item.py:28`,
    `exchange_thread.py:160`). **The enum is the one source** (settled at PR 0 review): change the
    display name in `entity_enums.py`, and make the hand-written UI strings read it — no render-site
    override.
- **Tests:**
  - orphan fixtures in `test_gradebook_summaries.py`;
  - the E3 fixture gets the real root edge + a length assert (`test_exchange_thread.py:205`);
  - SECOND_TEACHER gets not_found on a removed exercise;
  - the `test_gradebook_summary.py` row default.
- **Docs:** ROUTE_MAP /gradebook and /exchange; `docs/domains/user_entry.md:118-125` (the snapshot
  marks a turn-in); the learning-loop skill.
- **Ruled (PR 4a session, 2026-09-25 — engineering choices the census found unsettled; none touches
  a ruling):**
  - The snapshot title is the root's title at submission: `coalesce(original.title, exercise.title)`
    — a revision whose original is already gone snapshots the revision's own title, since that
    is the best title left. Readers prefer the live exercise's current title while the node
    exists and fall back to the snapshot (a stale snapshot never outranks a live title).
  - The exchange thread's not-found is "no turn-in against this uid", not "no exercise": the
    service no longer refuses on a NULL exercise projection — that refusal was the defect. A
    revision response carries BOTH edges (the writer's shape), so `revision` and
    `via_revised_uid` are no longer exclusive on `ExchangeThreadEntry`; the snapshot key yields
    one row per entry, which is what deletes the duplicate-resubmit rows.
  - The queue's rank keeps the edge revision where the edge still exists (a pattern
    comprehension inside the `NOT EXISTS`, so a deleted exercise's copies rank on `created_at`
    alone — the writer mints revision and created_at in the same order, so the collapse is
    unchanged). The lineage guard is `turn_in_exercise_uid IS NULL` (not a turn-in → passes
    through), replacing `ex IS NULL`.
  - The three teacher projections that named the exercise (`get_review_queue_by_groups`,
    `get_entry_detail_for_teacher`, `get_student_submissions`) coalesce the snapshot, so the
    review page's "View exchange thread" and the student hub's exercise title survive the
    deletion too; the `/gradebook/{uid}` chain projection returns the snapshot with
    `removed: true` and the page hides "Request AI feedback" on a removed exercise (the reviewer
    reads the exercise's instructions).
  - The backfill's turn-in trace for an edge-less entry is the `Interaction` `RECORDS` edge
    (minted only when a frozen copy files); a property-only entry with no trace is a living vault
    note — listed as "left untouched", never stamped. Live census 2026-09-25: 4 candidates, all
    via a direct edge to a live exercise, 0 placeholder titles, 0 intent-only rows.
  - The section's "SECOND_TEACHER gets not_found on a removed exercise" is pinned as the gate
    being unchanged by the deletion: each teacher keeps exactly their classroom's entries
    (SECOND_TEACHER sees only the second-class turn-in), the unrelated teacher and a student
    with no turn-in stay not-found — a removed exercise widens nobody's scope.
  - `EXERCISE_REMOVED_TITLE` ("Exercise removed", `core/models/user_entry/user_entry.py`) is the
    placeholder title the backfill stamps with no live node and the last fallback of both
    reads; the UI badge label `EXERCISE_REMOVED_LABEL` (`ui/gradebook/summary.py`) is the same
    words on the line, the thread header and the detail badge.

### PR 4b — Two lineage predicates that never match

- `user_context_queries.py:940-944` pending revisions (in SUBMISSION_STATS_QUERY).
- `revised_exercise_service.py:83`: the same fix (its `_graph_enrichment_patterns` entry, `:82-87`).
- **Verified at PR 0 — accept both edges, don't swap.** The plan said `FULFILLS_EXERCISE→re` →
  `FULFILLS_REVISED_EXERCISE`. But the writer puts only `FULFILLS_EXERCISE` on a RevisedExercise that
  has no `REVISES_EXERCISE` edge (`_user_entry_lifecycle_mixin.py:130-134`); that edge is written only
  when an original exists (`exercise_backends.py:1115-1117`) and PR 4a's scenario (an exercise
  `DETACH DELETE`) removes it. A swap would regress that case: match
  `-[:FULFILLS_EXERCISE|FULFILLS_REVISED_EXERCISE]->(re)`. In the enrichment entry, both edges are
  matched either way — as one union if the pattern tuple accepts one, else as two patterns (an
  implementation detail with one behaviour).
- Add a negative case in `test_user_context_lifted_statements.py:66` and run the plan-cache test.
- Live acceptance setup (Mike's OK — it writes to AuraDB): resubmit against the live RevisedExercise
  (re_c4e92951), which writes the graph's first `FULFILLS_REVISED_EXERCISE` edge.
- **Ruled (PR 4b session, 2026-09-25 — engineering choices the census found unsettled; the first
  two are Mike's, on the resubmission route; none touches a ruling):**
  - **A turn-in against a revision reaches the root exercise's reviewers.** The census found the
    resubmission itself broken, not just the two readers: both `teachers` group lookups
    (`query_exercise_groups_for_member`, `query_default_groups_for_curriculum_submission`) matched
    the target uid — a revision is never `SHARED_WITH_GROUP` and has no `scope` — so a Teacher
    resubmission of a revision filed no `SUBMITTED_TO_GROUP`, and with no failed target the
    compensation never fired: an entry no teacher could open. Both lookups resolve a RevisedExercise
    to the exercise it revises (the `REVISES_EXERCISE` coalesce the writer and
    `count_entries_for_exercise` already use); a revision whose original is gone resolves to
    nothing. Ruled by Mike: fix here, not at PR 7 (whose zero-reach rule would refuse loudly but
    reach no one).
  - **A revision is usable by the student it names.** The exercise-use check
    (`query_user_can_use_exercise`) accepted an owner, a group member or an IN_PROGRESS PathStep, so
    the door refused the named student with 403 before anything persisted — the revision detail
    page's own submit link led there. The revision's `student_uid` is a claim; the refusal message
    names it.
  - The enrichment entry is one union pattern (`FULFILLS_EXERCISE|FULFILLS_REVISED_EXERCISE`,
    incoming, `submissions`): the renderer interpolates the tuple's relationship string verbatim,
    so a union is one `OPTIONAL MATCH` and one `submissions_list`, never two context fields.
  - The negative case seeds both answered shapes beside the pending one — the writer's
    (`FULFILLS_EXERCISE` on the root + `FULFILLS_REVISED_EXERCISE` on the revision) and the
    orphan's (`FULFILLS_EXERCISE` on the revision alone) — so a swap fails as surely as the old
    predicate did; the enrichment is driven through `graph_aware_faceted_search` on a real backend.
  - Live acceptance 2026-09-25 (branch app on :8001, the upload door as linguistic76): the
    resubmission wrote 3 nodes (UserEntry `ue_d8d8a7bf`, its `RECORDS` Interaction, an
    iteration Insight) and 8 edges, including the graph's first `FULFILLS_REVISED_EXERCISE` and the
    `SUBMITTED_TO_GROUP` to the default group; the old predicate still listed `re_c4e92951` as
    pending and the new one listed nothing; the GradeBook line read Waiting, `/today` dropped the
    pending revision, the admin queue collapsed the revision-requested copy and listed the new one,
    and its review fragment opened. Deleted afterwards by uid (3 nodes, 8 edges; the Interaction and
    Insight do not cascade) — the content was a scripted placeholder, not Mike's response.

### PR 5 — Recipients can open what's shared with them (R4, R6)

- **`SearchVisibility.OWNER_OR_AUDIENCE`.** `build_search_visibility_clause` (`crud_queries.py:285`)
  gets an explicit branch built on the audience fragment, using `ownership_property` for the owner arm.
  - **This PR creates the fragment** (see Architecture) and is its first consumer.
  - The SCOPE_AWARE fall-through becomes an explicit `is SCOPE_AWARE` check, with a raise for unknown members.
  - A unit test is parametrized over every member.
  - There is no code precedent (ADR-086's `OWNER_OR_ATTENDEE` is design-only).
- **DomainConfig `read_visibility`** (default = `search_visibility`); UserEntry = OWNER_OR_AUDIENCE.
  `get_visible_to_user` composes `read_visibility`. Search is untouched (Refinement 4).
  - Verified at PR 0: two sites hand a visibility to the backend read — `base_service.py:667-669`
    and `ExerciseService.get_exercise_for_user` (`exercise_service.py:365-367`); switch both. The
    "pass `search_visibility`" contract text lives at `_crud_mixin.py:354-355`,
    `base_protocols.py:510`, `base_service.py:641-643` and ADR-085 §2.
- **`/gradebook/{uid}` is viewer-aware:**
  - the owner sees today's detail;
  - an audience member sees an R6 recipient card, with **no status badge and no /exchange link**;
  - anyone else gets `refuse_not_found` (a real 404; today it's 200).
  - Verified at PR 0: the route does not reach `get_visible_to_user` today — it is
    `orchestrator.get_entry` → `UserEntryService.get_entry`, a bare `get()` plus a Python owner check
    (`user_entry_service.py:441-451`). Rewire that read, then branch owner vs audience on
    `entry.user_uid`.
- **Download:** a new `/gradebook/{uid}/download` returns text/markdown from content behind the same
  read (pattern `exercises_api.py:330`). The journal file route is not widened.
- **Retire** the peer route /groups/{g}/entries/{e}, query_user_entry_shared_with_group,
  get_user_entry_shared_with_group, and the groups peer-entry card module (peer_entry.py; reuse its
  chrome and attribution). Add stale_names rows; `/groups` tiles link to `/gradebook/{uid}`.
  - Verified at PR 0: the card body renders `processed_content` (an R6 violation) — do **not** carry
    the body over. Also delete the `ui/groups/__init__.py:5` re-export and the `group_page.py`
    docstring references, and update `test_groups_hub_routes.py:48` and
    the four get_user_entry_shared_with_group unit tests in `test_unified_sharing_service.py`. The tile href that becomes `/gradebook/{entry_uid}` is
    built in `ui/groups/shared_preview.py:38`, whose docstrings (`:4`, `:55`) cite the retired route.
- **Tests:**
  - an access matrix: ex-member, deactivated group, revoked share, and SUBMITTED-only teacher all get 404;
  - the recipient response has no report content;
  - extend `test_chunk_retrieval_visibility.py:187` (Askesis stays OWNER_ONLY) and `test_vector_search_backend_scope.py`;
  - `test_owner_only_ownership_invariant.py` is untouched (search is unchanged).
- **Docs:** SEARCH_ARCHITECTURE, the ADR-085 note (fix its drifted cites while there), ROUTE_AUTH_REQUIREMENTS
  (verified at PR 0: it has no gradebook/groups row — add one, e.g. an audience-read rule), ROUTE_MAP,
  SHARING_PATTERNS:310,348,599, the search skill, the `metadata_enums.py:292` and `domain_config.py:167`
  docstrings, and `base_service.py:641-643` (it repeats ADR-085 §2's "agree by construction"). The
  "amended by ADR-088" notes this PR lands: ADR-085 §2, ADR-042 §7 (a share reaches members and
  owners of an active group) and ADR-038 (a link alone grants access). SEARCH_ARCHITECTURE lists the
  audience fragment as a composition point.
- **An accepted window (verified at PR 0):** until PR 6a, a person share is not co-membership-checked
  (the JSON `share_with_users`, forms `recipient_uids`), and this PR makes it openable. Live
  person shares on UserEntries: 0.
- **Live acceptance setup (Mike's OK):** before PR 6a/6b the only person-share writer is the JSON
  `share_with_users` on `POST /api/user-entries`. Share with a recipient Mike can log in as
  (user_admin, or the second account once it exists); the non-recipient is a third account.
- **Ruled (PR 5 session, 2026-09-25 — engineering choices the census found unsettled; none touches
  a ruling):**
  - The fragment is `build_audience_fragment(entity_alias)` beside the clause builder in
    `crud_queries.py`: it references `$user_uid` and introduces no parameter, and the clause's
    `OWNER_OR_AUDIENCE` branch is `(n.{ownership_property} = $user_uid OR <fragment>)`. Without a
    user it applies no clause, the OWNER_ONLY contract (no audience exists for nobody).
  - `DomainConfig` refuses `search_visibility=OWNER_OR_AUDIENCE` at construction: it is a read
    declaration by definition (Refinement 4), so the enum member cannot widen a search by a typo.
    `get_read_visibility()` is the derivation; `BaseService.read_visibility` rides beside
    `search_visibility`, and both `get_visible_to_user` call sites pass it.
  - SCOPE_AWARE keeps its own group arm (`MEMBER_OF` only, no `is_active`): it is Exercise's
    ADR-038/040 audience, and re-basing it on the fragment (owners admitted, strict `is_active`) is
    an Exercise-domain change this arc does not make. The fall-through is now an explicit
    `is SCOPE_AWARE`; any other member raises.
  - `UserEntryService.get_entry` (the owner read behind updates, deletes, journals and the API
    get) is untouched — an owner read, not an unscoped sibling. The page and the download read
    through `UserEntryOrchestrator.get_entry_for_viewer` → `BaseService.get_visible_to_user`; the
    owner-versus-recipient branch compares `entry.user_uid` with the viewer. The Askesis bundle
    fetch (`_fetch_entities_by_uid`) also composes `read_visibility`, but it serves the activity
    domains only, so no UserEntry widens there; chunk retrieval stays OWNER_ONLY (pinned on a real
    index: a `SHARES_WITH` to the viewer grounds nothing).
  - The recipient card (`ui/gradebook/recipient_card.py`) renders inside `BasePage` with the
    Shared page's chrome (`active_page="shared"`), the owner's page keeps the GradeBook sidebar,
    and the refusal is the GradeBook sidebar page at 404 (`refuse` + `render_activity_sidebar_error`
    — a stranger and a missing uid are one body). The card's badge is the fixed "Shared with you";
    the derived "Revised after feedback" badge is PR 6c's.
  - The `.md` download (`adapters/outbound/user_entry_renderer.py`) carries the title, description
    and `content` — the same body for the owner and a recipient — and never `status`,
    `processed_content` or feedback; the recipient contract is enforced by what the renderer
    omits, not by who calls it. A recipient who cannot be resolved to a display name gets no
    "From" line rather than a uid.
  - `GroupSharedPreviewList` lost its `group_uid` parameter with the tile href; `GroupSharesPage`
    keeps its own for the "Back to Groups" link.

### PR 6a — One audience vocabulary

- **`AudienceSpec`** (`core/models/user_entry/audience.py`) + `AudienceResolver` are the one parser <!-- planned -->
  and applier. The vocabulary table is above.
  - It accepts lists and preserves case (usernames match `User.title` exactly; today's vault parser
    lowercases, `user_entry_ingestion.py:84`).
  - It replaces the web parser (`user_entry_api.py:181`) and the vault parser with its private spec
    (`user_entry_ingestion.py:60-107`).
  - The JSON door's raw `share_with_*` fields are routed through it. **Verified at PR 0 (contract,
    settled at PR 0 review):** the JSON `share_with_users` carries user **UIDs**
    (`user_entry_request.py:126-128`) while the vocabulary's person form is `user:<username>`. The
    JSON door speaks `user:<username>` through `AudienceSpec` and the raw uid field leaves the
    contract (ADR-088's one vocabulary covers the JSON API; One Path Forward); the resolver maps
    username → uid internally.
  - It retires PR 1's interim TEACHER_REVIEW mapping. **Verified at PR 0 (contract, settled at PR 0
    review — R5, ADR-088 §8):** once retired, a TEACHER_REVIEW request whose explicit audience names
    no feedback target (`teachers` / `teacher:<group_uid>`) is **rejected with guidance** ("to ask
    this group's teacher for feedback, use `teacher:<group_uid>`") — with or without an exercise, at
    both doors, on a non-content field (`batch.py:84-86`). An absent audience still means `teachers`,
    and `[teachers, group:<uid>]` (submit and share) is valid. Never turn `group:<uid>` into a silent share there: an explicit group share
    suppresses the exercise auto-share (`audience_resolver.py:282-285`) and counts toward
    `any_success`, so nothing would reach the queue. Reword the `test_review_queue_copy_collapse.py`
    docstrings (`:100`, `:326`) to `teacher:<group_uid>`.
  - `teachers` keeps the member intersection and the curriculum default-group fallback
    (`audience_resolver.py:282-317`, `sharing_backend.py:316-345`); test that a curriculum turn-in
    still reaches the default group's owner. On a non-TEACHER_REVIEW pipeline it writes no link
    (PR 1's pipeline-gap contract).
  - **Verified at PR 0 — the vault window until PR 8 (contract, settled at PR 0 review — R9).**
    `create_entry` step 5 runs
    `resolve_and_share` on the living-note upsert too (`user_entry_service.py:343-348`), and
    `_file_submission_copy` does not carry the audience, so a vault `user:` / `teacher:` applied here
    would share a mutable draft (against R9) — and be data PR 8 must retract. So on an
    absolute-path vault note, `user:` / `teacher:` are parsed and validated but not applied; the sync
    warns "applies when `status: submitted` files a copy (PR 8)". Never write `SUBMITTED_TO_GROUP` on
    a non-TEACHER_REVIEW entry.
- **R8 co-membership** is enforced where person links are written: the resolver's user step, plus
  `form_submission_service` `recipient_uids` (`share_with_admin` stays exempt).
  - **Every door validates every audience target before its first write** (settled at PR 0
    review). For a UserEntry that is `AudienceResolver.validate` / `validate_references`, which
    `create_entry` already runs before it persists (`user_entry_service.py:153-162`): it resolves and checks each `user:` (exists, co-member) and each
    `group:` / `teacher:` target (exists, active, the owner is a member or owner) — today the entry
    is written (`user_entry_service.py:289-314`) before the resolver applies the audience
    (`:343-350`), so a refusal found there would error over a committed entry, leave a mixed list
    half-shared, and duplicate on retry. The post-persist step then writes only validated targets.
  - **The writes stay guarded, and a late refusal compensates** (settled at PR 0 review): validation
    and the writes are separate operations, so a membership removal or a group deactivation can land
    between them. Each audience write re-checks its own authorization in its statement — the group
    MERGE's membership/active guard (PR 1), and a co-membership guard added to the person
    `SHARES_WITH` MERGE — and when a guarded write refuses after validation passed, step 5a
    compensates everything this call wrote (the entry it created and every edge it wrote), for
    forms as for UserEntries. No authorization-less edge is ever written.
  - **Every audience target is validated before anything is written** (settled at PR 0 review):
    `submit_form` persists the submission and its relationships (`form_submission_service.py:143-149`)
    before `_share_on_submit` runs (`:158-159`), so a refusal found afterwards would report failure
    over committed work, leave a mixed list half-shared, and duplicate the response on retry. Resolve
    and check every target first — each person recipient (exists, co-member) **and** the group
    (exists, active, the submitter is a member or owner, as PR 1's guard requires); a refusal fails
    the submit with nothing written. The post-submit share door does the same over its whole target
    list before its first edge.
  - The helper is `shares_group_with(owner, recipient)`, which excludes default-group co-membership.
  - One uniform not-found error covers both unknown and non-co-member usernames.
  - **The owner is never a person recipient** (settled at PR 0 review): `user:<own username>` is
    refused at validation — co-membership would otherwise accept the same user on both sides and
    write a self-`SHARES_WITH`, putting the entry under both *Shared with you* and *Your wall* and
    ringing the owner for their own work.
  - Verified at PR 0: forms' `_share_on_submit` swallows share failures (it logs a warning and
    returns `None`, and `share_submission` then returns `Result.ok(True)`). The helper returns a `Result` (or
    an explicit outcome) propagated through both the submit and the post-submit
    (`/api/form-submissions/share`) callers, so a refused recipient is an error, never a false
    confirmation (settled at PR 0 review). The default group is
    recognised only by its uid prefix (`sharing_backend.py:337`; Group has no flag) — name the
    mechanism in the PR (SKUEL034 excludes `startswith` by ruling; ADR-013 still applies to the
    owner, who is read from the `:OWNS` edge).
- **Journal privacy:** the resolver refuses to share entries where `not pipeline.allows_sharing()` or
  `entry.private`. "Share" is R1's verb — a `group:` / `user:` / `public` target; a feedback request
  (`teachers` / `teacher:`) is Submit, so a `private: true` entry may still ask a teacher for
  feedback (settled at PR 0 review; `private` is the companion-retrieval opt-out, and nothing in the
  rulings stops a student asking for feedback on such a note). Verified at PR 0: the pipeline half already exists at create
  (`audience_resolver.py:104`); applying it to post-create shares amends ADR-054 §5's "lifetime
  audience" sentence, and refusing `entry.private` is a **new rule** that reverses the documented
  `private` ⊥ sharing contract (`user_entry.py:108-113`, `user_entry_request.py:73-80` — update both
  docstrings). ADR-088 records it as its amendment of ADR-054 §5.
- **Tests:** the parser matrix (including `private` combined with another value → a parse error);
  co-membership; uniform errors; the JSON door; forms recipients.
- **Docs:** the "amended by ADR-088" notes on ADR-054 §3 (the audience options and the YAML
  `audience:` rows — `teacher:<group_uid>`, `user:<username>`, lists), §4 (the turn-in edge), §5
  (the lifetime gate and the `private: true` refusal) and its Consequences ("post to a group feed");
  the `private` docstrings named above.
- **Live acceptance:** a JSON-door `user:` share to a co-member (user_admin — the Default Group's
  owner — or a member of a non-default group) succeeds; a Default-Group-only member gets the uniform
  error (this also tests the exclusion); the vault `[teachers, user:<name>]` parse is a unit case —
  applying it is PR 8's and the arc-close verification's.

### PR 6b — Share, Stop sharing, and the two-sided Shared page (R2, R3, R6–R8, R10)

- **Routes:** `POST /api/user-entries/{uid}/share` and `/unshare` (owner, CSRF). <!-- planned -->
  - UserEntry only: any other entity gets a 404.
  - Only `group:` / `user:` are accepted.
  - Unshare calls `unshare` / `unshare_from_group`, which can't touch SUBMITTED_TO_GROUP.
  - A Share button sits on the `/gradebook/{uid}` owner view and on each version in the exchange thread.
  - Verified at PR 0: the share gate (`_check_shareable`) refuses an `archived` UserEntry. **R2
    ("anything, any time") lifts it** (settled at PR 0 review): the UserEntry branch accepts every
    status, and the privacy refusals (a non-sharing pipeline, `private: true`) are the only ones.
    The activity and curriculum branches are unchanged. Test that an archived entry shares.
- **Candidates:** `get_share_candidates` returns my student groups + the groups I OWN, and person
  candidates from R8 co-membership, never the owner. They are server-rendered checkboxes. Verified at PR 0: a new
  method composing existing reads. The student-groups half exists (`group_service.py:194`
  `get_user_groups(role="student")`), and so does the owned-groups half — twice:
  `get_teacher_groups_with_stats` (`collab_backends.py:183`, `OWNS`→Group with no `is_active` filter;
  its `pending_count` is a PR 1 teacher reader; live on `/teaching/groups`) and
  `UserContext.teacher_groups` (`user_context_queries.py:1468`). Extract the `OWNS` match and reuse
  it — never a third owned-groups reader — and **filter candidates to active groups**
  (`is_active = true`; settled at PR 0 review): `create_group_share` refuses an inactive group and the
  audience fragment never exposes one, so the Share panel never offers it.
- **Shared page** (`/profile/shared`):
  - **Shared with you** is one UNION query, deduped by entity uid, collecting the via-list:
    - direct `SHARES_WITH` of `user_entry` + `form_submission` (forms kept as today), excluding my
      own entries (the self-share guard's second half — PR 6a refuses the write);
    - SHARED_WITH_GROUP UserEntries through the audience fragment, excluding my own;
    - the sharer is the owner; `shared_at` goes through `toString`;
    - no subject/exchange line for peer entries;
    - FilterBar: Type · Shared by · Via;
    - the method gets a fresh name — never the deleted name of the old group-inbox query.
  - **Your wall** (`query_shared_by_me`) shows UserEntries only: one row per item, audience chips
    with × Stop sharing.
  - `get_privacy_summary.shares_granted` reads the same query. Verified at PR 0: today it reads
    ActivityReportBackend.get_shares_granted (`misc_backends.py:152`; PLANNED, no route) — the
    rewire adds a sharing-backend dependency to `ActivityReportService` and orphans
    get_shares_granted (protocol `report_protocols.py:369`, mock `test_activity_report_service.py:26`).
    **Delete it** with its protocol member, mock and doc references (settled at PR 0 review — a
    consumer-less second access-list query would drift from the wall's).
  - Rebuild the `/groups` tab list on the audience fragment and delete
    query_user_entries_shared_with_group (the single-entry peer read is PR 5's).
- **R3 cleanup:**
  - Drop the student's self-SHARES_WITH on EntryReports (`exercise_backends.py:990,1077`; the
    create_student_share params at `teacher_review_service.py:208,296` and `entry_report_service.py:317,493`).
    Verified at PR 0: the self-share at `exercise_backends.py:1077` is unconditional (it ignores the
    param), and three docstrings assert the grant (`entry_report_service.py:17,454`,
    `teacher_review_service.py:7`).
  - A migration deletes the existing ones (live 2026-09-24: 2), with the app stopped
    (§ Standing conventions → Migrations: the old code writes the self-share unconditionally).
  - Feedback types leave the Shared page. The RevisedExercise→student grant stays but is not listed
    (live: 1).
- **Delete** get_shared_with / get_groups_shared_with with their backend queries, protocols, tests
  and PLANNED entries; also remove unshare's PLANNED entries.
  - Verified at PR 0: **stale_names has no rows for these — ADD `DELETED` rows** (the
    `sharing-http-door.md` precedent), with ALLOWED_OCCURRENCES for historical lines. Once the four
    PLANNED entries go, _SHARING_REVOKE_AND_ACCESS_LIST (`detect_bloat.py:500`) is orphaned —
    delete it. The `## Sharing HTTP Door — Operations on Existing Shares` heading in
    `deferred-work.md` stays: `_SHARING_VISIBILITY_LADDER.blocked_by` points at it.
  - Docs naming them in backticks outside the list below: ADR-038, ADR-042 §8,
    PROTOCOL_REFERENCE:466, RELATIONSHIPS_ARCHITECTURE:187, the deferred-work MOC line body (heading
    unchanged), `.claude/skills/learning-loop/reference.md:333`, SHARING_PATTERNS:235,319,351,405,413.
- **Person-share bell:**
  - `create_share` returns `created` (`MERGE … WITH r, r.shared_at IS NULL AS created …`);
  - `ShareOutcome.newly_shared_users`;
  - `EntryShared` is published by UserEntryService and the share route → `shared_with_you`;
  - the golden table gets `EntryShared`;
  - group shares ring no one.
- **Tests:**
  - `test_shared_with_me_view.py` (feedback cards gone);
  - `test_sharing_workflows.py:184-240`;
  - `test_entry_report_ai_path.py:141-195` (no self-share);
  - the groups hub routes;
  - wall / unshare / type refusal;
  - the bell fires once per new link;
  - verified at PR 0: the four get_user_entries_shared_with_group unit tests
    (`test_unified_sharing_service.py:618-700`) go with the query they cover.
- **Docs:** ROUTE_MAP /profile/shared and /groups, SHARING_PATTERNS, the sharing-http-door case file
  (revoke half done), `shared_view.py` and `user_profile_ui.py` docstrings, the navbar inbox label
  (verified at PR 0: there is no tooltip — the `sr-only` "Shared with me" label and the
  `_shared_inbox_button` docstring, `navbar.py:180-190`), HUB_PAGES, the skuel-ui skill; the
  "amended by ADR-088" notes on ADR-038 (the door, Your wall replaces the access list, the
  person-share bell, and §4's archived refusal lifted) and ADR-042 §8 (the access-list method); the
  stale_names reason at `stale_names.py:265` that names the live group reader.

### PR 6c — Badge and nudge (R2)

- **Badge (derived, never stored):**
  - "Reviewed · Teacher/AI" = the entry has a report with `assessment_outcome IS NOT NULL`;
  - "Revised after feedback" = an earlier entry in the same (owner, `turn_in_exercise_uid`) exchange
    has such a report with `report.created_at < entry.created_at`.
- It shows on Shared-with-you cards, the wall and the recipient card.
- **Nudge:** a GradeBook exchange line whose latest entry is a post-feedback revision offers
  "Share your revised work" → the Share panel, preselected.
- **Verified at PR 0:**
  - It depends on PR 4a's persisted `turn_in_exercise_uid` (today a local in `create_entry`), and on
    PR 5 (the recipient card it badges) and PR 6b (the wall, the cards, the Share panel the nudge
    opens).
  - **Timestamp trap:** `UserEntry.created_at` is stored as an ISO string (`neo4j_mapper.py:209-211`)
    while `EntryReport.created_at` is a native DateTime (`exercise_backends.py:970`); a raw `<`
    compares DateTime to String and yields null — a never-matching predicate. Parse the entry side
    as a DateTime in Cypher (`datetime(entry.created_at) > report.created_at`, as
    `telemetry_retention_backend.py:150` does for ISO-string stamps; a string with no timezone reads
    as UTC). Do not copy the exchange queries: they only emit `toString()` on both sides and never
    compare the two stamps.
  - `StudentExchangeSummary` (`core/ports/query_types.py:2994-3016`) cannot tell "an earlier entry has a report
    older than the latest entry" — `get_student_exchange_summaries_raw`
    (`_user_entry_report_query_mixin.py:236`) needs a new column.
- Tests for both.
- Live acceptance setup (Mike's OK): a second turn-in in one exercise exchange, made after its
  report — the Gentle Return exchange (ue_bd5ce4a1, `revision_requested`) is the natural candidate.

### PR 7 — The Submit page asks two questions (C)

- **The form** (`ui/user_entry/forms.py` + the Alpine `submit` component at `static/js/skuel.js:2606`):
  - **Ask for feedback?** Teacher (default) / AI / No.
  - **Share with** (optional, collapsed): candidate groups and people, plus the existing Portfolio
    "coming soon" row.
- **Teacher** works without an exercise (`teachers` → all my teachers; the form lists
  `teacher:<group>` when I'm in several groups).
- **Ruling for Mike (added after PR 4b): does a turn-in keep the title the student typed?** The
  `UserEntryCreated` linker (`core/services/user_entry/exercise_linker.py`) overwrites every
  turn-in's title with the root exercise's snapshot title plus a revision suffix ("The Gentle
  Return v3") and stores `revision_number` on the node — the form's own title field is discarded.
  Every exchange reader keys on `turn_in_exercise_uid` / `turn_in_exercise_title` (PR 4a), so
  the entry title identifies nothing; the revision number lives on the `FULFILLS_EXERCISE` edge
  and the `revision_number` property. Decide before the form is rebuilt:
  (a) keep the retitle (the form's title field is then cosmetic — drop it or label it as ignored),
  or (b) drop the retitle and keep the student's words, keeping the `revision_number` write.
  Census for (b) — the surfaces that print `entry.title` for a turn-in and would show an untitled
  upload's filename: `/submissions/history` (`_user_entry_content_mixin.py`, `get_history`), the
  queue rows and their dashboard twin (`_user_entry_assessment_mixin.py`, `entry.title AS
  title`), the student hub (`get_student_submissions`), the review page header, the GradeBook
  detail `/gradebook/{uid}`, and the `/exchange` thread entries. Either way the `.md` download
  name and the vault copy's filename are unaffected (they derive from the uid).
- **AI** is offered only with an exercise: it's graded against the exercise. After submitting, the
  entry page shows the existing gated "Request AI feedback" button (stated honestly on the form).
  Why two steps (kept at PR 0 review, where Codex proposed that submit summon the reviewer): the
  LLM reviewer is one door, `POST /api/exercises/report` — owner-summoned and gated per user by the
  intelligence tier (ruled 2026-07-03, systems review R1; ADR-043). The form's AI option says the
  next step and never promises an automatic report; making submit call the reviewer is a ruling for
  Mike, not a PR 7 edit.
- **The zero-reach rule moves into `create_entry` 5a:** a TEACHER_REVIEW entry with no successful
  submission is compensated, with an error on a non-content field, so the vault reports it as an error.
  Delete the vault duplicate (`user_entry_ingestion.py:744-760`) and update `test_user_entry_service.py:538`.
  Verified at PR 0: `batch.py:84-86` classifies `audience` (and status, pipeline, uid, metadata,
  private, je_use) as content fields — ignored-with-reason, not an error — so the field must be none
  of those. The moved rule reads `submitted_groups` (matched), never the created subset, and the
  compensating delete applies only to a node **this call created**: the create branch always, and
  the upsert branch (`request.uid` set) only when the upsert reports it created the node (a
  deterministic uid can be new) — so have the upsert return that flag. A pre-existing living node is
  never deleted: zero reach is returned as an error. The Interaction audit node `create_entry` writes
  at step 3 must not outlive a compensated entry (a `DETACH DELETE` of the entry leaves it orphaned,
  falsely recording a submission). The contract is the invariant — no Interaction outlives a
  compensated entry; create it after the zero-reach check (preferred) or compensate it with the entry
  (settled at PR 0 review). The upsert branch stops carrying TEACHER_REVIEW
  vault notes at PR 8.
- **Teacher bell:**
  - `UserEntryCreated` gains `submitted_group_uids`, filled from newly created SUBMITTED_TO_GROUP
    links (PR 1's `newly_submitted_groups`, the `created` subset), so re-syncs never ring;
  - the handler notifies the group owners (`get_owner_uids_batch`, `_relationship_crud_mixin.py:423-460`
    — it unions the `OWNS` edge with the `user_uid`/`owner_uid` spellings), excluding the submitter,
    as `submission_for_review`. Verified at PR 0: the helper does not deduplicate (a group created
    through `GroupService.create` carries both `owner_uid` and an `OWNS` edge, and one teacher may own
    several targeted groups), so the handler builds one unique recipient set across all submitted
    groups first — one submission rings each teacher once;
  - bump the golden count (`test_compose_execution.py:178`).
- **Rename:**
  - "Submit" becomes the header, the sidebar row (`ui/workbench/nav.py:20`) and the MOC card.
  - The one route is `/submissions/submit`; `/submissions/exercise` and today's legacy `/submit` <!-- planned -->
    302 are **deleted, not redirected** (One Path Forward — changed at PR 0 review from the plan's
    redirects: nothing outside the app links to them — no download, service-worker or manifest
    reference). Every caller is updated in this PR.
  - Update every `/submissions/exercise` reference. Verified at PR 0: `git grep` finds 24 lines — 1
    false match (ADR-054:53, a model path) and 2 `done/` archives, so ≈21 live sites: user_entry.md:205,220,
    REPORT_ARCHITECTURE:393, CORE_SYSTEMS:42, UNIFIED_INGESTION_GUIDE:530, ROUTE_MAP:122 (missing from
    the plan's list), the learning-loop and skuel-ui skills, `exchange_thread.py:7`, `user_entry_ui.py`,
    CLAUDE.md's door line.
  - Update the Alpine registry docs + the `scripts/smoke_test.py:131` constructor fixture.
- New form tests (none exist).

### PR 8 — Every vault note submits the same way (R9)

- **Identity gates:**
  - The submit signal is `status: submitted` alone. Provenance is the persisted living `entry.uid`.
  - Uid-less notes with `fulfills_exercise_uid` become drafts too: drop that clause from the
    prior-uid gate (`user_entry_ingestion.py:463-469`) **and** its mirror (`ingestion_tracker.py:153-159`)
    in lockstep.
  - **Verified at PR 0 — the first sync.** Dropping the clause helps only from the second sync on.
    On a note's first sync `prior_uid` is None, so `create_entry` treats a note carrying
    `fulfills_exercise_uid` as a turn-in (`user_entry_service.py:229`: fresh node,
    `FULFILLS_EXERCISE`, revision, Interaction), and the next sync upserts that frozen turn-in in
    place. PR 8 must also stop a vault file from ever entering the turn-in branch.
- **The copy:** the generalised `_file_submission_copy` (`user_entry_ingestion.py:693`) files a frozen
  copy via `create_entry` with the note's `audience:` list.
  - Default `teachers`, whatever the living pipeline; the pipeline is TEACHER_REVIEW when a feedback
    target is present, else NONE. AI is never sync-triggered (ruling 2026-07-04).
  - `status: submitted` + `audience: private` is an error ("nothing to submit to") — on a non-content
    field (`batch.py:84-86`, see PR 7).
  - The copy metadata carries no `vault_file_path`.
  - **The copy carries the note's `private` flag** (settled at PR 0 review): today's helper does not
    copy it, so `UserEntryCreateRequest.private` would default the frozen copy to `false` and slip
    past PR 6a's refusal to share a `private: true` entry. The flag is part of the snapshot and of its
    fingerprint.
  - **The copy's status is set explicitly:** a frozen copy of a `status: submitted` note is stamped
    `submitted` whatever its pipeline — `create_entry` defaults NONE to `active`, and the helper
    receives the living request after its authored status has been reset (settled at PR 0 review).
    Make `create_entry` accept `submitted` on NONE for this door.
- **Drafts are never shared:** the living upsert skips `resolve_and_share`, and
  `Pipeline` loses its shares-by-default method (with `test_user_entry_service.py:208`).
- **Rejection:** `pipeline: teacher_review` on a **vault** note (gated on `file_path.is_absolute()`,
  not on uid) is rejected with guidance. Verified at PR 0: the plan's "`/upload` YAML is unchanged"
  names a door that no longer exists — relative paths come only from scripts and tests. The gate is
  harmless, but the `/upload` wording survives well beyond the `user_entry_ingestion.py:461-462`
  comment: `user_entry_ingestion.py:4,44,141` (`:141` is the rejection text vault users see for an
  audio pipeline), `audience_resolver.py:6`, `user_entry_service.py:81,122,160,212,222`,
  `unified_ingestion_service.py:1035`, and the teacher-facing empty state at `teaching_ui.py:589`
  ("upload a group YAML at /upload"). Re-derive the list by grepping for a bare `/upload`, excluding
  the live `/journals/upload` and `/api/user-entries/upload`; rewrite them to say vault ingest.
- **Provenance and dedup:**
  - A first-class `submitted_from_uid` replaces the `metadata` provenance key (submitted_from_entry).
  - The migration runs **before the first sync on the new code** (§ Standing conventions →
    Migrations), and the post-restart census of the old key must read 0 — dedup reads only
    `submitted_from_uid` (changed at PR 0 review from the plan's dual read: a fallback would be a
    second provenance authority that hides an incomplete migration).
  - Dedup = the newest copy from the same note, compared over the **whole submitted snapshot** —
    every authored field the copy carries, canonically serialized: its content, title, description,
    tags and `private` flag (`_file_submission_copy` copies the first four,
    `user_entry_ingestion.py:728-733`), the `audience:` list **and the exercise target**
    (`fulfills_exercise_uid`) (settled at PR 0 review). Today's
    `_file_submission_copy` compares content only, inside a lookup scoped by exercise uid; keyed on
    provenance instead, a note that stays `status: submitted` must file a new copy when its
    `audience:` changes (say `teachers` → `user:bob`) or its exercise changes, because drafts never
    share and a filed copy is frozen.
  - **The comparison reads a fingerprint, never the copy's live links.** The copy is stamped at filing
    with a fingerprint of what was authored (every copied field + audience list + exercise target) — a record
    of provenance, not a second audience record (ADR-088 §3: the links alone grant access). Comparing against the live
    links would read a Stop sharing (PR 6b) as an audience edit and re-file the copy, re-granting the
    recipient; against the fingerprint, a revocation stays durable while the note is unchanged.
  - The queue, the dashboard twin and `get_students_summary` supersede older pending same-note copies.
  - `cleanup_untracked_vault_entries.py` excludes `submitted_from_uid IS NOT NULL`.
- **Migration/census:**
  - provenance keys;
  - share edges on living notes, retracted with `--confirm` (live 2026-09-24: 0 — re-census: syncs
    between PR 1 and this PR may have written explicit `group:` shares);
  - retire the retract_defaulted_vault_note_shares script.
- **Closes** [`vault-resync-never-retracts-a-share.md`](vault-resync-never-retracts-a-share.md) → `done/`.
  Repoint every inbound link: `INDEX.md`, the `deferred-work.md` MOC entry's link (heading kept) and
  its banner (`deferred-work.md:12`, reworded), `sharing-http-door.md` (the script cite in its
  `unshare_from_group` row, and items 54-57 reworded — the gap closes by never sharing drafts, not by
  reconciliation), SHARING_PATTERNS:245-247, and this document's Related line.
- **Tests:** `test_user_entry_ingestion.py` (lines 120, 166, 178, 253, 352, 511-540, 630, 651, 683,
  767, 784), `test_vault_exercise_channel.py:78`, `test_review_queue_copy_collapse.py`,
  `test_move_detection.py`.
- **Docs:**
  - UNIFIED_INGESTION_GUIDE (lines 95, 113-126, 234-254, 298-359, the 386 example; its `:353` uses
    the retired colon uid), the ADR-054 YAML table, ADR-073, `JOURNALS_DOMAIN_ARCHITECTURE.md:173`,
    `how-your-content-is-used.md:14,89`, SHARING_PATTERNS:129,344.
  - Flag the two personal-vault user guides for Mike: they live outside the repo, in the personal
    vault's userguides folder (/home/mike/0bsidian/skuel/userguides/), and are not tracked here.

## Non-goals (this arc)

- Peer responses (the next arc, R14).
- Group pages, unread counts, topic subscriptions.
- Visiting someone else's wall.
- A public portfolio reader.
- Form submissions on the wall, and a form recipient read — deferred:
  [`form-submission-recipient-read.md`](form-submission-recipient-read.md).
- Widening UserEntry search.
- Re-litigating R1–R14 or the four refinements.

## Standing conventions that bind every PR here

- **Branch and checks:** a fresh branch from the updated `main` (`git pull --ff-only` first). Run
  `./dev format` + `./dev quality` (0 mypy errors) + targeted unit tests + real-Neo4j integration tests.
- **Smoke:** `scripts/authed_smoke.py` over `/gradebook`, `/profile/shared`, `/groups`,
  `/notifications`, `/submissions/submit` (from PR 7 on), `/teaching/queue`, `/exchange`. <!-- planned -->
- **UI PRs:** rebuild Tailwind, then headless Chrome at 375px and at desktop width.
- **Migrations:** census by default, `--confirm` to write, before/after counts, never widen. One
  order for every migrating PR — **stop the running app → census, then `--confirm` with Mike's OK →
  start on the new code → census again; it must read 0** (the second census catches rows the old code
  wrote in between). Why the order matters, per PR:
  - PR 1: the new queue reads `SUBMITTED_TO_GROUP` while the old code writes `SHARED_WITH_GROUP`.
  - PR 2a: the new code raises on `shared` (`dto_helpers.py:110-129`), and the post-2b writers still
    write it.
  - PR 4a: turn-ins without the snapshot fall into Other feedback.
  - PR 6b: the old code writes the student self-share unconditionally (`exercise_backends.py:1077`).
  - PR 8: the provenance migration must run before the first sync on the new code.
- **Live writes need Mike's explicit OK in that session** — every `--confirm` against AuraDB and
  every AuraDB write made to set up an acceptance case (a test exercise, a resubmission, a share, a
  second account or group). Dry-run censuses need none.
- **Docs and names:** docs change in the same PR as the code (no claims before code). Keep the
  `deferred-work.md` headings. Re-derive the stale_names anchors; a PR that deletes a name **adds**
  its `DELETED` row (none of this arc's names has one yet).
- **New events** go into the golden subscription table in the PR that adds them.
- **Review:** `scripts/request_codex_review.sh <PR#> 540` (+ `--resume`) → consideration note →
  `scripts/apply_codex_considered.sh` → merge per policy.
- **How this document is written (keep it so):**
  - A path or route that a later PR creates is backticked with ` <!-- planned -->` on the same line
    (never inside a fence); remove the marker in the PR that creates the target.
  - A name this arc deletes is written **without backticks** here and in ADR-088, so stale_names
    never needs a line anchor in a file every PR edits. Names already deleted are never backticked.
  - Docs→docs links are relative to this file. Run `./dev health` before `git add` or after the
    commit (never between — a staged, uncommitted new doc fails `docs_updated`), and
    `./dev docs-links` after `git add`.

## Running the arc: one PR per fresh context

Mike resets the context between PRs. Each session implements exactly one PR, from an updated `main`,
through merge. Nothing may depend on an earlier conversation, so each session reads everything it
needs from this document (and ADR-088).

**Kickoff prompt to paste into each fresh context:**
> Continue the Submit & Share arc. Read `docs/roadmap/submission-sharing-arc.md`: the rulings, the
> refinements, the Amendments by record table, the Standing conventions and the Rules for each PR
> session, the PR table, and the section for the first PR whose status isn't merged. Implement only
> that PR, from an updated main, on a new branch.

**Rules for each PR session:**
- **Treat citations as hints.** The file:line cites were checked on `d65f624fd` and drift after
  every PR. Re-verify by grepping symbols; never trust a line number.
- **Census before edits.** Run a site census (a subagent/workflow for the broad sweeps in PRs 1,
  2a, 6b and 8) before editing. The census is the site list, not this document's snapshot.
- **Rule new choices first.** A choice the PR's census finds that this document does not settle is
  decided before the first edit (Mike's, if it touches a ruling), recorded in the PR description
  **and** in this document — a one-line `Ruled:` in that PR's section, in its final commit — because
  a later session reads only this document.
- **Split if it won't fit.** If the PR won't fit one context, split it before coding (e.g. PR 1 →
  1a UserEntry, 1b forms) and record the split in the PR table.
- **Get Mike's OK for live writes.** Any `--confirm` against AuraDB, and any AuraDB write that sets
  up an acceptance case, needs Mike's explicit OK in that session. Dry-run censuses need no OK.
- **Finishing a PR:** its final commit sets its row below to `merged #NNNN, date` → merged per
  policy → the memory index updated (one line per PR) → stop. The next PR happens in the next fresh
  context.

## PR plan (contract)

Rows are in execution order — **PR 2b runs before PR 2a** (see PR 2b). Dependencies (verified at
PR 0 — the plan's "PR 4b and PR 3 can float after PR 1" was unbounded for PR 3): PR 4b depends on
nothing. PR 3 may move but must land before PR 6b and PR 7 (it creates `shared_with_you` /
`submission_for_review` and the `/teaching/review/{uid}` card override). PR 5 requires PR 1. PR 6b
requires PR 1, PR 3, PR 5 and PR 6a. PR 6c requires PR 4a, PR 5 and PR 6b. PR 7 requires PR 1 (the
`created` flag), PR 3, PR 6a and PR 6b. PR 8 requires PR 1, PR 6a and PR 7.

| PR | Scope | Acceptance (live case) | Status |
|----|-------|------------------------|--------|
| 0 | This document + ADR-088 + the form-recipient-read case file and MOC entry + INDEX rows (docs only; summon Codex explicitly) | This document and ADR-088 are merged; `./dev docs-links` is clean and the INDEX rows resolve | merged #1413, 2026-09-24 |
| 1 | `SUBMITTED_TO_GROUP`: writer, request side (gated on TEACHER_REVIEW; `teachers` writes no link on other pipelines), forms, teacher readers, migration | Census: 2 edges re-typed, and a count of classmate-visible turn-ins (a `MEMBER_OF` member reaching a `teacher_review` entry it does not own through `SHARED_WITH_GROUP`) reads 0. `/teaching/queue` still lists the Gentle Return turn-in. A `pipeline: none` vault note with no `audience:` writes no group link. (`/groups` as linguistic76 shows no turn-ins before PR 1 too — linguistic76 owns both.) | merged #1414, 2026-09-24 |
| 2b | The outcome discriminator; the EntryReport access check retired; report detail is an owner read | The GradeBook shows the same exchanges as before (3 live on 2026-09-24, on old and new code — the PR 0 census counted 2). `/entry-reports/detail` gives the owner 200 and others 404 | merged #1415, 2026-09-24 |
| 2a | `visibility` = {private, public}: enum, writers, Events field, spawn fix, migration first; `set_visibility` PUBLIC-only; the duplicate ingestion gate and the unused request/response classes deleted | The census shows 0 `shared`/`team` values. The Events form has no Visibility field. Spawned instances are private | merged #1416, 2026-09-24 |
| 3 | `NotificationType`; card links; admin activity reports owned by the student + their bell; subject validation; generated-report reads exclude admin (human) reports, both user-context statements included | An admin writes an activity report → the student's bell → the detail page opens. The old feedback bells open their reports | merged #1417, 2026-09-25 |
| 4a | Snapshot-keyed exchanges; "Exercise removed"; R13 subtitle | After deleting a test exercise with turn-ins, the GradeBook shows an "Exercise removed" line and `/exchange` opens | merged #1418, 2026-09-25 |
| 4b | The two lineage predicates accept `FULFILLS_EXERCISE\|FULFILLS_REVISED_EXERCISE`; the two `teachers` lookups and the exercise-use check resolve a revision (ruled in-session) | A resubmitted revision no longer shows as pending in UserContext | merged #1419, 2026-09-25 |
| 5 | `OWNER_OR_AUDIENCE` + `read_visibility`; the audience fragment; viewer-aware `/gradebook/{uid}` + download; the peer route retired | A person-shared entry opens for its recipient with no status or feedback. A non-recipient gets 404 | open |
| 6a | `AudienceSpec` + resolver; R8 co-membership; journal privacy; `group:` never files a feedback request; vault `user:` / `teacher:` parsed but applied only from PR 8 | The vault parser accepts `audience: [teachers, user:<name>]` (unit matrix). A JSON-door `user:` share to a co-member (user_admin, or a member of a non-default group) succeeds; a Default-Group-only member gets the uniform error | open |
| 6b | Share / Stop sharing routes; candidates; the two-sided Shared page; R3 cleanup; person-share bell; the two access-list methods deleted (DELETED rows added); `shares_granted` rewired | Share with a co-member (as in 6a) → the recipient's *Shared with you* + bell. Your wall lists it, and Stop sharing removes it. Feedback is gone from the Shared page | open |
| 6c | Derived "reviewed" badges; the GradeBook nudge | A revised shared entry carries "Revised after feedback". The GradeBook nudge appears on it | open |
| 7 | The two-question Submit form; teacher without an exercise; teacher bell; the zero-reach rule moves into `create_entry`; the "Submit" rename | The web Teacher option works without an exercise. The teacher's bell links to `/teaching/review/{uid}` | open |
| 8 | Vault notes are drafts; one frozen copy per `status: submitted`; provenance + dedup; closes the re-sync case file | A vault note with `status: submitted` files one copy; an idle re-sync files nothing | open |

## Verification (arc close)

A live walk-through as linguistic76, plus a second account (for example `user_uxsmoke`), set up only
with Mike's OK: the second account joins the Default Group (the classmate in step 1 and a group-share
recipient), and user_admin creates a second, non-default group containing linguistic76 and the second
account — R8 does not count co-membership through the Default Group (Refinement 3, ADR-088 §7), so
person shares need a real shared group:
1. **Submit and get feedback.** Submit an exercise with Teacher → the admin's bell (the link opens
   `/teaching/review/{uid}`) → the classmate doesn't see it on `/groups` → a teacher report → the
   student's GradeBook shows it, and the Shared page does not.
2. **Revise and share.** Revise → the nudge → share with the Default Group and, as a person, the
   second account (a co-member through the new group).
3. **What the second account sees.** The item is on *Shared with you* with "Revised after feedback".
   The bell rang once, for the person share (a group share rings no one). `/gradebook/{uid}` shows
   the recipient card: no status, no feedback, and the `.md` download works.
4. **Your wall.** It lists both audiences. Stop sharing the person → the item leaves their page, and
   they get 404.
5. **Activity report.** An admin writes one → the student's bell → the detail opens. The student's
   own report generation is not in cooldown.
6. **Exercise deletion.** Delete the exercise → the GradeBook shows an "Exercise removed" line, and
   `/exchange` opens with the snapshot title.
7. **Vault.** A note with `status: submitted` + `audience: [teachers, user:<the second account's username>]`
   files one copy. An idle re-sync files nothing and rings nothing.
