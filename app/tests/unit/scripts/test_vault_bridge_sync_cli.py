"""``vault_bridge_sync.py`` argument routing: ``--preview`` is the dry run.

The script composes the whole app, so these tests stop at the argparse/dispatch
seam: which coroutine ``main()`` hands to ``asyncio.run`` and with what, and
the one refused combination. The reconciler behaviour behind each door is
covered where it lives (``test_vault_sync_preview.py``).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import vault_bridge_sync  # type: ignore[import-not-found]


def _run(monkeypatch: pytest.MonkeyPatch, *argv: str) -> tuple[int, AsyncMock, AsyncMock]:
    preview = AsyncMock(return_value=0)
    sync = AsyncMock(return_value=0)
    monkeypatch.setattr(vault_bridge_sync, "run_preview", preview)
    monkeypatch.setattr(vault_bridge_sync, "run_sync", sync)
    monkeypatch.setattr(sys, "argv", ["vault_bridge_sync.py", *argv])
    with pytest.raises(SystemExit) as exc:
        vault_bridge_sync.main()
    return int(exc.value.code or 0), preview, sync


def test_preview_dispatches_to_the_dry_run_only(monkeypatch: pytest.MonkeyPatch) -> None:
    code, preview, sync = _run(monkeypatch, "--vault", "content", "--preview")
    assert code == 0
    preview.assert_awaited_once_with("content", "user:system")
    sync.assert_not_called()


def test_preview_honours_the_named_user_for_a_personal_vault(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    code, preview, sync = _run(monkeypatch, "--user", "user_x", "--preview")
    assert code == 0
    preview.assert_awaited_once_with("personal", "user_x")
    sync.assert_not_called()


def test_default_dispatches_to_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    code, preview, sync = _run(monkeypatch, "--user", "user_x")
    assert code == 0
    sync.assert_awaited_once_with("personal", "user_x", force=False)
    preview.assert_not_called()


def test_preview_and_force_are_refused_together(monkeypatch: pytest.MonkeyPatch) -> None:
    """--force is a sync knob; a dry run has nothing to force."""
    code, preview, sync = _run(monkeypatch, "--vault", "content", "--preview", "--force")
    assert code == 2  # argparse usage error
    preview.assert_not_called()
    sync.assert_not_called()
