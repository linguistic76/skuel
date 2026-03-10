---
name: zpd
description: >
  Expert guide for SKUEL's Zone of Proximal Development — the pedagogical gravity well.
  Use when working on ZPD assessment, readiness scoring, blocking gaps, compound evidence,
  behavioral readiness, recommended actions, ZPD snapshots, or when asking "what should this
  learner do next?". TRIGGER when: implementing learning recommendations, working on Askesis
  intelligence, modifying ZPDService, ZPDBackend, ZPDSnapshotHandler, UserContext.zpd_assessment,
  DailyPlanningMixin P5 learning, or when designing features that need curriculum-aware
  learner positioning.
allowed-tools: Read, Grep, Glob
---

# Zone of Proximal Development (ZPD)

> "The intelligence layer that makes the learning loop adaptive."

ZPD is the capstone computation on UserContext — it synthesizes curriculum graph traversal,
behavioral signals, life path alignment, and compound evidence into actionable learning
priorities. Without ZPD, intelligence services react to isolated domain signals. With ZPD,
the system knows where the learner is in the curriculum, what they're ready for, and how
it connects to their life direction.

---

## Where ZPD Fits: The System Layers

```
┌────────────────────────────────────────────┐
│  5. Semantics (coherence)                  │
├────────────────────────────────────────────┤
│  4. Knowledge Graph (structural memory)    │
├────────────────────────────────────────────┤
│  3. Saved Interactions (compounding)       │
├────────────────────────────────────────────┤
│  2. ZPD + UserContext (intelligence) ◄──── │  THIS SKILL
├────────────────────────────────────────────┤
│  1. Learning Loop (base)                   │
└────────────────────────────────────────────┘
```

ZPD is **Layer 2** — the intelligence layer. It reads the knowledge graph (Layer 4) to
understand curriculum structure, reads saved interactions (Layer 3) to understand learner
engagement, and feeds the learning loop (Layer 1) with what to do next. The learning loop
is the base; ZPD makes it adaptive.

---

## Architecture

```
ZPDBackend (adapters/persistence/neo4j/zpd_backend.py)
    ↓  raw graph data (9-tuple: zones, prereqs, evidence, submissions)
ZPDService (core/services/zpd/zpd_service.py)
    ↓  readiness scoring + behavioral enrichment + recommended actions
ZPDAssessment (core/models/zpd/zpd_assessment.py)
    ↓  frozen dataclass snapshot consumed by:
    ├── UserContext.zpd_assessment (capstone of build_rich())
    ├── DailyPlanningMixin P5 (learning priority)
    ├── LearningIntelligenceMixin (optimal next learning steps)
    └── AskesisService (pedagogical scaffolding)
```

### Service Layer (business logic)

**File:** `core/services/zpd/zpd_service.py`

```python
class ZPDService:
    def __init__(
        self,
        backend: ZPDBackendOperations,
        choices_intelligence: ChoicesIntelligenceService | None = None,
        habits_intelligence: HabitsIntelligenceService | None = None,
    ) -> None: ...

    # PUBLIC API (ZPDOperations protocol)
    async def assess_zone(
        self, user_uid: str, context: UserContext | None = None
    ) -> Result[ZPDAssessment]: ...

    async def get_proximal_ku_uids(self, user_uid: str) -> Result[list[str]]: ...

    async def get_readiness_score(self, user_uid: str, ku_uid: str) -> Result[float]: ...
```

**Key private methods:**
- `_compute_readiness_scores()` — fraction of prerequisites met per proximal KU
- `_compute_behavioral_readiness()` — choices (65%) + habits (35%) signals
- `_build_zone_evidence()` — compound mastery tracking per current-zone KU
- `_build_recommended_actions()` — three action types: unblock, learn, reinforce

### Backend Layer (Cypher queries)

**File:** `adapters/persistence/neo4j/zpd_backend.py`

Single-roundtrip `_ZONE_QUERY` — 6 steps in one Cypher query:

1. **Current zone** — KUs via APPLIES_KNOWLEDGE (tasks, journals) + REINFORCES_KNOWLEDGE (habits). Returns per-source lists for compound evidence.
2. **Proximal zone** — adjacent via PREREQUISITE_FOR, COMPLEMENTARY_TO, LP ORGANIZES. Excludes already-engaged KUs.
3. **Prerequisite graph** — total vs met prerequisites per proximal KU (readiness scoring).
4. **Engaged Learning Paths** — LPs the user is partially traversing.
5. **Blocking gaps** — prerequisite KUs not met that gate proximal KUs.
6. **Submission scores** — via `FULFILLS_EXERCISE -> APPLIES_KNOWLEDGE` join.

**Guard:** `get_ku_count()` — ZPD requires 3+ KUs in the curriculum graph. Below threshold, returns empty assessment.

### Assessment Model

**File:** `core/models/zpd/zpd_assessment.py`

```python
@dataclass(frozen=True)
class ZoneEvidence:
    ku_uid: str
    submission_count: int = 0
    best_submission_score: float = 0.0
    habit_reinforcement: bool = False
    task_application: bool = False
    journal_application: bool = False

    @property
    def signal_count(self) -> int: ...     # count of active signal types (0-4)
    @property
    def is_confirmed(self) -> bool: ...    # True when 2+ signal types


@dataclass(frozen=True)
class ZPDAction:
    entity_uid: str
    entity_type: str       # "article"
    action_type: str       # "learn", "reinforce", "unblock"
    priority: float        # 0.0-1.0
    rationale: str
    ku_uid: str | None = None


@dataclass(frozen=True)
class ZPDAssessment:
    current_zone: list[str]              # KU UIDs engaged
    proximal_zone: list[str]             # KU UIDs structurally adjacent, not engaged
    engaged_paths: list[str]             # LP UIDs partially traversed
    readiness_scores: dict[str, float]   # proximal KU → readiness 0.0-1.0
    blocking_gaps: list[str]             # prerequisite KU UIDs not met
    behavioral_readiness: float          # 0.0-1.0 aggregate

    # Life path integration
    life_path_alignment: float = 0.0
    life_path_uid: str | None = None

    # Recommended actions — three types
    recommended_actions: tuple[ZPDAction, ...] = ()

    # Zone evidence tracking (compound mastery)
    zone_evidence: dict[str, ZoneEvidence] = field(default_factory=dict)

    # Submission-derived scores
    submission_scores: dict[str, float] = field(default_factory=dict)

    def is_empty(self) -> bool: ...
    def top_proximal_ku_uids(self, n=5) -> list[str]: ...
    def top_recommended_actions(self, n=5) -> list[ZPDAction]: ...
    def confirmed_zone_uids(self) -> list[str]: ...
```

### Protocols

**File:** `core/ports/zpd_protocols.py`

```python
@runtime_checkable
class ZPDBackendOperations(Protocol):
    async def get_ku_count(self) -> int: ...
    async def get_zone_data(self, user_uid: str) -> Result[tuple[...]]: ...

@runtime_checkable
class ZPDOperations(Protocol):
    async def assess_zone(self, user_uid: str, context: UserContext | None = None) -> Result[ZPDAssessment]: ...
    async def get_proximal_ku_uids(self, user_uid: str) -> Result[list[str]]: ...
    async def get_readiness_score(self, user_uid: str, ku_uid: str) -> Result[float]: ...
```

---

## Three Action Types

ZPD generates recommended actions that reflect the learning loop:

| Action | Priority | When | Loop Role |
|--------|----------|------|-----------|
| **unblock** | 0.9 (highest) | Prerequisite KU blocks proximal KUs | Removes structural barriers |
| **learn** | readiness × 0.5 + alignment × 0.3 + behavior × 0.2 | Proximal KU ready for engagement | Advances the zone |
| **reinforce** | (1 - signal_strength) × 0.4 + alignment × 0.3 + behavior × 0.3 | Current-zone KU has < 2 signal types | Compounds mastery |

**Unblock** actions are always highest priority — a blocking gap is the most leveraged
learning move because it unlocks the most new territory.

**Learn** actions advance the zone by engaging new KUs. Priority favors KUs where
prerequisites are met and that align with the life path.

**Reinforce** actions target current-zone KUs with thin evidence. A KU with only 1
signal type (e.g., just a task) needs a second signal type (e.g., a journal reflection)
to reach compound-confirmed status.

---

## Behavioral Readiness

Behavioral readiness enriches zone assessment with signals about *how the learner is living*:

### Choices Intelligence (65% weight)

```python
choices_score = (
    adherence * 0.35       # principle adherence
    + consistency * 0.35   # decision consistency
    + quality_rate * 0.20  # high-quality decision rate
    - conflict_penalty     # min(0.25, conflicts * 0.05)
)
```

### Habits Intelligence (35% weight)

```python
habits_score = mean_reinforcement_strength - at_risk_penalty
# mean_reinforcement_strength: mean of habit strengths overlapping current_zone
# at_risk_penalty: min(0.20, at_risk_count * 0.05)
```

### Combined

```python
if both available:    behavioral = choices * 0.65 + habits * 0.35
if only choices:      behavioral = choices_score
if only habits:       behavioral = habits_score
if neither:           behavioral = 0.5  # neutral default (CORE tier)
```

---

## Event-Driven Snapshot Persistence

**File:** `core/services/zpd/zpd_event_handler.py`

`ZPDSnapshotHandler` takes ZPD snapshots on pedagogically significant events:

| Event | Trigger | Signal |
|-------|---------|--------|
| `SubmissionApproved` | Student work validated | Mastery signal |
| `ReportSubmitted` | Teacher feedback delivered | Feedback loop closed |
| `KnowledgeMastered` | KU mastery confirmed | Zone shift |
| `LearningStepCompleted` | Curriculum progress | LP advancement |
| `LearningPathProgressUpdated` | LP milestone | Path progression |

**Snapshot Backend:** `adapters/persistence/neo4j/zpd_snapshot_backend.py`
- Single `:ZPDHistory` node per user (MVP — no history array)
- Fields: `latest_assessed_at`, zone counts, behavioral readiness, life path alignment, trigger event, snapshot count
- MERGE on `(User)-[:HAS_ZPD_HISTORY]->(ZPDHistory)`

---

## UserContext Integration

ZPD is the **capstone computation** of `build_rich()`:

```python
# In UserContextBuilder.build_rich():
# ... all other context fields populated first (~250 fields) ...
# ZPD runs LAST — it synthesizes everything above
if zpd_service is not None:
    assessment = await zpd_service.assess_zone(user_uid, context=context)
    context.zpd_assessment = assessment.value
```

**Field:** `UserContext.zpd_assessment: ZPDAssessment | None`
- `None` on standard `build()` or CORE tier
- Populated only on `build_rich()` with FULL intelligence tier

**Consumers:**
- `DailyPlanningMixin.get_ready_to_work_on_today()` — P5 Learning: uses `recommended_actions`
- `LearningIntelligenceMixin.get_optimal_next_learning_steps()` — primary ranking signal
- `AskesisService` — reads assessment for scaffolding decisions

---

## Implementation Checklist

When modifying ZPD, verify:

1. **Backend query returns all 9 tuple elements** — current_zone, proximal_zone, engaged_paths, prereq_data, blocking_gaps, task_engaged, journal_engaged, habit_engaged, submission_data
2. **No APOC in queries** — SKUEL001 compliance; use pure Cypher for set operations
3. **Guard condition preserved** — `get_ku_count() < 3` returns empty assessment
4. **Behavioral readiness defaults to 0.5** when intelligence services unavailable
5. **All three action types generated** — unblock, learn, reinforce
6. **ZPDAssessment is frozen** — immutable snapshot, no mutations after creation
7. **Event handler wired** — check `services_bootstrap.py` for event subscriptions
8. **Protocol compliance** — `ZPDOperations` and `ZPDBackendOperations` both `@runtime_checkable`

---

## Anti-Patterns

### Don't query the graph from ZPDService

```python
# WRONG — ZPDService should not contain Cypher
class ZPDService:
    async def assess_zone(self):
        records = await self._driver.execute_query("MATCH ...")  # No!

# CORRECT — delegate to ZPDBackend
class ZPDService:
    async def assess_zone(self):
        graph_result = await self._backend.get_zone_data(user_uid)
```

### Don't use ZPD on CORE tier

```python
# WRONG — ZPD is FULL tier only
context = await builder.build(user_uid)  # standard build
actions = context.zpd_assessment.top_recommended_actions()  # None!

# CORRECT — check tier
if context.zpd_assessment is not None:
    actions = context.zpd_assessment.top_recommended_actions()
```

### Don't skip compound evidence

```python
# WRONG — treating any engagement as "mastered"
if ku_uid in assessment.current_zone:
    mark_as_mastered(ku_uid)  # One signal ≠ mastery

# CORRECT — require compound evidence
evidence = assessment.zone_evidence.get(ku_uid)
if evidence and evidence.is_confirmed:
    mark_as_mastered(ku_uid)  # 2+ signal types
```

### Don't ignore blocking gaps

```python
# WRONG — recommending proximal KUs without checking gaps
for ku_uid in assessment.proximal_zone:
    recommend(ku_uid)

# CORRECT — unblock actions first, then learn
actions = assessment.top_recommended_actions()
# Actions are pre-sorted: unblock (0.9) > learn > reinforce
```

---

## Key Source Files

| File | Purpose |
|------|---------|
| `core/services/zpd/zpd_service.py` | Business logic — readiness, behavioral enrichment, actions |
| `core/services/zpd/zpd_event_handler.py` | Event-driven snapshot persistence |
| `core/models/zpd/zpd_assessment.py` | ZPDAssessment, ZoneEvidence, ZPDAction frozen dataclasses |
| `core/ports/zpd_protocols.py` | ZPDOperations + ZPDBackendOperations protocols |
| `adapters/persistence/neo4j/zpd_backend.py` | Cypher zone traversal query |
| `adapters/persistence/neo4j/zpd_snapshot_backend.py` | ZPDHistory node persistence |
| `docs/user-guides/zpd.md` | User-facing ZPD guide |
| `docs/roadmap/zpd-service-deferred.md` | Design rationale |
| `docs/architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md` | Pedagogical vision |

---

## Related Skills

- **[learning-loop](../learning-loop/SKILL.md)** — The base layer ZPD serves
- **[user-context-intelligence](../user-context-intelligence/SKILL.md)** — Consumes ZPDAssessment
- **[neo4j-cypher-patterns](../neo4j-cypher-patterns/SKILL.md)** — Graph query patterns used in ZPDBackend
- **[base-analytics-service](../base-analytics-service/SKILL.md)** — Analytics that read zone data
- **[prompt-templates](../prompt-templates/SKILL.md)** — Askesis templates that consume ZPD context
