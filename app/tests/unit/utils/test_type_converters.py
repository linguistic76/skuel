"""Unit tests for core/utils/type_converters.py — the canonical duck-typed
conversion layer.

Two of these tests are structural guards, not behavior checks:

- ``test_module_is_an_import_leaf`` pins the property that makes the single
  canonical copy possible at all: the module imports only stdlib, so any
  module (including ``core.ports``) can import from it without a cycle.
- ``test_to_dict_converts_plain_dataclass`` pins the branch that silently
  went missing when the module was duplicated into
  ``core.ports.base_protocols`` (the copies drifted; the ports copy dropped
  the dataclass branch). It is the red test that duplication-by-copy earns.
"""

import ast
import inspect
from dataclasses import dataclass
from enum import Enum
from types import SimpleNamespace

from pydantic import BaseModel

import core.utils.type_converters as type_converters
from core.utils.type_converters import (
    EnumLike,
    finite_float,
    get_enum_attr_str,
    get_enum_value,
    normalize_enum_str,
    to_dict,
)


class _Color(Enum):
    RED = "red"


class _PydanticUser(BaseModel):
    name: str


@dataclass(frozen=True)
class _FrozenPoint:
    x: int
    y: int


@dataclass(frozen=True)
class _FrozenWithToDict:
    x: int

    def to_dict(self) -> dict[str, object]:
        return {"custom": self.x}


class TestModuleStructure:
    def test_module_is_an_import_leaf(self) -> None:
        tree = ast.parse(inspect.getsource(type_converters))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        first_party = {
            module
            for module in imported
            if module.split(".")[0] in {"core", "adapters", "ui", "services_bootstrap"}
        }
        assert not first_party, (
            f"type_converters must stay a stdlib-only import leaf "
            f"(cycle-proof from anywhere), but imports: {sorted(first_party)}"
        )


class TestToDict:
    def test_pydantic_model_uses_model_dump(self) -> None:
        assert to_dict(_PydanticUser(name="Alice")) == {"name": "Alice"}

    def test_dict_passes_through(self) -> None:
        payload = {"key": "value"}
        assert to_dict(payload) is payload

    def test_converts_plain_dataclass(self) -> None:
        assert to_dict(_FrozenPoint(x=1, y=2)) == {"x": 1, "y": 2}

    def test_own_to_dict_outranks_dataclass_reflection(self) -> None:
        assert to_dict(_FrozenWithToDict(x=7)) == {"custom": 7}

    def test_sequence_converts_recursively(self) -> None:
        assert to_dict([_FrozenPoint(x=1, y=2), {"a": 1}]) == [{"x": 1, "y": 2}, {"a": 1}]

    def test_primitive_passes_through(self) -> None:
        assert to_dict(42) == 42


class TestGetEnumValue:
    def test_extracts_enum_value(self) -> None:
        assert get_enum_value(_Color.RED) == "red"

    def test_plain_value_passes_through(self) -> None:
        assert get_enum_value("already_a_string") == "already_a_string"

    def test_enum_matches_protocol(self) -> None:
        assert isinstance(_Color.RED, EnumLike)
        assert not isinstance("plain", EnumLike)


class TestGetEnumAttrStr:
    def test_enum_attribute_lowercased(self) -> None:
        assert get_enum_attr_str(SimpleNamespace(status=_Color.RED), "status") == "red"

    def test_string_attribute_lowercased(self) -> None:
        assert get_enum_attr_str(SimpleNamespace(status="Pending"), "status") == "pending"

    def test_missing_attribute_returns_default(self) -> None:
        assert get_enum_attr_str(SimpleNamespace(), "status", "unknown") == "unknown"


class TestNormalizeEnumStr:
    def test_enum_lowercased(self) -> None:
        assert normalize_enum_str(_Color.RED) == "red"

    def test_string_lowercased(self) -> None:
        assert normalize_enum_str("Pending") == "pending"

    def test_none_returns_default(self) -> None:
        assert normalize_enum_str(None, "unknown") == "unknown"


class TestFiniteFloat:
    def test_int_converts(self) -> None:
        assert finite_float(40) == 40.0

    def test_numeric_string_converts(self) -> None:
        assert finite_float("40") == 40.0

    def test_non_numeric_string_is_none(self) -> None:
        assert finite_float("forty") is None

    def test_nan_is_none(self) -> None:
        assert finite_float(float("nan")) is None

    def test_inf_is_none(self) -> None:
        assert finite_float(float("inf")) is None

    def test_none_is_none(self) -> None:
        assert finite_float(None) is None

    def test_list_is_none(self) -> None:
        assert finite_float([1, 2]) is None
