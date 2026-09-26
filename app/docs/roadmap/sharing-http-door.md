---
title: "Sharing HTTP Door — Operations on Existing Shares"
updated: 2026-09-26
status: "staged — the revoke half shipped 2026-09-25 (Submit & Share arc PR 6b: Share + Stop sharing on a UserEntry, Your wall as the access list); set_visibility alone stays PLANNED, waiting on the PUBLIC reader"
registered: 2026-09-21
ruled: 2026-09-21
trigger: "set_visibility waits on the PUBLIC reader (a portfolio listing); the re-sync half dissolves with R9's drafts (Submit & Share arc PR 8)"
check: "grep -rn 'set_visibility' adapters/inbound ui core/services --include='*.py' — a production caller outside core/services/sharing/ retires its PLANNED entry in scripts/detect_bloat.py"
---

# Sharing HTTP Door — Operations on Existing Shares

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

> **2026-09-25 — Amended by [ADR-088](../decisions/ADR-088-submit-and-share.md) (Submit & Share arc,
> PR 6b).** The revoke half has its door: `POST /api/user-entries/{uid}/share` and `/unshare`
> (`EntrySharingService`), the Share panel on the owner's `/gradebook/{uid}` page, and *Your wall*
> on `/profile/shared` — the owner's access list with × Stop sharing on every chip. `unshare` and
> `unshare_from_group` are live; the two access-list methods (get_shared_with,
> get_groups_shared_with) are deleted, replaced by `get_shared_by_me` (the wall's one query,
> narrowed to one entry for the Share panel). The 2026-09-21 "never a second share form" ruling
> is superseded by R2 ("anyone may share anything, any time"): the Share panel IS a post-create
> share door, and it speaks the same vocabulary through the same checks and writers as
> audience-at-submit. What remains below is the `set_visibility` half.

`UnifiedSharingService` (`core/services/sharing/unified_sharing_service.py`) has two halves.
The **write half is live**: audience-at-submit ([ADR-054](../decisions/ADR-054-user-entry-unified-submissions.md)
— `AudienceResolver.resolve_and_share` → `share` / `share_with_group`, fed by the Submit page's
(`/submissions/submit`) audience selector, the JSON door and a vault note's `audience:`), the Share door
(`EntrySharingService.share`, the same checks and writers on an entry the owner already has),
the post-submit `POST /api/form-submissions/share`, and the ADR-040 auto-shares
(`ExerciseService` → `share_with_group`). The **reads that render what those wrote are live**:
`/profile/shared` (`get_shared_with_me` — *Shared with you*; `get_shared_by_me` — *Your wall*),
the groups hub (the same reader narrowed by `via`; a listed entry opens at `/gradebook/{uid}`
through `UserEntryService.get_visible_to_user` under `read_visibility` OWNER_OR_AUDIENCE —
ADR-088 §5) and the teacher review queue (`get_review_queue_by_groups`); an EntryReport is an
owner read (ADR-088 §3 — the access check that once admitted a non-owner on `SHARED` + a link
is retired). The **revoke half is live** (`unshare`, `unshare_from_group` behind
`POST /api/user-entries/{uid}/unshare`). The one thing without a door is *changing* visibility
after the fact. [ADR-038 § API Layer](../decisions/ADR-038-content-sharing-model.md) records
the six endpoints that once existed; they left with the submissions API on 2026-04-17.

## The ruling, per method (2026-09-21, census on `6193a1bb1`)

| Method | Production callers | Ruling | Why |
|---|---|---|---|
| `unshare` | **LIVE** since PR 6b — `POST /api/user-entries/{uid}/unshare` (a *Your wall* chip's ×) | shipped | The revoke half of the access list. Takes the recipient by username (the vocabulary's `user:<username>`), no co-membership needed. Re-sync reconciliation never needed it — R9's drafts (PR 8) dissolve that case. |
| `unshare_from_group` | **LIVE** since PR 6b — the same door with a `group:<uid>` value | shipped | Group twin. Touches `SHARED_WITH_GROUP` only; a feedback request to the same group stands (ADR-088 §2). `scripts/retract_defaulted_vault_note_shares.py` still hand-rolls its own `DELETE` because it sweeps every owner's edges at once. |
| get_shared_with | 0 | **DELETED** (PR 6b) | The owner's "who has access" list is *Your wall* — `get_shared_by_me` returns every owned entry with its people and groups, and narrows to one entry for the Share panel. A per-entity access-list query beside it would drift from the wall's. Backend twin query_shared_with_users went with it. |
| get_groups_shared_with | 0 — its one caller left on 2026-04-18 (`7dc89f3fd` replaced it with the auto-share intersection query) | **DELETED** (PR 6b) | Group twin of the access list, replaced by the wall's `groups` column. Backend twin query_groups_shared_with went with it. |
| `set_visibility` | 0 (5 test sites) | **PLANNED** — `_SHARING_VISIBILITY_LADDER` | PUBLIC-only since ADR-088 §4 (publish / unpublish; it still lacks the TEACHER gate the creation doors apply). Its trigger is the PUBLIC reader, not the access list — see [The visibility ladder](#the-visibility-ladder-waits-on-a-reader-not-a-panel). |
| `verify_shareable` | 0 (3 test sites) | **DELETED** | A pure rule (`_check_shareable`, a staticmethod of status + entity type) behind a DB round-trip for inputs every caller already holds. Every mutation applies the rule inside `_verify_owned_and_shareable`; none of the six historical endpoints exposed a standalone check. Its backend twin `query_shareable_status` went with it. |
| `get_shared_with_me_via_groups` | 0 (0 test sites) | **DELETED** | A third group listing. Its shape would not have served the group half of `/profile/shared`: no sharer attribution, ordered by `entity.created_at` rather than the edge, owner excluded by property rather than the `:OWNS` edge. That half arrived in PR 6b as `query_shared_with_me` itself — one statement over both reach patterns, gated by the audience fragment, with a via-list — and the groups hub reads it narrowed by `via`; the per-group reader get_user_entries_shared_with_group (backend twin query_user_entries_shared_with_group) was deleted with that. Backend twin `query_shared_with_me_via_groups` went with it. |
| public-portfolio listing | never existed | **the reader `set_visibility` waits on** | Nothing lists `visibility = 'public'` — not a route, not a search clause. Named here so the trigger has a name. |

The one remaining ruling is a `PLANNED_METHODS` entry in `scripts/detect_bloat.py` (`blocked_by`
→ this file's heading); every deletion is a `DELETED` row in `scripts/health/stale_names.py`.

## What the door is (shipped in PR 6b)

**Audience-at-submit and the Share panel are one write path** (ADR-054, ADR-088 §6): both
speak `AudienceSpec`, both check every target through `AudienceResolver.resolve_people` /
`check_groups_reachable` before the first write, and both write through
`AudienceResolver.resolve_and_share` — the same guarded MERGEs. The Share panel accepts the two
share values only (`group:<uid>` / `user:<username>`); a feedback request stays Submit.

1. **The access list with revoke controls** is *Your wall* on `/profile/shared`:
   `get_shared_by_me` renders every owned entry with its people and groups; each chip's × posts
   `POST /api/user-entries/{uid}/unshare` → `unshare` / `unshare_from_group`.
2. **Share reconciliation on vault re-sync** is dissolved rather than built: with R9's drafts
   (PR 8) a vault note's `audience:` applies only to the frozen copy `status: submitted` files,
   so a narrowed `audience:` has nothing to retract —
   [§ Vault Re-Sync Never Retracts a Share](vault-resync-never-retracts-a-share.md) closes there.

## The visibility ladder waits on a reader, not a panel

`Visibility` (`core/models/enums/metadata_enums.py`) is `{PRIVATE, PUBLIC}` — public-or-not
(ADR-088 §4; the `shared` and `team` values are deleted from the enum and rewritten to
`private` in the graph by `scripts/migrations/collapse_visibility_to_public_or_not_2026_09.py`).
What the graph does with the property:

- **Written at creation only.** `UserEntryService.create_entry` stores
  `request.visibility or PRIVATE`; the Submit page's (`/submissions/submit`) `audience=public` and the vault door's
  `audience: public` both map to `PUBLIC`, TEACHER-gated at both doors. A vault re-sync
  refreshes every property (the living-entry `upsert`), so a note that narrows
  `audience: public` → `private` **does** return to `PRIVATE` on the property — while its
  edges stay (the gap above).
- **Read by no non-owner path.** There is no access check (ADR-088 §3; the report detail is
  an owner read), and the report-history queries identify received feedback by
  `assessment_outcome`, not by `visibility`. The property has no reader at all.
- **The search visibility clause is edge-only.** `build_search_visibility_clause`
  ([ADR-085](../decisions/ADR-085-ownership-read-enforcement-contract.md)'s chokepoint) admits
  by `:OWNS`, `:SHARES_WITH` and `MEMBER_OF ← SHARED_WITH_GROUP`; it never tests the property.
  So the edge decides every share, and `PUBLIC` reaches no listing and no search.
- **The UI already stages the public rung as "Coming soon".** The Submit page's (`/submissions/submit`) Portfolio
  destination renders disabled (`portfolio_mode="coming_soon"`; no caller passes `active`), so
  `audience=public` at the API is reachable only by a hand-built POST or the vault door.

Therefore a visibility selector today would write a value that nothing honours for anyone but
the owner — a control that names a state the system does not have. `set_visibility` completes
**with the PUBLIC reader**: a portfolio listing (the successor to the public-browse endpoint
ADR-038 § API Layer records as retired), which is also what turns the Portfolio destination on. A
share never needs the selector (audience-at-submit writes the edge); `PRIVATE`-from-`PUBLIC` is the
unpublish, and is the one transition that is the selector's own. The method is PUBLIC-only today
and carries no TEACHER gate — the door must add the one the creation doors apply.

## Named cost

Until the PUBLIC reader exists, `visibility = 'public'` is a value nothing honours: an owner can
share and stop sharing (PR 6b), but cannot publish a portfolio, and the Submit page's
(`/submissions/submit`) Portfolio destination stays "Coming soon".
