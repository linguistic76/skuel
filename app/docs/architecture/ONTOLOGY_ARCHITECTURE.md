---
title: Ontology Architecture — World Layer and User Layer
updated: 2026-07-20
status: current
category: architecture
tags: [architecture, ontology, world-layer, user-layer, curriculum]
related: [ENTITY_TYPE_ARCHITECTURE.md, CURRICULUM_GROUPING_PATTERNS.md, RELATIONSHIPS_ARCHITECTURE.md]
---

# Ontology Architecture — World Layer and User Layer

## The Central Design Question

> Does this node exist without a user?

If yes → World Layer.
If no → User Layer.

This question is the cleanest lens for understanding SKUEL's graph structure.

---

## Layer 1 — World Layer (Shared, Stable)

These nodes exist independently of any user. They represent the **objective structure** of SKUEL:

| Node | Purpose |
|------|---------|
| `Ku` | Atomic knowledge unit — a single concept, state, practice, or principle |
| `PathStep` | Unit for learning — composes Kus into curriculum content |
| `LearningPath` | Ordered sequence of PathSteps |
| `Exercise` | Instruction template, assignment, or formal assessment |
| `Resource` | Curated external content (books, talks, films) |

World Layer nodes:
- Are **not user-owned** (`requires_user_uid()` returns `False`)
- Are created by **admin/teacher roles** via ingestion or UI
- Are **read by all users**
- Have `ContentScope.SHARED`

### Ku (Atomic Knowledge Unit)

Kus are the leaf nodes of the World Layer — the smallest indivisible unit of knowledge.
Every PathStep, LearningPath, and Exercise ultimately points back to Kus.

```cypher
// Ku as content atom
(:PathStep)-[:USES_KU]->(:Ku)   // step composes this Ku
(:PathStep)-[:TRAINS_KU]->(:Ku)  // step trains this Ku as a learning objective
```

#### Domain classification lives ON the Ku

A Ku carries its own taxonomy as in-model properties — there is **no separate
`:KnowledgeDomain` node**. The three levels are all populated at ingestion from Ku
frontmatter and are queryable as node properties + search facets:

| Property | Level | Type |
|----------|-------|------|
| `nous` | outermost topic taxonomy (L1) | multi-valued slugs (11 official, e.g. `self-awareness`, `body`, `stories`) |
| `nous_subtopic` | topic taxonomy (L2) | multi-valued slugs |
| `sel_category` | SEL competency | `SELCategory` enum (5 members) |

These drive the search facets (`SearchRouter.nous_subtopic_map`), Askesis retrieval
scope, and cross-domain grouping. See `docs/patterns/NOUS_SUBTOPIC_FACET.md`.

> **Historical note.** An earlier design added a separate `:KnowledgeDomain`
> taxonomy node with `(Ku)-[:IN_DOMAIN]->(:KnowledgeDomain)` membership, authored
> via a `domains:` frontmatter field. It never had a live writer (0 nodes, 0 edges,
> nothing authored `domains:`) and was redundant with `nous`/`nous_subtopic`/
> `sel_category`, so the whole stack was deleted (2026-07-20). Domain classification
> is a Ku property, not a graph node.

---

## Layer 2 — User Layer (Contextual, Dynamic)

These nodes exist **because a user exists**. They represent the **lived experience** of a user
moving through the World Layer:

| Node | World Layer Anchor |
|------|-------------------|
| `UserEntry` | Responds to `Exercise` (or acts as standalone entry) |
| `EntryReport` | Reports on `UserEntry` |
| `Task` | May link to `Ku`, `Goal`, `PathStep` |
| `Goal` | May align with `LifePath`, link to `Ku` |
| `Habit` | May reinforce `Ku`, align with `PathStep` |
| `Event` | May link to `Habit`, `Goal` |
| `Choice` | May be informed by `Ku` |
| `Principle` | May be grounded in `Ku` |
| `ActivityReport` | Aggregates User Layer activity |
| `LifePath` | The destination — all domains flow toward this |

User Layer nodes:
- Are **user-owned** (`requires_user_uid()` returns `True`)
- Carry `user_uid` as a discriminator
- Use `ContentScope.USER_OWNED`
- Do NOT own World Layer nodes (no `[:OWNS]->(:Ku)` or `[:OWNS]->(:PathStep)`)

---

## The Interaction Edge — Where SKUEL's Power Emerges

The real power of SKUEL comes from the **interaction edge between layers**:

```
User Layer ←——— interaction edge ———→ World Layer
```

This chain is everything:

```cypher
(:User)
  -[:SUBMITTED]->
(:UserEntry)
  -[:SUBMISSION_FOR]->
(:Exercise)
  <-[:USES_EXERCISE]-
(:PathStep)
  -[:USES_KU]->
(:Ku)
```

From this chain, SKUEL can derive:
- Learning progression (what did the user submit, for which exercise, on which PathStep)
- Knowledge coverage (which Kus has the user engaged with)
- Domain coverage (via each Ku's `nous` / `sel_category` classification)
- ZPD assessment (what is the user ready to learn next)

---

## Core Relationships

These are the structural relationships that hold the ontology together:

| Relationship | Pattern | Meaning |
|-------------|---------|---------|
| `USES_KU` | `(PathStep)-[:USES_KU]->(Ku)` | PathStep composes this Ku as content |
| `TRAINS_KU` | `(PathStep)-[:TRAINS_KU]->(Ku)` | PathStep declares this Ku as learning objective |
| `HAS_STEP` | `(LearningPath)-[:HAS_STEP]->(PathStep)` | Path contains this step |
| `ORGANIZES` | `(Ku)-[:ORGANIZES]->(Ku)` | Non-linear MOC navigation (any Ku can organize) |
| `REQUIRES_KNOWLEDGE` | `(Ku)-[:REQUIRES_KNOWLEDGE]->(Ku)` | Prerequisite knowledge |

All relationship types are defined in `RelationshipName` enum (`core/models/relationship_names.py`).

---

## Two Navigation Paths to the Same Knowledge

| Path | Topology | Pedagogy |
|------|----------|---------|
| **PS Path** (structured) | LP → PathStep → Ku | Teacher-directed linear curriculum |
| **MOC Path** (exploratory) | Ku → [ORGANIZES] → Ku | Learner-directed non-linear discovery |

Both paths reach the same Kus. Progress is tracked on the Ku itself, unified across both paths.

---

## What Does NOT Connect to the User

Not everything connects to the user. **Only interaction + ownership objects do.**

```cypher
// ✅ These are correct
(:User)-[:OWNS]->(:UserEntry)
(:User)-[:OWNS]->(:Task)
(:User)-[:OWNS]->(:Goal)

// ❌ These are wrong — World Layer belongs to the system, not the user
(:User)-[:OWNS]->(:Ku)
(:User)-[:OWNS]->(:PathStep)
(:User)-[:OWNS]->(:LearningPath)
```

---

## Key Files

| Component | File |
|-----------|------|
| Ku model (incl. `nous` / `nous_subtopic` / `sel_category`) | `core/models/ku/ku.py` |
| PathStep model | `core/models/pathways/path_step.py` |
| LearningPath model | `core/models/pathways/learning_path.py` |
| RelationshipName | `core/models/relationship_names.py` (see `USES_KU`, `TRAINS_KU`) |
| NeoLabel | `core/models/enums/neo_labels.py` (see `KU`, `PATH_STEP`) |

**See also:**
- `docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` — KU/PS/LP grouping patterns
- `docs/architecture/ENTITY_TYPE_ARCHITECTURE.md` — complete entity type behavioral traits
- `docs/architecture/RELATIONSHIPS_ARCHITECTURE.md` — relationship service architecture
