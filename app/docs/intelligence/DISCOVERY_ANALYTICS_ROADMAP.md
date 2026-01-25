---
title: Discovery Analytics Implementation Roadmap
updated: 2025-11-27
status: current
category: intelligence
tags: [analytics, discovery, intelligence, roadmap]
related: []
---

# Discovery Analytics Implementation Roadmap

**Endpoint:** `/api/search/discovery-analytics`
**Status:** FUTURE_VISION (Shelved until prerequisites met)
**Priority:** Medium
**Estimated Effort:** 2-3 days

---

## What It Does

Analyzes search patterns to provide insights:
- Query clustering (what users search for together)
- Temporal patterns (when users search)
- Content gaps (what users can't find)
- User behavior insights (search → success patterns)

**Key Value:** Helps you understand what users need and what content is missing.

---

## Prerequisites (Check These First)

- [ ] Search query logging is enabled
- [ ] At least 1000+ search queries in database
- [ ] Multiple users with varied search patterns (3+ users minimum)
- [ ] Search feature is actively used

**Critical:** You need real usage data. This feature is useless without it.

---

## Implementation Plan

### Day 1: Enable Search Query Logging

**Step 1:** Add logging to SearchRouter
```python
# /core/models/search/search_router.py

async def faceted_search(self, request: SearchRequest, user_uid: str | None = None) -> Result[SearchResponse]:
    # Log the search query
    await self._log_search_query(
        query=request.query_text,
        filters=request.get_active_filters(),
        timestamp=datetime.now()
    )

    # Execute search as normal (route to domain services)
    ...

async def _log_search_query(self, query: str, filters: dict, timestamp: datetime):
    """Store search query in Neo4j for analytics"""
    cypher = """
    CREATE (sq:SearchQuery {
        query: $query,
        filters: $filters,
        timestamp: $timestamp,
        session_id: $session_id
    })
    """
    await self._services.driver.execute_query(cypher, ...)
```

**Run for 1+ week to collect real data before implementing analytics.**

---

### Day 2: Query Clustering & Pattern Analysis

Create `/core/services/analytics_service.py`:
```python
class AnalyticsService:
    async def cluster_queries(self, time_period: str) -> List[dict]:
        """Group similar queries using SearchIntelligenceService"""
        # 1. Fetch all queries from time period
        queries = await self._fetch_queries(time_period)

        # 2. Use SearchIntelligenceService to analyze each query
        analyzed = [
            self.search_intelligence.analyze_query_intent(q)
            for q in queries
        ]

        # 3. Group by primary_intent and domain
        clusters = self._group_by_similarity(analyzed)

        return clusters

    async def analyze_temporal_patterns(self, queries: List[dict]) -> dict:
        """When do users search? Hour of day, day of week"""
        # Simple datetime aggregation
        by_hour = defaultdict(int)
        by_day = defaultdict(int)

        for q in queries:
            hour = q['timestamp'].hour
            day = q['timestamp'].strftime('%A')
            by_hour[hour] += 1
            by_day[day] += 1

        return {"by_hour": by_hour, "by_day": by_day}
```

---

### Day 3: Content Gap Analysis

```python
async def identify_content_gaps(
    self,
    queries: List[str],
    knowledge_corpus: List[KnowledgeUnit]
) -> List[dict]:
    """Find what users search for but can't find"""

    gaps = []
    for query in queries:
        # Search for matching content via SearchRouter
        request = SearchRequest(query_text=query)
        results = await self.search_router.faceted_search(request, user_uid=None)

        # If few or no results, it's a gap
        if len(results) < 3:
            gaps.append({
                "query": query,
                "result_count": len(results),
                "suggested_action": "Create knowledge unit on this topic"
            })

    return sorted(gaps, key=lambda x: x['result_count'])
```

---

## Services Needed

| Service | Status | Create? |
|---------|--------|---------|
| SearchRouter | ✅ Exists | Extend with logging |
| SearchIntelligenceService | ✅ Exists | No |
| AnalyticsService | ❌ Doesn't exist | Yes |

---

## Data Model

**SearchQuery Node:**
```cypher
CREATE (sq:SearchQuery {
    query: "machine learning basics",
    filters: {domain: "TECH"},
    timestamp: datetime(),
    session_id: "abc123",
    result_count: 15,
    clicked_result_uid: "ku.ml_intro"  # Optional: if user clicked
})
```

**Keep it simple!** Just log queries and results.

---

## Success Criteria

**Before considering this "done":**
- [ ] Can cluster queries into meaningful groups
- [ ] Identifies peak search times
- [ ] Reveals content gaps clearly
- [ ] Helps prioritize content creation

**Not required:** Machine learning, complex NLP, real-time

---

## When to Implement

✅ **Implement when:**
- You have 1000+ logged searches
- Multiple users searching regularly
- You want to know what content to create next
- Search logging has run for 2+ weeks

❌ **Don't implement if:**
- No search query logging yet (start there first!)
- Less than 500 total searches
- Single user only
- Core features need more work

---

## Important Notes

**This feature is USELESS without data.**

Implementation is easy (2-3 days), but you need real searches first. Don't implement until you have meaningful query data to analyze.

**Minimum viable data:**
- 1000+ searches
- 5+ days of search history
- 3+ users with different search patterns
