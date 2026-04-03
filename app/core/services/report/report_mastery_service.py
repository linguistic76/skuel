"""
Report Mastery Service
======================

Explicitly unifies mastery propagation for Exercise Reports. Calculates the
proper mastery score via the MasteryImpact logic and propagates it back to the ZPD
boundaries by:
1. Updating the Submission's `score` tracking (for compound evidence)
2. Creating the `MASTERED` relationships for the linked syllabus elements.

See: /docs/architecture/LEARNING_LOOP_ARCHITECTURE.md
"""

from typing import TYPE_CHECKING, Any

from core.models.enums.learning_enums import MasteryImpact
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.domain_backends import SubmissionsBackend
    from core.services.ps.ps_mastery_service import PsMasteryService

logger = get_logger("skuel.services.report.mastery")


class ReportMasteryService:
    """Explicit closed-loop propagation for exercise submissions."""

    def __init__(
        self,
        submissions_backend: "SubmissionsBackend",
        ku_interaction_service: "PsMasteryService | None",
    ) -> None:
        self.submissions_backend = submissions_backend
        self.ku_interaction_service = ku_interaction_service

    async def propagate_mastery(
        self,
        submission_uid: str,
        user_uid: UserUID,
        linked_ku_uids: list[str],
        mastery_impact: MasteryImpact,
        method: str,
    ) -> Result[int]:
        """
        Calculates and explicitly propagates the mastery assessment back to ZPD.

        Args:
            submission_uid: The submission to apply the score to explicitly.
            user_uid: The student who submitted the exercise.
            linked_ku_uids: The KUs related to the exercise.
            mastery_impact: The MasteryImpact setting from the exercise.
            method: Either "activity_report" (AI) or "ku_approval" (Teacher).

        Returns:
            Count of successfully mastered KUs.
        """
        if not self.ku_interaction_service:
            logger.warning("No KU interaction service available to propagate mastery.")
            return Result.ok(0)

        if not linked_ku_uids:
            return Result.ok(0)

        # 1. Calculate explicit score
        if method == "activity_report":
            score = mastery_impact.get_ai_score()
        else:
            score = mastery_impact.get_teacher_score()

        # 2. Update Submission `score` explicitly so ZPD queries track correct value
        update_result = await self.submissions_backend.update_submission_score(
            submission_uid, score
        )
        if update_result.is_error:
            logger.warning(
                f"Failed to update submission score for {submission_uid}: {update_result.error}"
            )

        # 3. Propagate explicit score to ZPD via MASTERED edges
        mastered_count = 0
        for ku_uid in linked_ku_uids:
            mastery_result = await self.ku_interaction_service.mark_mastered(
                user_uid=user_uid,
                ku_uid=ku_uid,
                mastery_score=score,
                method=method,
            )
            if mastery_result.is_ok:
                mastered_count += 1
            else:
                logger.warning(
                    f"Failed to update mastery for KU {ku_uid} from {method}: {mastery_result.error}"
                )

        if mastered_count > 0:
            logger.info(
                f"Explicitly propagated mastery ({score}) for {mastered_count} "
                f"KUs from {method} on submission {submission_uid}"
            )

        return Result.ok(mastered_count)
