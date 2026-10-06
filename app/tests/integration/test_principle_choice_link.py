"""A choice's informers are read by kind, and a link is removed by kind.

``INFORMS_CHOICE`` points into a choice from three kinds of node: a principle, a habit
and a PathStep (its ``choice_uids``). Every reader of the choice's principles names
the kind it reads, so a habit or a PathStep is never counted as a principle.

One choice informed by a habit, a principle and a published PathStep. The principle
informs two more choices (three in all); the habit and the PathStep each inform three
more (four in all), so a reader that counted them as principles would rank one of them
above the principle. Each read through every path that lists a choice's principles:

- the keyed reads (``informing_principles``, ``informing_habits``), one choice at a
  time and batched;
- ``ChoiceRelationships.fetch`` and ``PrincipleRelationships.fetch``;
- the typed cross-domain context (``ChoiceCrossContext.principles``) and the raw
  buckets;
- the choice page and the principle page;
- the rich-context statement's choice row (``guiding_principles``) and principle row
  (``guided_choices``);
- the choice-alignment metric (``_fetch_alignment_links``, ``get_decision_patterns``);
- the ZPD choice-adherence query (``get_choice_principle_adherence``);
- the principle's choice-effectiveness stats (``GET /api/principles/choice-effectiveness``).

Search enrichment emitting no shared-neighbour placeholder (a choice's
``related_choices``) is held by tests/unit/test_graph_enrichment_shared_neighbour.py.

The transitive case: a habit that embodies a principle that informs a choice does not
itself inform the choice, and a principle that inspires a habit that informs a choice
does not itself inform that choice.

Unlinking: ``ChoicesService.unlink_choice_from_principle`` removes a principle's link
and the ``informing_habits`` keyed delete a habit's; neither removes the other kind's,
whichever uid it is handed.

The app runs bootstrapped over its own graph (``tests/integration/_activity_link_rig.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.user_context_queries import UserContextQueryExecutor
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.services.choices.choice_relationships import ChoiceRelationships
from core.services.principles.principle_relationships import PrincipleRelationships
from tests.integration._activity_link_rig import (
    create,
    edges_between,
    seed_published_path_step,
    signed_in_client,
    under_heading,
    write_edge,
)

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

MARK = "zzzpclink"
CALLER = f"user_{MARK}"

INFORMS_CHOICE = RelationshipName.INFORMS_CHOICE.value
EMBODIES_PRINCIPLE = RelationshipName.EMBODIES_PRINCIPLE.value
INSPIRES_HABIT = RelationshipName.INSPIRES_HABIT.value

PRINCIPLES_HEADING = "Principles that inform this choice"
HABITS_HEADING = "Habits that inform this choice"
PRINCIPLE_PAGE_HEADING = "Choices this principle informs"


@dataclass(frozen=True)
class Env:
    client: httpx.AsyncClient
    services: Any  # boundary: the composed Services container
    driver: AsyncDriver


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def env(
    skuel_app: Any,  # boundary: fasthtml-app
) -> AsyncIterator[Env]:
    async with signed_in_client(skuel_app, CALLER, MARK) as client:
        yield Env(
            client=client,
            services=skuel_app.state.services,
            driver=skuel_app.state.services.neo4j_driver,
        )


async def _related(
    service: Any,  # boundary: a composed domain facade (choices, principles, habits)
    key: str,
    uid: str,
) -> list[str]:
    read = await service.relationships.get_related_uids(key, uid)
    assert read.is_ok, read
    return list(read.value)


# ---------------------------------------------------------------------------
# One choice, three kinds of informer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Informed:
    """One choice and its three informers, plus the other choices each informs.

    ``principle_only``: two choices the principle alone informs (three with ``choice``).
    ``non_principle_only``: three choices the habit and the PathStep inform and no
    principle does (four each with ``choice``).
    """

    choice: str
    habit: str
    principle: str
    step: str
    principle_only: tuple[str, ...]
    non_principle_only: tuple[str, ...]

    choice_title = f"{MARK} informed choice"
    habit_title = f"{MARK} informing habit"
    principle_title = f"{MARK} informing principle"
    step_title = f"{MARK} informing path step"

    @property
    def principles_choices(self) -> list[str]:
        return sorted((self.choice, *self.principle_only))


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def informed(env: Env) -> Informed:
    found = Informed(
        choice=await create(env.client, "choices", Informed.choice_title),
        habit=await create(env.client, "habits", Informed.habit_title),
        principle=await create(env.client, "principles", Informed.principle_title),
        step=f"ps.{MARK}.informer",
        principle_only=tuple(
            [await create(env.client, "choices", f"{MARK} principle-only {n}") for n in (1, 2)]
        ),
        non_principle_only=tuple(
            [await create(env.client, "choices", f"{MARK} habit-only {n}") for n in (1, 2, 3)]
        ),
    )
    await seed_published_path_step(env.driver, found.step, Informed.step_title)
    for informer in (found.habit, found.principle, found.step):
        await write_edge(env.driver, informer, INFORMS_CHOICE, found.choice)
    for choice in found.principle_only:
        await write_edge(env.driver, found.principle, INFORMS_CHOICE, choice)
    for choice in found.non_principle_only:
        await write_edge(env.driver, found.habit, INFORMS_CHOICE, choice)
        await write_edge(env.driver, found.step, INFORMS_CHOICE, choice)
    return found


async def test_the_seed_holds_three_informers_of_three_kinds(env: Env, informed: Informed) -> None:
    """The premise every test below reads against: all three edges are stored."""
    async with env.driver.session() as session:
        result = await session.run(
            """
            MATCH (s)-[:INFORMS_CHOICE]->(:Choice {uid: $choice})
            RETURN s.uid AS uid, [l IN labels(s) WHERE l <> 'Entity'] AS kinds, s.entity_type AS t
            """,
            choice=informed.choice,
        )
        stored = {row["uid"]: (row["kinds"], row["t"]) async for row in result}

    assert stored == {
        informed.habit: (["Habit"], "habit"),
        informed.principle: (["Principle"], "principle"),
        informed.step: (["PathStep"], "path_step"),
    }


async def test_informing_principles_reads_the_principle_only(env: Env, informed: Informed) -> None:
    assert await _related(env.services.choices, "informing_principles", informed.choice) == [
        informed.principle
    ]


async def test_informing_habits_reads_the_habit_only(env: Env, informed: Informed) -> None:
    assert await _related(env.services.choices, "informing_habits", informed.choice) == [
        informed.habit
    ]


@pytest.mark.parametrize(
    ("key", "kind"), [("informing_principles", "principle"), ("informing_habits", "habit")]
)
async def test_the_batched_read_agrees_with_the_single_read(
    env: Env, informed: Informed, key: str, kind: str
) -> None:
    uids = [informed.choice, *informed.non_principle_only]

    batched = await env.services.choices.relationships.batch_get_related_uids(key, uids)

    assert batched.is_ok, batched
    assert batched.value.get(informed.choice, []) == [getattr(informed, kind)]
    expected_elsewhere = [informed.habit] if kind == "habit" else []
    for choice in informed.non_principle_only:
        assert batched.value.get(choice, []) == expected_elsewhere


async def test_the_principle_reads_its_three_choices_and_the_habit_reads_its_four(
    env: Env, informed: Informed
) -> None:
    principles_choices = await _related(
        env.services.principles, "informed_choices", informed.principle
    )
    habits_choices = await _related(env.services.habits, "informed_choices", informed.habit)

    assert sorted(principles_choices) == informed.principles_choices
    assert sorted(habits_choices) == sorted((informed.choice, *informed.non_principle_only))


async def test_choice_relationships_fetch_separates_principles_from_habits(
    env: Env, informed: Informed
) -> None:
    fetched = await ChoiceRelationships.fetch(informed.choice, env.services.choices.relationships)

    assert fetched.informing_principle_uids == [informed.principle]
    assert fetched.informing_habit_uids == [informed.habit]
    assert fetched.is_principle_aligned()


async def test_a_choice_informed_only_by_a_habit_and_a_path_step_is_not_principle_aligned(
    env: Env, informed: Informed
) -> None:
    fetched = await ChoiceRelationships.fetch(
        informed.non_principle_only[0], env.services.choices.relationships
    )

    assert fetched.informing_principle_uids == []
    assert not fetched.is_principle_aligned()


async def test_principle_relationships_fetch_reads_the_informed_choices(
    env: Env, informed: Informed
) -> None:
    fetched = await PrincipleRelationships.fetch(
        informed.principle, env.services.principles.relationships
    )

    assert sorted(fetched.informed_choice_uids) == informed.principles_choices
    assert fetched.informs_choices()


async def test_the_typed_choice_context_lists_the_principle_only(
    env: Env, informed: Informed
) -> None:
    typed = await env.services.choices.relationships.get_cross_domain_context_typed(informed.choice)

    assert typed.is_ok, typed
    assert [principle.uid for principle in typed.value.principles] == [informed.principle]


async def test_the_raw_choice_context_puts_each_kind_in_its_own_bucket(
    env: Env, informed: Informed
) -> None:
    raw = await env.services.choices.relationships.get_cross_domain_context(
        informed.choice, depth=1
    )

    assert raw.is_ok, raw
    buckets = {
        name: [entry["uid"] for entry in entries]
        for name, entries in raw.value.items()
        if isinstance(entries, list) and entries
    }
    assert buckets == {
        "informing_principles": [informed.principle],
        "informing_habits": [informed.habit],
    }


async def test_the_choice_page_lists_each_informer_under_its_own_heading(
    env: Env, informed: Informed
) -> None:
    response = await env.client.get(f"/choices/detail/content?uid={informed.choice}")
    assert response.status_code == 200, response.text[:500]
    page = response.text

    principles = under_heading(page, PRINCIPLES_HEADING)
    habits = under_heading(page, HABITS_HEADING)

    assert Informed.principle_title in principles
    assert Informed.habit_title not in principles
    assert Informed.habit_title in habits
    assert Informed.principle_title not in habits
    assert Informed.step_title not in page, "a PathStep informer is under no heading"
    assert page.count(PRINCIPLES_HEADING) == 1, "one principle view on the page"


async def test_the_principle_page_lists_its_three_choices(env: Env, informed: Informed) -> None:
    response = await env.client.get(f"/principles/detail/content?uid={informed.principle}")
    assert response.status_code == 200, response.text[:500]

    choices = under_heading(response.text, PRINCIPLE_PAGE_HEADING)

    assert Informed.choice_title in choices
    assert f"{MARK} principle-only 1" in choices
    assert f"{MARK} principle-only 2" in choices
    assert f"{MARK} habit-only" not in choices


def _rows_by_uid(
    rows: list[dict[str, Any]],  # boundary: rich-context rows
) -> dict[str, dict[str, Any]]:
    return {row["entity"]["uid"]: row["graph_context"] for row in rows}


async def test_the_rich_context_choice_row_lists_the_principle_only(
    env: Env, informed: Informed
) -> None:
    mega = await UserContextQueryExecutor(Neo4jQueryExecutor(env.driver)).execute_mega_query(
        UserUID(CALLER)
    )

    assert mega.is_ok, mega
    choices = _rows_by_uid(mega.value["entities"]["choices"])
    assert choices[informed.choice]["guiding_principles"] == [
        {"uid": informed.principle, "title": Informed.principle_title}
    ]
    for choice in informed.non_principle_only:
        assert choices[choice]["guiding_principles"] == []


async def test_the_rich_context_principle_row_lists_its_three_choices(
    env: Env, informed: Informed
) -> None:
    mega = await UserContextQueryExecutor(Neo4jQueryExecutor(env.driver)).execute_mega_query(
        UserUID(CALLER)
    )

    assert mega.is_ok, mega
    principles = _rows_by_uid(mega.value["entities"]["principles"])
    guided = principles[informed.principle]["guided_choices"]
    assert sorted(choice["uid"] for choice in guided) == informed.principles_choices


async def test_the_alignment_links_count_the_principle_only(env: Env, informed: Informed) -> None:
    choices = [informed.choice, *informed.principle_only, *informed.non_principle_only]

    links = await env.services.choices.intelligence._fetch_alignment_links(choices)

    assert links.is_ok, links
    principle_links, _goal_links = links.value
    assert principle_links == {
        informed.choice: [informed.principle],
        **{choice: [informed.principle] for choice in informed.principle_only},
        **{choice: [] for choice in informed.non_principle_only},
    }


async def test_the_decision_patterns_name_the_principle_most_common(
    env: Env, informed: Informed
) -> None:
    """The habit and the PathStep each inform four choices; the principle three.

    A reader that counted them as principles would name one of them.
    """
    patterns = await env.services.choices.get_decision_patterns(UserUID(CALLER), days=30)

    assert patterns.is_ok, patterns
    assert patterns.value["patterns"]["most_common_principle"] == informed.principle


async def test_the_adherence_query_reads_the_principle_only(env: Env, informed: Informed) -> None:
    backend = CrossDomainBackend(Neo4jQueryExecutor(env.driver))

    adherence = await backend.get_choice_principle_adherence(CALLER, 30)

    assert adherence.is_ok, adherence
    (row,) = adherence.value
    details = {detail["choice_uid"]: detail["principles"] for detail in row["choice_details"]}
    assert details[informed.choice] == [informed.principle]
    for choice in informed.principle_only:
        assert details[choice] == [informed.principle]
    for choice in informed.non_principle_only:
        assert details[choice] == []


async def test_the_choice_effectiveness_counts_the_principles_three_choices(
    env: Env, informed: Informed
) -> None:
    response = await env.client.get(
        f"/api/principles/choice-effectiveness?uid={informed.principle}"
    )

    assert response.status_code == 200, response.text
    assert response.json()["total_choices_guided"] == len(informed.principles_choices)


# ---------------------------------------------------------------------------
# The transitive case
# ---------------------------------------------------------------------------


def _bucket(
    raw: dict[str, Any],  # boundary: raw cross-domain context
    name: str,
) -> dict[str, int]:
    """One context bucket as uid -> distance."""
    return {entry["uid"]: entry["distance"] for entry in raw[name]}


async def test_a_habit_does_not_inform_the_choice_its_principle_informs(env: Env) -> None:
    habit = await create(env.client, "habits", f"{MARK} transitive habit")
    principle = await create(env.client, "principles", f"{MARK} embodied principle")
    reached_choice = await create(env.client, "choices", f"{MARK} choice the principle informs")
    own_choice = await create(env.client, "choices", f"{MARK} choice the habit informs")
    await write_edge(env.driver, habit, EMBODIES_PRINCIPLE, principle)
    await write_edge(env.driver, principle, INFORMS_CHOICE, reached_choice)
    await write_edge(env.driver, habit, INFORMS_CHOICE, own_choice)
    assert await edges_between(env.driver, habit, reached_choice) == []

    context = await env.services.habits.relationships.get_cross_domain_context(habit, depth=2)

    assert context.is_ok, context
    assert _bucket(context.value, "informed_choices") == {own_choice: 1}
    assert _bucket(context.value, "embodied_principles") == {principle: 1}


async def test_a_principle_does_not_inform_the_choice_its_habit_informs(env: Env) -> None:
    principle = await create(env.client, "principles", f"{MARK} transitive principle")
    habit = await create(env.client, "habits", f"{MARK} inspired habit")
    reached_choice = await create(env.client, "choices", f"{MARK} choice the habit alone informs")
    own_choice = await create(env.client, "choices", f"{MARK} choice the principle informs")
    await write_edge(env.driver, principle, INSPIRES_HABIT, habit)
    await write_edge(env.driver, habit, INFORMS_CHOICE, reached_choice)
    await write_edge(env.driver, principle, INFORMS_CHOICE, own_choice)
    assert await edges_between(env.driver, principle, reached_choice) == []

    raw = await env.services.principles.relationships.get_cross_domain_context(principle, depth=2)
    typed = await env.services.principles.relationships.get_cross_domain_context_typed(
        principle, depth=2
    )

    assert raw.is_ok, raw
    assert _bucket(raw.value, "informed_choices") == {own_choice: 1}
    assert _bucket(raw.value, "inspired_habits") == {habit: 1}
    assert typed.is_ok, typed
    assert [choice.uid for choice in typed.value.choices] == [own_choice]


# ---------------------------------------------------------------------------
# Unlinking
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pair:
    choice: str
    habit: str
    principle: str


async def _choice_with_a_habit_and_a_principle(env: Env, name: str) -> Pair:
    """A choice informed by one habit (seeded) and one principle (the choice's door)."""
    pair = Pair(
        choice=await create(env.client, "choices", f"{MARK} {name} choice"),
        habit=await create(env.client, "habits", f"{MARK} {name} habit"),
        principle=await create(env.client, "principles", f"{MARK} {name} principle"),
    )
    await write_edge(env.driver, pair.habit, INFORMS_CHOICE, pair.choice)
    assert (await env.services.choices.link_choice_to_principle(pair.choice, pair.principle)).is_ok
    assert await _informers(env, pair) == ([pair.habit], [pair.principle], [pair.choice])
    return pair


async def _informers(env: Env, pair: Pair) -> tuple[list[str], list[str], list[str]]:
    """(the choice's habits, the choice's principles, the principle's choices), by keyed read."""
    return (
        await _related(env.services.choices, "informing_habits", pair.choice),
        await _related(env.services.choices, "informing_principles", pair.choice),
        await _related(env.services.principles, "informed_choices", pair.principle),
    )


async def test_unlinking_the_principle_removes_it_at_both_ends_and_keeps_the_habit(
    env: Env,
) -> None:
    pair = await _choice_with_a_habit_and_a_principle(env, "unlink-principle")

    unlinked = await env.services.choices.unlink_choice_from_principle(pair.choice, pair.principle)

    assert unlinked.is_ok, unlinked
    assert await _informers(env, pair) == ([pair.habit], [], [])
    assert await edges_between(env.driver, pair.principle, pair.choice) == []
    assert len(await edges_between(env.driver, pair.habit, pair.choice)) == 1


async def test_unlink_principle_handed_the_habit_removes_nothing(env: Env) -> None:
    pair = await _choice_with_a_habit_and_a_principle(env, "unlink-wrong-kind")

    unlinked = await env.services.choices.unlink_choice_from_principle(pair.choice, pair.habit)

    assert unlinked.is_ok, unlinked
    assert await _informers(env, pair) == ([pair.habit], [pair.principle], [pair.choice])
    assert len(await edges_between(env.driver, pair.habit, pair.choice)) == 1


async def test_the_habit_keyed_delete_handed_the_principle_removes_nothing(env: Env) -> None:
    pair = await _choice_with_a_habit_and_a_principle(env, "unlink-wrong-kind-mirror")

    deleted = await env.services.choices.relationships.delete_relationship(
        "informing_habits", pair.choice, pair.principle
    )

    assert deleted.is_ok, deleted
    assert await _informers(env, pair) == ([pair.habit], [pair.principle], [pair.choice])
    assert len(await edges_between(env.driver, pair.principle, pair.choice)) == 1


async def test_the_habit_keyed_delete_removes_the_habit_and_keeps_the_principle(
    env: Env,
) -> None:
    pair = await _choice_with_a_habit_and_a_principle(env, "unlink-habit")

    deleted = await env.services.choices.relationships.delete_relationship(
        "informing_habits", pair.choice, pair.habit
    )

    assert deleted.is_ok, deleted
    assert await _informers(env, pair) == ([], [pair.principle], [pair.choice])
    assert await edges_between(env.driver, pair.habit, pair.choice) == []
    assert len(await edges_between(env.driver, pair.principle, pair.choice)) == 1
