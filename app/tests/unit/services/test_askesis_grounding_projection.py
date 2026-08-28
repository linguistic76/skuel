"""Tests for the Askesis grounding projection (ADR-082 D2).

Three contracts:
1. The projection renders exactly its curated Askesis-natural shape —
   identity, skeleton-tolerant LifePath framing, learning-journey position,
   light study-serving goals — and a skeleton context renders NOTHING
   (sections omitted, never filler).
2. The EXPLICIT field list is enforced: a recording UserContext proves the
   renderer reads nothing beyond ``ASKESIS_GROUNDING_FIELDS`` (the
   scope-creep mitigation ADR-082 names), and the list contains no
   discussion-transcript fields (ADR-073/078 privacy wall).
3. The grounding lands on BOTH answer branches: the guided system prompt
   carries it between stance and pedagogy leaf; the facet/context-aware
   ``build_llm_context`` renders it in place of the pre-ADR-082 UserContext
   dump, with workload/alert mechanics and the curriculum block untouched.
"""

from unittest.mock import MagicMock

from core.prompts import PROMPT_REGISTRY
from core.services.askesis.grounding_projection import (
    ASKESIS_GROUNDING_FIELDS,
    render_askesis_grounding,
)
from core.services.askesis.response_generator import ResponseGenerator
from core.services.user.unified_user_context import UserContext

_USER = "user_mike"


def _context(**overrides) -> UserContext:
    return UserContext(user_uid=_USER, display_name="Mike", **overrides)


def _rich_goal(uid: str, title: str) -> dict:
    return {"entity": {"uid": uid, "title": title}, "graph_context": {}}


def _rich_path(title: str, completed: int = 0, total: int = 0) -> dict:
    return {
        "path": {"title": title},
        "graph_context": {
            "steps": [{"uid": f"ps.step-{i}", "completed": i < completed} for i in range(total)]
        },
    }


class TestRenderAskesisGrounding:
    def test_skeleton_context_renders_nothing(self):
        # The elicited skeleton case: no LifePath, nothing enrolled, no
        # mastery — the block degrades to NOTHING, never to filler.
        assert render_askesis_grounding(UserContext(user_uid=_USER)) == ""

    def test_identity_line(self):
        assert render_askesis_grounding(_context()) == "You are studying with Mike."

    def test_life_path_designated_without_alignment(self):
        # Designation is real signal even before alignment is computed —
        # but no invented numbers.
        context = _context(life_path_uid="lifepath_mike")
        assert "They have designated a LifePath." in render_askesis_grounding(context)
        assert "alignment" not in render_askesis_grounding(context)

    def test_life_path_alignment_rendered_when_present(self):
        context = _context(life_path_uid="lifepath_mike", life_path_alignment_score=0.34)
        text = render_askesis_grounding(context)
        assert "current activity alignment with it: 34%." in text

    def test_enrolled_paths_with_step_progress(self):
        context = _context(
            enrolled_paths_rich=[
                _rich_path("Web Foundations", completed=3, total=12),
                _rich_path("Systems Thinking"),
            ]
        )
        text = render_askesis_grounding(context)
        assert "Enrolled learning paths: Web Foundations (3/12 steps), Systems Thinking." in text

    def test_enrolled_paths_capped_at_three(self):
        context = _context(enrolled_paths_rich=[_rich_path(f"Path {i}") for i in range(5)])
        text = render_askesis_grounding(context)
        assert "Path 2" in text
        assert "Path 3" not in text

    def test_untitled_path_is_skipped_not_rendered_blank(self):
        context = _context(enrolled_paths_rich=[{"path": {}, "graph_context": {}}])
        assert "Enrolled learning paths" not in render_askesis_grounding(context)

    def test_empty_path_renders_title_alone(self):
        # A path with no HAS_STEP edge arrives with NO step — the MEGA-QUERY
        # collects nothing for it (the all-null placeholder that once made it
        # "(0/1 steps)", Codex #786 P2, is gone at the writer). Title only.
        context = _context(
            enrolled_paths_rich=[
                {
                    "path": {"title": "Empty Skeleton"},
                    "graph_context": {
                        "steps": [],
                        "total_steps": 0,
                        "completed_steps": 0,
                        "progress_percentage": 0.0,
                    },
                }
            ]
        )
        text = render_askesis_grounding(context)
        assert "Enrolled learning paths: Empty Skeleton." in text
        assert "steps" not in text

    def test_now_studying_from_current_path_steps(self):
        context = _context(
            current_path_steps=[
                {"uid": "ps.a", "title": "Hypermedia Foundations"},
                {"uid": "ps.b", "title": "Graph Modeling"},
            ]
        )
        assert "Now studying: Hypermedia Foundations, Graph Modeling." in render_askesis_grounding(
            context
        )

    def test_knowledge_position_counts(self):
        context = _context(
            mastered_knowledge_uids={"ku1", "ku2"}, in_progress_knowledge_uids={"ku3"}
        )
        assert "Knowledge base: 2 concepts mastered, 1 in progress." in render_askesis_grounding(
            context
        )

    def test_goals_joined_from_rich_entities_by_active_lens(self):
        # active_goal_uids is the relevance lens; entities_rich supplies the
        # titles inline (rich depth — no service joins).
        context = _context(
            active_goal_uids=["g1", "g2"],
            entities_rich={"goals": [_rich_goal("g1", "Ship SKUEL"), _rich_goal("g2", "Read Tao")]},
        )
        text = render_askesis_grounding(context)
        assert "Goals they are working toward: Ship SKUEL, Read Tao." in text

    def test_completed_goal_in_rich_payload_is_not_revived(self):
        # entities_rich carries recently-touched completed entities too —
        # only the active lens decides what grounds the tutor.
        context = _context(
            active_goal_uids=["g1"],
            entities_rich={"goals": [_rich_goal("g1", "Live goal"), _rich_goal("g_done", "Done")]},
        )
        text = render_askesis_grounding(context)
        assert "Live goal" in text
        assert "Done" not in text

    def test_active_goals_without_rich_titles_render_nothing(self):
        # Standard-depth shape (UIDs, no entities_rich) degrades to no goal
        # line — never a UID dump.
        context = _context(active_goal_uids=["g1"])
        assert "Goals" not in render_askesis_grounding(context)


class _RecordingContext(UserContext):
    """UserContext that records every dataclass-field read — the field-list tripwire."""

    def __init__(self, **kwargs):
        object.__setattr__(self, "_reads", set())
        super().__init__(**kwargs)

    def __getattribute__(self, name):
        if name != "_reads" and name in UserContext.__dataclass_fields__:
            object.__getattribute__(self, "_reads").add(name)
        return object.__getattribute__(self, name)


class TestExplicitFieldList:
    def test_render_reads_only_the_declared_fields(self):
        context = _RecordingContext(
            user_uid=_USER,
            display_name="Mike",
            life_path_uid="lifepath_mike",
            life_path_alignment_score=0.5,
            enrolled_paths_rich=[_rich_path("Web Foundations", completed=1, total=4)],
            current_path_steps=[{"uid": "ps.a", "title": "Graph Modeling"}],
            mastered_knowledge_uids={"ku1"},
            in_progress_knowledge_uids={"ku2"},
            active_goal_uids=["g1"],
            entities_rich={"goals": [_rich_goal("g1", "Ship SKUEL")]},
        )
        render_askesis_grounding(context)
        reads = object.__getattribute__(context, "_reads")
        undeclared = reads - set(ASKESIS_GROUNDING_FIELDS)
        assert not undeclared, (
            f"render_askesis_grounding read UserContext fields outside the explicit "
            f"projection list: {sorted(undeclared)}. Extend ASKESIS_GROUNDING_FIELDS "
            f"deliberately (ADR-082 D2) or drop the read."
        )

    def test_declared_fields_exist_on_user_context(self):
        # A renamed UserContext field must fail here, not silently un-ground.
        missing = set(ASKESIS_GROUNDING_FIELDS) - set(UserContext.__dataclass_fields__)
        assert not missing

    def test_no_transcript_shaped_fields_in_the_list(self):
        # ADR-073/078: grounding reads structural context, never discussion data.
        for field_name in ASKESIS_GROUNDING_FIELDS:
            assert "conversation" not in field_name
            assert "transcript" not in field_name
            assert "session" not in field_name


# ============================================================================
# Injection — both answer branches (ADR-082 D2)
# ============================================================================


def _stance() -> str:
    return PROMPT_REGISTRY.render("askesis_stance")


def _guided_generator() -> ResponseGenerator:
    generator = ResponseGenerator()
    generator._build_socratic_prompt = MagicMock(  # type: ignore[method-assign]
        return_value="PEDAGOGY LEAF"
    )
    return generator


def _guidance() -> MagicMock:
    from core.models.enums import GuidanceMode

    guidance = MagicMock()
    guidance.mode = GuidanceMode.SOCRATIC
    return guidance


class TestGuidedBranchInjection:
    def test_grounding_sits_between_stance_and_pedagogy_leaf(self):
        context = _context(current_path_steps=[{"uid": "ps.a", "title": "Graph Modeling"}])

        prompt = _guided_generator().build_guided_system_prompt(_guidance(), MagicMock(), context)

        assert prompt.startswith(_stance())
        assert prompt.endswith("PEDAGOGY LEAF")
        assert (
            prompt.index(_stance())
            < prompt.index("You are studying with Mike.")
            < prompt.index("Now studying: Graph Modeling.")
            < prompt.index("PEDAGOGY LEAF")
        )

    def test_skeleton_context_leaves_the_composition_unchanged(self):
        # Skeleton grounding renders "" — no empty block between stance and leaf.
        prompt = _guided_generator().build_guided_system_prompt(
            _guidance(), MagicMock(), UserContext(user_uid=_USER)
        )

        assert prompt == _stance() + "\n\n" + "PEDAGOGY LEAF"


class TestFacetBranchInjection:
    def test_grounding_replaces_the_user_sections(self):
        context = _context(
            active_goal_uids=["g1"],
            entities_rich={"goals": [_rich_goal("g1", "Ship SKUEL")]},
            current_workload_score=0.4,
        )

        text = ResponseGenerator().build_llm_context(context)

        # The projection heads the block...
        assert text.startswith("You are studying with Mike.")
        assert "Goals they are working toward: Ship SKUEL." in text
        # ...workload mechanics stay as they were...
        assert "--- Workload & Capacity ---" in text
        assert "Current Workload: 40%" in text
        # ...and the pre-ADR-082 intent-selected dump sections are gone.
        for old_header in ("--- Tasks ---", "--- Goals ---", "--- Knowledge & Learning ---"):
            assert old_header not in text

    def test_curriculum_block_kept_when_bundle_present(self):
        bundle = MagicMock()
        bundle.curriculum_context_text = "CURRICULUM BODY"

        text = ResponseGenerator().build_llm_context(_context(), ps_bundle=bundle)

        assert "--- Curriculum Context ---" in text
        assert text.rstrip().endswith("CURRICULUM BODY")

    def test_alerts_mechanics_kept(self):
        context = _context(is_blocked=True, is_overwhelmed=True)

        text = ResponseGenerator().build_llm_context(context)

        assert "--- Alerts ---" in text
        assert "Blocked by prerequisites" in text
        assert "Workload overwhelming" in text

    def test_skeleton_context_still_renders_workload_mechanics(self):
        text = ResponseGenerator().build_llm_context(UserContext(user_uid=_USER))

        assert "You are studying with" not in text
        assert "--- Workload & Capacity ---" in text
