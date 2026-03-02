---
title: Constants Usage Guide
updated: 2025-11-27
category: patterns
related_skills: []
related_docs: []
---

# Constants Usage Guide

**Core Principle:** "Constants define behavior, services consume them"

**Last Updated:** 2025-11-16

## Overview

SKUEL uses centralized constants in `/core/constants.py` to eliminate magic numbers and provide a single source of truth for numeric thresholds, limits, and configuration values.

This follows the same philosophy as `core/models/enums/` but for numeric constants rather than enumerations.

## Philosophy

**Problem:** Hardcoded magic numbers scattered throughout the codebase
```python
# ❌ BAD - Magic numbers
depth = 3  # What does 3 mean?
confidence = 0.8  # Why 0.8?
limit = 100  # Is this the right limit?
```

**Solution:** Named constants with documentation
```python
# ✅ GOOD - Named constants
from core.constants import GraphDepth, ConfidenceLevel, QueryLimit

depth = GraphDepth.DEFAULT  # Rich bi-directional context
confidence = ConfidenceLevel.STANDARD  # Standard minimum confidence
limit = QueryLimit.COMPREHENSIVE  # Comprehensive results
```

## Benefits

1. **Single Edit Point** - Change threshold once, entire codebase updates
2. **Self-Documenting** - Constant name explains purpose
3. **Discoverability** - All constants visible in one file
4. **Type Safety** - IDE autocomplete works
5. **Consistency** - Same thresholds used everywhere

## Constant Categories

### 1. Graph Traversal Depths (`GraphDepth`)

Controls how deep Neo4j graph queries traverse:

| Constant | Value | Purpose | Use Case |
|----------|-------|---------|----------|
| `DIRECT` | 1 | Direct relationships only | Fast queries, shallow context |
| `NEIGHBORHOOD` | 2 | Local neighborhood | Moderate context |
| `DEFAULT` | 3 | Rich bi-directional context | **SKUEL standard** |
| `PREREQUISITE_CHAIN` | 5 | Deep prerequisite chains | Learning path construction |
| `MAXIMUM` | 10 | Shortest path queries | Maximum allowed depth |

**Usage:**
```python
from core.constants import GraphDepth

# Default semantic queries
query, params = CypherGenerator.build_semantic_context(
    node_uid="ku.python_basics",
    depth=GraphDepth.DEFAULT  # ✅ Self-documenting
)

# Prerequisite chains
query, params = CypherGenerator.build_prerequisite_chain(
    node_uid="ku.advanced_python",
    depth=GraphDepth.PREREQUISITE_CHAIN  # ✅ Clear intent
)

# Direct relationships only (performance optimization)
query, params = build_context(
    uid=task_uid,
    depth=GraphDepth.DIRECT  # ✅ Explicit shallow query
)
```

**Helper Methods:**
```python
# Get human-readable description
description = GraphDepth.get_description(GraphDepth.DEFAULT)
# → "Rich bi-directional context (default)"
```

### 2. Confidence Thresholds (`ConfidenceLevel`)

Semantic relationship confidence filtering (0.0 - 1.0):

| Constant | Value | Label | Purpose |
|----------|-------|-------|---------|
| `VERY_HIGH` | 0.95 | Very High | Expert knowledge |
| `HIGH` | 0.9 | High | Strong connections |
| `GOOD` | 0.85 | Good | Validated relationships |
| `STANDARD` | 0.8 | Standard | **Default minimum** |
| `MEDIUM` | 0.7 | Medium | Useful but uncertain |
| `LOW` | 0.6 | Low | Exploratory |
| `MIN_RELIABLE` | 0.9 | - | Minimum for prerequisites |
| `DEFAULT` | 0.8 | - | Default for general queries |

**Usage:**
```python
from core.constants import ConfidenceLevel

# Filter semantic relationships by confidence
query, params = CypherGenerator.build_semantic_context(
    node_uid="ku.python",
    min_confidence=ConfidenceLevel.STANDARD  # ✅ Standard filtering
)

# High-confidence prerequisites only
query, params = CypherGenerator.build_prerequisite_chain(
    node_uid="ku.advanced_ml",
    min_confidence=ConfidenceLevel.MIN_RELIABLE  # ✅ Only reliable
)

# Create relationship with default confidence
await relationship_service.create(
    source_uid=task_uid,
    target_uid=knowledge_uid,
    confidence=ConfidenceLevel.GOOD  # ✅ Named level
)
```

**Helper Methods:**
```python
# Get human-readable label
label = ConfidenceLevel.get_label(0.85)
# → "Good"
```

### 3. Mastery Thresholds (`MasteryLevel`)

Knowledge mastery levels (0.0 - 1.0):

| Constant | Value | Label | Meaning |
|----------|-------|-------|---------|
| `EXPERT` | 0.9 | Expert | Can teach others |
| `PROFICIENT` | 0.8 | Proficient | Comfortable application |
| `COMPETENT` | 0.7 | Competent | Basic understanding |
| `BEGINNER` | 0.5 | Beginner | Familiar but not confident |
| `DEFAULT` | 0.7 | - | Default "mastered" threshold |

**Usage:**
```python
from core.constants import MasteryLevel

# Check if user has mastered knowledge
if user_mastery >= MasteryLevel.COMPETENT:
    # User is ready for advanced content
    ...

# Create learning step with mastery threshold
step = LearningStep(
    knowledge_uid="ku.python_basics",
    mastery_threshold=MasteryLevel.PROFICIENT  # ✅ Clear expectation
)

# Filter ready-to-learn content
ready_content = await intelligence.get_ready_to_learn(
    user_uid=user_uid,
    threshold=MasteryLevel.DEFAULT  # ✅ Standard threshold
)
```

**Helper Methods:**
```python
# Get human-readable label
label = MasteryLevel.get_label(0.75)
# → "Competent"
```

### 4. Query Limits (`QueryLimit`)

Database query result limits:

| Constant | Value | Purpose | Use Case |
|----------|-------|---------|----------|
| `PREVIEW` | 5 | Quick previews | Dashboard widgets |
| `SMALL` | 10 | Small lists | Sidebar, dropdowns |
| `MEDIUM` | 20 | Medium lists | Search results |
| `LARGE` | 25 | Large lists | Full page listings |
| `DEFAULT` | 50 | Default pagination | **Standard pagination** |
| `COMPREHENSIVE` | 100 | Comprehensive results | Full dataset views |
| `BULK` | 1000 | Bulk operations | **Use with caution** |
| `MAXIMUM` | 10000 | Maximum allowed | Admin/debug only |

**Usage:**
```python
from core.constants import QueryLimit

# Dashboard preview
recent_tasks = await tasks_service.list(
    limit=QueryLimit.PREVIEW  # ✅ Quick 5-item preview
)

# Search results page
results = await search_service.search(
    query=search_query,
    limit=QueryLimit.MEDIUM  # ✅ 20 results per page
)

# Comprehensive analytics
all_data = await analytics_service.get_data(
    limit=QueryLimit.COMPREHENSIVE  # ✅ Full dataset
)

# Admin bulk export
export_data = await admin_service.export(
    limit=QueryLimit.BULK  # ✅ Explicit bulk operation
)
```

**Helper Methods:**
```python
# Get human-readable description
description = QueryLimit.get_description(QueryLimit.PREVIEW)
# → "Preview (quick glance)"
```

### 5. Intelligence Thresholds (`IntelligenceThreshold`)

AI/ML confidence thresholds:

| Constant | Value | Purpose |
|----------|-------|---------|
| `AUTO_PUBLISH` | 0.8 | Auto-publish generated content |
| `HIGH_CONFIDENCE_MIN` | 0.75 | Minimum high confidence |
| `HIGH_CONFIDENCE_MAX` | 0.87 | Maximum high confidence |
| `STYLE_CONFIDENCE` | 0.6 | Learning style matching |
| `CROSS_DOMAIN` | 0.6 | Cross-domain relationships |
| `MIN_RECOMMENDATION` | 0.7 | Minimum for recommendations |

**Usage:**
```python
from core.constants import IntelligenceThreshold

# Auto-publish high-confidence content
if generation_confidence >= IntelligenceThreshold.AUTO_PUBLISH:
    await publish(content)

# Learning style matching
if style_match >= IntelligenceThreshold.STYLE_CONFIDENCE:
    recommend_content(content)

# Cross-domain relationships
relationships = await find_cross_domain(
    threshold=IntelligenceThreshold.CROSS_DOMAIN
)
```

### 6. Feedback Time Periods (`FeedbackTimePeriod`)

Valid time period strings for activity feedback and review — shared vocabulary
used by `ActivityReviewService` and `ProgressFeedbackGenerator`:

| Constant | Value | Purpose |
|----------|-------|---------|
| `WEEK` | `"7d"` | 7-day review window |
| `TWO_WEEKS` | `"14d"` | 14-day review window |
| `MONTH` | `"30d"` | 30-day review window |
| `QUARTER` | `"90d"` | 90-day review window |
| `DEFAULT` | `"7d"` | Default period string |
| `DEFAULT_DAYS` | `7` | Default day count (for `.get()` fallback) |
| `DAYS` | `dict[str, int]` | Period string → day count mapping |

**Usage:**
```python
from core.constants import FeedbackTimePeriod

days = FeedbackTimePeriod.DAYS.get(time_period, FeedbackTimePeriod.DEFAULT_DAYS)
end_date = datetime.now()
start_date = end_date - timedelta(days=days)
```

### 7. Relationship Strength (`RelationshipStrength`)

Default confidence for relationship types:

| Constant | Value | Relationship Type |
|----------|-------|-------------------|
| `APPLIES_KNOWLEDGE` | 0.85 | Task → Knowledge |
| `PRACTICES_KNOWLEDGE` | 0.9 | Event → Knowledge |
| `DEVELOPS_KNOWLEDGE` | 0.9 | Habit → Knowledge |
| `DEFAULT` | 0.7 | Generic relationships |

**Usage:**
```python
from core.constants import RelationshipStrength

# Create relationship with default strength
await relationship_service.create(
    source_uid=task_uid,
    target_uid=knowledge_uid,
    relationship_type="APPLIES_KNOWLEDGE",
    confidence=RelationshipStrength.APPLIES_KNOWLEDGE  # ✅ Standard strength
)
```

## Migration

### Automated Migration

Use the migration script to identify and replace hardcoded values:

```bash
# Analyze codebase (report only)
poetry run python scripts/migrate_to_constants.py --analyze

# Dry run (show proposed changes)
poetry run python scripts/migrate_to_constants.py --dry-run

# Apply changes
poetry run python scripts/migrate_to_constants.py --apply
```

### Manual Migration

**Before:**
```python
# Hardcoded magic numbers
query, params = CypherGenerator.build_semantic_context(
    node_uid="ku.python",
    depth=3,  # What does 3 mean?
    min_confidence=0.8  # Why 0.8?
)

results = await backend.find_by(
    user_uid=user_uid,
    limit=100  # Arbitrary limit
)
```

**After:**
```python
from core.constants import GraphDepth, ConfidenceLevel, QueryLimit

# Named constants with clear intent
query, params = CypherGenerator.build_semantic_context(
    node_uid="ku.python",
    depth=GraphDepth.DEFAULT,  # Rich bi-directional context
    min_confidence=ConfidenceLevel.STANDARD  # Standard filtering
)

results = await backend.find_by(
    user_uid=user_uid,
    limit=QueryLimit.COMPREHENSIVE  # Comprehensive results
)
```

## Best Practices

### 1. Always Use Constants for Standard Values

```python
# ❌ BAD - Magic numbers
depth = 3
confidence = 0.8
limit = 100

# ✅ GOOD - Named constants
from core.constants import GraphDepth, ConfidenceLevel, QueryLimit

depth = GraphDepth.DEFAULT
confidence = ConfidenceLevel.STANDARD
limit = QueryLimit.COMPREHENSIVE
```

### 2. Document Custom Values

If you need a custom value that's not in constants:

```python
# Custom threshold for specific business logic
EXPERIMENTAL_THRESHOLD = 0.65  # Temporary lower threshold for testing

# But prefer adding to constants if it's reusable:
# → Add to IntelligenceThreshold class instead
```

### 3. Use Helper Methods

```python
from core.constants import GraphDepth, ConfidenceLevel

# Get human-readable descriptions
depth_desc = GraphDepth.get_description(GraphDepth.PREREQUISITE_CHAIN)
confidence_label = ConfidenceLevel.get_label(0.85)

# Use in logging/debugging
logger.info(f"Querying at {depth_desc} with {confidence_label} confidence")
```

### 4. Import at Module Level

```python
# ✅ GOOD - Import at top of file
from core.constants import (
    GraphDepth,
    ConfidenceLevel,
    QueryLimit,
    MasteryLevel,
)

# ❌ BAD - Don't import inline
def my_function():
    from core.constants import GraphDepth  # Repeated import
    ...
```

## Examples

### Example 1: Semantic Query with Standard Values

```python
from core.constants import GraphDepth, ConfidenceLevel, QueryLimit

# Build semantic context with standard values
query, params = CypherGenerator.build_semantic_context(
    node_uid="ku.python_basics",
    semantic_types=[SemanticRelationshipType.REQUIRES],
    depth=GraphDepth.DEFAULT,  # Rich context
    min_confidence=ConfidenceLevel.STANDARD  # Standard filtering
)

# Execute with reasonable limit
results = await backend.execute_query(query, params)
top_results = results[:QueryLimit.MEDIUM]  # 20 results
```

### Example 2: Learning Path Construction

```python
from core.constants import GraphDepth, ConfidenceLevel, MasteryLevel

# Find prerequisite chains for learning path
query, params = CypherGenerator.build_prerequisite_chain(
    node_uid="ku.advanced_ml",
    depth=GraphDepth.PREREQUISITE_CHAIN,  # Deep traversal
    min_confidence=ConfidenceLevel.MIN_RELIABLE  # Only reliable prerequisites
)

# Check if user is ready
if user_mastery >= MasteryLevel.COMPETENT:
    # Offer advanced content
    ...
```

### Example 3: Intelligence Service

```python
from core.constants import (
    ConfidenceLevel,
    IntelligenceThreshold,
    QueryLimit,
)

# Get high-confidence recommendations
recommendations = await intelligence_service.get_recommendations(
    user_uid=user_uid,
    min_confidence=IntelligenceThreshold.MIN_RECOMMENDATION,
    limit=QueryLimit.SMALL  # 10 recommendations
)

# Auto-publish if confidence is high enough
if recommendation.confidence >= IntelligenceThreshold.AUTO_PUBLISH:
    await publish_recommendation(recommendation)
```

## Testing

When testing, you can still use explicit values if needed for clarity:

```python
# Tests can use explicit values for clarity
def test_confidence_filtering():
    # Explicit value to verify exact filtering behavior
    results = filter_by_confidence(relationships, min_confidence=0.75)

    # Or use constants for semantic clarity
    from core.constants import ConfidenceLevel
    results = filter_by_confidence(relationships, min_confidence=ConfidenceLevel.MEDIUM)
```

## Migration Status (November 2025)

**Analysis Complete:**
- **283 hardcoded values** identified across codebase
- **Top 5 categories:** Confidence (89), Depth (75), Limits (110), Mastery (9)

**Ready for Migration:**
- Migration script created: `/scripts/migrate_to_constants.py`
- Dry-run tested on top 10 files
- All patterns validated

**Next Steps:**
1. Review analysis output
2. Run `--dry-run` to verify changes
3. Run `--apply` to migrate codebase
4. Verify tests pass
5. Commit changes

## See Also

- **Dynamic Enum Pattern:** `/home/mike/0bsidian/skuel/docs/patterns/CLAUDE.md` (§1.8)
- **Constants Module:** `/core/constants.py`
- **Migration Script:** `/scripts/migrate_to_constants.py`
- **Shared Enums:** `/core/models/enums/`
