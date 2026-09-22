---
title: "Symbol Claims in Docs — the queue, and the instrument that would order it"
updated: 2026-09-22
status: "waits on the instrument — the census is a gitignored prototype; the follow-on arc's PR 1 builds it"
registered: 2026-09-22
ruled: 2026-09-22
trigger: "Mike schedules the follow-on arc; its PR 1 builds the scanner, and only then is there a queue to sweep"
check: "unbuilt — the prototype's method is the spec, described below. Until it ships there is no re-measure command; `uv run python scripts/health/stale_names.py --list` is the confirmed-symbol half that already exists"
---

# Symbol Claims in Docs — the queue, and the instrument that would order it

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

**The class.** A live doc or skill that names a class, method, constant or dotted member that
does not exist in the tree — the symbol-shaped half of the fiction the route-claim scanner
proved absent for routes. It is the (b) queue of the docs de-fiction pass
([docs-defiction-pass.md](done/docs-defiction-pass.md) § 2 (b)), measured there and
deliberately not swept: the queue is roughly eight times the route queue and its precision
depends on the span-adjacent negation grammar the route scanner had to ratify on a smaller
corpus first.

## The instrument is not built — and that is the ruling

Building it is an M with its own review tail (the route scanner's PR took 18 Codex rounds and 39
findings, every one in the instrument), so it does not belong in the closing PR of the arc that
measured it. **Ruled 2026-09-22: register the queue with its method as the spec; the follow-on
arc's PR 1 builds the scanner.** The census that produced the numbers below was a
gitignored scratch prototype, deleted with the arc — reproducible from the description below,
which is the point of writing it here.

**The method, as the spec.** An AST symbol table over `core/ adapters/ ui/ services_bootstrap/
scripts/ tests/ main.py` — every `ClassDef`, `FunctionDef`, module-level and class-body
assignment, type alias and imported name — unioned with the `dir()` of the standard library and
the third-party modules the docs legitimately name (typing, dataclasses, pathlib, asyncio,
fasthtml, pydantic, starlette, neo4j). Claims are the inline code spans of the link checker's
corpus (`dead_doc_links.get_md_files()`, its carve-outs inherited), outside fenced blocks, in
four shapes: class (`CamelCase`), call (`name()`), dotted member (`Class.member`) and enum member
(`Class.MEMBER`), plus `ALL_CAPS` constants. A claim resolves or it does not; an unresolved one
is a finding only after the grammar below.

What PR 1 has to carry that the prototype does not:

- **The span-adjacent negation grammar and the history vocabulary, imported not copied.** Both
  already exist in `scripts/health/route_claims.py` and `scripts/history_in_code.py`. Two
  vocabularies for one idea drift apart; the route scanner ships one because of that.
- **A third vocabulary the route scanner never needed.** `ALL_CAPS` claims are half environment
  variable names (`OPENAI_API_KEY`, `INGESTION_PATH`) and Cypher keywords (`MATCH`, `FOREACH`) —
  neither is a Python symbol and neither is fiction.
- **Sentence mode, which symbol existence cannot see.** The prototype's own worst false positive:
  `HabitConsistencySignal` is honestly described as a proposal on every one of its mentions
  ([ADR-057](../decisions/ADR-057-activity-domain-sibling-signals.md), "design only"), so a
  `stale_names` entry for it would flag a doc for being right. This is the same false-positive
  class as planned-without-marker in the route scanner.
- **Positive controls in the test, not the script** — known-dead symbols must report, known-live
  ones must not. Two instrument defects shipped green in the route prototype before controls
  caught them.

## The five verdicts a confirmed claim takes

Swept in PR 5 of the de-fiction arc (#1388, nine symbols), and the reason a symbol scanner needs
a reader rather than an autofix. Establish which one with
`git log --all -S"<symbol>" --name-only --format="=== %h %s"` **and a positive control** — a
symbol you know exists, run the same way. A pathspec that matches nothing looks exactly like a
symbol that never existed, and below the squashed initial commit (`15e148778`) the probe has no
discriminating power at all: target and control both return that one commit, which is a bottomed-out
probe, not history. Three further traps, each of which has produced a published falsehood here: the
pathspec is not portable (`-- '*.py'` returns near-nothing for a symbol that lives in a `.js` file
and reads as confirmation); a working-tree grep answers *present*, never *ever*, so no grep licenses
the words "never existed"; and `-S` counts occurrences tree-wide, so a file MOVED into an archive
leaves the count unchanged and the commit that unwired the caller never appears in the log at all.
Grep the call form (`.method(`), not the name.

| Verdict | What the tree shows | Action |
|---|---|---|
| never existed | zero hits in `*.py` at any commit, control returns commits | delete the sentence |
| renamed | the successor is in the tree | repoint, present tense, and add a `RENAMED` entry |
| wired then removed | live at some commit, unwired later — often by a MOVE, which `-S` cannot see (use `--diff-filter=D --name-only`) | delete the section; check for staging before deleting the capability |
| fictional namespace, real members | the members shipped; the class around them never did (`UnifiedUserContext` is the module's name, not a class; `DomainConfig.cross_domain_relationship_types` is a real member of `DomainRelationshipConfig`) | repoint to the real namespace — spot-checking the member finds it and concludes the doc is right |
| honest proposal | every mention says it is unbuilt | leave it; it is not fiction |

## The regression half already exists

`scripts/health/stale_names.py` is the gate for a *confirmed* symbol: its `RENAMED` and `DELETED`
tables are scanned over docs, skills and CLAUDE.md on every `./dev health`, with a line-anchored,
count-pinned allowance tier for the places a retired name must appear. Every symbol a sweep
confirms becomes an entry there, so the sweep's output is durable with or without the scanner.
What `stale_names` cannot do is *find* the claims — it only knows the names it has been told.

## Two blind spots the arc measured, and neither scanner covers

Named as fact, not as a proposal to widen anything. Both were found by reading, not by an
instrument:

- **A README beside code is outside every docs scanner's scan dirs** — those are `docs/`,
  `.claude/skills/` and `CLAUDE.md`, so a README under `core/models/` or `scripts/` is read by
  whoever opens that package and by nothing else. The one README under `core/models/` — the
  Principle package's — was deleted in the arc's closing PR: 4 of 9 required-field rows named
  fields the model does not have, two enum lists were wrong, the uid example used the colon
  spelling retired 2026-08-14, and its one link had been dead since 2026-03-28 — untouched since
  the initial commit, cited by nothing.
- **Prose, as opposed to a code span, is invisible to `stale_names`** — it reads fenced blocks and
  backtick spans only, on purpose, so that a doc may narrate its past. A sentence that names a
  gone directory without backticks is read by no pass at all.
