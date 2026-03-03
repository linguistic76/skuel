"""
Quick-Add Route Factory - Generic Form Handling for HTMX/HTML Routes
====================================================================

Consolidates ~60 lines of duplicate quick-add form handling across 6 UI routes.

Core Pattern Consolidated:
1. Request authentication
2. Form data extraction
3. Required field validation
4. Service creation call with error handling
5. Add-another vs list-switch response logic

Usage:
    from adapters.inbound.route_factories.quick_add_factory import (
        QuickAddConfig,
        QuickAddRouteFactory,
    )

    # Define domain-specific functions (named functions, not lambdas - SKUEL012)
    async def create_task_from_form(form_data: dict[str, Any], user_uid: str) -> Result[Task]:
        # Parse form data, build request, call service
        create_request = TaskCreateRequest(title=form_data["title"], ...)
        return await tasks_service.create_task(create_request, user_uid)

    async def render_task_success_view(user_uid: str) -> Any:
        tasks, stats = await get_filtered_tasks(user_uid, ...)
        return TasksViewComponents.render_list_view(tasks=tasks, stats=stats, ...)

    async def render_task_add_another_view(user_uid: str) -> Any:
        projects = await get_distinct_projects(user_uid)
        return TasksViewComponents.render_create_view(projects=projects, ...)

    # Define config
    config = QuickAddConfig(
        domain_name="tasks",
        required_field="title",
        create_entity=create_task_from_form,
        render_success_view=render_task_success_view,
        render_add_another_view=render_task_add_another_view,
    )

    # Register route
    QuickAddRouteFactory.register_route(rt, config)

Benefits:
    - ~360 lines saved across 6 domains (60 lines each)
    - Consistent error handling and logging
    - Consistent add-another behavior
    - Full flexibility via callables for domain-specific logic
    - Type-safe with clear configuration
    - No lambdas (SKUEL012 compliant)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import ValidationError as PydanticValidationError
from starlette.responses import Response

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

from adapters.inbound.auth.session import require_authenticated_user
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from ui.patterns.error_banner import render_error_banner

logger = get_logger(__name__)

T = TypeVar("T")


# Type aliases for clarity
CreateEntityFn = "Callable[[dict[str, Any], str], Awaitable[Result[Any]]]"
RenderViewFn = "Callable[[str], Awaitable[Any]]"
ValidatorFn = "Callable[[dict[str, Any]], tuple[bool, str]]"


@dataclass
class QuickAddConfig:
    """
    Configuration for a quick-add route handler.

    This design uses callables for domain-specific logic, allowing each domain
    to handle its unique creation patterns (DTOs, request objects, service signatures).

    Attributes:
        domain_name: Domain identifier (e.g., "tasks", "goals")
        required_field: Primary field that must be present (usually "title" or "name")
        create_entity: Async function that handles ALL domain-specific creation logic:
            - Form data parsing
            - DTO/request building
            - Service call with correct signature
            Takes (form_data, user_uid) and returns Result[entity]
        render_success_view: Async function to render success response (list, calendar, or redirect)
            Takes (user_uid) and returns the view response
        render_add_another_view: Async function to render create form for add-another
            Takes (user_uid) and returns the create view response
        extra_validators: Optional list of validators run before create_entity
            Each validator takes form_data and returns (is_valid, error_message)
    """

    domain_name: str
    required_field: str
    create_entity: Callable[[dict[str, Any], str], Awaitable[Result[Any]]]
    render_success_view: Callable[[str], Awaitable[Any]]
    render_add_another_view: Callable[[str], Awaitable[Any]]
    extra_validators: list[Callable[[dict[str, Any]], tuple[bool, str]]] = field(
        default_factory=list
    )


class QuickAddRouteFactory:
    """
    Factory for generating quick-add form handlers.

    All Activity domain UI routes share the same quick-add pattern:
    1. Authenticate user
    2. Extract and validate form data
    3. Call domain-specific create_entity function
    4. Handle success (add_another or success view)
    5. Handle errors consistently

    This factory consolidates that pattern into reusable code while allowing
    full flexibility for domain-specific creation logic via callables.
    """

    @staticmethod
    def create_handler(config: QuickAddConfig) -> Callable[..., Awaitable[Any]]:
        """
        Create a quick-add route handler from configuration.

        Args:
            config: QuickAddConfig with domain-specific settings

        Returns:
            Async route handler function
        """

        async def quick_add_handler(request) -> Any:
            """Generated quick-add handler."""
            domain = config.domain_name
            logger.info(f"=== QUICK-ADD {domain.upper()} START ===")

            # Step 1: Authenticate
            user_uid = require_authenticated_user(request)
            logger.info(f"User authenticated: {user_uid}")

            # Step 2: Extract form data
            form = await request.form()
            form_data = dict(form)
            logger.debug(f"Form data received: {form_data}")

            # Step 3: Validate required field
            required_value = form_data.get(config.required_field, "")
            if isinstance(required_value, str):
                required_value = required_value.strip()
            if not required_value:
                return Response(f"{config.required_field.title()} is required", status_code=400)

            # Step 4: Run extra validators
            for validator in config.extra_validators:
                is_valid, error_msg = validator(form_data)
                if not is_valid:
                    return Response(error_msg, status_code=400)

            # Step 5: Call domain-specific create_entity function
            # This handles ALL domain-specific logic: parsing, DTO building, service calls
            try:
                result = await config.create_entity(form_data, user_uid)

                if result.is_error:
                    logger.error(f"Failed to create {domain}: {result.error}")
                    return Response(f"Failed to create {domain}: {result.error}", status_code=500)

                created_entity = result.value
                logger.info(f"{domain.title()} created: {created_entity.uid}")

                # Step 6: Handle success response
                add_another = form_data.get("add_another", "")

                if add_another:
                    # Re-render create view for continuous adding
                    response = await config.render_add_another_view(user_uid)
                    logger.info(f"=== QUICK-ADD {domain.upper()} END (add_another) ===")
                    return response

                # Default: render success view (list, calendar, or redirect)
                response = await config.render_success_view(user_uid)
                logger.info(f"=== QUICK-ADD {domain.upper()} END ===")
                return response

            except PydanticValidationError as e:
                first_error = e.errors()[0]
                loc = first_error.get("loc", ())
                field = str(loc[-1]) if loc and loc[-1] != "__root__" else None
                msg = first_error.get("msg", "Validation error")
                user_msg = f"{field}: {msg}" if field else msg
                logger.warning(f"Validation error creating {domain}: {user_msg}")
                return render_error_banner(user_msg)
            except Exception as e:
                logger.error(f"Error creating {domain}: {e}")
                return Response(f"Error: {e}", status_code=500)

        return quick_add_handler

    @staticmethod
    def register_route(
        rt: Callable[..., Any],
        config: QuickAddConfig,
    ) -> None:
        """
        Register a quick-add route with the FastHTML router.

        Args:
            rt: FastHTML route decorator
            config: QuickAddConfig with domain-specific settings
        """
        handler = QuickAddRouteFactory.create_handler(config)
        route_path = f"/{config.domain_name}/quick-add"

        # Use the rt decorator to register the route
        rt(route_path, methods=["POST"])(handler)

        logger.debug(f"Registered quick-add route: POST {route_path}")


__all__ = ["QuickAddConfig", "QuickAddRouteFactory"]
