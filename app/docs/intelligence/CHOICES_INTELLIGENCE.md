# ChoicesIntelligenceService - Decision Support & Impact Analysis

## Overview

**Architecture:** Extends `BaseAnalyticsService[ChoicesOperations, Choice]`
**Location:** `/core/services/choices/choices_intelligence_service.py` (shell ~170 lines)
**Service Name:** `choices.intelligence`

**File Structure (decomposed March 2026):**
| File | Responsibility |
|------|---------------|
| `choices_intelligence_service.py` | Shell: `__init__`, `entity_label`, 3 protocol delegation methods |
| `_core_intelligence_mixin.py` | `get_choice_with_context`, `get_decision_intelligence`, `analyze_choice_impact` |
| `_analytics_mixin.py` | `get_quick_decision_metrics`, `batch_analyze_decision_complexity`, `get_decision_patterns`, `get_choice_quality_correlations`, `get_domain_decision_patterns` |
| `_behavioral_signals_mixin.py` | Event handlers, dual-track assessment, principle analysis, prediction, life-path contribution, `get_zpd_behavioral_signals` |

---

## Purpose

ChoicesIntelligenceService provides comprehensive decision intelligence combining graph-based context analysis with impact assessment. It analyzes cross-domain decision impact, provides decision support with principle alignment, generates risk assessments, and identifies opportunities through semantic graph traversal and cascade analysis.

**Version:** 1.0.0 (Extracted from EnhancedChoicesService, October 2025)

---

## Core Methods

### Method 1: get_choice_with_context()

**Purpose:** Get choice with full graph context using pure Cypher graph intelligence. Automatically selects optimal query type based on choice's suggested intent.

**Signature:**
```python
@requires_graph_intelligence("get_choice_with_context")
async def get_choice_with_context(
    self,
    uid: str,
    depth: int = 2
) -> Result[tuple[Choice, GraphContext]]:
```

**Parameters:**
- `uid` (str) - Choice UID
- `depth` (int, default=2) - Graph traversal depth

**Returns:**
```python
(choice, graph_context)  # Tuple
```

**Query Selection:**
- **RELATIONSHIP** → Related goals, principles, knowledge
- **HIERARCHICAL** → Decision hierarchy and dependencies
- **AGGREGATION** → Impact analysis across domains
- **Default** → Comprehensive decision ecosystem

**Example:**
```python
result = await choices_service.intelligence.get_choice_with_context(
    uid="choice_001",
    depth=2
)

if result.is_ok:
    choice, graph_context = result.value
    print(f"Choice: {choice.title}")
    print(f"Graph nodes: {len(graph_context.nodes)}")

    # Extract cross-domain insights
    goals = graph_context.get_nodes_by_domain(Domain.GOALS)
    principles = graph_context.get_nodes_by_domain(Domain.PRINCIPLES)
    knowledge = graph_context.get_nodes_by_domain(Domain.KNOWLEDGE)

    print(f"Related to {len(goals)} goals")
    print(f"Guided by {len(principles)} principles")
```

**Dependencies:**
- GraphIntelligenceService (REQUIRED - uses `@requires_graph_intelligence` decorator)
- Uses GraphContextOrchestrator pattern (Phase 2 consolidation)

**Performance:**
- Old approach: ~220ms (3-4 separate queries)
- New approach: ~28ms (single Pure Cypher query)
- 8x faster with single database round trip

---

### Method 2: get_decision_intelligence()

**Purpose:** Get complete decision intelligence for informed choice-making, including context, impact analysis, decision complexity, and recommendations.

**Signature:**
```python
@requires_graph_intelligence("get_decision_intelligence")
async def get_decision_intelligence(
    self,
    choice_uid: str,
    min_confidence: float = 0.7,
    depth: int = 2
) -> Result[DecisionIntelligence]:
```

**Parameters:**
- `choice_uid` (str) - Choice UID
- `min_confidence` (float, default=0.7) - Minimum confidence for graph relationships
- `depth` (int, default=2) - Graph traversal depth

**Returns:**
```python
DecisionIntelligence(
    choice=Choice(...),
    context=DecisionContext(
        goals=[...],         # List[PathAwareGoal]
        principles=[...],    # List[PathAwarePrinciple]
        knowledge=[...]      # List[PathAwareKnowledge]
    ),
    impact=DecisionImpact(
        tasks=[...],         # List (empty for choices)
        goals=[...],         # Supporting + conflicting goals
        habits=[...]         # List (empty for choices)
    ),
    decision_analysis=DecisionAnalysis(
        complexity=7.5,      # 0-10 scale
        confidence_needed="high",
        stake_level="medium"
    ),
    recommendations=DecisionRecommendations(
        gather_more_info=True,
        consult_principles=["Core Value 1", "Core Value 2"],
        consider_impact_on=["goal progress", "habit consistency"],
        improvement_opportunities=["Focus on high-strength goals", ...]
    ),
    graph_context=ChoiceGraphContext(
        cascade_impact=CascadeImpact(...),
        path_aware_context=PathAwareContext(...),
        raw_context={...}
    )
)
```

**Example:**
```python
result = await choices_service.intelligence.get_decision_intelligence("choice_001")

if result.is_ok:
    intelligence = result.value

    # Decision context
    context = intelligence.context
    print(f"Related goals: {len(context.goals)}")
    print(f"Guiding principles: {len(context.principles)}")
    print(f"Required knowledge: {len(context.knowledge)}")

    # Impact analysis
    impact = intelligence.impact
    print(f"Will affect {len(impact.goals)} goals")

    # Decision analysis
    analysis = intelligence.decision_analysis
    print(f"Decision complexity: {analysis.complexity:.1f}/10")
    print(f"Stakes: {analysis.stake_level}")

    # Recommendations
    recs = intelligence.recommendations
    if recs.gather_more_info:
        print("Recommendation: Gather more information before deciding")

    for principle in recs.consult_principles:
        print(f"Consult principle: {principle}")
```

**Dependencies:**
- ChoicesOperations backend (REQUIRED)
- UnifiedRelationshipService (REQUIRED - uses `_require_relationships = True`)
- Uses CrossDomainContextService for typed context retrieval (Phase 3)
- Uses PathAwareIntelligenceHelper for cascade impact calculation (Phase 4)

**Decision Intelligence Components:**

**Context Analysis:**
- Supporting goals (positively aligned)
- Conflicting goals (potentially opposing)
- Guiding principles (value alignment)
- Required knowledge (information needs)

**Complexity Calculation:**
Uses `choice.calculate_decision_complexity()` domain method:
```python
complexity = (
    (num_options * 1.5) +
    (num_principles * 2.0) +
    (num_knowledge * 1.0) +
    (consequence_weight * 3.0)
)
```

**Confidence Levels:**
- `complexity > 7.0` → "high" confidence needed
- `3.0 ≤ complexity ≤ 7.0` → "medium" confidence needed
- `complexity < 3.0` → "low" confidence needed

**Stake Levels:**
- `total_impact > 10` → "high" stakes
- `3 ≤ total_impact ≤ 10` → "medium" stakes
- `total_impact < 3` → "low" stakes

---

### Method 3: analyze_choice_impact()

**Purpose:** Analyze cross-domain impact of a choice with detailed domain breakdowns, risk assessment, and opportunity identification.

**Signature:**
```python
@requires_graph_intelligence("analyze_choice_impact")
async def analyze_choice_impact(
    self,
    choice_uid: str,
    depth: int = 2,
    min_confidence: float = 0.7
) -> Result[ChoiceImpactAnalysis]:
```

**Parameters:**
- `choice_uid` (str) - Choice UID
- `depth` (int, default=2) - Graph traversal depth
- `min_confidence` (float, default=0.7) - Minimum confidence for relationships

**Returns:**
```python
ChoiceImpactAnalysis(
    choice=Choice(...),
    impact_summary=ImpactSummary(
        total_entities_affected=15,
        domains_affected=["goals", "principles"],
        impact_score=8.5  # 0-10 scale
    ),
    domain_impact=DomainImpactBreakdown(
        goals=DomainImpactDetail(
            affected=[...],      # List[PathAwareGoal]
            count=12,
            severity="high"
        ),
        tasks=DomainImpactDetail(
            affected=[],
            count=0,
            severity="none"
        ),
        habits=DomainImpactDetail(
            affected=[],
            count=0,
            severity="none"
        ),
        principles=DomainImpactDetail(
            affected=[...],      # List[PathAwarePrinciple]
            count=3,
            severity="high"
        )
    ),
    risk_assessment=RiskAssessment(
        risk_level="high",
        risk_factors=[
            "May affect 3 core principles",
            "Impacts 12 goals",
            "High overall impact score"
        ],
        mitigation_suggestions=[
            "Carefully evaluate alignment with principles",
            "Consider phased implementation",
            "Track impact on goal progress"
        ]
    ),
    opportunities=[
        "Opportunity to accelerate multiple goals simultaneously",
        "Opportunity to live more aligned with principles",
        "Focus on high-strength goals (3 connections with path strength > 0.7)"
    ],
    graph_context=ChoiceGraphContext(
        cascade_impact=CascadeImpact(...),
        path_aware_context=PathAwareContext(...),
        raw_context={...}
    )
)
```

**Example:**
```python
result = await choices_service.intelligence.analyze_choice_impact("choice_001")

if result.is_ok:
    impact = result.value

    # Impact summary
    summary = impact.impact_summary
    print(f"Affects {summary.total_entities_affected} entities")
    print(f"Impact score: {summary.impact_score:.1f}/10")
    print(f"Domains: {', '.join(summary.domains_affected)}")

    # Domain breakdown
    domain = impact.domain_impact
    print(f"Goals affected: {domain.goals.count} ({domain.goals.severity})")
    print(f"Principles affected: {domain.principles.count} ({domain.principles.severity})")

    # Risk assessment
    risk = impact.risk_assessment
    print(f"\nRisk level: {risk.risk_level}")
    for factor in risk.risk_factors:
        print(f"  ⚠ {factor}")

    print("\nMitigation:")
    for suggestion in risk.mitigation_suggestions:
        print(f"  → {suggestion}")

    # Opportunities
    print("\nOpportunities:")
    for opp in impact.opportunities:
        print(f"  ✨ {opp}")
```

**Dependencies:**
- ChoicesOperations backend (REQUIRED)
- UnifiedRelationshipService (REQUIRED)
- Uses PathAwareIntelligenceHelper for cascade impact calculation (Phase 4)

**Impact Scoring:**
```python
impact_score = min(10.0,
    (num_goals × 2.5) +
    (num_habits × 2.0) +
    (num_tasks × 1.0) +
    (num_principles × 3.0)
)
```

**Severity Levels:**
- `count > 5` → "high" severity
- `2 < count ≤ 5` → "medium" severity
- `0 < count ≤ 2` → "low" severity
- `count = 0` → "none"

**Risk Level Determination:**
```python
if num_principles > 0:
    risk_level = "high"
elif num_goals > 3:
    risk_level = "medium"
elif impact_score > 7.0:
    risk_level = "high"
else:
    risk_level = "low"
```

---

### Method 4: get_quick_decision_metrics()

**Purpose:** Get quick decision metrics using parallel relationship fetch for fast screening without path metadata.

**Signature:**
```python
async def get_quick_decision_metrics(
    self,
    choice_uid: str
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `choice_uid` (str) - Choice UID

**Returns:**
```python
{
    "choice_uid": "choice_001",
    "relationship_counts": {
        "knowledge": 5,
        "principles": 3,
        "learning_paths": 2,
        "required_knowledge": 4
    },
    "quick_complexity": 7.5,  # 0-10 scale
    "stake_level": "high",
    "needs_full_analysis": True,
    "is_informed": True,
    "is_principle_aligned": True
}
```

**Example:**
```python
# Quick check first (fast - ~160ms)
metrics_result = await choices_service.intelligence.get_quick_decision_metrics("choice_001")
metrics = metrics_result.value

if metrics["needs_full_analysis"]:
    # Only call expensive method when needed (slow - ~250ms)
    intel_result = await choices_service.intelligence.get_decision_intelligence("choice_001")
else:
    # Use quick metrics for simple decisions
    print(f"Simple decision: {metrics['stake_level']} complexity")
```

**Dependencies:**
- UnifiedRelationshipService (REQUIRED)
- Uses `ChoiceRelationships.fetch()` for fast UID retrieval

**Performance Optimization:**
- Uses `fetch()` for ~60% faster simple metrics
- No path metadata extraction
- Perfect for dashboard quick views and batch analysis

**Quick Complexity Calculation:**
```python
quick_complexity = min(10.0,
    (knowledge_count × 1.5) +
    (principle_count × 2.0) +
    (required_count × 1.0)
)
```

**Full Analysis Threshold:**
```python
needs_full_analysis = (quick_complexity > 6.0) or (principle_count > 2)
```

---

### Method 5: batch_analyze_decision_complexity()

**Purpose:** Analyze decision complexity for multiple choices in parallel using fast batch processing.

**Signature:**
```python
async def batch_analyze_decision_complexity(
    self,
    choice_uids: list[str]
) -> Result[dict[str, dict[str, Any]]]:
```

**Parameters:**
- `choice_uids` (list[str]) - List of choice UIDs

**Returns:**
```python
{
    "choice_001": {
        "complexity": 7.5,
        "total_relationships": 14,
        "is_informed": True,
        "is_principle_aligned": True
    },
    "choice_002": {
        "complexity": 3.2,
        "total_relationships": 5,
        "is_informed": True,
        "is_principle_aligned": False
    },
    ...
}
```

**Example:**
```python
# Analyze 100 user choices in ~4s instead of ~8s
all_choices = ["choice_001", "choice_002", ..., "choice_100"]
batch_result = await choices_service.intelligence.batch_analyze_decision_complexity(all_choices)

if batch_result.is_ok:
    # Filter complex decisions for full analysis
    complex_choices = [
        uid
        for uid, metrics in batch_result.value.items()
        if metrics["complexity"] > 6.0
    ]

    # Only run expensive analysis on subset
    for uid in complex_choices:
        await choices_service.intelligence.get_decision_intelligence(uid)
```

**Dependencies:**
- UnifiedRelationshipService (REQUIRED)
- Uses `ChoiceRelationships.fetch()` with `asyncio.gather()` for parallel fetching

**Performance:**
- ~50% faster than sequential processing
- ~4s for 100 choices vs ~8s sequential
- Perfect for dashboards and pattern analysis

---

### Method 6: assess_decision_quality_dual_track() (ADR-030)

**Purpose:** Compare user's self-assessed decision quality with system-measured decision quality metrics, generating perception gap analysis and personalized insights.

**Signature:**
```python
async def assess_decision_quality_dual_track(
    self,
    user_uid: str,
    user_decision_quality_level: DecisionQualityLevel,
    user_evidence: str,
    user_reflection: str | None = None,
    period_days: int = 30,
) -> Result[DualTrackResult[DecisionQualityLevel]]:
```

**Parameters:**
- `user_uid` (str) - User identifier
- `user_decision_quality_level` (DecisionQualityLevel) - User's self-assessed level
- `user_evidence` (str) - User's evidence for their assessment
- `user_reflection` (str, optional) - User's optional reflection
- `period_days` (int, default=30) - Period to analyze for system calculation

**Returns:**
```python
DualTrackResult[DecisionQualityLevel](
    entity_uid="user.mike",
    entity_type="decision_quality_assessment",

    # USER-DECLARED (Vision)
    user_level=DecisionQualityLevel.EXCELLENT,
    user_score=0.90,
    user_evidence="I carefully consider all options before deciding",
    user_reflection="My decisions usually lead to good outcomes",

    # SYSTEM-CALCULATED (Action)
    system_level=DecisionQualityLevel.GOOD,
    system_score=0.72,
    system_evidence=(
        "Positive outcome rate: 70%",
        "Principle alignment: 75%",
        "Decision rate: 80%",
        "Confidence calibration: 65%",
    ),

    # GAP ANALYSIS
    perception_gap=0.18,
    gap_direction="user_higher",

    # INSIGHTS
    insights=("Self-assessment exceeds measured decision quality by ~18%",),
    recommendations=(
        "Review decisions with negative outcomes for learning",
        "Improve confidence calibration",
    ),
)
```

**DecisionQualityLevel Enum:**
```python
class DecisionQualityLevel(str, Enum):
    EXCELLENT = "excellent"                # 0.85+
    GOOD = "good"                          # 0.70-0.85
    MODERATE = "moderate"                  # 0.50-0.70
    POOR = "poor"                          # 0.30-0.50
    VERY_POOR = "very_poor"                # <0.30

    def to_score(self) -> float: ...
    @classmethod
    def from_score(cls, score: float) -> "DecisionQualityLevel": ...
```

**System Metrics Used:**
- Positive outcome rate (choices with positive outcomes / decided choices)
- Principle alignment (choices aligned with principles / total choices)
- Decision rate (decided choices / total choices)
- Confidence calibration (outcome matches confidence level)

**Example:**
```python
result = await choices_service.intelligence.assess_decision_quality_dual_track(
    user_uid="user.mike",
    user_decision_quality_level=DecisionQualityLevel.EXCELLENT,
    user_evidence="I carefully consider all options before deciding",
    user_reflection="My decisions usually lead to good outcomes",
    period_days=30,
)

if result.is_ok:
    assessment = result.value

    if assessment.gap_direction == "aligned":
        print("Your self-assessment matches your actual decision quality!")
    elif assessment.gap_direction == "user_higher":
        print("You may be overestimating your decision quality.")
    else:
        print("You may be underestimating your decision quality!")

    for insight in assessment.insights:
        print(f"Insight: {insight}")
```

**Dependencies:**
- ChoicesOperations backend (REQUIRED)
- Uses `BaseAnalyticsService._dual_track_assessment()` template

**API Endpoint:**
```
POST /api/choices/assess-decision-quality
```

**See:** [ADR-030: Dual-Track Assessment Pattern](../decisions/ADR-030-dual-track-assessment-pattern.md)

---

### Method 7: get_decision_patterns()

**Purpose:** Analyze user's decision-making patterns over a time window.

**Signature:**
```python
async def get_decision_patterns(
    self, user_uid: str, days: int = 90
) -> Result[dict[str, Any]]:
```

**Returns:** `decision_metrics` (frequency, principle alignment %, goal orientation %), `decision_quality`, `patterns` (trend, strategic vs tactical), `recommendations`.

---

### Method 8: get_choice_quality_correlations()

**Purpose:** Analyze correlations between decision quality dimensions (time pressure vs satisfaction, energy vs confidence, principle alignment vs satisfaction).

**Signature:**
```python
async def get_choice_quality_correlations(
    self, user_uid: str, days: int = 90
) -> Result[dict[str, Any]]:
```

---

### Method 9: get_domain_decision_patterns()

**Purpose:** Analyze decision-making frequency and quality broken down by domain.

**Signature:**
```python
async def get_domain_decision_patterns(
    self, user_uid: str, days: int = 90
) -> Result[dict[str, Any]]:
```

---

### Method 10: analyze_principle_adherence()

**Purpose:** Analyze how consistently the user's choices align with their stated principles over a time period. Pure Cypher query — counts ALIGNED_WITH_PRINCIPLE relationships on choices created within the window.

**Signature:**
```python
async def analyze_principle_adherence(
    self, user_uid: str, period_days: int = 90
) -> Result[dict[str, Any]]:
```

**Returns:** `overall_adherence_score` (0.0–1.0), `principle_breakdown` (per-principle aligned count + avg satisfaction), `most_aligned_principle`, `recommendations`.

---

### Method 11: detect_principle_choice_conflicts()

**Purpose:** Detect direct and implicit conflicts between a specific choice and the user's principles. Checks CONFLICTS_WITH_PRINCIPLE edges and flags high-impact choices with zero principle alignment.

**Signature:**
```python
async def detect_principle_choice_conflicts(
    self, choice_uid: str, user_uid: str
) -> Result[dict[str, Any]]:
```

**Returns:** `has_conflicts`, `direct_conflicts` (with severity), `unaligned_warning`, `mitigation_strategies`.

---

### Method 12: predict_decision_quality()

**Purpose:** Predict expected decision quality using a 4-factor model before the choice is made.

**Signature:**
```python
async def predict_decision_quality(
    self, choice_uid: str, user_uid: str
) -> Result[dict[str, Any]]:
```

**4-Factor Model:**
- Principle alignment: 35% weight
- Knowledge-informed: 25% weight
- Historical correlation (past aligned vs unaligned satisfaction): 25% weight
- Complexity-guidance ratio: 15% weight

**Returns:** `predicted_quality_score` (0.0–1.0), `confidence`, `quality_factors` breakdown, `historical_correlation`, `recommendations`.

---

### Method 13: calculate_life_path_contribution_via_principles()

**Purpose:** Trace the contribution chain `Choice → Principle → LifePath` via graph traversal. Combines direct SERVES_LIFE_PATH (60%) with principle-mediated contribution (40%).

**Signature:**
```python
async def calculate_life_path_contribution_via_principles(
    self, choice_uid: str, user_uid: str
) -> Result[dict[str, Any]]:
```

**Returns:** `total_contribution_score`, `direct_contribution`, `principle_mediated_contribution`, `contributing_principles`, `life_path_uid`.

---

### Method 14: get_zpd_behavioral_signals() (ZPD Bridge — March 2026)

**Purpose:** Extract behavioral readiness signals for ZPDService consumption. Aggregates choice history into signals that indicate the user's readiness to engage with new knowledge.

**Signature:**
```python
async def get_zpd_behavioral_signals(
    self, user_uid: str
) -> Result[dict[str, Any]]:
```

**Returns:**
```python
{
    "principle_adherence_score": float,    # 0.0-1.0 — values clarity
    "decision_consistency_score": float,   # 0.0-1.0 — decision maturity
    "active_conflict_count": int,          # unresolved principle tensions (last 30d)
    "high_quality_decision_rate": float,   # recent decision quality trend
}
```

**Consumed by:** `ZPDService.assess_zone()` → `ZPDAssessment.behavioral_readiness`

**See:** `core/services/zpd/zpd_service.py` (Phase 3, pending implementation)

---

## BaseAnalyticsService Features

### Inherited Infrastructure

ChoicesIntelligenceService extends `BaseAnalyticsService[ChoicesOperations, Choice]` for graph analytics WITHOUT AI dependencies (ADR-030).

**Architecture Enforcement:**
- `__slots__` guard prevents llm/embeddings attributes (see BaseAnalyticsService lines 70-100)
- Analytics services work WITHOUT AI - pure graph queries and Python calculations only
- AI features go in separate BaseAIService subclasses (not used for Choices)

**Fail-Fast Validation:**
- `_require_graph_intelligence()` - Ensures graph_intel available
- `_require_relationship_service()` - Ensures relationships available (REQUIRED)

**Standard Attributes (from BaseAnalyticsService):**
- `self.backend` - ChoicesOperations (REQUIRED)
- `self.graph_intel` - GraphIntelligenceService (REQUIRED for graph methods)
- `self.relationships` - UnifiedRelationshipService (REQUIRED)
- `self.event_bus` - Event bus for publishing choice events (optional)
- `self.logger` - Hierarchical logger instance

**NO AI Attributes:**
- ❌ NO `self.llm` - BaseAnalyticsService __slots__ prevents this
- ❌ NO `self.embeddings` - BaseAnalyticsService __slots__ prevents this
- All analytics work via graph queries, not AI

**Domain-Specific Attributes:**
- `self.context_service` - CrossDomainContextService for typed context retrieval (Phase 3)
- `self.orchestrator` - GraphContextOrchestrator for get_with_context pattern (Phase 2)
- `self.path_helper` - PathAwareIntelligenceHelper for cascade analysis (Phase 4)

**Dual-Track Assessment Template:**
- `_dual_track_assessment()` - Template method for vision vs. action gap analysis
- Used by `assess_decision_quality_dual_track()` (Method 6)
- Returns `DualTrackResult[DecisionQualityLevel]` with perception gap

**Logging:**
```python
self.logger.info("Message")  # Logs to: skuel.intelligence.choices.intelligence
```

---

## Integration with ChoicesService

### Facade Access

```python
# ChoicesService creates intelligence internally
choices_service = ChoicesService(
    backend=choices_backend,
    graph_intelligence_service=graph_intelligence,
    embeddings_service=embeddings_service,
    llm_service=llm_service,
    event_bus=event_bus,
    user_service=user_service,
)

# Access via .intelligence attribute
result = await choices_service.intelligence.get_decision_intelligence(
    choice_uid="choice_001"
)
```

---

## Domain-Specific Features

### Decision Support

ChoicesIntelligenceService excels at **informed decision-making** through:
- **Context gathering** - Related goals, guiding principles, required knowledge
- **Impact analysis** - Cross-domain cascade effects
- **Complexity assessment** - Quantified decision difficulty
- **Recommendation generation** - Principle consultation, information gathering

### Impact Analysis

Provides detailed impact breakdown with:
- **Domain-specific severity** - Per-domain impact levels
- **Cascade analysis** - Direct and indirect effects
- **Risk assessment** - Potential negative consequences
- **Opportunity identification** - Positive leverage points

### Path-Aware Intelligence (Phase 4)

Uses `PathAwareIntelligenceHelper` for:
- **Path strength calculation** - Connection quality scoring
- **Cascade impact** - Multi-hop effect analysis
- **Strong connection detection** - High-value relationship identification
- **Recommendation generation** - Path-strength-based suggestions

**Path-Aware Types:**
```python
from core.models.graph.path_aware_types import (
    PathAwareGoal,          # Goal with distance, path_strength, via_relationships
    PathAwarePrinciple,     # Principle with path metadata
    PathAwareKnowledge,     # Knowledge with path metadata
    ChoiceCrossContext      # Strongly-typed choice context
)
```

### Graph-Native Relationships

Uses `ChoiceRelationships.fetch()` for typed relationship access:
- `informed_by_knowledge_uids` - Knowledge informing decision
- `aligned_principle_uids` - Principles guiding decision
- `opens_learning_path_uids` - Learning paths enabled by choice
- `required_knowledge_uids` - Knowledge needed for decision

**Relationship Analysis Methods:**
```python
# Check decision quality
is_informed = rels.is_informed_decision()        # Has knowledge?
is_aligned = rels.is_principle_aligned()         # Has principles?
total_knowledge = rels.total_knowledge_count()   # Knowledge + required
```

### CrossDomainContextService (Phase 3)

Uses typed context retrieval with:
- `ChoiceCrossContext` - Type-safe field access
- `supporting_goals`, `conflicting_goals` - Separated goal relationships
- Cascade impact calculation
- Path-aware recommendation generation

---

## Testing

### Unit Tests
```bash
poetry run python -m pytest tests/unit/services/test_choices_intelligence_service.py -v
```

### Integration Tests
```bash
# Test with real backend
poetry run python -m pytest tests/integration/intelligence/test_choices_intelligence.py -v

# Test specific method
poetry run python -m pytest tests/integration/intelligence/ -k "test_get_decision_intelligence" -v
```

### Example Test
```python
from unittest.mock import Mock
from core.services.choices.choices_intelligence_service import ChoicesIntelligenceService

# Create mock services
backend = Mock()
graph_intel = Mock()
relationships = Mock()

# Instantiate service
service = ChoicesIntelligenceService(
    backend=backend,
    graph_intelligence_service=graph_intel,
    relationship_service=relationships
)

# Verify initialization
assert service._service_name == "choices.intelligence"
assert service.backend == backend
assert service.graph_intel == graph_intel
assert service.relationships == relationships
assert service.path_helper is not None
```

---

## See Also

- `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` - Master index
- `/docs/decisions/ADR-024-base-intelligence-service-migration.md` - BaseAnalyticsService pattern
- `/core/services/base_intelligence_service.py` - Base implementation
- `/core/services/choices/choices_service.py` - ChoicesService facade
- `/core/services/intelligence/cross_domain_context_service.py` - Phase 3 context retrieval
- `/core/services/intelligence/path_aware_intelligence_helper.py` - Phase 4 cascade analysis
