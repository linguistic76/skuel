"""
TaskInferenceResult — Typed return contract for task inference services.
========================================================================

Frozen dataclass carrying ONLY the enrichment fields that knowledge inference
produces. Callers apply it to a Task / TaskDTO via ``dataclasses.replace()``
(or ``**result.as_kwargs()``) rather than receiving a fresh DTO or — worse —
having a DTO mutated in place.

Why a per-domain Result type instead of returning the full ``TaskDTO``?

- The contract becomes visible in the type signature: the only thing inference
  is allowed to set is what appears here. A reader does not have to guess
  which TaskDTO fields the inference layer "claims".
- Callers cannot accidentally pick up unrelated fields the inference layer
  defaulted (status, priority, etc.) — those simply are not on this object.
- Inference no longer needs to know how to construct a valid TaskDTO; it only
  needs to know what it inferred. The shape of the input is the caller's
  concern.

See: ADR-065 (Functional Inference Contract) — closes ADR-035's flagged risk
of intelligence services operating on mutable DTOs.
See: /docs/patterns/three_tier_type_system.md § "Intelligence is the exception"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaskInferenceResult:
    """The three task-level enrichment fields produced by knowledge inference.

    Defaults make this safe to construct when inference produced nothing —
    callers can apply it unconditionally and the input is left effectively
    untouched.
    """

    knowledge_confidence_scores: dict[str, float] | None = None
    knowledge_inference_metadata: dict[str, Any] | None = None
    learning_opportunities_count: int = 0

    def as_kwargs(self) -> dict[str, Any]:
        """Return the enrichment fields as kwargs for ``dataclasses.replace()``.

        Usage::

            task = dataclasses.replace(task, **result.as_kwargs())

        Reads more cleanly than spelling out each field at every call site.
        """
        return {
            "knowledge_confidence_scores": self.knowledge_confidence_scores,
            "knowledge_inference_metadata": self.knowledge_inference_metadata,
            "learning_opportunities_count": self.learning_opportunities_count,
        }
