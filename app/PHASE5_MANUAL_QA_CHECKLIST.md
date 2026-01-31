# Phase 5: Manual QA Checklist

Quick reference for testing lateral relationships visualization.

---

## Prerequisites

```bash
# Start server
poetry run python main.py

# Verify server is running
curl http://localhost:5001/
```

---

## API Endpoint Tests

### Test Pattern

Replace `{uid}` with actual entity UIDs from your database.

```bash
# Get blocking chain
curl http://localhost:5001/api/tasks/{task_uid}/lateral/chain

# Get alternatives comparison
curl http://localhost:5001/api/goals/{goal_uid}/lateral/alternatives/compare

# Get relationship graph (depth=2)
curl http://localhost:5001/api/habits/{habit_uid}/lateral/graph?depth=2
```

### Expected Response

```json
{
  "success": true,
  "uid": "task_abc123",
  "entity_type": "tasks",
  "chain": [...],
  "alternatives": [...],
  "nodes": [...],
  "edges": [...]
}
```

**Status:** 200 OK
**Response Time:** < 500ms (chain, compare), < 1000ms (graph)

### All 9 Domains

Test each domain (replace `{domain}` and `{uid}`):

- [ ] `/api/tasks/{uid}/lateral/chain`
- [ ] `/api/goals/{uid}/lateral/chain`
- [ ] `/api/habits/{uid}/lateral/chain`
- [ ] `/api/events/{uid}/lateral/chain`
- [ ] `/api/choices/{uid}/lateral/chain`
- [ ] `/api/principles/{uid}/lateral/chain`
- [ ] `/api/ku/{uid}/lateral/chain`
- [ ] `/api/ls/{uid}/lateral/chain`
- [ ] `/api/lp/{uid}/lateral/chain`

---

## UI Integration Tests

### Step-by-Step Checklist

Navigate to any entity detail page (e.g., `/tasks/{uid}`, `/goals/{uid}`, etc.)

#### 1. Page Load
- [ ] Page loads without errors
- [ ] No console errors (open DevTools → Console)
- [ ] Relationships section appears at bottom

#### 2. Relationships Section
- [ ] Section header: "Relationships"
- [ ] 3 collapsible subsections visible:
  - [ ] "Blocking Chain"
  - [ ] "Alternative Approaches"
  - [ ] "Relationship Network"

#### 3. Blocking Chain View
- [ ] Click "Blocking Chain" to expand
- [ ] HTMX request fires (check Network tab)
- [ ] Content loads in < 500ms
- [ ] Vertical flow chart appears (if data exists)
- [ ] OR "No blocking relationships" message (if empty)

#### 4. Alternatives Comparison
- [ ] Click "Alternative Approaches" to expand
- [ ] HTMX request fires
- [ ] Content loads in < 500ms
- [ ] Comparison table appears (if data exists)
- [ ] OR "No alternatives found" message (if empty)

#### 5. Relationship Graph (Vis.js)
- [ ] Click "Relationship Network" to expand
- [ ] HTMX request fires
- [ ] Content loads in < 1000ms
- [ ] Vis.js graph renders with nodes and edges
- [ ] OR "No relationships found" message (if isolated)

#### 6. Graph Interactions
- [ ] **Drag nodes** - Click and drag individual nodes
- [ ] **Zoom** - Mouse wheel zooms in/out
- [ ] **Pan** - Drag canvas background to pan
- [ ] **Click node** - Clicking node navigates to detail page
- [ ] **Depth control** - Depth selector (1-3) changes graph

#### 7. Visual Appearance
- [ ] Nodes are labeled with entity titles
- [ ] Edges are color-coded:
  - Red: BLOCKS
  - Orange: PREREQUISITES
  - Blue: ALTERNATIVES
  - Green: COMPLEMENTARY
  - Purple: SIBLING
  - Gray: RELATED_TO
- [ ] Graph uses force-directed layout (nodes spread naturally)

#### 8. Mobile Responsive
- [ ] Open Chrome DevTools
- [ ] Toggle device emulation (Ctrl+Shift+M)
- [ ] Select "iPhone SE" or custom 375px width
- [ ] Verify:
  - [ ] Relationships section is full-width
  - [ ] Graph renders correctly
  - [ ] Touch gestures work (if on device)

---

## All 9 Domains UI Checklist

Test each domain's detail page:

- [ ] **Tasks:** `/tasks/{uid}` → Relationships section present
- [ ] **Goals:** `/goals/{uid}` → Relationships section present
- [ ] **Habits:** `/habits/{uid}` → Relationships section present
- [ ] **Events:** `/events/{uid}` → Relationships section present
- [ ] **Choices:** `/choices/{uid}` → Relationships section present
- [ ] **Principles:** `/principles/{uid}` → Relationships section present
- [ ] **KU:** `/ku/{uid}` → Relationships section present
- [ ] **LS:** `/ls/{uid}` → Relationships section present
- [ ] **LP:** `/lp/{uid}` → Relationships section present

---

## Performance Tests

### HTMX Lazy Loading Timing

1. Open Chrome DevTools → Network tab
2. Navigate to detail page (e.g., `/tasks/{uid}`)
3. Expand "Relationship Network"
4. Check timing for:
   - [ ] `/api/{domain}/{uid}/lateral/chain` → < 500ms
   - [ ] `/api/{domain}/{uid}/lateral/alternatives/compare` → < 500ms
   - [ ] `/api/{domain}/{uid}/lateral/graph` → < 1000ms

### Console Errors

1. Open Chrome DevTools → Console
2. Navigate to 3-5 different detail pages
3. Expand all 3 relationship subsections
4. **Expected:** Zero errors

### Memory/CPU

1. Open Chrome DevTools → Performance
2. Record while interacting with graph:
   - Drag 5-10 nodes
   - Zoom in/out 5 times
   - Pan around canvas
3. **Expected:** Smooth 60 FPS, no memory spikes

---

## Edge Cases

### Empty Data
- [ ] Navigate to entity with NO relationships
- [ ] Verify each section shows appropriate message:
  - "No blocking relationships found"
  - "No alternatives found"
  - "No relationships found"

### Large Graphs (100+ nodes)
- [ ] Set depth=3 on entity with many relationships
- [ ] Graph should render in < 3 seconds
- [ ] Vis.js physics should stabilize in < 5 seconds

### Concurrent Requests
- [ ] Rapidly expand/collapse all 3 sections
- [ ] No race conditions or duplicate requests
- [ ] Content loads correctly

---

## Browser Compatibility

Test in multiple browsers:

- [ ] **Chrome** (primary target)
- [ ] **Firefox**
- [ ] **Safari** (macOS/iOS)
- [ ] **Edge**

Expected behavior: Identical across all browsers

---

## Known Issues / Expected Behavior

### Phase 5 Limitations
- **Placeholder data for curriculum domains:** LS/LP may show "Lorem ipsum" until real data populated
- **Empty graphs:** New installations will have no relationships → empty graphs expected
- **Performance:** Graphs with 500+ nodes may be slow (future optimization)

### Not Bugs
- Empty sections when no relationships exist
- Graph auto-layouts may look different each time (force-directed is non-deterministic)
- Mobile touch gestures may differ from desktop mouse (expected)

---

## Success Criteria

**All green checkboxes = Phase 5 QA PASSED** ✅

Minimum required:
- [ ] All 9 domain detail pages load
- [ ] Relationships section present on each
- [ ] No console errors
- [ ] API endpoints return 200 OK
- [ ] Vis.js graph renders (when data exists)
- [ ] Graph interactions work (drag, zoom, click)

---

## Reporting Issues

If any test fails:

1. **Capture evidence:**
   - Screenshot of error
   - Browser console output
   - Network tab (failed requests)

2. **Document steps:**
   - Exact URL visited
   - Actions taken
   - Expected vs actual behavior

3. **Create issue:**
   - File in project issue tracker
   - Tag with `Phase5`, `lateral-relationships`, `QA`

---

## Quick Commands

```bash
# Run automated verification
./scripts/verify_phase5_complete.sh

# Run unit tests
poetry run pytest tests/unit/test_lateral_graph_queries.py -v

# Start server
poetry run python main.py

# Check server logs
tail -f /tmp/server.log

# Test API endpoint
curl http://localhost:5001/api/tasks/{uid}/lateral/graph?depth=2 | jq
```

---

**Last Updated:** 2026-02-01
**Phase 5 Status:** Ready for Manual QA
