---
title: "R4 Vault Inbound Propagation — Build Plan"
updated: 2026-09-15
status: "scheduled — build plan ruled 2026-09-15; PR 1 next"
registered: 2026-08-24
ruled: 2026-09-15
trigger: "scheduled by Mike 2026-09-15 (was: Mike schedules it — product decision, not a data threshold)"
check: "each PR lands its rig test in tests/integration/test_vault_inbound_propagation.py and fails the mutant named beside it; after PR 2 the live W28→W29 fixture re-points with no twin minted"
---

# R4 Vault Inbound Propagation — Build Plan

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

## Ruling (Mike, 2026-09-15)

**Unparked.** The vault becomes the place tasks are edited: a vault-side check, uncheck,
edit, move or deletion of a 🆔 line reaches the SKUEL task. Three product rules:

1. **Deletion cancels an open task and leaves a terminal one.** Clearing done lines out of a
   weekly note is tidying, not a state change; removing an open task's line is a decision, and
   `CANCELLED` records it reversibly (the graph keeps the history; a hard delete would tear
   out knowledge/goal edges and substance events).
2. **Moves re-point.** A 🆔 line cut from one note and pasted into another keeps its task; the
   provenance edge follows the line. A move is never a deletion plus a re-mint.
3. **Markdown is authoritative for what ADR-070 Decision 2 already says it is** — title, due
   (📅), scheduled (⏳), priority, `#tags`, and the checkbox in both directions — with SKUEL's
   own completion/reopen winning only when the vault line has not changed since SKUEL last
   saw it (Decision 3's field-level merge, made concrete below).

What this makes true: ADR-070's title. Its status annotation ("outbound-only for task state")
retires with PR 6.

## History, in three lines

The reconciler's inbound half has been `ingest_directory`-only since its first commit; the
CLAUDE.md "completions propagate back" claim landed two days *after* the outbound-only code
(`git log --all -S` on both, 2026-08-23). Ruled then: make the docs honest, park the build here.
Foundation laid since: Guard 2b (#1143 — the 🆔 is identity at ingest) and line-deletion
retirement (#1341 — an edge whose line is gone by both keys is retired; a stripped token is
re-minted; `done/line-deletions-leave-extracted-from-edges.md`).

## Three constraints every PR must respect — each named by the failure it prevents

**C1 — The change signal is a three-way merge per field, never a hash inequality and never a
bare state comparison.** The hash cannot say *what* changed. And a bare "line state ≠ task
state ⇒ apply the line" loses every completion made in SKUEL: the sync runs inbound *before*
outbound, so on the sync right after you complete a task in SKUEL the line still reads
`- [ ]` and the branch would reopen it before the write-back ever ran (mirror case: reopen in
SKUEL, the line still reads `[x] ✅`, the branch re-completes it). The fix is to know what the
line looked like when SKUEL last saw it: **the edge stores the last-seen line verbatim
(`source_line`)** beside its digest. Then for each field: base = the stored line, theirs = the
current line, ours = the task. A field changed on the vault side (theirs ≠ base) is applied;
a field unchanged on the vault side keeps SKUEL's value, and the outbound pass writes it
back as today. Both sides changed the same field ⇒ the vault wins (Decision 3: the user just
pushed "sync"; for the checkbox the later `✅` date wins).

**C2 — Deletion is judged with a one-sync grace, never per file at ingest — and the grace
record lives on the Task, not the edge.** A cut-and-paste is a deletion in the source note. A
verdict taken while ingesting that note would cancel the task and, when the destination
ingests, mint a twin (Guard 4 ignores terminal twins) — the exact shape the live W28→W29
fixture shows (below). So a retirement (#1341's pre-pass, and now whole-note deletion too)
hard-deletes the edge as today **and stamps the task** (`retired_vault_id`,
`vault_line_retired_at`) in the same statement; an **end-of-sync sweep** acts on stamps older
than the sync's start. A 🆔 that reappears in any note within one sync — another note or the
same one — finds its task by the stamp and is re-linked; one gone for two consecutive syncs is
a deletion and the sweep applies rule 1. The order files ingest in cannot matter. The stamp
is on the task because an edge cannot outlive its note: whole-note deletion is `DETACH DELETE`
on the entry (`IngestionBackend.delete_entities_with_metadata`), which takes every
`EXTRACTED_FROM` with it — an edge-side tombstone would leave every open task of a deleted
note untracked and uncancelled, and would put a third shape in front of every reader of the
edge. `EXTRACTED_FROM` keeps one shape.

**C3 — Every write goes through the domain door.** Status through `update_task` (the
status-guarded write, ADR-087: legality, `completion_date` stamp/clear, `TaskCompleted` /
`TaskReopened` published, the "keep-a-day" rule) — never `backend.update({"status": …})`.
Field edits through `TaskUpdateRequest(...).to_intent()`. A refused write is a sync
warning naming the line, never a crash and never a silent skip.

## The mechanism, branch by branch

### Three properties: one on the edge, two on the task

`EXTRACTED_FROM` gains `source_line` (the raw line as last seen, 🆔 token included — the
parse base). `create_extracted_from_links` sets it on create and on the Guard 2b refresh (the
refresh already rewrites the digest for a moved line; the line text rides with it).
`get_extracted_entities_for_entry` — the one read the guards and the reconciler share —
returns it. Existing edges have no base: the first sight of a 🆔 line after PR 3 stores the
base and applies **nothing** (SKUEL's state stands, the outbound pass writes it back as today
— the "Vacuum" case in the fixture). One `./dev vault-sync --force` after PR 3 seeds every
base at once.

`Task` gains `retired_vault_id` and `vault_line_retired_at` — the grace record, non-null only
between a line's disappearance and the sweep (or its re-link). Set by the retiring statement
itself, read by the user-wide 🆔 lookup and the sweep, cleared by re-link or by the sweep
after it has acted. No other reader of `Task` sees them.

### Reconciling a recognised line (the Guard 2b identity branch)

Today the branch counts the line as skipped and `continue`s. It becomes: parse `base`
(stored line) and `theirs` (current line) through the same adapter that minted the task
(`obsidian_task_line_to_parsed`), read `ours` (the task), and hand all three to a **pure,
DB-free** `reconcile_task_line(base, theirs, ours) -> LineReconciliation` in
`core/services/dsl/line_reconciliation.py`. It returns at most one status transition and
one field patch; the extractor applies them through `tasks_service.update_task` and records
the outcome on the result (`lines_reconciled`, `reconciliation_errors` → run summary → sync
warnings on refusal). No base ⇒ store, apply nothing.

Status, both directions, from the checkbox + trailing `✅`:

| base | theirs | ours | verdict |
|---|---|---|---|
| `[ ]` | `[ ]` | completed | vault unchanged — keep completed; outbound writes `[x] ✅` |
| `[ ]` | `[x] ✅ D` | not completed | vault checked — complete, `completion_date = D` (today if dateless) |
| `[ ]` | `[x] ✅ D` | completed on D′ | both completed — later date wins (Decision 3); tie: nothing |
| `[x] ✅ D` | `[ ]` | completed | vault unchecked — reopen (`status = ACTIVE`); a stale trailing `✅` the user left is SKUEL's and the outbound un-check strips it |
| `[x] ✅ D` | `[x] ✅ D` | reopened in SKUEL | vault unchanged — keep reopened; outbound un-checks as today |
| any | `[ ]` | cancelled | not a reopen — cancel is a SKUEL decision; the line stays open and diverges visibly (the user can complete it in the vault: `[x]` on a cancelled task is a check, applied) |

A dateless `[x]` the user ticked without the plugin completes with today; the outbound pass
then appends SKUEL's `✅ today`, and from then on SKUEL owns that completion (a later reopen in
SKUEL un-checks it) — consistent with ADR-070 § Decision 4 op. 3.

Fields, each on its own three-way rule (theirs ≠ base ⇒ apply): title (the line's
description), `due_date` (📅), `scheduled_date` (⏳), `priority` (emoji → `Priority`),
`tags` (`#tags`; the SKUEL-stamped `period:{kind}` tag is excluded from the diff). Writes go
through `TaskUpdateRequest(...).to_intent()`; the "keep-a-day" rule (a task keeps a day —
removing the only date is refused) surfaces as a warning naming the line, not an error.

### Moves — resolved on the destination side

A parsed line carries 🆔 X and this entry holds no edge for X. Today: Guard 4 merges an
active twin (no edge written) or a terminal one re-mints a twin. New: the processing service
pre-scans the text (`VAULT_ID_RE`, the same oracle as #1341's pre-pass), subtracts the ids
this entry's edges own, and looks the rest up **user-wide** (new read:
`find_task_by_vault_id(user_uid, X)` — a live edge `(task)-[:EXTRACTED_FROM {vault_id: X}]->
(:UserEntry {user_uid})` **or** an owned task stamped `retired_vault_id = X`). Three cases:

- **Live edge on another entry ⇒ a move.** Re-pointed in **one statement**
  (`repoint_extracted_from_link`): delete the old edge keyed on `(task, X)`, MERGE the new one
  on this entry with the current digest and `source_line`. Two service calls would leave a
  window in which the only identity edge is gone and a retry mints a twin — a re-point is one
  transaction or it is not a re-point.
- **Stamped task, no edge (the line vanished in an earlier sync — a slow move, a whole-note
  consolidation, or a line deleted and restored in the *same* note) ⇒ a revival.** One
  statement: MERGE the edge on this entry, clear both stamps. This is the path the residual
  "re-type the line before the next sync" promise depends on; same note or another is the
  same case.
- **Found nowhere ⇒ a phantom:** today's behaviour, and the cleanup script's `--repair-id`
  stays the repair for pre-🆔-era tasks.

In the first two cases the line then takes the identity branch above — reconciled against
the base the old edge carried (carried onto the new edge by the re-point; a revival has no
base and seeds one), so a check made *during* the move still lands.

Same family, same PR: a 🆔-less line Guard 4 merges into an active twin that has **no edge to
this entry** (the twin's uid is not among `existing_extracted`'s values) gets its edge
written. Kody #501's no-write rule exists to avoid clobbering the twin's edge *to this entry*;
when there is none, MERGE creates and nothing is clobbered. This closes the cleanup script's
LINE-BACKED class: a line retyped for an open task is tracked again and re-keyed by the
outbound pass.

### Deletion — stamp, sweep, cancel

Two doors retire, one record, one sweep.

- **A line gone from a surviving note:** the #1341 pre-pass keeps its verdict (both keys
  gone) and its in-memory digest pruning; `delete_extracted_from_links` becomes
  `retire_extracted_from_links` — the same keyed delete, plus `SET t.retired_vault_id = X,
  t.vault_line_retired_at = datetime()` on the task, **one statement**.
- **A deleted note:** `delete_entities_with_metadata` gains the same stamp on every task
  holding a 🆔-bearing edge into the entry, in the statement that `DETACH DELETE`s it. Today
  those tasks silently become edge-less and stay open forever; under rule 1 they must cancel
  like any other deleted line — after the same grace, so consolidating a week (paste its
  lines into the next note, delete the old one) re-links instead of cancelling.

`VaultReconciler.sync` gains an end-of-sync step after ingest and deletion reconciliation:
`list_vault_retired_tasks(user_uid, retired_before = sync_started_at)` returns every owned
task whose stamp predates this sync. For each: terminal ⇒ clear the stamp; open ⇒ post
`update_task(status = CANCELLED)` through the facade and **clear the stamp only when that
write returns ok**. A refused or failed cancel keeps the stamp (sync warning naming the
task), so the next sweep retries it — the stamp is the retry record and must outlive the
attempt. A new counter, `VaultSyncStats.tasks_cancelled_by_deletion`, renders only when
nonzero ("N tasks cancelled — their lines were removed from the vault"), beside "tasks
re-opened". A cancel is a state change the user should see; a retirement alone still is not
(#1341's reasoning stands).

The grace window: cut, sync, paste, sync — the first sync stamps, the second re-links before
its sweep runs, and the sweep only acts on stamps older than that sync's start. A paste that
never comes is a deletion two syncs after the cut.

### Out of scope, by name

🔁 recurrence and ⛔ dependencies (Decision 2: read-only), 🛫 start (Task has no field),
`@context()` prose lines and bridge-generated lines (no 🆔, no identity — unchanged),
non-Task activity domains (the checkbox door mints Tasks only), and the content vault (no
round trip). The two hard-authored duplicates already in the graph (Mirror, Trailer — below)
are the cleanup script's propose/confirm, not this arc's.

## The live fixture: W28 → W29

Read-only probe, 2026-09-15 (`scripts/cleanup_duplicate_vault_tasks.py` dry run + a direct
edge-vs-note read): the five "dangling" W28 edges from the #1143 census are five lines the
owner **moved** into `2026-W29.md`, 🆔s intact. What today's guards did with them:

| line moved to W29 | task in SKUEL | on W29's ingest |
|---|---|---|
| `[x] Mirror via FB marketplace… ✅` | completed | Guard 4 ignores terminal twins → **a second completed task**, edge into W29 |
| `[x] Trailer @Van 🏁 keep ✅` | completed | same — a twin |
| `[ ] Deck coating purchase` | draft | Guard 4 merged, **no edge**; the W28 edge is its only link |
| `[ ] Repair on Fraser 28th?` | draft | same |
| `[ ] Vacuum` | completed (after the move) | merged while open; the write-back aims at W28 and W29's line stays `[ ]` |

The cleanup script's DANGLING count reads 0 on the same graph — its definition is vault-wide
(the ids *are* on lines), the census's was per-entry. Both are right. Left untouched on
purpose (ruled 2026-09-15): after PR 2, a `--force` sync must re-point Deck, Repair and Vacuum
to W29 with no twin minted, retire the two W28 originals whose 🆔s W29's twins already own
(stamped, then swept as terminal — uncancelled — and left as the script's RE-MINT proposals),
and — after PR 3 seeds bases — write Vacuum's `[x] ✅` into W29 on the following sync. That
is the arc's acceptance test on real data.

## PR sequence

Each PR: unit tests for the pure/branch logic, one end-to-end case on the existing rig
(`tests/integration/test_vault_done_date_hash_roundtrip.py`'s `Rig`, moved to a shared
fixture module; new file `test_vault_inbound_propagation.py`), and the mutant it must fail
(run it — the round-trip file's tests were each probed that way in #1341).

1. **The stamp + the sweep, no consequence yet.** `retired_vault_id` /
   `vault_line_retired_at` on Task; `retire_extracted_from_links` (delete + stamp, one
   statement) replaces the delete in the pre-pass; `delete_entities_with_metadata` stamps a
   deleted note's tasks; the reconciler's end-of-sync sweep clears stamps older than the sync.
   Rig: delete a line, sync, sync → stamp gone; delete the note → its tasks stamped, still
   open. Mutants: the sweep clears stamps from *this* sync (a same-sync revival would lose
   its record); the note-deletion statement stamps nothing.
2. **Moves re-point; revivals and retyped lines re-link.** `find_task_by_vault_id` (live
   edges ∪ stamped tasks); `repoint_extracted_from_link` and the revival write, each one
   statement; Guard 4 writes the edge when the twin has none to this entry. Rig: cut a line
   from note A into note B in one edit → sync → one task, edge on B, no twin; A-first and
   B-first ingest orders (name the files to force each); cut, sync, paste, sync → same task;
   delete, sync, restore in the same note, sync → same task, stamp cleared. Mutants: the
   lookup ignores stamped tasks (the slow move mints a twin); the re-point as two calls with
   the create failing (the task is left edge-less). Post-merge: the W28→W29 fixture.
3. **Base line + status both directions.** `source_line` on create/refresh; `--force` seeds
   bases; `reconcile_task_line` (status rows of the table above) applied through
   `update_task`. Rig: check in the vault → completed with the ✅ date; uncheck → reopened;
   **complete in SKUEL, sync before the write-back → still completed** (the C1 race); reopen
   in SKUEL, sync → still reopened. Mutant: the branch ignores `base` (the race rows flip).
4. **Field edits.** Title, due, scheduled, priority, tags — three-way per field; the
   "keep-a-day" refusal surfaces as a warning. Rig: retitle + re-date in the vault, sync, the
   task follows; a SKUEL-side title edit with an untouched line survives the next sync.
   Mutant: any field applied without `theirs ≠ base`.
5. **Deletion cancels open tasks.** The sweep posts `CANCELLED` for open tasks and clears
   the stamp only on an ok write; the counter and its fragment line. Rig: delete an open
   task's line, two syncs → cancelled; delete a done line → untouched; delete a whole note →
   its open tasks cancelled two syncs later, its done ones untouched; cut/paste across a sync
   boundary → moved, not cancelled. Mutants: the sweep cancels terminal tasks; the stamp is
   cleared before the cancel's result is known (a refused cancel becomes a permanent
   divergence).
6. **Docs.** ADR-070: status annotation retired, Decision 2's `[x]`/`✅` rows and the field
   rows true, `source_line`/`retired_at` in Decision 1, a Decision 3 paragraph naming the
   three-way merge; CLAUDE.md § Obsidian VaultBridge and § Unified Content Ingestion; the
   neo4j-cypher-patterns reference's `EXTRACTED_FROM` row; `cleanup_duplicate_vault_tasks.py`
   narrowed to pre-🆔-era repair; this file → `done/`.

Sequencing note: 1 → 2 is fixed (moves need the stamp to be order-independent); 3 → 4 is
fixed (edits need the base); 2 and 3 are independent and 5 depends only on 1.

## Rejected alternatives

- **Per-file deletion verdict at ingest** (what #1341 ships, kept as the *verdict*, not the
  *consequence*): turns every move into cancel + twin. Rejected by the fixture.
- **A vault-wide 🆔 scan on every sync** to make the per-file verdict safe: reads every note
  per sync from inside `core/services` (a port and an adapter for one rare question), and
  still misses a paste that lands after the sync. The one-sync grace answers both.
- **A tombstone on the edge (`retired_at`, readers exclude it)** — the plan's first draft.
  Rejected on review: an edge cannot outlive its note (whole-note deletion is `DETACH
  DELETE` on the entry), so a deleted note's open tasks would never reach the sweep; and it
  puts a third shape in front of every `EXTRACTED_FROM` reader. The stamp on the task
  survives the note, is read by one lookup and one sweep, and leaves the edge one shape.
- **End-of-sync aggregation of per-file retirement lists instead of a grace record**: keeps
  one edge shape but threads a new list through `ingest_user_entry` → `batch.py` →
  `IncrementalStats` → the reconciler, and still cannot see a paste one sync later. The
  stamp is two properties, one lookup, and a sweep.
- **Hash inequality as the reconciliation trigger** (Codex round-5 P1 on #1143, rejected then
  and still): Guard 2b deliberately refreshes the digest on every moved line, so inequality
  is transient by design, and it cannot say what changed.
- **Bare state comparison** (no base): loses every SKUEL-side completion and reopen to the
  inbound-before-outbound order (C1).
- **Hard delete on line deletion**: takes knowledge/goal edges and substance history with the
  task; `CANCELLED` is the reversible record.

## Costs and residuals after the build

- One extra read per recognised 🆔 line on re-ingest (the task, for `ours`) — ~20 per weekly
  note; batch through the Tasks backend if a census shows notes larger than that.
- One edge property (`source_line`) and two task properties (`retired_vault_id`,
  `vault_line_retired_at`); the cleanup script's phantom/dangling census should read a
  stamped task as owning its 🆔 during the grace.
- A cancel-by-deletion is one sync late by design (the grace). An accidental line deletion
  is undone by re-typing the line before the next sync, or by un-cancelling in SKUEL after.
- A `[ ]` line on a `CANCELLED` task diverges visibly until the user acts — the rule 1
  asymmetry, chosen over silently reopening cancelled work.
- First sight seeds the base and applies nothing: a line that changed *between* the last
  pre-R4 sync and the seeding sync is not reconciled. Seed with `--force` immediately after
  PR 3 to keep that window empty.

**Named cost while open:** unchanged from the parking ruling until PR 3 lands — vault-side
checks, unchecks and edits of 🆔 lines do not propagate; tracked tasks must be completed and
edited in SKUEL. After PR 2, moves and retyped lines are tracked correctly.
