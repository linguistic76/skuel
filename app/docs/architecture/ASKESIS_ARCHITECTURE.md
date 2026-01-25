# Askesis Architecture - Cross-Cutting Intelligence System

**Last Updated:** January 12, 2026

## Overview

Askesis is one of SKUEL's **5 Cross-Cutting Systems** providing life context synthesis and action recommendations. Unlike Activity Domain services that manage entities, Askesis synthesizes across ALL 14 domains to answer: *"What should I work on next?"*

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
Activity Domains (6)          Askesis
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

Askesis uses a **pure facade pattern** with zero business logic in the main service:

```python
class AskesisService:
    """
    Facade coordinating 7 specialized sub-services.
    Zero business logic - pure delegation.
    """

    def __init__(self, ..., intelligence_factory):
        # Sub-service creation (no circular dependencies - uses pure functions)
        self.state_analyzer = UserStateAnalyzer()
        self.recommendation_engine = ActionRecommendationEngine()
        self.entity_extractor = EntityExtractor(...)
        self.context_retriever = ContextRetriever(...)

        # January 2026: QueryProcessor decomposition
        self.intent_classifier = IntentClassifier(embeddings_service=embeddings_service)
        self.response_generator = ResponseGenerator()
        self.query_processor = QueryProcessor(
            intent_classifier=self.intent_classifier,
            response_generator=self.response_generator,
            ...
        )

        # Required: 13-domain synthesis capability
        self.intelligence_factory = intelligence_factory  # REQUIRED

    # All methods delegate to sub-services
    async def analyze_user_state(self, context, focus_areas=None):
        return await self.state_analyzer.analyze_user_state(context, focus_areas)
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
├── QueryProcessor (orchestration only, ~500 lines)
│   ├── answer_user_question()
│   └── process_query_with_context()
├── IntentClassifier (January 2026 - extracted from QueryProcessor)
│   ├── classify_intent()
│   └── classify_via_keywords() (fallback)
├── ResponseGenerator (January 2026 - extracted from QueryProcessor)
│   ├── build_llm_context()
│   ├── generate_actions()
│   └── generate_suggested_actions()
├── EntityExtractor
│   └── extract_entities_from_query()
└── ContextRetriever
    ├── get_learning_context()
    └── analyze_knowledge_gaps()
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
| **Inheritance** | `FacadeDelegationMixin` | `FacadeDelegationMixin` (January 2026) |
| **Sub-services** | 7 (core, search, intelligence, etc.) | 7 (state, recommendation, query, intent, response, etc.) |
| **Entity CRUD** | Yes (BaseService) | No (cross-domain only) |
| **Backend** | `UniversalNeo4jBackend[T]` | None (uses domain services) |
| **Protocol** | `{Domain}Operations` | `AskesisOperations` |
| **Factory** | `create_common_sub_services()` | Manual creation |

### Why Different?

Askesis is fundamentally different:
1. **No entities** - Doesn't manage Askesis entities in Neo4j
2. **Cross-domain** - Synthesizes ALL 14 domains
3. **Intelligence-focused** - Recommendations, not CRUD
4. **Factory-dependent** - Requires UserContextIntelligenceFactory

---

## Bootstrap Integration

### Creation Location

Askesis is created in `compose_services()` AFTER the intelligence factory:

```python
# /core/utils/services_bootstrap.py (PHASE 4)

# First: Create factory with all 13 domain services
context_intelligence_factory = UserContextIntelligenceFactory(
    tasks=activity_services["tasks"].relationships,
    goals=activity_services["goals"].relationships,
    # ... all 13 domains
)

# Then: Create Askesis with factory as REQUIRED parameter
askesis_service = AskesisService(
    graph_intelligence_service=learning_services["graph_intelligence"],
    user_service=user_service,
    llm_service=learning_services["llm_service"],
    embeddings_service=learning_services["embeddings_service"],
    knowledge_service=learning_services["ku_service"],
    tasks_service=activity_services["tasks"],
    goals_service=activity_services["goals"],
    habits_service=activity_services["habits"],
    events_service=activity_services["events"],
    intelligence_factory=context_intelligence_factory,  # REQUIRED
)
services.askesis = askesis_service
```

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
└────────┬────────┘  │      Engine        │  │      (Orchestration)         │
         │           └──────────┬─────────┘  └───────────┬───────────────────┘
         │                      │                        │
         └──────────┬───────────┘             ┌──────────┼──────────┐
                    │                         │          │          │
           ┌────────▼────────┐      ┌─────────▼───┐ ┌────▼────┐ ┌───▼────────┐
           │ state_scoring.py│      │IntentClassi-│ │Response-│ │Entity-     │
           │ (pure functions)│      │    fier     │ │Generator│ │Extractor   │
           └─────────────────┘      └─────────────┘ └─────────┘ └────────────┘
                                          │               │            │
                                          ▼               │            ▼
                                   EmbeddingsService      │     Domain Services
                                                          │
                                                   ┌──────▼──────────┐
                                                   │ ContextRetriever│
                                                   └─────────────────┘
                                                          │
                                                          ▼
                                                  GraphIntelligence
                                                      Service
```

---

## Key Files

| File | Purpose |
|------|---------|
| `/core/services/askesis_service.py` | Main facade (~1,050 lines) |
| `/core/services/askesis/user_state_analyzer.py` | State assessment |
| `/core/services/askesis/action_recommendation_engine.py` | Recommendations |
| `/core/services/askesis/state_scoring.py` | Pure functions for state scoring (January 2026) |
| `/core/services/askesis/query_processor.py` | RAG pipeline orchestration (~500 lines) |
| `/core/services/askesis/intent_classifier.py` | Embeddings-based intent classification (January 2026) |
| `/core/services/askesis/response_generator.py` | Action and context generation (January 2026) |
| `/core/services/askesis/entity_extractor.py` | Entity extraction |
| `/core/services/askesis/context_retriever.py` | Context retrieval |
| `/core/services/askesis/types.py` | Shared data classes |
| `/core/services/protocols/askesis_protocols.py` | Protocol definitions |
| `/adapters/inbound/askesis_routes.py` | Route factory |
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
from core.services.protocols import AskesisOperations

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

---

## Implementation Status (January 2026)

### Completed Implementations

Six stub implementations were completed to bring Askesis from ~60-70% to ~95% functionality:

| Method | File | Implementation |
|--------|------|----------------|
| `_find_similar_knowledge()` | `context_retriever.py` | Semantic search via EmbeddingsService |
| `_build_user_learning_context_query()` | `context_retriever.py` | Comprehensive Cypher with 5 OPTIONAL MATCH clauses |
| `_analyze_blocked_knowledge_prerequisites()` | `context_retriever.py` | Gap analysis using Neo4j relationship traversal |
| `_identify_quick_wins_and_high_impact()` | `context_retriever.py` | Classification based on prerequisite count |
| `_generate_context_aware_response()` | `query_processor.py` | LLM integration with template fallback |
| `_order_by_prerequisites()` | `askesis_service.py` | Kahn's algorithm for topological sort |

### Semantic Search Implementation

`ContextRetriever._find_similar_knowledge()` now performs real semantic search:

```python
async def _find_similar_knowledge(self, query: str, _user_uid: str) -> list[tuple[str, float, str]]:
    # 1. Create query embedding via EmbeddingsService
    query_embedding = await self.embeddings_service.create_embedding(query)

    # 2. Fetch KUs with embeddings from Neo4j
    ku_query = """
    MATCH (ku:Ku) WHERE ku.embedding IS NOT NULL
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

`QueryProcessor._generate_context_aware_response()` now uses LLMService:

```python
async def _generate_context_aware_response(...) -> str:
    if self.llm_service:
        try:
            # Build context for LLM
            context = self._build_llm_context(current_knowledge, active_learning, ...)
            response = await self.llm_service.generate_context_aware_answer(
                query=query_message, context=context, intent=intent.value
            )
            return response
        except Exception as e:
            logger.warning("LLM failed, using template: %s", e)

    # Template fallback for graceful degradation
    return self._build_template_response(...)
```

### Prerequisite Ordering (Kahn's Algorithm)

`AskesisService._order_by_prerequisites()` implements topological sort:

```python
async def _order_by_prerequisites(self, ku_uids: list[str]) -> list[str]:
    # Query prerequisite relationships
    query = """
    UNWIND $ku_uids AS ku_uid
    MATCH (ku:Ku {uid: ku_uid})
    OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Ku)
    WHERE prereq.uid IN $ku_uids
    RETURN ku.uid AS uid, collect(prereq.uid) AS prerequisites
    """

    # Build adjacency + in-degree for Kahn's algorithm
    # Process nodes with zero in-degree first
    # Returns prerequisite-ordered list
```

---

## Related Documentation

- **Intelligence Guide:** [ASKESIS_INTELLIGENCE.md](../intelligence/ASKESIS_INTELLIGENCE.md)
- **Search Integration:** [ASKESIS_SEARCH_ARCHITECTURE.md](../guides/ASKESIS_SEARCH_ARCHITECTURE.md)
- **UserContext Architecture:** [UNIFIED_USER_ARCHITECTURE.md](./UNIFIED_USER_ARCHITECTURE.md)
- **ADR-021:** UserContext Intelligence Modularization
