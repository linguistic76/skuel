"""The ✅ line-hash migration's DB-free contract.

``scripts/rehash_vault_line_hashes.py`` is a one-shot pass that recomputes
``EXTRACTED_FROM.source_line_hash`` for edges whose stored digest was
produced by the retired normalisation (the one that kept the ``✅ YYYY-MM-DD``
done-date token inside the hash). The census classifies each edge before
anything is written, and that classification is the operator's only preview
of a rewrite — so it is pure (an injected in-memory file reader) and pinned
here:

1. **Rewrite only on proof.** An edge is rewritten when — and only when —
   its stored hash equals the RETIRED digest of the line it describes and
   differs from the current one. Nothing but the ``✅`` token can separate
   those two, so the equality proves the orphan.
2. **Current is left alone**, whether the line carries a ``✅`` or not.
3. **An edited line is its own state.** A stored hash matching neither
   digest is a real edit since extraction; ADR-070 keeps the hash as a
   change signal, so the migration reports it and never rewrites it.
4. **The join.** By 🆔 when the edge has one; by digest otherwise, or when
   the file no longer holds that 🆔 — the reconciler's own by-hash locator.
5. **Nothing is invented.** A missing file, a line that is gone, or an entry
   with no source text is reported by name.
6. **A non-vault entry is searched in its own content** — the same orphan
   arises on an API/upload entry re-processed with ``force``.

The Cypher — the guarded write especially — runs against a real graph in
``tests/integration/test_rehash_vault_line_hashes.py``. These run on every CI
job; that one is path-filtered.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import rehash_vault_line_hashes as rehash  # type: ignore[import-not-found]

from core.ports.vault_bridge_protocol import normalize_vault_line_hash

VAULT_PATH = "/vault/periodic_notes/2026-08-20.md"
CHECKED = "- [x] Water the plants 🆔 sk_a1b2c3 ✅ 2026-08-20"
UNCHECKED = "- [ ] Call the bank 🆔 sk_d4e5f6"
NOTE = f"# Daily\n\n{CHECKED}\n{UNCHECKED}\n"


def _reader(files: dict[str, str]):
    def read_text(path: str) -> str | None:
        return files.get(path)

    return read_text


def _row(
    *,
    stored_hash: str,
    vault_id: str | None = "sk_a1b2c3",
    vault_file_path: str | None = VAULT_PATH,
    entry_content: str | None = None,
) -> rehash.EdgeRow:
    """One census row, in the shape ``_to_edge_row`` projects from the RETURN aliases."""
    return {
        "entry_uid": "ue:daily:user_x:2026-08-20",
        "entity_uid": "task_water",
        "stored_hash": stored_hash,
        "vault_id": vault_id,
        "vault_file_path": vault_file_path,
        "entry_content": entry_content,
    }


def test_the_retired_and_current_digests_differ_only_on_the_done_date_token():
    assert rehash.legacy_normalize_vault_line_hash(UNCHECKED) == normalize_vault_line_hash(
        UNCHECKED
    )
    assert rehash.legacy_normalize_vault_line_hash(CHECKED) != normalize_vault_line_hash(CHECKED)


def test_a_hash_stored_with_the_done_date_inside_is_rewritten_to_the_current_digest():
    plan = rehash.classify(
        _row(stored_hash=rehash.legacy_normalize_vault_line_hash(CHECKED)),
        _reader({VAULT_PATH: NOTE}),
    )

    assert plan.outcome is rehash.Outcome.REWRITE
    assert plan.writes
    assert plan.new_hash == normalize_vault_line_hash(CHECKED)
    assert plan.source == VAULT_PATH


def test_a_current_hash_is_left_alone_even_on_a_checked_line():
    plan = rehash.classify(
        _row(stored_hash=normalize_vault_line_hash(CHECKED)), _reader({VAULT_PATH: NOTE})
    )

    assert plan.outcome is rehash.Outcome.CURRENT
    assert not plan.writes
    assert plan.new_hash is None


def test_a_line_edited_since_extraction_is_reported_not_rewritten():
    """The 🆔 finds the line; neither digest matches: the user changed it.
    Rewriting would erase the change signal ADR-070 keeps the hash for."""
    plan = rehash.classify(
        _row(stored_hash=normalize_vault_line_hash("- [x] Water the plant ✅ 2026-08-20")),
        _reader({VAULT_PATH: NOTE}),
    )

    assert plan.outcome is rehash.Outcome.EDITED
    assert not plan.writes


def test_an_id_less_edge_is_joined_by_the_retired_digest():
    """No 🆔 on the edge (injection never happened, or the line is checked-and-✅
    from the create door and the reconciler could no longer find it by hash)."""
    plan = rehash.classify(
        _row(stored_hash=rehash.legacy_normalize_vault_line_hash(CHECKED), vault_id=None),
        _reader({VAULT_PATH: NOTE}),
    )

    assert plan.outcome is rehash.Outcome.REWRITE
    assert plan.new_hash == normalize_vault_line_hash(CHECKED)


def test_a_vault_id_the_file_no_longer_holds_falls_back_to_the_digest_join():
    stale_id_row = _row(
        stored_hash=rehash.legacy_normalize_vault_line_hash(CHECKED), vault_id="sk_gone00"
    )

    plan = rehash.classify(stale_id_row, _reader({VAULT_PATH: NOTE}))

    assert plan.outcome is rehash.Outcome.REWRITE


def test_a_line_that_is_gone_is_reported():
    plan = rehash.classify(
        _row(
            stored_hash=normalize_vault_line_hash("- [ ] Something removed"), vault_id="sk_zzz999"
        ),
        _reader({VAULT_PATH: NOTE}),
    )

    assert plan.outcome is rehash.Outcome.LINE_NOT_FOUND
    assert not plan.writes


def test_a_missing_vault_file_is_reported_and_the_entry_content_is_not_consulted():
    """The vault is the source of truth for a vault entry: a file that is gone
    is a deletion in flight, not a reason to trust the node's copy."""
    plan = rehash.classify(
        _row(stored_hash=rehash.legacy_normalize_vault_line_hash(CHECKED), entry_content=NOTE),
        _reader({}),
    )

    assert plan.outcome is rehash.Outcome.FILE_MISSING
    assert not plan.writes


def test_a_non_vault_entry_is_searched_in_its_own_content():
    plan = rehash.classify(
        _row(
            stored_hash=rehash.legacy_normalize_vault_line_hash(CHECKED),
            vault_file_path=None,
            entry_content=NOTE,
        ),
        _reader({}),
    )

    assert plan.outcome is rehash.Outcome.REWRITE
    assert plan.source == rehash.ENTRY_CONTENT_SOURCE


def test_an_entry_with_nothing_to_search_is_reported():
    plan = rehash.classify(
        _row(stored_hash="deadbeef", vault_file_path=None, entry_content=""), _reader({})
    )

    assert plan.outcome is rehash.Outcome.NO_SOURCE


def test_the_row_projection_parses_the_json_metadata_and_tolerates_its_absence():
    row = rehash._to_edge_row(
        {
            "entry_uid": "ue_1",
            "entry_metadata": '{"vault_file_path": "/v/a.md", "entry_kind": "daily"}',
            "entry_content": None,
            "entity_uid": "task_1",
            "stored_hash": "abc",
            "vault_id": None,
        }
    )
    assert row["vault_file_path"] == "/v/a.md"
    assert row["entry_content"] is None

    bare = rehash._to_edge_row(
        {
            "entry_uid": "ue_2",
            "entry_metadata": None,
            "entry_content": "- [ ] x",
            "entity_uid": "task_2",
            "stored_hash": "abc",
            "vault_id": "sk_1",
        }
    )
    assert bare["vault_file_path"] is None
    assert bare["vault_id"] == "sk_1"


def test_the_write_is_guarded_on_the_census_value_and_touches_only_the_hash():
    """A sync between census and write re-stamps the edge; the guard skips it
    rather than clobbering the fresher digest. And the statement sets the one
    property it exists for — never ``vault_id``, never ``extracted_at``."""
    assert "WHERE r.source_line_hash = rw.old_hash" in rehash.REWRITE_QUERY
    assert rehash.REWRITE_QUERY.count("SET") == 1
    assert "SET r.source_line_hash = rw.new_hash" in rehash.REWRITE_QUERY
    assert "vault_id" not in rehash.REWRITE_QUERY
    assert "extracted_at" not in rehash.REWRITE_QUERY
