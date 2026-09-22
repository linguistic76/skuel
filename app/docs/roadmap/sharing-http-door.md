---
title: "Sharing HTTP Door — Operations on Existing Shares"
updated: 2026-09-22
status: "staged — ruled 2026-09-21: PLANNED tier for five methods, two deleted, never a second share form"
registered: 2026-09-21
ruled: 2026-09-21
trigger: "the first multi-user deployment, or the next sharing-fan-out touch (the same trigger as § Vault Re-Sync Never Retracts a Share — one door closes both); set_visibility separately waits on the PUBLIC reader (a portfolio listing)"
check: "grep -rn 'unshare\\|get_shared_with(\\|get_groups_shared_with\\|set_visibility' adapters/inbound ui core/services --include='*.py' — a production caller outside core/services/sharing/ retires that method's PLANNED entry in scripts/detect_bloat.py"
---

# Sharing HTTP Door — Operations on Existing Shares

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

`UnifiedSharingService` (`core/services/sharing/unified_sharing_service.py`) has two halves.
The **write half is live**: audience-at-submit ([ADR-054](../decisions/ADR-054-user-entry-unified-submissions.md)
— `AudienceResolver.resolve_and_share` → `share` / `share_with_group`, fed by the `/submit`
form's audience selector, the `/upload` YAML door and a vault note's `audience:`), the
post-submit `POST /api/form-submissions/share`, and the ADR-040 auto-shares
(`ExerciseService` → `share_with_group`). The **reads that render what those wrote are live**:
`/profile/shared` (`get_shared_with_me`), the groups hub (`get_user_entries_shared_with_group`,
`get_user_entry_shared_with_group`), the teacher review queue (`get_review_queue_by_groups`)
and `check_access` on EntryReports. The other half — *see* who has access, *retract* a share,
*change* visibility after the fact — has service methods, unit and integration tests, and no
door of any kind. [ADR-038 § API Layer](../decisions/ADR-038-content-sharing-model.md) records
the six endpoints that once existed; they left with the submissions API on 2026-04-17.

## The ruling, per method (2026-09-21, census on `6193a1bb1`)

| Method | Production callers | Ruling | Why |
|---|---|---|---|
| `unshare` | 0 (6 test sites) | **PLANNED** — `_SHARING_REVOKE_AND_ACCESS_LIST` | The revoke half of the access list, and the operation share reconciliation on re-sync needs — one method, two consumers, neither built. |
| `unshare_from_group` | 0 (1 test site) | **PLANNED** — same entry | Group twin. `scripts/retract_defaulted_vault_note_shares.py` hand-rolls its own `DELETE` because it sweeps every owner's edges at once; the service's owner check is right for the door and wrong for the sweep. |
| `get_shared_with` | 0 (3 test sites) | **PLANNED** — same entry | The owner's "who has access" list — the read half of revoke; you cannot retract what you cannot see. |
| `get_groups_shared_with` | 0 — its one caller left on 2026-04-18 (`7dc89f3fd` replaced it with the auto-share intersection query); two test fixtures still mocked it, removed with this ruling | **PLANNED** — same entry | Group twin of the access list. |
| `set_visibility` | 0 (9 test sites) | **PLANNED** — `_SHARING_VISIBILITY_LADDER` | Its trigger is the PUBLIC reader, not the access list — see [The visibility ladder](#the-visibility-ladder-waits-on-a-reader-not-a-panel). |
| `verify_shareable` | 0 (3 test sites) | **DELETED** | A pure rule (`_check_shareable`, a staticmethod of status + entity type) behind a DB round-trip for inputs every caller already holds. Every mutation applies the rule inside `_verify_owned_and_shareable`; none of the six historical endpoints exposed a standalone check. Its backend twin `query_shareable_status` went with it. |
| `get_shared_with_me_via_groups` | 0 (0 test sites) | **DELETED** | A third listing of `SHARED_WITH_GROUP`. Members read per group (`get_user_entries_shared_with_group` — the groups hub); owners read across groups (`get_review_queue_by_groups` — the review queue). Its shape would not serve the one consumer it could have had, a group half of `/profile/shared`: no subject-context join, no sharer attribution, ordered by `entity.created_at` rather than the edge, owner excluded by property (`entity.user_uid <>`) rather than the `:OWNS` edge. That half, if ever wanted, is a new query modelled on `query_shared_with_me`. Backend twin `query_shared_with_me_via_groups` went with it. |
| public-portfolio listing | never existed | **the reader `set_visibility` waits on** | Nothing lists `visibility = 'public'` — not a route, not a search clause. Named here so the trigger has a name. |

Rulings are registered as `PLANNED_METHODS` entries in `scripts/detect_bloat.py` (`blocked_by`
→ this file's heading); the two deletions are `DELETED` rows in `scripts/health/stale_names.py`.

## What the door is — and what it must not be

**Audience-at-submit is THE sharing write path** (ADR-054). The audience is declared when the
entry is created and resolved into `SHARES_WITH` / `SHARED_WITH_GROUP` edges by
`AudienceResolver`; a vault note re-declares it on every re-sync. The door this file stages is
**an operation on those existing edges, never a second way to create them**:

1. **The access list with revoke controls**, on the owner's entity page: `get_shared_with` +
   `get_groups_shared_with` render who has access; `unshare` + `unshare_from_group` retract one
   grant. Where on the page, and in what shape, is not designed — that is the `DELAYED`.
2. **Share reconciliation on vault re-sync**: diff the note's declared `audience:` against the
   entry's live edges and retract the ones no longer declared, through the same two revoke
   methods. This is the fix for [§ Vault Re-Sync Never Retracts a Share](vault-resync-never-retracts-a-share.md)
   — the two items are one missing operation seen from two doors, and share a trigger.

A "share with user / share with group" form on a detail page — the panel the 2026-06-13 ruling
sketched — would be a parallel write path to audience-at-submit. SKUEL does not duplicate a
surface: if a post-hoc *widening* is ever wanted, it is the same audience declaration re-run
(what a vault re-sync already does), not a new form.

## The visibility ladder waits on a reader, not a panel

`Visibility` (`core/models/enums/metadata_enums.py`) is `PRIVATE → SHARED → TEAM → PUBLIC`.
What the graph actually does with the property, verified on `6193a1bb1`:

- **Written at creation only.** `UserEntryService.create_entry` stores
  `request.visibility or PRIVATE`; the `/submit` form's `audience=public` and the vault door's
  `audience: public` both map to `PUBLIC`, TEACHER-gated at both doors. A vault re-sync
  refreshes every property (the living-entry `upsert`), so a note that narrows
  `audience: public` → `private` **does** return to `PRIVATE` on the property — while its
  edges stay (the gap above).
- **Read by one non-owner path.** `check_access` honours `PUBLIC`, and `SHARED` only together
  with an edge; its one production caller is `UserEntryOrchestrator` on EntryReports, whose
  writer sets `'shared'` in the same statement as the edge. The report-history queries exclude
  `'private'`. That is the whole reader set.
- **The search visibility clause is edge-only.** `build_search_visibility_clause`
  ([ADR-085](../decisions/ADR-085-ownership-read-enforcement-contract.md)'s chokepoint) admits
  by `:OWNS`, `:SHARES_WITH` and `MEMBER_OF ← SHARED_WITH_GROUP`; it never tests the property.
  So `SHARED` as a property is inert (the edge decides), `PUBLIC` reaches no listing and no
  search, and `TEAM` has no writer and no reader anywhere (ADR-040 records it as reserved).
- **The UI already stages the public rung as "Coming soon".** The `/submit` form's Portfolio
  destination renders disabled (`portfolio_mode="coming_soon"`; no caller passes `active`), so
  `audience=public` at the API is reachable only by a hand-built POST or the vault door.

Therefore a visibility selector today would write a value that nothing honours for anyone but
the owner — a control that names a state the system does not have. `set_visibility` completes
**with the PUBLIC reader**: a portfolio listing (the successor to the public-browse endpoint
ADR-038 § API Layer records as retired), which is also what turns the Portfolio destination on. `SHARED`
never needs the selector (audience-at-submit writes the edge); `PRIVATE`-from-`PUBLIC` is the
unpublish, and is the one transition that is the selector's own.

## Named cost

Until the door exists, a share is write-once: an owner cannot see who has access to an entry
and cannot take a grant back, and a narrowed `audience:` retracts nothing on re-sync. On the
founder vault that is a curiosity; with a second user it is a leak class, which is why the
trigger is the first multi-user deployment.
