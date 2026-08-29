---
title: Bloat Detection
updated: 2026-08-07
status: current
category: tools
tags: [dead-code, events, services, vulture, ast, maintenance]
related: [HEALTH_CHECKS.md]
---

# Bloat Detection

**Status:** ✅ Active (rewritten 2026-06-10, PRs #270 / #272)
**Location:** `scripts/detect_bloat.py`
**Tests:** `tests/unit/scripts/test_detect_bloat.py`

## Overview

Finds dead code that generic tools cannot express:

- **Event lifecycle** — events defined but never published, subscribed but never
  published (dead wiring chains), published but never subscribed. The
  publish/subscribe semantics live in SKUEL's event bus, not in Python's import
  graph, so no off-the-shelf tool can see them.
- **Service-method liveness** — Vulture as the liveness engine, post-filtered
  through SKUEL's dynamic-dispatch knowledge (route-factory templates,
  relationship-registry method names, dispatch tables).
- **Prompt-template backlog** — `PLANNED_TEMPLATES` entries with no render
  site (rides the full report only, not the scoped modes).

**Scope is exactly those three subjects.** Dataclasses, fields, enum members,
and config knobs are never examined, so a clean run is **not evidence** they
are live — inert fields are found by review, not by this tool (e.g. the
#849 / #853 / #864 / #877 deletions, all review-caught). There is deliberately
no `PLANNED_FIELDS` registry: the PLANNED tiers stay honest only because the
detector stale-audits their keys, and it has no field scanner to audit with.
Field-liveness detection itself is out of reach under the design rules below —
fields are consumed through `**kwargs`, DTO conversion, Neo4j property dicts,
and frontmatter mapping, which is cross-file dataflow.

```bash
./dev bloat               # full report (events + methods)
./dev bloat-events        # event lifecycle only
./dev bloat-methods       # service methods only

uv run python scripts/detect_bloat.py --verbose   # + unresolved/suppressed site lists
uv run python scripts/detect_bloat.py --json      # {"findings": [...], "planned_aging": [...]} (progress → stderr)
uv run python scripts/detect_bloat.py --check     # exit 1 on surviving WARNINGs
```

Advisory by default (exit 0). `--check` **is** wired into `./dev quality`
(check 7, the dead-code gate) and the CI lint job — gating became possible
once the recorded false-positive audit passed (PR #272). Staged work belongs
in the PLANNED tiers, which never fail `--check` — but a **stale** marking in
one of them does (ruled 2026-08-29): a registry key whose subject vanished or
is now wired is a lie about the backlog, and the tiers stay honest only if
nothing rots silently in them. The full advisory report
also runs on a clock: `.github/workflows/weekly-janitor.yml` (Mondays 06:30
UTC) runs it alongside the `./dev health` checks and renders the
PLANNED-tier aging plus any WARNING findings into an always-open status
issue — a rot detector that relies on human memory contradicts its own
purpose.

## Design rules

The detector follows the SKUEL linter's structural-soundness discipline
(see `/docs/patterns/linter_rules.md` for the same philosophy in lint rules):

1. **AST only — no regex over source.** Docstring examples are inert for free.
2. **No cross-file dataflow.** An event constructed in one file and published
   from another lands in the UNVERIFIED tier ("constructed but publication not
   structurally traceable"), never in the dead tier. A tool that lies is worse
   than none.
3. **Over-approximation only in the safe direction.** A resolution rule may
   suppress a dead-code accusation, never create one.
4. **No silent caps.** Everything the analysis could not resolve is counted and
   printed in the always-present Limitations section.

## Finding tiers

| Tier | Meaning | Fails `--check`? |
|------|---------|------------------|
| `WARNING` | Structurally dead — verified absence of liveness — **or a stale PLANNED marking** (subject vanished, or is now wired) | Yes |
| `UNVERIFIED` | Liveness signal exists but is not structurally traceable (constructed-but-untraced events; methods whose name appears as a string literal) | No |
| `PLANNED` | Structurally dead **by intent** — staged work registered in `PLANNED_EVENTS` / `PLANNED_METHODS` / `PLANNED_TEMPLATES`, awaiting its wiring | No |
| `INFO` | Live but noteworthy (published-never-subscribed — fine for fire-and-forget audit events; **name-masked PLANNED markings**, below) | No |

Act on `WARNING` findings after a manual grep-verify; treat `UNVERIFIED` as a
lead list, not a verdict.

**Unwired by intent is not bloat.** One Path Forward demands deleting
*abandoned* code; code whose wiring is deliberately staged (e.g. the
curriculum/resource `*EmbeddingRequested` events — subscribers live in
`embedding_worker.py`, publishers pending) is a completion to-do, not dead
code. Register it in `PLANNED_EVENTS` / `PLANNED_METHODS` (keyed
`relative/path.py::method_name`) with a reason naming what completes it. The
PLANNED section then functions as the visible wiring backlog. Integrity is
self-policing: a planned subject that vanished, or is now wired, is reported as
a **stale planned marking** — a `WARNING`, so it fails `--check` and must be
removed.

**The one case that is not staleness: a name-masked method.** Vulture's
liveness is name-based, so a single `self.backend.add_attendee(...)` marks
*every* `add_attendee` in the tree used — including a service method that is
still staged and unwired. "Stopped being a candidate" therefore stops meaning
"wired" for any name defined at more than one site. Such an entry is reported
as `planned-marking-masked` (INFO, its own report block): the marking may be
perfectly true, and deleting the entry to clear a report would hide genuinely
staged work — exactly the entries most likely to be forgotten. **Keep the
entry; verify wiring by hand.** The mask is not only a second `def` — one
`x.method_name` attribute load anywhere in the tree drops the candidate too
(`VultureScan.used_names` *is* the suppressor), so for methods there are exactly
two outcomes: **definition gone → stale** (the only provable case), **definition
still there → masked**. Reading "left the candidate set" as "wired" would fail
`--check` on honest staged work and would break the module's safe-direction rule
— over-approximation may suppress a dead-code accusation, never create one. The
masked detail names *why* attribution failed (N definition sites / the name is
loaded elsewhere / dispatch knowledge). Events and templates keep both stale
causes: their wiring is detected positively (a publish site, a render site), not
by name. The weekly janitor prints masked markings so the unverifiable case
stays visible rather than silently accruing.

**Prompt templates ride the same tier** (`PLANNED_TEMPLATES`, keyed by
template id — ADR-082 D4): registry `.md` files with no production render
site are invisible to the event/method scanners, so entries are emitted
directly with two verifications — existence (file deleted/renamed → stale)
and render-site liveness (a constant-string `.render()`/`.get()` reference
appeared → stale, wiring complete). Render sites that pass a variable
template id are invisible to the liveness check, so such an entry stays
listed until removed by hand. The template backlog appears on full runs
only — the scoped `--events-only` / `--methods-only` modes isolate their
own analysis.

## PLANNED-tier aging

A backlog is only honest if its age is visible, so every run summarizes each
examined registry: **entry count + oldest embedded ISO date + undated
count** — printed as the `◷ PLANNED-tier aging` block in the text report and
emitted as the `planned_aging` array in `--json` (one object per tier:
`tier`, `entries`, `dated`, `undated`, `oldest`).

Registry reasons carry decision dates as prose (`"Mike ruled PLANNED
2026-06-13"`), not structure — the registries are deliberately **not**
restructured for this, so extraction is best-effort by design: a `YYYY-MM-DD`
regex over the reason string, with non-calendar hits (e.g. `2026-13-40`)
discarded. Two rules keep it honest:

- **An entry ages from its OLDEST date.** A reason carrying an original
  staging date plus a later re-ruling measures from the first decision, not
  the latest touch-up.
- **No silent caps.** An entry whose reason yields no parseable date is
  counted in the `undated` figure, never dropped — a tier reading "84
  undated" is telling you the extraction's blind spot, not hiding it.

Tier scoping mirrors the analyses: `--events-only` summarizes
`PLANNED_EVENTS` only, `--methods-only` summarizes `PLANNED_METHODS` only,
and the full report adds `PLANNED_TEMPLATES` (same gate as the template
backlog itself). The weekly janitor workflow (below) renders this summary
into its status issue, so backlog aging is reviewed on a clock instead of
remembered.

## Event analysis (pure AST)

- **Universe:** transitive inheritance closure from `BaseEvent` over
  `core/events/` — catches indirect subclasses like
  `TaskEmbeddingRequested(EmbeddingRequested)`. An intermediate base is
  publish-live when any descendant is published.
- **Collection scope:** all first-party trees (`core`, `adapters`, `api`, `ui`,
  `services_bootstrap`, `main.py`). `tests/` never confers liveness — test
  references become annotations on findings.
- **Resolution layers** (all structural, file-scoped):
  - Import aliases: `from core.events.x import TaskCompleted as TC`.
  - Variable tracking: `event = EventClass(...)` then `publish_*(event)`.
  - Publish-wrapper inference, to a fixpoint: a function that publishes one of
    its own parameters is itself a publish helper (`publish_event`,
    `group_service._publish_event`, `BaseAIService._publish_event` — same-name
    wrappers with the event at different positions all resolve).
  - Subscribe-loop shape: `for ev in [A, B, C]: bus.subscribe(ev, h)`
    (`services_bootstrap/_event_wiring.py`).
- **Self-diagnostics:** the universe count prints beside `EVENT_REGISTRY`'s
  state, and zero resolved publishes/subscriptions triggers a loud "the scanner
  is probably broken" banner — fail-fast applied to the tool itself. Since
  2026-08-17 the registry is *derived* from each event's `event_type` ClassVar,
  so the line reads "derived — no literal to drift" and a **number** reappearing
  there means a hand-maintained literal came back. Registry completeness itself
  is a test (`tests/unit/test_event_registry_derivation.py`), not a report
  finding: the bloat report stays advisory by contract.

## Method analysis (Vulture + dispatch knowledge)

Vulture (`vulture>=2.16`, Python API) scavenges the full first-party tree plus
`vulture_whitelist.py` at `min_confidence=60` — that is mechanics, not tuning:
60 is the exact confidence Vulture assigns unused functions/methods/properties.
Findings are reported for `core/services/` only; the standalone CLI run
(`uv run vulture core adapters api ui services_bootstrap main.py
vulture_whitelist.py --min-confidence 90`) covers the rest of the tree.

Vulture's attribute-read semantics natively avoid the failure modes of
name-regex matching: `@cached_property` reads, by-reference handler
registration (`bus.subscribe(Ev, svc.handler)`), docstrings, and literal
`getattr` all count as usage.

Candidates then pass through the **dispatch-knowledge filter** — SKUEL's
dynamically-dispatched method vocabulary, collected structurally:

| Collector | Covers |
|-----------|--------|
| Literal method kwargs (`method_name=` / `*_method`) | hierarchy route factory, `AIRouteSpec`-style specs |
| Positional method args (`POSITIONAL_METHOD_ARGS`) | `AIRouteSpec` — `method_name` is field index 4, passed positionally in `ai_routes.py`'s route table |
| Query-route template expansion per literal `domain_name=` | `get_user_{d}`, `find_{d}`, `get_{d}_for_goal/habit` (hyphenated domains also expand underscored) |
| Relationship-registry cross product | `entity_label` × outgoing/incoming dict keys → `get_{label}_{suffix}` |
| String-literal demotion tier | any finding whose name appears as a used identifier-shaped string constant (docstring-aware) → demoted to UNVERIFIED, never suppressed |
| Operation-label inertness (`LABEL_CALL_FIRST_ARG` / `LABEL_KWARGS`) | strings naming an operation for error messages / metrics (`with_error_handling(...)`, `track_query_metrics(...)`, `operation=`) are NOT dispatch evidence and never demote — a method's own error label must not shield it from a dead finding |
| Computed-name `getattr` counter | counted + listed under `--verbose`, never hidden |

## Known limitations (also printed by the tool)

- **Out-of-scope subjects (dataclasses, fields, enum members, config knobs):**
  no scanner examines them — their absence from the report is silence, not a
  liveness verdict.
- **Vulture name-collision under-reporting:** any same-named attribute access
  anywhere marks ALL same-named methods used, so common-named dead methods and
  facade methods delegating to same-named sub-service methods are invisible.
- **No cross-function/cross-file event dataflow** by design — those flows land
  in UNVERIFIED.
- Unparseable files are reported loudly; their usage is invisible to every
  liveness claim.

## Exemptions

Central tables in the script (`EXEMPTED_EVENTS`, `EXEMPTED_METHODS` keyed
`relative/path.py::method_name`) — every entry requires a documented reason,
and exempted findings print collapsed rather than disappearing (the
`audit_route_security.py` convention). Vulture-level false positives belong in
`vulture_whitelist.py` instead.

## Acting on findings

1. Grep-verify the finding (include by-reference usage — a call-parens-only
   grep wrongly condemns a method that is passed by reference, e.g. as a
   callback or loader, rather than called directly).
2. Delete per One Path Forward — including the dead wiring (subscribers of a
   dead event are dead too).
3. Delete any sentinel test in `test_detect_bloat.py` that referenced the dead
   code by name.
4. If a finding is a false positive, either teach the dispatch-knowledge layer
   the missing structural pattern (preferred) or add a reasoned exemption.

## History

The original detector (initial-commit era) matched events against a hardcoded
class-name-suffix list and methods against `\.(\w+)\(` regexes; its headline
numbers (24 unused events / 396 unused methods) were false in both directions.
The 2026-06-10 rewrite replaced it wholesale — design plan and false-positive
audit are recorded in PRs #270 and #272.
