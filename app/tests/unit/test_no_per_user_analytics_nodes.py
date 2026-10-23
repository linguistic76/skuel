"""Analytics aggregate, they don't create — no Cypher writes a node keyed by its user alone.

A per-user figure the graph can answer (how many tasks are completed, when the first
habit completion was, how many paths a learner finished) is read from the source
facts when asked for. Stored instead, on a node an event handler keeps current, it
drifts from the graph through every door that announces nothing, every deletion and
every reopen — and nothing reconciles it.

The shape such a store takes is a node identified by its user and nothing else:
``MERGE (n:Label {user_uid: $user_uid})``. This test fails on any ``MERGE`` or
``CREATE`` in production code whose node pattern is keyed that way, whatever the
label — an f-string label (``MERGE (n:{label} {{user_uid: …}})``) included, since the
label never reaches the check.

The one store keyed this way on purpose is named below with its reason: a snapshot of
an assessment as it stood when an event fired is history the graph cannot re-derive
later, not an aggregate of facts it still holds.

Blind spots, stated: a node keyed by ``user_uid`` plus another property (a per-user,
per-period counter) passes, as does a pattern written across two lines or two strings.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_TREES = ("adapters", "core", "scripts", "services_bootstrap")

#: Labels keyed by their user alone on purpose, each with the reason it is a
#: record rather than a figure the graph can answer at read.
SNAPSHOT_STORES: dict[str, str] = {
    "ZPDHistory": (
        "the latest ZPD assessment as it stood when an event fired "
        "(core/services/zpd/zpd_event_handler.py) — a past assessment is not "
        "re-derivable from the graph once the graph has moved on"
    ),
}

_WRITE = re.compile(r"\b(?:MERGE|CREATE)\b([^\n]*)")
_NODE = re.compile(r"\(([^()]*)\)")
_MAP = re.compile(r"\{([^{}]*)\}")
_KEY = re.compile(r"^\s*`?([A-Za-z_]\w*)`?\s*:")
_LABELS = re.compile(r":\s*`?([A-Za-z_{][\w{}]*)`?")


def _labels_if_keyed_by_user_alone(node_body: str) -> set[str] | None:
    """The labels of a node pattern whose property map has exactly one key, ``user_uid``.

    ``None`` when the pattern is keyed any other way.
    """
    # An f-string doubles its literal braces; a placeholder such as ``{label}``
    # carries no colon, so it is never read as a property map.
    body = node_body.replace("{{", "{").replace("}}", "}")
    for property_map in _MAP.finditer(body):
        keys = [
            match.group(1)
            for part in property_map.group(1).split(",")
            if (match := _KEY.match(part))
        ]
        if keys == ["user_uid"]:
            return set(_LABELS.findall(body[: property_map.start()]))
    return None


def _per_user_writes(text: str) -> list[tuple[int, str, set[str]]]:
    """Each ``MERGE`` / ``CREATE`` node keyed by its user alone: line, text, labels."""
    found: list[tuple[int, str, set[str]]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        for write in _WRITE.finditer(line):
            for node in _NODE.finditer(write.group(1)):
                labels = _labels_if_keyed_by_user_alone(node.group(1))
                if labels is not None:
                    found.append((line_number, line.strip(), labels))
    return found


def test_no_production_cypher_writes_a_node_keyed_by_its_user_alone():
    offenders = []
    for tree in PRODUCTION_TREES:
        for path in sorted((ROOT / tree).rglob("*.py")):
            for line_number, line, labels in _per_user_writes(path.read_text(encoding="utf-8")):
                if labels and labels <= SNAPSHOT_STORES.keys():
                    continue
                offenders.append(f"{path.relative_to(ROOT)}:{line_number}: {line}")

    assert not offenders, (
        "Cypher writes a node keyed by its user alone — a stored per-user figure. "
        "Derive it from the source facts at read instead (CLAUDE.md § Analytics "
        "Architecture), or, if it records history the graph cannot re-derive, name its "
        "label in SNAPSHOT_STORES with the reason:\n" + "\n".join(offenders)
    )


def test_every_snapshot_store_is_still_written():
    """A registration whose label no production Cypher writes any more is stale."""
    written: set[str] = set()
    for tree in PRODUCTION_TREES:
        for path in sorted((ROOT / tree).rglob("*.py")):
            for _, _, labels in _per_user_writes(path.read_text(encoding="utf-8")):
                written |= labels

    assert set(SNAPSHOT_STORES) <= written, sorted(set(SNAPSHOT_STORES) - written)


def test_the_scanner_catches_each_spelling_of_the_shape():
    """Fires on the shape in a plain string and through an f-string label; not on an entity."""
    assert _per_user_writes("MERGE (v:LearningVelocity {user_uid: $user_uid})")
    assert _per_user_writes('f"MERGE (a:{label} {{user_uid: $user_uid}})"')
    assert _per_user_writes("MERGE (u)-[:HAS]->(h:Tally {user_uid: $user_uid})")
    assert _per_user_writes('f"MERGE (a:{_ANALYTICS} {{user_uid: u.uid}})"')

    assert not _per_user_writes("MERGE (u:User {uid: $user_uid})")
    assert not _per_user_writes("MERGE (t:Task {uid: $uid, user_uid: $user_uid})")
    assert not _per_user_writes("MATCH (a:Tally {user_uid: $user_uid})")
    [(_, _, labels)] = _per_user_writes("MERGE (h:ZPDHistory {user_uid: $user_uid})")
    assert labels == {"ZPDHistory"}
    [(_, _, labels)] = _per_user_writes('f"MERGE (a:{label} {{user_uid: $user_uid}})"')
    assert labels == {"{label}"}, "an f-string label is never a registered store"
