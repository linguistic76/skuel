# ADR-054 Commit 5c Stragglers

Shelved: 2026-04-15

These four files were the leaf API/protocol files for the old submissions
surface. Their sole orchestrator (`submissions_routes.py`) was shelved in
commit 5c (`_shelved/adr-054-commit-5/`), but these were missed.

- `submissions_api.py` — upload, list, process, download, content management
- `submissions_sharing_api.py` — share, unshare, visibility, portfolio
- `progress_report_api.py` — progress report generation endpoints
- `submission_protocols.py` — ISP protocols consumed by the above three

Replaced by: `adapters/inbound/user_entry_api.py` + `user_entry_routes.py`
and `core/ports/user_entry_protocols.py`.
