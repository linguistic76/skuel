#!/usr/bin/env python3
"""
Graph Vocabulary Audit — the DATA-side twin of SKUEL030
=======================================================

Asserts that every node label, relationship type and ``entity_type`` value
present in the **live graph** is a member of its enum (``NeoLabel`` /
``RelationshipName`` / ``EntityType``).

**Why this exists.** SKUEL030 and CYP011 check the vocabulary that appears in
*source* Cypher. Nothing checked the vocabulary that actually exists in the
*database*, and the two drift apart in one direction that is completely silent:
**Neo4j answers an unknown label or relationship type with zero rows, never an
error.** So a value the enums no longer contain is not a crash — it is data that
every reader steps over. #1003 gated the ingestion write door; a hand-run
migration, a stray ``SET``, or a rename that landed in code but not in data all
bypass that door entirely.

Found on its first run: a live ``SUPPORTS_HABIT`` edge, which two code comments
asserted "was never written" (#1010).

**Registry residue is not drift.** ``db.labels()`` and ``db.relationshipTypes()``
keep returning a name after the last node/edge carrying it is deleted, until the
store is compacted. A stray holding ZERO rows is therefore reported as INFO and
does not fail the run — failing on it would make this audit permanently red for
a condition that is both harmless and outside the app's control. A stray holding
data is a real finding and exits non-zero.

Read-only: this script never writes. Fixes belong in
``scripts/migrations/`` (data) or in the enums (vocabulary).

Usage:
    uv run python scripts/audit_graph_vocabulary.py            # exit 1 if any stray holds data
    uv run python scripts/audit_graph_vocabulary.py --verbose  # list every live value
    ./dev audit-graph-vocabulary
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models.enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# Labels Neo4j or the app creates that are deliberately not domain identities.
# :Content is the chunk shadow (G13); the rest are infrastructure nodes that
# predate NeoLabel and are not entity vocabulary.
NON_ENTITY_LABELS: frozenset[str] = frozenset(
    {
        "Content",
        "Chunk",
        "ReferenceChunk",
        "ContentChunk",
        "User",
        "Group",
        "Session",
        "AuthEvent",
        "SearchEvent",
        "IngestionMetadata",
        "ConversationSession",
        "Resource",
    }
)


@dataclass(frozen=True)
class Stray:
    """A live vocabulary value with no enum member.

    ``count`` is what separates a real finding from registry residue: zero means
    Neo4j is still listing a name whose last row is gone.
    """

    kind: str  # "label" | "relationship" | "entity_type"
    value: str
    count: int

    @property
    def holds_data(self) -> bool:
        return self.count > 0


def escape_identifier(name: str) -> str:
    """Backtick-quote a live label/relationship name for safe interpolation.

    These names come from the database, not from source, so they are arbitrary
    text — and Neo4j permits an embedded backtick via doubling. Interpolating a
    raw name would close the quoted identifier early and break the very audit
    that exists to inspect stray names (Codex P2, #1010).
    """
    return "`" + name.replace("`", "``") + "`"


def domain_label_values() -> list[str]:
    """Every label that identifies a domain entity, sourced from EntityType.

    Used to scope the ``entity_type`` scan: a node carrying that property is a
    domain node only if it wears :Entity or one of these. Enum-sourced so a new
    EntityType widens the scan automatically.
    """
    return sorted({NeoLabel.from_entity_type(et).value for et in EntityType})


def normalize_entity_type(raw: object) -> str:
    """Render a persisted ``entity_type`` to a comparable string key.

    A string passes through unchanged. Anything else — a number, a boolean, a
    list left by a bad write — is rendered with a marker that cannot collide
    with any enum value, so it is classified as drift rather than crashing the
    scan on an unhashable key.
    """
    if isinstance(raw, str):
        return raw
    return f"<non-string {type(raw).__name__}: {raw!r}>"


def classify_strays(
    live_labels: dict[str, int],
    live_relationships: dict[str, int],
    live_entity_types: dict[str, int],
) -> list[Stray]:
    """Pure categorizer: live {value: row_count} maps → strays, enum-sourced.

    Kept pure so it is unit-testable without a database — the same split the
    other audit scripts use.
    """
    known_labels = {label.value for label in NeoLabel} | NON_ENTITY_LABELS
    known_relationships = {rel.value for rel in RelationshipName}
    known_entity_types = {et.value for et in EntityType}

    strays: list[Stray] = []
    for value, count in sorted(live_labels.items()):
        if value not in known_labels:
            strays.append(Stray("label", value, count))
    for value, count in sorted(live_relationships.items()):
        if value not in known_relationships:
            strays.append(Stray("relationship", value, count))
    for value, count in sorted(live_entity_types.items()):
        if value not in known_entity_types:
            strays.append(Stray("entity_type", value, count))
    return strays


async def fetch_live_vocabulary(
    driver: AsyncDriver,
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    """Read every label, relationship type and entity_type value, with row counts.

    Counts are fetched per name rather than via a single aggregate because a
    ``count()`` over a MATCH that finds nothing returns NO ROW AT ALL, not zero —
    reading an empty result as "clean" is how registry residue would go unseen.
    """
    async with driver.session() as session:
        label_names = [
            record["label"]
            for record in await (
                await session.run("CALL db.labels() YIELD label RETURN label")
            ).data()
        ]
        relationship_names = [
            record["relationshipType"]
            for record in await (
                await session.run(
                    "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"
                )
            ).data()
        ]

        labels: dict[str, int] = {}
        for name in label_names:
            rows = await (
                await session.run(f"MATCH (n:{escape_identifier(name)}) RETURN count(n) AS c")
            ).data()
            labels[name] = rows[0]["c"] if rows else 0

        relationships: dict[str, int] = {}
        for name in relationship_names:
            rows = await (
                await session.run(
                    f"MATCH ()-[r:{escape_identifier(name)}]->() RETURN count(r) AS c"
                )
            ).data()
            relationships[name] = rows[0]["c"] if rows else 0

        # Scope: :Entity OR any EntityType-backed DOMAIN label — deliberately
        # neither narrower nor wider (Codex P2, twice, #1010).
        #
        # Narrower (`MATCH (n:Entity)`) misses the realistic corruption: the
        # backfill migrations key on DOMAIN labels (`MATCH (n:Task) ... SET
        # n.entity_type`), never on :Entity, so `(:Task {entity_type: 'x'})`
        # with no base label would exit clean.
        #
        # Wider (every node with the property) is a FALSE POSITIVE, because
        # `entity_type` is not exclusively a domain discriminator: an
        # :IngestionError node records which entity type a failed FILE was
        # about, and an edge-YAML validation failure stores the literal "edge"
        # (`batch.py` → `IngestionBackend.create_error_nodes`). That is
        # metadata, not vocabulary — reporting it would turn the audit red on a
        # perfectly clean domain graph.
        #
        # entity_type is free-form, so a corrupt node can hold a number, a
        # boolean or a list. Those are exactly what this audit exists to
        # surface, so they must be REPORTED — not crash the run on an unhashable
        # dict key or a mixed-type sorted(). normalize_entity_type renders any
        # non-string to a form that can never match an enum value, so it lands
        # in the stray list by construction.
        entity_types: dict[str, int] = {}
        for record in await (
            await session.run(
                "MATCH (n) WHERE n.entity_type IS NOT NULL "
                "  AND (n:Entity OR any(lbl IN labels(n) WHERE lbl IN $domain_labels)) "
                "RETURN n.entity_type AS entity_type, count(n) AS c",
                {"domain_labels": domain_label_values()},
            )
        ).data():
            key = normalize_entity_type(record["entity_type"])
            entity_types[key] = entity_types.get(key, 0) + record["c"]

    return labels, relationships, entity_types


def report(
    strays: list[Stray],
    *,
    verbose: bool,
    live_labels: dict[str, int],
    live_relationships: dict[str, int],
    live_entity_types: dict[str, int],
) -> int:
    """Print findings; return the process exit code."""
    print("Graph Vocabulary Audit — live graph vs NeoLabel / RelationshipName / EntityType")
    print("=" * 78)
    print(
        f"scanned: {len(live_labels)} labels, {len(live_relationships)} relationship types, "
        f"{len(live_entity_types)} entity_type values"
    )

    drift = [s for s in strays if s.holds_data]
    residue = [s for s in strays if not s.holds_data]

    if drift:
        print(f"\n✗ {len(drift)} stray value(s) HOLDING DATA — invisible to every reader:")
        for s in drift:
            print(f"    {s.kind:<13} {s.value:<28} {s.count} row(s)")
        print(
            "\n  Neo4j returns zero rows for an unknown label/type rather than erroring,\n"
            "  so this data is silently unreachable. Fix by migrating the data to the\n"
            "  canonical value, or by restoring the member if its removal was wrong."
        )

    if residue:
        print(f"\nℹ {len(residue)} stray name(s) with NO rows — registry residue, not drift:")
        for s in residue:
            print(f"    {s.kind:<13} {s.value}")
        print("  Neo4j lists a name until the store is compacted. Nothing to do.")

    if verbose:
        stray_values = {(s.kind, s.value) for s in strays}
        for kind, live in (
            ("label", live_labels),
            ("relationship", live_relationships),
            ("entity_type", live_entity_types),
        ):
            print(f"\n{kind}s ({len(live)}):")
            for value, count in sorted(live.items()):
                mark = "stray" if (kind, value) in stray_values else "ok"
                print(f"    {mark:<6} {value:<34} {count} row(s)")

    if not drift:
        print("\n✓ No stray vocabulary holding data.")
        return 0
    return 1


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--verbose", action="store_true", help="List every live value.")
    args = parser.parse_args()

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    conn = Neo4jConnection()
    driver = conn.connect()
    try:
        labels, relationships, entity_types = await fetch_live_vocabulary(driver)
    finally:
        await conn.close()

    strays = classify_strays(labels, relationships, entity_types)
    return report(
        strays,
        verbose=args.verbose,
        live_labels=labels,
        live_relationships=relationships,
        live_entity_types=entity_types,
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
