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

### Building blocks: BOTH halves already have them (corrected)

⚠️ An earlier draft of this table claimed principles had *no* registry key and *no* persistence
support, and implied `get_practice_events` was an implemented-but-uncalled method. **Both claims
were wrong** — caught by Codex on #1110, and each would have biased the verdict: the first toward
"principles must be built from scratch" (deletion), the second toward "just add a caller" (which
crashes). The real edges are `SCHEDULES_EVENT` and `GUIDED_BY_PRINCIPLE`; searching for
`practice_events` / `practice_principles` found the *registry key names*, not the edges.

| | Edge, registered | Live persistence support | Direct consumer of the bundle field |
|---|---|---|---|
| **events** | `SCHEDULES_EVENT`, key `practice_events` | ✅ counted by `fetch_practice_counts` | ✅ `response_generator.py:307` |
| **principles** | `GUIDED_BY_PRINCIPLE`, key `principles`, `yaml_field_path="principle_uids"` | ✅ counted by `fetch_practice_counts` | ✗ indirect only |

`PsIntelligenceBackend.fetch_practice_counts` (`ps_intelligence_backend.py:135`) **already
traverses all six channels** — `BUILDS_HABIT`, `ASSIGNS_TASK`, `SCHEDULES_EVENT`, `SUPPORTS_GOAL`,
`GUIDED_BY_PRINCIPLE`, `INFORMS_CHOICE` — and returns per-domain counts. So the edges and the
vocabulary exist for both halves.

⚠️ **But "only a projection and a fetch are missing" is TOO STRONG — there are two authoring
paths, and the direct edges are only one of them** (Codex, #1110). Corrected:

| Path | How the PS reaches an activity | Projected today? |
|---|---|---|
| **Vault-authored** | direct edge — `BUILDS_HABIT` / `SCHEDULES_EVENT` / `GUIDED_BY_PRINCIPLE`, written from Edge-YAML via `yaml_field_path` (`habit_uids`, `principle_uids`, …) | habits + tasks only |
| **Template + spawn** | `(PS)-[:HAS_EVENT_TEMPLATE\|HAS_PRINCIPLE_TEMPLATE]->(*Template)`, then `_SpawnOrchestrator` writes `(instance)-[:SPAWNED_FROM]->(template)` + `source_path_step_uid` on the learner-owned instance | **no** |

A `SCHEDULES_EVENT` projection therefore populates the bundle **only for
directly-authored PathSteps** and returns empty for template-based ones — which
`CLAUDE.md` calls the current model ("Activity Templates — PS-owned, spawn instances on
engagement"). Any plan must either add the **student-scoped spawned-instance traversal**
(`source_path_step_uid` / `SPAWNED_FROM`, necessarily user-scoped since instances are
learner-owned) or state plainly that its payoff covers legacy directly-authored content only.

### ✅ PROBED 2026-08-21 (AuraDB `d2d160c4`) — this arc is CONTENT-GATED. Do not build yet.

Both authoring paths are **completely unused**:

| | count |
|---|---|
| `(:PathStep)-[:BUILDS_HABIT\|ASSIGNS_TASK\|SCHEDULES_EVENT\|GUIDED_BY_PRINCIPLE\|SUPPORTS_GOAL\|INFORMS_CHOICE]->()` | **0** |
| `(:PathStep)-[:HAS_*_TEMPLATE]->()` | **0** |
| `SPAWNED_FROM` edges | **0** |
| PathSteps / Kus | 25 / 124 |
| Tasks / Choices / Events / Habits / Goals / Principles that exist | 91 / 10 / 6 / 5 / 3 / 2 |

And **no vault file has ever declared** `habit_uids`, `task_uids`, `event_template_uids`,
`principle_uids`, `goal_uids` or `choice_uids`. **Never authored — not a broken pipeline.** The
activity entities exist; nothing has ever been linked to a PathStep by either route.

**What this overturns, including in this document:**

1. **The events-vs-principles asymmetry is illusory.** The Socratic practice list is empty for
   *everyone* — `bundle.habits` and `bundle.tasks` are as empty as `bundle.events`, so the
   ENCOURAGING prompt always renders *"No specific practice activities linked."* The payoff
   argument built on that asymmetry (below, and in the verdict section) **does not hold**.
2. **Options A and B both build machinery that stays empty** until content exists.
3. **One Path Forward does not force a choice** — neither path superseded the other, because
   neither has ever been used. The "two competing authoring models" framing is premature.

**Do this before writing any code:** author `habit_uids: [...]` on one PathStep in the vault,
sync, and check whether the tutor picks it up. One line of content proves Way 1 end-to-end. If it
works, this arc shrinks to "add the two missing channels the same way habits and tasks already
work". If it does not, the defect is in ingestion and this document is looking in the wrong place.

⚠️ A snapshot, not a constant. Re-run before acting if much time has passed.

*(Retained for context: every `BUILDS_HABIT` / `SCHEDULES_EVENT` occurrence in `core/services/`
and `adapters/persistence/` is a **read** — `OPTIONAL MATCH`, `WHERE exists(...)`. No service
writes them; they arrive only from vault ingestion. Which is consistent with the count of zero.)*

⚠️ **Do not plan to "give `get_practice_events` its caller" — it is a PHANTOM.**
`PsOperations` declares `get_practice_events` (`:768`), `get_practice_habits` (`:756`) and
`get_practice_tasks` (`:744`), and **none of the three is implemented anywhere** — the only hit
for each `def` is the protocol itself. A call routed through the protocol reaches
`UniversalNeo4jBackend.__getattr__`, which resolves only the four CRUD aliases and otherwise
**raises `AttributeError`** (`universal_backend.py:449`, fallback at `:474`). Populate the bundle
through the MEGA-QUERY projection, the way habits and tasks already are.

⚠️ **And note what that implies about protocol probes.** `__getattr__` is typed `-> Any`, so mypy
treats *every* attribute as present on `UniversalNeo4jBackend` subclasses. A clean
`x: PsOperations = PsBackend(...)` probe is therefore **not** evidence that the backend implements
the protocol's methods — three phantoms sit behind that green result. (#1107's ruling does not
rest on it; its evidence was the `PsService` census. But treat the probe as a direction check
only, never as an implementation check.)

**Events has a real, learner-visible consumer.** `response_generator._build_guided_practice`
(ENCOURAGING mode, `askesis_guided_practice` template) builds its practice list from
`bundle.habits`, `bundle.tasks` **and `bundle.events`**, so an always-empty events collection
means the Socratic prompt can never name an event as practice.

⚠️ **The probe settled this: it is NOT a gap a learner experiences today.** The asymmetry only
bites if habits and tasks populate, and they do not — all six channels are at zero. Every learner
already gets *"No specific practice activities linked."* Keep this paragraph as the description of
what the code *would* do once content exists; do not use it as a reason to build now.

**Principles has only indirect reach.** `PsBundle.get_all_uids()` / `get_all_titles()` include
both collections; `intent_classifier.py:291` consumes `get_all_titles()`. So empty principles
narrows what intent classification can match against — real, but a matching-recall effect rather
than visible content.

⚠️ **Same-name decoy, verified.** `ps_engagement/_template_bundle.py`, `_validator.py` and
`ps_engagement_service.py` all reference `bundle.events` / `bundle.principles` — those are
**`TemplateBundle`** (`EventTemplate` / `PrincipleTemplate`), a different class. They are **not**
evidence that `PsBundle`'s fields are consumed.

### The verdict here is Mike's

Plausible endings: **finish the wiring** (a MEGA-QUERY `graph_context` projection change, the
`total_practice_opportunities` fix, and a `_fetch_entities_by_uid` call per channel — *not* a new
`get_practice_*` caller) · **delete both halves** as an abandoned idea · **register as visible
backlog** and leave the code. Per the phase directive a feature-shaped answer gets *"not now" +
a named cost*.

Both halves have their edges registered and already counted by `fetch_practice_counts`, so
neither is built from scratch.

⚠️ **The probe removes the tiebreaker this section used to offer.** It said payoff favoured
events, because events has a direct consumer (the ENCOURAGING practice list) while principles
reaches only `get_all_titles()`. Both are true of the *code* and neither matters yet: with all six
channels at zero, neither half has a payoff today. **The honest recommendation is now: author one
line of content and re-decide.** Splitting events from principles remains available, but pick the
split on what you actually author, not on which consumer looks better on paper.

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
