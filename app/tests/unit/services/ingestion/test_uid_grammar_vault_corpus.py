"""The real vaults against the uid grammar, through the directory door's own parse.

Every entity file in the content vault (``INGESTION_PATH``) and the personal vault
(``VAULT_ROOT``) is parsed by ``parse_file_sync`` — the directory door's
parse → validate → prepare stage, no database — and must come out with a uid the
grammar admits and no uid refusal. A ``user_entry`` file's uid is the one its own
door gives it (``build_user_entry_request``: periodic, or minted on a first
sync). A fixture shares the blind spots of whoever wrote it; the corpus is what
the next sync will actually read.

Skipped where a vault is absent (CI).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.models.enums.entity_enums import EntityType
from core.models.type_hints import UserUID
from core.services.ingestion.batch import parse_file_sync
from core.services.ingestion.config import collect_files
from core.services.ingestion.detector import is_non_entity_note
from core.services.ingestion.parser import parse_markdown
from core.services.ingestion.user_entry_ingestion import build_user_entry_request
from core.services.vault.vault_descriptor import VaultKind
from core.utils.uid_grammar import UidVerdict, classify, exemption_for
from tests.helpers.ingestion_owner import INGESTION_TEST_OWNER

_VAULTS = {
    VaultKind.CONTENT: Path(os.environ.get("INGESTION_PATH", "/home/mike/0bsidian/0vault")),
    VaultKind.PERSONAL: Path(os.environ.get("VAULT_ROOT", "/home/mike/0bsidian/skuel")),
}


def _user_entry_uid(path: Path) -> str:
    parsed = parse_markdown(path)
    assert parsed.is_ok, parsed
    data, body = parsed.value
    # A note may declare its owner; the door refuses any other acting user.
    owner = UserUID(str(data.get("user_uid") or INGESTION_TEST_OWNER))
    request = build_user_entry_request(data, path.resolve(), owner, body)
    assert request.is_ok, (path, request)
    return str(request.value.uid)


def _is_uid_fault(error: dict[str, object]) -> bool:
    return error.get("field") == "uid" or "valid uid" in str(error.get("error"))


@pytest.mark.parametrize("kind", list(_VAULTS), ids=[k.value for k in _VAULTS])
def test_every_vault_file_takes_a_uid_in_the_grammar(kind: VaultKind) -> None:
    root = _VAULTS[kind]
    if not root.is_dir():
        pytest.skip(f"no {kind.value} vault at {root}")

    uid_faults: list[str] = []
    outside: list[str] = []
    parsed = 0
    for path in collect_files(root):
        if is_non_entity_note(path):
            continue
        entity_type, entity_data, error = parse_file_sync(
            path, INGESTION_TEST_OWNER, vault_kind=kind, identities={}
        )
        if error is not None:
            if _is_uid_fault(error):
                uid_faults.append(f"{path.relative_to(root)}: {error.get('error')}")
            continue
        if entity_type is None or entity_data is None:  # an Edge file — no uid of its own
            continue
        parsed += 1
        uid = _user_entry_uid(path) if entity_type is EntityType.USER_ENTRY else ""
        uid = uid or str(entity_data["uid"])
        if classify(uid) is not UidVerdict.FITS and exemption_for(uid) is None:
            outside.append(f"{path.relative_to(root)}: {uid}")

    assert uid_faults == [], "\n".join(uid_faults)
    assert outside == [], "\n".join(outside)
    assert parsed > 0, f"the corpus test parsed no entity file under {root}"
