---
title: "py314 Annotation Sweeps — UP037 Schedulable, TC002/TC003 Never"
updated: 2026-09-05
status: "deferred"
registered: 2026-08-28
trigger: "UP037: a churn window Mike picks; TC002/TC003: never"
check: "uv run ruff check --select UP037 --statistics . | tail -3; TC002/TC003 still in pyproject's ignore list marked permanent"
---

# py314 Annotation Sweeps — UP037 Schedulable, TC002/TC003 Never

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

**Home: ADR-067 § "Deferred: TC/UP037 annotation-modernization sweep"** — the rationale, the two
dispositions, the runtime-evaluation hazard and the measured baseline live there; this section
holds only the trigger and the check, so the review walk sees it. For today's size, run the
check — the counts move with every commit, so no number is written down here.
**Trigger:** UP037 — a churn window Mike picks (one mechanical PR, boot-verified per the ADR);
TC002/TC003 — never as a sweep (permanent ignore; re-open only if ruff can name a local
decorator as runtime-evaluated).
**Check:** `uv run ruff check --select UP037 --statistics . | tail -3` — no UP037 row after the
sweep; `grep -n '"TC002"\|"TC003"' pyproject.toml` still in the ignore list, comment says
*permanent*.
