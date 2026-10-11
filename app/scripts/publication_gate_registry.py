"""The classified set of query surfaces that touch the curriculum publication gate.

**Why a registry rather than a hand-written list.** ``publication_state`` is
applied surface by surface, and a hand enumeration of those surfaces misses some:
the enumeration is the defect, not any individual missing gate. The misses take
two shapes, and this module is shaped around both. An **omission** is a surface
no census sees, because the census keys on labels and the binding carries none
(``discover_semantic_bridges``) or the bridging step is an anonymous
``(:Entity)`` (``get_learning_path_uids``). A **misclassification** is a surface
that is enumerated and gated, just gated wrongly: the wrong alias (gating ``lp``
in ``get_paths_by_knowledge`` and not the bridging ``ps``), the wrong half of a
mixed surface (gating the catalogue in ``get_prioritized_steps`` without yielding
to the learner's own progress), or the wrong channel (withholding the draft node
in ``find_ready_to_learn`` and then naming its uid inside a collected list).

So this module carries two things, and neither is a correctness judgement made
by a pattern:

1. **The classification** — every surface that composes a gate helper appears
   below with a disposition and a reason. ``scripts/audit_publication_gate.py``
   asserts the set is COMPLETE against the tree by AST. That claim ("is this
   surface classified?") is exactly decidable; the claim a linter must never
   make is "is this surface correctly gated?", which is where a regex
   approximating a parser generates an infinite tail — narrow the claim rather
   than approximate it.

2. **The criterion** — ``tests/integration/test_publication_gate_output_invariant.py``
   runs each GATED surface against a seeded graph and asserts no draft
   IDENTITY reaches the caller at any depth. That is the invariant itself
   rather than a proxy for it, and it is the only form that can express the
   misclassification shapes: it does not care which alias carries the
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

    ADMISSION = "admission"
    """A write door's admission read. It answers which of the uids a caller
    handed in name published nodes, so the door refuses an edge to a draft —
    it returns no curriculum the caller did not name, so there is nothing for
    the output invariant to withhold."""


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
        "adapters.persistence.neo4j._knowledge_context_mixin",
        "_KnowledgeContextMixin.get_exercises_for_path_step",
        Disposition.GATED,
        "The step page's exercise listing for a visitor who is not signed in: "
        "the SCOPE_AWARE audience predicate with no user, so the floor is "
        "published CURRICULUM alone — a teacher's PERSONAL or a group's ASSIGNED "
        "exercise hanging from the step is withheld, as is a draft-marked one. "
        "The step itself is the caller's anchor and is not gated here, as the "
        "page that embeds the listing opens a step by uid.",
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
        "adapters.persistence.neo4j._relationship_crud_mixin",
        "_RelationshipCrudMixin.batch_get_related_uids",
        Disposition.GATED,
        "The batched related-uid read behind the relationship service. Its anchors "
        "are the backend's own nodes, so under an Activity backend the related node "
        "is tied by build_link_far_node_clause and a draft at the far end of a "
        "user's link edge is not named.",
    ),
    Surface(
        "adapters.persistence.neo4j._relationship_query_mixin",
        "_RelationshipQueryMixin.get_related_entities",
        Disposition.GATED,
        "The caller holds one of its own activities and gets back the entities "
        "across an edge — curriculum it reached by a link, not by name. Tied "
        "through an Activity backend only (build_link_far_node_clause).",
    ),
    Surface(
        "adapters.persistence.neo4j._relationship_query_mixin",
        "_RelationshipQueryMixin.get_related_uids",
        Disposition.GATED,
        "The uid twin of get_related_entities — the read under every "
        "relationship-key lookup of the six Activity facades. A draft's uid "
        "across a link edge is withheld as if the edge were absent; the edge "
        "stays, so a republish restores it. Tied through an Activity backend only "
        "(build_link_far_node_clause).",
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
        "adapters.persistence.neo4j._traversal_mixin",
        "_TraversalMixin.find_uids_by_semantic_filter",
        Disposition.USER_STATE,
        "Returns the viewer's own activities that carry a semantic edge onto a "
        "target — the OWNER_ONLY clause on the returned node, composed because the "
        "target may be a shared Ku every learner links to. The rows are the user's "
        "entities, never curriculum, so there is no draft for a gate to withhold.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.activity_backends",
        "TasksBackend.get_tasks_reinforcing_habit",
        Disposition.USER_STATE,
        "The viewer's own tasks that reinforce a habit — the OWNER_ONLY clause on "
        "the task. A task is never draft curriculum.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.activity_backends",
        "TasksBackend.get_tasks_contributing_to_goal",
        Disposition.USER_STATE,
        "The viewer's own tasks that contribute to a goal — the OWNER_ONLY clause on "
        "the task. A task is never draft curriculum.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.activity_backends",
        "_edge_targets",
        Disposition.GATED,
        "The batched source→target edge maps (task→habit, event→habit, "
        "habit→goal, event→goal, task→goal). Targets are user-owned types today; the "
        "far-node predicate is composed whole so a map over a curriculum target "
        "would be gated by construction.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.collab_backends",
        "LateralRelationshipBackend.get_relationships",
        Disposition.GATED,
        "The lateral neighbours of a held anchor, each tied to the caller by "
        "build_far_node_clause (ADR-085 G4): the caller's own entity through any "
        "ownership spelling, or published shared content. The anchor itself rides "
        "along by uid; its draft NEIGHBOUR does not — a lateral edge carries a "
        "title into every lateral panel and the relationship graph, and the "
        "far-node rule withholds a draft's title across an edge from a reader.",
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
        "KuBackend.list_library",
        Disposition.GATED,
        "The Ku catalogue the /explore reading plan draws its fallback hero and "
        "its library size from — both a listing and a count, so a draft is "
        "neither shown nor counted.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.curriculum_backends",
        "KuBackend.search_by_alias",
        Disposition.GATED,
        "A search over the whole Ku corpus.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.curriculum_backends",
        "KuBackend.get_published_titles",
        Disposition.GATED,
        "The titles the hub's recommendations (method 1's ZPD and context "
        "sources) name their steps by — a recommendation is discovery, so a "
        "draft's title is withheld and its step keeps the uid placeholder.",
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
        "adapters.persistence.neo4j.backends.exercise_backends",
        "EntryReportBackend.get_for_owner",
        Disposition.ANCHORED,
        "The EntryReport owner read (ADR-088 §3) — the typed by-UID fetch behind "
        "the OWNER_ONLY clause, the same carve-out as _CrudMixin.get_visible_to_user "
        "with EntryReportBackend.get's subject_uid projection kept. The caller "
        "named the report; an EntryReport is never draft curriculum, so the gate "
        "has nothing to withhold here either way.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.exercise_backends",
        "ExerciseBackend.get_exercises_for_curriculum",
        Disposition.GATED,
        "The reverse lookup behind GET /api/exercises/for-curriculum — which "
        "exercises require this Ku. A discovery listing, so the SCOPE_AWARE "
        "audience predicate with the gate on: another user's unanchored PERSONAL "
        "exercise and a draft-marked shared one are absent, not refused.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.exercise_backends",
        "ExerciseBackend.get_ps_exercises_with_status",
        Disposition.GATED,
        "The signed-in step page's exercise listing (the learning-loop fragment). "
        "Every row links to the by-UID exercise read, so the listing composes the "
        "same SCOPE_AWARE audience predicate, gate on: a PERSONAL exercise hanging "
        "from a DRAFT step is listed to its owner only (the anchor admits it once "
        "the step is published), a draft-marked exercise to its owner only. The "
        "step is the caller's anchor and is not gated, as the embedding page opens "
        "a step by uid.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.exercise_backends",
        "ExerciseBackend.get_required_knowledge_for_user",
        Disposition.ANCHORED,
        "The by-UID read behind GET /api/exercises/required-knowledge: the "
        "exercise behind the SCOPE_AWARE audience predicate with the gate off — "
        "the caller named it, and an owner lists what their own draft requires — "
        "with its REQUIRES_KNOWLEDGE far ends riding along as the contents of a "
        "container the caller may open. Absent and out of audience are one "
        "outcome.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.sharing_backend",
        "_anchored_exercise_teacher_match",
        Disposition.ADMISSION,
        "The direct feedback target's rule (ADR-088 §9), composed by the resolving "
        "read and by the SUBMITTED_TO_TEACHER write: a turn-in on a PERSONAL exercise "
        "reaches its owner only while the anchoring PathStep is published "
        "(build_anchored_exercise_clause), so a draft step's exercise asks nobody. "
        "It returns a teacher uid or whether the edge landed — no curriculum the "
        "caller did not name.",
    ),
    Surface(
        "adapters.persistence.neo4j.connection_fetch_backend",
        "ConnectionFetchBackend.fetch_entity_connections",
        Disposition.GATED,
        "The connection chips on every Activity list and detail page: the owner "
        "sees the titles of what their entity links to. A linked Ku or PathStep "
        "that is now a draft is hidden, title and all (Mike, 2026-10-03) — no "
        "'already had it' exemption.",
    ),
    Surface(
        "adapters.persistence.neo4j.connection_fetch_backend",
        "ConnectionFetchBackend.fetch_source_pathstep",
        Disposition.GATED,
        "An activity's source_path_step_uid is a plain uid a vault file writes "
        "verbatim, so the step it resolves is curriculum the activity's owner may "
        "never have been shown: a draft resolves only when the owner ENGAGED_WITH "
        "it (the learner who started a step keeps the banner after it is "
        "unpublished — the gate yields to the learner's own engagement, as the "
        "mixed catalogue surfaces do).",
    ),
    Surface(
        "adapters.persistence.neo4j.cross_domain_backend",
        "<module>:_ADHERENCE_PRINCIPLE_WALL",
        Disposition.GATED,
        "The ZPD choice-adherence read: the principles that inform the user's "
        "choices, behind the far-node wall every reader of INFORMS_CHOICE composes "
        "— another user's principle is left out, and a shared one only when it is "
        "not a draft. Composed at module level because the statement is.",
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
        "adapters.persistence.neo4j.endpoint_queries",
        "<module>:_PUBLISHED_CLAUSE",
        Disposition.ADMISSION,
        "The link-edge guard's publication read (PUBLISHED_UIDS_BATCH_QUERY): of "
        "the far-end uids a link, create or vault door was handed, which name a "
        "published node. A shared far end it leaves out is refused like a uid that "
        "names nothing, so a learner's goal, habit or task cannot carry a draft "
        "Ku's title into its readers. Composed at module level because both "
        "backends that serve the guard share the one statement — and the guarded "
        "link write (build_guarded_link_query) re-asserts the same clause over its "
        "far node as it merges the edge, returning only which named uids it admitted.",
    ),
    Surface(
        "adapters.persistence.neo4j.backends.curriculum_backends",
        "<module>:_PUBLISHED_KU",
        Disposition.ADMISSION,
        "The Ku page's two learner writes' far end (KuBackend.mark_in_progress, "
        "KuBackend.mark_mastered — studying, understood): the edge lands on a "
        "published Ku only, so a learner's IN_PROGRESS / MASTERED never references "
        "a draft Ku. Each write returns whether it landed — no curriculum the caller "
        "did not name. Composed at module level because both writes share the one "
        "MATCH.",
    ),
    Surface(
        "adapters.persistence.neo4j._learning_state_mixin",
        "<module>:_PUBLISHED_STEP",
        Disposition.ADMISSION,
        "The PathStep learner-state writes' far end (record_view, mark_in_progress, "
        "mark_as_learning, mark_as_read, create_bookmark): the edge lands on a "
        "published step only, so a learner's VIEWED / IN_PROGRESS / MARKED_AS_READ / "
        "BOOKMARKED never references a draft. Each write returns whether it landed — "
        "no curriculum the caller did not name. Composed at module level because the "
        "five writes share the one MATCH.",
    ),
    Surface(
        "adapters.persistence.neo4j.user_relationship_backend",
        "<module>:_PUBLISHED_ENTITY",
        Disposition.ADMISSION,
        "UserRelationshipBackend.pin_entity's write: a Ku or PathStep nobody owns is "
        "pinned only when published, so a draft's uid never sits in a learner's pins "
        "for the Saved sidebar to resolve. It returns whether the pin landed — no "
        "curriculum the caller did not name.",
    ),
    Surface(
        "adapters.persistence.neo4j.entry_grounding_backend",
        "EntryGroundingBackend.write_applies_knowledge",
        Disposition.ADMISSION,
        "Vector grounding's edge write: it links an entry to a candidate Ku only "
        "when the Ku is published, so a draft never becomes a chip on the entry or "
        "earns a substance credit. It returns whether the edge was created — no "
        "curriculum the caller did not name.",
    ),
    Surface(
        "adapters.persistence.neo4j.query.cypher.context_query_generator",
        "_build_shared_neighbor_clause",
        Disposition.GATED,
        "The two-hop shared-neighbour clauses of the registry context statement: "
        "entity → shared node → related entity. Both the shared node and the "
        "related entity are tied to the entity's owner, so a draft is not the "
        "bridge either.",
    ),
    Surface(
        "adapters.persistence.neo4j.query.cypher.domain_queries",
        "build_entity_with_context",
        Disposition.GATED,
        "The registry context statement (generate_context_query) — an activity with "
        "every registered neighbour's uid and title. Under an Activity label each "
        "neighbour is tied by build_link_far_node_clause.",
    ),
    Surface(
        "adapters.persistence.neo4j.query.cypher.semantic_queries",
        "build_domain_context_with_paths",
        Disposition.GATED,
        "The path-aware neighbourhood. Under an owned center a draft on a path is "
        "left out with the paths that run through it; under a shared center (a Ku "
        "page) the fragment keeps shared content whatever its state, and "
        "publication is the curriculum readers' own gate.",
    ),
    Surface(
        "adapters.persistence.neo4j.user_context_queries",
        "_far_node",
        Disposition.GATED,
        "THE far-node predicate of the rich-context statements: every "
        "`__FAR(alias)__` token expands through it. The context feeds daily "
        "planning, Askesis and the insight routes, so a draft's title linked from "
        "a user's activity would reach all of them.",
    ),
    Surface(
        "adapters.persistence.neo4j.user_progress_backend",
        "UserProgressBackend.get_prerequisite_map",
        Disposition.GATED,
        "The global knowledge → prerequisites map behind the pathways progress "
        "summary. Unanchored, so it is a listing: both ends are scoped to "
        "published knowledge, which also keeps every user's goal (a "
        "REQUIRES_KNOWLEDGE source) out of it.",
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
        "adapters.persistence.neo4j._learning_state_mixin",
        "_LearningStateMixin.detect_path_step_completion",
        Disposition.GATED,
        "Derives a step's mastery from its Kus. An ungated derivation would write "
        "a learner-state reference to a draft step the learner never saw, and the "
        "learner-state reads (MASTERED_PATH_STEPS_QUERY) carry no gate of their own.",
    ),
    Surface(
        "adapters.persistence.neo4j._learning_state_mixin",
        "_LearningStateMixin.find_step_mastery_gaps",
        Disposition.GATED,
        "The reconciler's read of the same derivation across all users; a draft "
        "step is no gap until it is published.",
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
