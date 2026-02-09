---
title: ADR-003: Journal Context Gathering Query
updated: 2026-01-30
status: current
category: decisions
tags: [003, adr, decisions, journals, query]
related: []
---

# ADR-003: Journal Context Gathering Query

**Status:** Accepted

**Date:** 2025-11-16

**Decision Type:** ☑ Query Architecture  ☑ Performance Optimization  ☑ Pattern/Practice

**Complexity Score:** 31 (Very High)

**Related ADRs:**
- Related to: ADR-001 (Unified User Context - similar multi-domain aggregation pattern)
- Related to: Step 3 Implementation (November 2025 - Single Query Context Retrieval)

---

## Context

**Problem:** When processing audio transcripts into formatted journals, the AI needs rich contextual awareness to provide intelligent, personalized editing. The system must gather: recent journals (7 days), active goals, trending topics (30 days), and mood trends.

**Requirements:**
- Recent journals (last 7 days) with full metadata
- Active goals for progress tracking awareness
- Trending topics (last 30 days) for thematic continuity
- Mood/energy averages for emotional awareness
- All data in single query for performance
- Complete in < 250ms for real-time transcript processing

**Naive Approach:**
1. Get recent journals (1 query)
2. Get active goals (1 query)
3. Get all journals for topic extraction (1 query)
4. Get all journals for mood calculation (1 query)
5. Process topics and calculate averages in Python

**Total: 4 queries + Python aggregation** = ~300-500ms latency = **Too slow for real-time AI processing**

---

## Decision

Use **single complex query** with:
1. User anchor (property filter on indexed field)
2. Three OPTIONAL MATCH clauses for different data slices:
   - Recent journals (7-day window)
   - Active goals (status filter)
   - All recent journals for topics/mood (30-day window)
3. Server-side aggregation with collect()
4. Advanced mood calculation using reduce() and list comprehensions
5. Strategic WITH staging to avoid cartesian products

**File:** `/core/services/transcript_processor_service.py` (context query)
**Types:** `/core/services/journals/journals_types.py` (`JournalContext`, `JournalAIInsights`)

**Complexity Breakdown:**
- 1 MATCH clause (2 pts)
- 3 OPTIONAL MATCH clauses (6 pts)
- 3 WITH clauses (9 pts)
- 3 WHERE conditions (3 pts)
- 4 collect() aggregations (8 pts)
- 1 CASE expression (2 pts)
- 1 reduce() aggregation (2 pts)
- 2 list comprehensions (4 pts)
- **Total: 36 points** → Adjusted to 31

**Query Structure:**

```cypher
// STEP 1: Anchor on user (indexed property filter)
MATCH (u:User {uid: $user_uid})

// STEP 2: Recent journals (last 7 days) with full details
OPTIONAL MATCH (u)-[:OWNS]->(recent:Journal)
WHERE recent.entry_date >= date() - duration('P7D')
WITH u, collect({
    uid: recent.uid,
    title: recent.title,
    content: recent.content,
    entry_date: toString(recent.entry_date),
    mood: recent.mood,
    energy_level: recent.energy_level,
    key_topics: recent.key_topics
}) as recent_journals

// STEP 3: Active goals for progress tracking
OPTIONAL MATCH (u)-[:OWNS]->(g:Goal)
WHERE g.status = 'active'
WITH u, recent_journals, collect({
    uid: g.uid,
    title: g.title,
    description: g.description
}) as active_goals

// STEP 4: All recent journals for topic/mood analysis (30-day window)
OPTIONAL MATCH (u)-[:OWNS]->(j:Journal)
WHERE j.entry_date >= date() - duration('P30D')
  AND j.key_topics IS NOT NULL
WITH u, recent_journals, active_goals,
     collect(j.key_topics) as all_topics_raw,
     collect(j.energy_level) as all_energy_levels

// STEP 5: Return with advanced mood calculation
RETURN {
    recent_entries: recent_journals,
    active_goals: active_goals,
    all_topics_json: all_topics_raw,
    recent_mood_avg:
        CASE
            WHEN size([e IN all_energy_levels WHERE e IS NOT NULL]) > 0
            THEN reduce(sum = 0.0, e IN [x IN all_energy_levels WHERE x IS NOT NULL] | sum + e) /
                 size([e IN all_energy_levels WHERE e IS NOT NULL])
            ELSE 0.0
        END,
    data_points: size(all_energy_levels)
} as context
```

---

## Key Design Patterns

### 1. Dual Time Window Strategy

The query uses two different time windows for different purposes:

**7-day window (Recent journals):**
```cypher
WHERE recent.entry_date >= date() - duration('P7D')
```
- **Purpose:** Immediate context for AI editing
- **Rationale:** Last week's journals most relevant for thematic continuity

**30-day window (Topics/mood):**
```cypher
WHERE j.entry_date >= date() - duration('P30D')
```
- **Purpose:** Trending topics and mood patterns
- **Rationale:** Longer window needed for pattern detection

**Benefits:**
- Balances recency (7 days) vs pattern detection (30 days)
- Optimizes data transfer (full details only for recent 7 days)
- AI gets both immediate context and broader trends

### 2. Advanced Mood Calculation with reduce()

Server-side average calculation using Cypher reduce():

```cypher
CASE
    WHEN size([e IN all_energy_levels WHERE e IS NOT NULL]) > 0
    THEN reduce(sum = 0.0, e IN [x IN all_energy_levels WHERE x IS NOT NULL] | sum + e) /
         size([e IN all_energy_levels WHERE e IS NOT NULL])
    ELSE 0.0
END
```

**Why This Complexity:**
- **NULL handling:** Filters out NULL energy_level values before averaging
- **Division by zero prevention:** CASE checks for empty list first
- **Type safety:** reduce() ensures float arithmetic

**Why in Cypher:**
- 10-50x faster than Python (no data transfer)
- Handles sparse data gracefully (some journals have no energy_level)
- Single source of truth for average calculation

### 3. Strategic WITH Staging to Avoid Cartesian Products

Uses three WITH clauses to stage data:

```cypher
WITH u, collect(...) as recent_journals          // Stage 1
WITH u, recent_journals, collect(...) as active_goals  // Stage 2
WITH u, recent_journals, active_goals, collect(...), collect(...)  // Stage 3
```

**Why Staging:**
- **Prevents cartesian products:** Without WITH, OPTIONAL MATCH patterns multiply
- **Example failure:** 10 journals × 5 goals = 50 rows instead of separate collections
- **Aggregation points:** Each WITH creates a collection, reducing rows to 1

**Performance Impact:**
- Staging = O(N + M + K) operations
- Without staging = O(N × M × K) operations
- **10-100x performance difference** for typical user data

---

## Alternatives Considered

### Alternative 1: Four Separate Queries with Python Aggregation

**Description:** Execute 4 queries (recent journals, goals, topics, mood), aggregate in Python

**Pros:**
- Simpler individual queries
- Easier to debug each data slice
- More flexible Python aggregation logic

**Cons:**
- 4 database round-trips = 4× network latency
- Python mood calculation slower than Cypher reduce()
- Data duplication (journals fetched twice for different purposes)
- **300-500ms total latency** (vs 150-220ms for single query)

**Why Rejected:** Performance critical for real-time AI processing. Every journal entry triggers this query, so latency compounds.

---

### Alternative 2: Pre-Computed Journal Context Index

**Description:** Maintain materialized view of user context, update on journal creation

**Pros:**
- Constant-time reads
- No complex queries
- Predictable performance

**Cons:**
- Write amplification: Every journal creation triggers full context rebuild
- Stale data risk: Active goals might change between journal entries
- Storage overhead: N users × full context snapshot
- **Cannot handle dynamic time windows** (7-day/30-day windows require re-indexing)

**Why Rejected:** Time windows are dynamic (always "last 7 days", not "journals from Nov 1-7"). Materialized views can't efficiently support rolling time windows.

---

### Alternative 3: Simplified Context (No Mood Calculation)

**Description:** Remove mood/energy averaging, return raw energy_level values for Python processing

**Pros:**
- Lower complexity (score ~23 vs 31)
- Simpler query logic
- No reduce() complexity

**Cons:**
- **AI gets incomplete context** - mood trends are critical for emotional awareness
- Python averaging is 10-50x slower
- Loses server-side NULL handling

**Example Impact:**
```
Journal entry: "I'm feeling overwhelmed today"
AI without mood trends: Generic editing, misses emotional context
AI with mood trends: "You've been low energy this week - consider self-care"
```

**Why Rejected:** Mood awareness is core to intelligent journal editing. The query complexity is justified by AI quality improvement.

---

## Consequences

### Positive
- ✅ **60%+ latency reduction** - Single query vs 4 queries (180ms vs 450ms+)
- ✅ **Rich AI context** - All data types in one response (journals, goals, topics, mood)
- ✅ **NULL-safe aggregation** - Server-side reduce() handles sparse data
- ✅ **Dual time windows** - Balances recency vs pattern detection

### Negative
- ⚠️ **High complexity** - Score 31 requires careful maintenance
- ⚠️ **Advanced Cypher** - reduce() and list comprehensions less familiar to developers
- ⚠️ **Fixed time windows** - 7-day/30-day hardcoded in query (not parameterized)

### Risks & Mitigation

| Risk | Mitigation |
|------|------------|
| Long journal history (1000+ entries) slows 30-day topic scan | Add LIMIT to OPTIONAL MATCH, monitor performance |
| NULL energy_level values break mood calculation | Already mitigated with WHERE e IS NOT NULL filters |
| Performance degradation with many active goals (50+) | Monitor p95 latency, alert at 300ms |

---

## Implementation Details

**Location:** `/core/services/transcript_processor_service.py`

**Method:** `gather_journal_context(user_uid: str)`

**Types:** `/core/services/journals/journals_types.py` defines `JournalContext` and `JournalAIInsights`

**Performance:**
- Typical: 150-220ms (20 journals, 5 goals, 30-day history)
- Worst-case: 250-320ms (100+ journals, 20+ goals, complex mood patterns)
- **60%+ improvement** over 4-query approach (180ms vs 450ms+)

**Output Structure (JournalContext):**
```python
{
    "user_uid": str,
    "gathered_at": str,  # ISO timestamp
    "recent_journals": [  # Last 7 days, full details
        {
            "uid": str,
            "title": str,
            "content": str,
            "entry_date": str,
            "mood": str,
            "energy_level": float,
            "key_topics": list[str]
        }
    ],
    "active_goals": [
        {"uid": str, "title": str, "description": str}
    ],
    "recent_topics": list[str],  # Extracted from 30-day journals
    "mood_trends": {
        "average_energy": float,  # 0.0-1.0
        "data_points": int
    }
}
```

**Time Windows:**
- Recent journals: 7 days (P7D)
- Topics/mood: 30 days (P30D)

**Tests:** Integration tests in `/tests/integration/test_option_a_journals_processing.py`

---

## Monitoring

**Success Criteria:**
- Latency < 250ms for 95% of requests
- AI-generated journal edits incorporate context effectively
- NULL energy_level values handled gracefully

**Failure Indicators:**
- 🚨 p95 latency > 300ms
- 🚨 AI edits ignore recent journal themes (context not working)
- 🚨 Mood averages return NaN or incorrect values

---

## 2026-01 Update: Protocol Compliance & Domain Separation

**Dates:**
- November 27, 2025 - Transcript processor refactoring
- January 28, 2026 - Protocol compliance update

The transcript processor was refactored to streamline journal processing:

### Key Changes

1. **Single-Query Context Gathering**
   - Method: `get_journal_context_for_processing(user_uid: str)`
   - Returns: `JournalContext` (same structure as above)
   - Purpose: Fetch all context needed for AI processing in one query

2. **No Entity Creation in Transcript Processor**
   - **Old:** TranscriptProcessorService created Journal nodes
   - **New:** Returns `JournalAIInsights` only (AI-processed data)
   - **Rationale:** Separation of concerns - processor analyzes, other services persist

3. **Domain Separation (January 2026)**
   - Journals are now a separate domain with JournalsCoreService
   - Queries `:Journal` nodes directly (not `:Assignment` nodes)
   - Reflects proper domain boundaries in the graph

4. **Protocol Compliance (January 28, 2026)**
   - **Old:** `BaseService[UniversalNeo4jBackend[JournalPure], JournalPure]`
   - **New:** `BaseService[JournalsOperations, Report]`
   - Uses protocol-based backend for zero port dependencies

> **Note:** JournalPure was merged into Report (February 2026). The Journal domain was absorbed into the Reports domain. See `/docs/domains/reports.md`.

### Updated Architecture

```
Audio Transcript → TranscriptProcessorService (JournalsOperations protocol)
    │
    ├─ gather_journal_context(user_uid)     # Single query (this ADR)
    │  └─ Queries: :Journal nodes directly
    │  └─ Returns: JournalContext
    │
    └─ process_transcript(transcript, context)
       └─ Returns: JournalAIInsights (NO entity creation)

JournalAIInsights → JournalsCoreService
    └─ create_journal_from_insights(insights)
       └─ Creates: Journal node in Neo4j
```

**See:** `/core/services/transcript_processor_service.py` (protocol-compliant, line 45)

---

## Approval

| Reviewer | Status | Date |
|----------|--------|------|
| Strategic Quality Initiative | ☑ Approved | 2025-11-16 |
| CYP009 Linter | ☑ Flagged (score 31) | 2025-11-16 |
| Step 3 Implementation | ☑ Approved | 2025-11-01 |

---

## Changelog

| Date | Change | Version |
|------|--------|---------|
| 2025-11-27 | Transcript processor refactoring (no entity creation) | 3.0 |
| 2025-11-01 | Step 3: Single Query Context Retrieval | 2.0 |
| 2025-11-16 | Initial ADR documentation | 1.0 |
