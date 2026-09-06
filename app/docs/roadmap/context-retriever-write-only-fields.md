---
title: "ContextRetriever's Three Write-Only Fields"
updated: 2026-09-06
status: "open — events/principles half"
registered: 2026-08-20
ruled: 2026-08-21
trigger: "the Askesis arc completes the events/principles projection + bundle fetch"
check: "load_ps_bundle still hardcodes events = [] / principles = [] in core/services/askesis/context_retriever.py"
---

# ContextRetriever's Three Write-Only Fields

*Live plan. Registered 2026-08-20. Case file for the `deferred-work.md` entry of the same name;
move to `docs/roadmap/done/` when nothing in it remains open.*

`ContextRetriever` (`core/services/askesis/context_retriever.py`) assigned three `self.*` fields
that nothing reads. Surfaced by the AST sweep in PR #1108 and deliberately left there, because
they are **not** the case that PR was closing (write-only *deps copies*, all superseded).
**Case A (`graph_intel`) is now executed — deleted 2026-08-21.** Case B remains open below: its
P1 disclosure is CLOSED (ADR-085 G1+G2, the ownership bundle, 2026-08-21); what remains is the
events/principles projection + bundle fetch (the Askesis arc) and the templates-vs-activities
authoring question, with the `event_template_uids` rename HELD until that is settled.

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

## Case A — `graph_intel` ✅ EXECUTED 2026-08-21 — superseded, deleted

Zero reads inside the class. Zero reads repo-wide. Yet the constructor still took it (`:148`),
the Args docstring still described it (`:174`), and the class docstring still asserted **"Requires
GraphIntelligenceService for graph queries."**

**The supersession hypothesis is CONFIRMED and dated**: `git log -S` landed on `e4ac7a9ed`
(2026-03-26, *"refactor: migrate inline Cypher from services to backends"*), whose message names
the replacement outright — *"ContextRetriever: use backend methods instead of
graph_intel.execute_query()"* — and whose diff removes every `self.graph_intel` read plus the
`@requires_graph_intelligence` decorators. **Superseded → delete**, per protocol; no ask needed.

Deleted: the field, the constructor param, both docstring claims, 1 production call site
(`askesis_service.py`), 18 test sites across 3 files, and the tests' `_make_graph_intel` helper.
`AskesisDeps.graph_intel` **stays** — `ContextRelevanceEngine` reads it live (the decoy below).

**Rider — `QueryProcessor.graph_intel` was the same residue class and went in the same PR.** The
AST sweep on it: dead = `{graph_intel}` exactly. Its last read (a None-guard) was deleted in
`e782e74f1` (*"remove backwards compatibility from Askesis"*). Same treatment: param + field +
docstring + TYPE_CHECKING import + 1 production site + 2 test sites. It was outside this doc's
register only because the #1108 sweep ran solely on `ContextRetriever` — sweep the sibling
classes before assuming a register is complete.

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

### ✅ PROBED 2026-08-21 (AuraDB `d2d160c4`) — was content-gated; **resolved below**

At probe time both authoring paths were **completely unused**:

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

### ✅ THE TEST HAS BEEN RUN — 2026-08-21. **Way 1 works. This arc is now Option A.**

The paragraph above prescribed one authored line; it was run on Mike's instruction. Paired on
meaning rather than convenience — *"Managing Your Reactions"* ↔ *"Pause and Name One Reaction"*:

```yaml
# 0vault/Ps/Ps_dev/ps_managing-your-reactions.md
habit_uids:
  - habit.pause-and-name
```

Ingested through the **single-file** door (`UnifiedIngestionService.ingest_file`), deliberately
**not** `ingest_directory` — a directory run propagates deletions, and that is not a risk worth
taking on the live graph to test one line.

| step | outcome |
|---|---|
| ingest | `success: True`, `relationships_created: 1` |
| edge in graph | `(ps.self-management.managing-your-reactions)-[:BUILDS_HABIT]->(habit.pause-and-name)` ✅ |
| MEGA-QUERY projection — `user_context_queries.py:829` pattern run verbatim | `practice_habits: [{uid: habit.pause-and-name, title: "Pause and Name One Reaction"}]` ✅ |

**The vault → ingestion → graph → `graph_context` path is intact.** It had simply never been
exercised. The table above becomes `BUILDS_HABIT` **1**; every other channel is still 0.

⚠️ **Exactly what is proven, and what is not** — stated in the discipline this document's
governing caveat demands. **Proven by direct observation:** the edge exists, and the MEGA-QUERY's
own `practice_habits` pattern returns it. **Not run:** a live Askesis session.
`load_ps_bundle` is user-scoped (it walks `active_path_steps_rich`), so observing it in the tutor
requires that PathStep to be active for a user. That is user state; no part of the plumbing
remains in doubt.

### ✅ P1 — RESOLVED BY THE OWNERSHIP BUNDLE (ADR-085, PR-3, 2026-08-21); was: OPTION A BLOCKED ON AN OWNERSHIP RULING

> Status: the cross-user disclosure mechanism described below is CLOSED — see
> the un-suspended verdict at the end of this entry. The findings below are the
> 2026-08-21 investigation record (file:lines as of that date); the open
> remainder is the templates-vs-activities authoring question and the
> events/principles projection completion (Askesis arc).

**A shared PathStep pointing at a user-owned activity crosses an ownership boundary.** Verified at
every link:

| link | verified |
|---|---|
| `Habit` / `Event` are `UserOwnedEntity` (OWNER_ONLY domains) | CLAUDE.md § Ownership Verification |
| vault-authored activities are stamped with the vault owner | `habit.pause-and-name` and `event.evening-check-in` both carry `user_uid=user_admin` **and** a `(user_admin)-[:OWNS]->` edge |
| the MEGA-QUERY projection has **no owner predicate** | `user_context_queries.py:829` — `OPTIONAL MATCH (ps)-[:BUILDS_HABIT]->(ps_habit:Habit)` |
| the bundle fetch is **unscoped** | `_fetch_entities_by_uid` → `service.get(uid)` → `CrudOperationsMixin.get` (`:135`) takes **no `user_uid` and performs no ownership check**) |
| the value reaches a prompt | `response_generator._build_guided_practice` renders `f"Habit: {habit.title}"` |

So when that PathStep is active for **any learner other than the vault owner**, the owner's
user-owned habit lands in that learner's `PsBundle` and Socratic prompt. Curriculum is SHARED;
activities are USER_OWNED; a direct edge between them has no scoping anywhere along the path.

⚠️ **This is the first instance in the graph, and this arc's own test created it.** Low
sensitivity (a curriculum-flavoured habit title, owned by `user_admin`) — but it is the mechanism
that matters, and building the events projection would multiply it.

**And it reframes the whole Way-1-vs-Way-2 question.** The template + spawn model exists to give
each learner *their own* instance — which is precisely the boundary a direct edge violates. Way 2
may be architecturally right after all, rather than dead.

**✅ RULED (Mike, 2026-08-21) — the vault ROOT decides ownership.**
`/home/mike/0bsidian/0vault` (`INGESTION_PATH`) is **shared curriculum**;
`/home/mike/0bsidian/skuel` (`VAULT_ROOT`) is **user-owned**. So content-vault activities are
shared curriculum, and **the `user_uid=user_admin` + `:OWNS` stamp on them is the bug** — not the
direct-edge model. Way 2 is **not** forced; Option A is architecturally sound.

⚠️ **Cause — an earlier draft blamed `default_user_uid`, and that is WRONG** (Codex, #1112).
Production installs a `VaultRegistry` (`compose.py:1433-1455`) and `_resolve_owner`
(`unified_ingestion_service.py:351-371`) resolves content-vault paths to the content descriptor's
**acts-as owner**. The two vault doors are already distinguished; changing `DEFAULT_USER_UID`
would change nothing.

**The ingestion layer already does the right thing** — its docstring: *"Only `requires_user_uid`
entity types actually persist this owner; SHARED curriculum drops it."* Measured: `HABIT` /
`EVENT` / `PRINCIPLE` → `requires_user_uid=True`; `HABIT_TEMPLATE` / `EVENT_TEMPLATE` /
`PATH_STEP` → `False`. The owner is persisted **because the entity type demands it**, not because
a default leaked. **The actionable cause is the type choice** — a USER_CREATED activity type
authored where a curriculum template is required, which is the finding below reached from the
other direction.

So the P1 is a **known-cause bug, not an open design question**. What still needs deciding is the
general one it shares with three sibling entries in `deferred-work.md`: what enforces ownership on
a read that does not pass through SearchRouter?

### 🔑 But the type system already answers this, and its answer is TEMPLATES

Measured 2026-08-21 via `EntityType.<T>.content_origin()`:

| entity | `content_origin` |
|---|---|
| `Habit` / `Event` / `Principle` | **`user_created`** |
| `HabitTemplate` / `EventTemplate` / `PrincipleTemplate` | **`curriculum`** |

So **"a shared curriculum Habit" is not representable — by design.** The
curriculum-side representation of an activity *is* the Template (CLAUDE.md's
tier B). Combined with Mike's ruling that `0vault` is shared curriculum, it
follows that **content-vault activity files are authoring the wrong entity
type**: they should be `HabitTemplate` / `EventTemplate` / `PrincipleTemplate`,
not `Habit` / `Event` / `Principle`.

Which reframes the P1's root cause once more: the direct-edge channels point
**curriculum at user-owned instances** — that is the boundary violation — while
the template channels (`HAS_HABIT_TEMPLATE` → `HabitTemplate`) point curriculum
at curriculum and violate nothing. ⚠️ **Way 2 may be right after all**, for a
type-system reason rather than the ownership one.

⚠️ **And here is the actual gap: neither path is currently usable.**

- The **correct** entity type (Template) is **not vault-ingestible** — no
  reference to any `*Template` class exists under `core/services/ingestion/`
  (verified). It can only be created through the PathStep template routes in the
  app.
- The **authorable** entity type (Activity, via `habit_uids` etc.) is
  user-created and crosses the ownership boundary.

So a content author cannot currently express "this lesson has this practice" in
the vault without authoring a user-owned entity. **That is the design question
for the fresh context** — bigger than the four ownership entries, and upstream of
them.

**The question, in plain terms** (the first framing was too abstract to answer —
Mike said so, fairly). *When you write a lesson in the vault and want to say
"practise this by doing X", what should X be?*

| | X is a **Template** | X is an **Activity** (today's fields) |
|---|---|---|
| what it means | a curriculum-owned *pattern* — "a 2-min evening check-in". On engagement the app spawns **the learner's own copy** | the lesson points at **one real Habit/Event** that belongs to somebody |
| ownership | shared → shared; no boundary crossed | shared → user-owned; **every learner sees the author's item** (the P1) |
| type system | `*Template` is `content_origin=curriculum`, `requires_user_uid=False` ✅ | activities are `user_created`, `requires_user_uid=True` ✗ |
| works today? | **no** — templates are not vault-ingestible at all | yes, and that is how the P1 arose |

**Mike's leaning (2026-08-21): make Templates vault-ingestible** — *"Templates are
a basic part of this app and must be easy to use and understand."* ⚠️ Recorded as
a **leaning, not a ruling**: Mike said the question as first put to him was
unclear, so the fresh context should re-put it using the table above and confirm
before building. The leaning is well-aligned — templates are already the app's
stated model (CLAUDE.md: *"Activity Templates — PS-owned, spawn instances on
engagement"*) — but it implies real work: a new vault ingestion path for six
template types.

**✅ Ruled firmly (Mike, 2026-08-21): HOLD the `event_template_uids` → `event_uids`
rename** until this is settled. That rename was ruled on the framing "the
behaviour is right, the label lies". If the answer is Templates, the label was
right and the **target** is wrong — the option that ruling rejected. Do not
rename toward a model we may be leaving.

**✅ HOLD RELEASED, rename EXECUTED 2026-09-05** — the templates question was
settled on 2026-09-05 (templates are vault-authored; see
[activity-templates-vault-door.md](done/activity-templates-vault-door.md)), and it
settled in the direction that makes the rename *required*, not merely tidy: the
template door registers `HAS_EVENT_TEMPLATE` under `event_template_uids`, and
`generate_ingestion_relationship_config` keys on `yaml_field_path`, so the two
channels could not share the name. `SCHEDULES_EVENT` → `:Event` is now
`event_uids`; `event_template_uids` targets `:EventTemplate`, which is what an
author reading the name expects. Both halves of the hazard below are closed.

⚠️ Not established, and worth checking before acting: whether the direct-edge
channels were *intended* for something else (a teacher linking a PathStep to a
real personal habit as an exemplar), which would make them correct-but-misused
rather than wrong.

⚠️ **This is the read-side facet of a question three other `deferred-work.md`
entries circled** (Mike, 2026-08-21). The root: **ownership is declared in three
places — the `user_uid` property, the `(User)-[:OWNS]->` edge, and DomainConfig's
`SearchVisibility` — and enforced in one**, `build_search_visibility_clause`,
"the one Cypher composition point" (CLAUDE.md § Ownership Scoping). The Askesis
bundle never reaches it: `context_retriever.py` references neither
`SearchVisibility` nor that clause, and reads entities directly through
`service.get()`, bypassing SearchRouter.

The other three facets were `deferred-work.md` entries until their closure record was archived
to `docs/roadmap/done/ownership-bundle.md`; the table below now cites that record.

| facet | where it landed |
|---|---|
| write-side (`:OWNS` writers that skipped `user_uid`) | ✅ RESOLVED — ADR-086 + bundle PR-2 residue collapse: paper channel deleted, attendee triple retargeted onto consent-carrying `ATTENDS`. See `done/ownership-bundle.md` § 1 |
| declaration-side (`GroupService` declared `OWNER_ONLY` on a model with no `user_uid`) | ✅ RESOLVED — bundle PR-4: `DomainConfig.ownership_property`, Group declares `owner_uid`, guard test tightened to the declaration. See `done/ownership-bundle.md` § 3 |
| index-side (`User.uid` had no index or constraint) | ✅ RESOLVED — bundle PR-4: `User_uid_unique` uniqueness constraint via startup DDL, applied live + `NodeUniqueIndexSeek` confirmed. See `done/ownership-bundle.md` § 2 |
| **this P1** | **read-side** — ✅ RESOLVED (ADR-085 G1+G2, bundle PR-3: `_fetch_entities_by_uid` reads through `get_visible_to_user`, and the MEGA-QUERY habit/task projections carry `user_uid = user.uid`) |

**Ruled 2026-08-21 (Mike): this is significant cross-cutting work and belongs to
a fresh context, taken with the other three facets together rather than as four
separate fixes** — which is how the ownership bundle was in fact taken. Whoever
takes it should settle the general question — *what enforces ownership on a read
that does not go through SearchRouter?* — before touching any single site.
⚠️ `CrudOperationsMixin.get` (`:135`) is used by every domain; changing its
signature is a repo-wide change, not a local one.

**✅ That ruling landed — ADR-085 (the read-enforcement contract, bundle PR-1),
and the mechanism is CLOSED (bundle PR-3, 2026-08-21):** two chokepoints, one
floor; `get_visible_to_user` promoted to THE audience-aware by-UID read (now a
`BaseService` method); bare `get()` stays unscoped with §3 legality rules —
`CrudOperationsMixin.get`'s signature was indeed left alone. This entry's two
disclosure paths are both shut: `_fetch_entities_by_uid` threads `user_uid` and
reads through `get_visible_to_user` (G1), and the MEGA-QUERY `practice_habits`/
`practice_tasks` projections re-tie to the anchored user (G2) — the vault-stamped
`user_admin` habit no longer reaches another learner's bundle OR their rich
context. The verdict below is therefore UN-SUSPENDED.

---

**Verdict — Option A in shape, but ⚠️ the test does NOT generalize to events.** (The P1 above
is closed; nothing here is suspended.) The arc is no
longer "which of two authoring models should the tutor see?": Way 2 (templates + spawn) stays
entirely unused and needs no decision, and the projection + `_fetch_entities_by_uid` +
`total_practice_opportunities` shape is right. ⚠️ Populate through the projection — **never** by
giving the phantom `get_practice_events` a caller.

⚠️ **But `habit_uids` is the most permissive of the six channels, and I generalized from it**
(caught by Codex on #1112). The PathStep activity block's target labels are not uniform:

| vault field | edge | target label |
|---|---|---|
| `habit_uids` | `BUILDS_HABIT` | `:Entity` ← **the one tested** |
| `choice_uids` | `INFORMS_CHOICE` | `:Entity` |
| `task_uids` | `ASSIGNS_TASK` | `:Task` |
| `goal_uids` | `SUPPORTS_GOAL` | `:Goal` |
| `principle_uids` | `GUIDED_BY_PRINCIPLE` | `:Principle` |
| **`event_template_uids`** | `SCHEDULES_EVENT` | **`:Event`** |

`:Entity` matches every domain node, so the habit test cleared the lowest bar available. ⚠️ *At
the time this table was written* the strict targets were untested — **both have since been tested
and pass** (`:Event` and `:Principle`, below). `:Task` and `:Goal` remain untested, and no longer
matter for this arc: `PsBundle` has no goals or choices field, so only habits, tasks, events and
principles are in scope, and tasks share the already-working `practice_tasks` projection.

**The events channel carries a specific, named hazard.** Its vault field is
`event_template_uids` but its target is `:Event` — an *instance* label. `EventTemplate` nodes
carry `NeoLabel.EVENT_TEMPLATE` (`"EventTemplate"`), so an author following the field name to an
`EventTemplate` uid **matches nothing**. Meanwhile the live template path
(`ps_engagement/_template_loader.py:64-70`) uses `HAS_EVENT_TEMPLATE` → `EventTemplate` — a
different edge entirely.

### ✅ EVENT TEST RUN — 2026-08-21. The strict-target channel works too.

Run on Mike's instruction, on the one vault-authored event (the other five `:Event` nodes are a
user's real calendar, not curriculum). Paired on meaning again — *"Noticing Your Patterns"*
(objective: *"practice the 'pause and name' technique for real-time self-observation"*) ↔ a daily
2-minute evening reflection:

```yaml
# 0vault/Ps/Ps_dev/ps_noticing-patterns.md
event_template_uids:
  - event.evening-check-in
```

| step | outcome |
|---|---|
| ingest (`ingest_file`) | `success: True`, `relationships_created: 1` |
| edge in graph | `(ps.self-reflection.noticing-patterns)-[:SCHEDULES_EVENT]->(event.evening-check-in)` ✅ |
| `practice_events` projection (`OPTIONAL MATCH (ps)-[:SCHEDULES_EVENT]->(ev:Event)`) | `[{uid: event.evening-check-in, title: "Evening Check-In — 2 min"}]` ✅ |

**So the strict `:Event` target works when pointed at an Event instance** — the mechanism is
sound for both permissive (`:Entity`) and strict (`:Event`) targets. Graph now: `BUILDS_HABIT` 1,
`SCHEDULES_EVENT` 1.

⚠️ **The hazard is confirmed as purely a NAMING hazard, and it survives the test.**
`event_template_uids` needs an **Event instance** uid; an author following the field name to an
`EventTemplate` matches nothing. That mistake is currently *impossible to make* — there are **zero
`:EventTemplate` nodes** — but it becomes live the moment anyone creates one through the PathStep
template routes.

**✅ RENAME EXECUTED (2026-09-05, with the template vault door).**

Mike first ruled *rename to `event_uids`*, on the framing "the behaviour is proven correct — it is
the label that lies", with retargeting the edge at `EventTemplate` rejected. **He then held it**
once the type-system finding landed: if the answer is Templates, the label was right all along and
the **target** is wrong — the option that ruling rejected.

The templates answer resolved it without either horn: **both channels are real**, so the instance
channel keeps its proven behaviour under an honest name (`event_uids`) and the template channel
takes the name that describes it (`event_template_uids` → `:EventTemplate`). The naming hazard is
gone in both directions — a uid followed from either field now lands on the label the field names.

Scope, as measured and as executed: `yaml_field_path` in `relationship_registry.py`, one test
(`test_ingestion_edge_and_wiring.py`), three authoring docs (`CURRICULUM_DEVELOPER_GUIDE.md`,
`UNIFIED_INGESTION_GUIDE.md`, `yaml-to-graph.md`), a **regenerated**
`docs/reference/GRAPH_CONTRACT.yaml` (drift-tested — run `scripts/generate_graph_contract.py`,
never hand-edit), and the one vault file using it. Clean rename, no alias, no deprecation
(One Path Forward). The measurement held: nothing outside that list needed touching.

⚠️ Two things that make it smaller than it looks, both verified: the raw frontmatter key **does
not persist as a node property**, so no data migration is owed; and it is **not a PathStep model
field**, despite `yaml-to-graph.md:151` listing it as one — a doc error to fix in the same pass.

### ✅ PRINCIPLE TEST RUN — 2026-08-21. All three target classes now verified.

Mike asked for the same treatment on principles. `principle_uids:
[principle.observation-before-action]` added to the same PathStep (*"Noticing Your Patterns"* ↔
*"Observation Before Action"* — its first learning objective is *"distinguish between experiencing
a reaction and observing it"*). Ingested single-file; `GUIDED_BY_PRINCIPLE` edge landed against
the strict `:Principle` target.

**All three target classes are now proven for the correct-type case:** `:Entity` (habits),
`:Event`, `:Principle`. Graph: `BUILDS_HABIT` 1, `SCHEDULES_EVENT` 1, `GUIDED_BY_PRINCIPLE` 1.

⚠️ **But "nothing remains untested" was wrong — the WRONG-type case is open, and habits is the
one channel exposed to it** (Codex, #1112). Writer and reader disagree only there:

| channel | writer accepts | reader requires | |
|---|---|---|---|
| `BUILDS_HABIT` | **`:Entity`** — any entity at all | **`:Habit`** (`user_context_queries.py:829`) | ⚠️ **mismatch** |
| `ASSIGNS_TASK` | `:Task` | `:Task` (`:843`) | agree |
| `SCHEDULES_EVENT` | `:Event` | *(no reader yet)* | — |
| `GUIDED_BY_PRINCIPLE` | `:Principle` | *(no reader yet)* | — |

So `habit_uids: [task.something]` — a typo or a wrong-type paste — **creates a `BUILDS_HABIT`
edge and is then silently ignored by the projection.** The pre-ingestion validator cannot catch
it either: it validates against the declared target, `:Entity`, which matches everything. That is
the SKUEL030 class (a name that matches zero rows instead of erroring), and it makes the
*permissive* channel the **riskiest to author**, not the safest — the opposite of how the habit
test was first framed.

**Not tested here deliberately:** a wrong-type authoring test would put a junk edge in the live
graph, and the code reading is decisive without it. **Fix option for whoever takes this:** change
`BUILDS_HABIT`'s declared target from `Entity` to `Habit` so writer and reader agree and the
validator can reject. ⚠️ Check first whether the permissive target was deliberate — habits are the
one channel where a PathStep might legitimately point at something broader.

⚠️ **The two halves are gated on DIFFERENT things — do not lump them as "content-gated."** After
both authoring tests, the state per `PsBundle` channel is:

| channel | content authored | `graph_context` projection | `load_ps_bundle` fetch | tutor sees it? |
|---|---|---|---|---|
| **habits** | ✅ 1 edge | ✅ exists | ✅ `_fetch_entities_by_uid` | **yes** — end-to-end today |
| **tasks** | none | ✅ exists | ✅ | needs content only |
| **events** | ✅ 1 edge | ❌ **missing** | ❌ **hardcoded `[]`** (`:505`) | **CODE-GATED — build this** |
| **principles** | ✅ 1 edge | ❌ **missing** | ❌ **hardcoded `[]`** (`:506`) | **CODE-GATED — same as events** |

**Events is now code-gated, not content-gated** — the edge exists and is queryable. ⚠️ But it takes
**both** halves of the change, not just the projection: `load_ps_bundle` hardcodes
`events: list[Any] = []` at `context_retriever.py:505`, so a `practice_events` projection alone
would still yield an empty bundle. Projection **and** the `_fetch_entities_by_uid` call are one
change, and only together do they produce the payoff — the ENCOURAGING prompt naming *"Evening
Check-In — 2 min"* on that PathStep. (An earlier draft promised that from the projection alone,
contradicting the complete remedy stated further down this file.) ⚠️ **Principles is now code-gated too**, not content-gated — the principle test below authored
`GUIDED_BY_PRINCIPLE`, so it needs exactly what events needs: projection + bundle fetch. Both
channels are now in the same state; neither is waiting on content.

⚠️ An earlier draft of this section said "one habit edge exists; the other five channels have
none" — written *after* the event was authored, and it would have wrongly deferred the very wiring
this verdict asks for (caught by Codex on #1112). ⚠️ **And then made the identical mistake one
round later for principles** — authored the edge, left the table saying it had no content. Both
channels now have content and both need projection + fetch, so **build them together**; there is
no sequencing argument left between them.

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

### Verdict — Option A in shape (2026-08-21); events half still open

**Finish the wiring**, the way habits and tasks already work: a MEGA-QUERY `graph_context`
projection per channel, a `_fetch_entities_by_uid` call per channel, and the
`total_practice_opportunities` fix. ⚠️ *Not* a new `get_practice_*` caller — those are phantoms.

The other endings are closed. **Delete both halves** is refuted: the path demonstrably works, and
the fields are the injected half of a route that now has a live edge through it. **Two competing
authoring models** was never the situation: Way 2 (templates + spawn) has zero edges and zero
spawned instances, so nothing superseded anything.

Both halves have their edges registered and already counted by `fetch_practice_counts`, so
neither is built from scratch.

The events/principles projection completion stays with the **Askesis arc**, not the ownership
bundle — new channels inherit the G1/G2 scoping by construction (the fetch helper requires
`user_uid`; a new projection copies the owner-predicate shape).

⚠️ **Do not re-litigate the events-vs-principles tiebreaker on consumer strength.** An early draft
argued payoff favoured events (a direct ENCOURAGING-prompt consumer) over principles (only
`get_all_titles()`). That is true of the *code* and was never the deciding factor — with the
channels near-empty, payoff follows **what gets authored**. Split them if you like, but split on
content, not on which consumer reads better on paper.

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
