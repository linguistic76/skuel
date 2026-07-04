"""Tests for the Engage/Abandon action group rendered on /explore/ps/{uid}.

Covers the ``render_engagement_actions`` helper in ``path_steps_ui.py`` —
the single source of truth for what the engagement action area looks like.
HTMX handler closures inside ``create_path_steps_ui_routes`` delegate to
the engagement service and then re-render via this helper, so testing the
helper covers the visible contract for slice 1.

Full handler-flow coverage (Neo4j edge writes, lifecycle transitions) lives
in ``tests/integration/test_ps_engagement_lifecycle.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fasthtml.common import to_xml

from adapters.inbound.path_steps_ui import (
    _parse_review_form,
    _ps_tasks_fragment,
    render_engagement_actions,
)
from core.models.enums.learning_enums import KnowledgeStatus
from core.ports.query_types import Violation
from core.services.ps_engagement.engagement import Engagement
from core.services.ps_engagement.ps_engagement_service import ReviewItem
from ui.explore.ps_completion_review import render_review_error, render_review_form
from ui.explore.ps_publish_state import (
    PUBLISH_STATE_ID,
    STATUS_BADGE_ID,
    render_publish_state,
    render_publish_violations,
    render_status_badge,
)

_PS_UID = "ps:test:slice1"
_WRAPPER_ID = 'id="ps-engagement-actions"'


def _engaged() -> Engagement:
    return Engagement(
        student_uid="user_alice",
        ps_uid=_PS_UID,
        state="engaged",
        since=datetime(2026, 5, 11, 9, 0, tzinfo=UTC),
    )


class TestRenderEngagementActionsNoActive:
    """When find_active returned None — page invites the user to engage."""

    def test_shows_engage_button_with_post_target(self) -> None:
        html = to_xml(render_engagement_actions(_PS_UID, None))

        assert "Engage with this Path Step" in html
        assert f'hx-post="/explore/ps/{_PS_UID}/engage"' in html

    def test_uses_wrapper_id_and_swaps_self(self) -> None:
        html = to_xml(render_engagement_actions(_PS_UID, None))

        assert _WRAPPER_ID in html
        assert 'hx-target="#ps-engagement-actions"' in html
        assert 'hx-swap="outerHTML"' in html

    def test_no_abandon_button_in_clean_state(self) -> None:
        html = to_xml(render_engagement_actions(_PS_UID, None))

        assert "Abandon" not in html


class TestRenderEngagementActionsEngaged:
    """When an active engagement exists — show status + Abandon."""

    def test_shows_engaged_badge(self) -> None:
        html = to_xml(render_engagement_actions(_PS_UID, _engaged()))

        assert "Engaged" in html

    def test_shows_abandon_button_with_confirm(self) -> None:
        html = to_xml(render_engagement_actions(_PS_UID, _engaged()))

        assert "Abandon" in html
        assert f'hx-post="/explore/ps/{_PS_UID}/abandon"' in html
        assert "hx-confirm=" in html

    def test_shows_complete_button_opening_review_panel(self) -> None:
        """Slice 4: Complete button GETs the review form into the wrapper."""
        html = to_xml(render_engagement_actions(_PS_UID, _engaged()))

        assert "Complete" in html
        # Complete opens the review (GET); the actual mutation is on submit.
        assert f'hx-get="/explore/ps/{_PS_UID}/complete-review"' in html
        # No direct POST to /complete from this button — that's the form action.
        assert f'hx-post="/explore/ps/{_PS_UID}/complete"' not in html

    def test_wrapper_id_preserved_for_htmx_swap(self) -> None:
        html = to_xml(render_engagement_actions(_PS_UID, _engaged()))

        assert _WRAPPER_ID in html


# ============================================================================
# Slice 4 — completion review panel
# ============================================================================


def _items(*specs: tuple[str, str, str, str]) -> list[ReviewItem]:
    """Build ReviewItems from (template_uid, instance_uid, label, title) tuples."""
    return [
        ReviewItem(template_uid=t, instance_uid=i, label=lab, title=title)
        for t, i, lab, title in specs
    ]


class TestRenderReviewFormPopulated:
    """Review form with N spawned items — one row per template_uid."""

    def test_renders_row_per_item_with_title_and_label(self) -> None:
        items = _items(
            ("tpl_task_x", "task_001", "Task", "Read chapter 3"),
            ("tpl_habit_y", "habit_001", "Habit", "Practice daily"),
        )
        html = to_xml(render_review_form(_PS_UID, items))

        assert "Read chapter 3" in html
        assert "Practice daily" in html
        assert "Task" in html
        assert "Habit" in html

    def test_checkbox_per_template_pre_checked_keep(self) -> None:
        items = _items(("tpl_task_x", "task_001", "Task", "Read chapter 3"))
        html = to_xml(render_review_form(_PS_UID, items))

        assert 'name="keep_tpl_task_x"' in html
        # The checkbox is pre-checked by default ("All pre-checked as Keep").
        assert "checked" in html

    def test_hidden_template_uids_collected_per_row(self) -> None:
        items = _items(
            ("tpl_a", "i_a", "Task", "A"),
            ("tpl_b", "i_b", "Goal", "B"),
        )
        html = to_xml(render_review_form(_PS_UID, items))

        # Two hidden inputs feeding the multi-value template_uids list.
        assert html.count('name="template_uids"') == 2
        assert 'value="tpl_a"' in html
        assert 'value="tpl_b"' in html

    def test_form_posts_to_complete_endpoint(self) -> None:
        items = _items(("tpl_x", "i_x", "Task", "X"))
        html = to_xml(render_review_form(_PS_UID, items))

        assert f'hx-post="/explore/ps/{_PS_UID}/complete"' in html
        assert f'hx-target="#{_WRAPPER_ID[4:-1]}"' in html  # "ps-engagement-actions"

    def test_cancel_button_restores_engagement_actions(self) -> None:
        items = _items(("tpl_x", "i_x", "Task", "X"))
        html = to_xml(render_review_form(_PS_UID, items))

        assert f'hx-get="/explore/ps/{_PS_UID}/engagement-actions"' in html

    def test_wrapper_id_preserved(self) -> None:
        items = _items(("tpl_x", "i_x", "Task", "X"))
        html = to_xml(render_review_form(_PS_UID, items))

        assert _WRAPPER_ID in html


class TestRenderReviewFormEmpty:
    """Engaged but no spawned instances (edge case — PS had empty template set)."""

    def test_empty_state_shows_no_activities_message(self) -> None:
        html = to_xml(render_review_form(_PS_UID, []))

        assert "No activities were spawned" in html

    def test_empty_state_still_submits_to_complete(self) -> None:
        """An empty review is valid — service interprets {} as keep-all (no-op)."""
        html = to_xml(render_review_form(_PS_UID, []))

        assert f'hx-post="/explore/ps/{_PS_UID}/complete"' in html


class TestRenderReviewError:
    """Failure path — service couldn't load the review or complete failed."""

    def test_renders_error_message_inline(self) -> None:
        html = to_xml(render_review_error(_PS_UID, "Database unreachable"))

        assert "Database unreachable" in html

    def test_provides_back_to_engagement_action(self) -> None:
        html = to_xml(render_review_error(_PS_UID, "boom"))

        assert f'hx-get="/explore/ps/{_PS_UID}/engagement-actions"' in html

    def test_preserves_wrapper_id_for_swap(self) -> None:
        html = to_xml(render_review_error(_PS_UID, "boom"))

        assert _WRAPPER_ID in html


# ============================================================================
# _parse_review_form — checkbox semantics
# ============================================================================


class _FakeForm:
    """Stub for Starlette FormData — supports getlist + `in` containment."""

    def __init__(self, *, multi: dict[str, list[str]], scalar: list[str]) -> None:
        self._multi = multi
        self._scalar = set(scalar)

    def getlist(self, key: str) -> list[str]:
        return list(self._multi.get(key, []))

    def __contains__(self, key: str) -> bool:
        return key in self._scalar


class TestParseReviewForm:
    def test_kept_template_renders_keep_decision(self) -> None:
        form = _FakeForm(
            multi={"template_uids": ["tpl_a"]},
            scalar=["keep_tpl_a"],
        )

        assert _parse_review_form(form) == {"tpl_a": "keep"}

    def test_unchecked_template_renders_discard_decision(self) -> None:
        form = _FakeForm(
            multi={"template_uids": ["tpl_a"]},
            scalar=[],  # checkbox unchecked → not in form payload
        )

        assert _parse_review_form(form) == {"tpl_a": "discard"}

    def test_mixed_keep_discard(self) -> None:
        form = _FakeForm(
            multi={"template_uids": ["tpl_a", "tpl_b", "tpl_c"]},
            scalar=["keep_tpl_a", "keep_tpl_c"],
        )

        assert _parse_review_form(form) == {
            "tpl_a": "keep",
            "tpl_b": "discard",
            "tpl_c": "keep",
        }

    def test_empty_form_yields_empty_review(self) -> None:
        """Defensive — empty review tells service to keep-all (no-op)."""
        form = _FakeForm(multi={}, scalar=[])

        assert _parse_review_form(form) == {}


# ============================================================================
# Slice 2 — teacher publish flow (badge + button + violations panel)
# ============================================================================


def _violation(
    *,
    template_uid: str = "tpl_task_x",
    template_title: str = "Read intro",
    template_type: str = "TaskTemplate",
    field: str = "fulfills_goal_template_uid",
    violation: str = "target_missing",
    referenced_uid: str | None = "tpl_goal_missing",
    hint: str | None = None,
) -> Violation:
    return Violation(
        template_uid=template_uid,
        template_title=template_title,
        template_type=template_type,  # type: ignore[typeddict-item]
        field=field,
        violation=violation,  # type: ignore[typeddict-item]
        referenced_uid=referenced_uid,
        hint=hint,
    )


class TestRenderStatusBadge:
    """The Draft/Published indicator that lives in the PS metadata row."""

    def test_draft_status_renders_draft_label(self) -> None:
        html = to_xml(render_status_badge(KnowledgeStatus.DRAFT))

        assert "Draft" in html
        assert "Status:" in html

    def test_published_status_renders_published_label(self) -> None:
        html = to_xml(render_status_badge(KnowledgeStatus.PUBLISHED))

        assert "Published" in html

    def test_carries_stable_id_for_oob_swap(self) -> None:
        html = to_xml(render_status_badge(KnowledgeStatus.DRAFT))

        assert f'id="{STATUS_BADGE_ID}"' in html

    def test_oob_flag_adds_swap_oob_attribute(self) -> None:
        """Publish handler returns the badge as an OOB swap on success."""
        html = to_xml(render_status_badge(KnowledgeStatus.PUBLISHED, oob=True))

        assert 'hx-swap-oob="true"' in html

    def test_oob_default_omits_swap_oob_attribute(self) -> None:
        """In-page render (initial metadata row) must NOT be OOB-tagged."""
        html = to_xml(render_status_badge(KnowledgeStatus.DRAFT))

        assert "hx-swap-oob" not in html

    def test_none_status_defaults_to_draft(self) -> None:
        """Legacy nodes missing the field still render something sensible."""
        html = to_xml(render_status_badge(None))

        assert "Draft" in html


class TestRenderPublishStateTeacherDraft:
    """Teacher viewing a DRAFT PS — Publish button is visible and posts."""

    def test_button_visible_for_teacher_on_draft(self) -> None:
        html = to_xml(render_publish_state(_PS_UID, KnowledgeStatus.DRAFT, is_teacher=True))

        assert "Publish" in html
        assert f'hx-post="/explore/ps/{_PS_UID}/publish"' in html

    def test_button_swaps_publish_state_wrapper(self) -> None:
        html = to_xml(render_publish_state(_PS_UID, KnowledgeStatus.DRAFT, is_teacher=True))

        assert f'hx-target="#{PUBLISH_STATE_ID}"' in html
        assert 'hx-swap="outerHTML"' in html

    def test_wrapper_id_present(self) -> None:
        html = to_xml(render_publish_state(_PS_UID, KnowledgeStatus.DRAFT, is_teacher=True))

        assert f'id="{PUBLISH_STATE_ID}"' in html


class TestRenderPublishStateHidden:
    """Button is hidden when the role or status disqualifies the viewer."""

    def test_non_teacher_sees_no_publish_button(self) -> None:
        html = to_xml(render_publish_state(_PS_UID, KnowledgeStatus.DRAFT, is_teacher=False))

        assert "Publish" not in html

    def test_teacher_on_published_ps_sees_no_button(self) -> None:
        """DRAFT-only trigger — re-publish isn't meaningful."""
        html = to_xml(render_publish_state(_PS_UID, KnowledgeStatus.PUBLISHED, is_teacher=True))

        assert "Publish" not in html

    def test_teacher_on_under_review_sees_no_button(self) -> None:
        html = to_xml(render_publish_state(_PS_UID, KnowledgeStatus.UNDER_REVIEW, is_teacher=True))

        assert "Publish" not in html

    def test_hidden_state_preserves_wrapper_id(self) -> None:
        """Dismiss-from-violations needs the wrapper id to swap back into."""
        html = to_xml(render_publish_state(_PS_UID, KnowledgeStatus.DRAFT, is_teacher=False))

        assert f'id="{PUBLISH_STATE_ID}"' in html


class TestRenderPublishViolations:
    """Validation-failure panel replaces the publish button."""

    def test_renders_one_row_per_violation(self) -> None:
        violations = [
            _violation(template_uid="t1", template_title="Read intro"),
            _violation(template_uid="t2", template_title="Master X", violation="wrong_type"),
            _violation(template_uid="t3", template_title="Daily review", violation="cycle"),
        ]
        html = to_xml(render_publish_violations(_PS_UID, violations))

        assert "Read intro" in html
        assert "Master X" in html
        assert "Daily review" in html

    def test_heading_counts_issues(self) -> None:
        html = to_xml(render_publish_violations(_PS_UID, [_violation()]))

        assert "Cannot publish: 1 issue" in html

    def test_heading_pluralizes_correctly(self) -> None:
        violations = [_violation(template_uid="a"), _violation(template_uid="b")]
        html = to_xml(render_publish_violations(_PS_UID, violations))

        assert "Cannot publish: 2 issues" in html

    def test_dismiss_button_restores_publish_state(self) -> None:
        html = to_xml(render_publish_violations(_PS_UID, [_violation()]))

        assert "Dismiss" in html
        assert f'hx-get="/explore/ps/{_PS_UID}/publish-state"' in html
        assert f'hx-target="#{PUBLISH_STATE_ID}"' in html

    def test_wrapper_id_preserved_for_swap(self) -> None:
        html = to_xml(render_publish_violations(_PS_UID, [_violation()]))

        assert f'id="{PUBLISH_STATE_ID}"' in html

    def test_violation_field_and_kind_rendered(self) -> None:
        violations = [
            _violation(
                template_title="Read intro",
                field="fulfills_goal_template_uid",
                violation="target_missing",
            )
        ]
        html = to_xml(render_publish_violations(_PS_UID, violations))

        assert "fulfills_goal_template_uid" in html
        # The phrase is humanized rather than the raw enum value.
        assert "references a template not on this PathStep" in html

    def test_hint_rendered_when_present(self) -> None:
        violations = [_violation(hint="tpl_goal_existing")]
        html = to_xml(render_publish_violations(_PS_UID, violations))

        assert "tpl_goal_existing" in html

    def test_no_hint_omits_did_you_mean(self) -> None:
        violations = [_violation(hint=None)]
        html = to_xml(render_publish_violations(_PS_UID, violations))

        assert "did you mean" not in html


# ============================================================================
# _ps_tasks_fragment — tasks section HTMX fragment
# ============================================================================


class _FakeTask:
    """Minimal Task stub for fragment rendering tests."""

    def __init__(self, uid: str, title: str, status: str | None = None) -> None:
        self.uid = uid
        self.title = title
        self.status = _FakeStatus(status) if status else None


class _FakeStatus:
    def __init__(self, value: str) -> None:
        self._value = value

    def __str__(self) -> str:
        return self._value


class TestPsTasksFragment:
    """Tests for the tasks-from-this-step HTMX fragment."""

    def test_fragment_has_stable_id_for_htmx_swap(self) -> None:
        html = to_xml(_ps_tasks_fragment(_PS_UID, []))

        assert 'id="ps-tasks-fragment"' in html

    def test_fragment_retains_htmx_attributes_for_subsequent_swaps(self) -> None:
        # After outerHTML swap, the returned element must keep hx-get + hx-trigger
        # so the ps-engaged event still has a listener on re-engagement.
        html = to_xml(_ps_tasks_fragment(_PS_UID, []))

        assert f'hx-get="/explore/ps/{_PS_UID}/tasks"' in html
        assert 'hx-trigger="ps-engaged"' in html
        assert 'hx-swap="outerHTML"' in html

    def test_empty_tasks_shows_truthful_empty_state(self) -> None:
        # Care-arc W7: the old "Click Start learning" call-to-action was wrong
        # for enrolled users and for steps without task templates.
        html = to_xml(_ps_tasks_fragment(_PS_UID, []))

        assert "No tasks from this step yet" in html
        assert "Click Start learning" not in html

    def test_task_title_links_to_detail_page(self) -> None:
        task = _FakeTask(uid="task_001", title="Read chapter 3")
        html = to_xml(_ps_tasks_fragment(_PS_UID, [task]))

        assert "Read chapter 3" in html
        assert 'href="/tasks/detail?uid=task_001"' in html

    def test_completed_task_applies_strikethrough(self) -> None:
        task = _FakeTask(uid="task_001", title="Done task", status="completed")
        html = to_xml(_ps_tasks_fragment(_PS_UID, [task]))

        assert "line-through" in html

    def test_active_task_no_strikethrough(self) -> None:
        task = _FakeTask(uid="task_002", title="Active task", status="active")
        html = to_xml(_ps_tasks_fragment(_PS_UID, [task]))

        assert "line-through" not in html

    def test_multiple_tasks_all_rendered(self) -> None:
        tasks = [
            _FakeTask(uid="task_001", title="First task"),
            _FakeTask(uid="task_002", title="Second task"),
        ]
        html = to_xml(_ps_tasks_fragment(_PS_UID, tasks))

        assert "First task" in html
        assert "Second task" in html
