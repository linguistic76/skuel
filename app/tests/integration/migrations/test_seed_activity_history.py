"""``seed_activity_history_2026_09.cypher`` — one history entry per stamped, history-less node.

The report's ``goals_progressed`` / ``principles_reviewed`` counters read
persisted history, never the latest-only stamps; a node that carries a stamp
but no history would count nowhere. The migration gives each such node one
entry dated at its stamp — in the exact shape the writers persist and the
model reads back — and leaves every node that already holds history alone.

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from core.models.enums.principle_enums import AlignmentLevel
from core.models.principle.principle import _to_alignment_assessment
from core.services.report.progress_report_generator import _alignment_history, _progress_history

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "migrations"
    / "seed_activity_history_2026_09.cypher"
)


def _load_statements() -> list[str]:
    raw = MIGRATION_PATH.read_text()
    no_comments = "\n".join(
        line for line in raw.splitlines() if not line.lstrip().startswith("//")
    )
    chunks = [c.strip() for c in no_comments.split(";")]
    return [c for c in chunks if c and not re.fullmatch(r"\s*", c)]


async def _run_migration(neo4j_driver) -> None:
    async with neo4j_driver.session() as session:
        for stmt in _load_statements():
            result = await session.run(stmt)
            await result.consume()


async def _seed(neo4j_driver) -> None:
    async with neo4j_driver.session() as session:
        await session.run(
            """
            // Goal: stamped, no history at all
            CREATE (:Entity:Goal {uid: 'goal.seed.stamped', entity_type: 'goal',
                                  last_progress_update: '2026-08-20T09:00:00',
                                  progress_percentage: 40.0})
            // Goal: stamped, the mapper's empty native list
            CREATE (:Entity:Goal {uid: 'goal.seed.empty', entity_type: 'goal',
                                  last_progress_update: '2026-08-21T09:00:00',
                                  progress_percentage: 55, progress_history: []})
            // Goal: stamped AND already holding history — untouched
            CREATE (:Entity:Goal {uid: 'goal.seed.has', entity_type: 'goal',
                                  last_progress_update: '2026-08-22T09:00:00',
                                  progress_percentage: 70.0,
                                  progress_history: '[{"date": "2026-08-01T09:00:00", "progress_percentage": 10.0}]'})
            // Goal: no stamp — untouched
            CREATE (:Entity:Goal {uid: 'goal.seed.none', entity_type: 'goal',
                                  progress_percentage: 0.0})
            // Principle: stamped (a date string, as the live graph stores it), no history
            CREATE (:Entity:Principle {uid: 'principle.seed.stamped', entity_type: 'principle',
                                       last_review_date: '2026-03-29',
                                       current_alignment: 'mostly_aligned'})
            // Principle: stamped, empty native list, no current level
            CREATE (:Entity:Principle {uid: 'principle.seed.empty', entity_type: 'principle',
                                       last_review_date: '2026-05-05', alignment_history: []})
            // Principle: no stamp — untouched
            CREATE (:Entity:Principle {uid: 'principle.seed.none', entity_type: 'principle',
                                       alignment_history: []})
            """
        )


async def _prop(neo4j_driver, label: str, uid: str, prop: str):
    async with neo4j_driver.session() as session:
        result = await session.run(
            f"MATCH (n:{label} {{uid: $uid}}) RETURN n.{prop} AS v", uid=uid
        )
        record = await result.single()
        return record["v"]


@pytest.mark.asyncio
@pytest.mark.integration
class TestSeedActivityHistory:
    async def test_stamped_goals_get_one_entry_dated_at_the_stamp(
        self, neo4j_driver, clean_neo4j
    ) -> None:
        await _seed(neo4j_driver)
        await _run_migration(neo4j_driver)

        for uid, figure, when in (
            ("goal.seed.stamped", 40.0, "2026-08-20T09:00:00"),
            ("goal.seed.empty", 55.0, "2026-08-21T09:00:00"),
        ):
            raw = await _prop(neo4j_driver, "Goal", uid, "progress_history")
            assert isinstance(raw, str), f"{uid}: the mapper's non-empty shape is one JSON string"
            entries = _progress_history(raw)  # the report reader's own decoder
            assert entries == [{"date": when, "progress_percentage": figure}]
            assert json.loads(raw) == entries

    async def test_nodes_with_history_or_without_a_stamp_are_untouched(
        self, neo4j_driver, clean_neo4j
    ) -> None:
        await _seed(neo4j_driver)
        await _run_migration(neo4j_driver)

        has = await _prop(neo4j_driver, "Goal", "goal.seed.has", "progress_history")
        assert json.loads(has) == [{"date": "2026-08-01T09:00:00", "progress_percentage": 10.0}]
        assert await _prop(neo4j_driver, "Goal", "goal.seed.none", "progress_history") is None
        assert await _prop(neo4j_driver, "Principle", "principle.seed.none", "alignment_history") == []

    async def test_stamped_principles_get_a_seeded_review_the_model_reads_back(
        self, neo4j_driver, clean_neo4j
    ) -> None:
        await _seed(neo4j_driver)
        await _run_migration(neo4j_driver)

        raw = await _prop(neo4j_driver, "Principle", "principle.seed.stamped", "alignment_history")
        entries = _alignment_history(raw)
        assert len(entries) == 1
        assessment = _to_alignment_assessment(entries[0])  # Principle._from_dto's parse
        assert assessment.assessed_date == date(2026, 3, 29)
        assert assessment.alignment_level is AlignmentLevel.MOSTLY_ALIGNED
        assert assessment.kind == "seeded"
        assert "seed_activity_history_2026_09" in assessment.evidence

        raw = await _prop(neo4j_driver, "Principle", "principle.seed.empty", "alignment_history")
        assessment = _to_alignment_assessment(_alignment_history(raw)[0])
        assert assessment.assessed_date == date(2026, 5, 5)
        assert assessment.alignment_level is AlignmentLevel.UNKNOWN

    async def test_running_twice_seeds_nothing_more(self, neo4j_driver, clean_neo4j) -> None:
        await _seed(neo4j_driver)
        await _run_migration(neo4j_driver)
        first = await _prop(neo4j_driver, "Principle", "principle.seed.stamped", "alignment_history")
        await _run_migration(neo4j_driver)
        second = await _prop(neo4j_driver, "Principle", "principle.seed.stamped", "alignment_history")
        assert first == second
        assert len(_alignment_history(second)) == 1
