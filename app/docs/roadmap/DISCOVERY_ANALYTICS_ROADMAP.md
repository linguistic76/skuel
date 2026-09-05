---
title: Discovery Analytics Roadmap
updated: 2026-09-05
status: current
category: intelligence
tags: [analytics, discovery, intelligence, roadmap, search]
related: []
---

# Discovery Analytics Roadmap

**Status:** Phase 1 (search-event logging) SHIPPED 2026-07-10. Phases 2+ deferred
until 1,000+ logged events.

Discovery analytics closes the search-behavior loop: what users search for, what
they can't find (content gaps → feeds content authoring), and eventually how
usage should influence ranking.

---

## Phase 1 — Search-Event Logging + Content-Gap Surface ✅ SHIPPED

Every external search is recorded as a `:SearchEvent` node. This is the data
foundation for every later phase — and the zero/low-result aggregation is
useful immediately (it tells the content author what people looked for and
didn't find).

### Flow

```
SearchRouter (faceted_search / intelligent_search / advanced_search)
    → publishes SearchExecuted ("search.executed", core/events/search_events.py)
    → InMemoryEventBus (in-process subscriber — not a background worker)
    → SearchEventRecorder (core/services/search_event_recorder.py)
    → SearchEventBackend (adapters/persistence/neo4j/search_event_backend.py)
    → (:SearchEvent) node
```

- **One event per external search.** `intelligent_search` fans out through
  per-domain `faceted_search` calls internally — those pass `log_event=False`
  and never publish.
- **Empty/filter-only queries are never logged** — no query text means no gap
  signal (`/search/results` short-circuits empty queries anyway).
- **Fail-soft, twice over:** the router's publish helper never raises, and the
  event bus isolates handler errors — a logging failure cannot break or fail a
  search.
- **Tier-independent** (ADR-043 untouched): a plain graph write with no AI
  dependency, active on both CORE and FULL.

### `:SearchEvent` node

A plain infrastructure node (`:ContentChunk`/`:AuthEvent` precedent), NOT one
of the 25 EntityTypes. `NeoLabel.SEARCH_EVENT`.

| Property | Type | Notes |
|----------|------|-------|
| `uid` | string | uuid4 |
| `query_text` | string | as typed |
| `query_normalized` | string | `lower().strip()` — the gap grouping key |
| `user_uid` | string/null | who searched |
| `entry_point` | string | `faceted` \| `intelligent` \| `advanced` |
| `domains` | list[string] | requested scope; empty = cross-domain sweep |
| `filters_json` | string | `json.dumps` of active property filters |
| `result_count` | int | total results returned |
| `zero_results` | boolean | `result_count == 0` |
| `semantic_boost` | boolean | body-chunk layer enabled (faceted only) |
| `created_at` | datetime | native Neo4j datetime (writer passes isoformat) |

Indexes: `search_event_query_idx` (`query_normalized`) and
`search_event_created_idx` (`created_at`) — created by
`Neo4jSchemaManager.sync_domain_indexes()` on startup.

**Privacy stance:** query text is user-typed search *behavior*, stored with
`user_uid`. It is never journal content — ADR-073 (journals store zero) is
untouched. ~~TODO before multi-user launch: define a retention/purge policy for
search events.~~ ✅ Done (ADR-080 H0): `TelemetryRetention.SEARCH_EVENT_DAYS = 90`,
pruned by `telemetry_retention_backend.py` via `./dev telemetry-retention`.

### Content-gap read side

`SearchEventBackend.get_search_gaps(max_result_count=2, days=90)` aggregates
low/zero-result searches by normalized query (counts, zero-counts, avg results,
last seen, entry points). `count_search_events()` reports the running total
against the Phase 2 trigger. The admin surface is live: the
`/admin/analytics` "Search Gaps (content authoring queue)" section renders the
gap table plus the running event total vs the Phase-2 trigger.

---

## Phases 2+ — Deferred (trigger: 1,000+ logged events)

Check: `MATCH (e:SearchEvent) RETURN count(e)` — the running total is
surfaced on `/admin/analytics` (Search Gaps section).

⚠️ **Measured 41 on 2026-08-25** — ~8 genuine queries, flat since 2026-07-22 (the census is
in [`domain-fulltext-first-search.md`](domain-fulltext-first-search.md), Ruling 2). At the
observed rate the gate cannot fire; at the next review **re-base the number or retire the
phases** rather than re-checking them.

With few users, behavioral aggregates are noise. These phases subscribe to the
same `search.executed` stream / read the same nodes — no SearchRouter changes
needed:

1. **Query clustering** — group logged queries by intent/embedding similarity
   to reveal demand themes.
2. **Temporal patterns** — when searches happen (hour/day aggregation).
3. **Usage-aware ranking** — weight results by click-through/selection signal.
   Requires (a) a click-tracking property (`clicked_result_uid`) that Phase 1
   deliberately does not collect, and (b) a ranking integration point — note
   there is no `SearchRankingService` today; scoring lives in SearchRouter's
   result scoring path and would need a deliberate design pass.

**Do not build these early.** The analytics are cheap; meaningful data is the
scarce input.
