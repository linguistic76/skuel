"""Tests for scripts/adr_links.py — the one resolver for ``related_adrs``.

Two scripts read that field, and before this module both spelled the ADR filename
themselves: ``f"ADR-{ref}.md"``, which assumes ADRs have no slug (they all do) and
appends a second ``.md`` to a ref that already names a file. The generated index's
entire dead-link count was that first bug.

The branches below are the ones the live corpus cannot reach on its own — no ref
resolves to zero candidates today, and none carries a path separator — plus the
one it very much can: the duplicate ADR numbers, whose refusal is the ruling this
module implements.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from adr_links import (  # type: ignore[import-not-found]
    AdrReferenceError,
    adr_display,
    adr_sort_key,
    resolve_adr_filename,
)

DECISIONS_DIR = Path(__file__).resolve().parents[3] / "docs" / "decisions"


def _decisions(tmp_path: Path, *names: str) -> Path:
    directory = tmp_path / "decisions"
    directory.mkdir()
    for name in names:
        (directory / name).write_text("# ADR\n")
    return directory


class TestBareNumberRefs:
    def test_resolves_to_the_one_slugged_file(self, tmp_path):
        directory = _decisions(tmp_path, "ADR-035-tier-selection-guidelines.md")
        assert resolve_adr_filename("ADR-035", directory) == "ADR-035-tier-selection-guidelines.md"

    def test_number_without_the_adr_prefix_is_accepted(self, tmp_path):
        directory = _decisions(tmp_path, "ADR-035-tier-selection-guidelines.md")
        assert resolve_adr_filename("035", directory) == "ADR-035-tier-selection-guidelines.md"

    def test_a_slugless_adr_file_still_resolves(self, tmp_path):
        """The old spelling was not wrong in principle — just wrong about this corpus."""
        directory = _decisions(tmp_path, "ADR-042.md")
        assert resolve_adr_filename("ADR-042", directory) == "ADR-042.md"

    def test_no_match_raises_naming_what_was_looked_for(self, tmp_path):
        directory = _decisions(tmp_path, "ADR-035-tier-selection-guidelines.md")
        with pytest.raises(AdrReferenceError, match="matches no ADR"):
            resolve_adr_filename("ADR-099", directory)

    def test_several_matches_raise_naming_every_candidate(self, tmp_path):
        """Never pick silently — the refusal IS the ruling.

        The predecessor resolved duplicates by ``glob()`` into a dict with the last
        write winning, and ``Path.glob`` yields directory order: which ADR a ref
        meant could change when an unrelated file was added.
        """
        directory = _decisions(
            tmp_path,
            "ADR-030-curriculum-domain-unification.md",
            "ADR-030-dual-track-assessment-pattern.md",
            "ADR-030-usercontext-file-consolidation.md",
        )
        with pytest.raises(AdrReferenceError) as excinfo:
            resolve_adr_filename("ADR-030", directory)

        message = str(excinfo.value)
        assert "ADR-030-curriculum-domain-unification.md" in message
        assert "ADR-030-dual-track-assessment-pattern.md" in message
        assert "ADR-030-usercontext-file-consolidation.md" in message

    def test_a_slugless_file_counts_as_a_competing_candidate(self, tmp_path):
        directory = _decisions(tmp_path, "ADR-042.md", "ADR-042-something-else.md")
        with pytest.raises(AdrReferenceError, match="matches 2 ADRs"):
            resolve_adr_filename("ADR-042", directory)


class TestFullFilenameRefs:
    def test_existing_filename_is_returned_verbatim(self, tmp_path):
        """No second ``.md``.

        ``f"{adr}.md"`` on a ref already ending ``.md`` rendered
        ``ADR-037-….md.md`` — the latent bug both readers shared, and the reason
        the escape hatch from the slug bug was itself unusable.
        """
        name = "ADR-037-lateral-relationships-visualization-phase5.md"
        directory = _decisions(tmp_path, name)
        assert resolve_adr_filename(name, directory) == name

    def test_missing_filename_raises(self, tmp_path):
        directory = _decisions(tmp_path, "ADR-037-lateral-relationships-visualization-phase5.md")
        with pytest.raises(AdrReferenceError, match="names no file"):
            resolve_adr_filename("ADR-037-embedding-infrastructure-separation.md", directory)

    def test_a_slugless_filename_is_also_a_filename(self, tmp_path):
        directory = _decisions(tmp_path, "ADR-042.md")
        assert resolve_adr_filename("ADR-042.md", directory) == "ADR-042.md"


class TestMalformedRefs:
    """Neither documented form is a prefix match — the grammar is anchored at both ends.

    An unanchored number pattern read ``ADR-050-typo`` as the number 050 and
    resolved it, silently, to the real ADR-050 file: a skill associated with a
    decision nobody named it after (Codex P2, PR #1218). Rejecting the *shape*
    covers every spelling of the mistake at once, which enumerating bad suffixes
    never would.
    """

    @pytest.mark.parametrize(
        "ref",
        [
            # A valid number followed by junk — the shapes that used to resolve.
            "ADR-050-typo",
            "ADR-050junk",
            "ADR-050.md.bak",
            # No ADR number at all.
            "",
            "ADR-",
            "TEMPLATE",
            "ADR-TEMPLATE.md",
            "see the ADR",
            # Escaping the directory, from either end: a ref that would resolve
            # through a separator renders a link nobody authored. Both spellings
            # now fail at the one precondition rather than at two different guards.
            "../decisions/ADR-037-lateral-relationships-visualization-phase5.md",
            "ADR-037-lateral/../ADR-037-lateral-relationships-visualization-phase5.md",
        ],
    )
    def test_a_ref_outside_the_grammar_raises(self, ref, tmp_path):
        directory = _decisions(
            tmp_path,
            "ADR-050-pwa-mobile-strategy.md",
            "ADR-037-lateral-relationships-visualization-phase5.md",
        )
        with pytest.raises(AdrReferenceError, match="is not a valid ADR reference"):
            resolve_adr_filename(ref, directory)

    def test_the_malformed_ref_does_not_reach_the_real_adr(self, tmp_path):
        """The consequence, stated directly: a typo must not silently link ADR-050."""
        directory = _decisions(tmp_path, "ADR-050-pwa-mobile-strategy.md")
        assert resolve_adr_filename("ADR-050", directory) == "ADR-050-pwa-mobile-strategy.md"
        with pytest.raises(AdrReferenceError):
            resolve_adr_filename("ADR-050-typo", directory)


class TestDisplayAndOrder:
    @pytest.mark.parametrize(
        "ref",
        [
            "ADR-037",
            "037",
            "ADR-037-lateral-relationships-visualization-phase5.md",
        ],
    )
    def test_display_is_the_short_label_whichever_form_was_authored(self, ref):
        """Only the link target gains the slug; the reader still sees ``ADR-037``."""
        assert adr_display(ref) == "ADR-037"

    def test_order_is_numeric_not_lexical(self):
        refs = ["ADR-10-b.md", "ADR-9-a.md", "ADR-100-c.md"]
        assert sorted(refs, key=adr_sort_key) == ["ADR-9-a.md", "ADR-10-b.md", "ADR-100-c.md"]

    def test_a_shared_number_is_ordered_by_spelling(self):
        """Two files with one number must not sort by whatever order they arrived in.

        The artifact is byte-compared against a fresh render, so an unstable order
        would surface as drift nobody can explain.
        """
        refs = ["ADR-030-usercontext-file-consolidation.md", "ADR-030-curriculum-b.md"]
        assert sorted(refs, key=adr_sort_key) == [
            "ADR-030-curriculum-b.md",
            "ADR-030-usercontext-file-consolidation.md",
        ]


class TestAgainstTheLiveDecisionsDirectory:
    """The refusal has to fire on the real tree, not only on a fixture.

    These pin the PREMISE the metadata's three full-filename entries exist for. If
    the duplicate numbers are ever renumbered (registered as an open hygiene item
    in deferred-work.md, deliberately not done here), this is what says so.
    """

    @pytest.mark.parametrize("ref", ["ADR-030", "ADR-037"])
    def test_the_duplicated_numbers_are_refused(self, ref):
        with pytest.raises(AdrReferenceError, match="Replace the bare number"):
            resolve_adr_filename(ref, DECISIONS_DIR)

    def test_an_unambiguous_number_resolves_against_the_real_tree(self):
        assert resolve_adr_filename("ADR-050", DECISIONS_DIR) == "ADR-050-pwa-mobile-strategy.md"
