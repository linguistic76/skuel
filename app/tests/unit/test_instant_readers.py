"""Readers compare instants as aware UTC, in ``core/``.

A stored column holds naive stamps (a naive writer's offset-less string, UTC
digits), aware ones (a Neo4j native, a ``…Z`` or ``+hh:mm`` string) and gaps,
often at once. Every reader here — a sort, a window, a span, an age — reads each
value through ``as_utc`` / ``instant_of`` and measures against ``now_utc()``. The
tests put naive, aware and missing values in one list, and run under a process
clock forced to America/Vancouver, where a reader still on the naive
``datetime.now()`` reads seven hours off.

See: /docs/roadmap/utc-instants-arc.md § PR 5
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, tzinfo
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from neo4j.time import DateTime as Neo4jDateTime
from pydantic import BaseModel, ValidationError

from core.infrastructure.relationships.semantic_relationships import RelationshipMetadata
from core.models.auth.session import Session
from core.models.choice.choice import Choice
from core.models.enums.pipeline import ReportSource
from core.models.pathways.mastery import create_mastery
from core.models.pathways.path_step import PathStep
from core.models.progress.user_progress import UserProgress
from core.models.report.activity_report import ActivityReport
from core.models.request_base import ClientDateTime
from core.models.search.scoring import score_choice
from core.models.task.task import Task
from core.models.validation_rules import validate_future_date
from core.orchestrator.search_router import _sweep_sort_key
from core.services.choices_service import ChoicesService
from core.services.knowledge.knowledge_pattern_analyzer import KnowledgePatternAnalyzer
from core.services.report.period_eligibility import PeriodEligibility
from core.services.tasks.task_relationships import TaskRelationships
from core.services.user.unified_user_context import UserContext
from core.services.user.user_context_populator import UserContextPopulator
from core.utils.entity_filters import filter_choices
from core.utils.report_periods import resolve_report_period
from core.utils.result_simplified import Result
from core.utils.sort_functions import (
    get_created_at_attr,
    get_decision_deadline,
    get_updated_timestamp,
    make_attribute_sort_key,
)
from core.utils.timestamp_helpers import as_stored_clock, now_utc, to_wall_clock
from core.utils.zone_context import current_zone_var
from tests.helpers.forced_zone import forced_zone

VANCOUVER = ZoneInfo("America/Vancouver")
BANGKOK = ZoneInfo("Asia/Bangkok")


@pytest.fixture
def vancouver_process() -> Iterator[None]:
    """The process clock off the pin, in Vancouver — a naive ``now()`` reads 7 h behind UTC."""
    with forced_zone("America/Vancouver"):
        yield


@pytest.fixture
def vancouver_user() -> Iterator[None]:
    """The current zone is a Vancouver user's."""
    token = current_zone_var.set(VANCOUVER)
    try:
        yield
    finally:
        current_zone_var.reset(token)


def _ago(**delta: float) -> datetime:
    """An instant that far back, aware UTC."""
    return now_utc() - timedelta(**delta)


def _naive(moment: datetime) -> datetime:
    """The naive form a naive writer stores that instant in — UTC digits."""
    return as_stored_clock(moment)


# =============================================================================
# SORTS — naive, aware and absent in one list
# =============================================================================


class TestSortKeys:
    EARLY = datetime(2026, 9, 27, 23, 0)  # naive, UTC digits
    LATE = datetime(2026, 9, 28, 9, 0, tzinfo=BANGKOK)  # 02:00Z

    def test_created_at_sort_orders_naive_aware_and_absent(self) -> None:
        items = [SimpleNamespace(created_at=s) for s in (self.LATE, None, self.EARLY)]
        ordered = sorted(items, key=get_created_at_attr, reverse=True)
        assert [i.created_at for i in ordered] == [self.LATE, self.EARLY, None]

    def test_a_missing_decision_deadline_sorts_last(self) -> None:
        items = [SimpleNamespace(decision_deadline=s) for s in (None, self.LATE, self.EARLY)]
        ordered = sorted(items, key=get_decision_deadline)
        assert [i.decision_deadline for i in ordered] == [self.EARLY, self.LATE, None]

    def test_an_attribute_sort_reads_instants_and_puts_absent_first(self) -> None:
        items = [SimpleNamespace(decided_at=s) for s in (self.LATE, None, self.EARLY)]
        ordered = sorted(items, key=make_attribute_sort_key("decided_at"))
        assert [i.decided_at for i in ordered] == [None, self.EARLY, self.LATE]

    def test_the_moc_sort_reads_every_stored_shape(self, vancouver_user: None) -> None:
        rows = [
            {"uid": "a", "updated": "2026-09-27T23:00:00"},
            {"uid": "b", "updated": Neo4jDateTime(2026, 9, 28, 2, 0, 0, tzinfo=UTC)},
            {"uid": "c", "updated": "2026-09-28T01:00:00Z"},
            {"uid": "d", "updated": ""},
            {"uid": "e"},
        ]
        ordered = sorted(rows, key=get_updated_timestamp, reverse=True)
        assert [r["uid"] for r in ordered[:3]] == ["b", "c", "a"]
        assert {r["uid"] for r in ordered[3:]} == {"d", "e"}

    def test_the_search_sweep_sorts_stamps_as_instants(self, vancouver_user: None) -> None:
        # "…+07:00" sorts first as a string, but is the earliest instant (01:00Z).
        rows = [
            {"uid": "a", "updated_at": "2026-09-28T02:00:00"},
            {"uid": "b", "updated_at": "2026-09-28T08:00:00+07:00"},
            {"uid": "c", "updated_at": Neo4jDateTime(2026, 9, 28, 3, 0, 0, tzinfo=UTC)},
            {"uid": "d"},
        ]
        ordered = sorted(rows, key=_sweep_sort_key("updated_at"), reverse=True)
        assert [r["uid"] for r in ordered] == ["c", "a", "b", "d"]
        titles = [{"title": "b"}, {"title": "A"}, {}]
        assert sorted(titles, key=_sweep_sort_key("title")) == [{}, {"title": "A"}, {"title": "b"}]

    def test_choices_sort_by_deadline_instant_then_missing(self) -> None:
        choices = [
            Choice(uid="c1", title="later", user_uid="u", decision_deadline=self.LATE),
            Choice(uid="c2", title="none", user_uid="u"),
            Choice(uid="c3", title="sooner", user_uid="u", decision_deadline=self.EARLY),
        ]
        ordered = filter_choices(choices, status_filter="all", sort_by="deadline")
        assert [c.uid for c in ordered] == ["c3", "c1", "c2"]


# =============================================================================
# REPORT PERIODS — naive bounds, aware now, stamps of every shape
# =============================================================================


class TestReportPeriodsCompareInstants:
    # ISO week 38 of 2026 runs Monday 2026-09-14 to Sunday 2026-09-20.
    WEEK = "2026-W38"

    def test_a_period_compares_with_an_aware_now(self) -> None:
        period = resolve_report_period(self.WEEK, datetime(2026, 9, 16, 12, 0), VANCOUVER)
        during = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
        after = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
        assert period.has_started(during)
        assert not period.is_closed(during)
        assert period.is_closed(after)
        assert period.data_cutoff(during) is during
        assert period.data_cutoff(after) is period.end
        assert period.is_partial_at(during)
        assert not period.is_partial_at(period.end)

    def test_a_bare_completion_day_is_on_the_users_calendar(self, vancouver_user: None) -> None:
        """A task's ``completion_date`` is a bare day: the week's first day counts,
        and the next week's first day does not — whatever the week's bounds'
        UTC digits (07:00Z on the Monday, in Vancouver)."""
        period = resolve_report_period(self.WEEK, datetime(2026, 9, 22, 12, 0), VANCOUVER)
        eligible = PeriodEligibility.for_window(period.start, period.end)
        assert eligible.in_period("2026-09-14")
        assert eligible.in_period(date(2026, 9, 20))
        assert not eligible.in_period("2026-09-21")
        assert not eligible.in_period("2026-09-13")

    def test_stamps_of_every_shape_share_one_window(self, vancouver_user: None) -> None:
        period = resolve_report_period(self.WEEK, datetime(2026, 9, 22, 12, 0), VANCOUVER)
        eligible = PeriodEligibility.for_window(period.start, period.end)
        inside = [
            "2026-09-15T12:00:00",
            "2026-09-15T12:00:00Z",
            "2026-09-15T19:00:00+07:00",
            Neo4jDateTime(2026, 9, 15, 12, 0, 0, tzinfo=UTC),
            datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
        ]
        assert all(eligible.in_period(stamp) for stamp in inside)
        # 06:59Z on Monday is still Sunday evening in Vancouver — before the week.
        assert not eligible.in_period("2026-09-14T06:59:00Z")
        assert not eligible.in_period(None)
        assert not eligible.in_period("not-a-date")

    def test_a_report_title_reads_an_aware_cutoff(self) -> None:
        period = resolve_report_period(self.WEEK, datetime(2026, 9, 16, 12, 0), VANCOUVER)
        report = ActivityReport.create(
            user_uid="u",
            subject_uid="u",
            content="",
            processor_type=ReportSource.AUTOMATIC,
            period_start=period.start,
            period_end=period.end,
            time_period=self.WEEK,
            data_cutoff=datetime(2026, 9, 16, 19, 0, tzinfo=UTC),
            zone=VANCOUVER,
        )
        assert report.title.endswith("to Sep 16, 2026 (partial)")


# =============================================================================
# MODEL READERS — ages from now_utc(), never the process clock
# =============================================================================


class TestModelReaders:
    def test_recency_is_measured_from_utc_not_the_process_clock(
        self, vancouver_process: None
    ) -> None:
        # Eight days and three hours old: a Vancouver-local naive now() reads it
        # as seven days and twenty hours — recent — seven hours short.
        stale = Task(uid="t1", title="t", user_uid="u", created_at=_naive(_ago(days=8, hours=3)))
        fresh = Task(uid="t2", title="t", user_uid="u", created_at=_ago(days=3))
        assert not stale.is_recent(7)
        assert fresh.is_recent(7)

    def test_updated_compares_naive_with_aware(self) -> None:
        task = Task(
            uid="t",
            title="t",
            user_uid="u",
            created_at=_naive(_ago(days=2)),
            updated_at=_ago(days=1),
        )
        assert task.is_updated()

    def test_mastery_age_reads_an_aware_review(self, vancouver_process: None) -> None:
        reviewed_recently = replace(create_mastery("u", "ku.x"), last_reviewed=_ago(days=2))
        assert reviewed_recently.is_current_mastery()
        assert not reviewed_recently.needs_review()

    def test_a_deadline_is_scored_by_its_day(self, vancouver_user: None) -> None:
        soon = Choice(uid="c1", title="soon", user_uid="u", decision_deadline=_ago(days=-1))
        later = Choice(uid="c2", title="later", user_uid="u", decision_deadline=_ago(days=-60))
        context = SimpleNamespace(user_uid="u")
        soon_score = score_choice(soon, context)  # type: ignore[arg-type]
        later_score = score_choice(later, context)  # type: ignore[arg-type]
        assert soon_score.total > later_score.total


# =============================================================================
# SERVICE READERS — spans over a mixed column
# =============================================================================


class TestKnowledgePatternSpans:
    @pytest.mark.asyncio
    async def test_a_mixed_created_at_column_is_analysed(self, vancouver_user: None) -> None:
        """Vault-ingested entities carry aware stamps, UI-created ones naive: one
        user's list holds both, and every sort, span and gap reads them as one."""
        stamps = [
            _naive(_ago(days=20)),
            _ago(days=14).astimezone(BANGKOK),
            _naive(_ago(days=6)),
            _ago(days=1),
        ]
        tasks = [
            Task(uid=f"t{i}", title="t", user_uid="u", created_at=stamp)
            for i, stamp in enumerate(stamps)
        ]
        rels = TaskRelationships(
            applies_knowledge_uids=["ku.a"], prerequisite_knowledge_uids=["ku.b"]
        )

        async def fetch_rels(_uid: str) -> TaskRelationships:
            return rels

        result = await KnowledgePatternAnalyzer().analyze_learning_patterns(tasks, fetch_rels)

        assert result.is_ok, result
        spans = {pattern.timeframe_days for pattern in result.value}
        assert spans == {19}  # 20 days back to 1, whatever the order or shape


class TestContextPopulatorReadsInstants:
    def test_the_ku_window_reads_each_stamp_as_its_instant(self, vancouver_user: None) -> None:
        """The window opens at 12:00Z. A mastery at 18:00+07:00 is 11:00Z — before it,
        though its digits read later — while a native at 13:00Z and a naive view at
        12:30 (UTC digits) are inside."""
        context = UserContext(user_uid="u")
        context.mastery_timestamps = {
            "ku.bangkok_morning": "2026-09-28T18:00:00+07:00",  # type: ignore[dict-item]
            "ku.native": Neo4jDateTime(2026, 9, 28, 13, 0, 0, tzinfo=UTC),  # type: ignore[dict-item]
        }
        uids = {
            "ku_view_data": [
                {"uid": "ku.viewed", "last_viewed_at": "2026-09-28T12:30:00", "view_count": 2},
                {"uid": "ku.before", "last_viewed_at": "2026-09-28T11:59:00Z", "view_count": 1},
                {"uid": "ku.unreadable", "last_viewed_at": "yesterday", "view_count": 1},
            ]
        }

        UserContextPopulator().populate_ku_window_entities(
            context, uids, {"knowledge": []}, datetime(2026, 9, 28, 12, 0)
        )

        engaged = {item["entity"]["uid"] for item in context.entities_rich["ku"]}
        assert engaged == {"ku.native", "ku.viewed"}

    def test_recently_viewed_kus_sort_by_instant(self, vancouver_user: None) -> None:
        context = UserContext(user_uid="u")
        uids = {
            "ku_view_data": [
                {"uid": "ku.naive", "last_viewed_at": "2026-09-28T02:00:00", "view_count": 1},
                {
                    "uid": "ku.native",
                    "last_viewed_at": Neo4jDateTime(2026, 9, 28, 3, 0, 0, tzinfo=UTC),
                    "view_count": 1,
                },
                {
                    "uid": "ku.offset",
                    "last_viewed_at": "2026-09-28T08:00:00+07:00",
                    "view_count": 1,
                },
            ]
        }

        UserContextPopulator().populate_standard_fields(context, uids)

        assert context.recently_viewed_ku_uids == ["ku.native", "ku.naive", "ku.offset"]


class TestPendingDecisionCountdown:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("ahead", "zone", "score"),
        [
            # Two days and 18 hours out: urgent. Its Bangkok digits read 7 h later
            # (three days out) if the offset is dropped rather than converted.
            (timedelta(days=2, hours=18), BANGKOK, 0.9),
            # Naive, UTC digits: a Vancouver-local now() would add 7 h.
            (timedelta(days=2, hours=20), None, 0.9),
            (timedelta(days=5), UTC, 0.7),
            (timedelta(days=30), UTC, 0.5),
        ],
    )
    async def test_the_countdown_reads_the_deadline_as_an_instant(
        self, vancouver_process: None, ahead: timedelta, zone: tzinfo | None, score: float
    ) -> None:
        moment = now_utc() + ahead
        deadline = moment.astimezone(zone) if zone is not None else _naive(moment)
        choice = Choice(uid="c1", title="decide", user_uid="u", decision_deadline=deadline)
        facade = SimpleNamespace(get_pending_choices=AsyncMock(return_value=Result.ok([choice])))

        result = await ChoicesService.get_pending_decisions_for_user(
            facade,  # type: ignore[arg-type]
            UserContext(user_uid="u"),
        )

        assert result.is_ok
        assert [c.priority_score for c in result.value] == [score]


class TestMoreModelReaders:
    def test_substance_decays_by_instants_in_one_column(self, vancouver_process: None) -> None:
        """Substance stamps arrive as aware natives (``datetime($timestamp)``) and naive
        strings; the decay reads both, and a mixed max() cannot raise."""
        step = PathStep(
            uid="ps.x.y",
            title="p",
            times_applied_in_tasks=3,
            last_applied_date=_ago(days=2),
            times_practiced_in_events=2,
            last_practiced_date=_naive(_ago(days=40)),
        )
        mirrored = PathStep(
            uid="ps.x.z",
            title="p",
            times_applied_in_tasks=3,
            last_applied_date=_naive(_ago(days=2)),
            times_practiced_in_events=2,
            last_practiced_date=_ago(days=40),
        )
        assert step.substance_score(force_recalculate=True) == pytest.approx(
            mirrored.substance_score(force_recalculate=True)
        )
        assert step.days_until_review_needed() is not None

    def test_progress_orders_a_naive_start_before_an_aware_completion(self) -> None:
        with pytest.raises(ValueError, match="completed_at cannot be before started_at"):
            UserProgress(
                uid="p",
                user_uid="u",
                entity_uid="e",
                entity_type="task",
                progress_value=1.0,
                status="completed",
                tracked_at=_naive(_ago(hours=1)),
                started_at=_naive(_ago(hours=1)),
                completed_at=_ago(hours=3),
            )

    def test_a_session_expiry_read_back_naive_is_an_instant(self, vancouver_process: None) -> None:
        session = Session(
            uid="s",
            session_token="t",
            user_uid="u",
            created_at=_naive(_ago(days=1)),
            expires_at=_naive(_ago(hours=-2)),
            last_active_at=_naive(_ago(hours=1)),
            ip_address="",
            user_agent="",
        )
        assert not session.is_expired()
        assert timedelta(hours=1) < session.time_until_expiry() < timedelta(hours=3)

    def test_a_relationship_window_takes_naive_and_aware_bounds(self) -> None:
        metadata = RelationshipMetadata(valid_from=_naive(_ago(days=2)), valid_until=_ago(days=-2))
        assert metadata.is_valid_at(now_utc())
        assert metadata.is_valid_at(_naive(now_utc()))
        assert not metadata.is_valid_at(_ago(days=3))


class _DeadlineRequest(BaseModel):
    deadline: ClientDateTime | None = None

    _future = validate_future_date("deadline")


class TestClientDateTimeValidation:
    def test_a_future_check_reads_the_stored_instant(self, vancouver_user: None) -> None:
        """A ``datetime-local`` value is on the stored clock by the time the check
        runs, so it is compared as an instant — never with the zone's wall clock."""
        ahead = to_wall_clock(now_utc() + timedelta(hours=1), VANCOUVER)
        behind = to_wall_clock(now_utc() - timedelta(hours=1), VANCOUVER)

        assert _DeadlineRequest(deadline=ahead).deadline is not None
        with pytest.raises(ValidationError, match="cannot be in the past"):
            _DeadlineRequest(deadline=behind)
