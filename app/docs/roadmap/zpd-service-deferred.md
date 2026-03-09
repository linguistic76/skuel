# ZPDService — Design & Architecture

> "The plant grows on the lattice — ZPDService reads the graph to know where the user is
> and what they're ready for next."

**Status:** Implemented (March 2026)
**Service:** `core/services/zpd/zpd_service.py`
**Backend:** `adapters/persistence/neo4j/zpd_backend.py`
**Protocol:** `core/ports/zpd_protocols.py` — `ZPDOperations` (service), `ZPDBackendOperations` (backend)
**See:** `docs/architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md` — full pedagogical vision

---

## What ZPDService Does

`ZPDService` computes a user's Zone of Proximal Development by delegating graph
traversal to `ZPDBackend`. It answers: *what does this user know, and what are they
structurally ready to learn next?*

This is the service that gives Askesis its pedagogical edge. Without it, Askesis can
only react to what the user says. With it, Askesis knows where the user is in the
curriculum before the conversation starts.

---

## Architecture

```
ZPDBackend (adapters/persistence/neo4j/)
    ↓  raw graph data (current_zone, proximal_zone, prereq_data, ...)
ZPDService (core/services/zpd/)
    ↓  readiness scoring + behavioral enrichment → ZPDAssessment
UserContextIntelligence / AskesisService
```

- **ZPDBackend** owns all Cypher queries — zone traversal and KU count check
- **ZPDService** owns business logic — readiness scoring, behavioral enrichment
- **ZPDBackendOperations** protocol types the backend injection

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
    behavioral_readiness: float       # 0.0-1.0 aggregate from choices + habits signals

async def assess_zone(self, user_uid: str) -> Result[ZPDAssessment]:
    """
    Compute ZPD from the user's curriculum graph relationships.

    Current zone: KUs the user has applied, reflected on, or embodied.
    Proximal zone: KUs structurally adjacent to current zone, not yet engaged.
    """
```

---

## Graph Query Approach

ZPDBackend uses a single 2-hop Cypher traversal per `get_zone_data()` call:

- **Step 1:** Find current zone — KUs via APPLIES_KNOWLEDGE (Tasks, Journals) + REINFORCES_KNOWLEDGE (Habits)
- **Step 2:** Find proximal zone — adjacent via PREREQUISITE_FOR, COMPLEMENTARY_TO, LP ORGANIZES (same path, next step)
- **Step 3:** Prerequisite graph for readiness scoring — count total vs met prerequisites per proximal KU
- **Step 4:** Engaged Learning Paths — which LPs the user is actively on
- **Step 5:** Blocking gaps — prerequisite KUs not yet met that block proximal KUs

### Readiness Score Computation (ZPDService)

```python
def _compute_readiness_scores(self, prereq_data: list[dict[str, Any]]) -> dict[str, float]:
    """
    Score = fraction of the KU's prerequisites that are in the current zone.
    A KU with no prerequisites scores 1.0 (fully ready).
    A KU whose prerequisites are only partially met scores proportionally.
    """
```

### Behavioral Readiness (ZPDService)

Enriches the assessment with signals from ChoicesIntelligenceService and HabitsIntelligenceService:
- Principle adherence, decision consistency, quality rate (from choices)
- Habit reinforcement strength, at-risk KU penalty (from habits)
- Returns 0.5 (neutral) when intelligence services are unavailable

---

## Guard Condition

ZPDService returns an empty ZPDAssessment (not an error) when the curriculum graph
has fewer than 3 KUs. This is checked via `ZPDBackend.get_ku_count()`.

---

## Protocols

```python
# core/ports/zpd_protocols.py

class ZPDBackendOperations(Protocol):
    async def get_ku_count(self) -> int: ...
    async def get_zone_data(self, user_uid: str) -> Result[tuple[...]]: ...

class ZPDOperations(Protocol):
    async def assess_zone(self, user_uid: str) -> Result[ZPDAssessment]: ...
    async def get_proximal_ku_uids(self, user_uid: str) -> Result[list[str]]: ...
    async def get_readiness_score(self, user_uid: str, ku_uid: str) -> Result[float]: ...
```

---

## Integration

1. `adapters/persistence/neo4j/zpd_backend.py` — `ZPDBackend` (Cypher queries)
2. `core/services/zpd/zpd_service.py` — `ZPDService` (business logic)
3. `core/ports/zpd_protocols.py` — `ZPDBackendOperations` + `ZPDOperations` protocols
4. `services_bootstrap.py` — `services.zpd_service: ZPDOperations | None` (FULL tier only)
5. `UserContextIntelligence.get_optimal_next_learning_steps()` — calls `ZPDService` when not `None`
6. `AskesisService.analyze_user_state()` — reads `ZPDAssessment` in state snapshot

---

## Relationship to UserContextIntelligence

`UserContextIntelligence.get_optimal_next_learning_steps()` uses ZPDService as its
primary signal for curriculum-aligned recommendations:

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
adapters/persistence/neo4j/
├── zpd_backend.py            # Cypher queries + result parsing

core/services/
├── askesis/                   # Conversation + recommendation
├── zpd/                       # Zone of Proximal Development
│   ├── __init__.py
│   └── zpd_service.py        # Business logic (readiness scoring, behavioral enrichment)

core/ports/
├── zpd_protocols.py           # ZPDBackendOperations + ZPDOperations
```

ZPDService is a peer of `askesis/`, not a sub-service. It serves Askesis but is
independently testable and could serve other intelligence services.

---

## What ZPDService Does NOT Do

- It does not store ZPD state in Neo4j (stateless computation over the graph)
- It does not recommend content (Askesis does that, using ZPDAssessment as input)
- It does not track progress (that is `UserContextIntelligence`)
- It does not replace `get_optimal_next_learning_steps()` — it enriches it
- It does not contain Cypher queries (those live in ZPDBackend)
