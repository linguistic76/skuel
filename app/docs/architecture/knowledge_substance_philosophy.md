---
title: Knowledge Substance Philosophy
created: 2025-10-17
updated: 2026-08-12
status: active
audience: all
tags: [architecture, knowledge, substance, philosophy, learning, ku-activity-integration]
---

# Knowledge Substance Philosophy

## Core Principle: "Applied knowledge, not pure theory"

**SKUEL measures knowledge by how it's LIVED, not just learned.** Substance tracking embodies the philosophical foundation that knowledge only has value when applied in real life.

---

## The Ontological Hierarchy

```
Life Path (lp) - THE ONE ultimate convergence
    ↑ everything flows toward
Learning Paths (lp) - sequences toward life goals
    ↑ composed of
Path Steps (ps) - curated knowledge + practice bundles
    ↑ built from
Kus (atomic knowledge units, composed into PathSteps via USES_KU)
    ↕ BIDIRECTIONAL enrichment
Supporting Domains - tasks, events, habits, entries, choices, principles
```

**Philosophy:** Everything in SKUEL ultimately flows toward your life path — the ONE ultimate vision of who you want to become.

---

## Bidirectional Relationship: Ku/PathStep ↔ Supporting Domains

**Kus and PathSteps mutually enrich Supporting Domains.** Kus are atomic knowledge units; PathSteps compose Kus into learning content via `USES_KU`/`CONTAINS_KNOWLEDGE`/`TRAINS_KU` relationships. Substance scoring tracks how knowledge is applied across both levels.

### 1. Forward Direction (Knowledge → Supporting)
- Knowledge guides what tasks to create
- Knowledge informs which events to schedule
- Knowledge shapes which habits to build
- Knowledge influences decisions/choices

### 2. Reverse Direction (Supporting → Knowledge)
- Tasks give knowledge substance (practical application)
- Events provide practice opportunities (repetition)
- Habits integrate knowledge into lifestyle (automaticity)
- Entries demonstrate metacognition (reflection)
- Choices show decision-making capacity (judgment)

**Implementation:** Event-driven architecture enables this bidirectionality without coupling.

---

## Data Flow: Where Substance Lives

Substance data flows through two layers:

### Write Path (Event-Driven)

1. Activity domain services publish substance events (e.g., `KnowledgeBulkAppliedInTask`) when entities are created with knowledge UIDs
2. `_event_wiring.py` subscribes events to `PsService` handlers (aliased as `ku_service`)
3. `PsService.increment_substance_metric()` delegates to `KuBackend.increment_substance()`
4. `KuBackend` atomically updates the Ku node **and fans out to connected PathStep nodes** via `(ps:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku)`

```
Activity Event → PsService handler → KuBackend.increment_substance()
                                        ├── UPDATE Ku node (primary)
                                        └── UPDATE connected PathStep nodes (fan-out)
```

### Read Path (Model Construction)

When Ku or PathStep models are constructed from Neo4j (`from_neo4j_node()`), the generic mapper populates substance fields from node properties. The `Curriculum` base class methods (`substance_score()`, `is_well_practiced()`, etc.) then operate on real data.

### Storage Summary

| Node Type | Substance Data | Source |
|-----------|---------------|--------|
| **Ku** | Primary — event handlers write directly | `KuBackend.increment_substance()` |
| **PathStep** | Propagated — fan-out from connected Kus | Same Cypher query, traverses USES_KU/CONTAINS_KNOWLEDGE/TRAINS_KU |

---

## Confidence: Admin-Assessed Content Certainty

`Curriculum.confidence` tracks the admin's certainty about a piece of curriculum content — how reliable, well-sourced, and pedagogically sound it is.

| Level | Meaning |
|-------|---------|
| `UNCERTAIN` | Unverified, needs review |
| `LOW` | Some basis, but gaps or contradictions |
| `MEDIUM` | Reasonable basis, standard review |
| `HIGH` | Well-sourced, peer-reviewed |
| `CERTAIN` | Authoritative, fully verified |

**Distinct from substance:** Confidence is about *content quality* (admin assessment); substance is about *knowledge application* (user behavior). A PathStep can have HIGH confidence (well-written, accurate) but LOW substance (nobody has applied it yet).

**Wiring:** Stored on Curriculum model, round-trips through `CurriculumDTO` (`confidence: Confidence | None`), ingestible via `PathStepCreateRequest`.

---

## Substance Scoring: Weighted Ontology

**Not all practice is equal.** SKUEL weights application types by ontological significance:

| Type | Weight per Instance | Max Contribution | Rationale |
|------|-------------------|------------------|-----------|
| **Habits** | 0.10 | 0.30 (3 habits) | Lifestyle integration = highest substance |
| **Entries (reflection)** | 0.07 | 0.20 (3 reflections) | Metacognition = deep understanding |
| **Choices** | 0.07 | 0.15 (2 decisions) | Decision-making = practical wisdom |
| **Principles** | 0.07 | 0.15 (2 principles) | Value embodiment = living by knowledge |
| **Events** | 0.05 | 0.25 (5 events) | Practice = embodiment |
| **Tasks** | 0.05 | 0.25 (5 tasks) | Application = real-world use |

**Total possible substance:** 1.0 (capped — 6 channels contribute up to 1.30 raw, min(1.0) applied)

### Substance Scale

| Score Range | Classification | Meaning |
|-------------|---------------|---------|
| **0.0-0.2** | Pure theory | Read about it, no application |
| **0.3-0.5** | Applied knowledge | Tried it, some practice |
| **0.6-0.7** | Well-practiced | Regular use, developing mastery |
| **0.8-1.0** | Lifestyle-integrated | Automatic, embodied, second nature |

### Model Methods

These methods live on `Curriculum` (base class for PathStep, Exercise, LearningPath) and read from substance fields populated via Neo4j:

| Method | Returns | What It Tells You |
|--------|---------|-------------------|
| `substance_score()` | `float` (0.0-1.0) | Overall substance with time decay |
| `is_theoretical_only()` | `bool` | Score < 0.2 — no real application |
| `is_well_practiced()` | `bool` | Score >= 0.7 — deeply embedded |
| `needs_more_practice()` | `bool` | Below thresholds on tasks/events/habits |
| `get_substantiation_gaps()` | `list[str]` | Which channels are missing |
| `needs_review()` | `bool` | Once-practiced knowledge decayed below 0.5 |
| `days_until_review_needed()` | `int | None` | Predicted days until decay hits 0.5 |
| `get_substantiation_summary()` | `dict` | Full breakdown for UI display |

---

## Time Decay: Spaced Repetition

**Knowledge decays without practice.** SKUEL uses exponential decay to model forgetting:

### Decay Formula

```python
# Exponential decay with 30-day half-life
weight = e^(-days_since_use / 30)

# Minimum floor: 0.2 (20% retention even after long gap)
decay_weight = max(0.2, weight)
```

### Spaced Repetition Integration

- Predicts when substance will drop below 0.5 threshold
- Alerts user to review before forgetting
- Encourages regular practice (not cramming)

**Philosophy:** Knowledge that isn't used regularly isn't really known.

### Review Schedule

Based on substance score:
- **Score >= 0.8:** Review every 60 days (mastered)
- **Score 0.6-0.79:** Review every 30 days (well-practiced)
- **Score 0.4-0.59:** Review every 14 days (developing)
- **Score < 0.4:** Review every 7 days (needs practice)

---

## YAML Authoring: Substance Relationships

**All 6 substance channels can be declared in YAML** via `connections.*` fields. The ingestion engine reads the relationship registry's `yaml_field_path` and creates Neo4j edges automatically.

### Substance Connection Fields by Domain

| Domain | YAML Field | Relationship | Substance Channel |
|--------|-----------|-------------|-------------------|
| **Task** | `connections.applies_knowledge` | `APPLIES_KNOWLEDGE` | Tasks (0.05/task, max 0.25) |
| **Habit** | `connections.reinforces_knowledge` | `REINFORCES_KNOWLEDGE` | Habits (0.10/habit, max 0.30) |
| **Event** | `connections.applies_knowledge` | `APPLIES_KNOWLEDGE` | Events (0.05/event, max 0.25) |
| **Choice** | `connections.informed_by_knowledge` | `INFORMED_BY_KNOWLEDGE` | Choices (0.07/choice, max 0.15) |
| **Principle** | `connections.grounded_in_knowledge` | `GROUNDED_IN_KNOWLEDGE` | Principles (0.07/principle, max 0.15) |
| **UserEntry** | *(entry-driven, not YAML — see below)* | `APPLIES_KNOWLEDGE` | Entries (0.07/entry, max 0.20) |

The entries channel is scoped to **grounded knowledge/je_pro entries** (Mike's ruling
2026-07-11) and has TWO writers, both publishing the same `KnowledgeReflectedInEntry`
event: explicit `@ku()` references in the `EXTRACT_ACTIVITIES` pipeline (ADR-069), and
vector grounding of `pipeline: knowledge` entries (`EntryGroundingService`,
Entry-Enrichment PR 3). The handler is writer-agnostic — same event, same credit.

### Examples

```yaml
# Choice — informed by knowledge (creates INFORMED_BY_KNOWLEDGE edge)
type: Choice
uid: choice:2-minutes-right-now
title: Do Two Minutes Right Now
connections:
  informed_by_knowledge:
    - ku_breath_awareness_basics_a1b2

# Principle — grounded in knowledge (creates GROUNDED_IN_KNOWLEDGE edge)
type: Principle
uid: principle:small-steps
name: Small Steps Beat Big Bursts
connections:
  grounded_in_knowledge:
    - ku_breath_awareness_basics_a1b2
    - ku_mind_wandering_happens_c3d4

# Task — applies knowledge (creates APPLIES_KNOWLEDGE edge)
type: Task
uid: task:log-first-5-sessions
title: Log First 5 Sessions
connections:
  applies_knowledge:
    - ku_breath_awareness_basics_a1b2

# Habit — reinforces knowledge (creates REINFORCES_KNOWLEDGE edge)
type: Habit
uid: habit:daily-2min-breath
title: Daily 2-Minute Breath
connections:
  reinforces_knowledge:
    - ku_breath_awareness_basics_a1b2
```

### How It Works

1. YAML author writes `connections.{field}: [uid1, uid2]`
2. `preparer.py` flattens `connections` dict to dotted notation
3. `generate_ingestion_relationship_config()` reads `yaml_field_path` from the relationship registry
4. `bulk_ingestion.py` generates `MERGE (n)-[:REL_TYPE]->(target)` Cypher
5. Edge created in Neo4j — substance tracking is now structural

**See:** `_schemas/` for complete field reference.

---

## Event-Driven Substance Updates

**All substance changes flow through domain events:**

### Publishing Events

Single-item event when exactly 1 KU is connected; bulk event when 2+. Never publish both for the same connection.

```python
# Single when 1 KU, bulk when 2+ — actual pattern in TasksCoreService
ku_uids = task_request.applies_knowledge_uids
if len(ku_uids) == 1:
    event = KnowledgeAppliedInTask(
        knowledge_uid=ku_uids[0],
        task_uid=task.uid,
        user_uid=task.user_uid,
        task_title=task.title,
    )
else:
    event = KnowledgeBulkAppliedInTask(
        knowledge_uids=tuple(ku_uids),
        task_uid=task.uid,
        user_uid=task.user_uid,
    )
await publish_event(self.event_bus, event, self.logger)
```

### Subscribing to Events

```python
# PsService subscribes and updates substance atomically
# (aliased as ku_service in _event_wiring.py)
class PsService:
    async def handle_knowledge_applied_in_task(self, event):
        await self.increment_substance_metric(
            ku_uid=event.knowledge_uid,
            metric='times_applied_in_tasks',
            timestamp_field='last_applied_date',
            timestamp=event.occurred_at
        )
```

### KuBackend Fan-Out

```cypher
-- Atomically updates the Ku node AND connected PathStep nodes
MATCH (ku:Entity {uid: $ku_uid})
SET ku.times_applied_in_tasks = COALESCE(ku.times_applied_in_tasks, 0) + 1,
    ku.last_applied_date = datetime($timestamp),
    ku._substance_cache_timestamp = NULL
WITH ku
OPTIONAL MATCH (ps:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku)
WITH ku, ps WHERE ps IS NOT NULL
SET ps.times_applied_in_tasks = COALESCE(ps.times_applied_in_tasks, 0) + 1,
    ps.last_applied_date = datetime($timestamp),
    ps._substance_cache_timestamp = NULL
RETURN ku.times_applied_in_tasks as new_count
```

### Benefits

- **Zero coupling** between domains
- **Atomic Neo4j updates** (race-condition safe)
- **Fan-out propagation** — Ku substance automatically flows to composing PathSteps
- **Full audit trail** (every application tracked)
- **Flexible weighting** (adjust philosophy without code changes)

---

## Substance Events Catalog

**Location:** `/core/events/knowledge_substance_events.py`

Each channel has a **single-item** event (exactly 1 KU connection) and a **bulk** event (2+ KU connections). Publishers dispatch based on count — never double-publish both forms for the same connection. Subscribers for both forms are wired in `_event_wiring.py`.

| Channel | Single-item event | Bulk event |
|---------|-------------------|------------|
| Task | `KnowledgeAppliedInTask` | `KnowledgeBulkAppliedInTask` |
| Event | `KnowledgePracticedInEvent` | *(always single — events link one KU at a time)* |
| Habit | `KnowledgeBuiltIntoHabit` | `KnowledgeBulkBuiltIntoHabit` |
| Choice | `KnowledgeInformedChoice` | `KnowledgeBulkInformedChoice` |
| UserEntry | `KnowledgeReflectedInEntry` | *(always single — published per APPLIES_KNOWLEDGE edge write)* |

### 1. KnowledgeAppliedInTask / KnowledgeBulkAppliedInTask
- **Increments:** `times_applied_in_tasks`
- **Updates:** `last_applied_date`
- **Weight:** 0.05 per task (max 0.25)
- **Published by:** `TasksCoreService` — single when 1 KU, bulk when 2+

### 2. KnowledgePracticedInEvent
- **Increments:** `times_practiced_in_events`
- **Updates:** `last_practiced_date`
- **Weight:** 0.05 per event (max 0.25)
- **Published by:** `EventsService` — always single-item (events link one KU at a time)

### 3. KnowledgeBuiltIntoHabit / KnowledgeBulkBuiltIntoHabit
- **Increments:** `times_built_into_habits`
- **Updates:** `last_built_into_habit_date`
- **Weight:** 0.10 per habit (max 0.30) — HIGHEST weight
- **Published by:** `HabitsLearningService` — single when 1 KU, bulk when 2+
- **Rationale:** Habits represent lifestyle integration = deepest form of applied knowledge

### 4. KnowledgeInformedChoice / KnowledgeBulkInformedChoice
- **Increments:** `choices_informed_count`
- **Updates:** `last_choice_informed_date`
- **Weight:** 0.07 per choice (max 0.15)
- **Published by:** `ChoicesCoreService` — single when 1 KU, bulk when 2+
- **Rationale:** Applying knowledge to real decisions demonstrates practical wisdom

### 5. KnowledgeReflectedInEntry
- **Increments:** `times_reflected_in_entries`
- **Updates:** `last_reflected_date`
- **Weight:** 0.07 per entry (max 0.20)
- **Published by:** TWO writers, one event, writer-agnostic handler:
  - `UserEntryProcessingService` — once per successful
    `(UserEntry)-[:APPLIES_KNOWLEDGE]->(Ku)` edge write from an explicit `@ku()`
    reference in the `EXTRACT_ACTIVITIES` pipeline (ADR-069)
  - `EntryGroundingService` — once per genuinely NEW inferred edge
    (`inferred: true`, `confidence: <similarity>`, `grounded_at`) written by the
    vector grounding pass over `pipeline: knowledge` entries (knowledge/ and
    je_pro/ doors — Entry-Enrichment PR 3). Existing edges and user-rejected
    links never re-publish; removals via the grounding remove route are
    calibration data for the threshold.
- **Rationale:** Written reflection is metacognition — consciously processing the knowledge

---

## Per-User Substance

**Global vs. Personal:** While global substance tracks how knowledge is applied across all users, **per-user substance** answers "How am I personally using this knowledge?"

### The weight table lives in exactly one place

`core/services/knowledge/user_substance.py` — `USER_SUBSTANCE_CHANNELS`. It was written out by hand in `KuIntelligenceService` and `PsIntelligenceService` until August 2026, and the Layer-0 analytics metric was about to become a third copy. Callers own their presentation (bands, prompts, status lines); they do not own the arithmetic. `tests/unit/test_user_substance_weights.py` pins the table against the numbers published above and against the `UserContext` field names it reads.

### Personal is not "global, filtered"

Three differences are deliberate and must not be reconciled by making the two agree:

| | Global (`Curriculum.substance_score()`) | Personal (`user_substance.py`) |
|---|---|---|
| **Source** | counters on the shared node, written by `KuBackend.increment_substance` with **no `user_uid`** | the six `UserContext` activity→knowledge maps, which are by construction one learner's |
| **Channels** | 5 — there is no principles counter | 6 — principles (`GROUNDED_IN_KNOWLEDGE`) counts |
| **Time decay** | exponential, 30-day half-life, per-channel `last_*_date` | **none** — the channel maps carry uids and no timestamps, so a personal decay curve is not computable from this input. The score is cumulative, provided the maps come from the unwindowed source (see below). |

Deriving a personal decay clock from engagement-edge timestamps would time a *different event*: opening a step is not applying it.

### Two sources, one calculation

The scoring functions take the six maps; they do not fetch them. **Where the maps come from decides what the score means**, and there are two sources with different temporal semantics:

| Source | Window | Use for |
|---|---|---|
| `CrossDomainBackendOperations.get_user_knowledge_channels` | **none** — every activity, any age, any status | the **cumulative** figure: "how substantiated is this for me" (the Layer-0 weekly metric) |
| `UserContext`'s six fields (`channel_maps_from_context`) | the MEGA-QUERY's planning window | a detail page answering "how am I applying this *lately*" |

The context's copies are built for **planning**, so they admit a row only if it is currently open or was touched inside the window — and **unevenly**: an ACTIVE habit is admitted at any age, while an event outside the window vanishes entirely. There is no single sentence describing what a score over that mixture means, which is why the cumulative path does not use it.

⚠ **Two silent-zero traps on the context path.** The six maps are populated **only** by `UserContextBuilder.build_rich` (`populate_graph_sourced_fields` + `populate_entry_knowledge_applied`); the standard `build` / `get_user_context` leaves them empty. And an empty map does not raise — it scores every entity a confident **0.0**. Any caller passing a context to `calculate_user_substance` must therefore use `get_rich_unified_context`.

Both sources bridge PathStep targets to the Kus they compose over the **canonical triple** `USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU` — the same three edges the substance write fan-out uses. The MEGA-QUERY rollups listed only two of the three until 2026-08-12, so knowledge reachable from a step only over `CONTAINS_KNOWLEDGE` sat in the denominator and never the numerator.

### API Endpoints

```
GET /api/ku/{uid}/my-context          → KuIntelligenceService.calculate_user_substance
GET /api/path-steps/my-context        → PsIntelligenceService.calculate_user_substance
```

Requires authentication. Returns personalized substance data for the current user.

### Per-User Calculation

Uses the same weighted scoring, but only counts THIS user's applications:

```python
from core.services.knowledge.user_substance import (
    SUBSTANCE_ACTIVITY_TYPES, build_substance_index, channel_maps_from_rows, user_substance_score,
)

# Cumulative: the unwindowed source
rows = (await cross_domain_backend.get_user_knowledge_channels(
    user_uid, list(SUBSTANCE_ACTIVITY_TYPES))).value
index = build_substance_index(channel_maps_from_rows(rows))

# Or, for a detail page that already holds a RICH context (window-bounded):
#   index = build_substance_index_from_context(rich_user_context)

score = user_substance_score(ku_uid, index)   # weights + per-channel caps, total capped at 1.0
```

Weights per instance and per-channel caps are the table at the top of this document. Counting is **per activity**: an activity that names the same Ku twice is one application of it.

### A PathStep's personal substance

A PathStep has no channels of its own — activities link to Kus. Its personal substance is the **mean** of the per-Ku scores over the Kus it teaches (`USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU` — the same triple the global write fan-out traverses). A step teaching no Ku scores **0.0**, not undefined.

### Status Messages

| User Score | Status |
|------------|--------|
| 0.8+ | "Mastered! Consider teaching others." |
| 0.7-0.79 | "Well practiced! Keep it up." |
| 0.5-0.69 | "Solid foundation. Practice more to deepen mastery." |
| 0.3-0.49 | "Applied but not yet integrated. Build habits." |
| 0.01-0.29 | "Theoretical knowledge. Apply in projects." |
| 0.0 | "Pure theory. Create tasks and practice." |

### Ruling: what the weekly summary reports for an engaged-but-unapplied step (2026-08-12)

`AnalyticsMetricsService.calculate_knowledge_metrics` selects the path steps a learner engaged with in the window, then scores each one **per-learner**. A learner routinely marks a step in progress and never carries it into a task, habit, event, entry, choice or principle. The ruling for that step:

**It scores 0.0, it lands in `theoretical_knowledge`, and it stays in the denominator.**

Why, positively — 0.0 is not a missing value here. `theoretical_knowledge` is defined as *read about it, no application*, which is precisely and completely what has happened. The alternatives were considered and rejected:

- **Excluding unapplied steps from the average** would make `avg_substance_score` *rise* as a learner takes up more material without applying it. The metric exists to say "applied knowledge, not pure theory"; an average that rewards unapplied uptake inverts it.
- **Falling back to the node's global counters** for steps with no personal activity is the contamination itself, reintroduced as a special case — and it would be worst exactly where it is most misleading, on the material the learner has done least with.

**Consequence, stated up front:** the band distribution shifts hard toward `theoretical_knowledge` and `avg_substance_score` drops, on every instance with more than one learner and on single-learner instances too (global counters pool activity across *all* Kus of a step's composition, personal scoring averages over them). This is a corrected reading, not a regression — but a stored historical report generated before 2026-08-12 is on the old basis and is not comparable to one generated after.

**`decay_warnings` under this ruling.** The key keeps its name (report-template contract) but no longer carries a decay prediction: with no personal clock there is nothing to predict from. It now lists the engaged steps whose *personal* substance is under the 0.5 review threshold — the threshold `Curriculum.needs_review()` uses — sorted least-substantiated first, capped at 10. `days_until_review` is `0` on every row, meaning "review now".

### UserContext Knowledge Fields

All 6 channels tracked:
- `task_knowledge_applied` - Tasks applying KU
- `habit_knowledge_applied` - Habits reinforcing KU
- `event_knowledge_applied` - Events practicing KU
- `choice_knowledge_informed` - Choices informed by KU
- `principle_knowledge_grounded` - Principles grounded in KU
- `entry_knowledge_applied` - UserEntries reflecting on KU (explicit `@ku()` refs via EXTRACT_ACTIVITIES ADR-069, plus inferred grounding edges; the MEGA-QUERY's `min_confidence` filter applies to the inferred `confidence` property)

---

## Life Path Alignment

**Everything flows toward the life path.** UnifiedUserContext tracks alignment:

- Your life path represents who you want to **BECOME**
- Alignment measures how much you're **LIVING** that vision
- High alignment (0.7+) = knowledge is embodied in daily life
- Low alignment (<0.5) = knowledge is theoretical, not practiced

---

## Implementation Files

| Component | Location | Purpose |
|-----------|----------|---------|
| **Substance Fields** | `/core/models/curriculum.py` | Substance fields + methods on `Curriculum` base class (the GLOBAL figure) |
| **Decay Algorithm** | `/core/models/curriculum.py` | Exponential decay, spaced repetition (global only — see Per-User Substance) |
| **Per-User Weight Table** | `/core/services/knowledge/user_substance.py` | THE six-channel table + pure scoring; read by both intelligence services and the Layer-0 metric |
| **Domain Events** | `/core/events/knowledge_substance_events.py` | 9 substance events (5 channels; task/habit/choice also have bulk forms) |
| **Event Handlers** | `/core/services/ps_service.py` | `PsService.increment_substance_metric()` |
| **Backend Write** | `/adapters/persistence/neo4j/backends/curriculum_backends.py` | `KuBackend.increment_substance()` + PathStep fan-out |
| **Event Wiring** | `/services_bootstrap/_event_wiring.py` | Subscribe PsService to substance events |
| **Life Path Fields** | `/core/services/user/unified_user_context.py` | Life alignment tracking |
| **Confidence Enum** | `/core/models/enums/activity_enums.py` | `Confidence` enum (UNCERTAIN → CERTAIN) |

---

## Design Decisions

### Why bidirectional?
- Knowledge without practice = pure theory (useless)
- Practice without knowledge = trial and error (inefficient)
- Bidirectional = theory + practice = applied knowledge

### Why weighted scoring?
- Not all practice demonstrates equal understanding
- Habits > Entries > Tasks reflects ontological hierarchy
- Lifestyle integration > metacognition > application

### Why time decay?
- Models real forgetting curves (Ebbinghaus)
- Encourages spaced repetition (proven learning science)
- Knowledge you don't use regularly isn't truly mastered

### Why event-driven?
- Zero coupling between KU and supporting domains
- Atomic updates prevent race conditions
- Full audit trail for analytics
- Easy to add new substance types (extensible)

### Why fan-out from Ku to PathStep?
- Substance data originates at Ku (the atom events reference)
- PathStep composes Kus — its substance is the aggregate of its Kus' substance
- Fan-out ensures PathStep models read real data via the generic Neo4j mapper
- Single atomic Cypher query handles both layers

### Why life path convergence?
- Users need ONE ultimate goal (prevent diffusion)
- Life path represents who you want to BECOME
- All learning should flow toward that vision
- Alignment score measures embodiment, not completion

---

**Last Updated:** August 12, 2026
**Status:** Active — the Layer-0 knowledge metric reports PER-LEARNER magnitudes; the per-user weight table is consolidated in `core/services/knowledge/user_substance.py`
