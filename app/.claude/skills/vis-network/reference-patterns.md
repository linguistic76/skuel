# vis-network Reference: Configuration, Interaction, Use Cases & Depth Control

> On-demand reference for the [`vis-network`](SKILL.md) skill. SKILL.md holds the overview, quick start, and decision trees; this file holds the Configuration Patterns, Interaction Patterns, Common Use Cases, and the Depth Control Pattern.

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

Real-world examples from SKUEL's deployed domains.

### Use Case 0: Explore Sidebar Graph Navigation

**Scenario:** User is on the Explore hub or a Ku/PS detail page. The sidebar shows an interactive graph of their learning universe (hub) or the current entity's relationships (detail). Clicking a node navigates to that entity.

**Component:** `ExploreGraphView` (`ui/explore/graph.py`)

**Alpine Component:** `exploreGraph(mode, entity_uid, entity_type)` in `skuel.js`

**Implementation:**

```python
from ui.explore.graph import ExploreGraphView

# Hub mode — learning universe
graph = ExploreGraphView(mode="hub")

# Entity mode — centered on specific Ku/PS
graph = ExploreGraphView(mode="entity", entity_uid="ku_abc", entity_type="ku")
```

**Key differences from `relationshipGraph`:**
- Click navigation maps to `/explore/ku/{id}` and `/explore/ps/{id}` (Explore-aware)
- Filter tabs (All/Learning/Saved) dim non-matching nodes to 15% opacity
- Full-screen JS overlay on `document.body` (backdrop click / Escape to close) — creates second Vis.js network
- Node colors: violet (#8B5CF6) for Ku, teal (#14B8A6) for PS, blue (#3B82F6) for "You"
- Hub mode uses `GET /api/explore/graph`; entity mode uses existing lateral graph API
- Compact physics settings tuned for 384px sidebar width

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

def ku_detail(request, uid: str, ku: Ku, ...):
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
        cls="text-sm",
    ),
    cls="space-y-2 w-64",
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
