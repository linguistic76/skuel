"""
CI ↔ ./dev quality parity drift test
=====================================

`./dev quality` (scripts/run_quality_checks.py) and CI (../.github/workflows/
ci.yml) are two hand-maintained doors onto the same check list. Before this
test existed the lists drifted silently: the dead-code gate, the raw-headers
audit, and Pyright ran locally for months with no CI home, so a PR authored
without a local `./dev quality` could merge while failing it.

This test extracts the check set from both sides and fails when a quality
check has no home in a gate-required CI job:

- Quality side: AST — every `run_command([...])` call in run_quality_checks.py.
- CI side: YAML — every `run:` line of every job the `gate` job `needs`
  (a check that only runs in a non-required job is NOT coverage), with
  `echo`/comment lines dropped so "run locally" hints can't fake coverage.

CI may legitimately run MORE than quality (tests, docs freshness, smoke) —
the assertion is one-directional. A check that is deliberately local-only
belongs in DELIBERATELY_LOCAL_ONLY with a reason; entries that gain a CI home
are flagged as stale (the SKUEL026 discipline: an exemption must exempt).
"""

import ast
from pathlib import Path

import yaml

APP_ROOT = Path(__file__).resolve().parents[3]
QUALITY_RUNNER = APP_ROOT / "scripts" / "run_quality_checks.py"
CI_WORKFLOW = APP_ROOT.parent / ".github" / "workflows" / "ci.yml"

# Checks ./dev quality runs that deliberately have no CI home.
# Every entry needs a reason; an entry whose check appears in CI is stale.
DELIBERATELY_LOCAL_ONLY: dict[str, str] = {}

# Extraction-floor guards: a parser regression that returns near-empty sets
# must fail loudly, not pass vacuously.
MIN_QUALITY_CHECKS = 10
MIN_CI_CHECKS = 10

# Flags that change what a check ENFORCES, not how it prints. These are part
# of the check's identity: CI dropping --check from detect_bloat.py (advisory,
# exit 0 on WARNINGs) or ruff format (rewrites files, always exits 0), or
# --strict from a linter, is enforcement drift even though the command still
# matches (Codex, PR #981). Presentation flags (--quiet, --json) stay out;
# quality's --fix branches are pruned at extraction instead (see
# quality_check_set), so the auto-repair variants never reach comparison.
GATE_AFFECTING_FLAGS = frozenset({"--check", "--strict", "--errors-only"})


def canonical_check(tokens: list[str]) -> str | None:
    """Map a command's tokens to a stable check identifier, or None.

    Identifier is the scripts/ path — or the bare tool invocation (ruff keeps
    its subcommand) — plus any gate-affecting flags present, sorted. The
    command AND its enforcement mode are the check.
    """
    base: str | None = None
    for token in tokens:
        if token.startswith("scripts/") and token.endswith((".py", ".sh")):
            base = token
            break
    if base is None and "ruff" in tokens:
        index = tokens.index("ruff")
        subcommand = tokens[index + 1] if index + 1 < len(tokens) else ""
        base = f"ruff {subcommand}"
    if base is None and "mypy" in tokens:
        base = "mypy"
    if base is None and "pyright" in tokens:
        base = "pyright"
    if base is None:
        return None
    gate_flags = sorted(GATE_AFFECTING_FLAGS.intersection(tokens))
    return " ".join([base, *gate_flags])


def is_fix_mode_test(test: ast.expr) -> bool:
    """True for the literal `args.fix` condition in run_quality_checks.py."""
    return (
        isinstance(test, ast.Attribute)
        and test.attr == "fix"
        and isinstance(test.value, ast.Name)
        and test.value.id == "args"
    )


class EnforcementCallCollector(ast.NodeVisitor):
    """Collects run_command calls, skipping `if args.fix:` bodies.

    The fix branches (`ruff format`, `ruff check --fix`) are auto-repair
    conveniences, not the enforcement contract — comparing them against CI
    would false-fail on the flagless variants. Only the else-side (check
    mode) is what CI must mirror.
    """

    def __init__(self) -> None:
        self.calls: list[ast.Call] = []

    def visit_If(self, node: ast.If) -> None:
        if is_fix_mode_test(node.test):
            for statement in node.orelse:
                self.visit(statement)
            return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name) and func.id == "run_command":
            self.calls.append(node)
        self.generic_visit(node)


def quality_check_set() -> set[str]:
    """Every enforcement check run_quality_checks.py runs (fix mode pruned)."""
    tree = ast.parse(QUALITY_RUNNER.read_text(encoding="utf-8"))
    collector = EnforcementCallCollector()
    collector.visit(tree)
    checks: set[str] = set()
    for node in collector.calls:
        if not (node.args and isinstance(node.args[0], ast.List)):
            continue
        tokens = [
            element.value
            for element in node.args[0].elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        ]
        identifier = canonical_check(tokens)
        if identifier is not None:
            checks.add(identifier)
    return checks


def gate_required_job_ids(workflow: dict) -> list[str]:
    """Job ids the always-on gate aggregates — the required-coverage set."""
    needs = workflow["jobs"]["gate"]["needs"]
    return list(needs) if isinstance(needs, list) else [needs]


def ci_check_set() -> set[str]:
    """Every check invoked by a `run:` line of a gate-required CI job."""
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    checks: set[str] = set()
    for job_id in gate_required_job_ids(workflow):
        job = workflow["jobs"][job_id]
        for step in job.get("steps", []):
            run_block = step.get("run")
            if not isinstance(run_block, str):
                continue
            for line in run_block.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith(("#", "echo")):
                    continue
                identifier = canonical_check(stripped.split())
                if identifier is not None:
                    checks.add(identifier)
    return checks


def test_every_quality_check_has_a_ci_home() -> None:
    quality = quality_check_set()
    ci = ci_check_set()

    assert len(quality) >= MIN_QUALITY_CHECKS, (
        f"Extraction floor: only {len(quality)} checks parsed from "
        f"{QUALITY_RUNNER.name} — the AST extractor regressed, not the check list."
    )
    assert len(ci) >= MIN_CI_CHECKS, (
        f"Extraction floor: only {len(ci)} checks parsed from ci.yml — "
        "the YAML extractor regressed, not the workflow."
    )

    missing = quality - ci - set(DELIBERATELY_LOCAL_ONLY)
    assert not missing, (
        f"./dev quality checks with no gate-required CI home: {sorted(missing)}. "
        "Add a step to the matching CI job (usually lint), or register the "
        "check in DELIBERATELY_LOCAL_ONLY with a reason."
    )


def test_local_only_exemptions_are_not_stale() -> None:
    stale = set(DELIBERATELY_LOCAL_ONLY) & ci_check_set()
    assert not stale, (
        f"DELIBERATELY_LOCAL_ONLY entries that DO run in CI: {sorted(stale)}. "
        "Delete the exemption — an exemption that exempts nothing rots."
    )


def test_gate_needs_every_defined_job_or_documents_why() -> None:
    """A job outside the gate's needs list is invisible to branch protection.

    documentation_metrics is the known main-push-only artifact job; anything
    else outside the gate must be a deliberate, named decision here.
    """
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    non_gate_jobs = set(workflow["jobs"]) - set(gate_required_job_ids(workflow)) - {"gate"}
    known_unrequired = {"documentation_metrics"}
    unaccounted = non_gate_jobs - known_unrequired
    assert not unaccounted, (
        f"CI jobs neither gate-required nor registered as deliberately "
        f"unrequired: {sorted(unaccounted)}."
    )
