"""
Adaptive Learning Path Cross-Domain Service
==========================================

Handles cross-domain learning opportunity discovery.

Focuses on:
- Cross-domain opportunity identification
- Innovation pattern detection
- Domain synergy analysis
- Multi-domain opportunity scoring
"""

from collections import defaultdict
from operator import attrgetter
from typing import Any

from core.models.enums import Domain

# Import dataclasses from shared models module (breaks circular dependency)
from core.services.adaptive_lp.adaptive_lp_models import CrossDomainOpportunity
from core.services.adaptive_lp_types import KnowledgeState
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.uid_generator import UIDGenerator


class AdaptiveLpCrossDomainService:
    """
    Service for discovering cross-domain learning opportunities.

    Focuses on:
    - Identifying synergies between knowledge domains
    - Multi-domain innovation opportunities
    - Real-world application examples
    - Opportunity scoring and ranking
    """

    def __init__(self, cross_domain_threshold: float = 0.6) -> None:
        """
        Initialize the cross-domain service.

        Args:
            cross_domain_threshold: Minimum confidence threshold for opportunities
        """
        self.cross_domain_threshold = cross_domain_threshold
        self.logger = get_logger("skuel.adaptive_lp_cross_domain")

    @with_error_handling(error_type="system", uid_param="user_uid")
    async def discover_cross_domain_opportunities(
        self, user_uid: str, knowledge_state: KnowledgeState, min_confidence: float | None = None
    ) -> Result[list[CrossDomainOpportunity]]:
        """
        Discover learning opportunities that span multiple knowledge domains.

        Args:
            user_uid: User to analyze for cross-domain opportunities,
            knowledge_state: Current knowledge state analysis,
            min_confidence: Minimum confidence threshold for opportunities

        Returns:
            Result containing list of CrossDomainOpportunity objects
        """
        if min_confidence is None:
            min_confidence = self.cross_domain_threshold

        applied_knowledge = knowledge_state.applied_knowledge

        if len(applied_knowledge) < 2:
            # Need knowledge in multiple domains for cross-domain opportunities
            return Result.ok([])

        # Group knowledge by domain
        domain_knowledge = defaultdict(list)
        for ku_uid in applied_knowledge:
            if "." in ku_uid and len(ku_uid.split(".")) >= 3:
                domain = ku_uid.split(".")[1]
                domain_knowledge[domain].append(ku_uid)

        # Find domains with sufficient knowledge
        active_domains = {
            domain: knowledge_list
            for domain, knowledge_list in domain_knowledge.items()
            if len(knowledge_list) >= 2
        }

        if len(active_domains) < 2:
            return Result.ok([])

        # Generate cross-domain opportunities
        opportunities = []
        domain_pairs = []

        # Create all possible domain pairs
        domains = list(active_domains.keys())
        domain_pairs.extend(
            [
                (domains[i], domains[j])
                for i in range(len(domains))
                for j in range(i + 1, len(domains))
            ]
        )

        # Generate opportunities for each domain pair
        for source_domain, target_domain in domain_pairs:
            opportunity = await self._create_cross_domain_opportunity(
                source_domain,
                target_domain,
                active_domains[source_domain],
                active_domains[target_domain],
                user_uid,
            )
            if opportunity and opportunity.confidence_score >= min_confidence:
                opportunities.append(opportunity)

        # Add innovation opportunities (combining 3+ domains)
        if len(active_domains) >= 3:
            innovation_opportunities = await self._discover_innovation_opportunities(
                active_domains, user_uid
            )
            opportunities.extend(innovation_opportunities)

        # Score and rank opportunities
        scored_opportunities = await self._score_cross_domain_opportunities(
            opportunities, user_uid, knowledge_state
        )

        self.logger.info(
            f"Discovered {len(scored_opportunities)} cross-domain learning opportunities "
            f"for user {user_uid} across {len(active_domains)} domains"
        )

        return Result.ok(scored_opportunities[:10])  # Return top 10

    async def _create_cross_domain_opportunity(
        self,
        source_domain: str,
        target_domain: str,
        source_knowledge: list[str],
        target_knowledge: list[str],
        _user_uid: str,
    ) -> CrossDomainOpportunity | None:
        """Create a cross-domain opportunity between two domains."""
        try:
            # Define known cross-domain synergies
            domain_synergies = {
                ("programming", "data"): {
                    "application_type": "Data Engineering & Analytics",
                    "bridging_concepts": ["algorithms", "data_structures", "automation"],
                    "projects": [
                        "Build a data pipeline with automated processing",
                        "Create a real-time analytics dashboard",
                        "Develop a machine learning model deployment system",
                    ],
                    "skill_transfer": 0.8,
                    "innovation_potential": 0.9,
                },
                ("programming", "web"): {
                    "application_type": "Full-Stack Development",
                    "bridging_concepts": ["api_design", "database_integration", "user_experience"],
                    "projects": [
                        "Build a complete web application with backend API",
                        "Create a responsive single-page application",
                        "Develop a real-time web service",
                    ],
                    "skill_transfer": 0.9,
                    "innovation_potential": 0.7,
                },
                ("web", "design"): {
                    "application_type": "UI/UX Development",
                    "bridging_concepts": ["user_interface", "interaction_design", "accessibility"],
                    "projects": [
                        "Design and implement a user-centered web interface",
                        "Create an accessible and responsive design system",
                        "Build interactive prototypes and user flows",
                    ],
                    "skill_transfer": 0.7,
                    "innovation_potential": 0.8,
                },
                ("data", "business"): {
                    "application_type": "Business Intelligence & Strategy",
                    "bridging_concepts": ["analytics", "decision_making", "performance_metrics"],
                    "projects": [
                        "Develop business metrics and KPI dashboards",
                        "Create predictive models for business outcomes",
                        "Build automated reporting and insight systems",
                    ],
                    "skill_transfer": 0.6,
                    "innovation_potential": 0.8,
                },
                ("programming", "security"): {
                    "application_type": "Secure Software Development",
                    "bridging_concepts": [
                        "encryption",
                        "authentication",
                        "vulnerability_assessment",
                    ],
                    "projects": [
                        "Implement secure authentication and authorization systems",
                        "Build security testing and monitoring tools",
                        "Create encrypted communication systems",
                    ],
                    "skill_transfer": 0.7,
                    "innovation_potential": 0.9,
                },
            }

            # Check for synergy (both directions)
            synergy_key = (source_domain, target_domain)
            reverse_key = (target_domain, source_domain)

            synergy = domain_synergies.get(synergy_key) or domain_synergies.get(reverse_key)

            if not synergy:
                # Create generic cross-domain opportunity
                synergy = {
                    "application_type": f"{source_domain.title()} + {target_domain.title()} Integration",
                    "bridging_concepts": ["integration", "automation", "optimization"],
                    "projects": [
                        f"Combine {source_domain} and {target_domain} in a practical project",
                        f"Explore how {source_domain} enhances {target_domain} workflows",
                        f"Build tools that bridge {source_domain} and {target_domain}",
                    ],
                    "skill_transfer": 0.5,
                    "innovation_potential": 0.6,
                }

            # Calculate confidence based on user's knowledge depth
            source_depth = len(source_knowledge)
            target_depth = len(target_knowledge)
            min_depth = min(source_depth, target_depth)
            max_depth = max(source_depth, target_depth)

            # Higher confidence if user has good knowledge in both domains
            confidence = min(1.0, (min_depth * 0.3 + max_depth * 0.2) / 3.0)
            confidence = max(0.4, confidence)  # Minimum confidence

            # Create the opportunity
            return CrossDomainOpportunity(
                opportunity_id=UIDGenerator.generate_random_uid("cross_domain"),
                title=f"{synergy['application_type']}",
                description=f"Leverage your {source_domain} and {target_domain} knowledge to create innovative solutions",
                source_domain=self._string_to_domain(source_domain),
                target_domain=self._string_to_domain(target_domain),
                bridging_knowledge=synergy["bridging_concepts"],
                application_type=synergy["application_type"],
                practical_projects=synergy["projects"],
                skill_transfer_potential=synergy["skill_transfer"],
                innovation_potential=synergy["innovation_potential"],
                prerequisite_knowledge=source_knowledge + target_knowledge,
                estimated_difficulty=5.0 + (min_depth * 0.5),  # Base difficulty + complexity
                estimated_value=float(synergy["skill_transfer"])
                * float(synergy["innovation_potential"]),
                supporting_examples=await self._find_real_world_examples(
                    source_domain, target_domain
                ),
                success_patterns=[
                    f"Professionals combining {source_domain} and {target_domain} skills",
                    f"Startups bridging {source_domain} and {target_domain}",
                    f"Projects that integrate {source_domain} with {target_domain}",
                ],
                confidence_score=confidence,
            )

        except Exception as e:
            self.logger.warning(f"Failed to create cross-domain opportunity: {e}")
            return None

    async def _discover_innovation_opportunities(
        self, domain_knowledge: dict[str, list[str]], _user_uid: str
    ) -> list[CrossDomainOpportunity]:
        """Discover innovation opportunities combining 3+ domains."""
        opportunities = []

        if len(domain_knowledge) < 3:
            return opportunities

        domains = list(domain_knowledge.keys())

        # Define some known multi-domain innovation areas
        innovation_patterns: list[dict[str, Any]] = [
            {
                "domains": ["programming", "data", "web"],
                "title": "AI-Powered Web Applications",
                "description": "Create intelligent web applications that learn from user data",
                "bridging_concepts": ["machine_learning", "api_design", "real_time_processing"],
                "innovation_potential": 0.95,
            },
            {
                "domains": ["programming", "business", "data"],
                "title": "Automated Business Intelligence",
                "description": "Build systems that automatically generate business insights from data",
                "bridging_concepts": ["automation", "analytics", "decision_support"],
                "innovation_potential": 0.9,
            },
            {
                "domains": ["web", "design", "programming"],
                "title": "Interactive User Experience Platforms",
                "description": "Develop platforms that create personalized, interactive user experiences",
                "bridging_concepts": ["user_interface", "personalization", "responsive_design"],
                "innovation_potential": 0.85,
            },
        ]

        # Check which innovation patterns the user can pursue
        for pattern in innovation_patterns:
            required_domains = set(pattern["domains"])
            user_domains = set(domains)

            if required_domains.issubset(user_domains):
                # User has knowledge in all required domains
                # Type-safe access to pattern dict fields
                pattern_title = str(pattern["title"])
                pattern_title_lower = pattern_title.lower()

                opportunity = CrossDomainOpportunity(
                    opportunity_id=UIDGenerator.generate_random_uid("innovation"),
                    title=pattern_title,
                    description=str(pattern["description"]),
                    source_domain=self._string_to_domain(str(pattern["domains"][0])),
                    target_domain=self._string_to_domain(str(pattern["domains"][1])),
                    bridging_knowledge=pattern["bridging_concepts"],  # type: ignore[arg-type]
                    application_type="Multi-Domain Innovation",
                    practical_projects=[
                        f"Prototype a {pattern_title_lower} solution",
                        f"Research market opportunities in {pattern_title_lower}",
                        f"Build a proof-of-concept demonstrating {pattern_title_lower}",
                    ],
                    skill_transfer_potential=0.8,
                    innovation_potential=float(pattern["innovation_potential"]),
                    prerequisite_knowledge=[],  # User already has the knowledge
                    estimated_difficulty=7.0,  # High difficulty for innovation
                    estimated_value=float(pattern["innovation_potential"]),
                    supporting_examples=[
                        f"Successful companies in {pattern_title_lower}",
                        f"Emerging trends in {pattern_title_lower}",
                        f"Market opportunities for {pattern_title_lower}",
                    ],
                    success_patterns=[
                        f"Entrepreneurs who built {pattern_title_lower} solutions",
                        f"Teams that successfully integrated {', '.join(str(d) for d in pattern['domains'])}",
                    ],
                    confidence_score=0.8,  # High confidence for matched patterns
                )
                opportunities.append(opportunity)

        return opportunities

    async def _score_cross_domain_opportunities(
        self,
        opportunities: list[CrossDomainOpportunity],
        _user_uid: str,
        _knowledge_state: KnowledgeState,
    ) -> list[CrossDomainOpportunity]:
        """Score and rank cross-domain opportunities."""
        for opportunity in opportunities:
            # Calculate overall value score
            value_factors = [
                opportunity.skill_transfer_potential * 0.3,
                opportunity.innovation_potential * 0.3,
                opportunity.confidence_score * 0.2,
                (1.0 - (opportunity.estimated_difficulty / 10.0)) * 0.1,  # Easier = higher score
                opportunity.estimated_value * 0.1,
            ]

            opportunity.estimated_value = sum(value_factors)

        # Sort by estimated value
        opportunities.sort(key=attrgetter("estimated_value"), reverse=True)

        return opportunities

    async def _find_real_world_examples(self, source_domain: str, target_domain: str) -> list[str]:
        """Find real-world examples of cross-domain applications."""

        domain_examples = {
            ("programming", "data"): [
                "Netflix recommendation algorithms",
                "Uber real-time pricing systems",
                "Google search ranking algorithms",
            ],
            ("programming", "web"): [
                "Airbnb booking platform",
                "GitHub code collaboration platform",
                "Slack team communication tools",
            ],
            ("web", "design"): [
                "Apple website user experience",
                "Spotify music discovery interface",
                "Figma collaborative design platform",
            ],
            ("data", "business"): [
                "Amazon business intelligence dashboards",
                "Tesla manufacturing optimization",
                "Walmart supply chain analytics",
            ],
        }

        key = (source_domain, target_domain)
        reverse_key = (target_domain, source_domain)

        return domain_examples.get(
            key,
            domain_examples.get(
                reverse_key,
                [
                    f"Companies using both {source_domain} and {target_domain}",
                    f"Startups in the {source_domain}-{target_domain} space",
                    f"Products that combine {source_domain} with {target_domain}",
                ],
            ),
        )

    def _string_to_domain(self, domain_string: str) -> Domain:
        """Convert domain string to Domain enum."""
        domain_mapping = {
            "programming": Domain.TECH,
            "web": Domain.TECH,
            "data": Domain.TECH,
            "business": Domain.BUSINESS,
            "design": Domain.CREATIVE,
            "security": Domain.TECH,
            "ml": Domain.TECH,
            "api": Domain.TECH,
        }

        return domain_mapping.get(domain_string, Domain.KNOWLEDGE)
