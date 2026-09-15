---
title: "Skill↔Doc Backlink Reconciliation (post-canonicalization)"
updated: 2026-09-15
status: "done — every missing-reverse warning reconciled (62 by the time the pass ran, not the 28 registered), the rendered `## Related Skills` blocks regenerated from frontmatter across all 62 docs that declare one, and the sync writer's two whitespace defects fixed on the way; validator reads 137/137 bidirectional, 0 warnings"
registered: 2026-08-11
trigger: "a new related_skills declaration or skills_metadata.yaml entry that the other side does not mirror — the validator's MISSING_REVERSE warning names it"
check: "uv run python scripts/validate_cross_references.py — `Missing Reverse Links: 0`; uv run python scripts/sync_cross_references.py --all --dry-run — `Updated: 0` (a block that already matches its frontmatter is reported as skipped)"
---

# Skill↔Doc Backlink Reconciliation (post-canonicalization)

*Case file for the former [deferred-work.md](../deferred-work.md) entry of the same name.*

**Status: ✅ DONE — 2026-09-14.** Both items executed as one taxonomy pass — see *What landed*
at the end. The 28 warnings registered here had grown to 62 by the time the pass ran (every
ADR authored since #1023 declared `related_skills:` that no skill mirrored), which is the
reason the trigger above now names the mechanism rather than a count.

`validate_cross_references.py` used to read prose `@skill` mentions out of doc bodies while
the repo declared its doc→skill links in `related_skills:` frontmatter. Making the validator
read the canonical field (#1023, 2026-08-11) cleared 65 false warnings and **surfaced 28 real ones
that the prose reader had been hiding** — an ADR could satisfy the backlink contract merely by
containing the string `@python` somewhere in its body while its frontmatter named no skill at
all. The instrument is fixed; the data it now sees honestly is not.

Two follow-ons, both deliberately left alone because each needs a judgment call rather than a
mechanical edit:

**1. Reconcile the surfaced backlinks.** Each warning has two legitimate resolutions and only
a human picks: add `related_skills: [python]` to `ADR-022`, *or* drop `ADR-022` from the
`python` skill's `related_adrs` because a curated teaching set shouldn't include it. Doing this
by rote in either direction would corrupt the taxonomy — the point of `primary_docs` is that it
is curated, not exhaustive.

Regenerate the list rather than trusting a count copied into this file:

```bash
uv run python scripts/validate_cross_references.py --verbose
```

`scripts/add_skill_backlinks.py` mechanises the safe subset (doc gets the backlink), but it
walks only `primary_docs` — not `patterns` or `related_adrs` — so it resolved 1 of 28 at the
time of writing. It is the surviving sibling of the deleted `fix_missing_reverse_links.py`,
and unlike that one-shot it now writes a field the validator actually reads.

**2. Resync the drifted body sections.** `sync_cross_references.py` generates `## Related
Skills` blocks *from* frontmatter; 35 docs carry one and **3 had already drifted from the field
they were generated from** (e.g. `PWA_ARCHITECTURE.md`: frontmatter `[fasthtml, pwa]`, rendered
section `[fasthtml]`). These are now cosmetic — the validator no longer reads them — but they
are visibly wrong to a human reader. `--all` is not a surgical fix for those 3: it walks 211
docs across `patterns/`, `architecture/`, `decisions/`, `intelligence/` and would rewrite 47 of
them, adding sections to docs that have frontmatter but no rendered block yet. That breadth is
why it wasn't bundled into a validator fix; run it as its own reviewable change.

```bash
uv run python scripts/sync_cross_references.py --all --dry-run
```

**Enable when**: either a docs-taxonomy pass (item 1) or the next `docs/patterns` sweep that is
already touching these files (item 2). Neither blocks anything — every one of them is a warning,
and `--errors-only`, the pre-commit gate, exits 0.

**Watch for:** the report's orphaned/skills-without-docs listings are truncated. Read the
counts in the statistics block, not the length of the printed list — the info listing caps at
20 while the real orphan count is ~321.

---

## What landed (2026-09-14)

**The rule applied, so the next pass can repeat it instead of re-deriving it:** a doc→skill
declaration stands when the skill's own content overlaps the doc's subject — the skill's
markdown cites the doc, or the doc's subject is the skill's primary area (ownership → security,
HTMX → ui-browser) — and the skill then lists the doc back (an ADR into `related_adrs`, anything
else into `patterns`; `primary_docs` stays curated and was touched only for `docker`, which had
none and cites `DO_MIGRATION_GUIDE.md` as its runbook). Otherwise the declaration is dropped from
the doc. Skill→doc listings stand unless the skill has no content on the doc's subject.

**Item 1 — 62 warnings, 0 left.** 40 were doc-declares/skill-omits: 31 listed back, 8 dropped
from the doc (`PWA_ARCHITECTURE`→fasthtml and `UI_ORCHESTRATOR_PATTERN`→fasthtml were pre-`@pwa`
/ pre-`@ui-orchestrator` vestiges; `ADR-072`→ui-css and `ADR-084`→skuel-ui pointed the icon ADR
at the CSS skill and the typography ADR at the components skill; `ADR-087`→result-pattern hung on
one incidental `Result.fail`; `DO_MIGRATION_GUIDE`→neo4j-cypher-patterns names a stack with no
Neo4j container; `FASTHTML_ROUTE_REGISTRATION`→ui-browser confused route registration with
HTMX), and 1 resolved by deleting the doc — `patterns/PERFORMANCE_MONITORING.md` was an
eight-month tombstone for a removed class, cited only by the generated indexes and by
`pydantic`/`prometheus-grafana` `patterns`, and it declared `@skuel-ui` for a monitoring system.
22 were skill-lists/doc-omits: 21 docs gained the declaration; the one drop was the case file's
own example — `ADR-022` left `python`'s `related_adrs` (the skill has no authentication content;
`result-pattern` cites the ADR and `security` owns its subject, so the ADR declares those two).

**Item 2 — the rendered blocks.** `sync_cross_references.py --all` now runs clean over every
doc that declares `related_skills:`. Three defects in the writer surfaced on the first run and
were fixed before it was re-run: (1) it dropped the blank line after the closing frontmatter
fence on every file it touched — the shared `_FRONTMATTER_PATTERN`'s `---\s*` swallows it, and
the script rebuilt the file from the swallowed body; (2) a new block was inserted with no blank
line before its heading and two after (the insertion point backed up over the blank lines and
then re-emitted them); (3) replacing an existing block ran to the next `## ` heading, which
swallowed a `---` rule the doc kept between the block and that heading
(`CYPHER_VS_APOC_STRATEGY.md`). The block is now bounded by its own shape, and a block that already matches its frontmatter
is reported as skipped — the `--dry-run` count is a real would-change count, which the 47
above was not. `ADR-TEMPLATE.md` is
excluded from the walk — a block rendered into the template would be copied into every ADR
authored from it.

**Incidental, same files:** `docker`'s registry description still sold the skipped App Platform
plan (its `last_reviewed` was re-stamped after checking the skill against the runbook's delta
since #1072 — the credentials line and the ADR-080 wording, both mirrored);
`docs-skills-evolution/reference.md` still instructed authors to link a skill with prose
`See: @fasthtml` (two sites, both now show the frontmatter field); and
`guides/HTMX_VERSION_STANDARDIZATION.md` — registered as `ui-browser` reading by this pass —
said HTMX loads from unpkg and Lucide ships as a browser runtime (HTMX is vendored at
`/static/vendor/htmx.org/`; the Lucide bundle is `scripts/gen_icons.py`'s input, never served —
ADR-072; `ALPINE_JS_ARCHITECTURE.md` carried the same row). The two line-anchored
`ALLOWED_OCCURRENCES` groups whose docs gained a block were re-anchored from the scanner's report.

**Observed, not acted on:** a skill's `related_adrs` is a curated subset, not its citation
closure — the skills' own markdown cites **75** ADRs their `related_adrs` do not list (`journals`
cites ADR-073/076/077/078/081 and lists ADR-003/054; `activity-domains` cites eight and listed
none). Closing that is a different, larger judgment pass, and it would drive the orphan count
(370 docs with no `related_skills`) rather than the reverse-link count. Separately: since #1023
the rendered `## Related Skills` block is a projection of frontmatter that Obsidian and GitHub
both already display as properties — whether to keep rendering it at all is a One-Path question
nobody has asked yet.
