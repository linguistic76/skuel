# Secrets Out of the Worktree

**Status**: Stages 1, 2, 3 all shipped. No plaintext secrets on disk.
**Last updated**: 2026-05-12

**Canonical plan**: `/home/mike/.claude/plans/secrets-out-of-worktree.md` — full design, decision points, and rationale. This document is the in-repo "where are we" view.

---

## Why this work exists

`.env` in the worktree is one `git add .` away from a credential leak — and the pre-commit secret-scan hook is a seatbelt, not a structural fix. The hook can be bypassed with `--no-verify`, and its regex set is necessarily incomplete. The structural answer is: don't keep secrets in the worktree at all.

SKUEL already had bones for this — `core/config/credential_store.py` is a Fernet-encrypted JSON store with `get_credential(K, fallback_to_env=True)` that auto-migrates env values into the store on first read. The work was wiring that path consistently and getting secrets off the disk path that `git add` walks.

---

## What shipped

### Stage 1 — Normalize callers (commit `ffead61a`, 2026-05-12)

**Goal**: every secret read in the codebase goes through `get_credential()`. No more raw `os.getenv()` for credentials.

- Service-layer normalizations: `embeddings_service.py` (HF_API_TOKEN), `llm_service.py` (ANTHROPIC_API_KEY — silently missing from `.env.example` until then), `dsl/llm_dsl_bridge.py` (OPENAI_API_KEY).
- 8 scripts under `scripts/` converted from raw `os.getenv` reads.
- `CredentialSetup.CREDENTIALS` extended from 3 entries to 13.
- Dead-code removal discovered during the audit:
  - `ApplicationConfig.jwt_secret` / `jwt_algorithm` / `jwt_expiry_minutes` — zero consumers, with a `"change-me-in-production"` default that was a real production-safety smell.
  - `ApplicationConfig.enable_auth` — set in production_settings, read nowhere.
  - `APIConfig.api_key_enabled` / `api_key_header` — same pattern.
  - `"JWT_SECRET"` and `"API_KEY"` removed from the production `required_vars` list.

After Stage 1, where secrets *lived* hadn't changed; the surface area for the *next* stage was one funnel instead of fifteen.

### Stage 2 — direnv-sourced secrets (commit `5cd6970e`, 2026-05-12)

**Goal**: the worktree no longer contains credentials.

- `app/.envrc` (committed) — direnv loader: `~/.config/skuel/secrets.env` first (credentials), `./.env` second (non-secret config). Soft-fails on missing files.
- `.gitignore` — `!app/.envrc` exception added so the project-level loader is tracked while stray `.envrc` files everywhere else stay ignored.
- `app/scripts/migrate_secrets_to_homedir.py` — one-shot, idempotent migration. Parses `.env`, partitions on the SECRET_KEYS inventory, writes `secrets.env` with mode `0600`, rewrites `.env` without secret lines. Backs up to `.env.bak` (gitignored via `*.bak`). Handles the Docker-Compose `KEY=  # comment` quirk that `.env.example` warns about — those empty-placeholder lines aren't migrated as if the comment text were the value.
- `app/.env.example` — header documents the two-file convention; per-line `[SECRET → ~/.config/skuel/secrets.env]` markers.
- `app/README.md` — Configure-Environment section replaced with the direnv + two-file flow.

After Stage 2, the worktree has zero credential bytes. Verified by full-tree grep for OpenAI / HF / Stripe / GitHub / PEM patterns — zero matches.

### Stage 2 cleanup (2026-05-12)

`.env.bak` (the migration's safety copy) was `shred`-deleted after a working-day's use without surprises.

### Stage 3 — OS keychain backend (2026-05-12)

**Goal**: credentials live in the OS keychain — *not* in any plaintext file. Even an attacker with read access to `$HOME` can't dump credentials without going through the OS auth flow.

**Backend selection**: `SKUEL_CREDENTIAL_BACKEND=keyring` (set in `app/.env`) routes `get_credential()` to the keychain. Unset / any other value keeps the Fernet-encrypted JSON path. The keyring backend is therefore strictly opt-in — devs on the Fernet path or the direnv-only path are unaffected.

**What landed**:

- `core/config/credential_store.py` — `KeyringBackend` class (same `get/set/delete/list_keys/exists/migrate_from_env` interface as `CredentialStore`). Uses the `keyring` package: `SecretService` on Linux, `Keychain` on macOS, `Credential Locker` on Windows. Maintains a key-only index at `~/.config/skuel/keyring-index.json` so `credential_setup.py` can list what's stored without iterating the keychain (which isn't portable across keyring backends). Dispatch via `get_active_backend()`.
- `core/config/credential_store.get_credential()` — picks the active backend, catches backend errors gracefully (D-Bus down, etc.), auto-migrates env-loaded values into the active backend on first read. Placeholder values from `.env.example` (`your-openai-api-key-here`, etc.) are excluded from auto-migration via a shared `_PLACEHOLDER_VALUES` set.
- `app/scripts/migrate_secrets_to_keychain.py` *(new)* — idempotent one-shot. Reads `~/.config/skuel/secrets.env` (falls back to credential-shaped shell env vars if the file is gone), diffs against current keychain state, prompts before writing. Offers to append `SKUEL_CREDENTIAL_BACKEND=keyring` to `app/.env`. Optionally deletes `secrets.env` after success (with `shred`-style zero-fill before unlink). `--keep-source` keeps the file for verification; `--yes` is for automation.
- `pyproject.toml` — `keyring>=25.7.0` added.

**Verified**: 10 secrets migrated; `keyring.get_password("skuel", "NEO4J_PASSWORD")` returns the value; integration tests `test_ingestion_chunking.py` + `test_chunk_embedding_pipeline.py` pass with the keychain as the credential source (5 passed).

**Known caveats (documented in the migration script's output too)**:

1. **Docker Compose reads `.env` directly** for `${VAR}` interpolation. After Stage 3, `.env` no longer holds credentials — anything in `app/docker-compose.yml` or `infrastructure/docker-compose.yml` referencing `${NEO4J_PASSWORD}` will fail unless you pre-export from the keychain before running `docker compose up`. The pre-export shape:

   ```bash
   export NEO4J_PASSWORD="$(python -c 'import keyring; print(keyring.get_password(\"skuel\", \"NEO4J_PASSWORD\"))')"
   docker compose up
   ```

   Acceptable for the dev loop; CI/prod will need a different secret-injection path (out of scope for this work).

2. **Keychain unlock**: the credential store is unlocked when your desktop session is unlocked. Headless boxes / CI / cron environments don't get keychain access — they need the Fernet path or platform-native secrets.

3. **`secrets.env` is still intact** on disk (the migration ran with `--keep-source`). When you're satisfied Stage 3 sticks, run `shred -u ~/.config/skuel/secrets.env` to remove the last plaintext copy.

---

## What's left

Nothing structurally — Stages 1–3 cover the full "no plaintext secrets on disk" goal for a single-developer machine. Open follow-ups, all small and optional:

- Shred `~/.config/skuel/secrets.env` once Stage 3 has run a few sessions without surprises (it's still on disk because the migration was invoked with `--keep-source`).
- Pre-export wrapper for Docker Compose. A `scripts/dev/with-secrets` shim like `secret-tool` → `env` → `docker compose up` would smooth the rough edge in caveat #1 above.
- Tests for `KeyringBackend` round-trip. Currently covered by integration tests + the inline smoke test in the Stage 3a commit; a dedicated unit test isn't strictly needed but would be cheap insurance.

## What's permanently out of scope (deliberate)

From the plan's § "Out of scope":

- **Stage 4 (sops + age for team-shared secrets in the repo)** — only useful when a second long-term contributor needs the same credentials. SKUEL is single-developer; building this now is YAGNI.
- **Vault servers (HashiCorp Vault, AWS Secrets Manager, etc.)** — overkill for a single-dev codebase and adds an external dependency that has to be up for the app to start.
- **Hardware-backed secrets (YubiKey, TPM)** — different threat model, complex UX, not justified by current risk.
- **Rotating `SKUEL_MASTER_KEY` retroactively** — anyone with the old `.env` could have already exfiltrated the key; rotating doesn't undo that. Real remediation for any historical exposure is rotating the *underlying* credentials (Neo4j password, OpenAI key, etc.), not the encryption key.

---

## Pointers

- Plan (full design): `~/.claude/plans/secrets-out-of-worktree.md`
- Hook stack (the seatbelt): `app/scripts/git-hooks/README.md`
- Credential store (both backends — Fernet + Keyring): `app/core/config/credential_store.py`
- Setup tool: `app/core/config/credential_setup.py`
- Stage 2 migration script (`.env` → `~/.config/skuel/secrets.env`): `app/scripts/migrate_secrets_to_homedir.py`
- Stage 3 migration script (`secrets.env` → OS keychain): `app/scripts/migrate_secrets_to_keychain.py`
- direnv loader: `app/.envrc`
- Two-file convention reference: `app/.env.example`
- Backend selector: set `SKUEL_CREDENTIAL_BACKEND=keyring` in `app/.env` (already there if you ran the Stage 3 migration)
