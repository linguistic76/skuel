"""Unit test for TranscriptionService.list — the filters reach the backend as its ``filters``.

The backend fake is autospecced from ``UniversalNeo4jBackend``, so a call the real
``list`` signature would refuse is refused here too: an unpacked ``**filters`` (a
``user_uid=`` keyword ``list`` does not take) raised on every ``GET /api/transcriptions``.
"""

from __future__ import annotations

from unittest.mock import create_autospec

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums.transcription_enums import TranscriptionStatus
from core.models.type_hints import UserUID
from core.services.transcription.transcription_service import TranscriptionService
from core.utils.result_simplified import Result


async def test_list_hands_its_filters_to_the_backend_as_filters() -> None:
    backend = create_autospec(UniversalNeo4jBackend, instance=True)
    backend.list.return_value = Result.ok(([], 0))
    service = TranscriptionService(backend=backend)

    result = await service.list(
        user_uid=UserUID("user_owner"), status=TranscriptionStatus.COMPLETED, limit=10
    )

    assert result.is_ok, result
    backend.list.assert_awaited_once_with(
        limit=10,
        offset=0,
        filters={"user_uid": "user_owner", "status": TranscriptionStatus.COMPLETED.value},
    )
