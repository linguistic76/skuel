---
updated: 2026-08-13
---

# MOC + knowledge channel — design rulings

**Ruled** 2026-07-04. **Shipped:** MOC ingestion arc (#506, #507); vault exercise channel
arc (#508, #509, #511 — closed 2026-07-05).

These are RULINGS and DIRECTION, not an implementation plan. The arcs that executed them
are closed; what remains is the reasoning the code and its tests cite.

## The vault map

- **Content vault `0vault/`** — SKUEL's official curriculum. Polished, admin-owned, shared.
  The END of the pipeline.
- **FOUNDER vault `0bsidian/skuel/`** — the workshop. RAW: the beginnings of what may
  appear in `0vault`. SKUEL's relationship here is intimate and cooperative — listening,
  being guided, co-building the enterprise. Private; never leaked into the app at large.
- **Regular user's personal vault** — the Journals surface: periodic notes, activity
  round-trip, reporting and reinforcement across the 6 Activity Domains.

**The FOUNDER/regular line is a RELATIONSHIP line, not a capability line.** The machinery —
knowledge folder, MOC ingestion, sync doorways — is SHARED. Two things differ:

1. The journals instruction set, already in code as `JournalTier.FOUNDER` (three-stage
   DNWF) versus `STANDARD`. **This is THE gating hook — ruled: no new role.**
2. What SKUEL does with what it learns. Founder: how to build and operate SKUEL. Regular
   user: enough understanding to be a better accountability partner.

## Regular-user knowledge channel

- Regular users DO get a knowledge folder — "a space for a User to develop their own
  knowledge." Purpose test for anything built there: it must serve Activity Domain
  reinforcement or Askesis's PS-progression mission. **Not general-purpose PKM.**
- **Intimacy line (ruled):** regular-user knowledge feeds CONTEXT ONLY — the summaries
  Askesis and journals read. No entity extraction, no recommendations generated from it,
  nothing surfaced back. Founder knowledge may inform how SKUEL *behaves*; user knowledge
  only informs how SKUEL sees *that user*.

## MOC

- **First-class, standard, available to FOUNDER and regular users alike.** Honors how
  people naturally write in Obsidian. A MOC's value is usable, malleable grouping.
- **No new EntityType.** SKUEL already defines MOC as EMERGENT — any entity with ORGANIZES
  edges — and names the ORGANIZES Path as the second Path to Knowledge. MOC ingestion gives
  that path its authoring surface.
- Shape: frontmatter marks a file as a MOC; it ingests as a user-owned entity; its links
  become ORGANIZES edges. Editing the file re-draws the edges on the next sync, and
  deletion propagation already handles removals.
- **Dangling MOC links are PLANS, not errors** in a personal vault — a MOC names the shape
  of territory before the content exists, so a mix of real wiki-links and head-only topics
  is legitimate. The content vault keeps strict dangling-target warnings. Two postures, one
  mechanism.
- SKUEL's primary focus is the six **Activity Domain MOCs**. Getting users to THINK in MOCs
  is itself the accomplishment.
- **Founder MOC graduation to `0vault` is always a deliberate manual act.**

## Askesis ↔ Journals (direction)

- **Askesis pulls** the user along a path — progress through a PathStep, then the next.
  Vault understanding is supporting context.
- **Journals let the user guide** the path — the user's own space.
- Together, for a regular user: a space for the user, plus a pull in SKUEL's direction,
  which is the direction the user wants to go.
- "Knowledge is meant to be applied" is the fundamental principle. The regular user's
  problem is rarely not-knowing, it is not-acting — SKUEL is the accountability partner.
- Recurring daily-note reflection lines ("Reflect on what went well today") are **habits,
  not tasks**.

---

## Phase 0 rulings — vault exercise channel

Ruled 2026-07-04 after three correction rounds. These supersede an earlier framing in which
"map this PathStep into your own knowledge map" was to become a standard Exercise modality;
that idea survives only as possible *content*, never as machinery.

### R1 — Decoupling (the arc's central correction)

**MOC machinery and Exercise machinery never reference each other. No code path may know
that a submission "is" a MOC.** Ruled twice in one session:

1. There is no automatic relationship between a MOC and `fulfills_exercise_uid` — the
   uid-collision problem is generic to any vault file carrying that field.
2. An Activity Domain MOC is never *assigned* as an Exercise. An Exercise whose
   instructions say "make yourself a Goals MOC" is still just an Exercise; the MOC the user
   writes is still just a MOC.

The only join is the user's authored `fulfills_exercise_uid:` frontmatter on a particular
file during a particular engagement. Recorded as a durable working agreement.

**A MOC is an anchor, not a deliverable** — gather what you know, link it via an index page,
develop it over time as a discipline. Its home is the living in-progress channel, never a
turn-in's primary frame. **A list comes before a map:** "List your Tasks" is the more
valuable first exercise; a map is what a list can grow into.

### R2 — Submission semantics: status frontmatter + hand in a copy

- **Living entry:** a vault file with `fulfills_exercise_uid:` and `status: in process`
  syncs as ONE entity — deterministic uid, upsert in place, ORGANIZES edges free to
  re-draw, and it **never carries a FULFILLS_EXERCISE edge**. The fulfills field on a
  deterministic-uid vault entry is **declared intent**, stored on the entry and validated by
  the existing authorization guard at first sync — fail loud there, not at submit.
- **`status: submitted` plus a sync is the deliberate turn-in signal.** Submit is a real
  signal after which the user expects direct feedback. Sync files a **frozen copy** through
  the existing turn-in machinery — fresh random-uid node, FULFILLS_EXERCISE {revision},
  Interaction, audience routing. The notebook versus the pages handed to the teacher.
- A copy is filed **only when content changed** since the last copy. Sync never writes into
  user files, so idle re-syncs while still marked `submitted` are no-ops; editing while
  submitted is a re-submission; flipping back to `in process` lets the user revise in peace.
- **The `create_entry` honesty fix this required:** `fulfills_exercise_uid` used to
  force-mint a random uid even when the caller supplied a deterministic one, making the
  upsert branch structurally unreachable. A vault file carrying the field would duplicate a
  submission node on every edit-sync, orphan the prior node's ORGANIZES edges and its
  EntryReport, and inflate the revision counter. Turn-in is now defined as **fulfills AND
  no caller uid**; a deterministic uid plus fulfills routes to the upsert. Revision is the
  sequence of submitted copies.

### R3 — Feedback: TEACHER by default; AI is a manual website option

- The submitted copy routes to the **teacher review queue** — TEACHER_REVIEW pipeline, a
  truthful `submitted` enforced at the service chokepoint, audience machinery routing to
  the reviewing group. Teacher feedback already notifies via `ReportSubmitted`: navbar bell
  plus GradeBook entry reports. Zero new delivery machinery.
- **AI feedback is never sync-triggered.** It is a manual option at `/submissions/exercise`
  or the on-page "Request AI feedback" button. Ruled explicitly: the default is `teacher`.
- **Every Exercise has (should have) a group and teacher associated.** A no-reachable-teacher
  case surfaces as an ERROR in sync results, never a silent drop.

### R4–R6 — settled small rulings

- **Modality:** no new `SubmissionModality` value. The only behavioral branch is
  `Exercise.has_inline_form()`; ingestion leaves modality None.
- **Map rendering** is a MOC-entity concern, not an exercise concern. A user entry with
  ORGANIZES edges renders its ordered children on the existing entry detail page —
  owner-gated, respecting the context-only line.
- **Prompt:** no new template or registry entry. Exercise-submission feedback has no
  PROMPT_REGISTRY template at all — `Exercise.get_feedback_prompt()` is instructions plus
  context notes plus entry content, deliberately transparent.

### R7 — v1 exemplar content

**"List your Tasks"** and **"List your Goals"** — ASSIGNED scope, teacher → group, honoring
the teacher invariant. List before map.

Deliberately NOT shipped: "map this PathStep" (future content authoring); Activity-Domain-MOC
exercises as such — **ruled incoherent**, since an exercise may *ask for* a MOC in its
instructions and that is all; and an open-access rule for unanchored CURRICULUM exercises
(deferred).

## Authoring note

API-minted exercise uids are COLON-form (`exercise:<hex>`), and `fulfills_exercise_uid`
frontmatter is taken RAW by the door — no colon→dot normalization — so users author exactly
the uid every surface shows. Vault-authored CURRICULUM exercises store dots; author dots for
those.

**Related:** `docs/patterns/UNIFIED_INGESTION_GUIDE.md` § MOC files and § Vault exercise
channel.
