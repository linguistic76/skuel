"""CI-enforced content boundary: no proprietary vault content tracked in this PUBLIC repo.

Backs the principle "repo carries the machinery; vault carries the content." CI runs
tests/unit/, so this test is the gate that catches vault content (Kus, PathSteps,
taxonomies, per-user vault mirrors) being committed. Logic lives in
scripts/audit_content_boundary.py (also wired into ./dev quality).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit_content_boundary.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("audit_content_boundary", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_by_path(rel: str):
    """Load a module by file path, bypassing the package __init__ import chain
    (the guard runs on bare Python in CI and must not pull in heavy deps)."""
    path = Path(__file__).resolve().parents[2] / rel
    spec = importlib.util.spec_from_file_location(path.stem + "_boundary", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_guard_covers_ingestion_aliases() -> None:
    """The guard's CONTENT_TYPES must be a superset of ingestion's accepted type
    vocabulary (EntityType.from_string aliases). This is the anti-drift backstop:
    if ingestion gains a new alias the guard doesn't cover, this fails so the set
    is kept in sync rather than silently going blind to a new ingestible format."""
    guard = _load_guard()
    ee = _load_by_path("core/models/enums/entity_enums.py")
    uncovered = sorted(
        a for a in ee._ENTITY_TYPE_ALIASES if guard._normalize_type(a) not in guard.CONTENT_TYPES
    )
    assert not uncovered, (
        "Ingestion accepts type aliases the content-boundary guard does not cover — "
        "add them to CONTENT_TYPES in scripts/audit_content_boundary.py:\n  " + ", ".join(uncovered)
    )


def test_no_vault_content_tracked_in_repo() -> None:
    guard = _load_guard()
    violations = guard.find_violations()
    assert not violations, (
        "Proprietary vault content is tracked in the PUBLIC repo — move it to the "
        "private vault (~/0bsidian) and keep only mechanism docs here:\n  "
        + "\n  ".join(violations)
    )


def test_guard_detects_content_frontmatter(tmp_path: Path) -> None:
    """The structural detector fires on a real vault-entity frontmatter and not on a
    fenced yaml example inside a doc."""
    guard = _load_guard()

    entity = tmp_path / "ku_example.md"
    entity.write_text("---\ntype: Ku\nuid: ku:demo:x\ntitle: X\n---\n\nbody\n")
    assert guard._looks_like_vault_entity(entity) == "Ku"

    doc = tmp_path / "guide.md"
    doc.write_text("# Guide\n\nExample:\n\n```yaml\ntype: Ku\n```\n")
    assert guard._looks_like_vault_entity(doc) is None

    # Plain-YAML vault entity (no --- fence; SKUEL authors Kus/LP as bare YAML).
    yaml_entity = tmp_path / "ku_example.yaml"
    yaml_entity.write_text("# Ku: Example\nversion: 1.0\ntype: Ku\nuid: ku:demo:x\n")
    assert guard._looks_like_vault_entity(yaml_entity) == "Ku"

    # Benign YAML (config/workflow) must not trip it.
    benign = tmp_path / "config.yaml"
    benign.write_text("name: CI\non:\n  push:\n    branches: [main]\ntype: object\n")
    assert guard._looks_like_vault_entity(benign) is None

    # Canonical snake_case / alias / edge type strings normalize and are caught.
    ue = tmp_path / "ue.yaml"
    ue.write_text("type: user_entry\npipeline: extract_activities\n")
    assert guard._looks_like_vault_entity(ue) == "user_entry"

    edge = tmp_path / "edge.yaml"
    edge.write_text("type: Edge\nfrom: ku:a\nto: ku:b\n")
    assert guard._looks_like_vault_entity(edge) == "Edge"

    assert guard._normalize_type("user_entry") == "userentry"
    assert guard._normalize_type("path-step") == "pathstep"
    assert guard._normalize_type("Path Step") == "pathstep"

    # Spaced display-name type (ingestion's from_string normalizes spaces).
    spaced = tmp_path / "spaced.yaml"
    spaced.write_text("type: Learning Path\nuid: lp:x\n")
    assert guard._looks_like_vault_entity(spaced) == "Learning Path"

    # MOC markdown: classified as PathStep by ingestion via `moc: true`, no type:.
    moc = tmp_path / "moc_doc.md"
    moc.write_text("---\nmoc: true\ntitle: Map\n---\n\n[[link-a]] [[link-b]]\n")
    assert guard._looks_like_vault_entity(moc) == "PathStep (moc: true)"

    # A plain markdown doc (no frontmatter, mentions moc in prose) is not content.
    plain = tmp_path / "readme.md"
    plain.write_text("# Readme\n\nWe support moc: true files in the vault.\n")
    assert guard._looks_like_vault_entity(plain) is None


def test_archive_carriers_flagged_except_served_assets() -> None:
    """Binary archives can smuggle a vault export past the text checks; they are
    rejected as content carriers unless they are served assets under static/."""
    guard = _load_guard()
    assert "vault_export.zip".endswith(guard.ARCHIVE_SUFFIXES)
    # A served template archive is exempt; a stray tracked archive elsewhere is not.
    assert "static/templates/x.zip".startswith(guard.ALLOWED_ARCHIVE_PREFIXES)
    assert not "core/leaked_bundle.zip".startswith(guard.ALLOWED_ARCHIVE_PREFIXES)
