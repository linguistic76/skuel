# Zone of Proximal Development (ZPD)

*Last updated: 2026-03-09*

## What Is ZPD?

The Zone of Proximal Development is the sweet spot between what you already know and what you're ready to learn next. Not too easy (boring), not too hard (frustrating) — just right.

SKUEL computes your ZPD automatically from the curriculum graph. Every time you engage with knowledge — through tasks, journal reflections, or habits — the system updates its understanding of where you are. It then looks at what's structurally adjacent to what you know and ranks those next steps by how ready you are for them.

This is what makes Askesis a *pedagogical* companion rather than a generic chatbot. Before the conversation starts, Askesis already knows where you are in the curriculum and what you're ready for.

---

## How It Works

### Your Current Zone

Your current zone is everything you've meaningfully engaged with. SKUEL detects engagement through three relationship types:

| Relationship | Source | What it means |
|-------------|--------|--------------|
| APPLIES_KNOWLEDGE | Tasks, Journals | You applied this knowledge in your work or reflections |
| REINFORCES_KNOWLEDGE | Habits | You're building this knowledge through repeated practice |

If you wrote a journal entry about Stoic ethics, and that journal is linked to the "Stoic Ethics" knowledge unit, that KU enters your current zone. If you have a daily habit of practicing mindfulness and it's linked to "Meditation Basics," that KU is reinforced in your zone.

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

Askesis uses blocking gaps to guide you toward high-leverage learning: "You've been working on X and Y, but both require Z. Let's look at Z first."

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

### Learning Recommendations

`UserContextIntelligence.get_optimal_next_learning_steps()` uses ZPD as its primary signal. The proximal zone KUs, ranked by readiness score, become the recommended next steps in your daily plan.

### Intelligence Tier

ZPD requires the FULL intelligence tier (`INTELLIGENCE_TIER=full` in `.env`). On the CORE tier ($0, no API keys), ZPD is skipped and Askesis falls back to activity-based recommendations.

---

## The Minimum Curriculum Threshold

ZPD requires at least 3 knowledge units in the curriculum graph to produce meaningful results. Below that threshold, `assess_zone()` returns an empty assessment (not an error). This is by design — a curriculum graph with 1-2 KUs has no structural adjacency to compute.

---

## Example

Imagine a student named Alex:

1. Alex has completed tasks linked to "Variables" and "Data Types" KUs
2. Alex has a daily coding habit linked to "Basic Syntax"
3. **Current zone:** Variables, Data Types, Basic Syntax

The curriculum graph shows:
- Variables is PREREQUISITE_FOR Functions
- Data Types is PREREQUISITE_FOR Collections
- Basic Syntax is COMPLEMENTARY_TO Control Flow

**Proximal zone:**
| KU | Readiness | Why |
|----|-----------|-----|
| Functions | 1.0 | Its only prerequisite (Variables) is met |
| Collections | 1.0 | Its only prerequisite (Data Types) is met |
| Control Flow | 1.0 | No prerequisites, complementary to known KU |

Alex's habits are strong (daily coding) and choices are consistent. Behavioral readiness: 0.82.

Askesis might say: "You've been solid with variables and data types. Functions are a natural next step — want to explore how functions use what you already know about variables?"

---

## Technical Reference

| Component | Location |
|-----------|----------|
| Service (business logic) | `core/services/zpd/zpd_service.py` |
| Backend (Cypher queries) | `adapters/persistence/neo4j/zpd_backend.py` |
| Protocols | `core/ports/zpd_protocols.py` |
| Assessment model | `core/models/zpd/zpd_assessment.py` |
| Design rationale | `docs/roadmap/zpd-service-deferred.md` |
| Askesis architecture | `docs/architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md` |
