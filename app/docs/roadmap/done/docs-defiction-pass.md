---
title: "Docs de-fiction pass — build brief"
updated: 2026-09-22
status: "done — arc CLOSED 2026-09-22 in 7 PRs: #1379 instrument (`b7cb21478`), #1380 SEL + records (`5abf2d40b`, + #1381 `a790e3c75` the fragments → PLANNED), #1382 OWNERSHIP_VERIFICATION + draw 1 = 50% (`477aa039b`), #1385 domains + skills + draw 2 = 56.7% (`70f0a74b4`, + #1386 `127e3b9df` and #1387 `cdd48ff05`), #1388 patterns tail + code docstrings (`079ce77ba`, + #1389 `13ef46ad9` the two broken forms), #1390 decisions/ (`6193a1bb1`), #17 promote-or-record + close. Both precision draws came in under the 95% bar, so the `fiction` class STAYS ADVISORY by ruling — criterion (4)'s written alternative"
registered: 2026-09-19
ruled: "2026-09-19 (all five design questions); 2026-09-22 (the advisory branch)"
measured_on: "each row of § 6 carries its own merge commit — re-run every instrument, never quote a number from this file"
---

# Docs de-fiction pass — build brief

*The arc's record. It was written in the gitignored scratch tier while the arc ran and graduated
here when it closed; the eight per-PR prompts stayed behind in scratch. Nothing here is open.*

**The class.** A live doc or skill that describes a route, module, symbol, service, redirect or
behaviour that does not exist in the tree. CI stays green because every existing check tests a
*link target* or a *registered identifier* (dead links, stale names, `updated:` stamps, ADR
cross-references) — nothing tests a route claim, a `file.py:N` claim, or an example block against
the module it names. The last arc (#1378) found three sites agreeing on a `/ku` route with no
handler, a `status: production` doc whose whole UI section is fiction, and a "real-world example"
that never existed in `sidebar.py`; the seven single-fiction sweeps before it each found the brief's
list short and the enumeration wrong in both directions.

**Recommendation in one paragraph.** Build ONE new health instrument — the route-claim scanner —
on the *runtime* route table (891 paths; the AST-literal catalog `dead_doc_links.py` already builds
misses 417 factory-registered routes, 47%), plus two small extensions of instruments that exist
(`file.py:N` range checks inside `dead_doc_links.py`; a markdown reader for `history_in_code.py`).
Sweep the route class in five clustered PRs (165 fiction sites in 45 files, 47 of them in one
section of one file). Do NOT build a symbol-claim scanner or an example-fidelity scanner in this
arc — both were prototyped and measured, both are queues too big and too noisy for one arc, and the
symbol scanner's precision depends on a negation grammar the route scanner has to ratify first.
Gate nothing on day one; promote the fiction class to `./dev health` red (never CI — ruled) only
after two sweep PRs re-measure ≥95% precision. **All five rulings in §8 are in; PR 1 is unblocked.**

---

## 0. Baseline — every instrument run on `c4c0b26fb`, 2026-09-19

| Instrument | Command | Result |
|---|---|---|
| Dead doc links | `uv run python scripts/health/dead_doc_links.py` | **0 findings** (474 files; 6 + 94 carved out; 30 route skips, 69 `historical`, 11 `planned` markers) |
| Stale names | `uv run python scripts/health/stale_names.py` | **0** (65 renamed + 37 deleted identifiers, 574 files, code blocks only) |
| Dead modules | `uv run python scripts/health/dead_modules.py` | 2, both gitignored `plans/*.py` scratch — not CI |
| `updated:` stamps | `uv run python scripts/health/docs_updated.py` | ✓ current (470 docs) |
| History in code | `./dev history-in-code --top 10` | **731 lines / 287 files** of 1275 scanned (pr_tag 9 · pr_ref 235 · date 287 · phrase 227); head: `search_router.py` 16, `tasks_core_service.py` 15 |

Two of these baselines are themselves evidence for the arc:

- `docs/roadmap/dead-doc-links-sweep-queue.md` says **"Status: OPEN — 280 findings / 192 distinct
  targets"**; the instrument reports 0 (#1366 burned 279 → 0 on 2026-09-17). The doc's own
  `status:` and count are fiction about the instrument it documents. Same for
  `dead-doc-links-instrument.md` ("arc complete — residue queued" — the residue is gone). Both
  move to `docs/roadmap/done/` — a ride-along in PR 2.
- `history_in_code` is the model for every instrument here: advisory by contract, four categories
  each ratified on a hand-classified sample, "there is no exemption syntax", a census that orders
  a queue. This brief inherits that contract wholesale.

## 1. Evidence, re-verified against main

| Claim in the arc prompt | On `c4c0b26fb` | Class |
|---|---|---|
| `SEL_ADAPTIVE_CURRICULUM.md` (`status: production`, stamped 2026-09-17) names `/sel/{category}`, `create_sel_sidebar_layout`, `adaptive_sel` | **Still there.** Routes `/sel`, `/sel/{category}` were deleted in `27f6ef2a8` (2026-02-08, "SEL is a navigation lens, not a domain" — `sel_routes.py` + `sel_ui.py` deleted). `adaptive_sel` was absorbed into `PsService.adaptive` (`PsAdaptiveService`, 3 public methods; `track_page_view` is gone). The API survives renamed under `/api/path-steps/{journey,curriculum/{category},journey-html,curriculum-html/{category}}`; the two `-html` fragments have **no UI consumer**. Someone already half-retensed it: parentheticals like "(absorbed into … February 2026)" sit beside the intact fictional UI section and the `production` status | wired-then-removed (UI) + renamed (service, API) — **D3 test case** |
| Three sites agreeing on `/ku` | **Fixed in #1378** (ROUTE_MAP section, `ku_ui.py` log line, `hub_cards_from_organizers` default). Two live citations remain: `SEL_ADAPTIVE_CURRICULUM.md:467` "curriculum access via `/ku` hub", `docs/features/README.md:31` | rides the SEL PR |
| `/reports` 301, `/teaching` hub, `/curriculum` / `/study` redirects, `/home` | **Fixed in #1378** in the docs the arc touched. Surviving positive claims: `SHELL_FIRST_PAGE_PATTERN.md:205` ("Hub pages (`/home`, …)"), ADR-058 ("`/home` still resolves … retained as regression guard" — a *standing-contract* line in an Accepted ADR, now false) | route fiction |
| accessibility-guide "real-world example" not in `sidebar.py` | **Fixed in #1378** (Example 1 is now the real section nav) | — |
| Skill examples with emoji `icon=` values the component renders as `help-circle` | skuel-ui fixed in #1378; **`docs/patterns/UI_COMPONENT_PATTERNS.md:101-102`** still shows `SidebarItem(…, icon="✅")` / `"🎯"` (`Icon()` resolves a Lucide name; an emoji falls through). `EmptyState(icon="🎉")` at :774 is fine — that component accepts emoji | example-block fidelity (class e) |
| "line 470" in a 210-line file | **Fixed in #1378** (`ku_ui.py` prose citation) | line claim (class c) |
| 28-entry Evolution changelog in a live pattern doc | **Deleted in #1378** | history-in-docs (class d) |

Additions the prototypes surfaced while re-verifying (each confirmed against the catalog or `git log`):

- `docs/patterns/OWNERSHIP_VERIFICATION.md` §"All manual routes … now have ownership
  verification": **47 dead routes** — `/api/submissions/*` (11; renamed to `/api/user-entries/*`,
  ADR-054), `/api/choices/{uid}/options/*` (wired-then-removed, see memory), `/api/events/{uid}/{attendees,recurrence,cancel,start,conflicts}`,
  `/api/habits/{uid}/{track,untrack,reminders,streak,progress}`, `/api/expenses/*`, `/api/budgets/*`,
  … Every line carries "(was accepting user_uid …)" / "(had no auth)": a changelog in a live pattern
  doc. **One section — delete it.**
- `docs/domains/moc.md:139-146`: 7 `/api/moc/*` endpoints, none registered; wired-then-removed
  in `a1365ad0c` ("Remove KuType.MOC"), successors `/api/path-steps/{organize,unorganize,root-organizers,…}`.
- `docs/domains/ku.md`: `POST /api/knowledge` (create), `GET/PUT /api/ku/{uid}`,
  `/api/ku/{uid}/{relationships,prerequisites,dependencies,my-context}`, `/api/ku/analytics/summary`
  — none registered. ⚠ There is **no KU CRUD API under `/api/ku` at all** (the catalog holds only
  `/api/ku/{uid}/lateral/*`, `/api/ku/{uid}/mark-{studying,understood}` and `/api/knowledge/ai/*`;
  `my-context` lives at `/api/path-steps/my-context`). This brief's first draft wrote a
  `/api/ku/{get,create}?uid=` successor that does not exist — the sweep decides delete-vs-repoint
  per row from `git log` and the catalog, never from a brief.
- `adapters/inbound/admin_api.py` **module docstring** lists `POST /api/admin/users/{uid}/{role,deactivate,activate,hard-delete}`; the
  registrations are `/api/admin/users/{role,deactivate,…}` (no `{uid}` segment). `ingestion_api.py`
  and `vault_routes.py` docstrings still name `POST /api/ingest/directory`, which ADR-070 Decision 9
  deleted. 235 route claims live in `adapters/inbound/` docstrings; **9 are dead.** Same scanner,
  second corpus — the arc sweeps them (PR 5) but the instrument's default scope stays docs + skills.
- `UnifiedUserContext.build()` is cited in 6 live docs/skills (9 sites); the class is
  `UserContext` (`core/services/user/unified_user_context.py` — the *module* carries the word). A
  false namespace around a real member, the fourth archaeology shape. `HabitConsistencySignal`,
  `Expense` (as a class), `_get_learning_context()`, `Entity.user_uid` (the field lives on
  `UserOwnedEntity`) — all cited, none defined. These are symbol-class fiction (b); the arc records
  them but does not build the scanner (§3 (b)).
- `docs/design-handoff/calendar-month/README.md` self-declares **"HISTORICAL DESIGN RECORD … do not
  follow"** and carries a "the handoff says / the shipped contract" table — yet sits outside every
  history carve-out, so 8 of its `/events/…` citations report as fiction. D2 puts the directory
  where its header says it belongs.

## 2. What was prototyped, and what it measured

Four prototypes measured this section, all in the scratch tier. Three were superseded by
shipped instruments in PR 1 and deleted with the arc; the fourth was never built, and its method
is the spec in its own case file. Use the shipped commands, which measure the current tree:

```bash
./dev health-claims --all                             # (a) class totals + every fiction site
uv run python scripts/health/dead_doc_links.py        # (c) the `file.py:N` range check lives here
uv run python scripts/history_in_code.py --docs       # (d) the prose census
```

(b) has no command — see [Symbol Claims in Docs](../symbol-claims-in-docs.md).

### (a) Route claims — BUILD

**Catalog.** `_wire_all_routes(app, rt, MagicMock(), config, MagicMock())` on a bare `fast_app()`
(with `initialize_system_service` stubbed) registers **891 distinct paths in 3.6s without Neo4j** (892 before the catch-all strip).
The AST-literal catalog in `dead_doc_links.registered_route_paths()` holds 475 — a strict subset:
56 registrations are f-strings or names (`@rt(f"/{domain}")`, `@rt(f"{self.base_path}/create")`,
every lateral/hierarchy/CRUD/query/intelligence factory) and expand to **417 routes the static pass
cannot see**, including `/tasks`, `/goals`, `/api/tasks/create` and every `/api/{domain}/{uid}/lateral/*`.
Any scanner built on the AST catalog would report those as fiction. The runtime catalog is the union
over tiers (every service is a truthy mock) — correct for docs, which may describe FULL-tier routes.

⚠ **Two instrument defects found and fixed during prototyping — both would have shipped GREEN:**

1. `fast_app()` installs a root static catch-all `/{fname:path}.{ext:static}`; bootstrap strips it
   before wiring, the probe did not. Normalised to `/{}` it matched **every single-segment claim** —
   `/ku`, `/home`, `/sel`, `/reports`, `/teaching` all read as registered for the first two
   measurement rounds. Caught only when a known-dead route failed to appear. **The scanner ships with
   positive controls in its own test: known-dead (`/ku`, `/home`, `/api/moc/organize`) must be
   reported, known-live factory routes (`/tasks`, `/api/tasks/{uid}/lateral/blocks`) must not.**
2. A **line-scoped** negation grammar ("there is no", "404", "no `") skipped 9 lines — **5 of them
   hid real fiction**: `SHARING_PATTERNS.md:582` asserts `/api/activity-review/snapshot` "requires
   `@require_admin`" (dead route) and was skipped because a "no `" sits elsewhere on the line.
   Negation must be **span-adjacent** (`no `/x``, ``/x` → 404`, ``/x` is a 404`, "does not exist"
   immediately after the span). Span-scoped, it skips 2 and hides nothing. This is the
   cypher-vocabulary-gate lesson at claim scale: a token anywhere on the line is not a statement
   about the claim.

**Claim = an inline code span whose content is a URL path** (optionally `METHOD /path`, query and
anchor stripped, `{param}` segments and any segment containing `{…}` as wildcards; `/` trailing
stripped). Fence contents are a separate view (see (e)). Scope = `dead_doc_links.get_md_files()`
(its carve-outs inherited) — CLAUDE.md was probed separately: 17 route claims, all registered.

**Measured on the corpus** (inline spans, live docs + skills, `decisions/` counted separately):

| Class | Count | Meaning | Tier |
|---|---|---|---|
| matched | 1318 | registered (exact or wildcard-segment) | — |
| **fiction** | **165** (133 live + 32 `decisions/`) in **45 files** | unmatched, no history token on the line, not negated | the sweep; gate candidate |
| history | 34 | unmatched, line carries `was/were/deleted/retired/renamed/…` | class (d), reported under the history census |
| family-prefix | 40 | strict prefix of ≥1 registered route (`/api/context` "door", `/profile` → `/profile/inbox`) | reported, never gates — hides 7 real ones (`POST /api/knowledge`, `GET /api/ku/{uid}` ×3), so it is a class, not a skip |
| relative-suffix | 50 | single segment that ends ≥1 deeper route (`/create`, `/delete`, `/upload`) | reported, never gates — `/ku` lands here via `/library/ku`, so likewise a class, not a skip |
| negated | 2 | span-adjacent present-tense negative | skipped, printed |
| not a claim | — | filesystem paths (`/opt/skuel`, `/home/mike/…`, `/conf`, `/swapfile`), docs subdirs (`/patterns/`), `{domain}`/`domain` metavariable first segments (reuses `dead_doc_links._is_placeholder`), a vendor API with an Uppercase segment | excluded before matching |

**Precision, hand-classified** (three 40-item random samples, prototype seeds
1378 / 2026 / 4242 / 99): raw unmatched 50%; after the mechanical narrowings above, **fiction class
28/40 = 70%** on the last draw, **35/40 = 87.5%** on the draw before it. The residual false
positives are four shapes, each named so the sweep PRs can measure them down:

| FP shape | In sample | Remedy |
|---|---|---|
| framework-teaching skill examples (`.claude/skills/fasthtml/routing-patterns.md` converter table `/users/{id:int}`, `/price/{amount:float}`) | 3–4 | **RULED (§8 Q2): no carve-out.** PR 4 rewrites them to SKUEL routes, or to one sentence stating the feature is unused here; the same file carries wrong SKUEL-shaped examples (`@rt("/api/tasks/complete")`) a carve-out would have hidden |
| segment-vocabulary tables (`HTMX_ACCESSIBILITY_PATTERNS.md:42-50` "`/toggle`, `/status` → 'Status updated'") | 2 | single-segment claims that end no route; accept at advisory, or reshape the table to say "segment" |
| history narrated in a table cell or the previous sentence (`CYPHER_VOCABULARY_FINDINGS.md:67`, the "Removed routes" table in `ROUTE_AUTH_REQUIREMENTS.md`) | 1–3 | the (d) census catches the section; the sweep rewrites it |
| planned-without-marker in live roadmap (`/groups/{uid}/intelligence` "— new") | 1 | `<!-- planned -->` (B8's marker, reused as-is) |

Where the 133 live fiction sites are (the sweep's clusters): `OWNERSHIP_VERIFICATION.md` **47**,
`learning-loop/reference.md` 9, `SEL_ADAPTIVE_CURRICULUM.md` 8, `design-handoff/calendar-month/README.md` 8,
`domains/moc.md` 5, `domains/ku.md` 5, `fasthtml/routing-patterns.md` 5, `SHARING_PATTERNS.md` 4,
`REPORT_ARCHITECTURE.md` 4, `ADMIN_DASHBOARD_ARCHITECTURE.md` 4, `ROUTE_AUTH_REQUIREMENTS.md` 3, then a
tail of 22 files at ≤2. `decisions/`: ADR-038 9, ADR-058 4, ADR-019 4, ADR-018 4, ADR-069 3, seven
ADRs at ≤2.

**Size verdict.** Raw unmatched was 736 (>100), but 133 live sites in 33 files with 47 in one
deletable section is one arc. The cut is elsewhere: (b) and (d) are the >100 queues, and they are
not swept here (§2 (b), (d)).

### (c) `file.py:N` line claims — BUILD as an extension of `dead_doc_links.py`

Regex `path.ext:N[-M]` plus the prose forms "line N of/in `f.py`" / "`f.py` line N". **294 claims,
270 in range, 10 past EOF, 14 to a missing file — 24 findings (8%), mechanical precision ~100%.**
Heaviest: `ADMIN_DASHBOARD_ARCHITECTURE.md:165-169` cites `admin_routes.py:59…288` — the file is 36
lines. Eight of the 24 are in `decisions/` and take the historical marker.

⚠ **`dead_doc_links.py` currently sees none of these**: `_looks_like_local_path("core/models/nope.py:233")`
is `False` (the colon fails its shape test) and basename-only citations (`ku_graph_service.py:117`)
have no project prefix, so a `:N` citation to a *deleted* file is invisible to the link checker
today. The fix is inside the existing instrument — strip a trailing `:N[-M]` before resolving, then
assert `N ≤ line count` — and it inherits every carve-out and marker for free. ~40 lines + tests. Its
findings land in `./dev health` red, because that is where `dead_doc_links` already lives.

An in-range line is **not verified** — the line may say anything. That residual is review-only (§7).

### (b) Symbol claims — MEASURED, NOT BUILT THIS ARC

Prototype: an AST symbol table over `core/ adapters/ ui/ services_bootstrap/ scripts/ tests/`
(4221 classes, 35k names, type aliases and imported names included) plus stdlib/typing/fasthtml/pydantic
`dir()`s; claims = inline spans of class shape, `name()` shape, `Class.member`, `Enum.MEMBER`,
`ALL_CAPS`. **~12,000 claims, 1324 unresolved** (553 class-shaped, 440 ALL_CAPS, 154 dotted members,
114 calls). A 30-item hand sample: **~16 history/negation** ("`MocIntelligenceService` was deleted
in…", "then named `LessonOperations`, now `PsOperations`", `GraphContextLoader` ×17 across 8 files
— every one a "deleted in #241" sentence), **~8 illustrative** (naming-theory examples
`RevisingExercise`, cookie attributes `SameSite`, Chart.js `destroy()`, Prometheus
`histogram_quantile()`), **~6 real** (`UnifiedUserContext`, `HabitConsistencySignal`, `Expense`,
`Entity.user_uid`, `_get_learning_context()`, `DomainConfig.cross_domain_relationship_types` is on
two mixins, not `DomainConfig`). Precision on the fiction class ≈ 20–25% before a negation grammar;
the queue is ~8× the route queue.

Why not now: (i) its precision depends on the span-adjacent negation grammar that (a) ratifies on a
smaller corpus first — build it twice and they drift; (ii) ALL_CAPS claims are half env-var names
(`OPENAI_API_KEY`, `INGESTION_PATH`) and Cypher keywords (`MATCH`) that need a third vocabulary;
(iii) the regression half already exists: **`stale_names.py`'s `DELETED` table is the symbol gate**
— every fictional symbol the sweep confirms becomes a `DELETED` entry (zero new instrument, already
in `./dev health`). The census prototype stays in scratch; the follow-on arc inherits (a)'s grammar,
and this brief's residual section records the six confirmed symbols so they are not lost.

### (d) History-in-docs — BUILD as a markdown reader for `history_in_code.py`

`history_in_code.classify()` is a pure function over a line; feeding it prose lines of live docs
(fences and frontmatter excluded) gives: all live non-ADR docs **1671 signal lines in 284 of 387
files** (date 956 · pr_ref 431 · phrase 410 · pr_tag 137) — dominated by `docs/roadmap/` case
files whose *function* is dated rulings, and by `docs/INDEX.md`'s Completed table. Narrowed to
**phrase only, outside `roadmap/` and `decisions/`: 342 lines in 147 files** — `CYPHER_VOCABULARY_FINDINGS.md`
14, `PLACEHOLDER_INDEX.md` 11, `MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md` 10, `linter_rules.md` 10,
`INTELLIGENCE_SERVICES_INDEX.md` 8, `learning-loop/reference.md` 7 …

Build: a `--docs` mode (or `scan_markdown()` beside `scan_source()`) that reads prose lines outside
fences, skips YAML frontmatter, and applies the same four categories with the same output table;
**advisory by the finder's own contract** — never in `health`, never a gate, exit 0. Its queue is not
swept in this arc except where a route-fiction PR is already inside the file (the 34 route claims
tagged `history` are the overlap: `OWNERSHIP_VERIFICATION.md` 14, ADR-070 6, `HUB_PAGE_PATTERN.md` 3).
Ruling for the reader: a `date` hit in `docs/roadmap/` is the case file doing its job, same as the
DSL example timestamps in code — reported and skipped on read; no exemption syntax.

### (e) Example-block fidelity — NOT BUILT

Fence string literals starting with `/` were extracted as a second claim view: 594 claims, 304
unmatched. 30-item sample: ~11 generic framework illustrations (`/items/{price}`, `/ws`, `/item/1`),
2 `Path("/vault/docs")` filesystem args, ~17 SKUEL-shaped snippets naming dead routes
(`hx_get="/api/sel/curriculum-html/…"` in `HTMX_ACCESSIBILITY_PATTERNS.md:85`, `@rt("/sel/{category}")`,
`action="/api/tasks"` where create is `/api/tasks/create`). "Is this snippet a claim about SKUEL or a
lesson about the framework" is the whole question and it is semantic; the emoji-icon case is the
same class (the snippet executes, the component renders a fallback — only running it against the
module shows that). The cyphergenerator sweep's answer stands: **execute the published example**,
which is a per-file act during a sweep, not a scanner. The route scanner keeps `--fences` as an
advisory *view* (it already exists in the prototype) so a sweep PR can list a file's fenced route
claims; nothing counts them.

## 3. D1 — the scanner set (recommendation; Mike rules)

| Scanner | Verdict | Where it lives | Precision measured | Tier at birth | Tier after two sweeps |
|---|---|---|---|---|---|
| (a) route claims | **build** | new `scripts/health/route_claims.py`, catalog in a shared `scripts/health/route_catalog.py` that **also replaces** `dead_doc_links`'s AST catalog (one catalog, two readers — the `TEMPLATE_MARKERS` precedent; it retires that checker's "f-string routes stay red by design" exception — **ruled**, §8 Q5) | fiction 70–87.5% (n=40 ×2) | advisory: prints classes, exit 0 | **fiction → `./dev health` red** if ≥95% on the two re-measures; family-prefix / relative-suffix / history stay printed-only forever |
| (c) line claims | **build** | inside `dead_doc_links.py` (strip `:N`, range-check) | ~100% (24/24 mechanical) | `./dev health` red from day one — same instrument, same tier | — |
| (d) history in docs | **build, small** | `history_in_code.py --docs` | inherits the finder's ratified categories | advisory forever (the finder's anti-goal) | never |
| (b) symbol claims | **not this arc** | scratch; `stale_names.DELETED` is the gate for confirmed symbols | 20–25% fiction | — | follow-on arc after (a)'s negation grammar ships |
| (e) example fidelity | **not built** | `route_claims.py --fences` advisory view only | ~55% on route-shaped fence claims; the rest semantic | — | never as a scanner |

**Design rules the instrument PR must satisfy** (each is a Codex round already paid for elsewhere):

- Runtime catalog, one probe, mirrors bootstrap's catch-all strip, cached per process; the docstring
  states that it is the union over tiers and why. Positive controls (dead must report, live factory
  routes must not) in the test, not the script.
- Every exclusion is a **printed class with a count**, `dead_doc_links` style — no silent skip; a
  class that prints zero for a whole run is how a rotted narrowing looks like a clean scan.
- The negation grammar and the history-token list are **enumerated as test cases before the
  regex exists** (`tests/unit/scripts/test_route_claims.py`: the 9 lines from §2 (a) defect 2, both
  directions). History tokens reuse `history_in_code`'s phrase table — one vocabulary.
- Markers reused, not copied: `<!-- historical -->` honored in `decisions/`, `<!-- planned -->` in
  live `roadmap/`, through `dead_doc_links.MarkerSpec` — and a marker that suppresses no dead
  route claim is reported (the SKUEL026 inversion, already built for links).
- No teaching-example carve-out for `.claude/skills/fasthtml/*` (ruled, §8 Q2) — those sites are
  reported and rewritten in PR 4.
- Fault-inject before keeping every fix: a scratch doc with `/ku` must go red, with `/tasks` must
  not, with "no `/ku`" must print under negated, with `/api/context` must print under family-prefix.

## 4. D2 — live vs record

**By directory, plus the per-citation markers that already exist. No file-scope status mechanism.**

- `docs/roadmap/done/`, `docs/migrations/`, `docs/investigations/`, `docs/Reviews/` stay the silent
  history carve-out (ruled 2026-09-01). **Add `docs/design-handoff/`** — its one file declares itself
  a historical record in its header and reports 8 route fictions only because the directory is not
  listed. Same silent-dir shape, count printed on its own line.
- `docs/decisions/` keeps the per-citation `<!-- historical -->` mechanism (a whole-tier carve-out
  was rejected on Codex #1215 and the standing-vs-narrative split measured 81/70 — still intra-file:
  ADR-058's "`/home` still resolves" is a standing contract gone false three lines from faithful
  narrative). The 32 ADR route claims take B4's treatment: fix the standing contract, mark the
  narrative.
- `docs/roadmap/` (live) keeps `<!-- planned -->`; the one unmarked planned route
  (`/groups/{uid}/intelligence`) gets the marker.
- **The brief's "`status: proposed|superseded` as file-scope planned/historical" is declined.** The
  `status:` field holds **40 distinct free-text values across 220 docs** (`current` 110, `accepted`
  16, `complete` 11, `ruling needed (defect 3)`, `ruff patched`, `open — events/principles half` …);
  `superseded` appears twice, `proposed` three times, and `SEL_ADAPTIVE_CURRICULUM.md` is the one
  `production`. A scope mechanism on that field needs a vocabulary first, the vocabulary is a
  separate ruling, and status-scoping was already falsified for the tier it would matter most in.
  A doc whose whole body is superseded is not marked — it is moved or deleted (D3).
- `CLAUDE.md` / `AGENTS.md` are in scope for a **manual** probe each sweep PR (CLAUDE.md: 17 route
  claims, 0 fiction today), not in the scanner's default `SCAN_DIRS` — `stale_names` already
  includes CLAUDE.md; `dead_doc_links` does not; keep the two instruments' scopes as they are and
  note the asymmetry rather than resolve it here.

## 5. D3 — fix policy per class

The action follows the **tree's verdict** (never-existed / renamed / wired-then-removed /
staged), determined per claim by `git log --all -S"<literal>" --name-only` with a positive control,
`--diff-filter=D` for deleted route files, and the runtime catalog for the successor — never by the
doc's own account of itself.

| Tree says | Live doc claim | Action |
|---|---|---|
| renamed / moved (successor in the catalog) | route table row, API list | **repoint** to the successor, present tense (`/api/moc/organize` → `/api/path-steps/organize`; `/api/submissions/*` → `/api/user-entries/*`) |
| wired then removed, no successor | a section describing the surface | **delete the section**; one present-tense sentence stating the current door if the doc's purpose survives; the record is `git log`, an ADR or `done/`, pointed at, never retold |
| wired then removed, doc's purpose was that surface | whole doc | **delete the doc**; move the ≤20 live lines to the doc that owns the survivor; fix every inbound reference (`git grep` the basename — INDEX.md, the directory README, skills) |
| never existed | any | **delete the sentence** (ADR-TEMPLATE's "fictional by design" is the only sanctioned home) |
| staged (ruled keep) | any | leave, cite the ruling doc — Gantt precedent |
| exists, doc narrates its past | "(was accepting …)", "deleted in #NNN", changelog tables | **retense**: the rule once, positive, present; the why moves to the record, never deleted — `history_in_code`'s per-site rule |
| `decisions/` narrative | dead route in a faithful account | `<!-- historical -->` |
| `decisions/` standing contract | dead route stated as the current chokepoint | **fix against a reproduced successor** (B4) |
| `roadmap/` design destination | route the plan intends to create | `<!-- planned -->` |

**SEL, decided from the tree:** the UI (`/sel`, `/sel/{category}`, `create_sel_sidebar_layout`,
drawer, ARIA sections, the manual-testing checklist) is wired-then-removed with no successor
(`27f6ef2a8`); the service is renamed (`PsAdaptiveService`, 3 public methods — `track_page_view`
gone); the API is renamed (`/api/path-steps/…`) and its two HTML fragments have no consumer; the
"Migration History" section retells `docs/migrations/SEL_UX_MODERNIZATION_2026-02-03.md`, which
exists; "Future Enhancements" Phases 2–4 are planned work advertising a surface that no longer
exists (B4 ruling (1): delete, never mark). The doc's purpose *was* that surface → **delete the doc
and `docs/features/` with it** (its README lists SEL as the only feature and defines the directory
as "what was built and how to use it" — nothing else lives there). The ≤20 live lines — the three
`PsAdaptiveService` methods, the four `/api/path-steps/` routes, `SELCategory` as a Ku/PathStep lens —
go into `docs/domains/ps.md`, which does not mention `adaptive` today. Inbound: `docs/INDEX.md:408`,
`docs/features/README.md`, the three `related:` back-links, `curriculum-domains/DOMAIN_SPECIFICS.md:106`.
Ride-along: the consumer-less `journey-html` / `curriculum-html` fragments are **code**, registered
in the bloat detector's PLANNED tier or deleted under One Path Forward — a decision for the PR body,
flagged, not made here.

## 6. D4 — sweep shape and PR plan

Instrument first, never an S; then clusters; SEL first as the D3 proof; gate promotion last.

| PR | Scope | Size | Gate work | Proves |
|---|---|---|---|---|
| **1 — instrument — #1379** | `scripts/health/route_catalog.py` (runtime probe) + `route_claims.py` (classes, markers, positive controls, `--file`, `--fences` view) + `dead_doc_links.py` (`:N` range check; consume the shared catalog) + `history_in_code.py --docs` + tests (negation/history cases enumerated first; fault-injection fixtures) + `./dev` roster row + `HEALTH_CHECKS.md § 9` + `HISTORY_IN_CODE.md` docs mode | **M** (≈500 lines, 4 scripts) | advisory; (c) red in health | catalog superset; the two defects in §2 (a) pinned. **Measured on the merge commit `b7cb21478` (2026-09-20):** 1627 claims → 1295 matched · **210 fiction in 51 files** (4 are dead directory citations) · 17 history · 36 family-prefix · 51 relative-suffix · 15 negated · 2+1 marker-skipped; `[line]` 29 (15 past EOF · 11 missing · 3 ambiguous; 9 in `decisions/`); `--docs` 2322 lines / 363 files. Codex 18 rounds / 39 findings (37 fixed, 2 rejected with measurement), ALL in the instrument — the PR body carries the round-by-round list. The shipped `history` class uses `history_in_code.classify` (narrower than the prototype's token list) so `OWNERSHIP_VERIFICATION.md` reads 62 fiction, not 47; bare `/home` is a claim (14 sites the prototype excluded as a mount). Re-run, never quote |
| **2 — SEL + records — #1380** | delete `docs/features/`; live lines → `domains/ps.md`; INDEX/README/skill back-links; `design-handoff/` → history dir; `dead-doc-links-sweep-queue.md` + `dead-doc-links-instrument.md` → `done/` (status/count fiction about their own instrument); deferred-work MOC lines | **S** | — | D3 on the test case; `git grep` every inbound name. **Measured on the merge commit `5abf2d40b` (2026-09-20):** 1596 claims → 1288 matched · **189 fiction** (210 → 189: −8 deleted, −8 carved out, −4 ADMIN_DASHBOARD table, −1 LEARNING_LOOP row; site-set diff = 0 new) · 16 history · 36 family-prefix · 48 relative-suffix · 16 negated · 2+1 marker-skipped; `[line]` 29 → **12, all `decisions/`** (the split was 12 + 17, not 9 + 20); false positives 0 of 21 touched. The consumer-less `journey-html`/`curriculum-html` fragments + `ui/patterns/curriculum_adaptive.py` **deleted** (flagged in the PR body; no test, no orphaned method). Codex 2 rounds / 1 finding (the moved case file's own lifecycle preface — not the record — took the `done/` form). The PR body carries the site-set diff and the fragment decision |
| **3 — OWNERSHIP_VERIFICATION.md — #1382** | delete the 47-route changelog section; retense its 14 history lines; the doc keeps its rule (`verify_entity_ownership`, `require_owned_entity`, the 404 contract) | **S** | re-measure precision #1 | the biggest cluster is one section. **Measured on the merge commit `477aa039b` (2026-09-20):** file 63 claims → 2, fiction 62 → 0 (the changelog section AND its "Status: Complete" table — the same changelog twice); corpus 1605 → 1544 claims, **189 → 127 fiction in 46 files** (44 in `decisions/`), history 16 · family-prefix 36 · relative-suffix 49 · negated 16 · 2+1 marker-skipped; line-blind site-set diff = 0 new; false positives 0 of 62 touched. `--docs` on the file 5 → 0 (the brief's "14 history lines" was the prototype's count; the shipped class reads 5). **Precision draw 1: 15/30 = 50%** (seed `"docs-defiction-pr3"`, population 127; FP classes: history-vocabulary miss 9, negation-grammar miss 2, dead directory citation 2, planned-without-marker 1, segment-vocabulary 1; 12 of 30 drawn were ADR sites, 7 of those not a claim). Ride-along: `with_ownership` (never a consumer) + `require_ownership_query` (consumers shelved `67ec268e8`) deleted, → `stale_names.DELETED`. Codex 3 rounds / 3 findings, all real, two on the same point: the doc's UI example must return the helper's 404, and a fragment's 200 banner is a defect against the invariant, not an exception. Rulings handed to Mike: `OwnershipRouteFactory` has ZERO registrations since `67ec268e8` (re-adopt vs delete); the fragment-404 convention (`htmx:beforeSwap` opt-in); 30 inline owner compares (ADR-085 §4). The PR body carries the draw-1 table and the three rulings handed to Mike |
| **4 — domains + skills — #1385** | `domains/{moc,ku,user_entry,finance}.md`, `learning-loop/reference.md` (9), `curriculum-domains/{SKILL,QUICK_REFERENCE}.md`, `domain-route-config/PATTERNS.md`, `fasthtml/{routing-patterns,QUICK_REFERENCE}.md` (rewrite to SKUEL routes — ruled, no carve-out) | **M** | re-measure precision #2 | renamed → repoint. **Measured on the PR head `9efd70b13` (2026-09-20; merge `70f0a74b4` reads 1620 claims / 1421 matched — 17 Codex rounds added matched examples, the 92-site fiction set never moved):** corpus 1552 → 1598 claims, **127 → 92 fiction in 34 files** (44 in `decisions/`), history 16 · family-prefix 26 · relative-suffix 41 · negated 20 · 2 + 2 marker-skipped; the ten files 32 → 0 fiction, fences 12 → 0 (`routing-patterns.md`), `--docs` 22 → 6; site-set diff 0 new; false positives 5 of 35 touched (2 dead-directory citations, 1 planned, finance.md's history + plan pair). **Precision draw 2: 17/30 = 56.7%** (seed `"docs-defiction-pr4"`, population 92; FP classes: history-vocabulary miss 5, negation-grammar miss 2, dead directory/file citation 3, segment-vocabulary table 2, two-segment relative citation 1; 14 of 30 drawn were ADR sites, 7 of those not a claim) — **criterion (4)'s advisory branch is live**. Two brief premises measured false: "every SKUEL path param is a `str` uid" (calendar/journal period routes annotate `int`; the true sentence is *no converter is registered*) and "query params for all API routes" (186 of 598 API paths take a path uid). The KU CRUD API's `git log -S` "successor" is the PathStep API — a successor can serve a different entity. Ride-alongs: `KuOrganizationService` rename chain (→ `stale_names.RENAMED`, 5 sites), `CURRICULUM_GROUPING_PATTERNS.md`'s inverted service-size section, the queued `<!-- planned -->`. **Codex 17 rounds / 28 findings, ALL in sentences written while fixing fiction** — the recurring one: the facade is not the mixin (`organize`/`get_organization_view`/`get_navigation` gate on `ps_core.get()` = `:PathStep`; only four edge-level reads are entity-generic). **Handed to Mike (P1):** the ORGANIZES read routes are unauthenticated over `:Entity` — a personal `moc: true` UserEntry map is readable by anyone; fix priced in the PR body. The PR body carries the draw-2 table and the P1 pricing |
| **5 — architecture/patterns tail + code docstrings — #1388** | `REPORT_ARCHITECTURE`, `ADMIN_DASHBOARD_ARCHITECTURE`, `SHARING_PATTERNS`, `AUTH_PATTERNS`, `ROUTE_AUTH_REQUIREMENTS`, `ROUTE_FACTORIES`, `INTELLIGENCE_*`, `PATHSTEP_CONTENT_ARCHITECTURE`, `SHELL_FIRST_PAGE_PATTERN:205`, `UI_COMPONENT_PATTERNS.md:101` (emoji icons), the `adapters/inbound/` docstrings; the §2 (b) symbols → `stale_names` | **M** | — | the tail is flat (≤4/file). **Measured on the merge commit `079ce77ba` (2026-09-21):** corpus 1631 → 1637 claims, **92 → 44 fiction in 14 files — every one in `decisions/`** (the 48 non-ADR sites in 23 files → 0), history 15 · family-prefix 23 · relative-suffix 39 · negated 33 · 2 + 3 marker-skipped; site-set diff 0 new; false positives 3 of 48 touched (history-vocabulary: "The retired `/x`" ×1, a findings record's "was removed" on the previous line ×2 — negated in place, vocabulary not widened). `INTELLIGENCE_ROUTE_FACTORY_USAGE.md` deleted (a five-route API in no `.py` at any commit) and `FINANCE_CATEGORIES_GUIDE.md` deleted (578 lines "kept for archaeology" past its own deletion condition). (b): 3 RENAMED (`UnifiedUserContext`, `Entity.user_uid`, `DomainConfig.cross_domain_relationship_types` — a fictional namespace on a real `DomainRelationshipConfig` member), 6 DELETED (`MOCService`, `MocNavigationService`, `_get_learning_context`, `ExpensePure`/`ExpenseDTO`/`ExpenseCreateRequest`), `HabitConsistencySignal` **declined** (a proposal that says so on every mention); 63 doc hits → 0. Inbound docstrings: 30 dead route claims (not the brief's 9 — a docstring+comment scan, not a grep). `/toggle` + `/decide` deleted from `skuel.js`'s announce taxonomy (no registered route ever contained them since `67ec268e8`). **Three live defects found through docstring claims:** the admin role form and the exercise editor both post to unregistered paths (handed to Mike, priced); the intelligence context route leaked its tuple `Result` under `Result[Any]` (fixed — Codex round 4). Codex 4 rounds / 5 findings, all real, all in sentences written while fixing. The PR body carries the 30 docstring routes and the nine (b) verdicts |
| **6 — `decisions/` — #1390** | 44 route claims in 14 ADRs + the 12 `[line]` rows (the brief's "32 + 8 in 12" was the prototype's count): standing vs narrative per B4's worksheet method (reproduce the successor first — 4 of B4's worksheet verdicts were wrong) | **S** | — | red in the authority tier means rot. **Measured on the merge commit `6193a1bb1` (2026-09-21):** corpus 1637 → 1648 claims, **44 → 0 fiction**, history 19 · family-prefix 22 · relative-suffix 41 · negated 42 · 28 + 3 marker-skipped, 0 stale markers; `[line]` 12 → 0; site-set diff 0 new; **false positives 21 of 44 touched** (history-vocabulary 9, negation-grammar 8 — ADR-038's six-route list under a previous-sentence negation is most of it — dead directory 3, shape 1; the FP-heavy tier both draws predicted). `./dev health` GREEN — and it was red on Mike's machine for a second reason hidden behind the 12 rows: `dead_modules.py` walked the gitignored `plans/` prototypes (fixed — `plans` never scanned, the clone-independent rule `dead_doc_links` already states). Verdicts from the tree: ADR-018/019's `{uid}` path spellings never matched a decorator (the initial commit already registered `?uid=`); `/webhooks/stripe` + `/webhooks/chargekeep` in no `.py` at any commit; `/admin/component-gallery` never existed; `/home` gone in two hops (`1cb65580d`, #1377). Standing sections read through the doorway: ADR-002's "mastery threshold 0.7" was never built, ADR-004's output shape is `ReadyToLearnResult`, ADR-058's endpoint list was 8 → 5 with the habits fragment unlisted. **Codex: 1 round, 0 findings** (the first clean first round of the arc). Handed to Mike: `POST /api/ingest/domain/{domain_name}` is a second live directory-ingest door with no consumer (contradicts ADR-070 Decision 9). The PR body carries the standing-vs-narrative worksheet |
| **7 — record + close — #PR7** | both draws came in under the bar, so the **advisory branch**: the ruling written into `HEALTH_CHECKS.md § 9`, the `dev` roster comment and the scanner's own docstring + output note; the (b) and (d) queues registered in `deferred-work.md` with case files; this brief graduated here | **S** | none — the class gates nothing | the closing criterion below, criterion by criterion |

Every sweep PR: run the scanner on its files BEFORE and AFTER; record the fiction count and the
false-positive count in the PR body (that pair is the precision series PR 7 reads); `./dev health`
green; `./dev quality` clean; Codex summoned in a foreground `540` call after the final push.
Coordinates cited in any PR body are re-derived after rebase (the register-drift trap).

**Gate table**

| Class | Advisory (PR 1) | Health-red (PR 7, conditional) | CI | Janitor |
|---|---|---|---|---|
| (a) fiction | print | **yes, if ≥95% ×2** | never (docs checks live in health) | via health |
| (a) family-prefix / relative-suffix | print | never | never | via health |
| (a) history | print (hands off to (d)) | never | never | — |
| (c) line claims | — | yes (inside `dead_doc_links`) | never | via health |
| (d) history in docs | print | never | never | never |
| stale marker (route claim) | red | red | never | via health |

## 7. Residuals — review-only, named so nobody re-derives them

- **In-range `file.py:N` claims (270)** — the line exists; whether it says what the doc says is a
  read. The instrument proves absence, never truth.
- **Symbol fiction (b)** — six confirmed (`UnifiedUserContext`, `HabitConsistencySignal`, `Expense`,
  `Entity.user_uid`, `_get_learning_context()`, `DomainConfig.cross_domain_relationship_types`) go to
  `stale_names.DELETED` in PR 5; the other ~1300 unresolved wait for the follow-on arc. The
  `GraphContextLoader` ×17 sentences are (d), not (b).
- **Example blocks (e)** — the SKUEL-shaped snippets in `HTMX_ACCESSIBILITY_PATTERNS.md:85`,
  `FORM_GENERATOR_GUIDE.md:102/117/315`, `http_status_codes.md:76`, `HIERARCHY_COMPONENTS_GUIDE.md:588`,
  `chartjs/activity-domain-charts.md:506`, `skuel-ui/reference.md:92/572/851` name dead or drifted
  routes; each is fixed when its file is opened, by executing the snippet where it can be executed.
- **History in docs (d)** — 342 phrase lines / 147 files, the ride-along queue, ordered by the finder.
- **Sub-claims no scanner sees**: counts ("12 searchable domains"), "only/never/the sole X"
  assertions, a docstring that is right about the name and wrong about the behaviour. Adversarial
  read remains the instrument (the #856/#857 lesson).
- **`status:` vocabulary** (40 values) — a separate ruling if ever; not touched.
- **Consumer-less code the sweep exposes** (`journey-html` / `curriculum-html` fragments) — PLANNED
  tier or deletion, decided in PR 2's body.

## 8. Rulings (Mike, 2026-09-19)

1. **D1 as proposed — RULED yes.** (a) + (c) + (d) built; (b) and (e) measured and deferred.
2. **Framework-teaching skills — RULED: no carve-out; report, and rewrite to SKUEL routes.**
   Mike asked for a preference; the recommendation was no carve-out and he took it. Why: the
   carve-out would silence the wrong SKUEL-shaped examples alongside the generic ones in the SAME
   file (`fasthtml/routing-patterns.md:13` `@rt("/api/tasks/complete")` — the live status door is
   `POST /api/tasks/{uid}/status`; there is no `/api/tasks/{uid}/complete` (this brief first wrote that one — a second published successor that does not exist; check the catalog) — sits next to the generic converter table), the B1 shape that keeps
   `HUB_PAGES.md` reported; six sites do not pay for a registry entry + reason + count + stale test;
   and a skill is read by an agent working in this repo, so an example naming a real route teaches
   the framework and the repo at once and stays checkable. Where the framework feature is unused
   here (no `int`/`float`/`uuid` converters — every SKUEL path param is a `str` uid) the edit is one
   true sentence saying so (`e886b8ddc`: pattern docs describe what IS). PR 4 carries the rewrites;
   the `ui-browser` cases are fence claims (class e) and wait for their file to be opened.
3. **Gate destination — RULED: `./dev health` red, never CI.**
4. **`docs/features/` — RULED: delete** with the SEL doc (PR 2).
5. **Catalog — RULED: the runtime catalog replaces the AST one in `dead_doc_links.py`;** the AST
   extractor survives only as the test's subset assertion (`ast_paths ⊆ runtime_paths`, and the
   count of the difference printed so a shrinking gap is visible).

## 9. Closing criterion

The arc is closed when: (1) `route_claims.py` reports **0 fiction** over live docs + skills with
family-prefix, relative-suffix and history printed as non-zero classes nobody is asked to clear;
(2) `dead_doc_links.py` reports 0 with the `:N` check live and `/tasks` no longer route-skipped by
design; (3) `decisions/` route claims are all either fixed or marked, 0 stale markers; (4) two
consecutive sweep PRs measured ≥95% fiction precision on fresh draws and PR 7 promoted the class —
**or** they measured less and PR 7 records the number and leaves it advisory (that is a valid end
state, written down); (5) the (b) and (d) queues are registered in `deferred-work.md` with their
re-measure commands, never their counts; (6) this brief is in `docs/roadmap/done/` and no tracked
file cites `plans/`.

### The arc closed 2026-09-22 — criterion by criterion

| # | Criterion | Closed on | How |
|---|---|---|---|
| 1 | `route_claims.py` reports 0 fiction, the near-miss classes printed | `6193a1bb1` (#1390) | six sweep PRs; the near-miss and history classes print non-zero and nobody is asked to clear them |
| 2 | `dead_doc_links.py` reports 0 with the `:N` check live | `6193a1bb1` (#1390) | the last 12 `[line]` rows, all in `decisions/`, resolved |
| 3 | `decisions/` claims fixed or marked, 0 stale markers | `6193a1bb1` (#1390) | standing contracts fixed against a reproduced successor, narrative marked `<!-- historical -->` |
| 4 | two draws ≥95% → promote, **or** record and leave advisory | #PR7 | **recorded**: 15/30 and 17/30, so the class stays advisory. `HEALTH_CHECKS.md § 9` carries the numbers, the FP classes across all three measured sets, and why the two biggest are grammar the scanner does not carry |
| 5 | the (b) and (d) queues registered with their re-measure commands | #PR7 | (d) → `history-in-code-sweep.md` gains the `--docs` half and the hand-off rule; (b) → a new `symbol-claims-in-docs.md`, `status: waits on the instrument` — an instrument PR is an M with its own review tail, so the follow-on arc's PR 1 builds it and the case file carries its method as the spec |
| 6 | this brief in `done/`, no tracked file cites `plans/` | #PR7 | moved, never copied; the prototype citations retensed onto the shipped instruments; `scripts/audit_untracked_refs.py` is the standing guard |

Two blind spots the arc measured and did not widen anything to cover, recorded as fact.
**A README beside code is outside every docs scanner's scan dirs** — those are `docs/`,
`.claude/skills/` and `CLAUDE.md`, so a README under `core/models/` or `scripts/` is read by
whoever opens that package and by nothing else. And **a doc's prose is outside `stale_names` by
design** — it reads fenced blocks and backtick spans only, so that a doc may narrate its past,
which means a sentence naming a gone directory without backticks is read by no pass at all. Both
are written up in [Symbol Claims in Docs](../symbol-claims-in-docs.md).

## 10. What this arc is NOT trying to fix

It is not an LLM-judged truth pass (no model reads a paragraph and votes), not a style or tense
rewrite of docs the scanners do not flag, not an `llms.txt/` or any new doc format, not a
re-litigation of `done/` vs `roadmap/` or of the ADR marker mechanism, not a symbol-claim gate, not
an example-execution harness, not a `status:` vocabulary, and not a cleanup of the
`history_in_code` queue in code. It proves absence of routes and lines mechanically, sweeps the one
class whose precision was measured, and hands the rest forward as ordered, re-derivable queues.

---

*Appendix — how the numbers were made, and where the machinery went.* Route catalog: a bare
`fast_app()` with `MagicMock()` services and `initialize_system_service` stubbed, catch-all
stripped → 891 paths at the time of measurement. Claims: the scanner over
`dead_doc_links.get_md_files()`, inline spans via `_inline_code_spans_by_line`, fences via
`iter_code_fence_blocks`. Samples: `random.sample` with the seeds named in § 2, classified by
reading the line and resolving each path in the catalog.

**The prototypes were superseded by the instruments PR 1 shipped** —
`scripts/health/route_catalog.py`, `scripts/health/route_claims.py`, the `:N` range check inside
`scripts/health/dead_doc_links.py`, and `scripts/history_in_code.py --docs` — and were deleted
with this arc; (b)'s census was never promoted, and its method is written up in
[Symbol Claims in Docs](../symbol-claims-in-docs.md). The per-class site lists live in the PR
bodies of #1379–#1390, each beside the commit it was measured on. **Every number in this file is
a reading of a commit that is now history.** Re-run the instrument before repeating any of them.
