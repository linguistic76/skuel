---
title: "Roadmap: the ownership bundle (ADR-085 / ADR-086)"
updated: 2026-08-26
status: complete
category: roadmap
tags: [roadmap, ownership, search, attendance, neo4j, done]
---

# Roadmap: The Ownership Bundle

**Status:** ✅ **COMPLETE — 2026-08-21**, four PRs (#1118–#1121). Ruled and built the same
week after #1116 found the `HAS_*` legs of `get_recent_activities` had matched nothing since
the initial commit.

**Nothing below remains open.** The one thing the bundle left staged — the `ATTENDS`
attendance surface — is a live section of its own: `deferred-work.md` §
"Event Attendance Wiring (`ATTENDS`) — Staged Build", with its obligations recorded in
ADR-086 § 3 and § Follow-ups. This document is the closure record for the three
`deferred-work.md` sections the bundle retired, and is self-contained.

The contract itself lives in the two ADRs, which are the authority and stay live:
[ADR-085](../../decisions/ADR-085-ownership-read-enforcement-contract.md) (read
enforcement) and [ADR-086](../../decisions/ADR-086-universal-owns-and-attends-attendance.md)
(universal `:OWNS`, attendance is `ATTENDS`).

## What shipped

| PR | What landed |
|---|---|
| #1118 | **The two ADRs** — ADR-085's read-enforcement contract (two chokepoints only, never a third mechanism) and ADR-086's universal `:OWNS` + `ATTENDS` design. |
| #1119 | **The write-side collapse** — the paper `HAS_*` residue deleted, attendees retargeted onto `ATTENDS`. |
| #1120 | **The read-side gap census G1–G7** + `IntelligenceRouteFactory` fail-fast. |
| #1121 | **`Group` `ownership_property` declaration + the `User.uid` uniqueness constraint.** |

Predecessors, for anyone tracing how it was surfaced: #1116 (the `:OWNS` traversal fix) and
#1117 (the attendance-ownership ruling recorded against the staged attendee surface).

## 1. The `:OWNS` write side — what was deleted

Deleted outright by #1119, each site re-enumerated before deletion (the full list is
ADR-086 § 2): the registry `ownership_relationship` field and its paper
`HAS_*`/`MADE_REFLECTION` enum family — **zero such edges ever existed in the graph** —
`UnifiedRelationshipService.create_user_relationship` / `delete_user_relationship`, the
backend generic pair in `_user_entity_mixin.py` (the one interpolation that could write a
`HAS_*` edge), and the four gravity writers
(`create_user_goal/habit/principle/event_relationship`).

`is_ownership_relationship()` now traits `OWNS` alone, and the regenerated
`GRAPH_CONTRACT.yaml` stopped documenting never-written edges as "ownership".

⛔ **Never resurrect the `HAS_*` family.** Adoption/gravity — "this user has pulled this
entity into their orbit" — is a real semantic and *not* ownership; if SKUEL wants it, it
returns as its own named edge with its own design (ADR-086 § 2, which holds that note).

**Correction recorded while retiring the section:** its original claim that faceted search
"hard-anchors `(User)-[:OWNS]->`" was stale as of #1079 — `faceted_search_raw` is
property-scoped and fail-closed (`has_user=True`). The actual `:OWNS` readers today are the
MEGA-QUERY/CONSOLIDATED anchors (`user_context_queries.py`), `get_user_entities`, the GDPR
cascade, and one `SCOPE_AWARE` disjunct.

## 2. `User.uid` gained a uniqueness constraint

The open question — index or *uniqueness constraint*? — resolved to a **uniqueness
constraint** (ADR-086 § 4): `uid` is the identity key (`user_<name>`), and the constraint
doubles as the seek index. `sync_auth_indexes` (`neo4j_schema_manager.py`) creates
`User_uid_unique` as startup DDL, idempotent per boot (`IF NOT EXISTS`).

**Applied to the live graph 2026-08-21** (AuraDB `d2d160c4`), re-measured first: 6 users,
zero duplicate `uid`s, zero null `uid`s — built cleanly, by running the real
`sync_auth_indexes` path. Verified post-apply:
`EXPLAIN MATCH (u:User {uid:$uid})-[:OWNS]->(e:Entity)` plans
`NodeUniqueIndexSeek [UNIQUE u:User(uid)]` where it had been `NodeByLabelScan`. The ~290
`MATCH (:User {uid: $…})` adapter call sites all inherit the seek.

⚠️ **Counting trap**, preserved for anyone re-measuring those call sites: the f-string
spelling (`User {{uid:`) and the plain spelling (`User {uid:`) are **disjoint substrings**.
Grepping one undercounts by ~2×.

## 3. `GroupService` declared `OWNER_ONLY` on a model with no `user_uid`

Surfaced 2026-08-16 by Codex on #1079; closed by the ruling's **option 1** (ADR-086, arc
contract ruling 7). `DomainConfig` gained a **configurable ownership property** —
`ownership_property` (default `"user_uid"`, identifier-validated at construction and again
at the composition point) — and the `OWNER_ONLY` branch of
`build_search_visibility_clause` now renders `n.{ownership_property} = $user_uid`. The
declaration threads from `DomainConfig` through the service search mixin and
`get_visible_to_user` into every strategy builder, riding with `search_visibility`.
`GroupService._config` declares `ownership_property="owner_uid"` — the scoping claim its
model can finally render.

**What deliberately did NOT change:**

- Group stays absent from every search registry — wiring it in remains a product decision,
  and `test_group_is_not_a_searchable_domain` still pins that.
- No `user_uid` was added to `Group`; the two-names-for-one-claim divergence (#1078) closed
  the other way.
- Exercise's `owner_uid` half stays inside `SCOPE_AWARE` — its exemption is earned by that
  declaration, and the exemption set still asserts its own length. **Do not add Group to it.**

The guard was tightened per the contract:
`TestOwnerOnlyDomainsCarryTheScopingProperty::test_every_searchable_owner_only_domain_declares_a_real_property`
asserts every searchable `OWNER_ONLY` domain's **declared** property exists on its model.
Doc truth-up rode along in `docs/architecture/SEARCH_ARCHITECTURE.md` § Ownership Scoping.
