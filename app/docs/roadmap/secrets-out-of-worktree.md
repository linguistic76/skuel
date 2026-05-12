# Secrets Out of the Worktree

**Status**: Stage 1 + Stage 2 shipped. Stage 3 deferred.
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

---

## What hasn't shipped — Stage 3 (OS keychain backend)

**Status**: deferred until Stage 2 has run long enough to surface any breakage.

### What it would do

After Stage 3, credentials live in libsecret (Linux) / macOS Keychain — *not* in any plaintext file. Even an attacker with read access to `$HOME` can't dump credentials without going through the OS auth flow.

### What changes

| File | Change |
|---|---|
| `core/config/credential_store.py` | Add a `KeyringBackend` class implementing the same `get/set/delete/list_keys/exists` interface as the existing Fernet `CredentialStore`. Selection by env var: `SKUEL_CREDENTIAL_BACKEND=keyring` ⇒ keychain; anything else ⇒ existing Fernet JSON. The top-level `get_credential()` dispatches. |
| `core/config/credential_setup.py` | Extend the interactive setup with a "backend selection" prompt at first run. The existing Fernet flow stays for users who don't opt in. |
| `app/scripts/migrate_secrets_to_keychain.py` *(new)* | One-shot: reads each secret from `~/.config/skuel/secrets.env` (or env), writes via `secret-tool store --label="SKUEL <KEY>" service skuel key <KEY>`, removes from the homedir file after success. Mirrors the Stage-2 migration shape. |
| `pyproject.toml` | `uv add keyring` — single dependency, handles libsecret/Keychain/Windows Credential Locker uniformly. |

### When to do Stage 3

The plan's trigger criteria:

- **Threat-model needs Stage 3** — laptop is shared with other user accounts, or `$HOME` gets synced to a location you don't fully control (cloud sync that touches `~/.config/`), or you want OS-mediated unlock prompts for credential rotation. If you're single-user, full-disk-encrypted, and `~/.config/` isn't auto-synced anywhere sketchy, Stage 2 is already sufficient.
- **Stage 2 is settled** — at least a week of normal workflow use (dev server start, vault ingest, askesis endpoint, any one-off scripts) without finding a credential read path that bypasses direnv. Specific things to watch for during this period:
  - Docker Compose reads `.env` directly. Anything in `infrastructure/` or `app/docker-compose.yml` that needed a credential will break after Stage 2 because `.env` no longer has those values. CI / cron jobs that bypass interactive shells have the same risk.
  - Scripts that don't pick up `~/.config/skuel/secrets.env`. Symptom: `get_credential(K, fallback_to_env=True)` returns `None` in a script context that wasn't invoked from a direnv-loaded shell. Workaround pattern: `set -a; . ~/.config/skuel/secrets.env; set +a; <command>`.

### When NOT to do Stage 3

- If Stage 2 has surfaced friction that you'd rather fix first (e.g., Docker Compose can't see Neo4j password). Stage 3 doesn't help that class of problem and adds another moving part.
- If you're about to migrate to a hosted environment (Droplet, App Platform, AuraDB) where secrets come from the platform's secret store anyway. The Stage 3 keychain story is a developer-machine concern; production deployments have their own answer (which the plan calls out at § "Out of scope").

---

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
- Credential store (Fernet-encrypted, today's default): `app/core/config/credential_store.py`
- Setup tool: `app/core/config/credential_setup.py`
- Stage 2 migration script: `app/scripts/migrate_secrets_to_homedir.py`
- direnv loader: `app/.envrc`
- Two-file convention reference: `app/.env.example`
