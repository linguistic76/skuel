---
title: "R4 Vault Inbound Propagation — Build Plan"
updated: 2026-09-16
status: "in progress — PR 1 (identity survives one sync: stamps, source_line base, re-point/revival, sweep) #1343; PR 2 (reconciliation: status both directions + field edits, one intent per line, base advances on ok) #1344; PR 3 (deletion cancels open tasks: the sweep posts CANCELLED through the facade, stamp cleared on ok, the counter) #1345; PR 4 (docs) next"
registered: 2026-08-24
ruled: 2026-09-15
trigger: "scheduled by Mike 2026-09-15 (was: Mike schedules it — product decision, not a data threshold)"
check: "each PR lands its rig test in tests/integration/test_vault_inbound_propagation.py and fails the mutant named beside it (PR 1: 8 of 8; PR 2: 3 of 3; PR 3: 4 of 4 — in the PR bodies); after PR 1 one ./dev vault-sync --force seeds every base and the live W28→W29 fixture re-points with no twin minted; after PR 2 the first plain sync meets the seeded bases against SKUEL's own write-backs as ties and applies nothing wrongly; after PR 3 the first plain sync cancels the stamped backlog (censused in the PR body) and nothing else"
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
retires with PR 4.

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
parse base). `create_extracted_from_links` sets it on create and **seeds** it on an edge that
has none; it **advances** it (on the Guard 2b refresh, which already rewrites the digest for
a moved line) only once reconciliation exists to consume the diff, and only on an ok write
(C1). The two verbs are deliberately split across PRs: a base that advances before its
consumer ships absorbs every vault edit made in between as "already seen", and the consumer
then never applies them. So PR 1 seeds and never advances — edits made between PR 1 and
PR 2 accumulate as diffs against the seeded base and land when PR 2 arrives — and status
and fields ship together in PR 2, because they share one base string: advancing it for a
status reconciliation would absorb an unreconciled title edit on the same line.
`get_extracted_entities_for_entry` — the one read the guards and the reconciler share —
returns it. Existing edges have no base: the first sight of a 🆔 line after PR 1 seeds the
base and applies **nothing** (SKUEL's state stands, the outbound pass writes it back as today
— the "Vacuum" case in the fixture). One `./dev vault-sync --force` after PR 1 seeds every
base at once.

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
  on this entry **carrying the old edge's `source_line` and digest unchanged** — the base is
  what SKUEL last saw, and a line edited or checked during the move must still diff against
  it; the identity branch then reconciles and, on ok, advances both (C1). Writing the
  current line as the new edge's base would make the move-time edit its own base and drop
  it. Two service calls would leave a window in which the only identity edge is gone and a
  retry mints a twin — a re-point is one transaction or it is not a re-point.
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
`list_vault_retired_tasks(user_uid, retired_before = sync_cutoff)` returns **every** owned
task whose stamp predates this sync, each row saying whether the task still holds a live
🆔-bearing `EXTRACTED_FROM` edge (a task can be tracked from two notes — the Guard 4 re-link
above writes a second edge for a line retyped elsewhere — and deleting one of its lines is
not deleting the task). The reconciler branches on that row: terminal, or still tracked from
another note ⇒ clear the stamp; open and untracked ⇒ post `update_task(status = CANCELLED)`
through the facade and **clear the stamp only when that write returns ok**. A refused or
failed cancel keeps the stamp (sync warning naming the task), so the next sweep retries it —
the stamp is the retry record and must outlive the attempt.

Two gates on the sweep, both named by the failure they prevent:

- **The sweep runs only after a complete inbound pass — and holds every stamp otherwise,
  terminal ones included.** The batch engine records a per-file failure (parse, persistence,
  extraction) in its stats and still returns ok; a note that would have revived a stamped
  task but failed to ingest has not had its say. Clearing even a *terminal* task's stamp on
  such a sync destroys the only 🆔 mapping its restored line could revive by, and on the next
  clean sync Guard 4 — which ignores terminal twins by design — mints a duplicate completed
  task. So with any failed file the sweep does nothing at all — one warning, "N retirements
  held: not every note had its say" — and the next clean sync decides. The per-file failure is
  already surfaced and retried. **The same hold for a vault in doubt as a whole** (found by
  review on PR 3): a walk that finds no files ("No files found" is a run-level error —
  `files_failed` stays 0) and a mass-deletion refusal (the valve's verdict, which survived only
  as a warning string until `IncrementalStats.mass_deletion_refused`) are every note in doubt at
  once; without the hold an unmounted root or a sync client mid-resync would cancel every open
  task whose paste was one sync away, and the remount would mint a twin beside each. One
  predicate, `VaultSyncStats.inbound_pass_incomplete` (`files_failed` / `files_broken` /
  `mirror_files_stale` / `vault_read_refused`), is the sweep's gate.
- **One clock.** The stamp is written by Neo4j (`datetime()` inside the retiring statement,
  which runs with no sync context); the cutoff is therefore read from Neo4j too — one
  `RETURN datetime()` at sync start is `sync_cutoff`. An application-clock cutoff against a
  database-clock stamp turns modest skew into a retirement that looks older than the sync
  it happened in, and the grace disappears.

**The cancel consequence is built (PR 3).** Between PR 1 and PR 3 the sweep cleared
terminal and still-tracked tasks' stamps only and left an open, untracked task's stamp in
place — a stamp is deletion evidence, and clearing it before any consequence existed would
have made every line deleted in the meantime indistinguishable from a pre-🆔-era orphan,
never to be cancelled. PR 3's first sweep therefore cancelled the backlog accumulated since
PR 1 — the rule applied late, not skipped — and its PR description carries the census. The
counter `VaultSyncStats.tasks_cancelled_by_deletion` renders only when nonzero ("N tasks
cancelled — their lines were removed from the vault"), beside "tasks re-opened", on the
sync fragment and the JSON stats alike. A cancel is a state change the user should see; a
retirement alone still is not (#1341's reasoning stands). A refused cancel is one warning
per task ("cancel refused for <uid> … — retried next sync"), the PR 2 precedent (a refusal
names its line); a task whose stored status `EntityStatus` cannot read is held the same
way, not cancelled — the sweep cancels what it can read as open, nothing else.

**The stamp clears with the cancel (ruled, PR 3).** The alternative — keeping
`retired_vault_id` on a cancelled task so the revival path finds a line typed back later —
would make the sweep's "stamp cleared" invariant conditional, leave a stamp with no grace
attached (listed by every later sweep, or needing a fourth state), and re-link the line to
a task that then sits at row 6 (`[ ]` on a cancelled task diverges visibly until the user
acts). So a 🆔 line typed back *after* its cancel is a phantom: Guard 4 ignores terminal
twins, so it mints a new open task beside the cancelled one and adopts the line's 🆔 — the
cancelled task is the record of the deletion, not resurrected. The two doors the residual
names both hold and are pinned on the rig: re-type the line *before* the next sync (the
revival), or un-cancel in SKUEL *first* and then type it back (Guard 4 merges it into the
open twin by title and writes the edge). A note restored after its tasks were cancelled is
the same shape at note scale — new tasks, not a resurrection.

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
and — once PR 2 reconciles against the seeded bases — write Vacuum's `[x] ✅` into W29 on the
following sync. That is the arc's acceptance test on real data.

## PR sequence

Each PR: unit tests for the pure/branch logic, one end-to-end case on the existing rig
(`tests/integration/test_vault_done_date_hash_roundtrip.py`'s `Rig`, moved to a shared
fixture module; new file `test_vault_inbound_propagation.py`), and the mutant it must fail
(run it — the round-trip file's tests were each probed that way in #1341).

1. **Identity survives a line's disappearance for one sync** — ✅ #1343. The three stamps on Task;
   `source_line` on the edge — written on create, **seeded** where absent, carried by
   re-point and revival, never advanced (no reconciliation yet, so nothing may be marked
   "seen"); `retire_extracted_from_links` (delete + stamp, one statement) replaces the delete
   in the pre-pass; `delete_entities_with_metadata` stamps a deleted note's tasks;
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
   with the create failing (the task is left edge-less); the re-point writes the current
   line as the new base (an edit made during a B-first move is dropped in PR 2's rig); the
   Guard 2b refresh advances a present base (an edit made before PR 2 is lost); the sweep
   clears an open, untracked task's stamp; the sweep runs over a failed file (a completed
   task's restored line mints a twin next sync); the note-deletion statement stamps nothing;
   the cutoff read from the application clock (skew the test's stamp by a minute).
   Post-merge: one `--force` sync, then the W28→W29 fixture.
2. **Reconciliation — status both directions and field edits, together** — ✅ #1344. One
   base string, one intent, one write, one verdict; `reconcile_task_line` (the status rows of
   the table above plus title, due, scheduled, priority, tags — three-way per field) applied
   through `update_task`; base and digest advance only on ok; the "keep-a-day" refusal
   surfaces as a warning, holds the base, and leaves the note un-stamped so it re-warns every
   sync. Found while building: **SKUEL's own outbound writes must advance the base too** —
   the `[x] ✅` write-back, the un-check and the 🆔 injection change the line *after* its
   ingest, and a base that stopped at the ingest read SKUEL's own write-back as a vault
   check on the next sync (a task reopened in SKUEL between the write-back and the re-ingest
   was re-completed by its own `✅`). Each landed mutation is applied to the base as to the
   file (`_OwnWrite` in the reconciler — the same pure function, on the base's text, so a
   vault edit on the line stays a diff). Field rules apply to obsidian-tasks lines only; a
   `@context(task)` line reconciles its checkbox (`ParseDoor`). Rig: check in the vault → completed with the ✅ date; uncheck
   → reopened; **complete in SKUEL, sync before the write-back → still completed** (the C1
   race); reopen in SKUEL, sync → still reopened; move a line and check it in one edit,
   A-first and B-first → completed (the base rode the stamp / the re-point); retitle +
   re-date in the vault → the task follows; a SKUEL-side title edit with an untouched line
   survives the next sync; check and retitle in one edit → both land; remove the only date
   in the vault → warning, base held, warning again next sync; an edit made between the
   seeding sync and this PR's first sync → applied. Mutants: the branch ignores `base` (the
   race rows flip); the refresh runs on a refused write (the edit is never retried); any
   field applied without `theirs ≠ base`.
3. **Deletion cancels open tasks** — ✅ #1345. The sweep posts `CANCELLED` for open tasks
   through `update_task` (status only) and clears the stamp only on an ok write; the
   backlog since PR 1 was cancelled on the first sweep and the PR says so (census in its
   body); the counter and its fragment line. Rig: delete an open task's line, two syncs →
   cancelled, nothing written to the vault, the sync after quiet; delete a done line →
   untouched; delete a whole note → its open tasks cancelled two syncs later, its done ones
   untouched; cut/paste across a sync boundary → moved, not cancelled; delete a line, then
   break the note that restores it (bad frontmatter), sync → held with a warning, fix the
   note, sync → revived, not cancelled (open and done variants); a line typed back after
   its cancel → a new task beside it; un-cancel in SKUEL then type it back → reunited; a
   note restored after its tasks were cancelled → new tasks, not a resurrection. Mutants:
   the sweep cancels terminal tasks; the stamp is cleared before the cancel's result is
   known (a refused cancel becomes a permanent divergence); the sweep runs over a failed
   file (the broken note's open task is cancelled); the sweep ignores a live second edge.
4. **Docs.** ADR-070: status annotation retired, Decision 2's `[x]`/`✅` rows and the field
   rows true, `source_line` and the three stamps in Decision 1, a Decision 3 paragraph naming
   the three-way merge; CLAUDE.md § Obsidian VaultBridge and § Unified Content Ingestion; the
   neo4j-cypher-patterns reference's `EXTRACTED_FROM` row; `cleanup_duplicate_vault_tasks.py`
   narrowed to pre-🆔-era repair; this file → `done/`.

Sequencing note: 1 → 2 is fixed (reconciliation needs the seeded base and the stamps);
3 depends only on 1 and may land any time after it; 4 last.

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
  PR 1; edits from then until PR 2 lands are diffs against that base and apply when it does.
- A refused vault edit re-warns on every sync until the line and the task agree — standing
  visibility, the same contract as ignored files.
- A sync with any failed file holds every pending cancel until a clean sync — deletion
  waits on the vault being readable, which is the honest order.

**Named cost while open:** after PR 3 every product rule is built; what remains is PR 4 —
the docs still describe the pre-R4 truth (ADR-070's status annotation, CLAUDE.md § Obsidian
VaultBridge / § Unified Content Ingestion), and `cleanup_duplicate_vault_tasks.py` still
offers repairs the arc has made unnecessary.
