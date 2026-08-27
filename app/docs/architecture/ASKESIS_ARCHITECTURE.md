# Askesis Architecture - Cross-Cutting Intelligence System

**Last Updated:** March 12, 2026

## Overview

Askesis is one of SKUEL's **5 Cross-Cutting Systems** providing life context synthesis and action recommendations. Unlike Activity Domain services that manage entities, Askesis synthesizes across all entity types to answer: *"What should I work on next?"*

---

## Position in SKUEL Architecture

### The 5 Cross-Cutting Systems

| System | Purpose | Type |
|--------|---------|------|
| **UserContext** | ~240 fields of cross-domain state | Foundation |
| **Search** | Unified search across all domains | Infrastructure |
| **Calendar** | Aggregates Tasks, Events, Habits, Goals | Aggregation |
| **Askesis** | Life context synthesis + recommendations | Intelligence |
| **Messaging** | Notifications, alerts, reminders | Communication (Planned) |

### Askesis vs. Domain Services

```
Activity (6)                   Askesis
┌─────────────────┐          ┌─────────────────┐
│ TasksService    │          │                 │
│ GoalsService    │──────────│ AskesisService  │
│ HabitsService   │          │                 │
│ EventsService   │──────────│ (Synthesizes    │
│ ChoicesService  │          │  all domains)   │
│ PrinciplesService│          │                 │
└─────────────────┘          └─────────────────┘
        │                            │
        ▼                            ▼
Single-domain CRUD            Cross-domain Intelligence
```

---

## Facade Architecture

### Design Pattern

Askesis uses a **pure facade pattern** with zero business logic in the main service, and a typed `AskesisDeps` dataclass for dependency injection (March 2026):

```python
@dataclass(frozen=True)
class AskesisDeps:
    """Typed dependency container — all deps required (March 2026 streamlining)."""
    intelligence_factory: UserContextIntelligenceFactory
    graph_intel: Any
    user_service: Any
    llm_service: Any
    embeddings_service: Any
    knowledge_service: Any
    tasks_service: Any
    goals_service: Any
    habits_service: Any
    events_service: Any
    zpd_service: ZPDOperations            # Required for guided pipeline (LP gate ensures curriculum exists)
    citation_service: Any | None = None   # Wired in bootstrap via PathStep backend
    # PS bundle dependencies for ContextRetriever
    ku_service: Any | None = None         # For PS bundle KU fetching
    lp_service: Any | None = None         # For PS bundle LP fetching
    principles_service: Any | None = None # For PS bundle principle fetching


class AskesisService:
    """Facade coordinating 7 specialized sub-services. Zero business logic."""

    def __init__(self, deps: AskesisDeps) -> None:
        # Sub-service creation (no circular dependencies - uses pure functions)
        self.state_analyzer = UserStateAnalyzer()
        self.recommendation_engine = ActionRecommendationEngine()
        self.relevance_engine = ContextRelevanceEngine(graph_intel=deps.graph_intel)
        self.entity_extractor = EntityExtractor(...)

        # ContextRetriever handles graph retrieval + PS bundle loading.
        # August 2026: its graph_intel param deleted — superseded by
        # ku_backend/ps_backend (March 2026 Cypher migration).
        self.context_retriever = ContextRetriever(
            ps_service=deps.knowledge_service,
            ku_service=deps.ku_service,
            ku_backend=deps.ku_backend,
            ps_backend=deps.ps_backend, ...
        )

        # January 2026: QueryProcessor decomposition
        self.intent_classifier = IntentClassifier(embeddings_service=deps.embeddings_service)
        self.response_generator = ResponseGenerator()

        self.query_processor = QueryProcessor(
            intent_classifier=self.intent_classifier,
            response_generator=self.response_generator,
            entity_extractor=self.entity_extractor,
            context_retriever=self.context_retriever,
            zpd_service=deps.zpd_service,
            ...
        )

        # Required: 13-domain synthesis capability
        self.intelligence_factory = deps.intelligence_factory
```

### Sub-Service Responsibilities

```
AskesisService (Facade)
├── UserStateAnalyzer (uses state_scoring.py pure functions)
│   ├── analyze_user_state()
│   ├── identify_patterns()
│   └── calculate_system_health()
├── ActionRecommendationEngine (uses state_scoring.py pure functions)
│   ├── get_next_best_action()
│   ├── optimize_workflow()
│   └── predict_future_state()
├── QueryProcessor (LP-scoped RAG orchestrator + GuidanceMode-aware pipeline)
│   ├── answer_user_question()        ← main RAG pipeline (LP gate + ZPD + GuidanceMode)
│   └── process_query_with_context()
├── IntentClassifier (January 2026 - extracted from QueryProcessor)
│   ├── classify_intent()             ← embeddings-based QueryIntent (WHAT)
│   ├── classify_pedagogical_intent() ← deterministic decision tree
│   └── determine_guidance_mode()     ← maps PedagogicalIntent → GuidanceMode (HOW)
├── ResponseGenerator (January 2026 - extracted from QueryProcessor)
│   ├── build_llm_context()
│   ├── build_guided_system_prompt()  ← 4 mode builders (DIRECT/SOCRATIC/EXPLORATORY/ENCOURAGING)
│   ├── generate_actions()
│   └── generate_suggested_actions()
├── EntityExtractor
│   ├── extract_entities_from_query() ← global extraction
│   └── extract_from_bundle()         ← PS-scoped extraction
├── ContextRetriever
│   ├── retrieve_relevant_context()   ← graph + semantic retrieval
│   ├── load_ps_bundle()              ← loads PsBundle from UserContext
│   ├── get_learning_context()
│   └── analyze_knowledge_gaps()
```

### State Scoring Pure Functions (January 2026)

UserStateAnalyzer and ActionRecommendationEngine share common state scoring logic via pure functions in `state_scoring.py`:

```python
# /core/services/askesis/state_scoring.py
def score_current_state(user_context: UserContext) -> float:
    """Score the current state quality (0.0 to 1.0)."""

def find_key_blocker(user_context: UserContext) -> str | None:
    """Find the prerequisite that blocks the most items."""

def calculate_momentum(user_context: UserContext) -> float:
    """Calculate overall momentum score (0.0 to 1.0)."""

def calculate_domain_balance(user_context: UserContext) -> float:
    """Calculate balance across domains."""
```

This eliminates the former circular dependency between UserStateAnalyzer and ActionRecommendationEngine.

---

## Comparison to Activity Domain Facades

| Aspect | Activity Domain Facade | Askesis |
|--------|----------------------|---------|
| **Inheritance** | `BaseService` (explicit delegation methods) | `BaseService` (explicit delegation methods) |
| **Sub-services** | 7 (core, search, intelligence, etc.) | 7 (state, recommendation, query, intent, response, etc.) |
| **Entity CRUD** | Yes (BaseService) | No (cross-domain only) |
| **Backend** | `UniversalNeo4jBackend[T]` | None (uses domain services) |
| **Backend Protocol** | `{Domain}Operations` (types `self.backend`, NOT the service itself) | `AskesisOperations` |
| **Factory** | `create_common_sub_services()` | `create_askesis_service()` in `askesis_factory.py` |

### Why Different?

Askesis is fundamentally different:
1. **No entities** - Doesn't manage Askesis entities in Neo4j
2. **Cross-domain** - Synthesizes all entity types
3. **Intelligence-focused** - Recommendations, not CRUD
4. **Factory-dependent** - Requires UserContextIntelligenceFactory

---

## Bootstrap Integration

### Creation Location

Askesis is created in `compose_services()` AFTER the intelligence factory, via `create_askesis_service()` — **only when `INTELLIGENCE_TIER=full`** (March 2026):

```python
# /services_bootstrap/compose.py (PHASE 4)
from core.services.askesis_factory import create_askesis_service

if tier.ai_enabled:
    # First: Create factory with all domain services
    context_intelligence_factory = UserContextIntelligenceFactory(
        tasks=activity_services["tasks"].relationships,
        goals=activity_services["goals"].relationships,
        # ... all activity + curriculum domains
    )

    # Then: Create Askesis via factory function (handles AskesisDeps construction)
    # KeyError on missing deps is intentional — fail-fast, no degraded mode
    services.askesis = create_askesis_service(
        intelligence_factory=context_intelligence_factory,
        learning_services=learning_services,
        activity_services=activity_services,
        user_service=user_service,
    )
else:
    logger.info("Askesis: skipped (INTELLIGENCE_TIER=%s)", tier.value)
```

In CORE tier, `services.askesis` is `None` and `register_domain_routes` skips Askesis route registration entirely (system-level guard). On a FULL-tier system, both `/api/askesis/ask` and `/askesis/api/submit` enforce a **per-user tier gate** (ADR-043): REGISTERED users receive a 403 even when the system is FULL — only MEMBER and above may consume AI budget. The gate is **fail-secure**: if `intelligence_tier` or `user_service` is `None` at route time (misconfigured bootstrap), AI access is denied rather than silently granted.

### Why This Order?

The `UserContextIntelligenceFactory` requires all domain relationship services. These are only available after both `_create_activity_services()` and `_create_learning_services()` have completed.

**January 2026 Change:** Askesis was moved OUT of `_create_learning_services()` to enable passing the factory at construction time (eliminating post-wiring).

---

## Dependency Graph

```
                    ┌─────────────────────────┐
                    │ UserContextIntelligence │
                    │       Factory           │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │    AskesisService       │
                    │      (Facade)           │
                    └───────────┬─────────────┘
                                │
   ┌────────────────────────────┼────────────────────────────┐
   │                            │                            │
┌──▼──────────────┐  ┌──────────▼──────────┐  ┌──────────────▼───────────────┐
│ UserStateAnalyzer│  │ActionRecommendation│  │      QueryProcessor          │
└────────┬────────┘  │      Engine        │  │  (LP-scoped RAG pipeline)    │
         │           └──────────┬─────────┘  └───────────┬───────────────────┘
         │                      │                        │
         └──────────┬───────────┘          ┌─────────────┼──────────────┐
                    │                      │             │              │
           ┌────────▼────────┐   ┌─────────▼───┐ ┌──────▼──────┐ ┌────▼────────────┐
           │ state_scoring.py│   │IntentClassi-│ │Context-     │ │ResponseGenerator│
           │ (pure functions)│   │    fier     │ │  Retriever  │ │(prompts+actions)│
           └─────────────────┘   └─────────────┘ └──────┬──────┘ └─────────────────┘
                                       │                │
                                       ▼                ▼
                                EmbeddingsService  Domain Services
                                                   (PathStep, KU, Resource,
                                                    LP, Habits, Tasks, etc.)
                                                        │
                                               GraphIntelligence
                                                   Service
                                                        │
                                                   ZPDService
```

---

## Key Files

| File | Purpose |
|------|---------|
| `/core/services/askesis_service.py` | Main facade + `AskesisDeps` typed dataclass |
| `/core/services/askesis_factory.py` | `create_askesis_service()` — constructs AskesisDeps + returns AskesisService |
| `/core/models/submissions/journal_insight.py` | `JournalInsight` frozen dataclass — ZPD signals from journal (Phase 2 stub) |
| `/core/services/askesis/user_state_analyzer.py` | State assessment |
| `/core/services/askesis/action_recommendation_engine.py` | Recommendations |
| `/core/services/askesis/state_scoring.py` | Pure functions for state scoring (January 2026) |
| `/core/services/askesis/query_processor.py` | LP-scoped RAG pipeline orchestration (LP gate + ZPD + GuidanceMode) |
| `/core/services/askesis/intent_classifier.py` | Intent classification: embeddings (QueryIntent) + decision tree (GuidanceDetermination) |
| `/core/services/askesis/response_generator.py` | LLM context, guided system prompts (4 modes), action generation |
| `/core/services/askesis/entity_extractor.py` | Entity extraction: global + bundle-scoped |
| `/core/services/askesis/context_retriever.py` | Graph + semantic retrieval + PS bundle loading |
| `/core/services/askesis/askesis_core_service.py` | CRUD + `build_user_context()` (owns Neo4j driver) |
| `/core/services/askesis/types.py` | Shared data classes |
| `/core/ports/askesis_protocols.py` | Protocol definitions |
| `/adapters/inbound/askesis_routes.py` | Route wiring (DomainRouteConfig) |
| `/adapters/inbound/askesis_api.py` | JSON API endpoints |
| `/adapters/inbound/askesis_ui.py` | UI routes (thin — delegates to `ui/askesis/`) |
| `/ui/askesis/` | UI components (chat shell, nav) |

---

## Protocol Interface

### Complete Protocol

```python
@runtime_checkable
class AskesisOperations(
    AskesisStateAnalysisOperations,      # 3 methods
    AskesisRecommendationOperations,     # 3 methods
    AskesisQueryOperations,              # 2 methods
    AskesisDomainSynthesisOperations,    # 8 methods
    Protocol,
):
    """Complete Askesis intelligence operations (17 methods)."""

    async def load_askesis_context(self, askesis_uid: str) -> Result[AskesisContext]:
        """Load Askesis instance + owner's rich UserContext in one call."""
        ...
```

### Usage

```python
from core.ports import AskesisOperations

def process(askesis: AskesisOperations) -> Result[...]:
    return await askesis.get_daily_work_plan(context)
```

---

## Data Classes

### From `/core/services/askesis/types.py`

```python
@dataclass(frozen=True)
class AskesisInsight:
    """Identified pattern or opportunity."""
    type: str           # "pattern", "opportunity", "risk"
    domain: str         # Source domain
    description: str    # Human-readable description
    confidence: float   # 0.0-1.0

@dataclass(frozen=True)
class AskesisRecommendation:
    """Prioritized action recommendation."""
    action: str         # Action to take
    entity_type: str    # Domain type
    entity_uid: EntityUID     # Specific entity
    priority: int       # 1 (highest) to 5 (lowest)
    reasoning: str      # Why this action

@dataclass(frozen=True)
class AskesisAnalysis:
    """Complete state analysis."""
    insights: list[AskesisInsight]
    recommendations: list[AskesisRecommendation]
    health_metrics: dict[str, float]
    timestamp: datetime
```

---

## Routes

**The `@rt()` decorators are the source of truth** — read them directly rather than trusting a
table here. A route table in this file drifted into mostly-fiction once already: it listed four
API endpoints that no longer exist — two (`analyze`, `next-action`) never did, and two
(`daily-plan`, `synergies`) were real routes dropped in `2b0d7628d`. It is not reproduced.

- **API** — `/adapters/inbound/askesis_api.py` registers exactly one route: `/api/askesis/ask`.
- **UI** — `/adapters/inbound/askesis_ui.py` (thin; delegates to `ui/askesis/`). Six routes under
  the `/askesis` prefix: the main page (`/askesis`) and the HTMX submit endpoint
  (`/askesis/api/submit`) do the work; `new-chat`, `history`, `analytics` and `settings` are
  registered but are bare `302` redirects back to `/askesis`.

**The invariant that matters:** both surfaces converge on the same entry method —
`AskesisService.answer_user_question()` → `QueryProcessor.answer_user_question()`. No HTTP route
reaches the pipeline any other way. (`process_query_with_context()` is a second entry method on
the same service and port — `askesis_service.py:362` — but has no route today.)

---

## UserContext Depth — Critical for Intelligence Quality

### Two Depths

| Method | Depth | `entities_rich` | Use Case |
|--------|-------|-----------------|---------|
| `get_user_context()` | Standard | **Empty** | Ownership checks, basic queries |
| `get_rich_unified_context()` | Rich | **Populated** | Intelligence, Askesis routes |

### Why Askesis Requires Rich Context

The intelligence layer's `TemporalMomentumMixin` and several other mixin services check `entities_rich` for:
- At-risk habit detection (streak momentum)
- Overdue task patterns
- Goal advancement history
- Activity momentum scoring

If `entities_rich` is empty, these mixins return empty signals and the daily plan degrades silently.

**All Askesis intelligence routes use `get_rich_unified_context()` via `AskesisService.load_askesis_context()`.** This method fetches the Askesis instance, derives the user_uid, and builds the rich UserContext in a single service call — eliminating orchestration from routes. The 5-minute cache on `get_rich_unified_context()` means no performance regression vs. standard depth.

```python
# CORRECT — service handles the orchestration
ctx_result = await askesis_service.load_askesis_context(askesis_uid)
ctx = ctx_result.value  # AskesisContext(askesis, user_uid, user_context)

# WRONG — leaves entities_rich empty, degrades intelligence
# context_result = await user_service.get_user_context(askesis.user_uid)
```

### `entities_rich` Structure (March 2026)

`entities_rich` is a `dict[str, list[dict[str, Any]]]` with keys per domain. Populated by `build_rich()` on the UserContext builder:

```python
# Access pattern in intelligence services
entities_rich = user_context.entities_rich
tasks_rich = entities_rich.get("tasks", [])
goals_rich = entities_rich.get("goals", [])
habits_rich = entities_rich.get("habits", [])
events_rich = entities_rich.get("events", [])
choices_rich = entities_rich.get("choices", [])
principles_rich = entities_rich.get("principles", [])
```

---

## Evolution History

| Date | Change |
|------|--------|
| **October 2025** | Phase 1: RAG pipeline with basic Q&A |
| **November 2025** | Phase 2: Cross-domain synergy detection |
| **December 2025** | Phase 3: Life path alignment scoring |
| **January 2026** | Phase 4: Schedule-aware recommendations |
| **January 2026** | Architecture evolution: `intelligence_factory` required at construction |
| **January 2026** | Circular dependency eliminated via `state_scoring.py` pure functions |
| **January 2026** | QueryProcessor decomposition: IntentClassifier + ResponseGenerator extracted (962 → ~500 lines) |
| **January 2026** | Unused dependencies removed (`learning_orchestrator`, `cascade_manager`) - One Path Forward |
| **January 2026** | Stub implementations completed - semantic search, gap analysis, LLM integration, prerequisite ordering |
| **February 2026** | Route wiring switched to DomainRouteConfig (was bypassed in bootstrap) |
| **February 2026** | Neo4j driver encapsulated in `AskesisCoreService.build_user_context()` — routes no longer hold a raw driver |
| **June 2026** | Per-user intelligence tier gate added to both Askesis endpoints (ADR-043): REGISTERED users on FULL-tier systems now receive 403; `intelligence_tier` and `user_service` injected via `DomainRouteConfig.api_related_services` / `ui_related_services` |
| **June 2026** | Tier gate hardened to fail-secure: if `intelligence_tier` or `user_service` is `None` at route time, AI access is denied (previously silently bypassed) |
| **February 2026** | Reports → Submissions + Reports rename; Processing Domains now: Submissions, Journals, Reports |
| **March 2026** | `_load_askesis_and_context` closure extracted from route layer into `AskesisService.load_askesis_context()` — returns `AskesisContext` dataclass; `user_service` removed from route wiring; `askesis_core_service` wired into `AskesisDeps` |
| **March 2026** | `entities_rich` unification: `active_task_rich`, `active_goal_rich`, etc. → single `entities_rich` dict; `activity_rich` removed |
| **March 2026** | `ActivityDataReader` absorbed into `UserContext.build_rich()` — no longer a separate service |
| **March 2026** | `ActivityReviewService` split into `ActivityReportService` + `ReviewQueueService` |
| **March 2026** | EntityType renames: `AI_FEEDBACK → ACTIVITY_REPORT`, `FEEDBACK_REPORT → SUBMISSION_FEEDBACK` |
| **March 2026** | All intelligence routes switched to `get_rich_unified_context()` — ensures `entities_rich` is populated |
| **March 2026** | `AskesisDeps` typed dataclass replaces positional kwargs; `create_askesis_service()` factory in `askesis_factory.py` handles bootstrap construction |
| **March 2026** | `JournalInsight` frozen dataclass added — ZPD signal extraction point from processed journals (Phase 2 stub) |
| **March 2026** | 4 pedagogical prompt templates added: `askesis_scaffold_entry`, `askesis_socratic_turn`, `askesis_ku_bridge`, `askesis_journal_reflection` |
| **March 2026** | Backwards compatibility removed: all `AskesisDeps` fields required, `zpd_service` required (LP gate ensures curriculum exists), keyword fallback deleted from IntentClassifier, template fallback deleted from QueryProcessor, Askesis creation gated behind `INTELLIGENCE_TIER=full` |
| **March 2026** | `AskesisCitationService` wired in bootstrap — `create_askesis_service()` now requires `citation_service` param; QueryProcessor formats prerequisite-chain citations in responses |
| **March 2026** | Socratic pipeline added (LSContextLoader, SocraticEngine) then absorbed into existing services: LSContextLoader → ContextRetriever.load_ps_bundle(), SocraticEngine → ResponseGenerator.build_guided_system_prompt(), GuidanceDetermination added to IntentClassifier. LP enrollment gate. GuidanceMode enum: DIRECT/SOCRATIC/EXPLORATORY/ENCOURAGING. ConversationStyle deleted. One pipeline. |
| **March 2026** | EntityExtractor DRY fix: 5 copy-pasted `_extract_*_entities()` methods → single generic `_extract_matching_entities()` with `_EntityLookup` protocol. -155 lines. |
| **March 2026** | Guided system prompts migrated to PROMPT_REGISTRY: 7 `askesis_guided_*` templates replace hardcoded strings in ResponseGenerator. Prompt text editable without touching Python. |
| **August 2026** | `AskesisService.__init__` copied 14 deps onto `self`; **nine** were never read by the class (`graph_intel`, `embeddings_service`, `knowledge_service`, `tasks_service`, `goals_service`, `habits_service`, `events_service`, `citation_service`, `ps_engagement_service`) — each already reaches its consumer off `deps` in the sub-service construction below. Deleted. ⚠️ Defect class: `test_askesis_rag_wiring` asserted `askesis.embeddings_service is not None` — a facade field nothing read, so it passed whether or not the code using it was wired, *and* kept the dead copy alive by naming it. Wiring tests must assert on the object that **calls** the dependency. ⚠️ Re-anchoring to `askesis.context_retriever.embeddings_service` was the *same* bug and got caught in review: `ContextRetriever` also only stored it (chunk retrieval moved to `search_router` in July 2026). That field and its constructor param are now deleted too (17 call sites); the assertion names `askesis.intent_classifier.embeddings_service`, which actually calls `create_embedding()`. **"Who holds a reference" is not "who uses it" — grep for a read before anchoring a test.** |
| **August 2026** | `EntityExtractor`'s five constructor annotations were all unsatisfiable — `PsOperations`/`TasksOperations`/`GoalsOperations`/`HabitsOperations`/`EventsOperations` are BACKEND protocols, and each param receives a facade (`PsService` implements 8 of `PsOperations`' 142 members). Never caught because `AskesisDeps` types those fields `Any`. All five now take `EntityLookup[T]`, promoted from `context_retriever.py` into `types.py` with `KuLookup[T]` and parameterized by model so `.value.title` is checked. ⚠️ An `Any`-typed deps container makes a false annotation permanently unfalsifiable — probe the handle, don't read the annotation. |
| **July 2026** | Enrollment gate made PS-first (systems-review Arc B): an active PathStep (`current_ps_uids`, IN_PROGRESS edge) OR an enrolled Learning Path unlocks Askesis. MEGA-QUERY `active_path_steps_rich` traversal fixed to the real IN_PROGRESS edge (WORKING_ON had no production writer, so the guided pipeline could never activate). Phantom `:Lp` label fixed to `:LearningPath` across the persistence layer. |

---

## Implementation Status (March 2026)

### Completed Implementations

Six stub implementations were completed to bring Askesis from ~60-70% to ~95% functionality:

| Method | File | Implementation |
|--------|------|----------------|
| `_find_similar_chunks()` | `context_retriever.py` | Chunk-level vector search via `SearchRouter.retrieve_scoped_chunks()` → `Neo4jVectorSearchService.find_similar_chunks_by_text` |
| `get_learning_context()` | `context_retriever.py` | Delegates to `PsBackend.get_user_learning_context()` |
| `_analyze_blocked_knowledge_prerequisites()` | `context_retriever.py` | Gap analysis via `KuBackend.get_unmastered_prerequisites()` + `count_dependents()` |
| `_identify_quick_wins_and_high_impact()` | `context_retriever.py` | Classification based on prerequisite count |
| `_generate_context_aware_response()` | `query_processor.py` | LLM integration (required) |
| `_order_by_prerequisites()` | `askesis_service.py` | Kahn's algorithm for topological sort |

### Semantic Search Implementation

`ContextRetriever._find_similar_chunks()` performs chunk-level vector search so
answers cite the actual matching passage (not just the parent PathStep's title).
It routes through **SearchRouter — THE single path for external chunk (RAG)
retrieval**; `self.search_router` is post-wired in compose (typed against the
`ScopedChunkRetrievalOperations` ISP slice), so the retriever never holds
`Neo4jVectorSearchService` directly. A facet `scope` narrows the passages to a
topic, which is how Find and Ask share one facet→scope *path*.

⚠️ **Shared path, unrelated scopes.** Ask is not Find with a different renderer:
Askesis reaches everything about the user, bounded by scopes the USER opens and
closes, while a search surface reaches what it lists. So a facet VOCABULARY is
never derived from a search surface's result set — `/search` scopes its NOUS
sub-topics to the domains it returns, and the Askesis composer keeps the widest
honest vocabulary (ruled 2026-08-26; see
[`docs/roadmap/done/search-facet-redesign.md`](../roadmap/done/search-facet-redesign.md),
ruling 7).

```python
async def _find_similar_chunks(
    self,
    query: str,
    _user_uid: UserUID,
    chunk_types: list[str] | None = None,
    scope: SearchRequest | None = None,
) -> list[dict[str, Any]]:
    # The router targets contentchunk_embedding_idx (not entity_embedding_idx).
    # The join chunk → content → entity surfaces the owning PathStep for citation.
    request = (
        scope.model_copy(update={"query_text": query, "limit": 5})
        if scope is not None
        else SearchRequest(query_text=query, limit=5)
    )
    result = await self.search_router.retrieve_scoped_chunks(
        request,
        chunk_types=chunk_types,  # intent-aware (e.g. PRACTICE → ["exercise","example"])
        min_score=0.6,
        user_uid=_user_uid,
    )
    return [
        {
            "chunk_uid": hit["chunk_uid"],
            "chunk_type": hit["chunk_type"],
            "text": hit["text"],
            "context_window": hit["context_window"] or hit["text"],
            "similarity": hit["similarity_score"],
            "parent_uid": hit["parent_uid"],      # owning PathStep
            "parent_title": hit["parent_title"],
        }
        for hit in result.value
    ]
```

### LLM Integration

`QueryProcessor._generate_context_aware_response()` uses LLMService directly — no fallback:

```python
async def _generate_context_aware_response(...) -> str:
    # Compact inline summary of the retrieved learning context
    context = "\n".join([f"Knowledge units: {len(current_knowledge)}", ...])
    return await self.llm_service.generate_context_aware_answer(
        query=query_message, user_context=context,
        additional_context=additional_context, intent=intent
    )
```

### Prerequisite Ordering (Kahn's Algorithm)

`ContextRelevanceEngine._order_by_prerequisites()`
(`core/services/askesis/context_relevance_engine.py:286`) orders KU UIDs from the prerequisite
edge set using Kahn's algorithm. **No test pins the output ordering, and the direction stated in
the method's own docstring is not the direction the loop produces — do not rely on either.**

**It contains no Cypher.** The graph read is delegated to a backend method —
`self.graph_intel.backend.get_prerequisite_graph(ku_uids=...)` — and the service does only the
pure in-memory sort (adjacency map → in-degree counts → Kahn's queue). This is the required
shape. SKUEL021 fails the build on *executable* Cypher in `core/`, `adapters/inbound/` and
`ui/`; Cypher quoted in docstrings and inert example blocks is deliberately exempt
(`CLAUDE.md:667`), so the instruction below is discipline, not lint enforcement.

> Earlier revisions of this doc showed an inline `MATCH ... REQUIRES_KNOWLEDGE ...` query inside
> this method and attributed it to `AskesisService`. Both were wrong — the class name and the
> pattern. Do not copy Cypher into a `core/services/` example.

---

## LLM Prompts

### Two Layers

Askesis uses PROMPT_REGISTRY for two distinct prompt layers:

1. **Guided system prompts (template-driven):** `ResponseGenerator.build_guided_system_prompt()` renders one of 7 `askesis_guided_*` templates via `PROMPT_REGISTRY.render()`. Each template encodes one `PedagogicalIntent`. The Python method computes dynamic context (PathStep refs, KU names, resource refs, edge text) and passes it as template placeholders. Prompt text is editable in `core/prompts/templates/` without touching Python.

2. **LLM context assembly (programmatic):** `ResponseGenerator.build_llm_context()` renders the user-state block for the context-aware LLM call: the `render_askesis_grounding` projection (explicit `ASKESIS_GROUNDING_FIELDS` list — ADR-082 D2) plus workload/alert mechanics and the PsBundle curriculum text. This layer remains programmatic — the context is data-driven, not pedagogical prose.

### Guided System Prompt Templates

| Template ID | GuidanceMode | PedagogicalIntent | Key Placeholders |
|-------------|-------------|-------------------|-----------------|
| `askesis_guided_redirect` | DIRECT | REDIRECT_TO_CURRICULUM | `{path_steps_text}`, `{resource_refs}` |
| `askesis_guided_out_of_scope` | DIRECT | OUT_OF_SCOPE | `{ls_title}`, `{ls_intent}` |
| `askesis_guided_direct` | DIRECT | *(user override — in-scope)* | `{ls_title}`, `{ls_intent}` |
| `askesis_guided_assess` | SOCRATIC | ASSESS_UNDERSTANDING | `{concepts}` |
| `askesis_guided_probe` | SOCRATIC | PROBE_DEEPER | `{concepts}` |
| `askesis_guided_scaffold` | EXPLORATORY | SCAFFOLD | `{concepts}`, `{resource_refs}` |
| `askesis_guided_connection` | EXPLORATORY | SURFACE_CONNECTION | `{edges_text}` |
| `askesis_guided_practice` | ENCOURAGING | ENCOURAGE_PRACTICE | `{practice_text}`, `{resource_refs}` |

### Interaction Pattern Templates (Staged — PLANNED, ADR-082 D4)

Four additional templates define future interaction patterns — session opener, mid-turn Socratic, KU bridge, journal reflection. These are defined as pedagogical design artifacts in `core/prompts/templates/`, not yet wired to the pipeline, and registered in the bloat detector's `PLANNED_TEMPLATES` tier (ADR-082 D4):

| Template ID | Interaction Pattern | Wired |
|-------------|-------------------|-------|
| `askesis_scaffold_entry` | Session opener — invite, don't lecture | Staged (PLANNED) |
| `askesis_socratic_turn` | Mid-conversation Socratic turn | Staged (PLANNED) |
| `askesis_ku_bridge` | Introduce adjacent KU as natural next step | Staged (PLANNED; first wiring candidate) |
| `askesis_journal_reflection` | Respond to journal open questions | Staged (PLANNED; je_pro shared-entry doorway only) |

### Remaining Migration

The LLM context assembly layer (`build_llm_context()`) and the Q&A/planning responses (`generate_context_aware_answer()`) could move to templates when their patterns stabilize:

| Planned Template ID | Service | Placeholders |
|-------------|---------|--------------|
| `askesis_qa_response` | `QueryProcessor` | `{query}`, `{intent}`, `{knowledge_context}`, `{learning_context}` |
| `askesis_daily_plan` | `ActionRecommendationEngine` | `{user_summary}`, `{active_tasks}`, `{goals_progress}` |

**See:** `@prompt-templates` skill — complete registry reference, naming conventions, anti-patterns

---

## Related Documentation

- **How Askesis Works:** [ASKESIS_HOW_IT_WORKS.md](./ASKESIS_HOW_IT_WORKS.md) — plain-English explanation of both halves (start here)
- **Pedagogical Architecture:** [ASKESIS_PEDAGOGICAL_ARCHITECTURE.md](./ASKESIS_PEDAGOGICAL_ARCHITECTURE.md) — GuidanceMode, ZPD, Socratic companion design
- **Intelligence Guide:** [ASKESIS_INTELLIGENCE.md](../intelligence/ASKESIS_INTELLIGENCE.md)
- **Search Integration:** [SEARCH_ARCHITECTURE.md](./SEARCH_ARCHITECTURE.md) — SearchRouter, the single path Askesis retrieves chunks through
- **UserContext Architecture:** [UNIFIED_USER_ARCHITECTURE.md](./UNIFIED_USER_ARCHITECTURE.md)
- **Prompt Registry:** `core/prompts/` — centralized LLM template store
- **ADR-021:** UserContext Intelligence Modularization
