"""Pure-Python vector-math helpers shared across AI and embedding services.

Single home for the cosine-similarity kernel that was previously copy-pasted into
``base_ai_service``, ``embeddings_service``, ``askesis.intent_classifier``, and
``prereq_suggestion_service``. No numpy dependency — operates on plain ``list[float]``
so it stays importable from the Analog layer.

The ``cosine_similarity`` guard is the strict superset of every prior copy: it returns
``0.0`` for empty, length-mismatched, or zero-norm inputs. Callers that need
normalize-once/dot-many performance use ``l2_normalize`` + ``dot`` directly.
"""

from __future__ import annotations

import math


def dot(vec1: list[float], vec2: list[float]) -> float:
    """Dot product of two vectors (pairs truncate to the shorter length)."""
    return sum(a * b for a, b in zip(vec1, vec2, strict=False))


def l2_norm(vec: list[float]) -> float:
    """Euclidean (L2) norm of a vector."""
    return math.sqrt(sum(a * a for a in vec))


def l2_normalize(vec: list[float]) -> list[float]:
    """Unit vector for ``vec``; a zero (or empty) vector maps to all-zeros.

    An all-zeros result dots to ``0.0`` against anything, so pre-normalized cosine
    stays well-defined without a separate zero guard at the call site.
    """
    norm = l2_norm(vec)
    if norm <= 0.0:
        return [0.0] * len(vec)
    return [a / norm for a in vec]


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Cosine similarity in ``[-1.0, 1.0]``.

    Returns ``0.0`` for empty, length-mismatched, or zero-norm inputs.
    """
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    norm1 = l2_norm(vec1)
    norm2 = l2_norm(vec2)
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot(vec1, vec2) / (norm1 * norm2)
