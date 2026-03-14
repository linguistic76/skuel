---
title: Shared UI Components - Quick Reference Card
updated: 2025-11-27
status: current
category: guides
tags: [guides, quick, reference, shared]
related: []
---

# Shared UI Components - Quick Reference Card

**TL;DR:** Stop copying dashboard code. Use `SharedUIComponents` instead.

> **Note:** For page-level layout (container widths, spacing tokens, page headers), see the **Unified UX Design System** in `/docs/patterns/UI_COMPONENT_PATTERNS.md`. This guide covers dashboard content patterns within those layouts.

## The One Pattern You Need

```python
from ui.patterns.entity_dashboard import SharedUIComponents

# This replaces 80+ lines of manual composition
dashboard = SharedUIComponents.render_entity_dashboard(
    title="🎯 Your Dashboard",
    stats={'total': {'label': 'Total', 'value': 42, 'color': 'blue'}},
    entities=your_entities,
    entity_renderer=lambda e: YourEntityCard(e),
    quick_actions=[{'label': '➕ New', 'href': '/create', 'variant': 'primary'}]
)
```

## Common Patterns

### 1. Stats Cards Only

```python
stats = SharedUIComponents.render_stats_cards({
    'total': {'label': 'Total', 'value': 125, 'color': 'blue'},
    'active': {'label': 'Active', 'value': 78, 'color': 'green'},
    'urgent': {'label': 'Urgent', 'value': 12, 'color': 'red'}
})
```

**Colors:** blue, green, orange, purple, red, gray, yellow, indigo

### 2. Quick Actions Bar

```python
actions = SharedUIComponents.render_quick_actions([
    {'label': '➕ New', 'href': '/create', 'variant': 'primary'},
    {'label': '📊 Stats', 'hx_get': '/stats', 'hx_target': '#main', 'variant': 'secondary'}
])
```

### 3. Entity List with Filter

```python
list_view = SharedUIComponents.render_entity_list(
    entities=items,
    entity_renderer=lambda item: ItemCard(item),
    categories=["work", "personal"],
    filter_endpoint="/items/filter"
)
```

### 4. Entity Grid

```python
grid = SharedUIComponents.render_entity_grid(
    entities=items,
    entity_renderer=lambda item: ItemCard(item),
    columns=3
)
```

### 5. Empty State

```python
empty = SharedUIComponents.render_empty_state(
    icon="📋",
    title="No items yet",
    message="Create your first item",
    action={'label': 'Create', 'href': '/create', 'variant': 'primary'}
)
```

### 6. Search Bar

```python
search = SharedUIComponents.render_search_bar(
    search_endpoint="/search",
    placeholder="Search items..."
)
```

## Stats Card Format

```python
{
    'stat_key': {
        'label': 'Display Label',  # Required
        'value': 42,               # Required (str or int)
        'color': 'blue'            # Required
    }
}
```

## Action Button Format

```python
{
    'label': '➕ Button Text',        # Required
    'variant': 'primary',           # Required
    'href': '/path'                   # Use href OR hx_get
    # OR
    'hx_get': '/endpoint',            # HTMX alternative
    'hx_target': '#target-id'         # Optional with hx_get
}
```

## Color Palette

| Color | Use Case | Example |
|-------|----------|---------|
| `blue` | Totals, counts | Total Tasks: 125 |
| `green` | Success, completed | Completed: 78 |
| `orange` | Warnings, pending | Pending: 15 |
| `red` | Errors, overdue | Overdue: 3 |
| `purple` | Rates, percentages | 87% Complete |
| `gray` | Inactive, archived | Archived: 12 |
| `yellow` | Highlights | Featured: 5 |
| `indigo` | Secondary info | Followers: 234 |

## Migration Checklist

Refactoring an existing UI file:

- [ ] Find the dashboard rendering function
- [ ] Extract stats into dict format
- [ ] Extract actions into list format
- [ ] Keep domain-specific entity renderer
- [ ] Replace with `SharedUIComponents.render_entity_dashboard()`
- [ ] Test HTMX interactions
- [ ] Delete old manual composition code

**Time:** 30-60 minutes per file

## Common Mistakes

### ❌ Wrong: Incomplete stats format

```python
stats = {'total': 42}  # Missing label and color
```

### ✅ Correct: Full format

```python
stats = {'total': {'label': 'Total', 'value': 42, 'color': 'blue'}}
```

### ❌ Wrong: Missing lambda

```python
entity_renderer=EntityCard  # Won't work
```

### ✅ Correct: Use lambda or function

```python
entity_renderer=lambda e: EntityCard(e)
```

### ❌ Wrong: Mixing href and hx_get

```python
{'label': 'Button', 'href': '/path', 'hx_get': '/endpoint'}  # Pick one!
```

### ✅ Correct: Use one or the other

```python
{'label': 'Button', 'href': '/path'}  # Standard link
# OR
{'label': 'Button', 'hx_get': '/endpoint', 'hx_target': '#main'}  # HTMX
```

## When to Use What

| Need | Component | Example |
|------|-----------|---------|
| Full dashboard | `render_entity_dashboard()` | Main page |
| Just stats | `render_stats_cards()` | Analytics widget |
| Action buttons | `render_quick_actions()` | Toolbar |
| List with filter | `render_entity_list()` | Filterable items |
| Card grid | `render_entity_grid()` | Gallery view |
| No items | `render_empty_state()` | First-time UX |
| Search | `render_search_bar()` | Find items |

## Performance Tips

1. **Use `entity_renderer` for heavy computation**
   ```python
   def render_complex_card(entity):
       # Do expensive work once per entity
       return ComplexCard(entity)

   # Pass function, not inline lambda
   entity_renderer=render_complex_card
   ```

2. **Limit entities for large datasets**
   ```python
   # Don't render 10,000 entities
   entities=items[:50]  # Pagination!
   ```

3. **Use HTMX for dynamic updates**
   ```python
   # Load initial view fast, lazy-load rest
   hx_get="/load-more"
   hx_trigger="revealed"
   ```

## Need More Help?

- **Full Guide:** `/docs/SHARED_UI_COMPONENTS_GUIDE.md`
- **Example:** `/examples/habits_ui_refactored_example.py`
- **Source:** `/ui/patterns/entity_dashboard.py`

## One More Example

**Before (80+ lines):**
```python
def render_dashboard(entities):
    navbar = UnifiedComponents.create_navbar()
    stats = Div(
        Card(...), Card(...), Card(...), Card(...)
    )
    actions = Div(
        Button(...), Button(...), Button(...)
    )
    entity_list = Card(
        Select(...),
        Div(*[render_card(e) for e in entities])
    )
    return Div(navbar, H1(...), stats, actions, entity_list)
```

**After (20 lines):**
```python
def render_dashboard(entities):
    return SharedUIComponents.render_entity_dashboard(
        title="Dashboard",
        stats={'total': {'label': 'Total', 'value': len(entities), 'color': 'blue'}},
        entities=entities,
        entity_renderer=render_card,
        quick_actions=[{'label': 'New', 'href': '/create', 'variant': 'primary'}]
    )
```

**Lines saved: 60+ (75% reduction)**

---

**Remember:** If you're manually composing stats cards, action buttons, or entity lists, you should probably be using `SharedUIComponents` instead.
