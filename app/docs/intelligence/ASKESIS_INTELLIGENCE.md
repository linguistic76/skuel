# Askesis Intelligence - Cross-Cutting Life Context Synthesis

**Last Updated:** March 4, 2026

## Overview

Askesis is SKUEL's **cross-cutting intelligence system** that synthesizes all entity types to answer the fundamental question: *"What should I work on next?"*

Unlike domain intelligence services that focus on a single domain, Askesis orchestrates across ALL domains to provide holistic life context intelligence.

**Key Distinction:**
- **Domain Intelligence** (Tasks, Goals, etc.): Single-domain analysis and recommendations
- **UserContextIntelligence**: Cross-domain state aggregation (~240 fields)
- **Askesis**: Cross-domain SYNTHESIS - actively recommends based on priorities, patterns, and life path alignment

---

## Architecture

### Facade Pattern with 7 Sub-Services (January 2026)

```
AskesisService (Facade - Zero Business Logic)
        ↓
┌────────────────────────────────────────────────────────────────────┐
│ UserStateAnalyzer          │ State assessment, pattern detection   │
│ ActionRecommendationEngine │ Prioritized recommendations           │
│ QueryProcessor             │ RAG pipeline orchestration (~500 lines)│
│ IntentClassifier           │ Embeddings-based intent classification │
│ ResponseGenerator          │ Action and context generation          │
│ EntityExtractor            │ Entity extraction from queries         │
│ ContextRetriever           │ Domain context retrieval               │
└────────────────────────────────────────────────────────────────────┘
        ↓              ↑
        │    state_scoring.py (pure functions)
        ↓
UserContextIntelligenceFactory (13-Domain Synthesis)
```

**Files:**
- Facade: `/core/services/askesis_service.py` (~1,050 lines)
- Sub-services: `/core/services/askesis/` (9 files)
- Pure functions: `/core/services/askesis/state_scoring.py`
- Protocol: `/core/ports/askesis_protocols.py`

### Key Difference from Domain Intelligence

| Aspect | Domain Intelligence | Askesis |
|--------|---------------------|---------|
| **Scope** | Single domain (Tasks, Goals, etc.) | all entity types |
| **Inheritance** | `BaseAnalyticsService[T]` | Custom facade pattern |
| **Entity Focus** | Domain-specific entities | User's complete life context |
| **Primary Question** | "What's happening in this domain?" | "What should I work on next?" |

---

## Core Methods (16 Total)

### State Analysis (3 methods)

| Method | Description |
|--------|-------------|
| `analyze_user_state(context, focus_areas)` | Comprehensive analysis across all domains |
| `identify_patterns(context)` | Detect behavioral and productivity patterns |
| `calculate_system_health(context)` | Health metrics per domain (0.0-1.0) |

### Recommendations (3 methods)

| Method | Description |
|--------|-------------|
| `get_next_best_action(context)` | THE single best action to take now |
| `optimize_workflow(context)` | Workflow improvement suggestions |
| `predict_future_state(context, days)` | State trajectory projection |

### Query Processing (2 methods)

| Method | Description |
|--------|-------------|
| `answer_user_question(user_uid, question)` | RAG-based natural language Q&A |
| `process_query_with_context(user_uid, query, depth)` | Context-enriched query processing |

### 13-Domain Synthesis (8 methods)

| Method | Description |
|--------|-------------|
| `get_daily_work_plan(context)` | **THE FLAGSHIP** - optimal daily plan |
| `get_optimal_next_learning_steps(context)` | Prerequisite-aware learning sequence |
| `get_learning_path_critical_path(context)` | Fastest route to life path |
| `get_knowledge_application_opportunities(context, ku_uid)` | Where to apply knowledge |
| `get_unblocking_priority_order(context)` | Learning order by unlock impact |
| `get_cross_domain_synergies(context)` | Detect multi-domain synergies |
| `calculate_life_path_alignment(context)` | 5-dimension alignment scoring |
| `get_schedule_aware_recommendations(context)` | Time-appropriate recommendations |

---

## Priority Hierarchy

When generating recommendations, Askesis follows this priority order:

1. **At-Risk Habits** (Critical) - Prevent streak loss
2. **Unblocking** (High) - Clear blockers for stuck items
3. **Goal Advancement** (Medium) - Progress toward milestones
4. **Foundation Building** (Normal) - Knowledge acquisition
5. **Life Path Alignment** (Background) - Long-term direction

---

## Dependencies

### Required at Construction (January 2026)

| Dependency | Purpose |
|------------|---------|
| `intelligence_factory` | **REQUIRED** - 13-domain synthesis |
| `graph_intelligence_service` | Graph traversal queries |
| `user_service` | UserContext access |
| `llm_service` | Natural language generation |
| `embeddings_service` | Semantic search |
| `knowledge_service` | KU entity extraction |
| `tasks_service` | Task entity extraction |
| `goals_service` | Goal entity extraction |
| `habits_service` | Habit entity extraction |
| `events_service` | Event entity extraction |

### Optional

| Dependency | Purpose |
|------------|---------|
| `citation_service` | Evidence transparency (Phase 4C) |

**Note (January 2026):** `learning_orchestrator` and `cascade_manager` were removed per One Path Forward philosophy - unused dependencies eliminated.

---

## Usage Examples

### Get Daily Work Plan

```python
from core.services.askesis_service import AskesisService

# Via services container — MUST use get_rich_unified_context() for full intelligence
askesis = services.askesis
context = await user_service.get_rich_unified_context(user_uid)

# Get THE optimal daily plan
result = await askesis.get_daily_work_plan(
    user_context=context,
    prioritize_life_path=True,
    respect_capacity=True,
)

if result.is_ok:
    plan = result.value
    for item in plan.items:
        print(f"{item.priority}: {item.entity_type} - {item.title}")
```

**Important:** Use `get_rich_unified_context()`, not `get_user_context()`. Standard depth leaves `entities_rich` empty, causing silent degradation of habit momentum, pattern detection, and scheduling signals. The rich context has a 5-minute cache, so there is no performance cost.

### Natural Language Query

```python
# Ask a question about user's state
result = await askesis.answer_user_question(
    user_uid="user.mike",
    question="What tasks should I focus on today?"
)

if result.is_ok:
    answer = result.value
    print(f"Answer: {answer['response']}")
    print(f"Entities: {answer['entities']}")
```

### Cross-Domain Synergies

```python
# Find synergies across domains
result = await askesis.get_cross_domain_synergies(
    user_context=context,
    min_synergy_score=0.5,
)

if result.is_ok:
    for synergy in result.value:
        print(f"{synergy.source_domain} → {synergy.target_domain}")
        print(f"  Score: {synergy.score}, Type: {synergy.synergy_type}")
```

---

## Sub-Service Details

### UserStateAnalyzer

**Purpose:** Assess current user state across all domains

**Key Methods:**
- `analyze_user_state()` - Comprehensive state analysis
- `identify_patterns()` - Behavioral pattern detection
- `calculate_system_health()` - Per-domain health metrics

**January 2026:** Uses pure functions from `state_scoring.py` (no circular dependency)

### ActionRecommendationEngine

**Purpose:** Generate prioritized action recommendations

**Key Methods:**
- `get_next_best_action()` - Single best action
- `generate_recommendations()` - Multiple recommendations
- `optimize_workflow()` - Workflow suggestions
- `predict_future_state()` - State trajectory

**Priority Algorithm:** At-risk habits > Unblocking > Goal advancement > Foundation

**January 2026:** Uses pure functions from `state_scoring.py` (no circular dependency)

### State Scoring Functions (January 2026)

**Purpose:** Pure functions shared by UserStateAnalyzer and ActionRecommendationEngine

**File:** `/core/services/askesis/state_scoring.py`

**Functions:**
- `score_current_state(user_context)` - Score state quality (0.0-1.0)
- `find_key_blocker(user_context)` - Find most impactful prerequisite blocker
- `calculate_momentum(user_context)` - Overall momentum score (0.0-1.0)
- `calculate_domain_balance(user_context)` - Balance across domains

**Design:** Eliminates circular dependency between UserStateAnalyzer and ActionRecommendationEngine

### QueryProcessor (January 2026 - Refactored with LLM Integration)

**Purpose:** RAG pipeline orchestration (reduced from 962 to ~500 lines)

**Key Methods:**
- `answer_user_question()` - Full RAG with entity extraction
- `process_query_with_context()` - Context-enriched processing

**Internal Methods (January 2026 - Implemented):**
- `_generate_context_aware_response()` - LLM integration with graceful fallback:
  1. Builds context from current knowledge, active learning, tasks, goals
  2. Calls `llm_service.generate_context_aware_answer()` with intent
  3. Falls back to template-based response if LLM unavailable

**January 2026 Decomposition:** Intent classification and response generation extracted to separate services.

**Pipeline:** IntentClassifier → EntityExtractor → ContextRetriever → ResponseGenerator → LLM (with fallback)

**March 2026:** Uses `get_rich_unified_context()` for full `entities_rich` population.

### IntentClassifier (January 2026 - New)

**Purpose:** Embeddings-based semantic intent classification

**Key Methods:**
- `classify_intent()` - Primary classification via embeddings
- `classify_via_keywords()` - Keyword-based fallback

**Strategy:**
1. Create query embedding
2. Compare to INTENT_EXEMPLARS (pre-computed exemplar embeddings)
3. Return intent with highest similarity (≥0.65 threshold)
4. Fall back to keyword matching if low confidence

**Intent Types:** HIERARCHICAL, PREREQUISITE, PRACTICE, EXPLORATORY, RELATIONSHIP, AGGREGATION, SPECIFIC

### ResponseGenerator (January 2026 - New)

**Purpose:** Generate actions and LLM-friendly context

**Key Methods:**
- `build_llm_context()` - Convert UserContext to natural language for LLM
- `generate_actions()` - Generate suggested actions from user context
- `generate_suggested_actions()` - Generate actions from query context

**Context Selection:** Intelligently selects relevant UserContext fields based on query keywords

### EntityExtractor

**Purpose:** Extract entities from natural language

**Key Methods:**
- `extract_entities_from_query()` - Multi-domain extraction
- `_extract_knowledge_entities()` - KU extraction
- `_extract_task_entities()` - Task extraction
- `_fuzzy_match()` - Flexible entity matching

**Strategies:** Exact match, partial word match, acronym match

### ContextRetriever (January 2026 - Fully Implemented)

**Purpose:** Retrieve domain-specific context for queries with semantic search

**Key Methods:**
- `get_learning_context()` - Learning-focused context
- `analyze_knowledge_gaps()` - Gap identification with prerequisite analysis
- `retrieve_relevant_context()` - Multi-domain context

**Internal Methods (January 2026 - Implemented):**
- `_find_similar_knowledge()` - Semantic search via EmbeddingsService (cosine similarity ≥0.6)
- `_build_user_learning_context_query()` - Comprehensive Cypher with 5 OPTIONAL MATCH clauses
- `_analyze_blocked_knowledge_prerequisites()` - Gap analysis identifying missing prerequisites
- `_identify_quick_wins_and_high_impact()` - Classification by prerequisite count:
  - **Quick wins**: 0-1 prerequisites (easy to start)
  - **High impact**: Many dependents (unblocks the most)

**Graph Integration:** Uses GraphIntelligenceService for semantic analysis and EmbeddingsService for vector similarity

---

## entities_rich — Required for Full Intelligence (March 2026)

`entities_rich` is a `dict[str, list[dict[str, Any]]]` on `UserContext`, populated only when using `build_rich()` / `get_rich_unified_context()`. Keys: `"tasks"`, `"goals"`, `"habits"`, `"events"`, `"choices"`, `"principles"`.

Intelligence mixins that depend on `entities_rich`:
- `TemporalMomentumMixin` — habit streak tracking, at-risk detection
- `DomainBalanceMixin` — cross-domain activity ratios
- `PatternDetectionMixin` — recurrence + momentum signals

If `entities_rich` is empty, these mixins return empty signals and the daily plan degrades silently. Always use `get_rich_unified_context()` for Askesis routes — standard `get_user_context()` is for ownership checks and lightweight queries only.

---

## Domain Naming (March 2026)

The 13 domains used in Askesis intelligence:

- **Activity (5):** Tasks, Goals, Habits, Choices, Principles
- **Scheduling Domain (1):** Events (cross-cutting; serves Activity Domains)
- **Curriculum (3):** KU, LS, LP
- **Processing (3):** Submissions, Journals, Feedback
- **Temporal Domain (1):** Calendar

> Pre-February 2026: "Processing Domains" were called "Assignments, Journals, Reports". These were renamed in the Reports → Submissions + Feedback migration (February 2026) and the EntityType rename (`AI_FEEDBACK → ACTIVITY_REPORT`, `FEEDBACK_REPORT → SUBMISSION_FEEDBACK`) in March 2026.

---

## Feedback Services (March 2026)

The former `ActivityReviewService` was split into two focused services:

| Service | Protocol | `services.` attr | Responsibility |
|---------|----------|-----------------|----------------|
| `ActivityReportService` | `ActivityReportOperations` | `activity_report` | Processor-neutral CRUD: `create_snapshot`, `submit_feedback`, `persist`, `get_history`, `annotate`, `get_annotation` |
| `ReviewQueueService` | `ReviewQueueOperations` | `review_queue` | `ReviewRequest` node management: `request_review`, `get_pending_reviews` |

---

## Protocol Interface

```python
from core.ports import AskesisOperations

# Type-safe dependency
def process_user(askesis: AskesisOperations) -> Result[...]:
    return await askesis.get_daily_work_plan(context)
```

**Sub-protocols (ISP):**
- `AskesisStateAnalysisOperations` (3 methods)
- `AskesisRecommendationOperations` (3 methods)
- `AskesisQueryOperations` (2 methods)
- `AskesisDomainSynthesisOperations` (8 methods)

---

## Relationship to UserContextIntelligence

| Aspect | UserContextIntelligence | Askesis |
|--------|------------------------|---------|
| **Architecture** | Modular mixin package | Facade with sub-services |
| **Core Question** | "What is my current state?" | "What should I do next?" |
| **Methods** | 8 core methods | 16 methods |
| **Factory Pattern** | Creates instances per-request | Uses factory for synthesis |
| **Statefulness** | Stateless analysis | Maintains session context |

**Integration:** Askesis uses `UserContextIntelligenceFactory` to access UserContextIntelligence methods for 13-domain synthesis.

---

## Testing

```bash
# Unit tests
poetry run pytest tests/unit/services/test_askesis_service.py -v

# Integration tests
poetry run pytest tests/integration/askesis/ -v

# Protocol compliance
poetry run python -c "
from core.ports import AskesisOperations
from core.services.askesis_service import AskesisService
print('Protocol defined correctly')
"
```

---

## Facade-Level Intelligence (January 2026)

### Prerequisite Ordering

`AskesisService._order_by_prerequisites()` implements **Kahn's algorithm** for topological sort:

**Purpose:** Order KU UIDs so prerequisites come before dependents

**Algorithm:**
1. Query REQUIRES_KNOWLEDGE relationships from Neo4j
2. Build adjacency list and in-degree map
3. Start with nodes having zero in-degree (no prerequisites)
4. Process queue, decrementing in-degrees as nodes complete
5. Return ordered list (or original if cycle detected)

**Use Cases:**
- `get_optimal_learning_sequence()` - Orders learning recommendations
- `get_unblocking_priority_order()` - Orders by unlock impact
- Any method needing prerequisite-aware sequencing

---

## Implementation Completeness

### Functionality Status (March 2026)

| Component | Status | Notes |
|-----------|--------|-------|
| **IntentClassifier** | 100% | 7 intent types, 48 exemplars |
| **EntityExtractor** | 100% | Multi-domain extraction |
| **ContextRetriever** | ~95% | Semantic search, gap analysis implemented |
| **QueryProcessor** | ~95% | LLM integration with fallback; uses `get_rich_unified_context()` |
| **ResponseGenerator** | 100% | Action generation, context building |
| **UserStateAnalyzer** | 100% | State scoring via pure functions |
| **ActionRecommendationEngine** | 100% | Priority-based recommendations |
| **Facade (AskesisService)** | ~95% | Prerequisite ordering implemented |

**Overall:** ~95% functional

**Remaining Work:**
- Citation service integration (Phase 4C - planned)
- Advanced cross-domain synergy detection enhancements

---

## Related Documentation

- **Architecture:** [ASKESIS_ARCHITECTURE.md](../architecture/ASKESIS_ARCHITECTURE.md)
- **Search Integration:** [ASKESIS_SEARCH_ARCHITECTURE.md](../guides/ASKESIS_SEARCH_ARCHITECTURE.md)
- **Protocol Definition:** `/core/ports/askesis_protocols.py`
- **ADR-021:** UserContext Intelligence Modularization
- **ADR-029:** GraphNative Service Removal
