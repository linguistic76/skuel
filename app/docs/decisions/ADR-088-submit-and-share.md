---
title: "ADR-088: Submit and Share"
updated: 2026-09-26
status: accepted
category: decisions
tags: [adr, decisions, sharing, submissions, user-entry, groups, visibility, access-control, gradebook]
related: [ADR-038, ADR-040, ADR-042, ADR-053, ADR-054, ADR-085, ADR-086]
related_skills: [journals, learning-loop, security, skuel-search-architecture]
---

# ADR-088: Submit and Share

**Status:** Accepted — founder-ratified 2026-09-24. **Implementation pending:** every decision
below is built by the Submit & Share arc, PRs 1–8. The arc's PR contract table is the ledger of
what has landed; until a PR's row reads `merged`, the code still behaves as the amended records
describe.
**Date:** 2026-09-24
**Deciders:** MCF
**Decision Type:** ☑ Graph Schema  ☑ Pattern/Practice
**Arc:** [Submit & Share — rulings & contract](../roadmap/submission-sharing-arc.md) (rulings R1–R14,
four refinements, 13 PRs).
**Related ADRs:**
- Amends (each note lands with the PR whose code changes the record — see
  [§ Records this ADR amends](#records-this-adr-amends)): [ADR-038](ADR-038-content-sharing-model.md),
  [ADR-040](ADR-040-teacher-exercise-workflow.md), [ADR-042](ADR-042-privacy-as-first-class-citizen.md) §7,
  [ADR-053](ADR-053-groups-first-class-and-unified-sharing.md) §1,
  [ADR-054](ADR-054-user-entry-unified-submissions.md) §3 / §5 / §6 and its YAML audience table,
  [ADR-085](ADR-085-ownership-read-enforcement-contract.md) §2, and the 2026-09-21 ruling in
  [`sharing-http-door.md`](../roadmap/sharing-http-door.md).
- Related to: [ADR-086](ADR-086-universal-owns-and-attends-attendance.md) (its design-only
  `OWNER_OR_ATTENDEE` member has the shape §5 builds — an owner-scoped domain that declares one
  extra audience arm through a new SearchVisibility member; neither exists in code yet).

## Related Skills

For implementation guidance, see:
- [@learning-loop](../../.claude/skills/learning-loop/SKILL.md)
- [@security](../../.claude/skills/security/SKILL.md)
- [@skuel-search-architecture](../../.claude/skills/skuel-search-architecture/SKILL.md)

---

## Context

**What is the issue we're facing?**

SKUEL lets a user hand work to other people in two senses that the graph does not tell apart:
asking a teacher (or AI) for feedback, and letting a group or a person see the work. Both are
written today as the same edge, and access is recorded in two places that disagree. Verified on
`d65f624fd` and the live graph (the arc doc's § Verified ground truth holds the evidence):

- **One edge, two meanings.** `SHARED_WITH_GROUP` is read by the teacher's review queue (under
  the teacher's `OWNS` of the group) *and* by classmates on `/groups` (under their `MEMBER_OF`).
  A turn-in sent "to my teacher" is therefore listed to every member of the group. Curriculum
  turn-ins fall back to `group_default_{admin}`, which everyone who marks a PathStep in progress
  joins, so those turn-ins are visible across the enrolled population.
- **Access recorded twice.** Share links (`SHARES_WITH`, `SHARED_WITH_GROUP`) are one record;
  the `visibility` property is the other. For anyone but the owner, the EntryReport access check
  admits a shared report only on `visibility = shared` *and* a link — a link alone never grants
  access — while the UserEntry detail read ignores both and admits only the owner — so an entry shared with a person shows up as a card on the recipient's Shared page
  and opens as "Submission Not Found". The `team` value is written by the Events form and read
  by nothing.
- **Feedback and shares share one page.** The student's own EntryReports reach the Shared page
  through a self-share, beside work other people shared.
- **No way back.** The revoke half of sharing has service methods and no door (the 2026-09-21
  ruling registered it PLANNED as "never a second share form").

The founder ruled on the whole shape on 2026-09-24 (R1–R14 in the arc doc). This ADR records the
architectural decisions those rulings imply, plus the four refinements the plan made and the
founder signed off with it.

**Constraints:**
- ADR-085 §4: no third audience-policy mechanism — every read goes through the visibility clause
  or `verify_ownership`.
- ADR-013: never infer an entity's kind from its UID spelling.
- One Path Forward: each old path is removed in the PR that replaces it; no aliases.
- The artifacts are the messages (2026-08-01): no chat or message entity.

---

## Decision

### 1. Two verbs: Submit and Share (R1, R2, R3, R9)

- **Submit** asks for feedback — from a teacher or from AI. A submission is private: the
  teacher's verdict and the report land in the submitter's GradeBook and nowhere else. A teacher
  feedback request requires `Pipeline.TEACHER_REVIEW`, so the link that files the request and
  the pipeline that processes it always agree. AI feedback is graded against an exercise, so it
  is offered only with one.
- **Share** lets groups or people see your work. Anyone may share anything they own, at any
  time; no gate requires review first. The only refusals are privacy, not review: an entry whose
  pipeline does not allow sharing (`TRANSCRIBE_AND_STRUCTURE`, `REFERENCE`) or that is marked
  `private: true` cannot be shared, at submit or later. This amends ADR-054 §5 and reverses the
  documented rule that `private` is orthogonal to sharing (it lands in PR 6a). A feedback request is
  Submit, not Share: a `private: true` entry may still ask a teacher for feedback. An `archived` entry
  is shareable too — the share gate's archive refusal for a UserEntry is lifted (PR 6b). The
  encouraged route — submit → feedback → revise → share — is promoted by a nudge and a derived
  "reviewed" badge, never enforced.
- **There is no third verb.** No "post": work shared with a group is a share.
- **Feedback on your own work is not a share.** Reports, revision requests and activity reports
  live in the GradeBook only; they never appear on the Shared page.
- **A vault note is a draft.** Its `audience:` does nothing until `status: submitted` files a
  frozen copy, with or without an exercise.

### 2. Two group-link kinds: `SUBMITTED_TO_GROUP` and `SHARED_WITH_GROUP` (R5, Refinement 1)

```
entry ──SUBMITTED_TO_GROUP──▶ Group ◀─OWNS── teacher        feedback request → review queue only
entry ──SHARED_WITH_GROUP───▶ Group ◀─MEMBER_OF|OWNS─       share → every member
```

- `SUBMITTED_TO_GROUP` is a feedback request to the teachers who own the group. It grants group
  members nothing. Every teacher-side reader — e.g. the review queue and its detail, the
  dashboard, the teacher's group pages, the exchange in teacher mode, the forms review; PR 1's
  reader census is the full list — reads it through `(teacher)-[:OWNS]->(group)`.
- `SHARED_WITH_GROUP` is a share with every member. The curriculum direction (Exercise, PathStep,
  LearningPath → group, ADR-053) keeps this edge unchanged.
- Every FormSubmission group target is a feedback request.
- **Why two kinds, not a marker property on one edge:** the group revoke deletes any
  `SHARED_WITH_GROUP` between an entity and a group with no property predicate, so with a marker
  "Stop sharing" would silently cancel a feedback request. With two kinds it structurally cannot.
  A reader that forgets to switch fails closed (it hides) instead of leaking. Relationships are
  verbs.

### 3. Links are the only audience record (R4, R6)

- `SHARES_WITH` (person), `SHARED_WITH_GROUP` (group) and `SUBMITTED_TO_GROUP` (feedback request)
  are the whole record of who may see an entry. **A link alone grants access** — no property has
  to agree with it.
- **Two readers, never crossed.** The **audience fragment** decides what a non-owner may open as
  a recipient: a direct `SHARES_WITH` reaches them, or they reach an **active** group
  (`g.is_active = true`, strict) the entry is `SHARED_WITH_GROUP` to, through `MEMBER_OF` or
  `OWNS`. The **teacher gate** (§2: `SUBMITTED_TO_GROUP` under the teacher's `OWNS` of an active
  group) decides what a teacher may review. Neither admits through the other's link — a feedback
  request never makes an entry openable as a share, and a share never puts it in a queue.
- The audience fragment holds no owner arm. The visibility clause ORs it with the owner arm
  (`ownership_property`) for `OWNER_OR_AUDIENCE` (§5); the Shared page and the `/groups` list
  reuse the fragment alone, so whatever is listed can be opened.
- **Recipients see a basic card:** title, description, from, date, the derived badge and a link
  to open the file. Never the feedback, the exchange or the teacher's verdict: the recipient's
  response (the card and the `.md` download) never renders `status`, `processed_content`,
  reports or the exchange. The read behind it is the ordinary by-UID read; the owner-versus-
  audience branch decides what is shown.

### 4. `visibility` means public or not (R4)

`visibility` keeps two values: `private` and `public` (portfolio, TEACHER-gated). SHARED and TEAM
are deleted from the enum and from the graph; nothing may write or read them. `public` has no
reader yet (a portfolio listing is a non-goal of this arc), which keeps `set_visibility` PLANNED
exactly as the 2026-09-21 ruling staged it — now PUBLIC-only.

### 5. `read_visibility` beside `search_visibility` (Refinement 4)

- `DomainConfig` gains a declared `read_visibility`, defaulting to `search_visibility`.
  `get_visible_to_user` composes `read_visibility`; SearchRouter keeps composing
  `search_visibility`.
- A new `SearchVisibility` member, `OWNER_OR_AUDIENCE`, renders the owner arm
  (`ownership_property`) OR §3's audience fragment. UserEntry declares
  `read_visibility = OWNER_OR_AUDIENCE` and keeps search owner-only.
- **Why not widen search:** UserEntry's search fields include `processed_content`, and a search
  row carries `status` — the teacher's verdict. Search results over other people's entries would
  hand recipients exactly what §3 withholds. Shared items are discovered on the Shared page.
- **Why this is not a third mechanism (ADR-085 §4):** it is the same clause builder with one
  more declared member, composed through the same by-UID chokepoint. What changes is ADR-085 §2's
  "a direct read and a search of the same domain agree by construction": they still agree for
  every domain that declares no `read_visibility`, and UserEntry diverges by declaration.
- **The fragment has one home.** §3's audience fragment is one function beside
  `build_search_visibility_clause`, and the clause's `OWNER_OR_AUDIENCE` branch composes it. The
  two list readers that return other people's entries (the Shared-with-you group half and the
  `/groups` list) compose that same function, never a copy or a re-typed pattern — they replace
  today's hand-rolled `MEMBER_OF` joins in the sharing backend. ADR-085's audit ("grep the
  clause's composers") therefore also greps the fragment's composers.

### 6. "Your wall" is derived from the links (R7)

The Shared page has two sides. *Shared with you* lists entries whose links reach you. *Your wall*
lists what you shared and with whom, each audience with a Stop sharing control — derived by
reading your entries' `SHARES_WITH` / `SHARED_WITH_GROUP` links. There is no wall node and no
second record. Your wall is visible to you only. Stop sharing removes a share link and can never
touch a `SUBMITTED_TO_GROUP` feedback request.

### 7. Person shares require co-membership, excluding the default group's roster (R8, Refinement 3)

- You may share with a person only when you share a group with them. In the vault the person is
  named `user:<username>`.
- Co-membership through the default group does not count: everyone who marks a PathStep in
  progress joins `group_default_{admin}`, so "people in my groups" would otherwise list the
  enrolled platform. The default group's **owner** stays a candidate, and the default group itself
  stays offered as a *group* target.
- An unknown username and a non-co-member get the same not-found error, so the door does not
  disclose who exists.
- The default group records its owner only through its `:OWNS` edge. Identify the owner by that
  edge, never by the uid suffix (ADR-013). Until a declared marker exists, the default group
  itself is recognised by the one existing `STARTS WITH 'group_default_'` site (SKUEL034 leaves
  `startswith` out of scope by ruling); a new consumer reuses that site, never a second spelling.
- Forms' `share_with_admin` stays exempt from co-membership (its own question is open in the
  form-submission recipient-read case file).

### 8. `teacher:<group_uid>` — per-teacher targeting (Refinement 2)

A student in several classes can already direct a feedback request to one teacher's group (the
review queue pins the read side of this). That route is named `teacher:<group_uid>`: a
`SUBMITTED_TO_GROUP` to that one group. `teachers` means all my teachers: the exercise's groups
that I belong to; when that set is empty and the exercise is a curriculum exercise (never assigned
to a group), my default group (the curriculum fallback, ruled 2026-07-04, kept — under
`SUBMITTED_TO_GROUP` it reaches only the group's owner, so it no longer leaks); with no exercise,
every group I am a student of. `group:<uid>` is always a share: it never files a feedback
request.

### The one audience vocabulary

One parser and applier, used by the web form, the JSON API and the vault:

| Value | Writes |
|---|---|
| `teachers` | `SUBMITTED_TO_GROUP` to the exercise's groups I belong to (a curriculum exercise: my default group); with no exercise, to all my student groups |
| `teacher:<group_uid>` | `SUBMITTED_TO_GROUP` to one group |
| `group:<uid>` | `SHARED_WITH_GROUP` |
| `user:<username>` | `SHARES_WITH`, only with a co-member (§7) |
| `public` | `visibility = public` (TEACHER-gated) |
| `private` | no links — exclusive: it combines with no other value |

Lists are accepted; case is preserved (usernames match exactly). `private` is exclusive: a list that
combines it with any other value (say `[private, user:bob]`) is a parse error, never a silent
choice of which wins.

---

## Alternatives Considered

### Alternative 1: One edge with a per-link marker (teacher-only | all members)
**Description:** Keep `SHARED_WITH_GROUP` for both acts and mark each link with its audience.
This was the founder's first ruling, before the plan examined the revoke path.
**Pros:** no new relationship type; no migration of reader Cypher beyond a predicate.
**Cons:** every reader must remember the predicate, and one that forgets leaks; the group revoke
deletes the edge regardless of the marker.
**Why rejected:** Stop sharing would silently cancel a feedback request, and the failure mode of
a forgotten predicate is a leak rather than a hidden row.

### Alternative 2: One verb — a post is a submission with no response requested
**Description:** Everything is a submission; sharing with a group is a submission that asks for
nobody's feedback.
**Pros:** one door, one form.
**Cons:** the teacher's queue and the Shared page would each have to filter the other's traffic
out of one stream; "private feedback" and "public work" stay entangled.
**Why rejected:** the founder reframed the same day — submitting asks for feedback, sharing lets
people see; R1 retires the one-verb ruling.

### Alternative 3: Widen UserEntry search to its audience
**Description:** Let `search_visibility` be `OWNER_OR_AUDIENCE`, so search and by-UID reads keep
agreeing by construction.
**Pros:** no new DomainConfig member; ADR-085 §2 stays literally true.
**Cons:** search rows carry `status` and match on `processed_content`.
**Why rejected:** it violates R6 — a recipient would see the teacher's verdict and the processed
feedback text through search.

### Alternative 4: A share gate — only reviewed work may be shared
**Why rejected:** R2. The route is encouraged, not enforced.

### Alternative 5: A stored wall (a node per share event)
**Why rejected:** it is a second record of the audience, which R4 forbids; the links already
say what was shared and with whom.

### Alternative 6: Person candidates = everyone in any of my groups
**Why rejected:** the default group would make that the whole enrolled platform (Refinement 3).

---

## Consequences

### Positive Consequences
- ✅ A classmate can no longer see a turn-in that was sent to the teacher; the review queue loses
  nothing.
- ✅ Access has one record. A person share opens for its recipient; the property that had to agree
  with it is gone.
- ✅ Stop sharing cannot cancel a feedback request.
- ✅ The teacher queue holds only feedback requests and the Shared page holds only shares — each
  page answers one question.
- ✅ The web form, the JSON API and the vault speak one audience vocabulary.

### Negative Consequences
- ⚠️ ADR-085 §2's "agree by construction" becomes "agree unless the domain declares otherwise";
  a reviewer must now check two declared members on UserEntry.
- ⚠️ A second relationship type between an entity and a group: every teacher-side reader and every
  fixture that seeds a turn-in switches in the PR that introduces the kind (or its recorded split).
- ⚠️ Graph migrations run on AuraDB across the arc — the edge re-type, the visibility collapse, the
  student self-share deletion, the exchange snapshot backfill and the vault-copy provenance. Each
  runs with the app stopped, before the new code serves, followed by a census that must read 0
  (the arc doc's Migrations convention).
- ⚠️ ADR-085's two-point audit gains a third grep target: the audience fragment's composers.
- ⚠️ Recognising the default group still leans on its uid prefix until a declared marker exists.

### Neutral Consequences
- ℹ️ `public` keeps a writer and gains no reader in this arc.
- ℹ️ FormSubmissions keep their current Shared-page card; opening one as a recipient is deferred
  (the arc registers a case file).

### Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| A reader not switched to `SUBMITTED_TO_GROUP` | Medium | Low — the row hides (fails closed) | PR 1's reader census; the queue's integration tests |
| The visibility enum shrinks before the graph is rewritten | Low | High — reads of `shared` rows raise | The migration runs on AuraDB with the app stopped; a census after the restart reads 0 |
| A recipient card leaks feedback | Low | High | The recipient response carries no report content (the card and the download render neither `status` nor `processed_content`); the access matrix pins it |
| Per-person shares widen past co-membership through a side door | Low | Medium | Co-membership is enforced where person links are written (resolver + forms), not at one door |

---

## Implementation Details

### Code Location
Planned, per PR — the arc doc's per-PR sections hold the file-level scope and are re-verified by
each PR's own census. In outline: the relationship enum and the sharing backend/service (PR 1),
the visibility enum and its writers (PR 2a), the report and notification services (PR 2b, PR 3),
the exchange reads (PR 4a/4b), the visibility clause and DomainConfig (PR 5), the audience
resolver (PR 6a), the share routes and the Shared page (PR 6b), the derived badges and the
GradeBook nudge (PR 6c), the submit form (PR 7) and the vault door (PR 8).

### Testing Strategy
- [ ] Integration: `/groups` hides turn-ins and still shows shares; the review queue still lists
  them (PR 1).
- [x] Integration: an access matrix — ex-member, deactivated group, revoked share and
  SUBMITTED-only teacher all get not-found; a recipient response carries no report content (PR 5 —
  `tests/integration/routes/test_gradebook_audience_read.py`).
- [x] Unit: the visibility clause parametrized over every SearchVisibility member (PR 5 —
  `tests/unit/test_search_visibility_scoping.py`).
- [ ] Unit: the audience parser matrix, co-membership and the uniform error (PR 6a).
- [ ] Manual: the arc-close walk-through as a student and a second account (arc doc § Verification).

---

## Records this ADR amends

No record below is edited by the PR that adds this ADR. Each gets its "amended by ADR-088" note in
the PR whose code makes the change true.

| Record | What it decides today | What ADR-088 changes | Note lands in |
|---|---|---|---|
| ADR-038 — Content Sharing Model | A three-level model (private / shared / public) over a four-value enum with TEAM reserved; "Shared" access = `visibility` SHARED **and** a `SHARES_WITH`; the revoke/access-list service half; the 2026-09-21 "never a second share form" API ruling; no notifications | Two levels (§4) — PR 2a; the access check retired — PR 2b; a link alone grants access (§3) — PR 5; the revoke half gets its door, the access list is replaced by Your wall (§6), a person share rings a bell — PR 6b | PR 2a, PR 2b, PR 5, PR 6b |
| ADR-040 — Teacher Exercise Workflow | Header note: the review queue is `SHARED_WITH_GROUP` + `pipeline = 'teacher_review'`; TEAM reserved for a future phase | The queue reads `SUBMITTED_TO_GROUP` under the teacher's `OWNS` (§2); TEAM deleted (§4) | PR 1 (queue), PR 2a (TEAM) |
| ADR-042 §7 — Group sharing, membership-level access | Every current member of a group gets access to what is shared with it | A feedback request grants members nothing (§2); a share reaches members **and** owners of an active group (§3) | PR 1, PR 5 |
| ADR-053 §1 — Retire FOR_GROUP, unify on SHARED_WITH_GROUP | §1: `SHARED_WITH_GROUP` is the one teacher→group curriculum mechanism; the header's ADR-054 note extends it symmetrically to student→teacher turn-ins | The curriculum half of §1 is unchanged; turn-ins get their own kind — the note lands beside that header note | PR 1 |
| ADR-054 §3 — Audience, declared at submit time | Four audience options (teacher / group / peer / public) in any combination | Two verbs (§1); teacher → `SUBMITTED_TO_GROUP`; `teacher:<group_uid>`; co-member person shares; one vocabulary | PR 1, PR 6a |
| ADR-054 §3 — the YAML `audience:` table | `teachers` (the default) → every group I am a student of, on every submission-shaped pipeline | `teachers` → `SUBMITTED_TO_GROUP`; new rows `teacher:<group_uid>` and `user:<username>`; lists accepted; a vault note's `audience:` applies only to the frozen copy `status: submitted` files | PR 6a (rows), PR 8 (drafts) |
| ADR-054 §5 — Journal input → output | The pipeline policy gates the *submit-time* audience, "not the entry's lifetime audience" | The share door applies the same gate for the entry's lifetime, and refuses an entry marked `private: true` — which reverses the documented rule that `private` is orthogonal to sharing | PR 6a |
| ADR-054 §6 — Review queue and teacher authority | The queue is `SHARED_WITH_GROUP` + pipeline; teacher authority collapses into the EntryReport access check | The queue is `SUBMITTED_TO_GROUP`; the access check is retired and report detail is an owner read | PR 1, PR 2b |
| ADR-085 §2 — `get_visible_to_user` is THE audience-aware by-UID read | "a direct read and a search of the same domain agree **by construction**"; "Callers pass the domain's `search_visibility`" | Callers pass the domain's `read_visibility` (default `search_visibility`); UserEntry diverges by declaration (§5) | PR 5 |
| `sharing-http-door.md` — the 2026-09-21 per-method ruling | The revoke / access-list half is PLANNED as a door on existing edges, never a second share form; `set_visibility` waits on the PUBLIC reader | A Share and Stop-sharing door on a user entry (R2); both revoke methods go live; the two access-list methods are deleted (Your wall replaces them); `set_visibility` stays PLANNED, PUBLIC-only; share reconciliation on re-sync is dissolved by §1's drafts | PR 2a, PR 6b, PR 8 |

**Also contradicted — found when the plan was verified (2026-09-24), outside the list above.** Each
gets its note with the PR that falsifies it:
- ADR-042 §3 ("`SHARES_WITH` is the sole access gate") and §8 (names the EntryReport access check
  and the access-list method) — PR 2b, PR 6b.
- ADR-054 §4 ("`FULFILLS_EXERCISE` + `SHARED_WITH_GROUP` is an exercise turn-in"), its Consequences
  ("post to a group feed") and its Postscript (the queue on `SHARED_WITH_GROUP`) — PR 1, PR 6a.
- ADR-038 §4 ("Only Completed Reports Shareable"): for a UserEntry the share gate refuses only
  `archived`, and R2 lifts that (§1) — PR 6b.

---

## Future Considerations

### When to Revisit
- **Peer responses** (the next arc, R14) — it also revisits the 2026-08-01 ruling that peer
  feedback joins the GradeBook as a Source filter
  ([`feedback-loop-staged-directions.md`](../roadmap/feedback-loop-staged-directions.md) §1).
- **A public portfolio reader** — the first reader of `visibility = public`, and what
  `set_visibility` waits on.
- **Visiting someone else's wall** — Your wall is owner-only until then.

### Evolution Path
- Group pages, unread counts and topic subscriptions are future work; group shares ring no one.
- A declared default-group marker would replace the uid-prefix recognition in §7.

### Technical Debt
- [ ] A FormSubmission shared with a person still cannot be opened by its recipient —
  [`form-submission-recipient-read.md`](../roadmap/form-submission-recipient-read.md).

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2026-09-24 | MCF | Accepted with the Submit & Share arc plan (rulings R1–R14, refinements 1–4) | 1.0 |
| 2026-09-25 | MCF | PR 6a landed the one vocabulary (§7, §8, § The one audience vocabulary): `AudienceSpec` + `AudienceResolver`, R8 co-membership at every person-share writer, the `private: true` refusal (the ADR-054 §5 amendment) | 1.1 |
