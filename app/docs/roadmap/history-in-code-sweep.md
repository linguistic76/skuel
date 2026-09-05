---
title: "History-in-Code Sweep — the finder is built, the sweep is the queue"
updated: 2026-09-05
status: "sweep queue"
registered: 2026-09-03
trigger: "ride-along on any PR that opens a listed file, or a dedicated small sweep when Mike schedules one"
check: "./dev history-in-code --top 20 --verbose — re-run, never paste"
---

# History-in-Code Sweep — the finder is built, the sweep is the queue

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

**The class.** A comment or docstring that narrates what the code used to do, which PR changed it
and when — a fix's story written into the code as proof of work, burying the rule the reader came
for. The rule stands once (CLAUDE.md § Docstring Philosophy · `DOCSTRING_STANDARDS.md`
Anti-Pattern 4 · AGENTS.md § Style, all #1243): present tense, no history; a pointer at the record
is fine, a retelling is not. The finder that measures it is `./dev history-in-code`
(`docs/tools/HISTORY_IN_CODE.md`): comments via `tokenize`, docstrings via `ast`, strings and log
messages unread; four signal categories (`pr_tag`, `pr_ref`, `date`, `phrase`), each ratified on
a hand-classified sample before it shipped. **Advisory by contract** — the signal arc's anti-goal:
never in `./dev quality`, pre-commit, `./dev health` or the janitor; exit 0 always. A prose lint is
itself noise and flow-blind; this is a census that orders a queue.

**Queue = `./dev history-in-code --top 20 --verbose`**, most hits first — re-run it, never work
from a pasted list. PR-sized slices like signal PR-C/D/E (#1239 / #1240 / #1241): one file, or one
coherent cluster across files, per PR. Each rewrite = the positive, present tense, plus a pointer
to the record; **the why is never deleted, only moved** — to the ADR, the `done/` doc or the commit
message. Drop a negative only once the positive stands beside it (the arc's per-site rule). Read
every hit: the known false positives — a date-typed field's format, a DSL example timestamp
(`activity_dsl_parser.py` is the exemplar), the lowercase "utilized" `used to`, an entity that
"was removed" at runtime — are reported on purpose and skipped on read. **There is no exemption
syntax to add**; a category measuring mostly false positives is dropped from the finder, not
annotated in the code.

**Measured 2026-09-03** (first run, on `ac1450beb` + the finder — the row's cell below carries the
re-measure command): `core/` 526 lines in 187 files of 782 scanned (pr_tag 11 · pr_ref 151 · date 227
· phrase 162); default scope (`core/ adapters/ ui/ services_bootstrap/`) 755 lines in 283 files of
1282 scanned. The #1243 grep baseline (385 / 149 with a PR# or date; 164 with four phrases) read
strings too and cast a narrower phrase net, so the two are not the same measure — the finder's
own first run is the baseline the sweep is judged against. Heaviest files on `core/`:
`tasks_core_service.py` 19, `search_router.py` 17, `activity_dsl_parser.py` 13 (10 of them
example dates), `ingestion_tracker.py` 12 — the queue's head.

Not registered in `detect_bloat.py` — a script is outside bloat scope. `docs/tools/HEALTH_CHECKS.md`
gains no line: the finder is not a health check and not in the janitor, by the anti-goal.
