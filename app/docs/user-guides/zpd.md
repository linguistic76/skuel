# Zone of Proximal Development (ZPD)

*Last updated: 2026-03-10*

## What Is ZPD?

The Zone of Proximal Development is the sweet spot between what you already know and what you're ready to learn next. Not too easy (boring), not too hard (frustrating) — just right.

SKUEL computes your ZPD automatically from the curriculum graph. Every time you engage with knowledge — through tasks, journal reflections, submissions, or habits — the system updates its understanding of where you are. It then looks at what's structurally adjacent to what you know and ranks those next steps by how ready you are for them.

This is what makes Askesis a *pedagogical* companion rather than a generic chatbot. Before the conversation starts, Askesis already knows where you are in the curriculum and what you're ready for.

---

## Where ZPD Fits: The System Layers

SKUEL is not a flat collection of features. It's a layered system where each layer depends on the ones below it:

```
┌─────────────────────────────────────────┐
│  5. Semantics (coherence)               │  Embeddings, vector search, meaning
├─────────────────────────────────────────┤
│  4. Knowledge Graph (structural memory) │  Neo4j relationships encode everything
├─────────────────────────────────────────┤
│  3. Saved Interactions (compounding)    │  Conversations, journals, annotations
├─────────────────────────────────────────┤
│  2. ZPD + UserContext (intelligence)    │  "Where are you?" + "What's next?"
├─────────────────────────────────────────┤
│  1. Learning Loop (base)                │  Article → Exercise → Submission → ...
└─────────────────────────────────────────┘
```

**ZPD sits at Layer 2** — the intelligence layer. It reads the knowledge graph (Layer 4) to understand curriculum structure. It reads saved interactions (Layer 3) — your submissions, journals, habit patterns — to understand where you actually are. And it feeds the learning loop (Layer 1) by telling Askesis, daily planning, and your teacher what you're ready for next.

These layers are not equal. The learning loop is the base — everything exists to serve it. ZPD and UserContext are the intelligence that makes the loop *adaptive* rather than mechanical. Without ZPD, the loop still works (teacher assigns, student submits, teacher reviews). With ZPD, the loop knows *which* assignment to suggest, *what* to scaffold, and *where* the student's real gaps are.

---

## How It Works

### Your Current Zone

Your current zone is everything you've meaningfully engaged with. SKUEL detects engagement through three relationship types:

| Relationship | Source | What it means |
|-------------|--------|--------------|
| APPLIES_KNOWLEDGE | Tasks, Journals | You applied this knowledge in your work or reflections |
| REINFORCES_KNOWLEDGE | Habits | You're building this knowledge through repeated practice |

If you wrote a journal entry about Stoic ethics, and that journal is linked to the "Stoic Ethics" knowledge unit, that KU enters your current zone. If you have a daily habit of practicing mindfulness and it's linked to "Meditation Basics," that KU is reinforced in your zone.

### Compound Evidence

A single activity isn't enough to confirm mastery. ZPD requires **compound evidence** — 2 or more signal types — before considering a KU "confirmed" in your current zone:

| Signal Type | What counts |
|------------|------------|
| Submission | You submitted work against an exercise linked to this KU |
| Habit reinforcement | An active habit reinforces this KU |
| Task application | A completed task applies this KU |
| Journal application | A journal reflection references this KU |

A KU with only one signal type is in your current zone but not yet confirmed. ZPD may recommend **reinforcement** — engaging with that knowledge through a different activity type to build compound mastery.

### Your Proximal Zone

Once your current zone is established, ZPD looks outward. It finds knowledge units that are *adjacent* — connected to what you know but not yet engaged:

| Connection type | What it means |
|----------------|--------------|
| PREREQUISITE_FOR | You know X, and X is a prerequisite for Y — so Y is in reach |
| COMPLEMENTARY_TO | You know X, and Y complements X — exploring Y would deepen understanding |
| Learning Path siblings | You're on step 3 of a path — step 4 is structurally next |

The proximal zone excludes anything you've already engaged with. It's always forward-looking.

### Readiness Scores

Not everything in your proximal zone is equally ready. Each candidate KU gets a readiness score from 0.0 to 1.0:

- **1.0** — All prerequisites are met. You're fully ready.
- **0.5** — Half the prerequisites are in your current zone. You could start, but gaps exist.
- **0.0** — None of the prerequisites are met. This is too far ahead right now.

A KU with *no* prerequisites scores 1.0 — it's an entry point anyone can start with.

### Blocking Gaps

Sometimes a prerequisite KU is missing from your current zone, and it blocks multiple proximal KUs. These are *blocking gaps* — the most impactful things to learn next because they unlock the most new territory.

ZPD generates **unblock** actions for blocking gaps at the highest priority. Askesis uses them to guide you toward high-leverage learning: "You've been working on X and Y, but both require Z. Let's look at Z first."

---

## Three Action Types

ZPD doesn't just identify what's next — it generates concrete recommended actions, reflecting the learning loop:

| Action Type | What it means | When generated |
|------------|--------------|----------------|
| **unblock** | Learn a blocking-gap KU that gates further progress | A prerequisite KU is missing and blocks proximal KUs |
| **learn** | Advance into a proximal-zone KU you're ready for | Readiness score is above threshold |
| **reinforce** | Strengthen a current-zone KU with thin evidence | A KU has only 1 signal type (needs compound mastery) |

**Priority formula (learn):** `readiness × 0.5 + life_path_alignment × 0.3 + behavioral_readiness × 0.2`

Unblock actions always have the highest priority (0.9) — they're the most leveraged learning move. Reinforce actions prioritize KUs with the thinnest evidence, weighted by how central they are to your life path.

---

## Behavioral Readiness

ZPD goes beyond curriculum structure. It also considers *how you're behaving* — are your daily patterns supporting learning?

Two signals contribute:

### Choices Intelligence (65% weight)
- **Principle adherence** — Are your decisions aligned with your stated principles?
- **Decision consistency** — Are you following through on what you decide?
- **Quality rate** — What proportion of your decisions are high quality?
- **Conflict penalty** — Active principle conflicts reduce readiness

### Habits Intelligence (35% weight)
- **Reinforcement strength** — How strongly are your habits reinforcing current-zone KUs?
- **At-risk penalty** — KUs that are losing reinforcement (habits declining) reduce readiness

The behavioral readiness score (0.0-1.0) is included in every ZPD assessment. When both intelligence services are unavailable (CORE tier), it defaults to 0.5 (neutral).

---

## Where ZPD Appears

### Askesis Conversations

When you talk to Askesis, it reads your ZPD assessment before responding. This shapes:
- Which KUs it suggests exploring
- Whether it scaffolds (you're at the edge of your zone) or challenges (you're well within it)
- What blocking gaps it highlights

### Daily Planning

`get_ready_to_work_on_today()` surfaces ZPD actions at Priority 5 (Learning). Blocking gaps appear first, then learn actions ranked by readiness, then reinforce actions for thin evidence.

### Learning Recommendations

`UserContextIntelligence.get_optimal_next_learning_steps()` uses ZPD as its primary signal. The proximal zone KUs, ranked by readiness score, become the recommended next steps.

### Intelligence Tier

ZPD requires the FULL intelligence tier (`INTELLIGENCE_TIER=full` in `.env`). On the CORE tier ($0, no API keys), ZPD is skipped and Askesis falls back to activity-based recommendations.

---

## How ZPD Compounds Over Time

ZPD is not a static snapshot. It's a compounding system that gets more precise as you use SKUEL:

1. **First week:** Your current zone is small. Most KUs are in the proximal zone with high readiness (no prerequisites blocked). Recommendations are broad.

2. **First month:** Submissions, journals, and habits build compound evidence. The zone evidence system distinguishes confirmed mastery (2+ signal types) from surface engagement (1 signal). Reinforce actions target the gaps.

3. **Over time:** ZPD snapshots are persisted on significant events (submission approved, report submitted, knowledge mastered). The system builds a longitudinal record of your zone evolution. Each snapshot reflects the full curriculum graph at that moment — your growth is captured structurally, not as a self-reported number.

4. **With saved interactions:** Your journal insights, Askesis conversation patterns, and activity report annotations all feed back into the signals ZPD reads. A journal entry that references a KU creates an APPLIES_KNOWLEDGE relationship. An Askesis conversation anchored to a KU deepens engagement. Each interaction compounds the signal quality.

This compounding is why the learning loop is the *base* — each loop iteration (submit → feedback → reflect → resubmit) creates new graph relationships that ZPD reads on the next assessment. The loop feeds the intelligence; the intelligence guides the next loop.

---

## The Minimum Curriculum Threshold

ZPD requires at least 3 knowledge units in the curriculum graph to produce meaningful results. Below that threshold, `assess_zone()` returns an empty assessment (not an error). This is by design — a curriculum graph with 1-2 KUs has no structural adjacency to compute.

---

## Example

Imagine a student named Alex:

1. Alex has completed tasks linked to "Variables" and "Data Types" KUs
2. Alex has a daily coding habit linked to "Basic Syntax"
3. Alex submitted an exercise about Variables and scored well
4. **Current zone:** Variables (confirmed — task + submission), Data Types (1 signal), Basic Syntax (1 signal)

The curriculum graph shows:
- Variables is PREREQUISITE_FOR Functions
- Data Types is PREREQUISITE_FOR Collections
- Basic Syntax is COMPLEMENTARY_TO Control Flow

**Recommended actions:**

| KU | Action | Priority | Why |
|----|--------|----------|-----|
| Functions | learn | 0.82 | All prerequisites met, aligns with life path |
| Collections | learn | 0.80 | All prerequisites met |
| Control Flow | learn | 0.78 | No prerequisites, complementary to known KU |
| Data Types | reinforce | 0.65 | Only 1/4 evidence types — needs a journal or habit |
| Basic Syntax | reinforce | 0.65 | Only 1/4 evidence types — needs a submission or task |

Alex's habits are strong (daily coding) and choices are consistent. Behavioral readiness: 0.82.

Askesis might say: "You've been solid with variables and data types. Functions are a natural next step — want to explore how functions use what you already know about variables?"

And later: "I notice you've only engaged with Data Types through tasks. Writing a journal reflection about when you'd choose different data types would deepen that understanding."

---

## Technical Reference

| Component | Location |
|-----------|----------|
| Service (business logic) | `core/services/zpd/zpd_service.py` |
| Backend (Cypher queries) | `adapters/persistence/neo4j/zpd_backend.py` |
| Snapshot backend (persistence) | `adapters/persistence/neo4j/zpd_snapshot_backend.py` |
| Event handler (snapshot triggers) | `core/services/zpd/zpd_event_handler.py` |
| Protocols | `core/ports/zpd_protocols.py` |
| Assessment model | `core/models/zpd/zpd_assessment.py` |
| Design rationale | `docs/roadmap/zpd-service-deferred.md` |
| Askesis architecture | `docs/architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md` |
| Learning loop | `docs/user-guides/learning-loop.md` |
