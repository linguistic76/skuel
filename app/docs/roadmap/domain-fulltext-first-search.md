---
title: "Domain-level fulltext-first text search (D1(b) follow-on)"
updated: 2026-09-05
status: "ruled deferred (twice)"
registered: 2026-08-16
ruled: 2026-08-25
trigger: "a consumer wants relevance-ranked text search for the domains left on /search — the 6 Activity Domains + Ku"
check: "product need; read both rulings first — scope INVERTED, the OWNER_ONLY blocker is already closed"
---

# Domain-level fulltext-first text search (D1(b) follow-on)

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

Deferred 2026-08-16 from the fulltext/hybrid wiring arc (D1 ruling: SearchRouter rung now,
domain-level later). The rung gave Ku/PathStep/LearningPath relevance-ranked hybrid search on
`/api/search/unified` (FULL tier) — and **only** there. Every other text-search caller,
including the `/search` browser page, still runs `CONTAINS`.

**What the rung actually buys — corrected 2026-08-16, verified against Neo4j 2026.06.0.**
PR #1074 claimed the paths it did not reach run *case-sensitive* `CONTAINS`. They do not.
Both production `CONTAINS` predicates lower-case both sides — `faceted_search_raw`
(`toLower(entity.{field}) CONTAINS $query_text`, param pre-lowered) and
`build_text_search_query` behind `text_search_raw`
(`toLower(n.{field}) CONTAINS toLower($query)`). The single case-SENSITIVE predicate in the
persistence layer is `_SearchMixin.search` (`_search_mixin.py:224-227`), whose only
production caller is `PsAiService.search_by_semantic_query`'s embedding-failure fallback —
it is on neither `/search` nor `/api/search/unified`. So the honest value of moving a
surface to fulltext is **relevance ranking and vector recall**, NOT case-insensitivity,
which every surface already has. Two further measured facts bound the case:

- **No stemming.** The 14 shipped indexes carry Neo4j's default `standard-no-stop-words`
  analyzer (`_create_fulltext_index` emits no `OPTIONS`), so `run` does not match
  "Running". An `english` analyzer stems, but `CREATE ... IF NOT EXISTS` matches on
  *schema* as well as name and silently skips an existing index — changing an analyzer
  needs an explicit DROP + recreate + reindex, not a config edit.
- **Lucene loses substring matching.** It matches whole tokens: `photosyn` and `synthesis`
  both return nothing for a "Photosynthesis explained" title that `CONTAINS` matches. Any
  fulltext-first path must therefore keep a `CONTAINS` fallback that fires on **thin**
  results, not only empty ones — the shipped rung originally short-circuited on any hybrid
  hit and lost those matches; fixed by `_backfill_with_contains` (2026-08-16), which tops a
  short rung page up and is the shape any new path should copy.

The follow-on, in rough order of value:

- **The `/search` HTML page.** The shipped rung sits in `_execute_advanced_search`, reached
  only from `advanced_search()` — the `/api/search/unified` JSON endpoint. The browser page
  runs `faceted_search`, a separate path still on `CONTAINS`, so the highest-traffic search
  surface has not changed. Reaching it means either routing the faceted path through the
  same rung or giving `faceted_search` its own; decide which when a consumer asks.
- **`_search_mixin.search` goes fulltext-first with CONTAINS fallback** — makes every caller
  of domain search index-backed and the "Cypher-first search foundation" claim true. Requires
  threading each domain's `SearchVisibility` into the fulltext Cypher (OWNER_ONLY domains need
  `user_uid` scoping the current label-wide fulltext path does not have — the reason this half
  was split off). The gating helpers (`NeoLabel.fulltext_index_name`, `escape_lucene_query`,
  the publication-gated `query_fulltext_index`) already exist.
- **CORE-tier text story** — fulltext needs no embeddings, so a fulltext-only rung (skip the
  vector half) would give CORE-tier relevance-ranked search too. Decide whether that lives in
  the mixin (above) or as a CORE branch of the SearchRouter rung.
- **Exercise** — SCOPE_AWARE visibility (curriculum scope public, owned scopes via
  OWNS/SHARES_WITH/group membership) needs the same user_uid threading, plus Exercise has no
  vector index (add it alongside, or run fulltext-only).

**Enable when**: a consumer wants relevance-ranked text search beyond the curriculum
domains on `/api/search/unified` — the `/search` page included. Product need, not a
data threshold.

## Ruled DEFERRED twice — read this before scoping it a third time

**Ruling 1 (2026-08-16, in the arc that wrote this section).** The trigger was tested
against the value case and did NOT fire: there is no named consumer, and the corrected
value case above (ordering gain, recall regression, no stemming without an analyzer
migration) does not clear "product need" on a surface that already works. The only
recognized work that investigation produced was the partial-result fallback regression on
the already-shipped rung, which shipped as `_backfill_with_contains` (#1077). The five
decision points (`/search` reach · service-layer mixin · CORE tier · Exercise · UserEntry)
were scoped with recommendations but deliberately left undecided — they are the inherited
shape for whenever the trigger fires, not a backlog.

**Ruling 2 (2026-08-25) — the usage census, which was never taken before.** Every
`:SearchEvent` in the live graph, read whole (the population is small enough to enumerate,
so this is a census and not a sample):

| Measure | Value |
|---|---|
| Total events since logging shipped 2026-07-10 | **41** |
| Entry point `faceted` (the `/search` page + `/explore` catalog) | **41** |
| Entry point `advanced` (`/api/search/unified`) | **0** |
| Genuine human queries (rest are July test probes `a`, `x`, `zzz_no_such_thing_xyz`) | **~8** — `breath` ×6, `body` ×2 |
| Most recent search of any kind | **2026-07-22** |

⚠️ **`faceted` is TWO surfaces, and the telemetry cannot separate them.** Both
`search_routes.py` (`/search`) and `explore_ui.py` (`/explore` + `/explore/library`) call
`faceted_search()` without overriding `entry_point="faceted"`, so every row above is one
or the other. The `domains` stamp does not discriminate either: it is populated only when
`_resolve_single_domain` finds a SINGLE domain, and the library always sends
`[KU, PATH_STEP]` (two) while `/search` defaults to All Types — so both emit `domains=[]`.
All 8 genuine queries carry `domains=[]`, `filters=None`, i.e. an unfiltered text box on
one of the two. **Do not attribute the 8 to `/search` specifically.** A distinct
`entry_point` for the library calls is a one-argument fix if surface-level attribution
ever matters — and it would have to land BEFORE any post-redesign usage comparison,
since it cannot be backfilled. (Raised by Codex on #1153.)

So **the surface the shipped rung serves has never been used in production**, and the two
faceted surfaces together have had ~8 real queries. Corpus at the same date:
121 Ku · 25 PathStep · 2 LearningPath · 14 Exercise · 77 Task · 62 UserEntry. Relevance
ordering over ≤20 `CONTAINS` hits drawn from a 121-node Ku corpus is a marginal
difference, not a fix.

**The valuable half has INVERTED — do not scope from the bullet list above.** The
`/search` facet redesign ([`done/search-facet-redesign.md`](done/search-facet-redesign.md))
removed PathStep and LearningPath from that surface entirely; it shipped 2026-08-26 in
#1155–#1160. The shipped rung covers
exactly Ku/PathStep/LearningPath — two of the three are now gone from the page — while the
six Activity Domains promoted to the primary facet are all `OWNER_ONLY`, i.e. the half this
section split off as harder: it needs `user_uid` threaded into the fulltext Cypher.
Anything built for curriculum relevance would now rank two domains the page no longer
returns.

⚠️ **The OWNER_ONLY half is CHEAPER than the 2026-08-16 investigation assumed — its
blocking finding is stale.** That investigation recorded a symmetric difference between
two ownership mechanisms (`faceted_search_raw` anchoring `MATCH (:User)-[:OWNS]->(entity)`
vs `build_search_visibility_clause` matching the `user_uid` property) and called
reconciling them a required ruling. **The ownership-bundle work closed it**:
`faceted_search_raw` no longer reads the `:OWNS` edge — it passes `visibility` to
`build_search_visibility_clause` like every other strategy, and
`test_search_visibility_scoping.py::test_owner_only_emits_the_property_predicate_not_an_owns_match`
pins that the anchor MATCH is gone (`":User" not in query`). One mechanism, one
composition point. Do **not** re-open that ruling — it was already made. (Caught by Codex
on #1153, where this section first restated the stale fact.)

## The "Relevance" label is this section's lever — a known fiction, left standing

Inherited from the `/search` facet redesign, which deliberately did NOT repair it
([`done/search-facet-redesign.md`](done/search-facet-redesign.md)) and left it with the
section that would make it true. `/search`'s sort dropdown offers **"Relevance"**, it is
the DEFAULT, and no path behind it ranks by text relevance. What it actually does depends
on the request shape — three behaviours under one label, none of them BM25:

| Request shape | What "Relevance" does |
|---|---|
| **Single domain** (a Type choice, or a facet resolving to one domain) | `RELEVANCE.get_sort_field()` returns `None` → the backend falls back to the domain's `search_order_by DESC`. Here it IS "Recently Updated" for Ku/PS/LP, "Newest First" for the Activity Domains, event-date for Events — two dropdown entries, one behaviour. |
| **Cross-domain, pure text, no facets** (the default landing shape) | `wants_faceted` is False → `search_domains` (`max(5, limit//6)` per domain — **5** at the default page size of 20, not 3), then a sort by `combined_score` — which is **0.0 for every row**: `_wrap_results` sets neither `relevance_score` nor `priority_score`, and both default to `0.0`. The sort is stable, so it is a **no-op** that preserves domain-iteration order, each domain's block still internally `search_order_by DESC`. It is called "the scored sweep" in the code comments; nothing scores it on this path. |
| **Cross-domain with any facet/tag/relationship filter** | `_faceted_sweep`, then `zip_longest` **round-robin interleave** across domains — not ordering by anything. |

⚠️ Do not restate this as a flat "Relevance means recency" — that is true only of the
single-domain row, and #1153 shipped that overstatement before Codex corrected it. The
defect is that one label covers three behaviours and advertises a fourth.
`ui/explore/cards.py` already excludes RELEVANCE from the library's
sorts *deliberately*, for a different reason (it bypasses the pageable sweep), so `/search`
is the inconsistent surface. This is the same class the July 2026 pass deleted ("no fake
options") — but it is **left in place on purpose**: Mike's intent is to make the label
true — that is the work below, scoped to the domains that remain — rather than to relabel
it away. Do not "tidy" it in a passing PR; that would spend the one lever that makes the
ranking work visible.

**Enable when** (unchanged in kind, sharpened in target): a consumer wants relevance-ranked
text search for the domains that remain on `/search` after the facet redesign — **the six
Activity Domains and Ku**, which since #1155 is the whole surface: UserEntry, Exercise and
RevisedExercise were ruled off it (see `done/search-facet-redesign.md` ruling 2). The
rule, not the list, is the contract: every domain visible on `/search` is either in D1(b)'s
scope or has Relevance disabled for it — so a domain re-added to the page re-opens this,
and the same rule applies to whatever profile-side surface those three land on. Product
need, not a data threshold.
