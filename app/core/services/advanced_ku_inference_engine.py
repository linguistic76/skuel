"""
Advanced Knowledge Inference Engine (Phase 2.4)
===============================================

Sophisticated algorithms for automatic knowledge detection:
- Multi-algorithm content analysis
- Cross-domain knowledge relationship mapping
- Advanced confidence scoring
- Knowledge validation feedback loops

Builds on the foundation of KuInferenceService with enhanced capabilities.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from operator import attrgetter
from typing import Any, TypedDict

from core.constants import ConfidenceLevel
from core.models.ku.ku_dto import KuDTO as TaskDTO
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


@dataclass
class KuPattern:
    """Represents a detected knowledge pattern with metadata."""

    pattern_type: str
    knowledge_uid: str
    confidence: float
    evidence: list[str]
    domain: str
    cross_references: list[str] = None


@dataclass
class CrossDomainRelationship:
    """Represents a relationship between knowledge across domains."""

    from_knowledge_uid: str
    to_knowledge_uid: str
    from_domain: str
    to_domain: str
    relationship_type: str  # "prerequisite", "enhances", "complements", "applies_to"
    strength: float
    evidence: list[str]


class RelationshipMappingData(TypedDict):
    """Type definition for cross-domain relationship mapping data."""

    type: str  # Relationship type (e.g., "applies_to", "prerequisite")
    strength: float  # Relationship strength (0.0-1.0)
    evidence: list[str]  # Evidence supporting the relationship


class AdvancedKuInferenceEngine:
    """
    Advanced inference engine with sophisticated content analysis algorithms.

    Features:
    1. Multi-algorithm content detection
    2. Cross-domain relationship mapping
    3. Advanced confidence scoring with multiple factors
    4. Knowledge validation and feedback learning
    """

    def __init__(self) -> None:
        self.logger = get_logger("skuel.inference.advanced")
        self._initialize_knowledge_mappings()
        self._initialize_cross_domain_relationships()
        self._validation_feedback = defaultdict(list)

    def _initialize_knowledge_mappings(self) -> None:
        """Initialize comprehensive knowledge detection mappings."""

        # Enhanced keyword-based detection with contextual patterns
        self.knowledge_keywords = {
            # Programming Languages & Frameworks
            "ku.programming.python": {
                "direct": ["python", "django", "flask", "fastapi", "pandas", "numpy", "pip"],
                "contextual": ["def ", "import ", "class ", "python script", "virtual environment"],
                "advanced": ["asyncio", "decorators", "generators", "context managers"],
            },
            "ku.programming.javascript": {
                "direct": ["javascript", "js", "node.js", "react", "vue", "angular", "npm"],
                "contextual": ["function()", "=>", "const ", "async/await", "promise"],
                "advanced": ["closures", "prototypes", "event loop", "webpack"],
            },
            "ku.programming.java": {
                "direct": ["java", "spring", "maven", "gradle", "hibernate"],
                "contextual": ["public class", "extends", "implements", "package"],
                "advanced": ["dependency injection", "aspect programming", "jvm"],
            },
            # Data & Databases
            "ku.data.database": {
                "direct": ["database", "sql", "mysql", "postgresql", "mongodb", "redis"],
                "contextual": ["select ", "insert ", "update ", "delete ", "join"],
                "advanced": ["indexing", "normalization", "acid", "transactions"],
            },
            "ku.data.analytics": {
                "direct": ["analytics", "data analysis", "statistics", "visualization"],
                "contextual": ["data cleaning", "exploratory analysis", "correlation"],
                "advanced": [
                    "statistical modeling",
                    "feature engineering",
                    "dimensionality reduction",
                ],
            },
            # Architecture & Design
            "ku.architecture.microservices": {
                "direct": ["microservices", "microservice", "service mesh", "api gateway"],
                "contextual": ["distributed system", "service discovery", "load balancing"],
                "advanced": ["event sourcing", "cqrs", "saga pattern", "circuit breaker"],
            },
            "ku.architecture.patterns": {
                "direct": ["design pattern", "architecture pattern", "mvc", "mvvm"],
                "contextual": ["singleton", "factory", "observer", "strategy"],
                "advanced": ["dependency inversion", "solid principles", "hexagonal architecture"],
            },
            # DevOps & Infrastructure
            "ku.devops.docker": {
                "direct": ["docker", "container", "dockerfile", "docker-compose"],
                "contextual": ["containerization", "image", "registry", "orchestration"],
                "advanced": ["multi-stage builds", "security scanning", "distroless"],
            },
            "ku.devops.kubernetes": {
                "direct": ["kubernetes", "k8s", "kubectl", "helm"],
                "contextual": ["pods", "services", "deployments", "ingress"],
                "advanced": ["operators", "custom resources", "service mesh", "gitops"],
            },
            # Security
            "ku.security.authentication": {
                "direct": ["authentication", "oauth", "jwt", "saml", "ldap"],
                "contextual": ["login", "password", "token", "session"],
                "advanced": ["multi-factor", "biometric", "zero-trust", "identity provider"],
            },
            "ku.security.encryption": {
                "direct": ["encryption", "ssl", "tls", "aes", "rsa"],
                "contextual": ["encrypt", "decrypt", "certificate", "key"],
                "advanced": ["elliptic curve", "quantum resistance", "key management"],
            },
            # Machine Learning & AI
            "ku.ml.fundamentals": {
                "direct": ["machine learning", "ml", "ai", "artificial intelligence"],
                "contextual": ["training", "model", "prediction", "algorithm"],
                "advanced": ["neural networks", "deep learning", "reinforcement learning"],
            },
            "ku.ml.data_science": {
                "direct": ["data science", "data scientist", "jupyter", "kaggle"],
                "contextual": ["feature selection", "cross validation", "overfitting"],
                "advanced": ["ensemble methods", "hyperparameter tuning", "mlops"],
            },
        }

        # Phrase patterns for more sophisticated detection
        self.knowledge_phrases = {
            "ku.programming.api": [
                r"\b(?:rest|restful)\s+api\b",
                r"\b(?:graphql|grpc)\b",
                r"\bapi\s+(?:design|development|integration)\b",
                r"\b(?:endpoint|swagger|openapi)\b",
            ],
            "ku.architecture.scalability": [
                r"\b(?:horizontal|vertical)\s+scaling\b",
                r"\b(?:load\s+balancing|caching|cdn)\b",
                r"\b(?:performance|scalability)\s+optimization\b",
            ],
            "ku.devops.cicd": [
                r"\b(?:ci|cd|continuous)\s+(?:integration|deployment|delivery)\b",
                r"\b(?:jenkins|github\s+actions|gitlab\s+ci)\b",
                r"\b(?:pipeline|automation|deployment)\b",
            ],
        }

    def _initialize_cross_domain_relationships(self) -> None:
        """Initialize cross-domain knowledge relationships."""

        self.cross_domain_mappings: dict[tuple[str, str], RelationshipMappingData] = {
            # Programming → DevOps relationships
            ("ku.programming.python", "ku.devops.docker"): {
                "type": "applies_to",
                "strength": 0.8,
                "evidence": ["Python applications often containerized with Docker"],
            },
            ("ku.programming.javascript", "ku.devops.kubernetes"): {
                "type": "applies_to",
                "strength": 0.7,
                "evidence": ["Node.js apps commonly deployed on Kubernetes"],
            },
            # Architecture → Programming relationships
            ("ku.architecture.microservices", "ku.programming.api"): {
                "type": "prerequisite",
                "strength": 0.9,
                "evidence": ["Microservices architecture requires API design knowledge"],
            },
            ("ku.architecture.patterns", "ku.programming.python"): {
                "type": "enhances",
                "strength": 0.6,
                "evidence": ["Design patterns enhance programming skills"],
            },
            # Data → ML relationships
            ("ku.data.database", "ku.ml.data_science"): {
                "type": "prerequisite",
                "strength": 0.8,
                "evidence": ["Database knowledge essential for data science"],
            },
            ("ku.data.analytics", "ku.ml.fundamentals"): {
                "type": "prerequisite",
                "strength": 0.9,
                "evidence": ["Analytics foundation needed for machine learning"],
            },
            # Security → All domains relationships
            ("ku.security.authentication", "ku.programming.api"): {
                "type": "complements",
                "strength": 0.85,
                "evidence": ["API security requires authentication knowledge"],
            },
            ("ku.security.encryption", "ku.devops.kubernetes"): {
                "type": "complements",
                "strength": 0.7,
                "evidence": ["K8s security involves encryption"],
            },
        }

    async def analyze_content_advanced(
        self, title: str, description: str = "", entity_type: str = "task"
    ) -> Result[list[KuPattern]]:
        """
        Advanced content analysis using multiple algorithms.

        Args:
            title: Content title,
            description: Content description,
            entity_type: Type of entity (task, event, etc.)

        Returns:
            Result containing detected knowledge patterns
        """
        try:
            patterns = []
            content = f"{title} {description}".lower()

            # Algorithm 1: Enhanced keyword detection
            keyword_patterns = await self._detect_keyword_patterns(content)
            patterns.extend(keyword_patterns)

            # Algorithm 2: Phrase pattern matching
            phrase_patterns = await self._detect_phrase_patterns(content)
            patterns.extend(phrase_patterns)

            # Algorithm 3: Contextual analysis
            contextual_patterns = await self._detect_contextual_patterns(title, description)
            patterns.extend(contextual_patterns)

            # Algorithm 4: Complexity-based inference
            complexity_patterns = await self._detect_complexity_patterns(content)
            patterns.extend(complexity_patterns)

            # Deduplicate and merge similar patterns
            merged_patterns = self._merge_similar_patterns(patterns)

            self.logger.debug(
                "Advanced content analysis found %d patterns for: %s",
                len(merged_patterns),
                title[:50],
            )

            return Result.ok(merged_patterns)

        except Exception as e:
            self.logger.error("Advanced content analysis failed: %s", str(e))
            return Result.fail(
                Errors.system(
                    message="Advanced content analysis failed",
                    exception=e,
                    operation="analyze_content_advanced",
                    entity_type=entity_type,
                    content_length=len(title) + len(description),
                )
            )

    async def _detect_keyword_patterns(self, content: str) -> list[KuPattern]:
        """Detect knowledge patterns using enhanced keyword matching."""
        patterns = []

        for knowledge_uid, keywords_dict in self.knowledge_keywords.items():
            domain = knowledge_uid.split(".")[1]  # Extract domain from UID
            evidence = []
            confidence_factors = []

            # Check direct keywords
            for keyword in keywords_dict.get("direct", []):
                if keyword in content:
                    evidence.append(f"Direct keyword: '{keyword}'")
                    confidence_factors.append(0.8)

            # Check contextual keywords
            for keyword in keywords_dict.get("contextual", []):
                if keyword in content:
                    evidence.append(f"Contextual keyword: '{keyword}'")
                    confidence_factors.append(0.6)

            # Check advanced keywords (higher confidence if found)
            for keyword in keywords_dict.get("advanced", []):
                if keyword in content:
                    evidence.append(f"Advanced keyword: '{keyword}'")
                    confidence_factors.append(0.9)

            # Calculate confidence based on multiple factors
            if confidence_factors:
                base_confidence = max(confidence_factors)
                # Boost confidence for multiple matches
                if len(confidence_factors) > 1:
                    base_confidence = min(
                        0.95, base_confidence + 0.1 * (len(confidence_factors) - 1)
                    )

                patterns.append(
                    KuPattern(
                        pattern_type="keyword_enhanced",
                        knowledge_uid=knowledge_uid,
                        confidence=base_confidence,
                        evidence=evidence,
                        domain=domain,
                    )
                )

        return patterns

    async def _detect_phrase_patterns(self, content: str) -> list[KuPattern]:
        """Detect knowledge patterns using regex phrase matching."""
        patterns = []

        for knowledge_uid, phrase_patterns in self.knowledge_phrases.items():
            domain = knowledge_uid.split(".")[1]
            evidence = []

            for pattern in phrase_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    evidence.extend([f"Phrase pattern: '{match}'" for match in matches])

            if evidence:
                # Higher confidence for phrase patterns as they're more specific
                confidence = min(0.85, 0.7 + 0.05 * len(evidence))

                patterns.append(
                    KuPattern(
                        pattern_type="phrase_pattern",
                        knowledge_uid=knowledge_uid,
                        confidence=confidence,
                        evidence=evidence,
                        domain=domain,
                    )
                )

        return patterns

    async def _detect_contextual_patterns(self, title: str, description: str) -> list[KuPattern]:
        """Detect knowledge patterns using contextual analysis."""
        patterns = []

        # Context-specific detection rules
        combined_text = f"{title} {description}".lower()

        # Project complexity indicators
        complexity_indicators = {
            "high": ["advanced", "complex", "sophisticated", "enterprise", "scalable"],
            "medium": ["implement", "develop", "create", "build", "design"],
            "low": ["simple", "basic", "learn", "understand", "study"],
        }

        # Detect complexity level
        for indicators in complexity_indicators.values():
            if any(indicator in combined_text for indicator in indicators):
                break

        # Integration patterns
        if any(word in combined_text for word in ["integrate", "connect", "combine", "merge"]):
            patterns.append(
                KuPattern(
                    pattern_type="contextual_integration",
                    knowledge_uid="ku.architecture.integration",
                    confidence=ConfidenceLevel.MEDIUM,
                    evidence=[f"Integration context detected in: {title}"],
                    domain="architecture",
                )
            )

        # Learning patterns
        if any(word in combined_text for word in ["learn", "study", "understand", "explore"]):
            patterns.append(
                KuPattern(
                    pattern_type="contextual_learning",
                    knowledge_uid="ku.learning.self_directed",
                    confidence=ConfidenceLevel.LOW,
                    evidence=["Learning context detected"],
                    domain="learning",
                )
            )

        return patterns

    async def _detect_complexity_patterns(self, content: str) -> list[KuPattern]:
        """Detect knowledge patterns based on content complexity."""
        patterns = []

        # Technical depth indicators
        depth_keywords = {
            "ku.programming.advanced": ["optimization", "performance", "memory", "algorithm"],
            "ku.architecture.advanced": ["distributed", "scalable", "fault-tolerant", "resilient"],
            "ku.security.advanced": ["vulnerability", "penetration", "hardening", "compliance"],
        }

        for knowledge_uid, keywords in depth_keywords.items():
            matches = [kw for kw in keywords if kw in content]
            if matches:
                domain = knowledge_uid.split(".")[1]
                patterns.append(
                    KuPattern(
                        pattern_type="complexity_based",
                        knowledge_uid=knowledge_uid,
                        confidence=ConfidenceLevel.MEDIUM,
                        evidence=[f"Complexity indicators: {', '.join(matches)}"],
                        domain=domain,
                    )
                )

        return patterns

    def _merge_similar_patterns(self, patterns: list[KuPattern]) -> list[KuPattern]:
        """Merge similar patterns and combine evidence."""

        def _pattern_dict_factory() -> Any:
            return {"evidence": [], "confidences": []}

        pattern_map = defaultdict(_pattern_dict_factory)

        for pattern in patterns:
            key = pattern.knowledge_uid
            pattern_map[key]["evidence"].extend(pattern.evidence)
            pattern_map[key]["confidences"].append(pattern.confidence)
            pattern_map[key]["pattern"] = pattern

        merged = []
        for knowledge_uid, data in pattern_map.items():
            base_pattern = data["pattern"]
            # Take maximum confidence and combine evidence
            max_confidence = max(data["confidences"])
            # Slight boost for multiple detection methods
            if len(data["confidences"]) > 1:
                max_confidence = min(0.95, max_confidence + 0.05)

            merged.append(
                KuPattern(
                    pattern_type="merged",
                    knowledge_uid=knowledge_uid,
                    confidence=max_confidence,
                    evidence=list(set(data["evidence"])),  # Deduplicate evidence
                    domain=base_pattern.domain,
                )
            )

        return merged

    async def discover_cross_domain_relationships(
        self, detected_patterns: list[KuPattern]
    ) -> Result[list[CrossDomainRelationship]]:
        """
        Discover relationships between knowledge across different domains.

        Args:
            detected_patterns: List of detected knowledge patterns

        Returns:
            Result containing list of cross-domain relationships
        """
        try:
            relationships = []

            # Extract knowledge UIDs by domain
            knowledge_by_domain = defaultdict(list)
            for pattern in detected_patterns:
                knowledge_by_domain[pattern.domain].append(pattern)

            # Find cross-domain relationships
            for (from_uid, to_uid), relationship_data in self.cross_domain_mappings.items():
                from_pattern = next(
                    (p for p in detected_patterns if p.knowledge_uid == from_uid), None
                )
                to_pattern = next((p for p in detected_patterns if p.knowledge_uid == to_uid), None)

                if from_pattern and to_pattern:
                    # Calculate relationship strength based on pattern confidences
                    strength = (
                        (from_pattern.confidence + to_pattern.confidence)
                        / 2
                        * relationship_data["strength"]
                    )

                    relationships.append(
                        CrossDomainRelationship(
                            from_knowledge_uid=from_uid,
                            to_knowledge_uid=to_uid,
                            from_domain=from_pattern.domain,
                            to_domain=to_pattern.domain,
                            relationship_type=relationship_data["type"],
                            strength=strength,
                            evidence=relationship_data["evidence"]
                            + [
                                f"Detected {from_uid} with confidence {from_pattern.confidence:.2f}",
                                f"Detected {to_uid} with confidence {to_pattern.confidence:.2f}",
                            ],
                        )
                    )

            # Sort by strength (strongest relationships first)
            relationships.sort(key=attrgetter("strength"), reverse=True)

            self.logger.debug("Discovered %d cross-domain relationships", len(relationships))

            return Result.ok(relationships)

        except Exception as e:
            return Result.fail(
                Errors.system(
                    message="Cross-domain relationship discovery failed",
                    exception=e,
                    operation="discover_cross_domain_relationships",
                    pattern_count=len(detected_patterns),
                )
            )

    def calculate_advanced_confidence_score(
        self, pattern: KuPattern, context: dict[str, Any]
    ) -> float:
        """
        Calculate advanced confidence score using multiple factors.

        Args:
            pattern: Knowledge pattern to score,
            context: Additional context (entity type, user history, etc.)

        Returns:
            Enhanced confidence score
        """
        base_confidence = pattern.confidence

        # Factor 1: Evidence quality
        evidence_quality = len(pattern.evidence) * 0.05  # Up to 0.25 boost for 5+ evidence items
        evidence_quality = min(0.25, evidence_quality)

        # Factor 2: Pattern type reliability
        type_reliability = {
            "phrase_pattern": 0.1,  # Phrase patterns are more reliable
            "keyword_enhanced": 0.05,  # Enhanced keywords are somewhat reliable
            "contextual_integration": 0.08,
            "complexity_based": 0.12,  # Complexity-based are highly reliable
            "merged": 0.15,  # Merged patterns are most reliable
        }.get(pattern.pattern_type, 0.0)

        # Factor 3: Domain expertise (if available in context)
        domain_boost = 0.0
        if "user_expertise" in context:
            user_domains = context["user_expertise"].get("domains", [])
            if pattern.domain in user_domains:
                domain_boost = 0.1

        # Factor 4: Historical validation (if available)
        validation_boost = 0.0
        if pattern.knowledge_uid in self._validation_feedback:
            feedback_items = self._validation_feedback[pattern.knowledge_uid]
            if feedback_items:
                avg_feedback = sum(feedback_items) / len(feedback_items)
                validation_boost = (avg_feedback - 0.5) * 0.1  # -0.1 to +0.1 based on feedback

        # Calculate final confidence
        final_confidence = (
            base_confidence + evidence_quality + type_reliability + domain_boost + validation_boost
        )

        # Ensure confidence stays within bounds
        return max(0.0, min(1.0, final_confidence))

    def add_validation_feedback(
        self, knowledge_uid: str, was_correct: bool, confidence_adjustment: float = 0.0
    ):
        """
        Add validation feedback for knowledge inference accuracy.

        Args:
            knowledge_uid: The knowledge UID that was validated
            was_correct: Whether the inference was correct
            confidence_adjustment: Optional adjustment to confidence (-1.0 to 1.0)
        """
        feedback_score = 1.0 if was_correct else 0.0
        if confidence_adjustment != 0.0:
            feedback_score += confidence_adjustment

        self._validation_feedback[knowledge_uid].append(feedback_score)

        # Keep only recent feedback (last 20 items)
        if len(self._validation_feedback[knowledge_uid]) > 20:
            self._validation_feedback[knowledge_uid] = self._validation_feedback[knowledge_uid][
                -20:
            ]

        self.logger.info(
            "Added validation feedback for %s: correct=%s, score=%.2f",
            knowledge_uid,
            was_correct,
            feedback_score,
        )

    async def enhance_task_dto_with_advanced_inference(self, task_dto: TaskDTO) -> Result[TaskDTO]:
        """
        Enhance TaskDTO with advanced knowledge inference.

        Args:
            task_dto: TaskDTO to enhance

        Returns:
            Result containing enhanced TaskDTO with sophisticated inference data
        """
        try:
            # Run advanced content analysis
            analysis_result = await self.analyze_content_advanced(
                task_dto.title, task_dto.description or "", entity_type="task"
            )

            if analysis_result.is_error:
                self.logger.warning("Advanced analysis failed: %s", analysis_result.error)
                return Result.ok(task_dto)  # Return unmodified DTO

            detected_patterns = analysis_result.value

            # Extract knowledge UIDs and calculate enhanced confidence scores
            inferred_uids = []
            confidence_scores = {}
            knowledge_patterns = []

            context = {
                "entity_type": "task",
                "title_length": len(task_dto.title),
                "has_description": bool(task_dto.description),
            }

            for pattern in detected_patterns:
                inferred_uids.append(pattern.knowledge_uid)

                # Calculate advanced confidence score
                enhanced_confidence = self.calculate_advanced_confidence_score(pattern, context)
                confidence_scores[pattern.knowledge_uid] = enhanced_confidence
                knowledge_patterns.append(pattern.pattern_type)

            # Discover cross-domain relationships
            relationships_result = await self.discover_cross_domain_relationships(detected_patterns)
            cross_domain_relationships = (
                relationships_result.value if relationships_result.is_ok else []
            )
            if relationships_result.is_error:
                self.logger.warning("Cross-domain discovery failed: %s", relationships_result.error)

            # Update TaskDTO with enhanced inference
            task_dto.primary_knowledge_uids = list(
                set(task_dto.primary_knowledge_uids + inferred_uids)
            )
            task_dto.knowledge_confidence_scores = {
                **(task_dto.knowledge_confidence_scores or {}),
                **confidence_scores,
            }
            task_dto.knowledge_inference_metadata = task_dto.knowledge_inference_metadata or {}
            task_dto.knowledge_inference_metadata["patterns_detected"] = list(
                set(knowledge_patterns)
            )
            task_dto.learning_opportunities_count = len(detected_patterns) + len(
                cross_domain_relationships
            )

            # Enhanced inference metadata
            task_dto.knowledge_inference_metadata = {
                "inference_version": "2.4_advanced",
                "inference_timestamp": task_dto.updated_at.isoformat(),
                "algorithm_confidence": max(confidence_scores.values())
                if confidence_scores
                else 0.0,
                "patterns_detected": len(detected_patterns),
                "cross_domain_relationships": len(cross_domain_relationships),
                "advanced_features": {
                    "phrase_patterns": len(
                        [p for p in detected_patterns if p.pattern_type == "phrase_pattern"]
                    ),
                    "contextual_analysis": len(
                        [p for p in detected_patterns if "contextual" in p.pattern_type]
                    ),
                    "complexity_detection": len(
                        [p for p in detected_patterns if p.pattern_type == "complexity_based"]
                    ),
                },
            }

            return Result.ok(task_dto)

        except Exception as e:
            return Result.fail(
                Errors.system(
                    message="Advanced inference enhancement failed",
                    exception=e,
                    operation="enhance_task_dto_with_advanced_inference",
                    task_title=task_dto.title,
                )
            )
