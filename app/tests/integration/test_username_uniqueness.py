"""A username names one account — the constraint holds it, not sign-up's lookup.

A user uid is generated, so no uid collision stops a second account on a taken
username any more than on a free one. Sign-up looks the name up first, but two
concurrent sign-ups both see it free; the ``User.title`` uniqueness constraint is
what refuses the second, and ``UserBackend.create_user`` answers that refusal as
sign-up answers a taken name. The create door is called directly here — the
racing second sign-up, past its lookup.
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.persistence.neo4j.user_backend import UserBackend
from core.models.user import create_user
from core.utils.result_simplified import ErrorCategory

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

MARK = "zzuniq"
NAME = f"{MARK}name"


async def _rows(driver: Any, query: str, **params: Any) -> list[Any]:  # boundary: cypher-params
    async with driver.session() as session:
        result = await session.run(query, params)
        return [record async for record in result]


@pytest.fixture
async def users(skuel_app: Any) -> Any:  # boundary: fasthtml-app
    driver = skuel_app.state.services.neo4j_driver
    yield UserBackend(driver), driver
    await _rows(
        driver,
        "MATCH (u:User) WHERE u.title STARTS WITH $mark OR u.email STARTS WITH $mark "
        "DETACH DELETE u",
        mark=MARK,
    )


async def test_the_username_is_constrained(users: Any) -> None:
    _, driver = users
    rows = await _rows(
        driver,
        "SHOW CONSTRAINTS YIELD labelsOrTypes, properties, type "
        "WHERE type = 'NODE_PROPERTY_UNIQUENESS' RETURN labelsOrTypes, properties",
    )
    assert (("User",), ("title",)) in {
        (tuple(row["labelsOrTypes"]), tuple(row["properties"])) for row in rows
    }


async def test_a_second_account_on_a_taken_username_is_refused_as_taken(users: Any) -> None:
    backend, driver = users
    first = await backend.create_user(create_user(NAME, f"{MARK}1@example.com"))
    assert first.is_ok, first

    second = await backend.create_user(create_user(NAME, f"{MARK}2@example.com"))

    assert second.is_error
    error = second.expect_error()
    assert error.category == ErrorCategory.VALIDATION
    assert error.details.get("field") == "username"
    held = await _rows(driver, "MATCH (u:User {title: $name}) RETURN u.uid AS uid", name=NAME)
    assert [row["uid"] for row in held] == [first.value.uid]


async def test_a_second_account_on_a_taken_email_is_refused_as_taken(users: Any) -> None:
    backend, _ = users
    first = await backend.create_user(create_user(f"{MARK}one", f"{MARK}same@example.com"))
    assert first.is_ok, first

    second = await backend.create_user(create_user(f"{MARK}two", f"{MARK}same@example.com"))

    assert second.is_error
    assert second.expect_error().details.get("field") == "email"
