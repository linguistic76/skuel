"""A dropped tracker key that names no edge is skipped with a warning.

``retracted_edges`` decodes ``prior - current`` for the delete primitive. A key whose
type is not a ``RelationshipName`` member (a retired type) cannot be decoded: the edge
it once recorded is not retracted, and the warning is the only trace of that. The
decodable keys beside it are still returned.

The logger is structlog's, so the warning is read with ``structlog.testing.capture_logs``
(the stdlib ``caplog`` handler never sees it).
"""

from __future__ import annotations

from structlog.testing import capture_logs

from core.ingestion.ingestion_types import AuthoredEdge
from core.models.relationship_names import RelationshipName
from core.services.ingestion.authored_edges import retracted_edges

RETIRED = "GUIDES_GOAL|outgoing|goal.t.a"
LIVE = "USES_KU|outgoing|ku.t.b"
LIVE_EDGE = AuthoredEdge(RelationshipName.USES_KU, "outgoing", "ku.t.b")


def _warnings(logs: list[dict]) -> list[dict]:
    return [entry for entry in logs if entry["log_level"] == "warning"]


def test_the_retired_type_is_not_a_relationship_name() -> None:
    """The premise: the key below is undecodable because its type left the enum."""
    assert RelationshipName.from_string("GUIDES_GOAL") is None


def test_a_dropped_key_of_a_retired_type_logs_one_warning_naming_the_key() -> None:
    with capture_logs() as logs:
        retracted_edges([RETIRED, LIVE], [])

    warnings = _warnings(logs)
    assert len(warnings) == 1
    assert warnings[0]["extra"] == {"authored_edge_key": RETIRED}
    assert "not retracted" in warnings[0]["event"]


def test_the_decodable_keys_beside_it_are_still_returned() -> None:
    with capture_logs():
        edges = retracted_edges([RETIRED, LIVE], [])

    assert edges == [LIVE_EDGE]


def test_each_undecodable_dropped_key_is_warned_about() -> None:
    malformed = "USES_KU|sideways|ku.t.c"

    with capture_logs() as logs:
        edges = retracted_edges([RETIRED, malformed, LIVE], [])

    assert edges == [LIVE_EDGE]
    assert sorted(entry["extra"]["authored_edge_key"] for entry in _warnings(logs)) == sorted(
        [RETIRED, malformed]
    )


def test_a_retired_key_still_declared_is_not_dropped_and_not_warned_about() -> None:
    """Only ``prior - current`` is decoded: a key on both sides is no retraction."""
    with capture_logs() as logs:
        edges = retracted_edges([RETIRED, LIVE], [RETIRED])

    assert edges == [LIVE_EDGE]
    assert _warnings(logs) == []


def test_decodable_drops_log_no_warning() -> None:
    with capture_logs() as logs:
        edges = retracted_edges([LIVE], [])

    assert edges == [LIVE_EDGE]
    assert _warnings(logs) == []
