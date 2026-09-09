# SKUEL Git Hooks

Three hooks, three purposes, one canonical source per file — plus `secret-scan.sh`, the scan
shared by `pre-commit` and `pre-push`.

## Install

One line, from the repository root (`/home/mike/skuel`):

```bash
git config core.hooksPath app/scripts/git-hooks
```

That is the whole installation. The path is **relative**, so it resolves against whichever
worktree git is operating in and survives a fresh clone; git runs the tracked scripts directly,
so there are no symlinks to refresh and edits take effect immediately. Verify with:

```bash
git config --get core.hooksPath   # → app/scripts/git-hooks
```

## What runs and when

### `pre-commit` — runs on every `git commit`

One rewrite then four checks, fail-fast on any check:

0. **Docs `updated:` auto-stamp** — only when at least one `app/docs/**/*.md` is staged.
   - Runs `app/scripts/stamp_docs_updated.py`, which sets each staged doc's frontmatter `updated:` to today (UTC), creating the block when a new doc has none.
   - Writes the **index entry and the worktree file both** — never `git add`, which would replace the index entry with the whole working-tree file and silently stage hunks deliberately left out of a `git add -p`. Only the one `updated:` line is rewritten on disk, so other unstaged hunks survive.
   - Rewrites rather than reports: it does not block the commit. `./dev health-updated` is the gate that catches a bypassed or broken stamp.
   - Runs **first**, so checks 1–2 read the content that will actually land.

1. **Secret-leak scan** — always runs.
   - Refuses to commit `.env` / `.env.local` / `.env.<anything>` (allows `.env.example` and `.env.sample`).
   - Pipes **added lines only** (`git diff --cached -U0`) into [`secret-scan.sh`](secret-scan.sh) — see [The secret scan](#the-secret-scan) below for what it catches.

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

**Secret scan only**, against the diff range being pushed — the same `secret-scan.sh` the commit hook calls. The range covers merge commits (`--cc`, so a secret introduced only in a conflict resolution is seen) and parentless ones (`--root`, so an orphan branch or a first push to an empty remote is not handed a zero-byte diff). Exists because `git commit --no-verify` bypasses the commit-time scan, and a rushed dev who skipped commit-time checks will usually push next. Push history is permanent on most remotes — this is the last fence before that becomes a rotation incident.

Cross-reference validation deliberately doesn't run here. It's a quality concern, not a security one, and adding it would slow down every push.

### `post-merge` — runs after every `git pull` / merge

**Library-change detection, non-blocking.** When `uv.lock` changed in the merge it runs `app/scripts/detect_library_changes.py --from-ref ORIG_HEAD`, which reports the package versions that moved and the skills that may need review. It never blocks; it surfaces information you would otherwise miss.

**See:** [`/docs/development/GIT_HOOKS.md`](../../docs/development/GIT_HOOKS.md) and the `@docs-skills-evolution` skill's Library Upgrade Workflow.

*(There is no `post-commit` git hook. Documentation checking after a commit runs as the Claude Code PostToolUse hook at `.claude/hooks/post-commit-docs.sh` — see [`/docs/tools/AUTOMATIC_DOCS_CHECK.md`](../../docs/tools/AUTOMATIC_DOCS_CHECK.md).)*

## The secret scan

`secret-scan.sh` reads a unified diff on stdin and exits non-zero if any **added** line looks like a credential. Both hooks call it, so the commit-time and push-time fences are the same fence: one pattern set, not two that a human keeps equal.

It scans in two halves, because credentials come in two shapes:

| Half | Source of truth | Catches |
|---|---|---|
| **Content** | [`secret-patterns.txt`](secret-patterns.txt) (`label\|regex` per line) | Provider-issued keys with their own prefix: OpenAI (`sk-proj-…` and legacy `sk-<48>`), Anthropic (`sk-ant-…`), AWS, Stripe live + webhook, GitHub PATs (classic + fine-grained), HuggingFace, Slack, Google API keys, PEM private-key blocks. |
| **Assignment** | [`credential-keys.txt`](credential-keys.txt) (one name per line) | Any credential-bearing **name** assigned a non-placeholder value, whatever the value looks like: `DEEPGRAM_API_KEY`, `NEO4J_PASSWORD`, `SESSION_SECRET_KEY`, the `FIREFLY_*` set, … |

The assignment half exists because a Deepgram key (40 hex chars), an AuraDB password and a `SESSION_SECRET_KEY` are prefix-free high-entropy strings. A content regex that caught them would also catch every hash, UUID and lockfile digest in the tree — so for those the **name** is the signal, not the value.

Two syntaxes are matched, because a credential name means different things in each:

- **assignment** — `KEY=value`, `KEY: value`, `export KEY=value`, `KEY: str = value`, `- "KEY=value"` (compose's quoted env-list scalar), and any of those behind a line marker (`#`, `//`, `--`, `;`, `*`). The env / shell / YAML form, plus the typed Python constant. A credential parked in a commented config example is in the history exactly as much as an uncommented one. A quoted value here may contain spaces: `NEO4J_PASSWORD="correct horse battery staple"` is one value, not four, and measuring only its first word would clear it.
- **data literal** — `"KEY": value` and `config["KEY"] = value`, as JSON, dict literals and subscript assignment write it, whether one key per line or inline. Here the value must be **space-free** to count.

That space-free rule is the one place the two syntaxes disagree, and it is measured rather than stylistic. A dict keyed by a credential name, in this repo, holds a *description* — `"OPENAI_API_KEY": "OpenAI API key for embeddings and AI features"` in `core/config/environment_validator.py`, and `CREDENTIAL_CATALOG` in `credential_store.py` itself. Accepting a spaced value there reports the files that **are** this scan's source of truth, plus this README and the test that quote them, and no syntactic signal separates a description of a credential from a passphrase.

**Its cost, stated plainly:** a *spaced* passphrase hard-coded in a dict literal is not caught. A space-free one is, in every form, and the assignment syntax catches spaced passphrases (`NEO4J_PASSWORD="correct horse battery staple"`). The test pins both halves, so removing the rule fails loudly instead of quietly making the catalog files un-committable.

A value is treated as a placeholder, and not reported, when it is empty, shorter than 20 characters, an interpolation *reference* (`$VAR`, `${VAR}`, `${VAR:-}`), or contains `your-` or an angle-bracketed token. An interpolation with a fallback — `${FIREFLY_DB_PASSWORD:-firefly-local-dev}`, compose's live idiom — has its **fallback text measured by the same floor**, because that text is a real value: exempting everything beginning with `$` would let a production credential hide inside the fallback of a reference to itself.

Every placeholder arm must span the **whole** value, not merely its start, or `${NEO4J_PASSWORD}<secret>` is exempted for beginning with a reference. (A bare `$VAR` needs no such care: `$SESSION_SECRET_KEYabc` is the variable *named* `SESSION_SECRET_KEYabc` and expands to nothing — concatenation onto a bare reference requires a non-identifier boundary, which is reported.) The last two arms look **past the start** of the value, because the convention often sits behind a prefix: `sk-your-openai-key` and `# ANTHROPIC_API_KEY=sk-ant-your-anthropic-key` in `.env.example`, `NEO4J_AUTH=neo4j/<password>` in `SETUP.md`. A real credential contains no angle brackets, and the odds of one containing the literal `your-` are negligible.

That rule is deliberately **broader** than `core/config/credential_store.py::_is_placeholder`, which recognises only the empty string, a `your-` prefix, and its own `_PLACEHOLDER_VALUES` list. Every member of that list is covered here, and `tests/unit/scripts/test_secret_scan.py` pins it by driving the script with the real set — so the hook never reports a value the credential funnel would accept.

The length floor is what the committed templates need: `.env.example` carries `firefly-local-dev` and `sk-your-openai-key`, and `SETUP.md` carries `<your-openai-key>` — none of them `your-`-prefixed, none in `_PLACEHOLDER_VALUES`. An exact-list rule reports all three, and a scan that blocks `.env.example` gets bypassed with `SKUEL_ALLOW_SECRETS=1` until it stops being a fence at all.

**The floor's cost, stated plainly:** a locally-chosen credential under 20 characters is not caught by the assignment half. The gap is bounded — every provider-issued credential in the catalog is far longer (an AuraDB password is 43 base64url characters, `SESSION_SECRET_KEY` 43, a Firefly PAT hundreds), and the content half catches provider keys however they are assigned. What it leaves uncovered is a short hand-picked local password.

The scan **fails closed**: if it loads no patterns or no credential names — a truncated or unreadable data file, a missing shell builtin, a bad path — it exits non-zero with an error rather than reporting clean. A scanner with nothing to scan for must never pass a diff. (It also uses no bash-4-only builtin: `/bin/bash` on macOS is 3.2, where `mapfile` is not a command, and the arrays would have loaded empty and passed everything.)

Matches are always printed **redacted** — content matches with the matched text replaced, assignment matches with everything past the separator replaced. Every redaction is applied to every printed line, not only the one whose match produced the report: a single line can carry two credentials, and redacting only the current match would print each secret verbatim inside the other's report. A redaction that fails withholds the line rather than falling through to printing it. The point is to block the commit without echoing the secret into terminal scrollback or CI logs.

`credential-keys.txt` is a **mirror**, not a second source of truth: bash cannot import Python, so the names are duplicated from `core/config/credential_store.py::CREDENTIAL_CATALOG` and pinned by a drift test — the same arrangement `scripts/lint_skuel.py::SkuelLinter.CREDENTIAL_CATALOG` already uses.

It carries names `CREDENTIAL_CATALOG` does not:

- `NEO4J_AUTH` — Docker Compose reads it directly for `${VAR}` interpolation, and its `user/password` value carries a real password.
- The credential env keys the deployed services themselves read — `MYSQL_PASSWORD`, `DB_PASSWORD`, `APP_KEY`, `FIREFLY_III_ACCESS_TOKEN`, `GF_SECURITY_ADMIN_PASSWORD`, `GRAFANA_PASSWORD` — enumerated from the compose files, where each is an interpolation today. Replacing one with a literal is the leak they cover.

A name-*shape* rule (`*_PASSWORD`, `*_TOKEN`, …, mirroring `SkuelLinter.CREDENTIAL_SHAPE_RE`) was measured as an alternative to that list and rejected: it reports ordinary code identifiers — `_AUTH_EVENT`, `FENCE_TOKEN_RE`, `ALLOWLIST_KEY` — and the exclusion list it would need is a security hole by construction. What puts a name in this file is that assigning it a literal is a leak — a wider question than whether `get_credential()` manages it. Such names are declared in the drift test's `NON_FUNNEL_KEYS`, so the mirror stays pinned exactly in both directions and an unexplained extra fails.

## Bypass mechanisms

Listed worst-to-best:

```bash
git commit --no-verify     # skip ALL pre-commit checks (last resort)
git push   --no-verify     # skip ALL pre-push checks (last resort)
SKUEL_ALLOW_SECRETS=1 ...  # skip just the secret scan (false-positive case)
SKUEL_SKIP_MYPY=1     ...  # skip just the MyPy check (work-in-progress refactor)
SKUEL_SKIP_LINT=1     ...  # skip just the Ruff + SKUEL lint check
SKUEL_SKIP_DOC_STAMP=1 ... # skip just the docs `updated:` stamp
```

`SKUEL_SKIP_DOC_STAMP=1` is not a "rushed dev" bypass — it is required by
`scripts/backfill_docs_updated.py`, which writes each doc's *historical* date and
would be undone by a stamper that rewrote them all to today.

If you find yourself reaching for `--no-verify`, that's a signal — either fix the underlying issue or open a discussion about adjusting the patterns. The env-var bypasses are the right tool when you're committing a legitimate fixture (e.g. a test that asserts a fake-looking key is rejected) or staging a deliberate WIP that you'll fix before pushing — narrower scope, more obvious in `git log -p`. CI will still gate the push regardless of local bypasses.

## Defense layers

A pre-commit hook is the cheap, fast first line — not a comprehensive defense.

| Layer | Catches at | Bypassable? | Implemented? |
|---|---|---|---|
| `.gitignore` patterns | before `git add` | `git add -f`; useless against literals in `.py`/`.yaml` | yes (baseline) |
| **pre-commit hook** | at `git commit` | `--no-verify`, `SKUEL_ALLOW_SECRETS=1`, `SKUEL_SKIP_MYPY=1`, `SKUEL_SKIP_LINT=1`, `SKUEL_SKIP_DOC_STAMP=1` | **yes** (this file) |
| **pre-push hook** | at `git push` | `--no-verify`, `SKUEL_ALLOW_SECRETS=1` | **yes** (this file) |
| Server-side scan (GitHub secret scanning) | after push, on remote | no, but post-leak — alerts you to rotate | depends on plan |
| CI quality scan (MyPy + Lint) | on every PR / push to main | no — runs in CI | **yes** ([`ci.yml`](../../../.github/workflows/ci.yml)) |
| CI secret scan (gitleaks / trufflehog) | on every PR / on schedule | no — runs in CI, separate auth | **not yet** |
| No plaintext secrets in the worktree | always — there is no `.env` to commit | n/a | **yes** (see below) |
| No plaintext secrets on disk at all | always | n/a | **partly** — the keyring backend, yes; `~/.config/skuel/secrets.env` is still plaintext (see below) |

The bottom row is the only structural fix. Everything above it is reactive.

## "No plaintext secrets in the worktree"

That property holds, and it is the one the bottom rows distinguish. Credentials are read through `get_credential()` and resolved by the backend `SKUEL_CREDENTIAL_BACKEND` selects; `keyring` puts them in libsecret / macOS Keychain / Windows Credential Locker. Nothing under the repo holds a credential, so `git add .` has nothing to stage — which is what makes it a *structural* fix rather than a check that can be bypassed.

**It is not the same as encryption at rest, and the stronger claim would be false.** `~/.config/skuel/secrets.env` is still a plaintext file (mode 0600), holding `NEO4J_AUTH` + `NEO4J_PASSWORD` for Docker Compose `${VAR}` interpolation, and `app/.envrc` sources it. Moving a file outside the worktree defeats `git add .`; it does not defeat anything that can read the filesystem. Only the keyring backend gives the at-rest property, and only for the keys it holds — see [`/docs/roadmap/done/secrets-out-of-worktree.md`](../../docs/roadmap/done/secrets-out-of-worktree.md) § `fed4287f`, whose item 3 records that file as deliberately still on disk.

`sops` + `age` (commit an encrypted `.env.encrypted`, manage the decryption key outside git) is the one shape SKUEL has **not** adopted. It pays off when several developers share one secret set; with a single developer it is pure setup cost.

The hooks above stay regardless. They are the seatbelt for the case the structure does not cover: a key pasted into a `.py`, a `.yaml`, or a doc.

## Editing the hooks

This directory is the hook source dir, and `core.hooksPath` points git straight at it:

| File | Purpose |
|---|---|
| `pre-commit` | doc stamp + secret scan + cross-ref + MyPy + lint |
| `pre-push` | secret scan over the push range |
| `post-merge` | library-change detection after a pull |
| `secret-scan.sh` | the scan itself, called by both `pre-commit` and `pre-push` |
| `secret-patterns.txt` | content patterns, `label\|regex` per line |
| `credential-keys.txt` | credential names for the assignment half |

Edit these files directly — git executes them where they sit, so there is nothing to re-install. Changing the scan means changing one file, not two: add a content pattern to `secret-patterns.txt`, or a credential name to `credential-keys.txt` (and to `CREDENTIAL_CATALOG`, which the drift test compares it against). Add the matching row to `tests/unit/scripts/test_secret_scan.py` in the same change.
