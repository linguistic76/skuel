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
it cannot resolve, and a set of documentation placeholders are intentional examples — both
enumerated under *Cautions*, which is where those counts live. Verify before rewriting
rather than treating a report as proof.

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
basename** — the only ones a rename map could carry; 10 have several; **180 have none.**

⚠️ **"No same-basename candidate" is not "no successor."** A rename lands in the 180 even
when its replacement is well known: the deleted relationships-package `domain_configs.py`
has no same-named file anywhere, yet its successor is
`core/models/relationship_registry.py` — a repoint PR #1220 made four times over. Treat the 180 as **requiring investigation**, not
as proven deletions; the evidence is git history and the citing paragraph, never the
basename.

So the usual fix is **editing the citing prose**, and a bulk rename script cannot carry
this queue — but do look for a renamed successor before deleting a citation outright.

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
  not reject SHOUTING metavariables, nor a lowercase-hyphen stand-in like `skill-name`, so a
  doc teaching a naming convention reports its own examples. **Nine such findings are
  verified today** — six in `.claude/skills/docs-skills-evolution/reference.md` and three in
  the docstring template block at `docs/patterns/DOCSTRING_STANDARDS.md` — with the usual
  tells being a `_NAME` suffix, an all-`X` token, or a trailing `_X`. Never "fix" one — the narrowing that
  removes them is **scheduled below**, and until it lands these findings are noise to skip.
- ⚠️ **Do not reach for a same-basename file** — see the tail shape. Matching on basename
  is how a correct-looking fix points at the wrong module, and it also misses every
  renamed successor, which is the more common case.
- ⚠️ **A bulk correction script, if one ever emerges, re-derives its premise at run time
  and aborts on surprise.** A heuristic proposes; it never rewrites.
- ⚠️ **The historical-citation marker is honored ONLY under `docs/decisions/`.** Copying
  one into a live doc suppresses nothing and is itself reported, with the reason carried.
  There is no opt-out for this queue — that is deliberate.

## Scheduled: two scanner narrowings (Mike, 2026-09-02)

**Not built here.** Each targets a *measured* shape, each subtracts findings (the fail-safe
direction), and each must land with cases pinning it in
`tests/unit/scripts/test_dead_doc_links.py` — the module's standing discipline. Together
they remove **13 of the 343**; counts measured on `c6ed127e6`, re-derive before building.

### 1. `_is_placeholder` is consulted by ONE of the four passes — guard drift

`_looks_like_local_path` calls it, so the backtick and fence passes are covered.
`extract_bare_paths` and `extract_markdown_links` **never call it**. The proof is a target
already in the vocabulary that reports anyway: `NEW_FEATURE.md` matches the existing
`new_feature` topic marker, and the bare pass reports it regardless.

This is the same drift the module already warns about for `TEMPLATE_MARKERS` — a guard
that one pass consults and another does not — and B1 closed exactly this shape for the
template markers without closing it for the placeholders.

**Effect: −5**, and no new vocabulary is needed for any of them:

| Pass | Finding | Why the existing vocabulary already covers it |
|---|---|---|
| bare | `NEW_FEATURE.md` | the `new_feature` topic marker |
| link ×4 | three destinations that are only an elision marker, plus one `http`-prefixed illustrative example | the elided-path-segment substring |

The four link findings are Python generics and syntax examples read as links: a subscripted
call such as `require_found[T]` or `execute[T]` followed by an elided argument list parses
as link text plus a destination. B1 gave the link pass a shape guard whose measured
discriminator is a **raw space**, and an elision marker has none — so they survive today.
⚠️ **They need no rule of their own.** An earlier draft of this schedule proposed a third
item for them; it was redundant, and an exact-match version of it would additionally have
missed the `http`-prefixed one (Codex, PR #1222).

(Those examples are spelled here without their trailing argument lists on purpose —
writing them verbatim added two findings to this very queue.)

### 2. Documentation metavariables — vocabulary extension

The vocabulary targets lowercase scaffolding (`your_service.py`, `new_domain/`, `foo.py`)
and uppercase *version/date* metavariables (`X.Y.Z`, `YYYY`). It has no entry for the
metavariable a naming-convention doc uses for its own examples. Four discriminators cover
all eight, and **every one was checked against the full tracked tree and matches no real
file**:

| Shape | Covers | Real-file collisions |
|---|---|---|
| `_NAME` suffix on the stem | `FEATURE_NAME.md`, `SYSTEM_NAME.md`, `PATTERN_NAME.md`, `ARCHITECTURE_NAME.md` | none |
| an all-`X` token (`XX`+) | `ADR-XXX.md`, `ADR-0XX-example.md` | none |
| trailing `_X` on the stem | `FEATURE_X.md` | none |
| `-name` suffix on a segment | `skill-name/SKILL.md` | none |

**Effect: −8** — three from the backtick pass, one from the fence pass, and **four from the
bare pass**. ⚠️ Those four are **blocked on item 1**: extending the vocabulary alone would
not silence them, because the bare pass never consults it.

⚠️ **One target is deliberately excluded.** `RELATED_ARCHITECTURE.md` fits no discriminator
above, and a one-off `RELATED_` entry is precisely the shadow risk the module refuses
("an unmeasured entry is pure shadow risk" — why only `foo` is listed). Either leave it
reported, or fix the citing doc to use a shape the vocabulary already rejects. Do **not**
add a rule for a single instance.

⚠️ **The obvious wider rule is wrong.** "Reject uppercase stems" was measured and swept in
real doc names — `SERVICE_PATTERNS.md`, `TASK_PRIORITY_ALGORITHM.md`. The narrow
discriminators above exist because the wide one failed, which is the same lesson as the
comma that B1's link guard deliberately does not reject.

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
