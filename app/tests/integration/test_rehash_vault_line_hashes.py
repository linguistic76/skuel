"""The ✅ line-hash migration rewrites the right edges — and only those — on a real graph.

Four ways this migration could go wrong, each exercised against the container
with real vault files under ``tmp_path``:

1. **Rewriting more than the orphans.** The seed holds one edge of every
   census outcome; after ``--confirm`` only the edge whose stored hash was
   produced by the retired normalisation has changed, and every other stored
   value is byte-identical.
2. **Writing from the census alone.** The census is read-only: the graph is
   unchanged after it.
3. **Clobbering a fresher digest.** The write is guarded on the value the
   census saw, so a row re-stamped between census and write is skipped and
   the re-check reports it as current.
4. **Not converging.** The second run classifies everything as current and
   writes nothing.

The queries are **imported from the script**, not retyped. The
classification the census prints is pinned DB-free in
``tests/unit/scripts/test_rehash_vault_line_hashes.py``; the loop that
produces the orphan and the sync that would duplicate without this migration
are in ``tests/integration/test_vault_done_date_hash_roundtrip.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import pytest_asyncio

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import rehash_vault_line_hashes as rehash  # type: ignore[import-not-found]

from core.ports.vault_bridge_protocol import normalize_vault_line_hash

CHECKED = "- [x] Water the plants 🆔 sk_a1b2c3 ✅ 2026-08-20"
UNCHECKED = "- [ ] Call the bank 🆔 sk_d4e5f6"
ORIGINAL_TITLE = "- [x] Water the plant ✅ 2026-08-20"  # what an edited line used to say


async def _seed_edge(
    neo4j_driver,
    *,
    entry_uid: str,
    task_uid: str,
    stored_hash: str,
    vault_id: str | None,
    vault_file_path: str | None,
    content: str | None,
) -> None:
    metadata = {"entry_kind": "daily"}
    if vault_file_path is not None:
        metadata["vault_file_path"] = vault_file_path
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MERGE (entry:Entity:UserEntry {uid: $entry_uid})
            SET entry.entity_type = 'user_entry',
                entry.metadata = $metadata,
                entry.content = $content
            MERGE (t:Entity:Task {uid: $task_uid})
            SET t.entity_type = 'task', t.title = $task_uid
            MERGE (t)-[r:EXTRACTED_FROM]->(entry)
            SET r.source_line_hash = $stored_hash, r.vault_id = $vault_id,
                r.extracted_at = datetime()
            """,
            entry_uid=entry_uid,
            task_uid=task_uid,
            stored_hash=stored_hash,
            vault_id=vault_id,
            vault_file_path=vault_file_path,
            metadata=json.dumps(metadata),
            content=content,
        )
        await result.consume()


async def _stored_hashes(neo4j_driver) -> dict[str, str]:
    """``task_uid → source_line_hash`` for every provenance edge in the graph."""
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (t:Task)-[r:EXTRACTED_FROM]->(:UserEntry)
            RETURN t.uid AS uid, r.source_line_hash AS h
            """
        )
        return {row["uid"]: row["h"] async for row in result}


@pytest.mark.asyncio
@pytest.mark.integration
class TestRehashVaultLineHashes:
    @pytest_asyncio.fixture
    async def seeded(self, neo4j_driver, clean_neo4j, tmp_path: Path) -> dict[str, str]:
        note = tmp_path / "periodic_notes" / "2026-08-20.md"
        note.parent.mkdir(parents=True)
        note.write_text(f"# Daily\n\n{CHECKED}\n{UNCHECKED}\n", encoding="utf-8")
        path = str(note)

        legacy_checked = rehash.legacy_normalize_vault_line_hash(CHECKED)
        seeds: dict[str, dict] = {
            # The orphan: stored with the ✅ inside the digest (the create door, pre-fix).
            "task_orphan": {"stored_hash": legacy_checked, "vault_id": "sk_a1b2c3", "path": path},
            # Already current — a ✅-less line whose two digests agree.
            "task_current": {
                "stored_hash": normalize_vault_line_hash(UNCHECKED),
                "vault_id": "sk_d4e5f6",
                "path": path,
            },
            # Edited since extraction: the 🆔 finds the line, neither digest matches.
            "task_edited": {
                "stored_hash": normalize_vault_line_hash(ORIGINAL_TITLE),
                "vault_id": "sk_a1b2c3",
                "path": path,
            },
            # 🆔 the file no longer holds and no digest match: reported.
            "task_gone": {
                "stored_hash": normalize_vault_line_hash("- [ ] Something removed"),
                "vault_id": "sk_zzz999",
                "path": path,
            },
            # Vault file missing: reported, never rewritten from node content.
            "task_missing": {
                "stored_hash": legacy_checked,
                "vault_id": "sk_a1b2c3",
                "path": str(tmp_path / "periodic_notes" / "deleted.md"),
            },
            # Non-vault entry: the orphan lives in the node's own content.
            "task_api": {"stored_hash": legacy_checked, "vault_id": None, "path": None},
        }
        for task_uid, seed in seeds.items():
            await _seed_edge(
                neo4j_driver,
                entry_uid=f"ue_{task_uid}",
                task_uid=task_uid,
                stored_hash=seed["stored_hash"],
                vault_id=seed["vault_id"],
                vault_file_path=seed["path"],
                content=f"{CHECKED}\n" if seed["path"] is None else None,
            )
        return {uid: seed["stored_hash"] for uid, seed in seeds.items()}

    async def test_census_classifies_every_shape_and_writes_nothing(self, neo4j_driver, seeded):
        plans = await rehash.census(neo4j_driver)
        outcomes = {p.entity_uid: p.outcome for p in plans}

        assert outcomes == {
            "task_orphan": rehash.Outcome.REWRITE,
            "task_current": rehash.Outcome.CURRENT,
            "task_edited": rehash.Outcome.EDITED,
            "task_gone": rehash.Outcome.LINE_NOT_FOUND,
            "task_missing": rehash.Outcome.FILE_MISSING,
            "task_api": rehash.Outcome.REWRITE,
        }
        assert await rehash.run_rehash(neo4j_driver, confirm=False) == 0
        assert await _stored_hashes(neo4j_driver) == seeded, "the census wrote"

    async def test_confirm_rewrites_only_the_proven_orphans(self, neo4j_driver, seeded):
        assert await rehash.run_rehash(neo4j_driver, confirm=True) == 0

        after = await _stored_hashes(neo4j_driver)
        expected = dict(seeded)
        expected["task_orphan"] = normalize_vault_line_hash(CHECKED)
        expected["task_api"] = normalize_vault_line_hash(CHECKED)
        assert after == expected

        # Converged: the second run finds nothing to rewrite and changes nothing.
        assert await rehash.run_rehash(neo4j_driver, confirm=True) == 0
        assert await _stored_hashes(neo4j_driver) == expected
        assert not any(p.writes for p in await rehash.census(neo4j_driver))

    async def test_the_write_skips_a_row_re_stamped_since_the_census(self, neo4j_driver, seeded):
        """The guard: a plan carrying a stale ``old_hash`` matches nothing."""
        fresher = normalize_vault_line_hash(CHECKED)
        async with neo4j_driver.session() as session:
            result = await session.run(
                """
                MATCH (t:Task {uid: 'task_orphan'})-[r:EXTRACTED_FROM]->(:UserEntry)
                SET r.source_line_hash = $h
                """,
                h=fresher,
            )
            await result.consume()

        records, _, _ = await neo4j_driver.execute_query(
            rehash.REWRITE_QUERY,
            rewrites=[
                {
                    "entry_uid": "ue_task_orphan",
                    "entity_uid": "task_orphan",
                    "old_hash": seeded["task_orphan"],  # what the census saw
                    "new_hash": "0" * 64,
                }
            ],
        )

        assert int(records[0]["n"]) == 0
        assert (await _stored_hashes(neo4j_driver))["task_orphan"] == fresher
