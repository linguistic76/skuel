# Askesis Tool-Selection Queries — A Safe Alternative to text2cypher

**Status:** Possible development — not scheduled. Evaluation + design sketch only.
Captures the conclusion of a "should we adopt LangChain `text2cypher`?" review
(May 2026) and the SKUEL-aligned alternative that came out of it.

## Context

The repo used to declare four `langchain-*` packages in `pyproject.toml` (`langchain-core`,
`langchain-community`, `langchain-neo4j`, `langchain-openai`) while **importing none of
them** — `grep -rnE '^\s*(import|from)\s+langchain' --include="*.py"` returned zero hits. They were
declared-but-dead dependencies, and were removed on 2026-07-27 (see § Open questions
below). The trigger for this doc was the question: would
`langchain-neo4j`'s `text2cypher` (`GraphCypherQAChain` — an LLM generates a Cypher
string from a natural-language question, executes it, then synthesizes an answer)
add value, or does Askesis already cover it?

### What Askesis does today

Askesis is a **RAG pipeline with fixed, deterministic retrieval — no LLM ever writes
Cypher**:

1. **Intent classification** (`core/services/askesis/intent_classifier.py`) —
   embedding cosine-similarity against exemplars, into a fixed set
   (`QueryIntent` in `core/models/query_types.py`).
2. **Retrieval** (`core/services/askesis/context_retriever.py`,
   `retrieve_relevant_context`) — branches on intent, but the data is almost all
   *pre-computed*: the UserContext MEGA-QUERY carries ~240 fields per session, plus
   a native Neo4j **vector-index** search over `:ContentChunk` nodes, plus fuzzy
   entity matching against the user's known titles.
3. **Generation** — the LLM runs only here, producing the natural-language *answer*,
   never a query.

The "ask a question, get an answer grounded in your graph" capability therefore
already exists — by a different mechanism than text2cypher.

### The actual gap

Askesis can only answer questions that fit its pre-built retrieval shapes. Note that
`retrieve_relevant_context` (`context_retriever.py:213-240`) has branches for
`PREREQUISITE`, `PRACTICE`, `HIERARCHICAL`, and `EXPLORATORY` — but **no branch for
`AGGREGATION` or `RELATIONSHIP`**. Those intents fall through to bare MEGA-QUERY
counts + vector chunks. Open-ended ad-hoc analytics —
*"how many goals did I complete last quarter that were blocked by a habit I dropped?"*
— get no real graph aggregation today. That is exactly what text2cypher is pitched to
solve, and exactly where the alternative below slots in.

## Why not raw text2cypher

For SKUEL specifically, LLM-generated Cypher is the wrong fit:

- **Multi-tenancy is the killer.** SKUEL is per-user; its ownership model returns 404
  for entities you don't own (`docs/patterns/OWNERSHIP_VERIFICATION.md`). An LLM
  emitting raw Cypher has no enforced `user_uid` scoping — a generated query can
  trivially read across users. That is a data-leak *class* of bug, not a tuning
  problem, and it is the single strongest reason not to do this.
- **SKUEL001 + the hexagonal boundary** (ADR-044): all Cypher is parameterized,
  hand-written, reviewed, tested, and lives below `UniversalNeo4jBackend`. Services
  never construct Cypher. text2cypher inverts that.
- **Determinism / auditability** are explicit design values; LLM-generated queries
  are neither.
- LangChain isn't imported today; adopting text2cypher means pulling in the whole
  `GraphCypherQAChain` abstraction layer the team has otherwise avoided.
- **Product framing:** Askesis is a Socratic tutor scoped to *enrolled
  LearningPaths*, not an open data-exploration console.

## The destination — LLM tool-selection, not LLM Cypher-generation

The pattern that fits SKUEL: **the LLM never sees or emits Cypher. It picks a tool
name and fills typed parameters. Server-side code owns the Cypher and the
`user_uid`.** This gives most of text2cypher's "ask anything" flexibility while
keeping every SKUEL safety guarantee.

```
NL question
   │
   ▼
LLMService.select_tool(question, catalog)   ← LLM returns {tool, args}, NOT Cypher
   │
   ▼
ToolExecutor.run(selection, user_context)
   ├─ tool name ∈ catalog?            (else → fall through to today's behavior)
   ├─ args validated by pydantic       (typed, schema-checked)
   ├─ user_uid := user_context.user_uid (INJECTED here — never from the LLM)
   └─ backend.<vetted_parameterized_cypher>(user_uid=…, **args)
   │
   ▼
context["aggregation"] = result   →   existing ResponseGenerator answers in NL
```

### 1. The catalog entry — a vetted tool, not a free-form query

```python
# core/services/askesis/query_tools.py  (new)
from dataclasses import dataclass
from collections.abc import Awaitable, Callable
from pydantic import BaseModel, Field
from core.models.enums.entity_enums import EntityType, EntityStatus
from core.utils.result import Result

class CountByStatusArgs(BaseModel):
    """LLM fills ONLY these. No raw strings reach Cypher."""
    entity_type: EntityType                       # enum-bound → can't be arbitrary
    status: EntityStatus | None = None
    since: date | None = Field(default=None, description="ISO date lower bound")
    until: date | None = None

@dataclass(frozen=True)
class QueryTool:
    name: str
    description: str                              # what the LLM reads to choose
    args_model: type[BaseModel]                   # pydantic = the param schema
    handler: Callable[..., Awaitable[Result[dict[str, Any]]]]  # bound backend method

    def json_schema(self) -> dict[str, Any]:
        return self.args_model.model_json_schema()  # → OpenAI/Anthropic tool spec
```

### 2. The registry — small, hand-curated, every entry backed by tested Cypher

```python
def build_aggregation_catalog(backend: ActivityAggregationBackend) -> dict[str, QueryTool]:
    return {
        "count_entities_by_status": QueryTool(
            name="count_entities_by_status",
            description=(
                "Count a user's entities of one type, optionally filtered by status "
                "and a date range. Use for 'how many goals did I complete', etc."
            ),
            args_model=CountByStatusArgs,
            handler=backend.count_entities_by_status,
        ),
        # find_blocking_relationships, count_completed_in_period, … add as needed
    }
```

### 3. The backend method — the *only* place Cypher exists (SKUEL001-clean, user-scoped)

```python
# adapters/persistence/neo4j/backends/activity.py
async def count_entities_by_status(
    self,
    *,
    user_uid: str,                 # ← always required, always bound as a param
    entity_type: EntityType,
    status: EntityStatus | None = None,
    since: date | None = None,
    until: date | None = None,
) -> Result[dict[str, Any]]:
    """Parameterized aggregation. Ownership edge is non-optional in the MATCH."""
    cypher = """
        MATCH (u:User {user_uid: $user_uid})-[:OWNS]->(e:Entity)
        WHERE e.entity_type = $entity_type
          AND ($status IS NULL OR e.status = $status)
          AND ($since  IS NULL OR e.completed_at >= $since)
          AND ($until  IS NULL OR e.completed_at <= $until)
        RETURN count(e) AS total
    """
    params = {
        "user_uid": user_uid,
        "entity_type": entity_type.value,
        "status": status.value if status else None,
        "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None,
    }
    rows = await self.execute_query(cypher, params)
    return Result.ok({"total": rows[0]["total"] if rows else 0})
```

The `(u:User {user_uid: $user_uid})-[:OWNS]->` clause is structurally
non-bypassable — even a "correct" tool call can only ever read the requesting
user's subgraph.

### 4. LLM tool-selection added to `LLMService`

`LLMService` (`core/services/llm_service.py`) has no tool-calling today. Add one
method that uses the providers' *native* function-calling and returns a normalized
selection (Anthropic is the provider currently in use; OpenAI shown for clarity):

```python
@dataclass
class ToolSelection:
    tool_name: str | None
    arguments: dict[str, Any]          # raw LLM args, not yet validated

async def select_tool(
    self, question: str, tools: list[QueryTool],
) -> ToolSelection:
    """LLM chooses a tool + args. Returns no tool if none fits (→ fallback)."""
    if not isinstance(self.client, AsyncOpenAI):
        return ToolSelection(tool_name=None, arguments={})
    resp = await self.client.chat.completions.create(
        model=self.config.model_name,
        messages=[{"role": "user", "content": question}],
        tools=[
            {"type": "function", "function": {
                "name": t.name, "description": t.description,
                "parameters": t.json_schema()}}
            for t in tools
        ],
        tool_choice="auto",            # model may decline → None → fallback
    )
    calls = resp.choices[0].message.tool_calls
    if not calls:
        return ToolSelection(tool_name=None, arguments={})
    return ToolSelection(calls[0].function.name, json.loads(calls[0].function.arguments))
# Anthropic path is the parallel `tools=[{name, description, input_schema}]` shape.
```

### 5. The executor — validation + the critical `user_uid` injection

```python
async def run_tool(
    selection: ToolSelection,
    catalog: dict[str, QueryTool],
    user_context: UserContext,
) -> Result[dict[str, Any]]:
    tool = catalog.get(selection.tool_name or "")
    if tool is None:
        return Result.fail(Errors.validation(f"Unknown tool: {selection.tool_name}"))
    try:
        args = tool.args_model.model_validate(selection.arguments)  # schema gate
    except ValidationError as e:
        return Result.fail(Errors.validation(f"Bad tool args: {e}"))

    # user_uid comes from the authenticated context, NEVER from the LLM:
    return await tool.handler(user_uid=user_context.user_uid, **args.model_dump())
```

### 6. Wiring into the existing pipeline — a few lines in the empty branch

```python
# context_retriever.py — fills the AGGREGATION gap (currently absent at ~line 232)
elif intent == QueryIntent.AGGREGATION:
    selection = await self.llm_service.select_tool(query, self._agg_tools)
    result = await run_tool(selection, self._agg_catalog, user_context)
    if result.is_error:
        logger.info("Aggregation tool declined/failed; using baseline context")
    else:
        context["aggregation"] = {"tool": selection.tool_name, **result.unwrap()}
```

Everything downstream is unchanged — the result lands in the same `context` dict the
existing `ResponseGenerator` already consumes.

## Safety properties vs. raw text2cypher

| Risk with raw text2cypher | This approach |
|---|---|
| LLM invents arbitrary queries | LLM picks from a **fixed catalog**; unknown name → rejected |
| Cross-tenant data leak | `user_uid` **injected server-side**; ownership edge baked into every query |
| Cypher injection | Args are **enum/pydantic-typed**, bound as `$params` — never string-concatenated |
| Violates SKUEL001 / unauditable | All Cypher stays in **tested backend methods**, version-controlled |
| Non-deterministic | Same `{tool, args}` → same query; log the selection for a full audit trail |
| Hard failure mode | LLM may return **no tool** → graceful fall-through to today's behavior |

What we give up vs. real text2cypher: we can only answer question *shapes* we've added
a tool for. But each tool covers a whole parameter space (any `entity_type` × status ×
date range), so a handful of tools covers most of the `AGGREGATION`/`RELATIONSHIP` gap —
while keeping every SKUEL safety guarantee.

## Proposed first slice (if pursued)

Implement **one** tool end-to-end, behind the FULL intelligence tier
(`INTELLIGENCE_TIER=full`, so the $0 analytics tier is unaffected):

1. `count_entities_by_status` backend method (parameterized, user-scoped Cypher).
2. `QueryTool` + `CountByStatusArgs` + a one-entry aggregation catalog.
3. `LLMService.select_tool()` for the **Anthropic** provider in use.
4. `run_tool` executor with the `user_uid` injection.
5. The `QueryIntent.AGGREGATION` branch in `context_retriever.py`.
6. A pytest exercising: tool selected + args validated + cross-tenant attempt
   (LLM-supplied `user_uid` ignored) + no-tool fallback path.

Try it against a live question before deciding whether the pattern earns its keep.

## Open questions

- **Catalog growth governance.** Like the CSRF-exempt list, the tool catalog must
  stay small and curated, not become a dumping ground. What is the review bar for
  adding a tool? (cf. `docs/roadmap/programmatic-client-auth-csrf.md` on interim
  lists becoming the norm.)
- **Overlap with intent classification.** Tool-selection is itself a form of intent
  routing. Do `AGGREGATION`/`RELATIONSHIP` intents still earn their place in
  `IntentClassifier`, or does tool-selection subsume them?
- **Cost.** Adds one LLM round-trip (selection) before generation. Acceptable only
  for intents the pre-baked context genuinely can't serve — keep the gate narrow.
- ~~**langchain cleanup.**~~ ✅ **Done 2026-07-27.** The four unused `langchain-*` deps and
  the `langchain.*` MyPy override were removed from `pyproject.toml` per One Path Forward.
  This also closed security-backlog item 1 (`docs/roadmap/security-hardening-deferred.md`
  § 1), which existed only to pin them. Adopting tool-selection does **not** require them —
  the design above uses the provider SDKs' native function-calling directly.

## See

- `core/services/askesis/context_retriever.py` — the `retrieve_relevant_context`
  intent branches (the `AGGREGATION`/`RELATIONSHIP` gap)
- `core/services/llm_service.py` — `LLMService` (no tool-calling today)
- `core/models/query_types.py` — `QueryIntent` enum
- `docs/decisions/ADR-044-neo4j-committed-architectural-choice.md` — pure-Cypher /
  hexagonal-boundary stance (SKUEL001)
- `docs/patterns/OWNERSHIP_VERIFICATION.md` — the multi-tenant invariant this design
  must not break
- `docs/decisions/ADR-043-intelligence-tier-toggle.md` — FULL-tier gating
- `docs/roadmap/askesis-semantic-intelligence.md` — adjacent Askesis retrieval work
