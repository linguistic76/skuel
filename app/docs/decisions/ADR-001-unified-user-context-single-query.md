---
title: ADR-001: Single Complex Query for Unified User Context
updated: 2026-01-20
status: current
category: decisions
tags: [001, adr, context, decisions, query]
related: []
---

# ADR-001: Single Complex Query for Unified User Context

**Status:** Accepted

**Date:** 2025-11-16

**Decision Type:** ☑ Query Architecture  ⬜ Graph Schema  ☑ Performance Optimization  ⬜ Pattern/Practice

**Complexity Score:** 38 (Very High - flagged by CYP009)

**Related ADRs:**
- Related to: ADR-002 (Graph-Sourced Context Builder Pattern)

---

## Context

**What is the issue we're facing?**

The UserContext requires aggregating data from multiple domains to provide a comprehensive view of user's activities, learning progress, and relationships. This context is used for:
- Profile hub data generation
- Intelligent recommendations
- Cross-domain analytics
- User dashboard rendering

**Requirements:**
- Gather data from 7+ activity domains (Tasks, Events, Habits, Goals, Choices, Principles, Finance)
- Include relationship counts and metadata
- Complete in < 500ms for responsive UX
- Support graphs with 10K+ nodes per active user

**Problem:**
The naive approach requires separate queries per domain:
- 1 query for active tasks
- 1 query for task-goal relationships
- 1 query for task-knowledge relationships
- 1 query for events
- ... (15+ queries total)

**Total latency:** 15 queries × 30-50ms each = 450-750ms + network overhead = **potential timeout**

**Constraints:**
- Must be read-optimized (called frequently)
- Graph traversal patterns are well-defined
- Data consistency less critical (analytics context, not transactional)
- Memory usage must stay reasonable (< 100MB per query)

---

## Decision

**What is the change we're proposing/making?**

We will use a **single complex Cypher query** with multiple MATCH clauses and strategic WITH staging to gather all user context data in one database round-trip.

**Implementation:**
- Start with User node (most selective - single node lookup)
- Use OPTIONAL MATCH for domains user may not have data in
- Stage aggregations with WITH clauses to avoid nested aggregates
- Collect UIDs and counts for each domain
- Return comprehensive context object with all data

**File:** `/core/services/user/graph_sourced_context_builder.py:128`

**Complexity Breakdown:**
- 8 MATCH clauses (16 pts)
- 4 WITH clauses (12 pts)
- 2 WHERE conditions (2 pts)
- 4 aggregations (8 pts)
- **Total: 38 points** (Very High Complexity)

**Query Structure:**
```cypher
MATCH (user:User {uid: $user_uid})

# Active tasks
OPTIONAL MATCH (user)-[:OWNS]->(task:Task)
WHERE task.status = 'active'

# Task-Goal relationships
OPTIONAL MATCH (task)-[:FULFILLS_GOAL]->(goal:Goal)
WITH user, task, collect(DISTINCT goal.uid) as goal_uids

# Task-Knowledge relationships
OPTIONAL MATCH (task)-[:APPLIES_KNOWLEDGE]->(ku:Ku)
WITH user, task, goal_uids, count(DISTINCT ku) as ku_count

# Events and habits (similar patterns)
# ...

WITH user,
     collect(DISTINCT task.uid) as active_task_uids,
     collect(DISTINCT {task_uid: task.uid, goals: goal_uids}) as task_goal_map,
     # ... other collections

RETURN user, active_task_uids, task_goal_map, ...
```

---

## Alternatives Considered

### Alternative 1: Multiple Separate Queries (Naive Approach)
**Description:**
Execute 15-18 separate Cypher queries, one per domain/relationship type. Aggregate results in Python.

**Pros:**
- Simple, straightforward queries (complexity < 10 each)
- Easy to debug individual queries
- Easy to add/remove domains
- Follows "simple over complex" principle

**Cons:**
- 15-18 database round-trips = **high latency** (450-750ms minimum)
- Network overhead multiplied
- Doesn't scale well with number of domains
- Python-side aggregation adds processing time

**Why rejected:**
Latency requirements cannot be met. User experience suffers with > 500ms load times. The complexity of multiple queries outweighs the complexity of a single larger query.

### Alternative 2: Cached Aggregates (Materialized View Pattern)
**Description:**
Pre-compute user context and store in a separate "UserContextCache" node. Update on write operations.

**Pros:**
- Extremely fast reads (single node lookup)
- Predictable performance
- Scales to very large graphs

**Cons:**
- **Write amplification** - every domain write must update cache
- Cache invalidation complexity (staleness issues)
- Consistency challenges (what if cache update fails?)
- Additional storage overhead
- More complex write paths across all services

**Why rejected:**
Adds significant complexity to write operations across 7+ services. Cache invalidation is notoriously difficult. Read performance gain doesn't justify write complexity for this use case. We'd rather accept read complexity than write complexity.

### Alternative 3: GraphQL Federation / Aggregation Service
**Description:**
Create a dedicated aggregation microservice that calls domain-specific services and aggregates results.

**Pros:**
- Separation of concerns
- Each domain service keeps simple queries
- Easier to test individual components

**Cons:**
- **Still requires multiple database queries** (one per service call)
- Adds network latency (service-to-service calls)
- More complex deployment architecture
- Doesn't solve fundamental latency problem

**Why rejected:**
Doesn't address the core issue (multiple database round-trips). Adds architectural complexity without performance benefit.

### Alternative 4: APOC Procedures (Neo4j Stored Procedures)
**Description:**
Write custom Neo4j APOC procedure in Java to perform aggregation server-side.

**Pros:**
- Maximum performance (runs in database JVM)
- Can use Neo4j's internal APIs
- Eliminates network serialization overhead

**Cons:**
- **Requires Java development** (different language from Python codebase)
- Deployment complexity (custom procedures must be installed on Neo4j)
- Harder to test and debug
- Tight coupling to Neo4j version
- Not portable (vendor lock-in)

**Why rejected:**
Development/operational complexity too high. We want to stay within Python ecosystem for maintainability. The 100-200ms performance gain doesn't justify the complexity cost.

---

## Consequences

### Positive Consequences
**What benefits do we gain?**
- ✅ **60% latency reduction** - Single round-trip vs 15-18 queries (measured: 180ms vs 450ms)
- ✅ **Simplified API** - One method call gets all context
- ✅ **Consistent snapshot** - All data from single transaction (no race conditions)
- ✅ **Reduced network overhead** - One serialization/deserialization cycle
- ✅ **Scalable with domains** - Adding new domain = adding OPTIONAL MATCH, not new query

### Negative Consequences
**What costs/trade-offs do we accept?**
- ⚠️ **High query complexity** - Score 38 (requires careful maintenance)
- ⚠️ **Harder to debug** - Multiple stages, large query plan
- ⚠️ **Testing complexity** - Need comprehensive test coverage for all domain combinations
- ⚠️ **Knowledge bus factor** - Requires understanding of Cypher staging patterns
- ⚠️ **Potential memory usage** - Large result sets if user has 10K+ entities

### Neutral Consequences
**What changes but isn't clearly positive/negative?**
- ℹ️ All context logic centralized in one service (graph_sourced_context_builder)
- ℹ️ Query automatically found by static analysis (Cypher linter flagged it)
- ℹ️ Sets precedent for complex queries in other services

### Risks & Mitigation
**What could go wrong and how do we handle it?**

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Query timeout with very large user datasets (100K+ entities) | Low | High | Add query timeout (5s), implement pagination fallback if needed |
| Memory exhaustion on large result sets | Low | Medium | Tested with realistic data (10K nodes), monitor memory usage in production |
| Query plan regression with Neo4j updates | Low | Medium | Pin Neo4j version, test upgrades thoroughly, benchmark before deploying |
| Maintenance difficulty (future developers) | Medium | Medium | Comprehensive documentation (this ADR), code comments, integration tests |
| Performance degradation as graph grows | Medium | High | Monitor query latency metrics, set alert at 300ms, re-evaluate if exceeded |

---

## Implementation Details

### Code Location
**Where is this decision implemented?**
- Primary file: `/core/services/user/graph_sourced_context_builder.py:128-246`
- Related files:
  - `/core/services/user/unified_user_context.py` (context data structure)
  - `/core/services/user/user_service.py` (caller)
- Tests:
  - `/tests/integration/test_unified_user_context.py` (14/14 passing)
  - `/tests/integration/test_graph_sourced_context_builder.py`

### Complexity Analysis
**Breakdown of query complexity:**

```
MATCH clauses: 8 (×2 pts = 16)
WITH clauses: 4 (×3 pts = 12)
WHERE conditions: 2 (×1 pt = 2)
Aggregations: 4 (×2 pts = 8)
Traversal depth: 0 (×1 pt = 0)
Subqueries: 0 (×5 pts = 0)
---
Total Score: 38 points
Threshold: Very High (31-40) - Architecture review required ✓
```

**Justification for high complexity:**
The complexity is intentional and justified by the 60% performance improvement over the naive approach. The query trades off maintainability for performance, which is acceptable for this read-heavy, performance-critical path.

### Performance Characteristics
**Expected performance:**
- Typical latency: 150-200ms (1K nodes)
- Worst-case latency: 300-400ms (10K nodes)
- Memory usage: 20-50MB (typical), 80-100MB (worst case)
- Scalability limits: Tested up to 10K nodes per user

**Benchmark Results (Nov 2025):**
```
Small dataset (100 nodes):  80ms
Medium dataset (1K nodes): 180ms
Large dataset (10K nodes): 350ms
```

### Testing Strategy
**How is this decision validated?**
- ✅ Unit tests: Query extraction and staging logic tested independently
- ✅ Integration tests: 14 tests covering all domain combinations
- ✅ Performance tests: Benchmarked with 100, 1K, 10K node datasets
- ✅ Manual testing: Verified in development with realistic user data

---

## Monitoring & Observability

**How will we know if this decision is working?**

### Metrics to Track
- Query latency (p50, p95, p99)
- Memory usage per query execution
- Query failure rate
- Cache hit/miss ratio (if caching added later)

### Success Criteria
- ✅ Latency < 300ms for 95% of requests
- ✅ Memory usage < 100MB per query
- ✅ Zero nested aggregate errors (validated by Cypher linter)

### Failure Indicators
**Red flags that would trigger revisiting this decision:**
- 🚨 p95 latency exceeds 400ms consistently
- 🚨 Memory usage exceeds 150MB (potential OOM risk)
- 🚨 Query timeouts in production (> 1% of requests)
- 🚨 Maintenance becomes too difficult (multiple bugs per month)

---

## Documentation & Communication

### Related Documentation
- Architecture docs: `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md`
- Code comments: Extensive inline documentation in query builder
- Other ADRs:
  - ADR-002: Graph-Sourced Context Builder Pattern (to be created)

### Team Communication
**How was this decision communicated?**
- ✅ Code review (implementation completed)
- ✅ Architecture review session (this ADR created as part of Week 7-8 implementation)
- ⏳ Team meeting (scheduled for next sprint planning)

### Stakeholders
**Who needs to know about this decision?**
- Impacted teams: Backend team, Frontend team (API consumers)
- Key reviewers: Tech lead, database specialist
- Subject matter experts: Neo4j specialists, performance engineers

---

## Future Considerations

### When to Revisit
**Under what conditions should we reconsider this decision?**
- If graph size per user exceeds 50K nodes (complexity may become unsustainable)
- If query latency consistently exceeds 400ms p95
- If complexity score increases beyond 45 (additional domains added)
- If Neo4j introduces new features that enable better alternatives (e.g., native aggregation views)
- If we implement write-through caching infrastructure (Alternative 2 becomes viable)

### Evolution Path
**How might this decision change over time?**

1. **Short term (Weeks 9-12):** Monitor performance, optimize WITH staging
2. **Medium term (3-6 months):** Consider partial caching for rarely-changing domains
3. **Long term (6-12 months):** If latency becomes issue, evaluate materialized view pattern

### Technical Debt
**What technical debt does this decision create?**
- ⏳ Refactoring needed when complexity exceeds 45 (add pagination or split query)
- ⏳ Documentation updates needed when new domains added (update ADR)
- ⏳ Performance optimization needed when p95 latency > 400ms

---

## Approval

**Reviewer Sign-offs:**

| Reviewer | Role | Status | Date |
|----------|------|--------|------|
| Strategic Quality Initiative | Architecture Review | ☑ Approved | 2025-11-16 |
| CYP009 Linter | Automated Analysis | ☑ Flagged (score 38) | 2025-11-16 |

**Conditions:**
- Monitor latency metrics in production
- Create performance alerts at 300ms threshold
- Re-evaluate if complexity increases beyond 45

---

## Changelog

**Revision History:**

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2025-11-16 | Strategic Quality Initiative | Initial ADR creation | 1.0 |
| 2026-01-20 | Context Integration | Extended MEGA_QUERY with user_properties, life_path, MOCs, progress_counts sections; added 6 new populate methods to close field mapping gaps | 1.1 |

---

## Appendix

### Code Snippet
**Simplified query structure:**

```cypher
MATCH (user:User {uid: $user_uid})

# Active tasks
OPTIONAL MATCH (user)-[:OWNS]->(task:Task)
WHERE task.status = 'active'

# Task-Goal relationships
OPTIONAL MATCH (task)-[:FULFILLS_GOAL]->(goal:Goal)
WITH user, task, collect(DISTINCT goal.uid) as task_goal_uids

# Task-Knowledge relationships
OPTIONAL MATCH (task)-[:APPLIES_KNOWLEDGE]->(ku:Ku)
WITH user, task, task_goal_uids, count(DISTINCT ku) as task_ku_count

# Similar patterns for Events, Habits, Goals, etc.

# Final aggregation
WITH user,
     collect({uid: task.uid, goals: task_goal_uids, ku_count: task_ku_count}) as tasks_data,
     # ... other domain collections

RETURN
  user.uid as user_uid,
  tasks_data,
  # ... other fields
```

### Performance Data
**Benchmark results (Nov 2025):**

```
Environment: Neo4j 5.x, Python 3.11, 16GB RAM

Benchmark 1: Small dataset (100 nodes, 10 active tasks)
  Time: 82ms (avg), 95ms (p95)
  Memory: 18MB

Benchmark 2: Medium dataset (1K nodes, 50 active tasks)
  Time: 185ms (avg), 215ms (p95)
  Memory: 42MB

Benchmark 3: Large dataset (10K nodes, 200 active tasks)
  Time: 348ms (avg), 410ms (p95)
  Memory: 95MB

Comparison to naive approach (18 separate queries):
  Small: 245ms (3x slower)
  Medium: 485ms (2.6x slower)
  Large: 920ms (2.6x slower)
```

### References
**External resources that informed this decision:**
- Neo4j documentation: https://neo4j.com/docs/cypher-manual/current/clauses/with/
- SKUEL Cypher Linter: `/scripts/cypher_linter.py` (flagged this query as CYP009)
- Strategic Quality Initiatives Plan: `/docs/plans/STRATEGIC_QUALITY_INITIATIVES_PLAN.md`
