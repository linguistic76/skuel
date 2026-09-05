---
title: "Catalog Copies in Code — the duplicated-fact defect, measured"
updated: 2026-09-05
status: "inventory — mechanical items unscheduled"
registered: 2026-08-29
ruled: 2026-08-29
trigger: "Mike schedules the mechanical items; ride-along on any PR adding a health check, an embeddable type, a vector-index label or a suppressible rule"
check: "uv run python scripts/detect_bloat.py --json → planned-marking-stale count; the scripts in dev § health) and the janitor loop are the same set"
---

# Catalog Copies in Code — the duplicated-fact defect, measured

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

The documentation lesson recorded across #1153, #1176 and #1184 — every summary line is a
duplicated fact, stale copies are paraphrases `git grep` cannot find, and re-syncing a copy is
not a fix — has an exact analogue in code. This section names the class, records what was
measured on `8030f8899`, and registers the remedies. **The mechanical items are not built**
(phase directive): the inventory is the deliverable, Mike schedules the rest. Done in this
registration: CLAUDE.md's four enumerations became pointers or rules, and two docs lost a
pairing the code never had.

**The class — a catalog copy.** A hand-maintained enumeration (map keys, a `subscribe()`
block, a runner's script list, a count or member list in prose) of a membership fact whose
truth is decided elsewhere in the tree. It is a duplicate by construction and rots when the
source changes in a diff the copy is not part of. **Rule for new code:** a second list of the
same members is the defect unless it is (a) derived from the first — `for x in SOURCE` — or
(b) covered by a drift test that *discovers* copies rather than naming them, or (c) marked
"not the full set — see SOURCE" where it sits. SKUEL's remedies, strongest first, each with a
live exemplar: derive the catalog (`EVENT_REGISTRY` in `core/events/__init__.py`), generate the
doc (`scripts/generate_graph_contract.py` → `docs/reference/GRAPH_CONTRACT.yaml`), drift-test
the copies (`tests/unit/test_metric_reference_drift.py`, `tests/unit/test_package_exports.py`,
`tests/unit/docs/test_content_origin_docs.py` — which discovers every tier table instead of
naming two), pin two literals to each other (`AuraDBCaps` ↔ `monitoring/prometheus/alerts.yml`).
A discipline a human must remember ("touch both files") is the weakest remedy, and it is what
most of the instances below rely on today.

**Measured instances** — each: the copies · what makes it drift · whether anything notices:

1. **The `./dev health` check set.** Copies: `dev` § `health)` and `dev`'s help line; five
   sites in `.github/workflows/weekly-janitor.yml` (the `for check in` loop, two `for name in`
   loops, the "All checks passed" prose, the "Reproduce locally" prose); the janitor row of
   `.github/workflows/README.md`; `docs/tools/HEALTH_CHECKS.md` § Overview and its
   § File Structure tree; and the `docs-skills-evolution` skill (SKILL.md's file-locations row
   and reference.md's table). Drifts when a check is added — **and it did, on 2026-09-01**:
   `docs_updated.py` landed and every copy above had to be edited by hand, which is the
   instance measuring itself. Three of them (the janitor row of `.github/workflows/README.md`,
   the skill's two) were NOT in the `updated:` section's "update all three" warning and would
   have been missed by anyone scoping from it; they were found by
   `git grep -l duplicate_headings`, which is the honest way to enumerate a copy set. Those
   three became pointers rather than lists in the same change — the rest still enumerate.
   Noticed by nothing:
   `tests/unit/scripts/test_quality_ci_parity.py` pins `run_quality_checks.py` ↔ `ci.yml` and
   is the exact precedent, but no test reads `dev` or the janitor. **Remedy — one source.**
   The janitor consumes a list `dev` prints (a `--list` mode; one bash array shared by the
   janitor's five sites is the fallback), and a parity test asserts every runnable
   `scripts/health/*.py` (has a `__main__` guard) is in that list or in a declared-exclusion
   dict with a reason (`mypy_suppressions.py` — its own weekly workflow). Delete the prose
   enumerations: "reproduce locally with `./dev health`" needs no member list.
   ⚠️ `scripts/health/markdown_fences.py` is a library with no `__main__`; a directory glob
   without that discriminator would demand it be run. ⚠️ `scripts/validate_cross_references.py`
   lives outside `scripts/health/` — the family is not a directory.
2. **`PLANNED_EVENTS` / `PLANNED_METHODS` / `PLANNED_TEMPLATES` in `scripts/detect_bloat.py`.**
   The registry is itself the copy of "staged and unwired". The detector already emits
   `planned-marking-stale` when a subject vanishes, gets wired, or is masked by a same-named
   backend method — but at INFO, and `--check` fails on WARNING only while the janitor body
   prints WARNING findings and PLANNED aging only, so **no automated reader ever sees a stale
   marking**. Measured: **2 stale on 2026-08-29** — `add_attendee` and `remove_attendee`,
   masked since #1119 introduced `self.backend.add_attendee(...)` on 2026-08-21, eight days
   unseen — and the Event-attendance section of this file said so too (both copies now point
   here instead). ✅ **BUILT (ruled + shipped 2026-08-29):** a stale marking is a `WARNING` and
   fails `--check`; the janitor prints both tiers. The masked case was measured to be **2 of the
   2** findings and is NOT staleness — see the ruling below.
   ✅ **BUILT (2026-08-29, readiness arc PR-3):** the registry now *points* at this file instead
   of restating it — `PlannedEntry.blocked_by` names the `##`/`###` heading (core text) whose
   section holds an entry's blocker; the detector reads this file on every run and a pointer at
   nothing is `planned-blocker-missing`, `WARNING`, fails `--check`, with a live sentinel test
   that fails on a heading rename before CI does. `HabitMissed` lost its restated constraints
   (one copy, here). The sibling-registry-key pointer form was NOT built — zero populators.
3. **Embeddable entity types.** Copies: `EMBEDDING_EVENT_TYPES` (13), `EMBEDDING_NODE_LABELS`
   (13), `EmbeddingWorker.subscribe()` (13 hand-written lines plus the two chunk events),
   `ENTITY_CONFIGS[…].embeddable` (11), `EMBEDDING_SCAN_LABELS` (derived ✓),
   `EMBEDDING_FIELD_MAPS` (16), and CLAUDE.md's "16 content-bearing". Mostly guarded by
   `tests/unit/services/ingestion/test_post_persist_embedding.py` — except that
   `test_event_map_mirrors_worker_subscriptions` pins the map to a **literal set inside the
   test**, never to the worker, so the worker is an unguarded fourth copy and the test literal
   a fifth. **Remedy (derive):** the worker subscribes `for cls in
   EMBEDDING_EVENT_TYPES.values()`; `EMBEDDING_NODE_LABELS` becomes
   `{t: NeoLabel.from_entity_type(t).value for t in EMBEDDING_EVENT_TYPES}` — two copies and
   two tests deleted. **Hollow entries:** `ENTRY_REPORT`, `FORM_TEMPLATE`, `FORM_SUBMISSION`
   carry field maps (since `9175bb708`) but no event, no label and no ingestion flag; the only
   other caller of `build_embedding_text` is `_rank_similar_entities` on the eight AI-bearing
   facades, so nothing ever builds text for them and the "16" faithfully restates a count three
   of which are dead. `./dev bloat` cannot see map entries. Deletion protocol: unwired → ask.
   ✅ **RULED + BUILT (2026-08-29 / 2026-08-30, readiness arc PR-4):** asked, ruled keep — the
   three hollow maps are registered in `PLANNED_EMBEDDING_MAPS`, joined by a new
   `ACTIVITY_REPORT` map (four declared-hollow, zero undeclared). `./dev bloat` now *derives*
   the hollow set (`set(EMBEDDING_FIELD_MAPS) - set(EMBEDDING_EVENT_TYPES)`, both dict literals
   read by AST) and the registry annotates it: an unregistered hollow map is
   `embedding-map-unregistered`, `WARNING`, fails `--check`; a registered key that gained an
   event class is masked, never stale. The advisory phantom-field check drove two map fixes
   on the day it landed — `ENTRY_REPORT` (`content`/`summary` exist, inherited, but both
   writers populate `processed_content`) and `HABIT` (`name` is no field). CLAUDE.md's "16" is
   a rule now (the map's keys are the list); the three other doc copies followed. The two
   derivations (worker `subscribe`, `EMBEDDING_NODE_LABELS`) remain unbuilt.
4. **Suppressible lint rules.** `SkuelLinter.SUPPRESSIBLE_RULES` has 21 members; the
   "Supported" lists in CLAUDE.md and `docs/patterns/linter_rules.md` both had 20 — **SKUEL033
   missing since it became suppressible on 2026-07-29 (#868)**, a month unseen.
   `linter_rules.md` called the set "drift-guarded by `TestSuppressibleRulesDrift`" — true of
   the set (code ↔ checker call sites), false of the doc's copy of it: **"drift-guarded" in
   prose names the guard's subject; check which two things it pins before trusting a doc's
   claim about itself.** Fixed here: CLAUDE.md's copy is a pointer, `linter_rules.md` re-synced
   once. **Remedy:** a docs drift test in the `test_content_origin_docs.py` shape that finds
   every "Supported rules" list and pins it to the set. Same family: CLAUDE.md's rule table
   carries 25 of the 32 live rules in `RULE_DOCS` (SKUEL002, 005, 006, 008, 009, 010, 018
   absent) — now labelled partial rather than pinned.
5. **Lateral relationship types.** `_LATERAL_TYPES` (17) and the generated
   `GRAPH_CONTRACT.yaml` `lateral` trait (17, drift-tested ✓) versus CLAUDE.md's "6 …
   `PREREQUISITE_FOR/DEPENDS_ON`" and `docs/architecture/RELATIONSHIPS_ARCHITECTURE.md`'s
   relationship-category table and "Phase 5 deployed types" line. `DEPENDS_ON` has never been
   in `_LATERAL_TYPES`: the inverse has been `REQUIRES_PREREQUISITE` since the lateral
   implementation landed (2026-01-31), and `LATERAL_RELATIONSHIPS_VISUALIZATION.md` calls
   `DEPENDS_ON` a deliberately separate scheduling edge — so both docs asserted a pairing the
   code never had. Fixed here (pairing corrected; CLAUDE.md's line replaced by the rule). The
   category table is a hand copy of the contract's traits whose **count column disagrees with
   its own row's name list** — count the backticked names per row against the number beside
   them: 8 of 14 rows disagreed on 2026-08-29 (Lateral said 13 and named 8) — two copies
   inside one row. Unmeasured against the enum row by row; do not correct one cell and call it
   done — the remedy is a pointer to the generated contract or a generated table.
6. **Vector-index label set.** `services_bootstrap/compose.py` creates six (`Entity`,
   `ContentChunk`, `ReferenceChunk`, `Ku`, `PathStep`, `LearningPath`);
   `scripts/create_vector_indexes.py` `PRIORITY_ENTITIES` names eight (adds `Task`, `Goal`);
   CLAUDE.md said eight. Three copies, two values; which the live graph holds is unverified
   (the local MCP tool reaches the stopped sandbox, not Aura — `SHOW VECTOR INDEXES` there
   settles it). Index *names* are safe: creation and query both compute
   `{label.lower()}_embedding_idx`. **Remedy:** one constant both importers read; CLAUDE.md's
   enumeration is deleted here.
7. **`EntityType → label`.** `_ENTITY_TYPE_TO_LABEL` in `core/models/enums/neo_labels.py`
   (25, the accessor's source), `ENTITY_TYPE_TO_LABEL` in `core/models/relationship_registry.py`
   (25 strings, one consumer: ingestion config), plus `EMBEDDING_NODE_LABELS` above. All agree
   today; nothing pins the two full maps to each other or to completeness (a missing key is a
   `KeyError` at first use, not at import). **Remedy:** derive both string maps from
   `NeoLabel.from_entity_type`.
8. **Vendored-asset versions.** `ui/theme.py` `HTMX_VERSION` / `ALPINE_VERSION` ↔
   `static/service-worker.js` `PRECACHE_URLS` ↔ the files under `static/vendor/`. In sync
   today (fourteen precache entries, all present); protected only by CLAUDE.md's "touches two
   files" warning — a discipline. A miss breaks `cache.addAll()` and service-worker install for
   every PWA client. **Remedy:** a pin test in the `AuraDBCaps` style — every `/static/`
   precache entry exists on disk, each `*_VERSION` appears in the precache list.
9. **Counts in prose — guarded, true, or now removed.** 25 EntityTypes, 14 statuses, 12
   searchable domains, 14 alert rules, 4 dashboards, 15 ingestion configs: measured true, and
   **none is pinned to the prose that states it** (no test asserts `len(EntityType) == 25`; the
   content-origin table is the only CLAUDE.md membership claim a test reads). "25" recurs
   across many docs; a 26th EntityType makes every copy stale — the cheap pin, if ever wanted,
   is `test_content_origin_docs.py`'s group-phrase pattern (assert the number in the phrase
   against the enum). Ruled leave. Alpine "22 shared / 26 total" was true but unpinned
   (`tests/unit/docs/test_alpine_docs_registry.py` derives the registry and pins the two
   complete-registry docs, not CLAUDE.md) and had drifted once before — replaced by the rule.
   CLAUDE.md's content-origin table stays: it is pinned. ⚠️ Measuring is itself a copy-reading
   act: the census regex for "Supported:" over-captured into the next sentence and reported a
   false extra rule — print the numbers, then check one by hand.
10. **Leave, by ruling** — the duplication is cheaper than any fix: `dev` help text vs its case
    labels (one drift today: `typecheck-strict` has no help line; one file, low harm);
    `HEALTH_CHECKS.md`'s file-structure tree (an `ls`; delete on next touch); root `AGENTS.md`
    (declares `app/CLAUDE.md` authoritative).

**RULED 2026-08-29 (Mike): yes — a stale PLANNED marking fails `--check`.** "If it renders as
stale it registers as a fail; we don't stale xyz." SKUEL026 parity: a registration that
registers nothing is a failure.

The objection that had recommended *advisory* — that the name-collision mask would force a
still-staged method out of the tier — was **not a reason to weaken the ruling; it was a
detector bug**, and measuring settled it: `planned-marking-stale` fired exactly twice, both on
the attendee pair, and both markings were **true** (the methods are still unwired; the only
production calls are the mixin's own `self.backend.add_attendee(...)`). So the fix was to make
"stale" mean stale, then gate on it:

- **Stale means exactly one thing: the subject is GONE** — the only fact the detector
  establishes without inference. It is a `WARNING` in all three tiers.
- **"Looks wired now" never gates.** Three Codex rounds on #1188 found the same defect in each
  tier in turn: a definition-site count catches only the def-side collision
  (`VultureScan.used_names` is global by attribute name, so one `x.name` load masks a single-def
  method); `_collect_rendered_template_ids` is receiver-blind, so `settings.get("<template_id>")`
  fabricates a became-live report; and publish resolution uses a file-scoped variable index plus
  class registries, so a sibling's publish resolves for every class in the registry. The pattern
  is not three bugs but one: **every liveness engine here over-approximates by design**, because
  the module's rule permits over-approximation only to SUPPRESS an accusation. Gating any
  became-live signal inverts it. All three now report `planned-marking-masked` (INFO) — printed
  in their own report block and by the janitor, never demanded.
- All seven `planned-marking-stale` emissions are `WARNING`, so `--check` (`./dev quality`
  check 7 + the CI lint job) fails on them, and the janitor's existing WARNING block prints
  them for free. A masked block was added beside it, because an INFO finding no reader prints
  is the defect this whole section is about.
- The gate landed **green**: true stale count is 0, masked count is 2.

**Build order if scheduled** — each is small; item 2 is DONE (above), the rest unscheduled:
~~the janitor floor for stale markings~~ → the health-check single source + parity test (the `updated:` guard's "update all three"
collapses to one edit) → the precache pin test → the three derivations (worker subscribe,
`EMBEDDING_NODE_LABELS`, `ENTITY_TYPE_TO_LABEL`; each deletes more than it adds) → the
suppressible-rules docs test → one vector-index constant. Do not build a same-file
contradictory-prose detector (sub-finding above) or a free-prose count checker: the count
claims that matter are pinned or gone, and "N things" in running text has no reliable anchor.
