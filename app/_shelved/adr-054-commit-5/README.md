# ADR-054 Commit 5 — Shelved Legacy Submissions/Journals Surface

Shelved during ADR-054 Commit 5c. Parent commit: `c647a048` (Commit 5b — route surface consolidated onto UserEntry hub).

These files are the pre-ADR-054 route and UI layer for `Submission` / `JeInput` / `JeOutput`. They were superseded by `UserEntryOrchestrator` + `adapters/inbound/user_entry_ui.py` + `adapters/inbound/user_entry_api.py`. Preserved for reference until the follow-up cleanup of extension-factory coupling in `submissions_api.py` / `submissions_sharing_api.py`.

## Contents

### `adapters/inbound/`
- `submissions_routes.py` — DomainRouteConfig wiring for `/submit`, `/submissions/history`, `/gradebook/*` plus registration of five extension factories (progress_report_api, exercise_report_api, submissions_sharing_api, activity_review_ui, batch_transcription_api).
- `submissions_ui.py` — FastHTML routes for the legacy worksheet submission hub (`submit_page`, `/gradebook/upload`, `/gradebook/{uid}` with six HTMX fragment panels).
- `submissions_hub_routes.py` — Three-tab `HomeHub` registration for `/submissions`, plus the `/api/submissions/*/preview` HTMX preview fragments.
- `journals_routes.py` — DomainRouteConfig wiring for `/journals/*` surface.
- `journals_ui.py` — FastHTML routes for journal upload / browse / detail / batch / instruction-upload.

### `ui/submissions/`
- `sharing.py` — `render_sharing_section` + related helpers, only used by the legacy `/gradebook/{uid}` detail page.

## Not shelved

These files remain live at their original paths because the new UI surface or other active code still imports them:

- `adapters/inbound/submissions_api.py`, `submissions_sharing_api.py` — extension factories re-registered from `user_entry_routes.py` (deferred cleanup).
- `ui/submissions/cards.py`, `ui/submissions/forms.py` — used by `user_entry_ui.py` and `user_profile_ui.py`.
- `ui/journals/cards.py`, `ui/journals/components.py`, `ui/journals/forms.py` — used by `user_entry_ui.py`.

The two legacy orchestrators (`core/orchestrator/submissions_orchestrator.py`, `core/orchestrator/journal_orchestrator.py`) were deleted outright in Commit 5c rather than shelved — pure plumbing with no reference value.
