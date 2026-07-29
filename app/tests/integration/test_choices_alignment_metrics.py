"""
Real-Neo4j guard for the Choices alignment metrics.
===================================================

``get_decision_patterns`` counted principle- and goal-aligned choices with::

    sum(1 for c in choices if getattr(c, "aligned_principles", None))
    sum(1 for c in choices if getattr(c, "related_goals", None))

Neither name is a field on ``Choice`` or ``ChoiceDTO``, so the ``None`` default made both
sums **structurally 0 for every input** — no error, no warning. ``principle_aligned_percentage``,
``goal_oriented_percentage``, ``principle_alignment_score`` and the ``strategic_vs_tactical``
band derived from them were therefore pinned at 0.0 / "tactical" for every user forever.
The data was never on the row: it lives on edges — ``INFORMED_BY_PRINCIPLE`` and
``GUIDES_CHOICE`` for principles, ``AFFECTS_GOAL`` for goals — which is what the fix reads.

Most of these are RED before the fix (measured: 0.0 where a fraction is expected,
``"tactical"`` where ``"balanced"`` is, ``None`` where a principle UID is), because the
pre-fix code returns 0.0 for *any* seeding — there is no seeding that distinguishes it.
That also means "assert non-zero" is enough here, unlike the window bug in the sibling
file, whose failure mode was an over-return that "assert non-empty" would have passed.

Two tests are not RED, and both exist to stop the others being satisfied by a constant:
``test_unlinked_user_still_reports_zero`` (a real 0.0 must stay 0.0) and
``test_service_refuses_to_construct_without_relationships`` (a 0.0 that is really a
missing dependency must never be reported as an answer at all).

The seeding carries three controls, one per way a fix can be wrong:

- ``align_c_bare`` — in the window, no edges. Keeps the percentages fractional, so a fix
  that counted every choice reads 1.0 instead of 3/5.
- ``align_c_old`` — outside the window, fully linked. Fails the counts if the alignment
  read escapes the ``days`` window that #859 established.
- ``align_c_guided`` — linked *only* by the incoming ``(Principle)-[:GUIDES_CHOICE]->``
  direction, which ``PrinciplesService.create_principle_link(link_type="choice")`` writes
  from the principle side via ``POST /api/principles/links``. Reading only the outgoing
  direction drops it and reads 2/5.

See: tests/integration/test_choices_analytics_window.py (the window half, same fixture shape)
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.activity_backends import ChoicesBackend
from core.models.choice.choice import Choice
from core.models.enums.neo_labels import NeoLabel
from core.services.activity_domain_config import ACTIVITY_DOMAIN_CONFIGS
from core.services.choices.choices_intelligence_service import ChoicesIntelligenceService
from core.services.relationships import UnifiedRelationshipService

USER = "user_choice_alignment"

PRINCIPLE_ONLY = "align_c_principle"  # -[:INFORMED_BY_PRINCIPLE]-> p1
GOAL_ONLY = "align_c_goal"  # -[:AFFECTS_GOAL]-> g1
BOTH = "align_c_both"  # -> p1, p2, g1
BARE = "align_c_bare"  # no edges — keeps the percentages fractional
GUIDED = "align_c_guided"  # p1 -[:GUIDES_CHOICE]-> it — the incoming direction only
OUT_OF_WINDOW = "align_c_old"  # 200 days old, fully linked — window control

P1 = "align_p1"
P2 = "align_p2"
P3 = "align_p3"  # only ever linked from the out-of-window choice
G1 = "align_g1"


@pytest.mark.asyncio
class TestChoicesAlignmentMetrics:
    """Principle/goal alignment must be read from edges, not from absent Choice fields."""

    @pytest_asyncio.fixture
    async def intelligence(self, neo4j_driver, clean_neo4j):
        """Seed six choices with a known edge layout and return the intelligence service."""
        now = datetime.now(UTC)
        in_window = (now - timedelta(days=10)).isoformat()
        out_window = (now - timedelta(days=200)).isoformat()

        async with neo4j_driver.session() as session:
            await session.run("MERGE (u:User {uid: $u})", u=USER)
            await session.run(
                """
                UNWIND $choices AS c
                CREATE (n:Entity:Choice {uid: c.uid, user_uid: $u, entity_type: 'choice',
                                         title: c.uid, status: 'active', domain: 'personal',
                                         created_at: c.created_at})
                """,
                u=USER,
                choices=[
                    {"uid": PRINCIPLE_ONLY, "created_at": in_window},
                    {"uid": GOAL_ONLY, "created_at": in_window},
                    {"uid": BOTH, "created_at": in_window},
                    {"uid": BARE, "created_at": in_window},
                    {"uid": GUIDED, "created_at": in_window},
                    {"uid": OUT_OF_WINDOW, "created_at": out_window},
                ],
            )
            await session.run(
                """
                UNWIND $principles AS p CREATE (n:Entity:Principle {uid: p, user_uid: $u})
                """,
                u=USER,
                principles=[P1, P2, P3],
            )
            await session.run("CREATE (n:Entity:Goal {uid: $g, user_uid: $u})", g=G1, u=USER)
            # p1 is linked from two in-window choices, p2 from one — so p1 wins the
            # most_common aggregation. p3 hangs off the out-of-window choice only.
            await session.run(
                """
                UNWIND $pairs AS e
                MATCH (c:Entity {uid: e[0]}), (p:Entity {uid: e[1]})
                CREATE (c)-[:INFORMED_BY_PRINCIPLE]->(p)
                """,
                pairs=[
                    [PRINCIPLE_ONLY, P1],
                    [BOTH, P1],
                    [BOTH, P2],
                    [OUT_OF_WINDOW, P3],
                ],
            )
            # The other direction: (Principle)-[:GUIDES_CHOICE]->(Choice), written from the
            # principle side by PrinciplesService.create_principle_link(link_type="choice").
            await session.run(
                """
                UNWIND $pairs AS e
                MATCH (p:Entity {uid: e[0]}), (c:Entity {uid: e[1]})
                CREATE (p)-[:GUIDES_CHOICE]->(c)
                """,
                pairs=[[P1, GUIDED], [P1, BOTH]],
            )
            await session.run(
                """
                UNWIND $pairs AS e
                MATCH (c:Entity {uid: e[0]}), (g:Entity {uid: e[1]})
                CREATE (c)-[:AFFECTS_GOAL]->(g)
                """,
                pairs=[[GOAL_ONLY, G1], [BOTH, G1], [OUT_OF_WINDOW, G1]],
            )

        # Backend and relationship service constructed as the composition root builds them
        # (services_bootstrap/_backends.py + create_common_sub_services), so the test
        # exercises the production label pair and the production registry config.
        backend = ChoicesBackend(neo4j_driver, NeoLabel.CHOICE, Choice, base_label=NeoLabel.ENTITY)
        # boundary: service-registry — mirrors the parameterisation the composition root
        # produces (activity_domain_config.py:330); annotated because mypy cannot infer the
        # type arguments from these constructor arguments.
        relationships: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
            backend=backend,
            config=ACTIVITY_DOMAIN_CONFIGS["choices"].relationship_config,
            graph_intel=None,
        )
        return ChoicesIntelligenceService(
            backend=backend,
            cross_domain_query=None,
            relationship_service=relationships,
        )

    async def test_principle_alignment_is_read_from_edges(self, intelligence):
        """3 of the 5 in-window choices carry a principle edge, in either direction."""
        result = await intelligence.get_decision_patterns(USER, days=30)
        assert result.is_ok, f"get_decision_patterns failed: {result}"

        metrics = result.value["decision_metrics"]
        assert metrics["total_choices"] == 5, "window control: the 200-day-old choice leaked in"
        assert metrics["principle_aligned_percentage"] == pytest.approx(3 / 5), (
            "0.0 = still reading the non-existent Choice.aligned_principles field; "
            "0.4 = only the outgoing INFORMED_BY_PRINCIPLE direction, dropping the "
            "GUIDES_CHOICE-only choice; 1.0 = counting every choice regardless of links"
        )

    async def test_goal_orientation_is_read_from_edges(self, intelligence):
        """2 of the 5 in-window choices carry an AFFECTS_GOAL edge. Pre-fix: 0.0."""
        result = await intelligence.get_decision_patterns(USER, days=30)

        assert result.value["decision_metrics"]["goal_oriented_percentage"] == pytest.approx(0.4)

    async def test_principle_alignment_score_tracks_the_percentage(self, intelligence):
        """decision_quality.principle_alignment_score is the same ratio. Pre-fix: 0.0."""
        result = await intelligence.get_decision_patterns(USER, days=30)

        quality = result.value["decision_quality"]
        assert quality["principle_alignment_score"] == pytest.approx(3 / 5)

    async def test_strategic_band_is_no_longer_pinned_to_tactical(self, intelligence):
        """The band is derived from goal_oriented_percentage, so it was always 'tactical'.

        At 0.5 the band is "balanced" — the assertion that matters is that the band can
        now move off the floor at all.
        """
        result = await intelligence.get_decision_patterns(USER, days=30)

        assert result.value["patterns"]["strategic_vs_tactical"] == "balanced"

    async def test_most_common_principle_is_aggregated(self, intelligence):
        """p1 is linked from three in-window choices, p2 from one. Pre-fix: hardcoded None."""
        result = await intelligence.get_decision_patterns(USER, days=30)

        assert result.value["patterns"]["most_common_principle"] == P1

    async def test_alignment_read_stays_inside_the_window(self, intelligence):
        """Widening to 365 days admits the fully-linked old choice and moves every metric."""
        wide = await intelligence.get_decision_patterns(USER, days=365)

        metrics = wide.value["decision_metrics"]
        assert metrics["total_choices"] == 6
        assert metrics["principle_aligned_percentage"] == pytest.approx(4 / 6)
        assert metrics["goal_oriented_percentage"] == pytest.approx(3 / 6)

    async def test_both_directions_union_without_double_counting(self, intelligence):
        """`align_c_both` carries p1 in *both* directions — it must appear once.

        The public dict only exposes the winner of the aggregation, so this reads the
        helper directly. Without the dedupe p1 would be counted twice for this one choice,
        inflating the most-common tally against a principle linked only one way.
        """
        links, _goals = (
            await intelligence._fetch_alignment_links([BOTH, GUIDED, PRINCIPLE_ONLY, BARE])
        ).value

        # Compared as sets plus a length check: the dedupe is what is under test, and the
        # order inside each list comes from Neo4j's collect(), which is not guaranteed.
        assert sorted(links[BOTH]) == [P1, P2]
        assert len(links[BOTH]) == 2, "p1 double-counted across the two edge directions"
        assert links[GUIDED] == [P1], "incoming GUIDES_CHOICE direction not read"
        assert links[PRINCIPLE_ONLY] == [P1]
        assert links[BARE] == []

    async def test_service_refuses_to_construct_without_relationships(self, neo4j_driver):
        """No relationship service is a wiring bug, and it is caught at construction.

        Every metric this service reports is a graph read, so without the relationship
        service each one returns an empty result indistinguishable from a real zero — the
        defect this module was rewritten to remove. `_require_relationships = True` makes
        `BaseAnalyticsService` refuse the construction, rather than letting four methods
        each invent their own degraded answer.

        Failing here rather than at read time also matters because
        `analyze_learning_patterns` is route-reachable (`choices_api.py:191`): a read-time
        raise would turn a mis-wired service into a 500 on a live route.
        """
        backend = ChoicesBackend(neo4j_driver, NeoLabel.CHOICE, Choice, base_label=NeoLabel.ENTITY)

        with pytest.raises(ValueError, match="requires relationship_service"):
            ChoicesIntelligenceService(backend=backend, cross_domain_query=None)

    async def test_unlinked_user_still_reports_zero(self, intelligence, neo4j_driver):
        """A choice with no edges reports 0.0 — the fix must not manufacture alignment."""
        other = "user_choice_alignment_empty"
        async with neo4j_driver.session() as session:
            await session.run("MERGE (u:User {uid: $u})", u=other)
            await session.run(
                """
                CREATE (n:Entity:Choice {uid: 'align_c_lonely', user_uid: $u,
                                         entity_type: 'choice', title: 'lonely',
                                         status: 'active', domain: 'personal',
                                         created_at: $c})
                """,
                u=other,
                c=(datetime.now(UTC) - timedelta(days=3)).isoformat(),
            )

        result = await intelligence.get_decision_patterns(other, days=30)

        metrics = result.value["decision_metrics"]
        assert metrics["total_choices"] == 1
        assert metrics["principle_aligned_percentage"] == 0.0
        assert metrics["goal_oriented_percentage"] == 0.0
        assert result.value["patterns"]["most_common_principle"] is None
        assert result.value["patterns"]["strategic_vs_tactical"] == "tactical"
