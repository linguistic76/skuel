# Context Cache Evolution

**Status:** Phase 1 complete (in-memory cache, integrated 2025-12-07)

This document consolidates everything SKUEL knows about the `UserContext` caching layer — what exists today, where the gaps are, and the planned evolution path. Cache knowledge was previously scattered across the implementation file, config stubs, a one-paragraph architecture doc, and a single bullet in `deferred-work.md`.

---

## Why Caching Matters Here

`UserContext` has ~240 fields built from a single MEGA_QUERY (~875 lines of Cypher) that hits every active entity across all 6 activity domains. On a data-rich user this fetches hundreds of nodes and their graph neighborhoods. The query takes ~150-200ms per call.

Without caching, every intelligence request — daily planning, life path alignment, learning recommendations — rebuilds this context from scratch. With caching at ~80% hit rate, the MEGA_QUERY runs once per 5-minute window and the rest serve from memory.

---

## Current Implementation (Phase 1 — Complete)

**File:** `core/services/user/user_context_cache.py`

### What It Does

| Aspect | Detail |
|--------|--------|
| Storage | In-memory `dict[str, UserContext]` per process |
| TTL | 5 minutes (300 seconds) |
| Invalidation | Event-driven — immediate on any domain mutation |
| Owner | `UserActivityService._context_cache` |
| Expected hit rate | ~80% during active sessions |

### Invalidation Events (20+)

The cache is cleared immediately — not on TTL expiry — when any of these domain events fire:

- **Tasks:** `TaskCreated`, `TaskCompleted`, `TaskUpdated`, `TaskDeleted`
- **Goals:** `GoalCreated`, `GoalAchieved`, `GoalMilestoneReached`, `GoalProgressUpdated`
- **Habits:** `HabitCreated`, `HabitCompleted`, `HabitStreakBroken`, `HabitStreakMilestone`
- **Events:** `EventCreated`, `EventCompleted`, `EventUpdated`, `EventDeleted`
- **Choices:** `ChoiceCreated`, `ChoiceUpdated`, `ChoiceDeleted`
- **Principles:** `PrincipleCreated`, `PrincipleUpdated`, `PrincipleDeleted`, `PrincipleStrengthChanged`
- **Finance:** `ExpenseCreated`, `ExpenseUpdated`, `ExpenseDeleted`, `ExpensePaid`
- **Content:** `JournalCreated`, `JournalUpdated`, `JournalDeleted`
- **Curriculum:** `KnowledgeCreated`, `LearningPathStarted`, `LearningPathCompleted`

Event subscriptions wired in `services_bootstrap.py`.

### Request Flow

```
Request → UserService.get_profile_hub_data(user_uid)
               ↓
          UserActivityService.get_valid_context(user_uid)
               ↓
          ┌── HIT  → return cached UserContext (sub-millisecond)
          └── MISS → UserContextBuilder.build_rich(user_uid)
                           ↓
                     MEGA_QUERY (~150-200ms)
                           ↓
                     cache.set(user_uid, context)
                           ↓
                     return UserContext

Domain mutation fires → event published → cache.invalidate(user_uid)
(next request is a MISS and rebuilds fresh)
```

### The Two Build Paths and the Cache

SKUEL has two context build paths:

| Path | Query | Speed | Use case | Cached? |
|------|-------|-------|----------|---------|
| `build()` | CONSOLIDATED_QUERY | ~50-100ms | Ownership checks, lightweight reads | **No** |
| `build_rich()` | MEGA_QUERY | ~150-200ms | Intelligence, daily planning | **Yes** |

`build()` is intentionally uncached: it serves high-frequency, low-data-need operations (ownership verification on every authenticated route). The CONSOLIDATED_QUERY is already fast; the overhead of cache management would not pay off. `build_rich()` is expensive and benefits significantly from caching.

**The longer-term question:** once Phase 2 (Redis) and Phase 4 (warm-up on login) are in place, `build_rich()` cached will be as fast as `build()` uncached — and the argument for maintaining two separate build paths weakens. See Phase 5 below.

---

## Known Gaps

### 1. Config/Implementation TTL Mismatch

`core/config/unified_config.py` defines `user_context_ttl: int = 86400` (24 hours) in `RedisConfig`. This field is **not connected** to the actual cache. The cache uses 300 seconds hardcoded in `UserContextCache.default_ttl`. The config field is a Redis-era placeholder created ahead of the Redis migration but never wired.

**Risk:** Low now. Becomes confusing when Redis is wired — developer expects `user_context_ttl` to control the TTL and gets 86400s instead of 300s.

### 2. Per-Process Cache (No Cross-Worker Consistency)

Each gunicorn worker owns its own `UserContextCache` instance. A user hitting two different workers sees two different cache states. For single-worker deployment this is invisible. For multi-worker or multi-server this means:

- Worker A caches user Alice's context
- Alice completes a task → event fires → Worker A invalidates Alice's cache
- Alice's next request hits Worker B → Worker B still has stale context

**Risk:** Acceptable for current single-server deployment. Becomes a real correctness issue at multi-worker scale.

### 3. Monitoring Not Surfaced

`UserContextCache.get_cache_stats()` returns `{cache_size, valid_count, expired_count}` but is not wired to Prometheus. There is no Grafana dashboard panel for cache hit rate.

### 4. No Warm-Up on Login

Context is built lazily on first intelligence request. The first daily plan of each session always pays the MEGA_QUERY cost. A warm-up at login would eliminate this cold-start miss.

---

## Future Evolution

### Phase 2 — Redis Migration

**Trigger:** Multi-worker deployment or multi-server deployment

**What changes:**
- Replace `dict[str, UserContext]` with Redis-backed store
- Use Redis pub/sub for cross-process invalidation: when Worker A invalidates Alice's cache, all workers are notified
- Wire `RedisConfig` from `unified_config.py` — the `redis_host`, `redis_port`, `redis_password`, and `redis_url` properties already exist
- Reconcile the TTL: either wire `user_context_ttl` from config (and change its value from 86400 to 300), or remove it as a dead field

**Key file:** `core/config/unified_config.py` — `RedisConfig` class

---

### Phase 3 — Incremental Delta Queries

**Trigger:** 10+ daily active users (see `deferred-work.md` item 3)

**Problem with full invalidation:** Today, `TaskCompleted` invalidates the entire UserContext entry. The next request rebuilds all ~240 fields including goals, habits, knowledge mastery, principles — even though none of that changed. For users who complete tasks frequently, this means near-continuous MEGA_QUERY execution.

**What changes:**
- Partition cache by domain: `{user_uid}:tasks`, `{user_uid}:goals`, `{user_uid}:habits`, etc.
- Event-to-partition mapping: `TaskCompleted` only invalidates `:tasks` partition
- `build_rich()` merges valid partitions with freshly-queried stale ones
- Eliminates whole-context rebuild for single-domain mutations

**Complexity:** High. Requires per-domain query decomposition and a merge layer. Only justified at scale.

---

### Phase 4 — Cache Warm-Up on Login

**Trigger:** Phase 2 (Redis) in place

**What changes:**
- On user login (session creation), trigger `build_rich()` proactively and cache result
- First intelligence request of the day serves from cache instead of paying MEGA_QUERY cost
- Removes the "cold start" miss that currently affects every morning session

**Where to wire:** `core/auth/` session creation path (groundwork exists per `deferred-work.md`).

---

### Phase 5 — Collapse to Single Build Path

**Trigger:** Phase 2 + Phase 4 in place

**The argument:**
- `build()` is fast because CONSOLIDATED_QUERY is lightweight
- `build_rich()` cached is fast because it serves from memory
- With warm-up on login, even the first `build_rich()` of a session is a cache hit
- At that point, `build()` exists only to avoid paying MEGA_QUERY on cache miss — which is now rare

**What changes:**
- Deprecate `build()` and `CONSOLIDATED_QUERY`
- All context builds go through `build_rich()` → cache
- Eliminates the two-path mental model and the `is_rich_context` guard pattern

**Caution:** Do not collapse until Phase 4 is working. Without warm-up, cold-start misses would pay MEGA_QUERY cost on ownership checks, which is the wrong trade-off.

---

## Summary Table

| Phase | What | Trigger | Status |
|-------|------|---------|--------|
| 1 | In-memory TTL + event-driven invalidation | — | ✅ Complete |
| 2 | Redis migration for cross-worker consistency | Multi-worker deployment | Deferred |
| 3 | Incremental delta queries (per-domain partitioning) | 10+ DAU | Deferred |
| 4 | Cache warm-up on login | After Phase 2 | Deferred |
| 5 | Collapse `build()` → `build_rich()` everywhere | After Phase 4 | Deferred |

---

## Key Files

| File | Purpose |
|------|---------|
| `core/services/user/user_context_cache.py` | Cache implementation + policy documentation |
| `core/services/user_service.py` (~line 545) | Cache integration in UserService |
| `services_bootstrap.py` | Event subscription wiring |
| `core/config/unified_config.py` (`RedisConfig`) | Future Redis config (TTL mismatch: 86400s) |
| `docs/roadmap/deferred-work.md` (item 3) | Incremental delta query context |
