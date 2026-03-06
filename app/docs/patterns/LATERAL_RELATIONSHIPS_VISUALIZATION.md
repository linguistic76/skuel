---
title: Lateral Relationships Visualization Pattern
updated: '2026-02-02'
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
- [@neo4j-cypher-patterns](../../.claude/skills/neo4j-cypher-patterns/SKILL.md) - Graph queries and Cypher patterns
- [@vis-network](../../.claude/skills/vis-network/SKILL.md) - Vis.js Network visualization integration


## Purpose

Provides interactive visualization of lateral relationships across all 9 SKUEL domains through a unified component architecture with HTMX lazy loading and Vis.js force-directed graphs.

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
- Manage Alpine.js collapsible state
- Provide consistent layout across domains
- Handle empty states gracefully

**Key Features:**
```python
def EntityRelationshipsSection(
    entity_uid: str,
    entity_type: str,
    show_blocking_chain: bool = True,
    show_alternatives: bool = True,
    show_graph: bool = True,
) -> Div:
    """
    Creates unified relationships section with 3 collapsible subsections.

    Each subsection:
    - Alpine.js state: x-data="{ expanded: false }"
    - Collapsible animation: x-collapse
    - HTMX lazy loading: hx-get triggers on expand
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

**Pattern:** Factory creates 3 routes per domain

```python
class LateralRouteFactory:
    def __init__(
        self,
        app: Any,
        rt: Any,
        domain: str,  # "tasks", "goals", etc.
        lateral_service: Any,  # Domain lateral service
        entity_name: str,  # "Task", "Goal", etc.
    ):
        self.domain = domain
        self.lateral_service = lateral_service

    def create_routes(self) -> list[Any]:
        """Creates 3 standard routes for the domain."""
        return [
            self._create_chain_route(),
            self._create_comparison_route(),
            self._create_graph_route(),
        ]
```

**Route Registration:** `adapters/inbound/lateral_routes.py`
```python
def create_lateral_routes(app, rt, services):
    """Register lateral routes for all 9 domains."""

    # Activity (5) + Events
    tasks_factory = LateralRouteFactory(
        app=app, rt=rt, domain="tasks",
        lateral_service=services.tasks_lateral,
        entity_name="Task"
    )
    all_routes.extend(tasks_factory.create_routes())

    # ... repeat for goals, habits, events, choices, principles

    # Curriculum (3)
    ku_factory = LateralRouteFactory(
        app=app, rt=rt, domain="ku",
        lateral_service=services.ku_lateral,
        entity_name="KnowledgeUnit"
    )
    all_routes.extend(ku_factory.create_routes())

    # ... repeat for ls, lp

    return all_routes  # 92 total (27 base + 65 specialized)
```

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

        cls="container mx-auto p-6 max-w-4xl",
    )

    return BasePage(content=content, ...)
```

---

### Step 2: Verify Service Methods

Ensure domain lateral service implements the 3 required methods:

```python
# In {domain}_lateral_service.py
class TasksLateralService:
    def __init__(self, lateral_service: LateralRelationshipService):
        self.lateral_service = lateral_service

    async def get_blocking_chain(self, uid: str, max_depth: int = 3):
        """Delegates to core lateral service."""
        return await self.lateral_service.get_blocking_chain(uid, max_depth)

    async def get_alternatives_with_comparison(self, uid: str):
        """Delegates to core lateral service."""
        return await self.lateral_service.get_alternatives_with_comparison(uid)

    async def get_relationship_graph(self, uid: str, depth: int = 1):
        """Delegates to core lateral service."""
        return await self.lateral_service.get_relationship_graph(uid, depth)
```

---

### Step 3: Register Routes

Ensure domain is registered in `adapters/inbound/lateral_routes.py`:

```python
# Add factory for new domain
new_domain_factory = LateralRouteFactory(
    app=app,
    rt=rt,
    domain="new_domain",
    lateral_service=services.new_domain_lateral,
    entity_name="NewDomainEntity",
)
all_routes.extend(new_domain_factory.create_routes())
```

---

## Performance Optimization

### HTMX Lazy Loading

**Why:** Detail pages load instantly without expensive graph queries

**Pattern:**
```html
<!-- Section is collapsed by default -->
<div x-data="{ expanded: false }">
    <div @click="expanded = !expanded">Click to expand</div>

    <!-- Content loads ONLY when expanded -->
    <div x-show="expanded" x-collapse>
        <div hx-get="/api/tasks/task_abc/lateral/chain"
             hx-trigger="intersect once"
             hx-swap="outerHTML">
            Loading...
        </div>
    </div>
</div>
```

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

1. ✅ Create `{domain}_lateral_service.py` with 3 methods
2. ✅ Register in `lateral_routes.py` via `LateralRouteFactory`
3. ✅ Add `EntityRelationshipsSection` to detail page
4. ✅ Import in UI file: `from ui.patterns.relationships import EntityRelationshipsSection`
5. ✅ Write unit tests for 3 service methods
6. ✅ Test in browser (expand sections, test graph)

**Time Estimate:** ~30 minutes per domain

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

## See Also

- `/docs/architecture/RELATIONSHIPS_ARCHITECTURE.md` - Core graph modeling — lateral types, service API, Cypher patterns
- `/PHASE5_COMPLETE.md` - Implementation completion details
- `/PHASE5_MANUAL_QA_CHECKLIST.md` - Testing guide
- `/.claude/skills/js-alpine/` - Alpine.js patterns
- `/docs/fasthtml-llms.txt` - FastHTML + HTMX patterns

---

**Status:** ✅ Complete - All 9 domains integrated
**Test Coverage:** 100% (40 automated tests)
**Deployment:** Production-ready
**Last Updated:** 2026-02-01
