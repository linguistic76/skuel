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

from dataclasses import dataclass
from typing import Any

from core.constants import ConfidenceLevel
from core.models.inference import KnowledgeConnection
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.models.task.task_inference_result import TaskInferenceResult

# Import the advanced inference engine
from core.services.advanced_inference_engine import AdvancedInferenceEngine
from core.services.tasks.task_relationships import TaskRelationships
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result


@dataclass
class InferenceConfig:
    """Configuration for knowledge inference algorithms."""

    confidence_threshold: float = 0.5
    max_inferred_connections: int = 10
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

        # Initialize advanced inference engine
        self.advanced_engine: AdvancedInferenceEngine | None
        if self.config.enable_advanced_engine:
            self.advanced_engine = AdvancedInferenceEngine()
            self.logger.info("Advanced knowledge inference engine enabled")
        else:
            self.advanced_engine = None
            self.logger.info("Using basic knowledge inference algorithms")

    @with_error_handling("enhance_task_dto_with_inference", error_type="system")
    async def enhance_task_dto_with_inference(
        self, task: Task | TaskDTO
    ) -> Result[TaskInferenceResult]:
        """Compute knowledge enrichment using advanced algorithms when enabled.

        Returns a typed ``TaskInferenceResult`` (ADR-065). Falls back to basic
        keyword inference when the advanced engine is disabled.
        """
        # Use advanced engine if available
        if self.advanced_engine and self.config.enable_advanced_engine:
            self.logger.debug("Using advanced inference engine for task: %s", task.title)
            return await self.advanced_engine.enhance_task_dto_with_advanced_inference(task)

        # Fallback to basic inference algorithms
        self.logger.debug("Using basic inference algorithms for task: %s", task.title)
        result = await self._basic_inference_fallback(task)
        return Result.ok(result)

    async def _basic_inference_fallback(
        self, task: Task | TaskDTO, rels: TaskRelationships | None = None
    ) -> TaskInferenceResult:
        """Basic inference fallback when advanced engine is disabled.

        Computes the same three enrichment fields the advanced engine produces
        and returns them as a TaskInferenceResult — does not touch the input.
        """
        # GRAPH-NATIVE: Use empty relationships if not provided (for new tasks)
        task_rels = rels or TaskRelationships.empty()

        # Infer knowledge connections from task content
        inferred_uids = await self._infer_knowledge_uids_from_content(
            task.title, task.description or ""
        )

        # Calculate confidence scores for each connection
        confidence_scores = await self._calculate_connection_confidence_scores(
            task_rels, inferred_uids
        )

        # Detect knowledge patterns
        patterns = await self._detect_knowledge_patterns(task_rels)

        # Count learning opportunities
        opportunity_count = await self._count_learning_opportunities(task_rels)

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

    async def _infer_from_content(self, title: str, description: str) -> list[KnowledgeConnection]:
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

    async def _infer_knowledge_uids_from_content(self, title: str, description: str) -> list[str]:
        """Extract potential knowledge UIDs from task content."""
        # Simplified implementation - can be enhanced with NLP/ML
        content = f"{title} {description}".lower()
        inferred_uids = []

        # Keyword-based inference
        if "python" in content:
            inferred_uids.append("ku.programming.python")
        if "database" in content or "sql" in content:
            inferred_uids.append("ku.data.database")
        if "api" in content or "rest" in content:
            inferred_uids.append("ku.programming.api")
        if "test" in content:
            inferred_uids.append("ku.programming.testing")

        return inferred_uids

    async def _calculate_connection_confidence_scores(
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

    async def _detect_knowledge_patterns(self, rels: TaskRelationships) -> list[str]:
        """
        Detect knowledge patterns in the task.

        GRAPH-NATIVE: Uses TaskRelationships for knowledge connections.
        """
        patterns = []

        # GRAPH-NATIVE: Check patterns from graph relationships
        if rels.prerequisite_knowledge_uids and rels.applies_knowledge_uids:
            patterns.append("knowledge_bridge")  # Connects existing to new knowledge

        if len(rels.applies_knowledge_uids) > 2:
            patterns.append("knowledge_integration")  # Integrates multiple knowledge areas

        # Note: knowledge_mastery_check and goal_progress_contribution are still on TaskDTO
        # These are scalar fields, not relationships, so they remain on the DTO
        # They would need to be passed separately if needed for pattern detection

        return patterns

    async def _count_learning_opportunities(self, rels: TaskRelationships) -> int:
        """
        Count potential learning opportunities in the task.

        GRAPH-NATIVE: Uses TaskRelationships for knowledge connections.
        """
        count = 0

        # Each knowledge application is an opportunity (from graph relationships)
        count += len(rels.applies_knowledge_uids)

        # Prerequisites are review opportunities (from graph relationships)
        # Note: knowledge_mastery_check is a scalar field on TaskDTO, not available here
        # Simplified to count all prerequisites as opportunities
        count += len(rels.prerequisite_knowledge_uids)

        # Note: knowledge_mastery_check would need to be passed as a parameter
        # if we need to distinguish mastery validation tasks

        return count

    # ========================================================================
    # INTROSPECTION
    # ========================================================================

    @with_error_handling("get_inference_statistics", error_type="system")
    async def get_inference_statistics(self) -> Result[dict[str, Any]]:
        """Return inference engine configuration / capability snapshot.

        Validation-feedback statistics were removed per ADR-065 along with the
        dormant feedback infrastructure they reported on; if/when a real
        feedback feature is built, this method will surface its stats.
        """
        stats = {
            "engine_type": "advanced" if self.advanced_engine else "basic",
            "config": {
                "confidence_threshold": self.config.confidence_threshold,
                "max_inferred_connections": self.config.max_inferred_connections,
                "advanced_features_enabled": self.config.enable_advanced_engine,
                "cross_domain_mapping": self.config.enable_cross_domain_mapping,
            },
        }
        return Result.ok(stats)

    @with_error_handling("analyze_inference_confidence", error_type="system")
    async def analyze_inference_confidence(
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
            "engine_type": "advanced" if self.advanced_engine else "basic",
        }

        if self.advanced_engine:
            # Use advanced engine for detailed analysis
            result = await self.advanced_engine.analyze_content_advanced(content, "", entity_type)
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
            # Basic analysis
            basic_keywords = ["python", "javascript", "database", "api", "docker", "kubernetes"]
            found_keywords = [kw for kw in basic_keywords if kw.lower() in content.lower()]
            analysis["estimated_inferences"] = len(found_keywords)
            analysis["confidence_factors"] = {
                f"ku.{kw}": {"confidence": 0.6} for kw in found_keywords
            }

        return Result.ok(analysis)
