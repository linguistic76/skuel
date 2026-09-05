---
title: "PathStep → Ku Wiring Backlog — Ku-less PathSteps, PathStep-less Kus"
updated: 2026-09-05
status: "content backlog"
registered: 2026-08-28
ruled: 2026-08-28
trigger: "Mike's next content session on Ps_dev"
check: "the three Cypher counts in the case file, over all three composition edges (1 / 67 / 67 on 2026-08-28)"
---

# PathStep → Ku Wiring Backlog — Ku-less PathSteps, PathStep-less Kus

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

Askesis grounds a PathStep through its COMPOSITION edges — `USES_KU`, `TRAINS_KU`,
`CONTAINS_KNOWLEDGE` — (`PsBundle.kus`, filled by `ContextRetriever._fetch_kus`,
`core/services/askesis/context_retriever.py:693`); a step with none renders `kus=0` and the
companion has no atomic knowledge to cite for it. Measured 2026-08-28 (AuraDB, all three edges:
`USES_KU` 73, `TRAINS_KU` 5, `CONTAINS_KNOWLEDGE` 0): **1 of 25 PathSteps has no composition
edge — `ps.meditation.basics`** (`0vault/Ps/Ps_dev/`, also in the seed set of
`scripts/seed_search_test_data.py`) — and **67 of 121 Kus are composed by no PathStep**.
⚠️ A `USES_KU`-only census says 5 steps, not 1: the four mindfulness/self-reflection steps
declare `trains_ku_uids:` in their frontmatter and Askesis grounds them correctly — test all three
edges or the backlog is overstated five-fold (Codex, #1179). `./dev knowledge-health` reports
neither count: its orphan count is degree-0 Kus (no edge of any kind), a different question.

**Ruling 2026-08-28 (Mike):** a content backlog, registered with the two counts as the check.
**Named work:** compose `ps.meditation.basics` (`uses_kus:` or `trains_ku_uids:` — a
`Ps_dev` content session); decide which of the 67 unused Kus deserve a PathStep — or an
`ORGANIZES` parent, the other path to knowledge (MOC); the third query below shows how many have
neither. Optional, not built: a `path_steps_without_ku` / `kus_unused_by_path_step` pair in
`KnowledgeHealthService` (ADR-080 H1 authoring gauge) so the check becomes
`./dev knowledge-health` — over the same three-edge alternation, never `USES_KU` alone.
**Trigger:** Mike's next content session on `Ps_dev`.
**Check** (one statement per block; the alternation is the same set `_fetch_kus` composes over):
```cypher
MATCH (p:PathStep) WHERE NOT (p)-[:USES_KU|TRAINS_KU|CONTAINS_KNOWLEDGE]->(:Ku)
RETURN count(p)     // 1 on 2026-08-28
```
```cypher
MATCH (k:Ku) WHERE NOT (:PathStep)-[:USES_KU|TRAINS_KU|CONTAINS_KNOWLEDGE]->(k)
RETURN count(k)     // 67 on 2026-08-28
```
```cypher
MATCH (k:Ku) WHERE NOT (:PathStep)-[:USES_KU|TRAINS_KU|CONTAINS_KNOWLEDGE]->(k)
  AND NOT ()-[:ORGANIZES]->(k)
RETURN count(k)     // 67 on 2026-08-28 — every PathStep-less Ku also lacks a MOC parent
```
**Named cost while open:** one step Askesis cannot ground in Kus; 67 Kus (55%) are composed by
no PathStep — and, by the third query, organised by no MOC either today, so they are reachable
only by search. The PathStep count alone cannot support that claim; keep the third query in
the check.
