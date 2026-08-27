---
title: "Roadmap: the reopen vault surface"
updated: 2026-08-26
status: complete
category: roadmap
tags: [roadmap, vault, obsidian, tasks, events, done]
---

# Roadmap: The Reopen Vault Surface

**Status:** ✅ **COMPLETE — 2026-08-24**, two PRs (#1151, #1152). The arc that gave a task
reopen a vault surface, and closed the write-outcome fragility that the third write
operation would otherwise have inherited.

**Nothing below remains open.** Two neighbours stay live in `deferred-work.md` and are
*not* part of this record: § "Vault Has Un-Synced Changes" Signal (the honest version of
the dirty flag this arc once proposed) and § R4 Vault Inbound Propagation — Parked Build.

⚠️ **Both headings below are cited by name from code** — `core/ports/vault_bridge_protocol.py`,
`core/services/vault/vault_reconciler.py`, and three test modules point at
`§ Phantom-🆔`; `docs/domains/tasks.md` points at the `TaskReopened` heading. The headings are
kept verbatim from the retired `deferred-work.md` sections so those citations resolve. **Do
not rename them** — and note the cross-reference validator does not read code comments, so a
rename fails silently.

## Phantom-🆔 on a No-Op Injection — ✅ RESOLVED (reopen-vault-surface arc PR-1, 2026-08-24)

`VaultReconciler._process_entry_outbound` minted a `vault_id`, queued the line injection, and
after a **file-level** successful `write_task_updates` persisted EVERY minted pair via
`update_extracted_vault_id`. `WriteResult` carried only `success`/`new_sha256` —
`apply_task_updates` computed a per-update `changed` and discarded it into a file-level OR — so
file-level success was TAKEN AS proof that every queued injection landed, with nothing enforcing
it. No production trigger was ever known (corrected by the Codex review on #1144: both windows
once thought live are closed by the queue-time hash lookup and the whole-file SHA guard); the
registration was the structural fragility, and the arc that adds a third write operation
(`mark_undone`) is exactly the touch that would have inherited it.

Closed by the arc's PR-1: `apply_task_updates` **returns** its per-update outcomes instead of
OR-ing them away, `WriteResult.updates_applied` carries them positionally parallel to the batch
across BOTH transports and the `skuel-vault-agent`, and the reconciler persists each minted 🆔
only when THAT injection reports applied. `WriteResult.was_applied` reads fail-CLOSED — an
unreported outcome is "did not land" — and only a real JSON boolean counts as a confirmation
(`bool("false")` is `True`, so coercing the wire would have forged exactly the confirmation this
removes). A withheld persist leaves a warning on the sync rather than "complete".
`stats.ids_injected` moved with it: it counts injections that reached the file, not injections
that were queued.

**Withholding is recoverable only because the recovery arm now runs — guarded.** The arm that
adopts a 🆔 the file already carries (its stated purpose: heal a partial-write failure) sat
behind `if not updates: return`, so in its own defining case — the healing pass has nothing to
write — it never ran, and the divergence was permanent. That early return is now conditioned on
there being neither writes nor pending adoptions, and such a pass still goes through the write
door with an **empty batch**: both transports answer an empty batch with the SHA-256 stale-read
guard and no file mutation, so the adopted id is re-validated against the snapshot it was read
from instead of being persisted blind. Both pre-existing, found by the Codex review on the PR
that made them matter.

**Hash lookups are injective across an entry.** Two identical task lines in one note share a
`source_line_hash` (the digest is content-based and 🆔-blind by design), and `_find_line_by_hash`
returned the first match, so both of their entities got the SAME line: a recovery copied the
first line's 🆔 onto the second entity's edge, and that task's completion write-back would then
check the wrong line. A line whose 🆔 an edge in the entry already owns is now excluded before
the loop, and every line a lookup takes is excluded afterwards. Also pre-existing — reachable
before only through a mixed batch, and reachable on any recovery once the arm above started
running.

**Stated limitation, not a defect:** for byte-identical lines, WHICH of them an entity adopts is
arbitrary. No edge→line mapping is recorded and none exists to recover — the digest is
position-free and 🆔-blind by design, so two identical lines carry the same text and the same
state, and the choice is unobservable. A line that diverges from its twin also diverges in the
digest (the ✅ date is deliberately inside it) and stops matching, which is the discriminator
the design does have. What was fixed is the part that IS in the reconciler's control: the
backend read carries no `ORDER BY`, so the pass now sorts its rows and the outcome is at least
reproducible. Do not "fix" this further with a positional discriminator — line positions move
under exactly the edits the content-hash design exists to tolerate.

Wire-protocol change, so `PROTOCOL_VERSION` went **1 → 2** on both sides in one commit (parity
contract-tested in `tests/unit/test_vault_agent.py`; RED-checked by a one-sided bump). No agent
release was cut for it — PR-2 bumps to v3 and ONE release follows, so users pull once.

**Residue SETTLED in PR-2 (2026-08-24) — the whole outbound stat trio now counts what LANDED.**
`stats.tasks_marked_done` was counted at QUEUE time, so a repeat sync of an unchanged vault
reported every completed 🆔-bearing task as "marked done" again. When `tasks_marked_undone`
landed beside it the pair was settled together, in the direction `ids_injected` had already
moved in this section: each counter is gated on its own `WriteResult.updates_applied` slot.
"N tasks marked done in vault" now means "N lines this sync actually changed", and a repeat sync
of an unchanged vault reports zeros — which is the truth.

Fail-closed follows from `was_applied`: a transport reporting no outcomes under-counts rather
than guessing. That costs a display number and never durable state, which is why the same
fail-closed read that WITHHOLDS a 🆔 persist may simply under-report here. ⚠️ Fixtures that
mocked a bridge returning a bare `WriteResult(success=True)` were modelling a transport no real
adapter is — they now report outcomes (`tests/unit/services/vault/test_reconciler_done_date.py`).

⚠️ **Only the un-check warns on a `False` outcome.** A `mark_done` no-op is ORDINARY — `[x] ✅`
is the steady state of every completed task. A `mark_undone` no-op is not: its arm is gated on
running the mutation against the very snapshot the write is guarded by (`needs_mark_undone`), so
a successful write that changed nothing means the file moved underneath the batch.


## `TaskReopened` Has Zero Subscribers, and a Reopen Has No Vault Surface (RESOLVED 2026-08-24)

Two halves of one question — *what should a reopen actually do?* — carried unresolved through
three arcs (completion-stamping, cascade-idempotency, conditional-write). Mike ruled it
2026-08-24; **Half B by the build, Half A by ruling.** Kept as the case file because the ruling
is the interesting part, and because a future bloat sweep will meet `TaskReopened` again.

**Half B — RESOLVED BY BUILD.** A reopen now un-checks its Obsidian line and strips the `✅`
date (`apply_mark_undone`, `TaskLineUpdate.mark_undone`, the outbound `else` arm), byte-exact
reverse of the completion write. ADR-070's deliberate outbound-undone deferral was **amended,
not silently overridden** — three sites (field-authority row, the three-write-operations list,
Resolved Design Question 2 + a changelog row). Wire-protocol change: `PROTOCOL_VERSION` 2 → 3
on both sides in one commit.

**Half A — RESOLVED BY RULING: the event stays published and gets NO subscriber.**

⭐ **Why STATE is the authority, not the event.** `is_reopen` is only knowable *after*
`update_with_status_guard` returns the prior (ADR-087), so the graph write has already committed
before any consumer could run. A failed vault write has **no retry**: re-issuing the request
writes nothing, because the prior is now non-completed and it is no longer a transition. **A
reopen transition is a one-shot fact, consumed by the write that produced it.** So the vault
write is driven by a predicate — "this task is not completed AND its line is still marked done"
— which is re-evaluable at any time and idempotent. See
`feedback_one_shot_transition_needs_state_not_event`.

⭐ **And once state is the authority, the event has no verb left.** The outbound pass already
evaluates that predicate on every sync, so the un-check lands with zero event involvement. What
a subscriber would add is *only* lower latency — and **there is no latency asymmetry to correct**:
a task COMPLETION also only reaches the vault on the next human-initiated sync (`VaultReconciler.sync`
has exactly two callers — `vault_routes.py` and `scripts/vault_bridge_sync.py`). A subscriber
would make a reopen's vault write *more eager than the completion it reverses*, and add a second
live path to "the vault line matches the task's state" — the shape ADR-070 Decision 9 Ruling 1
rejects.

**Three premises that were investigated and FALSIFIED — do not re-derive them:**

- ❌ *"CORE tier runs no background workers."* The guarantee is **AI-scoped**.
  `GRACEFUL_DEGRADATION_ARCHITECTURE.md` says *"No **AI** background workers spin up"* and then
  documents one that does: the hourly `ProgressReportWorker` (graph analytics only) IS a CORE-tier
  Analog worker. ADR-043 makes no no-workers claim, and the bus plus all ~45 subscriptions in
  `services_bootstrap/_event_wiring.py` are wired unconditionally in CORE.
- ❌ *"A subscriber is a background write in all but name."* `publish_event` awaits
  `InMemoryEventBus.publish_async`, which awaits handlers through `asyncio.gather`. A subscriber
  is exactly as synchronous with the request as an inline call.
- ❌ *"A filesystem write from a subscriber would be unprecedented."*
  `AnalyticsService.handle_goal_achieved` → `_save_report` → `filepath.write_text(...)`.

**⚠️ `./dev bloat` reporting `i TaskReopened` (published, never subscribed) is the RULED END
STATE**, not a regression — INFO is not a `--check` failure. And `PLANNED_EVENTS` is **NOT** the
way to silence it: `analyze_events` branches on `publish_live` first, so a published class listed
there earns a SECOND INFO (`planned-marking-stale`) and the PLANNED tier below is never reached.
The ⚠ marker on the event's own docstring carries the decision, and it is what a sweep meets first.

⭐ **The transferable lesson:** an event-shaped *"prompt"* still needs a recipient that can act on
it. When the only actor able to act is the human, the event has no verb — and "what exactly does
the subscriber do?" is not a detail to fill in later, it is the design failing out loud.

**Still open, and separately registered** — both live in `deferred-work.md`, not here: the
want behind "mark the owner's vault dirty" is real but bigger than a reopen (§ "Vault Has
Un-Synced Changes" Signal), and inbound propagation — a vault-side check/uncheck reaching
SKUEL — stays parked (§ R4 Vault Inbound Propagation — Parked Build).

