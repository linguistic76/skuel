---
title: Pedagogical Questions
updated: 2026-03-12
category: intelligence
---

# Pedagogical Questions

The 7 core questions SKUEL's intelligence layer must answer for every learner. Each question maps to one or more production services.

---

## 1. "What can I learn next?"

Prerequisite-gated, time-aware curriculum navigation. Shows only knowledge the learner is ready for — prerequisites met, within their time budget.

**Why it matters:** Without prerequisite filtering, learners attempt material they aren't ready for and get frustrated. Without time filtering, they start things they can't finish.

**Answered by:**
- `ZPDService.assess_zone()` — `core/services/zpd/zpd_service.py`
- `LearningIntelligence.get_optimal_next_learning_steps()` — `core/services/user/intelligence/learning_intelligence.py`

---

## 2. "How much of my knowledge am I actually living?"

Life path substance scoring — the gap between what a learner *knows* and what they *do*. Aggregates behavioral evidence (habits, journals, choices, events, tasks) into a 0.0–1.0 alignment score.

**Why it matters:** SKUEL's core thesis is that knowledge without application is incomplete. This question measures embodiment, not recall.

**Answered by:**
- `LifePathIntelligence.calculate_life_path_alignment()` — `core/services/user/intelligence/life_path_intelligence.py`

---

## 3. "What must I learn before I can reach this?"

Prerequisite chain visibility — given a target knowledge unit, show the full dependency tree and the learner's mastery state at each node.

**Why it matters:** Learners need to see the path, not just the next step. Showing the chain turns an opaque "not ready" into an actionable sequence.

**Answered by:**
- `build_prerequisite_chain()` — `adapters/persistence/neo4j/query/cypher/semantic_queries.py`

---

## 4. "Where is this knowledge showing up in my life?"

Cross-domain application mapping — for a given piece of curriculum, find all the tasks, habits, goals, events, and principles where the learner is applying it.

**Why it matters:** Connects the abstract (curriculum) to the concrete (daily life). Reinforces that learning is not a separate activity but woven into everything.

**Answered by:**
- `LearningIntelligence.get_knowledge_application_opportunities()` — `core/services/user/intelligence/learning_intelligence.py`

---

## 5. "What's my overall learning state?"

Progress snapshot — a complete picture of the learner's position across all enrolled paths, mastery counts, and life path status.

**Why it matters:** Orientation. Before deciding what to do next, a learner needs to know where they stand.

**Answered by:**
- `UserContextBuilder.build_rich()` — `core/services/user/user_context_builder.py`

---

## 6. "What should I study next to make the most progress?"

Adaptive recommendations weighted by difficulty match, enablement value (how many downstream units this unlocks), and life path alignment.

**Why it matters:** Not all available knowledge is equally valuable. This question prioritizes high-leverage learning — units that unlock the most future progress.

**Answered by:**
- ZPD priority formula in `ZPDService.assess_zone()` — `core/services/zpd/zpd_service.py`
- `LearningIntelligence.get_optimal_next_learning_steps()` — `core/services/user/intelligence/learning_intelligence.py`

---

## 7. "How deeply have I applied this specific knowledge recently?"

Substance recalculation from domain activity — recompute a knowledge unit's substance score from the last 30 days of behavioral evidence across all activity domains.

**Why it matters:** Substance decays. A learner who practiced something intensely three months ago but hasn't touched it since needs to know their embodiment has faded.

**Answered by:**
- `LessonIntelligenceService.calculate_user_substance()` — `core/services/lesson_intelligence_service.py`
