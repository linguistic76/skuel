# Shelved: Explore Merge (2026-04-03)

Original versions of files before `/ku` + `/path-steps` were merged into `/explore`.

## What was shelved

- `ku_ui.py` — Full Knowledge index + detail page + search panel (884 lines)
- `path_steps_ui.py` — Full PathStep detail page (436 lines)
- `curriculum_hub_ui.py` — PathStep browser with Registered In / Available accordion (230 lines)

## Why

The `/ku` and `/path-steps` pages duplicated the "my stuff" role that `/library` already serves.
Both were merged into a single `/explore` discovery page where Ku and PathStep entities intermingle
in a bento card grid with unified search.

## What replaced them

- `adapters/inbound/explore_ui.py` — Unified explore index + detail pages
- `adapters/inbound/explore_routes.py` — DomainRouteConfig wiring
- Old GET routes now 301 redirect to `/explore`
- POST mutation endpoints (mark-studying, mark-understood, start, mark-read, bookmark) remain in the original files
