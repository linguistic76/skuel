---
title: "Vault Task Door Publishes No Task Events"
updated: 2026-09-05
status: "registered"
registered: 2026-08-24
trigger: "the R4 build, or the next vault-door touch"
check: "git grep -n \"event_bus\" adapters/persistence/neo4j/bulk_upsert_backend.py — empty until wired"
---

# Vault Task Door Publishes No Task Events

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

The direct `type: task` frontmatter ingestion path persists through
`UnifiedIngestionService` → `BulkUpsertBackend.upsert_with_relationships`
(`adapters/persistence/neo4j/bulk_upsert_backend.py`) — no event bus anywhere in that chain. A
task that arrives completed (or is completed by a later re-ingest of its file) through that door
publishes no `TaskCompleted`, so nothing event-driven runs for it — concretely, the
`ProductivityAnalytics.first/last_completion_at` stamps never move: this is the residual root of
the `last_completion_at` staleness that survives #1142 (which derives the COUNT at read but kept
the stamps stored). Don't overstate the gap: checkbox/DSL **extraction**-created tasks go through
the activity services and DO cascade — only the frontmatter bulk-upsert door is silent.

**Trigger:** the R4 build (its reconciliation branch needs the same event honesty) or the next
vault-door touch.
**Named cost:** completion stamps drift stale for vault-frontmatter-authored completions; any
reader of first/last completion stamps under-reports that door's activity.
