# Substance-Write Grain — the `ku_uid` That May Not Be a Ku

*Live plan. Scheduled 2026-08-20. Case file for the register entry in
`deferred-work.md` § Substance-Write Grain; move to `docs/roadmap/done/` when nothing
in it remains open.*

Take the **Substance-Write Grain** item from `docs/roadmap/deferred-work.md`
(§ "the `ku_uid` That May Not Be a Ku", scheduled 2026-08-20). It carries item C of the
Backend-Typing Follow-on as its rider — the lying `ku_backend` fixture — and that pairing is
deliberate, not convenience.

Verified against `main` @ `372ec722a` on 2026-08-20. **Line refs drift and registers lie: re-run
every census yourself.** #1106 falsified its own register's premise, #1107 found the register
undercounted its consumers by two, #1108 corrected the same claim twice in one thread.

---

## The defect

This is follow-up #2 of the Ku-grain bridge arc (PR #247, 2026-06-06). #247 fixed the **read**
path — the MEGA-QUERY and ZPD roll-up now compose PathStep→Ku at read time. The **write** path
was left, and is still open.

⚠️ **Start by internalising that there are TWO writers to
`times_practiced_in_events`, not one.** This document's first draft conflated
them and Codex caught it on #1109 — the mistake is recorded because it is the
easiest one to repeat here. They fire on different triggers, carry different
field names, and only one attempts a roll-down:

| # | Trigger → path | Writer | Roll-down? |
|---|---|---|---|
| 1 | `CalendarEventCompleted` → `PsPracticeService` (`:146`) | `increment_practice_count` (`_adaptive_mixin.py:72`) — `MATCH (ku:Entity {uid})`, SET, done | **none at all** |
| 2 | event *created* w/ knowledge → `EventsService` → `KnowledgePracticedInEvent` → `PsService.handle_knowledge_practiced_in_event` | `increment_substance` (`curriculum_backends.py:242`) | present, inert at PathStep grain |

Both `SET` the **same property**. So a third question joins the list: is an event
that is created with knowledge *and* later completed **double-counted**? That is
independent of grain, and neither writer filters by type.

`KnowledgePracticed` (field **`ku_uid`**, not `knowledge_uid`) belongs to path 1
and is published *after* its counter is already incremented — a notification, not
the mechanism. `KnowledgePracticedInEvent` (field `knowledge_uid`) is the one the
`PsService` handler consumes, on path 2. **`test_event_ku_practice_flow.py`
covers path 1.**

Every site is grain-agnostic while *named* as if it were Ku-grain:

| Site | Says | Constrains to `:Ku`? |
|---|---|---|
| `_adaptive_mixin.py:67` (read) | `->(ku:Entity)`, `RETURN ku.uid AS ku_uid` | **no** |
| `_adaptive_mixin.py:77` (write, path 1) | `MATCH (ku:Entity {uid: $ku_uid})` | **no** |
| `ps_service.py:885–951` (8 handlers) | `ku_uid=` / `ku_uids=` | no |
| `curriculum_backends.py:242` (write, path 2) | `MATCH (ku:Entity {uid: $ku_uid})` | **no** |
| `test_event_ku_practice_flow.py:61` | fixture `ku_backend` | no (**is** a `PsBackend`) |

⚠️ **STOP — the premise this arc inherited is falsified. Read this before designing anything.**

Five Codex rounds on #1109 dismantled the original framing ("the write path leaves Ku-level
substance at 0"). Two independent reasons it cannot be right:

**1. `Ku` cannot hold substance, by design.** `Ku` extends `Entity`, *not* `Curriculum`
(`core/models/ku/ku.py:38`) — no `times_*` fields, no `is_well_practiced()`, and `KuDTO` drops
those properties. Its own docstring: *"Kus are lightweight ontology/reference nodes. They don't
carry full learning metadata (complexity, substance scores)."* So "Ku-level substance stays 0" is
the design, not a defect. `ku.is_well_practiced()` would raise `AttributeError`.

**2. The propagation runs UP, not down.** `OPTIONAL MATCH (ps:PathStep)-[:USES_KU|
CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku)` matches PathSteps that *use* the bound Ku — it credits a Ku's
**composing PathSteps**. Net effect of path 2:

| `$ku_uid` names… | primary SET | roll-up | readable counter | **returns** |
|---|---|---|---|---|
| `:Ku` **with** composing PathSteps | `ku.times_*` — unreadable | PathSteps credited | ✅ | real count |
| `:Ku` **orphan** (no `USES_KU` in) | `ku.times_*` — unreadable | none | ❌ **lost** | `ok(0)` |
| a `:PathStep` | `ps.times_*` — readable | none (nothing `USES_KU` a PathStep) | ✅ | `ok(0)` |

⚠️ **`WHERE ps IS NOT NULL` gates the `RETURN`, not just the second `SET`** — and that is the
strongest defect in this arc. The clause drops the whole row, so when no composing PathStep exists
the query emits **zero rows**, and `Result.ok(records[0][...] if records else 0)`
(`curriculum_backends.py:258`) reports **`ok(0)`** — a *success* claiming nothing was counted, for
a write that already landed. Two of the three cases hit it, including the PathStep case that is
otherwise correct. Callers cannot distinguish "incremented, unreportable" from "no-op".

⚠️ **The orphan row is not hypothetical.** Orphan Kus are a first-class tracked population —
`KnowledgeHealthService` scores `non_orphan_fraction` and flags them as an authoring-health signal
— so this is a live loss path, not a corner case. (Found by Codex on the 6th review round of
#1109, after an earlier draft of this table concluded "path 2 works". It does not.)

**What is actually left** — different from the inherited framing, and larger than it looked after
the falsification:

1. **The `WHERE ps IS NOT NULL` row-filter (strongest, and a real bug).** It gates the `RETURN`,
   so two of three cases report `ok(0)` for a write that landed. Fixing it is a small Cypher
   change — but decide deliberately whether the orphan-Ku case should also *credit* something or
   merely report honestly.
2. **Writer asymmetry.** Path 1 has **no roll-up at all**, so a real Ku uid there writes an
   unreadable property and credits no PathStep. ⚠️ The probe below shows real Ku uids *are* now
   the common case (28 of 32 edges), so this fires — but check whether path 1's trigger
   (`CalendarEventCompleted`) has any live traffic before ranking it: the hot channel is UserEntry.
3. **Possible double-count.** Both writers `SET` the same property on different triggers.
4. **Naming.** Every site says `ku_*` while PathStep is the readable grain — item C's fixture is
   the test-side face of this.
5. **Ku nodes accumulate properties nothing reads.** Cosmetic, or a cleanup — decide.

⚠️ **Method note for whoever takes this.** This register was wrong five times in a row while
being written *from measurements* — direction of a graph pattern, which model owns a field, which
service reads a counter, which bloat tier accepts a published event, which event carries which
field name. Every correction came from reading the actual definition rather than the surrounding
prose. Do that first, for every claim below, including the ones stated confidently. Path 1 has no roll-down to fail, so it lands wholly
on whichever node the uid names.

## Start here, before designing anything

### ✅ The probe has been run — 2026-08-21, AuraDB `d2d160c4`

The inherited June-2026 claim (*"all ~20 activity→knowledge edges target `path_step`, zero target
`:Ku`"*, measured on the old local Docker graph, pre-cutover) is **falsified**:

| Edge | count |
|---|---|
| `APPLIES_KNOWLEDGE` **user_entry → ku** | **28** |
| `REQUIRES_KNOWLEDGE` path_step → path_step | 2 |
| `REQUIRES_KNOWLEDGE` goal → path_step | 1 |
| `APPLIES_KNOWLEDGE` task → path_step | 1 |

**28 of 32 now target a real `:Ku`.** Two things follow, and both re-shape this arc:

1. **UserEntry → Ku is the dominant stored topology** (28 of 32 edges). ⚠️ That is a statement
   about what is *stored*, **not** about which handler executes most often — edge counts cannot
   establish frequency. The execution claim is made below, from counters, which is the evidence
   that actually supports it.
   ⚠️ **That channel has TWO writers, not one** — `UserEntryProcessingService`
   (`user_entry_processing_service.py:588-619`, explicit `@ku()` refs) and `EntryGroundingService`
   (`entry_grounding_service.py:287-314`, vector grounding). CLAUDE.md says so directly: *"two
   writers, one `KnowledgeReflectedInEntry` event"*. They have different idempotency behaviour.
   Scope the investigation to the channel, and break the 28 down by provenance before attributing
   anything to one service.
2. **The orphan-Ku case is live and is the majority case — measured by edges, not endpoints:**

| | edges | distinct Kus |
|---|---|---|
| target an **orphaned** Ku (no composing PathStep) | **17** | 9 |
| target a **composed** Ku | 11 | 8 |

⚠️ **What 17-of-28 (61%) is, and what it is NOT.** It is the **current orphan share of edges** — a
topology snapshot. It is **not** a write-loss rate and **not** evidence that this handler is hot,
because (a) `UserEntryProcessingService` publishes only for *newly created* links
(`:604-619`), so existing edges may predate that publisher entirely, and (b) a Ku orphaned today
may have been composed when its counter was incremented. **To size the defect properly, correlate
edge-creation / event history against composition state** — the snapshot cannot do it. What the
snapshot *does* establish is that the orphan case is common enough in the current topology that
any fix must handle it deliberately. Corpus-wide, 69 of 124 Kus (56%) are orphaned.

### Counter census — this IS execution evidence, unlike the edge counts

All five metrics enumerated from `_VALID_SUBSTANCE_METRICS` (`ps_service.py:77`), across **all**
entity types (not just Ku — an earlier pass checked only Kus):

| metric | Ku | PathStep |
|---|---|---|
| `times_reflected_in_entries` | **37** | **10** |
| `times_applied_in_tasks` | 1 | 2 |
| `times_built_into_habits` | 0 | 0 |
| `times_practiced_in_events` | **0** | **0** |
| `choices_informed_count` | 0 | 0 |

**Why this is execution evidence and the edge counts are not:** these counters are written only by
`increment_substance` / `increment_practice_count`, reached only from the substance handlers. No
ingestion path, script or migration writes them (checked). A non-zero value therefore *proves the
handler ran*.

So, soundly: **the reflection handler has demonstrably executed** (37 Kus + 10 PathSteps bear its
counter) and **the event and habit handlers have demonstrably never incremented anything, on any
entity type**. ⚠️ This establishes *past execution*, not current frequency — but it is enough to
say the two event writers this document opens with have never once fired, and to start elsewhere.

⚠️ **The 10 PathSteps do NOT prove the roll-up works — a draft claimed they did.**
`increment_substance` sets the counter on whatever `:Entity` the uid names, so a **PathStep-targeted
write** and a **Ku→PathStep roll-up** produce byte-identical state. Without event/edge history the
two are indistinguishable, and this graph *does* contain PathStep-targeted edges
(`APPLIES_KNOWLEDGE task → path_step`).

The snapshot can still **bound** it. Asking whether each counter-bearing PathStep composes a
counter-bearing Ku:

| | PathSteps |
|---|---|
| composes ≥1 counter-bearing Ku — **consistent with** roll-up | 9 |
| composes none — **must be** a direct write | **1** |

So at least one is definitely direct, and nine are *consistent with* roll-up without being proof
of it (a direct write to a PathStep that happens to compose a counter-bearing Ku looks identical).
**Do not use this to confine the defect to the orphaned half** — that needs the provenance
correlation, not the topology.

38 Kus carry some counter; **19 of them are orphaned** — accumulated substance the `Ku` model
cannot read, which credited no PathStep.

⚠️ **Three measurement corrections, worth copying as method** (all caught on #1111): a draft said
"53% of writes" while counting **distinct endpoints**; said "1 Ku has a counter" while querying
**2 of 4** fields; then said "the whole family" while querying **4 of 5** — missing
`choices_informed_count`. **Count the quantity you name. Derive the field list from the code
(`_VALID_SUBSTANCE_METRICS`) rather than typing it. And distinguish a topology snapshot from an
execution history.**

⚠️ A snapshot, not a constant — re-run if much time has passed. The point of the June example is
that a quoted number decays; this one will too.

Then answer, with measurements, before proposing a fix:

1. **Which grain actually flows today**, per channel — the 6 activity domains do not have to agree.
2. **Is the right fix at the write site or the read site?** #247 chose read-time composition
   deliberately, *below the hexagonal boundary, readers untouched*. A write-time fix that
   normalizes to Ku grain is the opposite choice and needs to justify itself against that
   precedent — including what happens to rows already written at PathStep grain.
3. **What does the counter mean at each grain?** A PathStep counter that moves and a Ku counter
   that does not may be defensible — "I practised this lesson" is a real fact. Decide whether the
   bug is the missing roll-down or the misleading parameter name, because those have different
   fixes and only one of them touches Cypher.
4. **Is any of this observable? — and mind which substance system you are in.** There are **two**,
   and they do not share a data path (this file's first draft named the wrong one; Codex caught it
   on #1109):

   - **Per-user, channel-map derived** — `PsIntelligenceService.calculate_user_substance` and
     `zpd_backend`. These read the user-context activity→Ku **channel maps**, *not* the node
     counters. This is the arm PR #247 fixed at read time. **Not affected by these writers.**
   - **Per-node, counter derived** — the `times_*` properties themselves, read by `Curriculum`
     model methods: `_calculate_substance_with_decay` (`core/models/curriculum.py:322`),
     `is_theoretical_only` (`:359`), `is_well_practiced` (`:363`), `needs_more_practice` (`:367`),
     `get_substantiation_gaps` (`:374`), `needs_review` (`:389`), `days_until_review_needed`
     (`:400`), `get_substantiation_summary` (`:431`). **This is the arm these writers feed.**

   ⚠️ Do **not** phrase the observable as "`pathstep.is_well_practiced()` true while
   `ku.is_well_practiced()` false" — an earlier draft did, and `Ku` has no such method
   (`AttributeError`). The comparison only exists between `Curriculum` subtypes. The real
   observable is whether a *given* PathStep's counter moved when the learner's activity should
   have credited it — which is what the writer-asymmetry question above actually tests. Trace who
   calls those eight model methods, and on which entity, before setting urgency.

## Adjacent, decide while you are in here

`KnowledgePracticed` (`knowledge.practiced`, published at `ps_practice_service.py:166`, path 1)
has **zero subscribers**. `./dev bloat` reports it at the informational tier — *"published but no
subscriber — fine if fire-and-forget"* — which is a judgment call nobody has made. Two honest
endings: **it earns a subscriber, or it goes** (with its publish site). Per the deletion protocol,
unwired → **ask Mike**; do not delete an event on your own authority.

⚠️ **`PLANNED_EVENTS` is not a third option here, and the tool will say so.**
`detect_bloat.py:1497` reports any *published* class found in `PLANNED_EVENTS` as
`planned-marking-stale` — that tier is for events **defined but never published**, i.e.
structurally dead staged code. `KnowledgePracticed` is published at `ps_practice_service.py:166`,
so registering it there would immediately be flagged. (An earlier draft of this file proposed
exactly that; Codex caught it on #1109.) If the decision is "fire-and-forget is fine", it needs
**no registration at all** — the detector already treats it as informational — only a sentence in
the event's docstring saying the call was made and by whom.

⚠️ **Do not read its docstring as design intent without checking.** It names two subscribers —
*"LearningAnalyticsService (track practice patterns)"* and *"SpacedRepetitionService (schedule
reviews)"* — and **neither class exists anywhere in the codebase**; the only file mentioning
either is `knowledge_substance_events.py` itself, 11 times across its docstrings
(`LearningAnalyticsService` ×7, `SpacedRepetitionService` ×2 among the "Subscribers:" lists).
Measured 2026-08-20. So the "Subscribers:" blocks in that file are aspirational in part and
accurate in part — `PsService` (×8), `TasksService` (×3), `HabitsService` (×2) are real. Sort
which is which before citing any of them, and apply the intent-vs-code discriminator: `git log -S`
on the class name distinguishes *never wired* (ask) from *orphaned* (delete). The register entry
for that discriminator is `docs/roadmap/deferred-work.md`; the arc that established it was
#1090–#1102.

## Sibling arc, do not conflate

`ContextRetriever` has its own unrelated write-only-field question (`graph_intel`,
`events_service`, `principles_service`) — different subsystem, different register entry. The only
thing they share is the AST sweep that found both. Do not merge the threads.

## The rider (item C)

`tests/integration/test_event_ku_practice_flow.py:61` — fixture named `ku_backend`, constructs a
`PsBackend`. Fix it **in this PR**, and fix it as part of the naming decision above rather than as
a local rename: it is the test-side instance of the same pattern the table shows. If the arc
concludes the parameters should say `entity_uid` (or stay `ku_uid` because the grain really is
Ku), the fixture follows that conclusion.

## Ground rules

1. **Investigate → verdict → Mike's ruling → implement.** The naming-vs-Cypher fork in question 3
   is a design decision, not yours. Present it with the measurement.
2. **All 8 handlers share the shape** — task, event, habit, entry, choice, plus 3 batch. Enumerate
   every site before fixing any; the last three PRs each got caught by a site found late.
3. **Seed-and-match is the proven test shape here.** #586 fixed the sibling defect and proved it
   5-fail-before / 6-pass-after by MERGEing the same edge the real writers write. The existing
   file is built that way — extend it, do not replace it.
4. **A test naming a field is not a reader.** If a counter is only ever asserted by a test that
   seeds it, that is evidence the production path is dead, not that it works (#1108's defect
   class).
5. **Integration tests here need Neo4j.** CI runs them on an ephemeral `neo4j:2026.06.0`
   testcontainer via path filters; mock-only tests hide phantom methods.

## Workflow

State worktree + branch at the start. Branch from updated `origin/main`. `./dev quality` **and**
`uv run pytest tests/unit` before push; run the integration file directly too (`uv run pytest
tests/integration/test_event_ku_practice_flow.py`), since that is the one this arc changes.
Pre-push is BOTH `./dev format` and `uv run ruff check --select I --fix`. **Every tool call goes
through `uv run` or `./dev`** — bare `pytest`/`ruff` are not on PATH on the dev machine, and where
they are, they resolve outside the locked environment. Summon Codex after
the **final** push (`scripts/request_codex_review.sh <PR#>`), verify the reviewed SHA equals HEAD,
address or reject findings **with the measurement**, then merge per standing authorization once
the gates are green. Close item C and this section in `deferred-work.md` in the same PR.

Ask if certainty is below the threshold to decide.
