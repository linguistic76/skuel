"""The CI Gate's result check is an ALLOW-LIST, proven by executing it.

WHY THIS EXISTS

On 2026-08-06 a GitHub Actions major outage killed ci.yml's `changes` job with
the result value `abandoned` — a value GitHub documents nowhere for
`needs.<job>.result`. Every job that `needs` it skipped, and the required
CI Gate on PR #967 still reported SUCCESS over zero test coverage. The gate's
guard was a DENY-LIST::

    if [[ "$r" == "failure" || "$r" == "cancelled" ]]; then exit 1; fi

which admits every value it does not know, including ones GitHub adds later.
The fix inverts it: only ``success`` and ``skipped`` pass, anything else fails
and names the job and its literal value.

``skipped`` MUST stay green: the heavy jobs are path-scoped, so a docs-only PR
legitimately skips them and a success-only gate would deadlock every such PR.

HOW THESE TESTS WORK

The defect survived because its failure branch was never exercised — the gate
cannot be provoked into seeing `abandoned` on demand. So instead of asserting
things ABOUT the script, these tests RUN it: the step's ``run`` block is read
out of ci.yml, each ``${{ needs.<job>.result }}`` expression is substituted
with a chosen value (exactly what the Actions runner does before bash ever
sees the text), and the result is executed under ``bash -e`` — the runner's
default shell invocation for ``run`` steps. What passes and fails here is the
shipped logic, not a transcription of it.

Two API caveats measured during the incident, recorded so nobody "improves"
this into something weaker:

  * ``gh api .../runs/<id>/jobs`` reported ``conclusion: "cancelled"`` for the
    same jobs whose ``needs.<job>.result`` read ``abandoned``. Only the
    workflow expression decides the gate; the REST view actively misleads.
  * The gate's own run log (the echo line this step prints) is the ground
    truth for diagnosis — which is why the error message must name the job
    and the raw value.

See: PR #967 (the vacuous pass), .github/workflows/ci.yml job `gate`.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"

_STEP_NAME = "Verify required jobs"

# The runner substitutes `${{ … }}` before bash runs; this reproduces the one
# form the gate step uses. Anything fancier appearing in the step should break
# the leftover-`${{` assertion below rather than run as bash garbage.
_NEEDS_RESULT = re.compile(r"\$\{\{\s*needs\.([A-Za-z0-9_-]+)\.result\s*\}\}")


def _gate_job() -> dict:
    document = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    return document["jobs"]["gate"]


def _gate_script() -> str:
    steps = [s for s in _gate_job()["steps"] if s.get("name") == _STEP_NAME]
    assert len(steps) == 1, (
        f"ci.yml's gate job must have exactly one {_STEP_NAME!r} step; "
        f"found {len(steps)}. If it was renamed, update _STEP_NAME."
    )
    return str(steps[0]["run"])


def _needed_jobs() -> list[str]:
    needs = _gate_job()["needs"]
    assert isinstance(needs, list) and needs
    return [str(j) for j in needs]


def _run_gate(tmp_path: Path, **overrides: str) -> subprocess.CompletedProcess[str]:
    """Execute the shipped gate step with substituted job results.

    Every needed job defaults to ``success``; keyword arguments override
    per job (``changes="abandoned"``). Runs ``bash -e <file>``, matching the
    Actions runner's default ``bash -e {0}`` for ``run`` steps.
    """
    results = dict.fromkeys(_needed_jobs(), "success")
    unknown = set(overrides) - set(results)
    assert not unknown, f"override for jobs the gate does not need: {sorted(unknown)}"
    results.update(overrides)

    def substitute(match: re.Match[str]) -> str:
        return results[match.group(1)]

    rendered = _NEEDS_RESULT.sub(substitute, _gate_script())
    assert "${{" not in rendered, (
        "the gate step contains an Actions expression this test did not "
        "substitute — extend _NEEDS_RESULT or the substitution map:\n" + rendered
    )
    script = tmp_path / "gate.sh"
    script.write_text(rendered, encoding="utf-8")
    return subprocess.run(["bash", "-e", str(script)], capture_output=True, text=True, timeout=30)


# --- Drift guards: the loop covers what the gate needs --------------------


def test_gate_script_references_every_needed_job() -> None:
    """A job in `needs:` but absent from the loop is ungated — silently.

    Both directions are pinned. A needed job the script never reads would pass
    the gate no matter how it ended; a script reference to a job NOT in
    `needs:` evaluates to the empty string on the runner, which the allow-list
    would fail — loud, but wrong loud.
    """
    referenced = {m.group(1) for m in _NEEDS_RESULT.finditer(_gate_script())}
    needed = set(_needed_jobs())
    assert referenced == needed, (
        f"gate `needs:` and the verify loop have drifted — "
        f"needed but never checked: {sorted(needed - referenced)}; "
        f"checked but not needed: {sorted(referenced - needed)}"
    )


def test_gate_always_runs() -> None:
    """Branch protection treats a SKIPPED required check as passing.

    Without `if: always()` the gate itself skips whenever an upstream job
    fails or dies — and the required check goes green over the failure, the
    same vacuous pass by another door.
    """
    assert str(_gate_job().get("if", "")).strip() == "always()"


# --- The allow side: exactly `success` and `skipped` pass -----------------


def test_all_success_passes(tmp_path: Path) -> None:
    completed = _run_gate(tmp_path)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "CI Gate passed" in completed.stdout


def test_docs_only_pr_shape_passes(tmp_path: Path) -> None:
    """The shape this gate exists for: path filters skip every heavy job.

    This is the case a "fail on everything but success" over-correction would
    break — every docs-only PR would go red.
    """
    skipped_jobs = dict.fromkeys(_needed_jobs(), "skipped")
    skipped_jobs["changes"] = "success"
    completed = _run_gate(tmp_path, **skipped_jobs)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "CI Gate passed" in completed.stdout


@pytest.mark.parametrize("passing", ["success", "skipped"])
def test_each_allowed_value_passes_alone(tmp_path: Path, passing: str) -> None:
    completed = _run_gate(tmp_path, unit_tests=passing)
    assert completed.returncode == 0, completed.stdout + completed.stderr


# --- The deny side: everything else fails, by name ------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "failure",  # the one the deny-list did catch
        "cancelled",  # the other one
        "abandoned",  # the outage value that greenlighted PR #967
        "neutral",  # a real GitHub conclusion that could leak in next
        "totally-invented-value",  # whatever GitHub ships after that
        "",  # a job that never reported at all
    ],
)
def test_each_unknown_value_fails_and_names_itself(tmp_path: Path, bad: str) -> None:
    """The whole defect was an unexercised branch; this exercises it per value.

    The error must carry the job id and the literal value — the next unknown
    result has to diagnose itself from the gate's own log, because (measured
    2026-08-06) the REST jobs API reports a DIFFERENT conclusion than the
    `needs.<job>.result` expression the gate actually reads.
    """
    completed = _run_gate(tmp_path, unit_tests=bad)
    assert completed.returncode != 0, (
        f"gate passed with needs.unit_tests.result={bad!r}:\n" + completed.stdout
    )
    assert "::error::" in completed.stdout
    assert "'unit_tests'" in completed.stdout, completed.stdout
    assert f"needs.unit_tests.result='{bad}'" in completed.stdout, completed.stdout
    assert "CI Gate passed" not in completed.stdout


def test_the_measured_outage_shape_fails(tmp_path: Path) -> None:
    """The exact result vector from PR #967's gate log, replayed.

    changes=abandoned  content_boundary=abandoned  everything else skipped —
    the run that passed as SUCCESS with zero coverage must now fail, naming
    both abandoned jobs.
    """
    outage = dict.fromkeys(_needed_jobs(), "skipped")
    outage["changes"] = "abandoned"
    outage["content_boundary"] = "abandoned"
    completed = _run_gate(tmp_path, **outage)
    assert completed.returncode != 0, completed.stdout
    assert "needs.changes.result='abandoned'" in completed.stdout
    assert "needs.content_boundary.result='abandoned'" in completed.stdout


def test_every_failing_job_is_reported_not_just_the_first(tmp_path: Path) -> None:
    """The old loop exited on the first hit; one red run should tell the whole
    story, not force a fix-push-fail cycle per job."""
    completed = _run_gate(tmp_path, mypy="failure", js_tests="abandoned")
    assert completed.returncode != 0
    assert "needs.mypy.result='failure'" in completed.stdout
    assert "needs.js_tests.result='abandoned'" in completed.stdout
