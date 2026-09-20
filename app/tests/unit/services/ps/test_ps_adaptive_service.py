"""Regression tests for PsAdaptiveService's SEL-level determination.

The old ``_determine_user_level`` counted masteries whose uid string started
with ``ku.{sel_category.value}``. Vault namespaces (``yoga``/``mind``/``sel``/…)
never equal SELCategory values and generated uids carry no namespace, so every
learner scored 0 in every category and was permanently BEGINNER. The fix counts
by the mastered node's ``sel_category`` FIELD (carried on Mastery from the
backend query) — uid strings are opaque (ADR-013 never-sniff).

These tests pin the fix: authored-uid masteries and generated-uid masteries
BOTH count toward the SEL category level (the old code counted neither).
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import LearningLevel, SELCategory
from core.models.pathways.mastery import LearningVelocity, Mastery, MasteryLevel
from core.models.user.user_intelligence import UserLearningIntelligence
from core.services.ps.ps_adaptive_service import PsAdaptiveService
from core.utils.result_simplified import Result


def make_mastery(knowledge_uid: str, sel_category: str | None) -> Mastery:
    """Minimal Mastery for level-determination fixtures."""
    now = datetime.now()
    return Mastery(
        uid=f"mastery_user_test_{knowledge_uid}",
        user_uid="user_test",
        knowledge_uid=knowledge_uid,
        sel_category=sel_category,
        mastery_level=MasteryLevel.PROFICIENT,
        confidence_score=0.8,
        mastery_score=0.7,
        learning_velocity=LearningVelocity.MODERATE,
        time_to_mastery_hours=None,
        review_frequency_days=None,
        mastery_evidence=[],
        last_reviewed=now,
        last_practiced=None,
        learning_path_context=None,
        difficulty_experienced=None,
        preferred_learning_method=None,
        created_at=now,
        updated_at=now,
    )


def make_intelligence(masteries: dict[str, Mastery]) -> UserLearningIntelligence:
    return UserLearningIntelligence(user_uid="user_test", current_masteries=masteries)


@pytest.fixture
def service() -> PsAdaptiveService:
    return PsAdaptiveService(backend=Mock(), user_service=Mock())


class TestDetermineUserLevel:
    def test_authored_and_generated_uids_both_count(self, service: PsAdaptiveService) -> None:
        """The regression the fix exists for: category comes from the FIELD.

        None of these uids starts with ``ku.self_awareness`` — under the old
        uid-prefix sniff every one was invisible and the level was BEGINNER.
        """
        masteries = {
            m.knowledge_uid: m
            for m in [
                # Authored uids — vault namespaces never equal SELCategory values.
                make_mastery("ku.mind.attention", SELCategory.SELF_AWARENESS.value),
                make_mastery("ku.yoga.breath", SELCategory.SELF_AWARENESS.value),
                make_mastery("ku.sel.body-scan", SELCategory.SELF_AWARENESS.value),
                # Generated uids — no namespace at all.
                make_mastery("ku_labeling_a1b2c3d4", SELCategory.SELF_AWARENESS.value),
                make_mastery("ku_noticing_e5f6a7b8", SELCategory.SELF_AWARENESS.value),
                # Other category / no category — must NOT count.
                make_mastery("ku.sel.empathy", SELCategory.SOCIAL_AWARENESS.value),
                make_mastery("ku.mind.uncategorized", None),
            ]
        }

        level = service._determine_user_level(
            make_intelligence(masteries), SELCategory.SELF_AWARENESS
        )

        # 5 field-matched masteries → INTERMEDIATE (>= 5); the old sniff
        # counted 0 and returned BEGINNER.
        assert level == LearningLevel.INTERMEDIATE

    def test_no_matching_category_is_beginner(self, service: PsAdaptiveService) -> None:
        masteries = {
            m.knowledge_uid: m
            for m in [
                make_mastery("ku.sel.empathy", SELCategory.SOCIAL_AWARENESS.value),
                make_mastery("ku.mind.uncategorized", None),
            ]
        }

        level = service._determine_user_level(
            make_intelligence(masteries), SELCategory.SELF_AWARENESS
        )

        assert level == LearningLevel.BEGINNER

    def test_twelve_matches_is_advanced(self, service: PsAdaptiveService) -> None:
        masteries = {
            m.knowledge_uid: m
            for m in [
                make_mastery(f"ku_concept-{i}_{i:08d}", SELCategory.SELF_MANAGEMENT.value)
                for i in range(12)
            ]
        }

        level = service._determine_user_level(
            make_intelligence(masteries), SELCategory.SELF_MANAGEMENT
        )

        assert level == LearningLevel.ADVANCED


class TestQueryUserMasteriesCarriesSelCategory:
    @pytest.mark.asyncio
    async def test_sel_category_flows_from_backend_record_to_mastery(self) -> None:
        """The backend row's ``sel_category`` (the mastered node's field) lands
        on the Mastery model — the data path _determine_user_level counts on."""
        backend = Mock()
        backend.query_user_masteries = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "ku_uid": "ku.mind.attention",
                        "sel_category": SELCategory.SELF_AWARENESS.value,
                        "mastery_level": "proficient",
                        "learning_velocity": "moderate",
                    },
                    {
                        "ku_uid": "ku_labeling_a1b2c3d4",
                        "sel_category": None,
                        "mastery_level": "introduced",
                        "learning_velocity": "moderate",
                    },
                ]
            )
        )
        service = PsAdaptiveService(backend=backend, user_service=Mock())

        masteries = await service._query_user_masteries("user_test")

        assert masteries["ku.mind.attention"].sel_category == SELCategory.SELF_AWARENESS.value
        assert masteries["ku_labeling_a1b2c3d4"].sel_category is None


class TestSelJourneyCompletion:
    @pytest.mark.asyncio
    async def test_journey_completion_is_derived_from_mastered_over_total(self) -> None:
        """Two of four Self-Awareness steps mastered reads 50% for the category, 10%
        overall (one of five categories), two steps available (the two unmastered ones
        pass the same readiness predicate the curriculum route applies), and the level
        the recommendation filter would use; the recommendation moves past the category.
        The counts are the ONLY input — nothing sets a percentage the service could forget."""
        from core.models.pathways.path_step import PathStep

        steps = [PathStep(uid=f"ps.sel.s{i}", title=f"S{i}") for i in range(4)]

        async def find_by(**kwargs: str) -> Result[list[PathStep]]:
            if kwargs["sel_category"] == SELCategory.SELF_AWARENESS.value:
                return Result.ok(steps)
            return Result.ok([])

        backend = Mock()
        backend.find_by = find_by
        backend.get_related_uids = AsyncMock(return_value=Result.ok([]))  # no prerequisites
        service = PsAdaptiveService(backend=backend, user_service=Mock())
        intel = make_intelligence(
            {
                "ps.sel.s0": make_mastery("ps.sel.s0", SELCategory.SELF_AWARENESS.value),
                "ps.sel.s1": make_mastery("ps.sel.s1", SELCategory.SELF_AWARENESS.value),
            }
        )
        service._load_user_intelligence = AsyncMock(return_value=intel)  # type: ignore[method-assign]

        result = await service.get_sel_journey("user_test")

        journey = result.value
        awareness = journey.category_progress[SELCategory.SELF_AWARENESS]
        assert (awareness.steps_mastered, awareness.total_steps) == (2, 4)
        assert awareness.steps_available == 2
        assert awareness.completion_percentage == 50.0
        assert awareness.current_level == service._determine_user_level(
            intel, SELCategory.SELF_AWARENESS
        )
        assert journey.overall_completion == pytest.approx(10.0)
        assert journey.get_next_recommended_category() == SELCategory.SELF_MANAGEMENT

    def test_derived_fields_reach_the_json_boundary_and_refuse_a_constructor_value(self) -> None:
        """The JSON route serializes dataclass FIELDS, so the derived pair must be fields —
        and derived, so no constructor can hand them a value the counts disagree with."""
        from pydantic_core import to_jsonable_python

        from core.models.pathways.learning_progress import CurriculumProgress

        progress = CurriculumProgress(
            user_uid="user_test",
            sel_category=SELCategory.SELF_AWARENESS,
            steps_mastered=12,
            total_steps=16,
        )
        payload = to_jsonable_python(progress)
        assert payload["completion_percentage"] == 75.0
        assert payload["current_level"] == LearningLevel.ADVANCED.value
        with pytest.raises(TypeError):
            CurriculumProgress(  # type: ignore[call-arg]
                user_uid="user_test",
                sel_category=SELCategory.SELF_AWARENESS,
                completion_percentage=1.0,
            )
