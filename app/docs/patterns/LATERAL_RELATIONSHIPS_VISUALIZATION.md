---
title: Lateral Relationships Visualization Pattern
updated: '2026-07-29'
category: patterns
related_skills:
- neo4j-cypher-patterns
- vis-network
related_docs: []
---
# Lateral Relationships Visualization Pattern

**Date:** 2026-02-01
**Status:** Implemented - Phase 5 Complete
**Pattern Type:** UI Component Architecture

---
## Related Skills

For implementation guidance, see:
- [@neo4j-cypher-patterns](../../.claude/skills/neo4j-cypher-patterns/SKILL.md)
- [@vis-network](../../.claude/skills/vis-network/SKILL.md)

## Purpose

Provides interactive visualization of lateral relationships across all 9 SKUEL domains through a unified component architecture with HTMX lazy loading and Vis.js force-directed graphs.

---

## Authoring (add / delete) — live on all 6 Activity domains

The visualizations are now backed by **authoring**, not read-only. Two things landed with the task-relationships-authoring arc:

1. **The chain + alternatives readers now render.** `BlockingChainView` and `AlternativesComparisonGrid` HTMX-load `/api/{domain}/{uid}/lateral/chain` and `.../alternatives/compare`, which now return **HTML fragments** (`render_chain_fragment` / `render_alternatives_fragment`) instead of JSON — fixing all domains that mount `EntityRelationshipsSection`. (The graph route stays JSON; Vis.js consumes it directly.)

2. **`EntityRelationshipsSection(..., authoring=True)`** prepends a "Manage Relationships" panel: an **Add-relationship modal** (`ui/patterns/relationships/add_modal.py`) whose four sub-forms POST directly to the existing `POST /api/{domain}/{uid}/lateral/{blocks,prerequisites,alternatives,complementary}` routes, and a flat, deletable edge list (`GET .../lateral/manage` → `render_lateral_manage_fragment`) whose "×" buttons drive the existing `DELETE .../lateral/{type}/{target_uid}` route. Authoring is gated to the entity types the `EntityPicker` supports (`PICKER_TYPES` — the six Activity types: task/goal/habit/event/choice/principle) and is enabled on all six Activity detail pages. Curriculum KU/PS/LP stay read-only (not in `PICKER_TYPES`; `authoring=True` is a guarded no-op there).

**One refresh event.** Every lateral write (create/delete) additively returns `HX-Trigger: relationships-changed` (via the boundary `_headers` path). The chain/alternatives/manage containers listen with `hx_trigger="load, relationships-changed from:body"`; the Vis.js graph listens with `x-on:relationships-changed.window="loadGraph(depth)"`. No full reload; every surface re-syncs off one event.

**Ownership + cycles** are enforced by the shared `LateralRelationshipService` (both-endpoint `verify_ownership` → 404, and `spec.check_cycles` for BLOCKS/PREREQUISITE_FOR). Note the shared constraints inherited by authoring: BLOCKS requires a shared parent, ALTERNATIVE_TO requires equal depth.

**DEPENDS_ON is separate.** The lightweight scheduling edge `(Task)-[:DEPENDS_ON]->(Task)` has its own task-scoped Dependencies section (`GET|POST /tasks/{uid}/dependencies*`) — kept deliberately distinct from the annotated lateral BLOCKS edge (see the task-relationships-authoring plan, decision R1).

---

## Problem

**Before Phase 5:**
- Lateral relationships existed in the graph but weren't visible to users
- No way to visualize blocking dependencies, alternatives, or relationship networks
- Each domain would need custom visualization code (duplication)
- Complex graph queries would slow down detail page loads

**Needed:**
- Unified visualization component for all domains
- Interactive graph exploration (drag, zoom, navigate)
- Performance optimization (lazy loading)
- Consistent UX across all 9 domains

---

## Solution

### Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  EntityRelationshipsSection (Main Orchestrator)        │
│  - 3 collapsible sections (Alpine.js state)            │
│  - HTMX lazy loading (deferred data fetch)             │
│  - Responsive layout (mobile + desktop)                │
└─────────────────┬───────────────────────────────────────┘
                  │ composes
    ┌─────────────┼─────────────┬─────────────────────────┐
    │             │             │                         │
┌───▼────┐  ┌────▼─────┐  ┌───▼──────────────────────┐  │
│Blocking│  │Alternatives│ │RelationshipGraphView     │  │
│ChainView│  │Comparison │ │(Vis.js Integration)      │  │
│         │  │Grid       │ │- Force-directed layout   │  │
│Vertical │  │Side-by-   │ │- Interactive controls    │  │
│flow     │  │side table │ │- Color-coded edges       │  │
└────┬────┘  └────┬──────┘ └───┬──────────────────────┘  │
     │            │            │                         │
     │ HTMX       │ HTMX       │ HTMX + Alpine          │
     │ hx-get     │ hx-get     │ x-data="relationshipGraph"
     │            │            │                         │
┌────▼────────────▼────────────▼─────────────────────────▼┐
│  API Endpoints (LateralRouteFactory)                    │
│  - GET /api/{domain}/{uid}/lateral/chain                │
│  - GET /api/{domain}/{uid}/lateral/alternatives/compare │
│  - GET /api/{domain}/{uid}/lateral/graph                │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│  LateralRelationshipService                             │
│  - get_blocking_chain(uid, max_depth=3)                 │
│  - get_alternatives_with_comparison(uid)                │
│  - get_relationship_graph(uid, depth=1, types=None)     │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│  Neo4j Graph Database                                   │
│  - BLOCKS, PREREQUISITES, ALTERNATIVES, etc.            │
│  - Cypher traversal queries                             │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation Pattern

### 1. Main Component: EntityRelationshipsSection

**File:** `ui/patterns/relationships/relationship_section.py`

**Usage:**
```python
from ui.patterns.relationships import EntityRelationshipsSection

# Add to any domain detail page
EntityRelationshipsSection(
    entity_uid=task.uid,
    entity_type="tasks",
    show_blocking_chain=True,    # Optional: default True
    show_alternatives=True,       # Optional: default True
    show_graph=True,              # Optional: default True
)
```

**Responsibilities:**
- Orchestrate 3 sub-components
- MonsterUI Accordion for collapsible state (multiple=True, graph open by default)
- Provide consistent layout across domains
- Handle empty states gracefully

**Key Features:**
```python
def EntityRelationshipsSection(
    entity_uid: EntityUID,
    entity_type: str,
    show_blocking_chain: bool = True,
    show_alternatives: bool = True,
    show_graph: bool = True,
) -> Div:
    """
    Creates unified relationships section with 3 collapsible subsections.

    Uses MonsterUI Accordion (multiple=True) — each subsection is an
    AccordionItem with built-in chevron icons and collapse transitions.
    Relationship Network starts open=True by default.
    """
```

---

### 2. Sub-Components

#### BlockingChainView

**File:** `ui/patterns/relationships/blocking_chain.py`

**Purpose:** Vertical flow chart showing transitive blocking dependencies

**HTMX Endpoint:**
```python
"hx-get": f"/api/{entity_type}/{entity_uid}/lateral/chain"
```

**Layout:**
```
Depth 0: [Current Entity]
           ↓ BLOCKS
Depth 1: [Blocker 1] [Blocker 2]
           ↓ BLOCKS
Depth 2: [Root Blocker 1] [Root Blocker 2]
```

**Features:**
- Depth-based vertical layout
- Expandable depth levels (1-3)
- Shows reason/metadata on hover
- Empty state: "No blocking relationships"

---

#### AlternativesComparisonGrid

**File:** `ui/patterns/relationships/alternatives_grid.py`

**Purpose:** Side-by-side comparison of alternative approaches

**HTMX Endpoint:**
```python
"hx-get": f"/api/{entity_type}/{entity_uid}/lateral/alternatives/compare"
```

**Layout:**
```
┌──────────────┬──────────────┬──────────────┐
│ Current      │ Alternative 1│ Alternative 2│
├──────────────┼──────────────┼──────────────┤
│ Field 1      │ Value        │ Value        │
│ Field 2      │ Value        │ Value        │
│ Differences  │ Highlighted  │ Highlighted  │
└──────────────┴──────────────┴──────────────┘
```

**Features:**
- Configurable comparison fields
- Highlights differences
- Metadata display (criteria, confidence)
- Empty state: "No alternatives found"

---

#### RelationshipGraphView

**File:** `ui/patterns/relationships/relationship_graph.py`

**Purpose:** Interactive Vis.js force-directed graph

**HTMX Endpoint:**
```python
"hx-get": f"/api/{entity_type}/{entity_uid}/lateral/graph?depth=2"
```

**Alpine Component:** `static/js/skuel.js` (line 1796)
```javascript
Alpine.data('relationshipGraph', function(entity_uid, entity_type, initial_depth) {
    return {
        depth: initial_depth || 1,
        network: null,

        init() {
            // Fetch graph data via HTMX
            // Initialize Vis.js Network
            // Set up physics simulation
            // Attach event handlers
        },

        changeDepth(newDepth) {
            // Re-fetch graph with new depth
            // Update visualization
        },

        handleNodeClick(nodeId) {
            // Navigate to entity detail page
            window.location.href = `/${entity_type}/${nodeId}`;
        }
    }
});
```

**Graph Features:**
- **Physics:** Force-directed layout (Barnes-Hut simulation)
- **Interactions:**
  - Drag nodes: Reposition entities
  - Zoom: Mouse wheel or pinch gesture
  - Pan: Drag canvas background
  - Click node: Navigate to detail page
- **Visual Design:**
  - Color-coded edges:
    - Red: BLOCKS (dependency blocking)
    - Orange: PREREQUISITES (knowledge requirements)
    - Blue: ALTERNATIVES (mutually exclusive)
    - Green: COMPLEMENTARY (synergistic pairing)
    - Purple: SIBLING (same parent)
    - Gray: RELATED_TO (general association)
  - Node labels: Entity titles
  - Edge labels: Relationship metadata

**Depth Control:**
```html
<select x-model="depth" @change="changeDepth($event.target.value)">
    <option value="1">1 Level</option>
    <option value="2">2 Levels</option>
    <option value="3">3 Levels</option>
</select>
```

---

### 3. Service Layer

**File:** `core/services/lateral_relationships/lateral_relationship_service.py`

#### get_blocking_chain()

**Purpose:** Transitive closure of blocking dependencies

**Cypher Query:**
```cypher
MATCH path = (start {uid: $uid})<-[:BLOCKS*1..3]-(blocker)
WITH path, length(path) as depth
RETURN DISTINCT blocker.uid, blocker.title, depth
ORDER BY depth, blocker.created_at
```

**Return Format:**
```python
{
    "uid": "task_abc",
    "entity_type": "tasks",
    "chain": [
        {
            "depth": 1,
            "entities": [
                {"uid": "task_def", "title": "Setup env", "reason": "Need env first"}
            ]
        },
        {
            "depth": 2,
            "entities": [
                {"uid": "task_ghi", "title": "Install Python"}
            ]
        }
    ]
}
```

---

#### get_alternatives_with_comparison()

**Purpose:** Side-by-side comparison of alternatives

**Cypher Query:**
```cypher
MATCH (entity {uid: $uid})-[r:ALTERNATIVE_TO]-(alt)
RETURN alt, r.criteria, r.confidence
ORDER BY r.confidence DESC
```

**Return Format:**
```python
{
    "current": {"uid": "task_abc", "title": "Learn React", ...},
    "alternatives": [
        {
            "entity": {"uid": "task_def", "title": "Learn Vue", ...},
            "criteria": "component model",
            "confidence": 0.85,
            "differences": {
                "complexity": {"current": "high", "alternative": "low"},
                "ecosystem": {"current": "mature", "alternative": "growing"}
            }
        }
    ]
}
```

---

#### get_relationship_graph()

**Purpose:** Vis.js network format for interactive visualization

**Cypher Query:**
```cypher
MATCH path = (start {uid: $uid})-[r*1..{depth}]-(related)
WHERE type(r) IN $relationship_types
RETURN DISTINCT related, r
```

**Return Format (Vis.js):**
```python
{
    "nodes": [
        {"id": "task_abc", "label": "Current Task", "group": "tasks"},
        {"id": "task_def", "label": "Blocker", "group": "tasks"}
    ],
    "edges": [
        {
            "from": "task_def",
            "to": "task_abc",
            "label": "BLOCKS",
            "color": {"color": "#ef4444"},  # Red
            "metadata": {"reason": "Dependencies"}
        }
    ]
}
```

---

### 4. API Layer

**File:** `adapters/inbound/route_factories/lateral_route_factory.py`

**Pattern:** Factory registers a full set of lateral routes per domain, sharing the universal `LateralRelationshipService` across all 9 domains. Ownership verification for Activity Domains is delegated via a narrow `OwnershipVerifier` protocol.

```python
class LateralRouteFactory:
    def __init__(
        self,
        domain: str,  # "tasks", "goals", "habits", "events", "choices", "principles", "ku", "ps", "lp"
        lateral_service: "LateralRelationshipOperations",
        entity_name: str,  # "Task", "Goal", …
        domain_service: "OwnershipVerifier | None" = None,  # None for shared/curriculum
    ) -> None:
        self.domain = domain
        self.lateral_service = lateral_service
        self.entity_name = entity_name
        self.domain_service = domain_service

    def register_routes(self, _app, rt) -> list[Any]:
        return [
            self._create_blocking_routes(rt),
            self._create_prerequisite_routes(rt),
            self._create_alternative_routes(rt),
            self._create_complementary_routes(rt),
            self._create_sibling_route(rt),
            self._create_delete_route(rt),
            self._create_chain_route(rt),
            self._create_comparison_route(rt),
            self._create_graph_route(rt),
        ]
```

**OwnershipVerifier protocol** (`core/ports/service_protocols.py`): single-method structural protocol (`verify_ownership(uid, user_uid) -> Result[Any]`) satisfied by every Activity Domain facade via `BaseServiceInterface[T]`. Replaces the old `domain_service: Any | None` threading.

**Route Registration:** `adapters/inbound/lateral_routes.py` — goes through `LateralRelationshipsOrchestrator`, which owns the 6 Activity Domain services and exposes `get_domain_service(slug) -> OwnershipVerifier | None` (returns `None` for curriculum domains).

```python
def create_lateral_api_routes(
    app: FastHTMLApp, rt: RouteDecorator, orchestrator: "LateralRelationshipsOrchestrator"
) -> list[Any]:
    all_routes: list[Any] = []
    for domain, entity_name, service_attr in _LATERAL_DOMAINS:
        domain_service = orchestrator.get_domain_service(service_attr) if service_attr else None
        factory = LateralRouteFactory(
            domain=domain,
            lateral_service=orchestrator.lateral_service,
            entity_name=entity_name,
            domain_service=domain_service,  # None for ku/ps/lp
        )
        all_routes.extend(factory.register_routes(app, rt))
    return all_routes
```

The `orchestrator.lateral_service` property is the single documented layering exception: `LateralRouteFactory` lives in the inbound adapter layer and cannot import a core orchestrator, so routes hand it the raw service instead.

---

## Integration Pattern

### Step 1: Add to Detail Page

```python
# In any domain UI file (e.g., tasks_ui.py)
from ui.patterns.relationships import EntityRelationshipsSection

@rt("/tasks/{uid}")
async def task_detail_page(request: Any, uid: str) -> Any:
    # ... existing detail page code ...

    content = Div(
        # Existing content (task details, etc.)
        Card(...),

        # Phase 5: Lateral Relationships Section
        EntityRelationshipsSection(
            entity_uid=uid,
            entity_type="tasks",
        ),

        cls=f"{Container.NARROW} {Spacing.PAGE}",
    )

    return BasePage(content=content, ...)
```

---

### Step 2: Nothing to Implement — the Methods Are Already Shared

The 3 read methods live on the one domain-agnostic `LateralRelationshipService` and take an entity uid, so **there is no service to write.** Per-domain wrapper services were deleted in `e8818dc26`; do not recreate one.

```python
# core/services/lateral_relationships/lateral_relationship_service.py
await services.lateral.get_blocking_chain(uid, max_depth=10)
await services.lateral.get_alternatives_with_comparison(uid, comparison_fields=None)
await services.lateral.get_relationship_graph(uid, depth=2, relationship_types=None)
```

Ownership is enforced by passing the domain's `OwnershipVerifier` (see [RELATIONSHIPS_ARCHITECTURE.md § Per-Domain Wiring](/docs/architecture/RELATIONSHIPS_ARCHITECTURE.md)), not by a wrapper method.

---

### Step 3: Register Routes

Add one entry to `_LATERAL_DOMAINS` in `adapters/inbound/lateral_routes.py` — the loop builds the factory for every domain:

```python
_LATERAL_DOMAINS: list[tuple[str, str, str | None]] = [
    ...
    ("new_domain", "NewDomainEntity", "new_domain"),  # None = shared/curriculum, no ownership check
]
```

---

## Performance Optimization

### HTMX Lazy Loading

**Why:** Detail pages load instantly without expensive graph queries

**Pattern:**
```python
from ui.components import Accordion, AccordionItem

# SKUEL Accordion (Alpine.js-driven, ADR-071) handles collapse/expand, chevrons, and transitions
Accordion(
    AccordionItem("Blocking Dependencies", BlockingChainView(uid, etype)),
    AccordionItem("Alternative Approaches", AlternativesComparisonGrid(uid, etype)),
    AccordionItem("Relationship Network", RelationshipGraphView(uid, etype), open=True),
    multiple=True,  # Each section toggles independently
)
```

HTMX lazy loading still works inside AccordionItems — child components use
`hx-get` with `hx-trigger="intersect once"` so data loads only when expanded.

**Benefits:**
- Zero upfront cost (no graph queries on page load)
- Data fetched only when user expands section
- `intersect once` = loads when scrolled into view
- Prevents duplicate requests

---

### Depth Limiting

**Why:** Prevent exponential graph explosion

**Pattern:**
```python
# Service layer enforces max depth
async def get_blocking_chain(self, uid: str, max_depth: int = 3):
    if max_depth > 3:
        max_depth = 3  # Hard limit

    # Cypher uses bounded path: -[:BLOCKS*1..{max_depth}]-
```

**Trade-offs:**
- Depth 1: ~10 nodes (fast, limited context)
- Depth 2: ~50 nodes (good balance)
- Depth 3: ~200 nodes (comprehensive, slower)

---

### Vis.js Physics Optimization

**Pattern:** Disable physics after stabilization

```javascript
network.on("stabilizationIterationsDone", function() {
    network.setOptions({ physics: false });
});
```

**Benefits:**
- Smooth initial animation (force-directed layout)
- Static graph after stabilization (better performance)
- User can still drag nodes (physics re-enabled on drag)

---

## Testing Pattern

### Unit Tests

**File:** `tests/unit/test_lateral_graph_queries.py`

```python
class TestGetBlockingChain:
    async def test_empty_chain(self):
        """Entity with no blockers returns empty chain."""

    async def test_single_level_chain(self):
        """Entity with 1 blocker returns depth=1."""

    async def test_multi_level_chain(self):
        """Transitive closure returns all depths."""

class TestGetAlternativesWithComparison:
    async def test_no_alternatives(self):
        """Entity with no alternatives returns empty list."""

    async def test_with_comparison(self):
        """Returns alternatives with field comparisons."""

class TestGetRelationshipGraph:
    async def test_isolated_entity(self):
        """Entity with no relationships returns single node."""

    async def test_complex_graph(self):
        """Returns Vis.js format with nodes + edges."""
```

---

### Integration Tests

**Manual Testing Checklist:**

1. **Page Load**
   - Navigate to detail page
   - Verify Relationships section appears
   - Verify no console errors

2. **HTMX Loading**
   - Expand each subsection
   - Verify HTMX request fires (Network tab)
   - Verify content loads in < 500ms

3. **Graph Interactions**
   - Drag nodes (repositions)
   - Zoom (mouse wheel)
   - Pan (drag canvas)
   - Click node (navigates to detail page)

4. **Mobile Responsive**
   - Test at 375px width
   - Verify collapsible sections work
   - Verify graph renders correctly

---

## Common Patterns

### Pattern 1: Hide Section if Not Applicable

```python
# Hide alternatives for domains that don't use them
EntityRelationshipsSection(
    entity_uid=journal.uid,
    entity_type="journals",
    show_alternatives=False,  # Journals don't have alternatives
)
```

---

### Pattern 2: Domain-Specific Relationship Types

```python
# Filter graph to show only specific relationship types
await lateral_service.get_relationship_graph(
    uid=habit_uid,
    depth=2,
    types=["STACKS_WITH", "COMPLEMENTARY_TO"]  # Habit-specific
)
```

---

### Pattern 3: Custom Comparison Fields

```python
# Override default comparison fields
await lateral_service.get_alternatives_with_comparison(
    uid=goal_uid,
    fields=["target_date", "priority", "domain"]  # Goal-specific fields
)
```

---

## Migration Guide

### Adding Visualization to New Domain

**Checklist:**

1. ✅ Add one entry to `_LATERAL_DOMAINS` in `lateral_routes.py` (the loop wires `LateralRouteFactory`)
2. ✅ Add `EntityRelationshipsSection` to detail page
3. ✅ Import in UI file: `from ui.patterns.relationships import EntityRelationshipsSection`
4. ✅ Test in browser (expand sections, test graph)

No service to create and no unit tests for wrapper methods — the 3 read methods are shared on `services.lateral` and already covered.

---

## Troubleshooting

### Issue: Graph not rendering

**Cause:** Vis.js library not loaded

**Fix:** Verify `base_page.py` includes:
```python
Link(rel="stylesheet", href="/static/vendor/vis-network/vis-network.min.css"),
Script(src="/static/vendor/vis-network/vis-network.min.js"),
```

---

### Issue: HTMX requests return 404

**Cause:** Routes not registered

**Fix:** Check `lateral_routes.py` includes domain factory

---

### Issue: Alpine collapsible not working

**Cause:** Missing `x-collapse` directive

**Fix:** Verify Alpine.js loaded and `x-collapse` plugin available

---

## Explore Sidebar Graph (April 2026)

The lateral relationship graph infrastructure was extended to power the **Explore sidebar graph** — an interactive Vis.js graph hero element in the Explore sidebar.

**Distinction from `EntityRelationshipsSection`:**

| | EntityRelationshipsSection | ExploreGraphView |
|---|---|---|
| **Location** | Domain detail pages (Tasks, Goals, etc.) | Explore sidebar (`/explore`, `/explore/ku/{uid}`, `/explore/ps/{uid}`) |
| **Component** | `ui/patterns/relationships/` | `ui/explore/graph.py` |
| **Alpine** | `relationshipGraph` | `exploreGraph` |
| **Modes** | Entity-centered only | Hub (learning universe) + Entity-centered |
| **Click nav** | `/{domain}/{id}` | `/explore/{type}/{id}` |
| **Extras** | Blocking chain + alternatives grid | Filter tabs (All/Learning/Saved) + full-screen JS overlay |
| **Width** | 384px height in content area | 260px height in 384px sidebar, expandable to full screen via JS overlay on `document.body` |

**Key files:** `ui/explore/graph.py`, `exploreGraph` component in `static/js/skuel.js`, `GET /api/explore/graph` endpoint in `adapters/inbound/explore_ui.py`.

## See Also

- `/docs/architecture/RELATIONSHIPS_ARCHITECTURE.md` - Core graph modeling — lateral types, service API, Cypher patterns
- `/docs/ui/COMPONENT_CATALOG.md` - ExploreGraphView component documentation
- `/PHASE5_COMPLETE.md` - Implementation completion details
- `/PHASE5_MANUAL_QA_CHECKLIST.md` - Testing guide
- `/.claude/skills/ui-browser/` - Alpine.js + HTMX patterns
- `/docs/llms.txt/fasthtml-llms.txt` - FastHTML + HTMX patterns

---

**Status:** ✅ Complete - All 9 domains integrated + Explore sidebar graph
**Test Coverage:** 100% (40 automated tests)
**Deployment:** Production-ready
**Last Updated:** 2026-04-04
