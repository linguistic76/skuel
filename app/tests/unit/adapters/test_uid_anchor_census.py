"""No statement below the persistence boundary binds a uid on a label-less node.

``MATCH (n {uid: $uid})`` names no label, so the planner has no uid index to seek:
it scans every node in the graph, once per uid it is handed. A uid is bound through
``build_uid_anchor`` (``adapters/persistence/neo4j/endpoint_queries.py``) — one index
seek per label a uid can name (``:Entity``, ``:User``, ``:Group``, plus the calling
backend's own) — or under the one label the statement already knows.

Three shapes start a match from a label-less uid, and this census refuses each in
every module under ``adapters/persistence`` (the one place Cypher may be authored,
SKUEL021):

- ``MATCH (n {uid: …})`` — the brace doubled (``{{uid``) in an f-string template;
- ``MATCH (n{kind} {uid: …})`` — a label interpolated from a value that may be empty;
- ``MATCH (n) WHERE n.uid = …`` / ``… IN …``.

A uid on the far end of a pattern (``MATCH (a)-[r]->(b {uid: $to_uid})``) is not
refused: the match reaches ``b`` by expanding from ``a``, never by a scan.
``uid_census_backend`` reads every uid in the graph by design and binds none, so its
``MATCH (n) WHERE n.uid IS NOT NULL`` matches none of the shapes.
"""

from __future__ import annotations

import re
from pathlib import Path

PERSISTENCE_ROOT = Path(__file__).resolve().parents[3] / "adapters" / "persistence"

_LABEL_LESS_UID_ANCHOR = re.compile(
    r"MATCH\s+\(\w+(?:\{\w+\})?\s+\{\{?uid:"
    r"|MATCH\s+\((\w+)\)\s+WHERE\s+\1\.uid\s*(?:=|IN\b)"
)


def _offenders(text: str) -> list[int]:
    """The 1-indexed lines a label-less uid anchor starts on."""
    return [text.count("\n", 0, m.start()) + 1 for m in _LABEL_LESS_UID_ANCHOR.finditer(text)]


def _cypher_bearing_sources() -> list[Path]:
    files = sorted(
        p
        for suffix in ("*.py", "*.cypher")
        for p in PERSISTENCE_ROOT.rglob(suffix)
        if "__pycache__" not in p.parts
    )
    assert files, f"no sources found under {PERSISTENCE_ROOT}"
    return files


def test_no_statement_binds_a_uid_on_a_label_less_node() -> None:
    offenders = [
        f"{path.relative_to(PERSISTENCE_ROOT.parent.parent)}:{line}"
        for path in _cypher_bearing_sources()
        for line in _offenders(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "A uid bound on a label-less node scans every node in the graph. Bind it "
        "through build_uid_anchor (endpoint_queries.py) or under its label:\n  "
        + "\n  ".join(offenders)
    )


def test_the_census_refuses_each_label_less_shape() -> None:
    """Each shape the census names is found; a walk that finds nothing proves nothing."""
    refused = [
        "MATCH (a {uid: $from_uid})",
        'f"""MATCH (a {{uid: $from_uid}})"""',
        'f"""MATCH (a{from_kind} {{uid: $from_uid}})-[r]->(b)"""',
        "OPTIONAL MATCH (a {uid: rel.from_uid})-[r]->(b)",
        "MATCH (e)\n    WHERE e.uid IN $entity_uids",
        "MATCH (n) WHERE n.uid = $uid",
    ]
    for sample in refused:
        assert _offenders(sample) == [sample.count("\n", 0, sample.index("MATCH")) + 1], sample


def test_the_census_passes_a_labelled_or_expanded_uid() -> None:
    passed = [
        "MATCH (a:Entity {uid: $from_uid})",
        'f"""MATCH (a:{self.label} {{uid: $uid}})"""',
        "MATCH (a)-[r:T]->(b {uid: $to_uid})",
        "MATCH (n) WHERE n.uid IS NOT NULL",
        "MATCH (n:Task) WHERE n.uid = $uid",
    ]
    for sample in passed:
        assert _offenders(sample) == [], sample
