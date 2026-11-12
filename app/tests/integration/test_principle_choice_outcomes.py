"""How the choices a principle informs turned out: one tally, read three ways.

``PrincipleChoiceOutcomes`` is built from one Cypher tally
(``build_choice_outcome_tally``) by two statements: the principle's own read
(``PrinciplesBackend.get_principle_choice_outcomes``, behind the principle page's
``/principles/choice-outcomes`` section and ``GET /api/principles/choice-effectiveness``)
and the rich context's ``principle_choice_outcomes`` registry entry
(``principle_guided_choice_counts``, ``principle_choice_satisfaction_avg``,
``principle_integration_score``). Each is read here over the same graph:

- one principle informs twelve of the caller's choices, three of them rated (5, 3, 4)
  and three created long before the context's window and completed; it also informs
  another user's choice, rated 1;
- a second principle informs two choices, neither rated; a third informs none;
- three more of the caller's choices are informed by no principle.

Twelve exceeds the ten the principles row's ``guided_choices`` display projection keeps,
and the completed old choices fall outside the window the context's choice entities are
read in: a count, an average or an integration score taken over either comes out wrong.

The app runs bootstrapped over its own graph (``tests/integration/_activity_link_rig.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from adapters.inbound.fasthtml_types import FastHTMLApp
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.user_context_queries import UserContextQueryExecutor
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.constants import SatisfactionScale
from core.models.relationship_names import RelationshipName
from core.models.user.user import User
from core.services.user.unified_user_context import RichUserContext
from core.services.user.user_context_builder import UserContextBuilder
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import create, signed_in_client, write_edge

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx
    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzpcoutcome"
CALLER = seed_user_uid(MARK)
OTHER = seed_user_uid(f"{MARK}-other")

INFORMS_CHOICE = RelationshipName.INFORMS_CHOICE.value

RATINGS = (5, 3, 4)
GUIDED = 12
OLD_COMPLETED = 3
QUIET_GUIDED = 2
UNINFORMED = 3


@dataclass(frozen=True)
class Seeded:
    client: httpx.AsyncClient
    driver: AsyncDriver
    principle: str
    quiet_principle: str
    lonely_principle: str


async def _seed_choices(driver: AsyncDriver, uids: list[str], cypher: str) -> None:
    async with driver.session() as session:
        await session.run(cypher, uids=uids)


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def seeded(skuel_app: FastHTMLApp) -> AsyncIterator[Seeded]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with signed_in_client(skuel_app, CALLER, MARK) as client:
        principle = await create(client, "principles", f"{MARK} guiding principle")
        quiet = await create(client, "principles", f"{MARK} unrated principle")
        lonely = await create(client, "principles", f"{MARK} principle guiding nothing")

        guided = [await create(client, "choices", f"{MARK} guided {n}") for n in range(GUIDED)]
        quiet_guided = [
            await create(client, "choices", f"{MARK} quiet {n}") for n in range(QUIET_GUIDED)
        ]
        for n in range(UNINFORMED):
            await create(client, "choices", f"{MARK} uninformed {n}")
        for choice in guided:
            await write_edge(driver, principle, INFORMS_CHOICE, choice)
        for choice in quiet_guided:
            await write_edge(driver, quiet, INFORMS_CHOICE, choice)

        async with driver.session() as session:
            for choice, rating in zip(guided, RATINGS, strict=False):
                await session.run(
                    "MATCH (c:Choice {uid: $uid}) SET c.satisfaction_score = $rating",
                    uid=choice,
                    rating=rating,
                )
        await _seed_choices(
            driver,
            guided[-OLD_COMPLETED:],
            """
            MATCH (c:Choice) WHERE c.uid IN $uids
            SET c.status = 'completed', c.created_at = datetime() - duration({days: 400})
            """,
        )
        foreign = f"choice.{MARK}-foreign"
        async with driver.session() as session:
            await session.run(
                """
                MERGE (u:User {uid: $other}) SET u.title = $other
                CREATE (c:Entity:Choice {uid: $uid, title: $uid, entity_type: 'choice',
                                         status: 'active', user_uid: $other,
                                         satisfaction_score: 1})
                CREATE (u)-[:OWNS]->(c)
                """,
                other=OTHER,
                uid=foreign,
            )
        await write_edge(driver, principle, INFORMS_CHOICE, foreign)

        yield Seeded(
            client=client,
            driver=driver,
            principle=principle,
            quiet_principle=quiet,
            lonely_principle=lonely,
        )
        async with driver.session() as session:
            await session.run("MATCH (u:User {uid: $uid}) DETACH DELETE u", uid=OTHER)


async def _rich_context(driver: AsyncDriver) -> RichUserContext:
    builder = UserContextBuilder(UserContextQueryExecutor(Neo4jQueryExecutor(driver)))
    built = await builder.build_rich_user_context(
        CALLER, User(uid=CALLER, title=CALLER, email=f"{CALLER}@example.test")
    )
    assert built.is_ok, built
    return built.value


MEAN = sum(RATINGS) / len(RATINGS)


async def test_the_context_counts_every_guided_choice_and_averages_the_rated(
    seeded: Seeded,
) -> None:
    context = await _rich_context(seeded.driver)

    assert context.get_principle_guided_choice_counts() == {
        seeded.principle: GUIDED,
        seeded.quiet_principle: QUIET_GUIDED,
    }
    assert context.get_principle_choice_satisfaction_avg() == {
        seeded.principle: pytest.approx(MEAN / SatisfactionScale.HIGHEST)
    }


async def test_the_integration_score_is_over_every_owned_choice(seeded: Seeded) -> None:
    context = await _rich_context(seeded.driver)

    owned = GUIDED + QUIET_GUIDED + UNINFORMED
    assert context.get_principle_integration_score() == pytest.approx(
        (GUIDED + QUIET_GUIDED) / owned
    )


async def test_the_json_door_reads_the_same_tally(seeded: Seeded) -> None:
    response = await seeded.client.get(
        f"/api/principles/choice-effectiveness?uid={seeded.principle}"
    )

    assert response.status_code == 200, response.text
    good = sum(1 for rating in RATINGS if rating >= SatisfactionScale.GOOD)
    assert response.json() == {
        "total_choices_guided": GUIDED,
        "choices_rated": len(RATINGS),
        "avg_satisfaction_score": round(MEAN / SatisfactionScale.HIGHEST, 3),
        "positive_outcome_rate": round(good / len(RATINGS), 3),
        "alignment_strength": round(MEAN / SatisfactionScale.HIGHEST * good / len(RATINGS), 3),
        "recommendation": "Continue using this principle for decision guidance",
    }


async def test_the_detail_page_loads_the_outcome_section(seeded: Seeded) -> None:
    response = await seeded.client.get(f"/principles/detail/content?uid={seeded.principle}")

    assert response.status_code == 200, response.text
    assert f"/principles/choice-outcomes?uid={seeded.principle}" in response.text


async def test_the_outcome_section_shows_the_rated_figures(seeded: Seeded) -> None:
    response = await seeded.client.get(f"/principles/choice-outcomes?uid={seeded.principle}")

    assert response.status_code == 200, response.text
    page = response.text
    assert "How its choices turned out" in page
    assert f"{MEAN:.1f} / {SatisfactionScale.HIGHEST}" in page
    assert ">12<" in page
    assert ">3<" in page
    assert "67%" in page


@pytest.mark.parametrize(
    ("which", "says"),
    [
        ("quiet_principle", "2 choices linked, none rated yet."),
        ("lonely_principle", "No choices are linked to this principle yet."),
    ],
)
async def test_the_outcome_section_says_what_is_missing(
    seeded: Seeded, which: str, says: str
) -> None:
    uid = seeded.quiet_principle if which == "quiet_principle" else seeded.lonely_principle

    response = await seeded.client.get(f"/principles/choice-outcomes?uid={uid}")

    assert response.status_code == 200, response.text
    assert says in response.text
    assert "/ 5" not in response.text


async def test_the_outcome_section_refuses_a_principle_the_caller_does_not_own(
    seeded: Seeded,
) -> None:
    response = await seeded.client.get(f"/principles/choice-outcomes?uid=principle.{MARK}-absent")

    assert response.status_code == 404, response.text
