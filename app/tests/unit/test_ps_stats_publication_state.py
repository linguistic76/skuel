"""
Unit Tests — the PathStep list stats count the authoring gate
=============================================================

``PsService.get_filtered_context`` reports published / draft counts over the full set.
A PathStep's publication lives in ``publication_state`` (``PublicationState``), the
authoring gate; ``status`` is lifecycle and has no published value, so a count read
from ``status`` is zero over any corpus. ``archived`` stays a lifecycle question.
"""

from core.models.enums import EntityStatus
from core.models.enums.curriculum_enums import PublicationState
from core.models.pathways.path_step import PathStep
from core.services.ps_service import _PS_FILTER_CONFIG, _compute_ps_stats
from core.utils.list_helpers import apply_entity_filter


def _steps() -> list[PathStep]:
    published = [PathStep(uid=f"ps.test.published-{i}", title=f"Step {i}") for i in range(25)]
    drafts = [
        PathStep(
            uid=f"ps.test.draft-{i}",
            title=f"Draft {i}",
            publication_state=PublicationState.DRAFT,
        )
        for i in range(3)
    ]
    # Lifecycle DRAFT on a published step: in progress, not unpublished.
    in_progress = PathStep(
        uid="ps.test.in-progress", title="In progress", status=EntityStatus.DRAFT
    )
    archived = PathStep(uid="ps.test.archived", title="Archived", status=EntityStatus.ARCHIVED)
    return [*published, *drafts, in_progress, archived]


def test_published_and_draft_count_publication_state() -> None:
    stats = _compute_ps_stats(_steps())

    assert stats == {"total": 30, "active": 27, "published": 27, "draft": 3}


def test_the_filters_read_the_same_field() -> None:
    steps = _steps()

    published = apply_entity_filter(steps, "published", _PS_FILTER_CONFIG)
    drafts = apply_entity_filter(steps, "draft", _PS_FILTER_CONFIG)
    archived = apply_entity_filter(steps, "archived", _PS_FILTER_CONFIG)

    assert len(published) == 27
    assert {s.uid for s in drafts} == {f"ps.test.draft-{i}" for i in range(3)}
    assert [s.uid for s in archived] == ["ps.test.archived"]
