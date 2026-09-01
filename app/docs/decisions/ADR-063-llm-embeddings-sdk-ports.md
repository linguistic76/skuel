---
title: "ADR-063: LLM & Embedding SDKs Behind Ports"
updated: 2026-07-10
status: current
category: decisions
tags: [adr, decisions, architecture, llm, embeddings, hexagonal, ports]
related: [ADR-044, ADR-043, ADR-049]
---

# ADR-063: LLM & Embedding SDKs Behind Ports

**Status:** Accepted

**Date:** 2026-05-26

**Decision Type:** ✅ Pattern/Practice

**Related ADRs:**
- Extends: ADR-044 (Neo4j as Committed Architectural Choice) — applies the same core→adapter dependency direction to the AI vendor SDKs
- Scoped by: ADR-043 (Intelligence Tier Toggle) — the adapters only exist in the FULL tier
- Builds on: ADR-049 (HuggingFace Embeddings Migration) — the HF inference client is the embedding adapter

---

## Context

After the SKUEL022 work (core must not import `adapters`), three vendor AI SDKs
were still imported **directly inside `core/services/`**, with no port:

- `openai` + `anthropic` in `core/services/llm_service.py` and `core/services/ai_service.py`
- `huggingface_hub` in `core/services/embeddings_service.py`
- `openai` in `core/services/dsl/llm_dsl_bridge.py`

This is the "flagship done-right" gap that the rest of the hexagonal work
implied but had not yet closed. SKUEL022 cannot catch it: that rule bans
`import adapters` in `core/`, not `import openai`. So a core service could call
a live LLM/embedding API directly, coupling the domain layer to a vendor SDK,
its client lifecycle, its response shapes (`response.choices[0]`, `TextBlock`,
numpy arrays), and its credential reads.

The pre-existing `core/ports/embeddings_protocols.py` only covered Neo4j
**storage** of vectors (`EmbeddingsBackendOperations`), not the inference client
— genuinely unported.

Two reference patterns already existed: **Deepgram** (`adapters/external/deepgram/`,
SDK-based, API key injected at the composition root) and **Firefly**
(`adapters/outbound/firefly_client.py` behind `core/ports/finance_protocols.py`).

## Decision

Put each AI vendor SDK **client** behind a `core/ports` protocol and move the
SDK below the hexagonal boundary into `adapters/external/`, injected at the
composition root. This combines the Deepgram directory convention (SDK-based,
key injected) with the Firefly protocol convention (a real `core/ports`
protocol).

**Ports (`core/ports/`):**
- `llm_protocols.py` — `ChatCompletionPort.complete(messages, *, system_prompt, model, temperature, max_tokens) -> Result[LLMCompletion]`, plus the `ChatMessage` TypedDict and the `LLMCompletion` DTO (`text`, `model`, optional `usage`).
- `embeddings_protocols.py` — `EmbeddingClientOperations.embed(text) -> Result[list[float]]` (plus `model`/`dimension`), alongside the existing storage port.

**Adapters (`adapters/external/`):**
- `llm/openai_adapter.py`, `llm/anthropic_adapter.py` — own the SDK clients, provider-specific message/system formatting, and error mapping to `Errors.integration`.
- `embeddings/huggingface_adapter.py` — owns `AsyncInferenceClient`, the tenacity retry, and numpy response parsing.
- `llm/dsl_bridge_factory.py` — the `create_llm_dsl_bridge` factory (builds the OpenAI adapter) relocated below the boundary.

**Core services keep their domain logic** (Askesis/RAG prompts, embedding
caching/versioning/storage, DSL parsing, journal enrichment) and depend only on
the injected port. Public method signatures (`LLMService.generate`,
`HuggingFaceEmbeddingsService.create_embedding`, etc.) are unchanged, so the 10
domain AI services and Askesis were untouched. Credential reads moved to the
composition root.

### Scope: the SDK client, not exception classes

The one sanctioned `openai`/`anthropic` import remaining in `core/` is
`core/utils/exception_types.py`, which imports the SDK **exception classes**
(behind `try/except`, degrading to `()`) to build the narrow-catch tuples that
SKUEL017 centralizes. Five `core/` services narrow-catch `LLM_EXCEPTIONS` and
**cannot** import it from `adapters/` (SKUEL022), so the tuples must live in
`core/` — as exception classes only, never the client. `huggingface_hub` has no
exception tuple and therefore no exemption.

## Alternatives Considered

### Alternative 1: Relocate the exception tuples below the boundary too
Rejected. `LLM_EXCEPTIONS` is consumed by five `core/` services for defensive
narrow catches; importing it from `adapters/` would violate SKUEL022. Exception
**classes** are not the client — keeping them in the centralized exception
module is consistent with how `neo4j` and `httpx` exceptions are already
handled there.

### Alternative 2: A new lint rule (à la SKUEL022)
Deferred. A guard test (`tests/unit/test_llm_sdk_boundary.py`) is lighter and matches
the existing boundary-test precedent (`test_infrastructure_boundary.py`,
`test_ingestion_boundary.py`). It has since been generalized from a 3-name SDK
denylist to a full third-party **allowlist** for `core/` (fails closed on any
new vendor import). A lint rule can be added later if the surface grows.

### Alternative 3: Keep `ai_service.py` as a thin core service
Rejected (One Path Forward / Consolidation): it was a second LLM entry point
alongside `LLMService`. It collapsed into the chat adapters; consumers depend on
the port.

## Consequences

### Positive
- `core/` is free of AI SDK clients; the domain layer no longer couples to vendor response shapes, client lifecycles, or credential reads.
- Providers/models are selected at the composition root; tests inject fakes via the port (no SDK monkeypatching).
- `LLMCompletion` preserves token `usage`, so nothing was lost collapsing `ai_service.py`.

### Negative / Risks
- One more indirection layer (service → port → adapter). Mitigated: the ports are minimal and the adapters are thin.
- The `exception_types.py` exemption is a deliberate hole in the guard; a canary test fails if any exemption ever stops being load-bearing, and the allowlist itself is canaried against dead entries.

## Implementation Details

**Delivered as five risk-split PRs (#67–#70 + this guard PR):**
1. Embeddings inference port (`huggingface_hub` out of `core/`).
2. Chat-completion port + `LLMService`.
3. Collapse `ai_service.py` into the chat adapters.
4. DSL bridge onto the chat port; factory relocated.
5. Boundary guard test + this ADR.

**The boundary in code:**
- Ports: `core/ports/llm_protocols.py`, `core/ports/embeddings_protocols.py`
- Adapters: `adapters/external/llm/`, `adapters/external/embeddings/`
- Composition root: `services_bootstrap/compose.py`, `services_bootstrap/_learning_services.py`

**Testing strategy:** `tests/unit/test_llm_sdk_boundary.py` enforces a third-party
import **allowlist** for `core/` (not a denylist of named SDKs — a denylist
fails open the moment someone writes `import stripe`/`import requests`). Two
tiers: `ALLOWED_THIRD_PARTY` (pure/edge-tier deps — pydantic, yaml, structlog,
bcrypt, cryptography, keyring, dotenv, markdown, prometheus_client) and
`EXCEPTION_CLASS_ONLY` (`openai`/`anthropic`/`neo4j`/`httpx` — exception classes
only, confined to `exception_types.py`). Anything else fails. Two canaries keep
both tiers honest (no dead exemptions, no dead allowlist entries) and a
fail-closed test proves a synthetic `import stripe`/misplaced SDK client is
flagged.

## Future Considerations

### When to Revisit
- If a future `core/` consumer needs to catch `huggingface_hub` exceptions, add an HF exception tuple to `exception_types.py` and extend the guard's exemption.
- If a third LLM provider is added, add an adapter implementing `ChatCompletionPort`; no core change.

### Evolution Path
Promote the guard test to a SKUEL lint rule if SDK-leak regressions recur.

### Completed follow-up — TranscriptionPort (2026-05-27)
The one remaining asymmetry is closed. Deepgram's `DeepgramAdapter` already sat
below the boundary (it was a *reference pattern* for this ADR), but core typed
against the **concrete adapter** — unlike the LLM/embeddings *ports*.
`core/ports/transcription_protocols.py` now defines `TranscriptionPort` + the
core-owned `TranscriptionResult` DTO (moved up from the adapter, mirroring
`LLMCompletion` in `llm_protocols.py`); `DeepgramAdapter` implements it
structurally; `TranscriptionService`, `BatchTranscriptionService`, and
`UserEntryProcessingService` now type against the port. All three external
model-call boundaries (chat, embeddings, transcription) are uniform: SDK in the
adapter below the boundary, core depends only on a `core/ports` protocol, the
concrete client injected at the composition root.
