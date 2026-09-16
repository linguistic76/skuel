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
the same name; the entry left the MOC when the UP037 sweep landed in PR #1347 on 2026-09-16.
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

## How it was verified — the check that COMPOSES the app, and what it caught

The ADR's hazard is that a quoted name imported only under `TYPE_CHECKING` is inert as a string
but, unquoted, raises `NameError` the moment something reads the signature in 3.14's default
VALUE format. A static pass over the swept files found **249** now carrying such a name unquoted
— most of the sweep — so the question was never *whether* the class exists but *who reads*:

- **`./dev test-integration` — the boot check — fired.** Its `skuel_app` fixture calls
  `bootstrap_skuel()`, the function `main()` runs, against a Neo4j testcontainer, in FULL tier
  (`.env`), so every handler registers. First run: 1769 passed, **12 errors**, all twelve the
  fixture itself — `RuntimeError: SKUEL bootstrap failed: name 'FT' is not defined` from
  `adapters/inbound/activity_reports_ui.py`. The reasoning that said this could not happen was
  wrong in a specific way worth keeping: FastHTML's `@rt` registration reads with `eval_str=True`
  (`fastcore.signature_ex`), which does evaluate a *whole-string* annotation — so `-> "FT"` on a
  handler would have failed before the sweep — but a quote **nested in a subscript**,
  `Result["FT"]` / `Result[list["TaskDTO"]]`, evaluates to a `ForwardRef` inside a real object
  and was inert. Unquoted, the inner name is evaluated at registration. Bootstrap aborts at the
  first `NameError`, so the rest were found statically (`@rt`-decorated handlers plus the
  factories' call-form `rt(path)(fn)` registrations, annotation names ∩ the module's
  `TYPE_CHECKING`-only imports): **8 handlers in 2 files** — `FT` in `activity_reports_ui`,
  `TaskDTO`/`EventDTO` in `orchestration_routes` — all made runtime imports. Re-run of the twelve:
  12 passed; both scans at 0.
- **`./dev test-unit` caught the readers that changed class** — 6 failures + 2 errors, every one
  a `NameError` from an `__annotate__` frame, in three tests that introspect constructor
  signatures with the 3.14 default: `Services` type hints
  (`test_route_service_attribute_contract`), `SearchRouter.__init__`
  (`test_search_router_registry`), the activity sub-service constructors
  (`test_activity_domain_config`). Each now asks for what it needs —
  `annotation_format=Format.FORWARDREF` where only names, kinds and defaults are read;
  `get_type_hints(..., format=Format.FORWARDREF)` with the test's own namespace where the types
  are, asserting nothing stays a `ForwardRef`. Re-run: green.
- **One production reader hardened:** `with_error_handling`'s uid extraction
  (`core/utils/decorators.py`) called bare `inspect.signature(func)` for parameter *names*, with
  an `except` that did not cover `NameError`. No decorated method names a `TYPE_CHECKING`-only
  type today, but the live rule now *mandates* the unquoted form, so the first one would have
  raised at the moment an error was being reported. It reads in FORWARDREF format now. Found
  beside it: the positional path indexed `args` with a position that counted `self`, so a
  positional call never carried the uid into the error details — fixed, and both pinned by
  `tests/unit/test_error_handling_decorator_context.py` (which deliberately has no
  `from __future__ import annotations`: PEP 563 would let the VALUE-format mutant survive — it
  did, until the import came out).
- `./dev quality` end to end — ruff (UP037 live), SKUEL lint, Cypher, the audits, MyPy **0
  errors** (2222 files), Pyright **0 errors**.

Docs that taught the quoted shape were rewritten with it: `TROUBLESHOOTING.md § Forward
References` (the pre-3.14 `"FT" | None` TypeError and its `Optional["FT"]` remedy are gone; the
`NameError`-from-`__annotate__` remedy replaces them) and CLAUDE.md's Troubleshooting line.

## The residual ruling — TC002/TC003, never as a sweep

Unchanged and permanent (ruled 2026-08-28, ADR-067 § Deferred): moving an import under
`TYPE_CHECKING` is only safe where nothing evaluates the annotation at runtime, and the residue
ruff's `runtime-evaluated-base-classes` cannot see is exactly FastHTML's local `@rt` decorator plus
every `get_type_hints`-style consumer. Enable either rule only per file, after checking no
annotation in it is evaluated. This is a ruling with a stated re-open condition, not open work —
which is why the case file graduates rather than staying in the MOC for it.
