---
title: "ADR-091: One Door for Curriculum"
updated: 2026-10-13
status: accepted
category: decisions
tags: [adr, decisions, curriculum, content-vault, ingestion, exercises, teacher-review, ownership, publication]
related: [ADR-018, ADR-040, ADR-053, ADR-054, ADR-070, ADR-085, ADR-086, ADR-088]
related_skills: [learning-loop, curriculum-domains]
---

# ADR-091: One Door for Curriculum

**Status:** Accepted — founder-ratified 2026-10-12. **Implementation pending:** the decisions below
are built by the changes listed in [§ Implementation](#implementation), one at a time. Until the
change that removes a door has merged, that door still answers, and the records marked in
[§ Records this ADR supersedes](#records-this-adr-supersedes) still describe the live code.
**Date:** 2026-10-12
**Deciders:** MCF
**Decision Type:** ☑ Graph Schema  ☑ Pattern/Practice
**Related ADRs:**
- Supersedes in part (each record carries a note at its head or beside the part superseded):
  [ADR-018](ADR-018-user-roles-four-tier-system.md) (the TEACHER role's in-app curriculum authoring),
  [ADR-040](ADR-040-teacher-exercise-workflow.md) (group assignment, in-app exercise authoring, the
  offline import script, revision requests on work with no exercise),
  [ADR-053](ADR-053-groups-first-class-and-unified-sharing.md) §1 and §3 (curriculum shared with a
  group, and its user-context reader),
  [ADR-054](ADR-054-user-entry-unified-submissions.md) §3 (`teachers` on an exercise),
  [ADR-070](ADR-070-bidirectional-vault-bridge.md) Decision 10 (the in-app exception and the
  prerequisite-approval vault write),
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
- exercise create, edit and requirement links (TEACHER), with three app-only scopes.

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
app reads curriculum and records what learners do with it. It authors no curriculum.

**The split (Mike, 2026-10-12, round 2).** Curriculum is a standing document, so it goes through
the vault. A teacher's reply (a report, a revision request, feedback on an activity report) is a
message about one submission at one moment, so it is sent from the review page where the teacher
reads the work. Mike writes the reply on his computer; only its delivery is in the app.

---

## Decision

Each decision below is Mike's ruling of 2026-10-12: S1–S9 first, then N1–N9 on the doors the census
found beside them. S5 and S6 were withdrawn the same day. The reason behind all of them is his: one
path forward, and less confusion.

### S1. Three different words, never mixed

- **Owner** (`:OWNS`) means a user's private content. Curriculum has no owner.
- **Teacher** is who reviews work on an exercise. The exercise's vault file names its teacher.
- **Addressed to** is which student a revised exercise or a teacher report is for: the student whose
  submission it answers.

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

### S5 and S6 (withdrawn): a teacher's reply stays on the review page

Mike first ruled that a revised exercise (S5) and a teacher's written report (S6) would be
content-vault files too. He withdrew both the same day. A reply (a report, a revision request, or
feedback on an activity report) belongs to the submission the teacher is looking at; it is a message
about one piece of work at one moment, not a standing document, and routing it through the vault
made the workflow worse. So a reply is sent from the review page where the teacher reads the work:
Mike writes it on his computer, and only its delivery is in the app. The report upload
(`POST /api/teaching/review/{uid}/report`), the revision form
(`POST /api/teaching/review/{uid}/revision`), the approve action and the admin's feedback on an
activity report (`POST /activity-review/submit-feedback`) stay in the app.

**The split.** Curriculum is a standing document, so it goes through the content vault (S2, S4, S7,
S8). A teacher's reply is a message, so it goes through the review page (N6, N7, N8).

### S7. Publish is one marker, set in the vault

Published means shared with SKUEL's users; draft means a work in progress, not shared. The vault's
`publication_state` is the one switch. The in-app publish button (`POST /api/ps/{ps_uid}/publish` <!-- historical -->
and `POST /explore/ps/{uid}/publish` <!-- historical -->) goes, and a PathStep's `status` stops meaning "published".

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

### N1–N9. The doors the first rulings did not name

The census behind this ADR found doors and readers that S1–S9 did not name. Mike ruled on each the
same day (round 2):

- **N1. `scripts/import_reports.py` goes.** It posted reports, revisions and approvals through
  `TeacherReviewService` from local files, a second door beside the review page.
  (`scripts/export_submissions.py` only reads the review queue.)
- **N2. The revised-exercise update and delete doors go** (`POST /api/revised-exercises/update` and
  `POST /api/revised-exercises/delete`). A revision is sent from the review page; nothing edits it
  afterwards.
- **N3. Prerequisite-suggestion approval goes** (`POST /admin/prereq-suggestions/approve`, which
  writes an Edge YAML file into the content vault from the app). It is in-app curriculum authoring
  (S8); Mike writes the edge file himself.
- **N4. The user-context reader of group-shared curriculum goes:** the three `group_assigned_*`
  fields (exercises, PathSteps, LearningPaths) and the query arms that fill them. With group
  assignment gone (S4) nothing writes such a share; live there were none, and no consumer reads the
  fields.
- **N5. FormTemplate create, update and delete stay in the app.** A FormTemplate is curated content
  (tier A), not curriculum. Only its link and unlink to a PathStep go (S8).
- **N6. The split** (above): S5 and S6 are withdrawn, and the admin's feedback on an activity report
  stays in the app too.
- **N7. Every revision request names an exercise.** The path that requests a revision on work with no
  exercise goes; work with no exercise gets a report only.
- **N8. A revision's teacher is the original exercise's named teacher** (S3), and work submitted
  against a revision goes to that teacher. Kept simple on purpose.
- **N9. Default-group enrolment on PathStep progress is unchanged** (`handle_path_step_enrolled`).
  The reasons ADR-040 and ADR-088 §8 record for it (access to ASSIGNED exercises, the curriculum
  fallback) retire under S4 and S3; its remaining reason is feedback on work with no exercise and
  sharing with the group. Revisit when a second teacher or open sign-up arrives.

Not adopted: sending a report and a revision as one `.md` upload. The revision form records
categorised feedback points that a file would lose.

### What stays

- Everything a learner does with curriculum: enrolment, progress, bookmarks, mastery check-ins,
  submissions, and the shares and feedback requests of ADR-088.
- Groups: a group's owning teachers still receive what is submitted to the group.
- A teacher's replies on the review page: the report upload, the revision form (on work with an
  exercise, N7) and the approve action; and the admin's feedback on an activity report (N6).
- The AI report a learner asks for (`POST /api/exercises/report`).
- FormTemplate CRUD (N5) and maintenance that authors nothing (S8).

---

## Not ruled by this ADR

Nothing the census found is left: N1–N9 rule on every door and reader it listed beside S1–S9.

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
- ✅ One door for curriculum, so the app can no longer make the graph disagree with the vault.
- ✅ `:OWNS` no longer stands for an exercise's teacher or controller. A reader looking for an
  exercise's teacher reads the teacher edge.
- ✅ The publish button can no longer report success while learners still see nothing.
- ✅ The door rules the in-app doors would need (whose template, whose link, who may publish) are
  never written.
- ✅ A teacher's reply has one door, the review page: no import script and no edit after sending.
- ✅ No hidden service admin remains to be activated.

### Negative Consequences
- ⚠️ A teacher other than Mike changes no curriculum in SKUEL without him: it is sent to Mike, who
  syncs it.
- ⚠️ A fix to a typo in curriculum waits for the next content-vault sync.
- ⚠️ Every exercise file must name its teacher; the sync refuses one that does not, so the 14 live
  exercise files gain the field in the same change.
- ⚠️ A sent revision cannot be edited or deleted (N2), and work with no exercise can get a report but
  no revision request (N7).
- ⚠️ Boot and the ingestion defaults no longer fall back to `user_system`; a test or CI run names
  its owner.

### Neutral Consequences
- ℹ️ `RevisedExercise` stays tier C (user-created) and teacher-owned, sent from the review page.
- ℹ️ Groups, sharing and ADR-088's two verbs are unchanged.

---

## Implementation

Each change below lands on its own. A door named in S1–S9 or N1–N9 keeps answering until its change
merges; the records listed in § Records this ADR supersedes say so in their own words.

| # | Change | Decisions |
|---|--------|-----------|
| 0 | This ADR and the supersession notes | all |
| 1 | Remove the two system accounts and the `SYSTEM_USER_UID` default chain | S9 |
| 2 | Delete the publish doors; `publication_state` is the one marker | S7 |
| 3 | The exercise file names its teacher; a feedback request on an exercise goes to that teacher | S1, S3 |
| 4 | Delete the in-app exercise doors, the three app-only scopes, group assignment and its user-context reader | S4, N4, N9 |
| 5 | The revision door: exercise-only, the named teacher; retire the extra review writers | N1, N2, N7, N8 |
| 6 | *Withdrawn* (was: teacher reports through the vault) | N6 |
| 7 | Delete the remaining in-app curriculum writes, prerequisite approval included | S8, N3 |
| 8 | CLAUDE.md, the skills and the docs describe the result | all |

Each change's own census (every writer and reader of what it removes, and the live graph read-only
before any narrowing) decides its file-level scope. Change 4 also restates the default-group
enrolment's docstring to the reason it keeps (N9).

**Order between changes 3 and 4.** Until change 4 merges, a teacher can still create an owned
exercise that has no vault file and so names no teacher. Change 3 must not leave such an exercise
with no feedback target: either it keeps the owner route for owned exercises until change 4 removes
them, or the two land together. (Live on 2026-10-12 there were no owned exercises.) Change 3
took the first: it routes a request on an exercise to its `REVIEWED_BY` teacher and retires the
default-group fallback, and keeps the owner route for owned exercises until change 4 removes them.

---

## Records this ADR supersedes

Each record below carries a note, added with this ADR, at its head or beside the part superseded.
Every note says the old behaviour stays live until the change that replaces it merges.

| Record | What it decides today | What ADR-091 changes | Live until change |
|---|---|---|---|
| ADR-018 — Four-Tier User Role System | TEACHER: "create/edit KU, LP, MOC" | A teacher reviews work; curriculum is authored in the content vault (S2, S8) | 2, 4, 7 |
| ADR-040 — Teacher Exercise Workflow | A teacher creates PERSONAL and ASSIGNED exercises and assigns them to a group; reviews can be imported from local files; a revision can be requested on work with no exercise | Exercises are vault files and group assignment goes (S4); the import script goes (N1); every revision request names an exercise (N7). The review page and its replies stay | 4, 5 |
| ADR-053 §1, §3 — Unify on `SHARED_WITH_GROUP`; Group in `UserContext` | `ExerciseService` shares an ASSIGNED exercise with its group; user context reads curriculum shared with the user's groups (`group_assigned_*`) | No exercise is assigned to a group (S4), and the reader goes (N4) | 4 |
| ADR-054 §3 — the YAML `audience:` table | `teachers` on a curriculum exercise files a request to my default group | `teachers` on an exercise files a request to the exercise's named teacher (S3) | 3 |
| ADR-070 Decision 10 — the content vault is the sole author | In-app exception: PERSONAL, ASSIGNED and ASSESSMENT exercises; prerequisite approval writes an Edge YAML into the vault | No exception (S2, S4); the approval door goes (N3) | 4, 7 |
| ADR-088 §8, §9 and the audience table | The curriculum default-group fallback; `SUBMITTED_TO_TEACHER` to the owner of an anchored PERSONAL exercise | A feedback request on an exercise, or on a revision of it, goes to the exercise's named teacher (S3, N8) | 3, 5 |
| [LEARNING_LOOP_ARCHITECTURE.md](../architecture/LEARNING_LOOP_ARCHITECTURE.md), its opening and phases 1 and 4 | A teacher creates and assigns exercises in the app; a revision may be requested without an exercise and edited after it is sent | Exercises are vault files naming their teacher (S3, S4); a revision names an exercise, goes to its teacher, and is not edited after sending (N2, N7, N8) | 3, 4, 5 |

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2026-10-12 | MCF | Accepted: the commitment and rulings S1–S9, then the split (S5 and S6 withdrawn) and N1–N9; supersession notes added to the records above, each live until its implementing change | 1.0 |
