---
title: SKUEL Intelligence Roadmap
updated: 2026-07-10
status: current
category: intelligence
tags: [intelligence, roadmap]
related: []
---

# SKUEL Intelligence Roadmap
**Last Updated:** 2026-07-10
**Status:** Foundation Complete; Discovery Phase 1 shipped; Semantic remainder approved

## Philosophy

**Focus on Core First, Intelligence Later**

SKUEL's intelligence features should be built on a foundation of:
1. ✅ **Stable core functionality** (tasks, habits, knowledge management)
2. ✅ **Real user data** (populated system with actual usage)
3. ✅ **Proven patterns** (users understand and value the features)

Intelligence without data is fantasy. Intelligence without users is premature optimization.

---

## Current State (2026-07-10)

### ✅ Production-Ready Intelligence

| Surface | Service | Capability |
|---------|---------|------------|
| `POST /api/search/intelligent` | `SearchRouter.intelligent_search` (`SearchQueryParser`) | Query intent parsing (priority/status/domain) + semantic filter extraction |
| `/search` body-chunk layer (#538) | Neo4jVectorSearchService | Lesson-body semantic hits fold into faceted results |
| `search.executed` → `:SearchEvent` | SearchEventRecorder | Search behavioral log (Discovery Analytics Phase 1) |

**Foundation Service:** `BaseAnalyticsService` (578 lines)
- Intent scoring with confidence
- Facet detection from query patterns
- Result ranking by relevance
- Search insights generation

**Status:** ✅ Working, tested, integrated with search UI

---

## Future Vision (Shelved - Awaiting Foundation)

### 🔮 Medium Priority (Implement After Core Proven)

#### 1. Semantic Analysis remainder — ✅ APPROVED 2026-07-10 (queued)
Search wiring shipped (#538 body-chunk layer); the readability/TextAnalysisService
recipe and its `/api/search/semantic-analysis` endpoint were buried (One Path
Forward). What remains — all three product-approved as a follow-up arc, one PR
each: concept clustering, prerequisite inference, Askesis/ZPD gap feed.

**Prerequisites:** none — sequenced after the Discovery Analytics Phase 1 arc
**Roadmap:** `/docs/intelligence/SEMANTIC_ANALYSIS_ROADMAP.md`

---

#### 2. Discovery Analytics Phases 2+ (Phase 1 ✅ shipped 2026-07-10)
Phase 1 (search-event logging + content-gap aggregation) is live: every external
search lands a `:SearchEvent` node. Deferred phases: query clustering, temporal
patterns, usage-aware ranking.

**Prerequisites:**
- 1000+ `:SearchEvent` nodes (`MATCH (e:SearchEvent) RETURN count(e)`)
- Multiple users with varied search patterns

**Value Proposition:** Identify content gaps, optimize search results

**Estimated Effort:** 2-3 days
**Roadmap:** `/docs/intelligence/DISCOVERY_ANALYTICS_ROADMAP.md`

---

### 🔮 Low Priority (Implement After Significant Usage)

#### 3. Real-time Intelligence (`/api/search/real-time-intelligence`)
**Prerequisites:**
- Session tracking infrastructure
- User behavior patterns established
- Personalization needs validated by users

**Value Proposition:** Adaptive search that learns from user behavior

**Estimated Effort:** 3-4 days
**Roadmap:** `/docs/intelligence/REALTIME_INTELLIGENCE_ROADMAP.md`

---

### 🌟 Aspirational (2+ Year Research Vision)

#### 4. Ultimate Intelligence (`/api/search/ultimate-intelligence`)
**Prerequisites:**
- Multi-modal AI research breakthroughs
- Quantum computing accessibility (😅)
- AGI-level semantic understanding

**Value Proposition:** Showcase long-term vision, inspire research direction

**Reality:** Educational blueprint, not near-term implementation
**Roadmap:** `/docs/intelligence/ULTIMATE_VISION.md`

---

## Implementation Decision Matrix

### When to Implement Each Feature

```
BEFORE implementing intelligence features, ensure:

✅ Core Features Status:
  - Tasks management working and used daily
  - Habits tracking proven valuable
  - Knowledge units created and organized
  - Events/calendar actively used
  - Users understand and rely on core features

✅ Data Foundations:
  - 100+ tasks created
  - 50+ knowledge units
  - 20+ habits tracked
  - 1000+ search queries logged
  - Multiple users providing feedback

✅ Technical Readiness:
  - Services stable and tested
  - Performance acceptable
  - Error handling mature
  - Monitoring in place
```

### Then Implement In Order:

1. **Semantic Analysis** - When you have rich text content to analyze
2. **Discovery Analytics** - When you have query patterns to mine
3. **Real-time Intelligence** - When you have user behavior to learn from
4. **Ultimate Intelligence** - Never (it's aspirational inspiration)

---

## Code Organization

### Production Intelligence
```
/core/orchestrator/search_router.py     # THE search orchestrator (intent parse, faceting, ranking)
/core/models/search/query_parser.py     # SearchQueryParser — Analog intent/token parsing
/core/models/search/scoring.py          # unified score_* result ranking
```

### Future Vision Documentation
```
/docs/intelligence/INTELLIGENCE_ROADMAP.md (this file)
/docs/intelligence/SEMANTIC_ANALYSIS_ROADMAP.md
/docs/intelligence/DISCOVERY_ANALYTICS_ROADMAP.md
/docs/intelligence/REALTIME_INTELLIGENCE_ROADMAP.md
/docs/intelligence/ULTIMATE_VISION.md
```

### Mock Responses (Educational Blueprints)
All mock responses now include:
- `"implementation_status": "FUTURE_VISION"` or `"ASPIRATIONAL_VISION"`
- `"note": "Link to implementation roadmap"`
- Clear prerequisites and dependencies

---

## Key Lessons Learned

### What Worked
✅ `BaseAnalyticsService` - Generic, reusable query understanding
✅ Clear separation - Real vs Future clearly marked

### What Didn't Work
❌ Building mock endpoints before having data to power them
❌ Elaborate fantasy features (quantum processing, consciousness simulation)
❌ Premature optimization - intelligence without users

### The Right Path Forward
1. Build core features users need
2. Collect real usage data
3. Identify actual pain points
4. Implement intelligence to solve real problems
5. Iterate based on feedback

---

## Contact & Questions

**When to revisit this roadmap:**
- After 3 months of active use
- When you have 5+ daily active users
- When search patterns emerge organically
- When users request specific intelligence features

**Not before:** The foundation must be solid and proven first.

---

## Appendix: Intelligence API Landscape

SKUEL has **11 intelligence API files** (14,139 lines total, 167 routes):
- Most are elaborate mocks like search intelligence originally was
- Likely candidates for similar "future vision" treatment
- Follow this roadmap pattern for other intelligence APIs

**Next Steps for Other Intelligence APIs:**
1. Identify which routes provide real value NOW
2. Mark others as FUTURE_VISION with roadmaps
3. Focus development on core features
4. Revisit when foundation is proven
