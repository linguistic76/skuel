"""Every write to a user's account names the fields it changes (testcontainer Neo4j).

The preferences save (the Settings editor, and the vault-consent grant) applies its
patch to the preferences read under the user node's lock and writes ``preferences``
and the ``last_active_at`` stamp alone; reactivation writes ``is_active`` alone. So
two saves for one user serialize, and a password, role or deactivation another
writer commits meanwhile keeps the value that writer gave it. The admin users table
reads the account's ``last_login_at`` stamp. Mastering a Ku writes the ``MASTERED``
edge and leaves the user node as it was: concept counts are counted from those edges.

Wiring mirrors services_bootstrap: ``UserCoreService`` and
``UserProgressRecorderService`` over the production ``UserBackend``, the session
writers from ``SessionBackend``.
"""

from __future__ import annotations

import asyncio
import dataclasses

import pytest
import pytest_asyncio

from core.models.enums.user_enums import UserRole
from core.models.type_hints import UserUID
from core.models.user import UserPreferences, create_user
from core.services.admin_stats_service import AdminStatsService
from core.services.user.user_core_service import UserCoreService
from core.services.user.user_progress_recorder_service import UserProgressRecorderService
from core.utils.result_simplified import ErrorCategory
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

pytestmark = pytest.mark.asyncio(loop_scope="session")

_USER = seed_user_uid("account-writes")
_MISSING = seed_user_uid("account-writes-nobody")
_MASTERED_KU_UID = "ku.account-writes.mastered"
_TRIALS = 5

#: Four saves of four different fields, as four tabs (or a tab and the vault's
#: consent grant) would post them at once.
_CONCURRENT_PATCHES: tuple[dict[str, object], ...] = (
    {"theme": "dark"},
    {"vault_write_consent": True},
    {"weekly_task_goal": 42},
    {"language": "fr"},
)


@pytest_asyncio.fixture(loop_scope="session")
async def account(neo4j_driver):
    """A seeded user, the core service over the production backends, and teardown."""
    backends = build_production_backends(neo4j_driver)
    core = UserCoreService(user_repo=backends["users_backend"])
    user = dataclasses.replace(
        create_user("account_writes", "account-writes@example.com", password_hash="hash-before"),
        uid=_USER,
    )
    created = await backends["users_backend"].create_user(user)
    assert created.is_ok, f"seed failed: {created.error}"

    yield core, backends

    async with neo4j_driver.session() as session:
        await session.run("MATCH (u:User {uid: $uid}) DETACH DELETE u", uid=_USER)


async def _properties(neo4j_driver, user_uid: UserUID) -> dict[str, object]:
    async with neo4j_driver.session() as session:
        record = await (
            await session.run("MATCH (u:User {uid: $uid}) RETURN properties(u) AS p", uid=user_uid)
        ).single()
    assert record is not None
    return dict(record["p"])


def _changed(before: dict[str, object], after: dict[str, object]) -> set[str]:
    return {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}


async def _reset_preferences(neo4j_driver) -> None:
    """Store default preferences through the same serializer the backend uses."""
    from adapters.persistence.neo4j.neo4j_mapper import to_neo4j_patch
    from core.models.user.user import User

    stored = to_neo4j_patch({"preferences": UserPreferences()}, User)["preferences"]
    async with neo4j_driver.session() as session:
        await session.run("MATCH (u:User {uid: $uid}) SET u.preferences = $p", uid=_USER, p=stored)


async def _stamp_natively(neo4j_driver) -> None:
    """Store ``updated_at`` as the role and password writers do: a native ``datetime()``.

    The model reads it back as a ``datetime`` and the mapper writes that as an ISO
    string, so a write that sends the whole model back changes it.
    """
    async with neo4j_driver.session() as session:
        await session.run("MATCH (u:User {uid: $uid}) SET u.updated_at = datetime()", uid=_USER)


async def test_preferences_save_writes_preferences_and_its_stamp_alone(neo4j_driver, account):
    core, _ = account
    await _stamp_natively(neo4j_driver)
    before = await _properties(neo4j_driver, _USER)

    saved = await core.update_preferences(_USER, {"weekly_task_goal": 15})

    assert saved.is_ok, f"save failed: {saved.error}"
    assert saved.value.preferences.weekly_task_goal == 15
    after = await _properties(neo4j_driver, _USER)
    assert _changed(before, after) == {"preferences", "last_active_at"}
    assert "_pref_lock" not in after, "the lock sentinel must not outlive its transaction"


async def test_concurrent_saves_of_different_fields_all_land(neo4j_driver, account):
    """Each save patches what the save before it stored, so none is lost."""
    core, _ = account
    for trial in range(_TRIALS):
        await _reset_preferences(neo4j_driver)

        results = await asyncio.gather(
            *(core.update_preferences(_USER, dict(patch)) for patch in _CONCURRENT_PATCHES)
        )

        assert all(result.is_ok for result in results), [r.error for r in results]
        stored = (await core.get_user(_USER)).value.preferences
        landed = {
            "theme": stored.theme == "dark",
            "vault_write_consent": stored.vault_write_consent is True,
            "weekly_task_goal": stored.weekly_task_goal == 42,
            "language": stored.language == "fr",
        }
        assert all(landed.values()), f"trial {trial}: a concurrent save was lost: {landed}"


async def test_preferences_saves_never_write_back_a_concurrent_password_or_role(
    neo4j_driver, account
):
    """A password change and a role change committed while saves run both stay."""
    core, backends = account
    sessions = backends["session_backend"]
    expected_hash = "hash-before"
    for trial in range(_TRIALS):
        new_hash = f"hash-after-{trial}"
        role = UserRole.MEMBER if trial % 2 == 0 else UserRole.TEACHER

        outcomes = await asyncio.gather(
            *(core.update_preferences(_USER, dict(patch)) for patch in _CONCURRENT_PATCHES),
            sessions.change_password_and_revoke_sessions(_USER, expected_hash, new_hash),
            sessions.update_role_and_revoke_sessions(_USER, role),
        )

        assert all(outcome.is_ok for outcome in outcomes), [o.error for o in outcomes]
        assert outcomes[len(_CONCURRENT_PATCHES)].value is not None, "the hash must have matched"
        stored = await _properties(neo4j_driver, _USER)
        assert stored["password_hash"] == new_hash, f"trial {trial}: a save restored the old hash"
        assert stored["role"] == role.value, f"trial {trial}: a save restored the old role"
        expected_hash = new_hash


async def test_unknown_preference_field_is_refused_and_writes_nothing(neo4j_driver, account):
    core, _ = account
    before = await _properties(neo4j_driver, _USER)

    refused = await core.update_preferences(
        _USER, {"weekly_task_goal": 9, "favourite_colour": "red"}
    )

    assert refused.is_error
    assert refused.expect_error().category is ErrorCategory.VALIDATION
    assert await _properties(neo4j_driver, _USER) == before


async def test_preferences_save_for_a_missing_user_is_not_found(account):
    core, _ = account

    missing = await core.update_preferences(_MISSING, {"weekly_task_goal": 9})

    assert missing.is_error
    assert missing.expect_error().category is ErrorCategory.NOT_FOUND


async def test_reactivation_writes_is_active_alone(neo4j_driver, account):
    core, backends = account
    deactivated = await backends["session_backend"].deactivate_user_and_revoke_sessions(_USER)
    assert deactivated.is_ok
    await _stamp_natively(neo4j_driver)
    before = await _properties(neo4j_driver, _USER)
    assert before["is_active"] is False

    reactivated = await core.activate_user(_USER)

    assert reactivated.is_ok, f"reactivation failed: {reactivated.error}"
    assert reactivated.value.is_active is True
    assert _changed(before, await _properties(neo4j_driver, _USER)) == {"is_active"}


async def test_reactivating_a_missing_user_is_not_found(account):
    core, _ = account

    missing = await core.activate_user(_MISSING)

    assert missing.is_error
    assert missing.expect_error().category is ErrorCategory.NOT_FOUND


async def test_admin_users_table_reads_the_last_login_stamp(neo4j_driver, account):
    """The table's Last Login column is the account's ``last_login_at``, not ``updated_at``."""
    _, backends = account
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (u:User {uid: $uid}) "
            "SET u.last_login_at = '2026-11-01T08:30:00+00:00', "
            "u.updated_at = '2026-02-01T11:29:18'",
            uid=_USER,
        )
    stats = AdminStatsService(backend=backends["cross_domain_backend"])

    rows = await stats.get_users_with_activity_counts(active_only=False)

    assert rows.is_ok, f"admin rows failed: {rows.error}"
    (row,) = [row for row in rows.value if row["uid"] == _USER]
    assert row["last_login_at"] == "2026-11-01T08:30:00+00:00"


async def test_recorded_mastery_leaves_the_user_node_unchanged(neo4j_driver, account):
    """The pathways progress door's mastery write lands on the edge, not the user."""
    _, backends = account
    recorder = UserProgressRecorderService(user_repo=backends["users_backend"])
    async with neo4j_driver.session() as session:
        await session.run(
            "MERGE (:Entity:Ku {uid: $uid, entity_type: 'ku', title: 'Mastered'})",
            uid=_MASTERED_KU_UID,
        )
    try:
        before = await _properties(neo4j_driver, _USER)

        recorded = await recorder.record_knowledge_mastery(_USER, _MASTERED_KU_UID, 0.9)

        assert recorded.is_ok, f"mastery failed: {recorded.error}"
        assert recorded.value == {"mastery_score": 0.9, "was_mastered": False}
        assert await _properties(neo4j_driver, _USER) == before
        async with neo4j_driver.session() as session:
            record = await (
                await session.run(
                    "MATCH (:User {uid: $user})-[m:MASTERED]->(:Entity {uid: $ku}) "
                    "RETURN count(m) AS n",
                    user=_USER,
                    ku=_MASTERED_KU_UID,
                )
            ).single()
        assert record is not None and record["n"] == 1
    finally:
        async with neo4j_driver.session() as session:
            await session.run("MATCH (k:Entity {uid: $uid}) DETACH DELETE k", uid=_MASTERED_KU_UID)
