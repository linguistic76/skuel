# Askesis Tool-Selection Queries — A Safe Alternative to text2cypher

**Status:** **Direction RULED 2026-08-31 (Mike) — position (b): Askesis DOES answer questions
about the user's own records, and this is how.** Not yet scheduled as a build, and **blocked on
a trigger**: intent classification cannot return `AGGREGATION` today because its 0.65 gate is
unreachable, so
[askesis-intent-classification-activation.md](askesis-intent-classification-activation.md) is a
prerequisite, not a neighbour. Originally captured the conclusion of a "should we adopt LangChain
`text2cypher`?" review (May 2026) and the SKUEL-aligned alternative that came out of it; the
ruling promotes that alternative from "possible" to "the intended shape".

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
`retrieve_relevant_context` (`context_retriever.py`, ~line 243 as of 2026-08-21) has
branches for `PREREQUISITE`, `PRACTICE`, `HIERARCHICAL`, and `EXPLORATORY` — but **no
branch for `AGGREGATION`** (`RELATIONSHIP` has since gained chunk-type routing via
`_intent_to_chunk_types`, so its half of the gap narrowed; the `AGGREGATION` gap — this
doc's thesis — is intact). Those intents fall through to bare MEGA-QUERY
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
from core.utils.result import Result

class CountGoalsAchievedArgs(BaseModel):
    """LLM fills ONLY these. No raw strings reach Cypher.

    Deliberately ONE domain, not an `entity_type` dial: the completion field
    differs per domain (§ 3), so a generic tool can only be wrong for some of
    them — and narrowing the schema is also what stops the LLM selecting a
    shape that has no field to filter on.
    """
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
def build_aggregation_catalog(goals: GoalsBackend) -> dict[str, QueryTool]:
    return {
        "count_goals_achieved": QueryTool(
            name="count_goals_achieved",
            description=(
                "Count the goals this user has achieved, optionally within a date "
                "range. Use for 'how many goals did I complete last quarter'."
            ),
            args_model=CountGoalsAchievedArgs,
            handler=goals.count_goals_achieved,
        ),
        # Siblings are added PER DOMAIN, each bound to its own backend and its own
        # completion field (§ 3): count_tasks_completed (TasksBackend,
        # completion_date), count_habits_completed (HabitsBackend, completed_at), …
        # There is no "count_entities_by_status" — that shape cannot be written
        # correctly across domains.
    }
```

### 3. The backend method — the *only* place Cypher exists (SKUEL001-clean, user-scoped)

```python
# adapters/persistence/neo4j/backends/activity_backends.py — on GoalsBackend
async def count_goals_achieved(
    self,
    *,
    user_uid: str,                 # ← always required, always bound as a param
    since: date | None = None,
    until: date | None = None,
) -> Result[dict[str, Any]]:
    """Parameterized aggregation. Ownership edge is non-optional in the MATCH.

    One domain, one field: Goal's completion is ``achieved_date`` (a ``date``).
    Siblings on TasksBackend/HabitsBackend bind THEIR field and type — see the
    table below for why this cannot be one shared method.
    """
    # ⚠ `uid`, NOT `user_uid` — `User` declares its identifier as `uid`
    # (core/models/user/user.py) and every production query matches
    # `(u:User {uid: $user_uid})`. An unknown property name matches ZERO rows
    # rather than erroring, so the earlier `{user_uid:}` spelling in this sketch
    # would have reported 0 for every valid account — the SKUEL030 defect class,
    # and exactly the kind of silence a "safe alternative to text2cypher" cannot
    # afford. Corrected 2026-08-31 (Codex, #1202).
    cypher = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(g:Goal)
        WHERE g.achieved_date IS NOT NULL
          AND ($since IS NULL OR g.achieved_date >= $since)
          AND ($until IS NULL OR g.achieved_date <= $until)
        RETURN count(g) AS total
    """
    params = {
        "user_uid": user_uid,
        "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None,
    }
    # `execute_query` returns Result[list[dict]], never a bare list — reading
    # rows[0] off it fails on EVERY call and swallows database errors. Result.fail
    # (not `return result`) because the payload types differ here: list[dict] in,
    # dict out (SKUEL028).
    result = await self.execute_query(cypher, params)
    if result.is_error:
        return Result.fail(result)
    rows = result.value or []
    return Result.ok({"total": rows[0]["total"] if rows else 0})
```

⚠ **There is no single completion field, so a date-bounded count CANNOT be one generic
`EntityType` tool** (Codex, #1202 — verified against the models):

| domain | completion field | model type | **persisted in Neo4j** |
|---|---|---|---|
| Task | `completion_date` | `date` | **ISO string** `"2026-06-15"` |
| Goal | `achieved_date` | `date` | **ISO string** `"2026-06-15"` |
| Choice / Event / Habit | `completed_at` | `datetime` | **ISO string** `"2026-06-15T08:09:10.111213"` |
| Principle | **none** | — | — (deliberate: ADR-087 keeps Principle off the completion guard) |

The sketch's original `e.completed_at` is real — on Choice, Event and Habit — and **absent on
exactly the two types this doc's own headline example names** ("how many *goals* did I complete
last quarter"). Same silent-zero class as the `uid` defect above: an unknown property matches no
rows instead of erroring.

Three consequences for whoever builds this:

1. **Dispatch per domain**, from a service, to domain-specific backend methods — which is also
   what SKUEL's architecture rule already requires ("domain-specific Cypher belongs on the domain
   backend; cross-domain aggregation stays in services"). Narrow each tool's `args_model` to the
   domains it can actually serve, so the LLM cannot select a shape that has no field.
2. **Everything temporal is persisted as an ISO STRING, not a temporal type.**
   `neo4j_mapper.py` serializes both `date` and `datetime` with `.isoformat()`, and
   `tests/integration/test_backfill_activity_completion_stamps.py` asserts `STRING` for
   `achieved_date` and `completed_at` alike. So bind ISO strings — as the sketch above does —
   and **never** a Neo4j temporal value: comparing `date()` against a stored string matches
   nothing and fails silently.
   ⚠ **The surviving difference is the string's SHAPE, and it bites the upper bound.**
   Lexicographic order makes ISO-8601 compare correctly *until* the shapes differ:
   `"2026-06-15T08:09:10" <= "2026-06-15"` is **false**, so an `until` bound of `2026-06-15`
   silently excludes everything completed *on* that day for the three `completed_at` domains,
   while behaving as expected for Task/Goal. Each domain's tool must normalise its own bound
   (a date-shaped `until` needs widening to the day's end for `datetime`-backed fields) — one
   more reason the tool is per-domain and not generic.
3. **A "completed" count over Principle is not answerable** and must not be offered as a tool
   option — not an omission to fix later.

The `(u:User {uid: $user_uid})-[:OWNS]->` clause is structurally
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

### 6. Wiring into the existing pipeline

⚠ **The obvious placement reaches only ONE of the three answer paths.** Dropping the tool call
into `retrieve_relevant_context` is where the gap is *described*, but (Codex, #1202 — confirmed
in code):

| path | does it run the tool? | does the answer see the count? |
|---|---|---|
| non-guided chat (`generate_context_aware_answer`) | yes | yes — `additional_context=relevant_context` |
| **guided chat** (`_generate_guided_answer`) | yes | **no** — that call takes only the question, the guided system prompt and the PS bundle |
| **`process_query_with_context`** | **no** — it calls `get_learning_context()` (`query_processor.py:480`), not `retrieve_relevant_context()` | n/a |

So a guided learner could be handed an answer *unrelated to a count that was computed for them*,
and the public context-query API would keep the very gap this doc exists to close. **Whoever
builds this must name the delivery point for each path**, not just the computation point — and
for the guided path that means deciding whether an aggregation result may enter a deliberately
narrow Socratic prompt at all (ADR-077), which is a pedagogical question, not a plumbing one.

```python
# context_retriever.py — computes the aggregation (necessary, NOT sufficient — see above)
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

1. `count_goals_achieved` on `GoalsBackend` (parameterized, user-scoped Cypher —
   `(u:User {uid: $user_uid})`, `achieved_date`; see the ⚠ in § 3 for why it is
   per-domain and not a generic `EntityType` count).
2. `QueryTool` + `CountGoalsAchievedArgs` + a one-entry aggregation catalog.
3. `LLMService.select_tool()` for the **Anthropic** provider in use.
4. `run_tool` executor with the `user_uid` injection.
5. The `QueryIntent.AGGREGATION` branch in `context_retriever.py`. ⚠ **It cannot fire until
   the classifier arc lands.** `AGGREGATION` keeps its exemplars (ruled 2026-08-31 — see that
   doc's ruling 2), but the classifier returns only `SPECIFIC` today because the 0.65 gate is a
   MEAN over 8 exemplars and is unreachable, so a branch added now is dead on arrival. Build it
   AFTER
   [askesis-intent-classification-activation.md](askesis-intent-classification-activation.md)
   PR-2, and not before its PR-1 has disambiguated `AGGREGATION` from `EXPLORATORY`: until then
   a topic-orientation question ("introduce me to stoicism") can route here and be answered with
   a COUNT. That mis-route is harmless while this branch is absent and user-visible the moment
   it exists.
6. **Declare the catalog's COVERAGE, and decline outside it.** The first slice answers
   *"how many goals did I complete last quarter"* and nothing else — not the bare total, and
   not the relationship-bearing question this doc opens with (*"…blocked by a habit I
   dropped"*), which needs **service-level cross-domain aggregation**, not a single-domain
   backend method. `tool_choice="auto"` has no completeness check, so the model will either
   decline a question the ruling says is supported, or pick the nearest tool and report an
   achieved-goal total that quietly ignores the predicate. **The second failure is the
   dangerous one — a confident wrong number.** Either add the matching tools before those
   shapes can classify, or make an unmatched shape an explicit decline with a stated reason.
   ⚠ Cross-check against
   [askesis-intent-classification-activation.md](askesis-intent-classification-activation.md)
   PR-1, whose labelled set is required to carry BOTH shapes: labelling a query `AGGREGATION`
   does not conjure a tool that can answer it.
7. **Delivery, per answer path — the slice is not end-to-end without it** (§ 6 table).
   Computing the count in `ContextRetriever` reaches only non-guided chat. Decide and wire:
   (a) `process_query_with_context`, which calls `get_learning_context()` and so never runs
   the tool at all; (b) the guided path, where `_generate_guided_answer` receives no
   `relevant_context` — and whether an aggregation may enter a deliberately narrow Socratic
   prompt is a **pedagogical** call (ADR-077), so "wire it" is not the automatic answer. A
   documented decision to serve only the non-guided path is acceptable; shipping that by
   omission is not.
8. A pytest exercising: tool selected + args validated + cross-tenant attempt
   (LLM-supplied `user_uid` ignored) + no-tool fallback path + **the count actually reaching
   the answer on every path step 7 claims to serve** — the delivery half is where this
   silently fails, not the selection half — + **an out-of-coverage question is declined, not
   approximated** (step 6), + **a same-day `until` bound includes that day** on a
   `completed_at` domain (§ 3, consequence 2).

Try it against a live question before deciding whether the pattern earns its keep.

## Open questions

- **Catalog growth governance.** Like the CSRF-exempt list, the tool catalog must
  stay small and curated, not become a dumping ground. What is the review bar for
  adding a tool? (cf. `docs/roadmap/programmatic-client-auth-csrf.md` on interim
  lists becoming the norm.)
- ~~**Overlap with intent classification.**~~ ✅ **Answered for `AGGREGATION` 2026-08-31:** it
  earns its place — the ruling keeps it as the routing trigger for this path rather than having
  tool-selection subsume it. `RELATIONSHIP` is untouched and the question stands for it alone.
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
