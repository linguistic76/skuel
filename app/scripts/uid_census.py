#!/usr/bin/env python3
"""Read every node uid in the graph against the uid grammar — read-only.

Prints one row per label: how many uids fit the grammar, how many have a
character outside ``[a-z0-9._-]``, and how many are in the charset but in
neither shape (``core/utils/uid_grammar.py``). Below the table, every uid that
does not fit is grouped by the ``UID_EXEMPTIONS`` entry naming its shape — with
what retires that entry — or listed as UNREGISTERED with a sample. Every uid more
than one node holds is listed with their labels. Nodes with no uid are counted by
label. Nothing is written.

Exits 1 when a uid is outside the grammar — an exemption explains the writer
that minted it, never admits it — or is held by more than one node: a uid names
one node, in every label at once, and no constraint can say so across labels.
The uid grammar's record is written only when this census passes
(``scripts/migrations/uid_grammar_2026_10.py``), so the census opens the graph
without requiring that record (``Neo4jConnection(requires=…)``).

A node is counted under its labels other than ``Entity`` (``Task``,
``Content``, ``ContentChunk``). ``read_census`` takes the census over an open
driver — the stamp script and each uid migration's read-back read it too.

Usage:
    uv run scripts/uid_census.py
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.utils.process_clock import pin_process_clock_to_utc

pin_process_clock_to_utc()  # the UTC arc's bridge: before any clock read (ADR-089)

from core.utils.result_simplified import Result
from core.utils.uid_grammar import (
    UID_EXEMPTIONS,
    UidVerdict,
    classify,
    exemptions_for,
)

if TYPE_CHECKING:
    from neo4j import AsyncDriver

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
    """Per-label tallies, each non-fitting uid's exemption (or none), and shared uids."""

    by_label: dict[str, LabelTally] = field(default_factory=dict)
    by_exemption: Counter[tuple[str, str]] = field(default_factory=Counter)
    samples: dict[tuple[str, str], str] = field(default_factory=dict)
    # uid -> the sorted labels of every node holding it, for uids more than one holds
    shared: dict[str, list[str]] = field(default_factory=dict)


def label_of(labels: Iterable[str]) -> str:
    """The labels a node is counted under: every label but ``Entity``, joined."""
    named = sorted(label for label in labels if label != "Entity")
    return ":".join(named) or "Entity"


def take_census(rows: Iterable[tuple[Iterable[str], str]]) -> Census:
    """Tally ``(labels, uid)`` rows against the grammar."""
    census = Census()
    holders: defaultdict[str, list[str]] = defaultdict(list)
    for labels, uid in rows:
        label = label_of(labels)
        holders[uid].append(label)
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
    census.shared = {uid: sorted(held) for uid, held in holders.items() if len(held) > 1}
    return census


def failures(census: Census) -> list[str]:
    """Why the census fails — one line per kind of breach; empty when it passes."""
    lines: list[str] = []
    outside = sum(census.by_exemption.values())
    if outside:
        exempt = sum(
            count for (_, name), count in census.by_exemption.items() if name != _UNREGISTERED
        )
        lines.append(
            f"{outside} uid(s) outside the grammar ({exempt} in a shape an exemption names)"
        )
    if census.shared:
        lines.append(f"{len(census.shared)} uid(s) held by more than one node")
    return lines


def exit_code(census: Census) -> int:
    """1 when a uid is outside the grammar or held by more than one node, else 0."""
    return 1 if failures(census) else 0


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

    lines += ["", "Uids held by more than one node:"]
    if not census.shared:
        lines.append("  (none)")
    for uid in sorted(census.shared):
        lines.append(f"  {uid}  ({', '.join(census.shared[uid])})")

    lines += ["", "Nodes without a uid:"]
    if not uidless:
        lines.append("  (none)")
    for label, count in sorted(uidless.items()):
        lines.append(f"  {label:<24} {count:>6}")
    return "\n".join(lines)


async def read_census(driver: AsyncDriver) -> Result[tuple[Census, dict[str, int]]]:
    """The census of every uid on the graph, and the uid-less nodes counted by label."""
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from adapters.persistence.neo4j.uid_census_backend import UidCensusBackend

    backend = UidCensusBackend(Neo4jQueryExecutor(driver))
    rows = await backend.read_uids()
    if rows.is_error:
        return Result.fail(rows)
    uidless = await backend.count_uidless()
    if uidless.is_error:
        return Result.fail(uidless)
    by_label: Counter[str] = Counter()
    for labels, count in uidless.value.items():
        by_label[label_of(labels)] += count
    return Result.ok((take_census(rows.value), dict(by_label)))


#: The command that writes the uid grammar's record once the census passes.
STAMP_COMMAND = "uv run scripts/migrations/uid_grammar_2026_10.py --confirm"


async def closing_census(driver: AsyncDriver) -> str:
    """The census verdict a uid migration ends its run with, and the next step — one line.

    A migration's read-back holds what that run wrote to the grammar; this reads
    the whole graph, which passes only once every uid migration has run.
    """
    read = await read_census(driver)
    if read.is_error:
        return f"uid census: unreadable ({read.expect_error()}) — run ./dev uid-census"
    reasons = failures(read.value[0])
    if not reasons:
        return f"uid census: passes — stamp the graph: {STAMP_COMMAND}"
    return (
        "uid census: " + "; ".join(reasons) + " — the stamp refuses until they move "
        "(./dev uid-census names each)"
    )


async def run() -> int:
    """Connect, read every uid, print the census, return the exit code."""
    from adapters.persistence.neo4j.graph_driver import UTC_INSTANTS
    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    print("Connecting to Neo4j...", file=sys.stderr)
    # The uid grammar's record is what this census gates — never required to read it.
    connection = Neo4jConnection(requires=(UTC_INSTANTS,))
    driver = await connection.connect()
    try:
        read = await read_census(driver)
    finally:
        await connection.close()
    if read.is_error:
        print(f"ERROR reading the census: {read.expect_error()}", file=sys.stderr)
        return 1
    census, uidless = read.value
    print("\n=== UID census (read-only) ===\n")
    print(render(census, uidless))
    reasons = failures(census)
    print("\nVerdict: " + ("; ".join(reasons) if reasons else "passes"))
    return exit_code(census)


def main() -> None:
    sys.exit(asyncio.run(run()))


if __name__ == "__main__":
    main()
