---
title: "Quarterly / Yearly Periodic Notes — Founder Vault Pass First"
updated: 2026-09-05
status: "done"
registered: 2026-08-28
ruled: 2026-09-05
trigger: "the first real note in either founder-vault folder"
check: "shipped 2026-09-05 — the gate never fired; Mike ruled build anyway"
---

# Quarterly / Yearly Periodic Notes — Founder Vault Pass First

*Shipped 2026-09-05. Its `deferred-work.md` entry is deleted.*

The periodic-notes arc (`done/calendar-periodic-notes-arc.md`) unified daily + weekly + monthly:
the ingestion door derives `ue:daily:{user}:{date}`, `ue:weekly:{user}:{week_of}` and
`ue:monthly:{user}:{month}` (`core/services/ingestion/user_entry_ingestion.py:397-410`). The
founder vault also holds `templates/t_quarterly.md` (0 bytes) and `t_yearly.md` (2 bytes) and
the empty folders `periodic_notes/Quarterly/` and `periodic_notes/yearly/` (2026-08-28: Daily 13
files, Weekly 3, Monthly 0, Quarterly 0, yearly 0) — stubs with no UID derivation and no
calendar door.

**Ruling 2026-08-28 (Mike):** founder vault pass first — the templates get authored when a
quarterly/yearly rhythm actually starts; app support follows the first real note, not the stub.
**Named work (then):** `ue:quarterly:{user}:{YYYY-Qn}` / `ue:yearly:{user}:{YYYY}` derivation +
frontmatter date parsing beside the monthly branch, plus one `planning_period` branch in
`ui/journals/period_panel.py` so the note carries the read panel the weekly and monthly notes
have ([`done/monthly-note-panel-parity.md`](done/monthly-note-panel-parity.md)).
**Trigger:** the first file in either folder —
`find ~/0bsidian/skuel/periodic_notes/Quarterly ~/0bsidian/skuel/periodic_notes/yearly -type f | wc -l` > 0
(founder-owned check, non-repo — `find -type f`, not `ls`: with two directory operands `ls` prints
headings, so two EMPTY folders already count 3).
**Named cost while parked:** none in the app; two empty template files in the vault.

## Ruling 2026-09-05 (Mike): build anyway — the gate never fired

The trigger was re-derived immediately before any work, and it read **`0`**: both founder-vault
folders were empty and both templates were unauthored (`t_quarterly.md` 0 bytes, `t_yearly.md`
2 bytes). Mike ruled build anyway — the same call he had made one PR earlier for
[`monthly-note-panel-parity.md`](monthly-note-panel-parity.md) (#1276), where the gate was also
unfired.

⚠️ **That `find` now returns `2`, and it is NOT the trigger firing.** With Mike's explicit
one-time permission the two templates were authored and one specimen of each kind was seeded in
the founder vault (`periodic_notes/Quarterly/2026-Q3.md`, `periodic_notes/yearly/2026.md`) as
the arc's end-to-end proof. **The count is seeded, not lived.** A later sweep must not read `2`
as evidence of a lived quarterly/yearly rhythm; the pre-seeding measurement (`0`) is the one
that describes the world. The vault half stays outside the repo — nothing here copies it in.

Each specimen deliberately carries all three parse cases so it proves the E3 contract rather
than merely ingesting: unticked checkbox lines (one with a `📅` due date), a ticked `[x]` + `✅`
line, one explicit `@context()` DSL line, **and a paragraph of unmarked prose that must create
nothing** — the live proof of the FULL-tier `EXTRACT_ACTIVITIES` bridge bypass that widening
`PERIODIC_NOTE_KINDS` switches on.

## What shipped

**Contracts** — one period-key form per kind, each parseable by exactly one parser:

| Kind | Period key | Frontmatter | UID | Route |
|------|-----------|-------------|-----|-------|
| quarterly | `2026-Q3` | `quarter_of: 2026-Q3` | `ue:quarterly:{user}:2026-Q3` | `/journals/quarterly/{year}/{quarter}` |
| yearly | `2026` | `year_of: 2026` | `ue:yearly:{user}:2026` | `/journals/yearly/{year}` |

- **`PERIODIC_NOTE_KINDS` widened to five** (`core/models/user_entry/user_entry.py`). Membership
  is load-bearing in four places at once — the periodic-note page, the note-save guard, the
  FULL-tier `EXTRACT_ACTIVITIES` bridge bypass, and the ingestion tracker's similarity gate — so
  each is covered by its own test rather than assumed. Two of those tests now derive their
  parametrize from the frozenset itself, so a sixth kind inherits the coverage.
- **Ingestion derivation** (`core/services/ingestion/user_entry_ingestion.py`): two branches
  beside the monthly one. `year_of` is normalized from int, string, or date.
- **Routes:** two find-or-create doors above the `{entry_uid}` catch-all; an out-of-range
  quarter or a year outside four digits degrades to the current one rather than minting a key
  no parser accepts.
- **`planning_period`** (`ui/journals/period_panel.py`): quarterly → the quarter's three months,
  yearly → Jan 1 – Dec 31, with `quarterly_period_start` / `yearly_period_start` beside their
  siblings. The four key forms overlap dangerously (`2026-Q3` and `2026-W32` share a shape;
  `2026` is a prefix of all of them), so every parser is pinned against every foreign form.
- **Month sub-headings:** a period long enough to lose one's place in sub-heads its rows by
  month inside each pair group. Carried as `PlanningPeriod.groups_by_month`, set by kind rather
  than derived from the range — a week CAN cross a month boundary (Jul 27 – Aug 2) but still
  reads as one run of days, so the weekly and monthly panels are visually unchanged.
- **Period ladder** (ruling 2026-09-05, Mike): the periodic-note sidebar gains "up" links
  climbing daily → weekly → monthly → quarterly → yearly. This is the **only** door to the two
  new notes — the calendar has week and month views only, so without it the routes would be
  reachable by URL alone, which is the affordance-invisibility disease the calendar arc named
  and cured twice.
