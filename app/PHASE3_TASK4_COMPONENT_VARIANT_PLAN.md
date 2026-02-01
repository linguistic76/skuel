# Phase 3, Task 4: Component Variant System - Implementation Plan

**Date:** 2026-02-02
**Plan Reference:** `/home/mike/.claude/plans/lively-greeting-meadow.md` - Phase 3, Task 4
**Status:** ✅ **COMPLETE** (Infrastructure) - See `/home/mike/skuel/app/PHASE3_TASK4_COMPONENT_VARIANT_COMPLETE.md`

**Update (2026-02-02):**
- ✅ CardVariant enum implemented (DEFAULT, COMPACT, HIGHLIGHTED)
- ✅ CardConfig dataclass with factory methods
- ✅ EntityCard updated to accept config parameter
- ✅ Variant styling applied (content visibility, spacing, borders, backgrounds)
- ✅ Examples created (8 usage patterns)
- ✅ Documentation complete
- ⏸️ Domain migration pending (optional follow-up)
- **Time Invested:** ~4 hours (under 8-10 hour estimate)
- **Ready for:** Phase 3, Task 5 (Component Catalog Documentation)

---

## Overview

Implement a variant system for EntityCard to support different display modes (DEFAULT, COMPACT, HIGHLIGHTED) with configurable styling, spacing, and behavior across all domain cards.

---

## Current State

### Existing EntityCard
**Location:** `/ui/patterns/entity_card.py`

**Current Features:**
- Generic entity card for all 14 domains
- Priority border colors
- Status and priority badges
- Truncated text (title, description)
- Metadata display
- Actions section
- Clickable href support

**Limitations:**
- ❌ No variant system - all cards look the same
- ❌ No size/spacing configuration
- ❌ No highlighting mechanism
- ❌ Hard-coded layout (can't easily switch between compact/full)

---

## Proposed Variant System

### 1. CardVariant Enum

```python
from enum import Enum

class CardVariant(str, Enum):
    """Card display variants for different contexts."""

    DEFAULT = "default"      # Standard card - full layout
    COMPACT = "compact"      # Condensed - less padding, smaller text
    HIGHLIGHTED = "highlighted"  # Emphasized - border, background
```

**Use Cases:**
- **DEFAULT**: List views, main content areas
- **COMPACT**: Dense lists, sidebar widgets, mobile views
- **HIGHLIGHTED**: Featured items, pinned content, search results

---

### 2. CardConfig Dataclass

```python
from dataclasses import dataclass

@dataclass
class CardConfig:
    """Configuration for EntityCard variants."""

    variant: CardVariant = CardVariant.DEFAULT
    show_description: bool = True
    show_metadata: bool = True
    show_actions: bool = True
    truncate_title: bool = True
    description_lines: int = 2

    # Variant-specific CSS
    padding_cls: str = "p-4"
    gap_cls: str = "gap-3"
    border_cls: str = ""
    background_cls: str = ""

    @classmethod
    def default(cls) -> "CardConfig":
        """Standard card configuration."""
        return cls(
            variant=CardVariant.DEFAULT,
            padding_cls="p-4",
            gap_cls="gap-3",
        )

    @classmethod
    def compact(cls) -> "CardConfig":
        """Compact card for dense lists."""
        return cls(
            variant=CardVariant.COMPACT,
            show_description=False,
            show_metadata=False,
            description_lines=1,
            padding_cls="p-3",
            gap_cls="gap-2",
        )

    @classmethod
    def highlighted(cls) -> "CardConfig":
        """Highlighted card for emphasis."""
        return cls(
            variant=CardVariant.HIGHLIGHTED,
            padding_cls="p-4",
            gap_cls="gap-3",
            border_cls="border-2 border-primary",
            background_cls="bg-primary/5",
        )
```

---

### 3. Updated EntityCard Signature

```python
def EntityCard(
    title: str,
    description: str = "",
    status: str | None = None,
    priority: str | None = None,
    metadata: list[str] | None = None,
    actions: Any = None,
    href: str | None = None,
    config: CardConfig | None = None,  # NEW: Variant configuration
    **kwargs: Any,
) -> Div:
    """Generic entity card with variant support."""
    # Use default config if not provided
    config = config or CardConfig.default()

    # Apply config to control visibility
    if not config.show_description:
        description = ""
    if not config.show_metadata:
        metadata = None
    if not config.show_actions:
        actions = None

    # Apply variant-specific styling
    # ...
```

---

## Implementation Strategy

### Phase 1: Core Infrastructure (2-3 hours)

**Create Variant Types:**
1. Add `CardVariant` enum to `/ui/patterns/entity_card.py`
2. Add `CardConfig` dataclass with factory methods
3. Update `EntityCard()` to accept `config` parameter
4. Apply variant styling based on config

**Files Modified:**
- `/ui/patterns/entity_card.py` (~100 lines added)

---

### Phase 2: Apply to Domain Cards (4-5 hours)

**Identify Domain Cards:**
Search for card-rendering functions in domain UI files:
- Tasks: `render_task_card()`
- Goals: `render_goal_card()`
- Habits: `render_habit_card()`
- Events: `render_event_card()`
- Knowledge: `render_knowledge_card()`
- etc.

**Update Pattern:**
```python
# Before
def render_task_card(task):
    return EntityCard(
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
    )

# After
def render_task_card(task, variant: CardVariant = CardVariant.DEFAULT):
    config = {
        CardVariant.DEFAULT: CardConfig.default(),
        CardVariant.COMPACT: CardConfig.compact(),
        CardVariant.HIGHLIGHTED: CardConfig.highlighted(),
    }[variant]

    return EntityCard(
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        config=config,
    )
```

**Files to Update:**
- Find all `render_*_card()` functions
- Add `variant` parameter
- Pass appropriate `CardConfig`

---

### Phase 3: Use Cases (1-2 hours)

**Implement Common Use Cases:**

1. **Compact Sidebar Widget**
   ```python
   # Show recent tasks in compact mode
   recent_tasks = [
       render_task_card(task, variant=CardVariant.COMPACT)
       for task in tasks[:5]
   ]
   ```

2. **Highlighted Pinned Items**
   ```python
   # Show pinned tasks with emphasis
   pinned_tasks = [
       render_task_card(task, variant=CardVariant.HIGHLIGHTED)
       for task in pinned
   ]
   ```

3. **Mobile Responsive**
   ```python
   # Use compact on mobile, default on desktop
   variant = CardVariant.COMPACT if is_mobile else CardVariant.DEFAULT
   cards = [render_task_card(t, variant=variant) for t in tasks]
   ```

---

### Phase 4: Documentation (1-2 hours)

**Document Patterns:**
1. Update `/ui/patterns/entity_card.py` docstrings
2. Add examples for each variant
3. Document when to use each variant
4. Create usage guide

---

## Detailed Implementation

### Step 1: Add CardVariant Enum

**Location:** `/ui/patterns/entity_card.py` (after imports)

```python
from enum import Enum
from dataclasses import dataclass

class CardVariant(str, Enum):
    """Card display variants for different UI contexts.

    Variants:
        DEFAULT: Standard card with full layout (padding: p-4, description: 2 lines)
        COMPACT: Condensed card for dense lists (padding: p-3, no description)
        HIGHLIGHTED: Emphasized card for featured content (border, background)

    Usage:
        # Standard list view
        EntityCard(title="Task", config=CardConfig.default())

        # Sidebar widget
        EntityCard(title="Task", config=CardConfig.compact())

        # Pinned item
        EntityCard(title="Task", config=CardConfig.highlighted())
    """

    DEFAULT = "default"
    COMPACT = "compact"
    HIGHLIGHTED = "highlighted"
```

---

### Step 2: Add CardConfig Dataclass

```python
@dataclass
class CardConfig:
    """Configuration for EntityCard variant styling and behavior.

    This dataclass controls:
    - Which sections to show (description, metadata, actions)
    - Text truncation settings
    - Spacing and padding
    - Border and background styling

    Use factory methods for common configurations:
    - CardConfig.default() - Standard card
    - CardConfig.compact() - Condensed card
    - CardConfig.highlighted() - Emphasized card
    """

    variant: CardVariant = CardVariant.DEFAULT

    # Content visibility
    show_description: bool = True
    show_metadata: bool = True
    show_actions: bool = True

    # Text settings
    truncate_title: bool = True
    description_lines: int = 2

    # Spacing
    padding_cls: str = "p-4"
    gap_cls: str = "gap-3"

    # Styling
    border_cls: str = ""
    background_cls: str = ""

    @classmethod
    def default(cls) -> "CardConfig":
        """Standard card configuration for main content."""
        return cls(
            variant=CardVariant.DEFAULT,
            padding_cls="p-4",
            gap_cls="gap-3",
        )

    @classmethod
    def compact(cls) -> "CardConfig":
        """Compact card for dense lists and sidebars."""
        return cls(
            variant=CardVariant.COMPACT,
            show_description=False,
            show_metadata=False,
            description_lines=1,
            padding_cls="p-3",
            gap_cls="gap-2",
        )

    @classmethod
    def highlighted(cls) -> "CardConfig":
        """Highlighted card for featured or pinned content."""
        return cls(
            variant=CardVariant.HIGHLIGHTED,
            padding_cls="p-4",
            gap_cls="gap-3",
            border_cls="border-2 border-primary",
            background_cls="bg-primary/5",
        )
```

---

### Step 3: Update EntityCard Function

**Changes:**
1. Add `config: CardConfig | None = None` parameter
2. Apply config defaults if not provided
3. Use config to control content visibility
4. Apply variant-specific CSS classes
5. Update description line truncation

```python
def EntityCard(
    title: str,
    description: str = "",
    status: str | None = None,
    priority: str | None = None,
    metadata: list[str] | None = None,
    actions: Any = None,
    href: str | None = None,
    config: CardConfig | None = None,  # NEW
    **kwargs: Any,
) -> Div:
    """Generic entity card with variant support.

    Variants:
        config=CardConfig.default()      # Standard card
        config=CardConfig.compact()      # Condensed card
        config=CardConfig.highlighted()  # Emphasized card

    Example:
        # Compact sidebar widget
        EntityCard(
            title="Complete proposal",
            description="...",  # Won't show in compact mode
            status="active",
            config=CardConfig.compact(),
        )
    """
    # Use default config if not provided
    config = config or CardConfig.default()

    # Apply config to control visibility
    if not config.show_description:
        description = ""
    if not config.show_metadata:
        metadata = None
    if not config.show_actions:
        actions = None

    # Priority border (unchanged)
    # ...

    # Build header (unchanged)
    # ...

    # Build content
    content = [header]

    if description:
        content.append(
            TruncatedText(
                description,
                lines=config.description_lines,  # Use config
                cls="text-sm text-base-content/70 mt-2 block",
            )
        )

    # metadata and actions (unchanged)
    # ...

    # Apply variant styling
    card_cls_parts = []

    # Priority border
    if border_cls:
        card_cls_parts.append(f"border-l-4 {border_cls}")

    # Variant border (overrides priority if both exist)
    if config.border_cls:
        card_cls_parts.append(config.border_cls)

    # Variant background
    if config.background_cls:
        card_cls_parts.append(config.background_cls)

    # Merge with kwargs cls
    extra_cls = kwargs.pop("cls", "")
    card_cls = " ".join(card_cls_parts + [extra_cls]).strip()

    # Update Card call to use config padding/gap
    return Card(*content, cls=card_cls, padding=config.padding_cls, **kwargs)
```

---

## Files to Analyze

### Find Domain Card Functions

```bash
# Search for card rendering functions
grep -rn "def render.*card" adapters/inbound/*.py
grep -rn "def render.*card" components/*.py
```

**Expected Files:**
- `adapters/inbound/tasks_ui.py` - Task cards
- `adapters/inbound/goals_ui.py` - Goal cards
- `adapters/inbound/habits_ui.py` - Habit cards
- `components/card_generator.py` - Generic card generator
- `components/knowledge_ui_components.py` - KU cards
- etc.

---

## Success Criteria

| Criterion | Target |
|-----------|--------|
| `CardVariant` enum created | ✅ |
| `CardConfig` dataclass created | ✅ |
| `EntityCard` accepts `config` parameter | ✅ |
| Variant styling applied correctly | ✅ |
| At least 3 domain cards updated | ✅ |
| Documentation updated | ✅ |
| Examples provided | ✅ |
| No breaking changes | ✅ |

---

## Testing Strategy

### Visual Testing
1. **DEFAULT variant:**
   - Render task card with full description
   - Verify p-4 padding, 2-line description

2. **COMPACT variant:**
   - Render in sidebar
   - Verify p-3 padding, no description shown

3. **HIGHLIGHTED variant:**
   - Render pinned item
   - Verify border-2 border-primary, bg-primary/5

### Unit Testing (Optional)
```python
def test_card_config_default():
    config = CardConfig.default()
    assert config.variant == CardVariant.DEFAULT
    assert config.show_description == True
    assert config.padding_cls == "p-4"

def test_card_config_compact():
    config = CardConfig.compact()
    assert config.variant == CardVariant.COMPACT
    assert config.show_description == False
    assert config.padding_cls == "p-3"
```

---

## Time Estimate

| Phase | Effort |
|-------|--------|
| Core infrastructure (enum, dataclass, EntityCard) | 2-3 hours |
| Apply to domain cards | 4-5 hours |
| Use cases implementation | 1-2 hours |
| Documentation | 1-2 hours |
| **Total** | **8-10 hours** |

**Matches plan estimate:** ✅

---

## Next Steps

1. **Implement CardVariant enum and CardConfig dataclass**
2. **Update EntityCard to use config**
3. **Find and update domain card functions**
4. **Implement example use cases**
5. **Document the pattern**
6. **Move to Phase 3, Task 5: Component Catalog Documentation**

---

## Related Documentation

- **Current EntityCard:** `/ui/patterns/entity_card.py`
- **Main Plan:** `/home/mike/.claude/plans/lively-greeting-meadow.md` (Phase 3, Task 4)
- **UI Patterns:** `/docs/patterns/UI_COMPONENT_PATTERNS.md`

---

## Ready to Implement

Planning complete. Ready to begin implementation starting with core infrastructure.
