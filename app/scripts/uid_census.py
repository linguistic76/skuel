#!/usr/bin/env python3
"""Read every node uid in the graph against the uid grammar — read-only.

Prints one row per label: how many uids fit the grammar, how many have a
character outside ``[a-z0-9._-]``, and how many are in the charset but in
neither shape (``core/utils/uid_grammar.py``). Below the table, every uid that
does not fit is grouped by the ``UID_EXEMPTIONS`` entry naming its shape — with
what retires that entry — or listed as UNREGISTERED with a sample. Nodes with no
uid are counted by label. Nothing is written.

A node is counted under its labels other than ``Entity`` (``Task``,
``Content``, ``ContentChunk``).

Usage:
    uv run scripts/uid_census.py
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from core.utils.process_clock import pin_process_clock_to_utc

pin_process_clock_to_utc()  # the UTC arc's bridge: before any clock read (ADR-089)

from core.utils.uid_grammar import (
    UID_EXEMPTIONS,
    UidVerdict,
    classify,
    exemptions_for,
)

_UNREGISTERED = "UNREGISTERED"


@dataclass
class LabelTally:
    """One label's uids, by verdict."""

    fits: int = 0
    outside: int = 0
    shape: int = 0

    @property
    def total(self) -> int:
        return self.fits + self.outside + self.shape


@dataclass
class Census:
    """Per-label tallies, plus each non-fitting uid's exemption (or none)."""

    by_label: dict[str, LabelTally] = field(default_factory=dict)
    by_exemption: Counter[tuple[str, str]] = field(default_factory=Counter)
    samples: dict[tuple[str, str], str] = field(default_factory=dict)


def label_of(labels: Iterable[str]) -> str:
    """The labels a node is counted under: every label but ``Entity``, joined."""
    named = sorted(label for label in labels if label != "Entity")
    return ":".join(named) or "Entity"


def take_census(rows: Iterable[tuple[Iterable[str], str]]) -> Census:
    """Tally ``(labels, uid)`` rows against the grammar."""
    census = Census()
    for labels, uid in rows:
        label = label_of(labels)
        tally = census.by_label.setdefault(label, LabelTally())
        verdict = classify(uid)
        if verdict is UidVerdict.FITS:
            tally.fits += 1
            continue
        if verdict is UidVerdict.OUTSIDE:
            tally.outside += 1
        else:
            tally.shape += 1
        # A shape two writers mint is counted under both names, joined.
        names = "+".join(exemption.name for exemption in exemptions_for(uid))
        key = (label, names or _UNREGISTERED)
        census.by_exemption[key] += 1
        census.samples.setdefault(key, uid)
    return census


def render(census: Census, uidless: dict[str, int]) -> str:
    """The census as plain text (a markdown table, then the details)."""
    lines = ["| label | fits | outside | shape | total |", "|---|---:|---:|---:|---:|"]
    totals = LabelTally()
    for label in sorted(census.by_label):
        tally = census.by_label[label]
        lines.append(
            f"| {label} | {tally.fits} | {tally.outside} | {tally.shape} | {tally.total} |"
        )
        totals.fits += tally.fits
        totals.outside += tally.outside
        totals.shape += tally.shape
    lines.append(
        f"| **all** | {totals.fits} | {totals.outside} | {totals.shape} | {totals.total} |"
    )

    retired_by = {exemption.name: exemption.retired_by for exemption in UID_EXEMPTIONS}
    lines += ["", "Not fitting, by exemption:"]
    if not census.by_exemption:
        lines.append("  (none)")
    for (label, name), count in sorted(census.by_exemption.items()):
        where = (
            "; ".join(retired_by[part] for part in name.split("+"))
            if name != _UNREGISTERED
            else "no exemption names this shape"
        )
        sample = census.samples[(label, name)]
        lines.append(f"  {label:<24} {name:<18} {count:>6}  ({where}) e.g. {sample}")

    lines += ["", "Nodes without a uid:"]
    if not uidless:
        lines.append("  (none)")
    for label, count in sorted(uidless.items()):
        lines.append(f"  {label:<24} {count:>6}")
    return "\n".join(lines)


async def run() -> int:
    """Connect, read every uid, print the census, return the exit code."""
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from adapters.persistence.neo4j.uid_census_backend import UidCensusBackend
    from adapters.persistence.neo4j_adapter import Neo4jAdapter

    print("Connecting to Neo4j...", file=sys.stderr)
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        backend = UidCensusBackend(Neo4jQueryExecutor(adapter.get_driver()))
        rows = await backend.read_uids()
        if rows.is_error:
            print(f"ERROR reading uids: {rows.expect_error()}", file=sys.stderr)
            return 1
        uidless = await backend.count_uidless()
        if uidless.is_error:
            print(f"ERROR counting uid-less nodes: {uidless.expect_error()}", file=sys.stderr)
            return 1
    finally:
        await adapter.close()

    by_label: Counter[str] = Counter()
    for labels, count in uidless.value.items():
        by_label[label_of(labels)] += count
    print("\n=== UID census (read-only) ===\n")
    print(render(take_census(rows.value), dict(by_label)))
    return 0


def main() -> None:
    sys.exit(asyncio.run(run()))


if __name__ == "__main__":
    main()
