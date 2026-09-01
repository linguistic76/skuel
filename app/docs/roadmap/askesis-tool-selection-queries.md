---
updated: 2026-09-01
---

# Askesis Tool-Selection Queries — A Safe Alternative to text2cypher

**Status:** **FIRST SLICE SHIPPED 2026-08-31** (direction ruled 2026-08-31, Mike —
position (b): Askesis DOES answer questions about the user's own records, and this is how).
The slice landed as one PR, exactly per the ruled sequencing: the aggregation tool
(`count_goals_achieved` — `GoalsBackend`, :OWNS-scoped, `achieved_date`, FULL tier only), the
one-entry catalog + `run_tool` executor with server-side `user_uid` injection
(`core/services/askesis/query_tools.py`), `LLMService.select_tool()` (Anthropic-native), the
`QueryIntent.AGGREGATION` branch in `retrieve_relevant_context`, **and the deletion of the
activation arc's `UNREACHABLE_INTENTS` carve-out — all in the same commit**, so `AGGREGATION`
never classified with nothing behind it. What shipped resolves the two rulings recorded below
(§ Proposed first slice, steps 6-7): **decline outside the catalog** — the one-entry catalog
answers the time-windowed achieved-goals shape and nothing else, so day one most real count
questions DECLINE with a learner-visible reason (by design: a decline beats a confident wrong
number) — and **deterministic delivery on the chat pipeline only**, with
`process_query_with_context` declining rather than generating. OPEN PROBLEM 2 is closed for
this slice by construction (the outcome's own text IS the answer; generation is
short-circuited). OPEN PROBLEM 1 remains open and gates catalog growth.

⚠ **The constraint is REACHABILITY, not PR count — amended 2026-08-31 (Mike).** This doc
previously said the activation arc's PR-2 and this first slice are "ONE coordinated change, not a
sequence". That over-stated the requirement. The real invariant is that **`AGGREGATION` must
never CLASSIFY with nothing behind it** — and that is satisfied either by shipping them together
or by PR-2 holding `AGGREGATION` explicitly unreachable and this slice removing that exclusion in
the same change that adds the tool. **The ruled sequencing is the latter**, because this slice
carries an LLM-chosen, user-scoped query executor whose cross-tenant test deserves its own review,
plus two unresolved decisions (step 6's coverage enforcement, step 7's Socratic-prompt question)
that would otherwise block a one-constant threshold change. Prerequisites were therefore: the
arc's **PR-1 (labels, DONE — #1204/#1205)**, then its **PR-2 (activation with the carve-out,
DONE — #1208)**, then this slice — **executed exactly so, 2026-08-31**. Originally captured the conclusion of a "should we adopt LangChain
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

### The gap this doc existed to close (closed for one shape, 2026-08-31)

Askesis could only answer questions that fit its pre-built retrieval shapes:
`retrieve_relevant_context` had branches for `PREREQUISITE`, `PRACTICE`, `HIERARCHICAL`, and
`EXPLORATORY` — but **no branch for `AGGREGATION`**, so count questions fell through to bare
MEGA-QUERY counts + vector chunks with no real graph aggregation. The first slice added the
`AGGREGATION` branch (tool-selection → deterministic delivery) for exactly ONE shape — the
time-windowed achieved-goals count — and an explicit decline for every other count question.
Open-ended ad-hoc analytics — *"how many goals did I complete last quarter that were blocked
by a habit I dropped?"* — still decline: the relationship-bearing shape needs service-level
cross-domain aggregation and its own catalog entry, a separate decision.

## ⚠ How to read the code below

These blocks are **shape, not implementation** — the design the first slice was built against
(the real code lives in `core/services/askesis/query_tools.py` and its callers; where the two
differ, the code is the truth and the shapes are rationale). Eight rounds of review (#1202)
corrected them against the real codebase, so the ⚠ notes are checked facts — the `User.uid`
spelling, the per-domain completion fields and their ISO-string persistence, `execute_query`'s
`Result` wrapper, the service/adapter boundary, `LLMService.caller`, and the three answer
paths. Of the two problems below, the slice CLOSED problem 2 by construction and answered
problem 1 for one catalog entry only — problem 1 is the standing review bar for every future
catalog addition.

### OPEN PROBLEM 1 — coverage cannot be enforced by the model

`tool_choice="auto"` can say "no tool", but it cannot say *"I picked the closest one and it does
not really fit."* Given *"how many goals did I complete last quarter that were blocked by a habit
I dropped?"*, the model selects `count_goals_achieved`, the name resolves, the args validate, and
the answer is a total that **silently drops the habit predicate** — a confident wrong number,
the worst outcome this document can produce. Scheduling discipline ("don't let a shape classify
before a tool covers it") is necessary but **not sufficient**: activating `AGGREGATION` activates
the whole intent, and a novel production question the labelled set never anticipated still
reaches selection. What is missing is a **deterministic runtime coverage check** — a
capability predicate the selection is validated against, or a catalog complete enough that no
in-scope question falls outside it. **Still unresolved after the first slice** (2026-08-31):
the slice mitigates with a selection stance that instructs near-match declining
(`core/prompts/templates/askesis_tool_selection.md`), a period-only args model (no free-form
dates to approximate with), and an answer that states its applied bounds in code — but an
instruction to a model is not an enforcement mechanism, and this problem gates catalog growth.

### OPEN PROBLEM 2 — a decline must not be answerable around

Storing `context["aggregation_declined"]` puts the reason into ordinary prompt context, where
`_format_additional_context` renders it as one more scalar while the surrounding prompt still
instructs the model to answer from actual data. The model can simply ignore it and produce the
generic answer the decline exists to prevent. A decline therefore needs a **deterministic branch
that short-circuits generation** and returns a learner-visible "not answerable yet", not a hint
dropped into a prompt. **Closed by construction in the first slice** (2026-08-31): every
AGGREGATION outcome — Answered, Declined, Unavailable — renders its own answer text in the
pipeline and no generation runs; the decline IS the answer, not a context hint
(pinned by `tests/unit/test_askesis_aggregation_delivery.py`).

Both are the same shape of mistake, worth naming once: **an instruction to a model is not an
enforcement mechanism.** Every guarantee in this design has to hold in code the model cannot
route around.

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
   ├─ tool name ∈ catalog?            (else → Declined(reason), DELIVERED — not a fall-through)
   ├─ args validated by pydantic       (typed, schema-checked)
   ├─ user_uid := user_context.user_uid (INJECTED here — never from the LLM)
   └─ backend.<vetted_parameterized_cypher>(user_uid=…, **args)
   │
   ▼
context["aggregation"] = result   →   existing ResponseGenerator answers in NL
```

### 1–2. The catalog and its entries — requirements, not a body

Successive review rounds produced a defect per revision in this block; what survives review is
what the shapes must satisfy. `core/services/askesis/query_tools.py` (new):

- **The catalog needs a typed ERASURE BOUNDARY, and neither obvious option is it.**
  `Result[T]` is invariant here, so `QueryTool` cannot declare `Result[ToolPayload]` over a
  union and accept a handler returning `Result[GoalsAchievedCount]` — MyPy rejects it and the
  zero-error gate fails. But parameterising (`QueryTool[P]`) only works for a *homogeneous*
  catalog: the moment a second domain is registered, `QueryTool[GoalsAchievedCount]` and
  `QueryTool[TasksCompletedCount]` cannot share one `dict`. Since the catalog is designed to
  grow per domain, the design must **normalise each handler into one common result type at the
  registration boundary** (or provide an equivalent typed narrowing), so registering the second
  tool is not the thing that breaks the type gate. Unresolved — and it bites at tool #2, not
  tool #1, which is what makes it easy to ship past.
- **The args model is narrow, enum-bound, and per-domain.** No `entity_type` dial — the
  completion field differs per domain (§ 3), so a generic tool can only be wrong for some of
  them, and a narrow schema is also what stops the model selecting a shape that has no field to
  filter on.
- **Cross-field validation belongs in the args model**, not downstream. A model-emitted
  `since > until` must fail validation and take the deterministic unavailable path — otherwise
  the backend faithfully returns `0` for an empty interval and a **malformed selection is
  presented as a real answer**. Same failure family as everything else here: a wrong number
  that looks like a right one.
- **`handler` is a bound SERVICE method** (`GoalsService`, not `GoalsBackend`) — a `core/` file
  naming a concrete adapter is a SKUEL023 error, and binding the backend lets the executor
  bypass domain-service orchestration.
- **The tool's JSON schema comes from pydantic** (`model_json_schema()`), so the provider tool
  spec and the validation gate can never drift apart.
- **Entries are added per domain**, each bound to its own service and its own completion field:
  `count_goals_achieved` (`achieved_date`), `count_tasks_completed` (`completion_date`), …
  **There is no `count_entities_by_status`** — that shape cannot be written correctly across
  domains.
  ⚠ **And `count_habits_completed` is NOT `Habit.completed_at`.** That field is the habit's
  **lifecycle** stamp — the habit itself was closed out — and `habits_core_service.py` marks it
  as "distinct from occurrence completions" in as many words. The thing a learner means by "how
  many times did I do this" lives in **`HabitCompletion` nodes**, read through the completions
  sub-service. Binding the lifecycle field would answer a daily habit with **0 or 1**. Define
  that tool against habit completions, not against the Habit node. (Codex, #1202.)

### 3. The backend method — the *only* place Cypher exists (SKUEL001-clean, user-scoped)

```python
# adapters/persistence/neo4j/backends/activity_backends.py — on GoalsBackend
async def count_goals_achieved(
    self,
    *,
    user_uid: str,                 # ← always required, always bound as a param
    since: date | None = None,
    until: date | None = None,
) -> Result[GoalsAchievedCount]:      # ← the TypedDict, not dict[str, Any]
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
    # f-string + `RelationshipName.OWNS.value`, matching every real backend: a raw
    # `[:OWNS]` detaches the query from the canonical edge vocabulary, and an edge
    # name Neo4j does not know matches ZERO rows rather than erroring (SKUEL013 /
    # SKUEL030). Note the DOUBLED braces the f-string forces on the property map.
    cypher = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(g:Goal)
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
    # ⚠ Return the APPLIED BOUNDS with the count, in a TypedDict — not a bare total.
    # The safety contract requires the answer to state the scope it actually filtered
    # on, which is impossible if the resolved since/until do not survive the call. It
    # matters most exactly where it is easiest to forget: when the bounds were resolved
    # server-side from a relative period like "last quarter".
    return Result.ok(GoalsAchievedCount(
        total=rows[0]["total"] if rows else 0,
        since=params["since"],
        until=params["until"],
    ))
```

⚠ **There is no single completion field, so a date-bounded count CANNOT be one generic
`EntityType` tool** (Codex, #1202 — verified against the models):

| domain | completion field | model type | **persisted in Neo4j** |
|---|---|---|---|
| Task | `completion_date` | `date` | **ISO string** `"2026-06-15"` |
| Goal | `achieved_date` | `date` | **ISO string** `"2026-06-15"` |
| Choice / Event / Habit | `completed_at` | `datetime` | **ISO string** `"2026-06-15T08:09:10.111213"` |
| Habit *occurrences* | ⚠ **not a field** — `HabitCompletion` nodes | — | the row above is the habit's LIFECYCLE close, not "times done" |
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
   ⚠⚠ **Widening the bound is NOT sufficient, because offsets break the ordering outright.**
   `completed_at` is a bare `datetime` on the Choice/Event request models, so an offset-aware
   value is accepted and the mapper preserves that offset in the stored string — and the
   codebase writes tz-aware ISO elsewhere (`datetime.now(UTC).isoformat()`). Lexicographic
   order is then not chronological at all: `"…10:00:00+02:00"` sorts AFTER
   `"…09:00:00+00:00"` while occurring BEFORE it. Normalise stored values and bounds to one
   timezone and format, or convert both operands with Neo4j `datetime()` before comparing.
   **Sorting ISO strings is chronological only when every string shares a shape AND an
   offset.** (Codex, #1202.)
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

# ⚠ There is no `self.client` on LLMService, and there must not be. It holds
# `self.caller: LLMCallerProtocol` (llm_service.py:116), and vendor SDK clients live
# behind `adapters/external/llm/` by ADR-063 — `tests/unit/test_llm_sdk_boundary.py`
# fails closed on any vendor import in `core/`. So tool selection is a NORMALIZED
# operation added to the caller port, not an SDK call written here; the
# OpenAI/Anthropic tool-schema shapes are the ADAPTER's business.
# Deliberately stated as REQUIREMENTS, not a body. Three review rounds produced
# three different speculative implementations here, each with its own defects;
# the durable content is what the operation must satisfy:
#
#   • Lives on the CALLER PORT, not in LLMService — no vendor SDK may enter
#     `core/` (ADR-063; tests/unit/test_llm_sdk_boundary.py fails closed).
#     Provider tool-schema shapes are the adapter's business.
#   • Returns `Result[ToolSelection]`. Provider auth, network and parse failures
#     need a typed path — every other caller operation returns `Result`, and a
#     bare return turns them into exceptions or malformed selections.
#   • Threads the RESOLVED MODEL through. `UnifiedLLMCaller` picks its adapter
#     from the model prefix, so an operation that passes only the question and
#     schemas routes to the caller's default — in an Anthropic-only deployment,
#     to an unwired OpenAI adapter that rejects every selection.
#   • Returns "no tool" as a normal outcome, NOT an error — that is a Declined,
#     and it is the only decline the model can express (OPEN PROBLEM 1).
#   • Has NO CORE-tier branch. Askesis is constructed only at
#     INTELLIGENCE_TIER=FULL with every dependency required and fail-fast
#     (askesis_factory.py, askesis_service.py) — a `caller is None` path here
#     would be unreachable code contradicting that philosophy.
```

⚠ **`select_tool` must be handed a trusted reference date, or "last quarter" is a guess.**
The model is asked to emit absolute `since`/`until` values from a relative phrase, and it has no
reliable "today" — a hallucinated or stale bound produces a confidently wrong count with no
error anywhere. Either pass the current date and the user's timezone into the selection prompt
as system-supplied context (never trusting a date the model volunteers), or keep relative
periods out of the args model entirely and resolve them server-side from an enum
(`last_quarter`, `this_month`, …). The second is narrower and harder to get subtly wrong, which
is the same reason the args model is domain-narrow. (Codex, #1202.)

### 5. The executor — validation + the critical `user_uid` injection

⚠ **`run_tool` as shown CANNOT enforce the decline, and this is the design's weakest
point.** It checks only that the selected NAME exists in the catalog. Hand
`tool_choice="auto"` the relationship-bearing question — *"how many goals did I complete last
quarter that were blocked by a habit I dropped?"* — and the model will happily select
`count_goals_achieved`: the lookup succeeds, the args validate, and it returns a total that
**silently ignores the habit predicate**. A confident wrong number, which is the worst outcome
in this whole document. Two mitigations, and the first is not optional:

1. **Coverage is a SCHEDULING gate, not a runtime one.** A question shape must not be allowed to
   classify as `AGGREGATION` before a tool exists that answers it. That is why step 6 sits before
   activation, and why the labelled set in
   [askesis-intent-classification-activation.md](askesis-intent-classification-activation.md)
   PR-1 is the thing that exposes the gap.
2. **Make the applied scope visible in the answer.** The tool returns what it actually filtered
   on, and the response states it — *"You achieved 4 goals between 1 Apr and 30 Jun"* — so a
   dropped predicate reads as a mismatch to the learner instead of disappearing. A model asked
   to self-report "aspects I could not honour" is not a substitute: that is the same model that
   just mis-selected.

```python
# ⚠ A DECLINE IS NOT AN ERROR. Step 6 requires an out-of-coverage question to be
# declined with a reason, but an `Errors.validation` here is indistinguishable from
# a genuine failure, and the § 6 branch logs errors and continues — so the response
# generator answers the unsupported question anyway and the reason is discarded.
# Model the intentional decline as its own outcome and DELIVER it to the answer
# path, so the learner is told the question cannot be answered yet rather than
# being given a plausible substitute. (Codex, #1202.)
async def run_tool(
    selection: ToolSelection,
    catalog: dict[str, QueryTool],
    user_context: UserContext,
) -> Result[ToolOutcome]:          # ToolOutcome = Answered(payload) | Declined(reason)
    tool = catalog.get(selection.tool_name or "")
    if tool is None:
        # No tool matched — a coverage gap, not a failure.
        return Result.ok(Declined(reason=f"no tool covers this question yet"))
    try:
        args = tool.args_model.model_validate(selection.arguments)  # schema gate
    except ValidationError as e:
        return Result.fail(Errors.validation(f"Bad tool args: {e}"))

    # user_uid comes from the authenticated context, NEVER from the LLM:
    result = await tool.handler(user_uid=user_context.user_uid, **args.model_dump())
    if result.is_error:
        return Result.fail(result)              # a real failure, not a decline
    return Result.ok(Answered(payload=result.value))
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

**Decided and shipped (first slice, 2026-08-31) — the delivery point per path:**

| path | decision |
|---|---|
| non-guided chat | an `AGGREGATION` verdict short-circuits generation; the outcome's own text (Answered with its exact bounds / Declined / Unavailable) IS the answer |
| guided chat | **an aggregation never enters the Socratic prompt** (ADR-077 preserved — the guided prompt and its builders are untouched). The pedagogical call: a count question is not a Socratic turn, so an `AGGREGATION` verdict BYPASSES the guided pipeline and takes the deterministic branch above — a guided-eligible learner asking a count gets the count (or the decline), not a Socratic deflection over an invisible number |
| `process_query_with_context` | **does not serve the tool** — it declines deterministically at intent time rather than letting its generic generator answer a count question (the fall-through this doc forbids). The chat pipeline is the one surface that serves aggregation |

Pinned by `tests/unit/test_askesis_aggregation_delivery.py`.

**Requirements, not a snippet.** Successive drafts of this branch produced a defect per
review round; what it must satisfy is the durable part:

- **Unwrap `select_tool`'s `Result` before executing.** A provider failure is not a selection.
- **Three outcomes, three behaviours, and only one of them resumes normal generation:**

  | outcome | behaviour |
  |---|---|
  | `Answered(payload)` | attach the result; the answer must state the scope it actually filtered on |
  | `Declined(reason)` | deterministic learner-visible "not answerable yet" — **must not** be a hint in prompt context (OPEN PROBLEM 2) |
  | selection or tool **FAILED** | ⚠ **also not baseline generation.** An embeddings/provider outage on a reachable `AGGREGATION` question would otherwise let the ordinary generator produce a plausible **invented count** — the failure mode this whole document exists to avoid, arriving through the error path instead of the selection path. Return a deterministic "unavailable", the same shape as a decline. |

- **Deliver on every answer path**, not just where the value is computed (§ 7).

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
| Hard failure mode | LLM may return **no tool** → `Declined(reason)`, delivered to the learner — never a silent fall-through to a generic answer |

What we give up vs. real text2cypher: we can only answer question *shapes* we've added
a tool for. Each tool still covers a whole parameter space (its domain × date range), so a
handful of tools covers much of the `AGGREGATION`/`RELATIONSHIP` gap —
while keeping every SKUEL safety guarantee.

## Proposed first slice — ✅ SHIPPED 2026-08-31

Implemented as specified, one PR (see the Status block for what landed and the two rulings —
coverage: decline outside the catalog; delivery: § 6's decided table). Kept verbatim below as
the executed scope. **One** tool end-to-end, behind the FULL intelligence tier
(`INTELLIGENCE_TIER=full`, so the $0 analytics tier is unaffected):

1. `count_goals_achieved` on `GoalsBackend` (parameterized, user-scoped Cypher —
   `(u:User {uid: $user_uid})`, `achieved_date`; see the ⚠ in § 3 for why it is
   per-domain and not a generic `EntityType` count).
2. `QueryTool` + `CountGoalsAchievedArgs` + a one-entry aggregation catalog.
3. `LLMService.select_tool()` for the **Anthropic** provider in use.
4. `run_tool` executor with the `user_uid` injection.
5. The `QueryIntent.AGGREGATION` branch in `context_retriever.py`. ⚠ **It cannot fire until
   this slice lifts the carve-out.** `AGGREGATION` keeps its exemplars (ruled 2026-08-31 — see
   that doc's ruling 2), and since the arc's PR-2 (2026-08-31) the gate is live at 0.35 — but
   `classify_intent` holds `AGGREGATION` out of the production verdict (`UNREACHABLE_INTENTS`),
   so a branch added without lifting the carve-out is dead on arrival, and lifting the
   carve-out without the branch re-opens the window below.
   **This branch and the removal of PR-2's `AGGREGATION` carve-out are ONE change** — see the
   Status note. The harm to prevent is a window in which count questions classify as
   `AGGREGATION`, meet no branch, fall through to ordinary generation, and are answered
   generically or invented, with neither a tool result nor the promised decline (Codex, #1202).
   An earlier draft said to build this "after PR-2", which opens exactly that window; the
   carve-out closes it instead, and lifting the carve-out without the branch in the same commit
   re-opens it. ⚠ So the dangerous edit is not adding this branch late — it is deleting the
   exclusion early. It must also not land
   before PR-1 has disambiguated `AGGREGATION` from `EXPLORATORY`, or a topic-orientation
   question ("introduce me to stoicism") routes here and is answered with a COUNT. So the
   ordering is: **PR-1 (labels, DONE) → PR-2 (activation with the `AGGREGATION` carve-out,
   DONE 2026-08-31) → this branch, which removes the carve-out in the same commit that adds
   the tool.**
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
   (LLM-supplied `user_uid` ignored) + the no-tool **decline** path + **the count actually reaching
   the answer on every path step 7 claims to serve** — the delivery half is where this
   silently fails, not the selection half — + **an out-of-coverage question is declined, and
   the DECLINE reaches the learner** rather than the generator answering anyway (step 6) +
   **a same-day `until` bound includes that day** on a `completed_at` domain (§ 3,
   consequence 2) + **a relative period resolves against a server-supplied date**, never one
   the model volunteered (§ 4).

Try it against a live question before deciding whether the pattern earns its keep.
*(✅ Verified live, 2026-08-31 — two drives. At ship time the environment's Anthropic key was
invalid (401), so the first drive proved routing, deterministic delivery, the API decline, the
cross-tenant probe, and the § 6 failure fold — every count answered the honest "unavailable",
no invented number anywhere. After the key rotation the full split was re-driven: the covered
shape answered with the real count and its exact applied bounds ("Goals achieved between
2026-04-01 and 2026-06-30: 0.") on normal chat AND the nous-scoped path, while ALL SIX of the
ratified set's AGGREGATION queries declined with the stated coverage reason — including the
predicate-bearing "blocked by a habit I dropped" shape, where the model declined rather than
picking the nearest tool (OPEN PROBLEM 1's mitigation holding on the exact query that names
it), and "how many tasks did I complete this week", the right shape on the wrong domain.
Nothing fell through to generation on any probe.)*

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
