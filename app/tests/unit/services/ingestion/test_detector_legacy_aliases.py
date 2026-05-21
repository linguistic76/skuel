"""Detector regression: legacy UserEntry aliases are rejected (ADR-054).

Before the /upload integration, ``detect_entity_type`` silently routed
``je_input`` / ``je_output`` / ``exercise_submission`` to ``EntityType.USER_ENTRY``
with the promise of pipeline inference in the preparer — inference code that
was never written. Per SKUEL's One Path Forward principle, legacy aliases
are now rejected with a clear error pointing at ADR-054.
"""

from pathlib import Path

import pytest

from core.services.ingestion.detector import detect_entity_type


@pytest.mark.parametrize("alias", ["je_input", "je_output", "exercise_submission"])
def test_legacy_user_entry_aliases_rejected(alias: str) -> None:
    with pytest.raises(ValueError, match="ADR-054"):
        detect_entity_type({"type": alias}, Path(f"legacy_{alias}.yaml"))


def test_user_entry_routes_normally() -> None:
    from core.models.enums.entity_enums import EntityType

    result = detect_entity_type({"type": "user_entry"}, Path("x.yaml"))
    assert result == EntityType.USER_ENTRY
