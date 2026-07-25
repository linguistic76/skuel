"""
ADR-083 §3 chunk-budget guard — chunking grain vs embedding windows.

Embedding-text budgets are judged against the END-STATE model's window, not
just the wired provider's: the params-driven worst-case chunk text must fit
within EVERY embedding adapter's MAX_INPUT_CHARS — OpenAI (wired, ADR-068)
and the staged BGE adapter (ADR-083) alike — or
``EmbeddingsService.create_embedding`` silently truncates the tail of every
max-grain chunk on swap day. That is exactly the drift ADR-083 diagnosed
(1,000-word reference chunks vs the old 2,000-char staged BGE cap); this
guard fires at quality-gate time, not swap time, so it can't be reintroduced
silently.

Scope: this bounds the SYSTEMATIC grain — chunks produced by the prose split
paths, where ``ChunkingParams.max_chunk_size`` is enforced. Two chunker paths
bypass the word cap for content-shaped outliers and can emit chunks past any
fixed window (see the characterization tests pinning them below): fenced code
blocks are preserved verbatim, and a single sentence longer than
``max_chunk_size`` words is never split. Those outliers already exceed the
wired OpenAI budget today and are handled by the service's logged truncation;
capping them at the chunker would change chunk boundaries and therefore
requires a deliberate CHUNKING_ALGORITHM_VERSION bump, not a quiet edit here.
"""

import importlib
import pkgutil

import pytest

import adapters.external.embeddings as embeddings_pkg
from core.models.ps_content.content_chunks import (
    DEFAULT_CHUNKING_PARAMS,
    ChunkingParams,
    ContentChunkingStrategy,
    ContentChunkType,
)
from core.services.ingestion.config import REFERENCE_CHUNKING_PARAMS

# Deliberately conservative chars-per-word for worst-case chunk sizing: English
# prose averages ~6 chars/word including the separating space; 8 absorbs
# technical vocabulary and punctuation-dense content.
CONSERVATIVE_CHARS_PER_WORD = 8

# ContentChunk.context_window caps embedded context at 200 chars per side
# regardless of ChunkingParams.context_size (content_chunks.py).
CONTEXT_WINDOW_SIDE_CAP = 200

CHUNKING_CONFIGS: dict[str, ChunkingParams] = {
    "curriculum DEFAULT_CHUNKING_PARAMS": DEFAULT_CHUNKING_PARAMS,
    "reference REFERENCE_CHUNKING_PARAMS": REFERENCE_CHUNKING_PARAMS,
}


def worst_case_embedded_chars(params: ChunkingParams) -> int:
    """Params-driven upper bound on the text embedded per chunk.

    All three chunk-embedding call sites send ``ContentChunk.context_window``:
    the chunk text (≤ max_chunk_size words on the prose split paths) joined by
    two newlines to at most min(context_size, 200) chars of context per side.
    """
    context = 2 * min(params.context_size, CONTEXT_WINDOW_SIDE_CAP)
    return params.max_chunk_size * CONSERVATIVE_CHARS_PER_WORD + context + 2


def _adapter_budgets() -> list[tuple[str, int]]:
    """(module_name, MAX_INPUT_CHARS) for every module in the embeddings
    adapter package — discovery, not a hand-list, so a future third adapter
    is covered the day it lands."""
    budgets = []
    for mod_info in pkgutil.iter_modules(embeddings_pkg.__path__):
        module = importlib.import_module(f"{embeddings_pkg.__name__}.{mod_info.name}")
        max_chars = getattr(module, "MAX_INPUT_CHARS", None)
        if max_chars is not None:
            budgets.append((mod_info.name, max_chars))
    return budgets


ADAPTER_BUDGETS = _adapter_budgets()


def test_discovery_covers_wired_and_staged_adapters():
    """A one-sided or empty discovery would silence the whole guard."""
    names = {name for name, _ in ADAPTER_BUDGETS}
    assert {"openai_adapter", "huggingface_adapter"} <= names


@pytest.mark.parametrize(("adapter_name", "max_input_chars"), ADAPTER_BUDGETS)
@pytest.mark.parametrize(("config_name", "params"), CHUNKING_CONFIGS.items())
def test_worst_case_chunk_fits_adapter_window(
    config_name: str, params: ChunkingParams, adapter_name: str, max_input_chars: int
):
    worst_case = worst_case_embedded_chars(params)
    assert worst_case <= max_input_chars, (
        f"{config_name} worst-case embedded chunk (~{worst_case} chars at "
        f"{CONSERVATIVE_CHARS_PER_WORD} chars/word) exceeds {adapter_name} "
        f"MAX_INPUT_CHARS ({max_input_chars}) — EmbeddingsService would silently "
        f"truncate chunk tails. ADR-083 §3: chunking grain must fit EVERY "
        f"adapter's window (end-state included); shrink the chunk grain or "
        f"raise the adapter budget, and record the decision."
    )


# ---------------------------------------------------------------------------
# Characterization: chunker paths that BYPASS the params bound.
#
# These pin the two known word-cap bypasses so the guard's scope is explicit
# and a future chunker hard-cap flips them deliberately (with the required
# CHUNKING_ALGORITHM_VERSION bump) instead of silently. Content this shape
# exceeds any fixed embedding window; the consuming service truncates it with
# a logged warning today (wired OpenAI adapter included).
# ---------------------------------------------------------------------------


def test_known_bypass_code_fence_is_never_split():
    """A fenced code block is preserved verbatim as one CODE chunk — the
    word cap does not apply, so it can exceed every adapter budget."""
    fence = "```python\n" + ("x = 1  # padding line\n" * 1200) + "```"
    chunks = ContentChunkingStrategy.chunk_markdown(f"# H\n\nintro.\n\n{fence}", "ps.test.fence")
    code_chunks = [c for c in chunks if c.chunk_type == ContentChunkType.CODE]
    assert len(code_chunks) == 1
    assert len(code_chunks[0].context_window) > worst_case_embedded_chars(DEFAULT_CHUNKING_PARAMS)


def test_known_bypass_single_long_sentence_is_never_split():
    """A single sentence beyond max_chunk_size words is emitted whole —
    _split_large_text only breaks at sentence boundaries."""
    run_on = " ".join(["word"] * (DEFAULT_CHUNKING_PARAMS.max_chunk_size * 6)) + "."
    chunks = ContentChunkingStrategy.chunk_markdown(f"# H\n\n{run_on}", "ps.test.runon")
    assert max(len(c.text.split()) for c in chunks) > DEFAULT_CHUNKING_PARAMS.max_chunk_size
