# ZPDService — Deferred Design

> "The plant grows on the lattice — ZPDService reads the graph to know where the user is
> and what they're ready for next."

**Status:** Deferred — curriculum graph must have real data first (3+ KUs, 1+ APPLIES_KNOWLEDGE)
**Owner when built:** `core/services/zpd/zpd_service.py` (new package, peer to `askesis/`)
**See:** `docs/architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md` — full pedagogical vision

---

## What ZPDService Does

`ZPDService` computes a user's Zone of Proximal Development by traversing the Neo4j
curriculum graph. It answers: *what does this user know, and what are they structurally
ready to learn next?*

This is the service that gives Askesis its pedagogical edge. Without it, Askesis can
only react to what the user says. With it, Askesis knows where the user is in the
curriculum before the conversation starts.

---

## Primary Method: `assess_zone()`

```python
@dataclass(frozen=True)
class ZPDAssessment:
    current_zone: list[str]           # ku_uids user has meaningfully engaged
    proximal_zone: list[str]          # ku_uids structurally adjacent, not yet engaged
    engaged_paths: list[str]          # lp_uids partially traversed
    readiness_scores: dict[str, float] # ku_uid → 0.0-1.0 (how ready is the user for each proximal KU)
    blocking_gaps: list[str]          # ku_uids that block further progress (unmet prerequisites)

async def assess_zone(self, user_uid: str) -> Result[ZPDAssessment]:
    """
    Compute ZPD from the user's curriculum graph relationships.

    Current zone: KUs the user has applied, reflected on, or embodied.
    Proximal zone: KUs structurally adjacent to current zone, not yet engaged.
    """
```

---

## Graph Query Approach

ZPDService uses a 2-hop traversal from all engaged KUs:

```cypher
// Step 1: Find current zone (all meaningfully engaged KUs)
MATCH (u:User {uid: $user_uid})
OPTIONAL MATCH (u)-[:OWNS]->(t:Task)-[:APPLIES_KNOWLEDGE]->(ku:Curriculum)
OPTIONAL MATCH (u)-[:OWNS]->(j:Journal)-[:APPLIES_KNOWLEDGE]->(ku2:Curriculum)
OPTIONAL MATCH (u)-[:OWNS]->(h:Habit)-[:REINFORCES_KNOWLEDGE]->(ku3:Curriculum)
WITH u,
     collect(DISTINCT ku.uid) + collect(DISTINCT ku2.uid) + collect(DISTINCT ku3.uid)
     AS engaged_uids

// Step 2: Find proximal zone (adjacent KUs, not already engaged)
UNWIND engaged_uids AS engaged_uid
MATCH (engaged:Curriculum {uid: engaged_uid})
OPTIONAL MATCH (engaged)-[:PREREQUISITE_FOR]->(next:Curriculum)
OPTIONAL MATCH (engaged)-[:COMPLEMENTARY_TO]->(adjacent:Curriculum)
OPTIONAL MATCH (lp:Curriculum)-[:ORGANIZES]->(path_next:Curriculum)
WHERE (lp)-[:ORGANIZES]->(:Curriculum {uid: engaged_uid})  // same LP, next step
WITH engaged_uids,
     collect(DISTINCT next.uid) + collect(DISTINCT adjacent.uid) + collect(DISTINCT path_next.uid)
     AS candidate_uids
// Filter out already-engaged KUs
WITH [uid IN candidate_uids WHERE NOT uid IN engaged_uids] AS proximal_uids,
     engaged_uids
RETURN engaged_uids, proximal_uids
```

### Readiness Score Computation

For each KU in the proximal zone, compute a 0.0–1.0 readiness score:

```python
def _compute_readiness(
    self,
    ku_uid: str,
    current_zone: list[str],
    prerequisite_graph: dict[str, list[str]],
) -> float:
    """
    Score = fraction of the KU's prerequisites that are in the current zone.
    A KU with no prerequisites scores 1.0 (fully ready).
    A KU whose prerequisites are only partially met scores proportionally.
    """
    prerequisites = prerequisite_graph.get(ku_uid, [])
    if not prerequisites:
        return 1.0
    met = sum(1 for p in prerequisites if p in current_zone)
    return met / len(prerequisites)
```

---

## Trigger Condition

ZPDService is ready to build when:
1. The curriculum graph has **3 or more KUs**
2. At least **one user has an APPLIES_KNOWLEDGE relationship** to any KU

Before this, `assess_zone()` would return empty lists — technically correct but useless.
Build ZPDService when the curriculum is real enough to traverse.

---

## Protocol

```python
# core/ports/zpd_protocols.py
from typing import Protocol
from core.services.zpd.zpd_service import ZPDAssessment
from core.utils.result import Result

class ZPDOperations(Protocol):
    async def assess_zone(self, user_uid: str) -> Result[ZPDAssessment]: ...
    async def get_proximal_ku_uids(self, user_uid: str) -> Result[list[str]]: ...
    async def get_readiness_score(self, user_uid: str, ku_uid: str) -> Result[float]: ...
```

---

## Integration Path

1. `core/services/zpd/zpd_service.py` — new package, `ZPDService` class
2. `core/ports/zpd_protocols.py` — `ZPDOperations` protocol
3. `services_bootstrap.py` — `services.zpd_service: ZPDOperations | None` (optional until trigger condition met)
4. `UserContextIntelligence.get_optimal_next_learning_steps()` — calls `ZPDService` when not `None`
5. `AskesisService.answer_user_question()` — reads `ZPDAssessment` to populate `askesis_scaffold_entry` placeholders

---

## Relationship to UserContextIntelligence

`UserContextIntelligence.get_optimal_next_learning_steps()` currently returns items
based on UserContext fields (due dates, momentum, goal alignment). When ZPDService exists,
it becomes the primary signal for curriculum-aligned recommendations:

```python
async def get_optimal_next_learning_steps(self, context: UserContext) -> Result[list[dict]]:
    if self.zpd_service is not None:
        assessment = await self.zpd_service.assess_zone(context.user_uid)
        if not assessment.is_error:
            # Use proximal_zone + readiness_scores for ranking
            return self._rank_by_zpd(assessment.value, context)
    # Fallback: activity-based recommendations (current behavior)
    return self._rank_by_activity(context)
```

---

## Location in Architecture

```
core/services/
├── askesis/          # Conversation + recommendation
├── zpd/              # (NEW) Zone of Proximal Development
│   ├── __init__.py
│   └── zpd_service.py
```

ZPDService is a peer of `askesis/`, not a sub-service. It serves Askesis but is
independently testable and could serve other intelligence services.

---

## What ZPDService Does NOT Do

- It does not store ZPD state in Neo4j (stateless computation over the graph)
- It does not recommend content (Askesis does that, using ZPDAssessment as input)
- It does not track progress (that is `UserContextIntelligence`)
- It does not replace `get_optimal_next_learning_steps()` — it enriches it
