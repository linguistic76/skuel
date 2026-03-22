# Curriculum Developer Guide

**Purpose:** Show curriculum developers how to build structured, interconnected learning content for the SKUEL system — starting from atomic concepts (Kus), composing them into teaching narratives (Lessons), and linking everything into prerequisite chains that learners follow.

**Audience:** Curriculum developers and subject-matter experts creating content for SKUEL.app

**Prerequisite:** No coding experience required. You write YAML files and markdown. The system does the rest.

**Last Updated:** 2026-03-17

---

## The Big Idea

SKUEL separates **what you know** from **how you learn it**.

- A **Ku** (Knowledge Unit) is an atomic concept — a single definable thing. It exists as a reference node in the knowledge graph. It has no teaching narrative, no exercises, no learning objectives. It just *is*.
- A **Lesson** is a unit for learning — a teaching narrative that composes multiple Kus into coherent content. Lessons are where explanation, examples, exercises, and voice live.

This separation is deliberate. The same Ku — say, *Empathy* — can appear in a lesson about social awareness, a lesson about conflict resolution, a lesson about leadership, and a lesson about parenting. The concept is defined once; it's taught many ways.

Your job as a curriculum developer is to:

1. **Define the atoms** — write Kus that capture individual concepts clearly
2. **Compose the narratives** — write Lessons that weave those Kus into teachable stories
3. **Build the chains** — connect Lessons into prerequisite sequences so learners know where to start and where to go next

---

## A Worked Example: The SEL Prerequisite Chain

The best way to understand the system is to see it in action. SKUEL ships with a reference curriculum built around the five CASEL Social-Emotional Learning competencies. This section walks through how it was designed and why.

### The Five Lessons

```
Knowing Yourself → Managing Yourself → Understanding Others → Building Relationships → Making Good Decisions
     (SA)              (SM)                 (SOA)                  (RS)                    (RDM)
```

Each lesson covers one SEL competency. Each composes exactly four Kus. Each links forward to the next lesson via a prerequisite connection. The result is a linear chain that a learner can follow from start to finish — or enter at any point if they already have the prerequisites.

### Why This Order?

The order is not arbitrary. It follows a pedagogical logic:

1. **Knowing Yourself** (Self-Awareness) comes first because everything else depends on it. You cannot manage emotions you cannot name. You cannot empathize with others if you don't understand your own experience.

2. **Managing Yourself** (Self-Management) builds on self-awareness. Once you can identify what you're feeling, the next question is: what do I do about it? Goals, habits, impulse control, and stress management are the tools.

3. **Understanding Others** (Social Awareness) is the outward turn. The inward skills (awareness + management) now point toward other people. Empathy, perspective-taking, cultural awareness, and compassion require self-knowledge as a foundation — otherwise you project instead of perceive.

4. **Building Relationships** (Relationship Skills) applies social awareness in practice. Active listening, boundary setting, conflict resolution, and teamwork are empathy made concrete.

5. **Making Good Decisions** (Responsible Decision-Making) is the capstone. It synthesizes all four prior competencies: know yourself, manage yourself, understand others, relate to others — and now, choose wisely. The final lesson explicitly names this synthesis and closes the loop back to self-awareness.

This is not the only valid sequence. A curriculum developer might choose a different entry point, a different grouping, or a spiral structure that revisits competencies at increasing depth. The point is that the order should be *intentional* and *justified*, not accidental.

### How Each Lesson Composes Four Kus

Each lesson in the chain declares exactly four Kus in its `uses_kus` field. Here's the mapping:

| Lesson | Ku 1 | Ku 2 | Ku 3 | Ku 4 |
|--------|-------|-------|-------|-------|
| Knowing Yourself | Emotions | Emotional Triggers | Self-Worth | Growth Mindset |
| Managing Yourself | Goal Setting | Habits | Impulse Control | Stress Management |
| Understanding Others | Empathy | Perspective-Taking | Cultural Awareness | Compassion |
| Building Relationships | Active Listening | Conflict Resolution | Teamwork | Boundary Setting |
| Making Good Decisions | Ethical Reasoning | Consequence Analysis | Identifying Problems | Reflecting on Choices |

Four is not a magic number. A lesson might compose two Kus or seven. But four works well for beginner-level content because it's enough to create connections between ideas without overwhelming the learner. The constraint also forces you to choose — which concepts are *essential* to this lesson's narrative?

The relationship between a Lesson and its Kus is **composition, not coverage**. A lesson on "Understanding Others" doesn't just *mention* empathy — it weaves empathy into a narrative alongside perspective-taking, cultural awareness, and compassion, showing how these four concepts interact. The Ku provides the definition; the Lesson provides the meaning.

### How Prerequisite Chains Work

In each Lesson YAML, the `connections` field declares what must come before and what comes after:

```yaml
# From lesson_managing-yourself.yaml
connections:
  requires:
    - l:sel:knowing-yourself       # Must complete this first
  enables:
    - l:sel:understanding-others   # Unlocks this next
```

When ingested, the system creates directed relationships in the knowledge graph:

```
(Knowing Yourself)──ENABLES──>(Managing Yourself)──ENABLES──>(Understanding Others)──ENABLES──>...
```

These relationships power:
- **Prerequisite checking** — the system can warn a learner if they're jumping ahead
- **Learning path generation** — the system can build ordered sequences from the graph
- **Progress tracking** — the system knows which lessons unlock next based on what's been completed

A lesson with no `requires` is an entry point — anyone can start there. A lesson with no `enables` is a terminal — it's the end of a chain (or the start of a new one, once you extend it).

### How the Loop Closes

The final lesson — *Making Good Decisions* — has no `enables` connection. But thematically, it loops back to self-awareness:

> *"Decisions reveal who you are — which brings you back to self-awareness. The loop never ends. It just deepens."*

This is intentional. The prerequisite chain is linear (A → B → C → D → E), but the *conceptual* structure is circular. A learner who completes the chain is better equipped to start it again at a deeper level. This creates a natural opening for intermediate and advanced content that revisits the same five competencies with greater nuance.

In SKUEL's graph, this circularity is captured not through prerequisite edges (which would create cycles) but through the Ku layer. The Kus in the first lesson (Emotions, Emotional Triggers) and the Kus in the last lesson (Reflecting on Choices) share semantic connections — reflection *is* a form of self-awareness. A curriculum developer building the next level of content can make this explicit:

```yaml
# A future advanced lesson
connections:
  requires:
    - l:sel:making-good-decisions   # Completed the beginner chain
    - l:sel:knowing-yourself        # Revisiting self-awareness at depth
```

---

## The Two Primitives: Ku and Lesson

### Writing a Ku

A Ku is a YAML file with no content body. It defines a concept.

```yaml
version: 1.0
type: Ku

uid: ku:sel:empathy
title: Empathy
namespace: sel
ku_category: concept
aliases:
  - perspective-taking
  - emotional attunement
  - understanding others
source: sel_framework
sel_category: social_awareness
description: >
  The ability to understand and share the feelings of another person.
  Empathy involves both cognitive understanding (seeing their perspective)
  and affective resonance (feeling with them).
tags:
  - sel
  - social-awareness
  - empathy
  - connection
```

**Key fields:**

| Field | Purpose | Required? |
|-------|---------|-----------|
| `uid` | Unique identifier (`ku:{namespace}:{slug}`) | Yes |
| `title` | Display name | Yes |
| `namespace` | Grouping (e.g., `sel`, `attention`, `nutrition`) | No, but recommended |
| `ku_category` | What kind of thing this is (concept, practice, value, state, substance, principle, intake) | No |
| `sel_category` | Which SEL competency it belongs to | No (only for SEL content) |
| `aliases` | Alternative names for search | No |
| `description` | One-paragraph summary | No, but strongly recommended |
| `tags` | For filtering and search | No |

**Guidelines:**

- **One concept per Ku.** If you're writing "and" in the title, you probably have two Kus.
- **Describe, don't teach.** The description should define the concept, not explain how to develop it. Teaching belongs in Lessons.
- **Choose `ku_category` carefully.** A *concept* is an abstract idea (empathy, neuroplasticity). A *practice* is something you do (active listening, meditation). A *value* is something you aspire to (compassion, honesty). A *state* is something you observe (buzzing, calm).
- **Use `aliases` generously.** Learners search with different words. If your Ku is "Impulse Control," aliases like "self-regulation" and "pause before acting" help the system surface it.

### Writing a Lesson

A Lesson is a YAML file with a markdown content body. It teaches.

```yaml
version: 1.0
type: Lesson

uid: l:sel:understanding-others
title: Understanding Others — Empathy, Perspective, and Compassion
sel_category: social_awareness
learning_level: beginner
complexity: basic
domain: personal
estimated_time_minutes: 15

content: |
  ## The Outward Turn

  Self-awareness and self-management are inward skills.
  Social awareness is where you turn outward — toward other people.

  ... (full markdown narrative) ...

  ## Practice

  Pick one of these for today:
  1. The perspective question: ...
  2. The cultural check: ...
  3. Micro-compassion: ...

uses_kus:
  - ku:sel:empathy
  - ku:sel:perspective-taking
  - ku:sel:cultural-awareness
  - ku:sel:compassion

connections:
  requires:
    - l:sel:managing-yourself
  enables:
    - l:sel:building-relationships

tags:
  - sel
  - social-awareness
  - beginner
```

**Key fields:**

| Field | Purpose | Required? |
|-------|---------|-----------|
| `uid` | Unique identifier (`l:{namespace}:{slug}`) | Yes |
| `title` | Display name | Yes |
| `content` | Full markdown teaching narrative | Yes |
| `uses_kus` | Which atomic Kus this lesson composes | No, but essential for graph |
| `connections.requires` | Prerequisite lesson UIDs | No |
| `connections.enables` | Lessons this unlocks | No |
| `learning_level` | Target level (beginner, intermediate, advanced, expert) | No |
| `complexity` | Difficulty (basic, medium, advanced) | No |
| `estimated_time_minutes` | Reading time in minutes | No |
| `learning_objectives` | What the learner will gain | No |

**Guidelines for the content body:**

- **Start with why.** The first section should answer: why does this matter? Why now? Connect it to what the learner already knows (the prerequisite lesson).
- **Use headers to chunk.** Each `##` section should be one digestible idea. A learner should be able to pause after any section and resume later.
- **Include a practice exercise.** Every lesson should end with something the learner can *do*. Not "think about this" — something concrete, specific, and achievable today.
- **Close with what's next.** Point forward to the next lesson in the chain. This creates momentum and gives the learner a reason to continue.
- **Write in second person.** "You" is more engaging than "the learner" or "one." This is a conversation, not a textbook.
- **Be direct.** Short sentences. Active voice. Say what you mean. Cut filler.

---

## Designing a Prerequisite Chain

### Step 1: Map the Domain

Before writing any YAML, sketch the domain on paper (or in a note). What are the core concepts? What must a learner understand *before* they can understand something else?

For the SEL example, the sketch looked like:

```
Self-Awareness (foundation — everything else needs this)
    ↓
Self-Management (requires awareness)
    ↓
Social Awareness (outward application of inward skills)
    ↓
Relationship Skills (social awareness in practice)
    ↓
Decision-Making (synthesis of all four)
```

This is a dependency analysis, not a table of contents. The question isn't "what order should I teach this in?" — it's "what depends on what?"

### Step 2: Define the Kus

For each lesson in your chain, identify 2-6 atomic concepts that the lesson will compose. Write these as Ku YAML files first.

Ask yourself:
- Is this truly atomic? Could I define this in one paragraph?
- Could this Ku appear in a *different* lesson in a *different* context?
- Am I defining a concept, or am I already teaching? (If teaching, it belongs in the Lesson.)

### Step 3: Write the Lessons

Now write each lesson's content, weaving its Kus into a narrative. The Kus are your building blocks; the lesson is the structure you build with them.

For each lesson:
1. State the `uses_kus` — which Kus does this lesson compose?
2. State the `connections` — what must come before? What does this unlock?
3. Write the content — the teaching narrative itself

### Step 4: Validate the Chain

Before ingesting, review the chain as a whole:

- **No orphans:** Every lesson (except entry points) has at least one `requires`. Every lesson (except terminals) has at least one `enables`.
- **No circular prerequisites:** The `requires`/`enables` graph must be a DAG (directed acyclic graph). Thematic loops are fine; prerequisite loops are not.
- **Ku coverage:** Every Ku referenced in `uses_kus` should have a corresponding Ku YAML file. The ingestion system will create the relationship even if the Ku doesn't exist yet, but dangling references make the graph messy.
- **Entry points are clear:** A new learner should be able to look at the chain and know where to start. If your chain has multiple entry points, that's fine — but make it intentional.

### Step 5: Ingest

Place your YAML files in the ingestion directory (default `data/vault/`, configurable via `INGESTION_PATH` env var) and ingest them through the system. The ingestion pipeline will:

1. Parse each YAML file
2. Create graph nodes for each Ku and Lesson
3. Create `USES_KU` relationships between Lessons and their composed Kus
4. Create `ENABLES`/`REQUIRES` relationships between Lessons
5. Index content for search and RAG retrieval

---

## Beyond Linear Chains

The SEL example is a straight line: A → B → C → D → E. Real curricula are rarely this simple. Here are patterns you'll encounter as you build more content.

### Branching

After a foundational lesson, learners might choose between two parallel paths:

```
Foundations
    ├── Track A: Interpersonal Skills
    │   ├── Lesson A1
    │   └── Lesson A2
    └── Track B: Intrapersonal Skills
        ├── Lesson B1
        └── Lesson B2
```

Both A1 and B1 declare `requires: [l:foundations]`. Neither requires the other.

### Convergence

Two parallel tracks merge into a capstone:

```yaml
# Capstone lesson
connections:
  requires:
    - l:track-a:lesson-a2
    - l:track-b:lesson-b2
```

The learner must complete both tracks before the capstone unlocks.

### Spiral

The same competency taught at increasing depth:

```
Empathy (Beginner) → Empathy (Intermediate) → Empathy (Advanced)
```

Each level uses some of the same Kus but adds new ones. The beginner lesson might use `ku:sel:empathy` and `ku:sel:perspective-taking`. The advanced lesson might add `ku:sel:compassion-fatigue` and `ku:sel:structural-empathy`. The Ku layer makes this overlap explicit in the graph.

---

## Wiring Activities to Lessons

Curriculum content becomes *real* when learners apply it through activities. SKUEL's 6 activity domains — Habits, Tasks, Events, Goals, Principles, Choices — wire directly to Lessons, making each Lesson a self-contained learning unit with built-in practice.

### The 6 Activity YAML Fields

Add these to any Lesson YAML:

```yaml
type: Lesson
uid: l:sel:understanding-others
title: Understanding Others — Empathy, Perspective, and Compassion
content: |
  ...

uses_kus:
  - ku:sel:empathy
  - ku:sel:perspective-taking

# Activity domain wiring
habit_uids:
  - habit:daily-empathy-check        # BUILDS_HABIT → Habit

task_uids:
  - task:perspective-journal          # ASSIGNS_TASK → Task

event_template_uids:
  - event:weekly-reflection           # SCHEDULES_EVENT → Event

goal_uids:
  - goal:deeper-listening             # SUPPORTS_GOAL → Goal

principle_uids:
  - principle:empathy-first           # GUIDED_BY_PRINCIPLE → Principle

choice_uids:
  - choice:ask-before-assuming        # INFORMS_CHOICE → Choice
```

Not every Lesson needs all 6. Use what fits the content.

### LearningStep Inherits from Lessons

LearningSteps do NOT have their own activity fields. They inherit activities from their constituent Lessons via graph traversal:

```
(LS)-[:HAS_LESSON]->(Lesson)-[:BUILDS_HABIT]->(Habit)
```

An LS with 3 Lessons automatically aggregates all their activities.

### Substance Tracking

When activities link back to Lessons, substance counters track how much knowledge is being *lived*: Habits (weight 0.10), Choices (0.07), Principles (0.07), Events (0.05), Tasks (0.05). Total capped at 1.0.

For the complete reference, see the **[Lesson Activity Wiring Guide](/docs/guides/LESSON_ACTIVITY_WIRING.md)** and the **[YAML Authoring Guide](/docs/guides/YAML_AUTHORING_GUIDE.md)**.

---

## What Comes Next

This guide covers the foundation: Kus, Lessons, prerequisite chains, and activity wiring. Future guides will cover:

- **Learning Steps and Learning Paths** — grouping lessons into collections and ordered sequences
- **Exercises and the Learning Loop** — attaching practice exercises to lessons, collecting student submissions, generating feedback reports, and creating targeted revisions
- **The Askesis Companion** — how the AI tutor uses your curriculum graph to guide learners through their zone of proximal development
- **Ingestion Workflows** — bulk ingestion, dry-run mode, incremental updates, and vault management

For now, start small. Pick a domain you know well. Define 8-12 Kus. Write 3-5 Lessons that compose them. Connect the Lessons into a chain. Wire activities to each Lesson. Ingest and see what the system builds from your content.

The graph grows one node at a time.

---

## Quick Reference

### File Locations

| What | Where |
|------|-------|
| Ku YAML files | `data/vault/ku_*.yaml` |
| Lesson YAML files | `data/vault/lesson_*.yaml` |
| YAML templates and schemas | `yaml_templates/_schemas/` |
| Existing SEL content | `yaml_templates/sel_*/` |

### UID Patterns

| Entity | Pattern | Example |
|--------|---------|---------|
| Ku | `ku:{namespace}:{slug}` | `ku:sel:empathy` |
| Lesson | `l:{namespace}:{slug}` | `l:sel:understanding-others` |

### SEL Categories

| Value | Competency |
|-------|------------|
| `self_awareness` | Understanding your emotions, values, and strengths |
| `self_management` | Managing emotions, behaviors, and achieving goals |
| `social_awareness` | Understanding and empathizing with others |
| `relationship_skills` | Building and maintaining healthy relationships |
| `responsible_decision_making` | Making ethical, constructive choices |

### Ku Categories

| Value | What It Is | Example |
|-------|-----------|---------|
| `concept` | Abstract idea | Empathy, Neuroplasticity |
| `practice` | Something you do | Active Listening, Meditation |
| `value` | Something you aspire to | Compassion, Honesty |
| `state` | Something you observe | Buzzing, Calm |
| `principle` | Guiding truth | Growth Mindset |
| `substance` | Chemical/physical agent | Caffeine |
| `intake` | Something consumed | Coffee |
