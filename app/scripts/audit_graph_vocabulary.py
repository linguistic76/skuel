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

**A zero-row stray is usually held by a stale INDEX, and is cleanable.** #1010
shipped the claim that ``db.labels()`` keeps returning a name "until the store is
compacted, nothing to do". Both halves were wrong, and measuring beat reasoning:
dropping ``exercise_report_uid_idx`` removed ``ExerciseReport`` from
``db.labels()`` immediately. An index (or constraint) on a label or relationship
type keeps that name in the registry even at ZERO rows — so the four labels
#1010 reported as inert residue were really five stale indexes, and dropping
them erased all four (41 labels → 37). The same mechanism applies to
``db.relationshipTypes()``.

There is no ``DROP LABEL`` in Cypher; dropping the schema object that references
it is the mechanism. This audit therefore NAMES the holding index so the fix is
obvious rather than declaring the condition untouchable.

**Exit code still means "is the data reachable".** A zero-row stray does not fail
the run even though it is actionable: nothing is unreachable, so this is schema
hygiene rather than data corruption, and a red exit should mean the graph is
lying to its readers. Strays holding DATA exit non-zero.

Read-only: this script never writes. Fixes belong in ``scripts/migrations/``
(data), ``scripts/indexes.cypher`` (stale schema objects), or the enums
(vocabulary).

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


@dataclass(frozen=True)
class SchemaHolder:
    """A schema object keeping a token alive in the registry.

    ``kind`` is retained because the cleanup COMMAND differs — a constraint needs
    ``DROP CONSTRAINT``, not ``DROP INDEX`` (see
    ``scripts/migrations/drop_stale_bootstrap_constraints_2026_07.cypher``).
    Collapsing the two would hand the reader an instruction that fails.

    ``tokens`` is the FULL set the object covers, because a fulltext index may
    span several labels. If it covers a live label as well as the stray one,
    dropping it destroys working search coverage — so the remediation is a
    recreate-without, not a DROP (Codex P2, #1011).
    """

    name: str
    kind: str  # "INDEX" | "CONSTRAINT"
    tokens: tuple[str, ...] = ()

    def covers_only(self, token: str) -> bool:
        """True when this object exists solely for ``token``, so DROP is safe."""
        return set(self.tokens) <= {token}

    def remediation(self, token: str) -> str:
        r"""The cleanup instruction for freeing ``token`` from this object.

        Names are backtick-quoted with doubling: a schema name may legally
        contain spaces (verified) or a backtick, and an unquoted name yields an
        invalid statement that someone will paste and puzzle over. Caveat kept
        honest: Cypher also decodes ``\uXXXX`` INSIDE a quoted identifier
        (#1010), so a name containing that literal text still needs a human —
        there is no parameterized form of DROP INDEX to fall back on.
        """
        if "\\" in self.name:
            # Cypher re-decodes escape sequences INSIDE a quoted identifier
            # (#1010), so `Esc\u0060Probe` would be read back as a DIFFERENT
            # name — quoting cannot express it and DROP INDEX has no
            # parameterized form. Verified reachable: an index named
            # `back\slash` creates fine. Emit guidance that CANNOT be pasted as
            # a command rather than a command that silently targets the wrong
            # object (Codex P2, #1011).
            return (
                f"MANUAL: {self.kind} named {self.name!r} contains a backslash escape that "
                f"Cypher re-decodes inside a quoted identifier — there is no safe literal "
                f"form; drop it by hand"
            )

        quoted = "`" + self.name.replace("`", "``") + "`"
        if self.covers_only(token):
            return f"DROP {self.kind} {quoted} IF EXISTS;"
        others = ", ".join(sorted(t for t in self.tokens if t != token))
        return (
            f"{self.kind} {quoted} also covers {others} — do NOT drop it; "
            f"recreate it without {token}"
        )


# Neo4j's entityType → the Stray.kind it can hold.
_ENTITY_TYPE_TO_STRAY_KIND: dict[str, str] = {"NODE": "label", "RELATIONSHIP": "relationship"}


async def fetch_schema_holders(driver: AsyncDriver) -> dict[tuple[str, str], list[SchemaHolder]]:
    """Map each ``(stray_kind, token)`` to the schema objects referencing it.

    This is what turns "inert residue, nothing to do" into an actionable line:
    an index or constraint keeps a name alive in ``db.labels()`` /
    ``db.relationshipTypes()`` at zero rows, so naming it tells the reader
    exactly what to DROP.

    Keyed by ``(kind, token)`` rather than token alone: a label and a
    relationship type may share a spelling, and a RELATIONSHIP index on
    ``Legacy`` does not hold a ``:Legacy`` LABEL alive — pointing at it would
    send the reader to drop something that cannot fix their problem. The graph
    already carries a relationship index, so the two namespaces genuinely
    coexist here.
    """
    holders: dict[tuple[str, str], list[SchemaHolder]] = {}
    async with driver.session() as session:
        # A uniqueness CONSTRAINT owns a backing INDEX of the SAME NAME, so a
        # naive union reports the object twice and advises `DROP INDEX` on it —
        # which Neo4j refuses ("index belongs to constraint"). `owningConstraint`
        # is the discriminator; skip owned indexes and let the constraint row
        # speak for the pair.
        index_rows = await (
            await session.run(
                "SHOW INDEXES YIELD name, entityType, labelsOrTypes, owningConstraint "
                "WHERE owningConstraint IS NULL "
                "RETURN name, entityType, labelsOrTypes"
            )
        ).data()
        constraint_rows = await (
            await session.run(
                "SHOW CONSTRAINTS YIELD name, entityType, labelsOrTypes "
                "RETURN name, entityType, labelsOrTypes"
            )
        ).data()

        for rows, holder_kind in ((index_rows, "INDEX"), (constraint_rows, "CONSTRAINT")):
            for record in rows:
                stray_kind = _ENTITY_TYPE_TO_STRAY_KIND.get(record["entityType"])
                if stray_kind is None:
                    continue
                covered = tuple(record["labelsOrTypes"] or [])
                for token in covered:
                    holders.setdefault((stray_kind, token), []).append(
                        SchemaHolder(name=record["name"], kind=holder_kind, tokens=covered)
                    )
    return {key: sorted(set(found), key=lambda h: h.name) for key, found in holders.items()}


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

    Names are bound as PARAMETERS via Neo4j's dynamic label/type syntax
    (``:$($label)``), never interpolated into the query text. A live name is
    arbitrary text, and backtick-quoting it is not sufficient: Cypher decodes
    ``\\uXXXX`` escapes INSIDE a quoted identifier, so a label whose literal
    characters are ``Esc\\u0060Probe`` is re-read as a backtick and closes the
    identifier early — the audit crashed on exactly the pathological name it
    exists to inspect (Codex P2, #1010; reproduced with a dynamic-label CREATE).
    Doubling backticks cannot fix that, and a decode-then-double scheme would
    resolve to a DIFFERENT label than the one on disk. Parameters sidestep
    quoting altogether, which is also what CYP003 asks of every other query here.
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
                await session.run("MATCH (n:$($label)) RETURN count(n) AS c", {"label": name})
            ).data()
            labels[name] = rows[0]["c"] if rows else 0

        relationships: dict[str, int] = {}
        for name in relationship_names:
            rows = await (
                await session.run(
                    "MATCH ()-[r:$($rel_type)]->() RETURN count(r) AS c", {"rel_type": name}
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
    schema_holders: dict[tuple[str, str], list[SchemaHolder]] | None = None,
) -> int:
    """Print findings; return the process exit code."""
    holders = schema_holders or {}
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
        held = [s for s in residue if holders.get((s.kind, s.value))]
        unheld = [s for s in residue if not holders.get((s.kind, s.value))]

        if held:
            print(
                f"\n⚠ {len(held)} stray name(s) with NO rows, held alive by a stale "
                f"INDEX/CONSTRAINT:"
            )
            for s in held:
                for holder in holders[(s.kind, s.value)]:
                    print(f"    {s.kind:<13} {s.value:<28} {holder.remediation(s.value)}")
            print(
                "\n  An index or constraint keeps a name in db.labels() / "
                "db.relationshipTypes()\n"
                "  even at zero rows. There is no DROP LABEL — dropping the schema object IS\n"
                "  the mechanism. Retire indexes in scripts/indexes.cypher (Stale indexes\n"
                "  section); constraints need DROP CONSTRAINT, as in\n"
                "  scripts/migrations/drop_stale_bootstrap_constraints_2026_07.cypher."
            )

        if unheld:
            print(f"\nℹ {len(unheld)} stray name(s) with NO rows and no schema object:")
            for s in unheld:
                print(f"    {s.kind:<13} {s.value}")
            print("  Genuine token residue — clears when the store is next compacted.")

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
        schema_holders = await fetch_schema_holders(driver)
    finally:
        await conn.close()

    strays = classify_strays(labels, relationships, entity_types)
    return report(
        strays,
        verbose=args.verbose,
        live_labels=labels,
        live_relationships=relationships,
        live_entity_types=entity_types,
        schema_holders=schema_holders,
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
