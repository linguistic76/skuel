"""Markup pins for AlpineModal's dialog semantics, on every caller.

Every ``AlpineModal`` renders a ``role="dialog"`` box with ``aria-modal`` and an
``aria-labelledby`` that names a heading inside the same dialog, mounted with
the ``alpineModal`` component that moves, traps and restores focus. The AST
census covers each call site (one renders inside a route closure); the rendered
surfaces check the ids resolve.

The rendered markup of four callers is also kept as fixture files under
``tests/js/fixtures/``, where ``tests/js/alpine-modal.test.js`` mounts it with
the vendored Alpine. The drift test keeps those files equal to what the Python
renders; regenerate them with
``SKUEL_WRITE_JS_FIXTURES=1 uv run pytest tests/unit/ui/test_alpine_modal_markup.py``.
"""

import ast
import itertools
import os
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

import pytest
from fasthtml.common import FT, to_xml

from adapters.inbound.teaching_ui import _new_group_modal
from core.models.event.calendar_models import CalendarItem, CalendarItemType
from core.models.insight.persisted_insight import InsightImpact, InsightType, PersistedInsight
from core.models.type_hints import EntityUID, UserUID
from ui.calendar.components import create_item_details_modal
from ui.gradebook.share_panel import ShareButton
from ui.insights.insight_card import InsightCard
from ui.patterns.relationships.add_modal import AddRelationshipModal

APP_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = APP_ROOT / "tests" / "js" / "fixtures"
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def _walk(node: object) -> Iterator[FT]:
    if isinstance(node, FT):
        yield node
        for child in node.children:
            yield from _walk(child)
    elif isinstance(node, list | tuple):
        for child in node:
            yield from _walk(child)


def _calendar_item() -> FT:
    now = datetime(2026, 8, 1, 12, 0)
    item = CalendarItem(
        uid="habit-habit_1",
        source_uid="habit_1",
        item_type=CalendarItemType.HABIT,
        title="Meditate",
        start_time=now,
        end_time=now,
        streak_count=4,
    )
    return create_item_details_modal(item)


def _insight_card() -> FT:
    insight = PersistedInsight(
        uid="insight.difficulty_pattern.habit_1",
        user_uid=UserUID("user_a"),
        insight_type=InsightType.DIFFICULTY_PATTERN,
        domain="habits",
        title="Habit difficulty detected",
        description="Missed five of the last fourteen days.",
        confidence=0.85,
        impact=InsightImpact.HIGH,
        entity_uid=EntityUID("habit_1"),
        created_at=datetime(2026, 8, 1, 12, 0),
    )
    return InsightCard(insight)


def _add_relationship() -> FT:
    return AddRelationshipModal("task_abc", "tasks")


def _share_button() -> FT:
    return ShareButton("ue_1")


SURFACES: dict[str, Callable[[], FT]] = {
    "calendar item details": _calendar_item,
    "teaching new group": _new_group_modal,
    "gradebook share panel": _share_button,
    "insight detail": _insight_card,
    "add relationship": _add_relationship,
}


@pytest.mark.parametrize("surface", list(SURFACES))
def test_every_rendered_modal_is_a_named_modal_dialog(surface: str) -> None:
    tree = SURFACES[surface]()
    dialogs = [el for el in _walk(tree) if el.attrs.get("role") == "dialog"]
    assert len(dialogs) == 1, f"{surface}: expected one dialog, found {len(dialogs)}"
    (dialog,) = dialogs
    assert dialog.attrs.get("aria-modal") == "true"
    assert dialog.attrs.get("tabindex") == "-1"
    assert dialog.attrs.get("x-on:keydown.tab") == "modalTrapTab($event)"
    assert dialog.attrs.get("x-on:keydown.escape.stop"), f"{surface}: Escape does not close"
    title_id = dialog.attrs.get("aria-labelledby")
    titles = [el for el in _walk(dialog) if el.attrs.get("id") == title_id]
    assert len(titles) == 1 and titles[0].tag in HEADINGS, (
        f"{surface}: aria-labelledby={title_id!r} names no heading inside the dialog"
    )
    wrappers = [el for el in _walk(tree) if el.attrs.get("x-data") == "alpineModal"]
    assert len(wrappers) == 1
    assert str(wrappers[0].attrs.get("x-effect", "")).startswith("modalToggled(")


def _alpine_modal_calls() -> Iterator[tuple[Path, ast.AST, ast.Call]]:
    """Each AlpineModal call with the function that builds it (or the module)."""
    for root in ("ui", "adapters"):
        for path in sorted((APP_ROOT / root).rglob("*.py")):
            tree = ast.parse(path.read_text())
            scopes: list[ast.AST] = [tree]
            scopes += [
                n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
            ]
            seen: set[int] = set()
            for scope in reversed(scopes):  # innermost function first
                for node in ast.walk(scope):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == "AlpineModal"
                        and id(node) not in seen
                    ):
                        seen.add(id(node))
                        yield path, scope, node


def _heading_ids(scope: ast.AST) -> set[str]:
    ids: set[str] = set()
    for node in ast.walk(scope):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id.lower() in HEADINGS
        ):
            ids.update(ast.unparse(kw.value) for kw in node.keywords if kw.arg == "id")
    return ids


def test_every_alpine_modal_call_names_a_heading_it_renders() -> None:
    calls = list(_alpine_modal_calls())
    assert len(calls) >= 6, "the census lost the AlpineModal callers"
    for path, scope, call in calls:
        title = [ast.unparse(kw.value) for kw in call.keywords if kw.arg == "title_id"]
        where = f"{path.relative_to(APP_ROOT)}:{call.lineno}"
        assert title, f"{where}: AlpineModal without title_id"
        if path.name == "modal.py":
            continue
        assert title[0] in _heading_ids(scope), (
            f"{where}: title_id={title[0]} is not the id of a heading the function renders"
        )


FIXTURE_SURFACES: dict[str, Callable[[], FT]] = {
    "alpine-modal-add-relationship.html": _add_relationship,
    "alpine-modal-calendar.html": _calendar_item,
    "alpine-modal-insight.html": _insight_card,
    "alpine-modal-share.html": _share_button,
}


def _counting_token_hex() -> Callable[[int], str]:
    counter = itertools.count(1)

    def token_hex(nbytes: int = 4) -> str:
        return f"{next(counter):0{2 * nbytes}x}"

    return token_hex


@pytest.mark.parametrize("name", list(FIXTURE_SURFACES))
def test_js_fixture_matches_the_rendered_markup(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # The entity picker suffixes its ids with a random token; count instead.
    monkeypatch.setattr("ui.patterns.entity_picker.secrets.token_hex", _counting_token_hex())
    rendered = to_xml(FIXTURE_SURFACES[name]())
    path = FIXTURES / name
    if os.environ.get("SKUEL_WRITE_JS_FIXTURES") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered)
    assert path.exists() and path.read_text() == rendered, (
        f"{path} is stale — regenerate with SKUEL_WRITE_JS_FIXTURES=1 "
        "uv run pytest tests/unit/ui/test_alpine_modal_markup.py"
    )
