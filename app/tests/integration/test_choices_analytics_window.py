"""
Real-Neo4j guard for the Choices period-analytics window.
=========================================================

The three period methods on ``_AnalyticsMixin`` fetched their window with
``find_by(user_uid=..., date__gte=..., date__lte=...)``. ``Choice`` has no ``date``
field, and ``build_search_query`` skips filter keys that are not model fields, so both
temporal predicates were dropped: the query degraded to ``WHERE n.user_uid = $user_uid``
and returned **every** choice the user had ever made, ignoring ``days`` entirely.

Note the negative control this needs. "Assert the result is non-empty" would have passed
against the bug — the pre-fix query returned *more* rows, not fewer. So each test seeds a
choice **outside** the window and asserts it is excluded; the counts below are 2, not 3,
and the pre-fix code produces 3.

The in-window pair deliberately uses **both** ``created_at`` storage shapes — ISO string
(the majority) and a real zoned datetime (the minority) — so the test also pins the
coercion. A "fix" that merely repointed the key to ``find_by(created_at__gte=...)`` would
compare a string bound against the datetime-stored row, evaluate to null, and drop it;
that variant fails here at count 1.

See: tests/integration/test_created_at_window_coercion.py (the mixed-shape column)
     tests/unit/services/choices/test_choices_analytics_window.py (the cheap half)
"""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.activity_backends import ChoicesBackend
from core.models.choice.choice import Choice
from core.models.enums.neo_labels import NeoLabel
from core.services.choices.choices_intelligence_service import ChoicesIntelligenceService

USER = "user_choice_window"

IN_WINDOW_STRING = "choice_win_str"  # created_at as ISO string, 10 days ago
IN_WINDOW_DATETIME = "choice_win_dt"  # created_at as zoned datetime, 5 days ago
OUT_OF_WINDOW = "choice_out_str"  # created_at as ISO string, 200 days ago


@pytest.mark.asyncio
class TestChoicesAnalyticsWindow:
    """Period analytics must honour the requested window, on either storage shape."""

    @pytest_asyncio.fixture
    async def intelligence(self, neo4j_driver, clean_neo4j):
        """Seed the three choices and return a ChoicesIntelligenceService over them."""
        now = datetime.now(UTC)
        async with neo4j_driver.session() as session:
            await session.run("MERGE (u:User {uid: $u})", u=USER)
            # Majority shape: created_at as an ISO string, inside a 30-day window.
            await session.run(
                """
                CREATE (n:Entity:Choice {uid: $uid, user_uid: $u, entity_type: 'choice',
                                         title: 'In window (string)', status: 'active',
                                         domain: 'personal', created_at: $c})
                """,
                uid=IN_WINDOW_STRING,
                u=USER,
                c=(now - timedelta(days=10)).isoformat(),
            )
            # Minority shape: created_at as a real zoned datetime, also inside the window.
            await session.run(
                """
                CREATE (n:Entity:Choice {uid: $uid, user_uid: $u, entity_type: 'choice',
                                         title: 'In window (datetime)', status: 'active',
                                         domain: 'personal',
                                         created_at: datetime() - duration({days: 5})})
                """,
                uid=IN_WINDOW_DATETIME,
                u=USER,
            )
            # Outside the window — the negative control that makes these tests non-vacuous.
            await session.run(
                """
                CREATE (n:Entity:Choice {uid: $uid, user_uid: $u, entity_type: 'choice',
                                         title: 'Out of window', status: 'active',
                                         domain: 'health', created_at: $c})
                """,
                uid=OUT_OF_WINDOW,
                u=USER,
                c=(now - timedelta(days=200)).isoformat(),
            )

        # Constructed exactly as services_bootstrap/_backends.py builds it, so the test
        # exercises the production label/base_label pair rather than a lookalike.
        backend = ChoicesBackend(neo4j_driver, NeoLabel.CHOICE, Choice, base_label=NeoLabel.ENTITY)
        return ChoicesIntelligenceService(backend=backend, cross_domain_query=None)

    async def test_decision_patterns_counts_only_the_window(self, intelligence):
        """total_choices excludes the 200-day-old choice. Pre-fix: 3."""
        result = await intelligence.get_decision_patterns(USER, days=30)
        assert result.is_ok, f"get_decision_patterns failed: {result}"

        metrics = result.value["decision_metrics"]
        assert metrics["total_choices"] == 2, (
            "window ignored (3 = the out-of-window choice leaked in) or "
            "coercion dropped the datetime-stored choice (1)"
        )
        # weeks = 30/7; two choices in the window.
        assert metrics["choices_per_week"] == pytest.approx(2 / (30 / 7.0))

    async def test_domain_decision_patterns_counts_only_the_window(self, intelligence):
        """The out-of-window choice is the only 'health' one — its domain must not appear."""
        result = await intelligence.get_domain_decision_patterns(USER, days=30)
        assert result.is_ok, f"get_domain_decision_patterns failed: {result}"

        assert result.value["total_choices"] == 2
        domains = result.value["domain_patterns"]
        assert "health" not in domains, "out-of-window choice leaked into the domain split"
        assert domains["personal"]["choice_count"] == 2
        assert domains["personal"]["percentage"] == pytest.approx(100.0)

    async def test_quality_correlations_counts_only_the_window(self, intelligence):
        """The third period method shares the same fetch and the same guard."""
        result = await intelligence.get_choice_quality_correlations(USER, days=30)
        assert result.is_ok, f"get_choice_quality_correlations failed: {result}"

        assert result.value["total_choices_analyzed"] == 2

    async def test_widening_the_window_admits_the_older_choice(self, intelligence):
        """`days` is live: widening to 365 picks the out-of-window choice back up.

        Pre-fix this returned 3 for *both* windows, so the pair of assertions is what
        distinguishes a real filter from a dropped one.
        """
        narrow = await intelligence.get_decision_patterns(USER, days=30)
        wide = await intelligence.get_decision_patterns(USER, days=365)

        assert narrow.value["decision_metrics"]["total_choices"] == 2
        assert wide.value["decision_metrics"]["total_choices"] == 3
