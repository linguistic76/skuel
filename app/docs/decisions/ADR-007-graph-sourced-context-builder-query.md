---
title: ADR-007: Graph-Sourced-Context-Builder Query Architecture
updated: 2025-11-26
status: current
category: decisions
tags: [007, adr, builder, context, decisions]
related: []
---

# ADR-007: Graph-Sourced-Context-Builder Query Architecture

**Status:** Superseded by ADR-001

**Date:** 2025-11-16

**Decision Type:** ☑ Query Architecture  ⬜ Graph Schema  ☑ Performance Optimization  ⬜ Pattern/Practice

**Complexity Score:** 38 (Very High)

**Related ADRs:**
- **Superseded by**: ADR-001 (Unified User Context Single Query)

---

## Notice: Duplicate ADR

This ADR stub was automatically generated for the query at:
- **File**: `core/services/user/graph_sourced_context_builder.py:128`
- **Complexity Score**: 38

However, this query was already comprehensively documented in **ADR-001: Single Complex Query for Unified User Context**.

**Please refer to ADR-001 for complete documentation of this architectural decision.**

---

## Summary from ADR-001

**Purpose:** Build UserContext by aggregating data from 7+ activity domains in a single complex query.

**Decision:** Use single query with 8 MATCH clauses, 4 WITH clauses, and strategic staging to gather all user context in one database round-trip.

**Rationale:** 60% latency reduction (180ms vs 450ms for 15-18 separate queries).

**For complete details, see:** `/docs/decisions/ADR-001-unified-user-context-single-query.md`
