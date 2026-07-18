"""
Migrate: Remove Legacy Template Fields
======================================

One-shot migration to drop the denormalized
``source_learning_path_uid`` and ``curriculum_driven`` properties from
Activity nodes (Task, Habit, Event, Goal) on Neo4j.

The Activity Templates work (see /.claude/plans/skip-when-do-idempotent-shell.md
Phase 6) replaces these properties:

* ``source_learning_path_uid`` is now redundant — the LP is reachable via
  ``(activity)-[:?]->(PS)-[:IS_STEP_OF]->(LP)`` traversal whenever
  ``source_path_step_uid`` is set on the activity.
* ``curriculum_driven`` is now redundant — instances spawned from a template
  carry ``template_uid``; that presence is the curriculum-origin signal.

The script performs an audit pass before dropping, warning about any
Activity that holds an LP back-pointer but no PS link and no template_uid
(such nodes lose their only curriculum signal).

Idempotent: re-running on a clean database is a no-op.

Usage::

    uv run python scripts/migrate_remove_legacy_template_fields.py [--apply]

Without ``--apply`` the script audits only; pass the flag to actually
``REMOVE`` the properties.
"""

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection
from core.utils.logging import get_logger

load_dotenv(project_root / ".env")

logger = get_logger(__name__)

ACTIVITY_LABELS = ("Task", "Habit", "Event", "Goal")


def _resolve_password(password: str | None, username: str) -> str:
    if password is not None:
        return password
    try:
        from core.config.credential_store import get_credential

        cred = get_credential("NEO4J_PASSWORD", fallback_to_env=True)
        if cred:
            return cred
    except Exception:  # safety-net: credential store optional
        pass
    return getpass.getpass(f"Neo4j password for {username}: ")


async def _audit(session, label: str) -> dict[str, int]:
    """Count legacy properties + orphan-LP cases for one Activity label."""
    lp_count = (
        await (
            await session.run(
                f"MATCH (n:{label}) WHERE n.source_learning_path_uid IS NOT NULL "
                "RETURN count(n) AS c"
            )
        ).single()
    )["c"]
    cd_count = (
        await (
            await session.run(
                f"MATCH (n:{label}) WHERE n.curriculum_driven IS NOT NULL RETURN count(n) AS c"
            )
        ).single()
    )["c"]
    orphan_lp = (
        await (
            await session.run(
                f"MATCH (n:{label}) "
                "WHERE n.source_learning_path_uid IS NOT NULL "
                "  AND n.source_path_step_uid IS NULL "
                "  AND n.template_uid IS NULL "
                "RETURN count(n) AS c"
            )
        ).single()
    )["c"]
    return {"lp": lp_count, "cd": cd_count, "orphan_lp": orphan_lp}


async def _drop(session, label: str) -> int:
    """Drop both legacy properties from one Activity label. Returns affected count."""
    result = await session.run(
        f"MATCH (n:{label}) "
        "WHERE n.source_learning_path_uid IS NOT NULL "
        "   OR n.curriculum_driven IS NOT NULL "
        "REMOVE n.source_learning_path_uid, n.curriculum_driven "
        "RETURN count(n) AS c"
    )
    return (await result.single())["c"]


async def migrate(
    apply: bool,
    uri: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> dict[str, dict[str, int]]:
    uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = username or os.getenv("NEO4J_USERNAME", "neo4j")
    password = _resolve_password(password, username)

    conn = Neo4jConnection(uri=uri, username=username, password=password)
    driver = conn.connect()

    summary: dict[str, dict[str, int]] = {}
    try:
        async with driver.session() as session:
            logger.info("Auditing legacy template fields...")
            for label in ACTIVITY_LABELS:
                stats = await _audit(session, label)
                summary[label] = stats
                logger.info(
                    "  %s: lp=%d, curriculum_driven=%d, orphan_lp=%d",
                    label,
                    stats["lp"],
                    stats["cd"],
                    stats["orphan_lp"],
                )
                if stats["orphan_lp"] > 0:
                    logger.warning(
                        "  %d %s nodes have source_learning_path_uid but no "
                        "source_path_step_uid and no template_uid — these will "
                        "lose their curriculum signal entirely.",
                        stats["orphan_lp"],
                        label,
                    )

            if not apply:
                logger.info("Audit complete. Re-run with --apply to drop properties.")
                return summary

            logger.info("Dropping legacy properties...")
            for label in ACTIVITY_LABELS:
                affected = await _drop(session, label)
                summary[label]["dropped"] = affected
                logger.info("  %s: removed properties from %d nodes", label, affected)

            logger.info("Verifying...")
            for label in ACTIVITY_LABELS:
                post = await _audit(session, label)
                if post["lp"] != 0 or post["cd"] != 0:
                    logger.error(
                        "  %s: %d lp + %d cd remain after migration",
                        label,
                        post["lp"],
                        post["cd"],
                    )
                else:
                    logger.info("  %s: clean", label)

    finally:
        await conn.close()

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually drop the properties. Without this flag the script only audits.",
    )
    args = parser.parse_args()
    asyncio.run(migrate(apply=args.apply))


if __name__ == "__main__":
    main()
