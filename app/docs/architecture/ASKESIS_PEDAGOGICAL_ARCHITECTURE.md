# Askesis: Pedagogical Architecture

> "Not a recommendation feed. A Socratic companion that knows the curriculum and the learner,
> and guides them toward their own understanding."

**Companion to:** `docs/architecture/ASKESIS_ARCHITECTURE.md` (service structure)
**This doc:** pedagogical vision — how Askesis teaches, not how it is built

---

## 1. The Vision

Askesis is grounded in Vygotsky's **Zone of Proximal Development (ZPD)**: the space between
what a learner can do alone and what they can do with guidance. SKUEL's Neo4j curriculum graph
already encodes this zone. Askesis reads it.

The design goal is a **Socratic companion**, not a content delivery system:

- **Socratic** — asks questions that reveal what the user is thinking, not questions that test recall
- **Companion** — consistent presence across sessions, aware of where the user has been
- **Curriculum-aware** — knows the structure of knowledge, not just the user's activity
- **ZPD-anchored** — knows what the user is ready for next, and scaffolds them there gently

What Askesis is **not**:
- A news feed ("here are 5 things to learn today")
- A search engine ("find me resources on X")
- A tutor that delivers content ("here is an explanation of X")
- A recommendation engine that optimizes for engagement

---

## 2. ZPD in the Graph

SKUEL's Neo4j graph encodes the user's current and proximal zones implicitly through
relationship types. No separate ZPD index is needed — the graph is the ZPD.

### Current Zone (what the user has engaged)

```cypher
// Applied — user did work with this KU
(User)-[:OWNS]->(Task)-[:APPLIES_KNOWLEDGE]->(Ku)

// Reflected — user wrote about this KU in a journal
(Journal)-[:APPLIES_KNOWLEDGE]->(Ku)

// Embodied — user built a habit reinforcing this KU
(Habit)-[:REINFORCES_KNOWLEDGE]->(Ku)
```

A KU is in the **current zone** when the user has at least one of these relationships,
and the engagement is meaningful (not a single abandoned task).

### Proximal Zone (what the user is ready for)

```cypher
// Structurally ready — prerequisites met
(Ku_engaged)-[:PREREQUISITE_FOR]->(Ku_next)

// Could illuminate — complementary to engaged KU
(Ku_engaged)-[:COMPLEMENTARY_TO]->(Ku_adjacent)

// On their path — next step in a learning path they've started
(Lp)-[:ORGANIZES]->(Ku_next)
```

A KU is in the **proximal zone** when:
1. It is adjacent to an engaged KU via one of these edges, AND
2. The user has not yet meaningfully engaged it, AND
3. The user has engaged the prerequisite(s) for it (if any)

This is the computation `ZPDService.assess_zone()` will perform (deferred — see
`docs/roadmap/zpd-service-deferred.md`).

### ZPD and Context Awareness Protocols

When `ZPDService` and Askesis query user readiness, they need a well-defined slice of `UserContext` — not all 240 fields. The context awareness protocols define exactly these slices:

| Service | Protocol | Fields used |
|---------|----------|------------|
| `ZPDService.assess_zone()` | `KnowledgeAwareness & LearningPathAwareness` | `mastered_knowledge_uids`, `prerequisites_completed`, `prerequisites_needed`, `enrolled_path_uids`, `current_step_uid` |
| `AskesisQueryService` | `LearningPathAwareness` | Enrolled paths, current step, ZPD position |
| `AskesisStateAnalysisService` | `CrossDomainAwareness` | Cross-domain readiness signals |
| Askesis dialogue context | `FullAwareness` | Complete user state for Socratic scaffolding |

```python
from core.ports import KnowledgeAwareness, LearningPathAwareness

async def assess_zone(self, context: KnowledgeAwareness) -> ZPDAssessment:
    """ZPD assessment only needs knowledge mastery + prerequisites."""
    mastered = context.mastered_knowledge_uids
    prereqs = context.prerequisites_completed
    ...
```

This is architecturally significant: the ZPD score is derived entirely from knowledge state. A service that declares `KnowledgeAwareness` cannot accidentally access task or habit data — the contract is enforced by MyPy.

**See:** `core/ports/context_awareness_protocols.py`

---

## 3. Journal → Pedagogical Signal Pipeline

Journals are the richest signal of where the user actually is. A journal entry after
working with a KU reveals: what clicked, what they're still unsure about, what questions
remain open. These are prime scaffolding targets.

### Phase 1 (exists): Format

`JournalOutputGenerator` formats raw journal transcripts into clean Markdown. Three
templates capture intent:
- `journal_articulation.md` — user developing and articulating concepts
- `journal_exploration.md` — user exploring an unfamiliar domain
- `journal_activity.md` — user reflecting on a task or event

The formatted content is stored in `processed_content` on the Journal entity.

### Phase 2 (deferred): ZPD Signal Extraction

After formatting, `JournalOutputGenerator` will run a second LLM pass to extract
pedagogical signals into a `JournalInsight` object:

```python
# core/models/submissions/journal_insight.py — shape defined, extraction deferred
@dataclass(frozen=True)
class JournalInsight:
    journal_uid: str
    open_questions: list[str]       # Unresolved questions — prime conversation starters
    concepts_mentioned: list[str]   # Concepts to link to KUs via semantic search
    struggles: list[str]            # Expressed uncertainty — scaffolding targets
    insights_crystallized: list[str] # Things that clicked — mastery signals
    related_ku_uids: list[str]      # KU links via semantic search (Phase 2)
```

### Phase 3 (deferred): Surface in UserContext

`JournalInsight` objects surface in `UserContext.journal_insights` — a list of recent
insights, ordered by recency. Askesis reads them when opening a conversation.

### Trigger: Passive, Not Push

Journals do not push notifications to Askesis. When a user opens an Askesis session,
the service reads recent `JournalInsight` objects from UserContext. The signal is
**available when the conversation starts**, not delivered as a notification.

---

## 4. Conversation Sessions — In-Memory (Current State)

Conversation state lives in `core/models/user/conversation.py`:

- `ConversationSession` — mutable model; fields: `session_id`, `user_uid`, `state`,
  `guidance_mode`, `current_topic` (ku_uid), `turns: list[ConversationTurn]`, timestamps
- `ConversationContext` — in-memory dict keyed by `session_id`; lives in the process

**What this means:**
- Sessions survive within a single process run only
- No cross-device continuity — a session started on desktop is not visible on mobile
- No cross-session memory — Askesis cannot say "last week we talked about X"
- `to_llm_messages()` provides context window trimming for multi-turn LLM calls

This is sufficient for the current phase. Cross-session continuity becomes valuable
when the curriculum graph has real data and users have consistent conversation histories.

**See:** `docs/roadmap/conversation-neo4j-persistence-deferred.md` for the full Neo4j schema.

---

## 5. Conversation Sessions — Neo4j (Deferred)

See `docs/roadmap/conversation-neo4j-persistence-deferred.md`.

When implemented, Neo4j persistence enables:
- Cross-session continuity ("last week we talked about X — how does that feel now?")
- Teacher review of session summaries (with student consent)
- Training signal for GuidanceMode detection

---

## 6. Curriculum Anchoring

**Every Askesis session is anchored to a curriculum object**: a KU, an LP, or an Exercise.
This is the heart of Askesis' pedagogical edge over a generic AI assistant.

### The Anchor

`ConversationSession.current_topic` holds the `ku_uid` of the anchor. When the session
opens, Askesis reads the anchor's title, description, and graph neighborhood (PREREQUISITE_FOR,
ORGANIZES, COMPLEMENTARY_TO edges) to understand what the user is working with.

### Opening Points

A session can be opened from:
- **KU detail page** — "Talk with Askesis about this KU" (most common)
- **LP detail page** — "Explore this learning path with Askesis"
- **Journal insight** — "Askesis noticed an open question in your journal"
- **Askesis home** — open-ended life dialogue; Askesis surfaces curriculum organically

### Open-Ended Dialogues

When a session opens without an explicit anchor (from Askesis home), Askesis uses
`UserContext` to identify the most relevant KU from the user's current activity and
proposes it as a soft anchor. The user can redirect.

---

## 7. GuidanceMode Detection

Askesis detects the appropriate guidance mode from `UserContext` signals and adapts
its conversational register accordingly. **Implementation is deferred** — the modes and
their detection logic are documented here as the target design.

### Modes

| Mode | When | Askesis Register |
|------|------|-----------------|
| `SOCRATIC` | Consistent engagement with anchor KU | Questions that reveal thinking |
| `EXPLORATORY` | Journal with many open questions | Curiosity, "let's find out together" |
| `ENCOURAGING` | Low momentum (`momentum_score < 0.3`) | Warm, present, low-pressure |
| `DIRECT` | First encounter with KU | Orient clearly, then shift to SOCRATIC |

### Detection Signals (from UserContext)

```python
# Low momentum → encouraging mode
if context.momentum_score < 0.3:
    return GuidanceMode.ENCOURAGING

# Many open journal questions → exploratory
if len(context.journal_insights) > 0 and sum(
    len(i.open_questions) for i in context.journal_insights
) > 3:
    return GuidanceMode.EXPLORATORY

# First encounter with anchor KU → orient first
if anchor_ku_uid not in context.engaged_ku_uids:
    return GuidanceMode.DIRECT

# Default: Socratic
return GuidanceMode.SOCRATIC
```

### Teacher Override (Deferred)

Teachers can set `preferred_guidance_mode` per student. This overrides detection.
See `docs/roadmap/teacher-askesis-interface-deferred.md`.

### Implementation Location

Detection logic belongs in `UserStateAnalyzer` (exists) or the future `ZPDService`.
`GuidanceMode` enum: `core/models/enums/askesis_enums.py` (to be created in Phase 2).

---

## 8. Prompt Templates as Pedagogical Infrastructure

Each Askesis prompt template encodes one pedagogical intent. The template is the
curriculum of the conversation — it constrains what Askesis can do.

| Template | Intent | When Used |
|----------|--------|-----------|
| `askesis_scaffold_entry` | Open a session — invite, don't lecture | Session start |
| `askesis_socratic_turn` | Draw user toward their own realization | Mid-conversation |
| `askesis_ku_bridge` | Introduce adjacent KU as natural next step | ZPD traversal |
| `askesis_journal_reflection` | Respond to journal open questions | Journal-triggered session |

**Current state:** Templates are defined and loadable. Wiring to `QueryProcessor` is
Phase 2 (after ZPDService). Askesis currently uses programmatic string assembly in
`ResponseGenerator.build_llm_context()`.

**Migration path:** Each `generate_context_aware_answer()` call becomes one template.
The programmatic context becomes placeholders. Service logic shrinks.

---

## 9. Teacher-Askesis Intimacy (Deferred)

See `docs/roadmap/teacher-askesis-interface-deferred.md`.

The long-term vision: teachers do not just assign exercises. They shape the pedagogical
environment their students inhabit — including what Askesis says to them. Teacher
annotations on conversation sessions become training data for a fine-tuned model that
has internalized the curriculum structure and the students' patterns.

---

## 10. What This Is Not

**Askesis is not a recommendation engine.** It does not optimize for engagement, breadth,
or streaks. It does not surface the "most relevant" content according to an algorithm.

**Askesis is not a search engine.** It does not answer "explain X to me." It asks "what
do you already know about X?" and builds from there.

**Askesis is not a tutor that delivers content.** It does not explain concepts. It asks
questions that help the user discover the explanation themselves. When a hint is needed,
the hint points at the direction — not the answer.

**Askesis is not stateless.** Every response is informed by: the curriculum graph, the
user's activity history, their journal signals, their current momentum. A generic AI
assistant cannot do this. Askesis can.

---

## Cross-References

- [FOUR_PHASED_LEARNING_LOOP.md](/docs/architecture/FOUR_PHASED_LEARNING_LOOP.md) — Askesis scaffolds Phase 1 (Ku discovery) of the learning loop
- `docs/architecture/ASKESIS_ARCHITECTURE.md` — service structure (pre-refactor, 2025-11-27)
- `docs/roadmap/zpd-service-deferred.md` — ZPDService design
- `docs/roadmap/conversation-neo4j-persistence-deferred.md` — Neo4j conversation schema
- `docs/roadmap/teacher-askesis-interface-deferred.md` — teacher interface design
- `core/models/submissions/journal_insight.py` — JournalInsight dataclass stub
- `core/prompts/templates/askesis_*.md` — four prompt templates
- `.claude/skills/prompt-templates/SKILL.md` — template catalog
