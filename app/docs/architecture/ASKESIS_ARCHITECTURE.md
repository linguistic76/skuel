# Askesis Architecture - Cross-Cutting Intelligence System

**Last Updated:** March 8, 2026

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
    graph_intelligence_service: Any
    user_service: Any
    llm_service: Any
    embeddings_service: Any
    knowledge_service: Any
    tasks_service: Any
    goals_service: Any
    habits_service: Any
    events_service: Any
    citation_service: Any | None = None   # Not yet wired in bootstrap
    zpd_service: Any | None = None        # Optional: requires curriculum graph ≥ 3 KUs
    # Socratic pipeline (March 2026)
    ku_service: Any | None = None         # For LSContextLoader KU fetching
    lp_service: Any | None = None         # For LSContextLoader LP fetching
    principles_service: Any | None = None # For LSContextLoader principle fetching


class AskesisService:
    """Facade coordinating 7 specialized sub-services + Socratic pipeline. Zero business logic."""

    def __init__(self, deps: AskesisDeps) -> None:
        # Sub-service creation (no circular dependencies - uses pure functions)
        self.state_analyzer = UserStateAnalyzer()
        self.recommendation_engine = ActionRecommendationEngine()
        self.entity_extractor = EntityExtractor(...)
        self.context_retriever = ContextRetriever(...)

        # January 2026: QueryProcessor decomposition
        self.intent_classifier = IntentClassifier(embeddings_service=deps.embeddings_service)
        self.response_generator = ResponseGenerator()

        # March 2026: Socratic pipeline sub-services
        self.socratic_engine = SocraticEngine()
        self.conversation_context = ConversationContext()
        self.ls_context_loader = LSContextLoader(
            article_service=deps.knowledge_service,
            ku_service=deps.ku_service, ...
        )

        self.query_processor = QueryProcessor(
            intent_classifier=self.intent_classifier,
            response_generator=self.response_generator,
            ls_context_loader=self.ls_context_loader,
            socratic_engine=self.socratic_engine,
            zpd_service=deps.zpd_service,
            conversation_context=self.conversation_context,
            ...
        )

        # Required: 13-domain synthesis capability
        self.intelligence_factory = deps.intelligence_factory

    # All methods delegate to sub-services
    async def ask_socratic(self, user_uid, question, session_id=None):
        return await self.query_processor.process_socratic_turn(user_uid, question, session_id)
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
├── QueryProcessor (orchestration — legacy RAG + Socratic pipeline)
│   ├── answer_user_question()        ← legacy RAG pipeline
│   ├── process_socratic_turn()       ← LS-scoped Socratic pipeline (March 2026)
│   └── process_query_with_context()
├── IntentClassifier (January 2026 - extracted from QueryProcessor)
│   ├── classify_intent()             ← embeddings-based (legacy)
│   └── classify_pedagogical_intent() ← deterministic decision tree (Socratic)
├── ResponseGenerator (January 2026 - extracted from QueryProcessor)
│   ├── build_llm_context()
│   ├── generate_actions()
│   └── generate_suggested_actions()
├── EntityExtractor
│   ├── extract_entities_from_query() ← global (legacy)
│   └── extract_from_bundle()         ← LS-scoped (Socratic)
├── ContextRetriever (legacy pipeline)
│   ├── get_learning_context()
│   └── analyze_knowledge_gaps()
├── LSContextLoader (Socratic pipeline — March 2026)
│   └── load_bundle()                 ← loads LSBundle from UserContext
└── SocraticEngine (Socratic pipeline — March 2026, pure logic, no I/O)
    └── generate_move()               ← produces SocraticMove for LLM
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
# /services_bootstrap.py (PHASE 4)
from core.services.askesis_factory import create_askesis_service

if tier.ai_enabled:
    # First: Create factory with all 13 domain services
    context_intelligence_factory = UserContextIntelligenceFactory(
        tasks=activity_services["tasks"].relationships,
        goals=activity_services["goals"].relationships,
        # ... all 13 domains
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

In CORE tier, `services.askesis` is `None` and Askesis API routes return 404 via `ai_guard.py`.

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
└────────┬────────┘  │      Engine        │  │  (Legacy RAG + Socratic)     │
         │           └──────────┬─────────┘  └───────────┬───────────────────┘
         │                      │                        │
         └──────────┬───────────┘          ┌─────────────┼──────────────────────┐
                    │                      │             │                      │
           ┌────────▼────────┐   ┌─────────▼───┐ ┌──────▼──────┐ ┌────────────▼──────┐
           │ state_scoring.py│   │IntentClassi-│ │LSContext-   │ │SocraticEngine     │
           │ (pure functions)│   │    fier     │ │   Loader    │ │(pure logic)       │
           └─────────────────┘   └─────────────┘ └──────┬──────┘ └───────────────────┘
                                       │                │
                                       ▼                ▼
                                EmbeddingsService  Domain Services
                                                   (Article, KU, LP,
                                                    Habits, Tasks, etc.)
                                       │
                              ┌────────▼────────┐
                              │ContextRetriever │ (legacy pipeline)
                              └────────┬────────┘
                                       ▼
                               GraphIntelligence    ZPDService
                                   Service          (Socratic pipeline)
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
| `/core/services/askesis/query_processor.py` | RAG pipeline orchestration (legacy + Socratic) |
| `/core/services/askesis/intent_classifier.py` | Intent classification: embeddings (legacy) + decision tree (Socratic) |
| `/core/services/askesis/response_generator.py` | Action and context generation (legacy pipeline) |
| `/core/services/askesis/entity_extractor.py` | Entity extraction: global (legacy) + bundle-scoped (Socratic) |
| `/core/services/askesis/context_retriever.py` | Context retrieval (legacy pipeline) |
| `/core/services/askesis/ls_context_loader.py` | LS bundle loading (Socratic pipeline, March 2026) |
| `/core/services/askesis/socratic_engine.py` | Pedagogical move generation (Socratic pipeline, March 2026) |
| `/core/services/askesis/evaluation_engine.py` | Structured evaluation skeleton (Socratic pipeline) |
| `/core/services/askesis/askesis_core_service.py` | CRUD + `build_user_context()` (owns Neo4j driver) |
| `/core/services/askesis/types.py` | Shared data classes |
| `/core/ports/askesis_protocols.py` | Protocol definitions |
| `/adapters/inbound/askesis_routes.py` | Route wiring (DomainRouteConfig) |
| `/adapters/inbound/askesis_api.py` | JSON API endpoints |
| `/adapters/inbound/askesis_ui.py` | UI components |

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
    """Complete Askesis intelligence operations (16 methods)."""
    pass
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
    entity_uid: str     # Specific entity
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

### API Routes (`/adapters/inbound/askesis_api.py`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/askesis/analyze` | POST | Full state analysis |
| `/api/askesis/next-action` | GET | Single best action |
| `/api/askesis/daily-plan` | GET | Daily work plan |
| `/api/askesis/ask` | POST | Natural language Q&A |
| `/api/askesis/synergies` | GET | Cross-domain synergies |

### UI Routes (`/adapters/inbound/askesis_ui.py`)

| Route | Purpose |
|-------|---------|
| `/askesis` | Main dashboard |
| `/askesis/plan` | Daily plan view |
| `/askesis/chat` | Conversational interface |

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

**All Askesis intelligence routes use `get_rich_unified_context()` via `_load_askesis_and_context()`.** The 5-minute cache on this method means no performance regression vs. standard depth.

```python
# CORRECT — used in _load_askesis_and_context()
context_result = await user_service.get_rich_unified_context(askesis.user_uid)

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
| **February 2026** | Reports → Submissions + Feedback rename; Processing Domains now: Submissions, Journals, Feedback |
| **March 2026** | `_load_askesis_and_context` closure extracted inside `create_askesis_api_routes` — 11 identical 15-line blocks replaced with a single helper; returns `(askesis, user_uid, user_context)` 3-tuple (1302 → 1135 lines) |
| **March 2026** | `entities_rich` unification: `active_task_rich`, `active_goal_rich`, etc. → single `entities_rich` dict; `activity_rich` removed |
| **March 2026** | `ActivityDataReader` absorbed into `UserContext.build_rich()` — no longer a separate service |
| **March 2026** | `ActivityReviewService` split into `ActivityReportService` + `ReviewQueueService` |
| **March 2026** | EntityType renames: `AI_FEEDBACK → ACTIVITY_REPORT`, `FEEDBACK_REPORT → SUBMISSION_FEEDBACK` |
| **March 2026** | All intelligence routes switched to `get_rich_unified_context()` — ensures `entities_rich` is populated |
| **March 2026** | `AskesisDeps` typed dataclass replaces positional kwargs; `create_askesis_service()` factory in `askesis_factory.py` handles bootstrap construction |
| **March 2026** | `JournalInsight` frozen dataclass added — ZPD signal extraction point from processed journals (Phase 2 stub) |
| **March 2026** | 4 pedagogical prompt templates added: `askesis_scaffold_entry`, `askesis_socratic_turn`, `askesis_ku_bridge`, `askesis_journal_reflection` |
| **March 2026** | Backwards compatibility removed: all `AskesisDeps` fields required (except `citation_service`, `zpd_service`), keyword fallback deleted from IntentClassifier, template fallback deleted from QueryProcessor, Askesis creation gated behind `INTELLIGENCE_TIER=full` |
| **March 2026** | Socratic pipeline: LSContextLoader, SocraticEngine, ConversationContext wired into QueryProcessor. `ask_socratic()` facade method added. AskesisDeps extended with `ku_service`, `lp_service`, `principles_service`. See: `ASKESIS_SOCRATIC_ARCHITECTURE.md` |

---

## Implementation Status (March 2026)

### Completed Implementations

Six stub implementations were completed to bring Askesis from ~60-70% to ~95% functionality:

| Method | File | Implementation |
|--------|------|----------------|
| `_find_similar_knowledge()` | `context_retriever.py` | Semantic search via EmbeddingsService |
| `_build_user_learning_context_query()` | `context_retriever.py` | Comprehensive Cypher with 5 OPTIONAL MATCH clauses |
| `_analyze_blocked_knowledge_prerequisites()` | `context_retriever.py` | Gap analysis using Neo4j relationship traversal |
| `_identify_quick_wins_and_high_impact()` | `context_retriever.py` | Classification based on prerequisite count |
| `_generate_context_aware_response()` | `query_processor.py` | LLM integration (required) |
| `_order_by_prerequisites()` | `askesis_service.py` | Kahn's algorithm for topological sort |

### Semantic Search Implementation

`ContextRetriever._find_similar_knowledge()` now performs real semantic search:

```python
async def _find_similar_knowledge(self, query: str, _user_uid: str) -> list[tuple[str, float, str]]:
    # 1. Create query embedding via EmbeddingsService
    query_embedding = await self.embeddings_service.create_embedding(query)

    # 2. Fetch KUs with embeddings from Neo4j
    ku_query = """
    MATCH (ku:Curriculum) WHERE ku.embedding IS NOT NULL
    RETURN ku.uid, ku.title, ku.embedding LIMIT 100
    """

    # 3. Find similar via cosine similarity (threshold 0.6, top_k=5)
    similar = self.embeddings_service.find_similar(
        query_embedding=query_embedding,
        embeddings=embeddings_list,
        threshold=0.6, top_k=5
    )
    return [(uid, score, title) for uid, score in similar]
```

### LLM Integration

`QueryProcessor._generate_context_aware_response()` uses LLMService directly — no fallback:

```python
async def _generate_context_aware_response(...) -> str:
    # Build context for LLM
    context = self._build_llm_context(current_knowledge, active_learning, ...)
    response = await self.llm_service.generate_context_aware_answer(
        query=query_message, context=context, intent=intent.value
    )
    return response
```

### Prerequisite Ordering (Kahn's Algorithm)

`AskesisService._order_by_prerequisites()` implements topological sort:

```python
async def _order_by_prerequisites(self, ku_uids: list[str]) -> list[str]:
    # Query prerequisite relationships
    query = """
    UNWIND $ku_uids AS ku_uid
    MATCH (ku:Curriculum {uid: ku_uid})
    OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Curriculum)
    WHERE prereq.uid IN $ku_uids
    RETURN ku.uid AS uid, collect(prereq.uid) AS prerequisites
    """

    # Build adjacency + in-degree for Kahn's algorithm
    # Process nodes with zero in-degree first
    # Returns prerequisite-ordered list
```

---

## LLM Prompts

### Current State

Askesis's `QueryProcessor` uses `LLMService.generate_context_aware_answer()` for its
primary LLM interaction. Context is assembled programmatically in
`ResponseGenerator.build_llm_context()` — no PROMPT_REGISTRY use yet. The DSL bridge
(`LLMDSLBridgeService`) does use PROMPT_REGISTRY for domain recognition.

### Why This Will Change

Prompt engineering and service logic are currently coupled. When tuning Askesis's
responses, an implementer must read Python to find the prompt. This is the wrong layer.

As Askesis's LLM interactions stabilize, each should become a named template in
`core/prompts/templates/` with documented placeholders — editable without touching Python.

### Migration Path

Each `generate_context_aware_answer()` call maps to one template:

```python
# Current (programmatic assembly in ResponseGenerator)
context = self._build_llm_context(current_knowledge, active_learning, ...)
response = await self.llm_service.generate_context_aware_answer(
    query=query_message, context=context, intent=intent.value
)

# Target (template-driven)
from core.prompts import PROMPT_REGISTRY
prompt = PROMPT_REGISTRY.render("askesis_qa_response",
    query=query_message,
    intent=intent.value,
    knowledge_context=context["knowledge"],
    learning_context=context["learning"],
)
response = await openai_service.generate_completion(prompt=prompt)
```

### Planned Template IDs

| Template ID | Service | Placeholders |
|-------------|---------|--------------|
| `askesis_qa_response.md` | `QueryProcessor` | `{query}`, `{intent}`, `{knowledge_context}`, `{learning_context}` |
| `askesis_daily_plan.md` | `ActionRecommendationEngine` | `{user_summary}`, `{active_tasks}`, `{goals_progress}` |
| `askesis_synergy_detection.md` | `UserStateAnalyzer` | `{domain_stats}`, `{time_period}` |

### Editing Prompts Today

The existing templates live in `core/prompts/templates/`. To tune Askesis's DSL recognition:

```bash
# Edit the domain recognition prompt (used by LLMDSLBridgeService)
$EDITOR core/prompts/templates/dsl_domain_recognition.md
```

For Q&A and planning responses, edit `ResponseGenerator.build_llm_context()` and
`QueryProcessor._generate_context_aware_response()` until those migrate to templates.

**See:** `@prompt-templates` skill — complete registry reference, naming conventions, anti-patterns

---

## Related Documentation

- **Socratic Architecture:** [ASKESIS_SOCRATIC_ARCHITECTURE.md](./ASKESIS_SOCRATIC_ARCHITECTURE.md) — LS-scoped Socratic pipeline design
- **Intelligence Guide:** [ASKESIS_INTELLIGENCE.md](../intelligence/ASKESIS_INTELLIGENCE.md)
- **Search Integration:** [ASKESIS_SEARCH_ARCHITECTURE.md](../guides/ASKESIS_SEARCH_ARCHITECTURE.md)
- **UserContext Architecture:** [UNIFIED_USER_ARCHITECTURE.md](./UNIFIED_USER_ARCHITECTURE.md)
- **Prompt Registry:** `core/prompts/` — centralized LLM template store
- **ADR-021:** UserContext Intelligence Modularization
