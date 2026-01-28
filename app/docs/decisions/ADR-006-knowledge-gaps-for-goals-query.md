---
title: ADR-006: Knowledge Gaps for Goals Query Architecture
updated: 2025-11-27
status: current
category: decisions
tags: [006, adr, decisions, gaps, goals]
related: []
---

# ADR-006: Knowledge Gaps for Goals Query Architecture

**Status:** Accepted

**Date:** 2025-11-16

**Decision Type:** ☑ Query Architecture  ☑ Performance Optimization  ☑ Pattern/Practice

**Complexity Score:** 35 (Very High)

**Related ADRs:**
- Related to: ADR-005 (Ready-to-Learn Query - similar prerequisite checking)
- Related to: Goal-driven learning philosophy

---

## Context

**Problem:** Users need to identify which knowledge to learn next to unblock their goals. The system must answer: "What knowledge gaps are preventing me from achieving my goals?"

**Requirements:**
- Find knowledge required by user's goals but not yet mastered
- Calculate prerequisite depth (how many unmastered prerequisites block this knowledge)
- Prioritize by impact (which knowledge unblocks the most goals)
- Support filtering by goal status (active only vs all goals)
- Support filtering by specific goal
- Complete in < 250ms

**Naive approach:**
1. Get all user goals (1 query)
2. For each goal, get required knowledge (N queries)
3. Filter out mastered knowledge in Python
4. Calculate prerequisite depth for each KU (M queries)
5. Count blocking goals per KU (M queries)

**Total: 1 + N + M + M queries** = potential 100+ queries = **5-10 second latency**

---

## Decision

Use **single complex query** with:
1. Property filters first (indexed: user_uid, status)
2. Graph traversal second (goals → knowledge → prerequisites)
3. Nested EXISTS for mastery checking
4. Variable-length path for prerequisite depth calculation
5. Priority scoring server-side

**File:** `/core/services/user/intelligence/learning_intelligence.py`

**Complexity Breakdown:**
- 4 MATCH/OPTIONAL MATCH clauses (8 pts)
- 4 WITH clauses (12 pts)
- 2 nested EXISTS patterns (6 pts)
- 1 variable-length path ([:REQUIRES_KNOWLEDGE*]) (2 pts)
- 2 count DISTINCT aggregations (4 pts)
- CASE expression for priority calculation (3 pts)
- **Total: 35 points** (Very High)

**Query Structure:**
```cypher
// STEP 1: Filter goals by properties (indexed)
MATCH (goal:Goal)
WHERE goal.user_uid = $user_uid
  AND ($goal_statuses IS NULL OR goal.status IN $goal_statuses)
  AND ($goal_uid IS NULL OR goal.uid = $goal_uid)

WITH goal

// STEP 2: Find knowledge required by goals but not mastered
MATCH (goal)-[:REQUIRES_KNOWLEDGE]->(ku:Ku)
WHERE NOT EXISTS {
    MATCH (user:User {uid: $user_uid})-[:MASTERED]->(ku)
}

// STEP 3: Calculate prerequisite depth
OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE*]->(deep_prereq:Ku)
WHERE NOT EXISTS {
    MATCH (user:User {uid: $user_uid})-[:MASTERED]->(deep_prereq)
}
WITH goal, ku, count(DISTINCT deep_prereq) as prerequisite_depth

// STEP 4: Count how many goals this KU blocks
OPTIONAL MATCH (blocking_goal:Goal)-[:REQUIRES_KNOWLEDGE]->(ku)
WHERE blocking_goal.user_uid = $user_uid
  AND ($goal_statuses IS NULL OR blocking_goal.status IN $goal_statuses)
WITH goal, ku, prerequisite_depth,
     count(DISTINCT blocking_goal) as blocking_goals_count

// STEP 5: Calculate priority score
WITH goal, ku, prerequisite_depth, blocking_goals_count,
     (blocking_goals_count * 0.4 +  // More goals blocked = higher priority
      CASE WHEN prerequisite_depth = 0 THEN 0.6  // Easy to fix
           WHEN prerequisite_depth = 1 THEN 0.4
           WHEN prerequisite_depth = 2 THEN 0.2
           ELSE 0.1 END) as priority_score

RETURN
    ku.uid, ku.title, goal.uid, goal.title,
    prerequisite_depth, blocking_goals_count, priority_score
ORDER BY priority_score DESC, blocking_goals_count DESC
```

---

## Alternatives Considered

### Alternative 1: Multiple Queries with Python Aggregation
**Rejected:** Would require 100+ queries for typical user (10 goals × 5 required KUs × 2 calculations). Latency: 5-10 seconds vs 150ms for single query.

### Alternative 2: Pre-computed Knowledge Gaps Index
**Rejected:** Write amplification too high. Every goal creation/update and every knowledge mastery event would trigger recalculation. Correctness challenges with concurrent updates.

### Alternative 3: Simplified Priority (No Prerequisite Depth)
**Rejected:** Prerequisite depth is CRITICAL for prioritization. Without it, users might attempt to learn advanced concepts without foundation knowledge. Violates pedagogical soundness.

---

## Consequences

### Positive
- ✅ **90%+ latency reduction** - Single query vs 100+ queries (150ms vs 5000ms+)
- ✅ **Goal-driven learning** - Aligns learning with user's actual goals
- ✅ **Strategic prioritization** - High-impact knowledge identified automatically
- ✅ **Prerequisite awareness** - Users see learning path depth before committing

### Negative
- ⚠️ **High complexity** - Score 35 (requires careful maintenance)
- ⚠️ **Variable-length path risks** - Deep prerequisite chains could be slow
- ⚠️ **Priority formula hardcoded** - Changing weights requires query edit

### Risks & Mitigation

| Risk | Mitigation |
|------|------------|
| Deep prerequisite chains (>10 levels) slow query | Limit depth in model validation (max 7 levels) |
| Incorrect priority calculation | Comprehensive tests with known scenarios |
| Performance degradation with many goals | Monitor p95 latency, alert at 300ms |

---

## Implementation Details

**Location:** `/core/services/user/intelligence/learning_intelligence.py`

**Performance:**
- Typical: 120-180ms (5 active goals, 15 knowledge gaps)
- Worst-case: 250-320ms (20 goals, 50+ gaps, deep prerequisites)

**Tests:** 7/7 passing in `/tests/integration/test_knowledge_gaps.py`

---

## Monitoring

**Success Criteria:**
- Latency < 250ms for 95% of requests
- Priority scores correlate with user learning choices

**Failure Indicators:**
- 🚨 p95 latency > 300ms
- 🚨 Users report incorrect gap identification

---

## Approval

| Reviewer | Status | Date |
|----------|--------|------|
| Strategic Quality Initiative | ☑ Approved | 2025-11-16 |
| CYP009 Linter | ☑ Flagged (score 35) | 2025-11-16 |

---

## Changelog

| Date | Change | Version |
|------|--------|---------|
| 2025-11-16 | Initial ADR | 1.0 |
