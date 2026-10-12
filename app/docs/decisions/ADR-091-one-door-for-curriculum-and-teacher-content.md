---
title: "ADR-091: One Door for Curriculum and Teacher Content"
updated: 2026-10-12
status: accepted
category: decisions
tags: [adr, decisions, curriculum, content-vault, ingestion, exercises, teacher-review, ownership, publication]
related: [ADR-018, ADR-040, ADR-053, ADR-054, ADR-070, ADR-085, ADR-086, ADR-088]
related_skills: [learning-loop, curriculum-domains]
---

# ADR-091: One Door for Curriculum and Teacher Content

**Status:** Accepted — founder-ratified 2026-10-12. **Implementation pending:** the decisions below
are built by the changes listed in [§ Implementation](#implementation), one at a time. Until the
change that removes a door has merged, that door still answers, and the records marked in
[§ Records this ADR supersedes](#records-this-adr-supersedes) still describe the live code.
**Date:** 2026-10-12
**Deciders:** MCF
**Decision Type:** ☑ Graph Schema  ☑ Pattern/Practice
**Related ADRs:**
- Supersedes in part (each record carries a note in its own header):
  [ADR-018](ADR-018-user-roles-four-tier-system.md) (the TEACHER role's in-app curriculum authoring),
  [ADR-040](ADR-040-teacher-exercise-workflow.md) (group assignment, in-app exercise authoring, the
  in-app report and revision forms),
  [ADR-053](ADR-053-groups-first-class-and-unified-sharing.md) §1 (the exercise half),
  [ADR-054](ADR-054-user-entry-unified-submissions.md) §3 (`teachers` on an exercise),
  [ADR-070](ADR-070-bidirectional-vault-bridge.md) Decision 10 (the in-app exceptions),
  [ADR-088](ADR-088-submit-and-share.md) §8 (the curriculum fallback) and §9 (the owner route).
- Related to: [ADR-085](ADR-085-ownership-read-enforcement-contract.md) and
  [ADR-086](ADR-086-universal-owns-and-attends-attendance.md) (the `:OWNS` edge whose meaning S1
  narrows).

## Related Skills

For implementation guidance, see:
- [@learning-loop](../../.claude/skills/learning-loop/SKILL.md)
- [@curriculum-domains](../../.claude/skills/curriculum-domains/SKILL.md)

---

## Context

**What is the issue we're facing?**

Curriculum enters SKUEL by two kinds of door. The content-vault sync (`POST /api/vault/sync/content`
and `./dev vault-sync`) ingests what Mike writes in the content vault. A set of in-app doors writes
the same kinds of content from the browser or the API:

- PathStep composition and the publish button (ADMIN and TEACHER);
- the six Activity Template CRUD and attach/detach doors (TEACHER);
- lateral links between curriculum items (TEACHER);
- `@ku(...)` in a journal entry, which can create a Ku (TEACHER and up);
- exercise create, edit and requirement links (TEACHER), with three app-only scopes;
- the teacher's report upload and revision form on a student's submission (TEACHER).

Measured on 2026-10-12 in a read-only session against the live graph, nothing live showed an
in-app door's work. Every curriculum node but one Ku has a content-vault tracker row, none carries
an `:OWNS` edge or an extraction edge, all 14 Exercises are `scope: curriculum`, none of the 220
edges between curriculum nodes carries the `created_by` the lateral doors stamp, and no PathStep is
`status: published`. The doors still cost something:

- **One word meant three things.** `:OWNS` was read as the author (who may submit against an
  exercise), as the controller (who may change an exercise's requirements) and as the teacher (who
  receives a feedback request on an anchored personal exercise, ADR-088 §9).
- **Publish did not publish.** The publish button writes a PathStep's `status`, while learners see
  what `publication_state` allows. A draft step stayed hidden after it was "published".
- **Two sources of truth.** A re-sync rewrites what the file declares, its properties and its own
  edges, so an in-app edit to vault content disagrees with the vault until the next sync overwrites
  it.
- **Door rules nobody needed.** Any teacher may rename or delete another teacher's templates and
  curriculum links, and an admin may change the requirements of an exercise it cannot open.
- **Two service admins.** `user_system` is recreated as an ADMIN on every boot, owns nothing, and
  can be given a password through the admin reset door. `user_vault_watcher` still has a password
  although its watcher was deleted.

**The commitment (Mike, 2026-10-12):**

> Content is made on Mike's computer and enters SKUEL through the content-vault sync. Remove the
> alternative paths: one path forward.

Only Mike writes content-vault files. Another teacher's content is sent to Mike, who syncs it. The
app reads curriculum and records what learners do with it. It authors no curriculum and no teacher
content.

---

## Decision

Each decision below is Mike's ruling of 2026-10-12. The reason behind all of them is his: one path
forward, and less confusion.

### S1. Three different words, never mixed

- **Owner** (`:OWNS`) means a user's private content. Curriculum has no owner.
- **Teacher** is who reviews work on an exercise. The exercise's vault file names its teacher.
- **Addressed to** is which student a revised exercise or a teacher report is for. The vault file
  names the student, or the submission it answers.

**Why.** Reading one edge three ways is what made an exercise's owner its reviewer and its
controller at once. Each word now has one spelling, so a reader never has to guess which one an
`:OWNS` edge meant. The vocabulary is stated where "owner" is defined:
[OWNERSHIP_VERIFICATION.md § Owner, teacher, addressed to](../patterns/OWNERSHIP_VERIFICATION.md#owner-teacher-addressed-to).

### S2. Curriculum belongs to SKUEL

Curriculum is authored only in the content vault, and that includes every exercise. No user owns
any of it. Admins control it; learners see what is published.

**Why.** The design already says so: access to curriculum is computed from its type, never from an
owner (ADR-070 Decision 7), and live no curriculum node has an owner. Writing it down removes the
exceptions instead of adding rules to guard them.

### S3. Every exercise names its teacher

An exercise's vault file names its teacher, a user with the TEACHER role or higher. A feedback
request on an exercise goes directly to that teacher. This replaces the curriculum default-group
fallback (ADR-088 §8) and the owner route (ADR-088 §9). Submitting to a group's teachers and sharing
with people or groups stay as they are.

**Why.** A learner must be able to send work directly to the exercise's teacher, and Mike ruled the
default group an inadequate substitute. Once no exercise has an owner (S2, S4), the owner can no
longer stand in for the teacher (S1), so the file says who it is. The link is
`(Exercise)-[:REVIEWED_BY]->(User)`, a `RelationshipName` member the implementing change adds; it is
never `:OWNS`, and the exercise stays ownerless. Like every frontmatter edge, it is the file's own:
changing the field retracts the old edge on the next sync.

### S4. Exercises are created and edited only in the vault

- The in-app create and edit doors go (the CRUD API in `exercises_routes.py`, `/exercises/new` and
  `/exercises/{uid}/edit`), and so do `POST /api/exercises/require-knowledge` and
  `POST /api/exercises/unrequire-knowledge`.
- The PERSONAL, ASSIGNED and ASSESSMENT scopes go.
- Group assignment (ADR-040) goes. Groups still submit to their teachers and share.

**Why.** Mike's words: there is to be no other way to create or edit an exercise, for consistency
and to avoid complexity. With no user-owned exercise left, the question of what an admin may change
on an exercise it cannot read has nothing to apply to.

### S5. A revised exercise is a content-vault file

The file names its student, the exercise it revises, the submission it answers and the teacher who
wrote it. Only that student and the teacher can see it. `RevisedExercise` stays an entity type; only its in-app creation goes
(`POST /api/teaching/review/{uid}/revision` and `POST /api/revised-exercises/create`).

**Why.** A revision is teacher content, so it takes the one door teacher content has. It is always
specific to one student, never generic, which is why the file names the student.

### S6. A teacher's written feedback is a content-vault file

The teacher's report on a submission is a content-vault file naming the submission it answers and
the teacher who wrote it. The in-app upload door (`POST /api/teaching/review/{uid}/report`) goes. The admin's feedback text on a
user's activity report (`POST /activity-review/submit-feedback`) moves to the vault the same way.

Two actions author no content and stay: the "approve" button
(`POST /api/teaching/review/{uid}/approve`, a verdict on work already reviewed) and the AI report a
learner asks for (`POST /api/exercises/report`, generated by the machine).

**Why.** Mike already writes feedback as a local `.md` file and uploads it; only the door moves.

### S7. Publish is one marker, set in the vault

Published means shared with SKUEL's users; draft means a work in progress, not shared. The vault's
`publication_state` is the one switch. The in-app publish button (`POST /api/ps/{ps_uid}/publish`
and `POST /explore/ps/{uid}/publish`) goes, and a PathStep's `status` stops meaning "published".

**Why.** Two fields for one fact disagreed, and the one the button wrote was not the one learners
are gated by. One marker decides.

### S8. All in-app curriculum authoring goes

This supersedes Mike's earlier answer the same day that shared editing among teachers was fine for
now. It covers:

- the admin PathStep doors in `path_steps_api.py`: attach to and detach from a path, relationships,
  content, tags, organize, unorganize and reorder;
- the CRUD doors of the six Activity Templates and their attach/detach (for the Task Template,
  `POST /api/pathstep-task-templates/create` and `POST /api/pathstep-task-templates/attach`; the other
  five follow the same pattern);
- lateral writes between curriculum items (`lateral_route_factory.py` for Ku, PathStep and
  LearningPath, and `POST /api/ku/{uid}/lateral/enables`). Activity-domain laterals stay: those are
  users' private content;
- `@ku(...)` Ku creation from journal entries. A reference to an existing Ku stays (ADR-069);
- form-template link and unlink to a PathStep (`POST /api/form-templates/link-path-step` and
  `POST /api/form-templates/unlink-path-step`);
- the uncalled `LpCoreService` authoring methods (`create_path`, `update_path`, `delete_path`,
  `add_step_to_path`, `remove_step_from_path`, `reorder_steps`).

Maintenance that authors nothing stays, for example chunk regeneration (`POST /api/chunks/regenerate`).

**Why.** One path forward. An in-app edit to vault content is a second source of truth that the next
sync overwrites, and the door rules it would need (whose template, whose link) guard work nobody
does in the app.

### S9. `user_system` and `user_vault_watcher` go

The boot creation (`ensure_system_user`), the `SYSTEM_USER_UID` default chain, and both live User
nodes go.

**Why.** `user_system` owns nothing and nothing points at it; the "default journal projects" it was
made for no longer exist; and any admin could turn it into a hidden admin with a password.
`user_vault_watcher`'s only consumer was deleted, and it still has a working password. A missing
owner is a configuration error at boot, not a silent fallback (fail-fast).

### The same graph shape through the new door

Each vault door writes the graph shape the in-app door writes today: the same labels, edges and
owner. Only the door changes. A revised exercise, for example, keeps its teacher's `:OWNS` edge and
its `student_uid`: it is the teacher's private content addressed to one student (S1). A change that
finds it must alter the shape stops and asks.

The same holds for what the in-app write does besides the graph shape. A teacher's report moves the
submission to `COMPLETED` and publishes `ReportSubmitted`; a revision moves it to
`REVISION_REQUESTED` and publishes `UserEntryRevisionRequested` and `RevisedExerciseCreated`; an
admin's activity-report feedback publishes `ActivityReportWritten`. Those events notify the student
and refresh what is derived from the submission. The vault door makes the same status transitions,
through ADR-087's guarded write, and publishes the same events once per file, as the in-app write
publishes them once per request, never again on an unchanged re-sync.

The file's named teacher is the author the shape needs (the revision's owner, the report's author,
the events' actor): neither the sync's operator, who is Mike, nor the exercise's own teacher can
stand in, since a group's owning teachers may also review. The sync admits the named teacher by the
same rule the in-app review write admits by today: the submission asks that teacher for feedback.

### What stays

- Everything a learner does with curriculum: enrolment, progress, bookmarks, mastery check-ins,
  submissions, and the shares and feedback requests of ADR-088.
- Groups: a group's owning teachers still receive what is submitted to the group.
- The approve button and the learner-summoned AI report (S6).
- Maintenance that authors nothing (S8).

---

## Not ruled by this ADR

The census behind this ADR found these doors and readers, which the rulings do not name. Nothing
here decides them, but none may be left unsettled by the change it borders: a writer left in place
after that change would write state the vault does not hold, which the next sync can overwrite or
recreate. Each is put to Mike before that change merges.

- **The offline review scripts.** `scripts/import_reports.py` posts reports, revisions and approvals
  through `TeacherReviewService` (ADR-040's CLI workflow); `scripts/export_submissions.py` only reads
  the review queue. Borders S5 and S6.
- **The revised-exercise update and delete doors** (`POST /api/revised-exercises/update` and
  `POST /api/revised-exercises/delete`, TEACHER). S5 retires in-app creation. Borders S5.
- **Prerequisite-suggestion approval** (`POST /admin/prereq-suggestions/approve`) writes an Edge YAML
  file into the content vault from the app. The edge enters through the sync, but the app writes the
  file. Borders S8.
- **PathStep and LearningPath shared with a group** (`SHARED_WITH_GROUP`, ADR-053 §1). User context
  still reads it, and no door writes it. S4 retires the exercise half only.
- **What deleting or editing a synced review file does.** A content-vault file's deletion deletes
  its node, and a re-sync rewrites it. A report or revision file has also moved its submission's
  status and rung the student's bell, which a deletion cannot take back. Whether these files are
  fixed once synced, or a deletion or a changed `answers` is refused or compensated, is for the
  change that builds each door to put to Mike. Borders S5 and S6.
- **Default-group enrolment on PathStep progress** (`handle_path_step_enrolled`). The reasons
  ADR-040 and ADR-088 §8 record for it, access to ASSIGNED exercises and the curriculum fallback,
  retire under S4 and S3. Borders S3.

---

## Alternatives Considered

### Alternative 1: An `:OWNS` edge from a SKUEL account on all curriculum
**Description:** Make "SKUEL owns the curriculum" an edge.
**Cons:** The ingestion owner gate would refuse every re-sync of an owned node, the link guard would
refuse every learner's link to curriculum, far-node reads would drop curriculum, and deleting the
account would erase it. Nothing live needed an owner to find.
**Why rejected:** S2 states the rule the code already keeps; an edge would contradict it.

### Alternative 2: Keep the in-app doors and add per-door rules
**Description:** Record who authored each template, link and exercise, and let only that teacher or
an admin change it.
**Cons:** Four new door rules, an authorship property to write and read, and a decision about vault
content at each one, for doors that had authored nothing live.
**Why rejected:** The commitment removes the doors, so there is nothing left to guard.

### Alternative 3: Let publishing also lift the draft marker
**Description:** Keep both `status` and `publication_state`, and have the publish button write both.
**Why rejected:** Two fields for one fact stay redundant (S7), and the button stays an in-app
authoring door (S8).

### Alternative 4: Keep the default-group fallback for exercise feedback
**Description:** A feedback request on a curriculum exercise keeps going to the learner's default
group, owned by the oldest admin account that is not a service account.
**Why rejected:** Mike ruled that a learner must reach the exercise's own teacher (S3).

---

## Consequences

### Positive Consequences
- ✅ One door for curriculum and teacher content, so the app can no longer make the graph disagree
  with the vault.
- ✅ `:OWNS` no longer stands for an exercise's teacher or controller. A reader looking for an
  exercise's teacher reads the teacher edge.
- ✅ The publish button can no longer report success while learners still see nothing.
- ✅ The door rules the in-app doors would need (whose template, whose link, who may publish) are
  never written.
- ✅ No hidden service admin remains to be activated.

### Negative Consequences
- ⚠️ A teacher other than Mike changes no curriculum or teacher content in SKUEL without him: it
  is sent to Mike, who syncs it.
- ⚠️ A fix to a typo, or a new revision for a student, waits for the next content-vault sync.
- ⚠️ Every exercise file must name its teacher; the sync refuses one that does not, so the 14 live
  exercise files gain the field in the same change.
- ⚠️ ADR-070 Decision 7 attributes a user-owned node in a content-vault file to the vault's acts-as
  account (`SKUEL_CONTENT_VAULT_OWNER`). The in-app doors write other owners: a revised exercise is
  owned by its teacher, and a teacher's report by the student whose work it answers, with the
  teacher as its author. Keeping those shapes (§ The same graph shape), the revision and report
  doors take their owner from the users their file names and the sync validates, not from the
  vault. The change that builds each door states the exception in Decision 7.
- ⚠️ Boot and the ingestion defaults no longer fall back to `user_system`; a test or CI run names
  its owner.

### Neutral Consequences
- ℹ️ `RevisedExercise` stays tier C (user-created) and teacher-owned; only its door changes.
- ℹ️ Groups, sharing and ADR-088's two verbs are unchanged.

---

## Implementation

Each change below lands on its own. A door named in S1–S9 keeps answering until its change merges;
the records listed in § Records this ADR supersedes say so in their own words.

| # | Change | Decisions |
|---|--------|-----------|
| 0 | This ADR and the supersession notes | S1–S9 |
| 1 | Remove the two system accounts and the `SYSTEM_USER_UID` default chain | S9 |
| 2 | Delete the publish doors; `publication_state` is the one marker | S7 |
| 3 | The exercise file names its teacher; a feedback request on an exercise goes to that teacher | S1, S3 |
| 4 | Delete the in-app exercise doors, the three app-only scopes and group assignment | S4 |
| 5 | A content-vault door for revised exercises; delete the in-app creation doors | S5 |
| 6 | A content-vault door for teacher reports and activity-report feedback; delete the upload doors | S6 |
| 7 | Delete the remaining in-app curriculum writes | S8 |
| 8 | CLAUDE.md, the skills and the docs describe the result | all |

Each change's own census (every writer and reader of what it removes, and the live graph read-only
before any narrowing) decides its file-level scope.

**Order between changes 3 and 4.** Until change 4 merges, a teacher can still create an owned
exercise that has no vault file and so names no teacher. Change 3 must not leave such an exercise
with no feedback target: either it keeps the owner route for owned exercises until change 4 removes
them, or the two land together. (Live on 2026-10-12 there were no owned exercises.)

---

## Records this ADR supersedes

Each record below carries a note, added with this ADR, at its head or beside the part superseded.
Every note says the old behaviour stays live until the change that replaces it merges.

| Record | What it decides today | What ADR-091 changes | Live until change |
|---|---|---|---|
| ADR-018 — Four-Tier User Role System | TEACHER: "create/edit KU, LP, MOC" | A teacher reviews work; curriculum is authored in the content vault (S2, S8) | 2, 4, 7 |
| ADR-040 — Teacher Exercise Workflow | A teacher creates PERSONAL and ASSIGNED exercises and assigns them to a group; feedback is a `.md` upload and a revision is a form, both in the app | Exercises are vault files and group assignment goes (S4); revisions and reports are vault files (S5, S6) | 4, 5, 6 |
| ADR-053 §1 — Unify on `SHARED_WITH_GROUP` | `ExerciseService` shares an ASSIGNED exercise with its group | No exercise is assigned to a group (S4); PathStep and LearningPath are not ruled | 4 |
| ADR-054 §3 — the YAML `audience:` table | `teachers` on a curriculum exercise files a request to my default group | `teachers` on an exercise files a request to the exercise's named teacher (S3) | 3 |
| ADR-070 Decision 10 — the content vault is the sole author | In-app exceptions: PERSONAL, ASSIGNED and ASSESSMENT exercises | No exception: the content vault is the sole author of curriculum and teacher content (S2, S4–S6) | 4, 5, 6 |
| ADR-088 §8, §9 and the audience table | The curriculum default-group fallback; `SUBMITTED_TO_TEACHER` to the owner of an anchored PERSONAL exercise | A feedback request on an exercise goes to its named teacher (S3); the revised exercise and the teacher's report are vault files (S5, S6) | 3, 5, 6 |
| [LEARNING_LOOP_ARCHITECTURE.md](../architecture/LEARNING_LOOP_ARCHITECTURE.md), its opening and phases 3–4 | A teacher creates and assigns exercises, writes a report and creates a revision in the app | All three are content-vault files (S4, S5, S6) | 4, 5, 6 |

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2026-10-12 | MCF | Accepted: the commitment and rulings S1–S9; supersession notes added to the records above, each live until its implementing change | 1.0 |
