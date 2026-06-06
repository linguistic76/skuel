"""
Choices Service Intelligence Types
====================================

Frozen dataclasses for choices intelligence service results.
Follows Pattern 3C: dict[str, Any] → frozen dataclasses

Pattern:
- Frozen (immutable after construction)
- Type-safe field access
- Self-documenting structure
- Follows user_stats_types.py pattern
"""

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any


def _to_serializable(obj: Any) -> Any:
    """Recursively convert a frozen-dataclass result tree into JSON-serializable data.

    Handles the shapes these result types actually hold: nested frozen dataclasses
    (ImpactSummary, CascadeImpact, PathAware* entities, …), enums, date/datetime, the
    ``choice`` domain model (via its own ``to_dict``/``model_dump`` if present, else its
    uid), and plain containers. Not a blind ``dataclasses.asdict`` — that chokes on the
    domain model and non-JSON-native ``date`` values.
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_serializable(v) for v in obj]
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _to_serializable(getattr(obj, f.name)) for f in fields(obj)}
    # Domain model (e.g. Choice) — prefer its own serializer, else fall back to uid/str.
    domain_to_dict = getattr(obj, "to_dict", None)
    if callable(domain_to_dict):
        return domain_to_dict()
    model_dump = getattr(obj, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    uid = getattr(obj, "uid", None)
    return uid if uid is not None else str(obj)


@dataclass(frozen=True)
class DecisionContext:
    """
    Context information for making a decision.

    Attributes:
        goals: Related goals
        principles: Guiding principles
        knowledge: Required knowledge
    """

    goals: list[Any] = field(default_factory=list)
    principles: list[Any] = field(default_factory=list)
    knowledge: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class DecisionImpact:
    """
    Impact analysis for a decision.

    Attributes:
        tasks: Affected tasks
        goals: Affected goals
        habits: Affected habits
    """

    tasks: list[Any] = field(default_factory=list)
    goals: list[Any] = field(default_factory=list)
    habits: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class DecisionAnalysis:
    """
    Complexity and stakes analysis for a decision.

    Attributes:
        complexity: Decision complexity score (0-10)
        confidence_needed: Confidence level needed (low/medium/high)
        stake_level: Stakes level (low/medium/high)
    """

    complexity: float
    confidence_needed: str
    stake_level: str


@dataclass(frozen=True)
class DecisionRecommendations:
    """
    Recommendations for making a decision.

    Attributes:
        gather_more_info: Whether to gather more information
        consult_principles: Principles to consult
        consider_impact_on: Areas to consider impact on
        improvement_opportunities: Path-aware recommendations for strengthening connections
    """

    gather_more_info: bool
    consult_principles: list[str] = field(default_factory=list)
    consider_impact_on: list[str] = field(default_factory=list)
    improvement_opportunities: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CascadeImpact:
    """
    Cascade impact analysis using path-aware intelligence.

    Attributes:
        total_impact: Total weighted impact score
        direct_impact: Impact from direct connections (distance=1)
        indirect_impact: Impact from indirect connections (distance>1)
        domain_impacts: Impact breakdown by domain (goals, principles, etc.)
    """

    total_impact: float
    direct_impact: float
    indirect_impact: float
    domain_impacts: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PathAwareContext:
    """
    Path-aware context information.

    Attributes:
        total_strong_connections: Number of strong connections (path_strength >= 0.7)
        direct_connections_count: Number of direct connections (distance=1)
        max_path_depth: Maximum path depth discovered
        avg_path_strength: Average path strength across all connections
    """

    total_strong_connections: int
    direct_connections_count: int
    max_path_depth: int
    avg_path_strength: float


@dataclass(frozen=True)
class ChoiceGraphContext:
    """
    Complete graph context for a choice with path-aware intelligence.

    Attributes:
        cascade_impact: Cascade impact analysis
        path_aware_context: Path-aware metrics
    """

    cascade_impact: CascadeImpact
    path_aware_context: PathAwareContext


@dataclass(frozen=True)
class DecisionIntelligence:
    """
    Complete decision intelligence data.

    Comprehensive decision support including context, impact,
    analysis, and recommendations.

    Attributes:
        choice: The choice entity
        context: Decision context (goals, principles, knowledge)
        impact: Impact analysis (tasks, goals, habits)
        decision_analysis: Complexity and stakes analysis
        recommendations: Decision recommendations
        graph_context: Graph context with path-aware intelligence
    """

    choice: Any
    context: DecisionContext
    impact: DecisionImpact
    decision_analysis: DecisionAnalysis
    recommendations: DecisionRecommendations
    graph_context: ChoiceGraphContext

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable view (protocol/route boundary)."""
        return {f.name: _to_serializable(getattr(self, f.name)) for f in fields(self)}


@dataclass(frozen=True)
class ImpactSummary:
    """
    Summary of choice impact.

    Attributes:
        total_entities_affected: Total number of affected entities
        domains_affected: List of affected domain names
        impact_score: Impact score (0-10)
    """

    total_entities_affected: int
    domains_affected: list[str]
    impact_score: float


@dataclass(frozen=True)
class DomainImpactDetail:
    """
    Impact details for a specific domain.

    Attributes:
        affected: List of affected entities
        count: Number of affected entities
        severity: Severity level (low/medium/high)
    """

    affected: list[Any]
    count: int
    severity: str


@dataclass(frozen=True)
class DomainImpactBreakdown:
    """
    Breakdown of impact by domain.

    Attributes:
        goals: Impact on goals
        tasks: Impact on tasks
        habits: Impact on habits
        principles: Impact on principles
    """

    goals: DomainImpactDetail
    tasks: DomainImpactDetail
    habits: DomainImpactDetail
    principles: DomainImpactDetail


@dataclass(frozen=True)
class RiskAssessment:
    """
    Risk assessment for a choice.

    Attributes:
        risk_level: Risk level (low/medium/high)
        risk_factors: List of risk factors
        mitigation_suggestions: List of mitigation suggestions
    """

    risk_level: str
    risk_factors: list[str] = field(default_factory=list)
    mitigation_suggestions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChoiceImpactAnalysis:
    """
    Complete impact analysis for a choice.

    Detailed cross-domain impact analysis including summary,
    domain breakdown, risks, and opportunities.

    Attributes:
        choice: The choice entity
        impact_summary: Summary of impact
        domain_impact: Impact breakdown by domain
        risk_assessment: Risk assessment
        opportunities: List of opportunities
        graph_context: Graph context with path-aware intelligence
    """

    choice: Any
    impact_summary: ImpactSummary
    domain_impact: DomainImpactBreakdown
    risk_assessment: RiskAssessment
    opportunities: list[str]
    graph_context: ChoiceGraphContext

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable view (serves GET /api/choices/insights)."""
        return {f.name: _to_serializable(getattr(self, f.name)) for f in fields(self)}
