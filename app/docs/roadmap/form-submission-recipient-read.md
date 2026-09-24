---
title: "Form-Submission Recipient Read — a Form Shared With You Still 404s"
updated: 2026-09-24
status: "deferred — a non-goal of the Submit & Share arc, registered by its PR 0"
registered: 2026-09-24
ruled: 2026-09-24
trigger: "the Submit & Share arc's PR 5 has merged (the audience fragment and read_visibility exist to reuse) AND (a form is shared with a person in real use OR the first multi-user deployment)"
check: "behavioural: a MEMBER recipient holding a SHARES_WITH edge gets the not-found slot from /my-forms/detail/content?uid=<fs> (200 + the R6 card once built); declaration: grep -n 'read_visibility=SearchVisibility.OWNER_OR_AUDIENCE' core/services/forms/form_submission_service.py; real use: MATCH (:User)-[s:SHARES_WITH]->(:FormSubmission) RETURN count(s) (0 on 2026-09-24)"
---

# Form-Submission Recipient Read — a Form Shared With You Still 404s

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

## The defect

A FormSubmission shared with a person is listed on that person's Shared page and cannot be opened by
them. Verified on `d65f624fd`:

- **The share is written.** `_share_on_submit` (`form_submission_service.py:194`) calls
  `UnifiedSharingService.share`, which MERGEs `(recipient)-[:SHARES_WITH]->(submission)`.
- **It is listed.** `/profile/shared` → `get_shared_with_me` → the inbox query matches every
  `SHARES_WITH` target with no entity-type restriction, so the form renders the same card as a
  shared UserEntry.
- **It does not open.** The card's View link is `/my-forms/detail?uid=` (`entity_detail_href`), whose
  fragment `/my-forms/detail/content` calls `FormSubmissionService.get_submission`
  (`form_submission_service.py:284`) — a bare owner-equality check with no audience branch — so the
  recipient gets the not-found slot. The JSON read, `/api/form-submissions/get`, refuses the same way.
- **Every person-recipient's Shared-page card opens as not-found,** including the admin reached
  through `share_with_admin`.
- **A REGISTERED or MEMBER recipient has no door at all.** Today a TEACHER recipient can open the
  form at the TEACHER-gated `/teaching/forms/submission` (and sees it on `/teaching/forms/detail`):
  `_teacher_audience_predicate` (`forms_backends.py:61`) admits a direct `SHARES_WITH` from the
  teacher as well as a group share to an active group the teacher owns. **The arc's PR 1 removes that
  `SHARES_WITH` arm** (a person share is never a review grant — R3, ADR-088 §3), so from PR 1 on a
  teacher named by person has no door either. Any ADMIN skips that gate
  (`teaching_forms_ui.py:371`), which covers the `share_with_admin` recipient. The
  `verify_teacher_access` docstring and refusal wording (`form_submission_service.py:321-346`,
  `teaching_forms_ui.py:385`) describe a group-only gate and are stale against that predicate.
- FormSubmission's DomainConfig declares no `search_visibility` (derived OWNER_ONLY).

**Live, 2026-09-24:** 1 FormSubmission, with 0 person edges and 0 group edges — the defect is latent.
The whole gap is the owner-only `/my-forms/detail` read, which is the only door any person-recipient
has once PR 1 lands (an ADMIN keeps the teaching pages through the role bypass).

## Why it is deferred

The [Submit & Share arc](submission-sharing-arc.md) builds the recipient read for **UserEntry**
only: its PR 5 adds the `OWNER_OR_AUDIENCE` read visibility and the R6 recipient card, and its PR 6b
keeps forms on the Shared page as they are today. "Form submissions on the wall, and a form
recipient read" is one of that arc's non-goals
([`submission-sharing-arc.md` § Non-goals](submission-sharing-arc.md#non-goals-this-arc)); ADR-088
records it as technical debt.

## The shape of the fix, once PR 5 exists

FormSubmission declares `read_visibility = OWNER_OR_AUDIENCE`; the detail read goes through
`get_visible_to_user` (one chokepoint, ADR-085) and branches owner vs audience; a recipient sees
the R6 basic card — title, description, from, date and a link to the work — never the review.
Three questions to answer first:

1. **Is there a group half?** Since the arc's PR 1, every FormSubmission group target is a
   `SUBMITTED_TO_GROUP` feedback request, which grants group members nothing. If forms never get a
   `SHARED_WITH_GROUP` share, the recipient read is person-only.
   - **A cost that PR 1 opened (2026-09-24):** the teacher gate
     (`_teacher_audience_predicate`, `forms_backends.py`) reads the feedback request alone — a
     `SHARES_WITH` from a teacher named in `recipient_uids` is a share, never a review grant
     (R3, R5). Until this recipient read exists, a teacher named by person has **no door** to
     the form: not the gate, not the list, not the count.
2. **What is `share_with_admin`?** It writes a person share to the admin, and the arc's PR 6a keeps
   it exempt from co-membership. The admin can already read the submission through the teaching
   pages; the open question is whether that share belongs on the admin's Shared page at all, or —
   under R3, where a request for feedback belongs in the teacher's queue — should become a feedback
   request instead.
3. **What does "the file" show?** A form's work is its responses; the card links to them and never
   to a teacher's review of them.

## Named cost

Until this is built, sharing a form with a person gives them a card they cannot open and — from the
arc's PR 1 on, teachers included — no other door; only an admin recipient can still reach the
submission, through the teaching pages. With one student in the live graph it is latent; with a second user it
is a broken promise on a page the arc makes more prominent.
