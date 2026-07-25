# GraphQL - Optional Enhancements

## Overview

SKUEL's GraphQL API is **complete and production-ready** with:
- ✅ All core queries (learning paths, knowledge graph, tasks, dashboard)
- ✅ DataLoader batching (N+1 prevention)
- ✅ FastHTML playground (100% Python, no React)
- ✅ Four production guardrails
- ✅ Session-based authentication (two-layer: HTTP + resolver)
- ✅ Cross-domain discovery (wired to `AdaptiveLpCrossDomainService`)
- ✅ Comprehensive tests (98% schema.py coverage)

These enhancements are **optional** - implement only if needed.

Subscriptions were removed entirely (2026-07): the `learning_progress` subscription
was never reachable (no WebSocket transport), and real-time progress tracking is
not wanted. If live updates are ever needed, build an SSE route over the event bus
directly — not a GraphQL subscription.

---

## P1: Rate Limiting Per User

Per-user query rate limits to prevent abuse. Not yet implemented.

---

## P2: Cross-Domain Discovery Enrichment

### Current State

Wired to `AdaptiveLpCrossDomainService`. The `discoverCrossDomain` resolver builds a `KnowledgeState` from client-provided KU UIDs, discovers opportunities via the service, and loads real KnowledgeNodes via DataLoader for source/target representation. Falls back to domain-level placeholder nodes when no real KU is available.

### Remaining Enhancements

- Enrich `KnowledgeState` with real mastery data from `UserContext.zpd_assessment` instead of treating applied = mastered
- Consider `source_knowledge: [KnowledgeNode]` (list) instead of single representative node

---

## Summary

**Production Checklist:**
- ✅ DataLoader batching (complete)
- ✅ Query complexity limits (complete)
- ✅ FastHTML playground (complete)
- ✅ Authentication (complete — session-based, two-layer)
- ✅ Cross-domain discovery (complete)
- ✅ Tests (98% schema.py coverage)
- 📋 Rate limiting (optional)
