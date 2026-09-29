# vis-network Reference: Configuration, Interaction, the Explore Graph & Depth

> On-demand reference for the [`vis-network`](SKILL.md) skill. SKILL.md holds the surfaces, the quick start and the decision trees; this file holds SKUEL's live Vis.js configuration, its styling and interaction code, the Explore graph, and depth control.

---

## Configuration: One Builder, Three Profiles

SKUEL builds every Vis.js options object in one place, `SKUEL.graph.buildOptions(profile)`
in `static/js/skuel.js`, from a profile in `SKUEL.graph.PROFILES`. A new graph surface picks
or adds a profile; it doesn't re-type the numbers.

| Profile | Used by | Node size | Physics (forceAtlas2Based) | Stabilization |
|---------|---------|-----------|----------------------------|---------------|
| `relationship` | `relationshipGraph` (detail pages) | 16, one global size | gravity −50, central 0.01, spring 100 / 0.08 | 150 iterations |
| `exploreSidebar` | `exploreGraph` in the sidebar | center 24, others 14 | gravity −40, central 0.015, spring 80 / 0.06 | 100 iterations |
| `exploreExpanded` | `exploreGraph`'s full-screen overlay | center 30, others 18 | gravity −60, central 0.01, spring 120 / 0.04 | 150 iterations |

What `buildOptions(PROFILES.relationship)` produces:

```javascript
{
  nodes: {
    shape: 'dot',
    size: 16,
    font: { size: 14, color: '#333' },
    borderWidth: 2,
    shadow: true
  },
  edges: { width: 2, smooth: { type: 'continuous' }, shadow: true },
  physics: {
    forceAtlas2Based: { gravitationalConstant: -50, centralGravity: 0.01, springLength: 100, springConstant: 0.08 },
    maxVelocity: 50,
    solver: 'forceAtlas2Based',
    timestep: 0.35,
    stabilization: { iterations: 150 }
  },
  interaction: { hover: true, tooltipDelay: 200 }
}
```

The two Explore profiles are `navigable`, which adds `interaction.zoomView`,
`interaction.dragView` and `layout.improvedLayout`. Physics stays **on** after
stabilization on every surface: SKUEL registers no `stabilizationIterationsDone` handler.

**Why forceAtlas2Based:** lateral relationships are not a tree. `BLOCKS` chains, alternatives
and complements form clusters and can cycle, so a force-directed solver fits better than
`layout.hierarchical`.

---

## Edge Styling

The service colors each edge by type (`RelationshipColor`, see reference-architecture.md).
The browser then restyles by confidence and priority:

```javascript
// SKUEL.graph.styleEdgesByConfidence — used by relationshipGraph
var priorityWidthMap = { high: 3, medium: 2, low: 1 };
// width  ← priority (default 'medium' → 2)
// dashes ← confidence: ≥ 0.8 solid, ≥ 0.5 [8, 4] at 0.7 opacity, else [3, 3] at 0.5 opacity
// color  ← the server's color, with that opacity
```

The graph route doesn't put `confidence` or `priority` on its edges today, so every edge
renders solid at width 2. The styling engages when a caller supplies those fields.

Explore surfaces use `SKUEL.graph.styleNodes` / `styleEdges` instead: node color by entity
type (Ku violet `#8B5CF6`, PS teal `#14B8A6`, "You" blue `#3B82F6`, anything else gray),
center-vs-leaf sizing from the profile, and edges at 0.6 opacity.

---

## Interaction: Click to Navigate

```javascript
// SKUEL.graph.attachClickNav(network, nodes, centerUid, hrefFor)
network.on('click', function(params) {
    if (params.nodes.length === 0) return;
    var node = nodes.find(function(n) { return n.id === params.nodes[0]; });
    if (!node || node.id === centerUid || node.group === 'center') return;   // the center is this page
    var href = hrefFor(node);
    if (href) window.location.href = href;
});
```

- `relationshipGraph` passes `node => node.url || null`: the route resolved `url` with
  `entity_detail_href` from `entity_type`. A type with no detail page has `url: None`, and
  clicking it does nothing.
- **Never build a URL from `node.type`.** It is the Neo4j label (`"Task"`, `"Entity"` for a
  PathStep), not a route, and detail routes vary in shape (`/tasks/detail?uid=`,
  `/explore/ku/{uid}`).
- Navigation is a full page load, not an HTMX swap: a detail page is a page, with its own URL
  and history entry.

**Tooltips:** `interaction.hover` is on, but no node carries a `title`, so nothing shows on
hover. To add tooltips, set `title` on the nodes (Vis.js renders it as plain text or an
element) in the service or route.

---

## The Explore Graph (`exploreGraph`)

`ExploreGraphView(mode="hub" | "entity", entity_uid="", entity_type="", standalone=True, height="260px")`
in `ui/explore/graph.py`, driven by `exploreGraph(mode, entity_uid, entity_type)`:

| | `relationshipGraph` | `exploreGraph` |
|---|---|---|
| **Data** | `/api/{domain}/{uid}/lateral/graph?depth=` | hub: `GET /api/explore/graph`; entity: `/api/{ku,ps}/{uid}/lateral/graph?depth=2` |
| **Modes** | entity-centered | hub (the "You" node + studying Kus + in-progress PSes) or entity |
| **Where** | detail pages | the `/explore/library` sidebar (hub mode; its one caller passes no entity), `/explore/graph` |
| **Extras** | depth select | filter tabs (`setFilter('all' / 'learning' / 'saved')` dim non-matching nodes to 0.15 opacity); `expandGraph()` opens a full-screen overlay on `document.body` with a second network (Escape or the backdrop closes it) |
| **Click** | `node.url` | `node.url` in entity mode, else `/explore/{ku,ps}/{id}` |

The overlay exists because the sidebar is `overflow:hidden` inside a transformed column, so
the sidebar network can't grow past it; `expandGraph` builds a second network at the
`exploreExpanded` profile.

⚠ `render_explore_sidebar_page` mounts the component with `x_init="init()"` on top of the
component's own `init()`, so it loads twice. That's the same defect as `RelationshipGraphView`,
and it's logged.

---

## Depth Control

The graph grows fast with depth, so the UI offers 1–3 and defaults to 2.

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
    Div(id=f"network-{uid}", cls="w-full h-96"),
    **{"x-data": f"relationshipGraph('{uid}', 'tasks', 2)"},
)
```

The component's `changeDepth` method sets `depth` and reloads.
The select must sit **inside** the component's root element; Alpine doesn't bind a directive
outside any component tree.

**The server does not cap depth.** `get_graph(..., depth: int = 2, ...)` accepts any integer,
and the backend interpolates it into `*1..{depth}`. "1–3" is a UI convention and a docstring
recommendation, not an enforced limit. A clamp belongs in the route (validation → 400)
before anything sends larger values.

---

## Blocking Chain and Alternatives (not Vis.js)

Two of the section's three views are HTML, not a canvas:

- `BlockingChainView(entity_uid, entity_type)` HTMX-loads `GET .../lateral/chain`, which
  answers `render_chain_fragment(...)`: blockers by depth (`get_blocking_chain`,
  `max_depth=10` by default).
- `AlternativesComparisonGrid(entity_uid, entity_type)` HTMX-loads
  `GET .../lateral/alternatives/compare`, which answers `render_alternatives_fragment(...)`: a
  table whose criteria rows are fixed (`timeframe`, `difficulty`, `resources`) plus the edge's
  `tradeoffs` / `comparison_criteria`. No writer sets the three criteria today, so those rows
  read `N/A`.

Both reload on `relationships-changed from:body`.
