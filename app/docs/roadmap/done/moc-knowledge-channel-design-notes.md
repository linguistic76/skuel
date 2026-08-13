# MOC + knowledge channel — design rulings and direction (Mike, 2026-07-04)

Captured from the vault-structure design conversation after Arc E merged (#503).
These are RULINGS and DIRECTION, not an implementation plan. Two future arcs sketched
at the bottom. Seed fixture: `0bsidian/skuel/knowledge/nous topics.md` (uid
`moc:worldview`) — deliberately LEFT FAILING on every personal sync until the MOC
ingestion arc lands; the day it syncs clean is that arc's acceptance test.

## The vault map (ruled)

- **Content vault `0vault/`** — SKUEL's official curriculum. Polished, admin-owned,
  shared. The END of the pipeline.
- **FOUNDER vault `0bsidian/skuel/`** — Mike's workshop. RAW: the beginnings of what
  may appear in 0vault. SKUEL's relationship here is intimate and cooperative —
  listening, being guided, co-building the enterprise. Private, secure; never leaked
  into the app at large.
- **Regular user's personal vault** — the Journals surface: periodic notes,
  activity round-trip, reporting/reinforcement across the 6 Activity Domains.

**The FOUNDER/regular line is a RELATIONSHIP line, not a capability line.** The
machinery (knowledge/ folder, MOC ingestion, sync doorways) is SHARED. What differs:
1. The journals pipeline instruction set — already in code as `JournalTier.FOUNDER`
   (three-stage DNWF) vs `STANDARD`. This is THE gating hook (ruled: no new role).
2. What SKUEL does with what it learns — founder: how to build/operate SKUEL
   (listen, fluid, cooperative); regular user: enough understanding to be a better
   accountability partner (guide, lead, inspire, pull along the path).

## Regular-user knowledge channel (ruled)

- Regular users DO get a knowledge/ folder — "a space for a User to develop their
  own knowledge." Purpose test for anything built there: it must serve Activity
  Domain reinforcement or Askesis's PS-progression mission. Not general-purpose PKM.
- **Initial intimacy line (ruled yes):** regular-user knowledge feeds CONTEXT ONLY
  (the summaries Askesis/journals read) — no entity extraction, no recommendations
  generated from it, nothing surfaced back. Matches the PLANNED "global vs per-user
  two-layer split" from the journals arc: founder knowledge may inform how SKUEL
  behaves; user knowledge only informs how SKUEL sees THAT user.

## MOC (ruled)

- **First-class, standard, available to FOUNDER and regular users alike.** Honors how
  Mike (and users) naturally write in Obsidian. MOC's value = usable + malleable
  grouping.
- Architecture convergence: SKUEL already defines MOC as EMERGENT (any entity with
  ORGANIZES edges) and names the "ORGANIZES Path" (learner-directed) as the second
  Path to Knowledge. MOC ingestion = finally giving the ORGANIZES Path its authoring
  surface. NO new EntityType.
- Design shape: frontmatter marks a file as a MOC; it ingests as a user-owned entity;
  its links/listed items become ORGANIZES edges. Editing the file re-draws the edges
  on next sync (deletion propagation already handles removals).
- **Dangling MOC links are PLANS, not errors** in a personal/raw vault (a MOC names
  the shape of territory before the content exists — a mix of real wiki-links and
  head-only topics is legitimate, ruled). The content vault keeps strict
  dangling-target warnings (Arc E). Two postures, one mechanism.
- Regular-user MOCs: generic (any MOC is usable), but SKUEL's PRIMARY focus is the
  six **Activity Domain MOCs** (Tasks/Events/Habits/Goals/Principles/Choices MOC).
  Getting users to THINK in MOCs is itself the accomplishment.
- Founder MOC graduation to 0vault: **always a deliberate manual act by Mike** (ruled).

## Askesis ↔ Journals (direction)

- Askesis: pulls the user along a path — primary mission = progress through and
  complete a PS, then the next PS. Vault understanding is supporting context.
- Journals: lets the user guide the path — the user's space.
- Regular-user combination: a space for the user + a pull in SKUEL's direction
  (which is the direction the user wants to go).
- Founder mode: the journal process is also the instrument for building the
  enterprise. Developing topic; nuance does not need completing up front.
- "Knowledge is meant to be applied" = the fundamental principle. The regular user's
  problem is rarely not-knowing, it's not-acting; SKUEL = accountability partner.
- Recurring daily-note reflection lines ("Reflect on what went well today"):
  ruled — model as HABITS, not tasks (future arc; today they're one merged task).

## The mapping exercise (Mike's idea, 2026-07-04 — the payoff)

"Translate the PS into your own knowledge map" as a standard Exercise modality:
- The Exercise instructs: map this PathStep's territory in your own terms. The user
  writes a MOC file in their vault (natural Obsidian writing); sync ingests it;
  `fulfills_exercise_uid` frontmatter (ALREADY EXISTS in user-entry ingestion) ties
  it to the exercise; the learning loop (EntryReport feedback) runs unmodified.
- Pedagogy: generation effect — reorganizing material in your own structure is the
  deepest application. Converts the PS Path into the ORGANIZES Path: consume
  structured → produce personal structure.
- Assessable: the PS knows its USES_KU composition; feedback can be structural
  ("you clustered X with Y — not in the step, good connection; you omitted Z, which
  the step treats as central"). V1 = plain LLM feedback; structural comparison later.
- **Activity Domain MOCs can be ASSIGNED as exercises** ("Create your Goals MOC") —
  SKUEL's native instrument for getting a user to DO something teaches the MOC
  thinking style by doing, and yields the user's self-articulated map that Activity
  Domain reinforcement needs.

## Sequencing (agreed direction)

1. **Arc F — hygiene** (unchanged; prompt: `plans/arc-f-hygiene-prompt.md`).
2. **MOC ingestion arc** — the shared door: frontmatter recognition, user-owned MOC
   entity + ORGANIZES edges, dangling-as-plans posture for personal vaults,
   `nous topics.md` turns green as acceptance.
3. **Mapping-exercise arc** — the modality + the Activity Domain MOC exercise
   sequence.

---

## Implementation log — PR 1 (#506, MERGED 2026-07-04)

`feat/moc-ingestion-field` squash-merged to main (23604418). What landed:

- **`core/services/ingestion/moc_links.py`** — `extract_moc_link_suffixes(body)`:
  wiki + markdown links → ordered/deduped path suffixes (`/note.md`), verified
  against the real fixture (all 29 unique targets incl. `%20`, `(s)` parens,
  subpaths, dots-in-filenames). `frontmatter_organizes_targets(entity_data)` —
  protection helper (see Kody note below).
- **Preparer**: `moc: true` → transient `_moc_links` on entity_data (popped by
  both doors pre-persist; the `moc` field itself flows inert onto the node).
- **Backend** (`IngestionWriteBackend`): `resolve_path_suffixes` (ENDS WITH over
  IngestionMetadata, vault-root scoped, `edge:` rows excluded) +
  `refresh_moc_organizes(source, targets, protected)` (delete-stale + MERGE with
  `order`, sparing the file's own `organizes:` frontmatter targets).
- **Service**: `_apply_moc_links` — posture by `VaultRegistry.resolve_by_path(...).kind`
  (PERSONAL silent / CONTENT Arc E-style warnings); ambiguous basenames pick
  shortest-path-then-lex; self-links dropped. Inline for single-file door;
  batch defers to END of sync (`moc_pass_fn`, after metadata stamping + deletion
  reconciliation) so same-sync targets resolve; edge-pass failure drops the
  tracker row so the next sync retries.
- **The fixture's ACTUAL failure**: `batch.parse_file_sync` prefix-validated
  USER_ENTRY uids (the single-file door never did — its branch returns before
  `validate_uid_format`). Fixed: batch exempts USER_ENTRY (ADR-013 never-sniff);
  `build_user_entry_request` normalizes authored uids colon→dot
  (`moc:worldview` → `moc.worldview`) — derived periodic `ue:daily:` uids stay
  colon-form (live calendar join contract; verified only the fixture authors an
  explicit uid in the whole vault). `moc: true` rides into `metadata.moc` on the
  user-entry door.
- **Side fix (latent, pre-existing)**: `organizes` was missing from PathStep
  `uid_normalization_fields` — colon-authored `organizes:` targets never matched
  dot-stored uids.
- **Review**: Codex quota-blocked (4th day) → Kody substitute. Finding 1 accepted
  (protected-targets fix, integration-tested); findings 2 (ENDS WITH perf — exact
  match would break wiki basename resolution) and 3 (inline pass on untracked
  doors — stamping there would enroll ad-hoc files into deletion reconciliation)
  rejected with rationale in the PR consideration note.
- **Tests**: 35 unit + 3 integration (testcontainer; full lifecycle incl.
  same-sync forward refs, unchanged no-op, edit re-draw, deletion propagation,
  frontmatter-coexistence, content posture warnings). Docs:
  UNIFIED_INGESTION_GUIDE § MOC files; CLAUDE.md pointer; grouping-patterns
  dated update.
- **PR 2 watch item confirmed by code reading**: `status: in process` on a
  user_entry file is IGNORED by the door (no `status` in the request model);
  the service stamps ACTIVE. Nothing munges the file. Report to Mike in PR 2.

## Implementation log — PR 2 (live acceptance, 2026-07-04)

Fresh-context live acceptance on :8001 as linguistic76 (real `/login/submit`, real
"Sync from Obsidian" POST). **Zero code changes needed** — this PR is the log + memory
close-out. The seed fixture's deliberate failure is over.

- **Fixture green.** `nous topics.md` ingested clean on the real personal sync.
  MOC edge pass: **3 resolved, 26 unresolved of 29 links** (logged by the pass).
  The 3 resolved are exactly the already-ingested knowledge notes
  (`moc - resources.md` → ue_840cf583 order 0, `moc 8.md` → ue_b45b3660 order 1,
  `Research.md` → ue_1446d625 order 2); the 26 unresolved point at never-ingested
  workshop notes and drew nothing, silently — the personal-vault posture working.
- **Graph verified via read-only MCP.** `moc.worldview` exists (labels
  Entity+UserEntry, entity_type user_entry), owned by user_linguistic76 via :OWNS,
  `metadata.moc: true` present and inert (top-level `moc` property null; nothing
  queries either). ORGANIZES edges carry `order` 0/1/2 by document position.
- **Live edit round-trip.** Appended `[SKUEL Guide](SKUEL%20Guide.md)` → sync →
  4th edge (ue_5530185c, order 3). Restored the file byte-identical (md5-checked
  against pre-edit backup) → sync → back to exactly 3 edges. Unchanged re-sync
  between = true no-op (0 ingested, MOC pass did not re-run).
- **Honesty check (item 8), for Mike to rule on:** `status: in process` in the
  fixture frontmatter is silently DROPPED by the user-entry door —
  `build_user_entry_request` carries title/content/tags/metadata/uid/pipeline/
  audience/fulfills/transforms only; the service stamps `active`. The file is never
  touched (mtime + bytes verified). Same silent drop applies to `description:`,
  `domain:`, and `visibility:` in that file. Options: (a) one-line file edit
  (`status: active` or delete the line) for file↔graph honesty today; (b) door
  change to accept/normalize authored status — a design decision (status drives
  learning-loop + search semantics), not a seam; deferred to Mike.
- **Rendering walk (item 7) — the user_entry MOC's map is visible NOWHERE today.**
  Findings logged, nothing redesigned (new surfaces are ruled out of this arc):
  - `/journals/{entry_uid}` — periodic notes only, deliberate (ADR-073); 404 for
    knowledge entries.
  - `/submissions/history` — exercise submissions only; knowledge-pipeline entries
    not listed.
  - Lateral/relationship graph views (RelationshipGraphView) — 9 domains;
    user_entry is not one of them.
  - `/api/explore/graph` — curriculum-scoped (ku/ps); no user entries.
  - MOCs authored on Ku/PS entities WOULD render through the existing ORGANIZES
    surfaces (PS organization routes, library hub cards) — the gap is specific to
    user_entry MOCs. Natural home for the fix: the mapping-exercise arc, which
    needs a MOC-rendering surface anyway.
- **Pre-existing gap found on the walk (not MOC-specific):** SearchRouter's
  registry maps `EntityType.USER_ENTRY → "user_entry_search"`, but the Services
  container has no such attribute — user entries are silently unsearchable
  (`Service 'user_entry_search' not initialized` debug log) despite
  SEARCH_ARCHITECTURE's 13-searchable-domains claim. Filed here as a finding.
- **Acceptance items 4–5:** content-vault posture + re-draw semantics were
  integration-tested in PR 1 (testcontainer); no code changed in PR 2 so quality
  gates are unaffected.

**Arc status: MOC ingestion arc CLOSED. Next: mapping-exercise arc.**

## Implementation log — follow-up #507 (door honesty, MERGED 2026-07-04)

Mike's ruling on PR 2 finding 1: door change, not file edit. Plus his ask: an
`ownership:` field for personal-vault files. `feat/user-entry-door-status-ownership`
squash-merged (d350ecc6, in-session Merge sign-off):

- **`status:`** parsed via alias-aware `EntityStatus.from_string`; new
  `in_process` → ACTIVE alias (the fixture's authored spelling). Unrecognized →
  loud failure listing accepted values. Authored status wins over the pipeline
  default. **TEACHER_REVIEW exception (Kody critical finding, accepted):** status
  is service-owned there — only a truthful `submitted` accepted, at the service
  chokepoint (covers JSON API + YAML door + /submit form); tighter than Kody's
  {SUBMITTED, ACTIVE} suggestion (authored `active` adds nothing truthful).
- **`description:`** flows; falsy-but-authored values preserved (Kody medium
  finding, accepted: `None if raw is None else str(raw)`).
- **`ownership:`** (alias `user_uid:`) — consistency check, never a transfer:
  normalized (`linguistic76` → `user_linguistic76`), must match the syncing user,
  mismatch fails naming both identities. Ownership still stamps from session.
- `domain:`/`visibility:` remain door-ignored (audience machinery owns visibility).
- Review: Codex quota-blocked (5th day) → Kody substitute, 2 findings both
  accepted+fixed, consideration note + codex-considered.
- Live-verified on :8001 as linguistic76: fixture re-synced through the new door —
  node `status: active` (alias), description populated, `user_uid:` declaration
  validated, 3 ORGANIZES edges intact, file restored byte-identical. **The fixture
  needs NO edit — Mike's frontmatter is now honored as written.**

---

## Phase 0 rulings — VAULT EXERCISE CHANNEL arc (Mike dialog, 2026-07-04)

**This section supersedes the framing of "§ The mapping exercise" above.** That section
stands as dated history of the idea's origin; the design conversation that followed
(research-first Phase 0, three correction rounds) reshaped the arc. Execution prompt:
`plans/vault-exercise-channel-arc-prompt.md` (renamed from
`mapping-exercise-arc-prompt.md` — names reflect function).

### R1 — Decoupling (ruled TWICE; the arc's central correction)

**MOC machinery and Exercise machinery never reference each other. No code path may
know a submission "is" a MOC.** Mike corrected the coupling twice in one session:
1. "There is no automatic relationship between a MOC and fulfills exercise" — the
   uid-collision problem is GENERIC to any vault file carrying
   `fulfills_exercise_uid`, not MOC-specific.
2. "An Activity Domain MOC is never assigned as Exercise… let those two entities
   exist with independence." An Exercise whose *instructions* say "make yourself a
   Goals MOC" is still just an Exercise; the MOC the user writes is still just a MOC.
The only join is the user's authored `fulfills_exercise_uid:` frontmatter on a
particular file during a particular engagement. Saved as working agreement:
memory `feedback_entity_independence_no_coupling.md`.

**A MOC is an anchor, not a deliverable** (Mike): gather everything you know, link it
via an index page, develop it over time as a discipline. Its home is the living
in-progress channel (context for Askesis/Journals), never a turn-in's primary frame.
**A list comes before a map**: "List your Tasks" is the more valuable first exercise;
a map is what a list can grow into. The mapping exercise ("map this PathStep's
territory") remains *a possibility* — pure content authoring later, zero new
machinery, which is the test that the decoupling is real.

### R2 — Submission semantics: status frontmatter + hand in a copy

- **Living entry**: vault file with `fulfills_exercise_uid:` + `status: in process`
  syncs as ONE entity — deterministic uid, upsert-in-place, ORGANIZES edges re-draw
  freely (if it happens to be a MOC), never carries a FULFILLS_EXERCISE edge. The
  fulfills field on a deterministic-uid vault entry = **declared intent**
  ("exercise in progress"), stored on the entry, validated by the existing
  authorization guard at first sync (fail loud there, not at submit).
- **`status: submitted` + sync = the deliberate turn-in signal** ("submit is a real
  signal where the User is then expecting direct feedback"). Sync files a **frozen
  copy** through the EXISTING turn-in machinery (fresh random-uid node,
  FULFILLS_EXERCISE {revision}, Interaction, audience routing) — the notebook vs the
  pages handed to the teacher. A copy is filed only when content changed since the
  last copy (content-hash state; sync NEVER writes into user files, so idle re-syncs
  while still marked `submitted` are no-ops; editing while submitted = re-submission;
  flip to `in process` to revise in peace).
- **The `create_entry` honesty fix**: today `fulfills_exercise_uid` force-mints a
  random uid even when the caller supplies a deterministic one
  (`user_entry_service.py:191`), making the upsert branch structurally unreachable —
  a vault file with the field would duplicate a submission node on EVERY
  edit-sync, orphan the prior node's ORGANIZES edges (`refresh_moc_organizes` keys on
  source uid), orphan its EntryReport, and inflate the revision counter. The fix
  gives deterministic-uid callers living-entry semantics; the upload/form path (no
  uid) keeps fresh-node turn-ins untouched. Revision = the sequence of submitted
  copies, exactly what `count_entries_for_exercise` already counts.

### R3 — Feedback: TEACHER by default; AI is a manual website option

- The submitted copy routes to the **teacher review queue** (TEACHER_REVIEW pipeline;
  truthful `submitted` per #507's service chokepoint; audience machinery routes to
  the reviewing group). Teacher feedback **already notifies** (`ReportSubmitted` →
  "New feedback on your submission" → navbar bell + GradeBook Entry Reports — the
  surfaces Mike pointed at in screenshots). Zero new delivery machinery.
- **AI feedback is never sync-triggered.** It is a manual option selected at
  `/submissions/exercise` (website submission), or the existing on-page
  "Request AI feedback" button. Ruled explicitly: "the default is `teacher`".
- **Every Exercise has (should have) a group/teacher associated** (Mike's invariant).
  Execution verifies the default-group fallback for curriculum submissions
  (`query_default_groups_for_curriculum_submission`) and surfaces a
  no-reachable-teacher case as an ERROR in sync results, never a silent drop.

### R4–R6 — settled small rulings

- **Modality**: NO new `SubmissionModality` value. Research: the only behavioral
  branch is `Exercise.has_inline_form()`; ingestion leaves modality None; cosmetic.
- **Map rendering** (PR 2 gap from MOC ingestion arc): a MOC-entity concern, not an
  exercise concern. A user entry with ORGANIZES edges renders its ordered children on
  the existing entry detail page `/gradebook/{uid}` (already renders content +
  FULFILLS badge + EntryReports + serves any owned UserEntry), reusing the
  built-but-orphaned `hub_cards_from_organizers` bridge (`ui/patterns/hub.py:270`,
  zero live callers today). Owner-gated; context-only line respected.
- **Prompt**: NO new template/registry entry. Exercise-submission feedback has no
  PROMPT_REGISTRY template at all — `Exercise.get_feedback_prompt()` = instructions +
  context_notes + entry content, deliberately transparent. Unmodified.

### R7 — v1 exemplar content

**"List your Tasks"** and **"List your Goals"** — ASSIGNED scope, teacher → group
(ADR-040 machinery, honors the teacher invariant). List before map. NOT shipped:
"map this PathStep" (future content authoring), Activity-Domain-MOC exercises as
such (the concept was ruled incoherent — an exercise may *ask for* a MOC in its
instructions, that's all), open-access rule for unanchored CURRICULUM exercises
(deferred — today's guard = owner OR group-share OR IN_PROGRESS-on-anchored-PS,
which rejects everyone for unanchored curriculum exercises).

### Research findings that ground execution (Phase 0, all file:line-verified)

- Duplication timing: content-hash tracker skip saves idle syncs; every
  sync-after-edit duplicates (batch.py overwrites the tracker row with the newest
  minted uid; prior nodes never reconciled).
- **EntryReport generation is on-demand-only everywhere today** — sole call site
  `POST /api/exercises/report`; no event subscriber generates reports; CORE tier
  fails honestly at two gates (route ADR-043 per-user + service llm_caller None).
- **AI-path notification gap** (found, logged, NOT in scope unless pulled in):
  AI-generated EntryReports create no notification; only the teacher path publishes
  `ReportSubmitted`.
- **Live inconsistency** (found, logged, out of scope): `Pipeline.KNOWLEDGE`
  docstring claims exclusion from submission counts, but `/submissions/history` keys
  on the FULFILLS edge — an edge-bearing knowledge entry would list anyway. The
  copy model sidesteps it (living entry never carries the edge; copies carry a
  submission pipeline).
- `user_entry_search` never-composed gap: still open, still out of scope (PR 2 log
  above).

### Execution shape (3 PRs, fresh contexts): see
`plans/vault-exercise-channel-arc-prompt.md` — PR 1 channel mechanics, PR 2 surfaces
(map cards + exercise-in-progress visibility), PR 3 exemplar content + live
acceptance walk.

## PR 1 implementation log — channel mechanics (2026-07-04)

Branch `feat/vault-exercise-channel-mechanics`. All R2/R3 mechanics shipped:

- **create_entry collision fix** (`user_entry_service.py`): turn-in is now
  defined as fulfills + NO caller uid (that path byte-for-byte unchanged:
  random mint, `create_with_exercise_link`, revision, Interaction, event
  with fulfills). A deterministic uid + fulfills routes to the upsert —
  the living entry. `uid + fulfills + pipeline=teacher_review` is rejected
  with guidance (turn-ins are frozen).
- **Declared intent = first-class node property** `fulfills_exercise_uid`
  on `UserEntry` + DTO (metadata is a JSON string in Neo4j — unqueryable
  for PR 2's status chips; precedent `Exercise.path_step_uid`). Dual-written
  on copies (property + edge); living entries have property only. Removing
  the frontmatter line clears the property on next sync (upsert `+=` with
  explicit null) — intent withdrawn, no special code path.
- **Linker gating**: `UserEntryCreated.fulfills_exercise_uid` now rides only
  for turn-ins, so the exercise_handler → linker (scope check + title-stamp
  + revision_number write) never touches living entries.
- **Copy-dedup state = the copies themselves**: new
  `get_latest_entry_for_exercise` (backend mixin + `UserEntryCrudOperations`
  + service wrapper) returns the newest FULFILLS-bearing entry (ordered by
  edge revision DESC); the door diffs living content against it. Zero new
  bookkeeping; survives syncs by construction; sync never touches files.
- **Door submit branch** (`user_entry_ingestion.py::_file_submission_copy`):
  submit_signal = uid + fulfills + authored SUBMITTED. Living upsert runs
  with status coerced to ACTIVE (**the living-status decision**: the file's
  `submitted` is a channel signal; the node is not in review — documented in
  UNIFIED_INGESTION_GUIDE § Vault exercise channel). Copy request: no uid,
  TEACHER_REVIEW, status None (service stamps truthful SUBMITTED),
  metadata `{"submitted_from_entry": <living uid>}` — deliberately NO
  vault_file_path so VaultReconciler never write-backs into the copy.
  Zero-successful-shares copy → compensated (deleted) + file fails →
  batch pops file_entity_map → retried next sync; living entry persists.
- **Tests**: 7 new service unit tests (TestLivingEntryChannel), 8 new door
  unit tests (TestVaultExerciseChannel), 6 integration tests
  (`tests/integration/user_entry/test_vault_exercise_channel.py`) covering
  the full acceptance list: N edited syncs → ONE node/zero copies/zero
  edges; ORGANIZES edge survives edited re-sync (stable uid); flip → one
  copy revision 1 + Interaction + SHARED_WITH_GROUP; idle re-sync no-op;
  edit-while-submitted → revision 2 with prior copy frozen intact;
  unreachable-teacher → error + compensation, living stays.
- Gates: ./dev quality (0 errors), 3785 unit passed, user_entry +
  teacher-review integration suites passed (testcontainer), ./dev smoke ✓.

## Implementation log — PR 2 (surfaces), 2026-07-04 (PR #509)

- **Map of Content on /gradebook/{uid}** (`submission_detail`): renders an
  ordered card section for ANY owned entry with outgoing ORGANIZES edges —
  decoupling holds (no exercise/MOC-flag awareness; emergent identity only).
  Wiring: `UserEntryBackend` + shared `_OrganizesMixin` (READ slice only;
  writes stay ingestion-owned) → sixth ISP parent
  `UserEntryOrganizesOperations` (narrow: just `get_organized_children`) →
  `UserEntryService.get_organized_children` →
  `UserEntryOrchestrator.get_entry_organized_children` → route. Fetch errors
  surface inline (Kody #505 precedent), empty = no section.
- **Cross-type hrefs**: `OrganizerResult` gained `entity_type` (both mixin
  queries return it); NEW `ui/patterns/entity_links.py` owns THE
  entity_type → detail-URL mapping (verified against live routes:
  6 activity `/{plural}/detail?uid=`, ku/ps `/explore/…/{uid}`, lp
  `/lp/{uid}`, exercise `/exercises/get?uid=`, user_entry
  `/gradebook/{uid}`, 3 report types `…/detail?uid=`; no-detail types →
  None → "#"). `hub_cards_from_organizers` (formerly zero live callers)
  gained optional per-child `href_for` resolver; template path unchanged.
- **In Progress chips**: all three status queries
  (`get_student_exercises_with_status`, enrolled-PS, per-PS) OPTIONAL-MATCH
  the living entry — owned `user_entry` with
  `fulfills_exercise_uid = exercise.uid` AND NO FULFILLS_EXERCISE edge
  (edge exclusive to frozen copies, PR 1) — newest by `updated_at` →
  `has_in_progress`/`in_progress_uid` on `ExerciseStatusRow`. Chip
  precedence = loop-phase order: report > turn-in > intent > nothing
  (living entry keeps intent forever, so a filed copy must outrank it).
  In Progress action link = "View Entry →" `/gradebook/{living uid}`.
  Badge: BadgeT.accent (violet — distinct from revision amber).
- **Tests**: 8 unit (precedence incl. copy-outranks-intent, badge/link
  render, href mapping table, bridge resolver+ordering) + 3 integration
  (in-progress row lifecycle live→submit; cross-user invisibility;
  ordered typed MOC child reads + empty negative control).
- **Runtime verification** (:8001, authed linguistic76, headless Chrome
  via CDP with session cookie): positive `/gradebook/moc.worldview` → Map
  of Content, 3 child cards in ORGANIZES order (all user_entry →
  /gradebook hrefs); negative `ue_96757d94` → no section;
  `/library/exercises` → real statuses, no phantom In Progress (live graph
  has no living-intent entry yet — chip positive covered by
  integration/unit; PR 3 walk exercises it live). Zero NEW JS error
  classes vs untouched-page baseline.
- **FINDING (pre-existing, follow-up arc)**: ALL authed live pages throw
  3 JS exception classes (also on untouched /profile, 21 exceptions):
  `alpine.3.14.8.min.js:4 SyntaxError: Unexpected token 'var'`,
  `skuel.js:203 TypeError: … reading 'includes'`, `htmx querySelector of
  null`. Invisible to ./dev smoke (static fixtures only). Worth an arc:
  authed-page smoke coverage + fix the three classes.
- Codex quota-blocked (6th consecutive day) → Kody substitute per
  protocol.
- Gates: quality 0 errors, 3814 unit passed, 9 integration passed
  (testcontainer), smoke ✓, bloat 0 dead.

## Implementation log — PR 3 (exemplar content + live acceptance walk), 2026-07-04 (PR #511)

Fresh-context live walk on :8001. The walk itself PASSED end-to-end; it also
surfaced four real pre-existing bugs on the teacher/exercise path (PR #511,
branch `fix/adr040-assigned-exercise-share`).

### Exemplar content (R7)

- "List your Tasks" (`exercise:f65c01234590`, domain tasks) and "List your
  Goals" (`exercise:6fa272981bb2`, domain goals) — created as mfan0110 via
  `POST /api/exercises/create`, scope ASSIGNED, group
  `group_default_user_admin` (member: linguistic76), processor_type human.
  Instructions mention the channel in PROSE only (uid + fulfills +
  status-flip) — R1 decoupling holds; no machinery joins exercise↔file.
- NOTE: API-minted exercise uids are COLON-form (`exercise:<hex>`);
  `fulfills_exercise_uid` frontmatter is taken RAW by the door (no colon→dot
  normalization), so users author exactly the uid every surface shows.
  Vault-authored CURRICULUM exercises store dots — author dots for those.

### Bugs found live (all fixed + revert-verified in #511)

1. **ADR-040 auto-share NEVER worked for API-created exercises**:
   `query_ownership_and_status` read `entity.user_uid` only; Exercise stores
   `owner_uid` + :OWNS edge → share_with_group failed not_found
   (warning-level, node created shareless, invisible to students). First
   live ASSIGNED exercise ever created was this walk's. Fix:
   coalesce(user_uid, OWNS-owner). Note: pure-edge ownership would regress —
   graph has legacy user_uid nodes missing :OWNS (2 tasks, 2 choices, 1
   event, 1 habit, 2 principles).
2. **verify_ownership (CRUD mixin) same family** → every exercise
   delete/update/get_for_user via CRUD factory 500'd. owner_uid fallback.
3. **ExerciseCreate/UpdateRequest.domain unvalidated** → 500 in conversion
   instead of 422 (hit live with domain "Activity Domains"; valid: Domain
   enum values, used "tasks"/"goals").
4. **/notifications page returned `<coroutine object BasePage …>`** —
   missing await (the bell's target page, broken for everyone). Also:
   authed_smoke gained a render-shape guard (this class throws ZERO JS
   errors — event checks passed on a fully broken page); negative-control
   verified; /notifications + /gradebook added to defaults. CRUD factory
   Created/Updated/Deleted logs now success-gated (they printed on failure
   and misled diagnosis).

### The walk (8 syncs, MCP-verified, ≥2 per state)

- Files created (REAL user data, left live): personal vault
  `knowledge/tasks list.md` (uid list:tasks → graph `list.tasks`) and
  `knowledge/goals list.md` (list:goals), frontmatter type user_entry +
  pipeline knowledge + fulfills + `status: in process`; bodies distilled
  from linguistic76's actual Task/Goal nodes.
- Living phase: sync → 2 living entries (property intent, ZERO edges, OWNS
  linguistic76, auto-shared to teacher group by default audience); violet
  "In Progress" chips live on /library/exercises (PR 2's chip positive
  landed); edit+sync → in-place upsert (430 total, 0 copies); idle sync →
  true no-op; /gradebook/list.tasks renders living content.
- Submit phase (tasks list only; goals stays living for the chip):
  `status: submitted` + sync → ONE copy ue_f1485ae2 "List your Tasks v1"
  (FULFILLS rev 1, truthful submitted, teacher_review, SHARED_WITH_GROUP,
  Interaction ia_8ed7d23b, provenance metadata submitted_from_entry); chip
  flips to blue "Submitted" (copy outranks intent, live); idle sync no-op;
  edit-while-submitted + sync → ue_baa6cf8c "v2" rev 2, v1 frozen (does NOT
  contain the new line).
- Feedback phase: both copies in /teaching/queue as mfan0110; feedback .md
  via POST /api/teaching/review/ue_baa6cf8c/report → EntryReport er_0325c1fa
  (HUMAN, REPORT_FOR v2) → linguistic76 bell badge + "New feedback on your
  submission" at /notifications (post-fix) + GradeBook detail shows content,
  Fulfills badge, HUMAN response; copy status completed after review.
- Integrity: vault files byte-identical across syncs (md5); living entries
  intact (active, edges 0, intent present); zero orphaned reports; zero
  ownerless copies; totals exact 428→432 (+2 living +2 copies across 8
  syncs — zero duplicates).

### Residue / observations (logged, not built)

- Both copy revisions appear as separate teacher-queue items (v1 + v2) —
  correct by the copy model; whether the queue should collapse to newest
  revision is a future UX question.
- Interaction.created_at is STRING (writer isoformat) — known temporal
  storage class, matches siblings.
- `user_entry_search` never-composed gap: STILL open, still out of scope.

**Arc status: VAULT EXERCISE CHANNEL arc COMPLETE (PR 1 #508, PR 2 #509,
PR 3 walk + #511 squash-merged a16749f9 2026-07-05, in-session sign-off).
No in-arc loose ends.**

### #511 review round (post-log addendum)

Codex quota-blocked (7th consecutive day) → Kody substitute per protocol.
1/1 finding ACCEPTED + fixed (a7040238): the sharing ownership query must
coalesce the `owner_uid` PROPERTY too, not just user_uid → :OWNS edge —
the edge write is warn-only at exercise create, so property-without-edge
nodes exist and verify_ownership (properties-only) would diverge from
sharing. Final resolution chain in BOTH layers: user_uid → owner_uid →
:OWNS owner. Integration test added for the divergence scenario.
Consideration note + codex-considered applied after final push.
