# vis-network Reference: SKUEL Integration Architecture & Data Format

> On-demand reference for the [`vis-network`](SKILL.md) skill. SKILL.md holds the overview, quick start, decision trees, and summary; this file holds the Three-Layer Integration Architecture (Neo4j → FastHTML API → Alpine.js + Vis.js) and the Vis.js Data Format.

---

## Three-Layer Integration Architecture

SKUEL's Vis.js integration follows a clean three-layer architecture where each layer has a single responsibility:

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Alpine.js + Vis.js (Presentation)                  │
│ File: /static/js/skuel.js                                    │
│ Responsibility: Render interactive graph, handle UI events  │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ JSON (Vis.js format)
                            │
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: FastHTML API (Transformation)                      │
│ Files: lateral_routes.py, lateral_route_factory.py          │
│ Responsibility: Query service, format data for Vis.js       │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ Python domain models
                            │
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Neo4j + Service (Data)                             │
│ File: lateral_relationship_service.py                       │
│ Responsibility: Query graph, return domain models           │
└─────────────────────────────────────────────────────────────┘
```

---

### Layer 1: Neo4j + Service (Data Layer)

**Purpose:** Query Neo4j graph database, return typed domain models.

**Key File:** `/core/services/lateral_relationships/lateral_relationship_service.py`

**Core Method:**

```python
async def get_relationship_graph(
    self,
    entity_uid: EntityUID,
    depth: int = 1,
    relationship_types: list[str] | None = None,
) -> Result[dict[str, Any]]:
    """
    Get relationship graph data in Vis.js format.

    Args:
        entity_uid: Starting entity UID
        depth: Traversal depth (1-3, enforced max)
        relationship_types: Filter by relationship types (None = all)

    Returns:
        Result containing:
        {
            "nodes": [{"id": uid, "label": title, "type": type, ...}],
            "edges": [{"from": uid1, "to": uid2, "label": type, ...}],
        }
    """
```

**Cypher Query Pattern:**

The service uses Neo4j's `apoc.path.subgraphAll` for efficient graph traversal:

```cypher
MATCH (start {uid: $entity_uid})
CALL apoc.path.subgraphAll(start, {
    relationshipFilter: "BLOCKS|BLOCKED_BY|PREREQUISITE_FOR|...",
    minLevel: 0,
    maxLevel: $depth
})
YIELD nodes, relationships

// Extract node data
WITH [n in nodes | {
    id: n.uid,
    label: COALESCE(n.title, n.name, n.uid),
    type: labels(n)[0],
    status: n.status
}] AS nodeData,

// Extract edge data
[r in relationships | {
    from: startNode(r).uid,
    to: endNode(r).uid,
    type: type(r),
    label: type(r)
}] AS edgeData

RETURN {nodes: nodeData, edges: edgeData}
```

**Key Design:**
- Uses APOC for performance (10x faster than recursive Cypher)
- Enforces max depth of 3 (prevents exponential explosion)
- Returns domain models, not raw Neo4j data
- Handles bidirectional relationships (BLOCKS <-> BLOCKED_BY)

---

### Layer 2: FastHTML API (Transformation Layer)

**Purpose:** Expose HTTP endpoints, transform service data to Vis.js format.

**Key Files:**
- `/adapters/inbound/lateral_routes.py` - Route registration
- `/adapters/inbound/route_factories/lateral_route_factory.py` - Route factory

**API Endpoint Pattern:**

```
GET /api/{domain}/{uid}/lateral/graph?depth=2
```

**Example Endpoints:**
```
GET /api/tasks/task_fix-bug_abc123/lateral/graph?depth=1
GET /api/ku/ku_python-basics_xyz789/lateral/graph?depth=3
GET /api/goals/goal_launch-product_def456/lateral/graph?depth=2
```

**Route Factory Usage:**

```python
from adapters.inbound.route_factories.lateral_route_factory import LateralRouteFactory

def create_tasks_lateral_routes(app, rt, tasks_service, lateral_service):
    """Register lateral relationship routes for Tasks domain."""

    factory = LateralRouteFactory(
        domain_name="tasks",
        lateral_service=lateral_service,
        entity_service=tasks_service,  # For ownership verification
        content_scope=ContentScope.USER_OWNED,
    )

    routes = factory.create_routes(app, rt)
    return routes
```

**What the factory creates:**

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/tasks/{uid}/lateral/chain` | GET | Blocking chain data (vertical flow) |
| `/api/tasks/{uid}/lateral/alternatives/compare` | GET | Alternatives comparison table |
| `/api/tasks/{uid}/lateral/graph` | GET | Vis.js format graph data |

**Response Format (Vis.js):**

```json
{
  "nodes": [
    {
      "id": "task_write-tests_abc123",
      "label": "Write Unit Tests",
      "type": "Task",
      "group": "tasks",
      "color": "#3b82f6",
      "status": "IN_PROGRESS"
    },
    {
      "id": "task_setup-ci_xyz789",
      "label": "Setup CI Pipeline",
      "type": "Task",
      "group": "tasks",
      "color": "#10b981",
      "status": "COMPLETED"
    }
  ],
  "edges": [
    {
      "from": "task_write-tests_abc123",
      "to": "task_setup-ci_xyz789",
      "label": "BLOCKS",
      "arrows": "to",
      "color": {"color": "#ef4444"},
      "width": 2
    }
  ]
}
```

**Key Design:**
- Returns JSON, not HTML (Alpine handles rendering)
- Includes node styling metadata (color, status)
- Includes edge styling metadata (arrows, color, width)
- Validates depth parameter (1-3)
- Handles ownership verification (user can only see their entities)

---

### Layer 3: Alpine.js + Vis.js (Presentation Layer)

**Purpose:** Render interactive graph, handle user interactions (click, drag, zoom).

**Key File:** `/static/js/skuel.js` (lines 2313-2431)

**Complete Alpine Component:**

```javascript
/**
 * relationshipGraph - Alpine.js component for Vis.js network graph
 *
 * Usage:
 *   <div x-data="relationshipGraph('task_123', 'tasks', 1)" x-init="loadGraph()">
 *     <div x-ref="container" style="width: 100%; height: 500px;"></div>
 *   </div>
 */
Alpine.data('relationshipGraph', (entityUid, entityType, initialDepth = 1) => ({
  // State
  network: null,           // Vis.js Network instance
  depth: initialDepth,     // Current depth (1-3)
  loading: false,
  error: null,

  /**
   * Load graph data from API and render
   */
  async loadGraph() {
    this.loading = true;
    this.error = null;

    try {
      // Fetch graph data from Layer 2 (API)
      const response = await fetch(
        `/api/${entityType}/${entityUid}/lateral/graph?depth=${this.depth}`
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();

      // Render graph with Vis.js
      this.renderGraph(data.nodes, data.edges);

    } catch (err) {
      console.error('Failed to load relationship graph:', err);
      this.error = err.message;
    } finally {
      this.loading = false;
    }
  },

  /**
   * Render graph using Vis.js Network
   */
  renderGraph(nodes, edges) {
    const container = this.$refs.container;
    if (!container) {
      console.error('Graph container not found (missing x-ref="container")');
      return;
    }

    // Destroy existing network instance (prevent memory leaks)
    if (this.network) {
      this.network.destroy();
    }

    // Create Vis.js datasets
    const data = {
      nodes: new vis.DataSet(nodes),
      edges: new vis.DataSet(edges),
    };

    // Configure network options (SKUEL's tuned settings)
    const options = {
      // Physics: forceAtlas2Based for balanced layout
      physics: {
        enabled: true,
        solver: 'forceAtlas2Based',
        forceAtlas2Based: {
          gravitationalConstant: -50,
          centralGravity: 0.01,
          springLength: 100,
          springConstant: 0.08,
          damping: 0.4,
        },
        stabilization: {
          enabled: true,
          iterations: 200,
          fit: true,
        },
      },

      // Node styling
      nodes: {
        shape: 'box',
        margin: 10,
        widthConstraint: {
          maximum: 200,
        },
        font: {
          size: 14,
          color: '#374151',
        },
      },

      // Edge styling
      edges: {
        smooth: {
          type: 'cubicBezier',
          forceDirection: 'horizontal',
        },
        arrows: {
          to: {
            enabled: true,
            scaleFactor: 0.5,
          },
        },
      },

      // Interaction
      interaction: {
        hover: true,
        tooltipDelay: 200,
        navigationButtons: true,
        keyboard: true,
      },
    };

    // Initialize Vis.js Network
    this.network = new vis.Network(container, data, options);

    // Event: Click node to navigate to its real detail page.
    // Do NOT build the URL from the node's Neo4j label / entity_type — labels
    // ("Ku"/"Task") are not routes, and detail routes vary in shape
    // (/tasks/detail?uid=, /explore/ku/{uid}, /lp/{uid}). The graph route resolves
    // each node's `url` server-side via ui/patterns/entity_links.entity_detail_href
    // (None for types with no detail page); the click handler just uses it.
    this.network.on('click', (params) => {
      if (params.nodes.length > 0) {
        const node = data.nodes.find((n) => n.id === params.nodes[0]);
        if (node && node.url) {
          window.location.href = node.url;
        }
      }
    });

    // Event: Disable physics after stabilization (performance)
    this.network.on('stabilizationIterationsDone', () => {
      this.network.setOptions({ physics: false });
    });
  },

  /**
   * Cleanup on component destroy
   */
  destroy() {
    if (this.network) {
      this.network.destroy();
      this.network = null;
    }
  },
}));
```

**Key Alpine Features:**

1. **Reactive State:** `depth` changes trigger `loadGraph()` via `@change="loadGraph()"`
2. **Loading States:** `loading` boolean shows spinner while fetching
3. **Error Handling:** `error` string displays user-friendly messages
4. **Cleanup:** `destroy()` prevents memory leaks when component unmounts
5. **DOM References:** `$refs.container` finds graph container via `x-ref`

**HTMX Integration:**

Graphs are lazy-loaded via HTMX's `hx-trigger="intersect once"`:

```python
from fasthtml.common import Div
from ui.patterns.skeleton import SkeletonLines

Div(
    **{
        "hx-get": f"/api/{entity_type}/{entity_uid}/lateral/graph?depth=1",
        "hx-trigger": "intersect once",  # Load when scrolled into view
        "hx-swap": "innerHTML",
    },
    SkeletonLines(count=4),  # Shimmer placeholder while graph loads
)
```

**Why lazy loading?**
- Graphs are expensive to render (physics simulation)
- Most users don't scroll to relationship section
- Improves initial page load time (500ms → 200ms)

---

## Vis.js Data Format

Vis.js Network expects data in a specific JSON format with `nodes` and `edges` arrays.

### Node Structure

**Minimal Node:**

```json
{
  "id": "task_write-tests_abc123",
  "label": "Write Unit Tests"
}
```

**Full Node (SKUEL Pattern):**

```json
{
  "id": "task_write-tests_abc123",           // Unique identifier (required)
  "label": "Write Unit Tests",                // Display text (required)
  "type": "Task",                             // Entity type (for filtering)
  "group": "tasks",                           // Domain name (for color schemes)
  "color": "#3b82f6",                         // Node background color
  "status": "IN_PROGRESS",                    // Domain-specific status
  "shape": "box",                             // Shape: box, circle, ellipse, etc.
  "font": {"color": "#ffffff"},               // Text color
  "borderWidth": 2,                           // Border thickness
  "borderWidthSelected": 4                    // Border when selected
}
```

**Node Fields Reference:**

| Field | Type | Required | Purpose | Example |
|-------|------|----------|---------|---------|
| `id` | string | ✅ | Unique identifier | `"task_abc123"` |
| `label` | string | ✅ | Display text | `"Write Tests"` |
| `title` | string | ❌ | Hover tooltip HTML | `"<b>Status:</b> In Progress"` |
| `group` | string | ❌ | Grouping for colors | `"tasks"` |
| `color` | string/object | ❌ | Background color | `"#3b82f6"` |
| `shape` | string | ❌ | Node shape | `"box"`, `"circle"` |
| `size` | number | ❌ | Node size | `25` |
| `font` | object | ❌ | Font styling | `{"size": 14, "color": "#333"}` |

---

### Edge Structure

**Minimal Edge:**

```json
{
  "from": "task_write-tests_abc123",
  "to": "task_setup-ci_xyz789"
}
```

**Full Edge (SKUEL Pattern):**

```json
{
  "from": "task_write-tests_abc123",          // Source node ID (required)
  "to": "task_setup-ci_xyz789",               // Target node ID (required)
  "label": "BLOCKS",                          // Relationship type display
  "arrows": "to",                             // Arrow direction: "to", "from", "to,from"
  "color": {"color": "#ef4444"},              // Edge color (red for BLOCKS)
  "width": 2,                                 // Edge thickness
  "dashes": false,                            // Solid or dashed line
  "smooth": {"type": "cubicBezier"}           // Edge curvature
}
```

**Edge Fields Reference:**

| Field | Type | Required | Purpose | Example |
|-------|------|----------|---------|---------|
| `from` | string | ✅ | Source node ID | `"task_abc123"` |
| `to` | string | ✅ | Target node ID | `"task_xyz789"` |
| `label` | string | ❌ | Relationship type | `"BLOCKS"` |
| `arrows` | string | ❌ | Arrow direction | `"to"`, `"from"`, `"to,from"` |
| `color` | string/object | ❌ | Edge color | `"#ef4444"` |
| `width` | number | ❌ | Edge thickness | `2` |
| `dashes` | boolean/array | ❌ | Dashed line | `true`, `[5, 5]` |
| `smooth` | boolean/object | ❌ | Curvature | `{"type": "cubicBezier"}` |

---

### SKUEL's Relationship Color Scheme

SKUEL uses consistent colors across all domains for relationship types:

| Relationship Type | Color | Hex | Use Case |
|-------------------|-------|-----|----------|
| `BLOCKS` | Red | `#ef4444` | Task A blocks Task B (asymmetric) |
| `BLOCKED_BY` | Light Red | `#fca5a5` | Reverse of BLOCKS |
| `PREREQUISITE_FOR` | Orange | `#f59e0b` | KU A required before KU B |
| `DEPENDS_ON` | Light Orange | `#fbbf24` | Reverse of PREREQUISITE_FOR |
| `ALTERNATIVE_TO` | Blue | `#3b82f6` | Mutually exclusive options |
| `COMPLEMENTARY_TO` | Green | `#10b981` | Synergistic pairing |
| `SIBLING` | Purple | `#8b5cf6` | Same parent in hierarchy |
| `RELATED_TO` | Gray | `#6b7280` | General association |

**Implementation:**

```python
# Centralized in core/utils/palette.py (also importable via ui/palette re-export)
from core.utils.palette import RelationshipColor

# Get color for a relationship type
color = RelationshipColor.for_type("BLOCKS")      # "#EF4444" (Red)
color = RelationshipColor.for_type("SIBLING")      # "#8B5CF6" (Purple)

# Used in lateral_relationship_service.py:
edge["color"] = {"color": RelationshipColor.for_type(rel_type)}
```
