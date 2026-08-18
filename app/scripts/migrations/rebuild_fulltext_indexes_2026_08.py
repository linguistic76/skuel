#!/usr/bin/env python3
"""
Rebuild fulltext indexes whose field list drifted from FULLTEXT_INDEX_DEFINITIONS.

Why a migration at all: ``Neo4jSchemaManager._create_fulltext_index`` issues
``CREATE FULLTEXT INDEX ... IF NOT EXISTS``, which is a no-op when an index of
that name already exists — *whatever properties it indexes*. So editing the
field list in ``FULLTEXT_INDEX_DEFINITIONS`` changes nothing on a graph that
already has the index, and code and graph silently diverge. Restarting the app
does not help; only DROP + CREATE does.

This script compares the live graph against the code definitions and rebuilds
exactly the indexes that differ. It is idempotent: a graph already matching the
code reports "in sync" and touches nothing.

The 2026-08 run dropped two phantom properties that no node has ever carried,
so it changes no search result — ``Choice.context`` (never existed) and
``LearningPath.goal`` (a read-only Python property aliasing ``description``,
never persisted). Both were indexing nothing. See
tests/unit/test_fulltext_index_naming.py, which now fails on a field that is
not a persisted model field.

Brief gap while an index rebuilds: ``_fulltext_search`` degrades to an empty
result and hybrid search continues vector-only, so a rebuild is safe online.

Usage:
    uv run python scripts/migrations/rebuild_fulltext_indexes_2026_08.py --dry-run
    uv run python scripts/migrations/rebuild_fulltext_indexes_2026_08.py
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from adapters.persistence.neo4j.neo4j_schema_manager import FULLTEXT_INDEX_DEFINITIONS
from core.models.enums.neo_labels import NeoLabel
from core.utils.logging import get_logger

logger = get_logger("skuel.migrations.rebuild_fulltext_indexes")


async def _live_fulltext_indexes(session: Any) -> dict[str, tuple[str, list[str]]]:
    """Read the live graph's fulltext indexes as {name: (label, properties)}."""
    result = await session.run(
        "SHOW FULLTEXT INDEXES YIELD name, labelsOrTypes, properties "
        "RETURN name, labelsOrTypes, properties"
    )
    live: dict[str, tuple[str, list[str]]] = {}
    async for record in result:
        labels = record["labelsOrTypes"] or []
        live[record["name"]] = (labels[0] if labels else "", list(record["properties"] or []))
    return live


def _plan(
    live: dict[str, tuple[str, list[str]]],
) -> tuple[list[tuple[str, NeoLabel, list[str], list[str]]], list[str]]:
    """
    Compare code definitions against the live graph.

    Returns (to_rebuild, missing) where to_rebuild is
    [(index_name, label, live_fields, wanted_fields)] and missing names
    indexes the code defines that the graph does not have at all (those are
    created by the normal startup sync — reported, not rebuilt here).
    """
    to_rebuild: list[tuple[str, NeoLabel, list[str], list[str]]] = []
    missing: list[str] = []

    for label, wanted in FULLTEXT_INDEX_DEFINITIONS:
        index_name = NeoLabel.fulltext_index_name(label)
        if index_name not in live:
            missing.append(index_name)
            continue
        _live_label, live_fields = live[index_name]
        # Order is not semantically meaningful to Lucene, but a reordering still
        # means the definition moved — compare as ordered lists so the report is
        # literal about what the graph holds.
        if list(live_fields) != list(wanted):
            to_rebuild.append((index_name, label, list(live_fields), list(wanted)))

    return to_rebuild, missing


async def rebuild(dry_run: bool = False) -> int:
    """Rebuild drifted fulltext indexes. Returns the number rebuilt (or planned)."""
    from adapters.persistence.neo4j_adapter import Neo4jAdapter

    adapter = Neo4jAdapter()
    await adapter.connect()
    driver = adapter.driver

    try:
        async with driver.session() as session:
            live = await _live_fulltext_indexes(session)
            to_rebuild, missing = _plan(live)

            print(f"Live fulltext indexes: {len(live)}")
            print(f"Code definitions:      {len(FULLTEXT_INDEX_DEFINITIONS)}")

            if missing:
                print(
                    f"\nDefined in code but absent from the graph "
                    f"({len(missing)}) — startup sync creates these:"
                )
                for name in missing:
                    print(f"  {name}")

            if not to_rebuild:
                print("\n✓ Every live index matches its code definition — nothing to rebuild.")
                return 0

            print(f"\nDrifted ({len(to_rebuild)}):")
            for name, _label, live_fields, wanted in to_rebuild:
                print(f"  {name}")
                print(f"      live: {', '.join(live_fields)}")
                print(f"      code: {', '.join(wanted)}")

            if dry_run:
                print(f"\n[dry-run] would rebuild {len(to_rebuild)} index(es); nothing changed.")
                return len(to_rebuild)

            for name, label, _live_fields, wanted in to_rebuild:
                fields_str = ", ".join(f"n.{f}" for f in wanted)
                print(f"\nRebuilding {name} ...")
                await session.run(f"DROP INDEX {name} IF EXISTS")
                await session.run(
                    f"CREATE FULLTEXT INDEX {name} IF NOT EXISTS "
                    f"FOR (n:{label.value}) ON EACH [{fields_str}]"
                )
                logger.info(f"Rebuilt fulltext index {name} on {wanted}")
                print(f"  ✓ {name} → {', '.join(wanted)}")

            # Re-read so the summary reflects the graph, not our intent.
            after = await _live_fulltext_indexes(session)
            still_drifted, _ = _plan(after)
            if still_drifted:
                print(f"\n✗ {len(still_drifted)} index(es) still drifted after rebuild.")
                return len(still_drifted)

            print(f"\n✓ Rebuilt {len(to_rebuild)} index(es); graph now matches code.")
            return len(to_rebuild)
    finally:
        await adapter.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild fulltext indexes whose fields drifted from the code definitions"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report drift without modifying the graph"
    )
    args = parser.parse_args()
    asyncio.run(rebuild(dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
