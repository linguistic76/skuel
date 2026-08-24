#!/usr/bin/env python3
"""Recompute ``EXTRACTED_FROM.source_line_hash`` where the stored digest still has a ``✅`` in it — once.

A ONE-SHOT migration — no background loop, so the CORE "no background workers"
guarantee holds. Tier-independent: pure graph + vault-file maintenance, no API
keys.

``source_line_hash`` is the vault round-trip's line identity (ADR-070 Decision
1): the digest of a task line with its checkbox, 🆔 token and whitespace
normalised away, stored on the ``EXTRACTED_FROM`` edge so a re-ingested line
SKUEL has already extracted is recognised (extraction Guard 2) and so an
ID-less line can be found for 🆔 injection. Until this migration's companion
fix, the normalisation did NOT strip the ``✅ YYYY-MM-DD`` done-date token —
so SKUEL's own outbound write-back (``[x]`` + ``✅``) changed a line's digest,
Guard 2 missed on the next sync, and the freshly-completed task was created a
second time (Guard 4 ignores terminal twins by design).

The fix strips ``✅`` from the digest. That orphans every hash that was stored
WITH the token inside it — every extraction of an already-checked line (the
``- [x] … ✅ date`` create door): the current normalisation no longer produces
the stored value, so the next re-ingest of that file would duplicate the task.
The fix would trigger the bug it fixes. This script reconnects those rows:

1. For every ``EXTRACTED_FROM`` edge carrying a hash, locate the line it
   describes — in the vault file the entry's ``vault_file_path`` names (the
   vault is the source of truth for user data; for the ``local_agent``
   transport that path is the server-side mirror, i.e. the vault as of the
   last pull), or, for an entry that never came from a vault file, in the
   entry's own content. The 🆔 token is the primary join (``r.vault_id`` ↔
   ``🆔 <id>`` on the line); an ID-less edge is joined by digest, the same
   by-hash locator the reconciler itself uses for injection.
2. Classify. **Rewrite** only when the stored hash equals the RETIRED
   normalisation's digest of that line and differs from the current one —
   the digest equality is the proof that nothing but the ``✅`` token
   separates them. Everything else is reported, never guessed at: a line
   whose stored hash matches neither digest was edited since extraction
   (ADR-070 keeps the hash as a change signal — rewriting it would erase the
   edit), a line or file that is gone, an entry with no source text.
3. With ``--confirm``, write the new digest — guarded on the stored value the
   census saw, so a sync that lands between census and write is skipped, not
   clobbered — and re-census to prove nothing rewritable remains.

Idempotent: the second run classifies every row as current and writes nothing.

**Version skew (``local_agent`` transport only).** The line-hash contract is
shared with the user-side vault agent (ADR-075 B3 — ``apply_inject_id`` runs
ON THE DEVICE and compares the server's ``source_line_hash`` against its own
digest of each line). An agent still running the retired normalisation
computes a different digest for any ``✅``-bearing ID-less line, so the
server's injection request for such a line silently finds no target. There is
no compatibility shim (One Path Forward): update the agent — it imports the
contract from the checkout it runs from, so pulling the repo on the device is
the update. The filesystem transport applies the mutations server-side and is
unaffected.

Usage:
    uv run scripts/rehash_vault_line_hashes.py             # census only (default)
    uv run scripts/rehash_vault_line_hashes.py --confirm   # write
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.ports.vault_bridge_protocol import VAULT_ID_RE, normalize_vault_line_hash

if TYPE_CHECKING:
    from neo4j import AsyncDriver

_ENTITY = NeoLabel.ENTITY.value
_USER_ENTRY = NeoLabel.USER_ENTRY.value
_EXTRACTED_FROM = RelationshipName.EXTRACTED_FROM.value

# The line-content source an entry that never came from a vault file offers.
ENTRY_CONTENT_SOURCE = "entry.content"


def legacy_normalize_vault_line_hash(line: str) -> str:
    """The RETIRED line digest — checkbox + 🆔 + whitespace normalised, ``✅`` kept.

    Frozen here, and only here, as the join key for hashes stored before the
    ``✅`` strip. Not a second definition of the contract: the contract is
    ``normalize_vault_line_hash``; this is the shape the migration is retiring
    and it leaves with the script.
    """
    line = re.sub(r"^[-*]\s*\[[xX]\]\s*", "- [ ] ", line)
    line = re.sub(r"^[-*]\s*\[\s*\]\s*", "- [ ] ", line)
    line = VAULT_ID_RE.sub("", line)
    return hashlib.sha256(" ".join(line.split()).encode("utf-8")).hexdigest()


# READ-ONLY. Every provenance edge that carries a hash, with what the join
# needs from both ends: the entry's metadata (a JSON string on the node —
# ``vault_file_path`` lives in it) and content (the fallback source for
# non-vault entries), the edge's stored hash and 🆔.
ROWS_QUERY = f"""
MATCH (e:{_ENTITY})-[r:{_EXTRACTED_FROM}]->(entry:{_USER_ENTRY})
WHERE r.source_line_hash IS NOT NULL AND r.source_line_hash <> ''
RETURN entry.uid AS entry_uid,
       entry.metadata AS entry_metadata,
       entry.content AS entry_content,
       e.uid AS entity_uid,
       r.source_line_hash AS stored_hash,
       r.vault_id AS vault_id
ORDER BY entry.uid, e.uid
"""

# Guarded on the value the census saw: a sync that rewrote the edge between
# census and write (the fixed extractor re-stamping it) is skipped, and the
# re-census afterwards reports it as current rather than the write clobbering
# a fresher digest.
REWRITE_QUERY = f"""
UNWIND $rewrites AS rw
MATCH (e:{_ENTITY} {{uid: rw.entity_uid}})
      -[r:{_EXTRACTED_FROM}]->(entry:{_USER_ENTRY} {{uid: rw.entry_uid}})
WHERE r.source_line_hash = rw.old_hash
SET r.source_line_hash = rw.new_hash
RETURN count(r) AS n
"""


class EdgeRow(TypedDict):
    """One ``ROWS_QUERY`` row, keyed by its RETURN aliases, metadata already parsed.

    ``vault_file_path`` is the absolute path the ingest door stamped when the
    entry came from a vault file, or ``None`` for an API/upload entry;
    ``entry_content`` is that entry's own text, the fallback line source.
    """

    entry_uid: str
    entity_uid: str
    stored_hash: str
    vault_id: str | None
    vault_file_path: str | None
    entry_content: str | None


def _parse_metadata(raw: object) -> dict[str, Any]:
    """The entry's metadata map: a JSON string on the node (``neo4j_mapper`` dict
    fields), tolerated as an already-parsed map or absent."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _to_edge_row(record: Mapping[str, Any]) -> EdgeRow:  # boundary: raw neo4j-driver record
    """Project a driver record onto EdgeRow (KeyError on alias drift).

    Nothing statically links a Cypher alias to a TypedDict key, so a renamed
    RETURN would type-check while the census read a missing key as "nothing to
    do" — a confident no-op on a pass whose job is to notice orphaned hashes.
    Indexing each alias turns that into a loud failure before anything is
    written.
    """
    metadata = _parse_metadata(record["entry_metadata"])
    path = metadata.get("vault_file_path")
    content = record["entry_content"]
    vault_id = record["vault_id"]
    return {
        "entry_uid": str(record["entry_uid"]),
        "entity_uid": str(record["entity_uid"]),
        "stored_hash": str(record["stored_hash"]),
        "vault_id": None if vault_id is None else str(vault_id),
        "vault_file_path": None if path is None else str(path),
        "entry_content": None if content is None else str(content),
    }


class Outcome(Enum):
    """What the census found for one edge."""

    CURRENT = "current"  # stored == current digest of the line — nothing to do
    REWRITE = "rewrite"  # stored == RETIRED digest, != current — the ✅ orphan; written
    EDITED = "edited"  # stored matches neither digest — line edited since extraction; left alone
    LINE_NOT_FOUND = "line-not-found"  # no line carries the 🆔 or either digest
    FILE_MISSING = "file-missing"  # vault_file_path set, file unreadable
    NO_SOURCE = "no-source"  # no vault path and no entry content to search


@dataclass(frozen=True)
class RehashPlan:
    """What the write would do for one edge — pure, so it is testable DB-free.

    ``new_hash`` carries the digest that would be written, or ``None`` when
    nothing would be. ``source`` names where the line was looked for (the
    vault file's path, or :data:`ENTRY_CONTENT_SOURCE`).
    """

    entry_uid: str
    entity_uid: str
    vault_id: str | None
    source: str | None
    outcome: Outcome
    old_hash: str
    new_hash: str | None

    @property
    def writes(self) -> bool:
        return self.outcome is Outcome.REWRITE


# ``path → file text``, or ``None`` when the file cannot be read. Injected so
# the classifier runs over an in-memory vault in the unit tests.
ReadText = Callable[[str], str | None]


def _read_file(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def locate_line(text: str, vault_id: str | None, stored_hash: str) -> str | None:
    """The task line an edge describes, or ``None``.

    By 🆔 when the edge carries one (ADR-070's durable join key); otherwise —
    or when the file no longer holds that 🆔 — by digest, under either
    normalisation. Digest equality is an identity proof, so a by-digest hit
    can only classify as current or rewrite, never as edited.
    """
    lines = text.splitlines()
    if vault_id:
        for line in lines:
            match = VAULT_ID_RE.search(line)
            if match and match.group(1) == vault_id:
                return line
    for line in lines:
        if stored_hash in (
            normalize_vault_line_hash(line),
            legacy_normalize_vault_line_hash(line),
        ):
            return line
    return None


def classify(row: EdgeRow, read_text: ReadText = _read_file) -> RehashPlan:
    """Decide one edge's outcome without writing anything."""

    def plan(outcome: Outcome, source: str | None, new_hash: str | None = None) -> RehashPlan:
        return RehashPlan(
            entry_uid=row["entry_uid"],
            entity_uid=row["entity_uid"],
            vault_id=row["vault_id"],
            source=source,
            outcome=outcome,
            old_hash=row["stored_hash"],
            new_hash=new_hash,
        )

    path = row["vault_file_path"]
    if path is not None:
        text = read_text(path)
        if text is None:
            return plan(Outcome.FILE_MISSING, path)
        source = path
    elif row["entry_content"]:
        text = row["entry_content"]
        source = ENTRY_CONTENT_SOURCE
    else:
        return plan(Outcome.NO_SOURCE, None)

    line = locate_line(text, row["vault_id"], row["stored_hash"])
    if line is None:
        return plan(Outcome.LINE_NOT_FOUND, source)

    current = normalize_vault_line_hash(line)
    if current == row["stored_hash"]:
        return plan(Outcome.CURRENT, source)
    if legacy_normalize_vault_line_hash(line) == row["stored_hash"]:
        return plan(Outcome.REWRITE, source, new_hash=current)
    return plan(Outcome.EDITED, source)


async def census(driver: AsyncDriver) -> list[RehashPlan]:
    """Read-only survey: one plan per provenance edge that carries a hash."""
    records, _, _ = await driver.execute_query(ROWS_QUERY)
    return [classify(_to_edge_row(record)) for record in records]


def _print_census(plans: list[RehashPlan], *, confirm: bool) -> None:
    header = (
        "EXTRACTED_FROM source_line_hash rehash"
        if confirm
        else "EXTRACTED_FROM source_line_hash rehash — CENSUS (nothing written)"
    )
    print(f"\n=== {header} ===\n")
    by_outcome = {outcome: sum(1 for p in plans if p.outcome is outcome) for outcome in Outcome}
    print(f"  Edges with a hash      {len(plans):>6}")
    print(f"  Current                {by_outcome[Outcome.CURRENT]:>6}   (digest already matches)")
    print(
        f"  To rewrite             {by_outcome[Outcome.REWRITE]:>6}   "
        "(stored with the ✅ token inside the digest)"
    )
    print(
        f"  Edited since extracted {by_outcome[Outcome.EDITED]:>6}   "
        "(matches neither digest — left alone, a real line edit)"
    )
    print(
        f"  Line not found         {by_outcome[Outcome.LINE_NOT_FOUND]:>6}   "
        "(no line carries the 🆔 or either digest)"
    )
    print(
        f"  File missing           {by_outcome[Outcome.FILE_MISSING]:>6}   (vault_file_path unreadable)"
    )
    print(
        f"  No source              {by_outcome[Outcome.NO_SOURCE]:>6}   (no vault path, no content)"
    )

    reported = [p for p in plans if p.outcome is not Outcome.CURRENT]
    if not reported:
        print()
        return

    print(f"\n  {'outcome':<16} {'entity':<34} {'entry':<40} {'🆔':<10} source")
    for plan in reported:
        print(
            f"  {plan.outcome.value:<16} {plan.entity_uid:<34} {plan.entry_uid:<40} "
            f"{plan.vault_id or '-':<10} {plan.source or '-'}"
        )
    print()


async def run_rehash(driver: AsyncDriver, *, confirm: bool) -> int:
    """Census every provenance hash and, with --confirm, rewrite the ✅ orphans."""
    plans = await census(driver)
    _print_census(plans, confirm=confirm)

    rewrites = [p for p in plans if p.writes]
    if not rewrites:
        print("Nothing to rehash — no stored hash still carries the retired normalisation.")
        return 0

    if not confirm:
        print("Census only. Re-run with --confirm to write.")
        return 0

    records, _, _ = await driver.execute_query(
        REWRITE_QUERY,
        rewrites=[
            {
                "entry_uid": p.entry_uid,
                "entity_uid": p.entity_uid,
                "old_hash": p.old_hash,
                "new_hash": p.new_hash,
            }
            for p in rewrites
        ],
    )
    written = int(records[0]["n"]) if records else 0
    skipped = len(rewrites) - written
    print(f"✓ rewrote {written} source_line_hash value(s)")
    if skipped:
        print(f"  {skipped} planned row(s) changed under the census and were left to the re-check")

    # Prove the pass converged rather than asserting it.
    remaining = sum(1 for p in await census(driver) if p.writes)
    if remaining:
        print(
            f"\nFAILED: {remaining} rewritable hash(es) remain after the write. "
            "Investigate before re-running.",
            file=sys.stderr,
        )
        return 1
    print("Verified: no stored hash still carries the retired normalisation.")
    return 0


async def run_against_configured_graph(*, confirm: bool) -> int:
    """Connect to the configured Neo4j and run one pass."""
    from adapters.persistence.neo4j_adapter import Neo4jAdapter

    print("Connecting to Neo4j...", file=sys.stderr)
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        return await run_rehash(adapter.get_driver(), confirm=confirm)
    finally:
        await adapter.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help=(
            "actually write. Without it the run is a read-only census. Only hashes "
            "whose stored value equals the retired normalisation's digest of the "
            "line are rewritten; everything else is reported and left alone."
        ),
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run_against_configured_graph(confirm=args.confirm)))


if __name__ == "__main__":
    main()
