---
title: "py314 Annotation Sweeps — UP037 Swept and Live, TC002/TC003 Never"
updated: 2026-09-16
status: "done — UP037 swept 2026-09-16 and live; TC002/TC003 permanently ignored (a ruling, not open work)"
registered: 2026-08-28
ruled: 2026-08-28
trigger: "none — the UP037 window was 2026-09-16; TC002/TC003 re-open only if ruff can name a local decorator as runtime-evaluated"
check: "uv run ruff check --select UP037 --statistics . | tail -3 → no UP037 row (the rule is live, so `uv run ruff check .` gates it); grep -n '\"TC002\"\\|\"TC003\"' pyproject.toml still in the ignore list, comment says PERMANENT; grep -c UP037 pyproject.toml's ignore list → 0"
---

# py314 Annotation Sweeps — UP037 Swept and Live, TC002/TC003 Never

*Completed record. This was the case file for a [deferred-work.md](../deferred-work.md) entry of
the same name; the entry left the MOC when the UP037 sweep landed in PR #PRNUM on 2026-09-16.
The rationale, the two dispositions and the measured baseline stay where they always lived —
[ADR-067 § "Deferred: TC/UP037 annotation-modernization sweep"](../../decisions/ADR-067-dependency-upgrade-policy.md).*

## What the sweep did

One mechanical PR in a merge lull (only Renovate dependency PRs open, both roadmap arcs closed):

- `uv run ruff check --select UP037 --fix .` on `78cef10f7` — **1244 sites in 315 files**
  (`core` 718, `ui` 248, `adapters` 150, `services_bootstrap` 82, `tests` 27, `scripts` 19), every
  one marked safe by ruff. The added-line audit found no change outside an annotation position —
  no `cast(...)`, no `TypeVar(bound=...)`, no alias assignment — which is the class of site where an
  unquoted `TYPE_CHECKING`-only name would raise immediately rather than on introspection.
- `uv run ruff format .` on the five files whose lines the shorter annotations let the formatter
  rejoin.
- `"UP037"` removed from `[tool.ruff.lint] ignore` — the rule is **live**, so a new quoted
  annotation is a lint error at `./dev quality`, not a boot-time surprise.
- `[tool.black] target-version` moved `py312` → `py314`. Its lag was documented as pinned to this
  sweep and had no other reason; nothing in `dev`, `scripts/`, CI or pre-commit invokes black, so
  the value is a statement of the syntax target, not a behaviour change.

## How it was verified — the check that COMPOSES the app

The ADR's hazard is that a quoted name imported only under `TYPE_CHECKING` is inert as a string
but, unquoted, raises `NameError` the moment something introspects the signature — and FastHTML
introspects every `@rt` handler at registration. So the verification had to reach registration:

- `./dev quality` — ruff, SKUEL lint, Cypher validation, the audits, MyPy **0 errors** (2222
  files), Pyright **0 errors**.
- `./dev test-unit` — exercises the other runtime introspection consumers
  (`get_type_hints` in `conversion_service`, `crud_queries`, `neo4j_mapper`; `__annotations__`
  in `form_generator`).
- `./dev test-integration` — its `skuel_app` fixture calls `bootstrap_skuel()`, the function
  `main()` runs, against a Neo4j testcontainer; that is the moment every handler signature is
  evaluated. RESULTS_PLACEHOLDER

## The residual ruling — TC002/TC003, never as a sweep

Unchanged and permanent (ruled 2026-08-28, ADR-067 § Deferred): moving an import under
`TYPE_CHECKING` is only safe where nothing evaluates the annotation at runtime, and the residue
ruff's `runtime-evaluated-base-classes` cannot see is exactly FastHTML's local `@rt` decorator plus
every `get_type_hints`-style consumer. Enable either rule only per file, after checking no
annotation in it is evaluated. This is a ruling with a stated re-open condition, not open work —
which is why the case file graduates rather than staying in the MOC for it.
