"""No integration test writes a uid literal outside the uid grammar.

After each integration test the runtime census (``tests/integration/_uid_census.py``)
reads its graph against the uid grammar (``core/utils/uid_grammar.py``). It sees every
uid a test leaves at a read, computed or literal, but not one a test creates and
deletes inside its body, nor one written to a scratch container of its own. This
census reads the source instead: every uid literal written in ``tests/integration``,
at the edit, wherever it is written. Each covers what the other cannot.

A literal is read where a uid is named — the name ends in ``uid`` or ``uids``
(``uid``, ``owner_uid``, ``TASK_UID``, ``ku_uids``):

- a keyword argument (``create_task(uid="task.001")``);
- a dict key (``{"user_uid": …}``);
- an assignment target (``OWNER_UID = …``, ``self.uid = …``);
- a Cypher property or comparison inside a string (``{uid: '…'}``,
  ``n.user_uid = '…'``, ``<> '…'``).

A keyword or dict key that binds a Cypher parameter the module reads in a uid
position (``ex=…`` beside ``turn_in_exercise_uid: $ex``) is a uid position too. A
list, tuple or set in one of the first three positions has each member read, and a
module constant named there (``uid=EX``) is read as its value, where it is named. A
value is a uid when it looks like one — a prefix word, then ``.``, ``_`` or ``:``,
ending in a letter or digit — so a mock id (``"h"``, ``"m0"``) and a concatenation
fragment (``"ps.bulk-"``, ``"hc.eq."``) are not read.

A test that writes such a uid on purpose carries
``@pytest.mark.outside_uid_grammar("why")`` — the runtime census's marker, on the
test, its class or its module (``pytestmark``), read here from the source. A literal
in a module-level helper is exempt only by the module's marker. When the runtime
census never sees the uid — the test writes it to a scratch container, or names it
without writing it — the marker says ``static_only=True``: the runtime census then
holds the test as unmarked, and this census is the one that holds the marker — a
``static_only`` scope that names no uid outside the grammar fails as stale.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from core.utils.uid_grammar import UidVerdict, classify

INTEGRATION_ROOT = Path(__file__).resolve().parents[1] / "integration"

MARKER = "outside_uid_grammar"

_UID_NAME = re.compile(r"(?:^|_)uids?$", re.IGNORECASE)
_UID_SHAPED = re.compile(r"[A-Za-z][A-Za-z0-9]*[._:][A-Za-z0-9_.:-]*[A-Za-z0-9]")
# `{uid: '…'}`, `n.user_uid = '…'`, `n.uid <> '…'` — either quote.
_CYPHER_UID = re.compile(
    r"""\b(?:\w+_)?uid\s*(?::|=|<>)\s*(?:'(?P<single>[^'$]*)'|"(?P<double>[^"$]*)")"""
)
# `{turn_in_exercise_uid: $ex}`, `n.uid IN $uids` — the parameter a uid position reads.
_CYPHER_UID_PARAM = re.compile(r"\b(?:\w+_)?uids?\s*(?::|=|<>|IN\b)\s*\$(?P<param>\w+)")


def _outside(value: object) -> bool:
    return (
        isinstance(value, str)
        and _UID_SHAPED.fullmatch(value) is not None
        and classify(value) is not UidVerdict.FITS
    )


@dataclass
class _Scope:
    name: str
    line: int
    marked: bool = False
    static_only: bool = False
    findings: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class _Report:
    breaches: list[tuple[int, str]] = field(default_factory=list)
    stale: list[tuple[int, str]] = field(default_factory=list)


def _marker(node: ast.expr) -> ast.Call | None:
    """The ``pytest.mark.outside_uid_grammar(...)`` call ``node`` is, or ``None``."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == MARKER
    ):
        return node
    return None


def _static_only(call: ast.Call) -> bool:
    return any(
        kw.arg == "static_only" and isinstance(kw.value, ast.Constant) and kw.value.value is True
        for kw in call.keywords
    )


def _pytestmark_markers(body: list[ast.stmt]) -> list[ast.Call]:
    markers: list[ast.Call] = []
    for stmt in body:
        if not isinstance(stmt, ast.Assign | ast.AnnAssign) or stmt.value is None:
            continue
        targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
        if not any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets):
            continue
        values = stmt.value.elts if isinstance(stmt.value, ast.List | ast.Tuple) else [stmt.value]
        markers.extend(m for v in values if (m := _marker(v)) is not None)
    return markers


def _members(node: ast.expr) -> list[ast.expr]:
    return list(node.elts) if isinstance(node, ast.List | ast.Tuple | ast.Set) else [node]


def _target_name(target: ast.expr) -> str | None:
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def _module_constants(tree: ast.Module) -> dict[str, str]:
    """Each module-level name bound to a string, and the string."""
    constants: dict[str, str] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target, value = stmt.targets[0], stmt.value
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            target, value = stmt.target, stmt.value
        else:
            continue
        if (
            isinstance(target, ast.Name)
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
        ):
            constants[target.id] = value.value
    return constants


def _uid_params(tree: ast.Module) -> frozenset[str]:
    """The Cypher parameters the module's strings read in a uid position."""
    return frozenset(
        match["param"]
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        for match in _CYPHER_UID_PARAM.finditer(node.value)
    )


class _Reader(ast.NodeVisitor):
    def __init__(self, tree: ast.Module) -> None:
        self.scopes: list[_Scope] = []
        self.report = _Report()
        self.constants = _module_constants(tree)
        self.uid_params = _uid_params(tree)

    def _uid_position(self, name: str) -> bool:
        return _UID_NAME.search(name) is not None or name in self.uid_params

    def read(self, tree: ast.Module) -> _Report:
        self._enter(_Scope("module", 1), _pytestmark_markers(tree.body), tree)
        return self.report

    def _enter(self, scope: _Scope, markers: list[ast.Call], node: ast.AST) -> None:
        scope.marked = bool(markers)
        scope.static_only = any(_static_only(m) for m in markers)
        self.scopes.append(scope)
        self.generic_visit(node)
        self.scopes.pop()
        if scope.static_only and not scope.findings:
            self.report.stale.append((scope.line, scope.name))
        if self.scopes:
            self.scopes[-1].findings.extend(scope.findings)

    def _scoped(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        markers = [m for d in node.decorator_list if (m := _marker(d)) is not None]
        if isinstance(node, ast.ClassDef):
            markers += _pytestmark_markers(node.body)
        self._enter(_Scope(node.name, node.lineno), markers, node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scoped(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scoped(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._scoped(node)

    def _found(self, node: ast.expr, value: str, offset: int = 0) -> None:
        line = node.lineno + offset
        if (line, value) in self.scopes[-1].findings:
            return
        self.scopes[-1].findings.append((line, value))
        if not any(scope.marked for scope in self.scopes):
            self.report.breaches.append((line, value))

    def _read_value(self, value: ast.expr) -> None:
        for member in _members(value):
            if isinstance(member, ast.Constant):
                literal = member.value
            elif isinstance(member, ast.Name):
                literal = self.constants.get(member.id)
            else:
                continue
            if _outside(literal):
                self._found(member, literal)

    def visit_keyword(self, node: ast.keyword) -> None:
        if node.arg and self._uid_position(node.arg):
            self._read_value(node.value)
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for key, value in zip(node.keys, node.values, strict=True):
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and self._uid_position(key.value)
            ):
                self._read_value(value)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if any((name := _target_name(t)) and _UID_NAME.search(name) for t in node.targets):
            self._read_value(node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        name = _target_name(node.target)
        if node.value is not None and name and _UID_NAME.search(name):
            self._read_value(node.value)
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> None:
        # A string statement is a docstring: prose naming a uid writes none.
        if not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            for match in _CYPHER_UID.finditer(node.value):
                value = match["single"] if match["single"] is not None else match["double"]
                if _outside(value):
                    self._found(node, value, node.value.count("\n", 0, match.start()))


def read_source(source: str) -> _Report:
    """The unmarked uid literals outside the grammar in ``source``, and its stale markers."""
    tree = ast.parse(source)
    return _Reader(tree).read(tree)


def _integration_sources() -> list[Path]:
    files = sorted(p for p in INTEGRATION_ROOT.rglob("*.py") if "__pycache__" not in p.parts)
    assert files, f"no sources found under {INTEGRATION_ROOT}"
    return files


def _reports() -> list[tuple[str, _Report]]:
    root = INTEGRATION_ROOT.parents[1]
    return [
        (str(path.relative_to(root)), read_source(path.read_text(encoding="utf-8")))
        for path in _integration_sources()
    ]


def test_no_integration_test_writes_a_uid_literal_outside_the_grammar() -> None:
    offenders = [
        f"{path}:{line}  {value!r}"
        for path, report in _reports()
        for line, value in report.breaches
    ]
    assert not offenders, (
        "These uid literals are outside the uid grammar (core/utils/uid_grammar.py). Seed "
        "authored uids ({prefix}.{slug}) or the user uids tests/helpers/seed_uids.py mints; a "
        f"test that writes one on purpose carries @pytest.mark.{MARKER}(reason) — with "
        "static_only=True when the runtime census never sees it:\n  " + "\n  ".join(offenders)
    )


def test_every_static_only_marker_names_a_uid_outside_the_grammar() -> None:
    """Also the walk's control: a reader that stopped finding uids leaves every scope stale."""
    stale = [f"{path}:{line}  {name}" for path, report in _reports() for line, name in report.stale]
    assert not stale, (
        f"A static_only {MARKER} marker is held by this census alone, and these scopes name no "
        "uid outside the grammar — delete the marker:\n  " + "\n  ".join(stale)
    )


# ---------------------------------------------------------------------------
# Controls — a census that finds nothing proves nothing
# ---------------------------------------------------------------------------


_REFUSED = {
    "an underscore seed": 'create_task(uid="task_001")',
    "a colon seed": 'node = {"uid": "ku:mindfulness"}',
    "a username user uid in Cypher": "q = \"CREATE (:User {uid: 'user_alice'})\"",
    "a Cypher comparison": "q = \"MATCH (n) WHERE n.user_uid <> 'user_system'\"",
    "a double-quoted Cypher value": "q = 'CREATE (:Task {uid: \"task_001\"})'",
    "a constant": 'OWNER_UID = "user_alice"',
    "an annotated constant": 'TASK_UID: str = "task_001"',
    "an attribute": 'self.user_uid = "user_alice"',
    "a list member": 'link(ku_uids=["ku.fits", "ku_old"])',
    "a constant named in a uid position": 'EX = "ex_old"\n\ndef test_x():\n    run(uid=EX)\n',
    "a Cypher parameter's binding": (
        'def test_x():\n    run("CREATE (:UserEntry {turn_in_exercise_uid: $ex})", ex="ex_old")\n'
    ),
    "a helper beside a marked test": (
        'def _seed():\n    run(uid="task_001")\n\n'
        '@pytest.mark.outside_uid_grammar("why")\ndef test_x():\n    _seed()\n'
    ),
}

_PASSED = {
    "a fitting authored uid": 'create_task(uid="task.001")',
    "a fitting generated uid": 'OWNER_UID = "user_5a5b777a8bc89ffa"',
    "a fragment ending in a dot": "q = \"CREATE (:Habit {uid: 'habit.' + $n})\"",
    "a fragment ending in a hyphen": 'PREFIX_UID = "ps.bulk-"',
    "a mock id": 'Milestone(uid="m0")',
    "a docstring": 'def test_x():\n    """Reads ``user_uid = \'user_system\'``."""\n',
    "a name that is not a uid's": 'create_task(title="task_001")',
    "a constant named nowhere a uid is": 'METRIC = "times_practiced"\n\nrun(field=METRIC)\n',
    "a parameter no uid position reads": ('run("MATCH (n {title: $name})", name="task_001")\n'),
    "a marked test": '@pytest.mark.outside_uid_grammar("why")\ndef test_x():\n    run(uid="task_001")\n',
    "a marked class": (
        '@pytest.mark.outside_uid_grammar("why")\n'
        'class TestX:\n    def test_x(self):\n        run(uid="task_001")\n'
    ),
    "a class pytestmark": (
        'class TestX:\n    pytestmark = [pytest.mark.outside_uid_grammar("why")]\n'
        '    def test_x(self):\n        run(uid="task_001")\n'
    ),
    "a module pytestmark": (
        'pytestmark = [pytest.mark.integration, pytest.mark.outside_uid_grammar("why")]\n'
        'def _seed():\n    run(uid="task_001")\n'
    ),
    "a static_only marker with its uid": (
        '@pytest.mark.outside_uid_grammar("why", static_only=True)\n'
        "def test_x():\n    run(\"CREATE (:User {uid: 'user_system'})\")\n"
    ),
}


def test_the_census_refuses_each_shape() -> None:
    for name, source in _REFUSED.items():
        assert read_source(source).breaches, name


def test_the_census_passes_what_is_not_a_breach() -> None:
    for name, source in _PASSED.items():
        report = read_source(source)
        assert report.breaches == [], name
        assert report.stale == [], name


def test_a_static_only_marker_naming_no_uid_is_stale() -> None:
    source = (
        '@pytest.mark.outside_uid_grammar("why", static_only=True)\n'
        'def test_x():\n    run(uid="task.001")\n'
    )
    assert read_source(source).stale == [(2, "test_x")]


def test_a_plain_marker_naming_no_uid_is_left_to_the_runtime_census() -> None:
    """A plain marker's uid may be computed — only the runtime census can call it stale."""
    source = '@pytest.mark.outside_uid_grammar("why")\ndef test_x():\n    run(uid=f"task_{n}")\n'
    assert read_source(source).stale == []


def test_a_finding_in_a_multi_line_string_names_its_own_line() -> None:
    source = 'q = """\nMATCH (u:User)\nCREATE (:Task {uid: \'task_001\'})\n"""\n'
    assert read_source(source).breaches == [(3, "task_001")]
