#!/usr/bin/env python3
"""
A task contributes to a goal — FULFILLS_GOAL → CONTRIBUTES_TO_GOAL
===================================================================

Re-types the task's old goal edge onto the one edge the code now writes and reads
(ADR-090, ``docs/roadmap/activity-links-arc.md`` PR 4):

    (Task)-[:FULFILLS_GOAL]->(Goal)  →  (Task)-[:CONTRIBUTES_TO_GOAL]->(Goal)

A pair holding the old edge, the new one, or both ends with exactly one new edge. The
states, per (task, goal) pair:

- **The old edge alone, or both:** the new edge is MERGEd and the old one deleted.
- **The new edge already there** (a link made at ``POST /api/tasks/link-goal``, or an
  earlier partial run): MERGE matches it and it is kept.
- **A re-run:** no old edge matches, nothing is written.

The rest of the old shape goes with the type:

- ``Task.fulfills_goal_uid`` — the node column beside the old edge — is removed from
  every ``:Task``. Where it names a goal the task has no edge to (a task spawned from a
  PathStep template stored the column alone), the goal's owner owns the task, and the
  goal exists, the edge is MERGEd first, so the link survives as the edge. A column
  naming nothing linkable is dropped and listed. ``Goal.fulfills_goal_uid`` (a sub-goal's
  parent) is a different field and is not touched.
- ``TaskTemplate.fulfills_goal_template_uid`` is renamed
  ``contributes_to_goal_template_uid`` (``GoalTemplate``'s field of the same old name is
  the parent-goal template and is not touched).
- The link doors' unread edge properties (``contribution_percentage``, ``milestone_uid``,
  ``contribution_weight``) are removed from every ``CONTRIBUTES_TO_GOAL`` edge: the edge
  carries none.

The type leaves the enum with this change, so nothing of it may be left behind. The run
STOPS (exit 2) before any write while the graph holds:

- a ``FULFILLS_GOAL`` edge that is not Task → Goal — it would be stranded; a person
  removes each one;
- a vault tracker row for an Edge file (``entity_uid`` ``edge:<from>|FULFILLS_GOAL|<to>``)
  — rewrite the Edge file by hand to ``CONTRIBUTES_TO_GOAL`` and sync the vault once, so
  the row takes the file's new identity; then re-run.

The vault trackers move with the edges. A file's ``:IngestionMetadata`` row records the
edges its frontmatter authored as ``{type}|{direction}|{uid}`` keys, and a later ingest
retracts ``prior - current``; a key naming a type the enum no longer has cannot be
decoded, so the edge it recorded would never be retracted. Each key is rewritten:

    FULFILLS_GOAL|outgoing|<goal>   → CONTRIBUTES_TO_GOAL|outgoing|<goal>
    FULFILLS_GOAL|incoming|<task>   → CONTRIBUTES_TO_GOAL|incoming|<task>

Only the first occurs from a frontmatter field (a task's former
``connections.fulfills_goal``).

The stored goal tallies are recomputed afterwards by ``./dev reconcile-goal-tallies``,
the app's own locked recompute.

Run order (the live graph is AuraDB; run under ``direnv exec .`` so the credentials
resolve):

1. Stop the running app.
2. Edit the vault files BEFORE any sync on the new code: a task file's
   ``connections.fulfills_goal`` becomes ``connections.contributes_to_goal``, a task
   template's ``fulfills_goal_template_uid`` becomes ``contributes_to_goal_template_uid``.
   A file synced unconverted after ``--confirm`` authors no goal link (the retired field
   writes no edge), while its rewritten tracker key decodes, so the sync would retract
   the migrated edge. Synced converted before ``--confirm``, the file MERGEs the new edge
   beside the old one (its old key cannot be decoded and is dropped with a warning), and
   the re-type then deletes the old one.
3. Census (no flag), then ``--confirm``.
4. ``./dev reconcile-goal-tallies``.
5. ``./dev vault-sync --vault content --preview``, then the sync; the converted files'
   fingerprints equal the rewritten rows, so nothing is retracted.
6. Census again: 0 old edges, 0 old keys, 0 columns.

Usage:
    uv run scripts/migrations/task_contributes_to_goal_2026_10.py            # census
    uv run scripts/migrations/task_contributes_to_goal_2026_10.py --confirm  # re-type
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.utils.process_clock import pin_process_clock_to_utc

pin_process_clock_to_utc()  # before any clock read (ADR-089)

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# One driver record, keyed by RETURN alias; the values are heterogeneous Neo4j scalars.
type Row = dict[str, Any]  # boundary: raw neo4j-driver record

# The old type is not a RelationshipName member any more, so it is named as a string.
_FULFILLS = "FULFILLS_GOAL"
_CONTRIBUTES = RelationshipName.CONTRIBUTES_TO_GOAL.value
_TASK = NeoLabel.TASK.value
_GOAL = NeoLabel.GOAL.value
_TASK_TEMPLATE = NeoLabel.TASK_TEMPLATE.value
_TRACKER = NeoLabel.INGESTION_METADATA.value

_EDGE_ROW_PREFIX = "edge:"
_OLD_TEMPLATE_FIELD = "fulfills_goal_template_uid"
_NEW_TEMPLATE_FIELD = "contributes_to_goal_template_uid"
_UNREAD_EDGE_PROPS = ("contribution_percentage", "milestone_uid", "contribution_weight")

# --- census ---------------------------------------------------------------

_OLD_ROWS = f"""
MATCH (t:{_TASK})-[old:{_FULFILLS}]->(g:{_GOAL})
RETURN t.uid AS task_uid, g.uid AS goal_uid, properties(old) AS props
ORDER BY task_uid, goal_uid
"""

_STRANDED_ROWS = f"""
MATCH (a)-[old:{_FULFILLS}]->(b)
WHERE NOT (a:{_TASK} AND b:{_GOAL})
RETURN a.uid AS source_uid, labels(a) AS source_labels,
       b.uid AS target_uid, labels(b) AS target_labels
ORDER BY source_uid, target_uid
"""

_NEW_ROWS = f"""
MATCH (t:{_TASK})-[new:{_CONTRIBUTES}]->(g:{_GOAL})
RETURN t.uid AS task_uid, g.uid AS goal_uid, properties(new) AS props
ORDER BY task_uid, goal_uid
"""

_COLUMN_ROWS = f"""
MATCH (t:{_TASK})
WHERE t.fulfills_goal_uid IS NOT NULL
OPTIONAL MATCH (g:{_GOAL} {{uid: t.fulfills_goal_uid}})
RETURN t.uid AS task_uid, t.fulfills_goal_uid AS goal_uid,
       g IS NOT NULL AND g.user_uid = t.user_uid AS linkable,
       EXISTS {{ (t)-[:{_FULFILLS}|{_CONTRIBUTES}]->(:{_GOAL} {{uid: t.fulfills_goal_uid}}) }} AS has_edge
ORDER BY task_uid
"""

_TEMPLATE_ROWS = f"""
MATCH (tt:{_TASK_TEMPLATE})
WHERE tt.{_OLD_TEMPLATE_FIELD} IS NOT NULL
RETURN tt.uid AS template_uid, tt.{_OLD_TEMPLATE_FIELD} AS goal_template_uid
ORDER BY template_uid
"""

_EDGE_PROP_ROWS = f"""
MATCH (a)-[r:{_CONTRIBUTES}]->(g:{_GOAL})
WHERE any(key IN keys(r) WHERE key IN $unread)
RETURN a.uid AS source_uid, g.uid AS goal_uid, properties(r) AS props
ORDER BY source_uid, goal_uid
"""

_EDGE_FILE_ROWS = f"""
MATCH (row:{_TRACKER})
WHERE row.entity_uid STARTS WITH $edge_prefix AND row.entity_uid CONTAINS $infix
RETURN row.file_path AS file_path, row.entity_uid AS entity_uid
ORDER BY file_path
"""

_TRACKER_ROWS = f"""
MATCH (row:{_TRACKER})
WHERE any(key IN coalesce(row.authored_edges, []) WHERE key STARTS WITH $prefix)
RETURN row.file_path AS file_path, row.entity_uid AS entity_uid,
       row.authored_edges AS authored_edges
ORDER BY file_path
"""

# --- write ----------------------------------------------------------------

_LINK_COLUMN_ONLY = f"""
MATCH (t:{_TASK})
WHERE t.fulfills_goal_uid IS NOT NULL
MATCH (g:{_GOAL} {{uid: t.fulfills_goal_uid}})
WHERE g.user_uid = t.user_uid
MERGE (t)-[:{_CONTRIBUTES}]->(g)
RETURN count(*) AS linked
"""

_RETYPE = f"""
MATCH (t:{_TASK})-[old:{_FULFILLS}]->(g:{_GOAL})
MERGE (t)-[:{_CONTRIBUTES}]->(g)
DELETE old
RETURN count(old) AS edges_migrated
"""

_DROP_COLUMN = f"""
MATCH (t:{_TASK})
WHERE t.fulfills_goal_uid IS NOT NULL
REMOVE t.fulfills_goal_uid
RETURN count(t) AS columns_removed
"""

_RENAME_TEMPLATE_FIELD = f"""
MATCH (tt:{_TASK_TEMPLATE})
WHERE tt.{_OLD_TEMPLATE_FIELD} IS NOT NULL
SET tt.{_NEW_TEMPLATE_FIELD} = tt.{_OLD_TEMPLATE_FIELD}
REMOVE tt.{_OLD_TEMPLATE_FIELD}
RETURN count(tt) AS templates_renamed
"""

_STRIP_EDGE_PROPS = f"""
MATCH ()-[r:{_CONTRIBUTES}]->(:{_GOAL})
WHERE any(key IN keys(r) WHERE key IN $unread)
REMOVE r.contribution_percentage, r.milestone_uid, r.contribution_weight
RETURN count(r) AS edges_stripped
"""

_SET_TRACKER_KEYS = f"""
MATCH (row:{_TRACKER} {{file_path: $file_path}})
SET row.authored_edges = $authored_edges
RETURN count(row) AS rows_written
"""

_EDGE_FILE_PARAMS = {"edge_prefix": _EDGE_ROW_PREFIX, "infix": f"|{_FULFILLS}|"}
_TRACKER_PARAMS = {"prefix": f"{_FULFILLS}|"}
_EDGE_PROP_PARAMS = {"unread": list(_UNREAD_EDGE_PROPS)}


class StrandedEdgesError(Exception):
    """The graph holds an old edge or Edge-file row the re-type would leave behind."""


@dataclass(frozen=True)
class Census:
    """What the graph holds of the old shape, the new one, and everything beside them."""

    old: list[Row]
    stranded: list[Row]
    edge_file_rows: list[Row]
    contributes: list[Row]
    columns: list[Row]
    templates: list[Row]
    edge_props: list[Row]
    tracker_rewrites: dict[str, list[str]]

    @property
    def blocked(self) -> bool:
        """True while something only a person can fix would be left behind."""
        return bool(self.stranded or self.edge_file_rows)

    @property
    def pending(self) -> bool:
        """True while anything is left to write."""
        return bool(
            self.old or self.columns or self.templates or self.edge_props or self.tracker_rewrites
        )

    @property
    def pairs(self) -> set[tuple[str, str]]:
        """Every (task, goal) link the migration must leave as one new edge."""
        pairs = {(str(row["task_uid"]), str(row["goal_uid"])) for row in self.old}
        pairs |= {
            (str(row["task_uid"]), str(row["goal_uid"])) for row in self.columns if row["linkable"]
        }
        return pairs


def rewritten_keys(keys: list[str]) -> list[str]:
    """One tracker row's keys with each old key named as the edge it became.

    The result is sorted and de-duplicated, the form ``authored_edge_fingerprint``
    stores. A key that is not ``type|direction|uid`` passes through unchanged.
    """
    rewritten: set[str] = set()
    for key in keys:
        parts = key.split("|", 2)
        if len(parts) == 3 and parts[0] == _FULFILLS and parts[1] in ("outgoing", "incoming"):
            rewritten.add(f"{_CONTRIBUTES}|{parts[1]}|{parts[2]}")
        else:
            rewritten.add(key)
    return sorted(rewritten)


async def _fetch(
    driver: AsyncDriver,
    query: str,
    params: dict[str, Any] | None = None,  # boundary: neo4j query parameters
) -> list[Row]:
    result = await driver.execute_query(query, params or {})
    return [dict(record) for record in result.records]


async def census(driver: AsyncDriver) -> Census:
    """Read the old shape, the new one, the column, the templates and the trackers."""
    tracker_rows = await _fetch(driver, _TRACKER_ROWS, _TRACKER_PARAMS)
    tracker_rewrites: dict[str, list[str]] = {}
    for row in tracker_rows:
        current = [str(key) for key in row["authored_edges"]]
        rewritten = rewritten_keys(current)
        if rewritten != sorted(set(current)):
            tracker_rewrites[str(row["file_path"])] = rewritten
    return Census(
        old=await _fetch(driver, _OLD_ROWS),
        stranded=await _fetch(driver, _STRANDED_ROWS),
        edge_file_rows=await _fetch(driver, _EDGE_FILE_ROWS, _EDGE_FILE_PARAMS),
        contributes=await _fetch(driver, _NEW_ROWS),
        columns=await _fetch(driver, _COLUMN_ROWS),
        templates=await _fetch(driver, _TEMPLATE_ROWS),
        edge_props=await _fetch(driver, _EDGE_PROP_ROWS, _EDGE_PROP_PARAMS),
        tracker_rewrites=tracker_rewrites,
    )


@dataclass(frozen=True)
class Written:
    """What one ``--confirm`` run wrote."""

    columns_linked: int
    edges_migrated: int
    columns_removed: int
    templates_renamed: int
    edges_stripped: int
    tracker_rows: int


async def migrate(driver: AsyncDriver, found: Census) -> Written:
    """Write every step ``found`` calls for.

    Every statement is safe to repeat, so a run that failed part-way is re-run. Refuses,
    writing nothing, while ``found`` lists a stranded edge or Edge-file row. The column
    is linked before it is dropped, so a column-only link survives as its edge.
    """
    if found.blocked:
        raise StrandedEdgesError(
            f"{len(found.stranded)} stranded edge(s) and {len(found.edge_file_rows)} "
            f"Edge-file row(s) name {_FULFILLS}"
        )
    linked = await _fetch(driver, _LINK_COLUMN_ONLY)
    migrated = await _fetch(driver, _RETYPE)
    dropped = await _fetch(driver, _DROP_COLUMN)
    renamed = await _fetch(driver, _RENAME_TEMPLATE_FIELD)
    stripped = await _fetch(driver, _STRIP_EDGE_PROPS, _EDGE_PROP_PARAMS)
    rows_written = 0
    for file_path, keys in found.tracker_rewrites.items():
        written = await _fetch(
            driver, _SET_TRACKER_KEYS, {"file_path": file_path, "authored_edges": keys}
        )
        rows_written += int(written[0]["rows_written"]) if written else 0

    def first(rows: list[Row], key: str) -> int:
        return int(rows[0][key]) if rows else 0

    return Written(
        columns_linked=first(linked, "linked"),
        edges_migrated=first(migrated, "edges_migrated"),
        columns_removed=first(dropped, "columns_removed"),
        templates_renamed=first(renamed, "templates_renamed"),
        edges_stripped=first(stripped, "edges_stripped"),
        tracker_rows=rows_written,
    )


def _print_census(found: Census) -> None:
    print(f"{_FULFILLS} (task → goal): {len(found.old)}")
    for row in found.old:
        print(f"  {row['task_uid']} → {row['goal_uid']}  {row['props']}")
    print(f"{_CONTRIBUTES} (task → goal) already present: {len(found.contributes)}")
    for row in found.contributes:
        print(f"  {row['task_uid']} → {row['goal_uid']}  {row['props']}")
    print(f"Tasks holding fulfills_goal_uid: {len(found.columns)}")
    for row in found.columns:
        state = (
            "edge present"
            if row["has_edge"]
            else (
                "column only — will be linked"
                if row["linkable"]
                else "names nothing linkable — dropped"
            )
        )
        print(f"  {row['task_uid']} → {row['goal_uid']}  ({state})")
    print(f"Task templates holding {_OLD_TEMPLATE_FIELD}: {len(found.templates)}")
    for row in found.templates:
        print(f"  {row['template_uid']} → {row['goal_template_uid']}")
    print(f"{_CONTRIBUTES} edges carrying an unread property: {len(found.edge_props)}")
    for row in found.edge_props:
        print(f"  {row['source_uid']} → {row['goal_uid']}  {row['props']}")
    print(f"Links to hold as one {_CONTRIBUTES} each: {len(found.pairs)}")
    print(f"Tracker rows to rewrite: {len(found.tracker_rewrites)}")
    for file_path, keys in found.tracker_rewrites.items():
        print(f"  {file_path}")
        for key in keys:
            print(f"    {key}")
    if found.stranded:
        print(f"\n{_FULFILLS} edges that do NOT join a task and a goal: {len(found.stranded)}")
        for row in found.stranded:
            print(
                f"  {row['source_uid']} {row['source_labels']} → "
                f"{row['target_uid']} {row['target_labels']}"
            )
    if found.edge_file_rows:
        print(f"\nEdge-file tracker rows naming {_FULFILLS}: {len(found.edge_file_rows)}")
        for row in found.edge_file_rows:
            print(f"  {row['file_path']}  ({row['entity_uid']})")


async def main() -> int:
    parser = argparse.ArgumentParser(description=f"Re-type {_FULFILLS} to {_CONTRIBUTES}")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Write the re-type (default is a census: print every row, change nothing)",
    )
    args = parser.parse_args()

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    driver = await Neo4jConnection().connect()
    try:
        print("=== BEFORE ===")
        found = await census(driver)
        _print_census(found)

        if found.blocked:
            print(
                f"\nSTOP: the graph holds {_FULFILLS} that the re-type would leave behind. "
                "The type leaves the code with this change. Remove each stranded edge; "
                f"rewrite each Edge file to {_CONTRIBUTES} and run "
                "`./dev vault-sync --vault content` so its tracker row takes the new "
                "identity. Then re-run. Nothing was written."
            )
            return 2
        if not args.confirm:
            print("\nCENSUS ONLY — nothing written. Re-run with --confirm to re-type.")
            return 0
        if not found.pending:
            print("\nNothing to re-type.")
            return 0

        written = await migrate(driver, found)
        print(
            f"\nLinked {written.columns_linked} column-only task(s); re-typed "
            f"{written.edges_migrated} edge(s); removed {written.columns_removed} column(s); "
            f"renamed {written.templates_renamed} template field(s); stripped "
            f"{written.edges_stripped} edge(s) of unread properties; rewrote "
            f"{written.tracker_rows} tracker row(s)."
        )

        print("\n=== AFTER ===")
        after = await census(driver)
        _print_census(after)
        if after.pending or after.blocked:
            print("\nFAILED: something of the old shape remains.")
            return 1
        held = {(str(row["task_uid"]), str(row["goal_uid"])) for row in after.contributes}
        missing = found.pairs - held
        if missing:
            print(f"\nFAILED: {len(missing)} link(s) lost: {sorted(missing)}")
            return 1
        print(
            f"\nOK: {len(found.pairs)} link(s) each hold one {_CONTRIBUTES} edge. "
            "Next: `./dev reconcile-goal-tallies`."
        )
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
