---
title: "MEGA-QUERY Sits on the Plan-Cache Cliff"
updated: 2026-09-14
status: "done — Option A (the learning-loop tail lifted) then Option B (the statement split into the six RICH_CONTEXT_STATEMENTS, merged by execute_mega_query); the cliff is structurally unreachable and every statement is pinned under the edge by tests/integration/test_user_context_plan_cache.py, which derives its parametrization from the registry"
trigger: "the next read the rich context needs — it is a new RICH_CONTEXT_STATEMENTS entry, never a section appended to an existing statement (the guard fails otherwise); OR the AuraDB tier changing"
check: "tests/integration/test_user_context_plan_cache.py — the third back-to-back execution of every RICH_CONTEXT_STATEMENTS entry, SUBMISSION_STATS_QUERY, ENTRY_KNOWLEDGE_APPLIED_QUERY and CONSOLIDATED_QUERY reads `result_available_after` under 100 ms (cached: 2-5 ms; re-planned: 500+ ms), and test_every_statement_constant_is_guarded names any *_QUERY constant the parametrization misses"
registered: "2026-09-13 (measured while diagnosing the Askesis pipeline timeout, PR #1326)"
---

# MEGA-QUERY Sits on the Plan-Cache Cliff

**Status: ✅ DONE — 2026-09-13.** Option A lifted the learning-loop tail (#1330); Option B split
the remaining statement into the six `RICH_CONTEXT_STATEMENTS` — see *What landed (Option B)*
at the end. Nothing here remains open; the guard is the registry-derived
`tests/integration/test_user_context_plan_cache.py`.

**One sentence:** the rich-context MEGA-QUERY (`adapters/persistence/neo4j/user_context_queries.py`,
1,219 lines, 70 KB) executes in ~40 ms but is **re-planned on every execution** — ~0.5 s on a
self-hosted 2026.07 server, ~1.05 s on AuraDB Free — because it is one block past the point at
which Neo4j stops serving it from the plan cache; every prefix of it up to one block shorter is
cached and answers in single-digit milliseconds.

This file exists so the next structural decision about the query is made from measurements, not
from the belief that "one round-trip" is what makes it fast.

## What was measured (2026-09-13)

All timings are `summary.result_available_after` from the Neo4j driver — server-side time until
the first record — unless marked *wall*. The learner is the `enrolled_user_with_lp` test fixture:
one User, one LP, one PS, one Ku, no activity. **Against AuraDB Free `5.27-aura` (the production
graph, from this machine)** unless marked *container* (the integration testcontainer,
`neo4j:2026.07.1` community, query cache 1,000 entries, page cache 512 MiB).

| Measurement | Aura Free | Container |
|---|---|---|
| MEGA first execution (cold plan) | 4.9–5.3 s | 4.9–5.6 s; 3.0 s after `db.clearQueryCaches()` |
| MEGA every later execution, back-to-back ×8 | **1,040–1,130 ms** | **500–660 ms** |
| MEGA `EXPLAIN` only (planning, no execution), later runs | 1,130–1,190 ms | 550 ms |
| MEGA `PROFILE`: operators / total DbHits / summed operator time | 406 / 239 / **37 ms** | — |
| MEGA `result_consumed_after` (execution after first row) | 8–10 ms | 4–7 ms |
| MEGA wall per call, warm | 1.65–1.95 s | 0.77–0.95 s |
| CONSOLIDATED (standard context, 171 lines, 7.9 KB) first / later | 535 ms / **2 ms** | 295 ms / **2 ms** |
| Rich build end-to-end, cold (`get_rich_unified_context` on a cache miss) | **9.6–10.3 s** | — |
| — of which ZPD capstone (`assess_zone`) | 2.0 s | — |
| — of which `fetch_current_path_steps` + `fetch_user_groups` + `list_engaged` | 0.9 s | — |
| Warm rich context (in-process cache hit) | 0 ms | — |

Three readings of that table:

1. **Execution is trivial; planning is the cost.** For this learner the plan touches 239 nodes
   and relationships and spends 37 ms in operators. `EXPLAIN` alone costs the same as a full run.
   The recurring ~0.5–1.05 s is the planner/compiler, redone each time.
2. **The plan is not reused — and that is a property of this query, not of Aura.** The
   consolidated query's second run is 2 ms on both servers; MEGA's is never. Aura is ~2× slower
   at the same planning work (a CPU-class difference), and adds ~0.2 s of network/session per
   call from this machine, plus the 70 KB query text uploaded on every execution.
3. **The cold build is the number users feel.** A cache miss costs ~10 s of which ~5 s is the
   first-ever planning of MEGA on that server, ~1 s its re-planning on later misses, 2 s the ZPD
   capstone, ~1 s three follow-up queries. The in-process cache holds a context for 300 s and is
   **invalidated by 45 domain events** (36 activity/domain + 9 learning, `services_bootstrap/_event_wiring.py`)
   — a task completion, a habit check, a journal entry — so an active learner pays the miss far
   more often than "once per five idle minutes".

## Where the cliff is — bisected, on the container

Prefixes of `MEGA_QUERY` cut at section boundaries, closed with a `RETURN`, each run three times:

| Cut | Lines | `OPTIONAL MATCH` | `WITH` | 2nd/3rd run |
|---|---|---|---|---|
| through CHOICES | 614 | 38 | — | 4–5 ms ✅ |
| through LEARNING PATHS | 860 | 50 | — | 4–5 ms ✅ |
| through ACTIVE INSIGHTS | 952 | 53 | — | 3–4 ms ✅ |
| through REVISED EXERCISES (before ENTRY KNOWLEDGE APPLIED) | 1,096 | 57 | 75 | **2 ms ✅** |
| + ENTRY KNOWLEDGE APPLIED (= before the RETURN block) | 1,147 | 58 | 77 | **460–520 ms ❌** |
| full query | 1,219 | 58 | 77 | 500–660 ms ❌ |

It is **cumulative, not a construct.** Removing the `reduce(… pattern comprehension …)` from the
last block, or the same construct from the TASKS block, changes nothing. Taking the 1,096-line
prefix that caches and appending **duplicates of an already-cacheable block** (REVISED EXERCISES,
renamed): one duplicate (58 `OPTIONAL MATCH` / 76 `WITH`) still caches at 3 ms; two (59 / 77)
flips to 480–525 ms. The full query is at 58 / 77 — **one block over the edge**.

The server's `debug.log` at default level says nothing about it (community edition, no query
metrics). The mechanism is therefore unconfirmed; the two candidates are the pipelined runtime's
code generation exceeding a JVM class/method size limit and falling back per execution without
caching the fallback, or a planner-side size guard. Neither changes the decision below; either
would be settled by running the 1,147-line cut with `CYPHER runtime=slotted` (if the cost drops
to ms, it is code generation) — a ten-minute experiment, listed under *What would settle more*.

## What that means for the structure

The MEGA-QUERY's design premise — *one round-trip beats five* — comes from the November 2025
consolidation that took the standard build from 5–9 **sequential** round-trips to 1–2 (measured
3–5×; the docstrings on `build_user_context` and `build_rich_user_context` record it). The
premise is still true for sequential round-trips; it is false for planning, and it never priced
*concurrent* round-trips.
Today the one query costs more in re-planning (0.5–1.05 s, every time) than five cached queries
would cost in round-trips **run concurrently** (≈ one round-trip's latency, ~0.2 s from here to
Aura), and nothing in the query needs the sections to be one statement: after the initial
`MATCH (user:User {uid: $user_uid})`, the 16 data sections share only `user` — no section's
`MATCH` or `WHERE` reads another section's output (checked mechanically 2026-09-13); only the
final `RETURN` map does. Every `WITH` carries the previous sections' aggregates through unchanged,
which is what makes the `WITH` lines 30 variables wide.

### Options, priced

**A. Back under the edge — remove one block from the statement.** Move the ENTRY KNOWLEDGE
APPLIED block (51 lines, one `OPTIONAL MATCH`, two `WITH`s) — or any block of that shape —
into its own query in `UserContextQueryExecutor`, awaited alongside `fetch_current_path_steps`.
Cost: one new executor method + one populator call; the `RETURN` map loses one key. Gain: the
remaining 1,168-line statement is at 57 / 75 and **caches** — later executions drop from
~1,050 ms to single-digit ms on Aura (the bisect's 1,096-line cut reads 2 ms). This is the
cheapest change and the largest single gain. Its risk is that it is a *cliff*, not a slope:
the next section anyone adds puts the query back over it, silently. Pair it with the check
in this file's frontmatter run as a test (see *Guarding it*).

**B. Split by section into 2–4 concurrent statements.** Group the sections by what they read
(activities: TASKS/GOALS/HABITS/EVENTS/PRINCIPLES/CHOICES; curriculum: KNOWLEDGE/KU INTERACTION/
LEARNING PATHS/MOCs; learning loop: ACTIVITY REPORT/INSIGHTS/SUBMISSION/ENTRY KNOWLEDGE), each
its own statement starting from the `MATCH (user)`, run with `asyncio.gather` on separate
sessions, merged in Python where the executor already assembles `{"uids", "entities", "rich"}`.
Cost: a day — the `WITH`-carried variables have to be un-threaded per statement and the
`RETURN` map re-assembled; every populator reads the same dict shape, so the populator does not
change. Gain: every statement caches (each is far under the edge — the widest group is smaller than
the 614-line / 38-`OPTIONAL MATCH` cut, which the bisect shows at 4–5 ms), wall time is the slowest
statement's execution plus one round-trip, and the cliff is structurally unreachable — a new
section lands in one statement, not on the sum. This is the design that stops the problem
recurring.

**C. Leave it, widen the cache.** Raise the in-process TTL or narrow the invalidation set so
misses are rarer. Cost: near zero. Gain: none on the cold path users actually hit — the first
Askesis question, the daily plan after any completion, the report after a journal entry — and
a staleness cost on every field the 47 events exist to keep fresh. Not recommended on its own;
reasonable *alongside* A or B for the 2 s ZPD capstone, which is the next-largest cold cost and
is unaffected by either.

**Recommendation:** A now (it is a one-PR change with a measured 100× on the recurring cost),
B when the next section is needed, C never alone.

### What landed (Option A, wider than priced)

Lifting ENTRY KNOWLEDGE APPLIED alone did **not** put the statement under the edge: the
bisect above closed each prefix with a *minimal* `RETURN`, and the real 70-line `RETURN` map
counts toward the same budget. Measured on the container with the block removed
(57 `OPTIONAL MATCH` / 75 `WITH`, the full `RETURN`): still 543–646 ms on every run. Removing
REVISED EXERCISES as well: still 552 ms. Removing the `submission_stats` map from the `RETURN`
as well: **3 ms**. So the whole learning-loop tail left the statement — SUBMISSION & FEEDBACK
STATS + REVISED EXERCISES became `SUBMISSION_STATS_QUERY` (returns exactly the map
`populate_submission_stats` consumes), ENTRY KNOWLEDGE APPLIED became
`ENTRY_KNOWLEDGE_APPLIED_QUERY` (one row per entry, a `EntryKnowledgeAppliedRow`), and
`build_rich_user_context` runs all six statements (MEGA + those two + current path steps,
engagements, groups) under one `asyncio.gather`. `MEGA_QUERY` is now 53 `OPTIONAL MATCH` /
69 `WITH`, ~1,010 lines, and caches.

`build_rich_user_context` wall time on the container, five back-to-back builds:
**before** `[7049, 991, 1044, 1029, 929]` ms — **after** `[4980, 219, 259, 219, 216]` ms.
The remaining ~220 ms warm is transport (the ~65 KB statement text and its result) plus
Python population, not planning; the cold first build is the first-ever planning of the
six statements on that server.

The guard is `tests/integration/test_user_context_plan_cache.py`: three executions of each
statement with the app's own parameter builder (`build_mega_query_params`), the third under
100 ms `result_available_after`. Proven to fail first — against the pre-split `MEGA_QUERY` it
read `[7378, 639, 597]`.

### Guarding it

Whichever option lands, the property to pin is *"the third back-to-back execution of every
rich-context statement reads single-digit ms `result_available_after`"* — an integration test
against the testcontainer (the bisect harness was exactly this, ~20 s). A line-count or
`OPTIONAL MATCH`-count assertion is the wrong guard: the edge is cumulative and server-version
dependent, and the driver summary measures the real thing.

### What landed (Option B)

The remaining 1,013-line statement became six, one per read family, in ONE registry
(`RICH_CONTEXT_STATEMENTS`, `user_context_queries.py`): **tasks & goals** (`progress_counts`
spans both, and each projects the other), **habits & events** (the practice pair — an event's
practiced / reinforced habits), **principles & choices** (the values pair the populator
integrates), **knowledge** (every user→Ku edge: mastery, viewed, read, bookmarked),
**curriculum** (enrolled paths, active steps, MOCs), **learner state** (life path, latest
report, active insights — the family most likely to grow, so a statement of its own). Each
carries only its own names through its `WITH` lists and returns the partial of the merged map
it owns; `execute_mega_query` runs them concurrently (each in a session of its own) and merges
by top-level key into the exact `mega_data` shape the populator reads — the port, the builder,
the populator, the extractor and the three unit fakes did not change.

**The grouping was decided by measurement.** Prefix statements cut at section boundaries were
generated mechanically from the old text (the `WITH` lists un-threaded per statement) and timed
on the container, cold (`db.clearQueryCaches()`, first build) and warm, three repetitions:

| Grouping | statements | largest | cold build | warm build |
|---|---|---|---|---|
| one statement (the old shape, regenerated) | 1 | 59 KB | ~2,350 ms | ~40 ms |
| activities / curriculum / learner state | 3 | 32 KB | ~1,400 ms | ~28 ms |
| activities halved (by size) / curriculum / learner state | 4 | 14 KB | ~720 ms | ~20 ms |
| the six read families above | 6 | 9 KB | ~580 ms | ~19 ms |
| one per domain (tasks+goals, 4 activities, knowledge, paths, learner state) | 8 | 9 KB | ~570 ms | ~18 ms |

The planner's cost is super-linear in statement size — the six-section activities statement
alone (504 lines) planned in ~2.2 s, the whole old statement in ~2.5 s — so the cold build is
set by the largest statement and the step that matters is getting every statement to
~250 lines; finer than that buys ~10 ms and doubles the concurrent sessions. Six is the
coarsest grouping at that size whose every pairing the codebase already names.

**Before / after, same container, same session, interleaved** (`build_rich_user_context`, five
builds after `db.clearQueryCaches()`): before `[5386, 72, 53, 50, 53]` and `[2977, 32, 39, 32, 36]` ms;
after `[1075, 27, 28, 26, 29]` and `[775, 18, 22, 22, 27]` ms. Per statement, cold plan → cached:
the old statement `[2558, 4, 3]`; tasks & goals `[439, 2, 3]`, habits & events `[402, 3, 3]`,
principles & choices `[369, 2, 2]`, knowledge `[153, 2, 2]`, curriculum `[295, 10, 2]`, learner
state `[134, 4, 2]` — the six sum to 1.8 s of planning against 2.6 s, so a single-core server
that serialized them would still come out ahead. Statement text 59,402 → 39,503 bytes in total
(the carried names were a third of the old text), 9,420 at most per statement. On AuraDB the
warm gain is the smaller per-statement upload; the cold gain depends on how many statements it
plans concurrently — neither was re-measured there.

**Three silent defects the split exposed, each proven against the old text first:**

- **A learner whose every insight was dismissed, actioned or expired got an EMPTY rich context.**
  The insight predicate was `WITH …, ins WHERE ins IS NULL OR (…)` — a row filter after the
  grouped aggregation — so no row survived and the whole statement returned nothing
  (`{"uids": {}, "entities": {}, "rich": {}}` for a user with an active task). The predicate is
  on the `OPTIONAL MATCH` now, and `execute_mega_query` refuses a half-answer: a row from some
  statements but not others is a collapsed aggregation and fails the read loudly.
- **A goal with milestones failed the whole build** with `Neo.ClientError.Statement.TypeError:
  Type mismatch: expected a map but was String(…)` — `Goal.milestones` is stored as a JSON
  string (`neo4j_mapper` serializes a list of maps), which the `milestone_progress` projection
  iterated as a list. The projection had no consumer (`GOALS_CONFIG` says the count is derived
  from the parsed Goal) and is gone.
- **`completed_exercise_count` read −1 for every learner with no group-assigned exercise**
  (`SUBMISSION_STATS_QUERY`): `NOT` over a `FULFILLS_EXERCISE` pattern whose endpoint is null is
  true, so the unguarded `CASE` collected one phantom map and `0 − 1` followed. Guarded on
  `ex IS NOT NULL`.

**Guards:** `test_user_context_plan_cache.py` parametrizes over the registry plus the reads
beside it, and `test_every_statement_constant_is_guarded` fails on any `*_QUERY` constant it
does not run; `test_rich_context_statement_equivalence.py` seeds a learner in every section and
pins every field group of the merged map and of the built context to the values the SAME graph
produced through the pre-split text (captured before it was deleted), plus the two departures
above; `tests/unit/test_rich_context_statement_merge.py` pins the merge and the row-count
verdicts with a fake executor; `test_mega_query_null_placeholders.py` scans the module source,
so every statement stays in its scope.

**Observed, not changed (a decision, not a regression):** the knowledge section's
`MASTERED|IN_PROGRESS` alternation also matches the `PathStep` the user is `IN_PROGRESS` on, so
the step lands in `knowledge_mastery` at the 0.1 default; the equivalence test pins that as the
old semantics.

## What would settle more

- **Mechanism:** run the 1,147-line cut with `CYPHER runtime=slotted` prepended. Drops to ms →
  pipelined code generation is the limit (and `slotted` for this one statement is a fourth
  option, at the cost of slower execution on a large graph). Unchanged → planner-side.
- **Aura's per-call overhead:** the ~0.6 s of wall time per MEGA call that is neither
  `available_after` nor `consumed_after` (0.2 s for the consolidated query) — most likely the
  70 KB upload plus result transfer. Splitting (B) shrinks the upload per statement but not the
  total; only a smaller query does.
- **The ZPD capstone at 2 s** is a separate measurement; it runs its own queries after the
  MEGA-QUERY returns and would benefit from the same *concurrent, cached* treatment.

## Provenance note

These numbers were taken while diagnosing the Askesis `test_ask_endpoint_success` timeout
(PR #1326). At the time the `skuel_app` integration fixture bootstrapped from `.env`, which
since the 2026-08-15 cutover points at AuraDB Free — so the "Aura" column above **is** the
production graph, measured from the app's own driver path; the "container" column is the
`neo4j_driver` fixture. The fixture has since been bound to a testcontainer of its own
(`tests/integration/conftest.py::skuel_app`, guarded by `test_skuel_app_fixture.py`), so a
re-measurement through the app fixture lands in the "container" column; reproducing the Aura
column now takes an explicit `NEO4J_URI` on a throwaway harness.

## Related

- `adapters/persistence/neo4j/user_context_queries.py` — `RICH_CONTEXT_STATEMENTS`, `CONSOLIDATED_QUERY`,
  `UserContextQueryExecutor.execute_mega_query`
- `core/services/user/user_context_builder.py` — `build_rich_user_context` (the November 2025
  one-query rationale in its docstring), the ZPD capstone
- `core/services/user/user_context_cache.py` — the 300 s TTL and the invalidation policy
- `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md` — the UserContext contract the query serves
- [askesis-extraction-match-unverified.md](askesis-extraction-match-unverified.md) — the
  sibling finding from the same investigation (its test landed; the design half lives on in
  [../askesis-extraction-lookup-shape.md](../askesis-extraction-lookup-shape.md))
