---
title: "Catalog Copies in Code — the duplicated-fact defect, measured"
updated: 2026-09-11
status: "closed — every remedy built or ruled; nothing open"
registered: 2026-08-29
ruled: 2026-09-10
trigger: "none — item 5 ruled (a) and built 2026-09-10; items 9 and 10 are ruled leave"
check: "uv run pytest tests/unit/scripts/test_health_check_parity.py tests/unit/ui/test_vendored_asset_pins.py tests/unit/test_vector_index_labels.py tests/unit/docs/test_suppressible_rules_docs.py; uv run python scripts/detect_bloat.py --json → planned-marking-stale count"
---

# Catalog Copies in Code — the duplicated-fact defect, measured

*Completed record. This was the case file for a [deferred-work.md](../deferred-work.md) entry of the same name; the entry left the MOC when the last remedy was ruled and built on 2026-09-10.*

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
   **It drifted-by-hand a second time on 2026-09-09**, adding `secret_scan_floor.py`:
   nine edits across six files (`dev` ×3 — the health block, a `health-secrets` target
   and the help line; `weekly-janitor.yml` ×4; `HEALTH_CHECKS.md` ×3; the skill's
   table). The copies were found the honest way again, by `git grep -l
   duplicate_headings`. Nothing caught the addition automatically — same instance,
   same cost, two data points now. **And the copy list above was itself incomplete:**
   the skill's SKILL.md carried a SECOND enumeration — a `./dev health-*` command block,
   distinct from the file-locations row this entry names — which nobody had updated since
   at least 2026-09-01. It was missing `health-updated`, `health-xref` AND `health-mypy`
   before this change, so it had been silently stale across a prior addition and was
   found only by hand-checking each listed site while writing this note. Converted to a
   pointer (2026-09-09), like its three siblings. **This is the enumerate-vs-discover
   argument measuring itself a second time** — item 4 below records the same shape, where
   a discovering drift test found a third copy on arrival. An inventory of copies is a
   catalog copy too, and this one under-counted by one for eight days.
   Noticed by nothing:
   `tests/unit/scripts/test_quality_ci_parity.py` pins `run_quality_checks.py` ↔ `ci.yml` and
   is the exact precedent, but no test read `dev` or the janitor.
   ✅ **BUILT (2026-09-09).** `dev` holds ONE `HEALTH_CHECKS` array
   (`name|script|tier|message|help`); the `health` block, a single `health-*)` dispatcher and
   the help block all read it, and `./dev health --list` hands the tier-`health` rows to the
   janitor, which now enumerates nothing (an empty roster is a could-not-measure, never a
   green week). Nine hand-edits collapse to one. `tests/unit/scripts/test_health_check_parity.py`
   pins it from four directions — the array parses AND `--list` is *executed*; every runnable
   `scripts/health/*.py` is registered or exempted with a reason; the janitor names no
   health-tier script; and every documented copy equals the array. Both traps are pinned as
   their own tests: `markdown_fences.py` (a library, no `__main__`) must NOT be demanded, and
   the roster must keep a member outside `scripts/health/`. Three by-hand mutations were used
   as positive controls. Doc copies: `HEALTH_CHECKS.md`'s command block is the one surviving
   copy and is pinned (added to ci.yml's `py` filter so a docs-only PR still runs the pin);
   the skill's two and `documentation-freshness.md`'s System 2 became pointers; the
   file-structure tree became a companion-scripts table.
   **A fourth and fifth copy surfaced on arrival, both stale** —
   `docs/user-guides/documentation-freshness.md` carried a five-target command block AND a
   six-row Quick Reference table, each missing three checks, and the skill's `reference.md`
   held a five-line block plus a six-row table that never had `validate_cross_references.py`.
   The inventory above named neither pair. The first draft of the detector globbed *fenced
   blocks* and missed the table; keying on **contiguous lines** instead found both shapes.
   That is the enumerate-vs-discover argument measuring itself a third time in this one file.
   Two `ALLOWED_OCCURRENCES` entries in `stale_names.py` died with the deleted prose and were
   removed — the anchored text was gone, so the exemption exempted nothing.
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
   a rule now (the map's keys are the list); the three other doc copies followed.
   ✅ **BUILT (2026-09-09):** both derivations. `EmbeddingWorker.subscribe()` iterates
   `EMBEDDING_EVENT_TYPES.values()` (the two chunk events stay explicit — no `EntityType`, own
   queue), and `EMBEDDING_NODE_LABELS` is a comprehension over that map through
   `NeoLabel.from_entity_type`. The literal set inside
   `test_event_map_mirrors_worker_subscriptions` — which pinned the map to the *test*, leaving
   the worker an unguarded fourth copy — is replaced by a test that DRIVES `subscribe()`
   against a recording bus, so the assertion is about what the worker does rather than about
   two lists agreeing.
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
   ✅ **BUILT (2026-09-05, linter-hardening arc PR-4):** `tests/unit/docs/test_suppressible_rules_docs.py`
   discovers every "Supported rules:" list under `CLAUDE.md`, `docs/` and `.claude/skills/` and
   pins each to `SkuelLinter.SUPPRESSIBLE_RULES` (both directions; explicit ids only — range
   notation is refused, not expanded). It found a third copy on arrival —
   `docs/guides/LINTER_GUIDE.md`, in range notation and four members stale — which is the
   enumerate-vs-discover argument measuring itself; both lists now carry the 24 members.
5. **Lateral relationship types.** `_LATERAL_TYPES` (17) and the generated
   `GRAPH_CONTRACT.yaml` `lateral` trait (17, drift-tested ✓) versus CLAUDE.md's "6 …
   `PREREQUISITE_FOR/DEPENDS_ON`" and `docs/architecture/RELATIONSHIPS_ARCHITECTURE.md`'s
   relationship-category table and "Phase 5 deployed types" line. `DEPENDS_ON` has never been
   in `_LATERAL_TYPES`: the inverse has been `REQUIRES_PREREQUISITE` since the lateral
   implementation landed (2026-01-31), and `LATERAL_RELATIONSHIPS_VISUALIZATION.md` calls
   `DEPENDS_ON` a deliberately separate scheduling edge — so both docs asserted a pairing the
   code never had. Fixed 2026-08-29 (pairing corrected; CLAUDE.md's line replaced by the rule,
   and the Lateral row now points at the generated contract).

   **MEASURED 2026-09-09 — the remaining defect is not the one this entry described, and it is
   bigger.** The entry said to "count the backticked names per row against the number beside
   them". That reading is wrong: the column is headed **Examples**, so a row naming four of
   eighteen is not disagreeing with itself. What the measurement actually found:

   - `RelationshipName` has **172 members**; the section's own headline says **"80+"**.
   - The table has **14 groups whose counts sum to 115**. The enum has **~28 banner sections
     holding 162 members** (the rest sit under no banner), and the two taxonomies do not
     correspond: the doc has `Curriculum` and `Life Path` rows with no matching section, while
     the enum has `AUTHENTICATION`, `ACTIVITY TEMPLATE`, `EVIDENCE`, `INTERACTION` and more
     with no matching row.
   - The enum's banners are **prose comments, not a taxonomy** — several are edge shapes
     (`(PathStep)-[:EMBEDS_FORM]->(FormTemplate) …`), not group names, and one
     `Parent-Child Composition` banner spans 28 members across several domains.

   So there is **nothing machine-readable to derive a table from**, which is why this was never
   a cell fix. The remedy is a ruling between three options, and it is Mike's:
   **(a)** delete the Count column and keep the table as examples, pointing the membership
   question at `GRAPH_CONTRACT.yaml`; **(b)** give `RelationshipName` a real `group` trait and
   generate the table from it via `scripts/generate_graph_contract.py` (a code change, and the
   only option that makes the counts true and keeps them true); **(c)** replace the table
   wholesale with a pointer. Whichever is chosen, the `"80+"` headline goes with it — as a
   pointer, not as `"172"`, which is the same copy with a fresher date.

   ✅ **RULED (a) + BUILT (2026-09-10).** The Count column is gone, the fourteen rows are
   labelled an orientation aid rather than a partition, and both the headline and the
   membership question now point at the generated `GRAPH_CONTRACT.yaml`, which already carries
   all 172 members (with the traits each one has — 55 carry any) and is drift-tested. The row overlap is stated where the
   table sits (`ULTIMATE_PATH` is both an ownership and a life-path edge), so the grouping
   cannot be read as a set partition.

   **(b) was priced and declined on a measurement.** The nine trait predicates on the enum
   cover **55 of 172** members; 117 have no trait at all. They are behavioural sets that code
   branches on, not a taxonomy — `is_knowledge_relationship()` returns 9 where the doc's
   Knowledge row said 18. Building (b) meant inventing a grouping for 172 members, necessarily
   multi-valued, whose only reader would be a doc table, and teaching a YAML generator to emit
   markdown into a hand-written architecture doc. A code-level fact manufactured to justify a
   doc is this file's own defect running backwards; the nine traits that exist earned their
   place by having code readers.

   **No discovering drift test is buildable for this fact, and that is the ruling** — the same
   shape as item 6's, reached the same way, by trying to build one and measuring the corpus:

   - `[:NAME]` edge syntax across `docs/`: 659 occurrences, **104 non-members in 38 files**.
     The noise is structural, not stale: placeholders (`REL_TYPE`, `X`, `R`, `HAS_`), ADR
     history, deliberate counter-examples in `linter_rules.md`, staged proposals in roadmap.
   - Backticked UPPER_SNAKE tokens in the 64 files that mention `RelationshipName`:
     overwhelmingly env vars, config constants, status values and Cypher keywords.
   - A header-marker test keyed on `| Group | Count | Examples |` matches **exactly one table
     in the tree** — enumeration wearing a discovery costume, which is the trap this file's
     § 1 and § 4 each recorded.

   Either real corpus needs the fail-silent suppressor list item 6 already ruled against, so
   the doc copy here is pointer-shaped and labelled-partial (remedy (c) of the rule above),
   not pinned.

   **Two live defects the entry had not named, both found by re-measuring rather than by
   re-reading it:**
   - **`FOR_GROUP` in the Exercise/Group row was not a member** — retired by ADR-053 and
     removed from the enum, so the table advertised a dead edge for roughly five months.
   - **The "extended types … not yet wired to Phase 5 UI endpoints" line was false for three
     of its six.** `ENABLES`, `CONFLICTS_WITH` and `STACKS_WITH` each have a dedicated POST
     route (`/api/ku/{uid}/lateral/enables`, `/lateral/conflicts` on Events/Choices/Principles,
     `/api/habits/{uid}/lateral/stacks`). The line is now a pointer at the two route sources
     that decide it, naming only the genuinely writer-less types.

   **And the pairing this entry recorded as fixed was fixed in one place of two.** The
   2026-08-29 correction reached the Lateral row and CLAUDE.md, but the *Dependency
   relationships* table three sections down still gave `PREREQUISITE_FOR`'s inverse as
   `DEPENDS_ON` — the same false pairing, in the same document, surviving the change that
   claimed to remove it. Corrected here. **A correction is a copy set too: grep the claim, not
   the cell you were shown.**

   ⚠ **A name-keyed check would have called a live edge dead.** `LATERAL_ENABLES` and
   `LATERAL_ENABLED_BY` are the only two members whose Python name differs from the value they
   write (`ENABLES`, `ENABLED_BY`), and the doc names the *value*. A first pass keyed on
   `.name` reported the doc's `ENABLES` as a non-member and nearly published it as a finding;
   the corpus scan that cleared it was keyed on `.value`. The trap is now stated in the doc
   beside the tables that use the wire names.
6. **Vector-index label set.** `services_bootstrap/compose.py` created six (`Entity`,
   `ContentChunk`, `ReferenceChunk`, `Ku`, `PathStep`, `LearningPath`);
   `scripts/create_vector_indexes.py` `PRIORITY_ENTITIES` named eight (adding `Task`, `Goal`);
   CLAUDE.md said eight. Three copies, two values. Index *names* were never at risk: creation
   and query both compute `{label.lower()}_embedding_idx`.
   ✅ **BUILT (2026-09-09):** `EmbeddingGeometry.INDEX_LABELS`, read by both importers, pinned
   by `tests/unit/test_vector_index_labels.py` (every member a real `NeoLabel` — SKUEL030
   cannot see through the interpolation, and Neo4j answers an unknown label with an empty
   index rather than an error). **The value is the union, eight** — the de-duplication changes
   which *list* decides, never which indexes exist.

   ⚠️ **A first attempt set it to six and was wrong.** The reasoning was: nothing passes
   `"Task"`/`"Goal"` as a vector-search label, so those two indexes have no reader. That came
   from grepping `find_similar_*` call sites — and the reader is
   `SearchRouter._semantic_or_learning_search`, which computes its label as
   `NeoLabel.from_domain(entity_type)` for whatever domain the request scopes to, behind the
   `/search` **Semantic boost** and **Learning-aware** checkboxes. **A computed argument is
   invisible to a name grep**, so no search for a literal could have found it, and
   "no call site passes X" was only ever as strong as the search behind it. Caught by Codex
   (P1, #1308) before merge; both labels restored and the `drop_stale_indexes()` entries
   removed. The same read turned up a real defect that outlives this item — the rung can
   request a label for any of twelve domains while eight indexes exist — now registered as
   `deferred-work.md` § Label-Generic Vector Rung Has No Index for Most Domains.

   **A fourth doc copy was found in review** — the `neo4j-cypher-patterns` skill's index
   inventory advertised eight vector indexes and named Task/Goal as script-only additions;
   it and CLAUDE.md are pointers at the constant now.
   **Doc copies here are pointer-shaped, not pinned, and that is a ruling:** a discovering
   check ("every `<label>_embedding_idx` a doc names must be a live index") would need an
   exclusion list for `docs/migrations/` and `docs/roadmap/done/`, whose sample terminal
   output legitimately records indexes that no longer exist. A suppressor list fails silent,
   which is worse than the pointer.
7. **`EntityType → label`.** `_ENTITY_TYPE_TO_LABEL` in `core/models/enums/neo_labels.py`
   (25, the accessor's source), `ENTITY_TYPE_TO_LABEL` in `core/models/relationship_registry.py`
   (25 strings, one consumer: ingestion config), plus `EMBEDDING_NODE_LABELS` above. All
   agreed, but nothing pinned the two full maps to each other or to completeness (a missing
   key was a `KeyError` at first use, not at import).
   ✅ **BUILT (2026-09-09):** `ENTITY_TYPE_TO_LABEL` is a comprehension over `EntityType`
   through `NeoLabel.from_entity_type`. Deriving over the *enum* rather than a key list is
   what buys completeness: a new `EntityType` is covered on arrival, and a missing `NeoLabel`
   mapping is now an import-time failure instead of a first-use `KeyError`.
8. **Vendored-asset versions.** `ui/theme.py` `HTMX_VERSION` / `ALPINE_VERSION` ↔
   `static/service-worker.js` `PRECACHE_URLS` ↔ the files under `static/vendor/`. In sync
   (fourteen precache entries, all present), but protected only by CLAUDE.md's "touches two
   files" warning — a discipline. A miss breaks `cache.addAll()` and service-worker install for
   every PWA client.
   ✅ **BUILT (2026-09-09):** `tests/unit/ui/test_vendored_asset_pins.py` — every precache entry
   resolves on disk, and every `/static/` URL `theme.py` builds from a `*_VERSION` both exists
   and is precached. Two mutations (dropping a precache line; bumping a version alone) were run
   as positive controls. The third direction found the reader-less copy: **`CHARTJS_VERSION`
   said `"4"` beside a vendored Chart.js 4.5.1 and had no consumer at all** — a version
   constant that could not drift into a broken precache because nothing read it. Deleted rather
   than exempted, and the "every constant builds a URL" assertion is what keeps a new one from
   arriving stillborn. `CACHE_VERSION` stays a discipline by design: it must be bumped for ANY
   `/static/` change, precached or not, which no membership test can express.
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

**Build order — COMPLETE (2026-09-09).** ~~the janitor floor for stale markings~~ →
~~the health-check single source + parity test~~ → ~~the precache pin test~~ → ~~the three
derivations (worker subscribe, `EMBEDDING_NODE_LABELS`, `ENTITY_TYPE_TO_LABEL`)~~ →
~~the suppressible-rules docs test~~ → ~~one vector-index constant~~. Every item deleted more
than it added. Still deliberately NOT built: a same-file contradictory-prose detector
(sub-finding above) and a free-prose count checker — the count claims that matter are pinned
or gone, and "N things" in running text has no reliable anchor.

**Nothing remains open.** Item 5 was ruled (a) and built on 2026-09-10 — the last mechanical
remedy — and its measurement produced a second ruling worth as much as the build: *no
discovering drift test is buildable over relationship names in prose*, because the only two
corpora that could carry one are dominated by placeholders, ADR history and deliberate
counter-examples. That lands item 5 where item 6 already sits: pointer-shaped doc copies by
ruling, not by omission. Items 9 and 10 are ruled leave.

**One thing the build changed about the inventory itself.** Three of the six remedies found a
copy the inventory had not named: the health roster had two more (both stale), and the
vendored-asset pin found a version constant with no reader at all. Every one was found by a
*discovering* check on its first run, never by re-reading the list. An inventory of copies is
a catalog copy — this file's own § 1 already recorded under-counting by one for eight days, and
the pattern held for two of the three remaining instances. The rule that follows: when a remedy
is built, let the discovery run before trusting the entry's copy set.

**Trigger fired and was deferred — 2026-09-09 (Mike), then scheduled the same day.** The
frontmatter `trigger` said to ride the remedy along on any PR adding a health check.
`secret_scan_floor.py` was such a PR (#1303) and the ride-along was **not** taken: the
credential one-path arc was mid-flight with a written 3-PR contract, and no health check was
added by its remaining two PRs, so the catalog could not drift again before the arc closed —
waiting carried zero drift risk while interleaving would have delayed the arc's highest-risk
change (`SKUEL_CREDENTIAL_BACKEND=env` in `.env.production.example`, without which the parked
production deploy breaks on unpark).

That was logged because a `trigger` with no firing history reads as never-tested: it had fired
**twice** (2026-09-01, 2026-09-09) and been taken **zero** times, and the note said a third
miss would be the signal to schedule directly or retire. There was no third miss — the whole
build order was scheduled directly, hours later, once the credential arc closed. **The
ride-along was the wrong vehicle and the log is what showed it:** the remedy touches `dev`, a
workflow, four docs and a skill, which is not a rider on someone else's PR. The frontmatter
`trigger` now names the one remaining remedy (item 5) and the touch that should carry it.

**The remedy needed no re-derivation when scheduled**, which is the note's own payoff: item 1
named the shape (`dev --list`, janitor consumes it, parity test over runnable
`scripts/health/*.py`), both traps (`markdown_fences.py` has no `__main__`;
`validate_cross_references.py` lives outside `scripts/health/`) and the third `dev` copy (the
`health-<name>` targets, collapsed into one `health-*)` dispatcher). All four survived contact
with the build unchanged. The one thing the note could not have known is above: the copy set
was short by two.
