---
title: SKUEL Query Template Usage Guide
updated: 2025-11-26
status: current
category: general
tags: [guide, query, skuel, usage]
related: []
---

# SKUEL Query Template Usage Guide

**Quick reference for using SKUEL-specific Pure Cypher query templates**

---

## Quick Start

```python
from core.models.query.skuel_query_templates import get_template

# Get a template
template = get_template("next_knowledge_in_path")

# Build parameters
params = {
    "user_uid": "user:123",
    "current_path_uid": "lp:ego_to_self",
    "mastered_uids": ["ku:yoga_ego", "ku:self_awareness"],
    "available_minutes": 30,
    "limit": 10
}

# Execute with Neo4j session
result = await session.run(template.cypher, params)
records = [dict(record) async for record in result]
```

---

## Available Templates

### 1. Next Knowledge in Path

**Purpose:** Get next knowledge units in user's current learning path (prerequisites met)

```python
template = get_template("next_knowledge_in_path")

params = {
    "user_uid": "user:mike",
    "current_path_uid": "lp:ego_to_self",
    "mastered_uids": ["ku:yoga_ego", "ku:self_awareness"],
    "available_minutes": 30,
    "limit": 10
}

# Returns: List of knowledge units ready to learn
# Fields: knowledge_uid, title, section, time_required, path_title, prerequisites
```

**Use Cases:**
- Personalized learning dashboard
- "What should I learn next?" feature
- Progress tracking and recommendations

---

### 2. Life Path Alignment

**Purpose:** Calculate how well user is LIVING their life path (substance score)

```python
template = get_template("life_path_alignment")

params = {
    "user_uid": "user:mike"
}

# Returns: Life alignment analysis
# Fields:
#   - life_alignment_score (0.0-1.0)
#   - knowledge_items (list with substance per KU)
#   - total_knowledge, well_practiced, theoretical_only
```

**Interpretation:**
- 0.0-0.2: Pure theory (read about it)
- 0.3-0.5: Applied knowledge (tried it)
- 0.6-0.7: Well-practiced (regular use)
- 0.8-1.0: Lifestyle-integrated (embodied)

**Use Cases:**
- Life path dashboard
- Substance tracking
- "Living your knowledge" reports

---

### 3. Prerequisite Chain

**Purpose:** Find complete prerequisite chain for a target knowledge unit

```python
template = get_template("prerequisite_chain")

params = {
    "user_uid": "user:mike",
    "target_uid": "ku:alchemy_inner"
}

# Returns: Complete prerequisite tree
# Fields: knowledge_uid, title, prerequisite_depth, is_mastered, prerequisite_type
```

**Use Cases:**
- Learning path visualization
- Prerequisite checker before enrollment
- Progress blocking analysis

---

### 4. Cross-Domain Applications

**Purpose:** Show how knowledge is applied across supporting domains

```python
template = get_template("cross_domain_applications")

params = {
    "user_uid": "user:mike",
    "knowledge_uid": "ku:behavior_loop"
}

# Returns: All applications of knowledge
# Fields:
#   - tasks, habits, goals, events, journals, principles (lists)
#   - task_count, habit_count, etc. (counts)
#   - estimated_substance_score (0.0-1.0)
```

**Use Cases:**
- "Where am I using this knowledge?" reports
- Substance score calculation
- Cross-domain connection visualization

---

### 5. User Progress Snapshot

**Purpose:** Get complete snapshot of user's learning progress

```python
template = get_template("user_progress_snapshot")

params = {
    "user_uid": "user:mike"
}

# Returns: Complete progress overview
# Fields:
#   - learning_paths (list with progress per path)
#   - total_knowledge_available, total_knowledge_mastered
#   - average_path_progress
#   - life_path_uid, life_path_title
```

**Use Cases:**
- Dashboard overview
- Progress reports
- Learning analytics

---

### 6. Adaptive Recommendations

**Purpose:** AI-recommended next steps based on UserContext

```python
template = get_template("adaptive_recommendations")

params = {
    "user_uid": "user:mike",
    "current_path_uid": "lp:ego_to_self",
    "mastered_uids": ["ku:yoga_ego"],
    "available_minutes": 30,
    "learning_level": "intermediate",
    "limit": 5
}

# Returns: Ranked recommendations
# Fields: knowledge_uid, title, section, time_required, difficulty, recommendation_score
```

**Recommendation Scoring:**
- Section priority: foundation (3.0) > practice (2.0) > integration (1.0)
- Difficulty match: +2.0 if matches user level
- Enablement: +0.5 per enabled downstream KU

**Use Cases:**
- Personalized learning suggestions
- "Recommended for you" feature
- Adaptive learning paths

---

### 7. Knowledge Substance Update

**Purpose:** Update knowledge substance score based on domain events

```python
template = get_template("knowledge_substance_update")

params = {
    "user_uid": "user:mike",
    "knowledge_uid": "ku:behavior_loop"
}

# Returns: Updated substance score
# Fields: substance_score, habit_count, journal_count, etc., substance_level
```

**Substance Weights:**
- Habits: 0.10 per application (max 0.30)
- Journals: 0.07 per application (max 0.20)
- Choices: 0.07 per application (max 0.15)
- Events: 0.05 per application (max 0.25)
- Tasks: 0.05 per application (max 0.25)

**Use Cases:**
- Event-driven substance updates
- Real-time knowledge tracking
- Application analytics

---

### 8. Bulk Learning Path Ingestion

**Purpose:** Import learning paths and knowledge units from YAML/markdown

```python
template = get_template("bulk_learning_path_ingestion")

# Example data structure
learning_paths = [
    {
        "uid": "lp:ego_to_self",
        "title": "Ego to Self",
        "section": "foundation",
        "stream": "yoga_and_feeling",
        "description": "Understanding the difference between ego and self",
        "estimated_hours": 10,
        "knowledge_units": [
            {
                "uid": "ku:yoga_ego",
                "title": "What is the Ego?",
                "content": "...",
                "section": "foundation",
                "sequence_order": 1,
                "estimated_minutes": 30,
                "difficulty": "beginner",
                "domain": "PERSONAL",
                "prerequisites": [],
                "enables": ["ku:self_awareness"]
            }
        ]
    }
]

params = {"learning_paths": learning_paths}

# Returns: Creation stats
# Fields: learning_paths_created, knowledge_units_created
```

**Use Cases:**
- Initial curriculum setup
- Batch content imports
- Curriculum updates

---

### 9. Create Constraints

**Purpose:** Create unique constraints for all SKUEL entities (idempotent)

```python
template = get_template("create_constraints")

# No parameters needed
await session.run(template.cypher)
```

**Use Cases:**
- Initial database setup
- Schema migrations
- Constraint verification

---

### 10. Create Indexes

**Purpose:** Create indexes for common query patterns (idempotent)

```python
template = get_template("create_indexes")

# No parameters needed
await session.run(template.cypher)
```

**Indexes Created:**
- `ku.section` - Foundation/practice/integration queries
- `lp.section` - Learning path filtering
- `u.username` - User lookup
- `ku.domain` - Domain-specific queries

**Use Cases:**
- Initial database setup
- Performance optimization
- Schema migrations

---

## Service Integration Examples

### Example 1: Learning Path Service

```python
from core.models.query.skuel_query_templates import get_template

class LearningPathService:
    def __init__(self, session):
        self.session = session

    async def get_next_knowledge(
        self,
        user_uid: str,
        current_path_uid: str,
        user_context: UserContext
    ) -> list[dict]:
        """Get next knowledge units for user's current path."""

        # Get template
        template = get_template("next_knowledge_in_path")

        # Build params from UserContext
        params = {
            "user_uid": user_uid,
            "current_path_uid": current_path_uid,
            "mastered_uids": list(user_context.mastered_knowledge_uids),
            "available_minutes": user_context.available_minutes_daily,
            "limit": 10
        }

        # Execute query
        result = await self.session.run(template.cypher, params)
        records = [dict(record) async for record in result]

        return records
```

### Example 2: User Intelligence Service

```python
from core.models.query.skuel_query_templates import get_template

class UserIntelligenceService:
    def __init__(self, session):
        self.session = session

    async def calculate_life_alignment(
        self,
        user_uid: str
    ) -> dict:
        """Calculate user's life path alignment score."""

        # Get template
        template = get_template("life_path_alignment")

        # Execute query
        result = await self.session.run(
            template.cypher,
            {"user_uid": user_uid}
        )

        record = await result.single()
        if not record:
            return {"life_alignment_score": 0.0}

        return dict(record)

    async def get_adaptive_recommendations(
        self,
        user_uid: str,
        user_context: UserContext
    ) -> list[dict]:
        """Get personalized knowledge recommendations."""

        # Get template
        template = get_template("adaptive_recommendations")

        # Build params from UserContext
        params = {
            "user_uid": user_uid,
            "current_path_uid": user_context.current_learning_path_uid,
            "mastered_uids": list(user_context.mastered_knowledge_uids),
            "available_minutes": user_context.available_minutes_daily,
            "learning_level": user_context.learning_level.value,
            "limit": 5
        }

        # Execute query
        result = await self.session.run(template.cypher, params)
        records = [dict(record) async for record in result]

        return records
```

### Example 3: Event-Driven Substance Updates

```python
from core.models.query.skuel_query_templates import get_template
from core.events.base import EventBus

class KnowledgeSubstanceTracker:
    def __init__(self, session, event_bus: EventBus):
        self.session = session
        self.event_bus = event_bus

        # Subscribe to domain events
        event_bus.subscribe("task.completed", self.on_task_completed)
        event_bus.subscribe("habit.completed", self.on_habit_completed)
        event_bus.subscribe("journal.created", self.on_journal_created)

    async def on_task_completed(self, event):
        """Update substance when task is completed."""
        if event.applies_knowledge_uid:
            await self.update_substance(
                event.user_uid,
                event.applies_knowledge_uid
            )

    async def on_habit_completed(self, event):
        """Update substance when habit is completed."""
        if event.applies_knowledge_uid:
            await self.update_substance(
                event.user_uid,
                event.applies_knowledge_uid
            )

    async def on_journal_created(self, event):
        """Update substance when journal is created."""
        if event.reflects_on_knowledge_uid:
            await self.update_substance(
                event.user_uid,
                event.reflects_on_knowledge_uid
            )

    async def update_substance(
        self,
        user_uid: str,
        knowledge_uid: str
    ) -> dict:
        """Update knowledge substance score."""

        # Get template
        template = get_template("knowledge_substance_update")

        # Execute query
        result = await self.session.run(
            template.cypher,
            {
                "user_uid": user_uid,
                "knowledge_uid": knowledge_uid
            }
        )

        record = await result.single()
        return dict(record) if record else {}
```

---

## Best Practices

### 1. Always Use UserContext

```python
# ✅ GOOD - UserContext-aware
params = {
    "user_uid": user_uid,
    "mastered_uids": list(user_context.mastered_knowledge_uids),
    "available_minutes": user_context.available_minutes_daily,
    "learning_level": user_context.learning_level.value
}

# ❌ BAD - Hardcoded values
params = {
    "user_uid": user_uid,
    "mastered_uids": [],  # Ignores user state
    "available_minutes": 60,  # Assumes availability
    "learning_level": "intermediate"  # Assumes level
}
```

### 2. Handle Empty Results

```python
result = await session.run(template.cypher, params)
record = await result.single()

# Check for None
if not record:
    return default_value

return dict(record)
```

### 3. Use Proper Limits

```python
# ✅ GOOD - Reasonable limit
params = {"limit": 10}

# ❌ BAD - No limit (could return thousands)
params = {}  # Missing limit parameter
```

### 4. Cache Frequently Used Results

```python
# Cache user progress snapshot (expensive query)
@cached(ttl=300)  # 5 minutes
async def get_user_progress(user_uid: str):
    template = get_template("user_progress_snapshot")
    result = await session.run(template.cypher, {"user_uid": user_uid})
    return await result.single()
```

---

## Performance Tips

1. **Use PROFILE for slow queries**
   ```cypher
   PROFILE <query>
   ```

2. **Verify indexes exist**
   ```cypher
   SHOW INDEXES
   ```

3. **Limit relationship depth**
   - Templates already limit to `*0..5` for prerequisite chains
   - Adjust if needed for specific use cases

4. **Batch operations**
   - Use bulk ingestion template for multiple entities
   - Reduces network round-trips

5. **Monitor query performance**
   - Log query execution time
   - Alert on slow queries (>100ms)
   - Profile and optimize hot paths

---

## Testing

```python
import pytest
from core.models.query.skuel_query_templates import get_template

def test_next_knowledge_template():
    """Test next knowledge template structure."""
    template = get_template("next_knowledge_in_path")

    assert template.name == "next_knowledge_in_path"
    assert "user_uid" in template.parameters
    assert "MATCH" in template.cypher
    assert "RETURN" in template.cypher

def test_template_parameters():
    """Test template parameter validation."""
    template = get_template("adaptive_recommendations")

    params = template.execute_params(
        user_uid="user:test",
        current_path_uid="lp:test",
        mastered_uids=[],
        available_minutes=30,
        learning_level="beginner",
        limit=5
    )

    assert params["user_uid"] == "user:test"
    assert params["limit"] == 5
```

---

## Summary

**10 SKUEL query templates provide:**
- UserContext-driven personalization
- Curriculum-aware navigation
- Pure Cypher implementation (portable)
- Performance-optimized patterns
- Event-driven substance tracking

**Common patterns:**
1. Get user state from UserContext
2. Build query parameters
3. Execute template
4. Process results
5. Update UserContext if needed

**For complete design documentation:** See `/docs/SKUEL_QUERY_DESIGN.md`
