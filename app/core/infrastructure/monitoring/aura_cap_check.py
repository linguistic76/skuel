"""In-app AuraDB cap evaluator — the production counterpart of the cap alerts.

Production runs no Prometheus (PR #803 posture: app + Caddy only), so the
``AuraNodeCapApproaching`` / ``AuraRelationshipCapApproaching`` alert rules in
``monitoring/prometheus/alerts.yml`` evaluate only in the dev stack and never
observe AuraDB. This check is what guards the caps where they bind: the 5-min
graph-health poller (``scripts/dev/bootstrap.py``) calls it with each freshly
polled count, and it logs WARNING above 80% of cap / ERROR above 95% — every
cycle while the condition holds, so any ``docker logs`` tail surfaces it
(visibility over elegance; ~288 lines/day worst case is acceptable noise).

Thresholds live in ``core/constants.py`` ``AuraDBCaps`` and are drift-pinned
to the alert-rule expressions by ``tests/unit/test_metric_reference_drift.py``.
Comparisons are strictly greater-than, mirroring the alert exprs
(``skuel_total_entities > 160000``).

See: .claude/skills/prometheus-grafana/ALERTING.md § Where Alerts Actually Evaluate
"""

from core.constants import AuraDBCaps
from core.utils.logging import get_logger

logger = get_logger("skuel.monitoring.aura_caps")

_REMEDIATION = (
    "run ./dev telemetry-retention, review growth with ./dev knowledge-health, "
    "consider the invite gate / paid tier"
)


def check_aura_cap_headroom(total_nodes: int, total_relationships: int) -> None:
    """Log WARNING/ERROR when graph counts approach the AuraDB Free caps.

    Silent while both counts hold at or under 80% of cap. Grep production logs
    with ``docker compose logs skuel-app | grep 'AuraDB cap'``.
    """
    dimensions = (
        (
            "nodes",
            total_nodes,
            AuraDBCaps.NODE_CAP,
            AuraDBCaps.WARNING_NODES,
            AuraDBCaps.ERROR_NODES,
        ),
        (
            "relationships",
            total_relationships,
            AuraDBCaps.RELATIONSHIP_CAP,
            AuraDBCaps.WARNING_RELATIONSHIPS,
            AuraDBCaps.ERROR_RELATIONSHIPS,
        ),
    )
    for label, count, cap, warn_above, error_above in dimensions:
        if count <= warn_above:
            continue
        message = (
            f"AuraDB cap approaching: {count:,} {label} = {count / cap:.0%} of the "
            f"{cap:,} AuraDB Free cap (writes fail AT the cap) — {_REMEDIATION}"
        )
        if count > error_above:
            logger.error(message)
        else:
            logger.warning(message)
