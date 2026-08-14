# Curriculum Developer Guide

**Purpose:** Show curriculum developers how to build structured, interconnected learning content for the SKUEL system — starting from atomic concepts (Kus), composing them into teaching narratives (PathSteps), and linking everything into prerequisite chains that learners follow.

**Audience:** Curriculum developers and subject-matter experts creating content for SKUEL.app

**Prerequisite:** No coding experience required. You write YAML files and markdown. The system does the rest.

**Last Updated:** 2026-06-20

> **Historical note (2026-04):** SKUEL previously had a separate `Lesson` entity type sitting between `Ku` and `PathStep`. Lesson was merged into PathStep in April 2026 — PathStep now IS the teaching narrative. The three-entity curriculum stack is **Ku → PathStep → LearningPath**. Older docs and ADRs may still reference Lesson; treat those as historical.

---

## The Big Idea

SKUEL separates **what you know** from **how you learn it**.

- A **Ku** (Knowledge Unit) is an atomic concept — a single definable thing. It exists as a reference node in the knowledge graph. It has no teaching narrative, no exercises, no learning objectives. It just *is*.
- A **PathStep** is a unit for learning — a teaching narrative that composes multiple Kus into coherent content. PathSteps are where explanation, examples, exercises, and voice live. PathSteps are also the anchor of the learning loop: exercises, submissions, and feedback all attach to a PathStep.

This separation is deliberate. The same Ku — say, *Empathy* — can appear in a PathStep about social awareness, a PathStep about conflict resolution, a PathStep about leadership, and a PathStep about parenting. The concept is defined once; it's taught many ways.

Your job as a curriculum developer is to:

1. **Define the atoms** — write Kus that capture individual concepts clearly
2. **Compose the narratives** — write PathSteps that weave those Kus into teachable stories
3. **Build the chains** — connect PathSteps into prerequisite sequences so learners know where to start and where to go next

---

## A Worked Example: The SEL Prerequisite Chain

The best way to understand the system is to see it in action. SKUEL ships with a reference curriculum built around the five CASEL Social-Emotional Learning competencies. This section walks through how it was designed and why.

### The Five PathSteps

```
Knowing Yourself → Managing Yourself → Understanding Others → Building Relationships → Making Good Decisions
     (SA)              (SM)                 (SOA)                  (RS)                    (RDM)
```

Each PathStep covers one SEL competency. Each composes exactly four Kus. Each links forward to the next via a prerequisite connection. The result is a linear chain that a learner can follow from start to finish — or enter at any point if they already have the prerequisites.

### Why This Order?

The order is not arbitrary. It follows a pedagogical logic:

1. **Knowing Yourself** (Self-Awareness) comes first because everything else depends on it. You cannot manage emotions you cannot name. You cannot empathize with others if you don't understand your own experience.

2. **Managing Yourself** (Self-Management) builds on self-awareness. Once you can identify what you're feeling, the next question is: what do I do about it? Goals, habits, impulse control, and stress management are the tools.

3. **Understanding Others** (Social Awareness) is the outward turn. The inward skills (awareness + management) now point toward other people. Empathy, perspective-taking, cultural awareness, and compassion require self-knowledge as a foundation — otherwise you project instead of perceive.

4. **Building Relationships** (Relationship Skills) applies social awareness in practice. Active listening, boundary setting, conflict resolution, and teamwork are empathy made concrete.

5. **Making Good Decisions** (Responsible Decision-Making) is the capstone. It synthesizes all four prior competencies: know yourself, manage yourself, understand others, relate to others — and now, choose wisely. The final PathStep explicitly names this synthesis and closes the loop back to self-awareness.

This is not the only valid sequence. A curriculum developer might choose a different entry point, a different grouping, or a spiral structure that revisits competencies at increasing depth. The point is that the order should be *intentional* and *justified*, not accidental.

### How Each PathStep Composes Four Kus

Each PathStep in the chain declares exactly four Kus in its `uses_kus` field. Here's the mapping:

| PathStep | Ku 1 | Ku 2 | Ku 3 | Ku 4 |
|----------|-------|-------|-------|-------|
| Knowing Yourself | Emotions | Emotional Triggers | Self-Worth | Growth Mindset |
| Managing Yourself | Goal Setting | Habits | Impulse Control | Stress Management |
| Understanding Others | Empathy | Perspective-Taking | Cultural Awareness | Compassion |
| Building Relationships | Active Listening | Conflict Resolution | Teamwork | Boundary Setting |
| Making Good Decisions | Ethical Reasoning | Consequence Analysis | Identifying Problems | Reflecting on Choices |

Four is not a magic number. A PathStep might compose two Kus or seven. But four works well for beginner-level content because it's enough to create connections between ideas without overwhelming the learner. The constraint also forces you to choose — which concepts are *essential* to this PathStep's narrative?

The relationship between a PathStep and its Kus is **composition, not coverage**. A PathStep on "Understanding Others" doesn't just *mention* empathy — it weaves empathy into a narrative alongside perspective-taking, cultural awareness, and compassion, showing how these four concepts interact. The Ku provides the definition; the PathStep provides the meaning.

### How Prerequisite Chains Work

In each PathStep YAML, the `connections` field declares what must come before and what comes after:

```yaml
# From ps_managing-yourself.yaml
connections:
  requires:
    - ps.sel.knowing-yourself       # Must complete this first
  enables:
    - ps.sel.understanding-others   # Unlocks this next
```

When ingested, the system creates directed relationships in the knowledge graph:

```
(Knowing Yourself)──ENABLES──>(Managing Yourself)──ENABLES──>(Understanding Others)──ENABLES──>...
```

These relationships power:
- **Prerequisite checking** — the system can warn a learner if they're jumping ahead
- **Learning path generation** — the system can build ordered sequences from the graph
- **Progress tracking** — the system knows which PathSteps unlock next based on what's been completed

A PathStep with no `requires` is an entry point — anyone can start there. A PathStep with no `enables` is a terminal — it's the end of a chain (or the start of a new one, once you extend it).

### How the Loop Closes

The final PathStep — *Making Good Decisions* — has no `enables` connection. But thematically, it loops back to self-awareness:

> *"Decisions reveal who you are — which brings you back to self-awareness. The loop never ends. It just deepens."*

This is intentional. The prerequisite chain is linear (A → B → C → D → E), but the *conceptual* structure is circular. A learner who completes the chain is better equipped to start it again at a deeper level. This creates a natural opening for intermediate and advanced content that revisits the same five competencies with greater nuance.

In SKUEL's graph, this circularity is captured not through prerequisite edges (which would create cycles) but through the Ku layer. The Kus in the first PathStep (Emotions, Emotional Triggers) and the Kus in the last PathStep (Reflecting on Choices) share semantic connections — reflection *is* a form of self-awareness. A curriculum developer building the next level of content can make this explicit:

```yaml
# A future advanced PathStep
connections:
  requires:
    - ps.sel.making-good-decisions   # Completed the beginner chain
    - ps.sel.knowing-yourself        # Revisiting self-awareness at depth
```

---

## The Three Primitives: Ku, PathStep, and Exercise

### Writing a Ku

A Ku is a YAML file with no content body. It defines a concept.

```yaml
version: 1.0
type: Ku

uid: ku.sel.empathy
title: Empathy
aliases:
  - perspective-taking
  - emotional attunement
  - understanding others
nous:
  - social
  - relationships
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
| `uid` | Unique identifier (`ku.{group}.{slug}` — the middle token is an opaque grouping label, not a stored field) | Yes |
| `title` | Display name | Yes |
| `nous` | Topic-section membership — zero or more of the 11 official sections | No (empty is valid) |
| `sel_category` | Which SEL competency it belongs to | No (only for SEL content) |
| `aliases` | Alternative names for search | No |
| `description` | One-paragraph summary | No, but strongly recommended |
| `tags` | For filtering and search | No |

The 11 `nous` sections: `stories`, `environment`, `intelligence`, `investment`, `words`, `relationships`, `social`, `body`, `exercises`, `self-management`, `self-awareness`. The vocabulary is derived from the graph, not enum-validated — use the exact slugs.

**Grouping-label vocabulary (rulings 2026-08-14):** the middle UID token is a human-readable
grouping hint (machine-opaque — hierarchy lives in edges). To keep the hints coherent across
authoring sessions:

- **`mind` vs `mindfulness` are distinct families, kept deliberately.** `mind` = cognition
  (mistakes, cognitive-biases, ego, conditioning); `mindfulness` = the practice (attention,
  breath, anchors). Don't merge them.
- **`sel` vs `self-*`:** use `sel` for framework-level entities (the CASEL/SEL frame itself,
  cross-competency content); use the specific competency (`self-awareness`, `self-management`,
  `self-reflection`) when the entity belongs to one competency.
- **Course-bound steps use the course slug as their grouping label** —
  `ps.mindfulness-101.step-1`, `ps.mindfulness-101.intro` — so a course's steps read as one
  family. Freestanding steps keep a topic namespace (`ps.mindfulness.posture-basics`). Real
  membership is always the `HAS_STEP` edge; the label is the human hint.

Changing an existing entity's UID is an **identity change** (a new node) — harmonize labels in
deliberate passes, not casual edits.

**Guidelines:**

- **One concept per Ku.** If you're writing "and" in the title, you probably have two Kus.
- **Describe, don't teach.** The description should define the concept, not explain how to develop it. Teaching belongs in PathSteps.
- **Assign `nous` deliberately.** Place the Ku in the topic sections a learner would browse to find it. Leaving it empty is fine — a Ku can exist before it belongs to a section.
- **Use `aliases` generously.** Learners search with different words. If your Ku is "Impulse Control," aliases like "self-regulation" and "pause before acting" help the system surface it.

### Writing a PathStep

A PathStep is a **markdown file** (`.md`) with YAML frontmatter. Metadata goes in the frontmatter; the teaching content is the markdown body. The ingestion system automatically extracts the body as the `content` field.

```markdown
---
type: PathStep
uid: ps.mindfulness.breath-awareness-basics
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
  - ku.mindfulness.breath
  - ku.mindfulness.attention

exercise_uids:
  - ex.mindfulness.breath-awareness-check-in

connections:
  requires: []
  enables:
    - ps.mindfulness.posture-basics
    - ps.mindfulness.mind-wandering-happens

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

**Why `.md` instead of `.yaml`?** PathSteps are content-heavy — the body is the whole point. Markdown gives you natural prose authoring, Obsidian preview, and the ingestion system automatically extracts the body as `content`. No need to cram long prose into YAML `|` string blocks.

**Format convention:**
- **PathSteps** → `.md` files with YAML frontmatter (content-heavy, prose-first)
- **Everything else** (Kus, LP, activities, edges) → `.yaml` files (metadata-heavy, little/no prose)

**Key fields:**

| Field | Purpose | Required? |
|-------|---------|-----------|
| `uid` | Unique identifier (`ps.{namespace}.{slug}`) | Yes |
| `title` | Display name | Yes |
| `content` | Full markdown teaching narrative (auto-extracted from body) | Yes |
| `uses_kus` | Which atomic Kus this PathStep composes | No, but essential for graph |
| `connections.requires` | Prerequisite PathStep UIDs | No |
| `connections.enables` | PathSteps this unlocks | No |
| `learning_level` | Target level (beginner, intermediate, advanced, expert) | No |
| `complexity` | Difficulty (basic, medium, advanced) | No |
| `estimated_time_minutes` | Reading time in minutes | No |
| `learning_objectives` | What the learner will gain | No |

**Guidelines for the content body:**

- **Start with why.** The first section should answer: why does this matter? Why now? Connect it to what the learner already knows (the prerequisite PathStep).
- **Use headers to chunk.** Each `##` section should be one digestible idea. A learner should be able to pause after any section and resume later.
- **Include a practice exercise.** Every PathStep should end with something the learner can *do*. Not "think about this" — something concrete, specific, and achievable today.
- **Close with what's next.** Point forward to the next PathStep in the chain. This creates momentum and gives the learner a reason to continue.
- **Write in second person.** "You" is more engaging than "the learner" or "one." This is a conversation, not a textbook.
- **Be direct.** Short sentences. Active voice. Say what you mean. Cut filler.

### Writing an Exercise

An Exercise is a practice prompt attached to a PathStep. It closes the learning loop: the learner responds, the system (teacher or AI) evaluates, and targeted revision follows. Exercises are the third authoring primitive — alongside Kus and PathSteps — because they are what turn a reading into a *doing*.

An Exercise is a YAML file with an `instructions` field (the LLM prompt that processes the learner's submission) and an optional `form_schema` (for structured form responses rather than free-form uploads).

```yaml
version: 1.0
type: Exercise

uid: ex.sel.know-yourself-check-in
title: Know Yourself Check-In
description: A structured self-awareness reflection exercise
scope: curriculum
model: claude-sonnet-4-6
mastery_impact: moderate
sel_category: SELF_AWARENESS
learning_level: BEGINNER
tags: [self-awareness, reflection]

instructions: |
  You are a self-awareness coach. The student has answered two questions
  about their emotional experience today. Review their responses and provide
  warm, specific feedback in 3–5 sentences. Name what they did well. Point
  to one thing they could notice more clearly next time.

form_schema:
  - name: emotion_check
    type: textarea
    label: "Name one emotion you felt strongly today. What triggered it?"
    required: true
  - name: daily_habit
    type: text
    label: "What one habit will you build to increase self-awareness?"
    required: true
```

**Key fields:**

| Field | Purpose | Required? |
|-------|---------|-----------|
| `uid` | Unique identifier (`ex.{namespace}.{slug}`) | Yes |
| `title` | Display name | Yes |
| `scope` | Must be `curriculum` (shared vault-authored content, no user owner). `personal`/`assigned`/`assessment` are app-created only — ingestion rejects them (they describe an owner or group the file boundary cannot provide) | No (ingestion default: `curriculum`) |
| `instructions` | The LLM prompt that processes the learner's submission | Yes |
| `model` | Which LLM to use (default: `claude-sonnet-4-6`) | No |
| `form_schema` | Structured form fields — if present, submission is a form; if absent, submission is a file upload | No |
| `mastery_impact` | How aggressively completing this Exercise advances mastery (`minor`, `moderate`, `major`, `certification`) | No |
| `sel_category` | Which SEL competency this Exercise targets | No |
| `learning_level` | `BEGINNER`, `INTERMEDIATE`, `ADVANCED`, `EXPERT` | No |

**How the loop closes:**

Once an Exercise is wired to a PathStep (via `(PathStep)-[:HAS_EXERCISE]->(Exercise)`), the four-phase loop runs automatically:

```
1  Exercise    — the practice prompt the learner works from
2  UserEntry   — the learner's response (file upload or form submission)
3  EntryReport — AI or teacher evaluates the UserEntry against the Exercise instructions
4  RevisedExercise — teacher creates a targeted follow-up prompt if revision is needed
```

The learner sees all four phases on the PathStep detail page at `/explore/ps/{uid}`. For the full loop mechanics, see [The Learning Loop Architecture](/docs/architecture/LEARNING_LOOP_ARCHITECTURE.md).

**Guidelines:**

- **Instructions should be prompts, not rubrics.** The `instructions` field is sent to the LLM as context when generating an EntryReport. Write it as a persona + task, not a checklist. "You are a coach. Do X." works better than "Check for: criterion A, criterion B, criterion C."
- **Use `form_schema` for beginner content.** A structured form lowers the barrier to entry for new learners. File upload (the default when `form_schema` is absent) works well for intermediate and advanced exercises where the learner needs to produce prose.
- **Anchor Exercises from the PathStep side.** List each vault Exercise under `exercise_uids:` in the owning PathStep's frontmatter — ingestion creates the `(PathStep)-[:HAS_EXERCISE]->(Exercise)` edge. An unanchored curriculum Exercise is invisible to learners (no discovery surface reaches it).
- **`mastery_impact: moderate` is the right default.** Use `minor` for low-stakes reflections, `major` for capstone submissions, `certification` only for formal assessments.

---

### How the PathStep ↔ Exercise Connection is Stored

When you write `exercise_uids: [ex.mindfulness-101.breath-awareness-check-in]` in a
PathStep YAML, you might assume this sets a property on the PathStep — something like
`exercise_uid = "ex:..."` stored alongside its title and description. It does not. This
section explains what actually happens, because misunderstanding it leads to incorrect
assumptions about how to query and build on this relationship.

**What the YAML field creates: a graph edge**

```yaml
# PathStep YAML
exercise_uids:
  - ex.mindfulness-101.breath-awareness-check-in
```

This creates one thing in the database: a directed graph relationship.

```
(PathStep)-[:HAS_EXERCISE]->(Exercise)
```

No property is stored on the PathStep node. The PathStep node has no `exercise_uid` or
`exercise_uids` field. The *connection itself* — the `HAS_EXERCISE` edge — is the storage.

**Why an edge and not a property**

SKUEL runs on Neo4j, a graph database. In a graph database, traversing a relationship
edge is a direct pointer lookup — constant-time, not a scan. Asking "which exercises
belong to this PathStep?" follows the `HAS_EXERCISE` outgoing edges from that PathStep.
This is already the fast path; no property is needed to make it faster.

There is also a cardinality reason. A PathStep can anchor multiple Exercises (different
scopes, different levels, different forms). Storing a list of UIDs as a property on the
PathStep node would require reading and rewriting that list every time an Exercise is
added — a race-condition-prone read-modify-write cycle. The edge model handles any number
of Exercises naturally: each new Exercise is a single atomic write.

**The reverse direction: Exercise.path_step_uid**

The relationship is stored in one other place: as a property *on the Exercise node itself*.

```
Exercise.path_step_uid = "ps.mindfulness-101.breath-awareness-basics"
```

This covers the reverse direction. Given an Exercise, you can read which PathStep it
belongs to directly from the Exercise node — no graph traversal needed. This is a scalar
(one value) because a PERSONAL-scope Exercise always belongs to exactly one PathStep.

**How path_step_uid gets written depends on how the Exercise was created:**

- **API creation** (`ExerciseService.create()`): dual-write — both `path_step_uid` on
  the Exercise node and the `HAS_EXERCISE` edge are written in a single operation.
- **YAML ingestion** (PathStep side, `exercise_uids`): only the `HAS_EXERCISE` edge is
  created. The `exercise_uids` field is treated as a relationship key by the ingestion
  pipeline — it is filtered out of node properties and never written to the PathStep node
  or backfilled onto the Exercise node.

For YAML-authored exercises, if you want `Exercise.path_step_uid` to be populated (enabling
the no-traversal reverse lookup), include `path_step_uid` in the Exercise YAML itself:

```yaml
type: Exercise
uid: ex.mindfulness-101.breath-awareness-check-in
path_step_uid: ps.mindfulness-101.breath-awareness-basics
...
```

**Summary**

| Question | How the system answers it | Storage form |
|---|---|---|
| Which exercises does this PathStep have? | Follow `HAS_EXERCISE` edges outward | Graph edge (no property on PathStep) |
| Which PathStep does this Exercise belong to? | Read `Exercise.path_step_uid` (if set) or traverse incoming `HAS_EXERCISE` edge | Property on Exercise node (API path) or graph traversal (YAML path) |

**What this means for you as an author**

- `exercise_uids` in your PathStep YAML creates the `HAS_EXERCISE` edge. This is
  sufficient for the learning loop — the PathStep detail page uses the edge for all
  exercise lookups.
- To also populate `Exercise.path_step_uid` (the reverse-direction property), set
  `path_step_uid` in the Exercise YAML. This is optional for YAML-authored exercises
  but required if you later create UserEntries via the API against this Exercise.
- If you remove `exercise_uids` from a PathStep YAML and re-ingest with deletion
  propagation enabled, the `HAS_EXERCISE` edge is deleted. The Exercise node remains,
  but it is no longer anchored to that PathStep and will not appear on the PathStep
  detail page.
- An Exercise without a PathStep anchor (no `HAS_EXERCISE` edge) is an orphan. The
  learning loop cannot close for it. Always wire Exercises to their PathStep via
  `exercise_uids`.

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

For each PathStep in your chain, identify 2-6 atomic concepts that the PathStep will compose. Write these as Ku YAML files first.

Ask yourself:
- Is this truly atomic? Could I define this in one paragraph?
- Could this Ku appear in a *different* PathStep in a *different* context?
- Am I defining a concept, or am I already teaching? (If teaching, it belongs in the PathStep.)

### Step 3: Write the PathSteps

Now write each PathStep's content, weaving its Kus into a narrative. The Kus are your building blocks; the PathStep is the structure you build with them.

For each PathStep:
1. State the `uses_kus` — which Kus does this PathStep compose?
2. State the `connections` — what must come before? What does this unlock?
3. Write the content — the teaching narrative itself

### Step 4: Validate the Chain

Before ingesting, review the chain as a whole:

- **No orphans:** Every PathStep (except entry points) has at least one `requires`. Every PathStep (except terminals) has at least one `enables`.
- **No circular prerequisites:** The `requires`/`enables` graph must be a DAG (directed acyclic graph). Thematic loops are fine; prerequisite loops are not.
- **Ku coverage:** Every Ku referenced in `uses_kus` should have a corresponding Ku YAML file. The ingestion system will create the relationship even if the Ku doesn't exist yet, but dangling references make the graph messy.
- **Entry points are clear:** A new learner should be able to look at the chain and know where to start. If your chain has multiple entry points, that's fine — but make it intentional.

### Step 5: Ingest

Place your YAML files in the default ingestion vault at `/home/mike/0bsidian/0vault/` (configurable via `INGESTION_PATH` env var), and ingest them through the system. The ingestion pipeline will:

1. Parse each YAML/markdown file
2. Create graph nodes for each Ku and PathStep
3. Create `USES_KU` relationships between PathSteps and their composed Kus
4. Create `ENABLES`/`REQUIRES` relationships between PathSteps
5. Index content for search and RAG retrieval

---

## Beyond Linear Chains

The SEL example is a straight line: A → B → C → D → E. Real curricula are rarely this simple. Here are patterns you'll encounter as you build more content.

### Branching

After a foundational PathStep, learners might choose between two parallel paths:

```
Foundations
    ├── Track A: Interpersonal Skills
    │   ├── PathStep A1
    │   └── PathStep A2
    └── Track B: Intrapersonal Skills
        ├── PathStep B1
        └── PathStep B2
```

Both A1 and B1 declare `requires: [ps.foundations]`. Neither requires the other.

### Convergence

Two parallel tracks merge into a capstone:

```yaml
# Capstone PathStep
connections:
  requires:
    - ps.track-a.lesson-a2
    - ps.track-b.lesson-b2
```

The learner must complete both tracks before the capstone unlocks.

### Spiral

The same competency taught at increasing depth:

```
Empathy (Beginner) → Empathy (Intermediate) → Empathy (Advanced)
```

Each level uses some of the same Kus but adds new ones. The beginner PathStep might use `ku.sel.empathy` and `ku.sel.perspective-taking`. The advanced PathStep might add `ku.sel.compassion-fatigue` and `ku.sel.structural-empathy`. The Ku layer makes this overlap explicit in the graph.

---

## A Second Worked Example: Mindfulness 101 + Self-Reflection 101

The SEL chain above is linear and self-contained. This example shows two things the SEL chain doesn't: **the full three-entity curriculum stack** (Ku → PathStep → LearningPath) and **cross-domain progression** (one learning path leading into another).

### The Two Domains

**Mindfulness 101** teaches the foundational skill: noticing. Three PathSteps, one learning path.

**Self-Reflection 101** builds on that skill: once you can notice your breath and label your wandering mind, turn that capacity toward your behavior, emotions, and values. Three PathSteps, one learning path. It declares Mindfulness 101 as a prerequisite.

```
Mindfulness 101                          Self-Reflection 101
  PS: Breath Awareness                     PS: Noticing Patterns
  PS: Posture Basics                       PS: Emotional Awareness
  PS: Mind Wandering Happens               PS: Values Discovery

         lp.mindfulness-101  ──PREREQUISITE_FOR──>  lp.self-reflection-101
```

### The Three-Entity Stack

This is the full curriculum hierarchy in action:

| Layer | What It Does | Example |
|-------|-------------|---------|
| **Ku** | Defines one atomic concept | `ku.mindfulness.breath` — "The natural rhythm of breathing, used as the primary anchor for attention" |
| **PathStep** | Composes Kus into a teaching narrative with practice exercises | `ps.mindfulness.breath-awareness-basics` — 10-minute step teaching the two-minute practice |
| **LearningPath** | Sequences PathSteps into a learner journey | `lp.mindfulness-101` — beginner path from breath to labeling |

Each layer has a distinct purpose. Kus don't teach. PathSteps don't sequence an entire journey. Paths don't contain content. Mixing these roles creates confusion.

### Cross-Domain Edges

The connection between the two domains is declared in a standalone edge file:

```yaml
# edges/edge_mindfulness-to-self-reflection.yaml
version: 1.0
edges:
  - from: lp.mindfulness-101
    to: lp.self-reflection-101
    type: PREREQUISITE_FOR

  - from: ku.mindfulness.attention
    to: ku.self-reflection.self-observation
    type: PREREQUISITE_FOR

  - from: ps.mindfulness.mind-wandering-happens
    to: ps.self-reflection.noticing-patterns
    type: ENABLES
```

This creates a progression: a learner who completes Mindfulness 101 is ready for Self-Reflection 101. The attention training skill (labeling mind-wanders) becomes the self-observation skill (labeling behavioral patterns). Same muscle, different context.

### Supporting Activity Entities

Each domain wires activities directly to its PathSteps. The Mindfulness 101 bundle includes:
- `habit.daily-2min-breath` — the core daily practice
- `task.log-first-5-sessions` — a one-time logging task
- `event.practice-block-2min` — a recurring calendar template
- `goal.mindfulness-beginner` — the four-week process goal
- `principle.small-steps` — the guiding principle
- `choice.2-minutes-right-now` — the immediate action prompt

Self-Reflection 101 has its own parallel set: different habits, tasks, and principles — but the same structural pattern. Activities connect back to their domain's PathSteps via the `connections` block and substance tracking.

### PathStep Content Design

Every PathStep in both bundles follows the same content arc:

1. **Why this matters** — connect to what the learner already knows
2. **Core concept** — explain the idea clearly, no jargon
3. **The technique** — step-by-step, concrete, doable right now
4. **Common mistakes** — what to watch for (normalizes difficulty)
5. **Practice** — a specific exercise the learner can do today

The practice section is not optional decoration — it's the point. A PathStep without a practice exercise is an essay, not a teaching unit.

### File Layout

```
/home/mike/0bsidian/0vault/
  # Mindfulness 101
  ku_breath.yaml                     # Kus (YAML — metadata only)
  ku_attention.yaml
  ps_breath-awareness-basics.md      # PathSteps (Markdown — content-heavy)
  ps_posture-basics.md
  ps_mind-wandering-happens.md
  lp_mindfulness-101.yaml            # Learning Path (YAML)
  edges/edge_mindfulness-101-curriculum.yaml  # Internal edges
  # Self-Reflection 101
  ku_self-observation.yaml
  ku_emotional-patterns.yaml
  ku_personal-values.yaml
  ps_noticing-patterns.md
  ps_emotional-awareness.md
  ps_values-discovery.md
  lp_self-reflection-101.yaml
  edges/edge_self-reflection-101-curriculum.yaml
  # Cross-domain
  edges/edge_mindfulness-to-self-reflection.yaml
```

Notice the format convention: `.md` for PathSteps (content-heavy), `.yaml` for everything else (metadata-heavy).

---

## Wiring Activities to PathSteps

Curriculum content becomes *real* when learners apply it through activities. SKUEL's 6 activity domains — Habits, Tasks, Events, Goals, Principles, Choices — wire directly to PathSteps, making each PathStep a self-contained learning unit with built-in practice.

### The 6 Activity YAML Fields

Add these to any PathStep frontmatter:

```yaml
type: PathStep
uid: ps.sel.understanding-others
title: Understanding Others — Empathy, Perspective, and Compassion

uses_kus:
  - ku.sel.empathy
  - ku.sel.perspective-taking

# Activity domain wiring
habit_uids:
  - habit.daily-empathy-check        # BUILDS_HABIT → Habit

task_uids:
  - task.perspective-journal          # ASSIGNS_TASK → Task

event_template_uids:
  - event.weekly-reflection           # SCHEDULES_EVENT → Event

goal_uids:
  - goal.deeper-listening             # SUPPORTS_GOAL → Goal

principle_uids:
  - principle.empathy-first           # GUIDED_BY_PRINCIPLE → Principle

choice_uids:
  - choice.ask-before-assuming        # INFORMS_CHOICE → Choice
```

Not every PathStep needs all 6. Use what fits the content.

### LearningPath Inherits from PathSteps

LearningPaths do NOT have their own activity fields. They inherit activities from their PathSteps via graph traversal:

```
(LP)-[:HAS_STEP]->(PathStep)-[:BUILDS_HABIT]->(Habit)
```

An LP that contains 3 PathSteps automatically aggregates all their activities.

### Substance Tracking

When activities link back to PathSteps, substance counters track how much knowledge is being *lived* across six channels:

| Channel | Weight | Max | Note |
|---------|--------|-----|------|
| Habits | 0.10/habit | 0.30 | Lifestyle integration — highest weight |
| Entries/reflection | 0.07/entry | 0.20 | UserEntry via `EXTRACT_ACTIVITIES` pipeline |
| Choices | 0.07/each | 0.15 | Decision-making as applied wisdom |
| Principles | 0.07/each | 0.15 | Value embodiment |
| Events | 0.05/each | 0.25 | Dedicated practice |
| Tasks | 0.05/each | 0.25 | Real-world application |

Total capped at 1.0. The five YAML-declared channels (Habits, Choices, Principles, Events, Tasks) wire via `connections.*` fields on the activity entity. The sixth channel — UserEntry/reflection — is pipeline-driven: the `EXTRACT_ACTIVITIES` pipeline links a completed UserEntry to the PathStep it references and increments the counter automatically; no YAML declaration needed.

For the complete reference, see the **[YAML Authoring Guide](/docs/guides/YAML_AUTHORING_GUIDE.md)** and the **[Knowledge Substance Philosophy](/docs/architecture/knowledge_substance_philosophy.md)**.

---

## Building a Domain Bundle: The Practical Workflow

This is the sequence that works in practice. It was refined by building the Mindfulness 101 and Self-Reflection 101 bundles.

### Step 1: Start with the Kus (5 minutes)

Define 2-4 atomic concepts. Keep them tiny. If you're writing more than one paragraph for a Ku description, you're teaching — and teaching belongs in a PathStep.

### Step 2: Write the PathSteps (the bulk of the work)

This is where you spend most of your time. Each PathStep is a `.md` file with frontmatter metadata and a markdown body. Write in second person. Be direct. Include a practice exercise at the end.

A good PathStep takes 30-60 minutes to write well. Three PathSteps is a good starting size.

### Step 3: Write the Exercises (15 minutes each)

For each PathStep, write one Exercise that closes the learning loop. The Exercise is the mechanism that turns reading into doing and creates the submission→feedback cycle.

- Write `instructions` as a coach persona + task: "You are a mindfulness coach. The student has just completed their first breath-awareness session..."
- Use `form_schema` for beginner content (lower barrier to entry) or omit it for file-upload responses
- Wire the Exercise to its PathStep at ingestion via `exercise_uids` in the PathStep YAML — this creates the `(PathStep)-[:HAS_EXERCISE]->(Exercise)` graph edge automatically

### Step 4: Define the Supporting Activities (10 minutes each)

For each PathStep, ask: what should the learner *do* with this knowledge day-to-day?

- **Habit** — a repeating behavior (daily 2-minute practice)
- **Task** — a one-time deliverable (write three sentences about your patterns)
- **Goal** — a multi-week process goal (build a daily practice over four weeks)
- **Principle** — a guiding value (observation before action)
- **Choice** — a decision prompt (do two minutes right now)
- **Event** — a calendar template (evening check-in)

Not every PathStep needs all six. Wire what fits.

### Step 5: Build the Structure (LP, edges)

Sequence PathSteps into a LearningPath. Write edge files for the curriculum structure and any cross-domain connections.

### Step 6: Review the Graph

Before ingesting, mentally walk the graph:
- Can a learner start from the LP and follow a clear path?
- Does every PathStep compose at least one Ku?
- Does every PathStep have at least one Exercise to close the loop?
- Are activities wired to the right PathSteps?
- Are cross-domain connections declared in edge files?

### Step 7: Ingest

Place files in `/home/mike/0bsidian/0vault/` and ingest. The system handles node creation, relationship wiring, embedding generation, and indexing.

## What Comes Next

This guide covers: Kus, PathSteps, Exercises, prerequisite chains, activity wiring, the three-entity curriculum stack (Ku → PathStep → LP), cross-domain progression, and the practical workflow. For deeper reference:

- **[The Learning Loop](/docs/architecture/LEARNING_LOOP_ARCHITECTURE.md)** — the four-phase cycle (Exercise → UserEntry → EntryReport → RevisedExercise) that closes around each PathStep; how student work is collected, evaluated by AI or teacher, and used to drive targeted revision
- **[Askesis Pedagogical Architecture](/docs/architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md)** — how the AI tutor uses your curriculum graph and the learner's ZPD assessment to surface the right PathStep at the right moment
- **[Unified Ingestion Guide](/docs/patterns/UNIFIED_INGESTION_GUIDE.md)** — bulk ingestion, dry-run mode, incremental updates, vault management, and deletion propagation (entity file deleted → graph node deleted; edge file deleted → relationship deleted)
- **[YAML Authoring Guide](/docs/guides/YAML_AUTHORING_GUIDE.md)** — complete field reference per entity type, the connections system, edge files, enum-governed fields, and bundle structure

Start small. Pick a domain. Define 2-4 Kus. Write 3 PathSteps as `.md` files. Write one Exercise per PathStep. Wire a few activities. Build the LP structure. Write edge files. Ingest and see what the system builds.

The graph grows one node at a time.

---

## Quick Reference

### File Locations

| What | Where | Format |
|------|-------|--------|
| Ku files | `/home/mike/0bsidian/0vault/ku_*.yaml` | YAML |
| PathStep files | `/home/mike/0bsidian/0vault/ps_*.md` | Markdown + YAML frontmatter |
| Exercise files | `/home/mike/0bsidian/0vault/ex_*.yaml` | YAML |
| LearningPath files | `/home/mike/0bsidian/0vault/lp_*.yaml` | YAML |
| Activity files | `/home/mike/0bsidian/0vault/{type}_*.yaml` | YAML |
| Edge files | `/home/mike/0bsidian/0vault/edges/edge_*.yaml` | YAML |
| Templates and schemas | `yaml_templates/_schemas/` | YAML |

### UID Patterns

| Entity | Pattern | Example |
|--------|---------|---------|
| Ku | `ku.{namespace}.{slug}` | `ku.mindfulness.breath` |
| PathStep | `ps.{namespace}.{slug}` | `ps.mindfulness.breath-awareness-basics` |
| Exercise | `ex.{namespace}.{slug}` | `ex.sel.know-yourself-check-in` |
| LearningPath | `lp.{slug}` | `lp.mindfulness-101` |
| Activity | `{type}:{slug}` | `habit.daily-2min-breath` |

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
