# KuIntelligenceService - Semantic Knowledge & Cross-Domain Discovery

## Overview

**Architecture:** Extends `BaseAnalyticsService[KuOperations, Ku]`
**Location:** `/core/services/ku_intelligence_service.py`
**Service Name:** `ku.intelligence`
**Lines:** ~728
**Updated:** January 2026 (Protocol Compliance & Embeddings Service)

---

## Purpose

KuIntelligenceService provides semantic knowledge intelligence by analyzing knowledge graph relationships, identifying cross-domain connections, and tracking knowledge substance. It generates context-aware knowledge recommendations, discovers application opportunities across domains, and measures how knowledge is lived (not just learned) through the Knowledge Substance Philosophy.

---

## Core Methods

### Method 1: get_knowledge_suggestions()

**Purpose:** Generate semantic knowledge suggestions based on graph relationships and entity context, identifying related concepts, learning paths, and knowledge gaps.

**Signature:**
```python
async def get_knowledge_suggestions(
    self,
    user_uid: str,
    entity_uid: str | None = None
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `user_uid` (str) - User identifier
- `entity_uid` (str, optional) - Specific KU UID to analyze (if None, provides general recommendations)

**Returns:**
```python
{
    "related_concepts": [
        {
            "uid": "ku.python-advanced",
            "title": "Advanced Python Patterns",
            "relevance": 0.85
        }
    ],
    "learning_paths": [],  # Future: LP suggestions
    "knowledge_gaps": [],  # Future: Gap analysis
    "metadata": {
        "generated_at": "2026-01-08T10:00:00",
        "user_uid": "user.mike",
        "source_concept": "ku.python-basics"
    }
}
```

**Example:**
```python
# Get suggestions based on specific KU
result = await ku_service.intelligence.get_knowledge_suggestions(
    user_uid="user.mike",
    entity_uid="ku.python-basics"
)

if result.is_ok:
    data = result.value
    for concept in data["related_concepts"]:
        print(f"Related: {concept['title']} (relevance: {concept['relevance']})")

# Get general suggestions
result = await ku_service.intelligence.get_knowledge_suggestions(
    user_uid="user.mike"
)
```

**Dependencies:**
- GraphIntelligenceService (REQUIRED - uses `_require_graph_intelligence()`)
- Neo4jGenAIEmbeddingsService (optional - enhanced semantic analysis if available)

**Graph Intelligence Usage:**
Uses `graph_intel.get_entity_context()` to retrieve semantic neighborhood:
- **GraphDepth.NEIGHBORHOOD** - Returns up to 10 most relevant related concepts
- Analyzes node properties for title extraction
- Calculates relevance scores based on relationship strength

---

### Method 2: get_cross_domain_opportunities()

**Purpose:** Identify cross-domain knowledge connections by analyzing how knowledge units relate across different domains, revealing opportunities for knowledge transfer and integrated application.

**Signature:**
```python
async def get_cross_domain_opportunities(
    self,
    user_uid: str,
    entity_uid: str | None = None
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `user_uid` (str) - User identifier
- `entity_uid` (str, optional) - Specific KU UID to analyze

**Returns:**
```python
{
    "connections": [
        {
            "from_uid": "ku.python-basics",
            "to_uid": "ku.machine-learning",
            "relationship": "ENABLES",
            "strength": 0.8
        }
    ],
    "opportunities": [
        "Apply concepts across domains",
        "Transfer learning patterns"
    ],
    "synergies": [
        "Cross-domain pattern recognition",
        "Integrated knowledge application"
    ],
    "metadata": {
        "generated_at": "2026-01-08T10:00:00",
        "user_uid": "user.mike",
        "entity_uid": "ku.python-basics"
    }
}
```

**Example:**
```python
result = await ku_service.intelligence.get_cross_domain_opportunities(
    user_uid="user.mike",
    entity_uid="ku.python-basics"
)

if result.is_ok:
    data = result.value
    print(f"Cross-domain connections: {len(data['connections'])}")

    for conn in data["connections"]:
        print(f"{conn['from_uid']} --{conn['relationship']}--> {conn['to_uid']}")
        print(f"  Strength: {conn['strength']}")

    print("\nOpportunities:")
    for opp in data["opportunities"]:
        print(f"  - {opp}")
```

**Dependencies:**
- GraphIntelligenceService (REQUIRED - uses `_require_graph_intelligence()`)

**Graph Intelligence Usage:**
Uses `graph_intel.get_entity_context()` with `GraphDepth.DEFAULT`:
- Retrieves up to 20 cross-domain relationships
- Extracts relationship metadata (type, strength properties)
- Identifies knowledge transfer patterns

**Cross-Domain Analysis:**
The method identifies:
- **Direct connections** - Explicit ENABLES, REQUIRES_KNOWLEDGE relationships
- **Pattern transfer** - Similar knowledge structures in different domains
- **Synergy opportunities** - Where combined knowledge creates emergent value
- **Application contexts** - Where theoretical knowledge can be practiced

---

### Method 3: get_performance_analytics()

**Purpose:** Analyze knowledge substance and application metrics over a specified period, measuring how knowledge is LIVED through the Knowledge Substance Philosophy.

**Signature:**
```python
async def get_performance_analytics(
    self,
    user_uid: str,
    period_days: int = 30,
    user_context: "UserContext | None" = None  # January 2026: KU-Activity Integration
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `user_uid` (str) - User identifier
- `period_days` (int, default=30) - Period to analyze in days
- `user_context` (UserContext, optional) - UserContext for personalized metrics (January 2026)

**Returns:**
```python
{
    "metrics": {
        "total_knowledge_units": 5,  # Real count from UserContext when provided
        "average_substance_score": 0.65,  # Computed from mastery levels
        "application_rate": 0.72  # Applied KUs / mastered KUs ratio
    },
    "trends": {
        "knowledge_growth": "improving",
        "substance_trend": "stable"
    },
    "optimization_opportunities": [
        {
            "area": "knowledge_application",
            "suggestion": "Increase practical application of learned concepts",
            "potential_impact": "30-40% increase in knowledge retention"
        }
    ],
    "metadata": {
        "generated_at": "2026-01-11T10:00:00",
        "user_uid": "user.mike",
        "period_days": 30,
        "has_user_context": true  # Indicates personalized data
    }
}
```

**Example:**
```python
# Basic analytics (placeholder data)
result = await ku_service.intelligence.get_performance_analytics(
    user_uid="user.mike",
    period_days=90
)

# Personalized analytics with UserContext (January 2026)
context_result = await user_service.get_user_context("user.mike")
if context_result.is_ok:
    result = await ku_service.intelligence.get_performance_analytics(
        user_uid="user.mike",
        period_days=90,
        user_context=context_result.value  # Real metrics from UserContext
    )

if result.is_ok:
    data = result.value
    metrics = data["metrics"]
    print(f"Total KUs: {metrics['total_knowledge_units']}")
    print(f"Average substance score: {metrics['average_substance_score']:.2f}")
    print(f"Application rate: {metrics['application_rate']:.0%}")
```

**UserContext Integration (January 2026):**

When `user_context` is provided, the method returns real personalized metrics:
- **total_knowledge_units** - Count from `task_knowledge_applied` + `habit_knowledge_applied`
- **average_substance_score** - Mean of `knowledge_mastery` values
- **application_rate** - Ratio of applied KUs to mastered KUs

**Dependencies:** KuOperations backend, UserService (optional for personalization)

**Knowledge Substance Tracking:**

The method implements SKUEL's Knowledge Substance Philosophy:

| Substance Level | Score | Meaning |
|----------------|-------|---------|
| Pure theory | 0.0-0.2 | Read about it |
| Applied knowledge | 0.3-0.5 | Tried it |
| Well-practiced | 0.6-0.7 | Regular use |
| Lifestyle-integrated | 0.8-1.0 | Embodied |

**Application Types & Weights:**
- **Habits** (0.10/event, max 0.30) - Lifestyle integration (highest weight)
- **Journals** (0.07/event, max 0.20) - Metacognition and reflection
- **Choices** (0.07/event, max 0.15) - Decision-making wisdom
- **Events** (0.05/event, max 0.25) - Practice and embodiment
- **Tasks** (0.05/event, max 0.25) - Real-world application

---

### Method 4: calculate_user_substance() (January 2026)

**Purpose:** Calculate per-user substance score for a specific Knowledge Unit. This enables the personalized "How am I using this knowledge?" view by analyzing the user's actual activity data.

**Signature:**
```python
async def calculate_user_substance(
    self,
    ku_uid: str,
    user_context: "UserContext"
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `ku_uid` (str) - Knowledge Unit identifier
- `user_context` (UserContext) - User's context with activity data (REQUIRED)

**Returns:**
```python
{
    "ku_uid": "ku.python-basics",
    "user_uid": "user.mike",
    "user_substance_score": 0.45,  # Per-user score (0.0-1.0)
    "global_substance_score": 0.72,  # Global KU substance (from model)
    "breakdown": {
        "tasks": {"count": 3, "uids": ["task.001", "task.002", "task.003"], "score": 0.15},
        "habits": {"count": 1, "uids": ["habit.daily-python"], "score": 0.10},
        "events": {"count": 0, "uids": [], "score": 0.00},  # Placeholder
        "journals": {"count": 0, "uids": [], "score": 0.00},  # Placeholder
        "choices": {"count": 0, "uids": [], "score": 0.00}  # Placeholder
    },
    "mastery_level": 0.75,  # From user_context.knowledge_mastery
    "is_ready_to_learn": true,  # From user_context.ready_to_learn_uids
    "recommendations": [
        {
            "type": "event",
            "message": "Schedule practice time for this knowledge",
            "impact": "+0.05 per event (max +0.25)"
        },
        {
            "type": "journal",
            "message": "Reflect on this knowledge in a journal entry",
            "impact": "+0.07 per reflection (max +0.20)"
        }
    ],
    "status_message": "Applied but not yet integrated. Build habits.",
    "metadata": {
        "generated_at": "2026-01-11T10:00:00"
    }
}
```

**Example:**
```python
# Get UserContext first
context_result = await user_service.get_user_context("user.mike")
if context_result.is_error:
    return context_result

user_context = context_result.value

# Calculate per-user substance for specific KU
result = await ku_service.intelligence.calculate_user_substance(
    ku_uid="ku.python-basics",
    user_context=user_context
)

if result.is_ok:
    data = result.value
    print(f"Your substance score: {data['user_substance_score']:.0%}")
    print(f"Global substance: {data['global_substance_score']:.0%}")
    print(f"Status: {data['status_message']}")

    # Show breakdown
    for domain, info in data["breakdown"].items():
        if info["count"] > 0:
            print(f"  {domain}: {info['count']} ({info['score']:.2f})")

    # Show recommendations for improvement
    print("\nTo deepen your knowledge:")
    for rec in data["recommendations"]:
        print(f"  - {rec['message']} ({rec['impact']})")
```

**Substance Calculation Logic:**

The method implements the Knowledge Substance Philosophy with weighted scoring:

```python
# Weight per application, capped at max
task_score = min(0.25, len(task_uids) * 0.05)
habit_score = min(0.30, len(habit_uids) * 0.10)
event_score = min(0.25, len(event_uids) * 0.05)
journal_score = min(0.20, len(journal_uids) * 0.07)
choice_score = min(0.15, len(choice_uids) * 0.07)

user_substance_score = task_score + habit_score + event_score + journal_score + choice_score
```

**Status Messages by Score:**

| Score Range | Status Message |
|-------------|----------------|
| 0.8+ | "Mastered! Consider teaching others." |
| 0.7-0.79 | "Well practiced! Keep it up." |
| 0.5-0.69 | "Solid foundation. Practice more to deepen mastery." |
| 0.3-0.49 | "Applied but not yet integrated. Build habits." |
| 0.01-0.29 | "Theoretical knowledge. Apply in projects." |
| 0.0 | "Pure theory. Create tasks and practice." |

**UserContext Fields Used:**
- `task_knowledge_applied: dict[str, list[str]]` - Maps task UID to KU UIDs
- `habit_knowledge_applied: dict[str, list[str]]` - Maps habit UID to KU UIDs
- `knowledge_mastery: dict[str, float]` - KU UID to mastery score
- `ready_to_learn_uids: list[str]` - KUs ready to learn

**Note:** Event/Journal/Choice knowledge tracking fields are placeholders for future UserContext extension.

**Dependencies:**
- UserContext (REQUIRED)
- KuOperations backend (for global substance score lookup)

---

## BaseAnalyticsService Features

### Inherited Infrastructure

**Fail-Fast Validation:**
- `_require_graph_intelligence()` - Ensures graph_intel available (used in methods 1 & 2)
- `_require_embeddings()` - Ensures embeddings available (optional enhancement)
- `_require_llm()` - Ensures LLM available (not currently used)

**Standard Attributes:**
- `self.backend` - KuOperations (REQUIRED)
- `self.graph_intel` - GraphIntelligenceService (optional, validated on use)
- `self.relationships` - UnifiedRelationshipService (optional)
- `self.embeddings` - Neo4jGenAIEmbeddingsService (optional - enhanced semantic analysis)
- `self.llm` - LLMService (optional - not currently used)

**Logging:**
```python
self.logger.info("Message")  # Logs to: skuel.intelligence.ku.intelligence
```

**DTO Conversion Helper:**
```python
# Inherited from BaseAnalyticsService
model = self._to_domain_model(
    dto_or_dict=backend_result,
    dto_class=KuDTO,
    model_class=Ku
)
```

---

## Integration with KuService

### Facade Access

```python
# KuService creates intelligence internally
ku_service = KuService(
    backend=ku_backend,
    graph_intelligence_service=graph_intelligence,
    embeddings_service=embeddings_service,
    llm_service=llm_service,
    query_builder=query_builder,
    event_bus=event_bus,
    relationship_service=relationship_service,
)

# Access via .intelligence attribute
result = await ku_service.intelligence.get_cross_domain_opportunities(
    user_uid="user.mike",
    entity_uid="ku.python-basics"
)
```

### KuService Sub-Services

KuIntelligenceService is one of 7 sub-services in the KuService facade:

| Sub-Service | Purpose |
|-------------|---------|
| `core` | CRUD operations |
| `search` | Search and discovery |
| `graph` | Graph navigation and relationships |
| `semantic` | Semantic relationship management |
| `lp` | Learning path operations |
| `practice` | Practice integration |
| **`intelligence`** | **Semantic knowledge intelligence** |

---

## Domain-Specific Features

### Semantic Relationship Analysis

KuIntelligenceService uses **graph intelligence** to analyze semantic knowledge relationships:

**Source Tags:**
- `"ku_intelligence_explicit"` - User-created relationships
- `"ku_intelligence_inferred"` - System-generated relationships

**Confidence Scoring:**
- **0.9+** - User explicitly defined relationship
- **0.7-0.9** - Inferred from KU metadata
- **0.5-0.7** - Suggested based on patterns
- **<0.5** - Low confidence, needs verification

### Cross-Domain Knowledge Connections

Unique among intelligence services, KuIntelligenceService specializes in **cross-domain pattern recognition**:

**Knowledge Transfer Patterns:**
- Identify similar concepts in different domains
- Discover application contexts for theoretical knowledge
- Reveal integrated learning opportunities

**Domain Bridging:**
MOC (Maps of Content) uses this intelligence to:
- Connect related content across domains (Python → ML → Data Science)
- Build non-linear navigation structures
- Create knowledge transfer pathways

### Knowledge Substance Philosophy

KuIntelligenceService implements SKUEL's core principle: **"Applied knowledge, not pure theory"**

**Substance Tracking:**
Measures how knowledge is LIVED through 5 domain types:
1. **Habits** - Daily lifestyle integration (highest weight)
2. **Journals** - Metacognitive reflection
3. **Choices** - Decision-making application
4. **Events** - Practice and embodiment
5. **Tasks** - Real-world application

**Time Decay:**
- 30-day half-life with spaced repetition
- Event-driven updates via domain events
- Reinforcement through repeated application

**LifePath Alignment:**
Knowledge substance contributes 25% to life path alignment score, measuring whether knowledge is:
- Learned (low substance)
- Practiced (medium substance)
- Embodied (high substance)

### Enhanced Semantic Analysis

When `Neo4jGenAIEmbeddingsService` is available, the service provides:
- **Vector similarity** for knowledge recommendations
- **Semantic clustering** for concept grouping
- **Context-aware relevance** scoring
- **Graph-native embeddings** stored directly in Neo4j (January 2026)

---

## Testing

### Unit Tests
```bash
poetry run python -m pytest tests/unit/services/test_ku_intelligence_service.py -v
```

### Integration Tests
```bash
# Test with real backend
poetry run python -m pytest tests/integration/intelligence/test_ku_intelligence.py -v

# Test specific method
poetry run python -m pytest tests/integration/intelligence/ -k "test_get_knowledge_suggestions" -v
```

### Example Test
```python
from unittest.mock import Mock
from core.services.ku_intelligence_service import KuIntelligenceService

# Create mock services
backend = Mock()
graph_intel = Mock()

# Instantiate service
service = KuIntelligenceService(
    backend=backend,
    graph_intelligence_service=graph_intel
)

# Verify initialization
assert service._service_name == "ku.intelligence"
assert service.backend == backend
assert service.graph_intel == graph_intel
```

### Testing Cross-Domain Analysis
```python
from core.models.graph_context import GraphContext, GraphNode, GraphRelationship

# Mock graph context
mock_context = GraphContext(
    nodes=[
        GraphNode(uid="ku.python-basics", label="Ku", properties={"title": "Python Basics"}),
        GraphNode(uid="ku.machine-learning", label="Ku", properties={"title": "Machine Learning"}),
    ],
    relationships=[
        GraphRelationship(
            start_uid="ku.python-basics",
            end_uid="ku.machine-learning",
            rel_type="ENABLES",
            properties={"strength": 0.8}
        )
    ]
)

# Mock graph_intel.get_entity_context to return mock_context
graph_intel.get_entity_context.return_value = Result.ok(mock_context)

# Test cross-domain analysis
result = await service.get_cross_domain_opportunities(
    user_uid="user.mike",
    entity_uid="ku.python-basics"
)

assert result.is_ok
data = result.value
assert len(data["connections"]) == 1
assert data["connections"][0]["relationship"] == "ENABLES"
```

---

## See Also

- `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` - Master index
- `/docs/decisions/ADR-024-base-intelligence-service-migration.md` - BaseAnalyticsService pattern
- `/docs/architecture/knowledge_substance_philosophy.md` - Knowledge substance tracking
- `/core/services/base_intelligence_service.py` - Base implementation
- `/core/services/ku_service.py` - KuService facade
- `/core/services/ku/ku_core_service.py` - KU core operations
- `/core/services/infrastructure/graph_intelligence_service.py` - Graph intelligence utilities
- `/core/events/learning_events.py` - Knowledge domain events
