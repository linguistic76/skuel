"""Registry/factory agreement for the Activity Domain sub-service factory.

``ACTIVITY_DOMAIN_CONFIGS`` names the class that fills each sub-service slot, and
``create_common_sub_services`` constructs it with a fixed set of keyword arguments.
Nothing but these tests keeps the two in step at runtime:

- MyPy checks each registered class against the ``_*Factory`` protocols in
  ``activity_domain_config``, but those protocols are hand-written. If a protocol
  drifts from the call the factory actually makes, MyPy goes on checking the stale
  contract and stays green.
- So the kwargs here are read out of the factory's own source with ``ast``, never
  copied. A hand-copied mirror is exactly what drifts.

The invariant was not always true: before class references replaced module-name
strings, ``habits`` and ``choices`` registered intelligence services requiring a
``cross_domain_query`` argument the factory never passes. Both entries were dead —
the facades build their own — and unconstructible, and nothing could see it.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from core.services import activity_domain_config
from core.services.activity_domain_config import (
    ACTIVITY_DOMAIN_CONFIGS,
    create_common_sub_services,
)

SLOTS = (
    "core_class",
    "search_class",
    "intelligence_class",
    "event_handler_class",
    "learning_class",
)


def _factory_call_kwargs() -> dict[str, list[str]]:
    """Read `config.<slot>(...)` keyword names out of the factory's own source."""
    tree = ast.parse(inspect.getsource(activity_domain_config))
    found: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in SLOTS):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "config"):
            continue
        found[func.attr] = [kw.arg for kw in node.keywords if kw.arg is not None]
    return found


def test_every_slot_is_constructed_somewhere_in_the_factory() -> None:
    """Guards the guard: if a slot stops being constructed, the checks below go vacuous."""
    calls = _factory_call_kwargs()
    assert sorted(calls) == sorted(SLOTS), (
        f"factory constructs {sorted(calls)}, registry declares {sorted(SLOTS)} — "
        "a slot with no construction site would make the agreement test vacuous"
    )


@pytest.mark.parametrize("domain", sorted(ACTIVITY_DOMAIN_CONFIGS))
@pytest.mark.parametrize("slot", SLOTS)
def test_registered_class_accepts_the_factory_kwargs(domain: str, slot: str) -> None:
    """Every registered class is constructible exactly the way the factory builds it."""
    # The slots hold classes, so `type[object]` types the reflection precisely — no `Any`
    # needed. A union of the `_*Factory` protocols does NOT work here: a callback Protocol
    # describes callable *instances*, so it has no `__name__` and reading `__init__` off it
    # is unsound (measured: 3 MyPy errors).
    registered: type[object] | None = getattr(ACTIVITY_DOMAIN_CONFIGS[domain], slot)
    if registered is None:
        # Only the intelligence slot is optional — see ActivityDomainConfig.
        assert slot == "intelligence_class", f"{domain}.{slot} may not be None"
        return

    passed = _factory_call_kwargs()[slot]
    params = inspect.signature(registered.__init__).parameters
    takes_var_kwargs = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())

    unaccepted = [name for name in passed if name not in params and not takes_var_kwargs]
    assert not unaccepted, (
        f"{domain}.{slot} = {registered.__name__} does not accept {unaccepted}, "
        f"but create_common_sub_services passes it"
    )

    unmet = [
        name
        for name, param in params.items()
        if name != "self"
        and param.default is inspect.Parameter.empty
        and param.kind in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY)
        and name not in passed
    ]
    assert not unmet, (
        f"{domain}.{slot} = {registered.__name__} requires {unmet}, "
        f"which create_common_sub_services never passes — constructing it would raise TypeError"
    )


def test_intelligence_is_not_skippable() -> None:
    """`skip` no longer decides intelligence; the registry does."""
    with pytest.raises(ValueError, match="Invalid skip names"):
        create_common_sub_services(
            domain="principles",
            backend=object(),
            graph_intel=object(),
            skip={"intelligence"},
        )
