---
title: "Dead-Doc-Links Instrument — Rulings + Scheduled Work"
updated: 2026-09-05
status: "arc complete — residue queued"
registered: 2026-09-01
ruled: 2026-09-01
trigger: "duplicate ADR renumbering: Mike decides; the live-docs residue rides doc sweeps via the queue doc"
check: "uv run python scripts/health/dead_doc_links.py — every finding is the live-docs sweep queue"
---

# Dead-Doc-Links Instrument — Rulings + Scheduled Work

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

`scripts/health/dead_doc_links.py` (in `./dev health` + the weekly janitor; not a CI gate)
sat red at **871 findings / 531 distinct missing targets** before PR B1 (measured
2026-09-01 on `eb6aad6af`, confirmed identical by the classification pass on `e2e5b7f4a`).
An always-on check reporting 871 findings is one nobody reads. **PR B1 landed the
approved false-positive removals: 871 → 754 / 456 distinct**, **PR B2 the generated
index: 754 → 724 / 447 distinct**, and **PR B3 the history line: 724 → 497 / 314
distinct** (each measured on its branch by driving `check_file()` over
`get_md_files()`). Re-derive the same way — never trust these counts as current.
The rows below SUM to the current total: the parser, carve-out, generated-index and
history-dir classes are gone, and the route-shaped class is no longer scattered across
the others.

| Class | Findings (now) | Disposition |
|---|---|---|
| ~~Parser false positives~~ (subscript-as-link ×24, globs in the bare pass ×7, ` + ` joins ×9, un-decoded `%20`) | 0 (−40) | **DONE — PR B1.** Re-measured on the branch: 24 subscripts (not 30 — six of that count were the `%20` links, kept checkable), 9 joins (not 10). The `%20` fix resolves a citation to a REAL file rather than removing a line, so its effect lands inside the freeform carve-out |
| ~~Route-shaped targets~~ — application URLs read as filesystem paths | 0 · 6 still red | **DONE — PR B1.** Matched by AST against the live `@rt("…")` registrations in `adapters/inbound/`, never by shape and never by a URL list; skips are counted and printed. ⚠️ Unmatched stays RED by design: `/journals/browse` ×3 (deleted in #420 — the stale `user_entry_ui.py` docstring claiming otherwise was fixed in B1), `/yaml_templates/_schemas/` ×2 (neither route nor directory), and `/tasks` ×1 (live, but registered as `@rt(f"/{domain}")`, which no static pass resolves — fail toward reporting). All 6 join the sweep queue |
| ~~The two freeform design-principles files~~ + `.claude/skills/_templates/` | 0 (−50) | **DONE — PR B1** carve-outs, 5 files, count printed every run. ⚠️ FILE-scoped, not the directory: `design-principles/HUB_PAGES.md` cites a teaching-hub view module that no longer exists, and that finding is still reported — verify it still is, before ever widening this to a directory. (The path is named in prose there rather than backticked here: a backticked dead path in this doc is itself a finding.) |
| ~~Generated `CROSS_REFERENCE_INDEX.md`~~ (slug-less ADR links) | 0 (−30) | **DONE — PR B2.** One resolver (`scripts/adr_links.py`) now serves both `related_adrs` readers; the duplicate numbers are refused, never guessed. All 13 of the artifact's distinct `docs/decisions/` link targets exist (12 were dead). ⚠️ Corpus-wide distinct fell 9, not 12: `.claude/skills/docs-skills-evolution/SKILL.md` still cites three of those targets by hand, and those stay in the sweep queue — a generated-artifact fix reaches only the artifact |
| ~~History dirs~~ (`migrations/` 198, `roadmap/done/` 12, `investigations/` 12, `Reviews/` 4) | 0 (−226) | **DONE — PR B3.** Silent dir carve-out, 73 files, counted and printed on its own line (not folded into the freeform count: that set is meant to stay fixed while this one grows with every completed roadmap doc, so one merged number would be a number nobody can read). ⚠️ `roadmap/done/` and never `roadmap/` — the live half's 14 findings are ordinary rot on the sweep queue |
| ~~`docs/decisions/ADR-TEMPLATE.md`~~ | 0 (−1) | **DONE — PR B3.** Joined the template carve-out: its one finding sits in the `**Example:**` block illustrating what a Decision section looks like, naming a module never tracked in this repo (`git log --all` empty). Fictional by design, same species as `.claude/skills/_templates/`. FILE-scoped — `docs/decisions/` is the authority tier and a directory carve-out to reach one template would hide the rot below |
| ~~ADRs~~ (`docs/decisions/`, mixed faithful history and standing contracts) | 0 (−153) | **DONE — PR B4** applied the ruled mechanism: 62 markers on narrative citations, every standing contract fixed against a reproduced successor, and the four content rulings executed. Steady state: a finding here now means rot in the authority tier |
| Live docs — real rot | 280 | **RULED** — actionable, and **extracted 2026-09-01** to [`dead-doc-links-sweep-queue.md`](dead-doc-links-sweep-queue.md), which owns the queue from here. Dropped 1 in B4 (`docs/domains/README.md`'s Submissions row, the catalog ripple of the UserEntry doc) and 13 in B5, which were never rot at all — documentation stand-ins two of the four passes reported anyway |

**PR B1 (LANDED):** 871 → **754** (−117: 40 parser, 50 carve-out, 27 route-matched),
every removed finding classified and zero findings added. Four narrowings, each stating
the shape it targets and pinned in `tests/unit/scripts/test_dead_doc_links.py`:

- **Link destinations** get a shape guard (the pass had none). A RAW space is the
  discriminator — CommonMark-grounded, since an unescaped space cannot appear in a link
  destination at all. ⚠️ **A comma is deliberately NOT a rejection signal**: the arc's
  first sketch rejected commas, which would have declared the six correctly-`%20`-encoded
  vault links uncheckable — one of which names a REAL file.
- **`resolve_path` unquotes** the anchor-stripped target, so a `%20`-encoded citation of a
  real space-bearing file resolves. Corner: a literal `%20` in a filename would
  false-negative — measured zero (`git ls-files | grep %`).
- **The bare pass** consults the shared `TEMPLATE_MARKERS` predicate (globs, `{domain}`).
- **`_looks_like_local_path` rejects the two-path join** ` + `. ⚠️ **NOT spaces
  wholesale** — that would lose the live dead FastHTML Best Practices citation in
  `docs/patterns/FASTHTML_TYPE_HINTS_GUIDE.md` (spelled out in the test, not here: a
  backticked dead path in this doc is itself a finding) and undo the quoted-fence
  handling that keeps space-bearing filenames whole (Codex, PR #872). Pinned in both
  directions.

Carve-outs are scope exclusions with per-entry reasons and a printed file count
(`duplicate_headings.py` shape), plus a test that every entry still exists — a carve-out
naming a deleted file is a silent no-op. The route mechanism reads the live catalog by
AST from `adapters/inbound/` (docstring `@rt("…")` examples are invisible to a walk, and
would not be to a grep) and matches exact literal paths only; a repo-rooted target
(`/docs/…`, `/core/…`) is never route-matched. Both skip counts print on **every** run,
zero included — a silent zero is how a rotted carve-out looks like a clean scan. The
printed route-skip count tracks the corpus rather than the −117 accounting above, so it
moves whenever a doc gains or drops a route citation (this section's own pair pushed it
to 28 on the merge commit) — it is an observation, not an invariant.

**PR B2 (LANDED):** 754 → **724** (−30), every removed finding in the one generated
file, zero added. The generator linked ADRs as bare `ADR-NNN.md` under `docs/decisions/`
while every real ADR carries a slug. Both `related_adrs` readers now share one resolver,
`scripts/adr_links.py` (they remain the only two consumers of the field):

- **A bare number resolves by glob; zero or several matches raise, naming every
  candidate.** Loud failure is the ruling — the resolver will not choose. Driven on the
  real tree, not a fixture: a bare `ADR-030` restored into the metadata aborts the
  generator *before it writes* and reddens `validate_cross_references.py` with the same
  message and exit 1.
- **The grammar is anchored at BOTH ends** (Codex P2). Anchored only at the start, the
  number pattern read `ADR-050-typo` / `ADR-050junk` / `ADR-050.md.bak` as the number
  050 and silently resolved each to the real ADR-050 — a malformed ref linked to a
  decision nobody named it after, inside the resolver built to never pick silently. One
  grammar gate now serves every entry point, so a ref outside the two documented forms
  never reaches a glob, a file check or a display label; it also subsumes the separate
  path-separator guard, since rejecting the shape covers every spelling of the mistake
  at once.
- **A ref ending `.md` is a full filename** (verified to exist, and rejected if it
  carries a path separator). Both scripts previously appended a second `.md` to such a
  ref, so the escape hatch from the slug bug was itself broken.
- **The collision unblock** rides along, promoting intent already recorded in YAML
  comments: vis-network + neo4j-cypher-patterns `ADR-037` and user-context-intelligence
  `ADR-030` now name their files outright. The YAML header states the grammar so the
  next author meets the rule, not the traceback.
- **The validator's `adr_map` is gone.** It resolved duplicates last-write-wins over
  `Path.glob`, which yields *directory* order — so which ADR a ref meant could change
  when an unrelated ADR was added. It happened to pick correctly here; that was luck,
  not correctness, and it is now a reported error rather than a silent pick.
- **Display text stays the short `ADR-NNN`**; only the target gained the slug. The
  "By Document Category" section is keyed by the RESOLVED filename, so one ADR spelled
  two ways renders one row rather than two.
- **The honesty guard that would have caught this at birth** is in the generator's own
  tests: every rendered `/docs/decisions/` link target exists. Scoped to the one path
  the generator *constructs* — every other link is a metadata string passed through, and
  a dead one there is the validator's report, not this guard's.
  A drift test only proves the artifact matches the generator; it cannot prove either is
  right, which is exactly how 30 dead links sat inside a *generated* file.

**PR B3 (LANDED):** 724 → **497** (−227: 226 history-dir + 1 ADR-TEMPLATE), every
removed finding classified by source directory and zero added. The ruled history-line
mechanism, both halves:

- **The silent dir carve-out** extends B1's machinery rather than opening a second one
  — one `_carve_out_class()` predicate, one loop, per-class counts. ⚠️ **"Silent" names
  the absence of a tripwire, not the absence of a count.** The two classes print
  separately because they carve out for different reasons and move for unrelated
  causes; a stale-registration test now also asserts every carve-out directory is real
  AND inside the scanned tree, since a carve-out for a directory the checker never
  visits is the same silent no-op as one naming a deleted path. Directory matching is
  anchored at a path separator — `docs/migrations` must not swallow a
  `docs/migrations-v2/`, the same anchoring lesson B2 learned from `ADR-050-typo`.
- **The marker is `<!-- historical -->`**, matched as the WHOLE comment. The comment
  delimiters are the anchors, so a payload (`<!-- historical: see ADR-054 -->`), a
  different case, or prose that merely starts the same way is **not** a marker and its
  citation stays red — a predicate accepting a superset of its grammar would quietly
  swallow ADR prose that was never a marker. Zero HTML comments existed anywhere in
  `docs/decisions/` when the syntax was chosen, so it collides with nothing.
- **A marker inside backticks or anywhere in a fence — delimiter lines included — is
  prose ABOUT the marker**, not an annotation. Documenting this checker requires
  writing the shape it hunts, and this PR's own four occurrences (one here, three in
  `HEALTH_CHECKS.md`, one of those inside a sample output block) each reported as a
  marker-suppressing-nothing until the rule existed —
  caught by re-measuring AFTER the prose edits, which is why that step is in the arc's
  discipline. `stale_names.py` meets the same problem and answers it with a file skip
  list; a code-span rule needs no registry and generalises to the next doc that names
  the marker. A corpus test now asserts no doc in the tree carries a marker that
  suppresses nothing. ⚠️ The exclusion takes each fence's whole **span**, not the
  content-line projection: a marker in an INFO STRING sits on the opener, which is not
  a content line, and the prose passes DO read that line — so it could have suppressed
  a citation sharing the info string (Codex on this PR; `FenceBlock` carries `span`
  for exactly this, and zero findings sit on a delimiter line today).
- **It is honored ONLY under `docs/decisions/`**, and that scope needs no second
  mechanism to enforce: one rule ("a marker that suppressed nothing is reported")
  evaluated corpus-wide catches a marker copied into a live doc, with the reason
  carried on the row. A stale marker reddens the run on its own — a finding that does
  not fail the run is not a finding.
- **Line-scoped, which in this corpus is per-citation:** 153 of the 154 `decisions/`
  findings are alone on their line, and the single two-finding line (ADR-070:255,
  naming two deleted scripts) is homogeneous. ⚠️ B4: a line mixing a narrative citation
  with a standing-contract one must be SPLIT before marking — one marker silences both.
- **Driven on the live tree, not only fixtures** (four probes, reverted): a marked dead
  ADR citation is skipped and counted; a marked LIVE one is reported; a marker outside
  `decisions/` is reported with the scope reason; two near-miss spellings left their
  citations red.
- **`ADR-TEMPLATE.md` joined the template carve-out** as a FILE, with the reason
  recorded beside the entry — see its row above.

Steady state: red inside `decisions/` now means rot in the authority tier.

**PR B4 (LANDED):** 497 → **343** (−154: all 153 `docs/decisions/` findings plus the one
catalog ripple), zero findings added — the ADR content sweep, working from the
classification pass's verified worksheet. **62 markers** print on every run; **0 stale**.
The 153 split into 62 marked narrative citations and 91 edits.

- **The worksheet was a hypothesis, not an answer.** Reproducing each successor against the
  live tree overturned four of its verdicts: ADR-003's `JournalContext`/`JournalAIInsights`
  were *renamed* (`EnrichmentContext`/`EnrichmentInsights` in
  `core/services/content_enrichment/types.py`), not deleted-without-successor;
  `CompletionStatus` lives in `habit_enums.py`, not `entity_enums.py` with its two
  siblings; and ADR-011/012's "primary consumer" guesses were wrong in both files — driving
  the production path showed `analytics_life_path_service.py` and `askesis_service.py`.
  A finding can be right while its fix is wrong; so can a worksheet row.
- **A marker cannot land inside a fence** (B3 scoped it out as prose-about-the-marker), so
  the fence-bound illustrative paths took a content fix instead: ADR-013/014 spelled
  Obsidian **vault** files as repo paths (`/docs/stories/…`), which was wrong on its own
  terms — they now read `0vault/…` and are correctly invisible to a repo-path checker.
- **Planned-but-unbuilt is a third class**, distinct from both narrative and rot, and it
  takes neither treatment. ADR-057 and ADR-062 are `Proposed`; their citations are designed
  destinations, so the paths are named in prose rather than backticked as files (the
  spelling this document already uses for the same reason). Marking them would have called
  a plan "history"; deleting them would have destroyed the design.
- **Deleting a file breaks anchors no link checker sees.** Removing ADR-010 cost three
  inbound fixes — its `docs/INDEX.md` row, and a measured claim in BOTH
  `docs/tools/HEALTH_CHECKS.md` and `scripts/health/duplicate_headings.py` about phantom
  setext headings. That count was re-derived by driving the real `find_duplicates` with the
  narrowing lifted: **8 today (4 per file), not the "six" both copies claimed** — so the
  copies were already stale, and the surviving number is 4 in `ADR-TEMPLATE.md` alone.
  Editing ADR-042 likewise shifted a `(file, line)` anchor in `stale_names.py`'s
  `ALLOWED_OCCURRENCES`, caught by its own positive-control test.
- **The new domain doc surfaced a real bug in `audit_untracked_refs.py`.**
  `docs/domains/user_entry.md` is the first tracked doc whose lowercase-underscore name has
  the exact shape of a memory slug. The single-line probe excused it as a tracked basename;
  the wrapped-line probe called the raw regex instead and re-reported the same citation as
  half of a two-line one. Both probes now share one `_memory_citation()` helper. The
  suppression existed — the second caller simply never ran it. ⚠️ Review then found the
  deeper half: the helper excused the whole probe whenever its **leftmost** match was a
  tracked basename, so a real citation further along the same probe went unreported. It
  scans every match now — excusing a match must never excuse the line. Four cases pin it in
  `tests/unit/test_untracked_refs.py`.
- **ADR-027 is now `Superseded`**, which moves a number this section cites: strictly-Superseded
  ADRs are **3 of 88** (was 2 of 89 — ADR-027 gained the status, ADR-010 left the tree).
  Status-scoping stays falsified; the argument never rested on the exact count, and the
  intra-file mixing it actually rested on is untouched.
- **The 344-finding sweep queue was left alone** except for its one mandated ripple. ⚠️
  `docs/domains/README.md` still carried two dead rows three cells from the one B4 rewrote:
  its PS row links a nonexistent `ls.md` and its Journals row a deleted `journals.md`.
  Deliberately not fixed in B4 — they were ordinary sweep-queue rot, and that PR's fence was
  the ADR tier; both were fixed in B6 (the queue doc's § Named, still queued records how, and
  why the Journals row is gone rather than repointed). (Named here without link syntax on purpose: a markdown link is parsed inside
  backticks too, so writing the rows out verbatim would add two findings to the queue this
  paragraph is counting.)

**PRs B5–B8 (LANDED, 2026-09-02 — arc complete):** 343 → **280**, and `decisions/` + the
history dirs are clear. B5 — the two scheduled scanner narrowings (343 → 330, exactly the 13
measured; two rulings survive them: all four passes reach both vocabularies through ONE
predicate, and the wide "reject uppercase stems" rule stays refused), B6 — the queued
corrections + the domains catalog (330 → 327), and B7 — the four sweepable heavy hitters
(327 → 288) are recorded in [`dead-doc-links-sweep-queue.md`](dead-doc-links-sweep-queue.md)
(§ Landed, § Disproven claims, § Heavy hitters) — one copy, there. **B8 (288 → 280) — RULED
(Mike, 2026-09-02) + BUILT:** planned-file citations in live roadmap docs take option (b), a
`<!-- planned -->` marker honored only under live `docs/roadmap/`, over leaving the class
reported. ⭐ The deciding property is that it **self-retires**: when the planned file is built
the marker suppresses nothing and the SKUEL026 inversion reports it, turning a permanent dead
link into a build-completion signal. Built as ONE mechanism with `<!-- historical -->` (a
`MarkerSpec` registry), not a parallel copy; scopes are disjoint and both directions pinned.
⚠️ A fenced citation cannot carry a marker.

**RULED — the history line (226 + 156) (Mike, 2026-09-01, on the classification pass's
report):** C takes **(a)** — the silent dir carve-out (no tripwire to un-observe). D
takes **(d)** — the per-citation historical marker, the option whose steady state makes
red mean rot inside the authority tier. The measured split decided it: of 154
classifiable `decisions/` findings (167 raw − 11 parser-class − 2 route-matched PWA),
**81 (53%) are standing-contract rot across 31 Accepted/Implemented ADRs, 70 are
narrative, 3 ambiguous** — the cheap arm (report-separately-don't-red) was conditioned
on ~all-narrative with "first observed standing-contract rot in an Accepted ADR" as its
reopening tripwire, a condition this measurement shows already fired 81 times over.
Content rulings from the same sitting: **(1)** planned-work citations advertising work
that must never be done are DELETED, not marked — unchecked "[ ] Create X" checklist
items and "(if exists)" hedges included (ADR-027:221 is the precedent). **(2)**
ADR-003:379's historical note gets its chain completed (Journal → Reports → UserEntry),
its `See` repointed at ADR-054, **and** a UserEntry domain doc created under
`docs/domains/` — the
domains set documents 12 domains and is missing its busiest. **(3)**
`ADR-010-moc-core-service-query.md` is an unfilled template shell (its Decision section
is ADR-TEMPLATE's instructions + example block verbatim) — DELETE it; the number stays
retired (numbering already has gaps and duplicates). **The 3 ambiguous findings each
resolve under these rulings — B4 needs no further decision:** ADR-003:379 → (2);
ADR-037-embedding-infrastructure-separation:173 (the "(if exists)" hedge) → (1), delete
the line or repoint at ADR-068/ADR-074; ADR-027:221 → (1), delete the checklist item
alongside the supersession note. ⚠️ Standing constraints survive
the ruling: ADR findings stay OBSERVED (a silent `decisions/` carve-out remains off the
menu — Codex on #1215), and status-scoping stays FALSIFIED (2 of 89 Superseded as measured
at ruling time — 3 of 88 after B4, see its note above, which changes nothing: the
mixing is INTRA-file — reconfirmed by the pass: ADR-011/012 hold exemplary narrative
corrections lines above standing rot). Do not resurrect either.

**ADR classification pass (EXECUTED 2026-09-01):** full read, no sampling — all 154
findings classified from their surrounding paragraphs, every standing-contract case
verified against git history (`git log --follow` / `git ls-files` / `git grep`) before
classification; a citation was called "never tracked" only on empty `git log` since the
consolidation initial commit. Scanner residue landed entirely inside B1's approved
classes (11 parser-class + 2 PWA URLs matching `adapters/inbound/pwa_routes.py`) —
nothing new for B1. The worksheet (per-finding anchors, verified successors, quoted
ambiguous cases) is the pass's report in the scratch tier; PR B4's arc prompt carries
the pointer — this doc deliberately does not. Graduating it into `docs/` was considered
and rejected (Codex on #1216): a document consisting of ~150 intentionally-dead paths
would itself become ~150 scanner findings — the noise this section exists to remove.
**Fallback if the worksheet is unavailable** (fresh clone/worktree — scratch is
machine-local): B4 re-derives it by the recorded procedure — drive `check_file()` over
`docs/decisions/`, classify each finding by its surrounding paragraph
(narrative/standing/ambiguous), verify every standing case against git history — with
the split recorded above as the expected shape; re-derivation is mandatory for the
counts anyway, never guessed.

**Live-docs sweep queue — EXTRACTED to its own doc (Mike's call, 2026-09-01).** The
remaining **280 findings / 192 distinct targets** now live in
[`dead-doc-links-sweep-queue.md`](dead-doc-links-sweep-queue.md), with the per-directory
split, the tail shape that decides the fix (only 26 of 192 have a unique same-basename
relocation candidate, so the usual fix is editing the citing PROSE rather than swapping a
path — ⚠️ but "no same-basename candidate" is not "no successor", and the linked doc says
why), the heavy hitters, the ride-along protocol, and the cautions. That doc also
carries two things this section deliberately does not: the **disproven claims owed a
correction** (wrong claims about live files, invisible to the scanner) and the two named
`docs/domains/README.md` rows. Re-derive every count there; never quote one from prose.

**Noted, unscheduled — duplicate ADR numbers:** ADR-030 exists three times
(`curriculum-domain-unification`, `dual-track-assessment-pattern`,
`usercontext-file-consolidation`) and ADR-037 twice (`embedding-infrastructure-separation`,
`lateral-relationships-visualization-phase5`). PR B2's metadata unblock routed around the
collisions; it did not remove them — a bare `ADR-030` or `ADR-037` in `related_adrs` is
now a hard error naming all the candidates, which is the point, not a workaround.
Renumbering is a citation-update campaign — Mike decides if/when; nothing schedules it.
