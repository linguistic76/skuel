---
title: Intent-Based Graph Traversal
updated: 2025-12-03
category: patterns
related_skills: []
related_docs: []
---

# Intent-Based Graph Traversal Pattern

## Overview

All 6 Activity Domains in SKUEL use intent-based graph traversal via `GraphIntelligenceService.query_with_intent()`. Each domain has a domain-specific `QueryIntent` that optimizes Cypher queries for that domain's semantics.

**Core Principle:** "Domain-specific semantic understanding of graph queries"

## The 6-Domain Intent Architecture

| Domain | Intent | Focus | Analysis Method |
|--------|--------|-------|-----------------|
| Tasks | PRACTICE | Task execution and dependencies | `get_task_with_context()` |
| Goals | GOAL_ACHIEVEMENT | Achievement path analysis | `get_goal_achievement_analysis()` |
| Principles | PRINCIPLE_EMBODIMENT | How principle is LIVED | `get_principle_embodiment_analysis()` |
| Habits | PRACTICE | Practice patterns and streaks | `get_habit_practice_analysis()` |
| Choices | PRINCIPLE_ALIGNMENT | Principle-guided decisions | `get_choice_principle_alignment_analysis()` |
| Events | SCHEDULED_ACTION | Task→Event execution | `get_event_scheduled_action_analysis()` |

## QueryIntent Enum

**Location:** `/core/models/query/_query_models.py`

### Generic Intents (Cross-Domain)

```python
class QueryIntent(str, Enum):
    EXPLORATORY = "exploratory"      # Broad search/discovery
    SPECIFIC = "specific"            # Looking for specific concept
    HIERARCHICAL = "hierarchical"    # Parent/child context
    PREREQUISITE = "prerequisite"    # Prerequisite chains
    PRACTICE = "practice"            # Exercises/examples
    AGGREGATION = "aggregation"      # Statistical queries
    RELATIONSHIP = "relationship"    # Graph traversal focused
```

### Domain-Specific Intents (December 2025)

```python
    # Domain-specific intents
    GOAL_ACHIEVEMENT = "goal_achievement"        # Goal achievement path analysis
    PRINCIPLE_EMBODIMENT = "principle_embodiment"  # How principle is LIVED
    PRINCIPLE_ALIGNMENT = "principle_alignment"    # Choice alignment with principles
    SCHEDULED_ACTION = "scheduled_action"        # Event as scheduled task execution
```

## Architecture Components

### 1. GraphIntelligenceService

**Location:** `/core/services/infrastructure/graph_intelligence_service.py`

The central service that executes intent-based Cypher queries:

```python
async def query_with_intent(
    self,
    uid: str,
    intent: QueryIntent,
    depth: int = 2,
) -> Result[GraphContext]:
    """Execute intent-based graph traversal."""
    cypher = self._build_context_query_for_intent(intent, depth)
    # Execute and return GraphContext with entities and relationships
```

Each intent has a dedicated Cypher handler in `_build_context_query_for_intent()`.

### 2. Domain RelationshipService Pattern

Each domain's RelationshipService follows this pattern:

```python
class {Domain}RelationshipService(GenericRelationshipService[...]):
    def __init__(
        self,
        backend: {Domain}Operations,
        graph_intel: Any | None = None,
    ) -> None:
        super().__init__(...)
        self.graph_intel = graph_intel

    def _context_to_domain_model(self, data: dict | DTO | Model) -> Model:
        """Convert raw data to domain model for context queries."""
        ...

    @requires_graph_intelligence("get_{entity}_with_context")
    async def get_{entity}_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[{Entity}, GraphContext]]:
        """Get entity with full graph context using intent-based traversal."""
        entity = await self._get_entity(uid)
        intent = entity.get_suggested_query_intent()
        context = await self.graph_intel.query_with_intent(uid, intent, depth)
        return Result.ok((entity, context.value))

    @requires_graph_intelligence("get_{entity}_{analysis}_analysis")
    async def get_{entity}_{analysis}_analysis(self, uid: str) -> Result[dict[str, Any]]:
        """Domain-specific analysis using intent-based context."""
        context_result = await self.get_{entity}_with_context(uid)
        # Extract relevant entities, calculate scores, generate recommendations
        return Result.ok({
            "{domain}_score": score,
            "{domain}_level": level,
            "related_entities": [...],
            "recommendations": [...]
        })
```

### 3. Domain Model Integration

Each domain model implements `get_suggested_query_intent()`:

```python
def get_suggested_query_intent(self) -> QueryIntent:
    """Get suggested QueryIntent based on entity characteristics."""
    return QueryIntent.{DOMAIN_INTENT}
```

### 4. Service Wiring

Each facade service wires `graph_intel` to its RelationshipService:

```python
# In {Domain}Service.__init__():
self.relationships = {Domain}RelationshipService(
    backend=backend, graph_intel=graph_intelligence_service
)
```

## Intent Relationship Patterns

### GOAL_ACHIEVEMENT

Traces the complete achievement path for a goal:

- `FULFILLS_GOAL` (incoming) - Tasks that contribute
- `SUPPORTS_GOAL` (incoming) - Habits that reinforce
- `REQUIRES_KNOWLEDGE` (outgoing) - Knowledge prerequisites
- `SUBGOAL_OF` (bidirectional) - Goal hierarchy
- `GUIDED_BY_PRINCIPLE` (outgoing) - Guiding principles
- `HAS_MILESTONE` (outgoing) - Milestone nodes

### PRINCIPLE_EMBODIMENT

Traces how a principle is LIVED across domains:

- `GUIDED_BY_PRINCIPLE` (incoming) - Goals guided by this
- `ALIGNED_WITH_PRINCIPLE` (incoming) - Choices/Habits aligned
- `INSPIRES_HABIT` (outgoing) - Habits this inspires
- `GROUNDED_IN_KNOWLEDGE` (outgoing) - Knowledge foundation
- `GUIDES_GOAL` (outgoing) - Goals this guides
- `GUIDES_CHOICE` (outgoing) - Choices this guides

### PRINCIPLE_ALIGNMENT

Traces choice alignment with principles and knowledge:

- `ALIGNED_WITH_PRINCIPLE` (outgoing) - Guiding principles
- `INFORMED_BY_KNOWLEDGE` (outgoing) - Knowledge informing decision
- `SUPPORTS_GOAL` (outgoing) - Goals supported
- `CONFLICTS_WITH_GOAL` (outgoing) - Potential conflicts
- `REQUIRES_KNOWLEDGE_FOR_DECISION` (outgoing) - Required knowledge
- `OPENS_LEARNING_PATH` (outgoing) - Learning paths opened

### SCHEDULED_ACTION

Traces what an Event executes, practices, and reinforces:

- `EXECUTES_TASK` (outgoing) - Tasks being executed
- `PRACTICES_KNOWLEDGE` (outgoing) - Knowledge being practiced
- `REINFORCES_HABIT` (outgoing) - Habits being reinforced
- `MILESTONE_FOR_GOAL` (outgoing) - Goals being advanced
- `CONFLICTS_WITH` (bidirectional) - Scheduling conflicts
- `SUPPORTS_GOAL` (outgoing) - Goals supported

## Analysis Output Patterns

Each domain's analysis method returns a consistent structure:

```python
{
    "{entity}_uid": str,
    "{domain}_score": float,        # 0.0-1.0
    "{domain}_level": str,          # Domain-specific levels
    "related_{type}": [             # Lists of related entities
        {"uid": str, "title": str}
    ],
    "{domain}_patterns": {          # Domain-specific metrics
        ...
    },
    "recommendations": [str]        # Improvement suggestions
}
```

### Example: Goal Achievement Analysis

```python
{
    "goal_uid": "goal:123",
    "achievement_score": 0.75,
    "achievement_level": "on_track",  # or "blocked", "at_risk", "achieved"
    "fulfilling_tasks": [...],
    "supporting_habits": [...],
    "required_knowledge": [...],
    "blocking_factors": [...],
    "recommendations": [
        "Complete 2 more tasks to reach milestone",
        "Link additional knowledge requirements"
    ]
}
```

### Example: Scheduled Action Analysis

```python
{
    "event_uid": "event:456",
    "action_score": 0.65,
    "action_level": "productive",  # or "empty", "light", "packed"
    "tasks_executed": [...],
    "knowledge_practiced": [...],
    "habits_reinforced": [...],
    "conflicts": [...],
    "recommendations": [
        "Link this event to tasks it will execute",
        "Consider splitting into multiple focused events"
    ]
}
```

## Key Files

| Component | File |
|-----------|------|
| QueryIntent enum | `/core/models/query/_query_models.py` |
| GraphIntelligenceService | `/core/services/infrastructure/graph_intelligence_service.py` |
| @requires_graph_intelligence | `/core/utils/decorators.py` |
| **Tasks** | |
| TasksRelationshipService | `/core/services/tasks/tasks_relationship_service.py` |
| Task model | `/core/models/task/task.py` |
| TasksService | `/core/services/tasks_service.py` |
| **Goals** | |
| GoalsRelationshipService | `/core/services/goals/goals_relationship_service.py` |
| Goal model | `/core/models/goal/goal.py` |
| GoalsService | `/core/services/goals_service.py` |
| **Principles** | |
| PrinciplesRelationshipService | `/core/services/principles/principles_relationship_service.py` |
| Principle model | `/core/models/principle/principle.py` |
| PrinciplesService | `/core/services/principles_service.py` |
| **Habits** | |
| HabitsRelationshipService | `/core/services/habits/habits_relationship_service.py` |
| Habit model | `/core/models/habit/habit.py` |
| HabitsService | `/core/services/habits_service.py` |
| **Choices** | |
| ChoicesRelationshipService | `/core/services/choices/choices_relationship_service.py` |
| Choice model | `/core/models/choice/choice.py` |
| ChoicesService | `/core/services/choices_service.py` |
| **Events** | |
| EventsRelationshipService | `/core/services/events/events_relationship_service.py` |
| Event model | `/core/models/event/event.py` |
| EventsService | `/core/services/events_service.py` |

## Usage Examples

### Getting Entity with Context

```python
# In a route or service
result = await goals_service.relationships.get_goal_with_context(
    uid="goal:123",
    depth=2
)
if result.is_error:
    return handle_error(result)

goal, context = result.value
# context.entities contains related nodes
# context.relationships contains edge data
```

### Getting Domain Analysis

```python
# Get principle embodiment analysis
result = await principles_service.relationships.get_principle_embodiment_analysis(
    uid="principle:456"
)

analysis = result.value
print(f"Embodiment Score: {analysis['embodiment_score']}")
print(f"Level: {analysis['embodiment_level']}")
for rec in analysis['recommendations']:
    print(f"- {rec}")
```

## Benefits

1. **Semantic Understanding** - Each domain gets optimized Cypher for its semantics
2. **Consistent Pattern** - All 6 domains follow the same architecture
3. **Rich Context** - Returns complete graph neighborhood with analysis
4. **Actionable Insights** - Generates domain-specific recommendations
5. **Type Safety** - QueryIntent enum prevents typos and enables tooling

---

**Last Updated:** December 3, 2025
**Status:** Active - Core pattern for all Activity Domain graph traversal
