"""Private gate on the journal context read (canon P3).

``get_vault_notes_for_context`` is the shallow vault read that feeds journal
prompts — the first read-time surface to carry the ``private: true`` exclusion.
Introspective (mirrors ``test_reference_chunk_isolation.py``): the Cypher must
exclude private notes with the coalesce form (absent property = retrievable),
and must keep excluding them if the query is ever reshaped.
"""

import inspect

from adapters.persistence.neo4j._user_entry_content_mixin import _UserEntryContentMixin


def test_vault_notes_read_excludes_private_notes() -> None:
    source = inspect.getsource(_UserEntryContentMixin.get_vault_notes_for_context)
    assert "coalesce(e.private, false) = false" in source, (
        "get_vault_notes_for_context lost its private exclusion — this read "
        "feeds journal prompts, so private notes would leak into the companion."
    )


def test_vault_notes_read_still_scopes_to_owner() -> None:
    # The private gate composes WITH owner scope, never replaces it.
    source = inspect.getsource(_UserEntryContentMixin.get_vault_notes_for_context)
    assert "[:OWNS]" in source and "$user_uid" in source
