# Curriculum Developer Guide

**Purpose:** Show curriculum developers how to build structured, interconnected learning content for the SKUEL system — starting from atomic concepts (Kus), composing them into teaching narratives (Lessons), and linking everything into prerequisite chains that learners follow.

**Audience:** Curriculum developers and subject-matter experts creating content for SKUEL.app

**Prerequisite:** No coding experience required. You write YAML files and markdown. The system does the rest.

**Last Updated:** 2026-03-29

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

A Lesson is a **markdown file** (`.md`) with YAML frontmatter. Metadata goes in the frontmatter; the teaching content is the markdown body. The ingestion system automatically extracts the body as the `content` field.

```markdown
---
type: Lesson
uid: l:mindfulness:breath-awareness-basics
title: Breath Awareness — Basics
sel_category: self_awareness
learning_level: beginner
complexity: basic
domain: personal
estimated_time_minutes: 10

learning_objectives:
  - Understand why breath is used as a mindfulness anchor
  - Complete a two-minute breath awareness session

uses_kus:
  - ku:mindfulness:breath
  - ku:mindfulness:attention

connections:
  requires: []
  enables:
    - l:mindfulness:posture-basics
    - l:mindfulness:mind-wandering-happens

quality_score: 0.88

tags:
  - breath
  - meditation
  - beginner
---

## Why Breath?

You need an anchor — something to direct your attention toward...

## The Two-Minute Practice

Here's the whole thing. Two minutes.

1. **Sit comfortably.** Chair, floor, cushion — doesn't matter...
2. **Find the breath.** Don't change it. Just notice where you feel it most...

## Practice: Find Your Spot

Right now, take three natural breaths and answer one question:
where do you feel the breath most?
```

**Why `.md` instead of `.yaml`?** Lessons are content-heavy — the body is the whole point. Markdown gives you natural prose authoring, Obsidian preview, and the ingestion system automatically extracts the body as `content`. No need to cram long prose into YAML `|` string blocks.

**Format convention:**
- **Lessons** → `.md` files with YAML frontmatter (content-heavy, prose-first)
- **Everything else** (Kus, PS, LP, activities, edges) → `.yaml` files (metadata-heavy, little/no prose)

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

Place your YAML files in the default ingestion vault at `data/vault/` (i.e., `/home/mike/skuel/app/data/vault/`), configurable via `INGESTION_PATH` env var, and ingest them through the system. The ingestion pipeline will:

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

## A Second Worked Example: Mindfulness 101 + Self-Reflection 101

The SEL chain above is linear and self-contained. This example shows two things the SEL chain doesn't: **the full four-entity curriculum stack** (Ku → Lesson → PathStep → LearningPath) and **cross-domain progression** (one learning path leading into another).

### The Two Domains

**Mindfulness 101** teaches the foundational skill: noticing. Three lessons, two path steps, one learning path.

**Self-Reflection 101** builds on that skill: once you can notice your breath and label your wandering mind, turn that capacity toward your behavior, emotions, and values. Three lessons, two path steps, one learning path. It declares Mindfulness 101 as a prerequisite.

```
Mindfulness 101                          Self-Reflection 101
  PS Step 1: Two Minutes Today             PS Step 1: Notice Your Patterns
    └── Lesson: Breath Awareness             └── Lesson: Noticing Patterns
    └── Lesson: Posture Basics               └── Lesson: Emotional Awareness
  PS Step 2: Name The Wanders             PS Step 2: Understand Your Values
    └── Lesson: Mind Wandering               └── Lesson: Values Discovery
                                             └── Lesson: Emotional Awareness
         lp:mindfulness-101  ──PREREQUISITE_FOR──>  lp:self-reflection-101
```

### The Four-Entity Stack

This is the full curriculum hierarchy in action:

| Layer | What It Does | Example |
|-------|-------------|---------|
| **Ku** | Defines one atomic concept | `ku:mindfulness:breath` — "The natural rhythm of breathing, used as the primary anchor for attention" |
| **Lesson** | Composes Kus into a teaching narrative with practice exercises | `l:mindfulness:breath-awareness-basics` — 10-minute lesson teaching the two-minute practice |
| **PathStep** | Groups related lessons into a step with a clear intent | `ls:mindfulness-101:step-1` — "Try one two-minute breath session and notice where you feel the breath" |
| **LearningPath** | Sequences steps into a learner journey | `lp:mindfulness-101` — beginner path from breath to labeling |

Each layer has a distinct purpose. Kus don't teach. Lessons don't sequence. Steps don't define concepts. Paths don't contain content. Mixing these roles creates confusion.

### Cross-Domain Edges

The connection between the two domains is declared in a standalone edge file:

```yaml
# edges/edge_mindfulness-to-self-reflection.yaml
version: 1.0
edges:
  - from: lp:mindfulness-101
    to: lp:self-reflection-101
    type: PREREQUISITE_FOR

  - from: ku:mindfulness:attention
    to: ku:self-reflection:self-observation
    type: PREREQUISITE_FOR

  - from: l:mindfulness:mind-wandering-happens
    to: l:self-reflection:noticing-patterns
    type: ENABLES
```

This creates a progression: a learner who completes Mindfulness 101 is ready for Self-Reflection 101. The attention training skill (labeling mind-wanders) becomes the self-observation skill (labeling behavioral patterns). Same muscle, different context.

### Supporting Activity Entities

Each domain wires activities to its lessons. The Mindfulness 101 bundle includes:
- `habit:daily-2min-breath` — the core daily practice
- `task:log-first-5-sessions` — a one-time logging task
- `event:practice-block-2min` — a recurring calendar template
- `goal:mindfulness-beginner` — the four-week process goal
- `principle:small-steps` — the guiding principle
- `choice:2-minutes-right-now` — the immediate action prompt

Self-Reflection 101 has its own parallel set: different habits, tasks, and principles — but the same structural pattern. Activities connect back to their domain's lessons via the `connections` block and substance tracking.

### Lesson Content Design (Inspired by Practice-Reflection Structure)

Every lesson in both bundles follows the same content arc:

1. **Why this matters** — connect to what the learner already knows
2. **Core concept** — explain the idea clearly, no jargon
3. **The technique** — step-by-step, concrete, doable right now
4. **Common mistakes** — what to watch for (normalizes difficulty)
5. **Practice** — a specific exercise the learner can do today

The practice section is not optional decoration — it's the point. A lesson without a practice exercise is an essay, not a teaching unit.

### File Layout

```
data/vault/
  # Mindfulness 101
  ku_breath.yaml                          # Kus (YAML — metadata only)
  ku_attention.yaml
  lesson_breath-awareness-basics.md       # Lessons (Markdown — content-heavy)
  lesson_posture-basics.md
  lesson_mind-wandering-happens.md
  ls_mindfulness-101_step-1.yaml          # Path Steps (YAML)
  ls_mindfulness-101_step-2.yaml
  lp_mindfulness-101.yaml                 # Learning Path (YAML)
  edges/edge_mindfulness-101-curriculum.yaml  # Internal edges
  # Self-Reflection 101
  ku_self-observation.yaml
  ku_emotional-patterns.yaml
  ku_personal-values.yaml
  lesson_noticing-patterns.md
  lesson_emotional-awareness.md
  lesson_values-discovery.md
  ls_self-reflection-101_step-1.yaml
  ls_self-reflection-101_step-2.yaml
  lp_self-reflection-101.yaml
  edges/edge_self-reflection-101-curriculum.yaml
  # Cross-domain
  edges/edge_mindfulness-to-self-reflection.yaml
```

Notice the format convention: `.md` for lessons (content-heavy), `.yaml` for everything else (metadata-heavy).

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

### PathStep Inherits from Lessons

PathSteps do NOT have their own activity fields. They inherit activities from their Lessons via graph traversal:

```
(PS)-[:CONTAINS_KNOWLEDGE]->(Lesson)-[:BUILDS_HABIT]->(Habit)
```

An PS with 3 Lessons automatically aggregates all their activities. Wire activity fields to the Lessons listed in `knowledge_uids`.

### Substance Tracking

When activities link back to Lessons, substance counters track how much knowledge is being *lived*: Habits (weight 0.10), Choices (0.07), Principles (0.07), Events (0.05), Tasks (0.05). Total capped at 1.0.

For the complete reference, see the **[Lesson Activity Wiring Guide](/docs/guides/LESSON_ACTIVITY_WIRING.md)** and the **[YAML Authoring Guide](/docs/guides/YAML_AUTHORING_GUIDE.md)**.

---

## Building a Domain Bundle: The Practical Workflow

This is the sequence that works in practice. It was refined by building the Mindfulness 101 and Self-Reflection 101 bundles.

### Step 1: Start with the Kus (5 minutes)

Define 2-4 atomic concepts. Keep them tiny. If you're writing more than one paragraph for a Ku description, you're teaching — and teaching belongs in a Lesson.

### Step 2: Write the Lessons (the bulk of the work)

This is where you spend most of your time. Each lesson is a `.md` file with frontmatter metadata and a markdown body. Write in second person. Be direct. Include a practice exercise at the end.

A good lesson takes 30-60 minutes to write well. Three lessons is a good starting size.

### Step 3: Define the Supporting Activities (10 minutes each)

For each lesson, ask: what should the learner *do* with this knowledge?

- **Habit** — a repeating behavior (daily 2-minute practice)
- **Task** — a one-time deliverable (write three sentences about your patterns)
- **Goal** — a multi-week process goal (build a daily practice over four weeks)
- **Principle** — a guiding value (observation before action)
- **Choice** — a decision prompt (do two minutes right now)
- **Event** — a calendar template (evening check-in)

Not every lesson needs all six. Wire what fits.

### Step 4: Build the Structure (PS, LP, edges)

Group lessons into Path Steps. Sequence steps into a Learning Path. Write edge files for the curriculum structure and any cross-domain connections.

### Step 5: Review the Graph

Before ingesting, mentally walk the graph:
- Can a learner start from the LP and follow a clear path?
- Does every PS have at least one lesson?
- Does every lesson compose at least one Ku?
- Are activities wired to the right lessons?
- Are cross-domain connections declared in edge files?

### Step 6: Ingest

Place files in `data/vault/` and ingest. The system handles node creation, relationship wiring, embedding generation, and indexing.

## What Comes Next

This guide covers: Kus, Lessons, prerequisite chains, activity wiring, the four-entity curriculum stack (Ku → Lesson → PS → LP), cross-domain progression, and the practical workflow. Future guides will cover:

- **Exercises and the Learning Loop** — attaching practice exercises to lessons, collecting student submissions, generating feedback reports, and creating targeted revisions
- **The Askesis Companion** — how the AI tutor uses your curriculum graph to guide learners through their zone of proximal development
- **Ingestion Workflows** — bulk ingestion, dry-run mode, incremental updates, and vault management

Start small. Pick a domain. Define 2-4 Kus. Write 3 Lessons as `.md` files. Wire a few activities. Build the PS/LP structure. Write edge files. Ingest and see what the system builds.

The graph grows one node at a time.

---

## Quick Reference

### File Locations

| What | Where | Format |
|------|-------|--------|
| Ku files | `data/vault/ku_*.yaml` | YAML |
| Lesson files | `data/vault/lesson_*.md` | Markdown + YAML frontmatter |
| PathStep files | `data/vault/ls_*.yaml` | YAML |
| LearningPath files | `data/vault/lp_*.yaml` | YAML |
| Activity files | `data/vault/{type}_*.yaml` | YAML |
| Edge files | `data/vault/edges/edge_*.yaml` | YAML |
| Templates and schemas | `yaml_templates/_schemas/` | YAML |
| Worked examples | `yaml_templates/lesson_ls_lp/` | Mixed |

### UID Patterns

| Entity | Pattern | Example |
|--------|---------|---------|
| Ku | `ku:{namespace}:{slug}` | `ku:mindfulness:breath` |
| Lesson | `l:{namespace}:{slug}` | `l:mindfulness:breath-awareness-basics` |
| PathStep | `ls:{path}:{slug}` | `ls:mindfulness-101:step-1` |
| LearningPath | `lp:{slug}` | `lp:mindfulness-101` |
| Activity | `{type}:{slug}` | `habit:daily-2min-breath` |

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
