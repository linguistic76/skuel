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
