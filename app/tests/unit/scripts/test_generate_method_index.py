"""
Drift + honesty guards for docs/reference/BASESERVICE_METHOD_INDEX.md
=====================================================================

Same pattern as test_generate_graph_contract.py: the artifact is a checked-in
generated view whose freshness is enforced by byte-comparing it against a
fresh render. There is no commit-time automation — the generator's original
docstring claimed a pre-commit hook that was never wired, which is exactly
how the artifact silently sat stale for months.

The honesty guards pin the properties the index exists to provide:
- the mixin sections mirror ``BaseService.__bases__`` exactly (a newly
  composed mixin cannot be silently omitted), and
- every Activity Domain facade contributes a non-empty facade-specific
  method list (the dead ``_delegations`` extraction rendered all six
  facades as "0 methods" for months — the silent-zero failure mode).
"""

import re
import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from generate_method_index import (  # type: ignore[import-not-found]
    ARTIFACT_PATH,
    FACADES,
    facade_specific_methods,
    mixin_spine,
    render_method_index,
)

from core.services.base_service import BaseService


def test_artifact_is_fresh() -> None:
    """The checked-in markdown must byte-match a fresh render of its sources."""
    assert ARTIFACT_PATH.exists(), (
        f"{ARTIFACT_PATH} is missing. "
        "Generate it: cd app && uv run python scripts/generate_method_index.py"
    )
    assert ARTIFACT_PATH.read_text(encoding="utf-8") == render_method_index(), (
        "docs/reference/BASESERVICE_METHOD_INDEX.md is stale — a BaseService "
        "mixin or an Activity Domain facade changed without regenerating the "
        "view. Run: cd app && uv run python scripts/generate_method_index.py"
    )


def test_mixin_sections_mirror_base_service_composition() -> None:
    """Every mixin BaseService composes gets a section; no phantom sections."""
    spine_names = {mixin.__name__ for mixin in mixin_spine()}
    assert spine_names == {
        base.__name__ for base in BaseService.__bases__ if base.__name__.endswith("Mixin")
    }

    rendered_sections = set(re.findall(r"^### (\w+Mixin)$", render_method_index(), re.MULTILINE))
    assert rendered_sections == spine_names | {"KnowledgeIntelligenceDelegationMixin"}


def test_every_facade_lists_a_nonempty_specific_surface() -> None:
    """All six facades appear and none regresses to the silent-zero state."""
    content = render_method_index()
    assert len(FACADES) == 6
    for facade in FACADES:
        assert f"### {facade.__name__}" in content
        assert facade_specific_methods(facade), (
            f"{facade.__name__} reports no facade-specific public methods — "
            "either the facade genuinely lost its surface (unlikely) or the "
            "MRO attribution in generate_method_index.py broke."
        )
