---
title: "Roadmap: /search facet redesign"
updated: 2026-08-26
status: complete
category: roadmap
tags: [roadmap, search, facets, ownership, curriculum, done]
---

# Roadmap: `/search` Facet Redesign

**Status:** ✅ **COMPLETE — 2026-08-26.** Ruled in full 2026-08-25 (#1153) after a code
trace of both search surfaces; built and closed the same week in six PRs.

**Nothing below remains open.** The one obligation the arc created — the profile-side
search that replaces what it stripped — is a live section of its own:
`../deferred-work.md` § "Profile-Side Search for UserEntry, Exercise and RevisedExercise".
This document is the closure record and is self-contained; it defers to nothing.

`/search` is now one surface with one job — *your lived activity, plus the knowledge
behind it*: the 6 Activity Domains + Ku, and nothing else.

## What shipped

| PR | What landed |
|---|---|
| #1155 | **Result scope** — `SEARCH_PAGE_ENTITY_TYPES` / `scope_to_search_page` (`adapters/inbound/search_routes.py`). Declared at the page's own entry point, never as an edit to `SearchRouter`'s shared sweep default: `/explore` and `/explore/library` ride the same `faceted_search`. |
| #1156 | **Primary facet control** — the Type dropdown is the 6 Activity Domains; `entityTypeFilters` (`static/js/skuel.js`) dropped `path_step`/`learning_path`/`user_entry`; the three vocabulary sites derive from each other (`tests/unit/test_search_page_scope.py`). |
| #1157 | **Knowledge mode** — the Nous facet drives the four knowledge filters; the two scope facets are mutually exclusive, enforced by `disabled` (htmx omits disabled controls, so the unused scope is *absent* rather than blank). |
| #1158 | **NOUS sub-topic vocabulary** — scoped to the curriculum domains `/search` returns (Ku alone). |
| #1159 | **Tag vocabulary** — widened to the page's FULL result set, per-user scoped for the OWNER_ONLY half. |
| #1160 | **Close the record** — D-LP graduated, tag ruling recorded, section marked ✅ RESOLVED. |

## The rulings — settled, do not re-open

1. **Removal is from the RESULTS, not just the filter.** A filter-only removal leaves an
   unfiltered search still returning rows no facet can reach. Encoded in
   `scope_to_search_page`'s docstring.
2. **UserEntry, Exercise and RevisedExercise leave `/search` for the profile hub.**
   Entries are lived *output* and are searched where they live. ⚠️ All **three** — a
   follow-up scoped to two would leave revision artifacts with no browser search at all.
   Mike sequenced it **strip first, build after**; the gap is accepted, and the build has
   its own live section.
3. **Type and Nous are MUTUALLY EXCLUSIVE.** `nous` is an array property only curriculum
   nodes carry, and the faceted sweep applies every property filter to *every* swept
   domain, so `Type=Task, Nous=body` returns zero **by construction**. The impossible
   state is made unreachable rather than allowed to return an empty page. The same fact is
   why knowledge mode is honest rather than cosmetic: a Nous topic narrows the result set
   to Ku on its own.
4. **The Nous facet keeps its name.** "Nous → Ku" was rejected: NOUS is the official
   *grouping* of Kus (a vault-derived vocabulary), not an entity-type label.
5. **D-LP: LearningPaths are NAVIGATED, not searched.** No browser surface finds an LP by
   typing — `/explore/library` carries Ku + PathStep only. Coherent rather than a hole
   because LP is reached by navigation: `/learning-paths`, `/pathways/browse`, and the
   `/lp/{uid}` detail page. Not data loss: `POST /api/search/unified` still reaches LP for
   programmatic callers. Defensible at 2 LearningPaths; if the corpus grows enough that
   people hunt for one by name, adding LP to the library catalog is still open — see the
   trap below.
6. **The tag facet covers every domain `/search` returns, per-user scoped** (Mike's option
   (a), 2026-08-26). The defect was the INVERSE of how the design first framed it: not "9
   dead curriculum options" but **six of seven result domains contributing nothing to
   their own dropdown** — nobody could filter by a tag on their own Tasks. `tags` is an
   `Entity` base field, so **a facet's scope follows the domains it filters**, which is why
   the tag scope is `SEARCH_PAGE_ENTITY_TYPES` and not the `SEARCH_PAGE_FACET_DOMAINS` the
   NOUS vocabularies take.
7. **`/askesis` is not a search surface, so it takes the WIDEST honest vocabulary — it
   stays MERGED.** In Mike's words: *"Askesis is not the /search result set… Askesis has
   access to everything about the user with some transparent and adjustable boundaries."*
   The general rule outranks this one facet: **never derive an Askesis scope from what a
   page lists.** See `ASKESIS_ARCHITECTURE.md`.
8. **Pagination and the match count are DROPPED — `/search` is top-N** (Mike, 2026-08-28;
   #555 closed won't-build). Search runs one page-only query and never counts the match
   set, so the header said `Found 20 results` for any ≥20 matches and pagination never
   rendered (`total_pages` was always 1). Counting would have cost a second query per search
   plus a three-protocol contract change, for a browsing affordance a find-the-thing tool
   does not need. The header now says `Top N results` for a full page and `N results` for a
   short one; `SearchResponse.total` stays as the API's page size (`total_count`), documented
   as such; `get_page_info` / `has_more_pages` / `_render_pagination` are gone.

## Where the mechanisms are documented

The arc's durable contracts live in the architecture docs and the code, not here:

| Contract | Authority |
|---|---|
| Facet vocabularies scope by the same `SearchVisibility` declaration through a different builder; fail-closed per domain | `SEARCH_ARCHITECTURE.md` § Ownership Scoping → *Facet vocabularies*; `@skuel-search-architecture` key rule 6b |
| The two mutually-exclusive scope facets, and the Tags facet that is not one | `SEARCH_ARCHITECTURE.md` § UI Mapping (Simple Search) |
| A surface's result scope is not `_SEARCHABLE_DOMAINS` | `SEARCH_ARCHITECTURE.md` § Searchable Entity Types |
| Facet scope is DERIVED (`SEARCH_PAGE_FACET_DOMAINS = CURRICULUM_FACET_DOMAINS ∩ SEARCH_PAGE_ENTITY_TYPES`), never a fourth site | `search_routes.py` (the constant's own comment) |
| `/search` has TWO doors onto the sub-topic control — a render GATE and the OPTIONS — and both take the same scope | `search_routes.py` § `/search/subtopics`; `tests/unit/test_nous_subtopic.py` |
| `'ku'` is a filter-GROUP entry, never a dropdown value | `static/js/skuel.js`; `tests/unit/test_search_page_scope.py` § 7 |
| Scope-change ordering in the browser (Alpine effects, HTMX-owned dependent controls) | `@ui-browser` skill § *Scope changes and stale dependent controls* |
| Measuring a facet vocabulary | `@skuel-search-architecture` § *Measuring a facet vocabulary* |

## The one trap kept — it re-arms if LP joins the library catalog

Adding LP to `/explore/library` is **not "one list literal"; the card renderer must move
too.** `render_explore_card` (`ui/explore/cards.py`) branches on `is_ku` and sends
**everything else** to a hard-coded "Path Step" pill and `/explore/ps/{uid}`, so every LP
would render as a mislabelled Path Step card with a dead detail link (LPs live at
`/lp/{uid}`). The fix is available rather than new: `entity_detail_href`
(`ui/patterns/entity_links.py`) already maps `learning_path` → `/lp` — adopt the shared
helper instead of widening a two-way branch to three, and give the pill a real per-type
value. The library's subtitle ("Explore all knowledge units and path steps") matches its
catalog exactly, so it changes with the catalog. **This warning also lives as a comment at
`render_explore_card` itself**, which is where whoever breaks it will be reading.

## What it cost, measured

Every figure below was taken by **driving the method that builds the vocabulary** through
the composed `SearchRouter`, never with hand-written Cypher — the arc paid for that lesson
twice (see `@skuel-search-architecture` § *Measuring a facet vocabulary*).

⚠️ **A dated snapshot, not a contract.** These decay as the vault grows; re-measure rather
than quote. Live graph 2026-08-26 (corpus: 121 Ku, 25 PathStep, 10 of them draft):

| Vocabulary | Merged | Effect of the scoping |
|---|---|---|
| NOUS topics | 11 | none — the topic facet was already Ku-only |
| NOUS sub-topics (flat / the render gate) | 33 | none |
| NOUS (topic, sub-topic) pairs (the options) | 81 → 78 | 3 dead options removed: `(body, attention)`, `(body, habits)`, `(self-awareness, breath)` |
| Tags | 181 → 172 anonymous | the 9 PathStep-only options left; the six Activity Domains' own tags joined, per user |

Tag vocabulary by caller: `/explore/library` **181** (unchanged) · `/search` anonymous
**172** · `user_linguistic76` **175** · `user_admin` **182** — and the two tag-carrying
users' additions are disjoint, so neither sees the other's.

⚠️ **A per-vocabulary count is not a per-facet count.** Every sub-topic *word* appears on
some Ku, but three *pairings* were PathStep-only — which is why the flat-list row and the
pair row disagree.

**The predicted cost arrived and was accepted, not overlooked.** Option (a) was ruled
knowing the activity tags include machine and typo tags; `user_linguistic76`'s three
additions are `Dr`, `period:daily` and `period:weekly`, visible to that one user until the
vault tags are cleaned. A data-quality item, not a facet defect.

## Two latent fail-opens found on the way, both closed in #1159

- `build_distinct_values_query` tested `if user_uid:`, so an **empty-string uid fell
  through to the corpus-wide branch**. Now `is not None`. The failure direction of a
  multi-tenant scope key must be "shows nothing", never "shows everyone".
- It scopes on `user_uid` specifically while `build_search_visibility_clause` honours
  `DomainConfig.ownership_property` (Group declares `owner_uid` — ADR-086). A domain
  declaring another property would have been filtered on one it does not write — its tags
  returned for nobody, silently. The router now **refuses** such a domain rather than
  guessing.

## Left standing on purpose

The **"Relevance"** fiction — three behaviours under one label, none of them BM25. Not
relabelled, not removed: Mike's intent is to make the label *true* rather than tidy it
away. It moved with its owner to `../deferred-work.md` § "Domain-level fulltext-first text
search (D1(b) follow-on)", the live section that would make it true.
