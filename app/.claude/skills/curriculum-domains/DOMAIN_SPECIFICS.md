# Curriculum Domain Specifics

> Special features and quirks for each Curriculum Domain.

## PS (PathStep) — THE Curriculum Content Entity

**Purpose:** THE curriculum content entity. Composes atomic Kus into coherent learning content and sits within a LearningPath. `PathStep` extends `Curriculum` in the model hierarchy. There is no `Lesson` entity.

**Sub-services (14 slots):** 12 from the specialized factory `create_ps_sub_services()` (`core/services/curriculum_domain_config.py`), plus `progress` and the optional `ai`, which the facade builds.

| Sub-service | Purpose |
|-------------|---------|
| `PsCoreService` | CRUD operations + persistence (extends BaseService) |
| `PsSearchService` | Text search, filtering (extends BaseService) |
| `PsGraphService` | Graph traversal, prerequisites, hub scores |
| `PsSemanticService` | Semantic relationship management |
| `PsPracticeService` | Event-driven practice tracking |
| `PsMasteryService` | Pedagogical tracking (VIEWED → IN_PROGRESS → MASTERED) |
| `PsAdaptiveService` | Adaptive learning recommendations |
| `PsApplicationDiscoveryService` | Reverse relationship queries via generic `find_activities_connected_to_knowledge()` |
| `PsContextService` | Context-first knowledge recommendations (`*_for_user` methods) |
| `PsOrganizationService` | `ORGANIZES` relationships — non-linear navigation (MOC pattern) |
| `PsIntelligenceService` | Readiness assessment, practice analysis, substance |
| `PsProgressService` | KU completion progress (event-driven; built by the facade) |

Plus optional `PsAIService` (`ai`, FULL tier only — LLM / embedding features).

**Factory:** `create_ps_sub_services()` — specialized. It builds relationships, then intelligence (which `PsSemanticService` takes), then the rest; `PsCoreService` takes no intelligence. All sub-services receive `PsBackend` (as `repo` or `backend`). All Cypher lives on `PsBackend`, decomposed into 5 domain-specific mixins: `_OrganizesMixin`, `_LearningStateMixin`, `_SemanticMixin`, `_KnowledgeContextMixin`, `_AdaptiveMixin`.

**Unique Features:**
- **Substance tracking** — measures how knowledge is LIVED. Substance comes from the learner's
  own activities pointing AT the knowledge, not from edges the PathStep authors. The weights and
  caps are `USER_SUBSTANCE_CHANNELS` (`core/services/knowledge/user_substance.py`):

  | Channel | Weight (cap) | Where the edge comes from |
  |---------|--------------|---------------------------|
  | Tasks | 0.05 (0.25) | `connections.applies_knowledge` on the Task → `APPLIES_KNOWLEDGE` |
  | Habits | 0.10 (0.30) | `connections.reinforces_knowledge` on the Habit → `REINFORCES_KNOWLEDGE` |
  | Events | 0.05 (0.25) | `connections.applies_knowledge` on the Event → `APPLIES_KNOWLEDGE` |
  | Entries | 0.07 (0.20) | **Pipeline-driven.** `(UserEntry)-[:APPLIES_KNOWLEDGE]->(Ku)` from explicit `@ku()` refs (EXTRACT_ACTIVITIES, ADR-069; far end admitted as a published Ku or PathStep by `UserEntryService.link_applied_knowledge`) and vector grounding (`EntryGroundingService`, published Kus only); both publish `KnowledgeReflectedInEntry` |
  | Choices | 0.07 (0.15) | `connections.informed_by_knowledge` on the Choice → `INFORMED_BY_KNOWLEDGE` |
  | Principles | 0.07 (0.15) | `connections.grounded_in_knowledge` on the Principle → `GROUNDED_IN_KNOWLEDGE` |

  The PathStep's own activity fields (`habit_uids`, `task_uids`, `event_uids`, `goal_uids`,
  `principle_uids`, `choice_uids`) draw `BUILDS_HABIT`, `ASSIGNS_TASK`, … — static practice
  assignment, scored by `PsIntelligenceService.get_practice_summary`, not substance. Do not
  look for a `connections.reflects_knowledge` field; it does not exist. See
  `/docs/guides/YAML_AUTHORING_GUIDE.md`.
- **Per-user context** — `calculate_user_substance(ps_uid, user_context)` for personalized metrics (needs a RICH context).
- **Semantic relationships** — REQUIRES_KNOWLEDGE, ENABLES_KNOWLEDGE, HAS_NARROWER, RELATED_TO.
- **Content ingestion** — YAML frontmatter + Markdown body.
- **Non-linear organization** — any PathStep can organize other PathSteps via `ORGANIZES` (emergent MOC pattern).
- **Composes atomic Kus** — `(PathStep)-[:USES_KU]->(Ku)` relationship.
- **Learning-state tracking** — `VIEWED` / `IN_PROGRESS` / `MASTERED` / `BOOKMARKED` / `MARKED_AS_READ` user-owned edges.

**Key Methods:**
```python
# Get PathStep with full context
await ps_service.intelligence.get_with_context(uid)

# Calculate substance for user (a RICH UserContext — build_rich())
await ps_service.intelligence.calculate_user_substance(ps_uid, user_context)

# Non-linear organization (MOC pattern) — PathStep subjects only
await ps_service.organization.organize(parent_uid, child_uid, order=1)
await ps_service.organization.get_organized_children(parent_uid)
await ps_service.organization.get_organization_view(parent_uid, max_depth=3)
await ps_service.organization.find_organizers(ps_uid)   # Multiple parents possible
await ps_service.organization.is_organizer(ps_uid)
await ps_service.organization.list_root_organizers()

# Prev/next sibling navigation in MOC ORGANIZES order
await ps_service.organization.get_navigation(ps_uid)

# Readiness and practice
await ps_service.intelligence.is_ready(ps_uid, completed_uids)
await ps_service.intelligence.get_practice_summary(ps_uid)

# Adaptive curriculum
await ps_service.adaptive.get_personalized_curriculum(user_uid, sel_category, limit=10)
await ps_service.adaptive.get_sel_journey(user_uid)

# Semantic neighborhood
await ps_service.semantic.get_semantic_neighborhood(ps_uid)

# ps_service.progress is event-driven (handle_knowledge_mastered) — nothing to call
```

**UID Format:** `ps.{namespace}.{slug}` authored (e.g., `ps.mindfulness.breath-awareness-basics`). PathSteps have no API create.

**MOC Pattern Note:** MOC is NOT an EntityType. Any PathStep (or other Entity) "is" an organizer when it has outgoing `ORGANIZES` relationships. There is no separate `MocService` or `core/services/moc/` directory — this is managed by `PsOrganizationService`.

---

## KU (Atomic Knowledge Unit) — The Atom

**Purpose:** Atomic knowledge unit — a single definable thing (concept, state, principle, substance, practice, value). `Ku` extends `Entity` directly (lightweight, like Resource).

**Sub-services (4):** Created via `create_curriculum_sub_services(backend, graph_intel, event_bus)` — the Ku-only factory. The facade also keeps the `KuBackend` for reverse traversal and learning state.

| Sub-service | Purpose |
|-------------|---------|
| `KuCoreService` | CRUD operations |
| `KuSearchService` | Text search, filtering |
| `UnifiedRelationshipService` | Graph relationship operations |
| `KuIntelligenceService` | Usage summary, per-user substance, dual-track mastery, per-Ku insights |

**Unique Features:**
- **Lightweight** — extends Entity directly, not Curriculum.
- **Composed into PathSteps** — `(PathStep)-[:USES_KU]->(Ku)` relationship.
- **Trained by PathSteps** — `(PathStep)-[:TRAINS_KU]->(Ku)` relationship.
- **Aliases + NOUS topics** — `aliases` (alternative names), `nous` (NOUS topic membership — the category vocabulary), `sel_category` (SELCategory enum). The former `namespace`/`ku_category`/`source` fields were retired 2026-07-06.
- **SEL organization** — `sel_category` (SELCategory enum) classifies Kus by SEL competency. It is a search filter (`sel_category` on `/search/results`), not a page; `/library/ku` lists the learner's bookmarked Ku.
- **Reference node** — ontology/reference, not a unit for learning.

**Key Methods:**
```python
# Ku has no CRUD API; the service mints generated Kus (EXTRACT_ACTIVITIES)
await ku_service.create_ku(title="Python basics", aliases=["py-basics"])
await ku_service.search.search(query)

# Learning state is Ku-native (KuBackend) — Ku never depends on PsService
await ku_service.mark_as_studying(user_uid, ku_uid)    # IN_PROGRESS (the route caps it at 5)
await ku_service.mark_as_understood(user_uid, ku_uid)  # MASTERED
# Both land on a PUBLISHED Ku only — any other uid is Errors.not_found("Ku"), alike

# Find PathSteps that use this Ku
await ku_service.get_path_steps(ku_uid)
```

**UID Format:** `ku.{ns}.{slug}` authored (content vault); `ku_{slug}_{random}` generated by `create_ku`. Both are sanctioned; never read the kind from the prefix.

---

## LP (LearningPath) — The Path

**Purpose:** A complete, ordered sequence of PathSteps — the full staircase from start to mastery.

**Sub-services (5 + `ai`):**

| Sub-service | Purpose |
|-------------|---------|
| `LpCoreService` | CRUD + HAS_STEP management (extends BaseService, requires PsService) |
| `LpSearchService` | Text search, filtering (extends BaseService) |
| `UnifiedRelationshipService` | Graph relationship operations (`LP_CONFIG`) |
| `LpProgressService` | Mastery progress (event-driven) |
| `LpIntelligenceService` | Validation, analysis, adaptive step, context |
| `LpAIService` | Optional LLM features (`ai`, FULL tier) |

**Factory:** `create_lp_sub_services()` — specialized (requires cross-domain `PsService` dependency). No `executor` parameter — all Cypher delegated to `LpBackend`.

**Backend:** `LpBackend` (3 domain-specific mixins): `_lp_step_mixin` (step management + path CRUD), `_lp_progress_mixin` (KU mastery + search queries), `_lp_intelligence_mixin` (intelligence + adaptive learning).

**Unique Features:**
- **Cross-domain dependency** — `LpCoreService` requires `PsService`.
- **Validation** — ensures prerequisite chains are valid.
- **Adaptive sequencing** — personalizes step order based on user progress.
- **Goal alignment** — `ALIGNED_WITH_GOAL` relationship.
- **Milestone tracking** — `HAS_MILESTONE_EVENT` relationship.
- **Life path destination** — a user designates one LP with `(User)-[:ULTIMATE_PATH]->(LearningPath)`; their Goals, Principles and other activities point at it with `SERVES_LIFE_PATH`.

**Key Methods:**
```python
# Validate learning path prerequisites
await lp_service.intelligence.validate_path_prerequisites(lp_uid)

# Get next adaptive step for user
# (staged — no surface calls it; docs/roadmap/lp-adaptive-reads.md)
await lp_service.intelligence.get_next_adaptive_step(step_uid, user_uid)

# Identify blockers
await lp_service.intelligence.identify_path_blockers(lp_uid, user_uid)

# Get optimal path recommendation
await lp_service.intelligence.get_optimal_path_recommendation(user_uid, goal_domain)
```

A learning path is authored in the content vault (`connections.contains_steps` writes `HAS_STEP`);
`LpService` only reads it (ADR-091).

**Relationships:**
- `HAS_STEP` — path structure (ordered).
- `REQUIRES_KNOWLEDGE` — knowledge prerequisites.
- `ALIGNED_WITH_GOAL` — goal alignment.
- `EMBODIES_PRINCIPLE` — principle alignment.
- `HAS_MILESTONE_EVENT` — milestone tracking.
- `OPENS_LEARNING_PATH` (incoming) — an entity that opens this path.
- `ENROLLED_IN` (incoming, from User) — explicit enrollment.
- `ULTIMATE_PATH` (incoming, from User) / `SERVES_LIFE_PATH` (incoming, from activities) — life path.

**UID Format:** `lp.{namespace}.{slug}` authored. LearningPaths have no API create.

---

## Exercise — The Learning Loop Anchor

**Purpose:** The instruction template that closes the learning loop. Without Exercise, the loop (Exercise → UserEntry → EntryReport → RevisedExercise) cannot start. Exercise is applied knowledge, subordinate to PathStep in the hierarchy (`is_applied_knowledge()`), though it is a full EntityType of its own.

**One scope, one door (ADR-091 S2, S4):** an exercise is curriculum — authored and edited only in the content vault, owned by no user. `CURRICULUM` is its one scope (`ExerciseScope`, the model default; ingestion refuses any other value). Its vault file names its teacher (`teacher:` → `(Exercise)-[:REVIEWED_BY]->(User)`, a TEACHER or higher), and a PathStep lists it (`exercise_uids:` → `HAS_EXERCISE`). The app has no create, edit or requirement door for it.

**Service:** `ExerciseService` — flat (no sub-service decomposition), reads only; its declared audience is PUBLIC (no owner, a draft unlisted by the publication gate):
- `get_exercise(uid)` / `get_exercise_for_user(uid, user_uid)` — by-UID reads; the second through the declared audience (`/exercises/get`, the worksheet download)
- `get_required_knowledge(exercise_uid)` — all Kus required by this exercise (the daily plan)
- `get_required_knowledge_for_user(exercise_uid, user_uid)` — the same through the declared audience (`GET /api/exercises/required-knowledge`); a uid naming nothing is not-found
- `get_exercises_for_curriculum(curriculum_uid, user_uid)` — reverse lookup, a listing (drafts unlisted)
- `get_student_exercises_with_status(...)` / `get_exercises_for_path_step_with_status(...)` — the exercises of the steps the learner is on, with submission status
- `get_exercises_for_path_steps(...)`, `get_actionable_exercises_for_user(...)`, `get_pending_revisions_for_user(...)`

**Key Relationships:**
- `(PathStep)-[:HAS_EXERCISE]->(Exercise)` — curriculum anchor, from the step's `exercise_uids`
- `(Exercise)-[:REVIEWED_BY]->(User)` — the teacher a vault exercise's `teacher:` field names; feedback requests on it go there (ADR-091 S3)
- `(Exercise)-[:REQUIRES_KNOWLEDGE]->(Ku)` — declared prerequisites (read here; no app door writes them)
- `(UserEntry)-[:FULFILLS_EXERCISE]->(Exercise)` — user work linkage (incoming)

**UID Format:** `ex.{ns}.{slug}`, authored in the content vault.

---

## Comparison Table

| Feature | PS (PathStep) | KU | LP | Exercise |
|---------|---------------|----|-----|---------|
| **Sub-services** | 14 slots (incl. optional `ai`) | 4 | 5 (+ optional `ai`) | 1 (flat) |
| **Factory** | Specialized (`create_ps_sub_services`) | Ku factory (`create_curriculum_sub_services`) | Specialized (`create_lp_sub_services`) | None (a single `BaseService`) |
| **Extends** | Curriculum | Entity | Curriculum | Curriculum |
| **Complexity** | Highest | Lowest | Medium | Low |
| **User Progress** | Learning state (VIEWED / IN_PROGRESS / MASTERED) | Studying / understood (IN_PROGRESS / MASTERED) + `PINNED` bookmark | Enrollment + mastery | `FULFILLS_EXERCISE` submission tracking |
| **Key Relationship** | `USES_KU`, `HAS_STEP` (incoming) | (composed into PS) | `HAS_STEP` | `HAS_EXERCISE` ← PathStep, `REQUIRES_KNOWLEDGE` → Ku |
| **Special Pattern** | Substance + Organization + Activity integration | Atomic reference | Validation + adaptive | Vault-authored, names its teacher; learning loop anchor |
| **Navigation** | Point lookup + non-linear (ORGANIZES) | Referenced from PathSteps | Linear path | Anchored to PathStep (`HAS_EXERCISE`) |
| **Cross-Domain Dep** | None | None | PsService | None |

**Activity integration lives directly on PathSteps** (no intermediate Lesson node), authored as `habit_uids`, `task_uids`, `event_uids`, `goal_uids`, `principle_uids`, `choice_uids`:
`BUILDS_HABIT`, `ASSIGNS_TASK`, `SCHEDULES_EVENT`, `SUPPORTS_GOAL`, `GUIDED_BY_PRINCIPLE`, `INFORMS_CHOICE`.
