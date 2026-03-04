# Deferred Work

**Context**: Items here are real, valuable improvements that are intentionally on hold. They are
not rejected — they are waiting for usage data, business decisions, or production prerequisites
that do not yet exist. Each item has an explicit trigger condition.

**Related**: `/docs/roadmap/security-hardening-deferred.md` — 5 deferred security items
(dependency pinning, rate limiting, secret scanning, session rotation, CI CVE scanning).

---

## Shelved Intelligence Features

The following three features have dedicated design documents in `/docs/intelligence/`. They are
not premature ideas — they are fully designed but correctly deferred until enough data exists
to make them meaningful.

**See**: `/docs/intelligence/INTELLIGENCE_ROADMAP.md` — master overview of the intelligence layer.

---

### 1. Semantic Analysis

**Why deferred**: Semantic analysis computes cross-KU similarity, concept clustering, and
prerequisite inference from content. With fewer than 50 KUs, the signal-to-noise ratio is too
low to produce useful clusters — the algorithm would find spurious patterns in thin data.

**The problem**: Users cannot currently discover related KUs they haven't explicitly linked.
Semantic similarity would surface "you studied X — here's Y which uses the same core concept"
recommendations, and would feed Askesis's gap-detection logic.

**What to do**:

1. Verify KU count: `MATCH (k:Curriculum) RETURN count(k)` — proceed when ≥ 50 with rich `content` fields.
2. Enable the `SemanticAnalysisService` in `services_bootstrap.py` (currently stubbed out).
3. Run the embedding pipeline against existing KUs: `POST /api/ingest/domain/ku` triggers
   embedding generation for all KUs missing embeddings.
4. Wire `SearchRouter.semantic_search()` to the `/search` UI — it already accepts vector queries
   but the UI toggle is disabled.
5. See `/docs/intelligence/SEMANTIC_ANALYSIS_ROADMAP.md` for full implementation steps.

**Enable when**: KU count ≥ 50, majority with non-empty `content` fields.

---

### 2. Discovery Analytics

**Why deferred**: Discovery analytics learns from search behavior — what users search for,
what they click, what they ignore. With fewer than 1,000 logged search queries, the behavioral
signal is too sparse to distinguish signal from noise.

**The problem**: SKUEL's search is currently keyword + embedding similarity. It does not learn
from usage. If 80% of users search "meditation" and click the same three KUs, those KUs should
rank higher. Discovery analytics closes this loop.

**What to do**:

1. Verify search query log count: `MATCH (e:SearchEvent) RETURN count(e)` — proceed when ≥ 1,000.
2. Enable search event logging in `SearchRouter` (event publishing is wired but disabled behind
   `INTELLIGENCE_TIER=full` and a feature flag).
3. Implement click-through rate weighting in `SearchRankingService` using logged events.
4. See `/docs/intelligence/DISCOVERY_ANALYTICS_ROADMAP.md` for full implementation steps.

**Enable when**: 1,000+ search queries logged in Neo4j.

---

### 3. Real-time Intelligence

**Why deferred**: Real-time intelligence (live activity feeds, push-based recommendations,
session-aware context updates) requires concurrent users to be meaningful. With a single
developer testing the system, "real-time" is indistinguishable from "refresh the page."

**The problem**: `UserContextIntelligence.get_ready_to_work_on_today()` currently rebuilds
context on every request. For 10+ daily active users, incremental updates (only recompute what
changed) would meaningfully reduce Neo4j load. Real-time also enables "your colleague just
completed the same KU" social signals.

**What to do**:

1. Verify daily active users: instrument `skuel_daily_active_users` Prometheus gauge — proceed
   when consistently ≥ 10.
2. Add WebSocket session tracking to `SessionBackend` (groundwork exists in `core/auth/`).
3. Replace full `build_rich()` calls with incremental delta queries for unchanged domains.
4. See `/docs/intelligence/REALTIME_INTELLIGENCE_ROADMAP.md` for full implementation steps.

**Enable when**: 10+ daily active users sustained over 2+ weeks.

---

## Decision Points

These items are blocked on business decisions, not engineering complexity. The code stubs exist;
they need a decision to wire up.

---

### 4. Per-user Intelligence Tier

**Why deferred**: The system-wide `INTELLIGENCE_TIER` env var toggle (CORE vs FULL) works
correctly. Per-user tier control requires a billing model — specifically, which features are
free vs paid — and that model has not been defined.

**The problem**: `core/services/intelligence_tier_service.py` implements `get_user_intelligence_tier(user_uid)`
and returns per-user tier based on role. It is not wired to route middleware. Currently all users
get the same tier controlled by the env var.

**What to do**:

1. Define the billing model: which `UserRole` levels get FULL tier? (e.g., MEMBER and above?)
2. In `services_bootstrap.py`, wire `intelligence_tier_service` into the route dependency chain.
3. Replace the env-var gating in the three bootstrap gating points with
   `await intelligence_tier_service.get_user_intelligence_tier(user_uid)`.
4. Update route middleware to pass `user_uid` to the tier check (requires auth context at
   service-selection time, not just inside route handlers).

**Enable when**: Billing model defined — specifically, which subscription tier gets AI features.

---

### 5. KnowledgeConfig Validation

**Why deferred**: `config/validation.py` has a `validate_knowledge_config()` function that
returns an empty list (stub). The fields it would validate — `embedding_model` and
`embedding_dimension` — do not yet exist on `KnowledgeConfig`. This is a 30-minute task once
those fields are added.

**The problem**: If someone deploys SKUEL with a mismatched `embedding_model` / `embedding_dimension`
pair (e.g., `text-embedding-3-large` with dimension 1536 instead of 3072), Neo4j vector index
operations will silently produce incorrect similarity scores. The validation stub exists but
does not catch this.

**What to do**:

1. Add `embedding_model: str` and `embedding_dimension: int` to `KnowledgeConfig` in
   `core/config/unified_config.py`.
2. In `config/validation.py`, implement `validate_knowledge_config()`:
   ```python
   VALID_EMBEDDING_DIMENSIONS = {
       "text-embedding-3-small": [512, 1536],
       "text-embedding-3-large": [256, 1024, 3072],
       "text-embedding-ada-002": [1536],
   }
   if config.embedding_model in VALID_EMBEDDING_DIMENSIONS:
       if config.embedding_dimension not in VALID_EMBEDDING_DIMENSIONS[config.embedding_model]:
           errors.append(f"embedding_dimension {config.embedding_dimension} invalid for {config.embedding_model}")
   ```
3. Add a test in `tests/unit/test_config_validation.py`.

**Enable when**: `embedding_model` and `embedding_dimension` fields are added to `KnowledgeConfig`.

---

## Review Schedule

Review this document at the **June 2026 quarterly review**. Checklist:

| Item | Trigger | Check |
|------|---------|-------|
| Semantic Analysis | KU count ≥ 50 | `MATCH (k:Curriculum) RETURN count(k)` |
| Discovery Analytics | Search queries ≥ 1,000 | `MATCH (e:SearchEvent) RETURN count(e)` |
| Real-time Intelligence | DAU ≥ 10 for 2+ weeks | Grafana `skuel_daily_active_users` |
| Per-user intelligence tier | Billing model defined | Business decision |
| KnowledgeConfig validation | Config fields added | `grep embedding_model core/config/unified_config.py` |

Items that hit their trigger condition before June should be unblocked immediately — don't wait
for the review.
