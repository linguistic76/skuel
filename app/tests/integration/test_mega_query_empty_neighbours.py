"""
An entity with no neighbours projects an EMPTY list, not a phantom placeholder
=============================================================================

Cypher's ``collect()`` drops null *values*, but a **map literal is never null**
— only its fields are. So ``collect({uid: x.uid, …})`` over an OPTIONAL MATCH
that found nothing yields ``[{uid: null, …}]``: a ONE-element list meaning
"zero neighbours".

Every consumer that iterates was defensively guarding
(``if item and item.get("uid")``); every consumer that **counted** was silently
wrong. The live instance, measured 2026-08-28 on AuraDB before the fix: the
graph holds **no ``GUIDES_CHOICE`` edges at all**, and
``principle_guided_choice_counts`` reported **1 guided choice for each of the 2
principles**. Two lines above that count, the same block's loop was correctly
null-guarded.

#1171 fixed one site (``lp_steps``) and ruled the ~30 siblings could wait until
one of them was counted. This suite is the behavioural half of the sweep that
followed: the source-shape guard lives in
``tests/unit/test_mega_query_null_placeholders.py``, and these tests prove the
runtime consequence on a real graph — an entity with no neighbours, and a
positive control that neighbours still arrive.

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

import pytest

from core.utils.uid_generator import UIDGenerator

pytestmark = pytest.mark.asyncio


@pytest.mark.integration
class TestEmptyNeighbourProjections:
    async def test_a_principle_with_no_guided_choices_counts_zero_not_one(
        self, clean_neo4j, services, test_user
    ) -> None:
        """The defect that was live: no choices must not read as one choice.

        ``principle_guided_choice_counts`` is derived with ``len()`` over the
        raw projection, so the placeholder map counted as a real choice. With
        the projection guarded, a principle that guides nothing contributes no
        entry at all (``if guided_choices:`` is falsy on ``[]``).
        """
        driver = services.principles.core.backend.driver
        lonely = UIDGenerator.generate_random_uid("principle")

        await driver.execute_query(
            """
            MATCH (user:User {uid: $user_uid})
            CREATE (p:Entity:Principle {uid: $uid, title: 'Guides Nothing',
                                        entity_type: 'principle', status: 'active',
                                        user_uid: $user_uid})
            CREATE (user)-[:OWNS]->(p)
            """,
            {"uid": lonely, "user_uid": test_user.uid},
        )

        result = await services.users.get_rich_unified_context(test_user.uid)
        assert result.is_ok, f"rich context failed: {result.error}"
        counts = result.value.principle_guided_choice_counts or {}

        assert counts.get(lonely, 0) == 0, (
            f"a principle guiding NO choices reported {counts.get(lonely)!r} — the "
            "all-null placeholder map was counted as a real choice"
        )

    async def test_a_principle_with_one_guided_choice_still_counts_one(
        self, clean_neo4j, services, test_user
    ) -> None:
        """Positive control — the guard did not simply empty the projection.

        Without this, a projection that dropped EVERY row would satisfy the
        test above and look like a working fix.
        """
        driver = services.principles.core.backend.driver
        principle = UIDGenerator.generate_random_uid("principle")
        choice = UIDGenerator.generate_random_uid("choice")

        await driver.execute_query(
            """
            MATCH (user:User {uid: $user_uid})
            CREATE (p:Entity:Principle {uid: $p_uid, title: 'Guides One',
                                        entity_type: 'principle', status: 'active',
                                        user_uid: $user_uid})
            CREATE (c:Entity:Choice {uid: $c_uid, title: 'A Real Choice',
                                     entity_type: 'choice', status: 'active',
                                     user_uid: $user_uid})
            CREATE (user)-[:OWNS]->(p)
            CREATE (user)-[:OWNS]->(c)
            CREATE (p)-[:GUIDES_CHOICE]->(c)
            """,
            {"p_uid": principle, "c_uid": choice, "user_uid": test_user.uid},
        )

        result = await services.users.get_rich_unified_context(test_user.uid)
        assert result.is_ok, f"rich context failed: {result.error}"
        counts = result.value.principle_guided_choice_counts or {}

        assert counts.get(principle) == 1, (
            f"a principle guiding exactly one choice reported {counts.get(principle)!r}"
        )

    async def test_neighbourless_sub_collections_are_empty_lists(
        self, clean_neo4j, services, test_user
    ) -> None:
        """The general shape, across domains — no projection is a 1-list of nulls.

        Asserts the RULE rather than one field: every list-of-maps the rich
        context exposes either is empty or has a real ``uid`` in element 0.
        A phantom is exactly the case that satisfies neither.
        """
        driver = services.tasks.core.backend.driver
        task = UIDGenerator.generate_random_uid("task")
        await driver.execute_query(
            """
            MATCH (user:User {uid: $user_uid})
            CREATE (t:Entity:Task {uid: $uid, title: 'No Neighbours At All',
                                   entity_type: 'task', status: 'active',
                                   user_uid: $user_uid})
            CREATE (user)-[:OWNS]->(t)
            """,
            {"uid": task, "user_uid": test_user.uid},
        )

        result = await services.users.get_rich_unified_context(test_user.uid)
        assert result.is_ok, f"rich context failed: {result.error}"

        # entities_rich is THE rich projection map, keyed by domain (ADR: the
        # entities_rich unification) — walk every domain, not just tasks, so
        # the assertion covers the class the sweep touched.
        phantoms: list[str] = []
        examined = 0
        for domain, items in (result.value.entities_rich or {}).items():
            for item in items or []:
                examined += 1
                for key, value in (item.get("graph_context") or {}).items():
                    if (
                        isinstance(value, list)
                        and value
                        and isinstance(value[0], dict)
                        and value[0].get("uid") is None
                    ):
                        phantoms.append(f"{domain}.{key} (len {len(value)})")

        assert examined, "no rich entities projected — the assertion would pass vacuously"
        assert phantoms == [], (
            "a neighbourless entity carries placeholder maps in its graph_context — "
            f"these read as one neighbour to any consumer that counts: {phantoms}"
        )
