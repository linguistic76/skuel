# Neo4j Relationship Reference

Curated catalog of the relationship types you'll actually meet in SKUEL's graph, grouped by category.

**Source of Truth:** `/core/models/relationship_names.py` — the `RelationshipName` enum (169 members). This file documents the load-bearing subset with endpoints and semantics; for the exhaustive list (family relations, notifications, devices, ...) read the enum, whose inline comments carry endpoint documentation.

**Naming note:** rows show the **Cypher edge type string** (the enum *value*). One member has a divergent name: `RelationshipName.LATERAL_ENABLES` has value `"ENABLES"` (and `LATERAL_ENABLED_BY` → `"ENABLED_BY"`).

## Ownership & Sharing

The universal ownership edge and the sharing model (ADR-038).

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `OWNS` | User | Entity | **Universal ownership — THE edge backends write and query** |
| `SHARES_WITH` | User | Entity | Manual sharing (`shared_at`, `role`, `share_version` props) |
| `SHARED_WITH_GROUP` | Entity | Group | Group-scoped sharing |
| `MEMBER_OF` | User | Group | Group membership |
| `ENROLLED_IN` | User | LearningPath | LP enrollment (`enrolled_at`, `status` — `'completed'` marks completion) |
| `PURSUING_GOAL` | User | Goal | Active goal pursuit (enum member; no current writer — search filters use OWNS + goal status) |

> `OWNS` is the one ownership edge — `RelationshipName.is_ownership_relationship()` is True for it alone, and the enum comment states the write rule (ADR-086). Events attendance is `ATTENDS` (consent-carrying, staged), not ownership.

## Curriculum Structure & Composition

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `HAS_STEP` | LearningPath | PathStep | Path contains ordered step |
| `REQUIRES_STEP` | PathStep | PathStep | Step prerequisites within a path |
| `USES_KU` | PathStep | Ku | **THE composition edge** — path step composes atomic Kus |
| `TRAINS_KU` | PathStep | Ku | Path step trains atomic Ku |
| `CONTAINS_KNOWLEDGE` | PathStep | Ku | Step covers knowledge (coexists with USES_KU) |
| `HAS_EXERCISE` | PathStep | Exercise | Curriculum loop anchor (dual-written with `Exercise.path_step_uid`) |
| `ORGANIZES` | Entity | Entity | MOC hierarchy (`order`, `importance` props) — MOC is emergent, not a label |
| `CITES_RESOURCE` | PathStep / Ku | Resource | Curriculum cites reference material (`context` prop) |

```cypher
// Find all Resources cited by PathSteps in a LearningPath
MATCH (lp:LearningPath)-[:HAS_STEP]->(ps:PathStep)-[:CITES_RESOURCE]->(r:Resource)
RETURN ps.title AS path_step, r.title AS resource, r.author, r.media_type
```

## Knowledge Relationships

Cross-domain edges into `:Ku` nodes (there is no `:Curriculum` label).

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `REQUIRES_KNOWLEDGE` | Goal/Task/Ku | Ku | Entity requires this knowledge (prerequisite when Ku→Ku) |
| `ENABLES_KNOWLEDGE` | Ku | Ku | This knowledge enables learning another |
| `RELATED_TO` | Ku | Ku | General semantic relationship |
| `APPLIES_KNOWLEDGE` | Task/Event/UserEntry | Ku | Entity applies this knowledge (the substance contract edge) |
| `REINFORCES_KNOWLEDGE` | Habit | Ku | Habit reinforces this knowledge |
| `GROUNDED_IN_KNOWLEDGE` | Principle | Ku | Principle grounded in knowledge |
| `INFORMED_BY_KNOWLEDGE` | Choice | Ku | Choice informed by knowledge |
| `HAS_NARROWER` / `HAS_BROADER` | Ku | Ku | Concept hierarchy (parent↔child) |
| `UNLOCKS_KNOWLEDGE` | Task | Ku | Completing unlocks knowledge |

## User Learning Progress

State progression: `NONE` → `VIEWED` → `IN_PROGRESS` → `MASTERED` (see `RelationshipName.is_learning_progress_relationship()`).

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `VIEWED` | User | Ku/PathStep | User has seen/read this content |
| `IN_PROGRESS` | User | Ku/PathStep | User is actively learning |
| `MASTERED` | User | Ku/PathStep | Knowledge acquired (`mastery_score`, `mastered_at` props) |

## Learning Loop (ADR-054)

Exercise → UserEntry → EntryReport → RevisedExercise.

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `FULFILLS_EXERCISE` | UserEntry | Exercise | Entry responds to an exercise |
| `FULFILLS_REVISED_EXERCISE` | UserEntry | RevisedExercise | Entry responds to a revised exercise |
| `REPORT_FOR` | EntryReport | UserEntry | Report targets submission |
| `RESPONDS_TO_REPORT` | RevisedExercise | EntryReport | Revision generated from feedback |
| `REVISES_EXERCISE` | RevisedExercise | Exercise | Links revision back to origin |
| `INTERACTION_DURING` | Interaction | PathStep | Interaction happened during step |
| `INTERACTION_WITHIN` | Interaction | LearningPath | Interaction within a path |

## Task Relationships

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `DEPENDS_ON` | Task | Task | Task dependency (blocking) |
| `BLOCKS` / `BLOCKED_BY` | Task | Task | Blocking pair |
| `HAS_SUBTASK` / `SUBTASK_OF` | Task | Task | Hierarchy pair |
| `CONTRIBUTES_TO_GOAL` | Task | Goal | Task contributes to goal progress |
| `FULFILLS_GOAL` | Task | Goal | Task directly fulfills goal |
| `IMPLEMENTS_CHOICE` | Task | Choice | Task implements a decision |
| `ASSIGNED_TO` | Task | User | Task assigned to user |

## Goal Relationships

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `SUBGOAL_OF` / `HAS_SUBGOAL` | Goal | Goal | Hierarchy pair |
| `DEPENDS_ON_GOAL` | Goal | Goal | Goal depends on another |
| `GUIDED_BY_PRINCIPLE` | Goal | Principle | Goal guided by principle |
| `SUPPORTS_GOAL` | Habit | Goal | Habit supports goal (with weight) |
| `CELEBRATES_GOAL` | Event | Goal | Event celebrates goal achievement |
| `ALIGNED_WITH_PATH` | Goal | LifePath | Goal aligned with life path |

## Habit Relationships

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `HAS_SUBHABIT` / `SUBHABIT_OF` | Habit | Habit | Hierarchy pair |
| `REQUIRES_PREREQUISITE_HABIT` | Habit | Habit | Habit requires another first |
| `ENABLES_HABIT` | Habit | Habit | This habit enables another |
| `STACKS_WITH` | Habit | Habit | Habit stacking |
| `EMBODIES_PRINCIPLE` | Habit | Principle | Habit embodies principle |
| `REINFORCES_STEP` | Habit | PathStep | Habit reinforces path step |
| `UNLOCKED_ACHIEVEMENT` | Habit | Achievement | Per-habit streak badge |
| `EARNED_BADGE` | User | Achievement | User earned a badge |

## Event Relationships

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `HAS_SUBEVENT` / `SUBEVENT_OF` | Event | Event | Hierarchy pair |
| `CONFLICTS_WITH` | Event | Event | Schedule conflict |
| `EXECUTES_TASK` | Event | Task | Event executes task |
| `ATTENDS` | User | Event | User attends event |
| `PRACTICED_AT_EVENT` | Habit | Event | Habit practiced at event |

## Principle Relationships

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `HAS_SUBPRINCIPLE` / `SUBPRINCIPLE_OF` | Principle | Principle | Hierarchy pair |
| `GUIDES_GOAL` | Principle | Goal | Principle guides goal |
| `GUIDES_CHOICE` | Principle | Choice | Principle guides choice |
| `CONFLICTS_WITH_PRINCIPLE` | * | Principle | Conflict marker |

## Choice Relationships

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `HAS_SUBCHOICE` / `SUBCHOICE_OF` | Choice | Choice | Hierarchy pair |
| `AFFECTS_GOAL` | Choice | Goal | Choice affects goal |
| `ALIGNED_WITH_PRINCIPLE` | Choice | Principle | Choice aligned with principle |
| `INFORMED_BY_PRINCIPLE` | Choice | Principle | Choice informed by principle |
| `TRIGGERS_CHOICE` | * | Choice | Something raises a decision |

## Lateral Relationships (all 9 domains, ADR-037)

Available on Tasks, Goals, Habits, Events, Choices, Principles, KU, PS, LP. Written by `LateralRelationshipBackend`.

| Relationship (Cypher string) | Enum member | Semantics |
|--------------|-------------|-----------|
| `BLOCKS` / `BLOCKED_BY` | same | Blocking pair |
| `PREREQUISITE_FOR` | same | Soft dependency inverse |
| `ENABLES` / `ENABLED_BY` | `LATERAL_ENABLES` / `LATERAL_ENABLED_BY` | Within-domain enabler pair |
| `ALTERNATIVE_TO` | same | Mutually exclusive options (symmetric) |
| `COMPLEMENTARY_TO` | same | Synergistic pairing (symmetric) |
| `SIBLING` | same | Same parent, same depth (symmetric) |
| `SIMILAR_TO` | same | High semantic similarity (symmetric) |
| `RECOMMENDED_WITH` | same | Often done together (symmetric) |
| `RELATED_TO` | same | Generic association |

## Life Path (the destination)

The `ULTIMATE_PATH` edge IS the designation — match by traversing it. The node is NOT mutated:
a designated path keeps its `:LearningPath` label and its `'learning_path'` entity_type, so
`{entity_type: 'life_path'}` matches ZERO rows. (It used to be flipped in place; that divergence
made every LP read of a designated path fail — see `docs/technical_debt/LIFEPATH_ALIGNMENT_DEBT.md`.)

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `ULTIMATE_PATH` | User | LifePath | User's designated life path (1:1) |
| `SERVES_LIFE_PATH` | Entity | LifePath | Entity flows toward the life path |
| `ALIGNMENT_SNAPSHOT` | User | LifePath | Daily alignment history (`date`, `score` props; MERGE-idempotent per day) |

## Activity Templates (PS-owned)

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `HAS_TASK_TEMPLATE` (+ `HAS_GOAL_TEMPLATE`, `HAS_HABIT_TEMPLATE`, `HAS_EVENT_TEMPLATE`, `HAS_CHOICE_TEMPLATE`, `HAS_PRINCIPLE_TEMPLATE`) | PathStep | *Template | Step owns activity template |
| `SPAWNED_FROM` | Activity instance | *Template | Instance provenance |
| `ENGAGED_WITH` | User | PathStep | Engagement marker |

## Forms

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `EMBEDS_FORM` | Entity | FormTemplate | Entity embeds a form |
| `RESPONDS_TO_FORM` | FormSubmission | FormTemplate | Submission answers form |

## Evidence Relationships

Observable connections between knowledge units.

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `EXACERBATED_BY` | Entity | Entity | Subject exacerbated by target |
| `REDUCED_BY` | Entity | Entity | Subject reduced/mitigated by target |
| `CORRELATED_WITH` | Entity | Entity | Statistical correlation |
| `CAUSES` | Entity | Entity | Direct causal relationship |
| `PRECEDES` | Entity | Entity | Temporal precedence |

Evidence edges carry properties: `confidence` (0.0–1.0), `polarity` (-1/0/1), `temporality` (minutes/hours/days/chronic), `source` (self_observation/research/teacher/clinical/inferred-approved), `evidence` (text), `observed_at`.

## Journal Pipeline (UserEntry, ADR-054)

Journals are a **pipeline**, not a domain. Audio upload creates a source `UserEntry` with
`pipeline=TRANSCRIBE_AND_STRUCTURE`; Deepgram transcribes, then the LLM generates a
structured second `UserEntry` linked by `TRANSFORMS`.

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `TRANSFORMS` | UserEntry (structured) | UserEntry (source) | LLM-processed output transforms raw input |

## DSL Extraction Provenance (ADR-069)

`Pipeline.EXTRACT_ACTIVITIES` parses Activity Lines in a `UserEntry` into real
entities. Each created entity gets a provenance edge back to its source entry
(written by the dedicated batch method `create_extracted_from_links` — the
source label varies per created entity, so this edge is not in the
relationship registry). Resolved `@ku()` references write the canonical
substance/ZPD edge from the entry itself.

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `EXTRACTED_FROM` | created Entity (Task, Habit, ...) | UserEntry (source) | Extraction provenance; carries `extracted_at`, `source_line_hash` (sha256 of the DSL line normalized for whitespace, checkbox state and the 🆔 token — `normalize_vault_line_hash`, the re-run dedup key; the ✅ date stays in it as a discriminator), `vault_id` (the 🆔 — a line whose 🆔 already has an edge to the entry is recognised by it whatever its hash, Guard 2b) |
| `APPLIES_KNOWLEDGE` | UserEntry | Ku | Knowledge applied/reflected in the entry (same contract edge as Task→Ku) |

## Authentication Relationships

Graph-native session and auth event tracking.

| Relationship | From | To | Purpose |
|--------------|------|-----|---------|
| `HAS_SESSION` | User | Session | User has active session |
| `HAD_AUTH_EVENT` | User | AuthEvent | User had auth event (audit) |
| `HAS_RESET_TOKEN` | User | ResetToken | User has password reset token |

## Helper Methods (RelationshipName Enum)

The `RelationshipName` enum provides helper methods:

```python
from core.models.relationship_names import RelationshipName

# Convert string to enum (returns None if invalid)
rel = RelationshipName.from_string("REQUIRES_KNOWLEDGE")

# Check if valid
is_valid = RelationshipName.is_valid("REQUIRES_KNOWLEDGE")  # True

# Category checks
rel = RelationshipName.REQUIRES_KNOWLEDGE
rel.is_knowledge_relationship()  # True
rel.is_blocking_relationship()   # False
rel.is_ownership_relationship()  # False (True only for RelationshipName.OWNS — ADR-086)
rel.is_learning_progress_relationship()  # False
```

## Edge Properties

Some relationships carry metadata on the edge:

### Confidence Score
```cypher
// Relationship with confidence
(task)-[:APPLIES_KNOWLEDGE {confidence: 0.85}]->(ku)

// Filter by confidence
MATCH (t:Task)-[r:APPLIES_KNOWLEDGE]->(ku:Ku)
WHERE r.confidence >= 0.8
```

### Mastery Score (Learning Progress)
```cypher
// User mastery with score
(user)-[:MASTERED {mastery_score: 0.95, mastered_at: datetime()}]->(ku)
```

### Timestamps
```cypher
// Relationship with timestamp
(user)-[:VIEWED {viewed_at: datetime()}]->(ku)
```
