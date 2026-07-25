"""
HuggingFace Embedding Adapter — Thin Wrapper for the Inference API
==================================================================

Single responsibility: text → embedding vector via the HuggingFace
Inference API (``huggingface_hub.AsyncInferenceClient``).

This is a thin adapter, NOT a service. It has no caching, no persistence,
no business logic — just the model call plus transport-level retry. The
caching / versioning / Neo4j storage orchestration lives in the consuming
core service (``EmbeddingsService``), which depends only on the
``EmbeddingClientOperations`` port.

ARCHITECTURE (W1 / ADR-044):
Keeps the ``huggingface_hub`` SDK out of ``core/``. The API key is read at
the composition root and passed in (mirrors DeepgramAdapter); the SDK lives
here, below the hexagonal boundary.

Model: BAAI/bge-m3 (1024-dim dense, 8192-token context) — the committed
end-state model (ADR-083, superseding ADR-049's bge-large-en-v1.5). NOT the
wired provider today: ADR-068 wires OpenAI now and stages this adapter for
the BGE swap at Arc 3 (single swap point: ``create_embedding_client()``).

Usage:
    adapter = HuggingFaceEmbeddingAdapter(api_key="hf_...")
    result = await adapter.embed("some text")
    if result.is_ok:
        vector = result.value  # list[float], len == adapter.dimension
"""

from __future__ import annotations

import numpy as np
from huggingface_hub import AsyncInferenceClient
from tenacity import retry, stop_after_attempt, wait_exponential

from core.constants import EmbeddingGeometry
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.adapters.embeddings.huggingface")

# BGE-M3 model facts (single source of truth for this adapter; the consuming
# service reads them off the port, never from constants). The dimension is the
# exception: it is cross-provider index geometry, frozen in EmbeddingGeometry
# (ADR-083). bge-m3's HF Inference API mapping is dual-task (sentence-similarity
# pipeline_tag + feature-extraction repo tag) — huggingface_hub serves the
# ``feature_extraction`` call below through the feature-extraction pipeline.
DEFAULT_MODEL = "BAAI/bge-m3"
DEFAULT_DIMENSION = EmbeddingGeometry.DIMENSION
# ~6.7k tokens at a conservative 3 chars/token (M3's XLM-R multilingual tokenizer
# is less char-dense on English than OpenAI's), well under the 8192-token M3 window.
MAX_INPUT_CHARS = 20000


class HuggingFaceEmbeddingAdapter:
    """Thin adapter for HuggingFace Inference API embedding generation.

    Implements ``EmbeddingClientOperations``. Does ONE thing:
    text → API call → vector. No persistence, no caching, no state.
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        dimension: int = DEFAULT_DIMENSION,
    ) -> None:
        """Initialize with the HuggingFace API token.

        Args:
            api_key: HuggingFace API token (required).
            model: Embedding model identifier.
            dimension: Expected vector dimension (exposed for the consuming
                service's validation/metrics).

        Raises:
            ValueError: If ``api_key`` is empty. Fail-fast at the wiring layer —
                the bootstrap try/except in ``_learning_services.py`` wraps this
                with the user-facing INTELLIGENCE_TIER guidance.
        """
        if not api_key:
            raise ValueError(
                "HF_API_TOKEN is required to construct HuggingFaceEmbeddingAdapter. "
                "Set it in the keychain (scripts/migrate_secrets_to_keychain.py) or env, "
                "or run with INTELLIGENCE_TIER=core to skip embedding services."
            )
        self._model = model
        self._dimension = dimension
        self._client = AsyncInferenceClient(model=model, token=api_key)
        self.logger = logger
        self.logger.info(f"HuggingFace embedding adapter initialized (model={model})")

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def max_input_chars(self) -> int:
        return MAX_INPUT_CHARS

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _call_api(self, text: str) -> list[float]:
        """Raw HuggingFace API call with automatic retry on transient failures.

        Retries up to 3 times with exponential backoff (2s, 4s, 8s) for
        network errors, 503 cold starts, and 429 rate limits. Raises on
        failure so tenacity can retry; ``embed`` maps the final exception
        to a Result.
        """
        raw = await self._client.feature_extraction(text)

        # feature_extraction returns a numpy array or a (possibly nested) list.
        if isinstance(raw, np.ndarray):
            # Shape could be (1, dim) or (dim,) depending on API response.
            vector = raw[0] if raw.ndim == 2 else raw
            return [float(x) for x in vector]
        elif isinstance(raw, list):
            # May be nested [[float, ...]] or flat [float, ...].
            inner = raw[0] if raw and isinstance(raw[0], list) else raw
            return [float(x) for x in inner]
        else:
            msg = f"Unexpected response type: {type(raw).__name__}"
            raise TypeError(msg)

    async def embed(self, text: str) -> Result[list[float]]:
        """Generate an embedding vector for a single text.

        Empty-text checks, truncation, dimension validation, caching and
        metrics are the consuming service's responsibility — this method is
        the raw model call only.
        """
        try:
            return Result.ok(await self._call_api(text))
        except (
            Exception
        ) as e:  # safety-net: HF API raises varied exceptions (HTTP, connection, type)
            self.logger.error(f"HuggingFace embedding call failed ({type(e).__name__}): {e}")
            return Result.fail(
                Errors.integration(
                    service="HuggingFace", message=f"Embedding generation failed: {e}"
                )
            )


__all__ = ["HuggingFaceEmbeddingAdapter"]
