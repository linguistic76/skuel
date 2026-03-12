# Askesis Guided Pipeline — LS-Scoped, ZPD-Centered, GuidanceMode-Aware

**Last Updated:** March 12, 2026

---

## Design Rationale

Askesis is a curriculum-focused chatbot scoped to the user's active Learning Path. No LP enrollment = no Askesis. It uses all curriculum content (Articles, Kus, Resources) linked to the LP/LS graph. Default register is DIRECT, with SOCRATIC, EXPLORATORY, and ENCOURAGING as situational modes.

**Three principles:**
1. **LP-scoped:** No LP enrollment = no Askesis. LP gate at top of pipeline.
2. **ZPD-centered:** GuidanceMode is driven by measured engagement evidence per KU.
3. **One pipeline:** The guided pipeline is integrated into `answer_user_question()` — no parallel pipeline.

---

## The Pipeline

```
USER ASKS QUESTION
        |
LP Enrollment Gate (user_context.enrolled_path_uids)
        |
IntentClassifier.classify_intent(question)  ← QueryIntent (WHAT)
        |
EntityExtractor.extract_entities_from_query(question, user_context)
        |
ContextRetriever.retrieve_relevant_context(user_context, question, intent)
        |
ContextRetriever.load_ls_bundle(user_uid, user_context)
        |
LSBundle (frozen, scoped to 1 Learning Step) — or None
        |
EntityExtractor.extract_from_bundle(question, ls_bundle)
        |
Target KU UIDs (scoped to bundle)
        |
ZPDService.assess_ku_readiness(user_uid, ku_uids)
        |
IntentClassifier.determine_guidance_mode(question, ls_bundle, zone_evidence, ku_uids)
        |
GuidanceDetermination (mode + pedagogical_detail + evidence)
        |
ResponseGenerator.build_guided_system_prompt(guidance, ls_bundle, user_context)
        |
LLMService.generate(prompt=question, system_prompt=guided_prompt)
        |
RESPONSE (GuidanceMode-tagged)
```

**Orchestration:** `QueryProcessor.answer_user_question()` runs this pipeline. When no LS bundle is available, it falls back to the standard RAG pipeline (global retrieval + LLM generation).

---

## GuidanceMode — How Askesis Responds

| Mode | PedagogicalIntent | Askesis Register |
|------|-------------------|-----------------|
| `DIRECT` | REDIRECT_TO_CURRICULUM, OUT_OF_SCOPE | Concise, informational, redirects to curriculum |
| `SOCRATIC` | ASSESS_UNDERSTANDING, PROBE_DEEPER | Probes understanding via questions, does not give answers |
| `EXPLORATORY` | SCAFFOLD, SURFACE_CONNECTION | Guided discovery through scaffolding and connections |
| `ENCOURAGING` | ENCOURAGE_PRACTICE | Warm, practice-focused, connects understanding to activity |

**Enum location:** `core/models/enums/metadata_enums.py` — `GuidanceMode` (DIRECT is default).

**Mapping:** `IntentClassifier.determine_guidance_mode()` wraps `classify_pedagogical_intent()` and maps PedagogicalIntent → GuidanceMode via `_INTENT_TO_GUIDANCE_MODE` dict.

---

## Pedagogical Intent Taxonomy

| Intent | When | Strategy |
|--------|------|----------|
| `ASSESS_UNDERSTANDING` | 2+ ZPD signals (confirmed) | Ask user to explain in own words |
| `PROBE_DEEPER` | 1 signal, practice present | Follow-up testing deeper understanding |
| `SCAFFOLD` | 0 signals, KU in bundle | Leading questions toward insight |
| `REDIRECT_TO_CURRICULUM` | No ZPD evidence at all | Point to Article to read first |
| `ENCOURAGE_PRACTICE` | 1 signal, missing practice | Connect understanding to habits/tasks |
| `SURFACE_CONNECTION` | Multi-KU question with edges | Highlight relationships between concepts |
| `OUT_OF_SCOPE` | Question not in LS bundle | Redirect to current learning focus |

**Key design decision:** Intent classification is deterministic (decision tree), not LLM-based. It uses ZoneEvidence boolean flags and runs in ~1ms with no network I/O.

---

## GuidanceDetermination

```python
@dataclass(frozen=True)
class GuidanceDetermination:
    mode: GuidanceMode                    # DIRECT, SOCRATIC, EXPLORATORY, ENCOURAGING
    pedagogical_detail: PedagogicalIntent # fine-grained intent within the mode
    target_ku_uids: list[str]
    zone_evidence: dict[str, Any]
```

**Produced by:** `IntentClassifier.determine_guidance_mode()`
**Consumed by:** `ResponseGenerator.build_guided_system_prompt()`

---

## LSBundle — Scoped Context

The LSBundle is a frozen dataclass containing the complete context for a Learning Step:

- `learning_step: LearningStep` — the active step
- `learning_path: LearningPath | None` — parent path
- `articles: tuple[Article, ...]` — primary + supporting content
- `kus: tuple[Ku, ...]` — atomic knowledge units trained by this step
- `habits, tasks, events, principles` — practice activities linked to the step
- `edges: tuple[dict, ...]` — semantic relationships between bundle entities
- `learning_objectives: tuple[str, ...]` — from Articles in the bundle

**Immutability:** Built once per question, passed through the pipeline, never mutated.

**Construction:** `ContextRetriever.load_ls_bundle()` builds the bundle from `UserContext.active_learning_steps_rich` (already loaded by the MEGA-QUERY) plus full entity fetches for content fields.

---

## ZPD as Query-Time Participant

`ZPDService.assess_ku_readiness(user_uid, ku_uids)` provides targeted engagement evidence for specific KUs without computing the full zone assessment.

`ZoneEvidence` per KU:
- `submission_count` — exercise submissions touching this KU
- `habit_reinforcement` — habit linked to this KU is active
- `task_application` — task linked to this KU is in progress
- `journal_application` — journal reflections on this KU
- `signal_count` — sum of boolean evidence types (0-4)
- `is_confirmed` — True when signal_count >= 2

**Compound mastery:** One submission alone doesn't prove understanding. Mastery requires 2+ evidence types (e.g., submission + habit reinforcement).

---

## Guided System Prompts

`ResponseGenerator.build_guided_system_prompt()` dispatches to 4 mode-specific builders:

- `_build_direct_prompt()` — redirect to curriculum or out-of-scope responses
- `_build_socratic_prompt()` — assess understanding or probe deeper (does NOT give answers)
- `_build_exploratory_prompt()` — scaffold toward insight or surface connections
- `_build_encouraging_prompt()` — connect understanding to practice activities

Each builder uses `guidance.pedagogical_detail` for fine-grained variation within the mode.

**ASSESS does not give answers.** The system prompt tells the LLM to ask "Tell me what you know about [X]" and the curriculum content is only for the LLM to evaluate, not to share.

---

## Structured Learning Objectives

Progressive enhancement on string-based `learning_objectives`:

```python
@dataclass(frozen=True)
class StructuredLearningObjective:
    statement: str                              # "Explain why breath is used as anchor"
    assessment_type: str = "conceptual"         # conceptual | procedural | reflective
    evidence_markers: tuple[str, ...] = ()      # Keywords a correct response contains
    depth_levels: dict[str, str] = {}           # {surface: "...", functional: "...", deep: "..."}
    ku_uid: str | None = None                   # KU this objective targets
```

When populated on Curriculum entities, the guided pipeline can assess learner responses against specific, measurable criteria. When empty, falls back to string objectives.

---

## Future Directions

### Conversation Signals to ZPD
Socratic conversations can generate ZPD signals: if the user explains a concept correctly in an ASSESS turn, that's evidence comparable to a submission. Not yet implemented — requires structured evaluation.

### ZPD Expansion to Articles and LS
Currently ZPD assesses per-KU. Expanding to per-Article and per-LS would enable "Have you understood this entire Learning Step?" assessment. Interfaces are ready; implementation waits for curriculum content to reveal what's needed.

### Multi-LP Users
Users enrolled in multiple Learning Paths need a way to select which LP's LS drives the session. Current implementation uses the first active (non-mastered) LS. Future: explicit session binding to a specific LP.

### Resource Connectivity (Phase 8)
Wire Resource entities into curriculum graph for Askesis to surface. Articles and Kus connect to Resources via REFERENCES edges.

---

## Key Files

| File | Role |
|------|------|
| `core/services/askesis/query_processor.py` | `answer_user_question()` — LP-scoped pipeline orchestration |
| `core/services/askesis/intent_classifier.py` | `classify_pedagogical_intent()` + `determine_guidance_mode()` |
| `core/services/askesis/entity_extractor.py` | `extract_from_bundle()` — scoped entity matching |
| `core/services/askesis/context_retriever.py` | `load_ls_bundle()` — LS bundle loading |
| `core/services/askesis/response_generator.py` | `build_guided_system_prompt()` — 4 mode builders |
| `core/services/zpd/zpd_service.py` | `assess_ku_readiness()` — targeted ZPD |
| `adapters/persistence/neo4j/zpd_backend.py` | `get_targeted_ku_engagement()` — Cypher query |
| `core/models/askesis/ls_bundle.py` | LSBundle frozen dataclass |
| `core/models/askesis/pedagogical_intent.py` | PedagogicalIntent enum (7 move types) |
| `core/models/askesis/learning_objective.py` | StructuredLearningObjective |
| `core/models/enums/metadata_enums.py` | GuidanceMode enum (DIRECT, SOCRATIC, EXPLORATORY, ENCOURAGING) |
