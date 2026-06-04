# Intent-Traversal ↔ Registry Convergence

**Status:** Phase 0 ✅ done (PR #224, 2026-06-04) — `INTENT_BASED_TRAVERSAL.md` rewritten to reality. **Phase 1 in progress (One Path Forward, Tasks-first):** PR **2A** (engine: `relationship_types` threaded from `UnifiedRelationshipService.get_with_context` → `query_with_intent` → `build_context_query_for_intent`, registry-sourced from `cross_domain_relationship_types` + `LIMIT` cap; **Tasks + Events** routed onto mechanism B; broken Events `get_entity_context(entity_type=...)` `TypeError` deleted) — verified on live Neo4j. Remaining Phase 1: **2B** Goals + Habits, **2C** Choices + Principles + confirm mechanism A removed from the activity path + fold old Phase 2 into Phase 1. Phases 2–4 (below) not started.

> **Phase 0 surfaced facts Phase 1 must account for** (verified, in the rewritten doc): intent sourcing is split across **three mechanisms** that facades reach inconsistently — A `GraphContextLoader`→`EXPLORATORY` (Goals/Habits/Choices/Principles facades), B `UnifiedRelationshipService`→config intent (Tasks facade), C `get_entity_context`→`RELATIONSHIP` (Events facade, **currently broken** — passes an unsupported `entity_type=` kwarg → `TypeError`). So Phase 1 must target the specific mechanism each route/facade actually uses, and the broken Events `get_entity_context` call is a latent bug to fix separately.

**Core Principle:** *"One registry, two readers — collapse the duplication, keep the lens."*

## The situation, reframed

SKUEL has **two systems that read the graph around an entity**, grown from opposite ends and now nearly touching:

| | Intent-traversal | Cross-domain-context |
|---|---|---|
| Entry | `GraphIntelligenceService.query_with_intent(domain, uid, intent, depth)` | `UnifiedRelationshipService.get_cross_domain_context(uid, depth, min_confidence)` |
| Edge vocabulary | **Hard-coded** `type(r) IN [...]` per intent in `build_context_query_for_intent` (`adapters/persistence/neo4j/query/graph_context_query_builder.py`) | **Registry-driven** off `DomainRelationshipConfig.cross_domain_relationship_types` |
| Bucketing | none (flat node + rel lists) | incident-edge attribution, `filter_property` tiers, per-`context_field_name` buckets |
| Drift | yes — hand-maintained lists rot (e.g. choice lens names `CONFLICTS_WITH_GOAL`, an edge written nowhere) | no — single source of truth; hardened across #210/#212/#214/#215/#216/#218 |

The audit found the intent side is **mostly aspirational**: every activity-domain model inherits `Entity`'s default `QueryIntent.EXPLORATORY` (no override), so the real intent is whatever the domain *config* sets (`default_context_intent`); `PRINCIPLE_ALIGNMENT` / `PRINCIPLE_EMBODIMENT` / `SCHEDULED_ACTION` are selected by nothing and their query clauses are unreachable; and 5 of the 6 documented per-domain "analysis methods" don't exist.

**The generative read:** the dead `PRINCIPLE_ALIGNMENT` clause is not garbage — it is a *hypothesis* ("to understand a choice's principle-alignment, traverse these edges") that the registry can now answer **correctly**, because #214/#218 established the real choice edges (`AFFECTS_GOAL`, `INFORMED_BY_PRINCIPLE`, `GUIDES_CHOICE`, `INFORMED_BY_KNOWLEDGE`). Point the intent traversal at the registry and the lens comes alive *and* becomes drift-proof — by **removing** duplication, not adding code.

## Destination

> **Intents are named life-questions → resolved through the registry → dispatched through the hardened cross-domain-context machinery → returning one uniform analysis shape.**

- `QueryIntent` stays as the **semantic layer**: a catalog of meaningful questions ("Is this choice aligned with my principles?", "How is this principle lived?", "What does this event execute?"). These are candidate Askesis prompts, ZPD inputs, and UI affordances — not just internal query routing.
- The **edge vocabulary always comes from the registry** (`DomainConfig`), never a hard-coded list. One source of truth feeds both readers; drift becomes structurally impossible.
- Intent differentiates **shape, not vocabulary**: depth emphasis, direction weighting, scoring, which `context_field_name` buckets to foreground — applied on top of the registry edge set.
- Per-domain "analysis" is **one generic method** parameterized by `(intent, metrics_fn)` over `_analyze_entity_with_context`, not six bespoke functions that were never written.

## Phased sketch (each phase independently shippable + verifiable)

**Phase 0 — Honest doc (small, do first regardless). ✅ DONE (PR #224).** Rewrote `INTENT_BASED_TRAVERSAL.md` to *what is actually wired*. Key correction vs. the original belief: intent is **config-sourced, not model-sourced**, but it is reached through **three inconsistent mechanisms** and the config intents barely reach any live caller — so "Goals→GOAL_ACHIEVEMENT / Habits→PRACTICE are the live specialized lenses" was **wrong**. Verified: A `GraphContextLoader`→inherited `EXPLORATORY` (Goals/Habits/Choices/Principles facades); B `UnifiedRelationshipService`→config `default_context_intent` (**only** the Tasks facade reaches this, via `tasks/_relationship_mixin.py`); C `get_entity_context`→`RELATIONSHIP` (Events facade, **currently broken** — passes an unsupported `entity_type=` kwarg → `TypeError`). Removed the fictional analysis-method table and stale Key-Files paths; marked per-domain specialization *aspirational → this roadmap*.

**Phase 1 — Registry-sourced vocabulary (the proof).** Give `build_context_query_for_intent` the domain's relationship set (thread `relationship_types: list[str]` from `cross_domain_backend.query_with_intent`, sourced from `config.cross_domain_relationship_types`). When supplied, the `type(r) IN [...]` filter uses it instead of the hard-coded literal. Start with the choice/principle lenses where #214/#218 nailed the edges. Verify on live Neo4j that a choice's intent traversal now surfaces its real principle/goal/knowledge neighbors. Delete the now-unused hard-coded lists as each lens migrates (One Path Forward).

**Phase 2 — Collapse toward one reader.** With both readers drawing the same registry vocabulary, evaluate folding intent-traversal's output through the same incident-edge attribution + strongest-path dedup that `get_cross_domain_context` already does (see the gotcha box in `docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md`). Likely outcome: `query_with_intent` becomes a thin semantic-shaping wrapper over the cross-domain-context primitive, not a parallel Cypher path. Retire the dead `QueryIntent` clauses (`PRINCIPLE_ALIGNMENT`/`PRINCIPLE_EMBODIMENT`/`SCHEDULED_ACTION`) or revive them as real shapes — decided per lens, not preserved by default.

**Phase 3 — Uniform analysis via `(intent, metrics_fn)`.** Generalize the per-domain "analysis method" idea onto `_analyze_entity_with_context`: intent selects the lens, registry supplies the edges, the template supplies the fetch→context→metrics→recommendations pipeline, and a domain `metrics_fn` supplies meaning. The existing real analyzers (`analyze_choice_impact`, `get_goal_progress_dashboard`) become instances of one shape rather than divergent one-offs.

**Phase 4 — Intents as life-questions (product surface).** Expose the intent catalog where it belongs: Askesis reflective prompts, ZPD recommended-action inputs, and detail-page "ask the graph" affordances. This is where the seed flowers — the same machinery that answers an internal query answers a user's question about their own life path.

## Guardrails (lessons already paid for)

- **Don't mechanically patch the doc in isolation** — it describes behavior; a find-replace leaves false claims (see `feedback_mechanical_doc_rename_unsound`). Phase 0 is a genuine rewrite-to-reality, not a rename.
- **Verify every behavioral claim against code or defer it.** Phases 1–2 must be proven on live Neo4j; CI runs no pytest.
- **`CONFLICTS_WITH_GOAL` is written nowhere** — do not resurrect it; if a "conflict" lens is wanted, it needs a real edge a writer produces first.
- **Doc + dead code + plan move together** — pruning the dead `QueryIntent` clauses, correcting the doc, and proving the registry source are one arc, not three drive-by edits.

## Key references

- Audit findings + reframe: memory `project_intent_traversal_registry_convergence`.
- Real choice edges + the cross-domain-context hardening: `project_xdctx_family_a_unimplemented`, PRs #214/#218; `docs/intelligence/CHOICES_INTELLIGENCE.md`.
- Cross-domain-context mechanics (incident-edge attribution, strongest-path dedup): `docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md`.
- Registry (single source of truth): `core/models/relationship_registry.py` (`DomainRelationshipConfig`, `cross_domain_relationship_types`, `default_context_intent`, `get_intent_for_operation`).
- Live intent engine: `core/services/infrastructure/graph_intelligence_service.py`, `adapters/persistence/neo4j/query/graph_context_query_builder.py`.
