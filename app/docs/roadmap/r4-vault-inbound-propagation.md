---
title: "R4 Vault Inbound Propagation — Build Plan"
updated: 2026-09-15
status: "scheduled — build plan ruled 2026-09-15; PR 1 next"
registered: 2026-08-24
ruled: 2026-09-15
trigger: "scheduled by Mike 2026-09-15 (was: Mike schedules it — product decision, not a data threshold)"
check: "each PR lands its rig test in tests/integration/test_vault_inbound_propagation.py and fails the mutant named beside it; after PR 1 the live W28→W29 fixture re-points with no twin minted"
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
retires with PR 5.

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
pushed "sync"; for the checkbox the later `✅` date wins). **The base advances only when the
write it implies has landed:** status and fields go in one `TaskUpdateIntent`, one
`update_task`, one verdict; on ok the edge's `source_line` and digest move to the current
line, on refusal or failure they stay, so the next sync sees the same `theirs ≠ base` and
retries — with the warning re-reported until the line and the task agree. Guard 2b's
digest refresh is gated the same way (its in-memory retirement is not: a same-text sibling
is still safe within the ingest, and the stale digest is retired again next time).

**C2 — Deletion is judged with a one-sync grace, never per file at ingest — and the grace
record lives on the Task, not the edge.** A cut-and-paste is a deletion in the source note. A
verdict taken while ingesting that note would cancel the task and, when the destination
ingests, mint a twin (Guard 4 ignores terminal twins) — the exact shape the live W28→W29
fixture shows (below). So a retirement (#1341's pre-pass, and now whole-note deletion too)
hard-deletes the edge as today **and stamps the task** with everything the edge knew
(`retired_vault_id`, `retired_source_line`, `vault_line_retired_at`) in the same statement;
an **end-of-sync sweep** acts on stamps older than the sync's start. A 🆔 that reappears in
any note within one sync — another note or the same one — finds its task by the stamp, is
re-linked, and is reconciled against the base the stamp carried, so a line moved *and*
checked in one edit lands its check whichever note ingests first; one gone for two
consecutive syncs is a deletion and the sweep applies rule 1. The order files ingest in
cannot matter. The stamp is on the task because an edge cannot outlive its note: whole-note
deletion is `DETACH DELETE` on the entry (`IngestionBackend.delete_entities_with_metadata`),
which takes every `EXTRACTED_FROM` with it — an edge-side tombstone would leave every open
task of a deleted note untracked and uncancelled, and would put a third shape in front of
every reader of the edge. `EXTRACTED_FROM` keeps one shape.

**C3 — Every write goes through the domain door.** Status through `update_task` (the
status-guarded write, ADR-087: legality, `completion_date` stamp/clear, `TaskCompleted` /
`TaskReopened` published, the "keep-a-day" rule) — never `backend.update({"status": …})`.
Field edits through `TaskUpdateRequest(...).to_intent()`. A refused write is a sync
warning naming the line, never a crash and never a silent skip.

## The mechanism, branch by branch

### Four properties: one on the edge, three on the task

`EXTRACTED_FROM` gains `source_line` (the raw line as last seen, 🆔 token included — the
parse base). `create_extracted_from_links` sets it on create and on the Guard 2b refresh (the
refresh already rewrites the digest for a moved line; the line text rides with it).
`get_extracted_entities_for_entry` — the one read the guards and the reconciler share —
returns it. Existing edges have no base: the first sight of a 🆔 line after PR 1 stores the
base and applies **nothing** (SKUEL's state stands, the outbound pass writes it back as today
— the "Vacuum" case in the fixture). One `./dev vault-sync --force` after PR 1 seeds every
base at once, so PR 2's reconciliation finds them in place.

`Task` gains `retired_vault_id`, `retired_source_line` and `vault_line_retired_at` — the
grace record, non-null only between a line's disappearance and the sweep (or its re-link).
Set by the retiring statement itself from the edge it deletes (the base travels with the
identity, or an A-first move loses the merge that would land its check), read by the
user-wide 🆔 lookup and the sweep, cleared by re-link or by the sweep after it has acted. No
other reader of `Task` sees them.

### Reconciling a recognised line (the Guard 2b identity branch)

Today the branch counts the line as skipped and `continue`s. It becomes: parse `base`
(stored line) and `theirs` (current line) through the same adapter that minted the task
(`obsidian_task_line_to_parsed`), read `ours` (the task), and hand all three to a **pure,
DB-free** `reconcile_task_line(base, theirs, ours) -> LineReconciliation` in
`core/services/dsl/line_reconciliation.py`. It returns at most one status transition and
one field patch — one intent, one write; the extractor applies it through
`tasks_service.update_task` and records the outcome on the result (`lines_reconciled`,
`reconciliation_errors` → run summary → sync warnings on refusal). The base and digest
refresh for that line is queued only on ok (C1). No base ⇒ store, apply nothing.

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
- **Stamped task, no edge (the line vanished in an earlier sync or earlier in this one — a
  slow move, an A-first move, a whole-note consolidation, or a line deleted and restored in
  the *same* note) ⇒ a revival.** One statement: MERGE the edge on this entry carrying the
  stamp's `retired_source_line` as its base, clear all three stamps. This is the path the
  residual "re-type the line before the next sync" promise depends on; same note or another
  is the same case.
- **Found nowhere ⇒ a phantom:** today's behaviour, and the cleanup script's `--repair-id`
  stays the repair for pre-🆔-era tasks.

In the first two cases the line then takes the identity branch above — reconciled against
the base the old edge carried (onto the new edge by the re-point, through the stamp by the
revival), so a check made *during* the move still lands whichever note ingests first.

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
  t.retired_source_line = r.source_line, t.vault_line_retired_at = datetime()` on the task,
  **one statement** (the edge's base is read before the delete, in the same transaction).
- **A deleted note:** `delete_entities_with_metadata` gains the same stamp on every task
  holding a 🆔-bearing edge into the entry, in the statement that `DETACH DELETE`s it. Today
  those tasks silently become edge-less and stay open forever; under rule 1 they must cancel
  like any other deleted line — after the same grace, so consolidating a week (paste its
  lines into the next note, delete the old one) re-links instead of cancelling.

`VaultReconciler.sync` gains an end-of-sync step after ingest and deletion reconciliation:
`list_vault_retired_tasks(user_uid, retired_before = sync_cutoff)` returns every owned task
whose stamp predates this sync **and that holds no live 🆔-bearing `EXTRACTED_FROM` edge**
(a task can be tracked from two notes — the Guard 4 re-link above writes a second edge for
a line retyped elsewhere — and deleting one of its lines is not deleting the task). For
each: terminal, or still tracked from another note ⇒ clear the stamp; open and untracked ⇒
post `update_task(status = CANCELLED)` through the facade and **clear the stamp only when
that write returns ok**. A refused or failed cancel keeps the stamp (sync warning naming the
task), so the next sweep retries it — the stamp is the retry record and must outlive the
attempt.

Two gates on the cancel, both named by the failure they prevent:

- **The sweep cancels only after a complete inbound pass.** The batch engine records a
  per-file failure (parse, persistence, extraction) in its stats and still returns ok; a
  note that would have revived a stamped task but failed to ingest has not had its say. If
  the sync's inbound half reports any failed file, the sweep clears terminal stamps and
  **holds every open one** — one warning, "N deletions held: the sync had failures" — and the
  next clean sync decides. The per-file failure is already surfaced and retried.
- **One clock.** The stamp is written by Neo4j (`datetime()` inside the retiring statement,
  which runs with no sync context); the cutoff is therefore read from Neo4j too — one
  `RETURN datetime()` at sync start is `sync_cutoff`. An application-clock cutoff against a
  database-clock stamp turns modest skew into a retirement that looks older than the sync
  it happened in, and the grace disappears.

**Until the cancel consequence ships (PR 4), the sweep clears terminal and still-tracked
tasks' stamps only and leaves an open, untracked task's stamp in place:** a stamp is
deletion evidence, and clearing it before any consequence exists would make every line
deleted in the meantime indistinguishable from a pre-🆔-era orphan, never to be cancelled.
PR 4's first sweep therefore cancels the backlog accumulated since PR 1 — the rule applied
late, not skipped — and its PR description says so. A new counter,
`VaultSyncStats.tasks_cancelled_by_deletion`, renders only when nonzero ("N tasks cancelled
— their lines were removed from the vault"), beside "tasks re-opened". A cancel is a state
change the user should see; a retirement alone still is not (#1341's reasoning stands).

The three stamps are scalars and record the **most recently** retired line; a task tracked
from two notes that loses both in one sync keeps the second's base. A revival of the first
🆔 then finds no stamp and resolves the way a phantom does today — by title through Guard 4,
which re-links it if the task is open. Two bases for one task is a shape not worth a
collection property.

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
purpose (ruled 2026-09-15): after PR 1, a `--force` sync must re-point Deck, Repair and Vacuum
to W29 with no twin minted, retire the two W28 originals whose 🆔s W29's twins already own
(stamped, then swept as terminal — uncancelled — and left as the script's RE-MINT proposals),
and — after PR 2 seeds bases — write Vacuum's `[x] ✅` into W29 on the following sync. That
is the arc's acceptance test on real data.

## PR sequence

Each PR: unit tests for the pure/branch logic, one end-to-end case on the existing rig
(`tests/integration/test_vault_done_date_hash_roundtrip.py`'s `Rig`, moved to a shared
fixture module; new file `test_vault_inbound_propagation.py`), and the mutant it must fail
(run it — the round-trip file's tests were each probed that way in #1341).

1. **Identity survives a line's disappearance for one sync.** The three stamps on Task;
   `source_line` on the edge (written on create and refresh, read back — no reconciliation
   yet); `retire_extracted_from_links` (delete + stamp, one statement) replaces the delete in
   the pre-pass; `delete_entities_with_metadata` stamps a deleted note's tasks;
   `find_task_by_vault_id` (live edges ∪ stamped tasks); `repoint_extracted_from_link` and
   the revival write, each one statement carrying the base; Guard 4 writes the edge when the
   twin has none to this entry; the end-of-sync sweep clears **terminal** tasks' stamps
   older than the sync and leaves open tasks' stamps alone. One PR, not two: a stamp with no
   re-link path is a window in which every slow move becomes a deletion. Rig: cut a line
   from note A into note B in one edit → sync → one task, edge on B, no twin; A-first and
   B-first ingest orders (name the files to force each); cut, sync, paste, sync → same task;
   delete, sync, restore in the same note, sync → same task, stamp cleared; delete a done
   line, sync, sync → stamp gone; delete an open line, sync, sync → still open, **still
   stamped**; delete a note → its tasks stamped; retype an open task's line in a second note
   → two edges, delete the first line, sync, sync → stamp cleared, task untouched. Mutants:
   the lookup ignores stamped tasks (the slow move mints a twin); the re-point as two calls
   with the create failing (the task is left edge-less); the sweep clears an open, untracked
   task's stamp; the note-deletion statement stamps nothing; the cutoff read from the
   application clock (skew the test's stamp by a minute). Post-merge: one `--force` sync,
   then the W28→W29 fixture.
2. **Base line + status both directions.** `--force` seeds bases; `reconcile_task_line`
   (status rows of the table above) applied through `update_task`; base and digest refresh
   gated on ok. Rig: check in the vault → completed with the ✅ date; uncheck → reopened;
   **complete in SKUEL, sync before the write-back → still completed** (the C1 race); reopen
   in SKUEL, sync → still reopened; move a line and check it in one edit, A-first → completed
   (the base rode the stamp). Mutants: the branch ignores `base` (the race rows flip); the
   refresh runs on a refused write (the edit is never retried).
3. **Field edits.** Title, due, scheduled, priority, tags — three-way per field, in the same
   intent as status; the "keep-a-day" refusal surfaces as a warning and holds the base. Rig:
   retitle + re-date in the vault, sync, the task follows; a SKUEL-side title edit with an
   untouched line survives the next sync; remove the only date in the vault → warning, base
   held, warning again next sync. Mutant: any field applied without `theirs ≠ base`.
4. **Deletion cancels open tasks.** The sweep posts `CANCELLED` for open tasks and clears
   the stamp only on an ok write; the backlog since PR 1 is cancelled on the first sweep and
   the PR says so; the counter and its fragment line. Rig: delete an open task's line, two
   syncs → cancelled; delete a done line → untouched; delete a whole note → its open tasks
   cancelled two syncs later, its done ones untouched; cut/paste across a sync boundary →
   moved, not cancelled; delete a line, then break the note that restores it (bad
   frontmatter), sync → held with a warning, fix the note, sync → revived, not cancelled.
   Mutants: the sweep cancels terminal tasks; the stamp is cleared before the cancel's result
   is known (a refused cancel becomes a permanent divergence); the sweep runs over a failed
   file (the broken note's task is cancelled); the sweep ignores a live second edge.
5. **Docs.** ADR-070: status annotation retired, Decision 2's `[x]`/`✅` rows and the field
   rows true, `source_line` and the three stamps in Decision 1, a Decision 3 paragraph naming
   the three-way merge; CLAUDE.md § Obsidian VaultBridge and § Unified Content Ingestion; the
   neo4j-cypher-patterns reference's `EXTRACTED_FROM` row; `cleanup_duplicate_vault_tasks.py`
   narrowed to pre-🆔-era repair; this file → `done/`.

Sequencing note: 1 → 2 → 3 is fixed (status needs the base the stamp carries; edits need
the status intent to ride in); 4 depends only on 1 and may land any time after it; 5 last.

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
- One edge property (`source_line`) and three task properties (`retired_vault_id`,
  `retired_source_line`, `vault_line_retired_at`); the cleanup script's phantom/dangling
  census should read a stamped task as owning its 🆔 during the grace.
- A cancel-by-deletion is one sync late by design (the grace). An accidental line deletion
  is undone by re-typing the line before the next sync, or by un-cancelling in SKUEL after.
- A `[ ]` line on a `CANCELLED` task diverges visibly until the user acts — the rule 1
  asymmetry, chosen over silently reopening cancelled work.
- First sight seeds the base and applies nothing: a line that changed *between* the last
  pre-R4 sync and the seeding sync is not reconciled. Seed with `--force` immediately after
  PR 1 (bases are written from then on) so PR 2 finds them in place.
- A refused vault edit re-warns on every sync until the line and the task agree — standing
  visibility, the same contract as ignored files.
- A sync with any failed file holds every pending cancel until a clean sync — deletion
  waits on the vault being readable, which is the honest order.

**Named cost while open:** unchanged from the parking ruling until PR 2 lands — vault-side
checks, unchecks and edits of 🆔 lines do not propagate; tracked tasks must be completed and
edited in SKUEL. After PR 1, moves and retyped lines are tracked correctly.
