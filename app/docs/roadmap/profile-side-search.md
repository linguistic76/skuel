---
title: "Profile-Side Search for UserEntry, Exercise and RevisedExercise"
updated: 2026-09-05
status: "parked"
registered: 2026-08-26
trigger: "Mike schedules the build half — the strip already landed"
check: "all THREE domains, not two; done/search-facet-redesign.md holds the arc's rulings"
---

# Profile-Side Search for UserEntry, Exercise and RevisedExercise

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

The one obligation the `/search` facet redesign created. Closure record for the arc itself:
[`done/search-facet-redesign.md`](done/search-facet-redesign.md) (#1155–#1160) — read it
before scoping this; do not re-derive its rulings.

That arc took **UserEntry, Exercise AND RevisedExercise** off `/search` — from the results,
not just the dropdown — on the ground that entries and exercises are lived *output*, and
are searched where they live: the profile hub (`/profile`: Activities · Curriculum ·
Submissions · Reports). Mike sequenced it **strip first, build after**, so the gap is
accepted rather than overlooked. This section is the build half.

⚠️ **All THREE domains, not two.** RevisedExercise is a distinct searchable domain and the
arc sent it to the profile hub alongside Exercise; a build scoped to two would leave
revision artifacts with no browser search at all. (Codex caught the two-name version of
this very row on #1160.)

⚠️ **That search does not exist yet, in any form.** The Submissions tab is four link
buttons, `/submissions/history` renders an unfiltered list, and the Reports tab is
collapsible card sections. `user_entry_ui.py`, `user_entry_routes.py` and
`user_entry_api.py` contain zero search references, and the journals sidebar's search is
conversation sessions, not entries. Exercise search happened ONLY through the old
unfiltered `/search` sweep. Accepted cost while the gap stands: 62 entries, ~8 genuine
searches ever across both `faceted` surfaces.

**The ranking question travels with the entries — it is answered here, not in D1(b).**
UserEntry would have inherited `/search`'s fake Relevance label (its `search_order_by` is
`created_at`). The 2026-08-16 investigation's D5 recommended *excluding* UserEntry from any
fulltext path on the merits: recall matters more than ordering when searching your own
writing, and Lucene's substring loss bites hardest there ("that entry where I mentioned
photosyn…"), on top of it being a privacy line. That pulls against wanting relevance at
all, and the tension is real — **either UserEntry joins D1(b)'s scope, or Relevance is
disabled for it specifically.** D1(b)'s contract is a rule and not a list precisely so this
answers itself: every domain visible on a surface is either in that scope or has Relevance
disabled for it, and that applies to whatever this build puts on `/profile`. (Raised by
Codex on #1153.)

**Enable when**: Mike schedules it — the strip already landed, so the trigger is the build
half: a product decision, not a data threshold. When Reports gains a search box, the
**EntryReport / ActivityReport Search** section above has had its trigger fired and is
scoped with it.
