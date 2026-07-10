"""Tests for ContentVaultEdgeWriter — the one sanctioned vault-write adapter.

The safety rails are NON-NEGOTIABLE (PR 4 ruling), so each is tested
explicitly: strict filename shape (traversal structurally impossible),
containment after resolve() (symlink escape), no-overwrite (atomic "x"),
and no implicit directory creation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.vault.content_edge_writer import ContentVaultEdgeWriter

CONTENT = "---\ntype: Edge\n---\n"


def _vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / "edges").mkdir(parents=True)
    return root


@pytest.mark.anyio
async def test_writes_new_edge_file(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    writer = ContentVaultEdgeWriter(root)

    result = await writer.write_edge_file("edge_one-prereq-two.md", CONTENT)

    assert not result.is_error
    written = Path(result.value)
    assert written == root / "edges" / "edge_one-prereq-two.md"
    assert written.read_text(encoding="utf-8") == CONTENT


@pytest.mark.anyio
@pytest.mark.parametrize(
    "filename",
    [
        "../evil.md",
        "edge_a/../b.md",
        "edge_a\\b.md",
        "notedge_a-prereq-b.md",
        "edge_A-PREREQ-B.md",  # uppercase refused
        "edge_a-prereq-b.txt",
        "edge_.md",
        "edge_a-prereq-b.md.md.exe",
        "",
    ],
)
async def test_invalid_filenames_refused(tmp_path: Path, filename: str) -> None:
    root = _vault(tmp_path)
    writer = ContentVaultEdgeWriter(root)

    result = await writer.write_edge_file(filename, CONTENT)

    assert result.is_error
    assert list((root / "edges").iterdir()) == []


@pytest.mark.anyio
async def test_never_overwrites_existing_file(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    existing = root / "edges" / "edge_one-prereq-two.md"
    existing.write_text("authored original", encoding="utf-8")
    writer = ContentVaultEdgeWriter(root)

    result = await writer.write_edge_file("edge_one-prereq-two.md", CONTENT)

    assert result.is_error
    assert "already exists" in result.expect_error().message
    assert existing.read_text(encoding="utf-8") == "authored original"


@pytest.mark.anyio
async def test_symlinked_target_refused(tmp_path: Path) -> None:
    """A valid-named symlink pointing outside edges/ must not be followed."""
    root = _vault(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    (root / "edges" / "edge_one-prereq-two.md").symlink_to(outside)
    writer = ContentVaultEdgeWriter(root)

    result = await writer.write_edge_file("edge_one-prereq-two.md", CONTENT)

    assert result.is_error
    assert outside.read_text(encoding="utf-8") == "outside"


@pytest.mark.anyio
async def test_edges_dir_symlinked_outside_root_refused(tmp_path: Path) -> None:
    """edges/ itself resolving outside the content root is a containment failure."""
    root = tmp_path / "vault"
    root.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (root / "edges").symlink_to(elsewhere)
    writer = ContentVaultEdgeWriter(root)

    result = await writer.write_edge_file("edge_one-prereq-two.md", CONTENT)

    assert result.is_error
    assert list(elsewhere.iterdir()) == []


@pytest.mark.anyio
async def test_missing_edges_dir_refused_not_created(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    writer = ContentVaultEdgeWriter(root)

    result = await writer.write_edge_file("edge_one-prereq-two.md", CONTENT)

    assert result.is_error
    assert not (root / "edges").exists()
