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

uv export --format requirements.txt --no-emit-project --all-groups \
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
uv run pip-audit --strict --disable-pip -r "$REQ" ${IGNORE_ARGS[@]+"${IGNORE_ARGS[@]}"}
