"""ZPD zone-query shape guards — the ENABLES-proximal ruling, frozen in Cypher.

Mike's ruling (2026-07-10, PR 5 of the discovery-analytics arc):
ENABLES counts for PROXIMAL EXPANSION ONLY. "You engaged A, A ENABLES B →
B is proximal" joins the PREREQUISITE_FOR forward step. Readiness scoring
(Step 3) and blocking-gap detection (Step 5) stay strictly prerequisite-only —
an enabler must NEVER become a gate or a requirement.

These tests assert on the Cypher text itself (the AST of this layer): the
zone query is a single string constant, so shape assertions here are exact,
not heuristic. Live traversal behavior is covered by
tests/integration/test_zpd_enables_proximal.py.
"""

from __future__ import annotations

import re

from adapters.persistence.neo4j.zpd_backend import (
    _TARGETED_KU_ENGAGEMENT_QUERY,
    _ZONE_QUERY,
)


def _strip_comments(cypher: str) -> str:
    """Drop // comment lines so assertions only see executable Cypher."""
    return "\n".join(line for line in cypher.splitlines() if not line.strip().startswith("//"))


_ZONE = _strip_comments(_ZONE_QUERY)
_TARGETED = _strip_comments(_TARGETED_KU_ENGAGEMENT_QUERY)


class TestEnablesProximalOnly:
    def test_proximal_expansion_follows_prerequisite_and_both_enabler_vocabularies(self) -> None:
        """Step 2 forward step follows PREREQUISITE_FOR + BOTH enabler edge types.

        Two enabler vocabularies exist (Codex P2 #600): standalone Edge YAML
        authors ENABLES; the relationship registry maps connections.enables
        to ENABLES_KNOWLEDGE. The proximal expansion must read both.
        """
        assert re.search(
            r"\(engaged:Entity \{uid: engaged_uid\}\)-\[:PREREQUISITE_FOR\|ENABLES\|ENABLES_KNOWLEDGE\]->",
            _ZONE,
        ), "proximal expansion must follow PREREQUISITE_FOR, ENABLES and ENABLES_KNOWLEDGE"

    def test_enabler_edges_appear_only_in_the_proximal_union(self) -> None:
        """Enabler types may exist ONLY in the single proximal-expansion union."""
        assert _ZONE.count("PREREQUISITE_FOR|ENABLES|ENABLES_KNOWLEDGE") == 1
        # Both ENABLES substrings live inside that one union — no other site
        assert _ZONE.count("ENABLES") == 2

    def test_readiness_and_gap_traversals_are_incoming_prereq_only(self) -> None:
        """Steps 3 + 5 count incoming prerequisites; no other edge type may gate.

        Both readiness (`prereq`) and blocking gaps (`gap`) traverse
        `<-[:PREREQUISITE_FOR]-` — exactly two incoming matches, neither
        mentioning ENABLES.
        """
        incoming = re.findall(r"<-\[:([A-Z_|]+)\]-", _ZONE)
        assert incoming == ["PREREQUISITE_FOR", "PREREQUISITE_FOR"]

    def test_enabler_never_appears_in_gap_step(self) -> None:
        """The blocking-gap match binds `gap` via PREREQUISITE_FOR only."""
        gap_match = re.search(
            r"OPTIONAL MATCH \(p:Entity \{uid: p_uid\}\)(.+)\(gap:Entity\)", _ZONE
        )
        assert gap_match is not None
        assert "ENABLES" not in gap_match.group(1)
        assert "PREREQUISITE_FOR" in gap_match.group(1)

    def test_targeted_engagement_query_has_no_enables(self) -> None:
        """The targeted (Socratic) query reads engagement only — no zone expansion."""
        assert "ENABLES" not in _TARGETED


class TestCallSubqueryScopeSyntax:
    """Neo4j 2026.x deprecates importing-WITH `CALL { WITH ... }` subqueries.

    All CALL subqueries must use the variable-scope form `CALL (vars) { ... }`
    (or `CALL () { ... }` when uncorrelated) — no deprecation noise in logs.
    """

    def test_zone_query_uses_scope_syntax(self) -> None:
        assert not re.search(r"CALL\s*\{", _ZONE)
        assert "CALL (task_engaged_uids, habit_engaged_uids, entry_engaged_uids) {" in _ZONE
        assert "CALL () {" in _ZONE  # submission subquery is uncorrelated ($user_uid param)

    def test_targeted_query_uses_scope_syntax(self) -> None:
        assert not re.search(r"CALL\s*\{", _TARGETED)
        assert "CALL (u) {" in _TARGETED

    def test_no_importing_with_inside_call(self) -> None:
        """The old form's first line inside CALL was `WITH <vars>` — gone now."""
        for query in (_ZONE, _TARGETED):
            for match in re.finditer(r"CALL[^\n]*\{\n(\s*[^\n]+)", query):
                first_line = match.group(1).strip()
                assert not first_line.startswith("WITH "), (
                    f"importing WITH inside CALL subquery is deprecated: {first_line!r}"
                )
