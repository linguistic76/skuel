---
title: "Docs updated: Frontmatter — Auto-Stamp"
updated: 2026-09-05
status: "shipped"
registered: 2026-08-29
ruled: 2026-09-01
trigger: "none — built 2026-09-01; kept for the settled forks and permanent rules"
check: "./dev health-updated green"
---

# Docs `updated:` Frontmatter — Auto-Stamp

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

**Built.** The field is now written by machine and checked by machine. Three pieces,
one shared module (`scripts/docs_updated_field.py`) so none is a catalog copy of the
others:

| Piece | Where | Runs |
|---|---|---|
| Stamper | `scripts/stamp_docs_updated.py` | pre-commit check 0 (`SKUEL_SKIP_DOC_STAMP=1` bypasses) |
| Backfill | `scripts/backfill_docs_updated.py` | once, 2026-09-01 |
| Guard | `scripts/health/docs_updated.py` | `./dev health-updated`, `./dev health`, weekly janitor |

**Result:** 412 of 412 green, in 2.6s. Before the backfill, 373 were wrong — 193 with
no `updated:` at all, 180 lagging their last substantive commit by over a week (33 by
over six months). The design and its reasoning live in
[`docs/tools/HEALTH_CHECKS.md` § 7](../tools/HEALTH_CHECKS.md) and the scripts'
docstrings; **this section deliberately does not restate them** — the sixteen traps
registered here were found by ten review rounds of *this prose*, four of them being
this document contradicting itself, and a stamp that is mechanically written is the
only form that cannot rot into a paraphrase. What follows is only what a future
session must not re-decide.

**Forks, as settled:**

- **Guard comparison = rot threshold, 7 days** (option (a), Mike 2026-09-01). Not
  merge-side stamping (b). ~~(c) drop the date comparison~~ **stays rejected**: on a
  doc stamped once whose hook then stops running, the old value remains present,
  unique, parseable and non-future forever — so the four structural checks pass on
  exactly the rot the guard exists to catch. Recorded rather than deleted so it is not
  re-proposed as "the simple option".
- **Backfill preserved pre-stamp history** (option (i)). Each file got its own last
  *substantive* commit date; the fall-back to a uniform backfill date was not needed.
- **Scope is `app/docs/**/*.md`.** Skills excluded — `SKILL.md` already carries
  `last_updated` and the cross-reference validator reads a human-set `last_reviewed`; a
  third date key would be a duplicated fact, and auto-stamping a *review* date destroys
  its meaning. Root `AGENTS.md`/`CLAUDE.md` excluded — always-loaded instruction files
  read in full, not sampled for freshness. `roadmap/done/` and pinned archives are
  **not** exempt: an unedited doc's stamp already matches its last substantive commit,
  so the guard is free on them and an exemption would only open a hole. **Machine-generated
  docs ARE excluded** — detected by their own `AUTO-GENERATED` banner, not a path list —
  because a generator's drift test is a stronger freshness guarantee than a date and a
  stamp breaks its byte-comparison.

**Permanent rules the guard carries:**

- **Stamp-only commits are excluded from "last substantive commit"** — stated as a rule,
  never a hardcoded SHA, so any future stamp-only commit gets the same treatment. A
  commit qualifies only if it actually changes an `updated:` line; fences and the blank
  separator are permitted alongside it because *creating* a block emits them, but on
  their own they are not a stamp change (a commit deleting two blank lines qualified
  under the looser rule and dated three docs from the wrong commit).
- ⛔ **Never cite `updated:` as staleness evidence outside the guard.** After shipping it
  is evidence *only within the 7-day rot window, and only because the guard runs*. It is
  never evidence of whether a doc's content is correct.
- ⛔ **No same-file contradictory-prose detector** — measured unmechanizable, 4/4 false
  positives. See the sub-finding below.

**Traps that survived into the build.** None was visible to a fixture; each was found by
running against the real corpus, by the full test suite, or by review, and each looks like
a simplification. **This is not the whole list** — Codex found twelve defects across ten
review rounds of the *implementation*, on top of the sixteen it found in ten rounds of the
registration, and every one of them is recorded in a docstring beside the code it
constrains, which is where a constraint cannot rot into a paraphrase. Carried here are the
ones a future session would most plausibly reintroduce while scoping:

- **Never `yaml.safe_load` the frontmatter to read this field.** 35 of 412 docs carried an
  unquoted `title: ADR-013: KU UID Flat Identity Design`, whose colon-space is a YAML
  syntax error — while their `updated:` line is perfectly well-formed. A YAML-parsing
  guard sits red on every such doc for a `title:` defect it does not own. (The titles were
  quoted 2026-09-04 by `scripts/quote_frontmatter_titles.py`, whose check mode is the
  corpus-wide "every block parses" probe; the rule stands because a new doc with the same
  title shape reintroduces the failure.)
- **Do not attribute `git show` hunks to files by parsing `+++ b/<path>`.** Git appends a
  TAB to that header for paths containing spaces, and three docs under
  `design-principles/` have them. Pass the path as a pathspec instead.
- ⚠️ **Never compute a file line number by adding an offset to a position inside the
  parsed frontmatter.** `split_frontmatter`'s opening fence is `^---\s*\n`, and `\s*`
  swallows a blank line after the `---` — so the raw block can begin on file line 2 while
  "raw index + 1" assumes line 1. Stamping then overwrote `title:` and left the real
  `updated:` below it: metadata deleted, duplicate key created, silently. Scan the file's
  own lines between the fences; `split_frontmatter` decides *whether* there is a block,
  not *where* its lines are. (Codex P1 on #1212 — the most destructive defect in the arc.)
- **Diff text cannot decide "touches only the stamp" — normalise the blobs instead.** Two
  formulations failed in sequence. *"Every changed line is a fence or a blank"* classified
  a commit that merely deleted two blank lines as stamp-only, dating three pattern docs
  from the commit before it. Adding *"and at least one changed line is `^updated:`"* still
  could not tell **where** that line sat — and two docs carry a documentation *example* of
  an `updated:` line in their body, so a commit editing only that example counted as
  stamp-only and the real edit stayed invisible to the guard indefinitely (Codex P2 on
  #1212). Stamping both blobs to the same date and comparing is positional by
  construction, because `apply_stamp` writes only the leading block.
- **A generated doc must not be stamped.** A date written into generated content
  describes nothing — the next regeneration overwrites it and the guard then reports a
  correctly regenerated file as missing its key — and where the artifact is drift-tested a
  frontmatter block reds that test immediately. ⚠️ The exemption does **not** assert that
  every excluded artifact is drift-tested — the argument for excluding it stands either
  way. (`CROSS_REFERENCE_INDEX.md` had no such test when this was recorded; closed by
  `tests/unit/scripts/test_generate_cross_reference_index.py`.) Detected by the file's own
  declaration — *"this file is auto-generated"*, matched as a self-assertion rather than
  the bare phrase, header-scoped — never a list of generated paths. The loose form has to
  be avoided in that exact direction: a hand-maintained doc wrongly matched is dropped
  from the guard permanently and *silently*, whereas a generated doc missing its banner
  fails loudly on its own drift test. The excluded paths are named on every run.
- **A writer must not treat malformed frontmatter as absent frontmatter.**
  `split_frontmatter` reports "no frontmatter" for a `---` fence that never closes — the
  right answer for a reader, a dangerous one for a writer: stamping prepends a second,
  valid block and the author's `title:`/`status:`/`related_skills:` become body text,
  present in the file and invisible to every parser. The stamper refuses and names the
  file; the guard reports `malformed` as its own verdict. Nothing in the corpus is
  malformed today; one mistyped fence is all it takes. (Codex P2 on #1212.)
- **A history-reading check must refuse a shallow clone, not measure it.**
  `actions/checkout` fetches one commit by default, and the weekly janitor's checkout had
  no `fetch-depth` — the guard reported 343 of 410 docs stale in a depth-1 clone, and at a
  HEAD touching no docs it would have reported a clean green having checked nothing. Fixed
  at the site (`fetch-depth: 0`) *and* in the check, which now exits 2 rather than publish
  either number — an audit that could not measure must never read as a passing week, the
  rule the janitor already applies to its bloat report. (Codex P2 on #1212.)
- **Creating a frontmatter block shifts every line number below it**, which invalidates
  any registry anchored by `(file, line)`. `stale_names.ALLOWED_OCCURRENCES` is exactly
  that, and the backfill left 72 of its anchors hitting nothing — so the exemptions
  stopped exempting and `./dev health-names` reported 72 phantom stale references. Found
  by the full unit suite, not by the backfill's own verification, which checked its
  writes but not what downstream depended on their line numbers. **Any future bulk edit
  that inserts at the top of docs must re-anchor that dict** (re-anchor by the file's
  measured line-count delta, not by a guessed constant — the delta here was 4, 1 or 0
  depending on whether the block was created, a key was inserted, or the key was
  rewritten in place).


## Sub-finding: same-file contradictory ruling prose is NOT mechanizable

Registered so it is not attempted again. The three sites cleaned up in #1182/#1183 shared a
shape — a ruling PR corrected one mention and left a contradicting one **in the same file**
(`search_request.py` 816 fixed / 895 stale; `SEARCH_MODELS.md` prose fixed / code block
stale; #1169's frontmatter vs its own body). The obvious detector does not work: scanning
for one `#NNN` cited twice in a file with both defer-family and settled-family words nearby
yields 28 pairs across 18 files, and **4 of 4 spot-checks were false positives** —
`INDEX.md` #978 (two correct rows), `deferred-work.md` #215 ("PR #215 dropped X" inside a
*different* item's "Why deferred"), `ingestion_tracker.py` #618 (Codex round citations),
and the deliberate "was deferred, now dropped" history in
`feedback-loop-staged-directions.md` § 4. History sections legitimately carry both
dispositions, so the check would flag correct prose as loudly as real drift.

Stays a **process discipline**, already recorded twice as a lesson: enumerate every site
before fixing any, and treat every summary as a duplicated fact. The one narrowing worth
carrying: when a ruling changes a fact, **re-grep the file you just edited** — in all three
cases the stale twin was in the same file as the fix. The post-commit docs hook covers the
*other* direction (docs referencing a changed module) and demonstrably works: it caught two
of the four sites unprompted during #1183.
