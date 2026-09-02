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
janitor; not a CI gate). The B1–B4 arc took it from 871 findings to 343 by removing every
class that was *not* rot — parser false positives, unvalidatable freeform files,
application URLs read as file paths, a generated index, dated history directories, and
the ADR tier. **What is left is overwhelmingly rot — but it is residue, not a verdict.**
Some reports are known-good citations the scanner cannot classify: `/tasks` is a live page
it cannot resolve, and eight are documentation placeholders (see *Cautions*). Verify before
rewriting rather than treating a report as proof.

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

**343 findings / 223 distinct missing targets**, measured 2026-09-01 on merged `main`
`7d159585d` by driving `check_file()` over `get_md_files()`. Re-derive the same way;
never quote these numbers without re-running.

| Area | Findings |
|---|---|
| `docs/patterns/` | 104 |
| `.claude/skills/` | 46 |
| `docs/intelligence/` | 41 |
| `docs/domains/` | 31 |
| `docs/architecture/` | 26 |
| `docs/guides/` | 18 |
| `docs/roadmap/` (live half only) | 14 |
| `docs/reference/` | 13 |
| `docs/ui/` | 11 |
| `docs/user-guides/` | 9 |
| `docs/` (root) | 8 |
| `docs/development/` | 6 |
| `docs/tools/` | 4 |
| `docs/technical_debt/` | 3 |
| `docs/deployment/`, `docs/features/` | 2 each |
| `design-principles/`, `examples/`, `observability/`, `security/`, `tutorials/` | 1 each |

### The tail shape decides the fix

Of the 223 distinct dead targets, **33 have exactly one tracked file sharing their
basename** — the only ones a rename map could carry. **180 have no candidate at all:**
the file is genuinely gone. So the usual fix is **editing the citing prose**, not swapping
a path, and a bulk rename script cannot carry this queue.

### Heavy hitters — candidates for dedicated small sweeps

| Findings | Doc |
|---|---|
| 12 | `docs/patterns/UI_COMPONENT_PATTERNS.md` |
| 11 | `docs/ui/COMPONENT_CATALOG.md` |
| 8 | `docs/patterns/three_tier_type_system.md` |
| 8 | `docs/user-guides/ui-development.md` |
| 7 | `docs/roadmap/finance-billing-migration.md` |

The first two are the same defect twice: citations of `ui/*.py` modules deleted in the
MonsterUI removal and the activity-views consolidation.

⚠️ **The table stops at 7 deliberately.** Below that the tail is flat (a run of files at
6 and fewer) and **a high count is not evidence of rot** — `.claude/skills/docs-skills-evolution/reference.md`
reports 6 and every one is a template placeholder. Check a file's findings before
scheduling it as cleanup.

## Protocol

1. **Ride-along.** Any sweep or PR touching a listed doc fixes that doc's dead links as
   part of the change. This is the default path — the queue burns down as the docs are
   worked, not in one campaign.
2. **Dedicated small sweeps** are sanctioned for the heavy hitters above.
3. **Re-derive per doc** by running the scanner and filtering to the file. Never work from
   a count in prose, including the ones on this page.

### Cautions, each learned the hard way

- ⚠️ **A route-shaped target that is still red is not automatically rot.** `/tasks` is a
  live page, but it is registered as `@rt(f"/{domain}")` and no static pass can resolve an
  f-string, so it reports by design (fail toward reporting). **Check `adapters/inbound/`
  before rewriting any leading-slash target.** Six are red for this reason: three journal
  browse URLs deleted in #420, two YAML-schema paths that are neither route nor directory,
  and `/tasks`.
- ⚠️ **Documentation placeholders report as rot.** The scanner's placeholder vocabulary
  targets lowercase scaffolding shapes (`your_service.py`, `new_domain/`, `foo.py`); it does
  not reject SHOUTING metavariables, so a doc teaching a naming convention reports its own
  examples. **Eight such findings are verified today** — six in
  `.claude/skills/docs-skills-evolution/reference.md` and two in
  `docs/patterns/DOCSTRING_STANDARDS.md` — with the reliable tells being a `_NAME` suffix,
  an all-`X` token, or a trailing `_X`. Never "fix" one. A narrowing for this shape is a
  candidate improvement to the scanner, but it must be measured first: an earlier
  all-uppercase heuristic swept in real doc names like `SERVICE_PATTERNS.md`.
- ⚠️ **Most targets are deleted, not moved** — see the tail shape. Reaching for a
  same-basename file is how a correct-looking fix points at the wrong module.
- ⚠️ **A bulk correction script, if one ever emerges, re-derives its premise at run time
  and aborts on surprise.** A heuristic proposes; it never rewrites.
- ⚠️ **The historical-citation marker is honored ONLY under `docs/decisions/`.** Copying
  one into a live doc suppresses nothing and is itself reported, with the reason carried.
  There is no opt-out for this queue — that is deliberate.

## Disproven claims owed a correction — NOT dead links

A different species, found while fixing PR #1220's findings and deliberately left outside
that PR's ADR-tier fence. The targets all exist, so the scanner is blind to these; they
are **wrong claims**, each verified against the code. Same protocol: ride-along on the
next PR touching the file.

> ⚠️ **A third entry was drafted here and withdrawn** — worth recording, because it is the
> failure mode this table can cause. It would have "corrected" `docs/domains/choices.md`'s
> line about payloads being the dataclass fields *minus the `occurred_at` / `metadata`
> every event carries*, on the strength of `BaseEvent` declaring only `occurred_at`. But
> every event in `core/events/choice_events.py` declares its own
> `metadata: dict[str, Any] | None`, so that sentence is **true for the table it heads**;
> the generalisation came from the UserEntry events, which have no such field. Following
> the entry would have replaced an accurate statement with a false one (Codex, PR #1221).
> **A queued correction is a claim like any other — reproduce it at ride-along time, not
> just when it is filed.**

| # | Where | The claim | The truth |
|---|---|---|---|
| 1 | `CLAUDE.md` § Unified Content Ingestion | `/submit` reaches `UserEntryService.create_entry()` *via* `core/services/ingestion/user_entry_ingestion.py` | No middle layer is involved. ⚠️ Name the canonical route, not the alias: `/submit` is a legacy 302 onto **`/submissions/exercise`**, whose form HTMX-posts to `POST /api/user-entries/upload`; that handler in `adapters/inbound/user_entry_api.py` builds the request and calls `create_entry()` itself. `ingest_user_entry` has exactly one caller — `UnifiedIngestionService`, the vault/YAML door. Two doors, no shared middle layer; `create_entry()` is the one convergence point |
| 2 | `core/models/relationship_registry.py` (the `TRANSFORMS` definition's comment) | the edge is "journal transcript → LLM-structured entry" | That is the **data flow**, and it reads as the edge direction, which is the reverse. `create_entry` does `relate(created.uid).via(TRANSFORMS).to(request.transforms_of_uid)` while the processing service sets `transforms_of_uid` on the structured **child** — so the edge runs **derived → source**. The definition's own `source_entry` field name is the tell |

## Named, still queued — `docs/domains/README.md`

Two rows of the entity-type table are dead links, three cells from the UserEntry row that
PR #1220 rewrote, and were left alone on purpose (that PR's fence was the ADR tier):

- the **PS** row links a file named `ls.md`, which has never existed — the doc is `ps.md`
- the **Journals** row links a `journals.md` deleted when the domain was absorbed; the
  successor content is the UserEntry doc

⚠️ Fixing the Journals row is not a path swap: Journals is no longer a domain of its own.
It is a `pipeline=JOURNAL` UserEntry, so the row either points at the UserEntry doc or
comes out of the table.

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
724→497), #1220 (ADR content sweep, 497→343). Rulings, the completed record, and the
duplicate-ADR-number note live in [`deferred-work.md`](deferred-work.md)
§ Dead-Doc-Links Instrument.
