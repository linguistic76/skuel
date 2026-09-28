"""The unchosen-"UTC" clear, census and write, against a real Neo4j.

``scripts/migrations/clear_unchosen_utc_timezone_2026_09.py`` sets six users'
stored zone from ``"UTC"`` to null, keyed by uid. Its census stops unless the
``"UTC"`` users are exactly the six; its write is one transaction of
compare-and-sets on the whole ``preferences`` string, so a row that changed
since the census rolls every row back.

Users are seeded through the real writer (``UserBackend.create_user``) holding
``"UTC"``, and each test reads the stored JSON back to pin its premise. The
shared test graph keeps User nodes across tests, so the six here are test uids
handed to the census as its expected set — ``main()`` hands it the module's
six the same way.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import sys
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from adapters.persistence.neo4j.user_backend import UserBackend
from core.models.user import create_user

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "scripts/migrations/clear_unchosen_utc_timezone_2026_09.py"
)
_RUN = uuid.uuid4().hex[:6]
SIX = frozenset(f"user_tzclear{i}_{_RUN}" for i in range(6))
CHOOSER = f"user_tzclear_bkk_{_RUN}"
FRESH = f"user_tzclear_fresh_{_RUN}"
STRAY = f"user_tzclear_stray_{_RUN}"


def _load() -> ModuleType:
    """Import the script by path (``scripts/`` is not a package).

    Registered in ``sys.modules`` before it runs: ``@dataclass`` resolves the
    module's annotations through it.
    """
    spec = importlib.util.spec_from_file_location("clear_unchosen_utc_timezone", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


migration = _load()


async def _seed(neo4j_driver, uid: str, timezone: str | None) -> None:
    """One user, written by the real writer, holding ``timezone``."""
    username = uid.removeprefix("user_")
    user = create_user(username=username, email=f"{username}@example.com")
    user = dataclasses.replace(
        user, preferences=dataclasses.replace(user.preferences, timezone=timezone, theme="dark")
    )
    created = await UserBackend(neo4j_driver).create_user(user)
    assert created.is_ok, f"create_user failed: {created.error}"


async def _stored(neo4j_driver, uid: str) -> dict[str, Any]:
    async with neo4j_driver.session() as session:
        record = await (
            await session.run(
                "MATCH (u:User {uid: $uid}) RETURN u.preferences AS preferences", uid=uid
            )
        ).single()
    assert record is not None
    assert isinstance(record["preferences"], str), "User.preferences is stored as a JSON string"
    return json.loads(record["preferences"])


async def _unreadable_user(neo4j_driver) -> None:
    # No writer produces this: the census must stop on it, not skip it.
    async with neo4j_driver.session() as session:
        await session.run("CREATE (:User {uid: $uid, preferences: 'not json'})", uid=STRAY)


@pytest.fixture
async def graph(neo4j_driver):
    """The six on "UTC", one user who chose Bangkok, one who never chose."""
    for uid in SIX:
        await _seed(neo4j_driver, uid, "UTC")
    await _seed(neo4j_driver, CHOOSER, "Asia/Bangkok")
    await _seed(neo4j_driver, FRESH, None)
    yield
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (u:User) WHERE u.uid IN $uids DETACH DELETE u",
            uids=[*SIX, CHOOSER, FRESH, STRAY],
        )


async def test_the_census_finds_the_six_and_the_write_clears_only_their_zone(
    graph, neo4j_driver
) -> None:
    before = {uid: await _stored(neo4j_driver, uid) for uid in SIX}
    assert {prefs["timezone"] for prefs in before.values()} == {"UTC"}

    census = await migration.run_census(neo4j_driver, SIX)
    assert census.stops == []
    assert census.utc_uids == SIX
    assert census.others[CHOOSER] == "Asia/Bangkok"
    assert census.others[FRESH] == "null"

    assert await migration.clear(neo4j_driver, census.utc) == []

    for uid in SIX:
        after = await _stored(neo4j_driver, uid)
        assert after == {**before[uid], "timezone": None}, "only the zone changes"
        assert after["theme"] == "dark"
    assert (await _stored(neo4j_driver, CHOOSER))["timezone"] == "Asia/Bangkok"
    assert (await _stored(neo4j_driver, FRESH))["timezone"] is None
    assert (await migration.run_census(neo4j_driver, SIX)).done


async def test_utc_outside_the_six_stops_the_census(graph, neo4j_driver) -> None:
    await _seed(neo4j_driver, STRAY, "UTC")
    census = await migration.run_census(neo4j_driver, SIX)
    assert not census.done
    assert census.stops == [f'"UTC" outside the six (a choice to keep?): {STRAY}']


async def test_one_of_the_six_not_on_utc_stops_the_census(graph, neo4j_driver, user_service):
    moved = min(SIX)
    await user_service.update_preferences(moved, {"timezone": "Asia/Bangkok"})
    census = await migration.run_census(neo4j_driver, SIX)
    assert census.stops == [f'of the six, not holding "UTC": {moved}=Asia/Bangkok']


async def test_unreadable_preferences_stop_the_census(graph, neo4j_driver) -> None:
    await _unreadable_user(neo4j_driver)
    census = await migration.run_census(neo4j_driver, SIX)
    assert census.stops == [f"unreadable preferences: {STRAY}"]


async def test_a_blank_stored_zone_is_no_choice(graph, neo4j_driver) -> None:
    await _seed(neo4j_driver, STRAY, "")
    assert (await _stored(neo4j_driver, STRAY))["timezone"] == ""
    census = await migration.run_census(neo4j_driver, SIX)
    assert census.others[STRAY] == "blank"
    assert census.stops == []


async def test_a_row_changed_since_the_census_rolls_the_whole_write_back(
    graph, neo4j_driver, user_service
) -> None:
    census = await migration.run_census(neo4j_driver, SIX)
    assert census.stops == []
    changed = max(SIX)
    await user_service.update_preferences(changed, {"theme": "light"})  # after the census

    assert await migration.clear(neo4j_driver, census.utc) == [changed]

    for uid in SIX:
        assert (await _stored(neo4j_driver, uid))["timezone"] == "UTC", "nothing was written"


async def test_a_census_that_finds_the_six_cleared_still_stops_on_an_unreadable_row(
    graph, neo4j_driver
) -> None:
    census = await migration.run_census(neo4j_driver, SIX)
    assert await migration.clear(neo4j_driver, census.utc) == []
    await _unreadable_user(neo4j_driver)

    after = await migration.run_census(neo4j_driver, SIX)
    assert after.done, "the six are at null"
    assert after.stops == [f"unreadable preferences: {STRAY}"], "and the census still fails"


class _Borrowed:
    """The session's driver lent to ``main()``, whose ``finally`` closes what it opened."""

    def __init__(self, driver: Any) -> None:
        self._driver = driver

    def __getattr__(self, name: str) -> Any:
        return getattr(self._driver, name)

    async def close(self) -> None:
        return None


class _Connection:
    def __init__(self, driver: Any) -> None:
        self._driver = driver

    async def connect(self) -> _Borrowed:
        return _Borrowed(self._driver)


@pytest.fixture
def cli(neo4j_driver, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Run the script's ``main()`` against the test graph and the test six: ``(exit, output)``."""
    import adapters.persistence.neo4j.neo4j_connection as connection

    def connection_to_the_test_graph() -> _Connection:
        return _Connection(neo4j_driver)

    monkeypatch.setattr(connection, "Neo4jConnection", connection_to_the_test_graph)
    monkeypatch.setattr(migration, "NEVER_CHOSEN", SIX)

    async def run(*args: str) -> tuple[int, str]:
        monkeypatch.setattr(sys, "argv", [SCRIPT.name, *args])
        code = await migration.main()
        return code, capsys.readouterr().out

    return run


async def _zones(neo4j_driver) -> set[Any]:
    return {(await _stored(neo4j_driver, uid))["timezone"] for uid in SIX}


async def test_the_command_line_census_then_confirm_then_nothing_to_clear(
    graph, neo4j_driver, cli
) -> None:
    code, out = await cli()
    assert code == 0
    assert "Would clear: 6 user(s)" in out and "CENSUS ONLY" in out
    assert await _zones(neo4j_driver) == {"UTC"}

    code, out = await cli("--confirm")
    assert code == 0
    assert "Cleared 6 user(s) in one transaction." in out
    assert "OK: the six follow SKUEL_TIMEZONE." in out
    assert await _zones(neo4j_driver) == {None}

    code, out = await cli()
    assert code == 0
    assert "Nothing to clear." in out


async def test_the_command_line_refuses_a_stopped_census(graph, neo4j_driver, cli) -> None:
    await _seed(neo4j_driver, STRAY, "UTC")
    code, out = await cli("--confirm")
    assert code == 2
    assert "REFUSED: nothing written." in out
    assert await _zones(neo4j_driver) == {"UTC"}


async def test_the_command_line_never_reports_done_over_an_unreadable_row(
    graph, neo4j_driver, cli
) -> None:
    assert (await cli("--confirm"))[0] == 0
    await _unreadable_user(neo4j_driver)

    code, out = await cli()
    assert code == 2
    assert "REFUSED: nothing written." in out
    assert "Nothing to clear." not in out
