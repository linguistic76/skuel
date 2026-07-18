"""
Migration: Delete the 120 duplicate "Transcripts 0" seed exercises.

Date: 2026-07-03
Context: services_bootstrap seeded a default transcript exercise on EVERY boot.
    load_exercise_from_file() looked up the caller-supplied idempotency UID
    ("jp.transcript_default") but then created the exercise under a freshly
    generated random UID ("ex_transcripts-0_<hash>") — the requested UID was
    never stored, so every boot's lookup missed and created another duplicate
    (120 copies, 2026-06-25 → 2026-07-02, 106 of them embedded).

    The seed mechanism is deleted in the same PR (superseded: the journals
    flow serves these instructions from data/instructions/ files + the prompt
    registry; nothing ever read the seeded entity). No re-seed after cleanup.

    Pre-verified via read queries: the duplicates' only relationships are the
    incoming OWNS edges from user_system; no entity references their UIDs via
    exercise_uid / parent_entity_uid properties.

Run: uv run python scripts/migrations/cleanup_transcripts0_duplicates_2026_07.py [--apply]
    Without --apply: audit only (counts what would be deleted).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

AUDIT_QUERY = """
MATCH (e:Entity {entity_type: 'exercise', title: 'Transcripts 0'})
WHERE e.uid STARTS WITH 'ex_'
OPTIONAL MATCH (owner:User)-[:OWNS]->(e)
RETURN count(e) AS total,
       count(e.embedding) AS embedded,
       collect(DISTINCT owner.uid) AS owners
"""

DELETE_QUERY = """
MATCH (e:Entity {entity_type: 'exercise', title: 'Transcripts 0'})
WHERE e.uid STARTS WITH 'ex_'
DETACH DELETE e
RETURN count(e) AS deleted
"""


async def main(apply: bool) -> None:
    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    conn = Neo4jConnection()
    driver = conn.connect()
    try:
        records, _, _ = await driver.execute_query(AUDIT_QUERY)
        audit = records[0]
        print(
            f"Audit: {audit['total']} duplicate 'Transcripts 0' exercises "
            f"({audit['embedded']} embedded), owners={audit['owners']}"
        )
        if audit["owners"] not in ([], ["user_system"]):
            print("ABORT: expected only user_system ownership — investigate before deleting.")
            return
        if not apply:
            print("Dry run (pass --apply to delete).")
            return
        records, _, _ = await driver.execute_query(DELETE_QUERY)
        print(f"Deleted: {records[0]['deleted']} nodes (DETACH — OWNS edges removed with them).")
        records, _, _ = await driver.execute_query(AUDIT_QUERY)
        print(f"Post-check: {records[0]['total']} remaining (expected 0).")
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv))
