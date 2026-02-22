---
title: Hierarchy Components Guide
updated: '2026-02-02'
category: patterns
related_skills:
- skuel-component-composition
related_docs: []
---
# Hierarchy Components Guide

**Date:** 2026-01-30
**Status:** Complete
**Version:** 1.0

---

## Overview

SKUEL provides a comprehensive set of hierarchy visualization components for displaying parent-child relationships across all domains:

1. **TreeView** - Custom expandable tree with full features
2. **AccordionHierarchy** - DaisyUI collapse-based for content-heavy nodes
3. **Breadcrumbs** - Ancestor navigation trail
4. **IndentedList** - Simple static indented display

All components support HTMX lazy loading, Alpine.js state management, and work across Goals, Habits, Events, Choices, Principles, and LP domains.

---

## Quick Start

**Skill:** [@skuel-component-composition](../../.claude/skills/skuel-component-composition/SKILL.md)

### TreeView - Full-Featured Tree

```python
from ui.patterns.tree_view import TreeView
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType

# In your route handler
@rt("/goals/{uid}/hierarchy")
async def goal_hierarchy(request: Request, uid: str):
    user_uid = require_authenticated_user(request)

    # Fetch root goal
    goal_result = await goals_service.get(uid)
    if goal_result.is_error:
        return NotFound()

    goal = goal_result.value

    # Render page with TreeView
    content = Stack(
        PageHeader(
            title=f"Hierarchy: {goal.title}",
            description="Explore goal breakdown",
        ),
        TreeView(
            root_uid=uid,
            entity_type="goal",
            children_endpoint="/api/goals/{uid}/children",
            move_endpoint="/api/goals/{uid}/move",
            show_checkboxes=True,
            keyboard_nav=True,
            draggable=True,
        ),
    )

    return BasePage(
        content=content,
        title=f"{goal.title} - Hierarchy",
        page_type=PageType.STANDARD,
        request=request,
    )
```

### AccordionHierarchy - Content-Rich Display

```python
from ui.patterns.accordion_hierarchy import AccordionHierarchy

# Fetch root nodes with metadata
root_goals_result = await goals_service.search(user_uid=user_uid, limit=10)
root_goals = root_goals_result.value

# Convert to dicts
goals_data = []
for g in root_goals:
    # Check if has children
    children_result = await goals_service.get_subgoals(g.uid, depth=1)
    has_children = not children_result.is_error and len(children_result.value) > 0

    goals_data.append({
        "uid": g.uid,
        "title": g.title,
        "description": g.description,
        "has_children": has_children,
        "child_count": len(children_result.value) if not children_result.is_error else 0,
    })

# Render
return AccordionHierarchy(
    root_nodes=goals_data,
    entity_type="goal",
    children_endpoint="/api/goals/{uid}/children",
    mode="checkbox",  # Multiple items can be open
    lazy_load=True,
    show_metadata=True,
)
```

### Breadcrumbs - Navigation Trail

```python
from ui.patterns.breadcrumbs import Breadcrumbs

# Build ancestor path (walk up the tree)
ancestors = []
current_result = await goals_service.get(uid)
current = current_result.value if not current_result.is_error else None

while current:
    ancestors.insert(0, {
        "uid": current.uid,
        "title": current.title,
        "url": f"/goals/{current.uid}",
    })
    parent_result = await goals_service.get_parent_goal(current.uid)
    current = parent_result.value if not parent_result.is_error else None

# Mark last item as current (no link)
if ancestors:
    ancestors[-1]["url"] = None

# Render above main content
Breadcrumbs(
    path=ancestors,
    show_home=True,
    home_url="/goals",
)
```

### IndentedList - Simple Static Display

```python
from ui.patterns.indented_list import IndentedList

# Fetch full hierarchy (for shallow trees only!)
hierarchy_result = await goals_service.get_subgoals(uid, depth=3)
children = hierarchy_result.value

# Flatten to list with depth
items = []

def flatten_goals(goals: list[Goal], depth: int = 0):
    for goal in goals:
        items.append({"uid": goal.uid, "title": goal.title, "depth": depth})
        # Get children
        children_result = await goals_service.get_subgoals(goal.uid, depth=1)
        if not children_result.is_error:
            flatten_goals(children_result.value, depth + 1)

flatten_goals([root_goal], depth=0)

# Render
IndentedList(
    items=items,
    entity_type="goal",
    link_pattern="/goals/{uid}",
)
```

---

## Features

### 1. Lazy Loading

TreeView and AccordionHierarchy support HTMX-based lazy loading:

**Flow:**
1. User clicks expand icon
2. Alpine.js dispatches custom event `expand-{uid}`
3. HTMX listens for event, fetches `/api/goals/{uid}/children`
4. Server returns `TreeNodeList` HTML
5. HTMX swaps into `#children-{uid}` container
6. Alpine.js re-initializes on new nodes

**Benefits:**
- Fast initial page load (only root nodes rendered)
- Scales to deep hierarchies (1000+ total nodes)
- Reduces server memory usage

**Example:**

```python
# TreeView automatically uses lazy loading
TreeView(
    root_uid=uid,
    entity_type="goal",
    children_endpoint="/api/goals/{uid}/children",  # HTMX fetches on expand
)
```

### 2. Drag-and-Drop

TreeView supports node reordering via HTML5 drag-and-drop:

**Flow:**
1. User drags node (HTML5 dragstart event)
2. Alpine.js stores `draggedNode` UID
3. User drops on new parent (drop event)
4. Alpine.js validates (prevents cycle via `isDescendant()`)
5. HTMX posts to `/api/goals/{uid}/move` with `new_parent_uid`
6. Server calls `create_subgoal_relationship` + `remove_subgoal_relationship`
7. HTMX refreshes affected nodes
8. Toast notification confirms success

**Cycle Prevention:**
- **Client-side:** `isDescendant(newParent, draggedNode)` checks DOM tree
- **Server-side:** Service validates no circular relationships (TODO: implement)

**Example:**

```python
TreeView(
    root_uid=uid,
    entity_type="goal",
    children_endpoint="/api/goals/{uid}/children",
    move_endpoint="/api/goals/{uid}/move",  # Enable drag-drop
    draggable=True,
)
```

### 3. Keyboard Navigation

TreeView supports full keyboard navigation:

| Key | Action |
|-----|--------|
| ↓ | Move to next visible node |
| ↑ | Move to previous visible node |
| → | Expand collapsed node, or move to first child |
| ← | Collapse expanded node, or move to parent |
| Enter/Space | Toggle expand/collapse |
| Tab | Focus next tree (exit tree navigation) |

**Implementation:**
- Alpine.js `handleKeydown()` method
- Tracks `focusedNode` UID
- Visual focus indicator (ring-2 ring-primary)
- Smooth scrolling to focused node

**Example:**

```python
TreeView(
    root_uid=uid,
    entity_type="goal",
    children_endpoint="/api/goals/{uid}/children",
    keyboard_nav=True,  # Enable keyboard navigation
)
```

**Accessibility:**
- Tree container is focusable (`tabindex="0"`)
- Visual focus indicators
- Prevents default only for handled keys
- Allows Tab key to exit tree

### 4. Multi-Select

TreeView supports checkbox-based multi-select:

**Features:**
- Checkbox on each node
- Alpine.js `selected` array tracks UIDs
- "Select All" / "Deselect All" buttons
- Bulk operations: delete, move, tag

**Example:**

```python
# Enable checkboxes
TreeView(
    root_uid=uid,
    entity_type="goal",
    children_endpoint="/api/goals/{uid}/children",
    show_checkboxes=True,  # Show checkboxes on each node
)

# Add bulk action controls
Div(
    **{"x-show": "selected.length > 0", "x-cloak": True}
)(
    Card(
        Row(
            Span(**{"x-text": "`${selected.length} items selected`"}),
            Button(
                "Delete Selected",
                variant="danger",
                **{"x-on:click": "bulkDelete()"},
            ),
        ),
    ),
)
```

**Alpine.js Methods:**
```javascript
selectAll()      // Select all visible nodes
deselectAll()    // Clear selection
bulkDelete()     // Delete all selected nodes
```

### 5. Inline Editing

TreeView supports inline title editing:

**Flow:**
1. User double-clicks node title
2. Alpine.js sets `editingNode = uid`
3. Title text replaced with input field (x-show conditional)
4. User edits, presses Enter
5. HTMX patches `/api/goals/{uid}` with new title
6. Server validates and updates
7. Alpine.js updates DOM and exits edit mode

**Example:**

```python
# Inline editing is enabled by default in TreeView
TreeView(
    root_uid=uid,
    entity_type="goal",
    children_endpoint="/api/goals/{uid}/children",
    # No special flag needed - double-click any title to edit
)
```

---

## API Requirements

To use hierarchy components, your domain must provide these API endpoints:

### GET /api/{domain}/{uid}/children

**Purpose:** Fetch children for lazy loading

**Query Params:** None

**Returns:** HTML (TreeNodeList component)

```html
<div>
    <div class="tree-node" data-uid="child1" data-depth="1">...</div>
    <div class="tree-node" data-uid="child2" data-depth="1">...</div>
</div>
```

**Implementation:**

```python
from ui.patterns.tree_view import TreeNodeList

@rt("/api/goals/{uid}/children")
async def get_children(request: Request, uid: str):
    user_uid = require_authenticated_user(request)

    # Verify ownership
    ownership_result = await goals_service.verify_ownership(uid, user_uid)
    if ownership_result.is_error:
        return Div(Span("Not found", cls="text-error"))

    # Get children
    result = await goals_service.get_subgoals(uid, depth=1)

    if result.is_error:
        return Div(Span(f"Error: {result.error}", cls="text-error"))

    children = result.value

    # Convert to dicts
    children_data = []
    for child in children:
        # Check if child has children
        child_children = await goals_service.get_subgoals(child.uid, depth=1)
        has_children = not child_children.is_error and len(child_children.value) > 0

        children_data.append({
            "uid": child.uid,
            "title": child.title,
            "has_children": has_children,
        })

    # Render
    return TreeNodeList(
        nodes=children_data,
        entity_type="goal",
        children_endpoint="/api/goals/{uid}/children",
        parent_depth=1,  # Depth of current node
    )
```

### POST /api/{domain}/{uid}/move

**Purpose:** Move node to new parent (drag-drop)

**Request Body:**
```json
{"new_parent_uid": "goal_xyz789"}
```

**Response:**
```json
{"success": true, "message": "Goal moved successfully"}
```

**Implementation:**

```python
@rt("/api/goals/{uid}/move", methods=["POST"])
async def move_goal(request: Request, uid: str):
    user_uid = require_authenticated_user(request)

    # Parse body
    body = await request.json()
    new_parent_uid = body.get("new_parent_uid")

    if not new_parent_uid:
        return {"success": False, "error": "new_parent_uid required"}, 400

    # Verify ownership of both nodes
    ownership_result = await goals_service.verify_ownership(uid, user_uid)
    if ownership_result.is_error:
        return {"success": False, "error": "Not found"}, 404

    parent_ownership = await goals_service.verify_ownership(new_parent_uid, user_uid)
    if parent_ownership.is_error:
        return {"success": False, "error": "Parent not found"}, 404

    # Remove old parent relationship (if exists)
    old_parent_result = await goals_service.get_parent_goal(uid)
    if not old_parent_result.is_error and old_parent_result.value:
        await goals_service.remove_subgoal_relationship(
            old_parent_result.value.uid,
            uid
        )

    # Create new relationship
    result = await goals_service.create_subgoal_relationship(new_parent_uid, uid)

    if result.is_error:
        return {"success": False, "error": str(result.error)}, 400

    return {"success": True, "message": "Goal moved successfully"}
```

### PATCH /api/{domain}/{uid}

**Purpose:** Update node (inline edit)

**Request Body:**
```json
{"title": "New Title"}
```

**Response:**
```json
{"success": true, "title": "New Title", "uid": "goal_abc"}
```

**Implementation:**

```python
@rt("/api/goals/{uid}", methods=["PATCH"])
async def update_goal(request: Request, uid: str):
    user_uid = require_authenticated_user(request)

    # Parse body
    body = await request.json()
    title = body.get("title")

    if not title:
        return {"success": False, "error": "title required"}, 400

    # Verify ownership
    ownership_result = await goals_service.verify_ownership(uid, user_uid)
    if ownership_result.is_error:
        return {"success": False, "error": "Not found"}, 404

    # Update
    result = await goals_service.update(uid, {"title": title})

    if result.is_error:
        return {"success": False, "error": str(result.error)}, 400

    return {"success": True, "title": title, "uid": uid}
```

### POST /api/{domain}/bulk-delete

**Purpose:** Delete multiple nodes (multi-select)

**Request Body:**
```json
{"uids": ["goal1", "goal2", "goal3"]}
```

**Response:**
```json
{
  "success": true,
  "deleted_count": 3,
  "errors": []
}
```

**Implementation:**

```python
@rt("/api/goals/bulk-delete", methods=["POST"])
async def bulk_delete(request: Request):
    user_uid = require_authenticated_user(request)

    # Parse body
    body = await request.json()
    uids = body.get("uids", [])

    if not uids:
        return {"success": False, "error": "uids required"}, 400

    deleted_count = 0
    errors = []

    for uid in uids:
        # Verify ownership
        ownership_result = await goals_service.verify_ownership(uid, user_uid)
        if ownership_result.is_error:
            errors.append(f"{uid}: Not found")
            continue

        # Delete
        result = await goals_service.delete(uid)
        if result.is_error:
            errors.append(f"{uid}: {result.error}")
        else:
            deleted_count += 1

    return {
        "success": len(errors) == 0,
        "deleted_count": deleted_count,
        "errors": errors,
    }
```

---

## Component Comparison

| Feature | TreeView | AccordionHierarchy | Breadcrumbs | IndentedList |
|---------|----------|-------------------|-------------|-------------|
| **Expand/Collapse** | ✅ | ✅ | ❌ | ❌ |
| **Lazy Loading** | ✅ | ✅ | ❌ | ❌ |
| **Drag-Drop** | ✅ | ⚠️ Limited | ❌ | ❌ |
| **Keyboard Nav** | ✅ | ❌ | ❌ | ❌ |
| **Multi-Select** | ✅ | ❌ | ❌ | ❌ |
| **Inline Edit** | ✅ | ❌ | ❌ | ❌ |
| **Content-Rich Nodes** | ⚠️ Compact | ✅ Best | ❌ | ⚠️ Basic |
| **Deep Trees (10+ levels)** | ✅ Excellent | ⚠️ Okay | ❌ | ⚠️ Okay |
| **Performance (1000+ nodes)** | ✅ (with lazy load) | ✅ (with lazy load) | N/A | ❌ Slow |

---

## Best Practices

### When to Use Each Component

**TreeView:**
- Goal breakdowns (OKRs, project milestones)
- Habit stacking hierarchies
- Event schedules with sub-events
- File/folder-like navigation
- **Use when:** Interactive features needed (drag-drop, keyboard, multi-select)

**AccordionHierarchy:**
- Knowledge Unit organization (course → module → lesson)
- Principle value hierarchies (core → supporting → derived)
- Choice decision trees with descriptions
- Documentation/wiki navigation
- **Use when:** Nodes have substantial metadata/content

**Breadcrumbs:**
- Every detail page with hierarchy
- Above TreeView/Accordion for context
- Navigation aid in deeply nested structures
- **Use when:** User needs context of current location

**IndentedList:**
- Quick overviews (< 50 items)
- Static displays without interaction
- Print-friendly hierarchy views
- Sidebar navigation (shallow trees)
- **Use when:** Simple display, no interaction needed

### Performance Optimization

1. **Always use lazy loading for deep trees:**
   ```python
   TreeView(root_uid=uid, ...)  # ✅ Lazy loads by default
   ```

2. **Limit initial render depth:**
   ```python
   # Fetch only direct children
   children = await goals_service.get_subgoals(uid, depth=1)  # ✅
   all_descendants = await goals_service.get_subgoals(uid, depth=99)  # ❌
   ```

3. **Batch API requests:**
   ```python
   # Bad: N+1 queries
   for goal in goals:
       has_children = await goals_service.get_subgoals(goal.uid)

   # Good: Single query with child counts
   # (Future enhancement: add get_goals_with_child_counts method)
   ```

4. **Use IndentedList for small trees:**
   ```python
   if total_nodes < 50:
       return IndentedList(items=all_items)  # ✅ Faster render
   else:
       return TreeView(root_uid=root_uid)  # ✅ Better UX
   ```

### Accessibility

All components include:

- **Semantic HTML:** Proper structure (divs for layout, no table abuse)
- **ARIA attributes:** Future enhancement for `role="tree"`, `aria-expanded`
- **Keyboard support:** Full navigation via arrow keys (TreeView)
- **Focus management:** Visible focus indicators
- **Screen reader support:** Descriptive text, live regions (future)

### Responsive Design

Components are mobile-friendly:

- **TreeView:** Smaller indent on mobile (12px vs 24px on desktop)
- **AccordionHierarchy:** Stacks naturally on mobile
- **Breadcrumbs:** Wraps to multiple lines
- **IndentedList:** Smaller indent on mobile

**Mobile CSS:**

```css
@media (max-width: 640px) {
    .tree-container {
        max-height: 400px;  /* Shorter on mobile */
    }

    .tree-node .node-content {
        font-size: 0.75rem;  /* Smaller text */
    }
}
```

---

## Troubleshooting

### Children not loading

**Symptom:** Click expand icon, nothing happens

**Fixes:**

1. **Check browser console** for HTMX errors
2. **Verify endpoint returns HTML** (not JSON):
   ```python
   return TreeNodeList(nodes=children_data, ...)  # ✅ HTML
   return {"nodes": children_data}  # ❌ JSON
   ```
3. **Ensure `hx-trigger` matches Alpine event**:
   ```html
   <div hx-trigger="expand-{uid} from:body">  <!-- ✅ Correct -->
   <div hx-trigger="click">  <!-- ❌ Wrong trigger -->
   ```
4. **Check Alpine dispatches event**:
   ```javascript
   document.body.dispatchEvent(new CustomEvent('expand-' + uid));  // ✅
   ```

### Drag-drop not working

**Symptom:** Can't drag nodes

**Fixes:**

1. **Verify `draggable="true"` attribute** on node:
   ```html
   <div draggable="true" ...>  <!-- ✅ -->
   <div>  <!-- ❌ Missing draggable -->
   ```
2. **Check Alpine.js handlers exist**:
   ```javascript
   handleDragStart(event, uid) { ... }  // Must be defined
   ```
3. **Ensure move endpoint returns JSON**:
   ```python
   return {"success": True}  # ✅
   return "Success"  # ❌ Not JSON
   ```
4. **Verify HTMX processes response**:
   - Check Network tab for 200 response
   - Check for CORS errors if using different port

### Keyboard navigation jumps around

**Symptom:** Arrow keys don't navigate properly

**Fixes:**

1. **Ensure tree container is focusable**:
   ```html
   <div class="tree-container" tabindex="0">  <!-- ✅ -->
   <div class="tree-container">  <!-- ❌ Not focusable -->
   ```
2. **Check `handleKeydown` prevents default**:
   ```javascript
   if (handled) event.preventDefault();  // ✅ Must prevent default
   ```
3. **Verify only visible nodes in DOM** (collapsed nodes should be hidden via `x-show`)

### Alpine.js not initializing after HTMX swap

**Symptom:** New nodes don't respond to clicks after loading

**Fixes:**

1. **Verify HTMX event listener exists** in skuel.js:
   ```javascript
   document.addEventListener('htmx:load', function(event) {
       var loadedElement = event.detail.elt;
       if (loadedElement && loadedElement._x_dataStack === undefined) {
           window.Alpine.initTree(loadedElement);
       }
   });
   ```
2. **This is already implemented** in skuel.js:1141-1164
3. **Check console for Alpine errors**

---

## Examples

### Complete Goals Hierarchy Page

See `/adapters/inbound/goals_ui.py:1351` for full example:

```python
@rt("/goals/{uid}/hierarchy")
async def goal_hierarchy_view(request, uid: str):
    """Hierarchy tree view for a goal and its subgoals."""
    user_uid = require_authenticated_user(request)

    # Fetch root goal
    result = await goals_service.get_for_user(uid, user_uid)
    if result.is_error:
        return NotFound()

    goal = result.value

    # Render hierarchy view
    content = GoalsViewComponents.render_hierarchy_view(
        root_uid=uid,
        root_goal=goal,
    )

    return BasePage(
        content=content,
        title=f"{goal.title} - Hierarchy",
        page_type=PageType.STANDARD,
        request=request,
    )
```

### Hierarchy View Component

See `/components/goals_views.py:609` for full example:

```python
@staticmethod
def render_hierarchy_view(root_uid: str, root_goal: Goal) -> Div:
    """Render goal hierarchy tree view."""
    from ui.patterns.tree_view import TreeView

    return Stack(
        # Header with controls
        PageHeader(
            title=f"Hierarchy: {root_goal.title}",
            description="Explore goal breakdown",
            actions=Row(
                Button("Expand All", **{"x-on:click": "expandAll()"}),
                Button("Collapse All", **{"x-on:click": "collapseAll()"}),
            ),
        ),
        # Tree view
        TreeView(
            root_uid=root_uid,
            entity_type="goal",
            children_endpoint="/api/goals/{uid}/children",
            move_endpoint="/api/goals/{uid}/move",
            show_checkboxes=True,
            keyboard_nav=True,
            draggable=True,
        ),
        # Bulk actions
        Div(**{"x-show": "selected.length > 0", "x-cloak": True})(
            Card(
                Span(**{"x-text": "`${selected.length} selected`"}),
                Button("Delete", **{"x-on:click": "bulkDelete()"}),
            ),
        ),
        gap=6,
    )
```

---

## Architecture Notes

### Component Files

| File | Purpose | Lines |
|------|---------|-------|
| `/ui/patterns/tree_view.py` | TreeView, TreeNodeList | ~250 |
| `/ui/patterns/accordion_hierarchy.py` | AccordionHierarchy | ~200 |
| `/ui/patterns/breadcrumbs.py` | Breadcrumbs | ~80 |
| `/ui/patterns/indented_list.py` | IndentedList | ~100 |
| `/static/js/skuel.js` | hierarchyTree() Alpine component | +300 |
| `/static/css/hierarchy.css` | Hierarchy styles | ~120 |

### Route Files

| File | Purpose |
|------|---------|
| `/adapters/inbound/route_factories/hierarchy_route_factory.py` | Generic route factory |
| `/adapters/inbound/hierarchy_routes.py` | Route registration |

### Integration Files

| File | Purpose |
|------|---------|
| `/components/goals_views.py` | Example: Goals hierarchy view |
| `/adapters/inbound/goals_ui.py` | Example: Route handler |

---

## Future Enhancements

### Virtual Scrolling
For trees with 1000+ nodes:
- Use Intersection Observer API
- Render only visible nodes
- Recycle DOM elements

### Search/Filter
- Filter tree by title
- Highlight matching nodes
- Auto-expand to matches

### Tree Visualization
- D3.js tree diagram
- Collapsible radial tree
- Org chart style

### Export/Import
- Export hierarchy to JSON
- Import from CSV/JSON
- Generate markdown outline

### Undo/Redo
- Track move operations
- Undo drag-drop mistakes
- Command pattern implementation

---

## Related Documentation

- `/docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md` - Backend hierarchical methods
- `/docs/migrations/HIERARCHICAL_METHODS_IMPLEMENTATION_COMPLETE_2026-01-30.md` - Backend implementation
- `/ui/layouts/base_page.py` - BasePage includes hierarchy.css
- `/static/js/skuel.js` - Alpine.js components

---

**Status:** ✅ Complete (2026-01-30)
**Tested:** Goals domain
**Ready for:** Habits, Events, Choices, Principles, LP
