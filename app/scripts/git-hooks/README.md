# SKUEL Git Hooks

Two hooks, two purposes, one canonical source per file. Install with `app/scripts/install_git_hooks.sh` — it symlinks (does not copy) the canonical scripts so future edits take effect immediately.

## What runs and when

### `pre-commit` — runs on every `git commit`

Four checks, fail-fast on any:

1. **Secret-leak scan** — always runs.
   - Refuses to commit `.env` / `.env.local` / `.env.<anything>` (allows `.env.example` and `.env.sample`).
   - Greps **added lines only** (`git diff --cached -U0`) for high-confidence credential shapes: OpenAI project/live/test keys, AWS access keys, Stripe live + webhook secrets, GitHub PATs (classic + fine-grained), HuggingFace tokens, Slack tokens, Google API keys, PEM private-key blocks.
   - Length thresholds are tuned so doc placeholders like `sk-proj-...` don't trip.
   - Matched strings are **redacted** in the printed output so the secret doesn't leak into terminal scrollback / CI logs.

2. **Cross-reference validation** — only when at least one `.md` file is staged.
   - Runs `app/scripts/validate_cross_references.py --errors-only`.
   - Blocks on unresolvable names in a doc's `related_skills:` frontmatter, broken `/docs/...` links, and missing frontmatter on pattern docs.

3. **MyPy type check** — only when at least one `app/**/*.py` file is staged.
   - Runs `uv run mypy --follow-imports=silent <staged files>` from `app/`.
   - `--follow-imports=silent` means MyPy loads imported modules for full type info but doesn't *report* errors there. Pre-existing issues in unmodified files don't block unrelated commits; the MyPy job in [`ci.yml`](../../../.github/workflows/ci.yml) is the global zero-baseline gate.
   - Reads files from disk, not from the index — if you `git add` then edit, the check sees the edited version. (This is almost always what you want.)
   - ~10 s warm cache for ~20 staged files; cold first run can take longer.

4. **Lint (Ruff + SKUEL architecture linter)** — only when at least one `app/**/*.py` file is staged.
   - Runs `uv run ruff check <staged files>` and `uv run python scripts/lint_skuel.py --staged --strict` from `app/`.
   - Both are file-scoped to the staged set, so pre-existing issues elsewhere never block an unrelated commit; the Lint job in [`ci.yml`](../../../.github/workflows/ci.yml) is the full-tree gate.
   - Auto-fix most Ruff findings with `cd app && ./dev lint-fix`.

### `pre-push` — runs on every `git push`

**Secret scan only**, against the diff range being pushed. Exists because `git commit --no-verify` bypasses the commit-time scan, and a rushed dev who skipped commit-time checks will usually push next. Push history is permanent on most remotes — this is the last fence before that becomes a rotation incident.

Cross-reference validation deliberately doesn't run here. It's a quality concern, not a security one, and adding it would slow down every push.

## Bypass mechanisms

Listed worst-to-best:

```bash
git commit --no-verify     # skip ALL pre-commit checks (last resort)
git push   --no-verify     # skip ALL pre-push checks (last resort)
SKUEL_ALLOW_SECRETS=1 ...  # skip just the secret scan (false-positive case)
SKUEL_SKIP_MYPY=1     ...  # skip just the MyPy check (work-in-progress refactor)
SKUEL_SKIP_LINT=1     ...  # skip just the Ruff + SKUEL lint check
```

If you find yourself reaching for `--no-verify`, that's a signal — either fix the underlying issue or open a discussion about adjusting the patterns. The env-var bypasses are the right tool when you're committing a legitimate fixture (e.g. a test that asserts a fake-looking key is rejected) or staging a deliberate WIP that you'll fix before pushing — narrower scope, more obvious in `git log -p`. CI will still gate the push regardless of local bypasses.

## Defense layers

A pre-commit hook is the cheap, fast first line — not a comprehensive defense.

| Layer | Catches at | Bypassable? | Implemented? |
|---|---|---|---|
| `.gitignore` patterns | before `git add` | `git add -f`; useless against literals in `.py`/`.yaml` | yes (baseline) |
| **pre-commit hook** | at `git commit` | `--no-verify`, `SKUEL_ALLOW_SECRETS=1`, `SKUEL_SKIP_MYPY=1`, `SKUEL_SKIP_LINT=1` | **yes** (this file) |
| **pre-push hook** | at `git push` | `--no-verify`, `SKUEL_ALLOW_SECRETS=1` | **yes** (this file) |
| Server-side scan (GitHub secret scanning) | after push, on remote | no, but post-leak — alerts you to rotate | depends on plan |
| CI quality scan (MyPy + Lint) | on every PR / push to main | no — runs in CI | **yes** ([`ci.yml`](../../../.github/workflows/ci.yml)) |
| CI secret scan (gitleaks / trufflehog) | on every PR / on schedule | no — runs in CI, separate auth | **not yet** |
| No plaintext secrets on disk | always — there is no `.env` to commit | n/a | **not yet** (see below) |

The bottom row is the only structural fix. Everything above it is reactive.

## Path to "no plaintext secrets on disk"

SKUEL already has `core/config/credential_store.py` (encrypted store) and reads secrets via `get_credential("HF_API_TOKEN", fallback_to_env=True)`. The bones for moving off `.env` exist. Three practical migrations, in roughly increasing effort:

1. **`direnv` + per-user secrets file outside the repo.**
   `.envrc` (committed, no secrets) sources `~/.config/skuel/secrets.env` (gitignored by virtue of being outside the repo). Simplest of the three; works today on any Unix.

2. **OS keychain (libsecret / Keychain).**
   Extend `credential_store.py` to read from the OS keychain instead of `.env`. Credentials live in the keychain; the worktree never holds them. Survives `git add .` because there's nothing to add.

3. **`sops` + `age` (or `git-crypt`).**
   Commit an encrypted `.env.encrypted`; decryption key managed outside git. Lets the team share secrets via the repo without exposing them. Heaviest setup; pays off when more than one dev shares the same secrets.

Any of these makes "I accidentally `git add .` my `.env`" structurally impossible. Until then, the hooks above are the seatbelt.

## Editing the hooks

The canonical scripts are in this directory:

- `pre-commit` — combined secret-scan + cross-ref check
- `pre-push` — secret-scan over the push range

The installed hooks are **symlinks** to these files. Edit the files directly; no re-install needed. To verify your install is correct:

```bash
readlink "$(git config --get core.hooksPath || git rev-parse --git-dir)/hooks/pre-commit"
# should print: app/scripts/git-hooks/pre-commit (or absolute equivalent)
```

If the secret-scan patterns drift between `pre-commit` and `pre-push`, the push-time hook becomes weaker than the commit-time hook. Keep them in sync — they're intentionally identical bash arrays.
