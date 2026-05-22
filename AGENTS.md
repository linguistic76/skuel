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
- **Codex is currently paused** (the ChatGPT account is at its weekly usage
  limit) — its auto-trigger in `.github/workflows/codex-review.yml` is commented
  out, so PRs are **not** reviewed by Codex right now. **Kody (Kodus) is the
  active reviewer**, and CI Gate remains the required check.
- To re-enable Codex: confirm usage at `chatgpt.com/codex`, uncomment the
  `pull_request:` trigger in `codex-review.yml`, then verify per
  `.github/workflows/README.md` → "Verifying / re-enabling a reviewer".
- When live, `codex-review.yml` posts `@codex review` automatically on every
  non-draft PR; you can also comment `@codex review` yourself on demand.
