---
related_skills:
- pytest
---
# SKUEL Testing Guide

## Quick Reference

**Skill:** [@pytest](.claude/skills/pytest/SKILL.md)

```bash
# Run integration tests (real Neo4j via Docker)
./dev test-integration

# Run unit tests (fast, no Docker; parallel — up to 8 xdist workers)
./dev test-unit

# The pytest arms (test, test-unit, test-integration, test-quick) forward their flags
./dev test-unit -k "task" --tb=short

# Run specific test files
uv run pytest tests/unit/test_tasks_service.py -v
uv run pytest tests/unit/test_tasks_scheduling_service.py -v

# Coverage is opt-in — the one path; writes coverage.xml + coverage.json + htmlcov/
./dev test --cov
./dev coverage-summary   # the gap picture from coverage.json (three tables)
```

## Test Suite Status

SKUEL runs two primary tiers, both gated in CI (`.github/workflows/ci.yml`):

- **Unit** (`tests/unit/`) — mock-based, no Docker, parallel. `./dev test-unit`
- **Integration** (`tests/integration/`) — real Neo4j via testcontainers, serial. `./dev test-integration`

Run both tiers in one session with `./dev test` (needs Docker; serial — see
[Parallel Execution](#parallel-execution)), or the integration tier plus the auth /
error-handling unit files with `./dev test-quick`.

**Why integration tests are the primary tier:**
- Use a real database and services
- Exercise the actual graph-native architecture
- Relationship queries run against real edges, not mocked field access

## Test Categories

### By Type

| Category | Command | Notes |
|----------|---------|-------|
| **Integration** | `./dev test-integration` | Real Neo4j (Docker), serial, slower than unit |
| **Unit** | `./dev test-unit` | Mock-based, no Docker, parallel — fastest |
| **Both** | `./dev test` | Unit + integration in one serial session, needs Docker |

### By Domain

```bash
# Tasks domain (recurse, then filter by keyword — catches nested suites)
uv run pytest tests/unit/ -k "task" -v
uv run pytest tests/integration/ -k "task" -v

# Habits domain
uv run pytest tests/unit/ -k "habit" -v
uv run pytest tests/integration/ -k "habit" -v

# Goals domain
uv run pytest tests/unit/ -k "goal" -v
uv run pytest tests/integration/ -k "goal" -v

# All unit tests (pytest recurses into tests/unit/ subdirectories)
uv run pytest tests/unit/ -v
```

## Common Test Commands

### Quick Verification

```bash
# Run specific test file with verbose output
uv run pytest tests/unit/test_tasks_service.py -v

# Run specific test function
uv run pytest tests/unit/test_tasks_service.py::test_create_task_succeeds -v

# Show short traceback for failures
uv run pytest tests/unit/test_tasks_service.py --tb=short

# Run with print output visible
uv run pytest tests/unit/test_tasks_service.py -v -s
```

### Coverage Analysis

Coverage is opt-in: a plain run collects none (pass rate is the quality metric), and
`--cov` on any of the pytest `./dev test*` arms (`test`, `test-unit`, `test-integration`,
`test-quick`) is the one path that does — it writes `coverage.xml`, `coverage.json` and
`htmlcov/` and prints `term-missing` for `core/`, `adapters/`, `ui/` and `services_bootstrap/`.
(`./dev test-js` forwards its flags to vitest, which has no `--cov`.)

`./dev coverage-summary [path]` (`scripts/coverage_summary.py`) renders the gap picture from
`coverage.json` as three Markdown tables — per-package rates, files with zero coverage, large
files under 50 % — the same tables the weekly composed CI run appends to its step summary. It
reads the JSON report rather than the Cobertura XML because, with four `--cov=` trees, coverage
writes each file into the XML relative to its own tree: `core/auth/__init__.py` and
`ui/auth/__init__.py` collapse into one entry, and `auth/graph_auth.py` names no tree. Coverage
numbers carry no threshold anywhere — pass rate is the quality metric; the tables say where
the next test is worth writing.

```bash
# Both tiers with coverage
./dev test --cov

# One tier, or a filtered subset, with coverage
./dev test-integration --cov
./dev test-unit --cov -k "task"

# Open HTML coverage report
xdg-open htmlcov/index.html

# The three gap tables (per package / zero coverage / large under 50 %)
./dev coverage-summary
```

### Filtering Tests

```bash
# Run only tests matching pattern
uv run pytest tests/ -k "task" -v

# Run only integration tests for tasks
uv run pytest tests/integration/ -k "task" -v

# Exclude a path from collection (e.g. the nested service suites)
uv run pytest tests/unit/ --ignore=tests/unit/services
```

### Parallel Execution

The **unit tier runs in parallel by default** — `./dev test-unit` (the `unit` mode of
`scripts/run_tests.py`) appends `-n logical --maxprocesses 8 --dist loadfile`: pytest-xdist
with one worker per logical CPU, at most eight, and a test module never split across
workers (the corpus-scanning modules carry module-scoped fixtures, so the critical path
is the longest module, not the sum). The cap is measured: every worker imports the app
(~0.5 GB resident), and past eight workers the run is no shorter — the longest module is
the floor — while fourteen of them push a 16 GB laptop with a desktop session into swap.
CI's `unit_tests` job runs the same shape (a 4-vCPU runner never reaches the cap). Any
worker or distribution choice in the forwarded flags replaces the default wholesale:

```bash
./dev test-unit                    # -n logical --maxprocesses 8 --dist loadfile
./dev test-unit --maxprocesses 4   # a lower cap (pytest keeps the last one given)
./dev test-unit -n 1               # one xdist worker
./dev test-unit -n 0               # in-process serial — the shape bare `uv run pytest tests/unit/` has
```

The **integration tier is serial, by ruling**, and so is every mode that holds it
(`./dev test`, `./dev test-integration`, `./dev test-quick`): its session-scoped fixtures
are three Neo4j testcontainers (two in `conftest.py`, the APOC-lockdown suite's third)
plus one app boot, and under xdist a session fixture is built on every worker whose
assigned files request it — with `--dist loadfile` the shared container on nearly every
worker, the app container and its boot on every worker that receives an Askesis or route
module, the lockdown container once — so N workers cost up to N container sets and never
less than N shared containers. Each container's JVM is **sized for the test graphs, not for the host**:
`bounded_neo4j_container()` (`tests/integration/_container_lifecycle.py`) pins 128m
initial / 512m max heap and a 128m page cache, measured at ~2.8 GiB for the three
together at the tier's peak (the busy shared container ~1.4 GiB, the other two ~0.6–0.9)
against ~3.1 GiB unsized, with the tier's wall time unchanged. The numbers are a
code-side ceiling and stay one on a larger machine — a bigger host is not a licence to
size from it again. Every memory bound in the test tooling, where it lives, and what a larger
machine changes is the [development-machine-capacity](docs/roadmap/development-machine-capacity.md)
case file. `./dev test` is the composed-session guard
(one session, both tiers — the shape the per-tier CI jobs never run; its CI twin is the
weekly `composed-test-run.yml`, see [Continuous Integration](#continuous-integration)), and its wall time is the
integration tier's plus the unit tier's, serial.

**A test that only passes serially has a hidden dependency** — a fixed path, a fixed
port, module state another worker also touches. Fix the test (`tmp_path`, per-test
state); there is no serial marker, and none is enforced.

Every test body has a **120 s ceiling** (`pytest-timeout`, `timeout = 120` with
`timeout_func_only = true` in `pyproject.toml`): fixture setup — the container starts,
the app boot — is not charged, and `Failed: Timeout (>120.0s) from pytest-timeout`
means the body hung. A test that legitimately needs longer declares
`@pytest.mark.timeout(N)` with a one-line reason.

## Test Philosophy

### Integration Tests First

**SKUEL prioritizes integration tests because:**

1. **Graph-Native Architecture** - Real Neo4j queries test actual behavior
2. **End-to-End Validation** - Service → Backend → Database → Result
3. **Relationship Testing** - Graph edges tested properly
4. **Fast & Reliable** - Quick feedback against real behavior

**When to Use:**
- ✅ Verifying feature implementation
- ✅ Testing relationship queries
- ✅ Validating service integrations
- ✅ Continuous development workflow

### Unit Tests Second

**Unit tests are valuable for:**
- Testing pure business logic
- Validating error handling
- Testing edge cases
- Isolated component behavior

**When to Use:**
- Fast feedback on pure logic without spinning up Docker
- Complementary to integration tests, which remain the primary verification tier

## Test Organization

### Directory Structure

```
tests/
├── unit/                     # Mock-based, no Docker (./dev test-unit)
│   ├── test_tasks_service.py
│   ├── test_tasks_scheduling_service.py
│   └── ...
│
├── integration/              # Real Neo4j via testcontainers (./dev test-integration)
│   ├── routes/               # Route / API tests
│   ├── relationships/        # Graph-edge tests
│   ├── e2e/                  # Whole-workflow flows (worker → stored vector → search)
│   ├── conftest.py           # Testcontainer lifecycle
│   └── ...
│
└── conftest.py               # Shared fixtures
```

### Test Naming Conventions

```python
# Integration tests
def test_create_task_with_relationships_integration():
    """Integration test - uses real database and services"""

# Unit tests
def test_create_task_success():
    """Unit test - uses mocks"""

# Service tests
def test_tasks_service_creation():
    """Service-level test"""
```

## Continuous Integration

CI (`.github/workflows/ci.yml`, both jobs path-gated on Python changes) runs:

- **`unit_tests`** — `pytest tests/unit/ -n logical --maxprocesses 8 --dist loadfile`
  (mock-based, no Docker; the runner's parallel shape, `-x` stopping every worker on
  the first failure)
- **`integration_tests`** — `pytest tests/integration/`, serial; testcontainers boots the
  pinned Neo4j image on the runner's Docker daemon,
  identical to `./dev test-integration` locally. No `services:` block needed —
  the testcontainer fixture in `tests/integration/conftest.py` owns the
  container lifecycle.

Every CI job carries a `timeout-minutes` budget (≈3× its measured duration; the test
tiers 20 and 25 min), so a hung job frees its runner in minutes. Inside a job, a hung
*test* is caught earlier by pytest-timeout's 120 s per-test ceiling.

Every collected test runs in one of those two jobs — as separate processes. The
composed session (`./dev test`, both tiers in one process) has a CI twin of its own:
`.github/workflows/composed-test-run.yml` runs `scripts/run_tests.py comprehensive --cov
--tb=short -q` weekly (Mondays 05:00 UTC) and on `workflow_dispatch`, serial, at
`INTELLIGENCE_TIER=core`. A defect in the *composition* — a test package shadowing a
top-level one once both trees share a collection path, a session fixture one tier leaves
behind for the other — is what that run catches and the per-tier jobs cannot. It is the
one run that collects coverage: `coverage.xml` + `coverage.json` + `htmlcov/` and the
pytest output are uploaded as artifacts (30 days), the gap picture from
`./dev coverage-summary` is appended to the step summary, and a red run opens or comments
on one marker-keyed issue ("The composed test run is red"). Advisory — it feeds no gate,
and no coverage number is a failure condition. `tests/benchmarks/` holds an uncollected
script (`./dev test` ignores the directory by name to guard that intent).

### Pre-Commit Hooks

```bash
# .git/hooks/pre-commit
#!/bin/bash
./dev format-check
./dev lint
./dev test-quick
```

## Troubleshooting

### Tests Hang or Timeout

**A single test fails with `Failed: Timeout (>120.0s) from pytest-timeout`:** the test
body never returned — a wait on something that never arrives. Find the wait; the
ceiling is a hang detector, not a budget to raise (`@pytest.mark.timeout(N)` is for a
test that provably needs longer, with its reason on the line).

**The whole integration run hangs before its first test:**

**Cause:** Docker isn't ready. Integration tests boot an **ephemeral Neo4j
testcontainer** (`tests/integration/conftest.py`) on the Docker daemon — not the
Compose `skuel-neo4j` container — so the daemon must be running and able to start
the pinned Neo4j image.
**Fix:**
```bash
# Ensure the Docker daemon is running (testcontainers manages Neo4j itself)
docker info >/dev/null && echo "Docker OK"

# While the suite runs, watch the ephemeral Neo4j testcontainer start
docker ps

# If startup is the problem, inspect the most recent container's logs
docker logs "$(docker ps -lq)"
```

### Orphaned Neo4j Testcontainers After a Killed Run

**Symptom:** `docker ps` shows `neo4j:…` containers from an earlier session — a run the
harness stopped, a terminal that went away, a `kill -9` — still up and holding ~1 GiB
each; a later `free -g` is short by that much.

**Cause:** Ryuk (testcontainers' reaper) was never told what to reap. The library
sends the session filter the moment the Ryuk container is *running*, without waiting
for the process inside to *listen*, and never reads the reply; on a Linux daemon
docker-proxy accepts that early connection on Ryuk's behalf and resets it, so Ryuk
never sees a client, exits on its own 60 s first-connection timer, and the session runs
with no reaper (testcontainers-python#1114 — observed here in 2 of 4 sessions).
`bounded_neo4j_container()` closes the hole for every container it builds: it reads
Ryuk's `ACK` before starting the container and re-registers when the ACK is missing, so
a killed session's containers are removed ~10 s after the process dies
(`RYUK_RECONNECTION_TIMEOUT`). Verify with `docker logs -f "$(docker ps -q --filter
name=testcontainers-ryuk)"` during a run: a registered session shows
`New client connected` and `Adding {"label":…}`; a lost one shows `Timeout waiting for
connection`.

**Remedy** for containers that leaked anyway (a session started on an older tree, Ryuk
disabled by `TESTCONTAINERS_RYUK_DISABLED`):
```bash
docker ps -aq --filter label=org.testcontainers=true | xargs -r docker rm -f
```

### Import Errors

**Cause:** Missing test dependencies
**Fix:**
```bash
uv sync
```

### Fixture Errors

**Cause:** Shared database state between tests
**Fix:**
```python
# Use proper fixture scoping
@pytest.fixture(scope="function")  # New instance per test
def backend():
    ...

# Clean up after tests
@pytest.fixture(autouse=True)
async def cleanup():
    yield
    # Clean up code
```

### Mock Issues

**Cause:** An `AsyncMock` backend resolves *any* attribute, so a call to a method
that doesn't exist silently "passes" — only integration tests catch that bug class.
**Fix:** Mock the backend, construct real frozen-dataclass domain models, and use
`AsyncMock(return_value=Result.ok(...))`. See the
[@pytest](.claude/skills/pytest/SKILL.md) skill for the full mocking patterns.

## Summary

**For Daily Development:**
```bash
./dev test-integration  # Real Neo4j, primary verification tier
```

**For Comprehensive Verification:**
```bash
./dev test        # unit + integration in one session (needs Docker)
./dev test --cov  # ... with a coverage report
```

**For Specific Features:**
```bash
uv run pytest tests/unit/ -k "<feature>" -v
uv run pytest tests/integration/ -k "<feature>" -v
```

**Priority:** Integration tests are the primary verification tier; unit tests give
fast, Docker-free feedback on pure logic. Both are gated in CI.
