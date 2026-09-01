---
updated: 2026-05-23
---

# user_uid Canonicalization — Underscore Convention

**Date:** 2026-05-22
**Status:** Implemented
**Scope:** The **user identifier** only (owner references + the system user). Not the broader
entity-UID separator migration (see `UID_STANDARDIZATION_MIGRATION_2026-01-30.md`).

## Problem

The canonical user-id format is underscore — `user_<name>` — enforced by
`TypeConverter.to_user_uid()`, produced by `create_user()`, and used by every `:User` node and
login session. But the ingestion default was `"user:system"` (colon), built via `UserUID(...)`
which bypasses `to_user_uid()`. So the system user was spelled two ways, and ingested content got
colon/bare owners (`user:system` ×42, `system` ×7, `user:mike` ×1) that no real session or `:User`
node could match — ownership is an exact string compare, so that content was unreachable by its
logical owner.

## Change (code)

- `core.constants.SYSTEM_USER_UID = UserUID("user_system")` — single source of truth, referenced by
  both the user service and the ingestion default.
- Ingestion default (`core/services/ingestion/config.py`) is now `SYSTEM_USER_UID` (canonical).
- **Fail-fast at the ingestion boundary:** the validator errors on a present non-canonical
  `user_uid`, and `_prepare_core` routes the owner through `to_user_uid()` before storage. Ingestion
  rejects non-canonical owners rather than silently persisting them.
- `TypeConverter.normalize_user_uid()` — one-time normalizer used by the migration only.
- Regression guard: `tests/unit/test_user_uid_canonical.py`.

## Data migration

Run once per environment (after backup):

```bash
uv run python scripts/migrations/canonicalize_user_uid_2026_05.py            # dry-run (counts)
uv run python scripts/migrations/canonicalize_user_uid_2026_05.py --execute  # apply
```

Rewrites every `:Entity.user_uid` not starting `user_` to canonical form
(`user:x`/`user.x`/`user-x`/bare `x` → `user_x`). Verify:

```cypher
MATCH (n:Entity) WHERE n.user_uid IS NOT NULL AND NOT n.user_uid STARTS WITH 'user_'
RETURN count(n)   // expect 0
```

Applied to the local dev DB on 2026-05-22: 50 nodes rewritten, 0 non-canonical remaining.
No backfill of relationships needed — only the `user_uid` property value changes.
