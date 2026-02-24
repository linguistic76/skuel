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

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Three-Layer Integration Architecture](#three-layer-integration-architecture)
4. [Vis.js Data Format](#visjs-data-format)
5. [Configuration Patterns](#configuration-patterns)
6. [Interaction Patterns](#interaction-patterns)
7. [Common Use Cases](#common-use-cases)
8. [Depth Control Pattern](#depth-control-pattern)
9. [Best Practices](#best-practices)
10. [Anti-Patterns](#anti-patterns)
11. [Decision Trees](#decision-trees)
12. [Integration Checklist](#integration-checklist)
13. [Related Skills](#related-skills)
14. [Deep Dive Resources](#deep-dive-resources)
15. [Troubleshooting](#troubleshooting)
16. [Performance Metrics](#performance-metrics)

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
- Activity domains (6): Tasks, Goals, Habits, Events, Choices, Principles
- Curriculum domains (3): KU, LS, LP

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
                    cls="select select-bordered select-sm",
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
    entity_uid: str,
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

    // Event: Click node to navigate
    this.network.on('click', (params) => {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        // Navigate to entity detail page
        window.location.href = `/${entityType}/${nodeId}`;
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

Div(
    **{
        "hx-get": f"/api/{entity_type}/{entity_uid}/lateral/graph?depth=1",
        "hx-trigger": "intersect once",  # Load when scrolled into view
        "hx-swap": "innerHTML",
    },
    Div("Loading graph...", cls="skeleton h-96"),  # Placeholder
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

```javascript
// In API layer (lateral_route_factory.py)
RELATIONSHIP_COLORS = {
    "BLOCKS": "#ef4444",
    "BLOCKED_BY": "#fca5a5",
    "PREREQUISITE_FOR": "#f59e0b",
    "DEPENDS_ON": "#fbbf24",
    "ALTERNATIVE_TO": "#3b82f6",
    "COMPLEMENTARY_TO": "#10b981",
    "SIBLING": "#8b5cf6",
    "RELATED_TO": "#6b7280",
}

# Apply color to edge
edge["color"] = {"color": RELATIONSHIP_COLORS.get(edge_type, "#6b7280")}
```

---

## Configuration Patterns

Vis.js Network offers extensive configuration options. SKUEL has tuned settings optimized for relationship graphs.

### Physics Solvers Comparison

**Vis.js supports 4 physics solvers:**

| Solver | Performance | Layout Quality | Use Case |
|--------|-------------|----------------|----------|
| **forceAtlas2Based** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | **SKUEL default** - Balanced force-directed layout |
| **barnesHut** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | Large graphs (1000+ nodes), fast but less organized |
| **hierarchical** | ⭐⭐⭐ | ⭐⭐⭐⭐ | Tree structures, DAGs - NOT suitable for lateral relationships |
| **repulsion** | ⭐⭐ | ⭐⭐ | Simple repulsion, poor for connected graphs |

**SKUEL uses forceAtlas2Based** because lateral relationships are cyclic (BLOCKS can form loops), requiring a force-directed algorithm.

---

### SKUEL's Tuned Configuration

**Complete options object with rationale:**

```javascript
const options = {
  // ===== PHYSICS =====
  physics: {
    enabled: true,  // Enable during initial layout
    solver: 'forceAtlas2Based',  // Best for lateral relationships

    forceAtlas2Based: {
      gravitationalConstant: -50,  // Repulsion between nodes (negative = repel)
      centralGravity: 0.01,        // Pull toward center (low = spread out)
      springLength: 100,           // Ideal edge length (pixels)
      springConstant: 0.08,        // Edge stiffness (low = flexible)
      damping: 0.4,                // Movement decay (higher = settle faster)
    },

    stabilization: {
      enabled: true,               // Run physics before showing graph
      iterations: 200,             // Max stabilization iterations
      fit: true,                   // Zoom to fit all nodes
    },
  },

  // ===== NODE STYLING =====
  nodes: {
    shape: 'box',                  // Rectangular nodes (better for text)
    margin: 10,                    // Padding inside node
    widthConstraint: {
      maximum: 200,                // Max node width (prevent overflow)
    },
    font: {
      size: 14,                    // Text size
      color: '#374151',            // Text color (gray-700)
      face: 'Inter, sans-serif',   // Font family
    },
    borderWidth: 2,                // Border thickness
    borderWidthSelected: 4,        // Border when selected (visual feedback)
    shadow: {
      enabled: true,               // Drop shadow
      size: 5,
      x: 2,
      y: 2,
    },
  },

  // ===== EDGE STYLING =====
  edges: {
    width: 2,                      // Default edge thickness
    smooth: {
      type: 'cubicBezier',         // Curved edges (avoid overlap)
      forceDirection: 'horizontal', // Prefer left-right flow
    },
    arrows: {
      to: {
        enabled: true,             // Show arrow on target end
        scaleFactor: 0.5,          // Arrow size (relative to edge width)
      },
    },
    color: {
      inherit: false,              // Don't inherit node color
    },
  },

  // ===== INTERACTION =====
  interaction: {
    hover: true,                   // Highlight on hover
    tooltipDelay: 200,             // Tooltip delay (ms)
    navigationButtons: true,       // Show zoom/pan controls
    keyboard: true,                // Keyboard shortcuts (arrow keys, +/-)
    dragNodes: true,               // Allow dragging nodes
    dragView: true,                // Allow panning canvas
    zoomView: true,                // Allow zooming
  },

  // ===== LAYOUT =====
  layout: {
    improvedLayout: true,          // Better initial positioning
    hierarchical: false,           // NOT hierarchical (lateral relationships)
  },
};
```

**Key Tuning Rationale:**

1. **gravitationalConstant: -50** - Nodes repel moderately (prevents overlap without excessive spread)
2. **centralGravity: 0.01** - Low center pull (allows natural clustering)
3. **springLength: 100** - Edges prefer 100px length (readable spacing)
4. **springConstant: 0.08** - Flexible edges (organic layout, not rigid grid)
5. **damping: 0.4** - Moderate damping (settles in ~3-5 seconds)
6. **stabilization: 200 iterations** - Enough for most graphs (balance speed vs quality)

---

### Node Styling Patterns

**Pattern 1: Color by Status**

```javascript
// In API response generation
nodes.forEach(node => {
  const statusColors = {
    'COMPLETED': '#10b981',   // Green
    'IN_PROGRESS': '#3b82f6', // Blue
    'PENDING': '#6b7280',     // Gray
    'CANCELLED': '#ef4444',   // Red
  };

  node.color = statusColors[node.status] || '#6b7280';
});
```

**Pattern 2: Size by Importance**

```javascript
// Larger nodes for high-priority items
nodes.forEach(node => {
  const sizeMap = {
    'CRITICAL': 30,
    'HIGH': 25,
    'MEDIUM': 20,
    'LOW': 15,
  };

  node.size = sizeMap[node.priority] || 20;
});
```

**Pattern 3: Shape by Type**

```javascript
// Different shapes for different entity types
nodes.forEach(node => {
  const shapeMap = {
    'Task': 'box',
    'Goal': 'ellipse',
    'Curriculum': 'diamond',
    'Habit': 'star',
  };

  node.shape = shapeMap[node.type] || 'box';
});
```

---

### Edge Styling Patterns

**Pattern 1: Relationship Type Colors (SKUEL Default)**

```javascript
// Already shown in "SKUEL's Relationship Color Scheme"
edges.forEach(edge => {
  edge.color = { color: RELATIONSHIP_COLORS[edge.type] };
});
```

**Pattern 2: Dashed Lines for Weak Relationships**

```javascript
// Dashed for "suggested" or "optional" relationships
edges.forEach(edge => {
  if (edge.strength === 'WEAK' || edge.type === 'SUGGESTED') {
    edge.dashes = [5, 5];  // 5px dash, 5px gap
  }
});
```

**Pattern 3: Width by Importance**

```javascript
// Thicker edges for stronger relationships
edges.forEach(edge => {
  const widthMap = {
    'CRITICAL': 4,
    'HIGH': 3,
    'MEDIUM': 2,
    'LOW': 1,
  };

  edge.width = widthMap[edge.importance] || 2;
});
```

---

### Performance Optimization

**Disable Physics After Stabilization:**

```javascript
// In Alpine component or manual initialization
network.on('stabilizationIterationsDone', () => {
  network.setOptions({ physics: false });
});
```

**Why?**
- Physics simulation is CPU-intensive (continuous force calculations)
- After initial layout settles, physics is unnecessary
- Disabling improves frame rate from ~30fps to 60fps
- Users can still drag nodes (manual positioning works without physics)

**When to keep physics enabled:**
- Real-time data updates (nodes/edges added dynamically)
- Animated transitions between layouts
- User expects continuous movement (not SKUEL's use case)

---

## Interaction Patterns

Vis.js Network supports rich interactions. SKUEL implements click navigation and hover tooltips.

### Click Navigation (SKUEL Pattern)

**Implementation:**

```javascript
network.on('click', (params) => {
  if (params.nodes.length > 0) {
    const nodeId = params.nodes[0];
    // Navigate to entity detail page
    window.location.href = `/${entityType}/${nodeId}`;
  }
});
```

**User Experience:**
- Click any node → navigate to its detail page
- Enables graph-based navigation (explore related entities)
- Alternative to traditional list views

**Why full page navigation (not HTMX swap)?**
- Detail pages are complex (not lightweight fragments)
- User expects new URL (browser history, bookmarks)
- Simplifies state management (no need to update graph after swap)

---

### Hover Tooltips

**Native Tooltip (Simple):**

```javascript
// In node data
nodes.forEach(node => {
  node.title = `<b>${node.label}</b><br>Status: ${node.status}`;
});
```

**Custom HTML Tooltip (Advanced):**

```javascript
// Requires external tooltip library (e.g., Tippy.js)
network.on('hoverNode', (params) => {
  const nodeId = params.node;
  const node = nodes.find(n => n.id === nodeId);

  // Show custom tooltip at mouse position
  showCustomTooltip(params.pointer.DOM, {
    title: node.label,
    status: node.status,
    relationships: node.relationshipCount,
  });
});

network.on('blurNode', () => {
  hideCustomTooltip();
});
```

**SKUEL uses native tooltips** (simpler, no extra dependencies).

---

### Double-Click Actions

**Pattern: Double-click to expand node**

```javascript
network.on('doubleClick', (params) => {
  if (params.nodes.length > 0) {
    const nodeId = params.nodes[0];
    // Load deeper relationships for this node
    expandNode(nodeId);
  }
});

async function expandNode(nodeId) {
  // Fetch additional relationships
  const response = await fetch(`/api/tasks/${nodeId}/lateral/graph?depth=1`);
  const data = await response.json();

  // Add new nodes/edges to existing graph
  network.body.data.nodes.add(data.nodes);
  network.body.data.edges.add(data.edges);
}
```

**Not implemented in SKUEL** (depth control handles this use case).

---

### Context Menu (Right-Click)

**Pattern: Right-click menu for actions**

```javascript
// Disable native context menu
network.on('oncontext', (params) => {
  params.event.preventDefault();

  if (params.nodes.length > 0) {
    const nodeId = params.nodes[0];
    showContextMenu(params.pointer.DOM, nodeId);
  }
});

function showContextMenu(position, nodeId) {
  // Show custom menu with actions:
  // - View Details
  // - Edit
  // - Delete Relationship
  // - Add Relationship
}
```

**Not implemented in SKUEL** (click navigation is simpler).

---

## Common Use Cases

Real-world examples from SKUEL's 9 deployed domains.

### Use Case 1: Task Blocking Chain Visualization

**Scenario:** User has a complex task with multiple blocking dependencies. They want to see the full chain: "What needs to happen before I can start this?"

**Domain:** Tasks

**Graph Type:** Vertical flow chart (blocking chain)

**Implementation:**

```python
from ui.patterns.relationships import BlockingChainView

def task_detail(request, uid: str, task: Task, ...):
    return BasePage(
        content=Container(
            H2("Task Details", cls="text-2xl font-bold"),
            # ... task info ...

            # Blocking chain shows: blocked_by relationships (transitive)
            BlockingChainView(
                entity_uid=task.uid,
                entity_type="tasks",
            ),
        ),
        request=request,
    )
```

**API Query:**

```cypher
// Find all tasks blocking this one (transitive)
MATCH path = (target:Task {uid: $uid})<-[:BLOCKS*1..3]-(blocker:Task)
RETURN blocker.uid, blocker.title, length(path) AS depth
ORDER BY depth DESC
```

**Result:**

```
Setup Environment (depth 3)
    ↓ BLOCKS
Install Dependencies (depth 2)
    ↓ BLOCKS
Write Tests (depth 1)
    ↓ BLOCKS
[CURRENT TASK]
```

**User Insight:** "I need to setup environment first, then install dependencies, then write tests before I can start this task."

---

### Use Case 2: Knowledge Prerequisites Graph

**Scenario:** User is learning "Machine Learning" but doesn't know what background knowledge they need. They want to see the prerequisite graph.

**Domain:** KU (Knowledge Units)

**Graph Type:** Prerequisite DAG (directed acyclic graph)

**Implementation:**

```python
from ui.patterns.relationships import RelationshipGraphView

def ku_detail(request, uid: str, ku: KnowledgeUnit, ...):
    return BasePage(
        content=Container(
            H2(ku.title, cls="text-3xl font-bold"),
            # ... content ...

            # Interactive graph shows PREREQUISITE_FOR relationships
            RelationshipGraphView(
                entity_uid=ku.uid,
                entity_type="ku",
                default_depth=2,  # Show 2 levels of prerequisites
            ),
        ),
        request=request,
    )
```

**API Query:**

```cypher
// Find prerequisites and what this enables
MATCH (center:Curriculum {uid: $uid})
OPTIONAL MATCH path1 = (prereq:Curriculum)-[:PREREQUISITE_FOR*1..2]->(center)
OPTIONAL MATCH path2 = (center)-[:PREREQUISITE_FOR*1..2]->(enables:Curriculum)

WITH center, collect(DISTINCT prereq) AS prerequisites,
     collect(DISTINCT enables) AS enables_list

RETURN center, prerequisites, enables_list
```

**Graph Visualization:**

```
[Linear Algebra] ──PREREQUISITE_FOR──> [Machine Learning]
[Python Basics]  ──PREREQUISITE_FOR──> [Machine Learning]
[Machine Learning] ──PREREQUISITE_FOR──> [Deep Learning]
[Machine Learning] ──PREREQUISITE_FOR──> [NLP]
```

**User Insight:** "I need Linear Algebra and Python before ML. Learning ML will unlock Deep Learning and NLP."

---

### Use Case 3: Goal Alternatives Comparison

**Scenario:** User has conflicting goals (e.g., "Travel the World" vs "Buy a House"). They want to see alternatives and make an informed choice.

**Domain:** Goals

**Graph Type:** Comparison table + relationship graph

**Implementation:**

```python
from ui.patterns.relationships import AlternativesComparisonGrid

def goal_detail(request, uid: str, goal: Goal, ...):
    return BasePage(
        content=Container(
            H2("Goal Alternatives", cls="text-2xl font-bold"),

            # Side-by-side comparison table
            AlternativesComparisonGrid(
                entity_uid=goal.uid,
                entity_type="goals",
            ),
        ),
        request=request,
    )
```

**API Query:**

```cypher
// Find ALTERNATIVE_TO relationships
MATCH (center:Goal {uid: $uid})
MATCH (center)-[:ALTERNATIVE_TO]-(alternative:Goal)

RETURN center, alternative
```

**Comparison Table:**

| Field | Travel the World | Buy a House |
|-------|------------------|-------------|
| **Status** | In Progress | Pending |
| **Priority** | High | Medium |
| **Target Date** | 2027-01-01 | 2028-01-01 |
| **Cost** | $50,000 | $500,000 |
| **Time Required** | 1 year | 5 years |
| **Related Tasks** | 12 | 3 |

**User Insight:** "These goals are mutually exclusive (can't do both now). Travel is more actionable short-term."

---

### Use Case 4: Habit Stacking (Complementary Relationships)

**Scenario:** User wants to build a morning routine. They want to see which habits complement each other.

**Domain:** Habits

**Graph Type:** Clustering graph (complementary relationships)

**Implementation:**

```python
from ui.patterns.relationships import RelationshipGraphView

def habit_detail(request, uid: str, habit: Habit, ...):
    return BasePage(
        content=Container(
            H2("Related Habits", cls="text-2xl font-bold"),

            # Graph shows COMPLEMENTARY_TO relationships
            RelationshipGraphView(
                entity_uid=habit.uid,
                entity_type="habits",
                default_depth=1,  # Just direct relationships
            ),
        ),
        request=request,
    )
```

**API Query:**

```cypher
// Find complementary habits
MATCH (center:Habit {uid: $uid})
MATCH (center)-[:COMPLEMENTARY_TO]-(related:Habit)

RETURN center, related
```

**Graph Visualization:**

```
[Meditation] ←──COMPLEMENTARY_TO──→ [Journaling]
     ↓
COMPLEMENTARY_TO
     ↓
[Morning Walk] ←──COMPLEMENTARY_TO──→ [Stretching]
```

**User Insight:** "These habits reinforce each other. Stack them in a morning routine: Walk → Stretch → Meditate → Journal."

---

## Depth Control Pattern

**Problem:** Relationship graphs grow exponentially. Depth 1 = 5 nodes, Depth 2 = 25 nodes, Depth 3 = 125 nodes.

**Solution:** Limit max depth to 3, provide UI control for users to adjust.

---

### Why Depth Matters

**Complexity Table:**

| Depth | Nodes (avg) | Edges (avg) | Render Time | Use Case |
|-------|-------------|-------------|-------------|----------|
| **1** | 5-10 | 5-15 | ~100ms | Direct relationships only |
| **2** | 15-30 | 30-60 | ~300ms | **SKUEL default** - Shows context |
| **3** | 40-100 | 100-300 | ~1000ms | Deep exploration (max allowed) |
| 4+ | 200+ | 500+ | 5000ms+ | ❌ **Not allowed** - exponential explosion |

**SKUEL enforces max depth of 3** to prevent performance issues.

---

### UI Control Implementation

**Select Dropdown with Alpine Binding:**

```python
from fasthtml.common import Div, Select, Option, Label

Div(
    Label("Graph Depth:", cls="label"),
    Select(
        Option("1 level (direct only)", value="1"),
        Option("2 levels (context)", value="2", selected=True),
        Option("3 levels (deep)", value="3"),
        **{
            "x-model": "depth",           # Bind to Alpine state
            "@change": "loadGraph()",     # Reload graph on change
        },
        cls="select select-bordered select-sm",
    ),
    cls="form-control w-64",
)
```

**Alpine Integration:**

```javascript
Alpine.data('relationshipGraph', (entityUid, entityType, initialDepth = 1) => ({
  depth: initialDepth,  // Reactive state

  async loadGraph() {
    // Fetch with current depth
    const response = await fetch(
      `/api/${entityType}/${entityUid}/lateral/graph?depth=${this.depth}`
    );
    // ... render graph
  },
}));
```

---

### API Endpoint with Depth Validation

**FastHTML Route:**

```python
from fastapi import Request, HTTPException

@rt("/api/{entity_type}/{uid}/lateral/graph")
async def get_relationship_graph(
    request: Request,
    entity_type: str,
    uid: str,
    depth: int = Query(default=1, ge=1, le=3),  # Enforce 1-3
):
    """Get relationship graph in Vis.js format."""

    # Validate depth
    if depth < 1 or depth > 3:
        raise HTTPException(400, "Depth must be 1-3")

    # Query service
    result = await lateral_service.get_relationship_graph(uid, depth)

    if result.is_error:
        raise HTTPException(500, str(result.error))

    return result.value  # {nodes: [...], edges: [...]}
```

---

## Best Practices

### 1. Use EntityRelationshipsSection for Standard Cases

**GOOD:**

```python
from ui.patterns.relationships import EntityRelationshipsSection

EntityRelationshipsSection(
    entity_uid=task.uid,
    entity_type="tasks",
)
```

**Why?**
- ✅ Zero boilerplate
- ✅ All three visualization types (chain, comparison, graph)
- ✅ Consistent UI across domains
- ✅ HTMX lazy loading built-in

**AVOID:**

```python
# Manually building graph HTML - unnecessary work
Div(
    Div("Blocking Chain", cls="tab"),
    Div("Alternatives", cls="tab"),
    Div("Graph", cls="tab"),
    # ... 50 lines of manual HTML
)
```

---

### 2. Always Include Vis.js Scripts

**GOOD:**

```python
# In base_layout.py (already done in SKUEL)
Script(src="/static/vendor/vis-network/vis-network.min.js"),
Link(rel="stylesheet", href="/static/vendor/vis-network/vis-network.min.css"),
```

**Why?**
- ✅ Vis.js is self-hosted (no CDN dependency)
- ✅ Loaded once per page (cached by browser)
- ✅ Version-locked (no breaking changes from CDN updates)

**AVOID:**

```html
<!-- CDN loading - version may change, breaks cache -->
<script src="https://unpkg.com/vis-network/dist/vis-network.min.js"></script>
```

---

### 3. Let Alpine Handle Loading States

**GOOD:**

```python
# Alpine component handles loading automatically
Div(
    **{
        "x-data": "relationshipGraph('task_123', 'tasks', 1)",
        "x-init": "loadGraph()",
    },
    # Loading state built into component
    Div("Loading graph...", **{"x-show": "loading"}),
    Div("Error: ", **{"x-show": "error", "x-text": "error"}),
    Div(**{"x-ref": "container", "x-show": "!loading && !error"}),
)
```

**Why?**
- ✅ Reactive loading states (no manual DOM updates)
- ✅ Error handling built-in
- ✅ Prevents FOUC (flash of unstyled content)

**AVOID:**

```python
# Manual loading state management - race conditions
Div(
    Div("Loading...", id="loading"),
    Div(id="graph"),
    Script("fetch(...).then(() => { $('#loading').hide() })")  # Fragile!
)
```

---

### 4. Use Consistent Colors (SKUEL Scheme)

**GOOD:**

```javascript
const RELATIONSHIP_COLORS = {
  "BLOCKS": "#ef4444",           // Red
  "PREREQUISITE_FOR": "#f59e0b", // Orange
  "ALTERNATIVE_TO": "#3b82f6",   // Blue
  "COMPLEMENTARY_TO": "#10b981", // Green
  // ... (consistent across all domains)
};
```

**Why?**
- ✅ Users learn color meanings across domains
- ✅ Accessibility (color + label redundancy)
- ✅ Brand consistency

**AVOID:**

```javascript
// Random colors per domain - confusing for users
const taskColors = { BLOCKS: "#ff0000" };  // Different red
const goalColors = { BLOCKS: "#ee0000" };  // Different red
```

---

### 5. Optimize for Large Graphs (Disable Physics)

**GOOD:**

```javascript
// Disable physics after stabilization
network.on('stabilizationIterationsDone', () => {
  network.setOptions({ physics: false });
});
```

**Why?**
- ✅ 2x frame rate improvement (30fps → 60fps)
- ✅ Users can still drag nodes (manual positioning)
- ✅ No visual difference after initial layout

**AVOID:**

```javascript
// Physics always enabled - CPU thrashing
physics: { enabled: true }  // No disable logic
```

---

## Anti-Patterns

### 1. Don't Create Network Instances Manually

**WRONG:**

```javascript
// Manual network instance - no cleanup, memory leaks
const container = document.getElementById('graph');
const network = new vis.Network(container, data, options);
// What happens when user navigates away? Memory leak!
```

**CORRECT:**

```python
# Use Alpine component - automatic cleanup
Div(
    **{
        "x-data": "relationshipGraph('task_123', 'tasks', 1)",
        "x-init": "loadGraph()",
    },
    Div(**{"x-ref": "container"}),
)
```

**Why Alpine?**
- ✅ Alpine calls `destroy()` on component unmount
- ✅ Prevents memory leaks (network instances are heavy ~5MB)
- ✅ Handles cleanup on navigation/HTMX swaps

---

### 2. Don't Skip Error Handling

**WRONG:**

```javascript
async loadGraph() {
  const response = await fetch(`/api/tasks/${this.uid}/lateral/graph`);
  const data = await response.json();  // What if 404? 500? Unhandled!
  this.renderGraph(data.nodes, data.edges);
}
```

**CORRECT:**

```javascript
async loadGraph() {
  this.loading = true;
  this.error = null;

  try {
    const response = await fetch(`/api/tasks/${this.uid}/lateral/graph`);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    this.renderGraph(data.nodes, data.edges);

  } catch (err) {
    console.error('Failed to load graph:', err);
    this.error = err.message;  // Show user-friendly error
  } finally {
    this.loading = false;
  }
}
```

**Why?**
- ✅ Graceful degradation (show error message, don't crash)
- ✅ Debugging (console.error logs for developers)
- ✅ User feedback (error message in UI)

---

### 3. Don't Forget to Destroy Network Instances

**WRONG:**

```javascript
// Create new network without destroying old one
renderGraph(nodes, edges) {
  this.network = new vis.Network(container, data, options);  // Memory leak!
}
```

**CORRECT:**

```javascript
renderGraph(nodes, edges) {
  // Destroy existing instance first
  if (this.network) {
    this.network.destroy();
  }

  // Now create new instance
  this.network = new vis.Network(container, data, options);
}
```

**Why?**
- ✅ Prevents memory leaks (each instance is ~5MB)
- ✅ Prevents event listener accumulation (click handlers stack up)
- ✅ Critical for depth changes (re-render same component)

---

### 4. Don't Use Unbounded Depth

**WRONG:**

```python
# No depth limit - exponential explosion
@rt("/api/tasks/{uid}/lateral/graph")
async def get_graph(uid: str, depth: int = 10):  # depth=10 = 10,000+ nodes!
    result = await service.get_relationship_graph(uid, depth)
    return result.value
```

**CORRECT:**

```python
from fastapi import Query, HTTPException

@rt("/api/tasks/{uid}/lateral/graph")
async def get_graph(
    uid: str,
    depth: int = Query(default=1, ge=1, le=3),  # Enforce max=3
):
    if depth > 3:
        raise HTTPException(400, "Max depth is 3")

    result = await service.get_relationship_graph(uid, depth)
    return result.value
```

**Why?**
- ✅ Prevents database timeouts (depth 5+ = minutes)
- ✅ Prevents browser crashes (10,000 nodes = OOM)
- ✅ Forces users to think about what they need (depth 3 usually sufficient)

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

**Step-by-step guide for adding Vis.js to a new domain** (estimated time: 30 minutes).

### Step 1: Add Lateral Relationship Routes (10 min)

**File:** `/adapters/inbound/{domain}_routes.py`

```python
from adapters.inbound.route_factories.lateral_route_factory import LateralRouteFactory

def create_{domain}_routes(app, rt, services, _sync_service=None):
    # ... existing routes ...

    # Add lateral relationship routes
    factory = LateralRouteFactory(
        domain_name="{domain}",  # e.g., "tasks", "goals", "ku"
        lateral_service=services.lateral_relationships,
        entity_service=services.{domain},  # For ownership verification
        content_scope=ContentScope.USER_OWNED,  # Or SHARED for curriculum
    )

    routes.extend(factory.create_routes(app, rt))
    return routes
```

**Verify:** Visit `/api/{domain}/{uid}/lateral/graph?depth=1` - should return JSON.

---

### Step 2: Add EntityRelationshipsSection to Detail Page (5 min)

**File:** `/adapters/inbound/{domain}_routes.py` (detail page function)

```python
from ui.patterns.relationships import EntityRelationshipsSection

@rt("/{domain}/{uid}")
async def {domain}_detail(request: Request, uid: str):
    # ... fetch entity ...

    return BasePage(
        content=Container(
            # ... existing content ...

            # Add relationships section at bottom
            EntityRelationshipsSection(
                entity_uid=entity.uid,
                entity_type="{domain}",
            ),
        ),
        request=request,
    )
```

**Verify:** Visit `/{domain}/{uid}` - should see "Relationships" section with tabs.

---

### Step 3: Verify Vis.js Scripts Loaded (2 min)

**Check:** View page source, search for `vis-network.min.js`.

```html
<!-- Should be in <head> -->
<script src="/static/vendor/vis-network/vis-network.min.js"></script>
<link rel="stylesheet" href="/static/vendor/vis-network/vis-network.min.css">
```

**If missing:** Add to `/ui/layouts/base_page.py`:

```python
Script(src="/static/vendor/vis-network/vis-network.min.js"),
Link(rel="stylesheet", href="/static/vendor/vis-network/vis-network.min.css"),
```

---

### Step 4: Test Interactive Graph (5 min)

1. Navigate to entity detail page (`/{domain}/{uid}`)
2. Scroll to "Relationships" section
3. Click "Interactive Graph" tab
4. Change depth dropdown (1 → 2 → 3)
5. Click a node → should navigate to that entity's detail page
6. Drag a node → should move smoothly
7. Zoom/pan → should work

**Expected behavior:**
- Graph loads on first tab click (lazy loading)
- Depth changes reload graph
- Click navigation works
- No console errors

---

### Step 5: Performance Check (5 min)

**Open browser DevTools → Network tab:**

1. Check API response time: `/api/{domain}/{uid}/lateral/graph?depth=2`
   - ✅ Should be <500ms (typically 100-300ms)
   - ❌ If >1000ms, investigate Cypher query performance

2. Check graph render time (console):
   - ✅ Should be <1000ms for depth 2
   - ❌ If >3000ms, reduce default depth or disable physics

3. Check memory usage (DevTools → Memory):
   - ✅ Network instance should be ~5-10MB
   - ❌ If >50MB, check for memory leaks (missing destroy())

---

### Step 6: Documentation Update (3 min)

**Update these files:**

1. `/docs/CROSS_REFERENCE_INDEX.md` - Add domain to vis-network mapping
2. `/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md` - Add domain to deployed list
3. `/.claude/skills/vis-network/SKILL.md` - Add use case example (optional)

---

## Related Skills

### Foundation Skills

**Required for Vis.js integration:**

| Skill | Why Required | Use For |
|-------|-------------|---------|
| **js-alpine** | Alpine.js component integration | `relationshipGraph()` component, reactive state |
| **html-htmx** | Lazy loading, server communication | HTMX `hx-trigger="intersect once"` pattern |
| **neo4j-cypher-patterns** | Graph queries | Cypher queries for lateral relationships |

**Recommended:**

| Skill | Relation | Use For |
|-------|----------|---------|
| **python** | Service layer | Service methods, API routes |
| **fasthtml** | Web framework | Route definitions, FastHTML components |
| **tailwind-css** | Styling | Container styling, responsive layout |

---

### Related Pattern Skills

**Domain-specific patterns:**

| Skill | Relation | Use For |
|-------|----------|---------|
| **activity-domains** | Activity domains use lateral relationships | Tasks, Goals, Habits, Events, Choices, Principles |
| **curriculum-domains** | Curriculum domains use lateral relationships | KU, LS, LP (prerequisites, alternatives) |
| **base-page-architecture** | Page layout | BasePage wrapper for detail pages |
| **skuel-component-composition** | UI patterns | Component hierarchy, reusable patterns |

---

## Deep Dive Resources

### Primary Documentation

**Must-read for Vis.js integration:**

| Document | Purpose | Key Sections |
|----------|---------|--------------|
| `/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md` | Complete pattern guide | Three-layer architecture, configuration, UI components |
| `/docs/architecture/LATERAL_RELATIONSHIPS_CORE.md` | Graph modeling | Relationship types, service architecture, Cypher patterns |
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

## Troubleshooting

### Issue 1: Graph Not Rendering

**Symptoms:**
- Blank white rectangle where graph should be
- No console errors
- API request succeeds (200 OK)

**Causes & Fixes:**

| Cause | Fix |
|-------|-----|
| **Vis.js library not loaded** | Check page source for `vis-network.min.js`. If missing, add to `base_layout.py`. |
| **Container missing `x-ref`** | Add `x-ref="container"` to graph container div. |
| **Container has no height** | Add explicit `height: 500px` or `min-height: 400px` to container style. |
| **Alpine component not initialized** | Check `x-data="relationshipGraph(...)"` and `x-init="loadGraph()"` are present. |

**Debug Steps:**

1. Open browser console, check for errors
2. Check Network tab - is `/api/.../lateral/graph` request successful?
3. Check DOM - does container have `style="height: XXXpx"`?
4. Check Alpine DevTools - is `relationshipGraph` component registered?

---

### Issue 2: HTMX Request Returns 404

**Symptoms:**
- "Relationships" section shows "Loading..." forever
- Network tab shows `404 Not Found` for `/api/{domain}/{uid}/lateral/graph`

**Causes & Fixes:**

| Cause | Fix |
|-------|-----|
| **Routes not registered** | Add `LateralRouteFactory` to domain routes file. |
| **Domain name mismatch** | Check `domain_name` parameter matches route URL (lowercase plural). |
| **Service not initialized** | Verify `services.lateral_relationships` exists in `services_bootstrap.py`. |

**Debug Steps:**

1. Check `/tmp/server.log` for route registration messages:
   ```
   [INFO] Registered 3 lateral relationship routes for tasks domain
   ```

2. List all routes:
   ```bash
   curl http://localhost:5001/routes | grep lateral
   ```

3. Test API directly:
   ```bash
   curl http://localhost:5001/api/tasks/task_test_123/lateral/graph?depth=1
   ```

---

### Issue 3: Graph Too Slow (>3 seconds)

**Symptoms:**
- Graph takes >3 seconds to render
- Browser becomes unresponsive during render
- CPU usage spikes to 100%

**Causes & Fixes:**

| Cause | Fix |
|-------|-----|
| **Depth too high** | Reduce default depth from 3 to 2 or 1. |
| **Too many nodes (>100)** | Switch physics solver from `forceAtlas2Based` to `barnesHut`. |
| **Physics always enabled** | Disable physics after stabilization: `network.on('stabilizationIterationsDone', () => network.setOptions({physics: false}))`. |
| **Cypher query inefficient** | Check Neo4j query plan: `PROFILE MATCH ...`. Add indexes on `uid` property. |

**Performance Optimization:**

```javascript
// Fast configuration for large graphs
const options = {
  physics: {
    solver: 'barnesHut',  // Faster than forceAtlas2Based
    stabilization: {
      iterations: 100,    // Reduce from 200
    },
  },
  nodes: {
    shape: 'dot',         // Simpler than 'box'
  },
  edges: {
    smooth: false,        // Disable curves
  },
};
```

---

## Performance Metrics

**SKUEL's production performance from Phase 5 testing (January 2026):**

### API Response Times

| Depth | Nodes (avg) | Edges (avg) | Response Time | Status |
|-------|-------------|-------------|---------------|--------|
| 1 | 5-10 | 5-15 | **100-200ms** | ✅ Excellent |
| 2 | 15-30 | 30-60 | **200-400ms** | ✅ Good |
| 3 | 40-100 | 100-300 | **500-1000ms** | ⚠️ Acceptable |

**Query optimization:** Using `apoc.path.subgraphAll` (10x faster than recursive Cypher).

---

### Graph Render Times

| Nodes | Physics Solver | Stabilization Time | Total Render Time | Status |
|-------|----------------|--------------------|--------------------|--------|
| <20 | forceAtlas2Based | 1-2s | **1.5-2.5s** | ✅ Good |
| 20-50 | forceAtlas2Based | 2-4s | **2.5-4.5s** | ✅ Acceptable |
| 50-100 | forceAtlas2Based | 4-8s | **5-9s** | ⚠️ Slow (consider depth reduction) |
| 100+ | barnesHut | 3-5s | **4-6s** | ⚠️ Switch solver or reduce depth |

**After optimization (physics disabled):** 60fps interaction (drag, zoom, pan).

---

### Memory Usage

| Component | Memory | Notes |
|-----------|--------|-------|
| Vis.js library | 2-3 MB | One-time load (cached) |
| Network instance | 5-10 MB | Per graph instance |
| Graph data (100 nodes) | 1-2 MB | JSON payload + DOM |
| **Total (typical)** | **8-15 MB** | ✅ Reasonable |

**Memory leak check:** Verified via Chrome DevTools - network instances properly destroyed on component unmount.

---

### Test Coverage

**Phase 5 verification (January 2026):**

- ✅ **40/40 automated tests passing**
  - 9 unit tests (service methods)
  - 31 integration tests (API routes, UI components)
- ✅ **92 API routes verified** (all 9 domains)
- ✅ **Zero breaking changes** (backward compatible)
- ✅ **Manual testing:** 9 domains × 3 visualizations = 27 manual tests passed

---

## Summary

**Vis.js Network in SKUEL:**

- **Purpose:** Visualize lateral relationships (blocking, prerequisites, alternatives, complements)
- **Integration:** Three-layer architecture (Neo4j → API → Alpine/Vis.js)
- **Deployment:** 9 domains (Tasks, Goals, Habits, Events, Choices, Principles, KU, LS, LP)
- **Performance:** <400ms API + <3s render for depth 2 (typical use case)
- **User Experience:** Interactive, physics-based, click-to-navigate

**Quick Start:** Add `EntityRelationshipsSection(entity_uid, entity_type)` to any detail page - done in 5 lines.

**Deep Integration:** Use `RelationshipGraphView` or manual Alpine integration for custom layouts.

**Best Practice:** Use forceAtlas2Based solver, depth 2 default, disable physics after stabilization.

---

**Related Skills:** @js-alpine @html-htmx @neo4j-cypher-patterns @activity-domains @curriculum-domains

**Deep Dive:** `/docs/patterns/LATERAL_RELATIONSHIPS_VISUALIZATION.md`
