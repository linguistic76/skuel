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
import re
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
    """Every enforcement check run_quality_checks.py runs (fix mode pruned).

    Fails loudly on any run_command call whose first argument is not a
    literal list of strings — silently skipping an unparseable call would
    let a refactor (`cmd = [...]; run_command(cmd, ...)`) drop a check from
    parity coverage while the floor still passes (Codex, PR #981 round 7).
    """
    tree = ast.parse(QUALITY_RUNNER.read_text(encoding="utf-8"))
    collector = EnforcementCallCollector()
    collector.visit(tree)
    checks: set[str] = set()
    for node in collector.calls:
        first = node.args[0] if node.args else None
        is_literal = isinstance(first, ast.List) and all(
            isinstance(element, ast.Constant) and isinstance(element.value, str)
            for element in first.elts
        )
        if not is_literal:
            raise AssertionError(
                f"run_command call at {QUALITY_RUNNER.name}:{node.lineno} does not "
                "pass a literal list of strings — the parity extractor cannot see "
                "this check. Keep quality commands literal, or teach the extractor "
                "the new shape."
            )
        assert isinstance(first, ast.List)
        tokens = [element.value for element in first.elts if isinstance(element, ast.Constant)]
        identifier = canonical_check(tokens)
        if identifier is not None:
            checks.add(identifier)
    return checks


def gate_required_job_ids(workflow: dict) -> list[str]:
    """Job ids the always-on gate aggregates — the required-coverage set."""
    needs = workflow["jobs"]["gate"]["needs"]
    return list(needs) if isinstance(needs, list) else [needs]


# `<command> || echo "name_failed=true" >> $GITHUB_OUTPUT` — the deferred-fail
# capture used by validate_documentation so a PR comment can report first.
OUTPUT_CAPTURE = re.compile(r'echo\s+"?([A-Za-z_]+)=true"?\s*>>\s*"?\$GITHUB_OUTPUT"?')

# `if:` conditions that keep a check enforced on gating PR runs (Codex,
# PR #981 rounds 5-6). A step gated on anything else — event_name, refs,
# inputs — can be skipped on PRs while the job stays green, so it earns no
# credit. Step level: only the see-every-violation guards are safe.
SAFE_STEP_IF_CLAUSES = (
    re.compile(r"^!cancelled\(\)$"),
    re.compile(r"^success\(\)$"),
    re.compile(r"^steps\.[\w-]+\.outcome\s*!=\s*'skipped'$"),
)


def preserves_pr_enforcement(condition: object, patterns: tuple[re.Pattern[str], ...]) -> bool:
    """True when a GitHub `if:` cannot skip the check on a gating PR run."""
    if condition is None:
        return True
    text = str(condition).strip()
    text = text.removeprefix("${{").removesuffix("}}").strip()
    clauses = [clause.strip() for clause in re.split(r"&&|\|\|", text)]
    return all(any(pattern.match(clause) for pattern in patterns) for clause in clauses)


# Job level: path filters are the gate's deliberate skipped-when-unrelated
# contract — but only when the job keys on filters that COVER the check's
# inputs. `needs.changes.outputs.docs` on the mypy job would credit MyPy
# while a Python-only PR skips the job entirely (Codex, PR #981 round 6).
JOB_FILTER_CLAUSE = re.compile(r"^needs\.changes\.outputs\.([\w-]+)\s*==\s*'true'$")

# ALWAYS_ON: a job with no `if:` runs on every PR — covers any check.
ALWAYS_ON = frozenset({"*"})

# check identifier -> filters that must ALL be present in the job's OR-chain
# for the check to be enforced whenever its inputs change. New quality checks
# fail closed: an unmapped identifier earns no CI credit, and the parity
# assertion then names it — add the mapping alongside the CI step.
REQUIRED_FILTERS: dict[str, frozenset[str]] = {
    "ruff format --check": frozenset({"py"}),
    "ruff check": frozenset({"py"}),
    "mypy": frozenset({"py"}),
    "pyright": frozenset({"py"}),
    "scripts/lint_skuel.py --strict": frozenset({"py"}),
    # Lints standalone .cypher files AND py-embedded Cypher — needs both doors.
    "scripts/cypher_linter.py --errors-only --strict": frozenset({"py", "cypher"}),
    "scripts/audit_route_security.py": frozenset({"py"}),
    "scripts/audit_raw_headers.py": frozenset({"py"}),
    "scripts/detect_bloat.py --check": frozenset({"py"}),
    "scripts/shellcheck_tracked.py": frozenset({"py"}),
    # Lockfiles ride the py filter; osv-scanner.toml + the JS lockfile ride audit.
    "scripts/audit_dependencies.sh": frozenset({"py", "audit"}),
    "scripts/audit_content_boundary.py": frozenset({"py"}),
    "scripts/skills_validator.py": frozenset({"docs"}),
}

# Checks NO path filter can cover, so only an unconditional job counts as a home.
# Listing filters for these would be an approximation that reads like an encoding:
# `filters_cover_check` accepts any job whose OR-chain is a superset, so a filtered
# job carrying every named filter would pass this test while still skipping the
# check — and `app/.envrc` and `app/CLAUDE.md` are matched by NO filter at all,
# yet both are tracked files that can carry a scratch citation (both did).
ALWAYS_ON_ONLY: frozenset[str] = frozenset({"scripts/audit_untracked_refs.py"})


def job_filter_names(condition: object) -> frozenset[str] | None:
    """The changes-filter outputs a job's `if:` ORs over, or None if unsafe.

    Only pure OR-chains of `needs.changes.outputs.X == 'true'` qualify: an
    `&&` of two filters runs the job only when BOTH areas changed, which
    skips single-area PRs, so it fails closed like any unknown shape.
    """
    if condition is None:
        return ALWAYS_ON
    text = str(condition).strip()
    text = text.removeprefix("${{").removesuffix("}}").strip()
    if "&&" in text:
        return None
    names: set[str] = set()
    for clause in text.split("||"):
        match = JOB_FILTER_CLAUSE.match(clause.strip())
        if match is None:
            return None
        names.add(match.group(1))
    return frozenset(names)


def filters_cover_check(identifier: str, job_filters: frozenset[str] | None) -> bool:
    if job_filters is None:
        return False
    if identifier in ALWAYS_ON_ONLY:
        # Reads files no filter names — only an unconditional job is coverage.
        return job_filters == ALWAYS_ON
    if job_filters == ALWAYS_ON:
        return identifier in REQUIRED_FILTERS
    required = REQUIRED_FILTERS.get(identifier)
    return required is not None and required <= job_filters


# A chokepoint's `if:` may only OR output-fired clauses of this shape —
# an event guard or an && (e.g. `github.event_name == 'push' && …`) could
# skip the failure step on PRs, silently converting capture into swallow
# (Codex, PR #981 round 9).
CHOKEPOINT_IF_CLAUSE = re.compile(r"^steps\.[\w-]+\.outputs\.[\w-]+\s*==\s*'true'$")


def has_failure_chokepoint(job: dict, output_name: str) -> bool:
    """True if some unsuppressed step in the job reds it on this output.

    The chokepoint must be able to fail (`exit 1` in its run) and must be
    guaranteed to run on PRs when the output is set: either no `if:` at all
    (run body reads the output and decides), or a pure OR-chain of
    `steps.X.outputs.Y == 'true'` clauses, one of them this output —
    validate_documentation's "Fail if critical issues found" step is the
    canonical shape.
    """
    for step in job.get("steps", []):
        if step.get("continue-on-error") is True:
            continue
        run_block = step.get("run")
        if not isinstance(run_block, str) or "exit 1" not in run_block:
            continue
        condition = step.get("if")
        if condition is None:
            if f"outputs.{output_name}" in run_block:
                return True
            continue
        text = str(condition).strip().removeprefix("${{").removesuffix("}}").strip()
        if "&&" in text:
            continue
        clauses = [clause.strip() for clause in text.split("||")]
        if all(CHOKEPOINT_IF_CLAUSE.match(clause) for clause in clauses) and any(
            f"outputs.{output_name}" in clause for clause in clauses
        ):
            return True
    return False


def ci_check_set() -> set[str]:
    """Every ENFORCED check of a gate-required CI job.

    A command only counts as a CI home when its failure can red the job
    (Codex, PR #981): steps under `continue-on-error: true` and lines whose
    exit status is `||`-suppressed get no credit — unless the suppression is
    the capture-to-GITHUB_OUTPUT pattern AND an unsuppressed downstream
    chokepoint step fails the job on that output. A piped command (`mypy . |
    tee`) is only credited once `set -o pipefail` appeared earlier in its run
    block — without it Bash returns the LAST command's status and the check's
    failure is swallowed. Job/step `if:` conditions must be enforcement-
    preserving (path filters / keep-running guards); anything else — e.g.
    `github.event_name == 'push'` — skips the check on PR runs, so no credit.
    """
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    checks: set[str] = set()
    for job_id in gate_required_job_ids(workflow):
        job = workflow["jobs"][job_id]
        job_filters = job_filter_names(job.get("if"))
        if job_filters is None:
            continue
        job_suppressed = job.get("continue-on-error") is True
        for step in job.get("steps", []):
            run_block = step.get("run")
            if not isinstance(run_block, str):
                continue
            if not preserves_pr_enforcement(step.get("if"), SAFE_STEP_IF_CLAUSES):
                continue
            step_suppressed = job_suppressed or step.get("continue-on-error") is True
            pipefail_active = False
            for line in run_block.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith(("#", "echo")):
                    continue
                if stripped.startswith("set ") and "pipefail" in stripped:
                    pipefail_active = True
                    continue
                command, or_else, fallback = stripped.partition("||")
                identifier = canonical_check(command.split())
                if identifier is None:
                    continue
                if not filters_cover_check(identifier, job_filters):
                    continue
                if "|" in command and not pipefail_active:
                    continue
                if not step_suppressed and not or_else:
                    checks.add(identifier)
                    continue
                capture = OUTPUT_CAPTURE.search(fallback)
                if capture and has_failure_chokepoint(job, capture.group(1)):
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
        f"Extraction floor: only {len(ci)} enforced checks credited from ci.yml — "
        "either the YAML extractor regressed, or a gate-required job lost PR "
        "enforcement wholesale (event-gated `if:`, continue-on-error, …)."
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


# Drift-pins on the changes-filter DEFINITIONS (Codex, PR #981 round 7):
# REQUIRED_FILTERS trusts filter NAMES, so losing/mistyping a load-bearing
# glob (e.g. 'app/**/*.py' under py) would keep every mapping satisfied while
# Python PRs skip the very jobs this test credits. Sentinels pin the globs
# each name's credit rests on — a pin, not a glob-coverage engine: novel
# additions stay free, removing a sentinel is loud.
# py pins '.github/workflows/**' for this test's OWN trigger (Codex round 8):
# the PR that drops it skips unit_tests and the gate accepts the skip, so
# detection is delayed to the NEXT py-touching PR — which then stays red until
# the glob returns. Delayed-but-certain is this filter block's documented
# contract (see the shellcheck note in ci.yml's py filter: unconditional
# runs were considered and rejected); an always-on job for this guard would
# re-litigate that decision for less than one PR of latency.
SENTINEL_FILTER_GLOBS: dict[str, frozenset[str]] = {
    "py": frozenset(
        {
            "app/**/*.py",
            "app/pyproject.toml",
            "app/uv.lock",
            ".github/workflows/**",
            ".github/actions/**",
        }
    ),
    "cypher": frozenset({"app/**/*.cypher"}),
    "docs": frozenset({"app/docs/**", "app/.claude/skills/**"}),
    "audit": frozenset(
        {
            "app/scripts/audit_dependencies.sh",
            "app/osv-scanner.toml",
            "app/package-lock.json",
        }
    ),
}


def changes_filter_definitions() -> dict[str, list[str]]:
    """The dorny/paths-filter name -> glob-list map from the changes job."""
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    for step in workflow["jobs"]["changes"]["steps"]:
        if step.get("id") == "filter":
            definitions = yaml.safe_load(step["with"]["filters"])
            assert isinstance(definitions, dict)
            return definitions
    raise AssertionError("changes job has no step with id 'filter'")


def test_path_filters_keep_their_sentinel_globs() -> None:
    definitions = changes_filter_definitions()
    for name, sentinels in SENTINEL_FILTER_GLOBS.items():
        assert name in definitions, (
            f"changes filter '{name}' vanished from ci.yml but REQUIRED_FILTERS "
            "still credits checks through it."
        )
        missing = sentinels - set(definitions[name])
        assert not missing, (
            f"changes filter '{name}' lost sentinel glob(s) {sorted(missing)} — "
            "parity credit through this filter assumes those inputs trigger it; "
            "without them the credited jobs skip on exactly the PRs that matter."
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
