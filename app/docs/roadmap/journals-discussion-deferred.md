---
updated: 2026-08-14
---

# Journals Discussion — Deferred Work (post-P3)

**Status:** the discussion-first arc (P1 → P2 → P3) is **complete and merged**
(#627, #633–#636, #638–#640, 2026-07-13). The three items below were consciously
scoped **out** of that arc and deferred with rulings. They are **not regressions
and not bugs** — each is a follow-on refinement waiting on its own trigger.

- **Arc SoT:** `docs/roadmap/done/journals-discussion-first.md`
- **Governing ADR:** `docs/decisions/ADR-078-discussion-sessions-stored-not-understood.md`
- **P3 choices doc:** `docs/roadmap/done/journals-discussion-storage-p3.md` (decisions 4 & 5)
- **Privacy commitment:** `docs/decisions/ADR-073-journals-zero-persistence-vault-memory.md`; `docs/decisions/ADR-042-privacy-as-first-class-citizen.md` (encryption)

---

## 1. File-content prompt weighting  *(deferred — and largely dissolved)*

**What.** When a discussion is grounded in a processed file (the file/audio door),
how heavily should that file's content weigh against the other grounding sources
(canon, personal vault, UserContext) in the prompt?

**Why deferred.** P3 changed **zero** prompt composition (P3 decision 5). The
opt-in-persistence realignment also **weakened the original motivation**: saving
only what the user deliberately keeps yields a high-signal corpus by construction,
so there is no flood of auto-saved noise that would need weight-sorting. The
problem the weighting was meant to solve mostly **dissolves** under opt-in.

**Where it stands today.** Grounding is assembled by the canon/vault retrieval
path feeding `run_discussion` / `run_follow_up` (`core/services/journal/`); file
content enters as the opening user turn (source→output pair) and as follow-up
context — it is not specially weighted or de-weighted.

**What "done" looks like (if ever).** A **measured** refinement, not a guess:
prove the success metric moved before/after
any weighting change. Likely trivial or unnecessary; only pick up if real usage
shows file-grounded discussions drift.

**Trigger.** Observed quality problem in file-grounded discussions. No dependency.

---

## 2. Per-book shelf picker on the upload form  *(UI convergence — separate arc)*

**What.** The **typed** door's source panel lists every shelved canon book as an
individual checkbox (`_landing_source_panel`, `ui/journals/chat_page.py`), so the
user composes the session's exact canon scope (C3: none / some / whole shelf). The
**file/audio upload** form has only **coarse booleans** (`summon_canon` /
`summon_vault`); a summoned upload draws the **whole shelf** (`canon=[]`).

**Why deferred.** P3 decision 4 explicitly kept this out: "Not in P3: a per-book
shelf picker on the upload form (UI convergence, separate arc)." The stored
`source_selection` already models per-book scope (`{"canon":[…], "canon_on":…,
"vault":…}`), so the data shape is ready — only the upload UI is coarse.

**Where it stands today.** File-door saves record `{"canon": [], "canon_on":
summon_canon, "vault": summon_vault}` (whole-shelf when canon is on). The typed
door records the checked `resource_uids`.

**What "done" looks like.** The upload form grows the same per-book checkbox panel
(reuse `_landing_source_panel`); the upload route threads the checked
`canon_book_uids` through to `FileOutputFragment` / the composer exactly as the
typed door does, so a saved file chat records a scoped `source_selection`.

**Trigger.** Product decision that file-grounded discussions need book-level scope.
Self-contained UI + route wiring; no new storage.

---

## 3. At-rest encryption of discussion turns  *(ADR-042 — discussions prioritized)*

**What.** `:ConversationTurn.content` (and the stored source text of a saved file
chat) is **plaintext at rest** in Neo4j until ADR-042 field-level encryption lands.

**Why deferred.** ADR-078 §6: this is the **same mechanism** of residual exposure
that doorway notes and periodic notes already carry — a known, documented residual,
not a regression introduced by the discussion store. It joins the existing ADR-042
field-level-encryption backlog rather than getting a bespoke scheme.

**Prioritization ruling (ADR-078 §6).** Sensitivity is **not** equivalent: a
doorway note is a deliberate, curated artifact, whereas a freeform discussion is
more intimate and less considered. So discussion turns are a **candidate to
prioritize first** within the ADR-042 work — not merely lumped in. Opt-in save
means *less* is stored, which only helps.

**Where it stands today.** Turn content and stored source text are written and read
back as plaintext (`ConversationBackend`); operator-level DB access can read them
exactly as it can read doorway/periodic notes today.

**What "done" looks like.** Field-level encryption per the ADR-042 plan, applied to
discussion turn content (and stored source text) — ideally first in that phase.

**Trigger + dependency.** The ADR-042 encryption phase. Blocked on that work; the
ruling here is only the **ordering** (discussions first).

---

## Not on this list (already resolved / out of scope)

- **Auto-saving anything** — rejected; persistence is opt-in, full stop (ADR-078 §1/§5).
- **Understanding wiring for discussions** — permanently out; the wall holds (ADR-078 §2).
- **Askesis adoption of the shared store** — its own consented migration arc (ADR-078
  "Learning from Askesis"); the neutral seams (`kind`, `HAS_SESSION`) exist so it *can*,
  but Askesis is untouched here.
