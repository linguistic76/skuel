---
title: "Parked Features — Memory-Only Until Now"
updated: 2026-09-05
status: "parked"
registered: 2026-08-28
trigger: "Mike schedules each — feature work, never self-scoped"
check: "the four git grep absence checks in the case file, all empty"
---

# Parked Features — Memory-Only Until Now

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

Four feature-shaped threads Mike ruled *build later, from a stated design* — parked under the
2026-08 stabilize directive, and until this section recorded nowhere the repo could see. Each
row: what it is, the constraint already ruled, and a check that it is still absent. **Trigger
for all four: Mike schedules it** — none is a data threshold, and none may be self-scoped.

## Activity ledger (ruled 2026-06-11)
A cross-domain, event-grained, chronological feed ("Completed habit: Exercise · 2h ago") with
two consumers: a profile sibling to the recent-reports section, and the evidence input
`ActivityReport` generation synthesizes from. **Constraint:** design from the LIVE stores and
`{domain}.{action}` events (`dual_track_checkins`, habit completions, choice records) across all
6 Activity Domains at once; never restore the #286-deleted `get_recent_activity` (single-track,
proxy timestamps).
**Check:** `git grep -n -i "activity_ledger\|ActivityLedger" -- core/ ui/ adapters/` → empty.

## Interest signal + adoption/gravity — ONE thread (ruled 2026-06-11, unified 2026-08-22)
An interest-aware recommendation signal derived from live stores — `VIEWED` edge
recency/frequency, tags of engaged entities, or an embedding centroid of touched content —
feeding LP/content ranking. The ownership bundle deleted the four `HAS_*` "gravity" writers
(ADR-086 § 2); Mike ruled adoption/engagement is the SAME signal. **Constraint:** one engagement
signal, never two edges; never resurrect the #288 facet-affinity code (session-local by design)
or the retired gravity edges `HAS_TASK` / `HAS_GOAL` / `HAS_HABIT` / `HAS_EVENT` / `HAS_CHOICE` /
`HAS_PRINCIPLE` / `HAS_KU` (the live `HAS_*_TEMPLATE` family is a different edge and stays).
**Check** — two greps, both empty today: the new signal is absent, and no retired gravity edge is
a `RelationshipName` member (SKUEL030 makes that enum the only door to a Cypher edge, so the
member is the thing to watch, not free-text mentions — two comments still name the edges
historically):
`git grep -n -i "interest_signal\|engagement_signal\|facet_affinit" -- core/ ui/ adapters/`
`git grep -n -E '^\s+HAS_(TASK|GOAL|HABIT|EVENT|CHOICE|PRINCIPLE|KU)\s*=' -- core/models/relationship_names.py`
The same idea also survived as two reader-less members of the lowercase semantic vocabulary
(`RelationshipType.HAS_GOAL` / `.HAS_HABIT`, `core/models/enums/metadata_enums.py`) — deleted in
#1179; `git grep -n -E '^\s+HAS_(GOAL|HABIT)\s*=' -- core/models/enums/metadata_enums.py` → empty.

## Icon provider swap (ruled 2026-06-29)
`Icon()` (`ui/components/icon.py`) is a real chokepoint but its port leaks lucide's vocabulary —
126 `Icon("<lucide-name>")` literals on 2026-08-28, one `ICON_PATHS` registry, no provider
concept. **Design when wanted:** a semantic `IconName` StrEnum port; one generated registry per
provider with a `SEMANTIC_MAP`; `ICON_PROVIDER=lucide|heroicons` selected at startup like
`INTELLIGENCE_TIER`; the build assertion becomes "every adapter is total". **Constraint:** no
swap machinery before a second provider is actually wanted (One Path Forward); the silent-
fallback validation already shipped (#454/#455, `gen_icons.py::icon_name_literals`).
**Check:** `git grep -n "IconName\|ICON_PROVIDER" -- ui/ core/` → empty.

## Activity-templates re-homing (ruled 2026-07-06, shape undecided)
The 6 Activity Templates are PS-owned, TEACHER-gated, spawn instances on engagement, and are
invisible to search (not in `SearchRouter._SEARCHABLE_DOMAINS`,
`core/orchestrator/search_router.py:335`; absent from the `/search` Types facet). Mike ruled they
should be modelled/surfaced *somewhere of their own* and explicitly did not want a shape forced
yet. **Constraint:** a separate arc (not folded into search/nous work); entities stay orthogonal —
no coupling edges to make templates "belong". The adjacent question — should the Types facet do
content-discovery-by-domain? — is distinct and unruled.
**Check:** `git grep -n "_TEMPLATE" -- core/orchestrator/search_router.py` → empty (still
unsearchable); no templates hub under `ui/`.
