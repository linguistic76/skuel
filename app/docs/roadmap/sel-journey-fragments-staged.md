---
title: "SEL Journey Fragments — staged behind a surface not yet designed"
updated: 2026-09-20
status: "staged — Mike's ruling 2026-09-20: PLANNED tier, not deletion"
registered: 2026-09-20
ruled: 2026-09-20
trigger: "A page that shows a learner their SEL journey or a per-competency curriculum grid is designed; or a second ruling deletes the fragments"
check: "grep -rn 'journey-html\\|curriculum-html' ui/ static/js adapters/inbound — a consumer outside adapters/inbound/path_steps_api.py retires the PLANNED entries"
---

# SEL Journey Fragments — staged behind a surface not yet designed

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

`GET /api/path-steps/journey-html` and `GET /api/path-steps/curriculum-html/{category}`
(`adapters/inbound/path_steps_api.py`) render `PsAdaptiveService.get_sel_journey` and
`get_personalized_curriculum` as HTMX fragments through `ui/patterns/curriculum_adaptive.py`
(`SELJourneyOverview`, `AdaptiveKUCard`, `SELCategoryCard`). Their JSON twins
(`/api/path-steps/journey`, `/api/path-steps/curriculum/{category}`) are the live API.

**No page loads the fragments.** The SEL pages that did were retired when SEL became a lens rather
than a domain (`27f6ef2a8`), and the `/ku` redesign (`143eed7f5`) dropped the last `hx_get`.
The route handlers are reachable by URL, so no liveness tool reports them; the record of their
consumer-less state is this file and the two `PLANNED_METHODS` entries in `scripts/detect_bloat.py`.

**What completes the entry:** a designed surface for the learner's SEL journey (the
`/path-steps` index or the `/explore/ps/{uid}` page are the candidates — both live) that loads
one of the fragments; wire it and delete the registry entries. The host page's contract is a
`#curriculum-list` element: a category card's "Continue Learning" button HTMX-loads that
category's `curriculum-html` fragment into it. **What retires it the other way:**
a ruling that the JSON twins are enough, after which the handlers, the UI module and the entries
go together under One Path Forward.

**Why staged, not deleted (ruled 2026-09-20):** the rendering is written and typed against the
live models, and a journey surface is the visible half of the adaptive service — deleting it
would make the next surface re-derive three components for the JSON the twins already return.
