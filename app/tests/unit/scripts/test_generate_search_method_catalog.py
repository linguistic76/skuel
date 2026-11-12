"""
Drift + honesty guards for docs/reference/SEARCH_SERVICE_METHODS.md
===================================================================

Same pattern as test_generate_method_index.py: the catalog is a checked-in
generated view, held fresh by byte-comparing it against a fresh render.

The guards pin what the generated view exists to provide:

- every matrix row names a method at least one search service has,
- every service's own methods are listed in its section, and
- each activity domain doc's ``## Search Methods`` section names only methods
  its search service has, so a hand table cannot grow back beside the catalog.
"""

import re
import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from generate_search_method_catalog import (  # type: ignore[import-not-found]
    ARTIFACT_PATH,
    PROJECT_ROOT,
    SERVICES,
    render_catalog,
    service_methods,
)

_MATRIX_ROW = re.compile(r"^\| `([a-z_]+)\(\)`", re.MULTILINE)
_NAMED_CALL = re.compile(r"`([a-z_][a-z0-9_]*)\(")

# The six activity domain docs and the search service each one's
# `## Search Methods` section describes.
_DOMAIN_DOCS: dict[str, str] = {
    "tasks": "TasksSearchService",
    "goals": "GoalsSearchService",
    "habits": "HabitsSearchService",
    "events": "EventsSearchService",
    "choices": "ChoicesSearchService",
    "principles": "PrinciplesSearchService",
}


def _service(class_name: str) -> type:
    return next(entry.cls for entry in SERVICES if entry.cls.__name__ == class_name)


def _section(text: str, heading: str) -> str:
    start = text.index(f"\n{heading}\n")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def test_artifact_is_fresh() -> None:
    """The checked-in markdown must byte-match a fresh render of its sources."""
    assert ARTIFACT_PATH.exists(), (
        f"{ARTIFACT_PATH} is missing. "
        "Generate it: cd app && uv run python scripts/generate_search_method_catalog.py"
    )
    assert ARTIFACT_PATH.read_text(encoding="utf-8") == render_catalog(), (
        "docs/reference/SEARCH_SERVICE_METHODS.md is stale — a search service or one "
        "of its mixins changed without regenerating the view. "
        "Run: cd app && uv run python scripts/generate_search_method_catalog.py"
    )


def test_every_matrix_row_names_a_live_method() -> None:
    """No row of the matrix names a method that no search service has."""
    rows = _MATRIX_ROW.findall(render_catalog())
    assert rows, "the matrix rendered no rows — the row pattern or the renderer broke"
    for name in rows:
        assert any(getattr(entry.cls, name, None) is not None for entry in SERVICES), (
            f"matrix row `{name}()` names a method no search service has"
        )


def test_every_service_section_lists_its_own_methods() -> None:
    """Each service's section lists every method the service defines itself."""
    content = render_catalog()
    for entry in SERVICES:
        heading = f"\n### {entry.cls.__name__}\n"
        start = content.index(heading) + len(heading)
        section = content[start:].split("\n### ", 1)[0].split("\n## ", 1)[0]
        assert section.strip(), f"{entry.cls.__name__}'s catalog section is empty"
        for name in service_methods(entry.cls):
            assert f"| `{name}` |" in section, (
                f"{entry.cls.__name__}.{name} is missing from its catalog section"
            )


def test_domain_docs_name_only_live_search_methods() -> None:
    """A domain doc's § Search Methods names no method its search service lacks."""
    for domain, class_name in _DOMAIN_DOCS.items():
        doc = PROJECT_ROOT / "docs" / "domains" / f"{domain}.md"
        section = _section(doc.read_text(encoding="utf-8"), "## Search Methods")
        assert f"`{class_name}`" in section, f"{doc.name} § Search Methods names no service"
        cls = _service(class_name)
        for name in _NAMED_CALL.findall(section):
            assert getattr(cls, name, None) is not None, (
                f"{doc.name} § Search Methods names `{name}(`, which "
                f"{class_name} does not have — the method list lives in "
                "docs/reference/SEARCH_SERVICE_METHODS.md (generated)"
            )
