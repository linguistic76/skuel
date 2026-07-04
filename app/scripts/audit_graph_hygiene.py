"""Graph hygiene audit — systems-review R4 ruling (2026-07-03).

One deliberate mechanism for cleaning user/app-owned graph rows that the G6
corruption and G8/G9 duplication bugs left behind. Dry-run by default: prints
exactly what it would fix (counts + UIDs + who survives and why) plus
report-only observations for Mike to rule on line by line. ``--apply``
executes ONLY the FIX categories, after the dry-run output has been reviewed.

FIX categories (--apply):
  F1  entity_type property contradicts the node's domain label (G6 residue) —
      corrected FROM THE LABEL (the never-sniff-compliant source of truth).
  F2  Same-entry bridge duplicates (G8, the R3 semantic key applied
      retroactively): entities EXTRACTED_FROM the same UserEntry with the same
      domain label + normalized title. Keep the oldest, delete the rest —
      only when every loser's edges are exactly the expected provenance pair
      ({EXTRACTED_FROM out, OWNS in}) and all owners match; anything else
      demotes the group to REPORT.
  F3  Wrong-door UserEntries (Arc E, R2 ruling "one journal door"):
      (a) content-vault-owner periodic entries (the deleted 0vault/Journal/
      door) and (b) legacy random-UID ``ue_*`` extract_activities entries
      (pre-deterministic-door leftovers). Entries deleted; their extracted
      entities deleted when the copy is a wrong-door duplicate (a personal
      survivor exists, or the entity is a content-owner copy); a personal
      entity with NO surviving copy is kept (it just loses its provenance
      edge). Tracker rows (IngestionMetadata) for deleted entries removed.
  F4  Cross-entry duplicates among SURVIVING entries (same label +
      normalized title from different deterministic entries): keep the
      oldest, delete the rest — same edge-safety demotion rule as F2.
      Groups touching test users are skipped (Arc F).

REPORT-ONLY categories (never touched by --apply):
  R2  Multi-owner daily-note UserEntry collisions remaining AFTER F3
      (expected residual: test-user dates only — Arc F).
  R3  Test users left in the graph (sysreview_sim, csrfprobe2, verifyperiodic).
  R4  Structural anomalies: :Entity nodes missing entity_type, nodes with ≠1
      domain label, :Content chunk shadows carrying EXTRACTED_FROM (G13).

Off-vault direct graph writes are sanctioned HERE and only here (R4 ruling):
these are user/app-owned rows, not vault-governed content. Content-vault
entities (dotted curriculum UIDs etc.) reconcile from files and are never
touched.

Usage:
    uv run python scripts/audit_graph_hygiene.py            # dry-run (default)
    uv run python scripts/audit_graph_hygiene.py --apply    # execute FIX cats
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.services.dsl.activity_extractor import normalized_activity_title

# Loser edges must be EXACTLY this provenance pair for a duplicate group to be
# auto-fixable; any other edge (completions, alignments, ...) carries state a
# blind delete would destroy → the group demotes to REPORT.
EXPECTED_LOSER_EDGES = frozenset({"EXTRACTED_FROM:out", "OWNS:in"})

KNOWN_TEST_USER_UIDS = (
    "user_sysreview_sim",
    "user_csrfprobe2",
    "user_verifyperiodic",
)


def expected_types_by_label() -> dict[str, str]:
    """Domain label → the entity_type value that label implies."""
    return {NeoLabel.from_entity_type(et).value: et.value for et in EntityType}


def domain_label(labels: list[str]) -> str | None:
    """The single domain label of a node, or None if it doesn't have exactly one.

    :Entity is the shared base label; :Content is the chunk-shadow label (G13)
    — neither is a domain identity.
    """
    domain = [lb for lb in labels if lb not in ("Entity", "Content")]
    return domain[0] if len(domain) == 1 else None


# ============================================================================
# CATEGORIZERS (pure — unit-tested against fixture rows)
# ============================================================================


@dataclass
class TypeMismatch:
    """F1: entity_type property contradicts the domain label."""

    uid: str
    label: str
    current: str | None
    expected: str


@dataclass
class DupGroup:
    """F2/R1: entities sharing the R3 semantic key.

    ``blockers`` non-empty ⇒ not auto-fixable (REPORT instead): unexpected
    edges on a loser, owner mismatch, or unparseable created_at ordering.
    """

    entry_uid: str  # "" for cross-entry groups
    label: str
    norm_title: str
    winner_uid: str
    loser_uids: list[str] = field(default_factory=list)
    node_summaries: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


def find_type_mismatches(rows: list[dict[str, Any]]) -> list[TypeMismatch]:
    """F1 categorizer over (uid, labels, entity_type) rows."""
    expected_map = expected_types_by_label()
    mismatches: list[TypeMismatch] = []
    for row in rows:
        label = domain_label(row.get("labels") or [])
        if label is None:
            continue  # ≠1 domain label → R4 anomaly, not a type fix
        expected = expected_map.get(label)
        if expected is None:
            continue  # non-EntityType label (e.g. User) — out of scope
        current = row.get("entity_type")
        if current != expected:
            mismatches.append(
                TypeMismatch(uid=row["uid"], label=label, current=current, expected=expected)
            )
    return mismatches


def _group_key_rows(
    rows: list[dict[str, Any]],
) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    """Group extracted-entity rows by the R3 key (entry, label, normalized title)."""
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        label = domain_label(row.get("labels") or [])
        title = row.get("title") or ""
        if label is None or not title:
            continue
        groups[(row["entry_uid"], label, normalized_activity_title(title))].append(row)
    return groups


def group_same_entry_duplicates(rows: list[dict[str, Any]]) -> list[DupGroup]:
    """F2 categorizer: same-entry R3-key groups with >1 node, oldest wins.

    Expects rows with keys: entry_uid, uid, labels, title, created_at (ISO
    string), owner, edge_sigs (list of "TYPE:in|out").
    """
    result: list[DupGroup] = []
    for (entry_uid, label, norm_title), members in sorted(_group_key_rows(rows).items()):
        if len(members) < 2:
            continue
        members = sorted(members, key=lambda r: r.get("created_at") or "9999")
        winner, losers = members[0], members[1:]
        group = DupGroup(
            entry_uid=entry_uid,
            label=label,
            norm_title=norm_title,
            winner_uid=winner["uid"],
            loser_uids=[m["uid"] for m in losers],
            node_summaries=[
                f"{m['uid']} (owner={m.get('owner')}, created={m.get('created_at')})"
                for m in members
            ],
        )
        if not winner.get("created_at"):
            group.blockers.append("winner has no created_at — ordering unverifiable")
        owners = {m.get("owner") for m in members}
        if len(owners) > 1:
            group.blockers.append(f"owner mismatch within group: {sorted(str(o) for o in owners)}")
        for m in losers:
            unexpected = set(m.get("edge_sigs") or []) - EXPECTED_LOSER_EDGES
            if unexpected:
                group.blockers.append(f"{m['uid']} carries unexpected edges: {sorted(unexpected)}")
        result.append(group)
    return result


@dataclass
class WrongDoorPlan:
    """F3: wrong-door UserEntries + the fate of every entity extracted from them.

    ``entries_to_delete``: the wrong-door UserEntries (uid, owner, reason).
    ``entities_to_delete``: extracted entities that are wrong-door copies —
    either owned by the content-vault owner (R2: personal copies survive) or
    legacy-door duplicates with a named surviving copy.
    ``blocked_entities``: deletion candidates carrying unexpected edges
    (state a blind delete would destroy) — reported, never deleted.
    ``orphaned_survivors``: personal entities with NO surviving copy — kept,
    but their EXTRACTED_FROM edge dies with the entry (noted for review).
    """

    entries_to_delete: list[dict[str, Any]] = field(default_factory=list)
    entities_to_delete: list[dict[str, Any]] = field(default_factory=list)
    blocked_entities: list[str] = field(default_factory=list)
    orphaned_survivors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def deleted_entry_uids(self) -> set[str]:
        return {e["uid"] for e in self.entries_to_delete}

    @property
    def deleted_entity_uids(self) -> set[str]:
        return {e["uid"] for e in self.entities_to_delete}


def _global_key_groups(
    rows: list[dict[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Group extracted rows by the CROSS-entry semantic key (label, norm title)."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        label = domain_label(row.get("labels") or [])
        title = row.get("title") or ""
        if label is None or not title:
            continue
        groups[(label, normalized_activity_title(title))].append(row)
    return groups


def plan_wrong_door_cleanup(
    entry_rows: list[dict[str, Any]],
    extracted_rows: list[dict[str, Any]],
    content_owner: str,
) -> WrongDoorPlan:
    """F3 categorizer (pure): decide the fate of wrong-door entries + entities.

    Wrong-door entries (both extract_activities): the content-vault owner's
    deterministic periodic entries (the deleted 0vault/Journal/ door, R2) and
    legacy random-UID ``ue_*`` entries (pre-deterministic-door leftovers).
    Test-user entries never match either condition (deterministic UIDs, own
    owner) — Arc F owns those.
    """
    plan = WrongDoorPlan()
    for row in entry_rows:
        uid = row.get("uid") or ""
        if row.get("pipeline") != "extract_activities":
            continue
        # All three deterministic periodic-note prefixes ingest_user_entry mints.
        is_journal_door = row.get("owner") == content_owner and (
            uid.startswith("ue:daily:")
            or uid.startswith("ue:weekly:")
            or uid.startswith("ue:monthly:")
        )
        is_legacy = uid.startswith("ue_")
        if is_journal_door:
            reason = f"journal-door entry owned by {content_owner} (R2: one door)"
        elif is_legacy:
            reason = "legacy random-UID extract_activities entry"
        else:
            continue
        plan.entries_to_delete.append({"uid": uid, "owner": row.get("owner"), "reason": reason})

    deleted_entries = plan.deleted_entry_uids
    groups = _global_key_groups(extracted_rows)

    for (label, norm_title), members in sorted(groups.items()):
        survivors = [m for m in members if m["entry_uid"] not in deleted_entries]
        for m in members:
            if m["entry_uid"] not in deleted_entries:
                continue
            summary = (
                f"{m['uid']} ({label} '{norm_title}', owner={m.get('owner')}, "
                f"entry={m['entry_uid']})"
            )
            if m.get("owner") == content_owner:
                reason = "content-owner copy from the journal door (R2)"
            elif survivors:
                reason = f"legacy-door duplicate of surviving {survivors[0]['uid']}"
            else:
                plan.orphaned_survivors.append(
                    {
                        "uid": m["uid"],
                        "label": label,
                        "norm_title": norm_title,
                        "entry_uid": m["entry_uid"],
                    }
                )
                continue
            unexpected = set(m.get("edge_sigs") or []) - EXPECTED_LOSER_EDGES
            if unexpected:
                plan.blocked_entities.append(
                    f"{summary} — unexpected edges {sorted(unexpected)} ({reason})"
                )
                continue
            plan.entities_to_delete.append(
                {
                    "uid": m["uid"],
                    "label": label,
                    "norm_title": norm_title,
                    "entry_uid": m["entry_uid"],
                    "owner": m.get("owner"),
                    "reason": reason,
                }
            )
    return plan


def plan_cross_entry_dedup(
    extracted_rows: list[dict[str, Any]],
    deleted_entry_uids: set[str],
    deleted_entity_uids: set[str],
    test_owner_uids: tuple[str, ...] = KNOWN_TEST_USER_UIDS,
) -> list[DupGroup]:
    """F4 categorizer (pure): cross-entry duplicates among SURVIVING entities.

    Runs on the post-F3 picture: rows from deleted entries / deleted entities
    are excluded. Winner = oldest ``created_at``; losers must pass the same
    edge-safety rule as F2 or the group is demoted to REPORT. Groups touching
    a test user are skipped entirely (Arc F owns test-user cleanup).
    """
    surviving = [
        r
        for r in extracted_rows
        if r["entry_uid"] not in deleted_entry_uids and r["uid"] not in deleted_entity_uids
    ]
    result: list[DupGroup] = []
    for (label, norm_title), members in sorted(_global_key_groups(surviving).items()):
        entries = {m["entry_uid"] for m in members}
        if len(members) < 2 or len(entries) < 2:
            continue
        members = sorted(members, key=lambda r: r.get("created_at") or "9999")
        group = DupGroup(
            entry_uid="",
            label=label,
            norm_title=norm_title,
            winner_uid=members[0]["uid"],
            loser_uids=[m["uid"] for m in members[1:]],
            node_summaries=[
                f"{m['uid']} (owner={m.get('owner')}, entry={m['entry_uid']}, "
                f"created={m.get('created_at')})"
                for m in members
            ],
        )
        if any(m.get("owner") in test_owner_uids for m in members):
            group.blockers.append("touches a test user — Arc F owns test-user cleanup")
        if not members[0].get("created_at"):
            group.blockers.append("winner has no created_at — ordering unverifiable")
        for m in members[1:]:
            unexpected = set(m.get("edge_sigs") or []) - EXPECTED_LOSER_EDGES
            if unexpected:
                group.blockers.append(f"{m['uid']} carries unexpected edges: {sorted(unexpected)}")
        result.append(group)
    return result


def find_daily_owner_collisions(entry_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """R2 categorizer: deterministic daily-note UIDs sharing a date across owners.

    Expects rows with keys: uid, owner. Deterministic daily UIDs look like
    ``ue:daily:{owner}:{date}``.
    """
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in entry_rows:
        uid = row.get("uid") or ""
        if uid.startswith("ue:daily:"):
            by_date[uid.rsplit(":", 1)[-1]].append(row)
    return [
        {"date": date, "entries": [r["uid"] for r in rows_]}
        for date, rows_ in sorted(by_date.items())
        if len({r.get("owner") for r in rows_}) > 1
    ]


# ============================================================================
# GRAPH I/O
# ============================================================================


async def fetch_entity_type_rows(driver: Any) -> list[dict[str, Any]]:
    result = await driver.execute_query(
        "MATCH (n:Entity) RETURN n.uid AS uid, labels(n) AS labels, n.entity_type AS entity_type"
    )
    return [dict(r) for r in result.records]


async def fetch_extracted_rows(driver: Any) -> list[dict[str, Any]]:
    result = await driver.execute_query(
        """
        MATCH (e:Entity)-[:EXTRACTED_FROM]->(entry:UserEntry)
        OPTIONAL MATCH (e)-[r]-()
        WITH e, entry,
             collect(DISTINCT type(r) +
                     CASE WHEN startNode(r) = e THEN ':out' ELSE ':in' END) AS edge_sigs
        RETURN entry.uid AS entry_uid, e.uid AS uid, labels(e) AS labels,
               e.title AS title, toString(e.created_at) AS created_at,
               e.user_uid AS owner, edge_sigs
        """
    )
    return [dict(r) for r in result.records]


async def fetch_user_entry_rows(driver: Any) -> list[dict[str, Any]]:
    result = await driver.execute_query(
        "MATCH (e:UserEntry) RETURN e.uid AS uid, e.user_uid AS owner, "
        "e.pipeline AS pipeline, toString(e.created_at) AS created_at"
    )
    return [dict(r) for r in result.records]


async def fetch_anomalies(driver: Any) -> dict[str, list[dict[str, Any]]]:
    """R4: structural anomalies, each fetched with its own query."""
    anomalies: dict[str, list[dict[str, Any]]] = {}
    queries = {
        "missing entity_type": (
            "MATCH (n:Entity) WHERE n.entity_type IS NULL RETURN n.uid AS uid, labels(n) AS labels"
        ),
        "not exactly one domain label": (
            "MATCH (n:Entity) "
            "WITH n, [l IN labels(n) WHERE NOT l IN ['Entity','Content']] AS dl "
            "WHERE size(dl) <> 1 RETURN n.uid AS uid, labels(n) AS labels"
        ),
        ":Content shadow carrying EXTRACTED_FROM (G13)": (
            "MATCH (c:Content)-[:EXTRACTED_FROM]->(entry) "
            "RETURN c.uid AS uid, entry.uid AS entry_uid"
        ),
    }
    for name, query in queries.items():
        result = await driver.execute_query(query)
        anomalies[name] = [dict(r) for r in result.records]
    return anomalies


async def fetch_test_users(driver: Any) -> list[dict[str, Any]]:
    result = await driver.execute_query(
        """
        MATCH (u:User) WHERE u.uid IN $uids
        OPTIONAL MATCH (u)-[r]-()
        RETURN u.uid AS uid, u.email AS email, count(r) AS edge_count,
               collect(DISTINCT type(r)) AS edge_types
        """,
        uids=list(KNOWN_TEST_USER_UIDS),
    )
    return [dict(r) for r in result.records]


async def apply_type_fixes(driver: Any, fixes: list[TypeMismatch]) -> int:
    fixed = 0
    for f in fixes:
        result = await driver.execute_query(
            f"MATCH (n:Entity {{uid: $uid}}) WHERE '{f.label}' IN labels(n) "
            "SET n.entity_type = $expected RETURN count(n) AS n",
            uid=f.uid,
            expected=f.expected,
        )
        fixed += int(result.records[0]["n"]) if result.records else 0
    return fixed


async def _delete_entity_checked(driver: Any, uid: str, label: str) -> bool:
    """DETACH DELETE one entity after the :Content-shadow-uid safety check."""
    shadow = await driver.execute_query(
        "MATCH (c:Content {uid: $uid}) RETURN count(c) AS n", uid=uid
    )
    if shadow.records and int(shadow.records[0]["n"]) > 0:
        print(f"    !! {uid}: :Content shadow shares this uid — skipped")
        return False
    await driver.execute_query(
        f"MATCH (n:Entity {{uid: $uid}}) WHERE '{label}' IN labels(n) DETACH DELETE n",
        uid=uid,
    )
    return True


async def apply_wrong_door_cleanup(driver: Any, plan: WrongDoorPlan) -> tuple[int, int, int]:
    """F3 apply: delete wrong-door entities, then entries, then tracker rows.

    Entities first so the entry DETACH DELETE never orphans a
    to-be-deleted copy's provenance mid-run. Returns
    (entities_deleted, entries_deleted, tracker_rows_deleted).
    """
    entities_deleted = 0
    for entity in plan.entities_to_delete:
        if await _delete_entity_checked(driver, entity["uid"], entity["label"]):
            entities_deleted += 1

    entries_deleted = 0
    for entry in plan.entries_to_delete:
        result = await driver.execute_query(
            "MATCH (e:Entity:UserEntry {uid: $uid}) DETACH DELETE e RETURN count(e) AS n",
            uid=entry["uid"],
        )
        entries_deleted += int(result.records[0]["n"]) if result.records else 0

    tracker_rows = 0
    if plan.entries_to_delete:
        result = await driver.execute_query(
            "MATCH (m:IngestionMetadata) WHERE m.entity_uid IN $uids "
            "DETACH DELETE m RETURN count(m) AS n",
            uids=sorted(plan.deleted_entry_uids),
        )
        tracker_rows = int(result.records[0]["n"]) if result.records else 0
    return entities_deleted, entries_deleted, tracker_rows


async def apply_cross_entry_dedup(driver: Any, groups: list[DupGroup]) -> int:
    """F4 apply: delete losers of clean surviving cross-entry groups.

    No winner-provenance re-assert (unlike F2): each surviving member already
    carries OWNS + EXTRACTED_FROM to its OWN entry.
    """
    deleted = 0
    for group in groups:
        if group.blockers:
            continue
        for loser_uid in group.loser_uids:
            if await _delete_entity_checked(driver, loser_uid, group.label):
                deleted += 1
    return deleted


async def apply_duplicate_merges(driver: Any, groups: list[DupGroup]) -> int:
    """Delete losers of clean same-entry groups (winner keeps the R3 identity).

    Winner provenance is re-asserted first (MERGE is a no-op when, as verified,
    the winner already carries OWNS + EXTRACTED_FROM for the same owner/entry).
    """
    deleted = 0
    for group in groups:
        if group.blockers:
            continue
        for loser_uid in group.loser_uids:
            shadow = await driver.execute_query(
                "MATCH (c:Content {uid: $uid}) RETURN count(c) AS n", uid=loser_uid
            )
            if shadow.records and int(shadow.records[0]["n"]) > 0:
                print(f"    !! {loser_uid}: :Content shadow shares this uid — skipped")
                continue
            await driver.execute_query(
                """
                MATCH (loser:Entity {uid: $loser_uid})
                MATCH (winner:Entity {uid: $winner_uid})
                MATCH (entry:UserEntry {uid: $entry_uid})
                OPTIONAL MATCH (owner:User)-[:OWNS]->(loser)
                FOREACH (o IN CASE WHEN owner IS NULL THEN [] ELSE [owner] END |
                    MERGE (o)-[:OWNS]->(winner))
                MERGE (winner)-[:EXTRACTED_FROM]->(entry)
                DETACH DELETE loser
                """,
                loser_uid=loser_uid,
                winner_uid=group.winner_uid,
                entry_uid=group.entry_uid,
            )
            deleted += 1
    return deleted


# ============================================================================
# REPORTING
# ============================================================================


def print_dry_run(
    mismatches: list[TypeMismatch],
    fixable: list[DupGroup],
    blocked: list[DupGroup],
    wrong_door: WrongDoorPlan,
    dedup_fixable: list[DupGroup],
    dedup_blocked: list[DupGroup],
    residual_collisions: list[dict[str, Any]],
    test_users: list[dict[str, Any]],
    anomalies: dict[str, list[dict[str, Any]]],
) -> None:
    print("=" * 72)
    print("GRAPH HYGIENE AUDIT — dry run (nothing modified)")
    print("=" * 72)

    print(f"\n[FIX F1] entity_type contradicts domain label: {len(mismatches)}")
    for m in mismatches:
        print(f"    {m.uid}  :{m.label}  {m.current!r} → {m.expected!r}")

    total_losers = sum(len(g.loser_uids) for g in fixable)
    print(
        f"\n[FIX F2] same-entry bridge duplicates (R3 key): "
        f"{len(fixable)} groups, {total_losers} nodes to delete"
    )
    for g in fixable:
        print(f"    ({g.entry_uid}, {g.label}, '{g.norm_title}')")
        print(f"        keep   {g.node_summaries[0]}")
        for s in g.node_summaries[1:]:
            print(f"        delete {s}")

    if blocked:
        print(f"\n[REPORT] same-entry duplicate groups NOT auto-fixable: {len(blocked)}")
        for g in blocked:
            print(f"    ({g.entry_uid}, {g.label}, '{g.norm_title}') — {'; '.join(g.blockers)}")
            for s in g.node_summaries:
                print(f"        {s}")

    print(
        f"\n[FIX F3] wrong-door UserEntries (R2 one-door ruling): "
        f"{len(wrong_door.entries_to_delete)} entries, "
        f"{len(wrong_door.entities_to_delete)} extracted entities to delete"
    )
    for entry in wrong_door.entries_to_delete:
        print(f"    delete entry {entry['uid']} (owner={entry['owner']}) — {entry['reason']}")
    for entity in wrong_door.entities_to_delete:
        print(
            f"    delete {entity['uid']} ({entity['label']} '{entity['norm_title']}', "
            f"owner={entity['owner']}, entry={entity['entry_uid']}) — {entity['reason']}"
        )
    if wrong_door.orphaned_survivors:
        print(
            f"    kept (no surviving copy; loses provenance edge): "
            f"{len(wrong_door.orphaned_survivors)}"
        )
        for orphan in wrong_door.orphaned_survivors:
            print(
                f"        keep {orphan['uid']} ({orphan['label']} '{orphan['norm_title']}', "
                f"entry={orphan['entry_uid']})"
            )
    if wrong_door.blocked_entities:
        print(f"    NOT auto-fixable (unexpected edges): {len(wrong_door.blocked_entities)}")
        for line in wrong_door.blocked_entities:
            print(f"        {line}")

    dedup_losers = sum(len(g.loser_uids) for g in dedup_fixable)
    print(
        f"\n[FIX F4] cross-entry duplicates among survivors: "
        f"{len(dedup_fixable)} groups, {dedup_losers} nodes to delete"
    )
    for g in dedup_fixable:
        print(f"    ({g.label}, '{g.norm_title}')")
        print(f"        keep   {g.node_summaries[0]}")
        for s in g.node_summaries[1:]:
            print(f"        delete {s}")
    if dedup_blocked:
        print(f"\n[REPORT] cross-entry duplicate groups NOT auto-fixable: {len(dedup_blocked)}")
        for g in dedup_blocked:
            print(f"    ({g.label}, '{g.norm_title}') — {'; '.join(g.blockers)}")
            for s in g.node_summaries:
                print(f"        {s}")

    print(
        f"\n[REPORT R2] multi-owner daily-note collisions remaining after F3: "
        f"{len(residual_collisions)}"
    )
    for c in residual_collisions:
        print(f"    {c['date']}: {', '.join(c['entries'])}")

    print(f"\n[REPORT R3] test users in graph: {len(test_users)}")
    for u in test_users:
        print(
            f"    {u['uid']} ({u.get('email')}) — {u.get('edge_count')} edges "
            f"{sorted(u.get('edge_types') or [])}"
        )

    print("\n[REPORT R4] structural anomalies:")
    for name, rows in anomalies.items():
        print(f"    {name}: {len(rows)}")
        for row in rows:
            print(f"        {row}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute the FIX categories (F1 type corrections, F2 duplicate merges). "
        "Run the dry-run and get sign-off first.",
    )
    args = parser.parse_args()

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    content_owner = os.getenv("SKUEL_CONTENT_VAULT_OWNER", "user_admin")

    conn = Neo4jConnection()
    driver = await conn.connect()
    try:
        entity_rows = await fetch_entity_type_rows(driver)
        extracted_rows = await fetch_extracted_rows(driver)
        entry_rows = await fetch_user_entry_rows(driver)

        mismatches = find_type_mismatches(entity_rows)
        same_entry = group_same_entry_duplicates(extracted_rows)
        fixable = [g for g in same_entry if not g.blockers]
        blocked = [g for g in same_entry if g.blockers]

        wrong_door = plan_wrong_door_cleanup(entry_rows, extracted_rows, content_owner)
        dedup_groups = plan_cross_entry_dedup(
            extracted_rows,
            wrong_door.deleted_entry_uids,
            wrong_door.deleted_entity_uids,
        )
        dedup_fixable = [g for g in dedup_groups if not g.blockers]
        dedup_blocked = [g for g in dedup_groups if g.blockers]

        # Residual collisions = what F3 does NOT resolve (expected: test users).
        surviving_entries = [
            r for r in entry_rows if (r.get("uid") or "") not in wrong_door.deleted_entry_uids
        ]
        residual_collisions = find_daily_owner_collisions(surviving_entries)
        test_users = await fetch_test_users(driver)
        anomalies = await fetch_anomalies(driver)

        print_dry_run(
            mismatches,
            fixable,
            blocked,
            wrong_door,
            dedup_fixable,
            dedup_blocked,
            residual_collisions,
            test_users,
            anomalies,
        )

        if not args.apply:
            print("\nDry run only — re-run with --apply to execute the FIX categories.")
            return 0

        print("\n" + "=" * 72)
        print("APPLYING FIX CATEGORIES")
        print("=" * 72)
        fixed = await apply_type_fixes(driver, mismatches)
        print(f"F1: corrected entity_type on {fixed}/{len(mismatches)} nodes")
        deleted = await apply_duplicate_merges(driver, fixable)
        expected = sum(len(g.loser_uids) for g in fixable)
        print(f"F2: deleted {deleted}/{expected} duplicate nodes")
        f3_entities, f3_entries, f3_tracker = await apply_wrong_door_cleanup(driver, wrong_door)
        print(
            f"F3: deleted {f3_entities}/{len(wrong_door.entities_to_delete)} entities, "
            f"{f3_entries}/{len(wrong_door.entries_to_delete)} entries, "
            f"{f3_tracker} tracker rows"
        )
        f4_deleted = await apply_cross_entry_dedup(driver, dedup_fixable)
        f4_expected = sum(len(g.loser_uids) for g in dedup_fixable)
        print(f"F4: deleted {f4_deleted}/{f4_expected} cross-entry duplicate nodes")

        # Post-apply verification: FIX categories must now be empty.
        post_entities = await fetch_entity_type_rows(driver)
        post_extracted = await fetch_extracted_rows(driver)
        post_entries = await fetch_user_entry_rows(driver)
        residual_types = find_type_mismatches(post_entities)
        residual_dups = [g for g in group_same_entry_duplicates(post_extracted) if not g.blockers]
        residual_wrong_door = plan_wrong_door_cleanup(post_entries, post_extracted, content_owner)
        residual_dedup = [
            g for g in plan_cross_entry_dedup(post_extracted, set(), set()) if not g.blockers
        ]
        print(
            f"\nPost-apply: {len(residual_types)} type mismatches, "
            f"{len(residual_dups)} fixable same-entry groups, "
            f"{len(residual_wrong_door.entries_to_delete)} wrong-door entries, "
            f"{len(residual_wrong_door.entities_to_delete)} wrong-door entities, "
            f"{len(residual_dedup)} fixable cross-entry groups remaining"
        )
        clean = (
            not residual_types
            and not residual_dups
            and not residual_wrong_door.entries_to_delete
            and not residual_wrong_door.entities_to_delete
            and not residual_dedup
        )
        return 0 if clean else 1
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
