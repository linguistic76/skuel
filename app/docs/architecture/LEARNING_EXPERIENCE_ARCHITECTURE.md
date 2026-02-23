# Learning Experience Architecture

How SKUEL models a human's learning experience in Python dataclasses, Neo4j relationships, and adaptive UI.

## The Core Insight

Learning is not consuming content. Learning is what happens when knowledge changes how you act, decide, and live. SKUEL models this through three layers: **what you can learn** (Knowledge Units), **how you're learning it** (mastery tracking), and **whether it's changing your life** (substance scoring).

Every layer is a frozen Python dataclass. Every connection is a Neo4j graph relationship. Every measurement flows from real user behavior, not self-reported progress.

---

## Layer 1: What You Can Learn

### The Knowledge Unit (`Ku`)

**File:** `core/models/ku/ku.py`

A Knowledge Unit is the atomic building block of learning. It is a frozen dataclass — immutable once created, like a published textbook page.

```
Ku (frozen dataclass)
├── Identity: uid, title, content, domain
├── SEL Lens: sel_category (SELCategory | None) — optional filter, not inherent to every KU
├── Difficulty: learning_level, estimated_time_minutes, difficulty_rating (0.0-1.0)
├── Quality: quality_score, complexity, semantic_links
└── Substance: times_applied_in_tasks, times_practiced_in_events, ...
```

A KU **may** carry an `sel_category` field — a classification into the Social Emotional Learning framework. SEL is a navigation lens over KUs, not an inherent property of every piece of knowledge.

In the Python dataclass, `sel_category` is typed as `SELCategory | None` with a default of `None`. KUs without an intentional SEL classification carry `None` — no silent default is injected. 



The per-domain DTO transfer layer carries `sel_category` where applicable, and `Entity.from_dto()` defaults to `None` via `getattr()` when absent.

**The five SEL categories** (when a KU does carry one):

| SELCategory | Human Meaning | Icon |
|---|---|---|
| `SELF_AWARENESS` | Understanding your emotions, values, strengths | `core/models/enums/learning_enums.py:313` |
| `SELF_MANAGEMENT` | Managing emotions and achieving goals | `:314` |
| `SOCIAL_AWARENESS` | Understanding and empathizing with others | `:315` |
| `RELATIONSHIP_SKILLS` | Building healthy relationships | `:316` |
| `RESPONSIBLE_DECISION_MAKING` | Making ethical, constructive choices | `:317` |

The `SELCategory` enum lives in `core/models/enums/learning_enums.py:305-351`. It carries presentation logic: `get_icon()`, `get_color()`, `get_description()`. The `DOMAIN_SEL_MAPPING` (line 354) bridges activity domains into the SEL framework — principles map to self-awareness, habits to self-management, choices to responsible decision-making.

The adaptive curriculum service (`KuAdaptiveService`) uses `sel_category` as a **filter** — `find_by(sel_category=category.value)` — to surface KUs grouped by SEL competency. KUs without a meaningful SEL classification simply won't appear in category-filtered views, which is correct behavior: not all knowledge fits neatly into an SEL lens.

### How KUs Are Born: Markdown to Graph

KUs originate as Markdown files with YAML frontmatter in the Obsidian vault (`/home/mike/0bsidian/skuel/docs/`). The ingestion pipeline (`core/services/ingestion/`) parses the frontmatter and, if present, extracts the `sel_category` field. A KU's Markdown may or may not include an SEL classification — it is optional metadata, not required for ingestion.

```
yoga-fundamentals.md          core/services/ingestion/        Neo4j
┌──────────────────┐           ┌──────────────┐           ┌──────────────┐
│ ---              │           │              │           │ (:Ku {       │
│ sel_category:    │  parse    │  Unified     │  create   │   uid: "ku.  │
│   self_awareness │ ───────>  │  Ingestion   │ ───────>  │     yoga-    │
│ learning_level:  │           │  Service     │           │     fund..", │
│   beginner       │           │              │           │   sel_cate-  │
│ ---              │           └──────────────┘           │     gory:    │
│ # Yoga           │                                      │   "self_     │
│ Content here...  │                                      │     aware-   │
└──────────────────┘                                      │     ness"})  │
                                                          └──────────────┘
```

Once in Neo4j, KUs connect through graph relationships:

```cypher
(ku1:Ku)-[:REQUIRES_KNOWLEDGE]->(ku2:Ku)   // Prerequisites
(ku1:Ku)-[:ENABLES_KNOWLEDGE]->(ku2:Ku)    // What mastering this unlocks
(moc:Ku)-[:ORGANIZES]->(ku:Ku)             // MOC grouping (non-linear)
(ku:Ku)-[:USED_IN_STEP]->(ls:Ls)           // Linear curriculum
```

---

## Layer 2: How You're Learning It

### Mastery Tracking (`KuMastery`)

**File:** `core/models/ku/ku_intelligence.py:58-149`

When a user interacts with a KU, a `MASTERED` relationship is created in the graph between `:User` and `:Ku`. The `KuMastery` dataclass models what that relationship means:

```
KuMastery (frozen dataclass)
├── Identity: uid, user_uid, knowledge_uid
├── Mastery: mastery_level (MasteryLevel), mastery_score (0.0-1.0)
├── Confidence: confidence_score (0.0-1.0)
├── Velocity: learning_velocity (LearningVelocity), time_to_mastery_hours
├── Evidence: mastery_evidence, last_reviewed, last_practiced
└── Preferences: preferred_learning_method (ContentPreference)
```

The `MasteryLevel` enum (`ku_intelligence.py:23-32`) tracks a seven-stage progression that mirrors how humans actually learn:

```
UNAWARE → INTRODUCED → FAMILIAR → PROFICIENT → ADVANCED → EXPERT → MASTERED
```

The `KuInteractionService` (a sub-service of `KuService`) manages the pedagogical progression: `VIEWED` → `IN_PROGRESS` → `MASTERED`. Each transition is a graph relationship event.

### Learning Velocity and Preferences

`LearningVelocity` (`ku_intelligence.py:35-42`) tracks how fast a user learns in different domains — not as a judgment but as data for personalization. A user who learns yoga slowly but Python quickly gets different time estimates for each.

`LearningPreference` (`ku_intelligence.py:151-241`) captures what works for this specific human: preferred content types, session duration, whether they learn better with examples, whether they prefer bottom-up or top-down approaches. This profile evolves from actual learning patterns, not questionnaires.

---

## Layer 3: Whether It's Changing Your Life

### Substance Scoring (on `Ku` model)

**File:** `core/models/ku/ku.py:758-1087`

This is what makes SKUEL's learning model distinctive. The `substance_score()` method on the `Ku` dataclass measures how knowledge is **lived**, not just consumed:

| Application Type | Weight | Max | What It Measures |
|---|---|---|---|
| Habits | 0.10/each | 0.30 | Lifestyle integration — knowledge becomes behavior |
| Journals | 0.07/each | 0.20 | Metacognition — user reflects on what they learned |
| Choices | 0.07/each | 0.15 | Decision wisdom — knowledge informs real decisions |
| Events | 0.05/each | 0.25 | Practice — dedicated time applying knowledge |
| Tasks | 0.05/each | 0.25 | Application — knowledge used in real projects |

Substance decays over time using exponential decay with a 30-day half-life (`_decay_weight()` at line 835). Knowledge never fully disappears (floor at 0.2), but it fades without practice — exactly like human memory.

The substance fields on the `Ku` model (`times_applied_in_tasks`, `times_practiced_in_events`, etc.) are updated via event-driven architecture. When a user completes a task that references a KU, the `KuService` handles the `knowledge.applied_in_task` event and atomically increments the counter in Neo4j.

---

## The Adaptive Service: Connecting the Layers

### `KuAdaptiveService`

**File:** `core/services/ku/ku_adaptive_service.py`

This service answers the question: **"What should this person learn next?"** It connects all three layers.

**Personalized Curriculum Delivery** (`get_personalized_curriculum`, line 74):

```
1. Load user's learning intelligence (masteries, paths, velocity)
2. Query all KUs in the requested SEL category
3. Filter by readiness:
   - Not already mastered
   - Prerequisites met (via REQUIRES_KNOWLEDGE graph traversal)
   - Appropriate for user's current level
4. Rank by learning value:
   - Enables many future KUs (×10) — high leverage
   - Matches preferred difficulty (×20) — flow state
   - Fits available time (×15) — practical
   - Foundational / no prerequisites (×5) — unblocked
   - Quick win (×10) — momentum
5. Return top N recommendations
```

### Category Progress (`KuCategoryProgress`)

**File:** `core/models/ku/ku_progress.py:20-99`

Tracks a user's progress through one SEL category. This is a frozen dataclass that captures a snapshot:

```
KuCategoryProgress (frozen dataclass)
├── user_uid, sel_category
├── Counts: kus_mastered, kus_in_progress, kus_available, total_kus
├── Progress: completion_percentage (0-100), current_level (LearningLevel)
└── Journey: started_at, last_activity, estimated_completion_date
```

Business logic lives on the model. `determine_level()` maps completion percentage to `LearningLevel`:
- 0-24% → BEGINNER
- 25-49% → INTERMEDIATE
- 50-74% → ADVANCED
- 75-100% → EXPERT

`needs_attention()` returns true if a user started a category but hasn't touched it in 7+ days — a gentle nudge signal for the UI.

Built by `KuAdaptiveService._calculate_category_progress()` (line 261), which queries all KUs in a category, checks how many the user has mastered, and creates the frozen snapshot.

### Learning Journey (`KuLearningJourney`)

**File:** `core/models/ku/ku_progress.py:102-217`

The complete picture — progress across all five SEL categories:

```
KuLearningJourney (frozen dataclass)
├── user_uid
├── category_progress: dict[SELCategory, KuCategoryProgress]
└── overall_completion: float (0-100)
```

`get_next_recommended_category()` implements a pedagogical ordering:
1. Start with Self-Awareness (foundation of all SEL)
2. Then Self-Management (builds on self-awareness)
3. Then whichever category has least progress (balanced growth)

`is_well_rounded()` checks if no category is more than 30% behind the average — the system values breadth alongside depth.

Built by `KuAdaptiveService.get_sel_journey()` (line 242), which iterates all five `SELCategory` values and assembles the complete journey.

---

## The Facade: How Services Wire Together

### `KuService` (Facade)

**File:** `core/services/ku_service.py`

The `KuService` facade delegates to 9 sub-services via `FacadeDelegationMixin`. The adaptive curriculum methods route through:

```python
# ku_service.py:192-197
_delegations = {
    "get_personalized_curriculum": ("adaptive", "get_personalized_curriculum"),
    "get_sel_journey": ("adaptive", "get_sel_journey"),
    "track_curriculum_completion": ("adaptive", "track_curriculum_completion"),
}
```

`self.adaptive` is a `KuAdaptiveService` instance, created by the `create_ku_sub_services()` factory in `core/utils/curriculum_domain_config.py`.

---

## The UI: Making Learning Visible

### Components

**File:** `components/ku_adaptive_components.py`

Three components render the learning experience:

**`SELCategoryCard(category, progress: KuCategoryProgress)`** (line 28)
Shows one SEL category's progress. Uses `EntityCard` with a progress bar (`kus_mastered / total_kus`), count badges (mastered, in progress, available), and a "Continue Learning" link to `/ku?sel={category.value}`.

**`AdaptiveKUCard(ku: Ku, prerequisites_met: bool)`** (line 69)
Shows one recommended KU. Displays estimated time, difficulty rating, learning level badge, and prerequisite status. Links to `/ku/{ku.uid}`.

**`SELJourneyOverview(journey: KuLearningJourney)`** (line 108)
The master view. Shows overall completion percentage, a "Recommended Focus" alert (from `journey.get_next_recommended_category()`), and a grid of five `SELCategoryCard` components — one per SEL category.

### API Routes

**File:** `adapters/inbound/ku_api.py`

| Route | Returns | Renders |
|---|---|---|
| `GET /api/ku/journey` | `KuLearningJourney` (JSON) | — |
| `GET /api/ku/curriculum/{category}` | `list[Ku]` (JSON) | — |
| `GET /api/ku/journey-html` | — | `SELJourneyOverview` (HTMX fragment) |
| `GET /api/ku/curriculum-html/{category}` | — | Grid of `AdaptiveKUCard` (HTMX fragment) |

The HTML routes enable HTMX partial updates — the journey overview loads once, and clicking a category fetches that category's personalized curriculum as an HTML fragment.

---

## Complete Data Flow

```
AUTHORING                     STORAGE                    INTELLIGENCE
┌─────────┐                  ┌──────────┐               ┌──────────────────┐
│ Markdown │  Ingestion      │  Neo4j   │  MEGA-QUERY   │  UserContext      │
│ + YAML   │ ────────────>   │  Graph   │ ───────────>  │  (~240 fields)   │
│ files    │                 │          │               │                  │
└─────────┘                  │ :Ku      │               └────────┬─────────┘
                             │ :User    │                        │
USER BEHAVIOR                │ :MASTERED│               ┌────────v─────────┐
┌─────────┐  Events          │ :VIEWED  │               │ KuAdaptiveService│
│ Complete │ ────────────>   │ :OWNS    │               │                  │
│ task,    │                 │ :APPLIES │               │ 1. Load intel    │
│ build    │                 └──────────┘               │ 2. Query by SEL  │
│ habit,   │                                            │ 3. Filter ready  │
│ reflect  │                                            │ 4. Rank value    │
└─────────┘                                             └────────┬─────────┘
                                                                 │
                                                        ┌────────v─────────┐
MODELS (frozen dataclasses)                             │ KuLearningJourney│
┌───────────────────────────────┐                       │ ├─ 5 categories  │
│ Ku                            │                       │ │  └─ KuCategory │
│ ├─ sel_category: SELCategory? │                       │ │     Progress   │
│ ├─ learning_level             │                       │ └─ overall_%    │
│ ├─ difficulty_rating          │                       └────────┬─────────┘
│ └─ substance_score()          │                                │
│                               │                       ┌────────v─────────┐
│ KuMastery                     │                       │ UI Components    │
│ ├─ mastery_level              │                       │ ├─ JourneyView   │
│ ├─ learning_velocity          │                       │ ├─ CategoryCard  │
│ └─ confidence_score           │                       │ └─ KUCard        │
│                               │                       └──────────────────┘
│ KuCategoryProgress            │
│ ├─ kus_mastered / total_kus   │
│ └─ determine_level()          │
│                               │
│ KuLearningJourney             │
│ ├─ category_progress (×5)     │
│ └─ get_next_recommended()     │
└───────────────────────────────┘
```

---

## Key Files Reference

| Purpose | File |
|---|---|
| KU domain model | `core/models/ku/ku.py` |
| KU mastery + intelligence models | `core/models/ku/ku_intelligence.py` |
| Category progress + journey models | `core/models/ku/ku_progress.py` |
| SELCategory enum | `core/models/enums/learning_enums.py` |
| LearningLevel enum | `core/models/enums/learning_enums.py` |
| Adaptive curriculum service | `core/services/ku/ku_adaptive_service.py` |
| KU facade (wires sub-services) | `core/services/ku_service.py` |
| UI components | `components/ku_adaptive_components.py` |
| API routes | `adapters/inbound/ku_api.py` |
| Ingestion pipeline | `core/services/ingestion/` |
| Substance philosophy | `docs/architecture/knowledge_substance_philosophy.md` |
| Curriculum grouping patterns | `docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` |
