"""Every uid-anchored node pattern in the persistence tree carries a label guard (G13).

The chunk store's ``MERGE (c:Content {uid: $uid})`` gives a Ku / PathStep with a
body a second node on the SAME uid, so an unlabeled ``(x {uid: $uid})`` binds
both — a write doubles its edge, a read doubles its rows. The guard is a label
on the pattern (``:Entity``, or the domain label) or ``NOT x:Content`` in the
same statement. This census reads every Cypher string under
``adapters/persistence/`` on its own and fails on a uid-anchored pattern that
has neither; ``tests/integration/test_g13_shadow_uid_guard.py`` proves the
doors on a real graph.

Reach: one string at a time. A pattern composed across two strings — a
``match_pattern`` built in Python and spliced into the statement — is not seen
here and is yours to guard by hand (bind the label where the variable is
introduced). A ``WHERE x.uid = $…`` filter on a variable the string never labels
is reported too, since it anchors the same way.

See: ``.claude/skills/neo4j-cypher-patterns/SKILL.md`` § 0.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
TREE = "adapters/persistence"

#: ``(var {uid: …})`` / ``(var {{uid: …}})`` with no label — ``uid`` anywhere in the map.
NODE_PATTERN = re.compile(r"\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\{\{?\s*[^}]*?(?<![A-Za-z0-9_])uid\s*:")
#: ``(var)`` — a variable reused without a label.
BARE_VAR = re.compile(r"\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")
#: ``(var:Label`` — the variable is labeled somewhere in the same string.
LABELED_VAR = re.compile(r"\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*:")
#: ``var.uid = $param`` — a uid anchor written as a filter.
UID_FILTER = re.compile(r"(?<![A-Za-z0-9_.])([A-Za-z_][A-Za-z0-9_]*)\.uid\s*=\s*\$")
#: ``NOT var:Content`` — the mixed-label guard.
SHADOW_GUARD = re.compile(r"NOT\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*Content")

#: A string is Cypher only if it carries a clause; a map literal in Python is not.
CLAUSES = ("MATCH", "MERGE", "CREATE", "OPTIONAL", "UNWIND", "CALL")
#: ``collect(DISTINCT {uid: …})`` and friends are map literals, not node patterns.
NOT_VARIABLES = frozenset({"DISTINCT", "MATCH", "MERGE", "CREATE", "WITH", "WHERE", "RETURN"})


def _tracked_sources() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", f"{TREE}/*.py"], cwd=APP, capture_output=True, text=True, check=True
    ).stdout
    return [APP / line for line in sorted(set(out.split()))]


def _cypher_strings(tree: ast.AST):
    """Every string constant or f-string that holds a Cypher clause, with its text.

    An f-string is read whole: its constant fragments are not strings of their
    own (the fragment before the first ``{expr}`` holds the ``MATCH`` and not
    the guard).
    """
    fragments = {
        id(value)
        for node in ast.walk(tree)
        if isinstance(node, ast.JoinedStr)
        for value in node.values
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            text = "".join(
                value.value if isinstance(value, ast.Constant) else "{…}" for value in node.values
            )
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in fragments:
                continue
            text = node.value
        else:
            continue
        if "uid" in text and any(clause in text for clause in CLAUSES):
            yield node.lineno, text


def unguarded_sites(source: str) -> list[tuple[int, str]]:
    """``(line, description)`` for every uid anchor in ``source`` with no label guard."""
    tree = ast.parse(source)
    found: list[tuple[int, str]] = []
    for lineno, text in _cypher_strings(tree):
        guarded = {match.group(1) for match in SHADOW_GUARD.finditer(text)}
        labeled = {match.group(1) for match in LABELED_VAR.finditer(text)}
        for match in NODE_PATTERN.finditer(text):
            var = match.group(1)
            if var in NOT_VARIABLES or var in guarded:
                continue
            line = lineno + text[: match.start()].count("\n")
            found.append((line, f"({var} {{uid: …}}) carries no label and no NOT {var}:Content"))
        bare = {match.group(1) for match in BARE_VAR.finditer(text)}
        for match in UID_FILTER.finditer(text):
            var = match.group(1)
            if var not in bare or var in labeled or var in guarded:
                continue
            line = lineno + text[: match.start()].count("\n")
            found.append((line, f"({var}) is filtered by {var}.uid with no label"))
    return found


def test_every_uid_anchor_in_the_persistence_tree_is_label_guarded() -> None:
    offences = [
        f"{path.relative_to(APP)}:{line}  {why}"
        for path in _tracked_sources()
        for line, why in unguarded_sites(path.read_text())
    ]
    assert not offences, "unlabeled uid anchors (G13 shadow rule, SKILL.md § 0):\n" + "\n".join(
        offences
    )


class TestTheScannerSeesTheShapes:
    """The census is only as good as its regexes; each sanctioned and offending shape once."""

    def test_an_unlabeled_anchor_is_reported(self) -> None:
        source = 'q = """MATCH (n {uid: $uid}) RETURN n"""\n'
        assert [why for _, why in unguarded_sites(source)] == [
            "(n {uid: …}) carries no label and no NOT n:Content"
        ]

    def test_an_fstring_anchor_in_any_position_is_reported(self) -> None:
        source = 'q = f"""MATCH (p:Entity)-[:{rel}]->(e {{uid: $uid}}) RETURN e"""\n'
        assert [why for _, why in unguarded_sites(source)] == [
            "(e {uid: …}) carries no label and no NOT e:Content"
        ]

    def test_a_uid_filter_on_an_unlabeled_variable_is_reported(self) -> None:
        source = 'q = """MATCH (e)-[r]->(x) WHERE e.uid = $uid RETURN r"""\n'
        assert [why for _, why in unguarded_sites(source)] == [
            "(e) is filtered by e.uid with no label"
        ]

    def test_the_two_sanctioned_forms_pass(self) -> None:
        source = (
            'a = """MATCH (n:Entity {uid: $uid}) RETURN n"""\n'
            'b = """MATCH (n {uid: $uid}) WHERE NOT n:Content RETURN n"""\n'
            'c = """MATCH (e:Entity {entity_type: $t}) WHERE e.uid = $uid RETURN e"""\n'
        )
        assert unguarded_sites(source) == []

    def test_a_map_literal_and_a_uid_other_than_the_anchor_pass(self) -> None:
        source = (
            'a = """MATCH (n:Entity {uid: $uid}) RETURN collect(DISTINCT {uid: n.uid}) AS u"""\n'
            'b = """MATCH (n:Entity {user_uid: $u}) RETURN n"""\n'
        )
        assert unguarded_sites(source) == []
