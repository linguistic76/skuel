"""Every insight writer stores a domain word from ``InsightDomain``.

``PersistedInsight.domain`` is a ``str``, so mypy cannot hold a writer to the
vocabulary the ``/insights`` domain filter validates against — a writer storing a
word outside it would write insights no filter can select. This census reads every
``PersistedInsight(...)`` / ``PersistedInsight.with_default_expiry(...)`` /
``persist_principle_alignment_insight(...)`` call under ``core/`` and checks its
``domain=`` argument: a string literal must be a member's value, and a name is
admitted only where the alignment writer forwards its own parameter.
"""

from __future__ import annotations

import ast
from pathlib import Path

from core.models.insight.persisted_insight import InsightDomain

CORE = Path(__file__).resolve().parents[3] / "core"
WRITERS = frozenset(
    {"PersistedInsight", "with_default_expiry", "persist_principle_alignment_insight"}
)
# The one writer that takes the domain from its caller, whose calls the census reads too.
FORWARDS = ("services/insight/alignment_insight.py", "domain")


def _callee(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _domain_args(source: str, relative: str) -> tuple[list[str], list[str]]:
    """(the literals the writer calls in ``source`` store, every offending argument)."""
    literals: list[str] = []
    offending: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or _callee(node) not in WRITERS:
            continue
        for keyword in node.keywords:
            if keyword.arg != "domain":
                continue
            value = keyword.value
            where = f"{relative}:{node.lineno}"
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                literals.append(value.value)
                if value.value not in {member.value for member in InsightDomain}:
                    offending.append(f"{where} domain={value.value!r}")
            elif isinstance(value, ast.Name) and (relative, value.id) == FORWARDS:
                continue
            else:
                offending.append(f"{where} domain={ast.unparse(value)}")
    return literals, offending


def _census() -> tuple[list[str], list[str]]:
    literals: list[str] = []
    offending: list[str] = []
    for path in sorted(CORE.rglob("*.py")):
        relative = path.relative_to(CORE).as_posix()
        found, bad = _domain_args(path.read_text(), relative)
        literals.extend(found)
        offending.extend(bad)
    return literals, offending


def test_every_writer_stores_an_insight_domain() -> None:
    literals, offending = _census()

    assert not offending, (
        "an insight writer stores a domain outside InsightDomain — add the member, "
        "or write a member's value:\n" + "\n".join(offending)
    )
    # The census reads the writers it claims to: each member is some writer's literal.
    assert set(literals) == {member.value for member in InsightDomain}


def test_the_census_flags_a_word_outside_the_vocabulary() -> None:
    sample = (
        "PersistedInsight(uid='x', domain='ku')\n"
        "PersistedInsight.with_default_expiry(domain=word)\n"
        "persist_principle_alignment_insight(store, log, domain='tasks')\n"
    )

    _literals, offending = _domain_args(sample, "services/sample.py")

    assert offending == ["services/sample.py:1 domain='ku'", "services/sample.py:2 domain=word"]
