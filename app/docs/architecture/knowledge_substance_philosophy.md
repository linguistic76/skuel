---
title: Knowledge Substance Philosophy
created: 2025-10-17
updated: 2026-02-23
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
Learning Steps (ls) - curated knowledge + practice bundles
    ↑ built from
Articles (teaching compositions, compose atomic Kus)
    ↕ BIDIRECTIONAL enrichment
Supporting Domains - tasks, events, habits, journals, choices, principles
```

**Philosophy:** Everything in SKUEL ultimately flows toward your life path - the ONE ultimate vision of who you want to become.

---

## Bidirectional Relationship: Article/KU ↔ Supporting Domains

**Articles (teaching compositions) and atomic Kus mutually enrich Supporting Domains.** Substance scoring applies to Articles — the essay-like compositions that users interact with. Atomic Kus (`EntityType.KU`) are lightweight reference nodes composed into Articles via `USES_KU`.

### 1. Forward Direction (Article → Supporting)
- Knowledge guides what tasks to create
- Knowledge informs which events to schedule
- Knowledge shapes which habits to build
- Knowledge influences decisions/choices

### 2. Reverse Direction (Supporting → Article)
- Tasks give knowledge substance (practical application)
- Events provide practice opportunities (repetition)
- Habits integrate knowledge into lifestyle (automaticity)
- Journals demonstrate metacognition (reflection)
- Choices show decision-making capacity (judgment)

**Implementation:** Event-driven architecture enables this bidirectionality without coupling.

---

## Substance Scoring: Weighted Ontology

**Not all practice is equal.** SKUEL weights application types by ontological significance:

| Type | Weight per Instance | Max Contribution | Rationale |
|------|-------------------|------------------|-----------|
| **Habits** | 0.10 | 0.30 (3 habits) | Lifestyle integration = highest substance |
| **Journals** | 0.07 | 0.20 (3 reflections) | Metacognition = deep understanding |
| **Choices** | 0.07 | 0.15 (2 decisions) | Decision-making = practical wisdom |
| **Events** | 0.05 | 0.25 (5 events) | Practice = embodiment |
| **Tasks** | 0.05 | 0.25 (5 tasks) | Application = real-world use |

**Total possible substance:** 1.0 (100% lifestyle-integrated knowledge)

### Substance Scale

| Score Range | Classification | Meaning |
|-------------|---------------|---------|
| **0.0-0.2** | Pure theory | Read about it, no application |
| **0.3-0.5** | Applied knowledge | Tried it, some practice |
| **0.6-0.7** | Well-practiced | Regular use, developing mastery |
| **0.8-1.0** | Lifestyle-integrated | Automatic, embodied, second nature |

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

## Event-Driven Substance Updates

**All substance changes flow through domain events:**

### Publishing Events

```python
# Supporting domains publish events
class TasksService:
    async def create(self, task: Task) -> Result[Task]:
        result = await self.backend.create(task)

        # Publish substance event for each knowledge UID
        for knowledge_uid in task.applies_knowledge_uids:
            event = KnowledgeAppliedInTask(
                knowledge_uid=knowledge_uid,
                task_uid=task.uid,
                user_uid=task.user_uid,
                occurred_at=datetime.now()
            )
            await self.event_bus.publish_async(event)

        return result
```

### Subscribing to Events

```python
# KuService subscribes and updates substance atomically
class KuService:
    async def handle_knowledge_applied_in_task(self, event):
        await self.increment_substance_metric(
            ku_uid=event.knowledge_uid,
            metric='times_applied_in_tasks',
            timestamp_field='last_applied_date',
            timestamp=event.occurred_at
        )
```

### Benefits

- **Zero coupling** between domains
- **Atomic Neo4j updates** (race-condition safe)
- **Full audit trail** (every application tracked)
- **Flexible weighting** (adjust philosophy without code changes)

---

## Per-User Substance (January 2026)

**Global vs. Personal:** While global substance tracks how knowledge is applied across all users, **per-user substance** answers "How am I personally using this knowledge?"

### API Endpoint

```
GET /api/ku/{uid}/my-context
```

Requires authentication. Returns personalized substance data for the current user.

### Per-User Calculation

Uses the same weighted scoring, but only counts THIS user's applications:

```python
# Extract from UserContext
task_uids = [uid for uid, ku_list in user_context.task_knowledge_applied.items()
             if ku_uid in ku_list]
habit_uids = [uid for uid, ku_list in user_context.habit_knowledge_applied.items()
              if ku_uid in ku_list]

# Calculate user's substance score
task_score = min(0.25, len(task_uids) * 0.05)
habit_score = min(0.30, len(habit_uids) * 0.10)
# ... same weights as global calculation
user_substance_score = task_score + habit_score + event_score + journal_score + choice_score
```

### Response Structure

```json
{
    "ku_uid": "ku.python-basics",
    "user_uid": "user.mike",
    "user_substance_score": 0.45,
    "global_substance_score": 0.72,
    "breakdown": {
        "tasks": {"count": 3, "uids": [...], "score": 0.15},
        "habits": {"count": 1, "uids": [...], "score": 0.10},
        "events": {"count": 0, "uids": [], "score": 0.00},
        "journals": {"count": 0, "uids": [], "score": 0.00},
        "choices": {"count": 0, "uids": [], "score": 0.00}
    },
    "recommendations": [
        {"type": "journal", "message": "Reflect on this knowledge", "impact": "+0.07"}
    ],
    "status_message": "Applied but not yet integrated. Build habits."
}
```

### Status Messages

| User Score | Status |
|------------|--------|
| 0.8+ | "Mastered! Consider teaching others." |
| 0.7-0.79 | "Well practiced! Keep it up." |
| 0.5-0.69 | "Solid foundation. Practice more to deepen mastery." |
| 0.3-0.49 | "Applied but not yet integrated. Build habits." |
| 0.01-0.29 | "Theoretical knowledge. Apply in projects." |
| 0.0 | "Pure theory. Create tasks and practice." |

### Implementation

- **Service:** `ArticleIntelligenceService.calculate_user_substance(article_uid, user_context)`
- **Facade:** `ArticleService.get_user_article_context(article_uid, user_context)`
- **Route:** `/adapters/inbound/article_api.py` (`get_article_user_context_route`)
- **Wiring:** `user_service` passed through `services_bootstrap.py` → `ArticleService` → `ArticleIntelligenceService`

### Future: UserContext Extensions

Currently tracks:
- `task_knowledge_applied` - Tasks applying KU
- `habit_knowledge_applied` - Habits reinforcing KU

Planned additions:
- `event_knowledge_applied` - Events practicing KU
- `journal_knowledge_applied` - Journals reflecting on KU
- `choice_knowledge_applied` - Choices informed by KU

---

## Life Path Alignment

**Everything flows toward the life path.** UnifiedUserContext tracks alignment:

```python
class UnifiedUserContext:
    # The ONE ultimate learning path
    life_path_uid: str | None
    life_path_milestones: list[str]
    life_path_alignment_score: float  # 0.0-1.0

    def calculate_life_alignment(self, life_path_knowledge_uids: list[str]) -> float:
        """
        Calculate alignment based on substance scores of life path knowledge.

        Philosophy: Life alignment is NOT about completion,
        it's about LIVING the knowledge in your life path.
        """
        # Average substance across all life path knowledge
        avg_substance = sum(substance_scores) / len(life_path_knowledge_uids)
        return avg_substance
```

### Philosophy

- Your life path represents who you want to **BECOME**
- Alignment measures how much you're **LIVING** that vision
- High alignment (0.7+) = knowledge is embodied in daily life
- Low alignment (<0.5) = knowledge is theoretical, not practiced

---

## Substance Dashboard UI

**Visibility drives action.** UI components visualize substance with color-coded feedback to guide users toward mastery.

### SubstanceScoreCard Component

**Location:** `/ui/substance_dashboard.py` (lines 47-80)

The primary component displaying substance status with color-coded visual feedback:

```python
def SubstanceScoreCard(score: float, ku_title: str) -> FT:
    """
    Display substance score with color-coded status levels.

    Status Levels:
    - Theoretical (<0.2): Red - No application
    - Building (0.2-0.4): Orange - Early practice
    - Practicing (0.4-0.7): Yellow - Developing mastery
    - Well-practiced (≥0.7): Light green - Strong foundation
    - Mastered (≥0.8): Dark green - Lifestyle integrated
    """
```

**Status Level Table:**

| Score Range | Status | Color | Badge | Message |
|-------------|--------|-------|-------|---------|
| **0.0-0.19** | Theoretical | Red | `badge-error` | Pure theory - no application yet |
| **0.2-0.39** | Building | Orange | `badge-warning` | Early practice - keep applying |
| **0.4-0.69** | Practicing | Yellow | `badge-info` | Developing mastery - practice more |
| **0.7-0.79** | Well-practiced | Light green | `badge-success` | Strong foundation - maintain practice |
| **0.8-1.0** | Mastered | Dark green | `badge-success` | Lifestyle integrated - embodied knowledge |

**Color-Coded Feedback System:**

The component uses MonsterUI badge classes to provide immediate visual feedback:
- **Red (badge-error):** Signals urgent need for practice
- **Orange (badge-warning):** Encourages initial application
- **Yellow (badge-info):** Motivates continued practice
- **Green (badge-success):** Reinforces mastery achievement

**Example Rendering:**

```python
# score = 0.15 → Red "Theoretical"
Div(
    Span("15%", cls="text-2xl font-bold"),
    Span("Theoretical", cls="badge badge-error ml-2"),
    Div("Pure theory - no application yet", cls="text-sm text-gray-600"),
    cls="substance-score-card"
)

# score = 0.85 → Dark Green "Mastered"
Div(
    Span("85%", cls="text-2xl font-bold"),
    Span("Mastered", cls="badge badge-success ml-2"),
    Div("Lifestyle integrated - embodied knowledge", cls="text-sm text-gray-600"),
    cls="substance-score-card"
)
```

### Other Dashboard Components

- **SubstanceBreakdownCard** - Detailed view showing substance by type (tasks: 0.15, habits: 0.30, etc.)
- **SubstanceRecommendationsCard** - Actionable suggestions to increase substance ("Build a daily habit")
- **SubstanceReviewCard** - Spaced repetition schedule based on decay predictions

**Philosophy:** Users should SEE how knowledge is (or isn't) integrated into life. Color-coded status provides intuitive guidance toward mastery without cognitive load.

---

## Implementation Files

| Component | Location | Purpose |
|-----------|----------|---------|
| **Substance Fields** | `/core/models/article/article.py` | Substance fields on `Article` model (extends Curriculum → Entity) |
| **Decay Algorithm** | `/core/models/article/article.py` | Exponential decay, spaced repetition |
| **Domain Events** | `/core/events/ku_events.py` | 5 substance events |
| **Event Listeners** | `/core/services/article_service.py` | Atomic substance updates |
| **Event Wiring** | `/services_bootstrap.py` | Subscribe KuService to events |
| **Dashboard UI** | `/ui/substance_dashboard.py` | Substance visualization (Article-level) |
| **Life Path Fields** | `/core/services/user/unified_user_context.py` | Life alignment tracking |

---

## Design Decisions

### Why bidirectional?
- Knowledge without practice = pure theory (useless)
- Practice without knowledge = trial and error (inefficient)
- Bidirectional = theory + practice = applied knowledge

### Why weighted scoring?
- Not all practice demonstrates equal understanding
- Habits > Journals > Tasks reflects ontological hierarchy
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

### Why life path convergence?
- Users need ONE ultimate goal (prevent diffusion)
- Life path represents who you want to BECOME
- All learning should flow toward that vision
- Alignment score measures embodiment, not completion

---

## Substance Events Catalog

**Location:** `/core/events/ku_events.py`

### 1. KnowledgeAppliedInTask
- **Increments:** `times_applied_in_tasks`
- **Updates:** `last_applied_date`
- **Weight:** 0.05 per task
- **Published by:** TasksService

### 2. KnowledgePracticedInEvent
- **Increments:** `times_practiced_in_events`
- **Updates:** `last_practiced_date`
- **Weight:** 0.05 per event
- **Published by:** EventsService

### 3. KnowledgeBuiltIntoHabit
- **Increments:** `times_built_into_habits`
- **Updates:** `last_built_into_habit_date`
- **Weight:** 0.10 per habit (HIGHEST)
- **Published by:** HabitsService
- **Rationale:** Habits represent lifestyle integration

### 4. KnowledgeReflectedInJournal
- **Increments:** `journal_reflections_count`
- **Updates:** `last_reflected_date`
- **Weight:** 0.07 per reflection
- **Published by:** JournalService
- **Rationale:** Reflection demonstrates metacognition

### 5. KnowledgeInformedChoice
- **Increments:** `choices_informed_count`
- **Updates:** `last_choice_informed_date`
- **Weight:** 0.07 per choice
- **Published by:** ChoiceService
- **Rationale:** Applying knowledge to decisions = practical wisdom

---

## Example: Full Lifecycle

### 1. User Creates Task
```python
task = Task(
    title="Write Python type hints for API endpoints",
    applies_knowledge_uids=["ku.python.type_hints"]
)
await tasks_service.create(task)
```

### 2. Event Published
```python
event = KnowledgeAppliedInTask(
    knowledge_uid="ku.python.type_hints",
    task_uid="task.123",
    user_uid="user.mike",
    occurred_at=datetime.now()
)
```

### 3. KuService Updates Substance
```cypher
MATCH (ku:Curriculum {uid: "ku.python.type_hints"})
SET ku.times_applied_in_tasks = COALESCE(ku.times_applied_in_tasks, 0) + 1,
    ku.last_applied_date = $timestamp,
    ku._substance_cache_timestamp = NULL
```

### 4. Substance Score Recalculated
```python
substance_score = min(1.0, sum([
    min(0.25, tasks * 0.05),    # 1 task = 0.05
    min(0.25, events * 0.05),   # 0 events = 0.00
    min(0.30, habits * 0.10),   # 0 habits = 0.00
    min(0.20, journals * 0.07), # 0 journals = 0.00
    min(0.15, choices * 0.07)   # 0 choices = 0.00
]) * decay_weight)
# = 0.05 * 1.0 (no decay yet) = 0.05 (Pure theory → Applied)
```

### 5. User Sees Dashboard
- Substance Score: 5% (Applied knowledge)
- Status: "Needs more practice"
- Recommendation: "Build habit to practice Python type hints daily"

---

## Related Documentation

- [Substance Tracking Implementation](/home/mike/skuel/app/SUBSTANCE_TRACKING_IMPLEMENTATION.md)
- [Knowledge Events Catalog](/home/mike/skuel/app/core/events/ku_events.py)
- [Substance Dashboard Components](/home/mike/skuel/app/ui/substance_dashboard.py)
- [Article Model Implementation](/home/mike/skuel/app/core/models/article/article.py)
- [Event-Driven Architecture Guide](/home/mike/0bsidian/skuel/docs/guides/EVENT_DRIVEN_MIGRATION_GUIDE.md)

---

## Future Enhancements

### Planned
- **Substance decay alerts** - Notify before knowledge drops below 0.5
- **Practice reminders** - Suggested tasks/events to maintain substance
- **Substance leaderboards** - Gamify knowledge application
- **Cross-domain substance** - Track how KUs are applied across domains

### Under Consideration
- **Collaborative substance** - Share substance data with learning partners
- **Substance predictions** - ML-based predictions of decay curves
- **Adaptive weighting** - Personalize weights based on learning style
- **Substance badges** - Visual achievements for well-practiced knowledge

---

**Last Updated:** February 23, 2026
**Status:** Active - Core philosophy driving substance tracking feature
**Recent:** KU-Activity Integration Enhancement (per-user substance calculation)
