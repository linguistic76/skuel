"""
OpenAI Embedding Adapter — Thin Wrapper for the Embeddings API
==============================================================

Single responsibility: text → embedding vector via the OpenAI Embeddings
API (``openai.AsyncOpenAI``).

This is a thin adapter, NOT a service. It has no caching, no persistence,
no business logic — just the model call plus transport-level retry. The
caching / versioning / Neo4j storage orchestration lives in the consuming
core service (``EmbeddingsService``), which depends only on the
``EmbeddingClientOperations`` port.

ARCHITECTURE (W1 / ADR-044):
Keeps the ``openai`` SDK out of ``core/``. The API key is read at the
composition root and passed in (mirrors OpenAIChatAdapter).

Model: text-embedding-3-small at 1024 dims — see ADR-068. The native
dimension is 1536, but we request 1024 via the API ``dimensions`` parameter
(Matryoshka truncation) so the Neo4j vector indexes stay compatible with the
staged BGE-large-en-v1.5 long-term swap (also 1024).

Usage:
    adapter = OpenAIEmbeddingAdapter(api_key="sk-...")
    result = await adapter.embed("some text")
    if result.is_ok:
        vector = result.value  # list[float], len == adapter.dimension
"""

from __future__ import annotations

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from core.constants import EmbeddingGeometry
from core.utils.exception_types import OPENAI_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.adapters.embeddings.openai")

# text-embedding-3-small model facts (single source of truth for this adapter;
# the consuming service reads them off the port, never from constants). The
# dimension is the exception: it is cross-provider index geometry, frozen in
# EmbeddingGeometry (ADR-083).
DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_DIMENSION = EmbeddingGeometry.DIMENSION  # via the API `dimensions` param (native: 1536)
MAX_INPUT_CHARS = 24000  # ~6k tokens, well under the 8191-token model cap


class OpenAIEmbeddingAdapter:
    """Thin adapter for OpenAI Embeddings API generation.

    Implements ``EmbeddingClientOperations``. Does ONE thing:
    text → API call → vector. No persistence, no caching, no state.
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        dimension: int = DEFAULT_DIMENSION,
    ) -> None:
        """Initialize with the OpenAI API key.

        Args:
            api_key: OpenAI API key (required).
            model: Embedding model identifier (must support the ``dimensions``
                parameter, i.e. a text-embedding-3-* model).
            dimension: Requested vector dimension, passed to the API.

        Raises:
            ValueError: If ``api_key`` is empty. Fail-fast at the wiring layer —
                the bootstrap try/except in ``_learning_services.py`` wraps this
                with the user-facing INTELLIGENCE_TIER guidance.
        """
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is required to construct OpenAIEmbeddingAdapter. "
                "Set it in the keychain (scripts/migrate_secrets_to_keychain.py) or env, "
                "or run with INTELLIGENCE_TIER=core to skip embedding services."
            )
        self._model = model
        self._dimension = dimension
        self._client = AsyncOpenAI(api_key=api_key)
        self.logger = logger
        self.logger.info(
            f"OpenAI embedding adapter initialized (model={model}, dimensions={dimension})"
        )

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
        """Raw OpenAI API call with automatic retry on transient failures.

        Retries up to 3 times with exponential backoff (2s, 4s, 8s) for
        network errors and rate limits. Raises on failure so tenacity can
        retry; ``embed`` maps the final exception to a Result.
        """
        response = await self._client.embeddings.create(
            model=self._model,
            input=text,
            dimensions=self._dimension,
        )
        # Explicit float conversion narrows the SDK's partially-typed payload.
        return [float(x) for x in response.data[0].embedding]

    async def embed(self, text: str) -> Result[list[float]]:
        """Generate an embedding vector for a single text.

        Empty-text checks, truncation, dimension validation, caching and
        metrics are the consuming service's responsibility — this method is
        the raw model call only.
        """
        try:
            return Result.ok(await self._call_api(text))
        except OPENAI_EXCEPTIONS as e:
            self.logger.error(f"OpenAI embedding call failed ({type(e).__name__}): {e}")
            return Result.fail(
                Errors.integration(service="OpenAI", message=f"Embedding generation failed: {e}")
            )
        except Exception as e:  # safety-net: unexpected response shape / transport errors
            self.logger.error(f"OpenAI embedding call failed ({type(e).__name__}): {e}")
            return Result.fail(
                Errors.integration(service="OpenAI", message=f"Embedding generation failed: {e}")
            )


__all__ = ["OpenAIEmbeddingAdapter"]
