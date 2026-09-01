---
title: The 7 Subsystems — SKUEL's Functional Organization
updated: 2026-08-11
status: current
category: architecture
tags:
- architecture
- mental-model
- mvp
- subsystems
related:
- ENTITY_TYPE_ARCHITECTURE
- THREE_LAYER_LENS
- LEARNING_LOOP_ARCHITECTURE
- ADR-047-entity-types-replace-domain-categories
- ADR-054-user-entry-unified-submissions
- ADR-055-architectural-lenses
---

# The 7 Subsystems

## Purpose

SKUEL's EntityTypes roll up into **7 subsystems** — coarse functional groupings that answer *where does this belong in the system?* The subsystems further split into three sections (**Object**, **Context**, **Meta**) that answer *what role does this group play?*

This doc is Model A at the rollup level. It has two companions:

| Doc | Level | Question it answers |
|-----|-------|---------------------|
| [ENTITY_TYPE_ARCHITECTURE.md](ENTITY_TYPE_ARCHITECTURE.md) | Model A — EntityTypes (fine) | *What is this thing?* |
| **This doc** | **Model A — 7 Subsystems (coarse)** | ***Where does this belong?*** |
| [THREE_LAYER_LENS.md](THREE_LAYER_LENS.md) | Model B — 3 Layers (cross-cutting) | *What role is this playing in the cycle?* |

### A note on the word

"Domains" is overloaded in SKUEL ("Activity Domains", "domain services", "domain models"). This doc uses **subsystems** for the coarse grouping. Code continues to use *domain* for the fine-grained senses it already owns.

## The 7 Subsystems

| # | Subsystem | What it is | Member EntityTypes |
|---|-----------|-----------|-------------------|
| 1 | **Ku** | Atomic knowledge units | `Ku`, `Resource` |
| 2 | **Curriculum Domains** | Composed, ordered curriculum | `PathStep`, `LearningPath`, `Exercise` |
| 3 | **Activity Domains** | User-authored life data | `Task`, `Goal`, `Habit`, `Event`, `Choice`, `Principle`, `LifePath` |
| 4 | **Learning Loop** | The Curriculum→Action→Feedback→Curriculum cycle | `Exercise`, `UserEntry`, `EntryReport`, `RevisedExercise`, `Interaction` |
| 5 | **User** | Person, identity, authorship, ownership, state | `User` (cross-cutting `UserContext`) |
| 6 | **Groups** | Cohorts, classrooms, sharing containers | `Groups`, `FormTemplate`, `FormSubmission` |
| 7 | **Askesis** | Pedagogical guide / interpretation layer | (no Entity — cross-cutting system) |

`Exercise` belongs to both Curriculum Domains (as authored object) and Learning Loop (as the seed of the cycle). That overlap is the point: the loop *is* curriculum-in-motion.

## The 3 Sections

| Section | Subsystems | What the group does |
|---------|-----------|---------------------|
| **Object** | Ku, Curriculum Domains, Activity Domains, Learning Loop | Produces entities — things the system holds |
| **Context** | User, Groups | Wraps entities — who owns them, who sees them |
| **Meta** | Askesis | Sits on top — interprets, guides, orchestrates |

The Object/Context/Meta split is how you know whether a new feature creates a *thing*, shapes *who can see a thing*, or *says something about a thing*. Most feature work lives in Object. Most policy work lives in Context. Most interpretation work lives in Meta.

## The 7 × 3 Matrix with MVP Flags

Each cell asks: *Does the MVP need this subsystem in this layer?*

**Legend**
- ✅ **Required** — MVP cannot ship without this cell working
- 🟡 **Minimal** — MVP needs a simple, unpolished version
- ⏳ **Deferrable** — post-MVP; the product works without it
- — **Not applicable** — this subsystem has no role in this layer

| Subsystem | Section | Curriculum Layer | Action Layer | Feedback Layer |
|-----------|---------|:---:|:---:|:---:|
| Ku | Object | ✅ | — | 🟡 |
| Curriculum Domains | Object | ✅ | — | — |
| Activity Domains | Object | — | ✅ | 🟡 |
| Learning Loop | Object | ✅ | ✅ | ✅ |
| User | Context | — | ✅ | 🟡 |
| Groups | Context | — | 🟡 | 🟡 |
| Askesis | Meta | ⏳ | ⏳ | ⏳ |

## MVP Reading

The ✅ and 🟡 cells together describe a shippable product:

**Curriculum layer (authored upstream).** An admin authors Kus and composes them into PathSteps. PathSteps are strung into LearningPaths. Each PathStep exposes Exercises. This is the Ku + Curriculum Domains + Learning Loop spine.

**Action layer (user-authored).** A user records Tasks, Goals, Habits, Events, Choices, and Principles. They enroll in a PathStep, engage with its Exercises, and submit `UserEntry`s. Identity and ownership come from User. If the MVP is teacher-led, Groups gates what the student sees and where entries go.

**Feedback layer (interpretation).** A teacher (or the student themselves) produces an `EntryReport` on a submitted `UserEntry`. Mastery on the underlying Ku ticks up. Simple ActivityReport rollups let the user see their own patterns. RevisedExercise closes the loop for any entry that needs another pass. Teacher review queue (via Groups) routes the work.

**What's off the MVP.** Askesis entirely. Rich AI-authored reports, pedagogical steering, ZPD-driven PathStep recommendations, Socratic dialog. Also deferrable: cross-domain intelligence rollups, advanced ActivityReport shapes, group-level analytics.

Read vertically, the MVP is: **authored curriculum → user action → human feedback → adapted curriculum.** Read horizontally, every Object subsystem ships at least minimally; every Meta cell waits.

## Two Sharpening Questions

Two product calls change the shape of the 🟡 cells — worth deciding explicitly before building:

1. **Solo learner or teacher-led MVP?** If solo, Groups drops to ⏳ across the board; Feedback layer becomes AI + self-review. If teacher-led, Groups is ✅ and teacher review is the Feedback layer's primary mode.
2. **Does the MVP include the Activity Domains, or only the Learning Loop?** If only the Learning Loop, Activity Domains → ⏳ and the product is "a learning platform." If both, the product is "a life-aligned learning platform" — which is SKUEL's stated vision but a broader MVP.

Neither question is answered here. The matrix above assumes **teacher-led + both tracks**, which is SKUEL's stated direction.

## How to Use This Doc

- Starting a new feature → ask *which subsystem?* → that tells you where code, docs, and ownership live.
- Scoping MVP cuts → read the matrix vertically and mark ⏳ on anything you're deferring. The remaining cells are your MVP.
- Writing an ADR → name the subsystem and section in the frontmatter. "This is an Object/Activity-Domain change" is more precise than "this is a domain change."

## Non-Goals

- **Not a code structure.** Subsystems are a mental model; they don't map 1:1 to directories. Activity Domains live under `core/services/{task,goal,habit,...}/`, not under a shared `activity_domains/`.
- **Not a replacement for EntityType membership.** An entity is still typed by its `EntityType`; subsystem membership is derived, not stored.
- **Not a fixed count.** If a new cross-cutting capability appears (e.g. a second Meta-layer system), this doc updates. The number 7 is current, not canonical.

## See Also

- [ADR-055](../decisions/ADR-055-architectural-lenses.md) — the decision that formalizes Model A + Model B and adopts the "Subsystems" vocabulary
- [ENTITY_TYPE_ARCHITECTURE.md](ENTITY_TYPE_ARCHITECTURE.md) — the EntityTypes behind these 7 subsystems
- [THREE_LAYER_LENS.md](THREE_LAYER_LENS.md) — Model B, the cross-cutting view
- [LEARNING_LOOP_ARCHITECTURE.md](LEARNING_LOOP_ARCHITECTURE.md) — subsystem 4 in depth
- [ADR-047](../decisions/ADR-047-entity-types-replace-domain-categories.md) — why behavioral traits, not category membership
- [ADR-054](../decisions/ADR-054-user-entry-unified-submissions.md) — why `UserEntry` + `Pipeline` consolidates what used to be three types
