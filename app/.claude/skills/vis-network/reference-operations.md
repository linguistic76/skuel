# vis-network Reference: Best Practices, Anti-Patterns, Checklist, Troubleshooting & Performance

> On-demand reference for the [`vis-network`](SKILL.md) skill. SKILL.md holds the overview, quick start, decision trees, and summary; this file holds Best Practices, Anti-Patterns, the Integration Checklist, Troubleshooting, and Performance Metrics.

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
from ui.patterns.skeleton import SkeletonLines

# Alpine component handles loading automatically
Div(
    **{
        "x-data": "relationshipGraph('task_123', 'tasks', 1)",
        "x-init": "loadGraph()",
    },
    # Shimmer skeleton visible while loading — never plain text
    Div(SkeletonLines(count=4), **{"x-show": "loading"}),
    Div("Error: ", **{"x-show": "error", "x-text": "error"}),
    Div(**{"x-ref": "container", "x-show": "!loading && !error"}),
)
```

**Explore graph note:** `ExploreGraphView` (`ui/explore/graph.py`) uses a different approach — an SVG with shimmer circles and edges is embedded directly inside `explore-graph-container`, and JS removes it by id (`#explore-graph-skeleton`) just before `new vis.Network()` renders. This gives a graph-shaped cue rather than text lines.

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

1. Navigate to entity detail page (e.g. `/tasks/detail?uid=...`, `/explore/ku/{uid}`)
2. Scroll to "Relationships" section
3. Click "Interactive Graph" tab
4. Change depth dropdown (1 → 2 → 3)
5. Click a node → should navigate to that entity's detail page (server-resolved `node.url`)
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
| **Service not initialized** | Verify `services.lateral_relationships` exists in `services_bootstrap/_container.py`. |

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
