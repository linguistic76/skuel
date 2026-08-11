---
title: The 3-Layer Lens — A Cross-Cutting View of SKUEL
updated: 2026-04-19
status: current
category: architecture
tags:
- architecture
- mental-model
- content-origin
- learning-loop
related:
- ENTITY_TYPE_ARCHITECTURE
- SEVEN_SUBSYSTEMS
- LEARNING_LOOP_ARCHITECTURE
- ADR-047-entity-types-replace-domain-categories
- ADR-054-user-entry-unified-submissions
- ADR-055-architectural-lenses
---

# The 3-Layer Lens

## Purpose

SKUEL has two useful ways to classify an entity, and they answer different questions. Keeping them separate keeps the architecture legible.

| Model | Question it answers | Shape |
|-------|--------------------|------|
| **Model A — Entity Types** | *Where does this belong in the system?* | Ontological / organizational |
| **Model B — 3 Layers** | *What role is this playing in the cycle?* | Operational / flow-of-information |

Model A is the domain model (see `ENTITY_TYPE_ARCHITECTURE.md`). Model B is this document.

## The Core Insight

The 3-layer lens is **not a domain model**. It is a **flow-of-information / lifecycle model**. It describes how information moves through SKUEL over time:

> Curriculum → Action → Reflection → Adaptation

That is a pipeline. The lens is the pipeline viewed side-on.

## The Three Layers

### 1. Curriculum Layer

Authored content — what someone is meant to learn, do, or use.

Members: `Resource`, `Ku`, `PathStep`, `LearningPath`, `Exercise`

### 2. Action Layer

User-authored data — what the user actually does, records, or commits to.

Members: `Task`, `Goal`, `Habit`, `Event`, `Choice`, `Principle`, `UserEntry`, `LifePath`

`UserEntry` is a single EntityType whose `Pipeline` discriminator expresses variety:

- `Pipeline.NONE` — plain text submission, no processing
- `Pipeline.TRANSCRIBE` — audio → text (Deepgram)
- `Pipeline.TRANSCRIBE_AND_STRUCTURE` — audio → transcribed entry → LLM-structured entry (journal)
- `Pipeline.LLM_SUMMARY` — text/file → LLM summary
- `Pipeline.EXTRACT_ACTIVITIES` — DSL parse → real entities with `EXTRACTED_FROM` provenance (ADR-069)
- `Pipeline.TEACHER_REVIEW` — no processing; waits in a teacher review queue via `SHARED_WITH_GROUP`
- `Pipeline.JOURNAL` — journals domain entry; processing driven by JournalTier (FOUNDER: DNWF, STANDARD: single-response)
- `Pipeline.REFERENCE` — RESERVED (no producer): the planned per-user *stored* journal-exemplar layer; je_raw/je_pro exemplars stay disk-only (ADR-073 §4), and a frontmatter-consented je_pro file ingests as KNOWLEDGE, not REFERENCE

New user-authored flows arrive as new pipeline variants, not as new EntityTypes (ADR-054).

### 3. Feedback / Intelligence Layer

Interpretive output — what the system (human or machine) says *about* Action-layer data.

Members: `EntryReport`, `ActivityReport`, `RevisedExercise`

## Mapping to `ContentOrigin`

The 3 layers are a coarsening of the 4-valued `ContentOrigin` enum (`core/models/enums/entity_enums.py`):

| Layer | `ContentOrigin` | Notes |
|-------|-----------------|-------|
| Curriculum | `CURATED` + `CURRICULUM` | Admin-authored; shared |
| Action | `USER_CREATED` | User-authored |
| Feedback | `REPORT` | Interpretive |

`ContentOrigin` keeps the 4-way split because `CURATED` (Resource) and `CURRICULUM` (Ku / PathStep / LearningPath / Exercise) have different ownership and access patterns at the code level. The 3-layer lens collapses them because their **role in the flow** is the same: authored, upstream of action.

### The one hybrid

`RevisedExercise` has `ContentOrigin.CURRICULUM` but sits in the Feedback layer by role. The hybrid is the structural signature of *adapted curriculum*: teacher-authored (user_uid required) but curricular in function. It is the loop closing — feedback returning to curriculum informed by what happened.

## The Seven Subsystems × Three Layers

| Subsystem | Curriculum | Action | Feedback |
|--------|-----------|--------|----------|
| Ku | Primary | — | — |
| Curriculum Domains (PathStep, LearningPath, Exercise) | Primary | — | — |
| Activity Domains (Task, Goal, Habit, Event, Choice, Principle) | Taxonomy only | Primary | — |
| Learning Loop | Spans | Spans | Spans |
| User | — | Primary | Secondary |
| Groups | — | Context | Context |
| Askesis | Influences | Influences | Primary |

The Learning Loop is where all three layers meet most cleanly.

## The Canonical Loop

```
Curriculum     Action              Feedback         Curriculum (again)
─────────      ────────────        ──────────────   ─────────────────
Exercise  →    UserEntry      →    EntryReport → RevisedExercise
                                                         │
                                                         ▼
                                                    UserEntry (next attempt)
                                                         ...
```

Each arrow is a relationship in the graph:

- `(UserEntry)-[:FULFILLS_EXERCISE {revision}]->(Exercise)` — the revision count lives on the edge, not on the node. A second attempt is a second `UserEntry`.
- `(EntryReport)-[:REPORT_FOR]->(UserEntry)`
- `(RevisedExercise)-[:RESPONDS_TO_REPORT]->(EntryReport)` and `(RevisedExercise)-[:REVISES_EXERCISE]->(Exercise)`

## When to Use Which Model

Use **Model A (Entity Types)** when you are:

- Deciding which service or backend owns an operation
- Adding a new kind of thing to the system
- Writing route handlers, services, or persistence code
- Reasoning about ownership, scope, and access

Use **Model B (3 Layers)** when you are:

- Explaining the system to someone new
- Deciding where a new pipeline variant should live
- Tracing how a piece of information flows end-to-end
- Writing documentation or ADRs that talk about *roles*, not *types*

The two models do not compete. They answer different questions.

## Non-Goals

- **Not a replacement for `ContentOrigin`.** The enum stays 4-valued. The lens is a reading of it.
- **Not a new EntityType or table.** Nothing in code changes because of this doc.
- **Not a hierarchy.** The 3 layers are not parent classes. They are a conceptual overlay.

## See Also

- `ADR-055-architectural-lenses.md` — the decision that formalizes Model A + Model B
- `SEVEN_SUBSYSTEMS.md` — Model A at the coarse (7-subsystem) level, with MVP matrix
- `ENTITY_TYPE_ARCHITECTURE.md` — Model A at the fine (EntityType) level
- `LEARNING_LOOP_ARCHITECTURE.md` — the canonical Exercise → UserEntry → EntryReport → RevisedExercise flow
- `ADR-054-user-entry-unified-submissions.md` — why `UserEntry` + `Pipeline` replaces the old per-type split
- `ADR-047-entity-types-replace-domain-categories.md` — why we talk about entity types and behavioral traits, not category membership
