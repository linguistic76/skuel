#!/usr/bin/env bash
# Dependency CVE audit — the ONE path for CI (ci.yml dep_audit job), the
# scheduled audit (dependency-audit.yml), ./dev quality check 8, and local
# runs (./dev audit-deps).
#
# One scanner, both ecosystems (ADR-067 § 6e): osv-scanner reads uv.lock and
# package-lock.json natively and queries OSV (the aggregate upstream: PYSEC +
# GHSA + more). ALL severities are reported in both ecosystems — every finding
# is either fixed or accepted in osv-scanner.toml with a reason and an
# ignoreUntil expiry. The former npm moderate+ floor was a workaround for
# `npm audit` having no accept mechanism and was deleted with that gap
# (ruled 2026-08-07; see the ADR).
#
# Exit contract (dependency-audit.yml's three-state issue relies on it):
#   0 — measured, clean (accepted findings may exist; stderr names them)
#   1 — measured, unaccepted findings
#   3 — NOT measured (stale lock, missing tool, count mismatch, scanner error)
set -euo pipefail
cd "$(dirname "$0")/.."

# Refuse uv's lock env overrides (UV_FROZEN / UV_LOCKED) rather than run
# under them: either one silently downgrades `uv lock --check` below to a
# validity-only check (measured, uv 0.10.9 — "only checked for validity, not
# whether it is up-to-date"), which would pass the freshness gate vacuously
# over a stale lock. That is the PR #935 defect class exactly, so it is a
# hard refusal, not a warning. The CI jobs that run this script deliberately
# declare neither variable (enforced by test_workflow_uv_lock_pinning.py —
# whose name rule is also why the messages below do not spell the variable
# names: the guard refuses those names in any executable shell).
if [[ -n "${UV_FROZEN:-}" || -n "${UV_LOCKED:-}" ]]; then
  echo "audit: a uv lock-pinning env override is set — it silently turns the" >&2
  echo "audit: 'uv lock --check' staleness gate into a validity-only check." >&2
  echo "audit: Unset it (the comment above this check names both variables)." >&2
  exit 3
fi

if ! command -v uv >/dev/null; then
  echo "audit: uv not found on PATH — required for the lock-freshness gate." >&2
  exit 3
fi

if ! command -v osv-scanner >/dev/null; then
  echo "audit: osv-scanner not found on PATH (CI installs it via .github/actions/install-osv-scanner)." >&2
  echo "audit: local install (Linux x86_64, pin + checksum live in that action):" >&2
  echo "  curl -sSfL -o ~/.local/bin/osv-scanner \\" >&2
  echo "    https://github.com/google/osv-scanner/releases/download/v2.5.0/osv-scanner_linux_amd64 && \\" >&2
  echo "    chmod +x ~/.local/bin/osv-scanner" >&2
  exit 3
fi

# The lock must match the manifest BEFORE scanning: osv-scanner happily audits
# a stale uv.lock and reports clean for a resolution that is not the one that
# would be installed. `uv lock --check` asserts freshness without writing.
# This replaces the old `uv export --locked` guard — same property, no derived
# requirements.txt (Codex, PR #797).
#
# --quiet is load-bearing, not cosmetic (same reason as #939): the bare form
# prints "Resolved N packages in Xms", and dependency-audit.yml hashes this
# script's output to decide whether the result CHANGED — nondeterministic
# timings would raise "result changed" comments about results that did not.
# --quiet also suppresses uv's own stale-lock error (measured, uv 0.10.9);
# the message below narrates the failure deterministically instead.
if ! uv lock --check --quiet; then
  echo "audit: uv.lock is stale against pyproject.toml — run 'uv lock', review, commit." >&2
  echo "audit: refusing to audit a resolution nobody reviewed." >&2
  exit 3
fi

RESULT="$(mktemp)"
STATE="$(mktemp)"
trap 'rm -f "$RESULT" "$STATE"' EXIT

# --all-packages is load-bearing, not verbosity: osv-scanner exits 0 on a
# lockfile it can only partially read, so the verifier below asserts that the
# number of packages scanned equals the number the lockfiles declare. A clean
# verdict over fewer packages than the lock holds is NOT a measurement.
#
# --verbosity error, for the same digest-determinism reason as the --quiet
# above: info-level stderr carries elapsed-time lines ("… 18.39ms elapsed"),
# absolute runner paths, and the per-finding "filtered out" notes. All of the
# deterministic content (package counts, accepted findings, unaccepted
# findings) is re-rendered by the verifier below from the JSON and the toml;
# real errors still print (measured: error verbosity is byte-silent on a
# clean run, and exit codes are unaffected).
rc=0
osv-scanner scan source \
  --config osv-scanner.toml \
  --lockfile uv.lock \
  --lockfile package-lock.json \
  --format json --all-packages \
  --verbosity error \
  --output-file "$RESULT" || rc=$?

# 0 = clean, 1 = findings — anything else is a scanner/API failure, and the
# result must read as "not measured", never as "clean" (osv-scanner exits 127
# on a malformed or missing lockfile — measured, v2.5.0).
if [[ "$rc" -ne 0 && "$rc" -ne 1 ]]; then
  echo "audit: osv-scanner failed (exit $rc) — dependencies were NOT measured." >&2
  exit 3
fi

# Second scan WITHOUT the ignores: the accepted advisories' current upstream
# state — above all, whether a FIXED release now exists — must be part of the
# deterministic report, or a fix shipping while an acceptance stands would
# leave the scheduled digest unchanged until ignoreUntil lapses (Codex, #978;
# the retired js_audit hashed npm's fixAvailable for exactly this transition).
# The config scan above stays the ONE verdict source; this one only feeds the
# report, so its failure is a failure to produce the promised report → exit 3.
#
# --config /dev/null is load-bearing, not decoration: osv-scanner AUTO-reads
# an osv-scanner.toml sitting next to the scanned lockfiles, so omitting the
# flag silently re-applies the very ignores this scan exists to see past
# (measured — every accepted advisory vanished from the "config-less" output).
src=0
osv-scanner scan source \
  --config /dev/null \
  --lockfile uv.lock \
  --lockfile package-lock.json \
  --format json --all-packages \
  --verbosity error \
  --output-file "$STATE" || src=$?
if [[ "$src" -ne 0 && "$src" -ne 1 ]]; then
  echo "audit: osv-scanner state scan failed (exit $src) — dependencies were NOT measured." >&2
  exit 3
fi

# The verifier's own failure (a JSON parse error, an unexpected schema) must
# surface as exit 3, never as the scanner's exit 1 — dependency-audit.yml
# reads exit 1 as "measured, unaccepted findings", which a crashed verifier
# cannot claim (Codex, #978). Its deliberate count-mismatch exit is already 3.
vrc=0
python3 - "$RESULT" "$STATE" <<'PY' || vrc=$?
import json
import sys
import tomllib

result_path, state_path = sys.argv[1], sys.argv[2]
scan = json.load(open(result_path))
state = json.load(open(state_path))
results = scan.get("results") or []

# Expected package counts, derived from the lockfiles themselves so the
# assertion tracks every future resolution change without maintenance.
with open("uv.lock", "rb") as f:
    uv_expected = sum(1 for line in f if line.strip() == b"[[package]]")
with open("package-lock.json", "rb") as f:
    npm_lock = json.load(f)
npm_expected = len(
    {
        (path.rsplit("node_modules/", 1)[-1], info.get("version"))
        for path, info in npm_lock.get("packages", {}).items()
        if path
    }
)
expected = {"uv.lock": uv_expected, "package-lock.json": npm_expected}

scanned = {}
findings = []
for result in results:
    source = result["source"]["path"].rsplit("/", 1)[-1]
    packages = result.get("packages") or []
    scanned[source] = len(packages)
    for package in packages:
        pkg = package["package"]
        for group in package.get("groups") or []:
            findings.append(
                (
                    source,
                    pkg["name"],
                    pkg["version"],
                    " / ".join(group.get("ids") or []),
                    group.get("max_severity") or "?",
                )
            )

failed = False
for lockfile, want in expected.items():
    got = scanned.get(lockfile)
    if got != want:
        failed = True
        print(
            f"audit: {lockfile}: scanned {got if got is not None else 'NO'} packages "
            f"but the lockfile declares {want} — partial scans read as clean, so this "
            "run is NOT a measurement.",
            file=sys.stderr,
        )
if failed:
    sys.exit(3)

with open("osv-scanner.toml", "rb") as f:
    accepted = tomllib.load(f).get("IgnoredVulns") or []
soonest = min((entry["ignoreUntil"] for entry in accepted), default=None)

# Each accepted advisory's upstream fix state, from the config-less scan.
# Rendered into the report so the digest CHANGES when a fixed release ships
# (or the advisory stops matching the lock) — the transitions a maintainer
# wants to hear about while an acceptance stands. Versions come from the OSV
# records' affected-range "fixed" events: stable strings, no timestamps, so
# the line moves only when the fix state does.
state_vulns = [
    (package["package"], vuln)
    for result in state.get("results") or []
    for package in result.get("packages") or []
    for vuln in package.get("vulnerabilities") or []
]

def fix_state(advisory_id: str) -> str:
    fixes: set[str] = set()
    matched = False
    for pkg, vuln in state_vulns:
        if vuln.get("id") != advisory_id and advisory_id not in (vuln.get("aliases") or []):
            continue
        matched = True
        for affected in vuln.get("affected") or []:
            if (affected.get("package") or {}).get("name") != pkg["name"]:
                continue
            for rng in affected.get("ranges") or []:
                for event in rng.get("events") or []:
                    if "fixed" in event:
                        fixes.add(str(event["fixed"]))
    if not matched:
        return "no longer reported by OSV for the locked resolution — entry deletable?"
    if fixes:
        return "fixed in " + ", ".join(sorted(fixes))
    return "no fixed release published"

for lockfile, want in expected.items():
    print(f"audit: {lockfile}: {want} packages scanned, count verified")
print(
    f"audit: {len(accepted)} accepted findings in osv-scanner.toml"
    + (f" (earliest ignoreUntil: {soonest})" if soonest else "")
)
for entry in sorted(accepted, key=lambda e: str(e["id"])):
    print(f"  accepted: {entry['id']} (until {entry['ignoreUntil']}) — {fix_state(str(entry['id']))}")
if findings:
    print(f"audit: {len(findings)} UNACCEPTED finding(s):")
    for source, name, version, ids, severity in findings:
        print(f"  {source}: {name} {version} — {ids} (max CVSS {severity})")
else:
    print("audit: no unaccepted findings")
PY

if [[ "$vrc" -ne 0 ]]; then
  if [[ "$vrc" -ne 3 ]]; then
    echo "audit: report verifier failed (exit $vrc) — dependencies were NOT measured." >&2
  fi
  exit 3
fi

exit "$rc"
