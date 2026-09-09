"""Tests for scripts/health/secret_scan_floor.py — the corpus sweep's own honesty.

The invariant
-------------
**A corpus check that cannot read the corpus has not found "no problems" — it has
found nothing, and must say so.** Every path that could yield an empty or truncated
corpus aborts rather than reporting a clean sweep.

This is not theoretical. The check shipped with ``check=False`` on both its
subprocesses, so a ``grep`` exit 2 (E2BIG on a large repo) or a failed ``sed``
produced an empty file list, an empty diff, and a confident ``✓ no false
positives`` over nothing scanned. Its vacuity probe could not catch it either: the
probe plants a credential in a *single synthetic line*, not in the corpus, so it
stays green while the corpus read is broken.

That is the same fail-open shape as the ``mapfile`` defect in the scan this check
guards — a security instrument reporting success because it was not working. The
tests below pin each abort.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = APP_ROOT / "scripts" / "health" / "secret_scan_floor.py"


def load_module():
    """Import the check by path — scripts/health has no package __init__."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("secret_scan_floor", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestRefusesToReportCleanWithoutReading:
    """Each abort is a refusal to call an unread corpus clean."""

    def test_an_empty_file_list_aborts(self) -> None:
        mod = load_module()
        with pytest.raises(SystemExit) as excinfo:
            mod.as_added_diff([])
        assert excinfo.value.code == 1

    def test_a_grep_error_aborts_instead_of_returning_no_files(self, monkeypatch, capsys) -> None:
        """grep exit 2 is a failure, not 'this repo has no text files'.

        The message is asserted, not just the exit: without the exit-2 guard this
        still aborts, but via the generic empty-result guard — which would pass the
        test while the specific defect went unfixed.
        """
        mod = load_module()
        real = subprocess.run

        def fake(cmd, *args, **kwargs):
            if cmd and cmd[0] == "grep":
                return subprocess.CompletedProcess(cmd, 2, "", "grep: E2BIG")
            return real(cmd, *args, **kwargs)

        monkeypatch.setattr(mod.subprocess, "run", fake)
        with pytest.raises(SystemExit) as excinfo:
            mod.tracked_text_files()
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "grep failed" in out and "exit 2" in out, (
            f"aborted for the wrong reason — the exit-2 guard is what should fire:\n{out}"
        )

    def test_grep_finding_no_matches_is_not_an_error(self, monkeypatch) -> None:
        """Exit 1 means 'no text files in this batch' — an answer, not a failure.

        Conflating it with exit 2 would make an all-binary batch abort the run.
        """
        mod = load_module()
        real = subprocess.run
        seen: list[int] = []

        def fake(cmd, *args, **kwargs):
            if cmd and cmd[0] == "grep":
                seen.append(1)
                # First batch reports no matches; let the rest behave normally.
                if len(seen) == 1:
                    return subprocess.CompletedProcess(cmd, 1, "", "")
            return real(cmd, *args, **kwargs)

        monkeypatch.setattr(mod.subprocess, "run", fake)
        files = mod.tracked_text_files()  # must not raise
        assert files, "later batches should still contribute files"

    def test_a_sed_failure_aborts(self, monkeypatch) -> None:
        mod = load_module()
        real = subprocess.run

        def fake(cmd, *args, **kwargs):
            if cmd and cmd[0] == "sed":
                return subprocess.CompletedProcess(cmd, 4, "", "sed: cannot read")
            return real(cmd, *args, **kwargs)

        monkeypatch.setattr(mod.subprocess, "run", fake)
        with pytest.raises(SystemExit) as excinfo:
            mod.as_added_diff(["README.md"])
        assert excinfo.value.code == 1

    def test_files_that_produce_no_lines_abort(self, monkeypatch) -> None:
        """A silent read failure looks exactly like a clean corpus to the scan."""
        mod = load_module()
        real = subprocess.run

        def fake(cmd, *args, **kwargs):
            if cmd and cmd[0] == "sed":
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return real(cmd, *args, **kwargs)

        monkeypatch.setattr(mod.subprocess, "run", fake)
        with pytest.raises(SystemExit) as excinfo:
            mod.as_added_diff(["README.md"])
        assert excinfo.value.code == 1


class TestBatching:
    """Argument lists are chunked, so a growing repo cannot hit ARG_MAX."""

    def test_chunks_cover_every_item_in_order(self) -> None:
        mod = load_module()
        items = [str(n) for n in range(1000)]
        batches = mod._chunked(items, size=400)
        assert [len(b) for b in batches] == [400, 400, 200]
        assert [x for b in batches for x in b] == items

    def test_an_empty_list_yields_no_batches(self) -> None:
        mod = load_module()
        assert mod._chunked([], size=400) == []


class TestTheSweepIsReal:
    """The happy path, against the actual repository."""

    def test_it_reads_the_real_corpus(self) -> None:
        mod = load_module()
        files = mod.tracked_text_files()
        assert len(files) > 1000, "the tracked corpus should be substantial"
        assert "README.md" in files or any(f.endswith("README.md") for f in files)
