---
updated: 2026-11-08
---

# Activity Domain Knowledge Inference

**Status:** Tasks and UserEntries ground; Goals, Habits, Events, Choices, Principles pending —
**blocked on product demand, not on engineering readiness.** Re-scoped 2026-11-08 (#1650's residuals,
row 2c): the capability this doc stages is unchanged — an Activity Domain infers the knowledge an
entity applies — and its means is now Ku grounding, not keyword inference.

**Pattern owner:** `KnowledgeGroundingService` (`core/services/knowledge_grounding_service.py`).
**Superseded contract:** [ADR-065 — Functional Inference Contract](../decisions/ADR-065-functional-inference-contract.md).

## Context

Tasks inferred knowledge by scoring the title and description against a keyword table
(`EntityInferenceService`) and storing three properties on the task (`knowledge_confidence_scores`,
`knowledge_inference_metadata`, `learning_opportunities_count`). The table's 26 keys named no Ku in
the content vault, so nothing it inferred was knowledge a learner could reach. It retired, with
`TaskInferenceResult` and the plan to give each domain a `{Domain}InferenceResult`.

Inference is now grounding: an entity's stored embedding is matched against the Ku vector index at
a threshold, an LLM judge filters the candidates in FULL, and each match becomes
`(entity)-[:APPLIES_KNOWLEDGE {inferred: true, confidence, grounded_at}]->(ku)` to a published Ku.
The edge earns substance like the owner's own link, is one-click removable, and a removal is
recorded and never re-inferred. A changed `embedding_text_hash` re-grounds; unchanged text never
re-runs. Nothing lands on the entity but its grounded stamp, so there is no result type to apply.

## Domain status

| Domain | Grounds | Source classes | Trigger |
|--------|---------|----------------|---------|
| UserEntry | ✅ | `EntryGroundingService` + `EntryGroundingBackend` (grounded pipelines, never `private`) | post-sync pass of a personal-vault sync |
| Tasks | ✅ | `TaskGroundingService` + `TaskGroundingBackend` (never a cancelled task) | `EmbeddingStored` from the embedding worker (FULL) |
| Goals | ❌ | — | — |
| Habits | ❌ | — | — |
| Events | ❌ | — | — |
| Choices | ❌ | — | — |
| Principles | ❌ | — | — |

## The pattern (per domain)

For an Activity Domain `X` to infer the knowledge it applies:

1. **The edge.** Decide which edge an inferred link is: the one the domain's owner link already
   writes to a Ku (Tasks and Events `APPLIES_KNOWLEDGE`, Habits `REINFORCES_KNOWLEDGE`, ...). The
   shared backend writes `APPLIES_KNOWLEDGE`; a domain whose owner link is another type parameterizes
   that first.
2. **A backend source** — a `KnowledgeGroundingBackend` subclass naming the label, the gate (which of
   its entities may ground) and the text the judge reads.
3. **A service source** — a `KnowledgeGroundingService` subclass naming its judge prompt (a
   `core/prompts/templates/{x}_ku_grounding_judge.md`) and its substance event (the one the owner's
   link publishes, e.g. `KnowledgeBuiltIntoHabit`).
4. **The trigger.** `EmbeddingStored` for the domain's type, as Tasks subscribe, once the domain is
   embedded (`EMBEDDING_EVENT_TYPES`).
5. **The removal door and the owner's link writer.** A removal door per domain; the owner's link
   writes go through the guarded link write, which promotes an inferred edge the owner names and
   leaves inferred edges alone on a replace.

**Trigger to unblock:** a product decision that a specific domain needs inferred knowledge. Until
then, this doc is a captured plan, not active work.

## References

- `core/services/knowledge_grounding_service.py` — the one pass.
- `adapters/persistence/neo4j/knowledge_grounding_backend.py` — the shared statements.
- `core/services/tasks/task_grounding_service.py`, `adapters/persistence/neo4j/task_grounding_backend.py` — the newest source, the one to copy.
- `adapters/persistence/neo4j/endpoint_queries.py::build_guarded_link_query` — the owner's link write and inferred edges.
