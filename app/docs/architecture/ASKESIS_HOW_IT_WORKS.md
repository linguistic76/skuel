# How Askesis Works

**Last Updated:** March 12, 2026

**Audience:** Anyone trying to understand what Askesis is, how its parts connect, and why it works the way it does. No code required — this is the plain-English explanation.

**Related docs:**
- `ASKESIS_ARCHITECTURE.md` — service structure, dependencies, evolution history
- `ASKESIS_PEDAGOGICAL_ARCHITECTURE.md` — ZPD theory, GuidanceMode design, journal signals
- `ASKESIS_SOCRATIC_ARCHITECTURE.md` — guided pipeline technical spec
- `ASKESIS_RAG_PIPELINE.md` — content → embedding → retrieval developer guide

---

## What Askesis Is

Askesis is SKUEL's **pedagogical companion**. It sits across all 21 entity types and answers two fundamental questions:

1. **"What should I work on next?"** — by synthesizing tasks, goals, habits, events, choices, principles, learning paths, and life path alignment into a single recommendation.
2. **"Help me understand this concept"** — by having a Socratic conversation grounded in the user's curriculum and Zone of Proximal Development.

Askesis is NOT a search engine, NOT a recommendation feed, and NOT a tutor that delivers answers. It asks questions that help the user discover understanding themselves.

---

## The Two Halves

Askesis has two distinct operational modes. Both require `INTELLIGENCE_TIER=full` and a real LLM + embeddings service.

### Half 1: Intelligence Synthesis

Eight methods that read the user's complete state (~250 fields from `UserContext.build_rich()`) and compute cross-domain recommendations. These don't have conversations — they return structured data.

| Method | Question It Answers |
|--------|-------------------|
| `get_daily_work_plan()` | "What should I focus on TODAY?" |
| `get_optimal_next_learning_steps()` | "What should I learn next, considering prerequisites?" |
| `get_learning_path_critical_path()` | "What's the fastest route to my life path?" |
| `get_knowledge_application_opportunities()` | "Where can I apply what I've learned?" |
| `get_unblocking_priority_order()` | "Which knowledge unlocks the most downstream items?" |
| `get_cross_domain_synergies()` | "What habits support my goals? What tasks reinforce my learning?" |
| `calculate_life_path_alignment()` | "How aligned am I with my life direction?" (5 dimensions, 0.0-1.0) |
| `get_schedule_aware_recommendations()` | "What's the right action RIGHT NOW given my energy and schedule?" |

These are delegated to `UserContextIntelligence`, which is built by `UserContextIntelligenceFactory` using all 13 domain services. The daily work plan is the flagship — it's the method that synthesizes everything.

### Half 2: The Guided RAG Pipeline

This is the conversational Askesis — the `/api/askesis/ask` endpoint. A user types a question and gets a response shaped by their curriculum position and engagement history.

---

## The Pipeline: Step by Step

When a user asks Askesis a question, here's exactly what happens:

### Step 1: Load User Context

`UserService.get_rich_unified_context(user_uid)` runs the MEGA-QUERY against Neo4j and builds a `UserContext` with ~250 fields: active entities, mastery levels, streaks, progress, enrolled paths, ZPD assessment, and temporal data.

### Step 2: LP Enrollment Gate

**No Learning Path = no Askesis.** If `user_context.enrolled_path_uids` is empty, the pipeline returns immediately with a message directing the user to enroll. This is intentional — Askesis is curriculum-anchored, not a general chatbot.

### Step 3: Classify Query Intent

`IntentClassifier.classify_intent(question)` uses **embeddings-based semantic similarity**. The user's question is embedded and compared against pre-computed exemplars for 6 intent types:

| Intent | Example Question |
|--------|-----------------|
| HIERARCHICAL | "What should I learn next?" |
| PREREQUISITE | "What do I need before async?" |
| PRACTICE | "How do I apply this?" |
| EXPLORATORY | "What's available to learn?" |
| RELATIONSHIP | "How are these topics connected?" |
| AGGREGATION | "How many tasks do I have?" |

This classification determines which context sections get included in the LLM prompt and which suggested actions get generated.

**Error tolerance:** If the embeddings API is unavailable or exemplar loading fails, the classifier defaults to `SPECIFIC` intent rather than crashing the pipeline. Individual exemplar embedding failures are skipped — classification works with fewer exemplars (lower precision, not a crash).

### Step 4: Extract Entities

`EntityExtractor.extract_entities_from_query(question, user_context)` uses fuzzy matching to find which specific entities (tasks, goals, habits, knowledge units, events) the user is referring to. For example, "How's my REST API goal going?" matches a goal titled "Build REST API."

**Error tolerance:** If entity extraction fails (e.g., a domain service is unavailable), the pipeline continues with empty matches rather than crashing. The LLM can still answer the question using context from other pipeline stages.

### Step 5: Retrieve Relevant Context

`ContextRetriever.retrieve_relevant_context()` does two things:
- **Graph-based retrieval:** prerequisite chains, blocked knowledge, active tasks/goals — driven by the classified intent
- **Semantic search enrichment:** for learning-related queries, finds semantically similar knowledge units via embedding comparison

### Step 6: Load the LS Bundle

This is where the Socratic pipeline begins. `ContextRetriever.load_ls_bundle()` loads the user's **active Learning Step** — the first non-mastered step in their enrolled Learning Path — along with everything connected to it:

```
LSBundle (frozen, loaded once per question)
├── LearningStep        — the step itself (title, intent, mastery threshold)
├── LearningPath        — the parent path
├── Lessons            — teaching compositions linked to this step
├── KUs                 — atomic knowledge units trained by this step
├── Resources           — reference material (books, talks, films) cited by Articles/KUs
├── Habits              — practice habits linked to this step
├── Tasks               — practice tasks linked to this step
├── Events              — (planned)
├── Principles          — (planned)
├── Edges               — semantic relationships between bundle entities
└── Learning Objectives — extracted from Articles
```

The bundle is the **scope window**. Every pedagogical decision operates within it. If the question falls outside the bundle, Askesis redirects gently.

**Resource integration (March 2026):** After Lessons and KUs are fetched, ContextRetriever traverses `(Lesson/Ku)-[:CITES_RESOURCE]->(Resource)` to load cited reference material. Resources appear in `curriculum_context_text` as compact summaries and are referenced in guided prompts (SCAFFOLD, REDIRECT_TO_CURRICULUM, ENCOURAGING modes). This gives Askesis access to the full intellectual context — not just the teaching narrative, but the sources it draws from. Resources are also included in semantic search (embedding similarity).

**Partial failure tolerance:** All 7 entity services (lessons, KUs, habits, tasks, events, principles, LP) are required at construction — missing services cause a clear construction-time error rather than silent empty bundles at query time. At runtime, the bundle fetches entities in parallel via `asyncio.gather(return_exceptions=True)`. If any individual fetch fails (e.g., a network timeout), that collection defaults to empty — the bundle is built from whatever succeeds. Resource fetching also degrades gracefully — a graph query failure yields an empty resource list. A minimal bundle (just the LearningStep) still enables GuidanceMode decisions like OUT_OF_SCOPE and REDIRECT_TO_CURRICULUM.

**Token truncation:** `curriculum_context_text` (concatenated Lesson content + Resource references) is truncated to `AskesisTokenBudget.MAX_CURRICULUM_CHARS` (~2500 tokens) to prevent exceeding LLM context windows when the bundle has many Lessons.

If no bundle is available (no active LS), Askesis falls back to context-aware LLM generation without the Socratic layer.

### Step 7: Determine GuidanceMode

This is the pedagogical heart. **Three sub-steps:**

**7a.** `EntityExtractor.extract_from_bundle(question, ls_bundle)` finds which KU UIDs from the bundle match the question (fuzzy matching against titles and aliases).

**7b.** `ZPDService.assess_ku_readiness(user_uid, target_ku_uids)` checks engagement evidence for those KUs. Evidence = has the user applied this KU via a task? Reinforced it via a habit? Reflected on it in a journal? Submitted work about it?

**7c.** `IntentClassifier.determine_guidance_mode()` runs a **deterministic decision tree** (no LLM, ~1ms) using the ZPD evidence:

| Evidence Strength | GuidanceMode | What Askesis Does |
|-------------------|-------------|-------------------|
| 2+ engagement signals | **SOCRATIC** | Asks the user to explain what they know. Does NOT give answers. |
| 1 signal, missing practice | **ENCOURAGING** | Acknowledges understanding, encourages practice activities. |
| 0 signals, KU in bundle | **EXPLORATORY** | Scaffolds via questions and analogies. Leads toward discovery. |
| No evidence / out of scope | **DIRECT** | Redirects to curriculum reading or acknowledges the question is outside scope. |

The decision tree always tutors to the **weakest** KU's evidence level. If the user asks about 3 KUs and has strong evidence for 2 but none for 1, the mode will be EXPLORATORY — scaffold the gap.

### Step 8: Build System Prompt

`ResponseGenerator.build_guided_system_prompt(guidance, ls_bundle, user_context)` constructs a mode-specific system prompt. Each mode has its own builder:

- **DIRECT:** "Gently redirect to the curriculum. Be encouraging, not dismissive."
- **SOCRATIC:** "Ask the learner to explain. Do NOT give answers. Test understanding."
- **EXPLORATORY:** "Guide through questions and analogies. Do NOT explain directly."
- **ENCOURAGING:** "Acknowledge understanding. Connect to practice activities."

The curriculum content from the bundle is injected as hidden context — the LLM can reference it to guide the conversation, but it's marked as "do NOT share directly."

### Step 9: Generate Answer

The LLM receives:
- **System prompt:** mode-specific pedagogical instructions
- **User message:** the question, prefixed with hidden curriculum context (if bundle exists)
- **Parameters:** temperature 0.7, max 500 tokens

Without a bundle, Askesis uses `generate_context_aware_answer()` with the full UserContext summary instead.

**Pipeline timeout:** The entire pipeline (Steps 1–10) runs under `asyncio.wait_for()` with a 30-second timeout (`AskesisPipelineTimeout.ANSWER_QUESTION_SECONDS`). If the pipeline exceeds this — due to a slow Neo4j query, unresponsive LLM, or network issue — it returns `Result.fail()` with a user-friendly message rather than hanging indefinitely. Both `answer_user_question()` and `process_query_with_context()` have independent timeouts.

### Step 9b: Format Citations

After LLM generation, `QueryProcessor._format_citations_for_askesis()` calls `AskesisCitationService.format_citations_for_askesis()` for each matched knowledge UID (up to 3). The citation service traverses `REQUIRES_KNOWLEDGE` chains up to 3 levels deep via `ProvenanceQueries.build_citation_export_query()`, returning `RelationshipCitation` objects with evidence counts. Citations are appended to the answer text.

The citation service is wired at bootstrap: `AskesisCitationService(backend=lesson_service.core.backend)` → passed through `create_askesis_service()` → `AskesisDeps.citation_service` → `QueryProcessor`. Without the service (if `citation_service` is `None`), citation formatting returns an empty string — the answer is still generated, just without source references.

### Step 10: Assemble Response

The final response includes:
- **answer:** the LLM-generated text (with citations appended when available)
- **context_used:** which entities and data informed the answer
- **suggested_actions:** next steps (at-risk habits, overdue tasks, learning path continuation)
- **confidence:** calculated from context availability, citations, and entity matches
- **guidance_mode:** which pedagogical mode was used (if guided)
- **citations:** prerequisite chain source references from `AskesisCitationService`

---

## State Analysis & Recommendations

Beyond the conversational pipeline, Askesis provides state analysis through two sub-services and a shared pure-function module.

### The Circular Dependency Problem (and How state_scoring.py Solves It)

UserStateAnalyzer needs recommendation data to produce a complete analysis. ActionRecommendationEngine needs state scores to prioritize actions. This is a textbook circular dependency — each service needs the other's output.

The solution: extract the shared math into **pure functions** in `state_scoring.py`. Both services import these functions; neither imports the other.

| Function | Input | Output | What It Computes |
|----------|-------|--------|-----------------|
| `score_current_state()` | UserContext | float (0.0-1.0) | Baseline quality from 5 binary factors: not blocked (+0.1), workload <70% (+0.1), no at-risk habits (+0.2), overdue items (-0.2), >5 blocked tasks (-0.1) |
| `find_key_blocker()` | UserContext | str \| None | The prerequisite blocking the most downstream items (counts across `prerequisites_needed` dict) |
| `calculate_momentum()` | UserContext | float (0.0-1.0) | 3-factor weighted average: task completion rate (10/10 = 1.0), habit streak average (14-day benchmark = 1.0), learning velocity |
| `calculate_domain_balance()` | UserContext | float (0.0-1.0) | Inverse of standard deviation across domain progress — lower variance = better balance |

These functions have **zero side effects** and **zero service dependencies**. They take a UserContext, return a number. This pattern could be applied anywhere two services share scoring logic.

### UserStateAnalyzer

Reads UserContext and produces an `AskesisAnalysis` — a frozen dataclass containing:

**Context summary** — per-domain structured dict exposed in the API response. Mirrors the same data points that `ResponseGenerator.build_llm_context()` renders as natural language for the LLM, but in structured form for API consumers:

| Section | Fields |
|---------|--------|
| `tasks` | active, overdue, blocked, due_today |
| `goals` | active, average_progress, nearing_deadline |
| `habits` | active, at_risk, longest_streak, average_streak |
| `events` | upcoming, today |
| `knowledge` | mastery_average, mastered, in_progress, ready_to_learn, learning_velocity, current_learning_path |
| `capacity` | workload, is_blocked, is_overwhelmed, has_overdue |
| `life_path` | alignment_score, is_aligned (only when life_path_uid set) |

Both `_summarize_context` (structured dict) and `build_llm_context` (natural language string) read directly from UserContext — incidental duplication, not structural. UserContext is the shared data source; each consumer picks the fields it needs in the format its audience requires.

**Health metrics** (each 0.0-1.0, combined into weighted `overall`):
- `consistency` — habit streak average / 30-day benchmark (weight: 30%)
- `progress` — goal advancement percentage (20%)
- `balance` — domain distribution via `calculate_domain_balance()` (15%)
- `momentum` — learning velocity via `calculate_momentum()` (15%)
- `sustainability` — 1.0 minus workload score (20%)

**Risk assessment:** habit risk (streaks at danger), goal risk (stalled goals), overload risk (too many active items), stagnation risk (no recent progress).

**Pattern detection:** habit-goal correlation, learning velocity acceleration/deceleration, high workload warnings.

**Insights** — typed `AskesisInsight` objects at three severity levels:
- **RISK:** at-risk habits, blocked progress, high workload
- **OPPORTUNITY:** multiple ready-to-learn KUs, high-momentum domains
- **PATTERN:** habit-goal correlations, learning velocity trends

The analyzer does NOT generate recommendations — it receives them. The `AskesisService` facade orchestrates: get insights first, pass them to the recommendation engine, then pass recommendations back into the final analysis assembly.

### ActionRecommendationEngine

Three responsibilities:

**1. Next best action** (`get_next_best_action()`) — a strict priority cascade:

| Priority | Trigger | Action |
|----------|---------|--------|
| **CRITICAL** | Habit with 14+ day streak at risk of breaking | "Complete [habit] to protect your streak" |
| **HIGH** | Key blocker identified by `find_key_blocker()` | "Unblock [prerequisite] — it's holding back N items" |
| **MEDIUM** | Goal between 50-100% completion | "Advance [goal] — you're X% there" |
| **LOW** | No urgent actions | "Establish a daily learning habit" |

Each level checks and falls through to the next if no match. The cascade always produces an action.

**2. Workflow optimizations** (`optimize_workflow()`) — structural suggestions: consolidate habits (when >10 active), align goals with life path, optimize knowledge paths, suggest MOC creation.

**3. Future state prediction** (`predict_future_state(days_ahead=7)`) — projects at-risk habits, goal completion likelihood, and knowledge readiness based on current trajectory.

### Orchestration Flow

The `AskesisService` facade eliminates the circular dependency at the orchestration level:

```
AskesisService.analyze_user_state(user_context)
  1. state_analyzer.identify_patterns()     → insights (or [] on failure)
  2. recommendation_engine.generate_recommendations(insights)  → recommendations (or [])
  3. recommendation_engine.optimize_workflow()  → optimizations (or [])
  4. zpd_service.assess_zone()              → zpd_assessment (or None)
  5. state_analyzer.analyze_user_state(     → AskesisAnalysis
       recommendations=recommendations,
       optimizations=optimizations,
       zpd_assessment=zpd_assessment,
     )
```

Each step uses whatever the previous steps produced. If any step fails, its output defaults to empty — the final analysis is assembled from whatever succeeded.

---

## Error Boundaries

Askesis requires `INTELLIGENCE_TIER=full` — it depends on Neo4j, an LLM, and an embeddings service. All three can fail. Here's what happens when they do.

### Construction vs. Runtime Failures

Askesis draws a hard line between **missing dependencies** (construction) and **failing operations** (runtime):

- **Construction (fail-fast):** All 7 entity services, the intelligence factory, LLM service, and embeddings service are required at `__init__`. A missing dependency raises immediately — no silent `None` defaults, no empty stubs. You find out at startup, not at query time.
- **Runtime (partial tolerance):** Once constructed, individual operations can fail without killing the pipeline. The pattern: `asyncio.gather(return_exceptions=True)` + default to empty on failure.

### Pipeline Timeout

The entire RAG pipeline (Steps 1–10) runs under `asyncio.wait_for()` with a **30-second timeout** (`AskesisPipelineTimeout.ANSWER_QUESTION_SECONDS`). This catches:
- Slow Neo4j MEGA-QUERY (cold cache, large graph)
- Unresponsive LLM API (rate limit, network partition)
- Cascading slowness from multiple partial failures

On timeout: `Result.fail()` with user message *"Your question is taking too long. Please try again."* Both `answer_user_question()` and `process_query_with_context()` have independent timeouts — a slow query processor doesn't block the outer pipeline indefinitely.

### What Fails and What Happens

| Component | Failure Mode | Pipeline Response |
|-----------|-------------|-------------------|
| **UserContext load** | Neo4j down or MEGA-QUERY fails | Pipeline cannot proceed — returns `Result.fail()` |
| **Intent classification** | Embeddings API unavailable | Defaults to `SPECIFIC` intent (lower precision, not a crash) |
| **Intent classification** | Individual exemplar embedding fails | Skipped — classification works with fewer exemplars |
| **Entity extraction** | Domain service unavailable | Continues with empty matches — LLM still answers using other context |
| **LS bundle fetch** | One of 7 entity fetches times out | That collection defaults to empty; bundle built from what succeeds |
| **LS bundle fetch** | All fetches fail | Minimal bundle (just the LearningStep) — still enables GuidanceMode |
| **LS bundle fetch** | No active Learning Step | Falls back to context-aware generation without Socratic layer |
| **ZPD assessment** | ZPD service fails | Continues with empty evidence — GuidanceMode still determined (less informed) |
| **Citation formatting** | Citation service `None` or graph query fails | Citations omitted — answer still returned without source references |
| **LLM generation** | LLM API error or timeout | `Result.fail()` — no fallback (this is the terminal step) |
| **Token overflow** | Bundle has too many Articles | `truncate_to_budget()` truncates to `MAX_CURRICULUM_CHARS` (~2500 tokens) |

### The Degradation Ladder

The pipeline degrades in stages, not all-or-nothing:

1. **Full pipeline** — all services respond, bundle complete, ZPD evidence available → Socratic guidance with rich context
2. **Partial bundle** — some entity fetches failed → guided response with narrower scope
3. **No ZPD evidence** — ZPD service failed → GuidanceMode defaults to EXPLORATORY (scaffold)
4. **No entity matches** — extraction failed → LLM answers from UserContext summary alone
5. **No bundle** — no active LS or bundle load failed → context-aware answer without Socratic layer
6. **No enrollment** — user has no Learning Path → immediate redirect (no computation wasted)
7. **Pipeline timeout** — 30s exceeded → clean failure with retry message

Stages 1–5 return a response (degraded but functional). Stages 6–7 return a failure.

### Error Handling Patterns Used

**`@with_error_handling` decorator** — wraps async methods with try/except, categorizes exceptions into 6 error types (validation, database, integration, business, not_found, system), and returns `Result.fail()` with rich `ErrorContext`. Used on all public methods in UserStateAnalyzer and ActionRecommendationEngine.

**`asyncio.gather(return_exceptions=True)`** — used in LS bundle loading. Each entity fetch runs in parallel; if one raises, the others continue. Failed fetches are logged and defaulted to empty.

**Result cascade** — the facade orchestration (state analysis) checks `result.is_error` at each step and substitutes empty defaults rather than propagating failures upward. The final assembly always runs.

---

## What Makes Askesis Work

Three things distinguish Askesis from a generic AI assistant:

1. **Curriculum anchoring.** Every conversation is scoped to the user's Learning Path and current Learning Step. The LLM has access to the actual teaching content (Lessons), not just metadata.

2. **ZPD-driven pedagogy.** The mode of response is determined by measured engagement evidence, not heuristics or LLM judgment. A deterministic decision tree ensures consistent pedagogical behavior.

3. **Cross-domain synthesis.** The daily work plan, learning recommendations, and life path alignment score all draw from the complete UserContext — all 21 entity types, not just one domain.

---

## What's Not Yet Built

| Feature | Status | Why It Matters |
|---------|--------|---------------|
| Journal signal extraction | Phase 2 — `JournalInsight` shape defined | Journals reveal what the user actually understands vs. what they've merely encountered |
| Neo4j conversation persistence | Deferred | Cross-session continuity ("last week we discussed X") |
| Teacher interface | Deferred | Teachers shaping what Askesis says to their students |
| Prompt template migration | **Partial** — guided system prompts (7 templates) migrated; LLM context assembly + Q&A/planning prompts remain programmatic | Editable pedagogical prompts without touching Python |
| Events + Principles in LS bundle | Planned | Currently empty tuples — will populate from graph_context |
| Resource access expansion | Planned | Broader resource discovery beyond CITES_RESOURCE — semantic search across all Resources |
| Fine-tuned model | Deferred | Training on conversation data once volume exists |

---

## Key Files

| Purpose | File |
|---------|------|
| Facade | `core/services/askesis_service.py` |
| Factory | `core/services/askesis_factory.py` |
| RAG orchestration | `core/services/askesis/query_processor.py` |
| Intent classification | `core/services/askesis/intent_classifier.py` |
| System prompt generation | `core/services/askesis/response_generator.py` |
| Entity extraction | `core/services/askesis/entity_extractor.py` |
| Context + LS bundle loading | `core/services/askesis/context_retriever.py` |
| State analysis | `core/services/askesis/user_state_analyzer.py` |
| Recommendations | `core/services/askesis/action_recommendation_engine.py` |
| Pure scoring functions | `core/services/askesis/state_scoring.py` |
| Citation formatting | `core/services/askesis_citation_service.py` |
| Citation Cypher queries | `adapters/persistence/neo4j/query/_provenance_queries.py` |
| Types/dataclasses | `core/services/askesis/types.py` |
| LS Bundle model | `core/models/askesis/ls_bundle.py` |
| GuidanceMode enum | `core/models/enums/metadata_enums.py` |
| PedagogicalIntent enum | `core/models/askesis/pedagogical_intent.py` |
| Token truncation | `core/utils/text_truncation.py` |
| Token budget constants | `core/constants.py` (`AskesisTokenBudget`) |
| Protocols (16 methods) | `core/ports/askesis_protocols.py` |
| API routes (20 endpoints) | `adapters/inbound/askesis_api.py` |
| UI routes | `adapters/inbound/askesis_ui.py` |
| Guided prompt templates (7) | `core/prompts/templates/askesis_guided_*.md` |
| Interaction pattern templates (4) | `core/prompts/templates/askesis_scaffold_entry.md`, `askesis_socratic_turn.md`, `askesis_ku_bridge.md`, `askesis_journal_reflection.md` |
