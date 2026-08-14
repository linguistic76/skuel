"""
Knowledge Inference Service
==========================

**UTILITY SERVICE** - Injected dependency, not a standalone service.
This service is used BY TasksService for automatic knowledge tagging, not a duplicate.

Automatic knowledge inference algorithms for enhanced task models.
Provides algorithms to infer knowledge connections from task content,
detect learning opportunities, and calculate confidence scores.

Contract (ADR-065 — Functional Inference Contract):
    Inference returns a typed ``Result[TaskInferenceResult]`` carrying ONLY
    the enrichment fields. Callers apply via
    ``dataclasses.replace(task, **result.value.as_kwargs())``. The input is
    never mutated.

Architecture:
- Lives at `/core/services/` level (not in `/ku/` directory)
- Injected into TasksService for automatic knowledge inference
- Specialized utility for pattern-based knowledge detection
- See `/core/services/ps/` for architecture overview
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from operator import attrgetter
from typing import Any, TypedDict

from core.constants import ConfidenceLevel, InferenceConfidence
from core.models.inference import KnowledgeConnection
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.models.task.task_inference_result import TaskInferenceResult
from core.services.tasks.task_relationships import TaskRelationships
from core.utils.decorators import with_error_handling
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


@dataclass
class KuPattern:
    """Represents a detected knowledge pattern with metadata.

    ``pattern_type`` names the detector that produced the pattern
    (``keyword_enhanced``, ``phrase_pattern``, ``contextual_*``,
    ``complexity_based``) — or ``merged`` when several same-UID patterns
    were combined, in which case ``contributing_types`` records the
    original detector types.
    """

    pattern_type: str
    knowledge_uid: str
    confidence: float
    evidence: list[str]
    domain: str
    contributing_types: list[str] = field(default_factory=list)

    @property
    def source_types(self) -> list[str]:
        """Detector types behind this pattern (unwraps ``merged``)."""
        return self.contributing_types or [self.pattern_type]


def _table_domain(knowledge_uid: str) -> str:
    """Grouping label for a *hardcoded inference-table* key.

    The keyword/phrase tables author their keys in dot form
    (``ku.programming.python``), so the middle segment is a table-local
    grouping label written right beside the keywords — this is NOT uid
    sniffing of unknown input (stored uids stay opaque per ADR-013).
    Guarded so a future dotless table key groups under ``general``
    instead of raising IndexError.
    """
    parts = knowledge_uid.split(".")
    return parts[1] if len(parts) >= 2 else "general"


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


@dataclass
class InferenceConfig:
    """Configuration for knowledge inference algorithms."""

    enable_pattern_detection: bool = True
    enable_opportunity_discovery: bool = True
    enable_insight_generation: bool = True
    # Advanced features
    enable_advanced_engine: bool = True
    enable_cross_domain_mapping: bool = True
    advanced_confidence_scoring: bool = True


class EntityInferenceService:
    """
    Service for automatic knowledge inference and enhancement.

    Provides algorithms to:
    - Infer knowledge connections from task content
    - Detect learning opportunities
    - Generate knowledge insights
    - Calculate confidence scores
    """

    def __init__(self, config: InferenceConfig | None = None) -> None:
        self.config = config or InferenceConfig()
        self.logger = get_logger("skuel.inference.service")

        # Pre-initialize mapping dicts; populated below when advanced engine is enabled.
        self.knowledge_keywords: dict[str, dict[str, list[str]]] = {}
        self.knowledge_phrases: dict[str, list[str]] = {}
        self.cross_domain_mappings: dict[tuple[str, str], RelationshipMappingData] = {}

        if self.config.enable_advanced_engine:
            self._initialize_knowledge_mappings()
            self._initialize_cross_domain_relationships()
            self.logger.info("Advanced knowledge inference engine enabled")
        else:
            self.logger.info("Using basic knowledge inference algorithms")

    # ========================================================================
    # KNOWLEDGE MAPPING INITIALISATION (advanced engine)
    # ========================================================================

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

        self.cross_domain_mappings = {
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

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    @with_error_handling("enhance_task_dto_with_inference", error_type="system")
    def enhance_task_dto_with_inference(self, task: Task | TaskDTO) -> Result[TaskInferenceResult]:
        """Compute knowledge enrichment using advanced algorithms when enabled.

        Returns a typed ``TaskInferenceResult`` (ADR-065). Falls back to basic
        keyword inference when the advanced engine is disabled.
        """
        if self.config.enable_advanced_engine:
            self.logger.debug("Using advanced inference for task: %s", task.title)
            return self._enhance_with_advanced_inference(task)

        self.logger.debug("Using basic inference for task: %s", task.title)
        result = self._basic_inference_fallback(task)
        return Result.ok(result)

    # ========================================================================
    # ADVANCED INFERENCE PATH
    # ========================================================================

    def _enhance_with_advanced_inference(self, task: Task | TaskDTO) -> Result[TaskInferenceResult]:
        """Infer knowledge enrichment using the advanced multi-algorithm pipeline.

        Per ADR-065 the inference layer does NOT mutate its input.
        """
        try:
            analysis_result = self._analyze_content_advanced(
                task.title, task.description or "", entity_type="task"
            )

            if analysis_result.is_error:
                self.logger.warning("Advanced analysis failed: %s", analysis_result.error)
                return Result.ok(TaskInferenceResult())

            detected_patterns = analysis_result.value

            confidence_scores: dict[str, float] = {}
            knowledge_patterns: list[str] = []

            context = {
                "entity_type": "task",
                "title_length": len(task.title),
                "has_description": bool(task.description),
            }

            for pattern in detected_patterns:
                enhanced_confidence = self._calculate_advanced_confidence_score(pattern, context)
                confidence_scores[pattern.knowledge_uid] = enhanced_confidence
                knowledge_patterns.append(pattern.pattern_type)

            relationships_result = self._discover_cross_domain_relationships(detected_patterns)
            cross_domain_relationships = (
                relationships_result.value if relationships_result.is_ok else []
            )
            if relationships_result.is_error:
                self.logger.warning("Cross-domain discovery failed: %s", relationships_result.error)

            metadata: dict[str, Any] = {
                "inference_version": "2.4_advanced",
                "inference_timestamp": task.updated_at.isoformat() if task.updated_at else None,
                "algorithm_confidence": (
                    max(confidence_scores.values()) if confidence_scores else 0.0
                ),
                "patterns_detected": sorted(set(knowledge_patterns)),
                "cross_domain_relationships": len(cross_domain_relationships),
                # source_types unwraps "merged" patterns so contributing
                # detector types still count.
                "advanced_features": {
                    "phrase_patterns": len(
                        [p for p in detected_patterns if "phrase_pattern" in p.source_types]
                    ),
                    "contextual_analysis": len(
                        [
                            p
                            for p in detected_patterns
                            if any("contextual" in t for t in p.source_types)
                        ]
                    ),
                    "complexity_detection": len(
                        [p for p in detected_patterns if "complexity_based" in p.source_types]
                    ),
                },
            }

            return Result.ok(
                TaskInferenceResult(
                    knowledge_confidence_scores=confidence_scores or None,
                    knowledge_inference_metadata=metadata,
                    learning_opportunities_count=(
                        len(detected_patterns) + len(cross_domain_relationships)
                    ),
                )
            )

        except DATA_CONVERSION_EXCEPTIONS as e:
            return Result.fail(
                Errors.system(
                    message="Advanced inference enhancement failed",
                    exception=e,
                    operation="_enhance_with_advanced_inference",
                    task_title=task.title,
                )
            )
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(
                "Unexpected error in inference enhancement: %s: %s", type(e).__name__, e
            )
            return Result.fail(
                Errors.system(
                    message="Advanced inference enhancement failed",
                    exception=e,
                    operation="_enhance_with_advanced_inference",
                    task_title=task.title,
                )
            )

    def _analyze_content_advanced(
        self, title: str, description: str = "", entity_type: str = "task"
    ) -> Result[list[KuPattern]]:
        """Advanced content analysis using multiple algorithms."""
        try:
            patterns = []
            content = f"{title} {description}".lower()

            keyword_patterns = self._detect_keyword_patterns(content)
            patterns.extend(keyword_patterns)

            phrase_patterns = self._detect_phrase_patterns(content)
            patterns.extend(phrase_patterns)

            contextual_patterns = self._detect_contextual_patterns(title, description)
            patterns.extend(contextual_patterns)

            complexity_patterns = self._detect_complexity_patterns(content)
            patterns.extend(complexity_patterns)

            merged_patterns = self._merge_similar_patterns(patterns)

            self.logger.debug(
                "Advanced content analysis found %d patterns for: %s",
                len(merged_patterns),
                title[:50],
            )

            return Result.ok(merged_patterns)

        except DATA_CONVERSION_EXCEPTIONS as e:
            self.logger.error("Advanced content analysis failed: %s", str(e))
            return Result.fail(
                Errors.system(
                    message="Advanced content analysis failed",
                    exception=e,
                    operation="_analyze_content_advanced",
                    entity_type=entity_type,
                    content_length=len(title) + len(description),
                )
            )
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error("Unexpected error in content analysis: %s: %s", type(e).__name__, e)
            return Result.fail(
                Errors.system(
                    message="Advanced content analysis failed",
                    exception=e,
                    operation="_analyze_content_advanced",
                    entity_type=entity_type,
                    content_length=len(title) + len(description),
                )
            )

    def _detect_keyword_patterns(self, content: str) -> list[KuPattern]:
        """Detect knowledge patterns using enhanced keyword matching."""
        patterns = []

        for knowledge_uid, keywords_dict in self.knowledge_keywords.items():
            domain = _table_domain(knowledge_uid)
            evidence = []
            confidence_factors = []

            for keyword in keywords_dict.get("direct", []):
                if keyword in content:
                    evidence.append(f"Direct keyword: '{keyword}'")
                    confidence_factors.append(InferenceConfidence.DIRECT_KEYWORD)

            for keyword in keywords_dict.get("contextual", []):
                if keyword in content:
                    evidence.append(f"Contextual keyword: '{keyword}'")
                    confidence_factors.append(InferenceConfidence.CONTEXTUAL_KEYWORD)

            for keyword in keywords_dict.get("advanced", []):
                if keyword in content:
                    evidence.append(f"Advanced keyword: '{keyword}'")
                    confidence_factors.append(InferenceConfidence.ADVANCED_KEYWORD)

            if confidence_factors:
                base_confidence = max(confidence_factors)
                if len(confidence_factors) > 1:
                    base_confidence = min(
                        InferenceConfidence.MULTI_MATCH_CAP,
                        base_confidence
                        + InferenceConfidence.MULTI_MATCH_BOOST_PER * (len(confidence_factors) - 1),
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

    def _detect_phrase_patterns(self, content: str) -> list[KuPattern]:
        """Detect knowledge patterns using regex phrase matching."""
        patterns = []

        for knowledge_uid, phrase_patterns in self.knowledge_phrases.items():
            domain = _table_domain(knowledge_uid)
            evidence = []

            for pattern in phrase_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    evidence.extend([f"Phrase pattern: '{match}'" for match in matches])

            if evidence:
                confidence = min(
                    InferenceConfidence.PHRASE_CAP,
                    InferenceConfidence.PHRASE_BASE
                    + InferenceConfidence.PHRASE_PER_EVIDENCE * len(evidence),
                )

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

    def _detect_contextual_patterns(self, title: str, description: str) -> list[KuPattern]:
        """Detect knowledge patterns using contextual analysis."""
        patterns = []
        combined_text = f"{title} {description}".lower()

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

    def _detect_complexity_patterns(self, content: str) -> list[KuPattern]:
        """Detect knowledge patterns based on content complexity."""
        patterns = []

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
        """Combine same-UID patterns; pass singletons through unchanged.

        A knowledge UID detected by several algorithms becomes one ``merged``
        pattern (max confidence + MERGE_BOOST, capped; evidence deduped) whose
        ``contributing_types`` records the original detector types. A UID
        detected once keeps its original pattern — type, confidence, and
        evidence intact — so per-type reliability scoring and the
        ``advanced_features`` metadata counters see real detector types.
        """
        pattern_map: defaultdict[str, list[KuPattern]] = defaultdict(list)
        for pattern in patterns:
            pattern_map[pattern.knowledge_uid].append(pattern)

        merged = []
        for knowledge_uid, group in pattern_map.items():
            if len(group) == 1:
                merged.append(group[0])
                continue

            max_confidence = min(
                InferenceConfidence.MERGE_CAP,
                max(p.confidence for p in group) + InferenceConfidence.MERGE_BOOST,
            )
            evidence: list[str] = []
            for pattern in group:
                evidence.extend(e for e in pattern.evidence if e not in evidence)

            merged.append(
                KuPattern(
                    pattern_type="merged",
                    knowledge_uid=knowledge_uid,
                    confidence=max_confidence,
                    evidence=evidence,
                    domain=group[0].domain,
                    contributing_types=sorted({p.pattern_type for p in group}),
                )
            )

        return merged

    def _discover_cross_domain_relationships(
        self, detected_patterns: list[KuPattern]
    ) -> Result[list[CrossDomainRelationship]]:
        """Discover relationships between knowledge across different domains."""
        try:
            relationships = []

            for (from_uid, to_uid), relationship_data in self.cross_domain_mappings.items():
                from_pattern = next(
                    (p for p in detected_patterns if p.knowledge_uid == from_uid), None
                )
                to_pattern = next((p for p in detected_patterns if p.knowledge_uid == to_uid), None)

                if from_pattern and to_pattern:
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

            relationships.sort(key=attrgetter("strength"), reverse=True)

            self.logger.debug("Discovered %d cross-domain relationships", len(relationships))

            return Result.ok(relationships)

        except DATA_CONVERSION_EXCEPTIONS as e:
            return Result.fail(
                Errors.system(
                    message="Cross-domain relationship discovery failed",
                    exception=e,
                    operation="_discover_cross_domain_relationships",
                    pattern_count=len(detected_patterns),
                )
            )
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(
                "Unexpected error in cross-domain discovery: %s: %s", type(e).__name__, e
            )
            return Result.fail(
                Errors.system(
                    message="Cross-domain relationship discovery failed",
                    exception=e,
                    operation="_discover_cross_domain_relationships",
                    pattern_count=len(detected_patterns),
                )
            )

    def _calculate_advanced_confidence_score(
        self, pattern: KuPattern, context: dict[str, Any]
    ) -> float:
        """Calculate advanced confidence score using multiple factors."""
        base_confidence = pattern.confidence

        evidence_quality = len(pattern.evidence) * InferenceConfidence.EVIDENCE_QUALITY_PER_ITEM
        evidence_quality = min(InferenceConfidence.EVIDENCE_QUALITY_CAP, evidence_quality)

        type_reliability = InferenceConfidence.PATTERN_RELIABILITY.get(pattern.pattern_type, 0.0)

        domain_boost = 0.0
        if "user_expertise" in context:
            user_domains = context["user_expertise"].get("domains", [])
            if pattern.domain in user_domains:
                domain_boost = InferenceConfidence.DOMAIN_EXPERTISE_BOOST

        final_confidence = base_confidence + evidence_quality + type_reliability + domain_boost
        return max(0.0, min(1.0, final_confidence))

    # ========================================================================
    # BASIC INFERENCE PATH (fallback when advanced engine disabled)
    # ========================================================================

    def _basic_inference_fallback(
        self, task: Task | TaskDTO, rels: TaskRelationships | None = None
    ) -> TaskInferenceResult:
        """Basic inference fallback when advanced engine is disabled.

        Computes the same three enrichment fields the advanced engine produces
        and returns them as a TaskInferenceResult — does not touch the input.
        """
        # GRAPH-NATIVE: Use empty relationships if not provided (for new tasks)
        task_rels = rels or TaskRelationships.empty()

        inferred_uids = self._infer_knowledge_uids_from_content(task.title, task.description or "")

        confidence_scores = self._calculate_connection_confidence_scores(task_rels, inferred_uids)

        patterns = self._detect_knowledge_patterns(task_rels)

        opportunity_count = self._count_learning_opportunities(task_rels)

        metadata: dict[str, Any] = {
            "inference_version": "1.0_basic",
            "inference_timestamp": task.updated_at.isoformat() if task.updated_at else None,
            "algorithm_confidence": max(confidence_scores.values()) if confidence_scores else 0.0,
            "patterns_detected": patterns,
        }

        return TaskInferenceResult(
            knowledge_confidence_scores=confidence_scores or None,
            knowledge_inference_metadata=metadata,
            learning_opportunities_count=opportunity_count,
        )

    def _infer_from_content(self, title: str, description: str) -> list[KnowledgeConnection]:
        """Infer knowledge connections from text content."""
        connections = []
        content = f"{title} {description}".lower()

        # Simple keyword-based inference (can be enhanced with NLP)
        knowledge_keywords = {
            "python": "ku.programming.python",
            "database": "ku.data.database",
            "api": "ku.programming.api",
            "algorithm": "ku.computer-science.algorithms",
            "design": "ku.design.principles",
            "test": "ku.programming.testing",
            "deploy": "ku.devops.deployment",
            "security": "ku.security.fundamentals",
        }

        for keyword, ku_uid in knowledge_keywords.items():
            if keyword in content:
                connections.append(
                    KnowledgeConnection(
                        knowledge_uid=ku_uid,
                        connection_type="applies",
                        confidence=ConfidenceLevel.LOW,  # Medium confidence for keyword matches
                        source="inferred",
                        metadata={"evidence": f"Inferred from keyword: '{keyword}' in content"},
                    )
                )

        return connections

    def _infer_knowledge_uids_from_content(self, title: str, description: str) -> list[str]:
        """Extract potential knowledge UIDs from task content."""
        content = f"{title} {description}".lower()
        inferred_uids = []

        if "python" in content:
            inferred_uids.append("ku.programming.python")
        if "database" in content or "sql" in content:
            inferred_uids.append("ku.data.database")
        if "api" in content or "rest" in content:
            inferred_uids.append("ku.programming.api")
        if "test" in content:
            inferred_uids.append("ku.programming.testing")

        return inferred_uids

    def _calculate_connection_confidence_scores(
        self, rels: TaskRelationships, inferred_uids: list[str]
    ) -> dict[str, float]:
        """
        Calculate confidence scores for knowledge connections.

        GRAPH-NATIVE: Uses TaskRelationships for explicit connections.
        """
        scores = {}

        # Explicit connections get high confidence (from graph relationships)
        for uid in rels.applies_knowledge_uids:
            scores[uid] = 0.95

        for uid in rels.prerequisite_knowledge_uids:
            scores[uid] = 0.90

        # Inferred connections get medium confidence
        for uid in inferred_uids:
            if uid not in scores:  # Don't override explicit connections
                scores[uid] = 0.60

        return scores

    def _detect_knowledge_patterns(self, rels: TaskRelationships) -> list[str]:
        """
        Detect knowledge patterns in the task.

        GRAPH-NATIVE: Uses TaskRelationships for knowledge connections.
        """
        patterns = []

        # GRAPH-NATIVE: Check patterns from graph relationships
        if rels.prerequisite_knowledge_uids and rels.applies_knowledge_uids:
            patterns.append("knowledge_bridge")

        if len(rels.applies_knowledge_uids) > 2:
            patterns.append("knowledge_integration")

        return patterns

    def _count_learning_opportunities(self, rels: TaskRelationships) -> int:
        """
        Count potential learning opportunities in the task.

        GRAPH-NATIVE: Uses TaskRelationships for knowledge connections.
        """
        count = 0
        count += len(rels.applies_knowledge_uids)
        count += len(rels.prerequisite_knowledge_uids)
        return count

    # ========================================================================
    # INTROSPECTION
    # ========================================================================

    @with_error_handling("get_inference_statistics", error_type="system")
    def get_inference_statistics(self) -> Result[dict[str, Any]]:
        """Return inference engine configuration / capability snapshot.

        Validation-feedback statistics were removed per ADR-065 along with the
        dormant feedback infrastructure they reported on; if/when a real
        feedback feature is built, this method will surface its stats.
        """
        stats = {
            "engine_type": "advanced" if self.config.enable_advanced_engine else "basic",
            "config": {
                "advanced_features_enabled": self.config.enable_advanced_engine,
                "cross_domain_mapping": self.config.enable_cross_domain_mapping,
            },
        }
        return Result.ok(stats)

    @with_error_handling("analyze_inference_confidence", error_type="system")
    def analyze_inference_confidence(
        self, content: str, entity_type: str = "task"
    ) -> Result[dict[str, Any]]:
        """
        Analyze confidence factors for a given content without applying inference.

        Args:
            content: Content to analyze
            entity_type: Type of entity

        Returns:
            Result containing confidence analysis
        """
        analysis: dict[str, Any] = {
            "content_length": len(content),
            "word_count": len(content.split()),
            "estimated_inferences": 0,
            "confidence_factors": {},
            "engine_type": "advanced" if self.config.enable_advanced_engine else "basic",
        }

        if self.config.enable_advanced_engine:
            result = self._analyze_content_advanced(content, "", entity_type)
            if result.is_ok:
                patterns = result.value
                analysis["estimated_inferences"] = len(patterns)

                for pattern in patterns:
                    analysis["confidence_factors"][pattern.knowledge_uid] = {
                        "confidence": pattern.confidence,
                        "pattern_type": pattern.pattern_type,
                        "evidence_count": len(pattern.evidence),
                        "domain": pattern.domain,
                    }
        else:
            basic_keywords = ["python", "javascript", "database", "api", "docker", "kubernetes"]
            found_keywords = [kw for kw in basic_keywords if kw.lower() in content.lower()]
            analysis["estimated_inferences"] = len(found_keywords)
            analysis["confidence_factors"] = {
                f"ku.{kw}": {"confidence": 0.6} for kw in found_keywords
            }

        return Result.ok(analysis)
