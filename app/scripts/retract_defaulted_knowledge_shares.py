#!/usr/bin/env python3
"""
One-off graph retraction — group shares the old ``knowledge`` default created
==============================================================================

Until 2026-09-02 the vault/YAML door defaulted an absent ``audience:`` to
``teachers`` for every pipeline, so a ``knowledge`` note synced without that
line was shared with every group its owner is a student-member of. Mike ruled
that a developed-files note is private unless its frontmatter says otherwise
(``Pipeline.shares_by_default()``), and a vault re-sync never retracts a share
(deferred-work § Vault Re-Sync Never Retracts a Share) — so the shares the old
default already wrote stay until this script removes them.

The script proves its premise per row rather than trusting the graph: a
``SHARED_WITH_GROUP`` edge on a ``knowledge`` UserEntry is retracted ONLY when
the note's vault file (``metadata.vault_file_path``) still exists AND its
frontmatter carries no ``audience:`` line. A file that authors ``audience:``
consented explicitly and is left alone; a missing file or missing path is
reported and skipped (honest count, no silent guess).

Safety: DRY-RUN by default — prints every edge with its verdict and changes
nothing. Pass ``--apply`` to delete the targeted edges (edges only; the notes
and their ``visibility`` are untouched — group sharing is edge-only).

Usage:
    uv run scripts/retract_defaulted_knowledge_shares.py            # dry run
    uv run scripts/retract_defaulted_knowledge_shares.py --apply    # execute
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

from core.models.enums.neo_labels import NeoLabel
from core.models.enums.pipeline import Pipeline
from core.models.relationship_names import RelationshipName

_FRONTMATTER_AUDIENCE = re.compile(r"^audience\s*:", re.MULTILINE)

_SELECT_QUERY = f"""
MATCH (u:{NeoLabel.USER.value})-[:{RelationshipName.OWNS.value}]->(e:{NeoLabel.USER_ENTRY.value})
      -[s:{RelationshipName.SHARED_WITH_GROUP.value}]->(g:{NeoLabel.GROUP.value})
WHERE e.pipeline = $pipeline
RETURN u.uid AS owner, e.uid AS uid, e.title AS title, e.metadata AS metadata,
       g.uid AS group_uid, toString(s.shared_at) AS shared_at
ORDER BY owner, title, group_uid
"""

_DELETE_QUERY = f"""
MATCH (e:{NeoLabel.USER_ENTRY.value} {{uid: $uid}})
      -[s:{RelationshipName.SHARED_WITH_GROUP.value}]->(g:{NeoLabel.GROUP.value} {{uid: $group_uid}})
DELETE s
RETURN count(s) AS removed
"""


def _frontmatter(text: str) -> str | None:
    """The YAML block between the leading ``---`` fences, or None when absent."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    return text[3:end] if end != -1 else None


def _verdict(metadata: Any) -> tuple[bool, str]:
    """(retract?, reason) — decided from the note's vault file, never the graph."""
    try:
        path_str = json.loads(metadata or "{}").get("vault_file_path")
    except TypeError, ValueError:
        return False, "metadata is not JSON"
    if not path_str:
        return False, "no vault_file_path in metadata"
    path = Path(path_str)
    if not path.is_file():
        return False, f"vault file missing: {path}"
    block = _frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    if block is None:
        return False, "no frontmatter block"
    if _FRONTMATTER_AUDIENCE.search(block):
        return False, "explicit audience: in frontmatter"
    return True, "defaulted share (no audience: in frontmatter)"


async def _fetch(driver: Any, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    result = await driver.execute_query(query, params)
    return [dict(record) for record in result.records]


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Retract the group shares the old knowledge audience default created"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete the targeted edges (default is dry-run: print the plan, change nothing)",
    )
    args = parser.parse_args()

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    driver = Neo4jConnection().connect()
    try:
        rows = await _fetch(driver, _SELECT_QUERY, {"pipeline": Pipeline.KNOWLEDGE.value})
        targets: list[dict[str, Any]] = []
        skipped: list[tuple[dict[str, Any], str]] = []
        for row in rows:
            retract, reason = _verdict(row["metadata"])
            (targets.append(row) if retract else skipped.append((row, reason)))

        print(f"Knowledge-note group shares in the graph: {len(rows)}\n")
        for row in targets:
            print(
                f"  RETRACT  {row['uid']}  → {row['group_uid']}  "
                f"(owner {row['owner']}, shared {row['shared_at']})  {row['title']!r}"
            )
        for row, reason in skipped:
            print(f"  keep     {row['uid']}  → {row['group_uid']}  — {reason}")
        print(f"\nTargeted: {len(targets)} edge(s); kept: {len(skipped)}")

        if not args.apply:
            print("\nDRY RUN — nothing deleted. Re-run with --apply to execute.")
            return 0
        if not targets:
            print("\nNothing to retract.")
            return 0

        removed = 0
        failures: list[str] = []
        for row in targets:
            outcome = await _fetch(
                driver, _DELETE_QUERY, {"uid": row["uid"], "group_uid": row["group_uid"]}
            )
            count = int(outcome[0]["removed"]) if outcome else 0
            if count == 1:
                removed += 1
            else:
                failures.append(f"{row['uid']} → {row['group_uid']} (removed {count})")
        print(f"\nRetracted {removed}/{len(targets)} edge(s).")
        if failures:
            print("Failures:")
            for line in failures:
                print(f"  {line}")
            return 1
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
