"""Every Pydantic model no production file reads has a verdict in its register.

The bloat detector's PLANNED tier holds events, methods, templates and embedding
maps, not classes, so a request or view model nothing reads is registered in
``docs/roadmap/request-models-no-door-reads.md`` with what it waits on. This test
holds that register to the code both ways:

- every model under ``core/models`` that no production file reads is in the
  register, so a new one cannot land without a verdict; and
- every name the register holds is a model under ``core/models``, so a deleted
  model cannot leave its row behind.

A read is the model's name as a word in a tracked ``.py`` file outside ``tests/``
(and outside the vulture whitelist, which names code so a scanner keeps it). The
model's own class line, a package ``__init__.py`` and an ``__all__`` entry are not
reads; a docstring is, so the unread set is a floor. A registered model that gains a
reader keeps its row until a session takes it out: this test never demands that.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
import subprocess
import sys
from functools import cache
from pathlib import Path

from pydantic import BaseModel

import core.models

APP = Path(__file__).resolve().parents[3]
REGISTER = APP / "docs" / "roadmap" / "request-models-no-door-reads.md"
#: A register row: its first cell is the model, its second the module that defines it.
_ROW = re.compile(r"^\| `(?P<name>[A-Za-z_][A-Za-z0-9_]*)` \| `(?P<file>core/models/[^`]+\.py)` \|")
#: Tracked Python that names code without reading it.
_NOT_READERS = ("tests/", "vulture_whitelist.py")


@cache
def _models() -> dict[str, str]:
    """Every Pydantic model defined under ``core/models``: name -> defining file."""
    for info in pkgutil.walk_packages(core.models.__path__, "core.models."):
        importlib.import_module(info.name)
    found: dict[str, str] = {}
    stack: list[type[BaseModel]] = [BaseModel]
    while stack:
        for sub in stack.pop().__subclasses__():
            stack.append(sub)
            if sub.__module__.startswith("core.models."):
                source = sys.modules[sub.__module__].__file__
                assert source is not None, sub.__module__
                found[sub.__name__] = Path(source).resolve().relative_to(APP).as_posix()
    return found


@cache
def _production_sources() -> dict[str, str]:
    out = subprocess.run(
        ["git", "ls-files", "*.py"], cwd=APP, capture_output=True, text=True, check=True
    ).stdout
    return {
        path: (APP / path).read_text(encoding="utf-8")
        for path in out.split()
        if not path.startswith(_NOT_READERS)
    }


def _is_read(name: str, own_file: str, sources: dict[str, str]) -> bool:
    word = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])")
    for path, text in sources.items():
        if path.endswith("__init__.py") or name not in text or not word.search(text):
            continue
        if path != own_file:
            return True
        for line in text.splitlines():
            stripped = line.strip()
            if not word.search(line) or stripped in (f'"{name}",', f"'{name}',"):
                continue
            if not line.startswith(f"class {name}("):
                return True
    return False


def _register() -> dict[str, str]:
    """The register's rows: model -> the file its row names."""
    text = REGISTER.read_text(encoding="utf-8")
    assert "\n## Register\n" in text, f"{REGISTER} has no '## Register' section"
    section = text.split("\n## Register\n", 1)[1].split("\n## ", 1)[0]
    rows = [match for line in section.splitlines() if (match := _ROW.match(line))]
    return {match["name"]: match["file"] for match in rows}


def _unread() -> set[str]:
    sources = _production_sources()
    return {name for name, file in _models().items() if not _is_read(name, file, sources)}


def test_the_scan_finds_models_and_reads() -> None:
    models = _models()
    assert len(models) > 100, "the model walk found too few models: it is broken"
    sources = _production_sources()
    # A model a route binds is read; the register's own entries are a control below.
    assert _is_read("TrackHabitRequest", models["TrackHabitRequest"], sources)


def test_every_unread_model_is_registered() -> None:
    missing = sorted(_unread() - set(_register()))
    assert not missing, (
        "A Pydantic model no production file reads needs a verdict: wire it, delete it, "
        f"or register it with its reason in {REGISTER.relative_to(APP)} § Register: {missing}"
    )


def test_every_registered_model_exists_where_its_row_says() -> None:
    models = _models()
    register = _register()
    assert register, f"{REGISTER.relative_to(APP)} § Register has no rows: the parse is broken"
    stale = sorted(
        f"{name} ({file})" for name, file in register.items() if models.get(name) != file
    )
    assert not stale, (
        f"A register row names no model at that file; take the row out or correct its file: {stale}"
    )
