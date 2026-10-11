---
title: "Explore Sidebar Entity Graph — the Reading Pages' Centred View"
updated: 2026-10-11
status: "staged"
registered: "2026-09-30 (F4b — curriculum lateral reads check the anchor)"
ruled: "2026-10-10 — the founder: not for now; stage it with a case file (not built, not deleted)"
trigger: "a Ku or PathStep reading page wants the Explore sidebar graph centred on the entity it shows"
check: "git grep -n -E 'current_uid=|current_entity_type=|lateral/graph\\?[^\"]*types=' -- adapters ui static"
---

# Explore Sidebar Entity Graph — the Reading Pages' Centred View

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

## What exists

- **The sidebar's entity mode.** `render_explore_sidebar_page` (`ui/explore/nav.py`) takes
  `current_uid` and `current_entity_type` (`'ku'` or `'ps'`). With both set, the sidebar graph
  (`ExploreGraphView`, `ui/explore/graph.py`) opens in entity mode — centred on that Ku or
  PathStep — instead of hub mode (the learner's own studying Kus and in-progress steps). The
  same two values mark the current item in the sidebar's lists.
- **The client half.** The `exploreGraph` Alpine component (`static/js/skuel.js`) reads
  `mode`, `entity_uid` and `entity_type`; in entity mode it loads
  `GET /api/{ku|ps}/{uid}/lateral/graph?depth=2` and centres the network on the entity.
- **The server half.** `LateralRouteFactory`'s graph route
  (`adapters/inbound/route_factories/lateral_route_factory.py`) serves that URL for all nine
  lateral domains, curriculum anchors included, behind the anchor check. It also takes
  `?types=` — a comma-separated `RelationshipName` list. With
  `types=REQUIRES_KNOWLEDGE,ENABLES_KNOWLEDGE` it is the knowledge-dependency view: an
  undirected walk, so the graph shows prerequisites and dependents around the centre.

## What no page does

The one caller of `render_explore_sidebar_page` (`explore_ui.py`, the library page) passes
neither `current_uid` nor `current_entity_type`, so the sidebar always opens in hub mode. No
page or script sends `types=` to the graph route. The entity mode and the knowledge-dependency
view are complete on both sides and are reached by nothing.

## Staged, not retired

The founder ruled it staged on 2026-10-10. Building it means one change on the Ku and PathStep
reading pages (`/explore/ku/{uid}`, `/explore/ps/{uid}`): render them inside the Explore
sidebar with `current_uid` / `current_entity_type` set. That is a layout move on the two
reading pages, so it is a UI change — verify at 375px. Sending `types=` for a
knowledge-dependency toggle is a separate choice for the same session.
