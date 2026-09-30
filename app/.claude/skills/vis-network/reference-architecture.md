# vis-network Reference: SKUEL Integration Architecture & Data Format

> On-demand reference for the [`vis-network`](SKILL.md) skill. SKILL.md holds the surfaces, the quick start and the decision trees; this file follows one graph from the Cypher to the canvas, then documents the JSON it carries.

---

## The Layers

```
Neo4j ── LateralRelationshipBackend.get_relationship_graph   (Cypher, adapters/persistence)
   │ rows
   ▼
LateralRelationshipService.get_relationship_graph           (ownership, nodes + edges, colors)
   │ Result[RelationshipGraphData]
   ▼
GET /api/{domain}/{uid}/lateral/graph                        (LateralRouteFactory; adds node url)
   │ JSON
   ▼
relationshipGraph (Alpine) + SKUEL.graph helpers             (static/js/skuel.js → new vis.Network)
```

---

### Layer 1: Cypher (`LateralRelationshipBackend`)

`adapters/persistence/neo4j/backends/collab_backends.py`, pure Cypher: SKUEL001 keeps
APOC out of every domain query.

```cypher
MATCH path = (center {uid: $uid})-[r:{type_filter}*1..{depth}]-(related)
WITH center, r, related, length(path) as depth_level
RETURN DISTINCT
    center.uid as center_uid, center.title as center_title,
    labels(center)[0] as center_type, center.entity_type as center_entity_type,
    center.status as center_status,
    related.uid as related_uid, related.title as related_title,
    labels(related)[0] as related_type, related.entity_type as related_entity_type,
    related.status as related_status,
    [rel in r | {type: type(rel), from: startNode(rel).uid, to: endNode(rel).uid}] as relationships,
    depth_level
```

- The match is **undirected** (`-[…]-`), so the graph shows both sides of every edge.
- `type_filter` and `depth` are interpolated into the pattern. A variable-length bound
  cannot be a parameter. `type_filter` is built from `RelationshipName` values only, but
  `depth` is whatever `int` the route received; nothing clamps it.

### Layer 2: Service (`LateralRelationshipService.get_relationship_graph`)

```python
async def get_relationship_graph(
    self,
    entity_uid: EntityUID,
    depth: int = 2,
    relationship_types: list[RelationshipName] | None = None,   # None = every lateral type
    user_uid: UserUID | None = None,
    domain_service: OwnershipVerifier | None = None,             # None = shared content
) -> Result[RelationshipGraphData]:
```

- **Ownership** runs through `_verify_entity_access` only when **both** `user_uid` and
  `domain_service` are passed, and it checks the **center** entity only. The traversal
  itself is not owner-filtered. On the six Activity domains a foreign or missing center is a
  404, never a 403.
- On `ku` / `ps` / `lp` there is no verifier (`domain_service=None`), so **nothing checks
  that the center exists**. A missing uid answers 200 with a synthetic center-only graph
  (`label` = the uid, `type` / `status` `"unknown"`), indistinguishable from a real entity
  with no edges.
- With no related rows it returns the center node alone, so the canvas shows one dot.
- Edges are colored per type with `RelationshipColor.for_type` (`core/utils/palette.py`).

### Layer 3: Routes (`LateralRouteFactory`)

`adapters/inbound/lateral_routes.py` builds one factory per `_LATERAL_DOMAINS` entry
(`tasks`, `goals`, `habits`, `events`, `choices`, `principles`, `ku`, `ps`, `lp`):

```python
for domain, entity_name, service_attr in _LATERAL_DOMAINS:
    domain_service = orchestrator.get_domain_service(service_attr) if service_attr else None
    LateralRouteFactory(
        domain=domain,
        lateral_service=orchestrator.lateral_service,
        entity_name=entity_name,
        domain_service=domain_service,  # OwnershipVerifier; None for ku/ps/lp
        require_role=None if domain_service else _CURRICULUM_WRITE_ROLE,  # TEACHER
        user_service_getter=get_user_service,
    ).register_routes(app, rt)          # @rt registers — nothing is returned
```

Each factory registers 15 routes, every one threading `domain_service`. On `ku` / `ps` / `lp`
the five writes (the POSTs and the DELETE) are also TEACHER-gated, and the service refuses any
endpoint that is not a Ku, PathStep or LearningPath with the same 404 as a missing uid; the
reads stay open:

| Route | Method | Answers |
|-------|--------|---------|
| `.../lateral/{blocks,prerequisites,alternatives,complementary}` | POST | create; `HX-Trigger: relationships-changed` |
| `.../lateral/{relationship_type}/{target_uid}` | DELETE | delete; `HX-Trigger: relationships-changed` |
| `.../lateral/{blocking,blocked,prerequisites,alternatives,complementary,siblings}` | GET | JSON lists |
| `.../lateral/chain` | GET | **HTML** fragment (`render_chain_fragment`) |
| `.../lateral/alternatives/compare` | GET | **HTML** fragment (`render_alternatives_fragment`) |
| `.../lateral/manage` | GET | **HTML** fragment (the deletable edge list) |
| `.../lateral/graph` | GET | **JSON** in Vis.js shape |

The graph route:

```python
@rt(f"/api/{self.domain}/{{uid}}/lateral/graph", methods=["GET"])
@boundary_handler()
async def get_graph(
    request: Request, uid: str, depth: int = 2, types: str | None = None
) -> Result[RelationshipGraphData]:
    user_uid = require_authenticated_user(request)
    relationship_types = None
    if types:   # comma-separated RelationshipName values, e.g. REQUIRES_KNOWLEDGE,ENABLES_KNOWLEDGE
        try:
            relationship_types = [RelationshipName(t.strip()) for t in types.split(",")]
        except ValueError as e:
            return Result.fail(Errors.validation(f"Invalid relationship type: {e!s}"))
    result = await self.lateral_service.get_relationship_graph(
        EntityUID(uid), depth, relationship_types,
        user_uid=user_uid, domain_service=self.domain_service,
    )
    if result.is_error:
        return result
    for node in result.value["nodes"]:
        node["url"] = entity_detail_href(node.get("entity_type"), node["id"])   # None → not a link
    return Result.ok(result.value)
```

`lateral_routes.py` adds domain-specific routes beside the factory's: `stacks` (Habits),
`conflicts` (Events/Choices/Principles), `enables` / `enabled-by` (Ku). Those writers emit no
`HX-Trigger`.

### Layer 4: Presentation (`relationshipGraph` in `skuel.js`)

```javascript
Alpine.data('relationshipGraph', function(entity_uid, entity_type, initial_depth) {
    return {
        entity_uid: entity_uid, entity_type: entity_type,
        depth: initial_depth || 2,
        network: null, loading: false, error: null,

        init: function() { this.loadGraph(this.depth); },   // Alpine calls this — no x-init

        loadGraph: async function(depth) {
            // SKUEL.getJson rejects on non-2xx; the error becomes a user message
            var data = await window.SKUEL.getJson(
                '/api/' + this.entity_type + '/' + this.entity_uid + '/lateral/graph?depth=' + depth
            );
            this.renderNetwork(data);
        },

        renderNetwork: function(data) {
            var container = document.getElementById('network-' + this.entity_uid);   // by id
            if (this.network) this.network.destroy();                                 // re-render
            if (!window.SKUEL.graph.ready()) { this.error = 'Graph library not loaded'; return; }
            data.edges = window.SKUEL.graph.styleEdgesByConfidence(data.edges);
            var options = window.SKUEL.graph.buildOptions(window.SKUEL.graph.PROFILES.relationship);
            this.network = new vis.Network(container, data, options);
            window.SKUEL.graph.attachClickNav(this.network, data.nodes, this.entity_uid,
                function(node) { return node.url || null; });
        },

        changeDepth: function(newDepth) { this.depth = parseInt(newDepth); this.loadGraph(this.depth); }
    };
});
```

(Abridged: the live `loadGraph` wraps the fetch in `try/catch/finally` for `loading` and `error`.)

- The component defines **no `destroy()`**, so when HTMX removes its element, nothing tears
  the network down. `renderNetwork` destroys the previous instance only when it re-renders.
- `relationshipGraph` hands `vis.Network` plain arrays, so a change means a full re-render.
  (`exploreGraph` keeps its nodes in a `vis.DataSet`, `_visNodes`, and re-colors them in
  place when a filter tab changes.)

---

## Vis.js Data Format

`RelationshipGraphData` (`core/ports/query_types.py`) is
`{"nodes": list[dict[str, Any]], "edges": list[dict[str, Any]]}`: the vendor payload stays
untyped inside. What SKUEL puts in it:

### Node

```json
{
  "id": "task_write-tests_abc123",
  "label": "Write Unit Tests",
  "type": "Task",
  "entity_type": "task",
  "status": "active",
  "group": "center",
  "level": 0,
  "url": "/tasks/detail?uid=task_write-tests_abc123"
}
```

| Field | Source | Notes |
|-------|--------|-------|
| `id` | `uid` | required by Vis.js |
| `label` | `title`, else the uid | the text drawn under the dot |
| `type` | `labels(n)[0]` | a Neo4j label, **not** a route; never build a URL from it |
| `entity_type` | the node's `entity_type` property | what `entity_detail_href` reads |
| `status` | `status`, else `"unknown"` | |
| `group` | `"center"` or `"related"` | Vis.js groups; the click handler skips `"center"` |
| `level` | hop count (`0` for the center) | |
| `url` | added by the route | `None` for a type with no detail page |

No `title` is set, so Vis.js shows no hover tooltip.

### Edge

```json
{
  "from": "task_write-tests_abc123",
  "to": "task_setup-ci_xyz789",
  "label": "blocks",
  "arrows": "to",
  "color": {"color": "#EF4444"},
  "relationship_type": "BLOCKS"
}
```

`label` is the type lower-cased with spaces. Duplicates (same from, to and type) are
dropped. The browser then restyles every edge with `styleEdgesByConfidence`
(reference-patterns.md). It reads `edge.confidence` and `edge.priority`, which the service
doesn't set today, so every edge falls to the defaults (solid, width 2).

### Relationship Colors

`RelationshipColor` (`core/utils/palette.py`) is the one map; anything not listed gets
`DEFAULT`:

| Type | Hex |
|------|-----|
| `BLOCKS` | `#EF4444` (red) |
| `PREREQUISITE_FOR` | `#F59E0B` (orange) |
| `ALTERNATIVE_TO` | `#3B82F6` (blue) |
| `COMPLEMENTARY_TO` | `#10B981` (green) |
| `SIBLING` | `#8B5CF6` (purple) |
| `RELATED_TO` | `#6B7280` (gray) |
| anything else (`BLOCKED_BY`, `REQUIRES_PREREQUISITE`, …) | `#6B7280` (`DEFAULT`) |

```python
from core.utils.palette import RelationshipColor

RelationshipColor.for_type("BLOCKS")    # "#EF4444"
RelationshipColor.for_type("BLOCKED_BY")  # "#6B7280" — inverses fall to DEFAULT
```
