---
updated: 2026-09-02
---

# Dead-doc-links sweep queue — the live-docs residue

**Status:** OPEN — **ACTIONABLE**. Ruled *register + burn down via doc sweeps*
(Mike, 2026-09-01). Extracted from
[`deferred-work.md`](deferred-work.md) § Dead-Doc-Links Instrument on Mike's call
(2026-09-01) so the queue can be worked independently of the arc that produced it;
that section keeps the rulings and the completed record, and points here.

The instrument is `scripts/health/dead_doc_links.py` (in `./dev health` and the weekly
janitor; not a CI gate). B1–B5 took it from 871 findings to 330 by removing every class
that was *not* rot — parser false positives, unvalidatable freeform files, application
URLs read as file paths, a generated index, dated history directories, the ADR tier, and
the documentation stand-ins two of the four passes reported anyway. B6–B7 begin the
burn-down of the residue itself (330 → 280).

⚠️ **What is left is NOT "overwhelmingly rot" — that framing was this doc's, and B7
measured it false.** Classifying all 46 findings across the five heavy hitters gave
**17 rot, 20 deliberate narrative, 7 planned files, 2 pure fiction**: barely a third was
the stale pointer the queue was assumed to be full of. Heavy hitters are a biased sample
— a doc that documents deletions accumulates narrative citations — so this is not the
corpus ratio, and it is not offered as one. It is enough to retire the assumption. All
four classes take DIFFERENT actions and three of them are **not** "repoint the path";
each is under *Cautions*. Verify before rewriting; a report is never proof.

> ⚠️ **Writing about this instrument creates findings in it.** This file is inside the
> scanned corpus (`docs/roadmap/` is live; only `docs/roadmap/done/` is carved out), so a
> dead path named here in link syntax or as a backticked project path becomes a finding
> in the queue this file is counting. Name dead targets in prose.
>
> ⚠️ **Backticks do not protect markdown link syntax.** The link pass reads every
> line, code spans and fences included, so wrapping a link to a deleted file in
> backticks still produces a finding. Only a *bare path* is made safe by backticks,
> and only when it lacks a project prefix. Drafting this very warning with a worked
> example added a finding to the queue — the trap is not theoretical. Re-measure
> after editing this file, not only after a sweep.

## The queue

**280 findings / 192 distinct missing targets**, measured 2026-09-02 on the B8 branch by
driving `check_file()` over `get_md_files()`. Re-derive the same way; never quote these
numbers without re-running.

| Area | Findings |
|---|---|
| `docs/patterns/` | 79 |
| `.claude/skills/` | 40 |
| `docs/intelligence/` | 40 |
| `docs/domains/` | 29 |
| `docs/architecture/` | 25 |
| `docs/guides/` | 18 |
| `docs/roadmap/` (live half only) | 6 |
| `docs/reference/` | 13 |
| `docs/` (root) | 8 |
| `docs/development/` | 6 |
| `docs/technical_debt/`, `docs/tools/` | 3 each |
| `docs/deployment/`, `docs/features/` | 2 each |
| `design-principles/`, `examples/`, `observability/`, `security/`, `tutorials/`, `ui/`, `user-guides/` | 1 each |

### The tail shape decides the fix

Of the 192 distinct dead targets, **26 have exactly one tracked file sharing their
basename** — the only ones a rename map could carry; 8 have several; **158 have none.**

⚠️ **"No same-basename candidate" is not "no successor."** A rename lands in the 158 even
when its replacement is well known: the deleted relationships-package `domain_configs.py`
has no same-named file anywhere, yet its successor is
`core/models/relationship_registry.py` — a repoint PR #1220 made four times over. Treat the 158 as **requiring investigation**, not
as proven deletions; the evidence is git history and the citing paragraph, never the
basename.

So the usual fix is **editing the citing prose**, and a bulk rename script cannot carry
this queue — but do look for a renamed successor before deleting a citation outright.

### Heavy hitters — SWEPT (B7), and the one that must not be

Four of the five listed here are done: the two UI-component docs, the UI development
guide, and the three-tier type-system doc — 39 findings, all four now reporting zero.

**The fifth was never rot and is now silenced correctly.** The finance/billing migration
roadmap's 7 findings are **files the plan says to CREATE** — four annotated "(new)" in its
own code-touch inventory. Sweeping them would have been the mistake this table exists to
warn about. They now carry `<!-- planned -->` markers (B8), which is not the same as being
hidden: when those files are built the markers suppress nothing and get reported.

⚠️ **Below 7 the tail is flat, and a high count was never evidence of rot** — the
finance-billing row is the proof, from inside this very table. The docs-skills-evolution
skill reference told the same story earlier: it reported 6, every one a template
placeholder, and the B5 narrowing took it to 1. **Classify a file's findings before
scheduling it as cleanup.** The current top of the tail is a run of files at 7 and fewer.

## Protocol

1. **Ride-along.** Any sweep or PR touching a listed doc fixes that doc's dead links as
   part of the change. This is the default path — the queue burns down as the docs are
   worked, not in one campaign.
2. **Dedicated small sweeps** were sanctioned for the heavy hitters, and the four
   sweepable ones are done. A new one earns a sweep only after its findings are
   CLASSIFIED — the fifth heavy hitter proved a high count can be entirely not-rot.
3. **Re-derive per doc** by running the scanner and filtering to the file. Never work from
   a count in prose, including the ones on this page.

### Cautions, each learned the hard way

- ⚠️ **A route-shaped target that is still red is not automatically rot.** `/tasks` is a
  live page, but it is registered as `@rt(f"/{domain}")` and no static pass can resolve an
  f-string, so it reports by design (fail toward reporting). **Check `adapters/inbound/`
  before rewriting any leading-slash target.** Six are red for this reason: three journal
  browse URLs deleted in #420, two YAML-schema paths that are neither route nor directory,
  and `/tasks`.
- ⚠️ **Documentation placeholders report as rot.** The vocabulary now rejects the naming
  metavariables a convention doc uses for its own examples — a `_NAME` suffix, an all-`X`
  token, a trailing `_X`, a `-name` segment — so eight of the nine verified cases are
  gone. **One is left, and it is deliberate:** the architecture metavariable cited at
  line 437 of the docs-skills-evolution skill reference fits no discriminator, and a rule
  for a single instance is the shadow risk the vocabulary refuses. Never "fix" it as
  though it were rot; it needs a decision (leave it red, or reshape the citing example).
  A new placeholder shape that starts reporting is a vocabulary gap, not a dead link —
  measure it against the whole tree before adding an entry.
- ⚠️ **A live doc's deliberate narrative citation is not rot, and it has NO marker.**
  A catalog saying "the former X was deleted, use Y instead" is doing its job, and outside
  `docs/decisions/` there is no `<!-- historical -->` to declare that — deliberately (see
  the last bullet). **20 of the 31 UI-doc findings B7 swept were this shape.** So the fix
  is neither "delete the history" nor "repoint the path": it is to name the dead target in
  prose. A backticked BARE filename is not extracted — the shape guard needs a leading `/`
  or a project directory — so "the former `buttons.py` wrapper" keeps the precision and
  loses the finding, while a dated evolution log keeps its record intact.
- ✅ **A roadmap doc citing files it plans to CREATE has a marker now** — `<!-- planned -->`,
  honored only under live `docs/roadmap/` (Mike's ruling, 2026-09-02). It is the
  historical marker's mirror image and the *same* mechanism, so it inherits every rule:
  line-scoped, exact grammar, skips only a DEAD target, and a marker that suppressed
  nothing is reported. ⭐ It was chosen over leaving the class reported because it
  **self-retires**: when the planned file is built the marker covers nothing, so the
  report tells you the roadmap line came true. ⚠️ A marker is never read inside a fence,
  so a fenced citation must move into prose to carry one. Still classify before
  annotating — a `docs/roadmap/` citation of a *deleted* file is ordinary rot, and the
  marker would be a lie about it.
- ⚠️ **Some citations are pure fiction** — a path that has never existed in this repo
  (`git log --all` empty). Two were found in B7, both instructing the reader to run a
  migration script that was never written. These are the one class where deleting the
  citation is the whole fix, and `git log --all` is what tells them apart from a rename.
- ⚠️ **Do not reach for a same-basename file** — see the tail shape. Matching on basename
  is how a correct-looking fix points at the wrong module, and it also misses every
  renamed successor, which is the more common case.
- ⚠️ **A bulk correction script, if one ever emerges, re-derives its premise at run time
  and aborts on surprise.** A heuristic proposes; it never rewrites.
- ⚠️ **The historical-citation marker is honored ONLY under `docs/decisions/`.** Copying
  one into a live doc suppresses nothing and is itself reported, with the reason carried.
  There is no opt-out for this queue — that is deliberate.

## Landed: the two scanner narrowings (B5)

Both narrowings scheduled on 2026-09-02 are **built and merged**; the schedule that stood
here is gone with them. They removed exactly the 13 findings they were measured for —
343 → 330, no collateral — and the detail now lives where it is enforced: the vocabulary
and its measurements in `scripts/health/dead_doc_links.py`, the pins in
`tests/unit/scripts/test_dead_doc_links.py`.

Two rulings from that work outlive it:

- **Every pass now consults both vocabularies through one predicate.** Two of the four
  extractors reached only the template markers, so a token *already in* the placeholder
  vocabulary was still reported by those two. That is the third time this module has
  grown the same drift, so the fix was structural rather than another pair of calls:
  add to either vocabulary and all four passes see it. Do not reintroduce a
  pass-specific guard.
- **The wide rule stays refused.** SHOUTING_SNAKE_CASE is how this corpus names ~200 real
  docs, so "reject any uppercase stem" would shadow the whole tier. The four
  discriminators are narrow because the wide one was measured and failed — the same
  lesson as the comma the link guard deliberately does not reject.

⚠️ One target is **deliberately still reported**: the architecture metavariable named in
*Cautions*. It fits no discriminator, and a one-off rule for a single instance is pure
shadow risk. It is a decision, pinned by a test, not an oversight — reshape the citing
example or leave it red, but do not add a rule.

## Disproven claims — a species the scanner is blind to

Wrong claims about files that **exist**, so no dead-link run will ever raise them. Three
were filed off PR #1220; all three are now closed, and the way they closed is the reason
this section stays:

- **Two were applied** (`CLAUDE.md`'s `/submit` ingestion path, and the `TRANSFORMS`
  direction comment in `core/models/relationship_registry.py`). Both reproduced exactly
  as filed before being applied.
- **One was withdrawn before it landed.** It would have "corrected" a `docs/domains/choices.md`
  sentence about event payloads on the strength of `BaseEvent` declaring only
  `occurred_at` — but every event in `core/events/choice_events.py` declares its own
  `metadata` field, so the sentence was **true for the table it heads**. The
  generalisation came from the UserEntry events, which have no such field. Following the
  entry would have replaced an accurate statement with a false one (Codex, PR #1221).

⚠️ **A queued correction is a claim like any other — reproduce it when you apply it, not
only when you file it.** That is two applied-as-filed to one withdrawn-on-contact, and it
is why nothing here is a work order. B5 hit the same edge from the other side: its
schedule cited two docs as real files a wide rule would eat, and neither is tracked.

File a new entry with the claim, the verified truth, and the evidence — then ride it
along on the next PR touching the file.

## Named, still queued

Nothing today. The `docs/domains/README.md` PS and Journals rows that stood here are
fixed: the PS row's link pointed at a filename that never existed, and the Journals row
named a doc deleted when the domain was absorbed. That row is **gone rather than
repointed** — Journals is not an entity type — and the catalog now points at
`docs/architecture/JOURNALS_DOMAIN_ARCHITECTURE.md`, which owns the persistence contract.

⚠️ **This queue's own successor guidance for that row was wrong, twice, and it is the most
instructive thing on this page.** It said the successor content was the UserEntry doc.
There is a real successor — different name, different directory, invisible to any basename
search — and the substitute claim was itself false: "a journal is a `pipeline=JOURNAL`
UserEntry" survives no contact with the code. The companion persists nothing by default and
a saved chat becomes an owner-private `:ConversationSession`; in-app periodic notes are
written `Pipeline.NONE`; vault notes are authored `extract_activities`; and
`Pipeline.JOURNAL` is **authored, never assigned** — no service sets it, but the
vault/YAML door accepts it from frontmatter (`_parse_pipeline` allows every member except
the two audio ones), so a synced note declaring `pipeline: journal` persists a live entry.
That last correction is itself the lesson: "no producer at all" was a *code-grep*
conclusion, blind to a data-driven door, and it is exactly the over-reach the rest of this
paragraph is about (Codex, PR #1224, six rounds on one paragraph).

**Two rules come out of that.** An entry on this page is a **lead, not a finding** — a lead
that names a successor has to be checked before it is followed. And when a fix keeps
drawing findings, stop restating the contract: a catalog's job is to point at the authority,
not to duplicate a live contract that has more than one answer.

⚠️ **The same table held rot the scanner cannot see, and a link fix that ignored it would
have left the doc wrong.** Its UID-prefix column was a second copy of the authoritative
per-type table, rotted into colon spellings no generator mints — a spelling the ratified
separator grammar reserves for internal machine identifiers — with two entity types
claiming the same prefix, under a header declaring one more column than any row supplied.
The copy is deleted and the authority cited. Expect this shape: **a dead link is often
the visible edge of a stale paragraph**, so read the surrounding claim before repointing
a path.

## How to re-derive everything on this page

```bash
uv run python scripts/health/dead_doc_links.py          # totals + per-file listing
uv run python scripts/health/dead_doc_links.py --verbose # each finding as it is found
```

Every exclusion prints its count on every run, zero included — carve-out file counts,
route skips, and marker skips. A silent zero is how a rotted carve-out looks exactly like
a clean scan, which is why they print.

## Provenance

Arc PRs: #1217 (parser + carve-outs + route matching, 871→754), #1218 (one ADR-link
resolver, 754→724), #1219 (history-dir carve-out + the per-citation marker mechanism,
724→497), #1220 (ADR content sweep, 497→343), B5 (the two scheduled narrowings,
343→330), B6 (the queued corrections + the domains catalog, 330→327), B7 (the four
sweepable heavy hitters, 327→288), B8 (the planned-file marker, 288→280). Rulings, the completed record, and the
duplicate-ADR-number note live in [`deferred-work.md`](deferred-work.md)
§ Dead-Doc-Links Instrument.
