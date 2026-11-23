#!/usr/bin/env python3
"""Read every stored node as its class — read-only.

For every label a backend reads through ``from_neo4j_node``, reads each node's
fields by the mapper's own rule, and lists every field a read would refuse: a
stored value its type cannot read (enum, temporal, collection, mapping and nested
dataclass fields), or a field the class requires that the node does not hold —
the node's class, uid and field, the stored value and why it cannot be read.
Every read of such a node fails (``UnreadableStoredValueError``) until the node
is migrated and the writer that stored it is fixed. Then it lists every stored key
no read reads: neither a field nor registered node state of the node's class
(``core/models/node_state.py``) — the node's class, uid and key. Nothing is written.

Exits 1 when any field is unreadable or any key is undeclared. The graph-health
poller reads the same census every five minutes (``check_stored_values``,
``check_undeclared_keys``).

Usage:
    uv run scripts/stored_value_census.py
"""

from __future__ import annotations

import asyncio
import sys

from core.utils.process_clock import pin_process_clock_to_utc

pin_process_clock_to_utc()  # the UTC arc's bridge: before any clock read (ADR-089)


async def run() -> int:
    """Connect, read every stored value, print the census, return the exit code."""
    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from services_bootstrap._backends import create_all_backends

    print("Connecting to Neo4j...", file=sys.stderr)
    connection = Neo4jConnection()
    driver = await connection.connect()
    try:
        backend = create_all_backends(driver, Neo4jQueryExecutor(driver))[
            "stored_value_census_backend"
        ]
        read = await backend.read_unreadable()
        undeclared = await backend.read_undeclared()
    finally:
        await connection.close()
    if read.is_error:
        print(f"ERROR reading the census: {read.expect_error()}", file=sys.stderr)
        return 1
    if undeclared.is_error:
        print(f"ERROR reading the census: {undeclared.expect_error()}", file=sys.stderr)
        return 1
    print(f"\n=== Stored-value census (read-only): {len(backend.readers)} labels ===\n")
    for refusal in read.value:
        print(
            f"{refusal.entity_class} {refusal.uid}.{refusal.field} = "
            f"{refusal.value!r:.80} — {refusal.reason}"
        )
    print(
        f"\nVerdict: {len(read.value)} unreadable stored field(s)"
        if read.value
        else "\nVerdict: every stored node reads as its class"
    )
    print("\n=== Stored keys no read reads ===\n")
    for found in undeclared.value:
        print(f"{found.entity_class} {found.uid}.{found.key}")
    print(
        f"\nVerdict: {len(undeclared.value)} stored key(s) neither a field nor node state"
        if undeclared.value
        else "\nVerdict: every stored key is a field or registered node state"
    )
    return 1 if read.value or undeclared.value else 0


def main() -> None:
    sys.exit(asyncio.run(run()))


if __name__ == "__main__":
    main()
