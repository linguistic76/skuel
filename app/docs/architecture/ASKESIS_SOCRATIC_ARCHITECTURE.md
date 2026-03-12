# Askesis Socratic Architecture — LS-Scoped, ZPD-Centered Tutoring

**Last Updated:** March 2026

---

## Design Rationale

Askesis is not a chatbot. It is a Socratic tutor whose value comes from going deep on what the learner is currently studying. The legacy pipeline retrieves globally and generates answers. The Socratic pipeline loads the learner's active Learning Step, classifies the pedagogical move, and responds with questions — it does not give answers.

**Three principles:**
1. **LS-scoped:** Every retrieval is bound to the active Learning Step's bundle
2. **ZPD-centered:** Pedagogical moves are driven by measured engagement evidence
3. **Socratic:** The system asks the learner to produce knowledge, not consume explanations

---

## The Pipeline

```
USER ASKS QUESTION
        |
LSContextLoader.load_bundle(user_uid, user_context)
        |
LSBundle (frozen, scoped to 1 Learning Step)
        |
EntityExtractor.extract_from_bundle(question, ls_bundle)
        |
Target KU UIDs (scoped to bundle)
        |
ZPDService.assess_ku_readiness(user_uid, ku_uids)
        |
zone_evidence: dict[str, ZoneEvidence] (per-KU engagement)
        |
IntentClassifier.classify_pedagogical_intent(question, ls_bundle, zone_evidence, ku_uids)
        |
PedagogicalIntent (ASSESS | PROBE | SCAFFOLD | REDIRECT | ENCOURAGE | SURFACE | OUT_OF_SCOPE)
        |
SocraticEngine.generate_move(intent, ls_bundle, zone_evidence, conversation, target_ku_uids)
        |
SocraticMove (system_prompt + curriculum_context + evaluation_rubric)
        |
LLMService.generate(prompt=question, system_prompt=move.system_prompt)
        |
TUTOR RESPONSE (question, not explanation)
```

**Orchestration:** `QueryProcessor.process_socratic_turn()` runs this pipeline. `AskesisService.ask_socratic()` is the facade entry point.

---

## Pedagogical Intent Taxonomy

| Intent | When | Socratic Strategy |
|--------|------|-------------------|
| `ASSESS_UNDERSTANDING` | 2+ ZPD signals (confirmed) | Ask user to explain in own words |
| `PROBE_DEEPER` | 1 signal, practice present | Follow-up testing deeper understanding |
| `SCAFFOLD` | 0 signals, KU in bundle | Leading questions toward insight |
| `REDIRECT_TO_CURRICULUM` | No ZPD evidence at all | Point to Article to read first |
| `ENCOURAGE_PRACTICE` | 1 signal, missing practice | Connect understanding to habits/tasks |
| `SURFACE_CONNECTION` | Multi-KU question with edges | Highlight relationships between concepts |
| `OUT_OF_SCOPE` | Question not in LS bundle | Redirect to current learning focus |

**Key design decision:** Intent classification is deterministic (decision tree), not LLM-based. It uses ZoneEvidence boolean flags and runs in ~1ms with no network I/O.

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

**Immutability:** Built once per Socratic turn, passed through the pipeline, never mutated.

**Construction:** `LSContextLoader` builds the bundle from `UserContext.active_learning_steps_rich` (already loaded by the MEGA-QUERY) plus full entity fetches for content fields.

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

## Socratic Engine — Move Generation

The SocraticEngine is pure logic (no I/O). Given the classified intent, it constructs a `SocraticMove` with:

- `system_prompt` — instructs the LLM how to respond (Socratically)
- `curriculum_context` — Article content for the LLM's reference (withheld from user in ASSESS moves)
- `evaluation_rubric` — learning objectives to check against (for future evaluation)
- `conversation_history` — recent turns for multi-turn context

**ASSESS does not give answers.** The system prompt tells the LLM to ask "Tell me what you know about [X]" and the curriculum content is only for the LLM to evaluate, not to share.

---

## Structured Learning Objectives (Phase 6)

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

When populated on Curriculum entities, the EvaluationEngine can assess learner responses against specific, measurable criteria. When empty, falls back to string objectives.

---

## Conversation Persistence (Skeleton)

`ConversationContext` manages in-memory sessions during the current process lifetime. `AskesisConversation(UserOwnedEntity)` is defined for future graph persistence:

- Session resumption across page reloads
- Conversation analytics (topics explored, depth achieved)
- ZPD signal generation from conversation patterns (future)

UID prefix: `conv_`. Implementation deferred until the Socratic pipeline demonstrates value.

---

## Future Directions

### Conversation Signals to ZPD
Socratic conversations can generate ZPD signals: if the user explains a concept correctly in an ASSESS turn, that's evidence comparable to a submission. Not yet implemented — requires structured evaluation.

### ZPD Expansion to Articles and LS
Currently ZPD assesses per-KU. Expanding to per-Article and per-LS would enable "Have you understood this entire Learning Step?" assessment. Interfaces are ready; implementation waits for curriculum content to reveal what's needed.

### Multi-LP Users
Users enrolled in multiple Learning Paths need a way to select which LP's LS drives the Socratic session. Current implementation uses the first active (non-mastered) LS. Future: explicit session binding to a specific LP.

### Curriculum Developer Guidance
How to write objectives the system can evaluate against:
- Include `evidence_markers` for keyword matching
- Use `depth_levels` to distinguish surface recall from functional understanding
- One objective per KU for precise assessment

---

## Key Files

| File | Role |
|------|------|
| `core/services/askesis/query_processor.py` | `process_socratic_turn()` — pipeline orchestration |
| `core/services/askesis_service.py` | `ask_socratic()` — facade entry point |
| `core/services/askesis/ls_context_loader.py` | LSBundle loading from UserContext |
| `core/services/askesis/intent_classifier.py` | `classify_pedagogical_intent()` — decision tree |
| `core/services/askesis/entity_extractor.py` | `extract_from_bundle()` — scoped entity matching |
| `core/services/askesis/socratic_engine.py` | SocraticMove generation (pure logic) |
| `core/services/askesis/evaluation_engine.py` | EvaluationResult skeleton |
| `core/services/zpd/zpd_service.py` | `assess_ku_readiness()` — targeted ZPD |
| `adapters/persistence/neo4j/zpd_backend.py` | `get_targeted_ku_engagement()` — Cypher query |
| `core/models/askesis/ls_bundle.py` | LSBundle frozen dataclass |
| `core/models/askesis/pedagogical_intent.py` | PedagogicalIntent enum |
| `core/models/askesis/socratic_move.py` | SocraticMove frozen dataclass |
| `core/models/askesis/learning_objective.py` | StructuredLearningObjective |
| `core/models/askesis/conversation_entity.py` | AskesisConversation (persistence skeleton) |
