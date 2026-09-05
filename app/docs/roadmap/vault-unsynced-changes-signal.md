---
title: "\"Vault Has Un-Synced Changes\" Signal"
updated: 2026-09-05
status: "parked"
registered: 2026-08-24
trigger: "Mike schedules it — a product decision about what the user is told"
check: "no last-sync state is persisted today; the signal must cover completions, 🆔 injections and new tasks, not reopens alone"
---

# "Vault Has Un-Synced Changes" Signal

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

The honest version of the dirty flag the reopen arc once proposed. A reopen now reaches the vault
on the next sync, but *the user is not told a sync is worth running*. The naive fix — light a flag
when a task is reopened — **tells a half-truth**: a completion, a minted 🆔 and a newly-extracted
task all leave the vault equally out of date, and a flag lit only by reopens would advertise the
rarest of the four while staying dark for the common ones. Whatever is built must cover all of
them, or it is worse than nothing.

**What exists to build on:**

- **No last-sync state is persisted anywhere today.** `/submissions/sync` is stateless on load
  (`adapters/inbound/vault_routes.py`) — the page cannot say "last synced 3 days ago" because
  nothing records it. That is the first thing any signal needs, and it does not exist yet.
- `UserPreferences.vault_write_consent` (`core/models/user/user.py`) is the **shape precedent**
  for a durable per-user vault flag.
- `:Notification` nodes (`core/services/notifications/notification_service.py`) are the existing
  durable per-user channel, already driven by four subscribers in
  `services_bootstrap/_event_wiring.py` — the one place a "your vault is behind" signal could live
  without inventing a mechanism.

**⚠️ The trap this replaces:** *"`TaskReopened` requests a sync"* was under-specified, and
investigating "what does the subscriber concretely DO?" is what dissolved it. Do not build a
signal without naming its verb and its actor first.

**Trigger:** Mike schedules it — a product decision about what the user should be told, not a
data threshold.
**Named cost until built:** the vault silently drifts from the graph between human-initiated
syncs, and nothing on any surface says so.
