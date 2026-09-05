---
title: "Vault Re-Sync Never Retracts a Share"
updated: 2026-09-05
status: "open privacy gap (ruled leave registered)"
registered: 2026-09-02
ruled: 2026-09-02
trigger: "the next sharing-fan-out touch, or the first multi-user deployment — whichever comes first"
check: "scripts/retract_defaulted_vault_note_shares.py (dry run) lists what the door left shared"
---

# ⚠️ Vault Re-Sync Never Retracts a Share

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

**Why this section is loud:** it is the one place in the vault door where a user's *narrowing* action does
nothing. Widening `audience:` takes effect on the next sync; narrowing or removing it does not — the share
already written stays. Every other privacy default in this door was corrected on 2026-09-02 (#1228, #1230);
this is the remaining asymmetry, and it is a leak class the moment a second user exists.

`AudienceResolver.resolve_and_share` only adds `SHARED_WITH_GROUP` / `SHARES_WITH` edges, and the
living-entry upsert a vault re-sync lands on carries no share reconciliation. So a note whose
frontmatter drops or narrows its `audience:` keeps every share it already has. The 2026-09-02
flips of the vault-note defaults to private (`knowledge`, then `extract_activities` —
`Pipeline.shares_by_default()`) exposed it: the notes synced under the old `teachers` default
stayed shared until `scripts/retract_defaulted_vault_note_shares.py` retracted them (one-shot,
dry-run default, reads each note's vault frontmatter so an explicit `audience:` is never touched).

**Trigger:** the next sharing-fan-out touch, or the first multi-user deployment (where a stale
share is a leak, not a founder-vault curiosity).
**Named cost:** `audience:` is write-once-widen in practice; narrowing needs the script or a
manual unshare.
