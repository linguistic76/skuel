# W-Series Docs & Skills Review — Scoping / Punch-List

**Status:** ✅ Done — executed 2026-05-26 (docs-only sweep, 9 files) · **Created:** 2026-05-26 · **Author:** scoped from the W1 implementation thread

**Purpose:** The W-series (hexagonal-boundary hardening) is complete in code, but
docs and skills carry stale references. This is the de-risked punch-list for a
focused docs/skills sweep — intended to be run in a **fresh thread** using the
`docs-skills-evolution` skill. Most of the precise W1 knowledge here came from
the implementation thread; capturing it so the review doesn't re-derive it or
fall into the find-replace trap below.

**W-series recap (what changed in code):**
- **W-cypher** (#40, ADR-044, SKUEL021): raw Cypher relocated out of `core/services/` into adapter backends.
- **W-infra** (#57): `core/infrastructure/` Cypher blind spots closed.
- **W3** (#58–#65, SKUEL022): `core/` must not import `adapters` (new ERROR lint rule).
- **W1** (#67–#71, ADR-063): `openai`/`anthropic`/`huggingface_hub` **clients** moved out of `core/services/` behind `ChatCompletionPort` / `EmbeddingClientOperations` into `adapters/external/`; `ai_service.py` deleted; `create_llm_dsl_bridge` relocated to `adapters/external/llm/`.

---

## ⚠️ Cardinal rule: VERIFY each hit — do not blind find-replace

A naive `grep + replace` will break the codebase docs. The single most common
token (`ai_service`) is mostly **NOT** stale.

### Do NOT touch (false positives)
- **`base_ai_service.py`** — still exists (base class for domain AI services). Every reference is valid.
- **`{domain}_ai_service.py`** (`tasks_ai_service.py`, `ps_ai_service.py`, `lp_ai_service.py`, …) — all still exist. Valid.
- **`ai_service=ps_ai_service`** style (e.g. `curriculum-domains/QUICK_REFERENCE.md`) — this is the `.ai` **facade sub-service** param, unrelated to the deleted `OpenAIService`. Valid.
- **Historical records**: ADRs describe a decision *at its time*; migration docs (`NEO4J_GENAI_MIGRATION.md`, `DO_MIGRATION_GUIDE.md`, `AURADB_MIGRATION_GUIDE.md`, ADR-049) intentionally reference the old GenAI/`text-embedding-3-small` embeddings. Prefer a forward-pointer over a rewrite; don't rewrite history. (The former `GENAI_SETUP.md` is no longer historical — rewritten to ADR-068 reality and renamed `EMBEDDINGS_SETUP.md`.)

### What IS stale (deleted/moved by W1)
- `OpenAIService` / `AnthropicService` (deleted) → `OpenAIChatAdapter` / `AnthropicChatAdapter` in `adapters/external/llm/`, behind `ChatCompletionPort`.
- `core/services/ai_service.py` (deleted as a file).
- `OpenAIService.generate_completion(prompt, …) -> Result[str]` → `ChatCompletionPort.complete(messages, *, system_prompt, model, …) -> Result[LLMCompletion]` (read `.text`).
- `core/services/neo4j_genai_embeddings_service.py` (gone since ADR-049) → `HuggingFaceEmbeddingsService` + `adapters/external/embeddings/huggingface_adapter.py`.
- `create_llm_dsl_bridge` imported from `core.services.dsl` → now `adapters/external/llm/`.

---

## Genuine-stale punch-list (W1)

Priority order — skills first (they actively guide work), then current-state architecture docs.

| File | Issue | Fix |
|------|-------|-----|
| `.claude/skills/prompt-templates/SKILL.md` (≈38, 187–189) | "System Prompt Pattern (`OpenAIService`)" — `OpenAIService.generate_completion()` accepts `system_prompt` | Update to `ChatCompletionPort.complete(..., system_prompt=...)`; the consumers are `UnifiedLLMCaller` / `ContentEnrichmentService` / `ProgressReportGenerator` (all now use the chat port) |
| `.claude/skills/prometheus-grafana/SKILL.md:312` | "OpenAI calls: `core/services/neo4j_genai_embeddings_service.py:138-160`" — doubly stale (file gone; it's HF not OpenAI) | Point at `adapters/external/embeddings/huggingface_adapter.py` (embeddings) and `adapters/external/llm/` (LLM); metrics still tracked in the consuming services |
| `docs/architecture/SERVICE_TOPOLOGY.md` (≈98, 100, others) | AI/LLM file inventory lists `ai_service.py` (deleted) and `neo4j_genai_embeddings_service.py` (deleted) | Replace with `adapters/external/llm/{openai,anthropic}_adapter.py`, `adapters/external/embeddings/huggingface_adapter.py`; keep `llm_caller.py`, `llm_service.py`, `embeddings_service.py` (these stayed, now port-based) |
| `docs/architecture/GRACEFUL_DEGRADATION_ARCHITECTURE.md` (≈66, 148) | "`OpenAIService` — not created / skipped" per tier | The CORE-tier skip now applies to the OpenAI/HF **adapters**; reword to the adapters + `llm_service`/`embeddings_service` being `None` in CORE |
| `docs/user-guides/intelligence-tier.md:99` | "`OpenAIService` … skipped in CORE" | Reword to the chat adapter / LLM service |
| `docs/decisions/ADR-043` (≈12, 14, 25, 34, 70) | Describes `OpenAIService` as the created service | **Judgment call.** ADR-043 is a historical decision record; ADR-063 supersedes the wiring detail. Prefer a one-line "superseded-by-ADR-063 for the SDK wiring" note over rewriting the body. |

## Additions the review should make (not just removals)

The new W1 ports are **not yet referenced anywhere** except the ADR-063 index entry. Weave them in where the old SDK-in-core story used to live:
- `docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md` — add `adapters/external/llm/` + `adapters/external/embeddings/` to the adapter inventory; note the AI SDKs are now below the boundary (parallels the Neo4j backend story).
- `.claude/skills/base-ai-service/SKILL.md` — note that `LLMService` / `HuggingFaceEmbeddingsService` now take an **injected** `ChatCompletionPort` / `EmbeddingClientOperations` (no SDK construction in the service); link ADR-063.
- Consider a short mention in CLAUDE.md's Intelligence Services or Fail-Fast sections that the LLM/embedding **clients** live in `adapters/external/` (pointer to ADR-063). Keep it terse (CLAUDE.md is for givens + `**See:**` pointers).

## W-cypher / W3 — verify (likely already current)

These landed *with* their doc updates, so VERIFY rather than assume gaps:
- `docs/patterns/linter_rules.md` — SKUEL021/022 documented? (should be)
- `docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md`, `docs/architecture/ENTITY_TYPE_ARCHITECTURE.md` — hexagonal boundary / `adapters/external` language current?
- Flag any architecture prose still describing raw Cypher / `execute_query` *inside* `core/services/` (predates #40).

---

## Approach

1. Run in a fresh thread; invoke the **`docs-skills-evolution`** skill.
2. Work the punch-list **file by file**, verifying each hit against the current code before editing (use the false-positive list above).
3. Cross-reference validation runs in pre-commit on staged `.md` files — keep links valid.
4. Group into one or a few PRs (docs-only, low risk); the boundary guard test `tests/unit/test_llm_sdk_boundary.py` already protects the *code* invariant.

## Pointers
- ADR-063 (`docs/decisions/ADR-063-llm-embeddings-sdk-ports.md`) — the W1 decision + scope.
- Memory: `project_w1_llm_embeddings_ports.md` (W1 details + gotchas), `project_skuel022_import_direction_series.md` (W3).
- Guard: `tests/unit/test_llm_sdk_boundary.py`.
- New ports: `core/ports/llm_protocols.py`, `core/ports/embeddings_protocols.py`. New adapters: `adapters/external/llm/`, `adapters/external/embeddings/`.
