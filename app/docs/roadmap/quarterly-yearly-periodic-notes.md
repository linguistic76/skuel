---
title: "Quarterly / Yearly Periodic Notes — Founder Vault Pass First"
updated: 2026-09-05
status: "deferred"
registered: 2026-08-28
ruled: 2026-08-28
trigger: "the first real note in either founder-vault folder"
check: "find ~/0bsidian/skuel/periodic_notes/Quarterly ~/0bsidian/skuel/periodic_notes/yearly -type f | wc -l > 0 (non-repo)"
---

# Quarterly / Yearly Periodic Notes — Founder Vault Pass First

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

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
