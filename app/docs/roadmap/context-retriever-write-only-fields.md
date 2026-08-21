# ContextRetriever's Three Write-Only Fields

*Live plan. Registered 2026-08-20. Case file for the `deferred-work.md` entry of the same name;
move to `docs/roadmap/done/` when nothing in it remains open.*

`ContextRetriever` (`core/services/askesis/context_retriever.py`) assigns three `self.*` fields
that nothing reads. Surfaced by the AST sweep in PR #1108 and deliberately left there, because
they are **not** the case that PR was closing (write-only *deps copies*, all superseded).

Verified against `main` @ `409aded1d` on 2026-08-20. **Line refs drift and registers lie — re-run
every census yourself.** The sibling register for the substance-write arc needed **seven** Codex
rounds to become accurate, every finding real, most of them in claims written *from* measurements.

```python
# The Store-vs-Load sweep that found them — grep cannot distinguish the two
for n in ast.walk(cls):
    if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == 'self':
        (assigned if isinstance(n.ctx, ast.Store) else read).add(n.attr)
dead = assigned - read
```

⚠️ It only sees the class. Callers hold these objects as `Any` (routes reach `services.askesis`),
so **mypy cannot see an external read** and a green gate proves nothing about deletion safety.
Repo-wide grep for `context_retriever.<field>` returns nothing for all three — re-confirm before
removing anything.

**These are two different cases with probably two different verdicts. Do not batch them.**

---

## Case A — `graph_intel` (assigned `:185`)

Zero reads inside the class. Zero reads repo-wide. Yet the constructor still takes it (`:148`),
the Args docstring still describes it (`:174`), and the class docstring still asserts **"Requires
GraphIntelligenceService for graph queries."**

Working hypothesis, **unconfirmed**: superseded when `ku_backend` / `ps_backend` were injected,
which the constructor comments describe as *"migrated from inline Cypher"*. If so it is residue,
and residue gets deleted. Nobody has dated its death — do that with `git log -S`, the way #1107
dated the dual-layer doctrine to a single commit. **Superseded → delete; never-wired → ask.**

⚠️ **Same-name decoy, already verified.** `ASKESIS_ARCHITECTURE.md:537` documents
`self.graph_intel.backend.get_prerequisite_graph(...)` — that is **`ContextRelevanceEngine`'s own
live field** (`context_relevance_engine.py:58`, read at `:93` and `:247`), a different class with
the same attribute name. It is not evidence about this one. This trap has now cost this arc
repeatedly; see also `TemplateBundle` below.

## Case B — `events_service` (`:199`) + `principles_service` (`:200`)

**Staged, not dead**, and the code says so:

```python
# load_ps_bundle, ~:505
events: list[Any] = []      # Event templates not yet in graph_context
principles: list[Any] = []  # Principles not yet in graph_context
```

`PsBundle.principles` (`core/models/askesis/ps_bundle.py:64`, *"via EMBODIES_PRINCIPLE"*) and
`PsBundle.events` (`:67`, *"via event templates"*) exist and are **permanently empty tuples**.
`load_ps_bundle` fetches habits and tasks from `graph_context` and hardcodes the other two.

### The blocker is upstream, and it is a query change — not a wiring job

The MEGA-QUERY's `graph_context` projection (`adapters/persistence/neo4j/user_context_queries.py:889`)
emits exactly: `prerequisite_steps`, `practice_habits`, `practice_tasks`,
`knowledge_relationships`, `learning_path`, `total_prerequisites`,
`total_practice_opportunities`, `is_sequenced`. **No `practice_events`, no `practice_principles`.**

⚠️ `total_practice_opportunities` is `size(ps_habits) + size(ps_tasks)`. Adding channels without
updating it makes it silently undercount.

### The two halves are asymmetric — in building blocks *and* in payoff

| | Registry key | Protocol method | Direct consumer of the bundle field |
|---|---|---|---|
| **events** | `practice_events` **registered** (`relationship_registry.py:1431/1860`) | `PsOperations.get_practice_events` **exists** (`curriculum_protocols.py:768`) — ⚠️ **zero callers** | ✅ `response_generator.py:307` |
| **principles** | none | none | ✗ indirect only |

**Events has a real, learner-visible consumer.** `response_generator._build_guided_practice`
(ENCOURAGING mode, `askesis_guided_practice` template) builds its practice list from
`bundle.habits`, `bundle.tasks` **and `bundle.events`**. Because events is always empty, the
Socratic prompt lists habits and tasks as practice and **never an event** — a real gap a learner
experiences, not just an unfilled field.

**Principles has only indirect reach.** `PsBundle.get_all_uids()` / `get_all_titles()` include
both collections; `intent_classifier.py:291` consumes `get_all_titles()`. So empty principles
narrows what intent classification can match against — real, but a matching-recall effect rather
than visible content.

⚠️ **Same-name decoy, verified.** `ps_engagement/_template_bundle.py`, `_validator.py` and
`ps_engagement_service.py` all reference `bundle.events` / `bundle.principles` — those are
**`TemplateBundle`** (`EventTemplate` / `PrincipleTemplate`), a different class. They are **not**
evidence that `PsBundle`'s fields are consumed.

### The verdict here is Mike's

Plausible endings: **finish the wiring** (a MEGA-QUERY projection change plus `total_*` fix, and
`get_practice_events` finally gets its caller) · **delete both halves** as an abandoned idea ·
**register as visible backlog** and leave the code. Per the phase directive a feature-shaped
answer gets *"not now" + a named cost*. The events half has the stronger case — a live consumer
and its building blocks already registered; principles would be built from scratch.

⚠️ If the ending is "register it": `./dev bloat`'s PLANNED tier covers **events/methods/templates
only**, so there is no tier for fields — which is exactly why an AST sweep found this and the
tooling did not. `get_practice_events` *is* a method and could be registered in `PLANNED_METHODS`
(it is not today). `docs/reference/PLACEHOLDER_INDEX.md` is the plausible home for the field half;
it does not currently list these.

---

## Ground rules

1. **Investigate → verdict → Mike's ruling → implement.** Case A may be decidable on evidence;
   Case B is a product call.
2. **Assigned-never-read is not a synonym for dead.** Deletion protocol: superseded → delete,
   unwired → **ask**. The discriminator that worked in #1108 was a dated changelog line naming
   what replaced the field. Find one, or you have not established supersession.
3. **A test naming a field is not a reader.** If a test is the only consumer you find, that is
   evidence *for* deadness — and the test is then part of the fix (#1108's defect class).
4. **If you delete a constructor parameter, delete it everywhere.** Removing `embeddings_service`
   in #1108 meant 17 call sites (1 production, 16 test). Enumerate before touching any, and check
   whether the corresponding `AskesisDeps` field then dies too.
5. **Watch for same-name decoys.** Two are already documented above (`ContextRelevanceEngine
   .graph_intel`, `TemplateBundle.events`). Confirm the class before believing a grep.

## Workflow

State worktree + branch at the start. Branch from updated `origin/main`. `./dev quality` **and**
`uv run pytest tests/unit` before push. Pre-push is BOTH `./dev format` and `uv run ruff check
--select I --fix`. **Every tool call goes through `uv run` or `./dev`** — bare `pytest`/`ruff` are
not on PATH on the dev machine. Summon Codex after the **final** push
(`scripts/request_codex_review.sh <PR#>`), verify the reviewed SHA equals HEAD, address or reject
findings **with the measurement**, then merge per standing authorization once the gates are green.

Ask if certainty is below the threshold to decide.
