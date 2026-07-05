"""Entity detail-page href resolution — one mapping for cross-type surfaces.

Graph-driven surfaces (MOC maps, ORGANIZES card grids) hold children of ANY
EntityType, so they can't hardcode a single href template. This module owns
the entity_type → detail-URL mapping; entity kind comes from the node's
``entity_type`` field (never sniffed from the UID — ADR-013).

Detail URL shapes verified against live route registrations:
    Activity (6)      /{plural}/detail?uid=   (activity_ui_factory)
    Ku / PathStep     /explore/{ku|ps}/{uid}  (learning_loop_routes)
    LearningPath      /lp/{uid}               (pathways_ui)
    Exercise          /exercises/get?uid=     (student detail page)
    UserEntry         /gradebook/{uid}        (user_entry_ui)
    Reports/Revisions /{plural}/detail?uid=   (gradebook sub-pages)
    FormSubmission    /my-forms/detail?uid=   (form_submissions_ui)

Types with no detail page (Resource, activity templates, FormTemplate,
Interaction, LifePath) resolve to ``None`` — the caller decides the
fallback.
"""

from __future__ import annotations

_QUERY_PARAM_DETAIL: dict[str, str] = {
    "task": "/tasks/detail",
    "goal": "/goals/detail",
    "habit": "/habits/detail",
    "event": "/events/detail",
    "choice": "/choices/detail",
    "principle": "/principles/detail",
    "entry_report": "/entry-reports/detail",
    "activity_report": "/activity-reports/detail",
    "revised_exercise": "/revised-exercises/detail",
    "exercise": "/exercises/get",
    "form_submission": "/my-forms/detail",
}

_PATH_PARAM_DETAIL: dict[str, str] = {
    "ku": "/explore/ku",
    "path_step": "/explore/ps",
    "learning_path": "/lp",
    "user_entry": "/gradebook",
}


def entity_detail_href(entity_type: str | None, uid: str) -> str | None:
    """Detail-page URL for an entity, or ``None`` when no detail page exists."""
    if entity_type in _PATH_PARAM_DETAIL:
        return f"{_PATH_PARAM_DETAIL[entity_type]}/{uid}"
    if entity_type in _QUERY_PARAM_DETAIL:
        return f"{_QUERY_PARAM_DETAIL[entity_type]}?uid={uid}"
    return None


__all__ = ["entity_detail_href"]
