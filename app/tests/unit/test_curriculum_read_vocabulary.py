"""
Guard: LearningPath→Ku reads go through PathSteps, and mastery reads use the
property mastery writers actually set.
===========================================================================

SKUEL030 findings §8 (tranche 4). Four sites read curriculum composition and
none of them named a live edge:

- ``_LpProgressMixin`` matched ``(lp)-[:INCLUDES_KU]->(ku)``.
- ``KuBackend.get_learning_path_uids`` matched
  ``(lp:LearningPath)-[:CONTAINS_KNOWLEDGE|INCLUDES_KNOWLEDGE]->(ku)``.
- ``LifePathBackend`` matched ``(ps)-[:CONTAINS]->(ku)`` in four queries.
- ``CrossDomainBackend`` matched ``(lp)-[:CONTAINS]->(step:PathStep)``.

``INCLUDES_KU``/``INCLUDES_KNOWLEDGE``/``CONTAINS`` are not ``RelationshipName``
members. ``CONTAINS_KNOWLEDGE`` *is*, but it is a PathStep→Ku edge — naming it
at a LearningPath endpoint is a different silent zero, not a fix. The live graph
holds no LearningPath→Ku relationship of any type: a path reaches a Ku through
``HAS_STEP``→PathStep→``USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU``, or directly via its
ingestible ``REQUIRES_KNOWLEDGE`` prerequisites.

The second half of this module guards what repointing those reads exposed. A
dead read hides the bugs inside it; making it live turns them on:

- ``mastery_level`` is written by exactly one MASTERED writer
  (``_AdaptiveMixin``) and it is a STRING (``'introduced'``/``'proficient'``).
  ``LifePathBackend.calculate_knowledge_alignment`` multiplied it by 0.6 — Neo4j
  raises a type error on that, so the repoint would have turned a silent zero
  into a hard query failure.
- ``substance_score`` is written by no MASTERED writer at all, so
  ``get_knowledge_substance_stats`` classified every Ku as theoretical.
"""

from __future__ import annotations

import inspect
import re

from adapters.persistence.neo4j import (
    _lp_progress_mixin,
    _traversal_mixin,
    lifepath_backend,
    user_context_queries,
)
from adapters.persistence.neo4j.backends import curriculum_backends
from adapters.persistence.neo4j.query.cypher import CURRICULUM_COMPOSITION_EDGES
from core.models.relationship_names import RelationshipName

# Names these reads used to carry that no writer creates.
DEAD_CURRICULUM_NAMES = ["INCLUDES_KU", "INCLUDES_KNOWLEDGE", "FUNDS_HABIT", "FUNDS_TASK"]


def _source(obj: object) -> str:
    return inspect.getsource(obj)  # type: ignore[arg-type]


def _cypher_only(source: str) -> str:
    """Keep only the executable Cypher in a module or method.

    Docstrings and comments here deliberately name the retired vocabulary to
    explain why it went; that prose must not read as usage. Cypher lives in
    triple-quoted blocks containing a clause keyword, so keep only those, minus
    any ``//`` comment lines inside them.
    """
    blocks = re.findall(r'"""([\s\S]*?)"""', source)
    cypher = [b for b in blocks if re.search(r"\b(MATCH|RETURN|MERGE)\b", b)]
    return "\n".join(
        line for block in cypher for line in block.splitlines() if not line.strip().startswith("//")
    )


def test_dead_curriculum_names_are_not_registered() -> None:
    """The names these reads used are genuinely absent from the vocabulary."""
    members = {r.value for r in RelationshipName}
    assert "INCLUDES_KU" not in members
    assert "INCLUDES_KNOWLEDGE" not in members
    assert "CONTAINS" not in members
    assert "FUNDS_HABIT" not in members


def test_lp_progress_reads_kus_through_path_steps() -> None:
    """Both LP progress reads traverse HAS_STEP rather than a direct LP→Ku edge."""
    source = _cypher_only(_source(_lp_progress_mixin._LpProgressMixin))

    for name in DEAD_CURRICULUM_NAMES:
        assert name not in source
    assert source.count("[:HAS_STEP]->(:Entity)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->") == 2


def test_ku_mastery_progress_survives_a_user_with_no_masteries() -> None:
    """The mastery test is a predicate, not a MATCH that can collapse the query.

    A mandatory ``MATCH (user)-[:MASTERED]->(ku)`` returns zero rows for a user
    who has mastered nothing, which the service reads back as "this path has no
    Kus" — the inverse of the truth, for the learner it matters most to.
    """
    source = _cypher_only(_source(_lp_progress_mixin._LpProgressMixin.get_ku_mastery_progress))

    assert "EXISTS {" in source
    assert "MATCH (user:User" not in source
    # An empty path must still yield one row of zeros rather than no rows.
    assert "CASE WHEN size(candidate_kus) = 0 THEN [null]" in source


def test_curriculum_lp_lookup_uses_live_endpoints() -> None:
    """get_learning_path_uids never names a LearningPath→Ku edge.

    Asserted on the SHAPE rather than one literal pattern string: the bridging
    step was anonymous (``->(:Entity)-``) until #1008 had to NAME it so the
    publication gate could apply to it, and a string-equality fixture would
    read that correct change as a regression. What must hold is that the path
    reaches the Ku only THROUGH a step, never by a direct LP→Ku edge.
    """
    source = _cypher_only(_source(curriculum_backends.KuBackend.get_learning_path_uids))

    assert "INCLUDES_KNOWLEDGE" not in source
    # The LP→step hop, then the step→Ku composition union — via a step of any
    # name, anonymous or bound.
    assert re.search(r"\(lp\)-\[:HAS_STEP\]->\(\w*:Entity\)", source)
    assert "-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku)" in source
    # CONTAINS_KNOWLEDGE is legitimate — but only at the PathStep endpoint.
    assert "(lp:LearningPath)-[:CONTAINS_KNOWLEDGE" not in source


def test_lifepath_reads_kus_through_path_steps() -> None:
    """All four LifePath alignment queries traverse the live composition edge."""
    source = _cypher_only(_source(lifepath_backend))

    assert "-[:CONTAINS]->" not in source
    assert source.count("-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku:Entity") == 4


def test_lifepath_mastery_reads_use_mastery_score_not_mastery_level() -> None:
    """`mastery_level` is a string; arithmetic on it raises a Neo4j type error."""
    source = _cypher_only(_source(lifepath_backend))

    assert "mastery_level" not in source
    # Both the alignment score and the substance proxy read the numeric property,
    # falling back to 1.0 for the one writer that records mastery without a score.
    assert source.count("coalesce(m.mastery_score, 1.0)") == 2
    assert "substance_score" not in source


def test_momentum_does_not_collapse_when_recent_activity_is_zero() -> None:
    """A user whose aligned activity stopped must score as declining, not "no data"."""
    source = _cypher_only(_source(lifepath_backend.LifePathBackend.calculate_momentum))

    assert "APPLIES_KNOWLEDGE" in source
    # Both week-window legs are OPTIONAL; a mandatory MATCH would return no rows
    # and the service would fall back to the neutral 0.5 default.
    assert source.count("OPTIONAL MATCH (u:User {uid: $user_uid})-[:OWNS]->(task") == 2


def test_batch_cross_domain_context_drops_the_dead_funds_arms() -> None:
    """FUNDS_* is ADR-052 residue with no writer; `habits` went with it."""
    source = _cypher_only(_source(_traversal_mixin._TraversalMixin.get_batch_cross_domain_context))

    assert "FUNDS_HABIT" not in source
    assert "FUNDS_TASK" not in source
    # The key could never be populated once its only edge was gone, so it must
    # not survive as a permanently empty list.
    assert "as habits" not in source
    assert "collect(DISTINCT habit)" not in source


def test_the_mega_query_composition_token_is_actually_substituted() -> None:
    """An unsubstituted placeholder is a silent zero, not a syntax error.

    ``MEGA_QUERY`` is a plain string (Cypher map literals everywhere, so an
    f-string would mean doubling ~1300 lines of braces), and shares the one
    canonical composition alternation by ``.replace()`` of a token. That buys
    the sharing at the cost of a new failure mode: a token that never gets
    substituted — a typo, a rollup added to a different string constant, a
    dropped ``.replace()`` — leaves ``[:__COMPOSITION_EDGES__]`` in the query.
    Neo4j does not error on an unknown relationship type; it matches zero rows.
    Every learner would then read as having applied nothing, which is precisely
    the failure this whole area keeps producing.

    So this asserts on the BUILT query, never the source text.
    """
    assert user_context_queries._COMPOSITION_EDGES_TOKEN not in user_context_queries.MEGA_QUERY, (
        "a composition token survived into the built query — it will match zero rows"
    )
    assert (
        user_context_queries.MEGA_QUERY.count(f"[:{CURRICULUM_COMPOSITION_EDGES}]->(k:Ku)") == 6
    ), "the six activity→Ku rollups must all traverse the shared composition triple"


def test_the_shared_composition_alternation_is_built_from_registered_edges() -> None:
    """Every arm is a RelationshipName member — structurally, not by lint.

    SKUEL030 can no longer see these edge names in the query source now that
    they arrive through a constant. That is not a loss of coverage: built from
    the enum, the alternation *cannot* name a non-member, which is stronger than
    checking the spelling. This pins that it stays built that way.
    """
    arms = CURRICULUM_COMPOSITION_EDGES.split("|")

    assert arms == [
        RelationshipName.USES_KU.value,
        RelationshipName.CONTAINS_KNOWLEDGE.value,
        RelationshipName.TRAINS_KU.value,
    ]
    assert len(arms) == len(set(arms)), "a duplicated arm means the triple was hand-edited"
    assert all(RelationshipName.is_valid(arm) for arm in arms)
