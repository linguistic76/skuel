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
      Groups touching test users are skipped (F5 owns those).
  F5  Test users (sysreview_sim, csrfprobe2, verifyperiodic) + ALL their
      owned subtrees, sessions, auth events, and tracker rows (Arc F).
      A user carrying edges beyond {OWNS, HAS_SESSION, HAD_AUTH_EVENT}
      demotes to REPORT. Also sweeps ORPHAN sessions/auth events left by
      earlier test-user deletions (user_uid names a User that no longer
      exists); null-user_uid AuthEvents are the by-design failed-login
      audit trail (user_not_found) and are report-only.
  F6  Legacy ``IN_PROGRESS → :Ku`` enrollment edges (old KU-studying model)
      — RULED (Mike, 2026-07-04): MIGRATE to the PathStep whose USES_KU
      covers the Ku (edge properties carried over; existing PS enrollment
      never clobbered), then remove the :Ku edge. A Ku with no (or several)
      covering PS demotes to REPORT — Mike's call, never guessed.
      ``--delete-uncovered-ku-edges`` (post-dialog only) deletes the
      reported uncovered edges instead.
  F7  ABOUT_ENTITY-blocked duplicate tasks from Arc E — RULED (Mike,
      2026-07-04): RE-POINT the incoming ABOUT_ENTITY edges to the
      surviving semantic twin (RULED_ABOUT_ENTITY_REPOINTS), then delete
      the dupe. Missing survivor / owner or title mismatch / unexpected
      edges demote to REPORT.
  F8  User ``role`` property values that aren't the lowercase enum value
      (G12 drift, e.g. legacy "MEMBER") — normalized so raw-Cypher role
      predicates match again.

REPORT-ONLY categories (never touched by --apply):
  R2  Multi-owner daily-note UserEntry collisions remaining AFTER F3+F5
      (expected residual after Arc F: none).
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
from core.models.enums.user_enums import UserRole
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

# F5: a test user carrying anything beyond these edges holds state the plan
# didn't model → REPORT, not delete.
EXPECTED_TEST_USER_EDGES = frozenset({"OWNS:out", "HAS_SESSION:out", "HAD_AUTH_EVENT:out"})

# F7 ruled mapping (Mike, 2026-07-04): Arc E's dry-run identified the surviving
# semantic twin for each ABOUT_ENTITY-blocked duplicate task.
RULED_ABOUT_ENTITY_REPOINTS = {
    "task_8ec20443": "task_b9d52706",
    "task_80fc80ab": "task_cdaf1474",
}

# F7: the dupe's edges must be a SUBSET of these (ownership + the insight edge
# being re-pointed); anything beyond is unmodeled state → REPORT. Subset, not
# equality, deliberately: a partial prior run leaves the dupe missing
# ABOUT_ENTITY:in (already re-pointed) — still safely deletable on re-run.
EXPECTED_DUPE_EDGES = frozenset({"OWNS:in", "ABOUT_ENTITY:in"})


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


@dataclass
class TestUserPlan:
    """F5: one test user + everything that hangs off it."""

    uid: str
    email: str | None
    owned: list[dict[str, Any]] = field(default_factory=list)  # uid, label, edge_sigs
    session_count: int = 0
    auth_event_count: int = 0
    blockers: list[str] = field(default_factory=list)


def plan_test_user_cleanup(
    user_rows: list[dict[str, Any]], owned_rows: list[dict[str, Any]]
) -> list[TestUserPlan]:
    """F5 categorizer (pure): test users + owned subtrees/sessions/auth events.

    Expects user_rows with keys: uid, email, edge_sigs, session_count,
    auth_event_count; owned_rows with keys: owner, uid, labels, edge_sigs.
    """
    owned_by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    blocked_owners: dict[str, list[str]] = defaultdict(list)
    for row in owned_rows:
        label = domain_label(row.get("labels") or [])
        if label is None:
            # ≠1 domain label → R4 anomaly; F5 won't guess AND won't delete the
            # user around it — a dropped row must block, or the user delete
            # would report success while its data remains (Kody #504).
            blocked_owners[row["owner"]].append(
                f"owned entity {row['uid']} has no single domain label"
            )
            continue
        owned_by[row["owner"]].append(
            {"uid": row["uid"], "label": label, "edge_sigs": sorted(row.get("edge_sigs") or [])}
        )
    plans: list[TestUserPlan] = []
    for row in user_rows:
        plan = TestUserPlan(
            uid=row["uid"],
            email=row.get("email"),
            owned=owned_by.get(row["uid"], []),
            session_count=int(row.get("session_count") or 0),
            auth_event_count=int(row.get("auth_event_count") or 0),
        )
        unexpected = set(row.get("edge_sigs") or []) - EXPECTED_TEST_USER_EDGES
        if unexpected:
            plan.blockers.append(f"user carries unexpected edges: {sorted(unexpected)}")
        plan.blockers.extend(blocked_owners.get(row["uid"], []))
        plans.append(plan)
    return plans


@dataclass
class OrphanAuthPlan:
    """F5 orphan sweep: sessions/auth events whose user no longer exists."""

    sessions: list[dict[str, Any]] = field(default_factory=list)  # uid, user_uid
    auth_events: list[dict[str, Any]] = field(default_factory=list)  # uid, user_uid
    audit_trail: list[dict[str, Any]] = field(default_factory=list)  # null user_uid — keep


def plan_orphan_auth_cleanup(
    session_rows: list[dict[str, Any]], auth_rows: list[dict[str, Any]]
) -> OrphanAuthPlan:
    """F5 orphan categorizer (pure). Inputs are ALREADY filtered to orphans
    (no HAS_SESSION / HAD_AUTH_EVENT from any User). Null-user_uid AuthEvents
    are the failed-login audit trail (``user_not_found``) — report, never delete.
    """
    plan = OrphanAuthPlan()
    plan.sessions = list(session_rows)
    for row in auth_rows:
        if row.get("user_uid") is None:
            plan.audit_trail.append(row)
        else:
            plan.auth_events.append(row)
    return plan


@dataclass
class KuEnrollmentMigration:
    """F6: one legacy ``(user)-[:IN_PROGRESS]->(:Ku)`` edge and its target PS."""

    user_uid: str
    ku_uid: str
    covering_ps: list[str] = field(default_factory=list)
    edge_props: dict[str, Any] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)

    @property
    def target_ps(self) -> str | None:
        return self.covering_ps[0] if len(self.covering_ps) == 1 else None


def plan_ku_enrollment_migrations(rows: list[dict[str, Any]]) -> list[KuEnrollmentMigration]:
    """F6 categorizer (pure) — RULED (Mike, 2026-07-04): MIGRATE, never delete.

    Expects rows with keys: user_uid, ku_uid, edge_props, covering_ps (the
    PathSteps whose USES_KU covers this Ku). Exactly one covering PS is
    migratable; zero or several go to Mike's dialog.
    """
    plans: list[KuEnrollmentMigration] = []
    for row in rows:
        plan = KuEnrollmentMigration(
            user_uid=row["user_uid"],
            ku_uid=row["ku_uid"],
            covering_ps=sorted(row.get("covering_ps") or []),
            edge_props=dict(row.get("edge_props") or {}),
        )
        if not plan.covering_ps:
            plan.blockers.append("no covering PathStep (USES_KU) — Mike's call, do not guess")
        elif len(plan.covering_ps) > 1:
            plan.blockers.append(f"multiple covering PathSteps {plan.covering_ps} — Mike's call")
        plans.append(plan)
    return plans


@dataclass
class RepointPlan:
    """F7: one ruled dupe → survivor ABOUT_ENTITY re-point + dupe deletion."""

    dupe_uid: str
    survivor_uid: str
    label: str = ""
    sources: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


def plan_about_entity_repoints(
    rows: list[dict[str, Any]],
    ruled: dict[str, str] = RULED_ABOUT_ENTITY_REPOINTS,
) -> list[RepointPlan]:
    """F7 categorizer (pure): validate each ruled pair before touching it.

    Expects rows keyed by uid with: uid, title, owner, labels, edge_sigs,
    about_sources. The dupe must still exist, the survivor must exist with
    the same owner and normalized title (it IS the semantic twin), and the
    dupe's edges must be exactly EXPECTED_DUPE_EDGES.
    """
    by_uid = {r["uid"]: r for r in rows}
    plans: list[RepointPlan] = []
    for dupe_uid, survivor_uid in sorted(ruled.items()):
        plan = RepointPlan(dupe_uid=dupe_uid, survivor_uid=survivor_uid)
        dupe = by_uid.get(dupe_uid)
        survivor = by_uid.get(survivor_uid)
        if dupe is None:
            plan.blockers.append("dupe not found (already cleaned?)")
            plans.append(plan)
            continue
        plan.label = domain_label(dupe.get("labels") or []) or ""
        plan.sources = sorted(dupe.get("about_sources") or [])
        if survivor is None:
            plan.blockers.append("survivor missing — cannot re-point")
        else:
            if dupe.get("owner") != survivor.get("owner"):
                plan.blockers.append(
                    f"owner mismatch: {dupe.get('owner')} vs {survivor.get('owner')}"
                )
            if normalized_activity_title(dupe.get("title") or "") != normalized_activity_title(
                survivor.get("title") or ""
            ):
                plan.blockers.append("titles no longer match — not the semantic twin")
        unexpected = set(dupe.get("edge_sigs") or []) - EXPECTED_DUPE_EDGES
        if unexpected:
            plan.blockers.append(f"dupe carries unexpected edges: {sorted(unexpected)}")
        if not plan.label:
            plan.blockers.append("dupe has no single domain label")
        plans.append(plan)
    return plans


def find_role_value_drift(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """F8 categorizer (pure): User.role values that aren't the lowercase enum value.

    Expects rows with keys: uid, role. A value whose lowercase form is a valid
    UserRole normalizes; anything else is reported with fix=None.
    """
    valid = {r.value for r in UserRole}
    drifts: list[dict[str, Any]] = []
    for row in rows:
        role = row.get("role")
        if role is None or role in valid:
            continue
        lowered = role.lower().strip() if isinstance(role, str) else None
        drifts.append(
            {"uid": row["uid"], "role": role, "fix": lowered if lowered in valid else None}
        )
    return drifts


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


async def fetch_test_user_rows(
    driver: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """F5 inputs: (test-user rows with edge signatures, their owned entities)."""
    users = await driver.execute_query(
        """
        MATCH (u:User) WHERE u.uid IN $uids
        OPTIONAL MATCH (u)-[r]-()
        WITH u, collect(DISTINCT type(r) +
             CASE WHEN startNode(r) = u THEN ':out' ELSE ':in' END) AS edge_sigs
        OPTIONAL MATCH (u)-[:HAS_SESSION]->(s:Session)
        WITH u, edge_sigs, count(DISTINCT s) AS session_count
        OPTIONAL MATCH (u)-[:HAD_AUTH_EVENT]->(a)
        RETURN u.uid AS uid, u.email AS email, edge_sigs,
               session_count, count(DISTINCT a) AS auth_event_count
        """,
        uids=list(KNOWN_TEST_USER_UIDS),
    )
    owned = await driver.execute_query(
        """
        MATCH (u:User)-[:OWNS]->(e:Entity) WHERE u.uid IN $uids
        OPTIONAL MATCH (e)-[r]-()
        WITH u, e, collect(DISTINCT type(r) +
             CASE WHEN startNode(r) = e THEN ':out' ELSE ':in' END) AS edge_sigs
        RETURN u.uid AS owner, e.uid AS uid, labels(e) AS labels, edge_sigs
        """,
        uids=list(KNOWN_TEST_USER_UIDS),
    )
    return [dict(r) for r in users.records], [dict(r) for r in owned.records]


async def fetch_orphan_auth_rows(
    driver: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """F5 orphan-sweep inputs: (orphan sessions, orphan auth events)."""
    sessions = await driver.execute_query(
        "MATCH (s:Session) WHERE NOT (s)<-[:HAS_SESSION]-(:User) "
        "RETURN s.uid AS uid, s.user_uid AS user_uid"
    )
    events = await driver.execute_query(
        "MATCH (a:AuthEvent) WHERE NOT (a)<-[:HAD_AUTH_EVENT]-(:User) "
        "RETURN a.uid AS uid, a.user_uid AS user_uid"
    )
    return [dict(r) for r in sessions.records], [dict(r) for r in events.records]


async def fetch_legacy_ku_enrollment_rows(driver: Any) -> list[dict[str, Any]]:
    """F6 inputs: every legacy IN_PROGRESS→:Ku edge + the PathSteps covering the Ku."""
    result = await driver.execute_query(
        """
        MATCH (u:User)-[r:IN_PROGRESS]->(k:Ku)
        OPTIONAL MATCH (ps:PathStep)-[:USES_KU]->(k)
        RETURN u.uid AS user_uid, k.uid AS ku_uid,
               properties(r) AS edge_props,
               collect(DISTINCT ps.uid) AS covering_ps
        """
    )
    return [dict(r) for r in result.records]


async def fetch_about_entity_rows(driver: Any) -> list[dict[str, Any]]:
    """F7 inputs: the ruled dupes + survivors with edges and ABOUT_ENTITY sources."""
    uids = sorted(set(RULED_ABOUT_ENTITY_REPOINTS) | set(RULED_ABOUT_ENTITY_REPOINTS.values()))
    result = await driver.execute_query(
        """
        MATCH (n:Entity) WHERE n.uid IN $uids
        OPTIONAL MATCH (n)-[r]-()
        WITH n, collect(DISTINCT type(r) +
             CASE WHEN startNode(r) = n THEN ':out' ELSE ':in' END) AS edge_sigs
        OPTIONAL MATCH (src)-[:ABOUT_ENTITY]->(n)
        RETURN n.uid AS uid, n.title AS title, n.user_uid AS owner,
               labels(n) AS labels, edge_sigs, collect(DISTINCT src.uid) AS about_sources
        """,
        uids=uids,
    )
    return [dict(r) for r in result.records]


async def fetch_user_role_rows(driver: Any) -> list[dict[str, Any]]:
    """F8 inputs: every User's role property."""
    result = await driver.execute_query("MATCH (u:User) RETURN u.uid AS uid, u.role AS role")
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


async def apply_test_user_cleanup(driver: Any, plans: list[TestUserPlan]) -> tuple[int, int]:
    """F5 apply: owned entities → sessions/auth events → tracker rows → user.

    Returns (users_deleted, owned_entities_deleted). Blocked users are skipped
    whole — partial deletion would leave an unmodeled half-user behind.
    """
    users_deleted = entities_deleted = 0
    for plan in plans:
        if plan.blockers:
            continue
        all_owned_deleted = True
        for entity in plan.owned:
            if await _delete_entity_checked(driver, entity["uid"], entity["label"]):
                entities_deleted += 1
            else:
                all_owned_deleted = False
        if not all_owned_deleted:
            # Deleting the user around a refused entity would orphan it and
            # report success anyway (Kody #504) — leave the whole user for
            # the next run, after the shadow anomaly is resolved.
            print(f"    !! {plan.uid}: owned entity delete refused — user kept")
            continue
        # HAS_SESSION is shared between auth :Session nodes and ADR-078
        # :ConversationSession nodes (companion-neutral edge). Detach-delete the
        # HAS_TURN children too, or a test user's saved discussions would leave
        # orphaned :ConversationTurn nodes (Codex #633 P2). OPTIONAL MATCH keeps
        # this correct for auth sessions (which have no turns).
        await driver.execute_query(
            "MATCH (u:User {uid: $uid})-[:HAS_SESSION]->(s) "
            "OPTIONAL MATCH (s)-[:HAS_TURN]->(t) DETACH DELETE s, t",
            uid=plan.uid,
        )
        await driver.execute_query(
            "MATCH (u:User {uid: $uid})-[:HAD_AUTH_EVENT]->(a) DETACH DELETE a", uid=plan.uid
        )
        if plan.owned:
            await driver.execute_query(
                "MATCH (m:IngestionMetadata) WHERE m.entity_uid IN $uids DETACH DELETE m",
                uids=[e["uid"] for e in plan.owned],
            )
        result = await driver.execute_query(
            "MATCH (u:User {uid: $uid}) DETACH DELETE u RETURN count(u) AS n", uid=plan.uid
        )
        users_deleted += int(result.records[0]["n"]) if result.records else 0
    return users_deleted, entities_deleted


async def apply_orphan_auth_cleanup(driver: Any, plan: OrphanAuthPlan) -> tuple[int, int]:
    """F5 orphan sweep apply. Returns (sessions_deleted, auth_events_deleted)."""
    sessions = events = 0
    if plan.sessions:
        result = await driver.execute_query(
            "MATCH (s:Session) WHERE s.uid IN $uids DETACH DELETE s RETURN count(s) AS n",
            uids=[r["uid"] for r in plan.sessions],
        )
        sessions = int(result.records[0]["n"]) if result.records else 0
    if plan.auth_events:
        result = await driver.execute_query(
            "MATCH (a:AuthEvent) WHERE a.uid IN $uids DETACH DELETE a RETURN count(a) AS n",
            uids=[r["uid"] for r in plan.auth_events],
        )
        events = int(result.records[0]["n"]) if result.records else 0
    return sessions, events


async def apply_ku_enrollment_migrations(driver: Any, plans: list[KuEnrollmentMigration]) -> int:
    """F6 apply: move the legacy edge onto the covering PS, properties intact.

    ``ON CREATE`` only — an existing IN_PROGRESS on the target PS is real,
    current study state and must never be clobbered by 2026-04 legacy props.
    """
    migrated = 0
    for plan in plans:
        if plan.blockers or plan.target_ps is None:
            continue
        result = await driver.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[old:IN_PROGRESS]->(k:Ku {uid: $ku_uid})
            MATCH (ps:Entity:PathStep {uid: $ps_uid})
            MERGE (u)-[new:IN_PROGRESS]->(ps)
            ON CREATE SET new += properties(old)
            DELETE old
            RETURN count(old) AS n
            """,
            user_uid=plan.user_uid,
            ku_uid=plan.ku_uid,
            ps_uid=plan.target_ps,
        )
        migrated += int(result.records[0]["n"]) if result.records else 0
    return migrated


async def apply_uncovered_ku_edge_deletions(driver: Any, plans: list[KuEnrollmentMigration]) -> int:
    """F6 fallback (``--delete-uncovered-ku-edges``, post-dialog only): delete
    the legacy edges that have NO covering PS — there is nothing to migrate to.
    """
    deleted = 0
    for plan in plans:
        if plan.covering_ps:
            continue  # migratable or multi-covered — not this fallback's business
        result = await driver.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[old:IN_PROGRESS]->(k:Ku {uid: $ku_uid})
            DELETE old
            RETURN count(old) AS n
            """,
            user_uid=plan.user_uid,
            ku_uid=plan.ku_uid,
        )
        deleted += int(result.records[0]["n"]) if result.records else 0
    return deleted


async def apply_about_entity_repoints(driver: Any, plans: list[RepointPlan]) -> tuple[int, int]:
    """F7 apply: move ABOUT_ENTITY edges to the survivor, then delete the dupe.

    Returns (edges_repointed, dupes_deleted).
    """
    repointed = deleted = 0
    for plan in plans:
        if plan.blockers:
            continue
        # Shadow precheck BEFORE mutating: re-pointing first and then refusing
        # the delete would leave the pair half-migrated (Kody #504).
        shadow = await driver.execute_query(
            "MATCH (c:Content {uid: $uid}) RETURN count(c) AS n", uid=plan.dupe_uid
        )
        if shadow.records and int(shadow.records[0]["n"]) > 0:
            print(f"    !! {plan.dupe_uid}: :Content shadow shares this uid — pair skipped")
            continue
        result = await driver.execute_query(
            """
            MATCH (src)-[old:ABOUT_ENTITY]->(dupe:Entity {uid: $dupe_uid})
            MATCH (survivor:Entity {uid: $survivor_uid})
            MERGE (src)-[new:ABOUT_ENTITY]->(survivor)
            ON CREATE SET new += properties(old)
            DELETE old
            RETURN count(old) AS n
            """,
            dupe_uid=plan.dupe_uid,
            survivor_uid=plan.survivor_uid,
        )
        repointed += int(result.records[0]["n"]) if result.records else 0
        if await _delete_entity_checked(driver, plan.dupe_uid, plan.label):
            deleted += 1
    return repointed, deleted


async def apply_role_normalizations(driver: Any, drifts: list[dict[str, Any]]) -> int:
    """F8 apply: lowercase the fixable role values."""
    fixed = 0
    for drift in drifts:
        if not drift["fix"]:
            continue
        result = await driver.execute_query(
            "MATCH (u:User {uid: $uid}) SET u.role = $fix RETURN count(u) AS n",
            uid=drift["uid"],
            fix=drift["fix"],
        )
        fixed += int(result.records[0]["n"]) if result.records else 0
    return fixed


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
    test_user_plans: list[TestUserPlan],
    orphan_auth: OrphanAuthPlan,
    ku_migrations: list[KuEnrollmentMigration],
    repoints: list[RepointPlan],
    role_drifts: list[dict[str, Any]],
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

    deletable_users = [p for p in test_user_plans if not p.blockers]
    print(
        f"\n[FIX F5] test users to delete (with subtrees): "
        f"{len(deletable_users)}/{len(test_user_plans)}"
    )
    for plan in test_user_plans:
        status = "delete" if not plan.blockers else f"BLOCKED ({'; '.join(plan.blockers)})"
        print(
            f"    {status} {plan.uid} ({plan.email}) — {len(plan.owned)} owned entities, "
            f"{plan.session_count} sessions, {plan.auth_event_count} auth events"
        )
        for entity in plan.owned:
            print(f"        owned: {entity['uid']} :{entity['label']} {entity['edge_sigs']}")
    print(
        f"    orphan sweep (earlier test-user deletions): "
        f"{len(orphan_auth.sessions)} sessions, {len(orphan_auth.auth_events)} auth events"
    )
    for row in orphan_auth.sessions:
        print(f"        session {row['uid']} (user_uid={row['user_uid']})")
    for row in orphan_auth.auth_events:
        print(f"        auth event {row['uid']} (user_uid={row['user_uid']})")
    if orphan_auth.audit_trail:
        print(
            f"    kept: {len(orphan_auth.audit_trail)} null-user_uid AuthEvents "
            f"(failed-login audit trail, by design)"
        )

    migratable = [p for p in ku_migrations if not p.blockers]
    print(
        f"\n[FIX F6] legacy IN_PROGRESS→:Ku edges (RULED: migrate to covering PS): "
        f"{len(migratable)}/{len(ku_migrations)} migratable"
    )
    for migration in ku_migrations:
        props = {k: str(v) for k, v in migration.edge_props.items()}
        if migration.blockers:
            print(
                f"    DIALOG {migration.user_uid} → {migration.ku_uid} — "
                f"{'; '.join(migration.blockers)} (props: {props})"
            )
        else:
            print(
                f"    migrate {migration.user_uid} → {migration.ku_uid} "
                f"onto PS {migration.target_ps}"
            )

    fixable_repoints = [p for p in repoints if not p.blockers]
    print(
        f"\n[FIX F7] ABOUT_ENTITY re-points (RULED pairs): {len(fixable_repoints)}/{len(repoints)}"
    )
    for repoint in repoints:
        status = "re-point" if not repoint.blockers else f"BLOCKED ({'; '.join(repoint.blockers)})"
        print(
            f"    {status} {repoint.dupe_uid} → survivor {repoint.survivor_uid} "
            f"(sources: {repoint.sources})"
        )

    fixable_roles = [d for d in role_drifts if d["fix"]]
    print(f"\n[FIX F8] User.role value drift: {len(fixable_roles)}/{len(role_drifts)} fixable")
    for drift in role_drifts:
        if drift["fix"]:
            print(f"    {drift['uid']}: {drift['role']!r} → {drift['fix']!r}")
        else:
            print(f"    REPORT {drift['uid']}: {drift['role']!r} — no valid lowercase form")

    print(
        f"\n[REPORT R2] multi-owner daily-note collisions remaining after F3+F5: "
        f"{len(residual_collisions)}"
    )
    for c in residual_collisions:
        print(f"    {c['date']}: {', '.join(c['entries'])}")

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
        help="Execute the FIX categories (F1–F8). Run the dry-run and get sign-off first.",
    )
    parser.add_argument(
        "--delete-uncovered-ku-edges",
        action="store_true",
        help="F6 fallback, post-dialog only: delete legacy IN_PROGRESS→:Ku edges "
        "that have NO covering PathStep (nothing to migrate to). Requires --apply.",
    )
    args = parser.parse_args()

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    content_owner = os.getenv("SKUEL_CONTENT_VAULT_OWNER", "user_admin")

    conn = Neo4jConnection()
    driver = conn.connect()
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

        user_rows, owned_rows = await fetch_test_user_rows(driver)
        test_user_plans = plan_test_user_cleanup(user_rows, owned_rows)
        orphan_auth = plan_orphan_auth_cleanup(*await fetch_orphan_auth_rows(driver))
        ku_migrations = plan_ku_enrollment_migrations(await fetch_legacy_ku_enrollment_rows(driver))
        repoints = plan_about_entity_repoints(await fetch_about_entity_rows(driver))
        role_drifts = find_role_value_drift(await fetch_user_role_rows(driver))

        # Residual collisions = what F3 + F5 do NOT resolve (expected: none).
        f5_deleted_uids = {e["uid"] for p in test_user_plans if not p.blockers for e in p.owned}
        surviving_entries = [
            r
            for r in entry_rows
            if (r.get("uid") or "") not in wrong_door.deleted_entry_uids
            and (r.get("uid") or "") not in f5_deleted_uids
        ]
        residual_collisions = find_daily_owner_collisions(surviving_entries)
        anomalies = await fetch_anomalies(driver)

        print_dry_run(
            mismatches,
            fixable,
            blocked,
            wrong_door,
            dedup_fixable,
            dedup_blocked,
            residual_collisions,
            test_user_plans,
            orphan_auth,
            ku_migrations,
            repoints,
            role_drifts,
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
        f5_users, f5_entities = await apply_test_user_cleanup(driver, test_user_plans)
        f5_expected_users = len([p for p in test_user_plans if not p.blockers])
        print(
            f"F5: deleted {f5_users}/{f5_expected_users} test users, {f5_entities} owned entities"
        )
        f5_sessions, f5_events = await apply_orphan_auth_cleanup(driver, orphan_auth)
        print(
            f"F5 orphan sweep: deleted {f5_sessions}/{len(orphan_auth.sessions)} sessions, "
            f"{f5_events}/{len(orphan_auth.auth_events)} auth events "
            f"({len(orphan_auth.audit_trail)} audit-trail rows kept)"
        )
        f6_migrated = await apply_ku_enrollment_migrations(driver, ku_migrations)
        f6_expected = len([p for p in ku_migrations if not p.blockers])
        print(f"F6: migrated {f6_migrated}/{f6_expected} legacy :Ku enrollment edges")
        if args.delete_uncovered_ku_edges:
            f6_deleted = await apply_uncovered_ku_edge_deletions(driver, ku_migrations)
            print(f"F6 fallback: deleted {f6_deleted} uncovered legacy :Ku edges (post-dialog)")
        f7_repointed, f7_deleted = await apply_about_entity_repoints(driver, repoints)
        f7_expected = len([p for p in repoints if not p.blockers])
        print(
            f"F7: re-pointed {f7_repointed} ABOUT_ENTITY edges, "
            f"deleted {f7_deleted}/{f7_expected} dupes"
        )
        f8_fixed = await apply_role_normalizations(driver, role_drifts)
        f8_expected = len([d for d in role_drifts if d["fix"]])
        print(f"F8: normalized {f8_fixed}/{f8_expected} User.role values")

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
        post_users, post_owned = await fetch_test_user_rows(driver)
        residual_test_users = plan_test_user_cleanup(post_users, post_owned)
        residual_orphans = plan_orphan_auth_cleanup(*await fetch_orphan_auth_rows(driver))
        residual_migrations = plan_ku_enrollment_migrations(
            await fetch_legacy_ku_enrollment_rows(driver)
        )
        if args.delete_uncovered_ku_edges:
            residual_ku = residual_migrations  # everything should be gone
        else:
            residual_ku = [p for p in residual_migrations if not p.blockers]
        residual_repoints = [
            p
            for p in plan_about_entity_repoints(await fetch_about_entity_rows(driver))
            if "dupe not found" not in "; ".join(p.blockers)
        ]
        residual_roles = [
            d for d in find_role_value_drift(await fetch_user_role_rows(driver)) if d["fix"]
        ]
        print(
            f"\nPost-apply: {len(residual_types)} type mismatches, "
            f"{len(residual_dups)} fixable same-entry groups, "
            f"{len(residual_wrong_door.entries_to_delete)} wrong-door entries, "
            f"{len(residual_wrong_door.entities_to_delete)} wrong-door entities, "
            f"{len(residual_dedup)} fixable cross-entry groups, "
            f"{len(residual_test_users)} test users, "
            f"{len(residual_orphans.sessions) + len(residual_orphans.auth_events)} orphan "
            f"sessions/auth events, "
            f"{len(residual_ku)} actionable legacy :Ku edges, "
            f"{len(residual_repoints)} pending re-points, "
            f"{len(residual_roles)} fixable role drifts remaining"
        )
        clean = (
            not residual_types
            and not residual_dups
            and not residual_wrong_door.entries_to_delete
            and not residual_wrong_door.entities_to_delete
            and not residual_dedup
            and not residual_test_users
            and not residual_orphans.sessions
            and not residual_orphans.auth_events
            and not residual_ku
            and not residual_repoints
            and not residual_roles
        )
        return 0 if clean else 1
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
