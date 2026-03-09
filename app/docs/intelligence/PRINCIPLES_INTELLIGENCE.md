# PrinciplesIntelligenceService - Cross-Domain Principle Alignment & Conflict Detection

## Overview

**Architecture:** Extends `BaseAnalyticsService[PrinciplesOperations, Principle]`
**Location:** `/core/services/principles/principles_intelligence_service.py`
**Service Name:** `principles.intelligence`
**Lines:** ~1,909

---

## Purpose

PrinciplesIntelligenceService analyzes how well users live by their stated principles through cross-domain activity tracking, adherence trend analysis, and conflict detection. It provides alignment scoring, behavioral consistency analysis, and identifies principle conflicts that may require resolution.

---

## Core Methods

### Method 1: get_principle_with_context()

**Purpose:** Get principle with full graph context using pure Cypher graph intelligence. Automatically selects optimal query type based on principle's suggested intent.

**Signature:**
```python
async def get_principle_with_context(
    self,
    uid: str,
    depth: int = 2
) -> Result[tuple[Principle, GraphContext]]:
```

**Parameters:**
- `uid` (str) - Principle UID
- `depth` (int, default=2) - Graph traversal depth

**Returns:**
```python
(principle, graph_context)  # Tuple
```

**Query Selection:**
- **RELATIONSHIP** → Activities aligned with principle
- **HIERARCHICAL** → Principle hierarchy and dependencies
- **AGGREGATION** → Alignment statistics and trends
- **Default** → Comprehensive principle ecosystem

**Example:**
```python
result = await principles_service.intelligence.get_principle_with_context(
    uid="principle:integrity",
    depth=2
)

if result.is_ok:
    principle, graph_context = result.value
    print(f"Principle: {principle.name}")
    print(f"Graph nodes: {len(graph_context.nodes)}")
    print(f"Graph relationships: {len(graph_context.relationships)}")
```

**Dependencies:**
- GraphIntelligenceService (REQUIRED - uses `@requires_graph_intelligence` decorator)
- Uses GraphContextOrchestrator pattern (Phase 2 consolidation)

---

### Method 2: assess_principle_alignment()

**Purpose:** Assess how well user is living by a principle through comprehensive alignment assessment including recent activities, adherence score trends, and cross-domain activity breakdown.

**Signature:**
```python
async def assess_principle_alignment(
    self,
    principle_uid: str,
    min_confidence: float = 0.7
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `principle_uid` (str) - Principle UID
- `min_confidence` (float, default=0.7) - Minimum confidence for graph relationships

**Returns:**
```python
{
    "principle": Principle(...),
    "alignment_score": 0.68,
    "recent_activities": 12,
    "activities_breakdown": {
        "tasks": [],
        "choices": [{"uid": "choice_001"}, {"uid": "choice_002"}],
        "habits": [{"uid": "habit_001"}],
        "goals": [{"uid": "goal_001"}]
    },
    "activity_counts": {
        "tasks": 0,
        "choices": 5,
        "habits": 3,
        "goals": 4,
        "total": 12
    },
    "alignment_assessment": {
        "needs_attention": False,
        "strong_alignment": True,
        "consistent_practice": True
    },
    "recent_trend": "improving",
    "recommendations": [
        "Excellent alignment! You're living this principle consistently"
    ],
    "metrics": {
        "adherence_score": 0.68,
        "goal_count": 4,
        "habit_count": 3,
        "choice_count": 5,
        "knowledge_count": 2,
        "total_influence_count": 12,
        "needs_attention": False,
        "strong_alignment": True,
        "consistent_practice": True
    },
    "graph_context": {
        "goal_count": 4,
        "habit_count": 3,
        "choice_count": 5,
        "knowledge_count": 2
    }
}
```

**Example:**
```python
result = await principles_service.intelligence.assess_principle_alignment(
    principle_uid="principle:integrity"
)

if result.is_ok:
    data = result.value
    print(f"Alignment score: {data['alignment_score']:.0%}")
    print(f"Recent trend: {data['recent_trend']}")
    print(f"Total activities: {data['recent_activities']}")

    print("\nActivity Breakdown:")
    counts = data['activity_counts']
    print(f"  Choices: {counts['choices']}")
    print(f"  Habits: {counts['habits']}")
    print(f"  Goals: {counts['goals']}")

    for rec in data["recommendations"]:
        print(f"Recommendation: {rec}")
```

**Dependencies:**
- PrinciplesOperations backend (REQUIRED)
- PrinciplesRelationshipOperations (REQUIRED - uses `_require_relationship_service()`)
- Uses CrossDomainContextService for typed context retrieval (Phase 3)
- Uses `calculate_principle_metrics()` for standard metrics
- Uses `PrincipleCrossContext` for type-safe field access

**Alignment Assessment Logic:**
```python
needs_attention = adherence_score < 0.4
strong_alignment = adherence_score >= 0.7
consistent_practice = total_activities >= 10
```

---

### Method 3: get_principle_adherence_trends()

**Purpose:** Analyze principle adherence trends over time including trajectory analysis, activity frequency, consistency metrics, and pattern identification.

**Signature:**
```python
async def get_principle_adherence_trends(
    self,
    principle_uid: str,
    days: int = 90
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `principle_uid` (str) - Principle UID
- `days` (int, default=90) - Number of days to analyze

**Returns:**
```python
{
    "principle": Principle(...),
    "period": {
        "start_date": "2025-10-10",
        "end_date": "2026-01-08",
        "days": 90
    },
    "current_state": {
        "adherence_score": 0.5,
        "recent_activity_count": 18,
        "consistency_score": 0.6
    },
    "trends": {
        "trajectory": "improving",
        "average_weekly_activities": 1.4,
        "most_active_week": {
            "week": 1,
            "activities": 2
        },
        "least_active_week": {
            "week": 13,
            "activities": 1
        }
    },
    "consistency_analysis": {
        "weeks_with_activity": 7,
        "consistency_percentage": 53.8,
        "longest_streak": 6,
        "current_streak": 4
    },
    "recommendations": [
        "Great 4-week streak! Keep it going",
        "Aim for at least 2-3 activities per week aligned with this principle"
    ]
}
```

**Example:**
```python
# Analyze last 90 days
result = await principles_service.intelligence.get_principle_adherence_trends(
    principle_uid="principle:integrity",
    days=90
)

if result.is_ok:
    data = result.value
    current = data["current_state"]
    trends = data["trends"]
    consistency = data["consistency_analysis"]

    print(f"Current adherence: {current['adherence_score']:.0%}")
    print(f"Trajectory: {trends['trajectory']}")
    print(f"Avg weekly activities: {trends['average_weekly_activities']:.1f}")
    print(f"Current streak: {consistency['current_streak']} weeks")
    print(f"Consistency: {consistency['consistency_percentage']:.1f}%")
```

**Dependencies:**
- PrinciplesOperations backend (REQUIRED)
- PrinciplesRelationshipOperations (REQUIRED)

**Trajectory Calculation:**
```python
trajectory = "improving"  # avg_weekly_activities > 3
trajectory = "declining"  # avg_weekly_activities < 1
trajectory = "stable"     # otherwise
```

---

### Method 4: get_principle_conflict_analysis()

**Purpose:** Analyze conflicts between user's principles by identifying situations where principles may be in tension through competing activities, resource allocation conflicts, priority conflicts, and value tensions.

**Signature:**
```python
async def get_principle_conflict_analysis(
    self,
    user_uid: str
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `user_uid` (str) - User identifier

**Returns:**
```python
{
    "user_uid": "user.mike",
    "total_principles": 5,
    "conflicts_detected": 2,
    "conflicts": [
        {
            "principle1": {
                "uid": "principle:work-excellence",
                "label": "Work Excellence"
            },
            "principle2": {
                "uid": "principle:family-first",
                "label": "Family First"
            },
            "severity": "high",
            "conflict_area": "goal_alignment",
            "overlapping_goals_count": 3,
            "description": "Work Excellence and Family First both guide the same goals"
        },
        {
            "principle1": {
                "uid": "principle:health",
                "label": "Health"
            },
            "principle2": {
                "uid": "principle:productivity",
                "label": "Productivity"
            },
            "severity": "medium",
            "conflict_area": "goal_alignment",
            "overlapping_goals_count": 2,
            "description": "Health and Productivity both guide the same goals"
        }
    ],
    "conflict_severity": {
        "high": 1,
        "medium": 1,
        "low": 0
    },
    "resolution_recommendations": [
        "Resolve 1 high-severity conflicts involving core principles",
        "Review 1 medium-severity conflicts for priority clarification",
        "Low harmony score - clarify principle priorities and values"
    ],
    "harmony_score": 0.8
}
```

**Example:**
```python
result = await principles_service.intelligence.get_principle_conflict_analysis(
    user_uid="user.mike"
)

if result.is_ok:
    data = result.value
    print(f"Total principles: {data['total_principles']}")
    print(f"Conflicts detected: {data['conflicts_detected']}")
    print(f"Harmony score: {data['harmony_score']:.0%}")

    print("\nConflicts:")
    for conflict in data["conflicts"]:
        p1 = conflict["principle1"]["label"]
        p2 = conflict["principle2"]["label"]
        severity = conflict["severity"]
        print(f"  [{severity.upper()}] {p1} vs {p2}")
        print(f"    {conflict['description']}")

    print("\nRecommendations:")
    for rec in data["resolution_recommendations"]:
        print(f"  - {rec}")
```

**Dependencies:**
- PrinciplesOperations backend (REQUIRED)
- PrinciplesRelationshipOperations (REQUIRED)

**Conflict Severity Calculation:**
```python
# Both principles are "core"
severity = "high"

# One principle is "core"
severity = "medium"

# Neither is "core"
severity = "low"
```

**Harmony Score:**
```python
total_possible_conflicts = len(principles) × (len(principles) - 1) // 2
harmony_score = 1.0 - (len(conflicts) / total_possible_conflicts)
```

---

### Method 5: get_quick_principle_impact()

**Purpose:** Get quick principle impact metrics using parallel relationship fetch for fast dashboard views and screening.

**Signature:**
```python
async def get_quick_principle_impact(
    self,
    principle_uid: str
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `principle_uid` (str) - Principle UID

**Returns:**
```python
{
    "principle_uid": "principle:integrity",
    "relationship_counts": {
        "grounded_knowledge": 2,
        "guided_goals": 4,
        "inspired_habits": 3,
        "related_principles": 1
    },
    "impact_score": 7.5,
    "adoption_level": "embodied",
    "has_foundation": True,
    "guides_actions": True,
    "total_action_count": 7
}
```

**Example:**
```python
# Quick check first (fast - ~160ms)
result = await principles_service.intelligence.get_quick_principle_impact(
    principle_uid="principle:integrity"
)

if result.is_ok:
    impact = result.value
    print(f"Impact score: {impact['impact_score']}/10")
    print(f"Adoption level: {impact['adoption_level']}")
    print(f"Guides actions: {impact['guides_actions']}")

    counts = impact["relationship_counts"]
    print(f"\nRelationships:")
    print(f"  Knowledge grounded: {counts['grounded_knowledge']}")
    print(f"  Goals guided: {counts['guided_goals']}")
    print(f"  Habits inspired: {counts['inspired_habits']}")

    if impact["impact_score"] > 5.0:
        # Only call expensive method for high-impact principles
        full_result = await principles_service.intelligence.get_principle_with_context(
            principle_uid
        )
```

**Dependencies:**
- PrinciplesRelationshipOperations (REQUIRED)
- Uses `PrincipleRelationships.fetch()` for fast parallel UID fetching

**OPTIMIZATION:** Uses `fetch()` for ~60% faster simple metrics compared to `get_principle_with_context()`.

**Impact Score Calculation:**
```python
impact_score = min(10.0,
    (goal_count × 2.5) +
    (habit_count × 2.0) +
    (knowledge_count × 1.0)
)
```

**Adoption Level Logic:**
```python
total_actions = goal_count + habit_count

adoption_level = "embodied"     # total_actions > 5
adoption_level = "developing"   # total_actions > 2
adoption_level = "exploring"    # otherwise
```

---

### Method 6: batch_analyze_principle_adoption()

**Purpose:** Analyze principle adoption for multiple principles in parallel for dashboard views and filtering high-impact principles before detailed analysis.

**Signature:**
```python
async def batch_analyze_principle_adoption(
    self,
    principle_uids: list[str]
) -> Result[dict[str, dict[str, Any]]]:
```

**Parameters:**
- `principle_uids` (list[str]) - List of principle UIDs to analyze

**Returns:**
```python
{
    "principle:integrity": {
        "impact_score": 7.5,
        "adoption_level": "embodied",
        "total_actions": 7,
        "has_foundation": True,
        "guides_actions": True
    },
    "principle:excellence": {
        "impact_score": 3.5,
        "adoption_level": "developing",
        "total_actions": 3,
        "has_foundation": True,
        "guides_actions": True
    },
    "principle:balance": {
        "impact_score": 1.0,
        "adoption_level": "exploring",
        "total_actions": 1,
        "has_foundation": False,
        "guides_actions": True
    }
}
```

**Example:**
```python
# Analyze all user principles in ~2s instead of ~4s
all_principles = ["principle:integrity", "principle:excellence", "principle:balance"]

result = await principles_service.intelligence.batch_analyze_principle_adoption(
    principle_uids=all_principles
)

if result.is_ok:
    batch_result = result.value

    # Filter embodied principles for deeper analysis
    embodied = [
        uid
        for uid, metrics in batch_result.items()
        if metrics["adoption_level"] == "embodied"
    ]

    print(f"Total principles: {len(all_principles)}")
    print(f"Embodied principles: {len(embodied)}")

    # Only run expensive analysis on embodied principles
    for uid in embodied:
        detailed = await principles_service.intelligence.get_principle_with_context(uid)
        # Process detailed context...
```

**Dependencies:**
- PrinciplesRelationshipOperations (REQUIRED)
- Uses `PrincipleRelationships.fetch()` with parallel execution

**OPTIMIZATION:** Uses `fetch()` for ~50% faster batch processing compared to sequential `get_principle_with_context()` calls.

---

### Method 7: assess_alignment_dual_track() (ADR-030)

**Purpose:** Compare user's self-assessed principle alignment with system-measured alignment metrics, generating perception gap analysis and personalized insights.

**Signature:**
```python
async def assess_alignment_dual_track(
    self,
    principle_uid: str,
    user_uid: str,
    user_alignment_level: AlignmentLevel,
    user_evidence: str,
    user_reflection: str | None = None,
) -> Result[DualTrackResult[AlignmentLevel]]:
```

**Parameters:**
- `principle_uid` (str) - Principle UID to assess alignment for
- `user_uid` (str) - User identifier
- `user_alignment_level` (AlignmentLevel) - User's self-assessed alignment level
- `user_evidence` (str) - User's evidence for their assessment
- `user_reflection` (str, optional) - User's optional reflection

**Returns:**
```python
DualTrackResult[AlignmentLevel](
    entity_uid="principle:integrity",
    entity_type="principle",

    # USER-DECLARED (Vision)
    user_level=AlignmentLevel.ALIGNED,
    user_score=1.0,
    user_evidence="I always act with integrity in my work and relationships",
    user_reflection="This is my core value",

    # SYSTEM-CALCULATED (Action)
    system_level=AlignmentLevel.MOSTLY_ALIGNED,
    system_score=0.75,
    system_evidence=(
        "Goals aligned: 4",
        "Choices consistent: 3",
        "Habits supporting: 2",
        "Total entities: 9",
    ),

    # GAP ANALYSIS
    perception_gap=0.25,
    gap_direction="user_higher",

    # INSIGHTS
    insights=("Self-assessment is higher than measured behavior",),
    recommendations=(
        "Track specific instances of integrity in daily decisions",
        "Link more habits to this principle",
    ),
)
```

**AlignmentLevel Enum:**
```python
class AlignmentLevel(str, Enum):
    ALIGNED = "aligned"                    # 0.85+
    MOSTLY_ALIGNED = "mostly_aligned"      # 0.70-0.85
    PARTIALLY_ALIGNED = "partially_aligned"  # 0.50-0.70
    MISALIGNED = "misaligned"              # 0.30-0.50
    UNKNOWN = "unknown"                    # <0.30

    def to_score(self) -> float: ...
    @classmethod
    def from_score(cls, score: float) -> "AlignmentLevel": ...
```

**System Metrics Used:**
- Goals aligned with the principle
- Choices consistent with the principle
- Habits supporting the principle
- Total entity count

**Example:**
```python
result = await principles_service.intelligence.assess_alignment_dual_track(
    principle_uid="principle:integrity",
    user_uid="user.mike",
    user_alignment_level=AlignmentLevel.ALIGNED,
    user_evidence="I always act with integrity",
    user_reflection="This is my core value",
)

if result.is_ok:
    assessment = result.value
    print(f"Principle: {assessment.entity_uid}")
    print(f"User level: {assessment.user_level.value}")
    print(f"System level: {assessment.system_level.value}")
    print(f"Perception gap: {assessment.perception_gap:.0%}")

    if assessment.has_perception_gap():
        print("\nRecommendations:")
        for rec in assessment.recommendations:
            print(f"  - {rec}")
```

**Dependencies:**
- PrinciplesOperations backend (REQUIRED)
- Uses `BaseAnalyticsService._dual_track_assessment()` template

**API Endpoint:**
```
POST /api/principles/assess-alignment
```

**See:** [ADR-030: Dual-Track Assessment Pattern](../decisions/ADR-030-dual-track-assessment-pattern.md)

---

## BaseAnalyticsService Features

### Inherited Infrastructure

**Fail-Fast Validation:**
- `_require_graph_intelligence()` - Ensures graph_intel available
- `_require_relationship_service()` - Ensures relationships available (REQUIRED for most methods)

**Standard Attributes:**
- `self.backend` - PrinciplesOperations (REQUIRED)
- `self.graph_intel` - GraphIntelligenceService (REQUIRED for graph methods)
- `self.relationships` - PrinciplesRelationshipOperations (REQUIRED for alignment/conflict analysis)
- `self.embeddings` - OpenAIEmbeddingsService (not currently used)
- `self.llm` - LLMService (not currently used)

**Domain-Specific Attributes:**
- `self.context_service` - CrossDomainContextService for typed context retrieval (Phase 3)
- `self.orchestrator` - GraphContextOrchestrator for get_with_context pattern (Phase 2)

**Logging:**
```python
self.logger.info("Message")  # Logs to: skuel.intelligence.principles.intelligence
```

---

## Integration with PrinciplesService

### Facade Access

```python
# PrinciplesService creates intelligence internally
principles_service = PrinciplesService(
    backend=principles_backend,
    graph_intelligence_service=graph_intelligence,
    embeddings_service=embeddings_service,
    llm_service=llm_service,
    event_bus=event_bus,
    user_service=user_service,
)

# Access via .intelligence attribute
result = await principles_service.intelligence.assess_principle_alignment(
    principle_uid="principle:integrity"
)
```

---

## Domain-Specific Features

### Cross-Domain Principle Alignment

PrinciplesIntelligenceService excels at **measuring lived values** through:
- **Activity tracking** - Goals, habits, choices aligned with principle
- **Adherence scoring** - Quantitative measure of principle embodiment
- **Trend analysis** - Weekly trajectory, consistency patterns
- **Behavioral insights** - Peak activity weeks, streak analysis

**Note on Tasks:** Principles don't directly relate to tasks in SKUEL's graph model. The relationship flow is: Principles → Goals/Habits/Choices → Tasks (indirect).

### Conflict Detection

The service identifies principle conflicts through:
- **Overlapping goals** - Multiple principles guiding the same goals
- **Severity analysis** - Based on principle strength (core vs. non-core)
- **Harmony scoring** - Overall principle ecosystem health
- **Resolution recommendations** - Prioritization guidance

**Conflict Detection Logic:**
```python
# Get cross-domain contexts for each principle
context1 = await relationships.get_cross_domain_context(principle1_uid)
context2 = await relationships.get_cross_domain_context(principle2_uid)

# Find overlapping goals
goals1 = set(g["uid"] for g in context1["goals"])
goals2 = set(g["uid"] for g in context2["goals"])
overlapping = goals1 & goals2

# Conflicts exist when multiple principles guide the same goal
if overlapping:
    severity = determine_severity(principle1.strength, principle2.strength)
```

### Graph-Native Relationships

Uses `PrincipleRelationships.fetch()` for typed relationship access:
- `grounded_knowledge_uids` - Knowledge grounding the principle
- `guided_goal_uids` - Goals aligned with principle
- `inspired_habit_uids` - Habits embodying principle
- `related_principle_uids` - Related or supporting principles

**Helper Methods:**
- `has_any_knowledge()` - Checks if principle has knowledge foundation
- `is_integrated()` - Checks if principle guides actions (goals or habits)
- `total_influence_count()` - Sum of all guided activities

### CrossDomainContextService (Phase 3)

Uses typed context retrieval with:
- `PrincipleCrossContext` - Type-safe field access
- `calculate_principle_metrics()` - Standard metrics calculation
- Recommendation generation via `_generate_alignment_recommendations()`

**Standard Metrics:**
```python
{
    "adherence_score": float,           # 0.0-1.0 alignment score
    "goal_count": int,                  # Goals guided by principle
    "habit_count": int,                 # Habits inspired by principle
    "choice_count": int,                # Choices guided by principle
    "knowledge_count": int,             # Knowledge grounding principle
    "total_influence_count": int,       # Sum of all activities
    "needs_attention": bool,            # adherence_score < 0.4
    "strong_alignment": bool,           # adherence_score >= 0.7
    "consistent_practice": bool         # total_influence >= 10
}
```

### Application Opportunities

The service discovers where principles can be applied:
- **Knowledge gaps** - Principles without knowledge foundation
- **Action gaps** - Principles not guiding goals or habits
- **Low adoption** - Principles with total_actions < 5
- **High conflicts** - Harmony score < 0.7

---

## Testing

### Unit Tests
```bash
poetry run python -m pytest tests/unit/services/test_principles_intelligence_service.py -v
```

### Integration Tests
```bash
# Test with real backend
poetry run python -m pytest tests/integration/intelligence/test_principles_intelligence.py -v

# Test specific method
poetry run python -m pytest tests/integration/intelligence/ -k "test_assess_principle_alignment" -v
```

### Example Test
```python
from unittest.mock import Mock
from core.services.principles.principles_intelligence_service import PrinciplesIntelligenceService

# Create mock services
backend = Mock()
graph_intel = Mock()
relationships = Mock()

# Instantiate service
service = PrinciplesIntelligenceService(
    backend=backend,
    graph_intelligence_service=graph_intel,
    relationship_service=relationships
)

# Verify initialization
assert service._service_name == "principles.intelligence"
assert service.backend == backend
assert service.graph_intel == graph_intel
assert service.relationships == relationships
assert service.entity_label == "Principle"
```

---

## See Also

- `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` - Master index
- `/docs/decisions/ADR-024-base-intelligence-service-migration.md` - BaseAnalyticsService pattern
- `/core/services/base_intelligence_service.py` - Base implementation
- `/core/services/principles/principles_service.py` - PrinciplesService facade
- `/core/services/intelligence/cross_domain_context_service.py` - Phase 3 context retrieval
- `/core/services/principles/principle_relationships.py` - PrincipleRelationships helper
