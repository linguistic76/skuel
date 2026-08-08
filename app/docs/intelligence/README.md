---
title: SKUEL Intelligence Documentation
updated: 2026-07-10
status: current
category: intelligence
tags: [intelligence, readme]
related: []
---

# SKUEL Intelligence Documentation

This directory contains roadmaps for search intelligence features - both implemented and future.

---

## Quick Navigation

### 📖 Start Here
- **[IMPLEMENTATION_SUMMARY.md](./IMPLEMENTATION_SUMMARY.md)** - What we built and why
- **[INTELLIGENCE_ROADMAP.md](./INTELLIGENCE_ROADMAP.md)** - Master roadmap and philosophy

### ✅ Production Features (Implemented)
- Query parsing + semantic-filter extraction — `SearchQueryParser`
  (`core/models/search/query_parser.py`) extracts typed filters (priority/status/domain);
  `SearchRouter.intelligent_search` (`POST /api/search/intelligent`) then routes user-owned
  activity domains through ownership-scoped faceted search and shared curriculum domains
  (Ku/PS/LP) through bare text search. No facet *suggestions* are returned — that was the
  deleted heuristic service's claim.
- Search-event logging (Discovery Analytics Phase 1, 2026-07-10) — every
  external search → `search.executed` → `:SearchEvent` node

### 🔮 Future Features (Roadmaps)
- **[SEMANTIC_ANALYSIS_ROADMAP.md](./SEMANTIC_ANALYSIS_ROADMAP.md)** - Approved 3-item remainder: concept clustering / prereq inference / ZPD gap feed (search-wiring shipped #538; readability recipe buried)
- **[DISCOVERY_ANALYTICS_ROADMAP.md](./DISCOVERY_ANALYTICS_ROADMAP.md)** - Phases 2+ (clustering, temporal, usage-aware ranking) at 1000+ logged events
- **[REALTIME_INTELLIGENCE_ROADMAP.md](./REALTIME_INTELLIGENCE_ROADMAP.md)** - Personalization (3-4 days)

### 🌟 Aspirational
- **[ULTIMATE_VISION.md](./ULTIMATE_VISION.md)** - Long-term (2+ years)

---

## How to Use These Docs

### If You're Wondering "What's Real?"
→ Read [IMPLEMENTATION_SUMMARY.md](./IMPLEMENTATION_SUMMARY.md)

### If You're Thinking "Should I Build Feature X?"
→ Read [INTELLIGENCE_ROADMAP.md](./INTELLIGENCE_ROADMAP.md), check prerequisites

### If You Want to Implement a Future Feature
→ Read its specific roadmap, verify ALL prerequisites first

### If You're Curious About Long-term Vision
→ Read [ULTIMATE_VISION.md](./ULTIMATE_VISION.md), but stay grounded

---

## Philosophy

**Core functionality first, intelligence later.**

Intelligence features should be built on:
1. Stable core features
2. Real user data
3. Validated user needs

Don't implement intelligence "because it's cool." Implement it because:
1. Users have a problem it solves
2. You have data to power it
3. Core features are proven

---

## Quick Reference

| Feature | Status | Priority | Prerequisites | Effort |
|---------|--------|----------|---------------|--------|
| Intent Prediction | ✅ DONE | - | - | - |
| Semantic Insights | ✅ DONE | - | - | - |
| Search-Event Logging (Discovery Ph. 1) | ✅ DONE (2026-07-10) | - | - | - |
| Semantic Analysis remainder | ✅ APPROVED (queued) | Medium | Sequenced after Discovery Phase 1 arc | 1 PR each |
| Discovery Analytics Phases 2+ | 🔮 FUTURE | Medium | 1000+ logged :SearchEvent nodes | 2-3 days |
| Real-time Intelligence | 🔮 FUTURE | Low | Sessions, users, need | 3-4 days |
| Ultimate Intelligence | 🌟 ASPIRATIONAL | Inspirational | AGI, quantum computers | 2+ years |

---

## Decision Tree

```
Do you want to implement an intelligence feature?
│
├─ Is it PRODUCTION (✅)?
│  └─ It's already done! See search_routes.py + SearchRouter
│
├─ Is it FUTURE_VISION (🔮)?
│  │
│  ├─ Have you checked ALL prerequisites?
│  │  │
│  │  ├─ YES → Read the roadmap, validate user need
│  │  └─ NO → Don't implement yet, prerequisites exist for a reason
│  │
│  └─ Do users actively request this feature?
│     │
│     ├─ YES → Proceed with implementation
│     └─ NO → Focus on features users actually need
│
└─ Is it ASPIRATIONAL (🌟)?
   └─ Don't implement, use as inspiration for grounded features
```

---

## Maintenance Schedule

**Quarterly Review (Every 3 months):**
- Check if prerequisites are now met for any FUTURE feature
- Evaluate user feedback and requests
- Update timelines if AI capabilities change

**Annual Review (Every October):**
- Major roadmap revision
- Assess AI research progress
- Reprioritize based on SKUEL's evolution

**When Prerequisites Met:**
- Read the specific roadmap
- Validate user need
- Implement following the plan
- Update status to PRODUCTION

---

## Adding New Intelligence Features

If you're adding a NEW intelligence feature:

1. **Implement it immediately if it's production-ready**
   - Use real services
   - Test thoroughly
   - Mark as ✅ PRODUCTION

2. **OR create a FUTURE_VISION blueprint:**
   ```python
   @rt("/api/feature/new-intelligence", methods=["POST"])
   async def new_intelligence(request):
       """
       FUTURE_VISION: Clear description.

       STATUS: Mock implementation - needs XYZ.
       PRIORITY: High/Medium/Low
       DEPENDENCIES: List them clearly

       See /docs/intelligence/NEW_FEATURE_ROADMAP.md
       """
       # Mock response with implementation_status marker
       return {
           "implementation_status": "FUTURE_VISION",
           "note": "See roadmap...",
           ...mock data showing intended structure...
       }
   ```

3. **Create a roadmap document:**
   - Prerequisites checklist
   - Implementation plan (day-by-day)
   - Services needed
   - Success criteria
   - When to implement

4. **Update master roadmap:**
   - Add to INTELLIGENCE_ROADMAP.md
   - Set priority
   - Document prerequisites

---

## Anti-Patterns to Avoid

❌ **Don't:** Build intelligence before having data
✅ **Do:** Collect data, then build intelligence

❌ **Don't:** Implement because "AI is cool"
✅ **Do:** Implement because users have a problem

❌ **Don't:** Delete elaborate mocks
✅ **Do:** Mark them as FUTURE_VISION with roadmaps

❌ **Don't:** Build all features at once
✅ **Do:** Build what's needed, shelf the rest

❌ **Don't:** Ignore prerequisites
✅ **Do:** Check ALL prerequisites before implementing

---

## Success Stories

### ✅ BaseAnalyticsService Pattern
- Generic, reusable graph-analytics base for the 9 domain intelligence services
- Composition over duplication
- **Lesson:** Build reusable foundations

### ✅ Production vs Future Separation
- Clear what's real vs aspirational
- No confusion about mock endpoints
- Easy to find implementation roadmaps
- **Lesson:** Clarity prevents wasted effort

### ✅ Honest Assessments
- "You probably don't need this" in roadmaps
- Prerequisites prevent premature work
- Focus maintained on core features
- **Lesson:** Honest guidance saves time

---

## Questions & Contact

**"Should I implement feature X?"**
→ Read its roadmap, check prerequisites

**"How do I know if prerequisites are met?"**
→ Each roadmap has a checklist - verify ALL items

**"Can I modify a future feature's plan?"**
→ Yes! Roadmaps are living documents, improve them

**"What if users request a FUTURE feature?"**
→ Great! That validates the need. Check prerequisites, then implement.

**"Should I create more intelligence features?"**
→ Only if: (1) Real service backing, (2) User need validated, (3) Core features stable

---

## Remember

**The best intelligence is invisible intelligence.**

Features that:
- Solve real problems
- Feel natural
- Don't require explanation
- Just work

Not features that:
- Showcase technical prowess
- Impress other developers
- Are complex for complexity's sake
- Solve imaginary problems

**Build for users, not for résumés.**
