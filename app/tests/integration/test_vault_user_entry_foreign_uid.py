"""A vault note that names another user's entry is refused like any vault file (ADR-070 Decision 11).

The UserEntry door writes through ``UserEntryBackend.upsert``, whose owner gate
refuses a uid another user owns. The Activity doors report that refusal as a
content fault — ignored, with the reason — in words that never say whose node it
is; a note naming a taken uid must read the same, not as a sync error.

Drives the production loop over a temp vault (``_vault_rig``).
"""

from __future__ import annotations

import pytest

from core.services.vault.vault_descriptor import VaultKind
from tests.integration._vault_rig import OWNER, Rig

OTHER = "user_nb2c_entry_other"


@pytest.mark.asyncio
async def test_a_note_naming_another_users_entry_is_ignored_with_reason(rig: Rig) -> None:
    async with rig.driver.session() as session:
        await session.run(
            "MERGE (u:User {uid: $other}) "
            "CREATE (u)-[:OWNS]->(:Entity:UserEntry {uid: 'ue.taken', user_uid: $other, "
            "title: 'Not yours', entity_type: 'user_entry', pipeline: 'knowledge', "
            "status: 'active'})",
            other=OTHER,
        )
    notes = rig.vault / "knowledge"
    notes.mkdir(parents=True, exist_ok=True)
    (notes / "mine.md").write_text(
        "---\ntype: user_entry\npipeline: knowledge\nuid: ue.taken\ntitle: Mine\n---\n\nmine\n"
    )
    (notes / "own.md").write_text(
        "---\ntype: user_entry\npipeline: knowledge\ntitle: Own note\n---\n\nmine too\n"
    )

    result = await rig.reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok, result
    stats = result.value
    assert stats.errors == [], stats.errors
    (ignored,) = [line for line in stats.ignored if "mine.md" in line]
    assert "ue.taken" in ignored and "already in use" in ignored, ignored
    assert OTHER not in ignored
    async with rig.driver.session() as session:
        rows = await (
            await session.run(
                "MATCH (e:UserEntry) WHERE e.title IN ['Not yours', 'Mine', 'Own note'] "
                "RETURN e.uid AS uid, e.title AS title, e.user_uid AS owner ORDER BY title"
            )
        ).data()
    # The other user's entry is untouched; the positive control — the owner's own
    # note in the same sync — landed.
    assert rows[0] == {"uid": "ue.taken", "title": "Not yours", "owner": OTHER}
    assert [r["title"] for r in rows] == ["Not yours", "Own note"]
