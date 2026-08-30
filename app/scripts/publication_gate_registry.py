"""The classified set of query surfaces that touch the curriculum publication gate.

**Why a registry rather than a fourth hand-written list.** ``publication_state``
has been applied per-surface three times over, and each pass was enumerated by
hand: #1006 gated nine surfaces and Codex found a new one on each of four
rounds; #1008 replaced the grep census with a structural one and found sixteen
more; Codex then found six further defects across three rounds *on #1008*. The
enumeration is the defect, not any individual missing gate.

Categorising those six is what this module is shaped around. Three were
**omissions** — a surface the census never saw, because the census keyed on
labels and the binding carried none (``discover_semantic_bridges``) or the
bridging step was an anonymous ``(:Entity)`` (``get_learning_path_uids``). Three
were **misclassifications** — a surface that WAS enumerated and gated, just
gated wrongly: the wrong alias (``get_paths_by_knowledge`` gated ``lp`` and not
the bridging ``ps``), the wrong half of a mixed surface
(``get_prioritized_steps`` gated the catalogue without yielding to the learner's
own progress), or the wrong channel (``find_ready_to_learn`` withheld the draft
node and then named its uid inside a collected list).

So this module carries two things, and neither is a correctness judgement made
by a pattern:

1. **The classification** — every surface that composes a gate helper appears
   below with a disposition and a reason. ``scripts/audit_publication_gate.py``
   asserts the set is COMPLETE against the tree by AST. That claim ("is this
   surface classified?") is exactly decidable; the claim a linter must never
   make is "is this surface correctly gated?", which is where a regex
   approximating a parser generates an infinite tail (#831, and the rule in
   #868: narrow the claim rather than approximate).

2. **The criterion** — ``tests/integration/test_publication_gate_output_invariant.py``
   runs each GATED surface against a seeded graph and asserts no draft
   IDENTITY reaches the caller at any depth. That is the invariant itself
   rather than a proxy for it, and it is the only form that can express the
   three misclassification shapes: it does not care which alias carries the
   predicate, where in the query it sits, or whether the leak travels as a node,
   a scalar or an element of a ``collect()``.

The distinction the criterion preserves, which a WHERE-clause check cannot:
``find_ready_to_learn`` COUNTS a prerequisite it may not NAME. Withholding it
from the count would raise readiness and recommend a blocked KU as more ready —
worse than the leak. Identity is what is withheld; arithmetic sees everything.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Disposition(StrEnum):
    """Why a surface does — or does not — withhold draft curriculum."""

    GATED = "gated"
    """A discovery surface. Composes the gate; the output invariant applies."""

    ANCHORED = "anchored"
    """A by-UID read. The caller NAMED the entity, so a draft must come back —
    the gate belongs to discovery, and an author opens their own draft."""

    CONTAINMENT = "containment"
    """Contents ride along with a container the caller already holds. A path's
    own steps are not a discovery of other curriculum."""

    WRITER = "writer"
    """A maintenance pass that must NOT inherit a reader's gate. Skipping drafts
    would leave freshly-published content with a stale cached value, because
    nothing recomputes on publish."""

    USER_STATE = "user_state"
    """Reflects the learner's own engagement. Gating it would erase their
    history rather than hide unfinished curriculum."""

    REPORTS_DRAFTS = "reports_drafts"
    """An authoring instrument. Drafts are the POINT — the knowledge-health
    gauge reports ``draft_curriculum_count`` rather than subtracting it."""


@dataclass(frozen=True)
class Surface:
    """One classified query surface.

    ``module`` + ``qualname`` are what the AST audit matches on, so they must
    spell the DEFINING module — the mixin a method is written in, not the
    backend class that happens to host it.
    """

    module: str
    qualname: str
    disposition: Disposition
    reason: str


# ---------------------------------------------------------------------------
# The classified set. Keep sorted by module, then qualname.
# ---------------------------------------------------------------------------
SURFACES: tuple[Surface, ...] = (
    Surface(
        "adapters.persistence.neo4j._crud_mixin",
        "_CrudMixin.get_visible_to_user",
        Disposition.ANCHORED,
        "THE by-UID carve-out — and the referent of five comments that named it "
        "`get_visible_by_uid`, a method which has never existed in this tree. "
        "It composes build_search_visibility_clause with "
        "apply_publication_gate=False, so it scopes the AUDIENCE and "
        "deliberately does NOT withhold drafts: the caller named the entity, "
        "and an author opens their own unfinished work. It was registered GATED "
        "with a reason describing a LIST, which is why ANCHORED stood at zero "
        "entries while its canonical member sat in the gated set — the "
        "disposition and the reason were both wrong about the same surface.",
    ),
    Surface(
        "adapters.persistence.neo4j._knowledge_context_mixin",
        "_KnowledgeContextMixin.find_learning_gaps",
        Disposition.GATED,
        "The caller holds GOALS and gets back the knowledge they require — "
        "curriculum it never referenced.",
    ),
    Surface(
        "adapters.persistence.neo4j._knowledge_context_mixin",
        "_KnowledgeContextMixin.find_learning_paths_teaching_ku",
        Disposition.GATED,
        "KU->path. Gates the bridging STEP as well as the path: the claim "
        "'this path teaches that KU' is carried by the bridge, so a published "
        "path reachable only via a draft step advertises unfinished content.",
    ),
    Surface(
        "adapters.persistence.neo4j._knowledge_context_mixin",
        "_KnowledgeContextMixin.find_learning_recommendations",
        Disposition.GATED,
        "A recommendation is the purest discovery surface.",
    ),
    Surface(
        "adapters.persistence.neo4j._knowledge_context_mixin",
        "_KnowledgeContextMixin.find_path_steps_containing_ku",
        Disposition.GATED,
        "A relational hop from a held KU that surfaces other curriculum.",
    ),
    Surface(
        "adapters.persistence.neo4j._knowledge_context_mixin",
        "_KnowledgeContextMixin.find_ready_to_learn",
        Disposition.GATED,
        "THE 'what can I learn next' surface. A withheld prerequisite still "
        "COUNTS but is not NAMED — dropping it from the count would raise "
        "readiness and recommend a blocked KU as more ready.",
    ),
    Surface(
        "adapters.persistence.neo4j._knowledge_context_mixin",
        "_KnowledgeContextMixin.get_ku_lateral_edges",
        Disposition.GATED,
        "Either endpoint may be the anchor, so the gate is 'held OR published' "
        "— gating both ends would hide a draft KU's edges from the author who "
        "asked for them by UID.",
    ),
    Surface(
        "adapters.persistence.neo4j._lp_intelligence_mixin",
        "_LpIntelligenceMixin.get_optimal_path_recommendations",
        Disposition.GATED,
        "Recommends paths the caller never named. Its HAS_STEP traversal is "
        "deliberately NOT step-gated: only `path` is returned, and a path's own "
        "steps ride along with it (containment).",
    ),
    Surface(
        "adapters.persistence.neo4j._lp_intelligence_mixin",
        "_LpIntelligenceMixin.get_recommended_path_steps",
        Disposition.GATED,
        "Recommends steps the caller never named.",
    ),
    Surface(
        "adapters.persistence.neo4j._lp_progress_mixin",
        "_LpProgressMixin.get_paths_aligned_with_goal",
        Disposition.GATED,
        "Discovery from a held Goal via ALIGNED_WITH_GOAL.",
    ),
    Surface(
        "adapters.persistence.neo4j._lp_progress_mixin",
        "_LpProgressMixin.get_paths_by_knowledge",
        Disposition.GATED,
        "KU->path; gates the bridging STEP too, same reasoning as find_learning_paths_teaching_ku.",
    ),
    Surface(
        "adapters.persistence.neo4j._lp_progress_mixin",
        "_LpProgressMixin.get_user_paths_prioritized",
        Disposition.GATED,
        "MIXED surface: enumerates the whole catalogue AND orders by the "
        "learner's enrolment. The gate lands after the progress match and "
        "yields to it — drafts are UNLISTED, not forbidden.",
    ),
    Surface(
        "adapters.persistence.neo4j._lp_step_mixin",
        "_LpStepMixin.list_all_paths_with_steps",
        Disposition.GATED,
        "The path catalogue. Gates `p` only — the steps it collects ride along "
        "with the path that holds them (containment).",
    ),
    Surface(
        "adapters.persistence.neo4j._organizes_mixin",
        "_OrganizesMixin.list_root_organizers",
        Disposition.GATED,
        "The MOC root listing — an entry point into curriculum the caller never named.",
    ),
    Surface(
        "adapters.persistence.neo4j._search_raw_mixin",
        "_SearchRawMixin.faceted_search_raw",
        Disposition.GATED,
        "Faceted search over the corpus; carries publication via build_search_visibility_clause.",
    ),
    Surface(
        "adapters.persistence.neo4j._semantic_mixin",
        "_SemanticMixin.compute_hub_scores",
        Disposition.WRITER,
        "Maintains a cached degree-centrality score. Composes the knowledge "
        "read clause with apply_publication_gate=False: a writer that skipped "
        "drafts would leave them with no cached score, and nothing recomputes "
        "on publish, so the value would still be stale when it became visible.",
    ),
    Surface(
        "adapters.persistence.neo4j._semantic_mixin",
        "_SemanticMixin.discover_semantic_bridges",
        Disposition.GATED,
        "Surfaces entities in OTHER domains the caller never referenced. Gates "
        "`shared` as well as `target` — the bridge uid is RETURNED as "
        "shared_concept. It carries no label in the pattern, which is how it "
        "escaped the label-keyed census.",
    ),
    Surface(
        "adapters.persistence.neo4j._semantic_mixin",
        "_SemanticMixin.query_foundational_knowledge",
        Disposition.GATED,
        "Ranks the KU corpus by hub score — discovery over everything.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.collab_backends",
        "LateralRelationshipBackend.get_relationships",
        Disposition.CONTAINMENT,
        "The held anchor's OWN lateral edges ride along with it — a by-anchor "
        "relationship read, not a discovery listing. Composes "
        "build_search_visibility_clause for the AUDIENCE half only (ADR-085 "
        "G4: owned targets are withheld from everyone but their owner) with "
        "apply_publication_gate=False — a draft neighbour of a held entity "
        "stays reachable, matching the by-UID carve-out.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.curriculum_backends",
        "<module>:_KNOWLEDGE_HEALTH_PARAMS",
        Disposition.REPORTS_DRAFTS,
        "The knowledge-health gauge takes build_publication_clause's PARAMS "
        "only (_KNOWLEDGE_HEALTH_PARAMS), so the draft vocabulary keeps one "
        "definition while the gauge REPORTS draft_curriculum_count rather than "
        "subtracting it — an authoring instrument should show its author "
        "unfinished work.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.curriculum_backends",
        "_nous_subtopic_pairs_query",
        Disposition.GATED,
        "Facet vocabulary for the curriculum filters: a draft's nous/subtopic "
        "must not populate a dropdown. NOT covered by the output invariant — "
        "what it returns is vocabulary, not identity, so there is no uid to "
        "detect. Stated as a residual rather than left to read as covered.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.curriculum_backends",
        "KuBackend.get_learning_path_uids",
        Disposition.GATED,
        "The third KU->path surface. Its HAS_STEP arm names and gates the "
        "bridging step; its REQUIRES_KNOWLEDGE arm has no bridge, so only `lp` "
        "gates there.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.curriculum_backends",
        "KuBackend.search_by_alias",
        Disposition.GATED,
        "A search over the whole Ku corpus.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.curriculum_backends",
        "PsBackend.count_engaged_knowledge",
        Disposition.USER_STATE,
        "Counts the knowledge the learner themselves marked in progress, "
        "mastered or read — Ku AND PathStep, since report-driven mastery lands "
        "on :Ku. The helper is doing real work here rather than riding along: "
        "its entity_type predicate IS the scope, there being no label pin. The "
        "publication half is off because the learner's own totals must not "
        "shrink when an author reopens an item for editing.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.curriculum_backends",
        "PsBackend.find_engaged_path_steps_by_date_range",
        Disposition.USER_STATE,
        "The windowed form of the same engagement set, feeding the weekly "
        "knowledge-substance metric. Reachable only from edges the learner "
        "wrote, so it discovers no curriculum they have not already opened — "
        "gating it would silently rewrite a past week's numbers.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.curriculum_backends",
        "PsBackend.get_prioritized_steps",
        Disposition.GATED,
        "MIXED surface, same shape as get_user_paths_prioritized: the gate "
        "yields to the learner's own progress.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.curriculum_backends",
        "PsBackend.get_standalone_steps",
        Disposition.GATED,
        "Lists steps belonging to no path — a catalogue.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.curriculum_backends",
        "PsBackend.list_steps_raw",
        Disposition.GATED,
        "The PathStep catalogue.",
    ),
    Surface(
        "adapters.persistence.neo4j.cross_domain_backend",
        "CrossDomainBackend.find_knowledge_hubs",
        Disposition.GATED,
        "Ranks the KU corpus by connectivity.",
    ),
    Surface(
        "adapters.persistence.neo4j.cross_domain_backend",
        "CrossDomainBackend.find_learning_clusters",
        Disposition.GATED,
        "Surfaces clusters of curriculum the caller never named.",
    ),
    Surface(
        "adapters.persistence.neo4j.cross_domain_backend",
        "CrossDomainBackend.find_similar_knowledge",
        Disposition.GATED,
        "A traversal from a held Ku that surfaces OTHER Kus — the carve-out is "
        "containment, and a similarity hop is not containment.",
    ),
    Surface(
        "adapters.persistence.neo4j.zpd_backend",
        "<module>:_ZONE_PUBLICATION_CLAUSE",
        Disposition.GATED,
        "The ZPD proximal zone — a recommendation, and the purest discovery "
        "surface there is. Composed at MODULE level (_ZONE_QUERY substitutes a "
        "sentinel into a plain-string template, because 17 Cypher brace pairs "
        "make an f-string error-prone), which is why the audit must attribute "
        "compositions outside functions. Only the proximal zone gates; the "
        "CURRENT zone is user-state and gating it would erase the learner's "
        "own history.",
    ),
    # The four search-strategy query builders. They live beside the helper
    # definitions but are surfaces in their own right: each composes a gate and
    # returns executable Cypher. Registered explicitly because an earlier
    # revision of the audit skipped the whole module and hid them, which would
    # have let a removed gate here pass both mechanisms green (Codex P2, #1012).
    Surface(
        "adapters.persistence.neo4j.query.cypher.crud_queries",
        "build_array_any_match_query",
        Disposition.GATED,
        "Tag/array search over the corpus. Publication rides on "
        "build_search_visibility_clause. Not output-measured — a query builder "
        "returns a string, not rows; covered by tests/unit/"
        "test_search_visibility_scoping.py.",
    ),
    Surface(
        "adapters.persistence.neo4j.query.cypher.crud_queries",
        "build_array_contains_query",
        Disposition.GATED,
        "Single-value array search over the corpus — the sibling of "
        "build_array_any_match_query, given the same clause composition by "
        "ADR-085 G5. Same builder residual: string out, not rows; covered by "
        "tests/unit/test_search_visibility_scoping.py.",
    ),
    Surface(
        "adapters.persistence.neo4j.query.cypher.crud_queries",
        "build_distinct_values_query",
        Disposition.GATED,
        "Facet vocabulary for filter dropdowns — a draft's values must not "
        "populate one. Same residual as _nous_subtopic_pairs_query: what it "
        "yields is vocabulary, not identity.",
    ),
    Surface(
        "adapters.persistence.neo4j.query.cypher.crud_queries",
        "build_graph_aware_search_query",
        Disposition.GATED,
        "Graph-traversal search strategy; gates the TARGET of the traversal, "
        "which is curriculum the caller never named.",
    ),
    Surface(
        "adapters.persistence.neo4j.query.cypher.crud_queries",
        "build_relationship_traversal_query",
        Disposition.GATED,
        "Relationship-traversal read behind get_by_relationship — targets are "
        "entities the caller never named, scoped by ADR-085 G3 through "
        "build_search_visibility_clause (audience + publication for the "
        "curriculum-facing declarations). Builder residual: string out, not "
        "rows; covered by tests/unit/test_search_visibility_scoping.py.",
    ),
    Surface(
        "adapters.persistence.neo4j.query.cypher.crud_queries",
        "build_text_search_query",
        Disposition.GATED,
        "The text-search strategy — a search over the whole corpus.",
    ),
    Surface(
        "adapters.persistence.neo4j.vector_search_backend",
        "VectorSearchBackend.query_vector_index",
        Disposition.GATED,
        "THE vector-discovery chokepoint — gating here covers every similarity "
        "surface at once rather than per-caller.",
    ),
    Surface(
        "adapters.persistence.neo4j.vector_search_backend",
        "VectorSearchBackend.query_fulltext_index",
        Disposition.GATED,
        "The fulltext half of hybrid search — an ungated fulltext door would "
        "resurface drafts the vector gate withholds (Codex #1006 class).",
    ),
    Surface(
        "adapters.persistence.neo4j.vector_search_backend",
        "VectorSearchBackend._chunk_visibility_clause",
        Disposition.GATED,
        "The body-chunk (RAG) audience clause, composed on EVERY chunk query: "
        "a curriculum parent must be published, a user-owned parent must be "
        "the viewer's (ADR-085 G8). An ungated chunk door would let a draft "
        "PathStep's body re-enter /search and Askesis through the Digital layer.",
    ),
)


def gated_surfaces() -> tuple[Surface, ...]:
    """Surfaces the output invariant applies to."""
    return tuple(s for s in SURFACES if s.disposition is Disposition.GATED)


def registry_keys() -> frozenset[tuple[str, str]]:
    """``(module, qualname)`` pairs, for the AST audit to match against."""
    return frozenset((s.module, s.qualname) for s in SURFACES)


__all__ = ["Disposition", "SURFACES", "Surface", "gated_surfaces", "registry_keys"]
