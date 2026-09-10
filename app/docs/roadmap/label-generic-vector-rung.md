---
title: "Label-Generic Vector Rung Has No Index for Most Domains"
updated: 2026-09-10
status: "open — a search-design decision, not a config change"
registered: 2026-09-10
trigger: "Next touch of the /search semantic rung, or the first report that 'Semantic boost' does nothing"
check: "grep the labels EmbeddingGeometry.INDEX_LABELS holds against the domains SearchRouter.advanced_search can scope to — every domain outside the tuple degrades silently"
---

# Label-Generic Vector Rung Has No Index for Most Domains

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

`SearchRouter._semantic_or_learning_search` computes its vector index from the
domain in scope:

```python
neo_label = NeoLabel.from_domain(entity_type)
label = neo_label.value
# → semantic_enhanced_search(label=…) / learning_aware_search(label=…)
# → Neo4jVectorSearchService.find_similar_by_vector
# → index_name = f"{label.lower()}_embedding_idx"
```

It runs when a request satisfies `has_semantic_boost()` or
`has_learning_aware()`, and the two reach it by different doors:

- **Learning-aware** is `enable_learning_aware` alone. It is a checkbox in
  `ui/search/components.py`, wired through `adapters/inbound/search_routes.py`
  into `SearchRequest`, and the route supplies the `user_uid` the branch
  requires — so it is reachable from the HTML `/search` form for **any domain in
  scope**.
- **Semantic boost** also needs `context_uids`, which the HTML form never
  supplies (`SEARCH_ARCHITECTURE.md` records this), so that half arrives only
  through the `/api/search/unified` JSON endpoint.

Either way the rung can ask for any of the twelve searchable domains, while
`EmbeddingGeometry.INDEX_LABELS` holds eight.

**Habit, Choice, Principle, Event, Exercise, RevisedExercise and UserEntry have
no per-label vector index.** For those domains the query returns nothing, the
rung falls through to standard search, and the user sees a toggle that is on and
doing nothing. It is graceful, silent, and indistinguishable from "the semantic
search found no better ordering".

## Why this is a design decision, not a config change

The obvious fix — add the missing labels to `INDEX_LABELS` — is wrong twice
over. It is seven more vector indexes on an AuraDB Free instance under a node
cap, and it is redundant: every one of those nodes is already `:Entity`, already
carries `embedding`, and is already in `entity_embedding_idx`. Per-label indexes
buy a narrower scan, not a different answer.

The shape that actually fits is the **`Entity` index plus an `entity_type`
filter** — one index serving every domain, which is why `Entity` is in the tuple
at all. That needs care the config change does not: the vector query has to carry
the type predicate without breaking the score normalization
`find_similar_by_vector` does per label, and `learning_aware_search`'s
`label != "Entity"` branch has to be reconciled with it rather than left as a
fallthrough.

## What was ruled here already

**Do not narrow `INDEX_LABELS`.** Task and Goal are in it *because* this rung
reads them. A 2026-09-09 measurement concluded the opposite — that nothing passed
`"Task"`/`"Goal"` as a vector-search label — and briefly removed both, plus added
their indexes to `drop_stale_indexes()`. The measurement was a name-grep for
`find_similar_*` call sites, and this rung's label is **computed**, so no grep for
a literal could have found it (Codex P1, PR #1308). Both were restored before
merge.

The general lesson is one the repo already carries: a dispatch that derives its
argument is invisible to a name search, and "no call site passes X" is only ever
as true as the search that produced it. Read the *path*, not the callers.
