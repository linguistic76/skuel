---
title: Bloat Detection
updated: 2026-08-30
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
- **Embedding field-map backlog** — `EMBEDDING_FIELD_MAPS` entries whose type
  has no event class in `EMBEDDING_EVENT_TYPES` ("hollow" maps: nothing builds
  text for them), audited against `PLANNED_EMBEDDING_MAPS` (full report only;
  see *Embedding field maps* below).

**Scope is exactly those four subjects.** Dataclasses, fields, enum members,
and config knobs are never examined, so a clean run is **not evidence** they
are live — inert fields are found by review, not by this tool (e.g. the
#849 / #853 / #864 / #877 deletions, all review-caught). There is deliberately
no `PLANNED_FIELDS` registry for dataclass fields, enum members or config
knobs: the PLANNED tiers stay honest only because the detector stale-audits
their keys, and it has no field scanner to audit with. `PLANNED_EMBEDDING_MAPS`
is the one field-shaped tier, and it is auditable where a general field
registry is not — its subject is a *key of a known dict literal*, and the
hollow set it annotates is derived at run time rather than copied.
Field-liveness detection itself is out of reach under the design rules below —
fields are consumed through `**kwargs`, DTO conversion, Neo4j property dicts,
and frontmatter mapping, which is cross-file dataflow.

```bash
./dev bloat               # full report (events + methods)
./dev bloat --ready       # only the READY PLANNED entries (flags pass through)
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
one of them does (ruled 2026-08-29): a registry key whose subject is gone is a
lie about the backlog, and the tiers stay honest only if nothing rots silently
in them. "Stale" means *provably* stale — see *Integrity is self-policing*
below. The full advisory report
also runs on a clock: `.github/workflows/weekly-janitor.yml` (Mondays 06:30
UTC) runs it alongside the `./dev health` checks and renders the
PLANNED-tier aging (per readiness), any WARNING findings, the name-masked
markings and any READY entry past the review window into an always-open
status issue — a rot detector that relies on human memory contradicts its own
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
| `WARNING` | Structurally dead — verified absence of liveness — **or a stale PLANNED marking** (the registered subject no longer exists) **or a dangling `blocked_by` pointer** (`planned-blocker-missing`: an entry names a `deferred-work.md` heading that does not exist) **or an unregistered hollow embedding map** (`embedding-map-unregistered`: a field map with no event class and no `PLANNED_EMBEDDING_MAPS` entry) | Yes |
| `UNVERIFIED` | Liveness signal exists but is not structurally traceable (constructed-but-untraced events; methods whose name appears as a string literal) | No |
| `PLANNED` | Structurally dead **by intent** — staged work registered in `PLANNED_EVENTS` / `PLANNED_METHODS` / `PLANNED_TEMPLATES` / `PLANNED_EMBEDDING_MAPS`, awaiting its wiring; every entry declares `READY` / `DELAYED` and its staging date (below) | No |
| `INFO` | Live but noteworthy (published-never-subscribed — fine for fire-and-forget audit events; **name-masked PLANNED markings**, below; **`planned-ready-aging`** — a READY entry staged past the review window, see *PLANNED-tier aging*; **`embedding-map-phantom-field`** — advisory, see *Embedding field maps*) | No |

Act on `WARNING` findings after a manual grep-verify; treat `UNVERIFIED` as a
lead list, not a verdict.

**Unwired by intent is not bloat.** One Path Forward demands deleting
*abandoned* code; code whose wiring is deliberately staged (e.g. the
curriculum/resource `*EmbeddingRequested` events — subscribers live in
`embedding_worker.py`, publishers pending) is a completion to-do, not dead
code. Register it in `PLANNED_EVENTS` / `PLANNED_METHODS` (keyed
`relative/path.py::method_name`), `PLANNED_TEMPLATES` (keyed by template id —
ADR-082 D4) or `PLANNED_EMBEDDING_MAPS` (keyed by `EntityType` member name) as
a `PlannedEntry(readiness, reason, since=date(...))` — a reason naming what
completes it, plus two structured facts and one optional pointer:

- **`readiness`** (required, no default — every entry classifies itself):
  `Readiness.READY` when the completing change is fully specified and no
  decision stands before it (the live half already exists — a consumer polling
  an empty table, a detail page rendering the field, the ADD route of a pair —
  and only the producer, the write form, or the mirror route is missing);
  `Readiness.DELAYED` when it waits on a product decision, a ruling, or a
  surface that does not exist yet. On 2026-08-29 the split was 7 READY / 105
  DELAYED — the backlog is overwhelmingly product decisions, and that skew is
  the report, not a defect.
- **`since`** — the date of the *staging decision*: the first ruling, never a
  later re-ruling. Recovered per key from `git log -S` when the registries were
  restructured (2026-08-29); for a new entry it is the day the entry is written.
- **`blocked_by`** (optional, keyword) — a *pointer* at the `deferred-work.md`
  section that holds why the entry waits, written as the heading's core text
  (`blocked_by="HabitMissed — Publisher-less Chain"`), never a restatement of
  it: a reason that repeats what the section says is two copies of one fact,
  and one rots. Compared on both sides by `normalize_heading` — backticks
  stripped, one trailing parenthetical (the `(REGISTERED … — ruled …)` status
  suffix; the last balanced group only, so an earlier parenthetical is core
  text) dropped, whitespace collapsed — so the pointer survives a suffix edit
  and dies on a rename (see *Integrity*, below). Every row about the entry —
  awaiting-wiring, masked, stale — prints it as a `blocked by:` note; the
  beside-findings (`planned-ready-aging`, `planned-blocker-missing`) do not
  repeat it. A pointer at another registry key is not a form the tool
  accepts: it had zero users when the field landed, and a form with no user is
  dead the day it ships.

The PLANNED section then functions as the visible wiring backlog. Something the
scanner cannot see but that is **live** — a method whose only caller is under
`scripts/`, outside `FIRST_PARTY_ROOTS` — is not staged work and does not belong
here: it is an `EXEMPTED_METHODS` entry. ⚠ Exemptions have no stale audit in the
tool; `tests/unit/scripts/test_detect_bloat.py::test_live_exempted_methods_still_exist`
is the audit.

**Integrity is self-policing, and exactly three things fail `--check` — all
provable absence, none inferred.** First, **the subject is GONE**
(`planned-marking-stale`): a deleted or renamed event class, service method,
template `.md` or field-map entry makes its registry key a lie. "Gone" is
proven by looking for the definition, never inferred from a subject's absence
from an index: an event class missing from the *event universe* may simply
have stopped resolving as a `BaseEvent` subclass (a base-class edit, or a
module missing from `core/events/__init__.py`), which is an inheritance
defect, not stale backlog metadata. Second, **a `blocked_by` pointer resolves
to nothing** (`planned-blocker-missing`): the tool reads
`docs/roadmap/deferred-work.md` once per run — a markdown read, not source
analysis; the AST-only rule is about Python — and compares every pointer, in
every examined tier and whatever state the run found the subject in, against
the file's `##` / `###` headings by core text. A section renamed, moved to
`done/` (its trigger fired), or a mistyped pointer is the same finding; there
is no fuzzy match, because absence is the only fact. A missing
`deferred-work.md` aborts the run rather than reporting zero pointers. Third,
**a hollow embedding field map has no registration** (`embedding-map-unregistered`,
see *Embedding field maps*): the registry is the only place a hollow map can
be declared intentional, so an undeclared one is an accident or abandoned work
and provably so. All three are `WARNING`, print under their own red heading
(the full report, `--ready`, and the verdict line each name them apart from
structurally-dead findings), and
`test_detect_bloat.py::test_live_blocked_by_pointers_resolve_against_the_live_deferred_work`
fails locally on a heading rename before CI does — and CI does: `deferred-work.md`
sits in `ci.yml`'s `py` path filter so a rename-only PR still runs the gate and
the sentinel instead of taking the docs-only skip.

**"It looks wired now" NEVER gates — it reports as `planned-marking-masked`
(INFO).** Every liveness engine here over-approximates *by design*, because the
module's safe-direction rule permits over-approximation only to **suppress a
dead-code accusation, never create one**. Gating a became-live signal inverts
that rule: it fails `--check` on honest staged work, and the only way to clear
it is to delete the entry — which hides exactly the entries most likely to be
forgotten (the #1119 attendee pair sat masked for eight days). The four
engines and why none can attribute its signal:

| Tier | Engine | Why it cannot attribute |
|------|--------|-------------------------|
| Methods | vulture | Liveness is name-based (`VultureScan.used_names` *is* the suppressor). A second `def` of the name, **or one `x.method_name` attribute load anywhere in the tree**, drops the candidate with no call reaching this definition. |
| Templates | `_collect_rendered_template_ids` | Receiver-blind: any constant string handed to a `.render()`/`.get()` counts, so `settings.get("some_template_id")` reads as a render site. |
| Events | `EventUsageCollector` | Publish resolution uses a file-scoped variable index and class registries — a different `x` published elsewhere in the file resolves here, and one published sibling marks every class in a registry published. |
| Embedding maps | `EMBEDDING_EVENT_TYPES` membership | An event class is not a producer that passes the type: `RESOURCE` sits in the event map with vault ingestion as its only producer, and a service-created type could gain an event class with no publish site. |

**Keep the entry; verify wiring by hand.** The masked detail names why
attribution failed. The weekly janitor prints masked markings so the
unverifiable case stays visible rather than silently accruing. (A template
render site passing a *variable* id is invisible to the check either way, so
such an entry stays listed until removed by hand.)

The template and embedding-map backlogs appear on full runs only — the scoped
`--events-only` / `--methods-only` modes isolate their own analysis.

## Embedding field maps

`EMBEDDING_FIELD_MAPS` (`core/utils/embedding_text_builder.py`) declares *what*
each entity type's vector would carry; `EMBEDDING_EVENT_TYPES`
(`core/events/embedding_publisher.py`) decides *whether* anything is embedded
at all — ADR-074's only producers key on the event map. A map whose type has
no event class is **hollow**: nothing builds text for it, and until 2026-08-30
the three hollow entries (`ENTRY_REPORT`, `FORM_TEMPLATE`, `FORM_SUBMISSION`)
were indistinguishable from accidents *precisely because there was nowhere to
declare them intentional* (`deferred-work.md` § Catalog Copies in Code,
instance 3). Ruled 2026-08-29: keep them, register them, add `ACTIVITY_REPORT`.

**Why this is auditable where a general `PLANNED_FIELDS` is not:** the subject
is a key of a known dict literal, and the hollow set is **derived** at run time
— `set(EMBEDDING_FIELD_MAPS) - set(EMBEDDING_EVENT_TYPES)`, both read by AST
(`read_entity_type_keys`; the events package is never imported at lint time).
`PLANNED_EMBEDDING_MAPS` (keyed by `EntityType` member name) *annotates* that
set rather than copying it. The reader treats the two dicts as a contract —
every key is `EntityType.<MEMBER>` — and **aborts the run** on any other shape
(missing module or name, non-literal value, computed key, `**` spread): a set
it cannot see whole is one it can neither accuse nor exonerate, and "zero
hollow maps" over an unread dict would be the lie the tier exists to prevent.

Four findings:

| Finding | Severity | When |
|---------|----------|------|
| `planned-marking-stale` | WARNING, gates | a registered key has no `EMBEDDING_FIELD_MAPS` entry — the subject is gone (same predicate as the derivation) |
| `embedding-map-unregistered` | WARNING, gates | a hollow map has no registration — register it (staged) or delete the map (abandoned). About a *map entry*, not a registry entry: carries no readiness, never appears in `--ready` |
| `planned-marking-masked` | INFO, never gates | a registered key is now in `EMBEDDING_EVENT_TYPES` — an event class is not a producer (see the engines table); keep the entry, verify a publish site by hand |
| `embedding-map-phantom-field` | INFO, **advisory forever** | a mapped name is no annotated field of the model bound to that type, bases included (the `CHOICE`/`outcome` class — a phantom contributes nothing on the model path) |

The phantom check resolves each type's model by its `entity_type` default
(`ModelFieldIndex`), unions the fields of every class binding the member and
of every class its bases name — over-approximation in the safe direction only,
so it can suppress a report, never fabricate one — and counts what it could
not examine in Limitations. It **can never be more than advisory**:
`_get_field_value` also reads ingestion / Neo4j property dicts, so a dict-only
key is legitimate; it is blind to the inverse — a field that *exists*
(inherited from `Entity`) but no writer populates is a writer fact, found by
review; and it has one blind spot in the *unsafe* direction — the index
records annotated names only while `_get_field_value` reads with `getattr`,
so any runtime-readable attribute without an annotation (a `@property`, a
`cached_property`, a bare class attribute, any descriptor) named in a map
would read as a phantom (a false advisory the live sentinel surfaces;
measured zero on 2026-08-30, see the `ModelFieldIndex` docstring). `ENTRY_REPORT`'s old map `("title", "content", "summary")` was exactly
that: both fields exist, both writers populate `processed_content`. The check
did find `HABIT`'s `name` on the day it landed (no such field; the map's
comment records the fix).

The live sentinel `test_live_embedding_map_tier_is_clean` pins the tier to its
intended state — every hollow map registered, every registered map hollow,
zero phantoms; a deliberate dict-only key is recorded in the map's comment and
in that pin.

## PLANNED-tier aging

A backlog is only honest if its age is visible, so every run summarizes each
examined registry: **entry count + oldest staging decision, per readiness
class** — printed as the `◷ PLANNED-tier aging` block in the text report
(`PLANNED_METHODS: 105 entries — 7 ready (oldest 2026-06-11, 79 days ago), 98
delayed (oldest …)`) and emitted as the `planned_aging` array in `--json` (one
object per tier: `tier`, `entries`, `oldest`, plus `ready` / `delayed`
sub-objects each carrying `entries` + `oldest`). The definitions of the two
classes live on the `Readiness` docstring in `scripts/detect_bloat.py`; the
split exists because the two age differently: **a DELAYED entry aging is
expected** — it waits on something other than the wiring — **a READY one aging
is the signal.**

The date is `PlannedEntry.since`, a structured field every entry must carry,
so nothing is extracted and nothing can be missed. (Until 2026-08-29 the tool
scraped `YYYY-MM-DD` out of reason prose and reported the misses as `undated`
— 74% of `PLANNED_METHODS`; restructuring the registries deleted that scrape
and its `dated` / `undated` counters rather than adding a second one.) One rule
keeps it honest: **an entry ages from its staging decision** — the first
ruling, not the latest re-ruling — which is what `since` is defined to hold.

**Readiness changes what the tool does, in three places:**

- **Grouping.** Every tier's PLANNED block prints READY first, then DELAYED,
  each labelled — the actionable slice leads. Findings carry the entry's
  readiness (`--json`: `"readiness": "ready" | "delayed" | null`, null for a
  finding that is not about a PLANNED entry). It rides every finding *about*
  an entry — awaiting-wiring, masked, stale — because it is a fact about the
  entry, not about what the run learned of its subject.
- **`--ready`.** Prints only the READY entries of the tiers the run examined,
  then the aging block and the verdict line — nothing else. It filters the
  full analyses' output rather than reading the registries, so a READY entry
  the run found masked or gone prints in that state (its detail says which);
  `--check` is unaffected. Mutually exclusive with `--json` (the document is
  always the full one — filter on `.readiness` with jq).
- **`planned-ready-aging`** (INFO, advisory, **never gates**). A READY entry
  staged for **more than `READY_AGING_DAYS` = 90 days** — one quarter, the
  cadence `deferred-work.md` § Review Schedule walks the backlog on, so such
  an entry has outlived a review without being wired or deleted. It is emitted
  *beside* the entry's `*-awaiting-wiring` finding (same subject, file, line),
  never instead of it, prints under its own heading in every report (not the
  tier's generic INFO one), and is counted apart from unverified/info on the
  verdict line. A DELAYED entry never triggers it, whatever its age. At the
  2026-08-29 baseline it fires on nothing and first fires 2026-09-10 — a
  signal, not noise.

Tier scoping mirrors the analyses: `--events-only` summarizes
`PLANNED_EVENTS` only, `--methods-only` summarizes `PLANNED_METHODS` only,
and the full report adds `PLANNED_TEMPLATES` and `PLANNED_EMBEDDING_MAPS`
(same gate as those backlogs themselves). The weekly janitor workflow (below) renders the per-readiness
summary and any `planned-ready-aging` findings into its status issue, so
backlog aging is reviewed on a clock instead of remembered.

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
- **Embedding field maps:** a phantom-field report is advisory (dict-only keys
  are legitimate; an inherited-but-unpopulated field is invisible to a name
  check), and map entries whose type no parsed class binds, or whose value is
  not a literal tuple, are counted as unexaminable rather than passed.
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
