---
title: "Embedded Forms Fragment — staged behind the PathStep page that dropped it"
updated: 2026-09-20
status: "staged — Mike's ruling 2026-09-20: PLANNED tier, not deletion"
registered: 2026-09-20
ruled: 2026-09-20
trigger: "The forms section returns to the PathStep page (/explore/ps/{uid} loads /learning-loop/ps/{ps_uid}/forms); or a second ruling deletes the fragment pair with the EMBEDS_FORM edge kept"
check: "grep -rn 'learning-loop/ps/.*forms' ui/ static/js adapters/inbound — a consumer outside adapters/inbound/learning_loop_routes.py and ui/learning_loop/embedded_forms.py retires the PLANNED entries"
---

# Embedded Forms Fragment — staged behind the PathStep page that dropped it

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

`GET /learning-loop/ps/{ps_uid}/forms` and `POST /learning-loop/ps/{ps_uid}/forms/{template_uid}/submit`
(`adapters/inbound/learning_loop_routes.py`) render the `FormTemplate`s a PathStep `EMBEDS_FORM`
(`FormTemplateService.get_forms_for_path_step`) as an inline HTMX section through
`ui/learning_loop/embedded_forms.py`, and post a filled form through `FormSubmissionService.submit_form`
with the default audience (so a teacher can read it).

**No page loads the fragment.** The reading-first PathStep page (`ui/explore/ps_detail.py`) loads
`/learning-loop/ps/{uid}/exercises` and `/learning-loop/ps/{uid}/submissions-and-feedback` and left
the forms section out of the redesign (`917946df4`). The route handlers are reachable by URL, so no
liveness tool reports them; the record of their consumer-less state is this file and the two
`PLANNED_METHODS` entries in `scripts/detect_bloat.py`.

**What stays live around it:** the `EMBEDS_FORM` edge and its writer (`link_to_path_step`), the
`FormTemplate` / `FormSubmission` domain, the teacher form pages (`/teaching/forms`,
`/teaching/forms/detail`, `/teaching/forms/submission`) and the forms API. Only the learner-side
inline surface is staged.

**What completes the entry:** a `_learning_loop_section` row on `/explore/ps/{uid}` that `hx-get`s
the fragment (the section collapses to an empty `Div` when a step embeds no form — the handler
already renders that); wire it and delete the registry entries. **What retires it the other way:**
a ruling that learners fill forms from the teacher-shared door alone, after which the two handlers,
`ui/learning_loop/embedded_forms.py` and the entries go together under One Path Forward.

**Why staged, not deleted (ruled 2026-09-20):** the rendering and the submit path are written and
typed against the live forms domain, and an inline form on the step it belongs to is the learning
loop's Phase-2 door for form-shaped exercises — deleting it would make the next surface re-derive
both halves for an edge the ingestion pipeline still writes.
