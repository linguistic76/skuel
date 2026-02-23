"""
Knowledge Inference Service
==========================

**UTILITY SERVICE** - Injected dependency, not a standalone service.
This service is used BY TasksService for automatic knowledge tagging, not a duplicate.

Automatic knowledge inference algorithms for enhanced task models.
Provides algorithms to infer knowledge connections from task content,
detect learning opportunities, and calculate confidence scores.

Architecture:
- Lives at `/core/services/` level (not in `/ku/` directory)
- Injected into TasksService for automatic knowledge inference
- Specialized utility for pattern-based knowledge detection
- See `/core/services/ku/README.md` for architecture overview
"""

from dataclasses import dataclass
from typing import Any

from core.constants import ConfidenceLevel
from core.models.ku.ku_inference import KnowledgeConnection
from core.models.ku.task_dto import TaskDTO

# Import the advanced inference engine
from core.services.advanced_inference_engine import AdvancedInferenceEngine
from core.services.tasks.task_relationships import TaskRelationships
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result


@dataclass
class InferenceConfig:
    """Configuration for knowledge inference algorithms (Phase 2.4 Enhanced)."""

    confidence_threshold: float = 0.5
    max_inferred_connections: int = 10
    enable_pattern_detection: bool = True
    enable_opportunity_discovery: bool = True
    enable_insight_generation: bool = True
    # Phase 2.4 Advanced features
    enable_advanced_engine: bool = True
    enable_cross_domain_mapping: bool = True
    enable_validation_feedback: bool = True
    advanced_confidence_scoring: bool = True


class EntityInferenceService:
    """
    Service for automatic knowledge inference and enhancement.

    Provides algorithms to:
    - Infer knowledge connections from task content
    - Detect learning opportunities
    - Generate knowledge insights
    - Calculate confidence scores


    Source Tag: "ku_inference_service_explicit"
    - Format: "ku_inference_service_explicit" for user-created relationships
    - Format: "ku_inference_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from ku_inference metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(self, config: InferenceConfig | None = None) -> None:
        self.config = config or InferenceConfig()
        self.logger = get_logger("skuel.inference.service")

        # Initialize advanced inference engine (Phase 2.4)
        if self.config.enable_advanced_engine:
            self.advanced_engine = AdvancedInferenceEngine()
            self.logger.info("Advanced knowledge inference engine enabled")
        else:
            self.advanced_engine = None
            self.logger.info("Using basic knowledge inference algorithms")

    async def enhance_task_with_knowledge_inference(self, task_dto: TaskDTO) -> Result[TaskDTO]:
        """
        Enhance a TaskDTO with automatic knowledge inference.

        Args:
            task_dto: The TaskDTO to enhance with inference

        Returns:
            Result containing enhanced TaskDTO with inferred knowledge data
        """
        # Apply knowledge inference to the DTO - already returns Result[TaskDTO]
        return await self.enhance_task_dto_with_inference(task_dto)

    @with_error_handling("enhance_task_dto_with_inference", error_type="system")
    async def enhance_task_dto_with_inference(self, task_dto: TaskDTO) -> Result[TaskDTO]:
        """
        Enhance a TaskDTO with inferred knowledge data using advanced algorithms (Phase 2.4).

        Args:
            task_dto: The TaskDTO to enhance

        Returns:
            Result containing the enhanced TaskDTO with sophisticated inference
        """
        # Use advanced engine if available (Phase 2.4)
        if self.advanced_engine and self.config.enable_advanced_engine:
            self.logger.debug("Using advanced inference engine for task: %s", task_dto.title)
            return await self.advanced_engine.enhance_task_dto_with_advanced_inference(task_dto)

        # Fallback to basic inference algorithms
        self.logger.debug("Using basic inference algorithms for task: %s", task_dto.title)
        enhanced = await self._basic_inference_fallback(task_dto)
        return Result.ok(enhanced)

    async def _basic_inference_fallback(
        self, task_dto: TaskDTO, rels: TaskRelationships | None = None
    ) -> TaskDTO:
        """
        Basic inference fallback when advanced engine is disabled.

        Args:
            task_dto: The TaskDTO to enhance
            rels: Task relationships from graph (optional for new tasks)

        Returns:
            The enhanced TaskDTO using basic algorithms
        """
        # GRAPH-NATIVE: Use empty relationships if not provided (for new tasks)
        task_rels = rels or TaskRelationships.empty()

        # Infer knowledge connections from task content
        inferred_uids = await self._infer_knowledge_uids_from_content(
            task_dto.title, task_dto.description or ""
        )

        # Calculate confidence scores for each connection
        confidence_scores = await self._calculate_connection_confidence_scores(
            task_rels, inferred_uids
        )

        # Detect knowledge patterns
        patterns = await self._detect_knowledge_patterns(task_rels)

        # Count learning opportunities
        opportunity_count = await self._count_learning_opportunities(task_rels)

        # Update the DTO with inferred data
        task_dto.primary_knowledge_uids = list(set(task_dto.primary_knowledge_uids + inferred_uids))  # type: ignore[attr-defined]
        task_dto.knowledge_confidence_scores = confidence_scores
        task_dto.knowledge_inference_metadata = task_dto.knowledge_inference_metadata or {}
        task_dto.knowledge_inference_metadata["patterns_detected"] = patterns
        task_dto.learning_opportunities_count = opportunity_count
        task_dto.knowledge_inference_metadata = {
            "inference_version": "1.0_basic",
            "inference_timestamp": task_dto.updated_at.isoformat(),
            "algorithm_confidence": max(confidence_scores.values()) if confidence_scores else 0.0,
        }

        return task_dto

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
    # VALIDATION FEEDBACK CAPABILITIES (Phase 2.4)
    # ========================================================================

    def add_validation_feedback(
        self,
        knowledge_uid: str,
        was_correct: bool,
        confidence_adjustment: float = 0.0,
        _context: dict[str, Any] | None = None,
    ):
        """
        Add validation feedback for knowledge inference accuracy.

        Args:
            knowledge_uid: The knowledge UID that was validated,
            was_correct: Whether the inference was correct,
            confidence_adjustment: Optional adjustment to confidence (-1.0 to 1.0),
            context: Optional context information for learning
        """
        if self.advanced_engine and self.config.enable_validation_feedback:
            self.advanced_engine.add_validation_feedback(
                knowledge_uid, was_correct, confidence_adjustment
            )
            self.logger.info(
                "Added validation feedback for %s: correct=%s (advanced engine)",
                knowledge_uid,
                was_correct,
            )
        else:
            # Basic logging for non-advanced mode
            self.logger.info(
                "Validation feedback for %s: correct=%s (basic mode - not persisted)",
                knowledge_uid,
                was_correct,
            )

    @with_error_handling("validate_inference_batch", error_type="system")
    async def validate_inference_batch(
        self, validation_data: list[dict[str, Any]]
    ) -> Result[dict[str, Any]]:
        """
        Process a batch of validation feedback for multiple inferences.

        Args:
            validation_data: List of validation entries with keys:
                - knowledge_uid: str
                - was_correct: bool
                - confidence_adjustment: float (optional)
                - context: dict (optional)

        Returns:
            Result containing validation summary
        """
        # Type-safe summary with explicit types
        summary: dict[str, Any] = {
            "total_validations": len(validation_data),
            "correct_inferences": 0,
            "incorrect_inferences": 0,
            "knowledge_uids_validated": set(),
            "avg_confidence_adjustment": 0.0,
        }

        confidence_adjustments: list[float] = []

        for entry in validation_data:
            knowledge_uid = entry.get("knowledge_uid")
            was_correct = entry.get("was_correct", False)
            confidence_adjustment = entry.get("confidence_adjustment", 0.0)
            context = entry.get("context", {})

            if not knowledge_uid:
                continue

            # Add individual feedback
            self.add_validation_feedback(knowledge_uid, was_correct, confidence_adjustment, context)

            # Update summary (type-safe with cast)
            if was_correct:
                summary["correct_inferences"] = int(summary["correct_inferences"]) + 1
            else:
                summary["incorrect_inferences"] = int(summary["incorrect_inferences"]) + 1

            summary["knowledge_uids_validated"].add(knowledge_uid)  # type: ignore[union-attr]
            confidence_adjustments.append(confidence_adjustment)

        # Calculate averages
        if confidence_adjustments:
            summary["avg_confidence_adjustment"] = sum(confidence_adjustments) / len(
                confidence_adjustments
            )

        # Calculate accuracy rate (type-safe)
        total = int(summary["total_validations"])
        correct = int(summary["correct_inferences"])
        summary["accuracy_rate"] = (correct / total) if total > 0 else 0.0
        summary["knowledge_uids_validated"] = list(summary["knowledge_uids_validated"])

        self.logger.info(
            "Processed validation batch: %d total, %.2f accuracy, %d unique knowledge UIDs",
            summary["total_validations"],
            summary["accuracy_rate"],
            len(summary["knowledge_uids_validated"]),
        )

        return Result.ok(summary)

    @with_error_handling("get_inference_statistics", error_type="system")
    async def get_inference_statistics(self) -> Result[dict[str, Any]]:
        """
        Get inference engine statistics and performance metrics.

        Returns:
            Result containing inference statistics
        """
        stats = {
            "engine_type": "advanced" if self.advanced_engine else "basic",
            "config": {
                "confidence_threshold": self.config.confidence_threshold,
                "max_inferred_connections": self.config.max_inferred_connections,
                "advanced_features_enabled": self.config.enable_advanced_engine,
                "cross_domain_mapping": self.config.enable_cross_domain_mapping,
                "validation_feedback": self.config.enable_validation_feedback,
            },
        }

        if self.advanced_engine:
            # Get advanced engine statistics
            feedback_data = self.advanced_engine._validation_feedback
            validation_feedback: dict[str, int | float | list[str]] = {
                "total_knowledge_uids_with_feedback": len(feedback_data),
                "total_feedback_entries": sum(len(entries) for entries in feedback_data.values()),
                "knowledge_uids_tracked": list(feedback_data.keys())[:10],  # First 10 for brevity
            }

            # Calculate accuracy if feedback exists
            if feedback_data:
                all_feedback = []
                for entries in feedback_data.values():
                    all_feedback.extend(entries)

                if all_feedback:
                    avg_feedback = sum(all_feedback) / len(all_feedback)
                    validation_feedback["average_accuracy"] = avg_feedback

            stats["validation_feedback"] = validation_feedback

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
