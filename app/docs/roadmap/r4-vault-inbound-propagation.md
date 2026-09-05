---
title: "R4 Vault Inbound Propagation — Parked Build"
updated: 2026-09-05
status: "parked"
registered: 2026-08-24
ruled: 2026-08-23
trigger: "Mike schedules it — product decision, not a data threshold"
check: "the design sketch in the case file; the change signal is parsed-line vs entity STATE, never a hash inequality"
---

# R4 Vault Inbound Propagation — Parked Build

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

**Never-wired verdict, then a parking ruling.** The `git log --all -S` discriminator ran with
multiple probes: the reconciler's inbound half has been `ingest_directory`-only since its first
commit (`b7a1bb3fe`); the only deleted artifact (`find_line_by_vault_id`) was same-day
scaffolding; the CLAUDE.md "completions propagate back" claim landed two days AFTER the
outbound-only code (`5cb1eec12`). The prose was vision, not history. Mike ruled (2026-08-23,
cascade-residue disposition): make the docs honest now — done 2026-08-24 (CLAUDE.md § Obsidian
VaultBridge, ADR-070 status annotation, both user guides) — and park the build here.

**Design sketch, for the day it is scheduled:**

- The `vault_id → entity` lookup the build needs already EXISTS: Guard 2b (#1143) builds
  `existing_vault_ids` per entry in `UserEntryProcessingService` from the same `EXTRACTED_FROM`
  provenance read that feeds Guards 2/3 (`ExtractedByVaultId` in
  `core/services/dsl/activity_extractor.py` carries `entity_uid` + the stored line hash).
- The build is a **status-reconciliation branch beside the extraction guards**: when a 🆔
  line is skipped as already-extracted, compare the PARSED LINE against the ENTITY'S STATE and
  reconcile — covering check (`[x]` + `✅` → complete the task), uncheck (`[ ]` → reopen), and
  edits (title/date changes). ADR-070 Decision 3's LWW-on-`✅` policy is the written conflict
  rule; it has never had a mechanism.
- ⭐ **The change signal must be parsed-line vs entity STATE, never a hash inequality.** The
  hash cannot say WHAT changed — and Guard 2b deliberately REFRESHES the edge hash on every
  moved 🆔 line, so hash inequality is transient by design. This was Codex round-5 P1 on
  #1143, rejected as exactly this parked feature
  (<https://github.com/linguistic76/skuel/pull/1143#issuecomment-5390505718>); the refresh
  forecloses nothing.
- The two historical guard-miss shapes the branch must not regress: Guard 2 misses when the
  hash moved (that miss becomes the reconciliation trigger), and Guard 4 filters to ACTIVE
  twins by design, so it can never catch a completed task.

**Trigger:** Mike schedules it — product decision, not a data threshold.
**Named cost while parked:** vault-side checks, unchecks, and edits of 🆔 lines silently do
not propagate — an edited 🆔 line is skipped + rehashed (#1143's deliberate behaviour: no
duplicate, no update). Tracked tasks must be completed and edited in SKUEL.
