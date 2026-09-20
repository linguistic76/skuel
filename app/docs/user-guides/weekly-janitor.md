---
title: The Weekly Janitor
updated: 2026-09-20
status: current
category: user-guides
tags: [janitor, health-checks, rot, github-actions, weekly, documentation]
related: [HEALTH_CHECKS.md, BLOAT_DETECTION.md, documentation-freshness.md]
---

# The Weekly Janitor

**In one sentence:** every Monday morning a GitHub Action runs SKUEL's rot detectors over `main`
and writes what it found to **one GitHub issue — [#1007 "Weekly janitor: codebase health"](https://github.com/linguistic76/skuel/issues/1007)** — and
nothing else in the system will ever tell you what it found. The janitor's job is to notice
slow decay; yours is to open the issue.

## Why it exists

Some kinds of breakage are never caused by the change that lands: a document's link dies
when the *file it points at* is moved, a Python module goes dead when its *last importer* is
deleted, a code example in a guide goes stale when the identifier it names is renamed
somewhere else. The file that rots is not the file that changed, so the checks that run on
every pull request — which only look at the files in the PR — cannot see it. Rot like this
accrues over weeks, and none of it is urgent. So it is measured on a clock, once a week, over
the whole tree.

Until the janitor existed these detectors ran only when someone remembered to run them. A
rot detector that depends on human memory contradicts its own purpose — hence the schedule,
and hence the issue: a red scheduled run that lands nowhere is indistinguishable from no
check at all.

## What it runs

The seven `./dev health` checks (the roster is read from `./dev health --list` at run time,
so a new check joins automatically), then the full bloat report:

| Section | Asks | Typical finding |
|---|---|---|
| `modules` | Is any Python file imported by nothing? | a service that lost its last caller in a refactor |
| `links` | Does every path a doc or skill cites still exist? | a guide pointing at a file that was renamed months ago |
| `names` | Do doc code examples name identifiers that no longer exist? | an example still calling a method that was renamed |
| `headings` | Does a doc repeat a heading under one parent? | a section pasted twice during a merge |
| `updated` | Has a doc's `updated:` stamp rotted (or gone missing)? | a doc edited without its stamp moving |
| `xref` | Do skills and docs point at each other consistently? | a skill naming a doc that was deleted |
| `secrets` | Has the commit-time secret scan started firing on the repo's own content? | a false-positive floor that moved |
| bloat report | Is any event, method, template or embedding map structurally dead — or registered as planned and now stale? | a PLANNED entry whose subject was deleted |

Each is documented in depth in [HEALTH_CHECKS.md](../tools/HEALTH_CHECKS.md) (the seven) and
[BLOAT_DETECTION.md](../tools/BLOAT_DETECTION.md) (the report). Two sibling instruments run
on the same Monday clock and file their own issues: the composed test run (05:00 UTC,
`composed-test-run.yml`) and the dead-mypy-suppressions audit (06:00 UTC,
`mypy-suppressions.yml`); the janitor is at 06:30.

## Where the result lands, and how to read it

- **The issue is [#1007](https://github.com/linguistic76/skuel/issues/1007).** There is only
  ever one; it stays open by design. The body is the latest report. A **new comment** is posted
  only when the report *changes* — so a quiet week adds nothing, and the comment count is a
  history of how often the picture moved.
- **Red** means: `**Failing sections:** \`links\`` (or whichever) at the top, followed by
  that section's output verbatim — the same text `./dev health-links` prints on your machine.
  Red is not an emergency; it is the list of what to clean.
- **Green** means the body says all checks passed. Nothing to do.
- **"The janitor could not measure"** means the toolchain failed to come up on the runner
  (a transient package-service problem, usually). It makes no claim about the codebase; a
  re-run clears it.
- The **Actions tab → Weekly Janitor** shows each run; the run's `janitor-output` artifact
  holds every section's full output when the issue body had to truncate it.

A red janitor that nobody reads is the exact failure it was built to prevent. From its
first run on 2026-08-08 to 2026-09-14 it ran red every week on `links` — the dead-doc-links
queue held ~280 entries — and the issue had five comments nobody had opened.

## The Monday ritual (two minutes)

1. Open [#1007](https://github.com/linguistic76/skuel/issues/1007).
2. If the newest comment is older than this week, nothing changed — done.
3. If it is new: read which section is named, and either fix it in a ride-along PR (the
   default for `links` and `names` — see below) or decide it is deferred and say so in a
   comment on the issue, so the next reader knows the red is known.

## When it is red: what each section wants

- **`links`** has its own protocol, because not everything it reports is rot: a
  document may deliberately name a deleted file as history, a roadmap may cite a file it
  intends to create, a citation may be pure fiction. **Classify before touching** — the
  report itself is the queue; the sweep record
  [dead-doc-links-sweep-queue.md](../roadmap/done/dead-doc-links-sweep-queue.md) holds
  the cautions, and HEALTH_CHECKS.md § 2 explains the two markers (`<!-- historical -->`
  under `docs/decisions/`, `<!-- planned -->` under live `docs/roadmap/`). Reproduce with
  `./dev health-links`.
- **`modules`**: a zero-importer module is either dead (delete it, One Path Forward) or
  staged work (register it in the bloat detector's PLANNED tier). `./dev health-modules`.
- **`names`**: fix the example, or add a `RENAMED`/`DELETED` entry in `stale_names.py` when the
  old identifier is named on purpose. HEALTH_CHECKS.md § Maintaining `stale_names.py`.
- **`headings`**, **`updated`**, **`xref`**: mechanical — the output names the line.
- **`secrets`**: the scan's false-positive floor moved; HEALTH_CHECKS.md § 8 says how to
  re-pin it.
- **bloat report**: its *findings* never fail the run (the WARNING tier already gates PRs);
  it fails only when the report itself could not be produced.

## Running it yourself

```bash
./dev health              # every section except health-mypy, on your checkout
./dev health-links        # one section
./dev bloat               # the report the janitor attaches
gh workflow run weekly-janitor.yml   # trigger a run on main now; result on #1007 in ~3 min
```

The janitor is advisory: it never blocks a pull request and it is not a required check. The
strict subset that *should* block a merge already does, inside the CI gate.
