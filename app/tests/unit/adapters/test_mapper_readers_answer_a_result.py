"""Every backend read that builds a model answers a refusal as a failed ``Result``.

``from_neo4j_node`` raises ``UnreadableStoredValueError`` on a stored value its field's
type cannot read. A backend method that reaches it — directly, or through helpers in
its own file that answer no ``Result`` themselves — must hand that refusal back as a
failed ``Result``: decorated with ``safe_backend_operation`` or ``with_error_handling``,
or catching it in its own body. Otherwise it raises past its caller, out of a service
that expects a ``Result``, and a page meeting one stray node answers no error at all.

The census reads every module under ``adapters/persistence/neo4j/`` by syntax tree.
"""

from __future__ import annotations

import ast
from pathlib import Path

PERSISTENCE = Path(__file__).resolve().parents[3] / "adapters" / "persistence" / "neo4j"
GUARDS = frozenset({"safe_backend_operation", "with_error_handling"})
#: Catches that turn the refusal into a failed Result in the method's own body.
GUARDING_CATCHES = frozenset({"Exception"})
#: Methods whose contract is to raise, each with why.
RAISES_BY_CONTRACT: dict[str, str] = {
    "query/unified_query_builder.py::execute": "the fluent builder raises on every failure",
}


def _function_facts(tree: ast.AST) -> dict[str, tuple[set[str], bool]]:
    """Each function's called names, and whether it answers a refusal itself."""
    facts: dict[str, tuple[set[str], bool]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        calls: set[str] = set()
        caught: set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                func = sub.func
                calls.add(func.id if isinstance(func, ast.Name) else getattr(func, "attr", ""))
            if isinstance(sub, ast.ExceptHandler) and sub.type is not None:
                caught.add(ast.unparse(sub.type))
        decorators = {ast.unparse(d).split("(")[0].split(".")[-1] for d in node.decorator_list}
        facts[node.name] = (calls, bool(decorators & GUARDS or caught & GUARDING_CATCHES))
    return facts


def _unguarded_readers(root: Path = PERSISTENCE) -> set[str]:
    """``file::method`` for each public method that can raise the refusal past its caller."""
    found: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        if path.name == "neo4j_mapper.py":
            continue
        facts = _function_facts(ast.parse(path.read_text(encoding="utf-8")))
        # The functions the refusal can leave as an exception: the mapper's callers,
        # then their unguarded callers, to a fixed point.
        raising = {name for name, (calls, _) in facts.items() if "from_neo4j_node" in calls}
        while True:
            leaking = {name for name in raising if not facts[name][1]}
            grown = raising | {name for name, (calls, _) in facts.items() if calls & leaking}
            if grown == raising:
                break
            raising = grown
        relative = path.relative_to(root).as_posix()
        found |= {
            f"{relative}::{name}"
            for name in raising
            if not name.startswith("_") and not facts[name][1]
        }
    return found


def test_every_backend_read_that_builds_a_model_answers_a_result() -> None:
    assert _unguarded_readers() == set(RAISES_BY_CONTRACT)


_GUARDED_MODULE = """
from core.utils.error_boundary import safe_backend_operation

class Backend:
    @safe_backend_operation("list_library")
    async def list_library(self):
        return [from_neo4j_node(node, Ku) for node in self._rows()]

    @safe_backend_operation("get_page")
    async def get_page(self):
        return self._through_a_helper()

    def _through_a_helper(self):
        return from_neo4j_node({}, Ku)
"""


def test_the_census_finds_a_reader_with_its_guard_removed(tmp_path: Path) -> None:
    """Controls over a module of the same shapes: guarded, it names nothing; with
    either guard stripped, it names that reader — the direct one and the one that
    reaches the mapper through a helper."""
    module = tmp_path / "backend.py"

    module.write_text(_GUARDED_MODULE, encoding="utf-8")
    assert _unguarded_readers(tmp_path) == set()

    module.write_text(_GUARDED_MODULE.replace('@safe_backend_operation("list_library")', ""))
    assert _unguarded_readers(tmp_path) == {"backend.py::list_library"}

    module.write_text(_GUARDED_MODULE.replace('@safe_backend_operation("get_page")', ""))
    assert _unguarded_readers(tmp_path) == {"backend.py::get_page"}
