---
title: "Vault Re-Sync Never Retracts a Share"
updated: 2026-09-26
status: "done — closed by the Submit & Share arc PR 8 (R9): a vault note is a draft and is never shared, so there is no share for a re-sync to retract"
registered: 2026-09-02
ruled: 2026-09-02
trigger: "the next sharing-fan-out touch, or the first multi-user deployment — whichever comes first"
check: "scripts/migrations/vault_notes_are_drafts_2026_09.py (census) reads 0 share links on living vault notes"
---

# Vault Re-Sync Never Retracts a Share

*Case file for the [deferred-work.md](../deferred-work.md) entry of the same name.*

**Status: ✅ CLOSED — 2026-09-26, by the Submit & Share arc's PR 8
([`submission-sharing-arc.md`](../submission-sharing-arc.md) § PR 8, founder ruling R9).** The gap
closed by never sharing drafts, not by reconciliation: a vault note is one living node, never
submitted and never shared, and its `audience:` applies only to the frozen copy `status: submitted`
files — a fresh node, filed once per authored snapshot. A re-sync writes no link, so it has nothing
to retract; narrowing a note's audience changes what its *next* copy reaches, and a filed copy is
taken back with Stop sharing (`POST /api/user-entries/{uid}/unshare`, PR 6b), which the next sync
never undoes (the vault door compares a fingerprint stamped at filing, never the copy's live links).
The migration `scripts/migrations/vault_notes_are_drafts_2026_09.py` censuses and retracts any link
the old code left on a living note (0 live on 2026-09-24 and at PR 8), and the one-shot retraction
script this file used to cite is deleted.

## What the gap was

`AudienceResolver.resolve_and_share` only added `SHARED_WITH_GROUP` / `SHARES_WITH` edges, and the
living-entry upsert a vault re-sync lands on carried no share reconciliation. So a note whose
frontmatter dropped or narrowed its `audience:` kept every share it already had — `audience:` was
write-once-widen. The 2026-09-02 flips of the vault-note defaults to private (`knowledge`, then
`extract_activities`) exposed it: the notes synced under the old `teachers` default stayed shared
until a one-shot script retracted them (dry-run default; it read each note's vault frontmatter so an
explicit `audience:` was never touched).

The ruling then was *leave registered* until share reconciliation on re-sync was built, calling the
two revoke methods (`UnifiedSharingService.unshare` / `unshare_from_group`) that had no caller.
The arc made both revoke methods live behind the owner's Stop-sharing door (PR 6b) and removed the
reason for reconciliation altogether (PR 8): a draft never carries a share.
