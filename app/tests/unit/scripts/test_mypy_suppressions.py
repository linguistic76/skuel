"""Pin the config surgery and output parsing in ``scripts/health/mypy_suppressions.py``.

Why this file exists
--------------------
The audit's verdict rests on two things a unit test CAN reach — that the generated
config says exactly what the audit thinks it says, and that mypy's output is read
correctly — and one thing it cannot: the mypy runs themselves, at ~30s each. That
split is deliberate and is the whole reason the script is not wired into a fast
target (see its module docstring).

So the cases below cover the parts that fail SILENTLY:

  * **Surgery.** If the text edit removes the wrong code, or drops a module list, or
    silently edits nothing, every downstream count is wrong but nothing errors. The
    script guards this by re-parsing its own output with ``tomllib``; that guard is
    itself tested here for non-vacuity — a guard that cannot fail is not a guard.

  * **Attribution.** A ``[code]`` suffix that fails to parse reads as "0 errors of
    that code", which is indistinguishable from a genuinely vacuous entry. The
    failure direction points at a WRONG DELETION, so the regex is pinned against
    real mypy output shapes rather than invented ones.

  * **The unused-section note.** Pinned against the exact string this repo's mypy
    emitted at ``8234e6c3c`` (the commit before #876 deleted the five dead targets).
    That string is history, not a fixture I wrote to match my own parser.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ has no __init__.py — add it to sys.path for import (matches test_lint_skuel.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "health"))

import mypy_suppressions as ms  # type: ignore[import-not-found]

# The real note this repo's mypy printed at 8234e6c3c, before #876 deleted them.
REAL_UNUSED_NOTE = (
    "pyproject.toml: note: unused section(s): module = "
    "['config', 'core.patterns.*', 'core.protocols', 'psutil.*', 'rdflib.*']"
)

SAMPLE = """\
[tool.mypy]
strict = false

[[tool.mypy.overrides]]
# A comment mentioning disable_error_code in prose.
module = ["core.events.*", "core.protocols"]
disable_error_code = ["call-arg", "no-untyped-def"]

[[tool.mypy.overrides]]
module = [
    "adapters.backends.activity",
    "adapters.backends.curriculum",
]
disable_error_code = ["misc"]

[[tool.mypy.overrides]]
module = ["ui.*"]
warn_return_any = false

[tool.pyright]
include = ["core"]
"""


# ============================================================================
# PARSING: blocks, their line numbers, and their codes
# ============================================================================


def test_parses_every_override_with_its_header_line() -> None:
    overrides = ms.parse_overrides(SAMPLE)
    assert [o.index for o in overrides] == [0, 1, 2]
    assert [o.header_line for o in overrides] == [4, 9, 16]
    assert overrides[0].codes == ["call-arg", "no-untyped-def"]
    assert overrides[1].codes == ["misc"]
    assert overrides[2].codes == []


def test_a_block_without_disable_error_code_contributes_no_pairs() -> None:
    """The audit's unit of work is the (block, code) pair, so a bare block yields none."""
    overrides = ms.parse_overrides(SAMPLE)
    pairs = [(o.index, c) for o in overrides for c in o.codes]
    assert pairs == [(0, "call-arg"), (0, "no-untyped-def"), (1, "misc")]


def test_module_given_as_a_bare_string_is_normalised_to_a_list() -> None:
    text = (
        '[tool.mypy]\n\n[[tool.mypy.overrides]]\nmodule = "config"\ndisable_error_code = ["misc"]\n'
    )
    assert ms.parse_overrides(text)[0].modules == ["config"]


def test_header_count_mismatch_aborts_rather_than_guessing() -> None:
    """An inline array-of-tables parses but cannot be located in the text.

    The script edits text by line span, so it must refuse any shape where the Nth
    header line is not the Nth parsed block. Guessing here would edit the wrong
    block and produce a confident wrong verdict.
    """
    text = '[tool.mypy]\noverrides = [{ module = "x", disable_error_code = ["misc"] }]\n'
    with pytest.raises(ms.AuditError, match="header lines"):
        ms.parse_overrides(text)


# ============================================================================
# SURGERY: remove exactly one code from exactly one block
# ============================================================================


def test_strips_one_code_from_one_block_and_leaves_the_sibling_untouched() -> None:
    """`misc` lives in two blocks in the real pyproject — that is why this matters."""
    out = ms.render_stripped(SAMPLE, {0: {"call-arg"}})
    overrides = ms.parse_overrides(out)
    assert overrides[0].codes == ["no-untyped-def"]
    assert overrides[1].codes == ["misc"]


def test_stripping_the_last_code_leaves_an_empty_list_not_a_missing_key() -> None:
    out = ms.render_stripped(SAMPLE, {1: {"misc"}})
    assert ms.parse_overrides(out)[1].codes == []


def test_multi_line_module_arrays_survive_a_strip_in_the_same_block() -> None:
    """The span finder must not mistake a wrapped `module = [` list for a table header."""
    out = ms.render_stripped(SAMPLE, {1: {"misc"}})
    assert ms.parse_overrides(out)[1].modules == [
        "adapters.backends.activity",
        "adapters.backends.curriculum",
    ]


def test_editing_two_blocks_at_once_keeps_both_edits() -> None:
    """The census run strips every block; bottom-up editing must not shift spans."""
    out = ms.render_stripped(SAMPLE, {0: {"call-arg", "no-untyped-def"}, 1: {"misc"}})
    overrides = ms.parse_overrides(out)
    assert [o.codes for o in overrides] == [[], [], []]
    assert overrides[2].modules == ["ui.*"]


def test_a_prose_mention_of_disable_error_code_is_not_edited() -> None:
    """The comment above block 0 names the key; only the assignment may be rewritten."""
    out = ms.render_stripped(SAMPLE, {0: {"call-arg"}})
    assert "# A comment mentioning disable_error_code in prose." in out


def test_stripping_a_block_with_no_such_assignment_aborts() -> None:
    with pytest.raises(ms.AuditError, match="no disable_error_code"):
        ms.render_stripped(SAMPLE, {2: {"misc"}})


# ============================================================================
# THE GUARD ITSELF: write_stripped_config must be able to FAIL
# ============================================================================


def test_write_verifies_against_the_reparsed_file(tmp_path: Path) -> None:
    target = tmp_path / "cfg.toml"
    ms.write_stripped_config(SAMPLE, {0: {"call-arg"}}, target)
    assert ms.parse_overrides(target.read_text())[0].codes == ["no-untyped-def"]


def test_the_verification_guard_is_not_vacuous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Positive control: a surgery that removes the WRONG code must be caught.

    Without this the guard could be comparing something to itself and passing
    unconditionally — the exact shape of defect #876 shipped and had to fix, where
    a test derived from the same misreading as the code pinned the bug as intended.
    """

    real_render = ms.render_stripped

    def wrong_edit(text: str, removals: dict[int, set[str]]) -> str:
        # Ignore what was asked for; strip a different code entirely.
        return real_render(text, {1: {"misc"}})

    monkeypatch.setattr(ms, "render_stripped", wrong_edit)
    with pytest.raises(ms.AuditError, match="expected"):
        ms.write_stripped_config(SAMPLE, {0: {"call-arg"}}, tmp_path / "cfg.toml")


# ============================================================================
# ATTRIBUTION: reading errors and the unused-section note off mypy's output
# ============================================================================


def test_parses_the_error_code_off_a_real_mypy_line() -> None:
    output = (
        'core/services/foo.py:12:5: error: Argument 1 has incompatible type "str"; '
        'expected "int"  [arg-type]'
    )
    errors = ms.parse_errors(output)
    assert {e.code for e in errors} == {"arg-type"}
    assert next(iter(errors)).path == "core/services/foo.py"
    assert next(iter(errors)).line == "12"


def test_lines_without_a_code_suffix_are_not_counted() -> None:
    """A missing `[code]` must not be attributed to some arbitrary code.

    Mis-attribution in this direction reads as a vacuous entry and licenses a
    wrong deletion, so an unparseable line is dropped rather than guessed at.
    """
    output = "\n".join(
        [
            "core/x.py:1:1: error: something with no code suffix",
            "core/x.py:2:1: note: some explanatory note  [misc]",
            "Found 1 error in 1 file (checked 2002 source files)",
        ]
    )
    assert ms.parse_errors(output) == set()


def test_identical_errors_in_different_files_are_counted_separately() -> None:
    output = "\n".join(
        [
            "core/a.py:3:1: error: Cannot assign to a method  [method-assign]",
            "core/b.py:3:1: error: Cannot assign to a method  [method-assign]",
        ]
    )
    assert len(ms.parse_errors(output)) == 2


def test_reads_the_unused_section_note_mypy_actually_printed() -> None:
    """Pinned to the real note from 8234e6c3c — the five targets #876 then deleted."""
    assert ms.parse_unused_sections(REAL_UNUSED_NOTE) == [
        "config",
        "core.patterns.*",
        "core.protocols",
        "psutil.*",
        "rdflib.*",
    ]


def test_no_unused_note_yields_no_findings() -> None:
    assert ms.parse_unused_sections("Success: no issues found in 2002 source files") == []


def test_a_malformed_note_yields_no_findings_rather_than_raising() -> None:
    assert ms.parse_unused_sections("pyproject.toml: note: unused section(s): module = [oops") == []
