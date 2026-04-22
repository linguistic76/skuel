"""Cross-domain UI component consistency tests.

Verifies that shared UI components (PageHeader, EmptyState, StatsGrid,
EntityRelationshipsSection) are used consistently across all activity
domain views and hub pages. Catches silent divergence from shared patterns.
"""

import inspect

import pytest
from fasthtml.common import to_xml

from core.models.choice.choice import Choice
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.principle.principle import Principle
from core.models.task.task import Task
from ui.activities import (
    choices_views,
    events_views,
    goals_views,
    habits_views,
    principles_views,
    tasks_views,
)
from ui.activities.choices_views import ChoiceDetailView, ChoiceList, ChoiceStatsBar
from ui.activities.events_views import EventDetailView, EventList, EventStatsBar
from ui.activities.goals_views import GoalDetailView, GoalList, GoalStatsBar
from ui.activities.habits_views import HabitDetailView, HabitList, HabitStatsBar
from ui.activities.principles_views import (
    PrincipleDetailView,
    PrincipleList,
    PrincipleStatsBar,
)
from ui.activities.tasks_views import TaskDetailView, TaskList, TaskStatsBar

ACTIVITY_DOMAINS = [
    ("tasks", tasks_views, TaskList, TaskStatsBar, TaskDetailView, Task, "tasks"),
    ("goals", goals_views, GoalList, GoalStatsBar, GoalDetailView, Goal, "goals"),
    ("habits", habits_views, HabitList, HabitStatsBar, HabitDetailView, Habit, "habits"),
    ("events", events_views, EventList, EventStatsBar, EventDetailView, Event, "events"),
    (
        "choices",
        choices_views,
        ChoiceList,
        ChoiceStatsBar,
        ChoiceDetailView,
        Choice,
        "choices",
    ),
    (
        "principles",
        principles_views,
        PrincipleList,
        PrincipleStatsBar,
        PrincipleDetailView,
        Principle,
        "principles",
    ),
]

DOMAIN_IDS = [d[0] for d in ACTIVITY_DOMAINS]


def _make_entity(model_cls: type, domain: str) -> object:
    """Construct a minimal domain entity for rendering."""
    return model_cls(uid=f"{domain}_test_1", title=f"Test {domain.title()}", user_uid="user_test")


class TestImportConsistency:
    """Verify all activity view modules import required shared components."""

    # EmptyState is intentionally excluded: all 6 views delegate empty-list rendering
    # to ActivityList (in _shared.py), which imports and uses EmptyState directly.
    # Each views file does not need its own import.
    REQUIRED_IMPORTS = [
        "from ui.patterns.page_header import PageHeader",
        "from ui.patterns.stats_grid import",
        "from ui.patterns.relationships.relationship_section import EntityRelationshipsSection",
    ]

    @pytest.mark.parametrize(
        "domain,module,_l,_s,_d,_m,_t",
        ACTIVITY_DOMAINS,
        ids=DOMAIN_IDS,
    )
    def test_shared_component_imports(
        self,
        domain: str,
        module: object,
        _l: object,
        _s: object,
        _d: object,
        _m: type,
        _t: str,
    ) -> None:
        source = inspect.getsource(module)
        for import_line in self.REQUIRED_IMPORTS:
            assert import_line in source, f"{domain}_views.py missing import: {import_line}"


class TestEmptyStateConsistency:
    """Verify *List([]) renders EmptyState for all domains."""

    @pytest.mark.parametrize(
        "domain,_mod,list_fn,_s,_d,_m,_t",
        ACTIVITY_DOMAINS,
        ids=DOMAIN_IDS,
    )
    def test_empty_list_renders_empty_state(
        self,
        domain: str,
        _mod: object,
        list_fn: object,
        _s: object,
        _d: object,
        _m: type,
        _t: str,
    ) -> None:
        result = to_xml(list_fn([]))
        assert "text-center" in result, f"{domain} empty list missing text-center"
        assert "py-12" in result, f"{domain} empty list missing py-12"


class TestStatsBarConsistency:
    """Verify *StatsBar([]) renders StatsGrid for all domains."""

    @pytest.mark.parametrize(
        "domain,_mod,_l,stats_fn,_d,_m,_t",
        ACTIVITY_DOMAINS,
        ids=DOMAIN_IDS,
    )
    def test_empty_stats_bar_renders_stats_grid(
        self,
        domain: str,
        _mod: object,
        _l: object,
        stats_fn: object,
        _d: object,
        _m: type,
        _t: str,
    ) -> None:
        result = to_xml(stats_fn([]))
        assert "text-3xl" in result, f"{domain} stats bar missing text-3xl"
        assert "font-bold" in result, f"{domain} stats bar missing font-bold"


class TestDetailViewConsistency:
    """Verify *DetailView renders PageHeader and EntityRelationshipsSection."""

    @pytest.mark.parametrize(
        "domain,_mod,_l,_s,detail_fn,model_cls,entity_type",
        ACTIVITY_DOMAINS,
        ids=DOMAIN_IDS,
    )
    def test_detail_view_has_page_header(
        self,
        domain: str,
        _mod: object,
        _l: object,
        _s: object,
        detail_fn: object,
        model_cls: type,
        entity_type: str,
    ) -> None:
        entity = _make_entity(model_cls, domain)
        result = to_xml(detail_fn(entity, []))
        assert "text-2xl" in result, f"{domain} detail missing PageHeader (text-2xl)"
        assert "mb-8" in result, f"{domain} detail missing PageHeader (mb-8)"

    @pytest.mark.parametrize(
        "domain,_mod,_l,_s,detail_fn,model_cls,entity_type",
        ACTIVITY_DOMAINS,
        ids=DOMAIN_IDS,
    )
    def test_detail_view_has_relationships_section(
        self,
        domain: str,
        _mod: object,
        _l: object,
        _s: object,
        detail_fn: object,
        model_cls: type,
        entity_type: str,
    ) -> None:
        entity = _make_entity(model_cls, domain)
        result = to_xml(detail_fn(entity, []))
        assert entity.uid in result, f"{domain} detail missing entity uid in relationships HTMX"


class TestHubPageConsistency:
    """Verify hub pages use PageHeader."""

    def test_activity_hub_has_page_header(self) -> None:
        from ui.activities.activity_hub import ActivityHubView

        result = to_xml(ActivityHubView())
        assert "text-2xl" in result, "ActivityHub missing PageHeader (text-2xl)"
        assert "font-bold" in result, "ActivityHub missing PageHeader (font-bold)"
        assert "mb-8" in result, "ActivityHub missing PageHeader (mb-8)"

    def test_gradebook_hub_has_page_header(self) -> None:
        from ui.gradebook.hub import GradeBookHub

        result = to_xml(GradeBookHub())
        assert "text-2xl" in result, "GradeBookHub missing PageHeader (text-2xl)"
        assert "font-bold" in result, "GradeBookHub missing PageHeader (font-bold)"
        assert "mb-8" in result, "GradeBookHub missing PageHeader (mb-8)"

    def test_library_hub_has_page_header(self) -> None:
        from ui.library.hub import LibraryHub

        result = to_xml(LibraryHub())
        assert "text-2xl" in result, "LibraryHub missing PageHeader (text-2xl)"
        assert "font-bold" in result, "LibraryHub missing PageHeader (font-bold)"
        assert "mb-8" in result, "LibraryHub missing PageHeader (mb-8)"

    def test_student_hub_has_page_header(self) -> None:
        from ui.teaching.student_hub import StudentHub

        result = to_xml(StudentHub("Test Student", "stu_1"))
        assert "text-2xl" in result, "StudentHub missing PageHeader (text-2xl)"
        assert "font-bold" in result, "StudentHub missing PageHeader (font-bold)"
        assert "mb-8" in result, "StudentHub missing PageHeader (mb-8)"
