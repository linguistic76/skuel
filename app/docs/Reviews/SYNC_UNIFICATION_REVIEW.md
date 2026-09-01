---
updated: 2026-07-02
---

# Review — Sync Unification (#482): "One Path Forward" Residual Surfaces

**Reviewed commit:** `638d2fa` — *refactor(vault): unify sync onto a descriptor
spine + surface-independent ingest ownership (#482)*
**Lens:** SKUEL's *One Path Forward* philosophy (`app/CLAUDE.md` — "no legacy
wrappers, no deprecation periods, no alternative paths; dead code is deleted, not
archived").
**Verdict:** the unification's **mechanism is sound and well-tested** — the
findings below are *consolidation debts*, not correctness bugs.

---

## Summary

Commit #482 collapsed the two divergent vault-sync paths onto a single
`VaultReconciler` + `VaultRegistry`, and made ingest ownership a function of the
vault a file lives in (`VaultRegistry.resolve_by_path`) rather than of the calling
surface. The core is coherent and pinned by tests:

- owner-uniformity across surfaces — `tests/integration/test_owner_uniformity.py`
- resolve-by-path precedence — `tests/unit/services/vault/test_resolve_by_path.py`
- combined-root guard — `tests/unit/services/vault/test_reconciler_coincident_guard.py`
- fail-closed wall + resolver chokepoint — `tests/unit/services/ingestion/test_sync_allowlist.py`,
  `tests/unit/services/ingestion/test_owner_resolution.py`

**The through-line for this review:** PR 1's commit message explicitly promised
that PR 2 would *retire* `vault_watch.py`, `/api/ingest/directory`, and the admin
content-sync button. The squashed PR 2 instead kept the first two **working** via
the new descriptor mechanism and only removed the button. So the unification's
*mechanism* landed but its *consolidation* did not — two independent ingest
surfaces and one extra trigger remain. Everything below flows from that.

Each finding lists a file:line anchor, why it is a One Path Forward tension, and a
recommended resolution: **consolidate**, **delete**, **register as PLANNED** (the
bloat-detector's staged-but-unwired backlog tier in `scripts/detect_bloat.py`), or
**document as a permanent seam**.

---

## A. Residual parallel ingest surfaces (the headline)

### A1. `/api/ingest/directory` was never retired
> **✅ RESOLVED — ADR-070 Decision 9 (2026-07-01).** The raw arbitrary-path route was
> deleted; content-vault ingestion is unified onto the reconciler (`POST /api/vault/sync/content`,
> admin) and the dashboard's directory card became a "Sync content vault" button. Arbitrary-path
> ingest was retired (Mike: not needed — the vault is the ingestion source of truth).

- **Where:** `adapters/inbound/ingestion_api.py:264-354` (route);
  still invoked by the admin dashboard JS `ui/ingestion/dashboard.py:173`
  (`fetch('/api/ingest/directory', …)`).
- **Tension:** an independent directory-ingest door standing beside the
  reconciler, despite PR 1 announcing its retirement. It *is* consistent with the
  new model — it resolves the owner by path and is covered by
  `test_owner_uniformity.py:141-159` — but it is a second live path to the same
  outcome, which One Path Forward discourages.
- **Rec:** decide explicitly. Either (a) keep it as a permanent admin door and
  **remove the "to be retired" language** from the commit history's intent /
  CLAUDE.md so it stops reading as debt, or (b) funnel it through the reconciler
  so there is one directory-ingest path.

### A2. `vault_watch.py` is a third ingest trigger
> **✅ RESOLVED — ADR-070 Decision 9 (2026-07-01).** `vault_watch.py` and its account
> provisioner were deleted; ingestion is human-initiated per event (no continuous or scheduled
> trigger). One engine (the reconciler) reachable via the sync buttons / `POST /api/vault/sync*`
> / one-shot `scripts/vault_bridge_sync.py`. Enforces Alternative E.

- **Where:** `scripts/vault_watch.py` drives ingest through the raw
  `/api/ingest/*` HTTP API (see its module docstring, `scripts/vault_watch.py:18-24`).
- **State of play:** three triggers now exist —
  1. `scripts/vault_bridge_sync.py` — in-process reconciler,
  2. `POST /api/vault/sync` — reconciler over HTTP (`adapters/inbound/vault_routes.py`),
  3. `scripts/vault_watch.py` — the raw `/api/ingest/*` door over HTTP,
  spanning **two engines** (raw ingest door vs. reconciler).
- **Nuance (argues for a seam, not debt):** the watcher's docstring deliberately
  chooses the HTTP door "so ingestion always runs on the app's fully-wired
  `UnifiedIngestionService` — embeddings, event bus, UserEntry routing — one path,
  no divergence." Post-#482 it also inherits the correct owner via
  `resolve_by_path`, so it is no longer a *correctness* divergence.
- **Rec:** make the choice explicit rather than implicit. Either route the watcher
  through the reconciler for a single engine, or **document** (in the watcher and
  in the ADR-070 notes) that the raw door is the sanctioned automation entry point
  now that ownership is surface-independent — closing the "was going to be retired"
  ambiguity.

### A3. `ingest_bundle` route skips the acting-user hint
- **Where:** `adapters/inbound/ingestion_api.py:461` — `unified_ingestion.ingest_bundle(path)`
  passes **no** `user_uid`, unlike every sibling door (`:251`, `:318`, `:391`).
- **Tension:** the module's own ownership contract docstring
  (`adapters/inbound/ingestion_api.py:8-14`) states *all* these routes pass an
  acting-user hint; bundle is a silent, undocumented exception.
- **Rec:** pass `current_user.uid` for symmetry, or add one line to the contract
  docstring declaring bundle a curriculum-only (owner-less) exception.

---

## B. Staged / decorative code

### B1. `domain_ingest` map is decorative
- **Where:** `adapters/inbound/ingestion_api.py:524-541`.
- **What:** builds a full `domain_to_entity` map, then uses it **only** to validate
  the domain string — `_ = domain_to_entity[domain_name]  # Validates domain exists`
  (`:541`) — discards the resolved `EntityType`, and ingests *all* files in the
  directory regardless of domain. The trailing comment admits it: *"entity type
  filter would be added to batch.py in future"* (`:543`).
- **Tension:** a half-implemented feature that reads as complete. One Path Forward
  wants staged work *visible*, not silently inert.
- **Rec:** implement the per-EntityType filter, simplify to a plain domain
  string-set validation (dropping the map), or register the endpoint/method in the
  PLANNED tier of `scripts/detect_bloat.py`.

### B2. Legacy `VaultConfig` fields bypassed by the new bridge
- **Where:** `core/config/unified_config.py` — `allowed_subdirs` (:598),
  `allowed_extensions` (:601), `auto_sync` / `watch_vault` /
  `sync_interval_minutes` (:589-591), `neo4j_import_dir` / `export_dir` (:594-595).
- **Tension:** the fail-closed sync wall is now sourced from the code-level
  `_DEFAULT_SYNC_SUBDIRS` (`core/services/ingestion/config.py`), **not** from
  `allowed_subdirs`. These fields are pre-ADR-070 residue that no longer feed the
  unified path.
- **Rec:** dead-config audit — delete the fields no live path reads, or
  PLANNED-register any that are deliberately staged for Stage 2/3.

### B3. Backward-compat delegate block
- **Where:** `core/services/ingestion/unified_ingestion_service.py:268-326` — ten
  methods under the banner *"DELEGATED METHODS (for backward compatibility)"*.
- **Callers:** production = **none**; the only consumer is
  `tests/test_pure_cypher_ingestion.py`.
- **Extra hazard:** the `prepare_entity_data` delegate (`:310-318`) is **lossy** —
  it forwards to the module function *without* `owner_is_authoritative`, so a
  caller of the *service* method silently loses the surface-independent-owner
  semantics the refactor introduced.
- **Tension:** "backward compatibility" wrappers are exactly what One Path Forward
  forbids.
- **Rec:** delete the block and point the test at the module-level functions
  (`preparer.prepare_entity_data`, etc.). If any method is genuinely a useful test
  seam, keep only that one and re-label it as such (not "backward compatibility"),
  and make its `prepare_entity_data` variant forward `owner_is_authoritative`.

---

## C. Config-coupling smells (secondary)

### C1. Hardcoded `je_*` journal staging paths
- **Where:** `adapters/inbound/journals_routes.py:41-53` — literal
  `/home/mike/0bsidian/skuel/je_in|je_out|je_raw|je_pro`, not derived from
  `VaultConfig.vault_root`.
- **Tension:** they point at `.../skuel/` while `VaultConfig.vault_root` defaults
  to `.../0vault/`; if `VAULT_ROOT` moves, the je_* folders don't follow —
  configuration exists but is bypassed.
- **Rec:** derive these paths from `VaultConfig` so there is one source of truth
  for the vault root.

### C2. "acts-as" prose duplicated four times
- **Where:** `core/config/unified_config.py:577-582`,
  `services_bootstrap/compose.py:1220-1224`,
  `core/services/vault/vault_descriptor.py:116-160` (docstring),
  `adapters/inbound/ingestion_api.py:8-14`.
- **Tension:** the same "the content vault *acts as* an account — NOT a fictional
  owner on curriculum" explanation is maintained in four places and will drift.
- **Rec:** canonicalize in `vault_descriptor.py` (nearest the mechanism) and
  replace the other three with a one-line pointer.

### C3. Pipeline seam: in-app periodic notes are round-trip-inert
- **Where:** in-app periodic-note creation writes `pipeline=Pipeline.NONE`
  (`adapters/inbound/journals_routes.py:906, 932, 959`), while the outbound
  round-trip only processes entries with `Pipeline.EXTRACT_ACTIVITIES`
  (`core/services/vault/vault_reconciler.py:220-221`).
- **Nuance:** the sync-page copy (`adapters/inbound/vault_routes.py:167-174`) is
  *accurate* — it explicitly says "Each daily note **with `pipeline:
  extract_activities` in its frontmatter**…". The gap is that a note created
  **in-app** never carries that frontmatter, so it is not task-round-trip-eligible
  until it is (re)ingested from a vault file that does. This is likely intended
  (the vault file is the source of truth), but it is a non-obvious seam between the
  two creation paths.
- **Rec:** document the rule (in-app notes must round-trip through the vault file
  to become eligible), or set the pipeline on in-app creation if that is the
  desired behavior.

---

## Scope note

> **✅ RESOLVED — PR #485 (2026-07-02).** All five hygiene items closed: reconciler
> `sync`/`grant_consent` retyped to `UserUID` (wraps deleted, boundaries wrap once);
> compose dead `else` branches collapsed; `_owned_by()` + `_owner_is_authoritative`
> extracted; `parse_file_sync` now enforces `validate_uid_format` (remaining
> divergence documented as an intentional seam); `ChunkEmbeddingRequested` carries
> the resolved `effective_user_uid`.

This review was deliberately scoped to the *One Path Forward* judgment calls.
A separate, lower-risk hygiene pass was identified but left out of this pass and
can be a follow-up:

- redundant `UserUID(...)` re-wraps in `vault_reconciler.py` (a `NewType` no-op);
- dead `else` branches in `compose.py`'s vault-root resolution (`config` is forced
  non-`None` at `compose.py:66-69`), which also re-hardcode default literals;
- duplicated `replace(self._personal, owner_uid=…)` and the
  `owner_is_authoritative = self.vault_registry is not None` boolean, both
  extractable to a helper/property;
- a shared per-file parse chokepoint for `ingest_file` vs. `parse_file_sync`
  (they already diverge — only `ingest_file` calls `validate_uid_format`);
- the `ChunkEmbeddingRequested` event carrying the raw acting hint
  (`unified_ingestion_service.py:677`) instead of the resolved `effective_user_uid`.

None of these affect correctness of the tested core.
