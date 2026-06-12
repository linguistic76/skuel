"""
Adaptive Learning Path Models
==============================

Shared dataclasses for the adaptive learning path system.

- CrossDomainOpportunity: Cross-domain learning opportunities
  (consumed by AdaptiveLpCrossDomainService and the GraphQL schema)
"""

from dataclasses import dataclass

from core.models.enums import Domain


@dataclass
class CrossDomainOpportunity:
    """An opportunity to apply knowledge across different domains."""

    opportunity_id: str
    title: str
    description: str

    # Domain connections
    source_domain: Domain
    target_domain: Domain
    bridging_knowledge: list[str]  # Knowledge that connects domains

    # Opportunity details
    application_type: str  # How knowledge applies across domains
    practical_projects: list[str]  # Suggested projects to explore this
    skill_transfer_potential: float  # How much skill transfers (0-1)
    innovation_potential: float  # Potential for creative application

    # Requirements
    prerequisite_knowledge: list[str]
    source_knowledge_uids: list[str]  # KU UIDs from source domain
    target_knowledge_uids: list[str]  # KU UIDs from target domain
    estimated_difficulty: float  # 0-10 scale
    estimated_value: float  # Expected learning value

    # Evidence
    supporting_examples: list[str]  # Real-world examples
    success_patterns: list[str]  # Patterns from successful transfers
    confidence_score: float
