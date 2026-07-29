#!/usr/bin/env python3
"""
Cypher Query Linter - Static Analysis for Neo4j Queries
========================================================

Validates Cypher queries against SKUEL best practices, catching common errors
before they reach runtime. Lints two source shapes:

- Python files (.py): Cypher extracted from non-docstring triple-quoted string
  literals, admitted by ``cypher_vocabulary.looks_like_cypher`` — the same gate
  SKUEL030 applies to the same kind of text — with comments masked before the
  rules run
- Standalone Cypher files (.cypher): whole-file Cypher (indexes, migrations,
  bulk-upsert templates), split into semicolon-terminated statements so each
  statement is linted as its own query

Both shapes now agree on the two things that decide what a rule reads: comments
are masked, and no rule ever sees prose. They did not before — the Python half
ran a local admission heuristic that scored the RAW text for four structural
shapes, so a query interpolating every structural position scored zero and was
dropped upstream of all twelve rules. See ``_extract_cypher_queries``.

**Validation Rules:**
- CYP001: Nested aggregate functions (ERROR)
- CYP002: DELETE without DETACH (ERROR)
- CYP003: Interpolated VALUE instead of parameter (ERROR) — flags value-position
  shapes only ('{var}' quoted literals, operator-adjacent = {var} / IN {var}).
  Structural composition (clause fragments, validated identifiers, *1..{depth}
  bounds — which Cypher cannot parameterize) is the sanctioned below-boundary
  pattern and is not flagged. Suppress a boundary-shaped hit with a Cypher
  comment: // noqa: CYP003 - <reason>
- CYP004: Unbounded relationship traversal (WARNING)
- CYP005: Missing depth limit on multi-hop traversal (WARNING)
- CYP006: Large result set without LIMIT (INFO)
- CYP007: Duplicate variable names (ERROR) - DISABLED
- CYP008: WITH clause without DISTINCT (WARNING) - DISABLED
- CYP009: Query complexity too high (WARNING)
- CYP010: Missing index hint for large dataset (INFO)
- CYP011: Node label / relationship type not registered in NeoLabel /
  RelationshipName (ERROR) — .cypher files only; the .py half is SKUEL030.
  Neo4j never validates a label or edge type, so an unregistered name matches
  zero rows silently. Suppress: // noqa: CYP011 - <reason>
- CYP012: DETACH on a relationship delete (WARNING) — CYP002's inverse over the
  same variable set. A relationship has nothing to detach, so `DETACH DELETE r`
  and `DELETE r` are identical; only flagged when EVERY target is a relationship
  (`DETACH DELETE r, n` is correct). Suppress: // noqa: CYP012 - <reason>

**Usage:**
    uv run python scripts/cypher_linter.py                    # Lint all files (warnings-only mode)
    uv run python scripts/cypher_linter.py path/to/file.py   # Lint specific file
    uv run python scripts/cypher_linter.py --errors-only     # Show only errors
    uv run python scripts/cypher_linter.py --strict          # Fail on errors (exit code 1)

**Modes:**
    - Default (warnings-only): Reports violations but always exits 0 (success)
    - Strict mode (--strict): Exits 1 if any ERROR severity violations found

**Integration:**
    Called by `./dev quality` in warnings-only mode for visibility without blocking
"""

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

# Shared with lint_skuel.py (SKUEL030) — one registry reader, one name scanner,
# and one admission gate for Cypher embedded in Python string literals.
sys.path.insert(0, str(Path(__file__).parent))
from cypher_vocabulary import (  # type: ignore[import-not-found]
    VocabularyError,
    load_vocabulary,
    looks_like_cypher,
    mask_cypher_comments,
    scanning_fragment_at,
    unregistered_names,
)


class Severity(StrEnum):
    """Violation severity levels."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class Violation:
    """Represents a Cypher validation violation."""

    rule_code: str
    severity: Severity
    message: str
    file_path: Path
    line_number: int
    line_content: str
    suggestion: str

    def __str__(self) -> str:
        """Format violation for display."""
        severity_emoji = {
            Severity.ERROR: "❌",
            Severity.WARNING: "⚠️",
            Severity.INFO: "ℹ️",
        }
        emoji = severity_emoji.get(self.severity, "•")

        return f"""
{emoji} {self.severity.value} [{self.rule_code}] {self.file_path}:{self.line_number}
   {self.message}

   Line {self.line_number}: {self.line_content.strip()}

   💡 Suggestion: {self.suggestion}
"""


class CypherLinter:
    """Static analysis tool for Cypher queries."""

    def __init__(self, errors_only: bool = False) -> None:
        """
        Initialize Cypher linter.

        Args:
            errors_only: If True, only report ERROR severity violations
        """
        self.errors_only = errors_only
        self.violations: list[Violation] = []

    def lint_file(self, file_path: Path) -> list[Violation]:
        """
        Lint a file for Cypher query issues.

        Args:
            file_path: Path to a Python file (Cypher extracted from string
                literals) or a standalone .cypher file (linted whole, one
                query per semicolon-terminated statement)

        Returns:
            List of violations found
        """
        if not file_path.exists():
            print(f"File not found: {file_path}")
            return []

        content = file_path.read_text()

        violations: list[Violation] = []

        # Find all Cypher queries in the file
        if file_path.suffix == ".cypher":
            queries = self._extract_cypher_statements(content)
        else:
            queries = self._extract_cypher_queries(content, file_path)

        for query, start_line in queries:
            # Run all validation rules
            violations.extend(self._check_nested_aggregates(query, file_path, start_line))
            violations.extend(self._check_delete_without_detach(query, file_path, start_line))
            violations.extend(self._check_detach_on_relationship(query, file_path, start_line))
            violations.extend(self._check_string_interpolation(query, file_path, start_line))
            violations.extend(self._check_unbounded_traversal(query, file_path, start_line))
            violations.extend(self._check_missing_depth_limit(query, file_path, start_line))
            violations.extend(self._check_missing_limit(query, file_path, start_line))
            violations.extend(self._check_duplicate_variables(query, file_path, start_line))
            violations.extend(self._check_vocabulary_registry(query, file_path, start_line))

            # Advanced features (Week 5-6)
            violations.extend(self._check_query_complexity(query, file_path, start_line))
            violations.extend(self._check_missing_index_hints(query, file_path, start_line))
            violations.extend(self._check_with_without_distinct(query, file_path, start_line))

        return violations

    # Cypher embedded in a Python file lives in triple-quoted literals. One
    # pattern, not two: the old second pass re-scanned for
    # `session.run("""...""")`, and every one of its 252 tree-wide matches was
    # already found by this one — structurally, not by luck, since the general
    # pattern has no context requirement to fail. What the second copy did
    # carry was a second copy of the admission decision.
    _TRIPLE_QUOTED_RE = re.compile(r'"""([\s\S]*?)"""')

    def _docstring_lines(self, content: str) -> set[int]:
        """Every line number covered by a module/class/function docstring.

        From the AST, because a docstring is defined by POSITION — first
        statement of a module, class or function — which is precisely what a
        regex over quote characters cannot see.

        Lines rather than character spans: ``col_offset`` is a UTF-8 BYTE
        offset, and this tree's docstrings carry em-dashes and box-drawing
        characters, so a character-span containment test would drift on exactly
        the files with the most prose. Line numbers have no such encoding
        dependence, and a second ``\"\"\"`` literal cannot open inside a
        docstring's line range — it would have closed it.

        Unparseable content yields an empty set, which exempts nothing: the
        gate is then the only filter, as it was before this exemption existed.
        """
        try:
            tree = ast.parse(content)
        except (SyntaxError, ValueError):  # fmt: skip
            return set()

        lines: set[int] = set()
        for node in ast.walk(tree):
            if not isinstance(
                node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
            ):
                continue
            body = node.body
            if not body:
                continue
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
                and first.value.end_lineno is not None
            ):
                lines.update(range(first.value.lineno, first.value.end_lineno + 1))
        return lines

    def _extract_cypher_queries(self, content: str, file_path: Path) -> list[tuple[str, int]]:
        """
        Extract Cypher queries from the triple-quoted literals of a Python file.

        Three decisions, each settled by measuring the scanned trees rather than
        by reasoning about what a query looks like:

        1. **The gate is ``looks_like_cypher``** — the same three-anchor
           predicate SKUEL030 applies to Python string literals — not a local
           heuristic. The local one this replaced (``_is_actual_cypher``) tested
           for four structural shapes in the RAW source text, so a query that
           interpolated every structural position scored zero and was dropped
           before any rule saw it: ``MATCH (from {from_pattern})-[r:{self.
           _relationship_type}]->(to {to_pattern})`` has no ``(var:Label``, no
           ``-[var:TYPE``, no ``{prop:`` and no ``$param``. That made all twelve
           CYP rules blind to 113 queries tree-wide, a gap upstream of every
           rule rather than in any of them. Deleting the local heuristic costs
           nothing measurable: the shared gate admits 1047 of the 1049 literals
           it admitted, and the 2 it declines are prose docstrings.

        2. **Docstrings are skipped.** This is a stated PRECONDITION of the
           shared gate's head anchor, not a preference — see the
           ``CYPHER_LEADING_CLAUSES`` block: "Docstrings are already exempt on
           the SKUEL030 side as inert nodes; head position is what keeps the
           rule honest for the prose that is assigned or passed." SKUEL030 gets
           that exemption free from its AST walk; this extractor is a regex over
           raw source and had none. The cost of the omission is not theoretical:
           SKUEL033's intent-only docstrings open with the clause the method
           performs ("MERGE VIEWED relationship with timestamp and count
           tracking"), which is head-anchor bait by construction. 19 such
           docstrings are admitted without this, and one made CYP002 — ERROR
           severity, CI-gating under ``--strict`` — report a node named 'the'.

        3. **Comments are masked**, which the ``.cypher`` path has always done
           and this one never did. The rules read raw text, so prose inside a
           ``//`` comment was read as Cypher: ``// The stale-owner DELETE
           enforces the single-owner invariant`` made CYP002 report a node named
           'enforces' inside a query that is entirely correct. Masking also
           stops CYP009 scoring comment keywords as query complexity — 4 sites
           re-score, one of them down from 663. ``keep_noqa=True`` for the same
           reason the statement splitter passes it: the suppression check reads
           the violation's own line.

        Returns:
            List of (query, line_number) tuples
        """
        queries: list[tuple[str, int]] = []
        seen_queries: set[str] = set()
        docstring_lines = self._docstring_lines(content)

        for match in self._TRIPLE_QUOTED_RE.finditer(content):
            line_num = content[: match.start()].count("\n") + 1
            if line_num in docstring_lines:
                continue
            query = match.group(1)
            if not looks_like_cypher(query):
                continue
            query_key = query.strip()
            if query_key in seen_queries:
                continue
            seen_queries.add(query_key)
            # Masking preserves length, newlines and therefore every offset the
            # rules compute line numbers from.
            queries.append((mask_cypher_comments(query, keep_noqa=True), line_num))

        return queries

    def _extract_cypher_statements(self, content: str) -> list[tuple[str, int]]:
        """
        Extract statements from a standalone .cypher file.

        The whole file is Cypher by declaration, so no admission gate at all —
        not the ``looks_like_cypher`` gate the Python half needs for string
        literals, and not the local ``_is_actual_cypher`` heuristic that gate
        replaced. Just split on statement-terminating semicolons and keep every
        non-empty fragment. Two comment treatments:

        - Comments — ``//`` line and ``/* */`` block (non-nesting, per the
          Cypher spec) — are masked with spaces (positions, newlines, and
          line numbers preserved): comment prose would false-positive
          prose-shaped rules — "DELETE the edges" in a migration header trips
          CYP002, and a trailing comment after a ``;`` would otherwise leak
          into the NEXT statement (or become a phantom tail statement) and do
          the same (Codex, PR #710 — both comment forms). Commented-out
          queries are not live code either.
        - ``noqa:``-carrying ``//`` comments are kept — the rule checks read
          suppressions from the violation's line. (noqa must be ``//`` style;
          block comments are always masked.) The natural placement
          ``DELETE n; // noqa: CYP002 - reason`` sits AFTER the terminator,
          so the splitter folds a noqa-only tail back into the statement its
          semicolon just closed (Codex, PR #710 round 3) — otherwise the
          suppression would land in the next fragment and never be seen.

        Both passes track quoted strings (a ``//`` inside a string literal is
        not a comment), and the splitter additionally skips kept comments so
        a ``;`` or quote inside one never splits or opens a string.

        Returns:
            List of (statement, start_line) tuples, start_line 1-indexed at
            the statement's first token
        """
        # Pass 1: mask comments in place (same length, so every offset and line
        # number survives). The masker lives in cypher_vocabulary because the
        # vocabulary scanner needs the identical treatment on the SKUEL030 side,
        # where nothing pre-masks an AST string literal — see mask_cypher_comments.
        text = mask_cypher_comments(content, keep_noqa=True)

        # Pass 2: split on statement-terminating semicolons
        raw_statements: list[tuple[str, int]] = []
        start = 0
        in_string: str | None = None
        i = 0
        while i < len(text):
            char = text[i]
            if in_string is not None:
                if char == "\\":
                    i += 2  # skip escaped character inside string
                    continue
                if char == in_string:
                    in_string = None
            elif char in ("'", '"'):
                in_string = char
            elif text[i : i + 2] == "//":
                i = text.find("\n", i)
                if i == -1:
                    break
                continue
            elif char == ";":
                statement = text[start:i]
                # Fold a same-line noqa tail into this statement (appended
                # without a newline, so it stays on the violation's line for
                # the suppression check), and consume it so it doesn't leak
                # into the next fragment. The guard requires the tail to be
                # comment-only — real code after the ';' (multi-statement
                # line) is left for the next split.
                tail_end = text.find("\n", i)
                if tail_end == -1:
                    tail_end = len(text)
                tail = text[i + 1 : tail_end]
                if "noqa:" in tail and tail.lstrip().startswith("//"):
                    raw_statements.append((statement + " " + tail.strip(), start))
                    start = tail_end
                    i = tail_end
                    continue
                raw_statements.append((statement, start))
                start = i + 1
            i += 1
        if text[start:].strip():
            raw_statements.append((text[start:], start))

        statements: list[tuple[str, int]] = []
        for statement, position in raw_statements:
            # THE shared admission predicate, the same one SKUEL030 uses. This
            # was a local keyword list (MATCH/CREATE/MERGE/DELETE/RETURN/WITH/
            # WHERE) justified as "drops DROP INDEX / SHOW — no rule applies to
            # them". CYP011 broke that premise: a vocabulary rule applies to any
            # statement carrying a label or edge name, and a whole family was
            # being discarded here before it ever reached the scanner — e.g.
            # `CALL db.index.fulltext.queryNodes(...) YIELD node SET node:Bogus`
            # (Codex P2 on #831). Two gates in series, and widening only the
            # inner one would have left CYP011 exactly as silent as before.
            # No heuristic gate here. A `.cypher` file is Cypher BY DECLARATION
            # — the extension already answers the only question `looks_like_cypher`
            # exists to answer, and that predicate is calibrated for Python string
            # literals, where prose is a real risk. Applying it here just invented
            # ways to discard real queries: first a local keyword list that dropped
            # `CALL ... SET node:Label`, then the shared gate, which dropped
            # lowercase Cypher and then `CYPHER runtime=slotted RETURN ...` (three
            # rounds of Codex P2 on #831, each a different clause the list did not
            # know). Empty fragments are the only thing worth dropping.
            if not statement.strip():
                continue
            # Anchor start_line at the first real token, not the newline after
            # the previous ';' — rules that report at start_line itself
            # (CYP009) would otherwise point one line early
            lead = len(statement) - len(statement.lstrip())
            line_num = text[: position + lead].count("\n") + 1
            statements.append((statement[lead:], line_num))

        return statements

    # ========================================================================
    # VALIDATION RULES
    # ========================================================================

    def _check_nested_aggregates(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP001: Check for nested aggregate functions.

        Example violation:
            collect({uid: n.uid, count: count(r)})  # Nested aggregate!

        Correct pattern:
            WITH n, count(r) as r_count
            RETURN collect({uid: n.uid, count: r_count})
        """
        violations: list[Violation] = []

        # Aggregate functions: count, collect, sum, avg, min, max
        aggregate_pattern = r"(count|collect|sum|avg|min|max)\s*\("

        # Find all aggregate function calls
        aggregates = list(re.finditer(aggregate_pattern, query, re.IGNORECASE))

        for outer_agg in aggregates:
            # Check if there's another aggregate inside this one
            # Get the content inside the outer aggregate's parentheses
            start_pos = outer_agg.end()

            # Find matching closing parenthesis
            depth = 1
            end_pos = start_pos
            for i in range(start_pos, len(query)):
                if query[i] == "(":
                    depth += 1
                elif query[i] == ")":
                    depth -= 1
                    if depth == 0:
                        end_pos = i
                        break

            inner_content = query[start_pos:end_pos]

            # Check if inner content has another aggregate
            if re.search(aggregate_pattern, inner_content, re.IGNORECASE):
                line_num = start_line + query[: outer_agg.start()].count("\n")
                line_content = self._get_line_at_position(query, outer_agg.start())

                violations.append(
                    Violation(
                        rule_code="CYP001",
                        severity=Severity.ERROR,
                        message="Nested aggregate functions detected",
                        file_path=file_path,
                        line_number=line_num,
                        line_content=line_content,
                        suggestion="Use WITH clause to stage aggregations: "
                        "WITH n, count(r) as r_count RETURN collect(...)",
                    )
                )

        return violations

    # A variable bound inside a relationship bracket. Anything inside `[...]` in
    # Cypher is an edge, so the only job is finding the NAME: skip optional
    # whitespace after `[`, then require the next token to end at something that
    # can legally follow a binding — `:` (type), `]` (bare), `{` (property map),
    # or `*` (var-length bound). An anonymous `-[:TYPE]` is correctly skipped
    # because the identifier class cannot match a leading `:`.
    #
    # The four terminators are load-bearing, and the narrower `[:\]]` this
    # replaced is why: it missed `-[ r:OWNS ]`, `-[r {active: true}]`, and
    # `-[r*1..2]` outright (Codex P2, #868). That narrowness was survivable while
    # CYP002 was the only reader — a missed edge variable there produces a false
    # POSITIVE, which someone sees. CYP012 reads the same set in the opposite
    # direction, where the identical miss produces a silent false NEGATIVE: the
    # rule would permit exactly the redundant detach it exists to catch.
    _REL_VAR_RE = re.compile(r"-\[\s*([A-Za-z_]\w*)\s*(?=[:\]{*])")

    # A variable bound by a NODE pattern — `(n)`, `(n:Label)`, `(n {props})`.
    # Read only by CYP012, as an ambiguity guard; see `_check_detach_on_relationship`.
    #
    # The lookbehind is the whole difficulty. Without it, `count(r)` and
    # `coalesce(r.confidence, 0)` read as node patterns binding `r`, which would
    # have classified the edge variable in `DELETE r RETURN count(r) AS deleted`
    # as a node and silently switched CYP012 off on two of the four sites it was
    # written for. A node pattern's `(` never follows an identifier character;
    # a function call's always does.
    _NODE_VAR_RE = re.compile(r"(?<![\w.])\(\s*([A-Za-z_]\w*)\s*(?=[:){])")

    @classmethod
    def _node_vars(cls, query: str) -> set[str]:
        """Variables the query binds to a node."""
        return {m.group(1).lower() for m in cls._NODE_VAR_RE.finditer(query)}

    # A name introduced by an `AS` alias. `WITH n AS r` rebinds `r` to whatever
    # `n` was — a node, an aggregate, anything — so the pattern-based classifiers
    # no longer describe it.
    _ALIAS_RE = re.compile(r"\bAS\s+([A-Za-z_]\w*)", re.IGNORECASE)

    @classmethod
    def _aliased_names(cls, query: str) -> set[str]:
        """Names an ``AS`` clause (re)binds somewhere in the query."""
        return {m.group(1).lower() for m in cls._ALIAS_RE.finditer(query)}

    @classmethod
    def _edge_only_vars(cls, query: str) -> set[str]:
        """Variables bound to a relationship and NEVER to a node in this query.

        **CYP012 only.** CYP002 reads the raw classifier on purpose — see the
        comment at its call site for why a CI-gating ERROR rule must not depend
        on these subtractions.

        That asymmetry is the whole design. Every subtraction here can only ever
        make CYP012 *quieter*, and quiet is CYP012's safe direction: it removes a
        redundant keyword, so a miss costs nothing while a wrong suggestion breaks
        a query. The same subtraction inside CYP002 pointed the other way and
        produced a false blocking failure (#868 round 7).

        The classifiers are query-wide and lexical, so CYP012 declines whenever a
        name is not plainly an edge. Known cases, all of them misses rather than
        false alarms:

        * a name reused across scopes —
          ``CALL { MATCH ()-[ r:OWNS]->() DELETE r } MATCH (r:Entity) DELETE r``
          binds ``r`` as an edge inside the subquery and a node outside it;
        * ``count (r)`` and friends, where whitespace before the paren makes an
          aggregate look like a node pattern. Distinguishing a function name from
          a clause keyword there is a parser's job, and this rule does not do
          parser jobs;
        * names rebound by an ``AS`` alias, below.

        Four review rounds arrived on this surface (#868). That progression is the
        signature of a regex growing toward a parser, and this tree has already
        paid 19 rounds for that lesson once (#831), so the mechanism stops here
        and the CLAIM carries the weight instead.

        Names rebound by an ``AS`` alias drop out for the same reason:
        ``MATCH (n:Entity) WITH n AS r DETACH DELETE r`` makes ``r`` a node no
        pattern in the query binds. That is the LIMIT of this classifier, stated
        rather than papered over — it does not resolve scopes, aliases, or data
        flow, and it deliberately will not learn to. Three findings in a row
        arrived on that surface (cross-scope reuse, then the CYP002 direction,
        then aliasing), which is the signature of a regex growing toward a parser;
        this tree has already paid 19 review rounds for that lesson once (#831).
        So the answer is to narrow the CLAIM: CYP012 speaks only when a name is
        bound by a relationship pattern, never by a node pattern, and never by an
        alias. Anything subtler, it stays quiet about.

        The real sites keep firing under all three subtractions: they alias only
        their aggregate (``count(r) AS deleted``), never the deleted variable.
        """
        return cls._relationship_vars(query) - cls._node_vars(query) - cls._aliased_names(query)

    @classmethod
    def _relationship_vars(cls, query: str) -> set[str]:
        """Variables the query BINDS to a relationship (``-[r:TYPE]``/``-[r]``).

        THE one classifier, shared by the two rules that ask opposite questions
        of it: CYP002 skips these variables (an edge needs no DETACH), CYP012
        flags only these (an edge cannot BE detached). A second copy answering
        the same question is how the two directions would drift apart — and,
        per the pattern comment above, a gap here is invisible in one direction
        and loud in the other.
        """
        return {m.group(1).lower() for m in cls._REL_VAR_RE.finditer(query)}

    def _check_delete_without_detach(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP002: Check for DELETE without DETACH on nodes.

        DELETE without DETACH fails if node has relationships.
        Relationships (edges) don't need DETACH - only nodes do.

        This distinguishes between:
        - DELETE n (node) - needs DETACH check
        - DELETE r (relationship) - correct as-is

        Note the direction: this rule only ever asks whether a DETACH is
        MISSING. The inverse — a DETACH that cannot do anything because the
        target is an edge — is CYP012, over the same variable set.
        """
        violations: list[Violation] = []

        # Deliberately the RAW classifier, not `_edge_only_vars`.
        #
        # Round 5 of #868 routed this rule through the node/alias subtractions to
        # close a cross-scope miss. Round 7 showed the price: `count (r)` — a
        # function call with a space before its paren, which Cypher allows — reads
        # as a node pattern, drops `r` from the edge set, and makes this
        # ERROR-severity rule BLOCK CI on a correct relationship deletion.
        #
        # That is the wrong trade for a gating rule. Before this PR CYP002 rested
        # on one hand-written approximation; the subtractions made it rest on
        # three, converting a rare miss of a contrived cross-scope query — which
        # was pre-existing behaviour, not this PR's to fix — into a false failure
        # on correct code. A gate must not fail closed on my regex being wrong.
        #
        # The cross-scope miss is therefore left as it was found, documented in
        # LINTER_GUIDE.md as a known limit. Fixing it needs scope resolution, which
        # is a parser's job and its own change with its own measurement.
        relationship_vars = self._relationship_vars(query)

        # Find DELETE statements that aren't DETACH DELETE
        delete_pattern = r"\bDELETE\s+([a-z_][a-z0-9_]*)\b"

        for match in re.finditer(delete_pattern, query, re.IGNORECASE):
            deleted_var = match.group(1).lower()

            # Check if this DELETE is preceded by DETACH
            context_start = max(0, match.start() - 20)
            context = query[context_start : match.end()]

            # Skip if DETACH DELETE
            if re.search(r"\bDETACH\s+DELETE\b", context, re.IGNORECASE):
                continue

            # Skip if deleting a relationship (relationships don't need DETACH)
            if deleted_var in relationship_vars:
                continue

            # This is a node deletion without DETACH - flag it
            line_num = start_line + query[: match.start()].count("\n")
            line_content = self._get_line_at_position(query, match.start())

            # Skip if line has noqa suppression for this rule
            if re.search(r"noqa:\s*CYP002", line_content):
                continue

            violations.append(
                Violation(
                    rule_code="CYP002",
                    severity=Severity.ERROR,
                    message=f"DELETE without DETACH on node '{deleted_var}' may fail if node has relationships",
                    file_path=file_path,
                    line_number=line_num,
                    line_content=line_content,
                    suggestion="Use DETACH DELETE for nodes. Note: Relationships don't need DETACH, only nodes do.",
                )
            )

        return violations

    def _check_detach_on_relationship(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP012: DETACH is meaningless when every DELETE target is a relationship.

        ``DETACH DELETE`` means "delete this node AND the relationships attached
        to it". A relationship has no relationships attached to it, so DETACH has
        nothing to do. Verified against a live server rather than read off the
        docs: two identical subgraphs, one deleted with ``DETACH DELETE r`` and
        one with ``DELETE r``, ended byte-identical — same row deleted, both
        endpoints and every other edge on them untouched.

        This is CYP002's inverse over the SAME variable set, and it is the
        direction CYP002 structurally cannot report: CYP002 only ever asks
        whether a DETACH is MISSING, so it *skips* relationship deletes outright
        and stayed silent on all three tree sites. Having the classifier already
        is what makes the second direction nearly free — the blind spot was the
        question never being asked, not a mechanism that was absent.

        ALL targets must be relationships. ``DETACH DELETE r, n`` is correct and
        is NOT flagged: the DETACH is there for ``n``. Flagging on the first
        target alone would have made that shape a false positive.

        A target also bound as a NODE anywhere in the query is skipped. The
        classifier is query-wide, so a name reused across scopes —
        ``CALL { MATCH ()-[n:OWNS]->() DELETE n } MATCH (n:Entity) DETACH DELETE n``
        — would otherwise read the outer node as an edge and advise dropping a
        DETACH that a node genuinely needs (Codex P2, #868). Real scope analysis
        is a parser's job, and a regex approximating a parser is a known tail in
        this tree; this guard instead fails in the harmless direction. CYP012
        only ever removes a redundant keyword, so a miss costs nothing, while a
        wrong suggestion costs a broken delete.

        WARNING, not ERROR: nothing misbehaves, so this can never be the reason a
        build fails on its own. The cost is a reader having to work out whether
        the DETACH is load-bearing — which is exactly what CYP002's own
        suggestion line already answers ("Relationships don't need DETACH, only
        nodes do").

        Suppress: // noqa: CYP012 - <reason>
        """
        violations: list[Violation] = []

        relationship_vars = self._edge_only_vars(query)
        if not relationship_vars:
            return violations

        # The whole comma-separated target list, not just the first variable —
        # see the docstring on why `DETACH DELETE r, n` must survive.
        detach_pattern = r"\bDETACH\s+DELETE\s+([a-z_][a-z0-9_]*(?:\s*,\s*[a-z_][a-z0-9_]*)*)"

        # Matched over the comment-MASKED copy, because a comment between targets
        # truncates the list: `DETACH DELETE r // edge first\n, n` would read as
        # the all-relationships case and suggest `DELETE r`, silently dropping the
        # node (Codex P2, #868). `mask_cypher_comments` preserves length and line
        # breaks, so offsets computed here still address the ORIGINAL text — which
        # is what the noqa lookup and line numbering below rely on.
        masked = mask_cypher_comments(query)

        for match in re.finditer(detach_pattern, masked, re.IGNORECASE):
            targets = [t.strip().lower() for t in match.group(1).split(",")]
            if not all(target in relationship_vars for target in targets):
                continue

            line_num = start_line + query[: match.start()].count("\n")
            line_content = self._get_line_at_position(query, match.start())

            if re.search(r"noqa:\s*CYP012", line_content):
                continue

            named = ", ".join(f"'{t}'" for t in targets)
            violations.append(
                Violation(
                    rule_code="CYP012",
                    severity=Severity.WARNING,
                    message=(
                        f"DETACH is a no-op deleting relationship {named} — "
                        "only nodes have relationships to detach"
                    ),
                    file_path=file_path,
                    line_number=line_num,
                    line_content=line_content,
                    suggestion=f"Use DELETE {', '.join(targets)} — DETACH changes nothing here",
                )
            )

        return violations

    def _check_string_interpolation(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP003: Check for interpolated VALUES instead of parameters.

        Value-position interpolation builds query text out of runtime data —
        the Cypher-injection shape. Two forms are flagged:

        - Quoted interpolation: ``'{var}'`` / ``"{var}"`` — a string literal
          assembled from a Python variable (f-string or ``.format()`` template).
        - Operator-adjacent interpolation: ``= {var}``, ``> {var}``,
          ``IN {var}``, ``CONTAINS {var}`` — a comparison operand assembled
          from a variable (also matches Neo4j's removed pre-4.0 ``{param}``
          parameter syntax, dead on the current server either way).

        NOT flagged — the sanctioned below-boundary composition patterns:
        clause fragments (``{where_clause}``), validated identifiers
        (``(n:{label})``, ``[r:{rel_type}]`` — guarded by validate_label() /
        validate_identifier()), and variable-length bounds (``*1..{depth}``,
        which Cypher cannot parameterize). The pre-2026-07 version flagged all
        of those (157 false positives) while its ':'-within-5-chars exemption
        missed real quoted map values like ``{{uid: '{source_uid}'}}``.

        Suppress a boundary-shaped hit with ``// noqa: CYP003 - <reason>``.
        """
        violations: list[Violation] = []

        # Doubled braces ({{ }}) are f-string escapes for literal braces —
        # the inner text is not interpolation. Quoted values inside them still
        # are: '{var}' carries its own single-braced group.
        # {expr} allows dotted/indexed f-string expressions ({node.uid},
        # {row[0]}) — but no ':' (Cypher map syntax) and no whitespace.
        expr = r"\{[A-Za-z_][^{}:\s]*\}"
        value_shapes = re.compile(
            rf"""
            ['\"]{expr}['\"]                                 # '{{var}}' / "{{var}}"
          | (?: (?<![<>=!:])=[~]?(?![=])                     # = or =~ (not ==, <=, >=, <>, !=)
              | <> | <= | >=
              | (?<![-=<>])>(?![=>])                         # > but not ->, >=, >>
              | (?<![-<>])<(?![=<>-])                        # < but not <-, <=, <>
              | \b(?:IN|CONTAINS|STARTS\s+WITH|ENDS\s+WITH)\b
            )
            \s* (?<!\{{){expr}(?!\}})                        # {{var}} not {{{{var}}}}
            """,
            re.VERBOSE | re.IGNORECASE,
        )

        for match in re.finditer(value_shapes, query):
            line_num = start_line + query[: match.start()].count("\n")
            line_content = self._get_line_at_position(query, match.start())

            # Skip if line has noqa suppression for this rule
            if re.search(r"noqa:\s*CYP003", line_content):
                continue

            violations.append(
                Violation(
                    rule_code="CYP003",
                    severity=Severity.ERROR,
                    message="Interpolated value in Cypher query (injection risk)",
                    file_path=file_path,
                    line_number=line_num,
                    line_content=line_content,
                    suggestion=(
                        "Pass the value as a driver parameter: $param instead of "
                        "'{variable}' / = {variable}"
                    ),
                )
            )

        return violations

    def _check_vocabulary_registry(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP011: Node label / relationship type must be registered in the enums.

        The `.cypher` half of SKUEL030. Neo4j validates neither labels nor
        relationship types, so a typo'd `(:Vectr)` in a constraint template or a
        retired edge name in a bulk-upsert simply matches nothing — no error, no
        log line, just a silently empty result forever.

        Scope is deliberately narrow: standalone `.cypher` files only.
        Cypher inside `.py` string literals is covered by SKUEL030 in
        lint_skuel.py, which has the AST context needed to tell an executable
        query from a docstring example. Running both here would double-report.

        `scripts/migrations/*.cypher` are excluded — a rename migration's job is
        to name the vocabulary it is renaming away.

        Suppress one line with `// noqa: CYP011 - <reason>`, or a whole file with
        `// noqa-file: CYP011 - <reason>` anywhere in it. The file-level form
        exists for templates that are dead end to end: annotating every line of a
        file that should not exist buries the point in ceremony.
        """
        if file_path.suffix != ".cypher":
            return []
        if "migrations" in file_path.parts:
            return []
        if re.search(r"noqa-file:\s*CYP011", file_path.read_text()):
            return []

        try:
            vocabulary = load_vocabulary()
        except VocabularyError as exc:
            # Fail loud, not open: an unreadable registry must never look clean.
            return [
                Violation(
                    rule_code="CYP011",
                    severity=Severity.ERROR,
                    message=f"Cannot read the enum vocabulary registry: {exc}",
                    file_path=file_path,
                    line_number=start_line,
                    line_content="",
                    suggestion="Check core/models/relationship_names.py and core/models/enums/neo_labels.py",
                )
            ]

        violations: list[Violation] = []
        # Diagnostics-only, no-op unless cypher_scan_diagnostics.py is recording.
        with scanning_fragment_at(start_line):
            unregistered = unregistered_names(query, vocabulary, declared_cypher=True)
        for name in unregistered:
            line_num = start_line + name.line_offset
            query_lines = query.splitlines()
            line_content = (
                query_lines[name.line_offset] if name.line_offset < len(query_lines) else ""
            )
            if re.search(r"noqa:\s*CYP011", line_content):
                continue
            violations.append(
                Violation(
                    rule_code="CYP011",
                    severity=Severity.ERROR,
                    message=(
                        f"Cypher {name.kind.value} '{name.value}' is not a "
                        f"{vocabulary.enum_for(name.kind)} member"
                    ),
                    file_path=file_path,
                    line_number=line_num,
                    line_content=line_content,
                    suggestion=(
                        f"Register '{name.value}' in {vocabulary.enum_for(name.kind)}, "
                        f"or fix the name — Neo4j matches zero rows on an unknown "
                        f"{name.kind.value} instead of erroring"
                    ),
                )
            )
        return violations

    def _check_unbounded_traversal(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP004: Check for unbounded relationship traversal.

        Pattern: -[:REL*]-> (no depth limit)
        Should be: -[:REL*1..5]-> (with depth limit)
        """
        violations: list[Violation] = []

        # Pattern: Relationship with * but no depth limit
        unbounded_pattern = r"-\[:[A-Z_]+\*\]-"

        for match in re.finditer(unbounded_pattern, query):
            line_num = start_line + query[: match.start()].count("\n")
            line_content = self._get_line_at_position(query, match.start())

            violations.append(
                Violation(
                    rule_code="CYP004",
                    severity=Severity.WARNING,
                    message="Unbounded relationship traversal detected",
                    file_path=file_path,
                    line_number=line_num,
                    line_content=line_content,
                    suggestion="Add depth limit: -[:REL*1..5]-> to prevent graph explosion",
                )
            )

        return violations

    def _check_missing_depth_limit(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP005: Check for multi-hop traversal without reasonable depth limit.

        Pattern: -[:REL*1..100]-> (excessive depth)
        Recommended: -[:REL*1..5]-> (reasonable depth)
        """
        violations: list[Violation] = []

        # Pattern: Relationship with depth > 10
        deep_traversal_pattern = r"-\[:[A-Z_]+\*\d+\.\.(\d+)\]-"

        for match in re.finditer(deep_traversal_pattern, query):
            max_depth = int(match.group(1))

            if max_depth > 10:
                line_num = start_line + query[: match.start()].count("\n")
                line_content = self._get_line_at_position(query, match.start())

                violations.append(
                    Violation(
                        rule_code="CYP005",
                        severity=Severity.WARNING,
                        message=f"Excessive traversal depth: {max_depth} (recommended: ≤10)",
                        file_path=file_path,
                        line_number=line_num,
                        line_content=line_content,
                        suggestion="Consider reducing depth limit to avoid performance issues",
                    )
                )

        return violations

    def _check_missing_limit(self, query: str, file_path: Path, start_line: int) -> list[Violation]:
        """
        CYP006: Check for large result set without LIMIT.

        Queries that return nodes without LIMIT can cause performance issues.
        """
        violations: list[Violation] = []

        # Check if query has MATCH and RETURN but no LIMIT
        has_match = bool(re.search(r"\bMATCH\b", query, re.IGNORECASE))
        has_return = bool(re.search(r"\bRETURN\b", query, re.IGNORECASE))
        has_limit = bool(re.search(r"\bLIMIT\b", query, re.IGNORECASE))

        # Also check for aggregation (count, collect, etc.) which doesn't need LIMIT
        has_aggregation = bool(
            re.search(r"\b(count|collect|sum|avg|min|max)\s*\(", query, re.IGNORECASE)
        )

        if has_match and has_return and not has_limit and not has_aggregation:
            # Find RETURN statement line
            return_match = re.search(r"\bRETURN\b", query, re.IGNORECASE)
            if return_match:
                line_num = start_line + query[: return_match.start()].count("\n")
                line_content = self._get_line_at_position(query, return_match.start())

                violations.append(
                    Violation(
                        rule_code="CYP006",
                        severity=Severity.INFO,
                        message="Query returns results without LIMIT clause",
                        file_path=file_path,
                        line_number=line_num,
                        line_content=line_content,
                        suggestion="Consider adding LIMIT clause to prevent large result sets",
                    )
                )

        return violations

    def _check_duplicate_variables(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP007: Check for duplicate variable names in query.

        Using the same variable name in different MATCH clauses can cause issues
        UNLESS it's intentional reuse (common pattern in Cypher).

        We only flag as error if:
        - Same variable appears in DIFFERENT MATCH statements
        - AND those MATCH statements are at different nesting levels
        """
        violations: list[Violation] = []

        # Split query into MATCH clauses
        match_clauses = re.split(r"\b(MATCH|OPTIONAL MATCH)\b", query, flags=re.IGNORECASE)

        # Track variables per MATCH clause
        match_variables: list[set[str]] = []

        for _i, clause in enumerate(match_clauses):
            if clause.strip().upper() not in ["MATCH", "OPTIONAL MATCH", ""]:
                # Extract variables from this clause
                variable_pattern = r"\(([a-z_][a-z0-9_]*)[:\{]"
                variables = set(
                    match.group(1) for match in re.finditer(variable_pattern, clause, re.IGNORECASE)
                )

                if variables:
                    match_variables.append(variables)

        # Check for duplicates across different MATCH clauses
        # This is often intentional in Cypher (reusing variables to connect patterns)
        # So we only warn if it seems unintentional (no relationship between matches)

        # For now, disable this check as it's too noisy for valid Cypher patterns
        # Cypher ALLOWS and ENCOURAGES variable reuse across MATCH clauses

        return violations

    def _check_with_without_distinct(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP008: Check for WITH clause without DISTINCT.

        WITH clauses CAN create duplicate rows, but this is often intentional.
        This is an informational check, not an error.

        Note: Disabled for now as it's too noisy. WITH without DISTINCT is
        a common and valid pattern in Cypher.
        """
        violations: list[Violation] = []

        # Disabled - too many false positives
        # WITH without DISTINCT is often intentional in Cypher

        return violations

    def _check_query_complexity(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP009: Check for overly complex queries.

        Complexity scoring based on:
        - Number of MATCH clauses (2 points each)
        - Number of WITH clauses (3 points each)
        - Traversal depth in relationships (1 point per hop)
        - Number of WHERE conditions (1 point each)
        - Aggregations (2 points each)
        - Subqueries (5 points each)

        Complexity > 20: Warning (query should be refactored)
        Complexity > 30: Strong warning (architecture review recommended)
        """
        violations: list[Violation] = []

        query_upper = query.upper()

        # Calculate complexity score
        complexity = 0

        # MATCH clauses (2 points each)
        match_count = len(re.findall(r"\bMATCH\b", query_upper))
        complexity += match_count * 2

        # WITH clauses (3 points each) - staging adds complexity
        with_count = len(re.findall(r"\bWITH\b", query_upper))
        complexity += with_count * 3

        # Relationship traversal depth
        # Pattern: -[:REL*1..5]-> gives depth
        traversal_patterns = re.findall(r"-\[.*?\*(\d+)\.\.(\d+)\]->", query)
        for _start, end in traversal_patterns:
            max_depth = int(end)
            complexity += max_depth

        # WHERE conditions (1 point each)
        where_count = len(re.findall(r"\bWHERE\b", query_upper))
        complexity += where_count

        # Aggregations (2 points each)
        agg_pattern = r"\b(COUNT|COLLECT|SUM|AVG|MIN|MAX)\s*\("
        agg_count = len(re.findall(agg_pattern, query_upper))
        complexity += agg_count * 2

        # Subqueries (5 points each) - CALL { ... }
        subquery_count = len(re.findall(r"\bCALL\s*\{", query_upper))
        complexity += subquery_count * 5

        # Report warnings based on complexity score
        if complexity > 30:
            violations.append(
                Violation(
                    rule_code="CYP009",
                    severity=Severity.WARNING,
                    message=f"Very high query complexity (score: {complexity}) - architecture review recommended",
                    file_path=file_path,
                    line_number=start_line,
                    line_content=self._get_line_at_position(query, 0),
                    suggestion=f"Consider refactoring into multiple simpler queries or using stored procedures. "
                    f"Breakdown: {match_count} MATCH ({match_count * 2}pts), {with_count} WITH ({with_count * 3}pts), "
                    f"{where_count} WHERE ({where_count}pts), {agg_count} aggregations ({agg_count * 2}pts)",
                )
            )
        elif complexity > 20:
            violations.append(
                Violation(
                    rule_code="CYP009",
                    severity=Severity.WARNING,
                    message=f"High query complexity (score: {complexity}) - consider refactoring",
                    file_path=file_path,
                    line_number=start_line,
                    line_content=self._get_line_at_position(query, 0),
                    suggestion=f"Break into smaller queries or simplify logic. "
                    f"Breakdown: {match_count} MATCH, {with_count} WITH, {where_count} WHERE, {agg_count} aggregations",
                )
            )

        return violations

    def _check_missing_index_hints(
        self, query: str, file_path: Path, start_line: int
    ) -> list[Violation]:
        """
        CYP010: Check for missing index hints on large dataset queries.

        NOTE: Disabled for now - most queries in SKUEL are already well-optimized,
        and Neo4j's query planner automatically uses indexes when available.

        This check would be useful if we had queries that weren't using existing indexes,
        but in practice, explicit USING INDEX is rarely needed in modern Neo4j.

        Keep this as a placeholder for future performance optimization work.
        """
        violations: list[Violation] = []

        # Disabled - Neo4j query planner handles this automatically
        # Most SKUEL queries are already well-optimized

        return violations

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _get_line_at_position(self, text: str, position: int) -> str:
        """Get the line of text at a specific character position."""
        # Find the line containing this position
        lines = text.split("\n")
        current_pos = 0

        for line in lines:
            if current_pos <= position < current_pos + len(line):
                return line
            current_pos += len(line) + 1  # +1 for newline

        return ""


def find_lintable_files(root_dir: Path) -> list[Path]:
    """
    Find files that likely contain Cypher queries.

    Python trees (Cypher embedded in string literals):
    - core/services/ (docstring Cypher examples — SKUEL021 bans executable Cypher)
    - adapters/persistence/neo4j/ (the below-boundary home of all executable Cypher)
    - scripts/ (migrations and maintenance scripts run raw Cypher directly —
      added 2026-07; the previous list also globbed core/models/query/, a tree
      that no longer exists)
    - tests/integration/

    Standalone .cypher files (whole-file Cypher — added 2026-07; before this,
    scripts/indexes.cypher and scripts/migrations/*.cypher ran in integration
    tests and migration tooling with zero lint coverage, and ci.yml already
    routed Cypher-only PRs through the Lint job in anticipation):
    - the same four trees, .cypher suffix

    tests/unit/ is deliberately excluded: the linter's own test fixtures are
    intentionally-bad queries.
    """
    trees = [
        "core/services",
        "adapters/persistence/neo4j",
        "scripts",
        "tests/integration",
    ]
    patterns = [f"{tree}/**/*.{suffix}" for tree in trees for suffix in ("py", "cypher")]

    files: list[Path] = []
    for pattern in patterns:
        files.extend(root_dir.glob(pattern))

    return files


def main() -> int:
    """Main entry point for Cypher linter."""
    parser = argparse.ArgumentParser(
        description="Cypher Query Linter - Static analysis for Neo4j queries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("files", nargs="*", help="Files to lint (default: auto-discover)")
    parser.add_argument(
        "--errors-only", action="store_true", help="Show only ERROR severity violations"
    )
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on errors (non-zero exit code). Default: warnings-only mode (always exit 0)",
    )

    args = parser.parse_args()

    # Find files to lint
    if args.files:
        files_to_lint = [Path(f) for f in args.files]
    else:
        # Derive the app root from this file's location (scripts/ -> app/) so
        # auto-discovery works on any checkout path — a hardcoded absolute path
        # made the CI Lint step discover 0 files on GitHub runners and pass
        # vacuously (Codex finding, PR #671).
        root_dir = Path(__file__).resolve().parents[1]
        files_to_lint = find_lintable_files(root_dir)
        print(f"🔍 Auto-discovered {len(files_to_lint)} files with potential Cypher queries\n")

    # Run linter
    linter = CypherLinter(errors_only=args.errors_only)
    all_violations: list[Violation] = []

    for file_path in files_to_lint:
        violations = linter.lint_file(file_path)
        all_violations.extend(violations)

    # Filter by severity if needed
    if args.errors_only:
        all_violations = [v for v in all_violations if v.severity == Severity.ERROR]

    # Report results
    if args.format == "text":
        print("=" * 80)
        print("Cypher Query Linter Results")
        print("=" * 80)
        print()

        if not all_violations:
            print("✅ No violations found!")
            print()
            print("All Cypher queries pass validation.")
            return 0

        # Group by severity
        errors = [v for v in all_violations if v.severity == Severity.ERROR]
        warnings = [v for v in all_violations if v.severity == Severity.WARNING]
        info = [v for v in all_violations if v.severity == Severity.INFO]

        print(f"Found {len(all_violations)} violations:")
        print(f"  - Errors: {len(errors)}")
        print(f"  - Warnings: {len(warnings)}")
        print(f"  - Info: {len(info)}")
        print()

        # Print violations
        for violation in all_violations:
            print(violation)

        print("=" * 80)
        print("Summary")
        print("=" * 80)
        print(f"Files scanned: {len(files_to_lint)}")
        print(f"Total violations: {len(all_violations)}")
        print()

        # Exit with error if there are ERROR severity violations AND --strict mode
        if args.strict:
            if errors:
                print("⚠️  STRICT MODE: Failing due to ERROR severity violations")
                return 1
            else:
                print("✅ STRICT MODE: No ERROR violations, passing")
                return 0
        else:
            # Warnings-only mode: always return 0 (success)
            if errors:
                print(
                    "ℹ️  Warnings-only mode: Violations reported but not blocking (use --strict to fail on errors)"
                )
            return 0

    else:  # JSON format
        import json

        output = {
            "files_scanned": len(files_to_lint),
            "total_violations": len(all_violations),
            "violations": [
                {
                    "rule_code": v.rule_code,
                    "severity": v.severity.value,
                    "message": v.message,
                    "file": str(v.file_path),
                    "line": v.line_number,
                    "suggestion": v.suggestion,
                }
                for v in all_violations
            ],
        }
        print(json.dumps(output, indent=2))
        # Exit with error only in strict mode
        if args.strict:
            return 1 if any(v.severity == Severity.ERROR for v in all_violations) else 0
        else:
            return 0  # Warnings-only mode


if __name__ == "__main__":
    sys.exit(main())
