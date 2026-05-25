# AGENTS.md

Repository guidance for AI coding agents (OpenAI Codex and any other agent that
reads `AGENTS.md`). Codex applies the **closest** `AGENTS.md` to each changed
file, so this top-level file sets repo-wide expectations. Most code lives under
`app/`; the authoritative, detailed specification is `app/CLAUDE.md` plus
`app/docs/` — read those when you need the "why."

SKUEL is a uv-based Python monorepo. The app is at `app/`; CI workflows are at
`.github/workflows/`.

## Review guidelines

Flag a change when it violates one of these. These are SKUEL's enforced
invariants — keep comments focused on real, high-priority risks.

### Error handling
- Services return `Result[T]`. Use `.is_error` (never `.is_err`).
- Create errors with the `Errors` factory; propagate across type boundaries with
  `Result.fail(result)` (not `return result`). Use `.expect_error()` only to
  *read* an error.
- Route handlers use `require_found(result, resource, uid)` for the fetch +
  not-found guard.
- No bare `except Exception`. Use the specific tuples in
  `app/core/utils/exception_types.py` (`NEO4J_EXCEPTIONS`, `LLM_EXCEPTIONS`,
  etc.). Intentional broad catches must carry a `# intentional-broad:`,
  `# safety-net:`, or `# skuel-lint: disable=SKUEL017` annotation.

### Enums over magic strings
- No raw string comparisons for roles, scopes, statuses, relationships, or
  domains. Use `EntityType` / `NonKuDomain` (entity & domain discriminators),
  `RelationshipName` (edges), and the domain enums in `app/core/models/enums/`.
- Presentation logic belongs on enum methods; magic numbers live in
  `app/core/constants.py`.

### Neo4j / persistence
- No APOC in domain services except `apoc.meta.*` (SKUEL001). Domain Cypher is
  pure Cypher.
- Domain-specific Cypher belongs on the domain backend; services call
  `self.backend.method_name()` and never inline `execute_query()`.
- Cross-domain aggregation stays in services, not backends.

### Type safety
- Every new `Any` must be justified with a `# boundary:` comment, or replaced
  with a specific type (`Neo4jProperties`, `FT`, a domain model, a TypedDict).
- New protocol methods and route handlers return a concrete model or TypedDict —
  not `Result[Any]`. `Result[FT]` is correct for HTMX fragment handlers.
- `./dev quality` enforces **0 MyPy errors**; a regression is a blocker.

### Ownership & auth
- User-owned reads return **404** (not 403) for entities the user doesn't own.
- Role gates use named functions, never lambdas (SKUEL012). Credential reads use
  `get_credential()`, never raw `os.getenv()` on credential-shaped names
  (SKUEL019).

### Style / general
- No `hasattr()` — use Protocol / `isinstance` / `getattr` (SKUEL011).
- No lambdas (SKUEL012). No `print()` in production code — use the logger
  (SKUEL015). `print()` is fine in interactive CLI scripts.
- `async def` only when the function awaits I/O; otherwise `def`.
- **One Path Forward:** SKUEL keeps no backward-compatibility shims. Flag added
  legacy wrappers, deprecation periods, or alternative code paths — the old path
  should be deleted, not preserved.
- Downloadable documents are Markdown (`.md`). Flag any new binary document
  format (PDF is reserved for finance invoices).

## Triggering a review
- **Both AI reviewers auto-run on PRs you open, and both are also summonable by
  comment** (2026-05-25). Codex auto-reviews on PR open (its dashboard); Kody
  auto-reviews (its app.kodus.io toggle). Summon explicitly with **`@codex review`**
  or **`@kody start-review`** — needed e.g. for a re-review after pushing more
  commits (Codex's auto-trigger is "On PR open", not per-push).
- **Codex** (`chatgpt-codex-connector`): auto-review is **ON** (unlocked by a paid
  ChatGPT plan; dashboard `chatgpt.com/codex/cloud/settings/code-review` → "Personal
  Review Trigger Preference" = "On PR open", repo `linguistic76/skuel` "Auto code
  review" = "Review my PRs"). It posts a PR review/comment, **never a status check**.
  A manual `@codex review` must come from a **human account** (e.g. `gh pr comment`,
  which posts as `linguistic76`) — a bot-posted comment yields only the cosmetic
  "create a Codex account" prompt, which is why the repo comment-bot
  (`.github/workflows/codex-review.yml`) stays disabled.
- **Codex is ADVISORY — not authoritative.** Treat its findings as input; Claude /
  the LLM arbitrates what is actually correct (consider, then accept *or reject*).
  ⚠️ Codex sometimes reasons from this repo's *prior* configuration (e.g. it has
  claimed "auto-review is off" while auto-reviewing the very PR) — verify any claim
  about repo/review state against current reality before acting on it.
- **Codex Review Gate** (required check, `.github/workflows/codex-gate.yml`) —
  **scoped to on-request**: a PR with no `@codex review` passes automatically; once a
  human posts `@codex review`, the gate is **RED** until the review is considered and
  the **`codex-considered`** label is applied (a new commit clears the label). This
  makes "the *requested* Codex review was read & considered" an enforced, auditable
  step. Clear it: read the review → post a short "Codex consideration" note
  (accept/reject + why) → `gh pr edit <PR#> --add-label codex-considered`.
- **Required checks on `main`:** **CI Gate** (mechanical — tests/types/lint/cypher/
  route-audit) **and Codex Review Gate**. Kody runs in request-changes mode, so a
  Kody `CHANGES_REQUESTED` also holds the merge. `main` keeps admin-bypass.
- To change a reviewer's auto-behavior, flip its **dashboard** toggle (Codex:
  the settings URL above; Kody: app.kodus.io "enable automatic code review"). The
  committed `kodus-config.yml` `automatedReviewActive` mirrors intent but does NOT
  control the trigger on its own (dashboard is the switch). See
  `.github/workflows/README.md` for the full reviewer map.
