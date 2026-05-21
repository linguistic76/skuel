"""
ADR-054 migration correctness — ``collapse_submissions_to_user_entry_2026_04.cypher``
======================================================================================

Seeds a real Neo4j container with legacy ``:ExerciseSubmission`` /
``:JeInput`` / ``:JeOutput`` nodes (some carrying a node-field
``revision_number``), runs the migration, and asserts:

1. All legacy-labelled nodes are now ``:UserEntry`` with
   ``entity_type = 'user_entry'`` and the pipeline derived from the old
   label (``exercise_submission`` → ``teacher_review``, audio JeInput →
   ``transcribe_and_structure``, others → ``none``).
2. ``revision_number`` has moved off the node; any
   ``FULFILLS_EXERCISE`` edge carries ``revision`` (with a default of 1
   where the source node had none).
3. Legacy indexes are dropped and new UserEntry indexes exist.
4. Re-running the migration is a no-op (idempotent).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "migrations"
    / "collapse_submissions_to_user_entry_2026_04.cypher"
)


def _load_statements() -> list[str]:
    """Split the migration file into individual Cypher statements.

    The file mixes single-statement writes with ``CALL apoc.periodic.iterate``
    blocks. Neither the Python driver nor the test container accept
    multi-statement input on a single ``session.run`` call, so we split
    on top-level ``;`` and drop comment / blank lines.
    """
    raw = MIGRATION_PATH.read_text()
    # Strip // line comments
    no_comments = "\n".join(
        line for line in raw.splitlines() if not line.lstrip().startswith("//")
    )
    # Split on semicolons; recombine any accidental splits inside braces
    chunks = [c.strip() for c in no_comments.split(";")]
    return [c for c in chunks if c and not re.fullmatch(r"\s*", c)]


async def _run_migration(neo4j_driver) -> None:
    statements = _load_statements()
    async with neo4j_driver.session() as session:
        for stmt in statements:
            result = await session.run(stmt)
            await result.consume()


async def _seed_legacy(neo4j_driver) -> None:
    """Seed a mixed fleet of legacy nodes plus an exercise + FULFILLS edge."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (ex:Entity:Exercise {uid: 'exercise.mig', title: 'Mig Exercise',
                                        entity_type: 'exercise', status: 'active'})
            CREATE (s1:Entity:ExerciseSubmission {
                uid: 'legacy.es.1',
                entity_type: 'exercise_submission',
                user_uid: 'user.mig_student',
                status: 'submitted',
                revision_number: 3,
                created_at: datetime()
            })
            CREATE (s2:Entity:ExerciseSubmission {
                uid: 'legacy.es.2',
                entity_type: 'exercise_submission',
                user_uid: 'user.mig_student',
                status: 'submitted',
                created_at: datetime()
            })
            CREATE (j1:Entity:JeInput {
                uid: 'legacy.ji.audio',
                entity_type: 'je_input',
                user_uid: 'user.mig_student',
                status: 'active',
                file_type: 'audio/mpeg',
                created_at: datetime()
            })
            CREATE (j2:Entity:JeInput {
                uid: 'legacy.ji.text',
                entity_type: 'je_input',
                user_uid: 'user.mig_student',
                status: 'active',
                file_type: 'text/plain',
                created_at: datetime()
            })
            CREATE (o1:Entity:JeOutput {
                uid: 'legacy.jo.1',
                entity_type: 'je_output',
                user_uid: 'user.mig_student',
                status: 'active',
                created_at: datetime()
            })
            CREATE (s1)-[:FULFILLS_EXERCISE]->(ex)
            CREATE (s2)-[:FULFILLS_EXERCISE]->(ex)
            """
        )


async def _count(neo4j_driver, query: str, **params) -> int:
    async with neo4j_driver.session() as session:
        result = await session.run(query, params)
        record = await result.single()
        return int(record[0]) if record else 0


@pytest.mark.asyncio
async def test_migration_collapses_legacy_nodes_to_user_entry(
    clean_neo4j,
    neo4j_driver,
) -> None:
    await _seed_legacy(neo4j_driver)

    # Sanity: legacy nodes are present before migration
    assert await _count(neo4j_driver, "MATCH (n:ExerciseSubmission) RETURN count(n)") == 2
    assert await _count(neo4j_driver, "MATCH (n:JeInput) RETURN count(n)") == 2
    assert await _count(neo4j_driver, "MATCH (n:JeOutput) RETURN count(n)") == 1

    await _run_migration(neo4j_driver)

    # 1. No legacy labels remain
    assert await _count(neo4j_driver, "MATCH (n:ExerciseSubmission) RETURN count(n)") == 0
    assert await _count(neo4j_driver, "MATCH (n:JeInput) RETURN count(n)") == 0
    assert await _count(neo4j_driver, "MATCH (n:JeOutput) RETURN count(n)") == 0

    # 2. All seeded nodes now :UserEntry with entity_type = 'user_entry'
    assert await _count(
        neo4j_driver,
        """
        MATCH (n:UserEntry)
        WHERE n.uid IN ['legacy.es.1','legacy.es.2','legacy.ji.audio',
                        'legacy.ji.text','legacy.jo.1']
          AND n.entity_type = 'user_entry'
        RETURN count(n)
        """,
    ) == 5

    # 3. Pipeline assignment per legacy label
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (n:UserEntry) WHERE n.uid STARTS WITH 'legacy.' RETURN n.uid AS uid, n.pipeline AS pipeline"
        )
        pipelines = {r["uid"]: r["pipeline"] async for r in result}
    assert pipelines["legacy.es.1"] == "teacher_review"
    assert pipelines["legacy.es.2"] == "teacher_review"
    assert pipelines["legacy.ji.audio"] == "transcribe_and_structure"
    assert pipelines["legacy.ji.text"] == "none"
    assert pipelines["legacy.jo.1"] == "none"

    # 4. revision_number removed from nodes; FULFILLS_EXERCISE.revision set
    assert await _count(
        neo4j_driver,
        "MATCH (n:UserEntry) WHERE n.revision_number IS NOT NULL RETURN count(n)",
    ) == 0

    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (u:UserEntry)-[r:FULFILLS_EXERCISE]->(:Exercise {uid: 'exercise.mig'})
            RETURN u.uid AS uid, r.revision AS revision
            """
        )
        revisions = {r["uid"]: r["revision"] async for r in result}
    assert revisions["legacy.es.1"] == 3, "migrated node_field revision_number → edge"
    assert revisions["legacy.es.2"] == 1, "defaulted to 1 when node had no revision_number"

    # 5. Index topology — new indexes present; legacy indexes absent
    async with neo4j_driver.session() as session:
        idx_result = await session.run("SHOW INDEXES YIELD name")
        index_names = {r["name"] async for r in idx_result}
    assert "user_entry_uid_idx" in index_names
    assert "user_entry_pipeline_idx" in index_names
    assert "user_entry_fulltext_idx" in index_names
    assert "exercise_submission_fulltext_idx" not in index_names
    assert "je_input_fulltext_idx" not in index_names
    assert "je_output_fulltext_idx" not in index_names

    # 6. Idempotence — re-running changes nothing
    user_entry_count_before = await _count(neo4j_driver, "MATCH (n:UserEntry) RETURN count(n)")
    await _run_migration(neo4j_driver)
    user_entry_count_after = await _count(neo4j_driver, "MATCH (n:UserEntry) RETURN count(n)")
    assert user_entry_count_before == user_entry_count_after
    assert await _count(
        neo4j_driver,
        "MATCH (n) WHERE n:ExerciseSubmission OR n:JeInput OR n:JeOutput RETURN count(n)",
    ) == 0
