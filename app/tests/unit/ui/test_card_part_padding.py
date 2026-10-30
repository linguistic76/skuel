"""Every card part pads itself, and no caller passes a padding class that loses to it.

``CardHeader``, ``CardBody`` and ``CardFooter`` pad all four sides (``p-6``). A body or
footer directly after another part drops its top: that part's bottom padding already
spaces them. The drop is a sibling selector on the part's own class, so it follows the
rendered card, never the caller.

A caller's padding class is merged after the part's own, but Tailwind orders the
compiled rules, not the class attribute: a bare ``p-4`` compiles before ``p-6`` and never
applies. The guard reads the committed ``output.css`` for the order — the same file the
browser reads — so a class that does win (``px-3``, ``py-2``, ``p-8``) stays allowed.
"""

import ast
import html
import re
from pathlib import Path

import pytest
from fasthtml.common import to_xml

from ui.components.card import CardBody, CardFooter, CardHeader

_APP_ROOT = Path(__file__).resolve().parents[3]
_CSS = (_APP_ROOT / "static/css/output.css").read_text()
_PARTS = {"CardBody": CardBody, "CardFooter": CardFooter, "CardHeader": CardHeader}

# The sides each padding property sets.
_SIDES = {
    "padding": {"top", "right", "bottom", "left"},
    "padding-inline": {"right", "left"},
    "padding-block": {"top", "bottom"},
    "padding-top": {"top"},
    "padding-bottom": {"bottom"},
    "padding-left": {"left"},
    "padding-right": {"right"},
    "padding-inline-start": {"left"},
    "padding-inline-end": {"right"},
}
_PADDING_TOKEN = re.compile(r"^-?p[xytblrse]?-")


def _classes(xml: str) -> list[str]:
    """The class tokens of the outermost element, as the browser reads them (``&amp;`` is ``&``)."""
    match = re.search(r'class="([^"]*)"', xml)
    assert match, xml
    return html.unescape(match.group(1)).split()


def _rule(token: str) -> tuple[int, set[str]] | None:
    """Where ``token``'s utility rule sits in output.css and the sides it pads."""
    escaped = re.sub(r"([^a-zA-Z0-9_-])", r"\\\1", token)
    match = re.search(rf"(?<=[}}\s,])\.{re.escape(escaped)}(?=[,{{])", _CSS)
    if match is None:
        return None
    body = _CSS[_CSS.index("{", match.end()) + 1 : _CSS.index("}", match.end())]
    sides: set[str] = set()
    for declaration in body.split(";"):
        prop = declaration.split(":", 1)[0].strip()
        sides |= _SIDES.get(prop, set())
    return match.start(), sides


def _caller_classes() -> list[tuple[str, str, list[str]]]:
    """Every card-part call in ui/ and adapters/: (site, part, literal cls tokens).

    A call with no ``cls`` has no tokens. A ``cls`` that is not a string literal (or a
    tuple of them), or a ``**`` splat that is not a dict literal with constant keys, is
    returned as ``["<expr>"]`` so the census refuses it instead of skipping it.
    """
    out = []
    for path in sorted(
        [*(_APP_ROOT / "ui").rglob("*.py"), *(_APP_ROOT / "adapters").rglob("*.py")]
    ):
        if path.name == "card.py" and path.parent.name == "components":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name not in _PARTS:
                continue
            values: list[ast.expr] = []
            tokens: list[str] = []
            for kw in node.keywords:
                if kw.arg == "cls":
                    values.append(kw.value)
                elif kw.arg is None:
                    splat = kw.value
                    if not (
                        isinstance(splat, ast.Dict)
                        and all(isinstance(k, ast.Constant) for k in splat.keys)
                    ):
                        tokens.append("<expr>")
                        continue
                    values += [
                        v
                        for k, v in zip(splat.keys, splat.values, strict=True)
                        if isinstance(k, ast.Constant) and k.value in ("cls", "class")
                    ]
            for value in values:
                parts = value.elts if isinstance(value, ast.Tuple) else [value]
                for part in parts:
                    if isinstance(part, ast.Constant) and isinstance(part.value, str):
                        tokens += part.value.split()
                    else:
                        tokens.append("<expr>")
            out.append((f"{path.relative_to(_APP_ROOT)}:{node.lineno}", name, tokens))
    return out


def _base_rules(name: str) -> list[tuple[int, set[str]]]:
    """The compiled rules of a part's own unconditional classes."""
    base = [t for t in _classes(to_xml(_PARTS[name]("x"))) if ":" not in t]
    return [r for r in map(_rule, base) if r is not None]


def _lost(token: str, base_rules: list[tuple[int, set[str]]]) -> set[str]:
    """The sides ``token`` pads that a later rule of the part pads instead."""
    rule = _rule(token)
    assert rule is not None, f"{token} is not in output.css (./dev css-prod)"
    position, sides = rule
    return {s for s in sides for at, base_sides in base_rules if at > position and s in base_sides}


def test_every_card_part_pads_all_four_sides() -> None:
    for name, part in _PARTS.items():
        tokens = _classes(to_xml(part("x")))
        assert "p-6" in tokens, name
        assert "pt-0" not in tokens, f"{name} drops its top unconditionally"


def test_body_and_footer_drop_their_top_only_after_another_part() -> None:
    assert 'data-slot="card-header"' in to_xml(CardHeader("x"))
    assert 'data-slot="card-body"' in to_xml(CardBody("x"))
    body = _classes(to_xml(CardBody("x")))
    footer = _classes(to_xml(CardFooter("x")))
    assert "[[data-slot=card-header]+&]:pt-0" in body
    assert "[[data-slot=card-header]+&]:pt-0" in footer
    assert "[[data-slot=card-body]+&]:pt-0" in footer


def test_the_sibling_rules_are_compiled() -> None:
    # Without the compiled rule every body after a header grows 24px at its top.
    for after in ("card-header", "card-body"):
        selector = re.search(
            rf"\[data-slot={after}\]\+\.\\\[\\\[data-slot\\={after}\\\]\\\+\\&\\\]\\:pt-0[,{{]",
            _CSS,
        )
        assert selector, after
        rule = _CSS[_CSS.index("{", selector.start()) : _CSS.index("}", selector.start()) + 1]
        assert rule == "{padding-top:0}", (after, rule)


def test_the_guard_tells_a_dead_class_from_a_live_one() -> None:
    # p-4 compiles before p-6 and never applies; the others compile after it and win.
    base = _base_rules("CardBody")
    assert _lost("p-4", base) == {"top", "right", "bottom", "left"}
    for live in ("px-3", "py-2", "pt-4", "p-8"):
        assert not _lost(live, base), live


@pytest.mark.parametrize("name", sorted(_PARTS))
def test_no_caller_passes_a_padding_class_the_part_overrides(name: str) -> None:
    base = _base_rules(name)
    dead = [
        f"{site}: {token} loses {sorted(lost)} to {name}'s own padding"
        for site, part, tokens in _caller_classes()
        if part == name
        for token in tokens
        if ":" not in token
        and _PADDING_TOKEN.match(token)  # a variant compiles after every bare utility
        if (lost := _lost(token, base))
    ]
    assert not dead, "\n".join(dead)


def test_every_card_part_cls_is_a_literal() -> None:
    # The guard above reads literal classes only; a computed cls would pass unread.
    computed = [site for site, _, tokens in _caller_classes() if "<expr>" in tokens]
    assert not computed, computed


def test_the_census_sees_the_callers() -> None:
    # A census that finds nothing proves nothing: the card parts have dozens of callers,
    # and some of them pass a cls.
    sites = _caller_classes()
    assert sum(part == "CardBody" for _, part, _ in sites) >= 50
    assert sum(part == "CardHeader" for _, part, _ in sites) >= 40
    assert any(tokens for _, _, tokens in sites)
