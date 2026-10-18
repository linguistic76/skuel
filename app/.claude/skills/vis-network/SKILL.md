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
last_updated: 2026-10-17
---

# Vis.js Network - Interactive Graph Visualization

> **Core Philosophy:** "Relationships are as fundamental as entities - visualization makes them tangible."
>
> SKUEL treats relationships as first-class citizens in the graph database. Vis.js Network draws them as an interactive, physics-based graph, so a user can see dependencies, alternatives and neighbours around the entity they are on.

---

## Table of Contents

**In this file:**
1. [Where SKUEL Draws Graphs](#where-skuel-draws-graphs)
2. [How a Graph Renders](#how-a-graph-renders)
3. [Quick Start](#quick-start)
4. [Decision Trees](#decision-trees)
5. [Related Skills](#related-skills)
6. [Deep Dive Resources](#deep-dive-resources)

**On-demand reference files:**
- [reference-architecture.md](reference-architecture.md) — the layers from Cypher to canvas, the route set, the JSON shape, the Alpine component
- [reference-patterns.md](reference-patterns.md) — SKUEL's Vis.js options, edge styling, click navigation, the Explore graph, depth
- [reference-operations.md](reference-operations.md) — Best Practices, Anti-Patterns, Integration Checklist, Troubleshooting

---

## Where SKUEL Draws Graphs

| Surface | Component | Alpine | Data |
|---------|-----------|--------|------|
| The six Activity detail pages, the Ku reading page, the LP page | `EntityRelationshipsSection` → `RelationshipGraphView` (`ui/patterns/relationships/`) | `relationshipGraph(uid, type, depth)` | `GET /api/{domain}/{uid}/lateral/graph` |
| `/explore/library` sidebar | `ExploreGraphView` (`ui/explore/graph.py`) via `render_explore_sidebar_page` | `exploreGraph(mode, uid, type)` | `GET /api/explore/graph` (hub mode) |
| `/explore/graph` | `ExploreGraphView(mode="hub")`, full page | `exploreGraph` | `GET /api/explore/graph` |

Lateral routes exist for nine domains: the six Activity domains plus `ku`, `ps`, `lp`
(`_LATERAL_DOMAINS` in `adapters/inbound/lateral_routes.py`). No PathStep page mounts the
section. Vis.js v9.1.9 is self-hosted (`/static/vendor/vis-network/`) and `build_head()`
loads it on every `BasePage`, so a page needs no script tag of its own.

---

## How a Graph Renders

| Layer | Where | What it does |
|-------|-------|--------------|
| **Data** | `LateralRelationshipBackend.get_relationship_graph` (`adapters/persistence/neo4j/backends/collab_backends.py`) | One variable-length match, `(center:Entity {uid})-[r:TYPES*1..{depth}]-(related)`, every node past the center filtered to the caller's audience (`build_path_audience_clause`); pure Cypher, no APOC |
| **Service** | `LateralRelationshipService.get_relationship_graph` (`core/services/lateral_relationships/`) | Gates the **center** entity — ownership on the six Activity domains, curriculum kind (Ku / PathStep / LearningPath) on ku / ps / lp, where a foreign or missing uid is the same 404 — builds `RelationshipGraphData` nodes + edges, colors edges with `RelationshipColor` |
| **Route** | `LateralRouteFactory` (`adapters/inbound/route_factories/lateral_route_factory.py`) | `GET .../lateral/graph?depth=&types=`, adds each node's detail-page `url` |
| **Presentation** | `relationshipGraph` + the `SKUEL.graph` helpers (`static/js/skuel.js`) | `SKUEL.getJson` → style edges → `new vis.Network` → click navigates to `node.url` |

The graph route answers JSON, not a fragment. The blocking chain, the alternatives
comparison and the manage list answer **HTML fragments** that HTMX swaps in.

---

## Quick Start

### Example 1: The Whole Section (the normal case)

```python
from ui.patterns.relationships import EntityRelationshipsSection

EntityRelationshipsSection(
    entity_uid=task.uid,
    entity_type="tasks",   # the route domain: tasks, goals, …, ku, ps, lp
    authoring=True,        # add/delete panel — takes effect for the six Activity types only
)
```

**What it renders:** an `Accordion` (`ui.components`, `multiple=True`) under a
`SectionHeader("Relationships")`:
- **Manage Relationships** (only with `authoring=True` on an Activity type, open): the add
  modal plus the deletable edge list (`GET .../lateral/manage`)
- **Blocking Dependencies**: `GET .../lateral/chain` on `load`
- **Alternative Approaches**: `GET .../lateral/alternatives/compare` on `load delay:300ms`
- **Relationship Network** (open): the Vis.js graph

The factory's lateral writes (the four creates the add modal posts to, and the delete)
answer `HX-Trigger: relationships-changed`. The three fragments listen with
`relationships-changed from:body`, and the graph with
`x-on:relationships-changed.window="loadGraph(depth)"`, so every surface refreshes off one
event. The domain-specific writers in `lateral_routes.py` (`stacks`, `conflicts`,
`enables`) don't emit the event; the authoring UI doesn't call them. The fragments load when
the page loads, whether or not their panel is open.

### Example 2: Just the Graph

```python
from ui.patterns.relationships import RelationshipGraphView

RelationshipGraphView(entity_uid=task.uid, entity_type="tasks", depth=2)
```

It renders a card with a depth select (1–3, the route's cap; the initial depth is the selected
option), the canvas (`Div(id=f"network-{uid}", cls="w-full h-96 …")`), an error line
(`x-text="error"`, shown when the graph fails to load), and a color legend. The `x-data`
sits on the card body, so one scope holds the select, the canvas and the error; Alpine calls
the component's `init()` (one fetch per mount) and its `destroy()` when the card leaves the
page (the network is torn down).
`RelationshipGraphView` is **the** graph for a detail page; use it (directly or through
`EntityRelationshipsSection`) rather than building a second one.

A change to the graph's behaviour belongs **in** `RelationshipGraphView`
(`ui/patterns/relationships/relationship_graph.py`), so every `EntityRelationshipsSection`
consumer gets it. `tests/js/graph-components.test.js` mounts its rendered markup with the
vendored Alpine (one fetch per mount, the depth select refetches, the error shows, removal
destroys the network); `tests/unit/ui/test_graph_alpine_markup.py` keeps that fixture equal to
what the Python renders.

### The Component Contract

What `relationshipGraph` requires of its markup — `RelationshipGraphView` meets it. This is
the checklist for changing that component, or for a genuinely new graph surface; it is not a
second way to draw the detail-page graph:

1. The canvas has `id="network-{entity_uid}"`. `renderNetwork` does
   `document.getElementById`, not `$refs`.
2. The canvas has a real height (`h-96`); Vis.js draws into the box it is given.
3. There's no `x-init`. Alpine calls the component's `init()`, which calls
   `loadGraph(this.depth)`.
4. Every control that calls `changeDepth` / `loadGraph` sits inside the `x-data` element.
5. The `x-data` element listens for `relationships-changed.window` to reload.
6. An element with `x-text="error"` (and `x-show="error"`) inside the scope shows a failed load.

Markup that satisfies it (measured: one fetch on load; a depth change refetches with
`?depth=3`):

```python
Div(
    Select(
        Option("Depth 1", value="1"),
        Option("Depth 2", value="2", selected=True),
        Option("Depth 3", value="3"),
        name="graph_depth",
        full_width=False,
        **{"x-on:change": "changeDepth($event.target.value)"},
    ),
    Div(id=f"network-{uid}", cls="w-full h-96 border border-border rounded-sm"),
    P(role="alert", x_show="error", x_text="error", x_cloak=True),
    **{
        "x-data": alpine_call("relationshipGraph", uid, "tasks", 2),  # ui.alpine
        "x-on:relationships-changed.window": "loadGraph(depth)",
    },
)
```

---

## Decision Trees

### When to Use Vis.js vs Other Visualizations

```
Does the data represent relationships between entities?
├─ YES → Are relationships the PRIMARY focus?
│   ├─ YES → Vis.js Network ✅
│   └─ NO  → Is it a strict ordered chain?
│       ├─ YES → BlockingChainView (an HTML fragment, no canvas) ✅
│       └─ NO  → Vis.js Network (force-directed) ✅
└─ NO  → Is it time-series or quantitative data?
    ├─ YES → Chart.js (see the chartjs skill)
    └─ NO  → Is it tabular data?
        ├─ YES → HTML table (TableFromDicts)
        └─ NO  → Vis.js Network (can represent any graph)
```

### Which Physics Solver to Use

```
What is your graph structure?
├─ Lateral relationships (cyclic, clustered)
│   → forceAtlas2Based ✅ (every SKUEL profile)
│
├─ Large graph (1000+ nodes, performance critical)
│   → barnesHut
│
├─ Hierarchical tree (DAG, no cycles)
│   → layout.hierarchical
│
└─ Simple repulsion (no structure)
    → repulsion (rarely needed)
```

### What Depth to Use

```
What is the user's goal?
├─ See immediate relationships only → depth 1
├─ Understand context → depth 2 (the default everywhere)
└─ Deep exploration → depth 3 (the select's maximum)
```

**The route caps it at 3.** `GET .../lateral/graph` reads `depth` strictly
(`parse_int_param_strict`): missing is 2, unreadable or below 1 is a 400, above 3 is 3
(`GraphDepth.DEFAULT`). The select's options are built from the same range, so a surface
cannot offer a depth the route does not draw.

---

## Related Skills

| Skill | Relation | Use For |
|-------|----------|---------|
| **ui-browser** | Alpine.js + HTMX | the `relationshipGraph` / `exploreGraph` components, the `relationships-changed` event |
| **neo4j-cypher-patterns** | Graph queries | the lateral Cypher in `LateralRelationshipBackend` |
| **skuel-ui** | Page layout | detail pages, `Accordion`, `SectionHeader` |
| **activity-domains** / **curriculum-domains** | Where the section mounts | Activity detail views, Ku / LP pages |
| **chartjs** | The other visualization library | quantitative charts |

---

## Deep Dive Resources

### Primary Documentation

| Document | Purpose |
|----------|---------|
| `/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md` | The pattern guide: authoring, components, routes |
| `/docs/architecture/RELATIONSHIPS_ARCHITECTURE.md` | Lateral types, `LateralRelationshipService` API, ownership coverage |

### Key Implementation Files

| File | Purpose |
|------|---------|
| `/static/js/skuel.js` | `SKUEL.graph` helpers (`PROFILES`, `buildOptions`, `styleEdgesByConfidence`, `attachClickNav`); `Alpine.data('relationshipGraph', …)`; `Alpine.data('exploreGraph', …)` |
| `/core/services/lateral_relationships/lateral_relationship_service.py` | `get_relationship_graph`, `get_blocking_chain`, `get_alternatives_with_comparison` |
| `/adapters/persistence/neo4j/backends/collab_backends.py` | `LateralRelationshipBackend` — the Cypher |
| `/adapters/inbound/route_factories/lateral_route_factory.py` | The per-domain route set |
| `/adapters/inbound/lateral_routes.py` | `_LATERAL_DOMAINS` — the domain list |
| `/ui/patterns/relationships/` | `EntityRelationshipsSection` (`relationship_section.py`), `RelationshipGraphView`, `BlockingChainView`, `AlternativesComparisonGrid`, `AddRelationshipModal`, the manage list |
| `/ui/explore/graph.py` | `ExploreGraphView` |
| `/core/utils/palette.py` | `RelationshipColor` — edge colors by type |

### Architecture Decision Records

| ADR | Title | Key Decision |
|-----|-------|--------------|
| ADR-037 (`ADR-037-lateral-relationships-visualization-phase5.md`) | Lateral Relationships Visualization Phase 5 | Three components, Vis.js as the graph library |

### External Resources

- [Vis.js Network Documentation](https://visjs.github.io/vis-network/docs/network/) — official API reference (v9)
- [Vis.js Examples](https://visjs.github.io/vis-network/examples/)

---

**Related Skills:** @ui-browser @neo4j-cypher-patterns @skuel-ui

**Deep Dive:** `/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md`
