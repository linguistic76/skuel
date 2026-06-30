---
name: vis-network
description: Expert guide to Vis.js Network for interactive graph visualization in SKUEL. Use when visualizing lateral relationships, building force-directed graphs, creating relationship network diagrams, or when the user mentions vis.js, graph visualization, relationship networks, interactive graphs, or lateral relationships.
allowed-tools:
  - Read
  - Glob
  - Grep
  - Edit
  - Write
  - Bash
version: 1.0.0
library: vis-network
library_version: 9.1.9
last_updated: 2026-02-02
---

# Vis.js Network - Interactive Graph Visualization

> **Core Philosophy:** "Relationships are as fundamental as entities - visualization makes them tangible."
>
> SKUEL treats relationships as first-class citizens in the graph database. Vis.js Network brings these connections to life through interactive, physics-based visualizations that help users understand complex dependencies, alternatives, and organizational structures.

---

## Table of Contents

**In this file:**
1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Decision Trees](#decision-trees)
4. [Related Skills](#related-skills)
5. [Deep Dive Resources](#deep-dive-resources)
6. [Summary](#summary)

**On-demand reference files:**
- [reference-architecture.md](reference-architecture.md) — Three-Layer Integration Architecture, Vis.js Data Format
- [reference-patterns.md](reference-patterns.md) — Configuration Patterns, Interaction Patterns, Common Use Cases, Depth Control Pattern
- [reference-operations.md](reference-operations.md) — Best Practices, Anti-Patterns, Integration Checklist, Troubleshooting, Performance Metrics

---

## Overview

**What is Vis.js Network?**

Vis.js Network is a JavaScript library for rendering interactive, physics-based network graphs. In SKUEL, it visualizes lateral relationships between entities within the same domain:

- **Blocking dependencies** (task chains)
- **Knowledge prerequisites** (learning paths)
- **Alternative choices** (mutually exclusive options)
- **Complementary relationships** (synergistic pairs)
- **Sibling relationships** (shared hierarchies)

**SKUEL's Integration Approach:**

SKUEL uses a **three-layer architecture** where Vis.js is the presentation layer in a clean separation of concerns:

| Layer | Technology | Purpose | Location |
|-------|-----------|---------|----------|
| **Data** | Neo4j | Store lateral relationship graph | Graph database |
| **API** | FastHTML | Query graph, format for Vis.js | `/api/{domain}/{uid}/lateral/graph` |
| **Presentation** | Alpine.js + Vis.js | Render interactive visualization | `/static/js/skuel.js` |

This architecture enables:
- **Type-safe data flow** from Neo4j to browser
- **Lazy loading** via HTMX (graphs load only when detail section visible)
- **Consistent styling** across all 9 SKUEL domains
- **Zero boilerplate** for new domain integrations

**Current Production Status:**

✅ **Deployed across 9 domains** (January 2026):
- Activity (6): Tasks, Goals, Habits, Events, Choices, Principles
- Curriculum (3): KU, PS, LP

✅ **Explore sidebar graph** (April 2026):
- `ExploreGraphView` (`ui/explore/graph.py`) — graph hero in Explore sidebar
- Alpine component: `exploreGraph(mode, entity_uid, entity_type)` in `skuel.js`
- Hub mode: user's learning universe ("You" center + studying Kus + in-progress PSes)
- Entity mode: lateral relationship graph centered on current Ku/PS
- Filter tabs (All/Learning/Saved) dim/highlight nodes
- Full-screen JS overlay on `document.body` (Escape/backdrop click to close) — creates second Vis.js network to escape sidebar `overflow:hidden` + `transform`
- API: `GET /api/explore/graph` returns Vis.js JSON for hub mode

✅ **40/40 automated tests passing**
✅ **92 API routes verified**
✅ **Zero breaking changes** in Phase 5 rollout

---

## Quick Start

### Installation

**Vis.js is already installed in SKUEL.** The library is self-hosted in `/static/vendor/vis-network/`:

```
/static/vendor/vis-network/
├── vis-network.min.js      # 476KB, v9.1.9
└── vis-network.min.css     # 220KB
```

Scripts are loaded via `/ui/layouts/base_page.py` in the `<head>` section:

```python
# Already included in all pages
Script(src="/static/vendor/vis-network/vis-network.min.js"),
Link(rel="stylesheet", href="/static/vendor/vis-network/vis-network.min.css"),
```

**No additional setup required.**

---

### Example 1: Add Graph to Existing Detail Page (5 lines)

**Use Case:** Add interactive relationship graph to any entity detail page.

**Time:** ~2 minutes

```python
from ui.patterns.relationships import EntityRelationshipsSection

# In your detail page function (e.g., task_detail, goal_detail, ku_detail)
def task_detail(request, uid: str, task: Task, ...):
    return BasePage(
        content=Container(
            # ... existing content (title, description, etc.)

            # Add this one line - that's it!
            EntityRelationshipsSection(
                entity_uid=task.uid,
                entity_type="tasks",  # Domain name (lowercase plural)
            ),
        ),
        request=request,
    )
```

**What you get:**
- Three visualization tabs (Blocking Chain, Alternatives, Interactive Graph)
- Lazy-loaded via HTMX (only loads when visible)
- Automatic depth control UI (1-3 levels)
- Click-to-navigate functionality
- Zero configuration needed

---

### Example 2: Custom Graph Component (Standalone)

**Use Case:** Want just the interactive graph, not the full section with tabs.

**Time:** ~5 minutes

```python
from ui.patterns.relationships import RelationshipGraphView

# In your detail page
def task_detail(request, uid: str, task: Task, ...):
    return BasePage(
        content=Container(
            H2("Task Dependencies", cls="text-xl font-bold"),

            # Standalone graph with custom depth
            RelationshipGraphView(
                entity_uid=task.uid,
                entity_type="tasks",
                default_depth=2,  # Start at depth 2 (default is 1)
            ),
        ),
        request=request,
    )
```

**What you get:**
- Just the interactive graph visualization
- Depth control select dropdown
- Alpine.js `relationshipGraph()` component auto-initialized
- HTMX lazy loading on viewport entry

---

### Example 3: Manual Alpine Integration (Full Control)

**Use Case:** Need custom container styling, multiple graphs on one page, or non-standard layout.

**Time:** ~10 minutes

```python
from fasthtml.common import Div, Select, Option

def custom_graph_page(request, uid: str):
    return BasePage(
        content=Container(
            # Custom container with your own styling
            Div(
                # Depth control (optional)
                Select(
                    Option("1 level", value="1"),
                    Option("2 levels", value="2", selected=True),
                    Option("3 levels", value="3"),
                    **{
                        "x-model": "depth",
                        "@change": "loadGraph()",
                    },
                    cls="text-sm",
                ),

                # Graph container - MUST have ID matching x-ref
                Div(
                    **{"x-ref": "container"},
                    style="width: 100%; height: 600px;",  # Explicit sizing required
                    cls="border rounded-lg bg-base-100",
                ),

                # Alpine component initialization
                **{
                    "x-data": f"relationshipGraph('{uid}', 'tasks', 2)",
                    "x-init": "loadGraph()",
                },
                cls="space-y-4",
            ),
        ),
        request=request,
    )
```

**Key requirements:**
1. Container must have `x-ref="container"` for Alpine to find it
2. Container must have explicit width/height (Vis.js requirement)
3. `x-data` must call `relationshipGraph(uid, entityType, depth)`
4. `x-init="loadGraph()"` triggers initial render

---

## SKUEL Integration Reference

The detailed integration material lives in three on-demand reference files:

- **[reference-architecture.md](reference-architecture.md)** — the Three-Layer Integration Architecture (Neo4j → FastHTML API → Alpine.js + Vis.js) and the Vis.js Data Format (nodes/edges JSON, palette).
- **[reference-patterns.md](reference-patterns.md)** — Configuration Patterns (physics, layout, styling), Interaction Patterns (events, hover, click), Common Use Cases (hub vs entity mode), and the Depth Control Pattern.
- **[reference-operations.md](reference-operations.md)** — Best Practices and Anti-Patterns (plus the Integration Checklist, Troubleshooting, and Performance Metrics, also linked below).

---

## Decision Trees

### When to Use Vis.js vs Other Visualizations

```
Does the data represent relationships between entities?
├─ YES → Are relationships the PRIMARY focus?
│   ├─ YES → Vis.js Network ✅
│   └─ NO  → Is it hierarchical (tree)?
│       ├─ YES → Consider D3 tree or Vis.js hierarchical layout
│       └─ NO  → Vis.js Network (force-directed) ✅
└─ NO  → Is it time-series or quantitative data?
    ├─ YES → Use Chart.js (line/bar charts) ❌
    └─ NO  → Is it tabular data?
        ├─ YES → Use HTML table ❌
        └─ NO  → Use Vis.js Network (can represent any graph) ✅
```

**Summary:**
- **Vis.js Network:** Relationships, dependencies, networks
- **Chart.js:** Time-series, metrics, statistics
- **HTML Table:** Tabular data, comparisons
- **D3:** Custom visualizations, complex interactions

---

### Which Physics Solver to Use

```
What is your graph structure?
├─ Lateral relationships (cyclic, clustered)
│   → forceAtlas2Based ✅ (SKUEL default)
│
├─ Large graph (1000+ nodes, performance critical)
│   → barnesHut ✅
│
├─ Hierarchical tree (DAG, no cycles)
│   → hierarchical ✅
│
└─ Simple repulsion (no structure)
    → repulsion ⚠️ (rarely needed)
```

**SKUEL uses forceAtlas2Based** because lateral relationships form clusters (not strict hierarchies).

---

### What Depth to Use

```
What is the user's goal?
├─ See immediate dependencies only
│   → Depth 1 ✅
│
├─ Understand context and indirect relationships
│   → Depth 2 ✅ (SKUEL default)
│
├─ Deep exploration, comprehensive view
│   → Depth 3 ⚠️ (may be slow)
│
└─ Complete graph traversal
    → Depth 4+ ❌ (not allowed - exponential)
```

**Default to depth 2** - good balance of context and performance.

---

## Integration Checklist

The step-by-step checklist for adding Vis.js graphs to a new domain lives in **[reference-operations.md](reference-operations.md#integration-checklist)**.

---

## Related Skills

### Foundation Skills

**Required for Vis.js integration:**

| Skill | Why Required | Use For |
|-------|-------------|---------|
| **ui-browser** | Alpine.js + HTMX integration | `relationshipGraph()` component, reactive state, lazy loading (`hx-trigger="intersect once"`) |
| **neo4j-cypher-patterns** | Graph queries | Cypher queries for lateral relationships |

**Recommended:**

| Skill | Relation | Use For |
|-------|----------|---------|
| **python** | Service layer | Service methods, API routes |
| **fasthtml** | Web framework | Route definitions, FastHTML components |
| **ui-css** | Styling | Container styling, responsive layout |

---

### Related Pattern Skills

**Domain-specific patterns:**

| Skill | Relation | Use For |
|-------|----------|---------|
| **activity-domains** | Activity domains use lateral relationships | Tasks, Goals, Habits, Events, Choices, Principles |
| **curriculum-domains** | Curriculum domains use lateral relationships | KU, PS, LP (prerequisites, alternatives) |
| **skuel-ui** | Page layout + UI patterns | BasePage wrapper for detail pages, component hierarchy, reusable patterns |

---

## Deep Dive Resources

### Primary Documentation

**Must-read for Vis.js integration:**

| Document | Purpose | Key Sections |
|----------|---------|--------------|
| `/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md` | Complete pattern guide | Three-layer architecture, configuration, UI components |
| `/docs/architecture/RELATIONSHIPS_ARCHITECTURE.md` | Graph modeling | Lateral relationship types, service API, Cypher patterns |
| `/PHASE5_COMPLETE.md` | Implementation completion guide | Deployment checklist, testing, verification |

---

### Key Implementation Files

**Read these files for implementation details:**

| File | Lines | Purpose |
|------|-------|---------|
| `/static/js/skuel.js` | 2313-2431 | Alpine `relationshipGraph()` component (complete source) |
| `/core/services/lateral_relationships/lateral_relationship_service.py` | All | Core service methods, Cypher queries |
| `/ui/patterns/relationships/relationship_graph.py` | All | FastHTML wrapper component |
| `/ui/patterns/relationships/relationship_section.py` | All | Main orchestrator (tabs, depth control) |
| `/adapters/inbound/lateral_routes.py` | All | Route registration examples |
| `/adapters/inbound/route_factories/lateral_route_factory.py` | All | Route factory pattern |

---

### Architecture Decision Records (ADRs)

| ADR | Title | Key Decision |
|-----|-------|--------------|
| ADR-037 | Lateral Relationships Visualization Phase 5 | Three-layer architecture, Vis.js choice, depth limits |

---

### External Resources

**Official Vis.js documentation:**
- [Vis.js Network Documentation](https://visjs.github.io/vis-network/docs/network/) - Official API reference
- [Vis.js Examples](https://visjs.github.io/vis-network/examples/) - Interactive examples
- [ForceAtlas2 Algorithm Paper](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0098679) - Physics solver research

---

## Troubleshooting & Performance

Common issues, fixes, and performance benchmarks live in **[reference-operations.md](reference-operations.md#troubleshooting)**.

---

## Summary

**Vis.js Network in SKUEL:**

- **Purpose:** Visualize lateral relationships (blocking, prerequisites, alternatives, complements)
- **Integration:** Three-layer architecture (Neo4j → API → Alpine/Vis.js)
- **Deployment:** 9 domains (Tasks, Goals, Habits, Events, Choices, Principles, KU, PS, LP)
- **Performance:** <400ms API + <3s render for depth 2 (typical use case)
- **User Experience:** Interactive, physics-based, click-to-navigate

**Quick Start:** Add `EntityRelationshipsSection(entity_uid, entity_type)` to any detail page - done in 5 lines.

**Deep Integration:** Use `RelationshipGraphView` or manual Alpine integration for custom layouts.

**Best Practice:** Use forceAtlas2Based solver, depth 2 default, disable physics after stabilization.

---

**Related Skills:** @ui-browser @neo4j-cypher-patterns @activity-domains @curriculum-domains

**Deep Dive:** `/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md`
