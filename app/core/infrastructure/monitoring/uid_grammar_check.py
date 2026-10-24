"""In-app uid grammar check — the uid census, read by the graph-health poller.

The uid census (``./dev uid-census``, ``scripts/uid_census.py``) is a script an
operator runs; this is the same verdict read where it binds, by the running app.
The 5-min graph-health poller (``scripts/dev/bootstrap.py``) reads the graph's
breaches of the grammar through ``UidCensusBackend.read_breaches`` — the server
filters by ``UID_PATTERN`` (``core/utils/uid_grammar.py``), so only breaches
cross the wire — sets the two gauges (``skuel_uids_outside_grammar_count``,
``skuel_uids_shared_count``) that the dev stack's ``UidOutsideGrammar`` /
``UidHeldByTwoNodes`` alerts read, and calls ``check_uid_grammar``. Production
runs no Prometheus, so this check's ERROR log is its alert: every cycle while a
breach holds (the AuraDB cap check's posture, ``aura_cap_check.py``).

A breach is a uid outside the grammar — a shape an exemption names included: an
exemption explains a writer, it never admits a uid — or a uid more than one node
holds. Either means a writer minted outside ``core/utils/uid_grammar.py``.
"""

from dataclasses import dataclass
from typing import Final

from core.utils.logging import get_logger

logger = get_logger("skuel.monitoring.uid_grammar")

#: How many of each breach the poller reads back and logs.
UID_BREACH_SAMPLE: Final = 5

_REMEDIATION = "run ./dev uid-census to name each uid and the writer that minted it"


@dataclass(frozen=True)
class UidBreaches:
    """The graph's breaches of the uid grammar, counted, with a few of each.

    Each sample entry reads ``{labels} {uid}`` — the node's labels other than
    ``Entity`` — for ``outside``; a bare uid for ``shared``.
    """

    outside: int
    shared: int
    outside_sample: tuple[str, ...] = ()
    shared_sample: tuple[str, ...] = ()


def check_uid_grammar(breaches: UidBreaches) -> None:
    """Log ERROR for each kind of breach the graph holds; silent when it holds none."""
    if breaches.outside:
        logger.error(
            f"uid grammar breached: {breaches.outside:,} uid(s) outside the grammar "
            f"(e.g. {', '.join(breaches.outside_sample)}) — {_REMEDIATION}"
        )
    if breaches.shared:
        logger.error(
            f"uid grammar breached: {breaches.shared:,} uid(s) held by more than one node "
            f"(e.g. {', '.join(breaches.shared_sample)}) — {_REMEDIATION}"
        )
