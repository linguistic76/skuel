#!/usr/bin/env bash
# Dependency CVE audit — the ONE path for both CI (ci.yml pip_audit job) and
# local runs (./dev audit-deps).
#
# Audits the FULL locked resolution (uv.lock, all groups — dev deps run on
# developer machines and CI, so they count), not the live venv: what ships is
# what the lock says, and the export carries hashes so pip-audit needs no
# resolver (--disable-pip).
#
# Accepted findings live in .pip-audit-ignore (one ID per line, each with a
# documented reason). See docs/roadmap/security-hardening-deferred.md item 5.
set -euo pipefail
cd "$(dirname "$0")/.."

REQ="$(mktemp)"
trap 'rm -f "$REQ"' EXIT

# --locked: refuse to run if uv.lock is stale against pyproject.toml — uv
# would otherwise silently re-lock and audit an uncommitted resolution
# instead of the reviewed one (Codex, PR #797). Fail-fast: a stale-lock PR
# must re-lock, not slip past the gate.
uv export --locked --format requirements.txt --no-emit-project --all-groups \
  --quiet --output-file "$REQ"

IGNORE_ARGS=()
if [[ -f .pip-audit-ignore ]]; then
  while IFS= read -r line; do
    id="${line%%#*}"
    id="${id//[[:space:]]/}"
    [[ -n "$id" ]] && IGNORE_ARGS+=(--ignore-vuln "$id")
  done < .pip-audit-ignore
fi

# --strict: unauditable deps (e.g. not on PyPI) fail instead of warn.
# --vulnerability-service osv: pip-audit defaults to PyPI's advisory feed;
# OSV is the aggregate upstream (PYSEC + GHSA + more), so select it
# explicitly — the documented coverage, not the default (Codex, PR #797).
#
# --quiet suppresses uv's OWN progress, and it is load-bearing rather than
# cosmetic. CI caches the venv built with `uv sync --no-install-project`, so
# `uv run` reinstalls the project and emits lines like "Installed 1 package in
# 4ms" ahead of the audit verdict. dependency-audit.yml renders this output into
# a status issue and hashes it to decide whether the result CHANGED — and those
# millisecond timings are nondeterministic (6 local runs gave 2 distinct values;
# the first live CI run gave different ones again), so the digest moves whenever
# they do and posts a "result changed" comment about a result that did not
# change. The damage is not the noise: a spurious change-notification is
# indistinguishable from a real one, so it trains the reader to ignore the exact
# signal the issue exists to carry. Observed on that workflow's first live run
# (issue #938).
#
# It does not hide failures: `uv export --locked` above already carries --quiet
# and still refuses a stale lock loudly ("error: The lockfile at `uv.lock` needs
# to be updated", exit 2 — verified), and pip-audit's own findings are the child
# process's output, untouched by uv's verbosity flag.
uv run --quiet --locked pip-audit --strict --disable-pip --vulnerability-service osv \
  -r "$REQ" ${IGNORE_ARGS[@]+"${IGNORE_ARGS[@]}"}
