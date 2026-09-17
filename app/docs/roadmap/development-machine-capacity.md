---
title: "Development Machine Capacity — what is memory-gated today, and what changes on a bigger machine"
updated: 2026-09-17
status: "deferred"
registered: 2026-09-17
trigger: "a development machine with ≥ 32 GB RAM (the composed test session plus a desktop needs ~12 GB headroom; 32 leaves room for a second container set or a local model), and/or a GPU with ≥ 16 GB VRAM for local inference of the ADR-083 models"
check: "two independent checks, either one opens its rows: `free -g` total ≥ 31 opens the RAM rows; `nvidia-smi --query-gpu=memory.total --format=csv` ≥ 16384 MiB (command absent = no GPU, the row stays closed) opens the local-model row; then re-measure every opened row on the new box before touching its bound"
---

# Development Machine Capacity

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

The machine this app is developed on is a 15 GB laptop with a 2 GB swapfile, and it will be for
the next year to a year and a half. Several bounds in the tree exist because of it. This file
names each bound, where it lives, what it was measured against, and what changes — and what
must not — when the machine does. Nobody should discover a bound by hitting it, and nobody
should lift one by copying a number from this box to the next.

## The host, measured (2026-09-17)

| | |
|---|---|
| CPU | 18 logical cores |
| RAM | 15.2 GiB (`free -g` total 15) |
| Swap | `/swapfile` 2 GiB, **1.4 GiB in use at rest**; `vm.swappiness=60` |
| Resident at rest | Firefox ≈ 2–3 GB across processes, Obsidian ≈ 0.3 GB, the Claude Code process ≈ 0.45 GB; ~9 GB available before any test runs |
| Docker | native daemon (no `daemon.json`, userland proxy on), sees all 15.2 GiB / 18 CPUs; `skuel-prometheus` 35 MB, `skuel-grafana` 48 MB, `skuel-firefly` + `firefly-db` 35 MB are up permanently |
| Claude Code | 2.1.273; its low-memory guard stops **background** commands on transient dips (6× in one session on trivial waiters, 7–10 GB available a minute later) — undocumented, no setting (`settings.json`, env or flag); anthropics/claude-code#92228 shows it reading `MemFree`, not `MemAvailable`; the 2.1.274 changelog says background commands are "now stopped only when memory is critically low". Foreground calls are not stopped; the foreground tool timeout is 600 000 ms |

Whoever changes the machine re-measures this block first; every number below was taken on it.

## What is bounded today, and where the bound lives

| Bound | Where it lives | Measured against | Kind |
|---|---|---|---|
| The unit tier runs on at most **8 xdist workers** | `scripts/run_tests.py` `UNIT_PARALLEL_ARGS` (`--maxprocesses 8`, [lines 79–86](../../scripts/run_tests.py)) | every worker imports the app, ~0.5–0.6 GB resident; 14 workers swapped the box and ran no faster (the tier's floor is its longest module, ~20–35 s) | memory |
| The composed session (`./dev test`) and every mode holding the integration tier are **serial** | `scripts/run_tests.py` module docstring ("run serially, by ruling"); TESTING.md § Parallel Execution | the integration tier's session fixtures are three Neo4j testcontainers plus one app boot, and under xdist a session fixture is built **per worker whose files request it** — with `--dist loadfile` the shared container on nearly every worker (most modules use it), the app container and its boot on every worker that receives an Askesis or route module, the lockdown container once (one file). So N workers cost between N × the shared container (~1.4 GiB busy) and N × the full set, never less than N × 1.4 GiB | memory (and fixture design) |
| Every Neo4j testcontainer's JVM is **sized for the test graphs**: 128m initial / 512m max heap, 128m page cache | `tests/integration/_container_lifecycle.py` `NEO4J_TESTCONTAINER_MEMORY` (lines 47–51), applied by `bounded_neo4j_container()` at all three builders | unsized, the image sizes heap and page cache from the host's RAM: 3124 MiB peak for the three; sized, 2839 MiB (busy container 1402, idle 577 / 860), wall time unchanged. ~0.8 GiB per busy container is JVM/Neo4j **off-heap** that no `NEO4J_server_memory_*` knob reaches (metaspace ~80 MB, GC ~65, code ~28, the native page cache and buffers under load) plus ~0.45 GiB reclaimable file cache | memory |
| Ryuk holds the session's filter, so a killed session's containers are reaped in ~10 s | the same module, `ensure_reaper_registered()` (testcontainers-python#1114 — the library loses the filter to docker-proxy in ~half the sessions, and Ryuk exits at +60 s) | before the handshake, four orphaned containers from two killed sessions held ~6 GB (#1353); `docker ps -a` carried 15 stopped testcontainers from six months, 13 of them `Exited (255)` — still running when the daemon went down | memory (indirectly: orphans) |
| **No `./dev quality` beside a test session** | discipline, not code — TESTING.md § Parallel Execution names it | the gate's processes peak at **1.86 GiB summed, 1.68 GiB in the largest one** (Pyright), for ~80 s; beside 8 unit workers (~4–5 GB) or the container set (~2.8 GiB) the box swaps | memory |
| Waits on remote work are **bounded foreground calls** (`request_codex_review.sh <PR#> 540`, then `--resume`) | `docs/development/PR_WORKFLOW.md` step 5, `AGENTS.md`, `scripts/request_codex_review.sh` | the harness guard above; a killed background wait loses the poll | harness |
| The SKUEL linter sweep runs on at most **12 workers** | `scripts/lint_skuel.py` `PARALLEL_MAX_WORKERS` (line 1539) | 8 → 1.14 s, 12 → 0.91 s, 16 → 0.95 s on the full tree — a **CPU** knee on 18 cores, ~40 MB per worker; not a memory bound and not lifted by RAM | CPU |
| The monitoring stack (`./dev up-monitoring`: Prometheus + Grafana + the sandbox Neo4j) and the local Neo4j sandbox are **not run beside a test session** | discipline — the sandbox's own JVM is *configured* for 1 G / 1.5 G heap + 2 G page cache (`.env` `NEO4J_HEAP_*` / `NEO4J_PAGECACHE`, `../infrastructure/docker-compose.yml` lines 52–56), ~3.5 GB by configuration; not measured, it is stopped | the sandbox is an opt-in, stopped by default (CLAUDE.md § Neo4j Infrastructure); the two monitoring containers are ~80 MB and are up now | memory (the sandbox) |
| **Local inference of the ADR-083 models is not runnable here** — BGE-M3 (568 M params: ~1.1 GB of fp16 weights, ~2.3 GB fp32) and a Qwen chat model (7 B: ~15 GB fp16, ~4–5 GB at 4-bit) beside the test infrastructure | nothing in the tree — serving is **hosted initially** (BGE-M3 via the HuggingFace Inference API, Qwen behind a vLLM / DashScope / Together endpoint: ADR-083 § 4 — "the droplet has no GPU, so serving is hosted initially"; the endpoint is chosen at Arc 2's start, and later self-hosting is not ruled out — that would be a production-host decision, not this laptop's) | this row gates only a *local* experiment — the fine-tuning work ADR-081/083 name as Arc 2's trigger, or offline development against the real models. It does **not** gate the cut-over, and it is not why the app is on OpenAI embeddings: ADR-068's "now" is that the key and SDK were already FULL-tier requirements and the BGE data migration had never run | memory / VRAM |
| Neo4j Graph Data Science (GDS / AuraDS) is deferred | ADR-080 (three-horizon strategy) | **density-gated, not memory-gated** — it waits on graph size and a Digital-layer need, and would run on AuraDS, not on this machine. Listed so nobody moves it here by mistake | not this file's |

Not a bound, but the number that sets the ceiling: the composed session's peak is **~2.8 GiB of
containers + the pytest process (0.35 GB measured with the app booted on a three-module run; the
full tier imports every module and sits higher) + the desktop (~3–4 GB)** on a 15 GB box — the
guard's dips come from the desktop, not the tests.

## What changes on the larger machine, and how

Per row: the edit, the measurement that must be re-taken **on the new box** first, and what must
not change. A battery number never travels; a ceiling never becomes host-derived.

| Row | The edit | Re-measure first | Must NOT change |
|---|---|---|---|
| 8 unit workers | one number: `--maxprocesses` in `UNIT_PARALLEL_ARGS` | wall time and peak RSS of `./dev test-unit` at 8 / 12 / 16 / `logical` workers on the new box; the floor is the longest module, so past the knee more workers buy nothing — stop where the curve flattens, not where memory allows | the cap stays a **number in the file**, never `logical` uncapped (a 4-vCPU runner and a 64-core box must both run the tier) |
| serial composed session | `comprehensive` / `integration` / `quick` gaining `-n N --dist loadfile` | the per-worker fixture mix, not a multiple: run the tier at N = 2 and 4 with `docker stats` sampled and count the containers that actually come up (the shared one per worker, the app one on the workers that received Askesis/route files, the lockdown once) — then the peak; and whether the integration modules are xdist-safe (a fixed port, a shared vault path, module state) — the **test-design** question the memory question hides behind | `loadfile` distribution (module-scoped fixtures); a worker still builds the fixtures its files request — sharing one container across workers is a different design, not a knob |
| JVM caps | `NEO4J_TESTCONTAINER_MEMORY` — raise max heap / page cache only if a test needs it (none did at 512m / 128m); the initial heap stays small regardless of RAM (`AlwaysPreTouch` commits it at boot, three times over) | `docker stats` every 5 s across a full `./dev test-integration` on the new box (the sampler and summariser from #1361 are the shape); the busy container's cgroup `anon` vs `file` | the caps stay a **code-side ceiling** — a bigger machine is not a licence to size from the host again (that is the unsized shape this file exists to prevent); a cgroup `mem_limit` is the lever if the off-heap remainder must be bounded too, at the price of OOM-kills presenting as test failures |
| Ryuk handshake | none — it is not a capacity bound; delete it when testcontainers-python#1114 closes upstream | — | the ACK read; a reaper that is configured is not a reaper that works |
| no quality beside tests | the discipline can lapse at ≥ 32 GB (`./dev quality` ~1.9 GiB + a unit session ~4–5 GB + the desktop) | peak RSS of `./dev quality` on the new box (Pyright's is the larger) | — |
| bounded foreground waits | none — the guard is the harness's, not the machine's, and a killed wait losing its poll is true at any RAM; `--resume` stays the path | whether the guard fires at all on the new box (it reads `MemFree`; a machine that never dips below the threshold never trips it) | the script's invariants (never label without a read verdict; every counted channel printed) |
| 12 linter workers | a CPU knee — re-measure on a machine with more **cores**, not more RAM | the 8 / 12 / 16 / 24 curve on the full tree | `PARALLEL_MIN_FILES` (a pre-commit-sized selection stays serial) |
| monitoring + sandbox | at ≥ 32 GB the sandbox Neo4j can stay up beside a test session | the sandbox's real RSS (`docker stats skuel-neo4j`) — its `.env` sizing is for the app's own graph, not for tests | the sandbox stays an opt-in; AuraDB Free stays the daily graph (ADR-080) |
| local ADR-083 models | a GPU with ≥ 16 GB VRAM makes local BGE-M3 and a 4-bit 7B Qwen runnable for experiments — the production serving topology is ADR-083's to choose (hosted initially; self-hosting later is a droplet question, not this one), and Arc 2 stays trigger-gated on a concrete reason to chat with Qwen | the models' actual VRAM at the chosen quantisation; the laptop's number is a datasheet estimate | ADR-083 § 3's design rules; `create_embedding_client()` as the one provider chokepoint (ADR-068); `EmbeddingGeometry.DIMENSION` |
| GDS | nothing here — density-gated | — | — |

## The rulings this file carries

- **A ceiling is code-side, always.** Every memory bound above is a number in a file or a
  documented discipline, never a value read from the host. The unsized testcontainers were the
  host-derived shape, and they cost 3.1 GiB and a reaper race nobody saw.
- **A larger machine re-measures before it re-tunes.** The `Re-measure first` column is not
  advice; a number carried from this box to the next is the kind of "measured" that isn't.
- **The corrections to what was assumed when this arc was planned** (the tree wins): ADR-083
  serves its models hosted, initially, and nothing in it waits on this machine; ADR-068's "OpenAI now" is not a
  memory decision; the linter's 12-worker knee is CPU, not memory; the tier runs three Neo4j
  containers, not two.

## Related

- [ADR-080 — AuraDB three-horizon strategy](../decisions/ADR-080-auradb-three-horizon-strategy.md) (GDS deferred, density-gated)
- [ADR-083 — Qwen + BGE end-state](../decisions/ADR-083-qwen-bge-end-state-commitment.md) (hosted initially; Arc 2 trigger-gated)
- [ADR-068 — OpenAI embeddings now, BGE later](../decisions/ADR-068-openai-embeddings-now-bge-later.md)
- [BGE embeddings migration](bge-embeddings-migration.md) (Arc 3 — the cut-over runbook, independent of this file's trigger)
- `TESTING.md` § Parallel Execution (the tiers' shapes and the serial ruling); `docs/development/PR_WORKFLOW.md` step 5 (the bounded foreground wait)
