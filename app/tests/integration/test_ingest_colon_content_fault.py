"""Single-file door: preparer content faults surface as VALIDATION, not system.

``prepare_entity_data`` raises ValueError on content faults the file's author
controls (blank ``uid:``, colon-spelled relationship targets — the colon input
alias was deleted 2026-08-14). ``ingest_file`` is wrapped in
``@with_error_handling(error_type="system")``, so an uncaught ValueError there
became an HTTP 500 for an authoring mistake (Codex P2 #1055). The door now
converts the ValueError to a validation failure — same outcome class as the
batch door, where "preparation" is a content-fault stage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.utils.result_simplified import ErrorCategory

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_colon_relationship_target_is_validation_not_system(
    ingestion_service, tmp_path: Path
) -> None:
    ps_file = tmp_path / "ps_colon-target.md"
    ps_file.write_text(
        "---\ntype: path_step\nuid: ps.test.colon-target\ntitle: Colon Target\n"
        "uses_kus:\n  - ku:sel/foo\n---\nBody.\n",
        encoding="utf-8",
    )

    result = await ingestion_service.ingest_file(ps_file)

    assert result.is_error
    error = result.expect_error()
    assert error.category == ErrorCategory.VALIDATION, (
        f"content fault must be VALIDATION (400), got {error.category}"
    )
    assert "retired colon spelling" in error.message


async def test_blank_uid_is_validation_not_system(ingestion_service, tmp_path: Path) -> None:
    """The pre-existing blank-``uid:`` ValueError rides the same conversion."""
    ku_file = tmp_path / "ku_blank-uid.md"
    ku_file.write_text(
        "---\ntype: ku\nuid:\ntitle: Blank Uid\n---\nBody.\n",
        encoding="utf-8",
    )

    result = await ingestion_service.ingest_file(ku_file)

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.VALIDATION
