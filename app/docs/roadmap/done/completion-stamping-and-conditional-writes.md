---
title: "Roadmap: completion stamping → cascade idempotency → conditional writes"
updated: 2026-08-26
status: complete
category: roadmap
tags: [roadmap, tasks, goals, habits, events, status, vault, neo4j, done]
---

# Roadmap: Completion Stamping → Cascade Idempotency → Conditional Writes

**Status:** ✅ **COMPLETE — 2026-08-24.** Three chained arcs, opened by a single truth-pass
residue and closed by ADR-087. It was filed as a subsection of the ownership bundle's
`:OWNS` Writers entry because that is where the residue surfaced; it is its own thread and
now has its own record.

**Nothing below remains open.** The contract lives in
[ADR-087](../../decisions/ADR-087-status-guarded-conditional-writes.md) and CLAUDE.md
§ Status-Guarded Writes, which are the authority and stay live. One neighbour is still
parked by ruling: vault **inbound** `[x]` propagation — `deferred-work.md` § R4 Vault
Inbound Propagation.

## The defect that opened it

`get_recent_activities` read `coalesce(completion_date[, achieved_date], updated_at)`
(#1116) — and `updated_at` is a **mutable proxy**. Editing a long-completed task re-dated
its "completion" and bounced it to the top of recent activity. Only the explicit complete
paths stamped anything: **measured 5 of 85 on the live graph.**

## Arc 1 — completion stamping (#1122–#1125, closed 2026-08-22)

Canonical fields per domain (#1122); the shared transition helper wired at all six
`update_<domain>` chokepoints plus `EntityType.valid_statuses()` enforcement (#1123); Goals
reopen alignment (#1124); the read + vault + backfill pass (#1125).

**In one line:** every transition into COMPLETED stamps the domain's canonical field, every
transition out clears it, and nothing downstream reads `updated_at` as a completion.

- **Read** (`cross_domain_backend.get_recent_activities`): the stamp alone — Task
  `completion_date`, Goal `achieved_date`. The legacy Goal `completion_date` leg died with
  it. A completed row carrying no stamp is **excluded, not approximated** — truth over
  coverage: an absent row is honest, a wrong date is not.
- **Vault outbound** (`vault_reconciler`): the Obsidian `✅ date` comes from
  `task.completion_date`, falling back to today only for pre-stamp history. It used to come
  from `updated_at`, which rewrote the user's own file every time a long-done task was edited.
- **History, frozen once:** `scripts/backfill_activity_completion_stamps.py` sets
  `field = updated_at` where a completed node has no stamp. **Applied to the live graph
  2026-08-22** (AuraDB `d2d160c4`, measured first): 85 completed Tasks, 5 already stamped,
  **80 frozen**, 0 unstampable; zero completed Goals/Habits/Events/Choices, so Task was the
  only label with anything to do. Verified post-apply — 85/85 stamped, all `STRING` (writers
  persist ISO strings via `to_neo4j_node`; a native Neo4j DATE would read back fine and
  still be the wrong shape). `migrate_activity_completion_aliases.py` reran to a clean
  no-op: zero legacy `completion_date` rows, as PR-1's rerun already found.
- **`complete_task_with_cascade`** gates its own stamp on the same transition rule
  (surfaced by Codex on #1124). It writes through the *generic* CRUD update, so the
  chokepoint helper never sees it — the stamp had been unconditional, and two live callers
  re-enter behind an ownership check only (`POST /today/tasks/{uid}/complete`,
  `UserContextService.complete_task_with_context`), so a retry re-dated the completion and
  would have propagated into the vault `✅`.

## Arc 2 — cascade idempotency (#1126–#1136, closed 2026-08-23)

**Ruled: the cascade genuinely re-runs**, and the subscribers were made safe to repeat — a
repeat complete stays a real complete, so the repair path is preserved.

Two things the original entry got wrong, kept because the corrections are the useful part:

- **Three of its four listed effects were not real.** "Goal progress bumped again, habit
  reinforced again, knowledge mastery +0.1 again" described `logger.debug("Would …")`
  **stubs** (`_update_goal_progress`, `_reinforce_habit`, `_update_knowledge_mastery`). The
  fourth — "dependent tasks re-triggered" — **was real**: `_trigger_task` wrote
  `{"status": "scheduled"}` through the generic CRUD with no read first, so it could reopen
  an already-completed dependent while leaving its `completion_date` set. Latent only
  because the graph has 0 `TRIGGERS_ON_COMPLETION` edges, and it fired on a **first**
  completion too, not just a repeat. Fixed in #1128. What else actually re-ran: the
  `ProductivityAnalytics` counter, a duplicate `PersistedInsight` (**two** append sites, not
  one), the Prometheus counter, and the duration-calibration EMA.
- **The "offline PWA queue replay" vector does not exist** — `static/service-worker.js` has
  no background-sync and no POST queue. The real vector was three deterministic clicks:
  complete → Undo → complete, because Today's Undo un-hid the card client-side without
  posting anything.

The mechanism is one signal, `TaskCompleted.is_repeat`, with the contract on the event
class: handlers that **recompute** ignore it; handlers that **count or append** skip on a
repeat. #1134 sharpened it — the flag gates what **accumulates** (appends, stamps), never
what **derives**. `core/events/task_events.py` carries the authoritative statement.

Residue PRs, all merged: #1139/#1140 (habit windows bounded at both ends), #1142
(`tasks_completed` derived at read; the reconcile instrument retired — ⛔ never resurrect),
#1143 (the 🆔 is identity at ingest — Guard 2b).

## Arc 3 — ADR-087, the conditional-write primitive (#1145–#1150, closed 2026-08-24)

Codex flagged the underlying read-then-write race five times across the cascade arc (#1127,
#1128, #1131, #1133, #1136) and each rejection was scoped, not dismissive — the window was
the one the completion stamps already carried (#1123), so closing it closed both.

Every status-bearing write in `core/services/` now goes through
`backend.update_with_status_guard`, which takes the node's write-lock **BEFORE** reading the
prior status and hands that prior back; `is_repeat` is exact by construction, and
`completion_transition_patch` (the read-then-write form) is **deleted — there is no second
path.** The five stamping domains plus seven raw status writers migrated. Principles is the
one deliberate exception (target-only legality, prior-independent, so no race) and calls
`validate_status_target` for that check alone.

See ADR-087 § Consequences / § Scope for the contract, and its never-resurrect list.

## Where R4 landed

Vault **inbound** `[x]`-completion propagation was dispositioned alongside this chain
(ruled 2026-08-23, docs corrected 2026-08-24): the `git log -S` discriminator ran, verdict
**never wired**, the docs now state the outbound-only truth (CLAUDE.md § Obsidian
VaultBridge, ADR-070's status annotation, both user guides), and the build is parked with a
trigger and a design sketch — `deferred-work.md` § R4 Vault Inbound Propagation — Parked
Build.
