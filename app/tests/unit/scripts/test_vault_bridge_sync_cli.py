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


@pytest.mark.parametrize(
    ("argv", "exit_code", "preview_call", "sync_call"),
    [
        pytest.param(
            ["--vault", "content", "--preview"],
            0,
            ("content", "user:system"),
            None,
            id="preview, content vault: dry run only, placeholder user",
        ),
        pytest.param(
            ["--user", "user_x", "--preview"],
            0,
            ("personal", "user_x"),
            None,
            id="preview, personal vault: dry run only, named user honoured",
        ),
        pytest.param(
            ["--user", "user_x"],
            0,
            None,
            ("personal", "user_x"),
            id="default: sync, not preview",
        ),
        pytest.param(
            ["--vault", "content", "--preview", "--force"],
            2,
            None,
            None,
            id="preview + force refused (argparse usage error): --force is a sync knob",
        ),
    ],
)
def test_dispatch_per_argv_state(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    exit_code: int,
    preview_call: tuple[str, str] | None,
    sync_call: tuple[str, str] | None,
) -> None:
    """Every dispatch state in one table: which coroutine ran, with what, and
    that the other did not — so a new flag without a row is visible at a glance
    (Kody rule: per-state tests for state-driven construction)."""
    code, preview, sync = _run(monkeypatch, *argv)
    assert code == exit_code
    if preview_call is None:
        preview.assert_not_called()
    else:
        preview.assert_awaited_once_with(*preview_call)
    if sync_call is None:
        sync.assert_not_called()
    else:
        sync.assert_awaited_once_with(*sync_call, force=False)
