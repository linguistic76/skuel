---
title: "Skill↔Doc Backlink Reconciliation (post-canonicalization)"
updated: 2026-09-05
status: "deferred"
registered: 2026-08-11
trigger: "a docs-taxonomy pass (item 1), or the next docs/patterns sweep already touching the files (item 2)"
check: "uv run python scripts/validate_cross_references.py --verbose; uv run python scripts/sync_cross_references.py --all --dry-run"
---

# Skill↔Doc Backlink Reconciliation (post-canonicalization)

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

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
