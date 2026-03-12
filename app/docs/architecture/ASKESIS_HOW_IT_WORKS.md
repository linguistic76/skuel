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

### Step 4: Extract Entities

`EntityExtractor.extract_entities_from_query(question, user_context)` uses fuzzy matching to find which specific entities (tasks, goals, habits, knowledge units, events) the user is referring to. For example, "How's my REST API goal going?" matches a goal titled "Build REST API."

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
├── Articles            — teaching compositions linked to this step
├── KUs                 — atomic knowledge units trained by this step
├── Habits              — practice habits linked to this step
├── Tasks               — practice tasks linked to this step
├── Events              — (planned)
├── Principles          — (planned)
├── Edges               — semantic relationships between bundle entities
└── Learning Objectives — extracted from Articles
```

The bundle is the **scope window**. Every pedagogical decision operates within it. If the question falls outside the bundle, Askesis redirects gently.

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

### Step 10: Assemble Response

The final response includes:
- **answer:** the LLM-generated text
- **context_used:** which entities and data informed the answer
- **suggested_actions:** next steps (at-risk habits, overdue tasks, learning path continuation)
- **confidence:** calculated from context availability, citations, and entity matches
- **guidance_mode:** which pedagogical mode was used (if guided)
- **citations:** for prerequisite/hierarchical queries, source references

---

## State Analysis & Recommendations

Beyond the conversational pipeline, Askesis provides state analysis through two sub-services:

**UserStateAnalyzer** reads UserContext and produces:
- Health metrics (consistency, progress, balance, momentum, sustainability — 0.0-1.0 each)
- Risk assessment (habit risk, goal risk, overload risk, stagnation risk)
- Pattern detection (habit-goal correlation, learning velocity, high workload)
- Insights (critical issues, opportunities, blocked states)

**ActionRecommendationEngine** generates the single next best action, following a strict priority:
1. **Critical:** Prevent habit streak loss (14+ day streaks at risk)
2. **High:** Unblock if stuck (key prerequisite identification)
3. **Medium:** Advance goals (closest to completion first)
4. **Low:** Build foundation (establish learning habits)

Both services use **pure functions** from `state_scoring.py` for shared calculations (score, momentum, balance, blocker identification), which eliminates circular dependencies.

---

## What Makes Askesis Work

Three things distinguish Askesis from a generic AI assistant:

1. **Curriculum anchoring.** Every conversation is scoped to the user's Learning Path and current Learning Step. The LLM has access to the actual teaching content (Articles), not just metadata.

2. **ZPD-driven pedagogy.** The mode of response is determined by measured engagement evidence, not heuristics or LLM judgment. A deterministic decision tree ensures consistent pedagogical behavior.

3. **Cross-domain synthesis.** The daily work plan, learning recommendations, and life path alignment score all draw from the complete UserContext — all 21 entity types, not just one domain.

---

## What's Not Yet Built

| Feature | Status | Why It Matters |
|---------|--------|---------------|
| Journal signal extraction | Phase 2 — `JournalInsight` shape defined | Journals reveal what the user actually understands vs. what they've merely encountered |
| Neo4j conversation persistence | Deferred | Cross-session continuity ("last week we discussed X") |
| Teacher interface | Deferred | Teachers shaping what Askesis says to their students |
| Prompt template migration | Deferred | Moving inline prompt strings to editable PROMPT_REGISTRY templates |
| Events + Principles in LS bundle | Planned | Currently empty tuples — will populate from graph_context |
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
| Types/dataclasses | `core/services/askesis/types.py` |
| LS Bundle model | `core/models/askesis/ls_bundle.py` |
| GuidanceMode enum | `core/models/enums/metadata_enums.py` |
| PedagogicalIntent enum | `core/models/askesis/pedagogical_intent.py` |
| Protocols (16 methods) | `core/ports/askesis_protocols.py` |
| API routes (20 endpoints) | `adapters/inbound/askesis_api.py` |
| UI routes | `adapters/inbound/askesis_ui.py` |
| Prompt templates (4) | `core/prompts/templates/askesis_*.md` |
