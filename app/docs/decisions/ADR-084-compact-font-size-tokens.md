---
title: "ADR-084: Compact Font-Size Tokens (Micro Type Scale)"
updated: 2026-08-14
status: accepted
category: decisions
tags: [adr, decisions, ui, tailwind, typography, tokens]
related: [ADR-071]
related_skills: [ui-css, skuel-ui]
---

# ADR-084: Compact Font-Size Tokens (Micro Type Scale)

**Status:** Accepted (2026-08-14) — foundations + tracer shipped in PR1; sweeps land in PR2–PR6

**Date:** 2026-08-14

**Decision Type:** ⬜ Architecture  ⬜ Infrastructure  ✅ Pattern/Practice

**Related ADRs:**
- Extends: ADR-071 (SKUEL-owned Tailwind layer — token ownership moves to `input.css` `@theme inline`)

---

## Context

The UI trees carry **289 arbitrary Tailwind font sizes** (`text-[13px]`, `sm:text-[40px]`,
`text-[clamp(...)]`) spanning **22 distinct px values across 31 files**. Arbitrary values
defeat the purpose of a type scale: every author re-derives "small metadata text" per call
site, drift accumulates in half-pixel steps (9.5, 11.5, 13.5), and nothing stops the 23rd
distinct value from appearing tomorrow.

Tailwind v4's CSS-first `@theme` fixes this structurally: SKUEL mints named tokens for the
compact sizes the house style actually uses below/between the stock scale, and every value
that already lands on a stock step adopts the existing named utility.

## Decision

### 1. Four new bare tokens, font-size only — deliberately NO line-height companions

`static/css/input.css`, end of `@theme inline`:

```css
--text-10: 0.625rem;   /* 10px — micro labels, badges, mono kickers */
--text-11: 0.6875rem;  /* 11px — metadata, uppercase section labels */
--text-13: 0.8125rem;  /* 13px — dense body/list text (house workhorse) */
--text-15: 0.9375rem;  /* 15px — emphasized body, list titles */
```

All four are rem-valued exact sixteenths (pixel-identical at the 16px root). A bare
`--text-N` token with no `--text-N--line-height` companion makes Tailwind emit a
**font-size-only utility** (verified compile shape: `.text-10{font-size:.625rem}`), which
inherits line-height exactly as `text-[10px]` did — the migration is pixel-parity by
construction.

**Reviewers: do not add `--text-N--line-height` companions mid-sweep.** The absence is the
design, not an omission — companions would change rendered rhythm at every converted site
and break the pixel-parity guarantee the sweep PRs rely on. Designed leadings for the
compact steps are a **named follow-up campaign** (own ADR, own screenshots), not this one.

### 2. Mapping table (the sweep contract, PR2–PR5)

| Current px | Count | Target | Notes |
|---|---|---|---|
| 9 / 9.5 / 10 / 10.5 | 40 | `text-10` | 9→10 is +1px on 2 Today micro-labels — eyeball density |
| 11 / 11.5 | 53 | `text-11` | pure rename / −0.5px |
| 12 / 12.5 | 52 | `text-xs` | line-height 1rem kicks in where no `leading-*`; 5 wrapping sites take `leading-snug` |
| 13 / 13.5 | 78 | `text-13` | largest cohort, pure rename / −0.5px |
| 14 / 14.5 | 25 | `text-sm` | LH 1.25rem kicks in — benign, single-line sites |
| 15 / 15.5 | 18 | `text-15` | pure rename |
| 16 | 3 | `text-base` | true no-op (LH 1.5rem = inherited) |
| 17 / 18 | 5 | `text-lg` | +1px on 2 brand marks (askesis/chat.py:202, journals/chat_page.py:335) — flag in PR body |
| 20 / 22 | 5 | `text-xl` | 22→20 = −2px judgment nudge, screenshots required |
| 30 / 32ish | 3 | `text-3xl` | 30px sites carry explicit `leading-[1.12]` — safe; the 32px at calendar components.py:140 is allowlisted (hero pair) |
| 40 / 44 / clamp()×5 | 8 | **allowlist** | permanent exceptions (ledger below) |

Stock-step adoptions (`text-xs`/`text-sm`/`text-lg`/`text-xl`) accept the stock utility's
line-height where no explicit `leading-*` is present — audited as benign per cohort; the
five wrapping-subtitle sites in the 12px cohort take `text-xs leading-snug` in the same
edit (`ui/journals/forms.py:92,411`, `ui/user_entry/forms.py:49`,
`ui/explore/reading_plan.py:576`, `ui/journals/chat_page.py:594`).

### 3. Exception ledger (permanent, count-pinned)

8 sites in 3 files stay arbitrary — deliberate responsive/hero typography, pinned by count
in `scripts/audit_font_sizes.py`:

| File | Count | Why |
|---|---|---|
| `ui/explore/reading_plan.py` | 5 | `clamp()` fluid heroes — deliberate responsive design |
| `ui/calendar/components.py` | 2 | `text-[32px] sm:text-[40px]` hero H1 pair (one line — never half-convert it) |
| `ui/today/page.py` | 1 | 44px planning-board headline (mirrors the `ALLOWED_H1` rationale) |

### 4. Guardrail

`scripts/audit_font_sizes.py` (sibling of `audit_raw_headers.py`) scans every string
constant in production UI code — plus the `static/js/*.js` Tailwind `@source` tree — for
arbitrary `text-[...]` values (variant prefixes included), matching the payload
generically and excluding only the color payloads (`text-*` is ambiguous; enumerating
size spellings proved unwinnable), and reports findings outside the count-pinned
allowlist. Advisory (exit 0) during the
sweep PRs — the shrinking count is each PR body's burndown metric; `--strict` flips on in
PR6. Wired as `./dev quality` check 5c and a CI lint step. The paired `css_freshness` CI
job compiles `input.css` and fails on `output.css` drift, so a sweep can never land with a
stale compiled asset.

## Alternatives Considered

**Mint `text-12` (and `text-14`, `text-16`…) instead of adopting stock utilities** —
rejected. `--text-12: 0.75rem` duplicates `text-xs`'s font-size exactly; two names for one
value is a One Path Forward violation and teaches authors that the stock scale is optional.
The blast radius of adopting `text-xs` is small: 12 of the 52 twelve-pixel sites carry
explicit `leading-*` (immune), and the ~5 wrapping sites get `leading-snug` in the same
edit. Same logic applies at 14/16/18/20/30.

**Add `--text-N--line-height` companions now** — rejected for this campaign. Companions
turn a rename into a rhythm change at 189 sites simultaneously, unreviewable except by
full-app screenshot diffing. Font-size-only tokens keep the sweep pixel-parity; designed
leadings become a separate, visually-reviewed follow-up campaign.

**Semantic names (`text-micro`, `text-meta`, `text-dense`)** — rejected. The house habit is
size-literal (`text-[13px]`); a numeric token (`text-13`) is a zero-thought rename with an
obvious px meaning, while semantic names demand a naming taxonomy nobody has validated and
invite bikeshedding per sweep file. Numeric names also stay honest when a "meta" label is
used for something that is not metadata.

**Do nothing** — rejected. 22 distinct values across 31 files is the measured cost; every
new UI file adds more half-pixel drift, and no tooling stops the 23rd value.

**22px → allowlist instead of `text-xl`** — the −2px nudge on `ui/today/page.py` is a
judgment call requiring screenshots at review. Fallback if rejected: allowlist
`ui/today/page.py` at count 4 (a one-line audit change).

## Consequences

- New UI code uses the named scale; `scripts/audit_font_sizes.py` flags any new
  `text-[Npx]` outside the 8-site ledger (advisory now, strict from PR6).
- The 4 tokens are SKUEL-owned in `input.css` `@theme inline` (ADR-071 ownership model);
  no `@source inline()` safelist is needed — all class literals are statically scanned.
- Line-height behavior at stock-step adoption sites changes only where the mapping table
  says it does, and each such cohort was audited before its sweep PR.
- Verification gate for the whole campaign (checked in PR1): the compiled utility must be
  exactly `.text-10{font-size:.625rem}` — any line-height in the emitted shape breaks the
  no-companion premise and halts the campaign.

## See

- `.claude/skills/ui-css/reference.md` § Typography — the authoring-facing scale + mapping
- `scripts/audit_font_sizes.py` — guardrail + exception ledger
- ADR-071 — SKUEL-owned Tailwind layer (token ownership)
