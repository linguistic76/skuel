---
title: History-in-Code Finder
updated: 2026-09-04
status: current
category: tools
tags: [docstrings, comments, signal, maintenance, advisory]
related: [BLOAT_DETECTION.md, HEALTH_CHECKS.md]
---

# History-in-Code Finder

**Status:** ✅ Active — advisory by contract, never a gate
**Location:** `scripts/history_in_code.py`
**Tests:** `tests/unit/scripts/test_history_in_code.py`
**Run:** `./dev history-in-code [--top N] [--verbose] [--json] [PATH ...]`

## What it measures

The rule stands once: a comment or docstring states what the code does now; what it
used to do, which PR changed it and when belong to the commit message and the ADR or
`done/` doc, and a comment may point at the record but never retell it (CLAUDE.md
§ Docstring Philosophy · `DOCSTRING_STANDARDS.md` Anti-Pattern 4 · AGENTS.md § Style).
This finder counts the prose lines that still retell, per file, and orders the files
so the sweep (`docs/roadmap/deferred-work.md` § History-in-Code Sweep) takes the heaviest
first. It is a census that orders a queue — not a rule that fails a build.

```bash
./dev history-in-code                        # per-file table over the default scope, most hits first
./dev history-in-code --top 20 --verbose     # the sweep queue, every hit listed under its file
./dev history-in-code --json > hits.json     # machine-readable; the status line goes to stderr
./dev history-in-code core/services/tasks    # any files or directories
```

## What it reads — and only this

- **Comments**, as `COMMENT` tokens from `tokenize`.
- **Docstrings** of modules, classes and functions, from `ast.get_docstring` uncleaned,
  so every docstring line reports its real source line.

String literals, f-strings and log messages are never read. A date in DSL example data,
a month name in a fixture, a PR number in a user-facing message are not prose about the
code, and reading prose alone is what makes the census tighter than a grep over the same
trees.

**Default scope:** `core/ adapters/ ui/ services_bootstrap/`. Tests are out — they carry
rationale legitimately; `scripts/` is out — it is CLI prose. Any path argument overrides
the scope.

## Signals

A line is counted once per category it carries; its `dominant` category is the first in
this order.

| Category | Matches | Example |
|----------|---------|---------|
| `pr_tag` | an arc-internal tag: `PR-3`, `(PR #1241` | `(ADR-087 PR-4) gave this site …` |
| `pr_ref` | a bare PR number, 3–4 digits, not inside a path or a word | `… (Codex #608).` |
| `date` | `2026-08` or `2026-08-06` | `SHELVED (2026-03-28)` |
| `phrase` | used to · no longer · formerly · previously · was/were deleted · was/were removed · stopped ‹verb›ing · fixed/since/until 20xx | `It used to hold module-name strings` |

`ADR-074` is not a signal — a pointer at the record is the sanctioned form.

## Not flagged, by design

- **A pointer line** — `See:` or `Backend:` opening the comment or the docstring line —
  whatever date or number the record's title carries.
- **`ADR-NNN` and `done/….md` citations**: they contain no signal token.
- **The "utilized" idiom and the runtime sense**, ruled out by grammar inside the `phrase`
  net: `Used to weight …` (sentence-initial) and `can be used to probe` carry no history,
  so `used to` counts only in lowercase and not after a form of *be*;
  `previously-recorded` is a compound adjective about state, so `previously` counts only
  unhyphenated.

## Known false positives — reported on purpose

- A docstring that documents a **real date-typed field or a date format**
  (`completion_date: YYYY-MM-DD, e.g. 2026-08-06`), and DSL example timestamps
  (`core/services/dsl/activity_dsl_parser.py` is the exemplar — most of its `date` hits
  are `@when(2025-11-27T09:30)` examples, a few are real history).
- The lowercase `used to` mid-sentence in the utilized sense (`the metrics used to curate
  the units`), and `no longer` / `was removed` about an entity at runtime rather than
  about the code (`True when an attendance was removed`).

These are listed, not special-cased. **There is no exemption syntax** — one becomes a
suppression ritual, and the sweep reads every hit anyway; a false positive costs the
reader one glance. A category that measured mostly false positives would be dropped,
not annotated.

## Why it is not a gate

The signal-over-noise arc's anti-goal: a prose lint is itself noise, and it is flow-blind
— it cannot tell a retelling from the one sentence of reason that still holds. So the
finder has the status of `./dev bloat`'s advisory tiers: printed, never demanded. It is
not in `./dev quality`, not in pre-commit, not in `./dev health`, not in the weekly
janitor. **Exit 0 whatever it finds**; the one non-zero exit is argparse's usage error
for an unknown flag or a path that does not exist — a typo'd path must not read as
"no history here".

New occurrences are a review matter, not a gate: AGENTS.md § Style asks the reviewer to
flag a docstring or comment that narrates.

## Reading the output

```text
 hits  /100  pr_tag  pr_ref    date  phrase  file
   20   1.9       0       9       4       9  core/services/tasks/tasks_core_service.py
```

- `hits` — prose lines carrying at least one signal, **the ordering key**; `/100` — hits
  per 100 source lines, the tiebreak (then path). A `--top N` cut of this order **is** the
  sweep queue. Hits order it rather than density because a file a reader meets history in
  twenty times is one PR-sized slice, while density alone front-loads one-line files.
- The category columns count lines carrying that category, so they can sum past `hits`.
- `--verbose` lists every hit as `L<line> <kind> [categories] <text>` under its file.
- `--json` emits `{advisory, scope, files_scanned, files_with_hits, total_hits,
  by_category, skipped, files: [{path, source_lines, hits, density, by_category, lines:
  [{lineno, kind, dominant, categories, text}]}]}` — files ranked and truncated as the
  table is; `skipped` names any file Python could not parse, never silently dropped.

Re-measure, never cite a snapshot: the numbers in a PR body or a deferred-work cell are
the count on that day, and the next merge moves them.

## The sweep

`docs/roadmap/deferred-work.md` § History-in-Code Sweep holds the queue's protocol: one
file or one coherent cluster per PR; each rewrite is the positive in present tense plus a
pointer to the record; the why is never deleted, only moved — to the ADR, the `done/` doc
or the commit message.
