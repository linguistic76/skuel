"""
Activity Template authoring routes (teacher-only).

Adds the UI counterpart to the existing JSON CRUD at
``/api/pathstep-{domain}-templates/*``. Layout per the scoping decision:

- Panel fragment on the PS detail page (HTMX-loaded):
  ``GET  /teaching/ps/{ps_uid}/templates``  — list templates by domain.
- Full-page create:
  ``GET  /teaching/ps/{ps_uid}/templates/{domain}/new``
  ``POST /teaching/ps/{ps_uid}/templates/{domain}/new``
- Full-page edit:
  ``GET  /teaching/ps/{ps_uid}/templates/{domain}/edit?uid=...``
  ``POST /teaching/ps/{ps_uid}/templates/{domain}/edit?uid=...``
- Inline detach (HTMX, returns refreshed panel):
  ``POST /teaching/ps/{ps_uid}/templates/{domain}/detach?uid=...``

All routes are TEACHER+ gated. On create the route MERGEs the
``HAS_*_TEMPLATE`` edge between the PS and the new template; on detach the
edge is removed (the template node stays — detaching is an authoring action,
not a delete). To fully delete a template node, use the JSON CRUD API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fasthtml.common import Div
from starlette.responses import RedirectResponse

from adapters.inbound._template_form_parsing import parse_template_form_body
from adapters.inbound.auth import make_service_getter, require_authenticated_user
from adapters.inbound.auth.roles import UserRole, require_role
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from core.ports import ActivityTemplateOperations
from core.services.conversion_service import ConversionServiceV2
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.uid_generator import UIDGenerator
from ui.components import ButtonT
from ui.layouts.base_page import BasePage
from ui.patterns.error_banner import render_error_banner
from ui.patterns.page_header import PageHeader
from ui.primitives import ButtonLink
from ui.teaching.templates_forms import (
    DOMAIN_SPECS,
    DomainSpec,
    build_create_form,
    build_edit_form,
)
from ui.teaching.templates_panel import (
    PANEL_DOMAINS,
    render_templates_panel,
)
from ui.tokens import Container

if TYPE_CHECKING:
    from services_bootstrap import Services

logger = get_logger("skuel.routes.templates_ui")


# ----------------------------------------------------------------------------
# Service mapping
# ----------------------------------------------------------------------------
# Maps the URL ``{domain}`` segment to the Services attribute holding the
# matching template service. Kept here (not in the panel/forms files) so the
# UI modules don't depend on the bootstrap container.

_DOMAIN_TO_SERVICE_ATTR: dict[str, str] = {
    "task": "task_templates",
    "goal": "goal_templates",
    "habit": "habit_templates",
    "event": "event_templates",
    "choice": "choice_templates",
    "principle": "principle_templates",
}

_DOMAIN_UID_PREFIX: dict[str, str] = {
    "task": "task-template",
    "goal": "goal-template",
    "habit": "habit-template",
    "event": "event-template",
    "choice": "choice-template",
    "principle": "principle-template",
}


def create_templates_ui_routes(
    _app: Any,
    rt: Any,
    services: Services | None,
    _sync_service: Any = None,
) -> None:
    """Register the teacher-facing template authoring routes.

    No-op (with a warning) if any of the 6 template services is missing —
    bootstrap may run in a partial mode that omits the template subsystem.
    """
    if services is None:
        logger.warning("Template UI routes registered without services")
        return

    raw_services = {
        domain: getattr(services, attr, None) for domain, attr in _DOMAIN_TO_SERVICE_ATTR.items()
    }
    if any(s is None for s in raw_services.values()):
        logger.warning(
            "Template UI routes registered, but one or more template services is None "
            "— skipping registration"
        )
        return
    template_services: dict[str, ActivityTemplateOperations] = cast(
        "dict[str, ActivityTemplateOperations]", dict(raw_services)
    )

    user_service = getattr(services, "user", None)
    get_user_service = make_service_getter(user_service)
    ps_service = getattr(services, "ps", None)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _gather_attached(ps_uid: str) -> dict[str, list[dict[str, Any]]]:
        """Fetch the property-dict list of templates attached to ``ps_uid``."""
        attached: dict[str, list[dict[str, Any]]] = {}
        for domain, service in template_services.items():
            result = await service.list_for_pathstep(ps_uid)
            attached[domain] = result.value if result.is_ok else []
        return attached

    async def _gather_picker_options(
        ps_uid: str, target_domains: set[str]
    ) -> dict[str, list[tuple[str, str]]]:
        """``{target_domain: [(uid, title), ...]}`` for the cross-template pickers."""
        options: dict[str, list[tuple[str, str]]] = {}
        for target in target_domains:
            service = template_services.get(target)
            if service is None:
                options[target] = []
                continue
            result = await service.list_for_pathstep(ps_uid)
            options[target] = (
                [
                    (str(t.get("uid", "")), str(t.get("title") or t.get("uid", "")))
                    for t in result.value
                ]
                if result.is_ok
                else []
            )
        return options

    def _spec_or_404(domain: str) -> DomainSpec | None:
        return DOMAIN_SPECS.get(domain)

    def _render_form_page(
        request: Request,
        ps_uid: str,
        title: str,
        body: Any,
    ) -> Any:
        """Wrap form content in a BasePage with PS breadcrumbs."""
        content = Div(
            PageHeader(title),
            Div(
                ButtonLink(
                    "← Back to PathStep",
                    href=f"/explore/ps/{ps_uid}",
                    cls=ButtonT.ghost,
                    size="sm",
                ),
                cls="mb-4",
            ),
            body,
            cls=f"{Container.NARROW} p-6 space-y-4",
        )
        return BasePage(
            content=content,
            title=title,
            request=request,
            active_page="teaching",
        )

    # ------------------------------------------------------------------
    # GET /teaching/ps/{ps_uid}/templates  — panel fragment
    # ------------------------------------------------------------------

    @rt("/teaching/ps/{ps_uid}/templates")
    @require_role(UserRole.TEACHER, get_user_service)
    async def templates_panel_fragment(
        request: Request, ps_uid: str, current_user: Any = None
    ) -> Any:
        require_authenticated_user(request)
        attached = await _gather_attached(ps_uid)
        return render_templates_panel(ps_uid, attached)

    # ------------------------------------------------------------------
    # GET /teaching/ps/{ps_uid}/templates/{domain}/new  — create form page
    # ------------------------------------------------------------------

    @rt("/teaching/ps/{ps_uid}/templates/{domain}/new", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    async def template_create_page(
        request: Request, ps_uid: str, domain: str, current_user: Any = None
    ) -> Any:
        require_authenticated_user(request)
        spec = _spec_or_404(domain)
        if spec is None:
            return _render_form_page(
                request,
                ps_uid,
                "Unknown template domain",
                render_error_banner(f"No template domain named '{domain}'."),
            )

        picker_options = await _gather_picker_options(ps_uid, set(spec.ref_fields.values()))
        return _render_form_page(
            request,
            ps_uid,
            f"New {domain.title()} Template",
            build_create_form(spec, ps_uid=ps_uid, picker_options=picker_options),
        )

    # ------------------------------------------------------------------
    # POST /teaching/ps/{ps_uid}/templates/{domain}/new  — submit create
    # ------------------------------------------------------------------

    @rt("/teaching/ps/{ps_uid}/templates/{domain}/new", methods=["POST"])
    @csrf_protected
    @require_role(UserRole.TEACHER, get_user_service)
    async def template_create_submit(
        request: Request, ps_uid: str, domain: str, current_user: Any = None
    ) -> Any:
        user_uid = require_authenticated_user(request)
        spec = _spec_or_404(domain)
        if spec is None:
            return _render_form_page(
                request,
                ps_uid,
                "Unknown template domain",
                render_error_banner(f"No template domain named '{domain}'."),
            )

        service = template_services[domain]
        picker_options = await _gather_picker_options(ps_uid, set(spec.ref_fields.values()))

        # Defensive: ensure the target PathStep exists before creating a
        # template + edge against a missing parent.
        if ps_service is not None:
            ps_check = await ps_service.core.get(ps_uid)
            if ps_check.is_error:
                return _render_form_page(
                    request,
                    ps_uid,
                    f"New {domain.title()} Template",
                    Div(
                        render_error_banner(f"PathStep {ps_uid} not found."),
                        build_create_form(spec, ps_uid=ps_uid, picker_options=picker_options),
                    ),
                )

        parsed = await parse_template_form_body(request, spec.create_schema)
        if parsed.is_error:
            err = parsed.expect_error()
            return _render_form_page(
                request,
                ps_uid,
                f"New {domain.title()} Template",
                Div(
                    render_error_banner(err.display_message),
                    build_create_form(spec, ps_uid=ps_uid, picker_options=picker_options),
                ),
            )

        prefix = _DOMAIN_UID_PREFIX[domain]
        uid = str(UIDGenerator.generate_uid(prefix, parsed.value.title))

        converter = ConversionServiceV2.get_converter(type(parsed.value))
        if converter is None:
            return _render_form_page(
                request,
                ps_uid,
                f"New {domain.title()} Template",
                render_error_banner(
                    f"Internal error: no converter registered for {type(parsed.value).__name__}."
                ),
            )

        entity = converter(parsed.value, uid, user_uid=user_uid)
        create_res = await service.create(entity)
        if create_res.is_error:
            err = create_res.expect_error()
            return _render_form_page(
                request,
                ps_uid,
                f"New {domain.title()} Template",
                Div(
                    render_error_banner(err.display_message),
                    build_create_form(spec, ps_uid=ps_uid, picker_options=picker_options),
                ),
            )

        # Attach the new template to the PS.
        attach_res: Result[bool] = await service.attach_to_pathstep(ps_uid, uid)
        if attach_res.is_error:
            err = attach_res.expect_error()
            logger.error(
                f"Created {domain} template {uid} but failed to attach to PS {ps_uid}: "
                f"{err.message}"
            )
            return _render_form_page(
                request,
                ps_uid,
                f"New {domain.title()} Template",
                render_error_banner(
                    f"Template {uid} was created but could not be attached to PathStep "
                    f"{ps_uid}. Use POST /api/pathstep-{domain}-templates/attach to "
                    "complete the link, or delete the orphan template via the JSON API."
                ),
            )

        return RedirectResponse(f"/explore/ps/{ps_uid}", status_code=303)

    # ------------------------------------------------------------------
    # GET /teaching/ps/{ps_uid}/templates/{domain}/edit?uid=...  — edit form page
    # ------------------------------------------------------------------

    @rt("/teaching/ps/{ps_uid}/templates/{domain}/edit", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    async def template_edit_page(
        request: Request, ps_uid: str, domain: str, current_user: Any = None
    ) -> Any:
        require_authenticated_user(request)
        spec = _spec_or_404(domain)
        if spec is None:
            return _render_form_page(
                request,
                ps_uid,
                "Unknown template domain",
                render_error_banner(f"No template domain named '{domain}'."),
            )

        template_uid = request.query_params.get("uid", "")
        if not template_uid:
            return _render_form_page(
                request,
                ps_uid,
                f"Edit {domain.title()} Template",
                render_error_banner("Missing template UID."),
            )

        service = template_services[domain]
        result = await service.get(template_uid)
        if result.is_error or result.value is None:
            return _render_form_page(
                request,
                ps_uid,
                f"Edit {domain.title()} Template",
                render_error_banner(f"Template {template_uid} not found."),
            )

        template = result.value
        picker_options = await _gather_picker_options(ps_uid, set(spec.ref_fields.values()))
        return _render_form_page(
            request,
            ps_uid,
            f"Edit: {getattr(template, 'title', template_uid)}",
            build_edit_form(spec, ps_uid=ps_uid, template=template, picker_options=picker_options),
        )

    # ------------------------------------------------------------------
    # POST /teaching/ps/{ps_uid}/templates/{domain}/edit?uid=...  — submit edit
    # ------------------------------------------------------------------

    @rt("/teaching/ps/{ps_uid}/templates/{domain}/edit", methods=["POST"])
    @csrf_protected
    @require_role(UserRole.TEACHER, get_user_service)
    async def template_edit_submit(
        request: Request, ps_uid: str, domain: str, current_user: Any = None
    ) -> Any:
        require_authenticated_user(request)
        spec = _spec_or_404(domain)
        if spec is None:
            return _render_form_page(
                request,
                ps_uid,
                "Unknown template domain",
                render_error_banner(f"No template domain named '{domain}'."),
            )

        template_uid = request.query_params.get("uid", "")
        if not template_uid:
            return _render_form_page(
                request,
                ps_uid,
                f"Edit {domain.title()} Template",
                render_error_banner("Missing template UID."),
            )

        service = template_services[domain]
        existing = await service.get(template_uid)
        if existing.is_error or existing.value is None:
            return _render_form_page(
                request,
                ps_uid,
                f"Edit {domain.title()} Template",
                render_error_banner(f"Template {template_uid} not found."),
            )
        template = existing.value
        picker_options = await _gather_picker_options(ps_uid, set(spec.ref_fields.values()))

        parsed = await parse_template_form_body(request, spec.update_schema)
        if parsed.is_error:
            err = parsed.expect_error()
            return _render_form_page(
                request,
                ps_uid,
                f"Edit: {getattr(template, 'title', template_uid)}",
                Div(
                    render_error_banner(err.display_message),
                    build_edit_form(
                        spec, ps_uid=ps_uid, template=template, picker_options=picker_options
                    ),
                ),
            )

        # Apply only the fields that were actually set; drop None to avoid
        # clobbering existing values when the teacher leaves a field blank.
        updates = parsed.value.model_dump(exclude_unset=True)
        # Translate any RelativeOffsetDTO sub-dicts (now dicts under
        # ``model_dump``) to RelativeOffset values the core model expects.
        updates = _materialize_offsets_for_update(updates, spec)

        update_res = await service.update(template_uid, updates)
        if update_res.is_error:
            err = update_res.expect_error()
            return _render_form_page(
                request,
                ps_uid,
                f"Edit: {getattr(template, 'title', template_uid)}",
                Div(
                    render_error_banner(err.display_message),
                    build_edit_form(
                        spec, ps_uid=ps_uid, template=template, picker_options=picker_options
                    ),
                ),
            )

        return RedirectResponse(f"/explore/ps/{ps_uid}", status_code=303)

    # ------------------------------------------------------------------
    # POST /teaching/ps/{ps_uid}/templates/{domain}/detach?uid=...
    # ------------------------------------------------------------------

    @rt("/teaching/ps/{ps_uid}/templates/{domain}/detach", methods=["POST"])
    @csrf_protected
    @require_role(UserRole.TEACHER, get_user_service)
    async def template_detach(
        request: Request, ps_uid: str, domain: str, current_user: Any = None
    ) -> Any:
        require_authenticated_user(request)
        if domain not in DOMAIN_SPECS:
            return render_templates_panel(ps_uid, await _gather_attached(ps_uid))

        template_uid = request.query_params.get("uid", "")
        if not template_uid:
            return render_templates_panel(ps_uid, await _gather_attached(ps_uid))

        service = template_services[domain]
        await service.detach_from_pathstep(ps_uid, template_uid)
        attached = await _gather_attached(ps_uid)
        return render_templates_panel(ps_uid, attached)

    logger.info(
        "Templates UI routes registered (panel fragment + create/edit/detach for %d domains)",
        len(PANEL_DOMAINS),
    )


def _materialize_offsets_for_update(updates: dict[str, Any], spec: DomainSpec) -> dict[str, Any]:
    """Coerce ``{days, hours, minutes}`` sub-dicts into ``RelativeOffset`` values.

    ``Pydantic.model_dump`` reduces :class:`RelativeOffsetDTO` to a plain dict;
    the core model's update path expects :class:`RelativeOffset` (frozen value)
    or ``None``. Iterate the spec's known offset fields and convert in place.
    """
    from core.models.templates.relative_offset import RelativeOffset

    for field in spec.offset_fields:
        value = updates.get(field)
        if isinstance(value, dict):
            days = int(value.get("days", 0))
            hours = int(value.get("hours", 0))
            minutes = int(value.get("minutes", 0))
            updates[field] = (
                None
                if days == 0 and hours == 0 and minutes == 0
                else RelativeOffset(days=days, hours=hours, minutes=minutes)
            )
    return updates


__all__ = ["create_templates_ui_routes"]
