# vis-network Reference: Best Practices, Anti-Patterns, Checklist & Troubleshooting

> On-demand reference for the [`vis-network`](SKILL.md) skill. SKILL.md holds the surfaces, the quick start and the decision trees; this file holds the working rules, the integration checklist and troubleshooting, each tied to the live code.

---

## Best Practices

### 1. Use `EntityRelationshipsSection` for a Detail Page

```python
from ui.patterns.relationships import EntityRelationshipsSection

EntityRelationshipsSection(entity_uid=task.uid, entity_type="tasks", authoring=True)
```

- It renders all three views plus the authoring panel, in the shared `Accordion`.
- Every surface refreshes off the one `relationships-changed` event.
- `authoring=True` is a guarded no-op on a type the `EntityPicker` doesn't support
  (`PICKER_TYPES`: the six Activity types), so the call is safe on Ku/LP pages.

### 2. Don't Load Vis.js Yourself

`build_head()` (`ui/layouts/base_page.py`) already emits the vendored
`/static/vendor/vis-network/vis-network.min.js` and `.css` on every `BasePage` / `AuthPage`.
A second tag reloads a 476 KB library, and a CDN tag drifts from the pinned v9.1.9.

### 3. Size the Canvas

The canvas element needs a real height (`h-96` on the detail pages, `260px` default in the
Explore sidebar). Vis.js fills the box it gets, and an auto-height `div` gives it nothing.

### 4. Use the Shared Helpers and Profiles

Build options with `SKUEL.graph.buildOptions(SKUEL.graph.PROFILES.<profile>)`, style with
`styleEdgesByConfidence` / `styleNodes` / `styleEdges`, and navigate with `attachClickNav`.
A new surface adds a profile to `PROFILES`; it doesn't copy an options literal.

### 5. Colors Come from `RelationshipColor`

Edge colors are set server-side by `RelationshipColor.for_type` (`core/utils/palette.py`). Add
a type's color there, not in a JavaScript map, and every graph picks it up.

### 6. Pass Both Ownership Arguments

A service call that reads a user-owned entity's graph passes `user_uid` **and**
`domain_service`. With a verifier the ownership check needs the user, so omitting `user_uid`
reads without enforcement. `domain_service=None` is correct only for shared curriculum
(ku/ps/lp) — the center must then be a Ku, PathStep or LearningPath (any other uid answers
as missing), and a write with it is held to curriculum endpoints, behind the routes' TEACHER
gate.

---

## Anti-Patterns

### 1. `x-init="init()"` on a Component That Has `init()`

```python
# ❌ Alpine already calls init(); this calls it a second time (two fetches, measured)
Div(Div(id=f"network-{uid}"), **{"x-data": f"relationshipGraph('{uid}', 'tasks', 2)", "x-init": "init()"})

# ✅ let Alpine call it
Div(Div(id=f"network-{uid}"), **{"x-data": f"relationshipGraph('{uid}', 'tasks', 2)"})
```

`RelationshipGraphView` and the Explore sidebar still carry this defect (logged); don't copy it.

### 2. Looking the Canvas Up by `x-ref`

`relationshipGraph.renderNetwork` does `document.getElementById('network-' + entity_uid)`.
A container with only `x-ref="container"` is never found: the console logs
`Network container not found` and nothing draws.

### 3. Controls Outside the Component

A `<select x-on:change="changeDepth(...)">` placed beside the `x-data` element instead of
inside it is never bound, so changing it does nothing and no error appears.

### 4. Building URLs from `node.type`

`node.type` is a Neo4j label. Use `node.url`, resolved by the route with
`entity_detail_href`.

### 5. Relying on the Server to Cap Depth

Nothing clamps `depth` on `GET .../lateral/graph`. Keep every surface at 1–3, and add a route
validator (→ 400) before exposing a larger value.

### 6. Hand-Rolling a Per-Domain Lateral Service

The per-domain wrappers (`TasksLateralService`, …) were deleted when lateral relationships
were unified. There is one `LateralRelationshipService` (reached through
`services.lateral_orchestrator`); a new domain never gets its own.

---

## Integration Checklist

Adding lateral relationships and the graph to a new domain.

### Step 1: Register the Routes

Add one entry to `_LATERAL_DOMAINS` in `adapters/inbound/lateral_routes.py`. The loop builds
the `LateralRouteFactory` for it:

```python
_LATERAL_DOMAINS: list[tuple[str, str, str | None]] = [
    ...
    ("new_domain", "NewDomainEntity", "new_domain"),   # 3rd item: ownership-verifier key; None = shared
]
```

**Verify:** `GET /api/new_domain/{uid}/lateral/graph?depth=1` answers JSON.

### Step 2: If the Domain Is User-Owned, Wire Its Verifier

The third tuple item is only a lookup key into
`LateralRelationshipsOrchestrator._domain_services`, a fixed map built from constructor
parameters (`core/orchestrator/lateral_relationships_orchestrator.py`). An unregistered key makes
`get_domain_service()` return `None` **silently**, which the factory reads as "shared, no
ownership check": every authenticated user could read the domain's graphs. Add the service
to the orchestrator's constructor and map, and wire it in the composition root.

**Verify:** a foreign entity's `.../lateral/graph` answers 404
(`tests/integration/routes/test_lateral_route_ownership.py` is the model).

### Step 3: Mount the Section

In the domain's detail view (a `ui/{domain}/` renderer, not the route):

```python
EntityRelationshipsSection(entity_uid=entity.uid, entity_type="new_domain")
```

Add `authoring=True` only if the type is in `PICKER_TYPES`.

### Step 4: Check It in the Browser

1. Open the detail page and find "Relationships".
2. The **Relationship Network** panel is open by default; the graph draws.
3. Click a node: it navigates to that node's `url` (the center node doesn't navigate).
4. With authoring: add a relationship; the chain, the alternatives, the manage list and the
   graph all refresh without a reload.
5. The console shows no `Network container not found` and no `Vis.js Network library not loaded`.

---

## Troubleshooting

### Graph Doesn't Render

`RelationshipGraphView` renders no element for the component's `error` state, so a failed
load shows only in the console. Read the console first.

| Symptom | Cause | Fix |
|---------|-------|-----|
| Console: `Network container not found: network-<uid>` | canvas `id` doesn't match `network-{entity_uid}` | give the canvas that id |
| Console: `Vis.js Network library not loaded` | `vis` missing on the page | the page isn't built on `BasePage` / `build_head()` |
| Blank box, request OK | canvas has no height | give it `h-96` or an explicit height |
| Nothing happens, no request | the `x-data` expression names an unregistered component, or the markup sits outside any `x-data` | check the component name and that `skuel.js` loaded |

### Request Fails

| Symptom | Cause | Fix |
|---------|-------|-----|
| 404 on `.../lateral/graph` for your own entity | domain not in `_LATERAL_DOMAINS` (no route), or, on an Activity domain, the uid is wrong | add the entry; check the uid |
| 404 on someone else's entity (Activity domains) | the ownership check working (not-found, never forbidden) | expected |
| 400 `Invalid relationship type` | a `?types=` value that isn't a `RelationshipName` value | pass enum values, comma-separated |
| Graph shows only the center dot | no lateral edges within `depth` — or, on `ku`/`ps`/`lp`, a uid that doesn't exist (no existence check there; the center's label is then the uid itself) | check the uid; otherwise expected |

### Graph Is Slow

- Keep depth at 2; depth 3 is the UI's maximum for a reason, and nothing server-side stops more.
- A very large neighborhood (hundreds of nodes) calls for `barnesHut` in a new profile, not
  for editing `relationship` in place.
- Check the traversal with `PROFILE` on the Cypher in `LateralRelationshipBackend`; the
  anchor `{uid: $uid}` must hit the uid index.

---

## Tests

- `tests/unit/test_lateral_graph_queries.py`: service graph and ownership gate (`TestOwnershipGate`)
- `tests/integration/routes/test_lateral_route_ownership.py`: foreign entity → 404, owner → 200, curriculum → 200
- `tests/integration/routes/test_curriculum_lateral_write_gate.py`: curriculum writes — MEMBER → 403, TEACHER → 201, a private endpoint answers as a missing one
