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

**State the failure mode correctly** — the memory this came from says "increments wrong/no node",
and that is not what the Cypher does. `increment_substance` (path 2) matches the base `:Entity`
label, so a PathStep uid *does* match and increments **the PathStep's own** counter. The roll-down
that follows — `OPTIONAL MATCH (ps:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku)` — then
finds nothing, because a PathStep is not the USES_KU target of another PathStep. Not a no-op: a
roll-**down that never happens**. Ku-level substance stays 0 for any channel authored at PathStep
grain, while the PathStep's own counter moves. Path 1 has no roll-down to fail, so it lands wholly
on whichever node the uid names.

## Start here, before designing anything

⚠️ **Re-probe the live edge grain.** The claim "all ~20 activity→knowledge edges target
`entity_type='path_step'`, zero target `:Ku`" is from **June 2026 on the old local Docker graph**
— it predates the AuraDB cutover (2026-08-15). The daily graph is now AuraDB Free `d2d160c4`. If
the grain has changed, the fix changes with it. **Do not quote that number; re-run it.**

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
4. **Is any of this observable?** Substance feeds `calculate_user_substance` and ZPD. If the Ku
   arm has been 0 since the feature shipped, say so plainly — it changes how urgent this is and
   whether a migration is owed for historical rows.

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
`pytest tests/unit` before push; run the integration file directly too, since that is the one this
arc changes. Pre-push is BOTH `./dev format` and `ruff check --select I --fix`. Summon Codex after
the **final** push (`scripts/request_codex_review.sh <PR#>`), verify the reviewed SHA equals HEAD,
address or reject findings **with the measurement**, then merge per standing authorization once
the gates are green. Close item C and this section in `deferred-work.md` in the same PR.

Ask if certainty is below the threshold to decide.
