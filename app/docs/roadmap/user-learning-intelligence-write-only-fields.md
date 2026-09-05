---
title: "UserLearningIntelligence Write-Only Fields"
updated: 2026-09-05
status: "ruling needed"
registered: 2026-08-28
trigger: "the owner's ruling, or the next touch of PsAdaptiveService"
check: "git grep -n \"intelligence\\.\" core/services/ps/ps_adaptive_service.py — assignments with no matching read"
---

# `UserLearningIntelligence` Write-Only Fields

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

`core/models/user/user_intelligence.py` lost its uid-sniffing "by domain" grouping and the
dead `EnhancedUserContext` that consumed it (never-sniff, ADR-013). What survives is read in
exactly two places: `PsAdaptiveService` reads `current_masteries` and calls
`get_dominant_learning_velocity()`. Every other field the loader
(`PsAdaptiveService._load_user_intelligence` / `_create_default_intelligence`) fills —
`active_learning_paths`, `completed_learning_paths`, `learning_preferences`,
`knowledge_recommendations`, `recent_search_queries`, `search_interests`,
`search_intent_patterns`, the three transfer lists, `intelligence_sources`,
`last_intelligence_update`, `intelligence_confidence` (and the `IntelligenceSource` enum that
only feeds one of them) — is written and never read. Their sources are gone (the search
archive and the `:LearningPreference` node were deleted earlier; the loader hard-codes
empties), so this is hollow shape, not staged foundation.

**Named work:** trim the dataclass to `user_uid` + `current_masteries` + the velocity reading;
drop the two LP queries the loader runs only to fill the unread path fields
(`_query_active_learning_paths` / `_query_completed_learning_paths` — check for other callers
first) and the `IntelligenceSource` enum; adjust the test factory. Or name a consumer.
**Trigger:** the owner's ruling, or the next touch of `PsAdaptiveService`.
**Named cost while parked:** two graph queries per adaptive-path call whose results nothing
reads; a dataclass that advertises intelligence it does not hold.
