---
title: Real-time Intelligence Implementation Roadmap
updated: 2025-11-27
status: current
category: intelligence
tags: [intelligence, realtime, roadmap]
related: []
---

# Real-time Intelligence Implementation Roadmap

**Endpoint:** `/api/search/real-time-intelligence`
**Status:** FUTURE_VISION (Shelved until prerequisites met)
**Priority:** Low
**Estimated Effort:** 3-4 days

---

## What It Does

Provides adaptive search that learns from user behavior:
- Session-based context tracking
- Adaptive result ranking based on user interactions
- Predictive query suggestions
- Personalized search based on past behavior

**Key Value:** Search gets smarter the more you use it.

---

## Prerequisites (Check These First)

- [ ] Core features are stable and proven
- [ ] Multiple daily active users
- [ ] User behavior patterns established (clicks, dwell time, bookmarks)
- [ ] Users understand and value basic search
- [ ] Need for personalization is validated by user feedback

**Critical:** This is premature without real users and behavioral data.

---

## Reality Check

**You probably don't need this feature.**

Most search systems work fine without real-time personalization. Implement this ONLY if:
1. You have evidence users want personalized search
2. Generic search is insufficient for user needs
3. You have time after all core features are solid

---

## Implementation Plan (If Prerequisites Met)

### Day 1: Session Tracking Infrastructure

**Option A: In-Memory (Simple, Start Here)**
```python
# /core/services/session_tracking_service.py

class SessionTrackingService:
    def __init__(self):
        self._sessions = {}  # session_id -> session_data

    def get_session(self, session_id: str) -> dict:
        """Get or create session"""
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "queries": [],
                "clicks": [],
                "created_at": datetime.now()
            }
        return self._sessions[session_id]

    def track_query(self, session_id: str, query: str):
        """Add query to session history"""
        session = self.get_session(session_id)
        session["queries"].append({
            "query": query,
            "timestamp": datetime.now()
        })

    def track_click(self, session_id: str, result_uid: str):
        """Track which results user clicks"""
        session = self.get_session(session_id)
        session["clicks"].append({
            "result_uid": result_uid,
            "timestamp": datetime.now()
        })
```

**Option B: Redis (For Production)**
- Use if you have multiple servers
- Persist sessions across restarts
- Add TTL for automatic cleanup

---

### Day 2: Adaptive Ranking

```python
# /core/services/adaptive_ranking_service.py

class AdaptiveRankingService:
    def __init__(self, session_tracking: SessionTrackingService):
        self.sessions = session_tracking

    async def rerank_results(
        self,
        results: List[SearchResult],
        session_id: str
    ) -> List[SearchResult]:
        """Adjust ranking based on session history"""

        session = self.sessions.get_session(session_id)

        # Boost results similar to what user clicked before
        for result in results:
            if self._similar_to_clicked(result, session["clicks"]):
                result.relevance_score *= 1.2

        # Sort by adjusted scores
        return sorted(results, key=lambda r: r.relevance_score, reverse=True)

    def _similar_to_clicked(self, result: SearchResult, clicks: List[dict]) -> bool:
        """Check if result is similar to previously clicked items"""
        # Use domain, tags, or content similarity
        # Keep it simple - exact domain match is a good start
        for click in clicks:
            if result.domain == click.get("domain"):
                return True
        return False
```

---

### Day 3: Query Prediction

```python
async def predict_next_queries(
    self,
    session_id: str,
    current_query: str
) -> List[str]:
    """Suggest what user might search next"""

    session = self.sessions.get_session(session_id)

    # Analyze query progression in session
    previous_queries = [q["query"] for q in session["queries"]]

    # Use SearchIntelligenceService to understand intent
    current_intent = self.search_intelligence.analyze_query_intent(current_query)

    # Predict natural progression
    if current_intent["primary_intent"] == "learn":
        # Suggest practice or discovery queries
        return self._generate_practice_queries(current_query)

    return []
```

---

### Day 4: Integration & Testing

- Wire up session tracking to search routes
- Test adaptive ranking with real queries
- Measure if personalization actually helps
- **Important:** Compare personalized vs generic results

---

## Services Needed

| Service | Status | Create? |
|---------|--------|---------|
| SessionTrackingService | ❌ Doesn't exist | Yes |
| AdaptiveRankingService | ❌ Doesn't exist | Yes |
| SearchIntelligenceService | ✅ Exists | No |
| UnifiedUserContext | ✅ Exists | No |

---

## Data Privacy Considerations

**Be careful with session tracking:**
- Clear retention policy (7 days? 30 days?)
- Let users opt out
- Don't track sensitive queries
- Document what you track and why

**Keep it ethical:**
- Improve search, don't surveil
- User benefit first
- Transparent about tracking

---

## Success Criteria

**Before considering this "done":**
- [ ] Sessions tracked reliably
- [ ] Ranking adapts based on behavior
- [ ] Users notice and appreciate personalization
- [ ] A/B test shows improvement over generic search

**Critical:** Must measure actual improvement, not just implement features.

---

## When to Implement

✅ **Implement when:**
- 10+ daily active users
- Users complain search isn't personalized
- You have behavioral data (clicks, bookmarks)
- Core features are completely stable
- You have 3-4 days to focus on this

❌ **Don't implement if:**
- Less than 5 active users
- Generic search works fine
- No evidence users want personalization
- Higher priority work exists
- Core features still evolving

---

## Honest Assessment

**You probably won't need this for months (or ever).**

Most successful products work great without real-time personalization. Focus on core features first. Come back to this only if:
1. Users explicitly request it
2. Generic search is clearly insufficient
3. You have concrete evidence of the need

**Reminder:** Simple + working >> complex + personalized
