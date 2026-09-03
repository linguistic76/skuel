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
- No APOC above the boundary — `core/`, `adapters/inbound/`, `ui/` (SKUEL001,
  CRITICAL, unsuppressable). `apoc.meta.*` is NOT an exception to this rule: it
  is banned there too. The `apoc.meta.*` allowance is the Neo4j *server* plugin
  allowlist (`dbms_security_procedures_allowlist` in the compose file), exercised
  only by two integration modules: `tests/integration/test_apoc_canary.py`
  (permissive fixture — "is the plugin alive?") and
  `tests/integration/test_apoc_allowlist_lockdown.py` (compose-shaped container —
  "is the lockdown on?"). They require opposite server configs, so neither can
  absorb the other. Domain Cypher is pure Cypher.
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
- **Present tense, no history in comments/docstrings:** a comment states what the
  code does now. Flag a docstring or comment that narrates what the code used to do,
  which PR changed it or when ("used to", "no longer", "fixed 2026-…", "#NNN") —
  that belongs in the commit message and the ADR/`done/` doc; a pointer to the
  record is fine, a retelling is not.
- **One Path Forward:** SKUEL keeps no backward-compatibility shims. Flag added
  legacy wrappers, deprecation periods, or alternative code paths — the old path
  should be deleted, not preserved.
- Downloadable documents are Markdown (`.md`). Flag any new binary document
  format (PDF is reserved for finance invoices).

## Triggering a review
- **Neither AI reviewer auto-runs — both are on-demand** (2026-05-25). The only thing
  that runs automatically is the mechanical **CI Gate**. Summon a reviewer by comment:
  **`@kody start-review`** (gating) and/or **`@codex review`** (advisory) — including for
  a re-review after pushing more commits. A review you never request never runs, so
  summon before merging anything non-trivial.
- **Codex** (`chatgpt-codex-connector`): auto-review is **OFF** (dashboard
  `chatgpt.com/codex/cloud/settings/code-review` → "Personal auto review preferences" OFF,
  and repo `linguistic76/skuel` "Auto code review" = "Follow personal preferences", which
  resolves to off). It reviews **only** on a manual `@codex review`, and posts a PR
  review/comment — **never a status check**. The `@codex review` must come from a **human
  account** (e.g. `gh pr comment`, which posts as `linguistic76`) — a bot-posted comment
  yields only the cosmetic "create a Codex account" prompt, which is why the repo
  comment-bot (`.github/workflows/codex-review.yml`) stays disabled.
- **Codex is ADVISORY — not authoritative.** Treat its findings as input; Claude /
  the LLM arbitrates what is actually correct (consider, then accept *or reject*).
  ⚠️ Codex sometimes reasons from this repo's *prior* configuration (e.g. asserting a
  review-trigger state that no longer holds) — verify any claim about repo/review state
  against current reality before acting on it.
- **Kody** (`kody-ai`): auto-review is **OFF** (app.kodus.io "enable automatic code
  review" toggle off). It reviews only on **`@kody start-review`**; when a PR opens it
  posts a "Code Review Skipped" check. When summoned it runs in request-changes mode, so
  a Kody `CHANGES_REQUESTED` holds the merge.
- **Codex Review Gate** (required check, `.github/workflows/codex-gate.yml`) —
  **scoped to on-request**: a PR with no `@codex review` passes automatically; once a
  human posts `@codex review`, the gate is **RED** until the review is considered and
  the **`codex-considered`** label is applied (a new commit clears the label). This
  makes "the *requested* Codex review was read & considered" an enforced, auditable
  step. Clear it: read the review → post a short "Codex consideration" note
  (accept/reject + why) → `app/scripts/apply_codex_considered.sh <PR#>` (race-safe:
  a gate run still queued from the last push strips a bare `gh pr edit --add-label`;
  the script drains in-flight runs and confirms the gate goes green).
- **Required checks on `main`:** **CI Gate** (mechanical — tests/types/lint/cypher/
  route-audit) **and Codex Review Gate**. `main` keeps admin-bypass.
- To change a reviewer's auto-behavior, flip its **dashboard** toggle (Codex: the
  settings URL above — "Personal auto review preferences" / the per-repo "Auto code
  review"; Kody: app.kodus.io "enable automatic code review"). The committed
  `kodus-config.yml` `automatedReviewActive` mirrors intent but does NOT control the
  trigger on its own (dashboard is the switch). See `.github/workflows/README.md` for
  the full reviewer map.
