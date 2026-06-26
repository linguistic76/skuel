"""
GraphQL Routes for FastHTML
============================

Integrates Strawberry GraphQL with FastHTML.

Security:
- All GraphQL endpoints require authentication (January 2026 hardening)
- Uses require_authenticated_user() - no development fallback

This provides:
- POST /graphql - GraphQL query endpoint (authenticated)
- GET /graphql - Simple FastHTML playground (authenticated)
"""

import asyncio
import json
from typing import Any

from fasthtml.common import (
    H1,
    H3,
    Div,
    Form,
    P,
    Pre,
    Textarea,
    Title,
)
from monsterui.franken import Button, ButtonT, CardBody, CardHeader, CardTitle
from monsterui.franken import CardContainer as Card

from adapters.inbound.auth.session import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from adapters.inbound.graphql import GraphQLContext, create_graphql_context, create_graphql_schema
from adapters.inbound.graphql.config import get_graphql_config
from core.utils.logging import get_logger
from services_bootstrap import Services

logger = get_logger(__name__)


def create_graphql_routes(app: FastHTMLApp, rt: RouteDecorator, services: Services) -> None:
    """
    Wire GraphQL routes manually (FastHTML does not support schema mounting).

    Args:
        app: FastHTML app
        rt: FastHTML router
        services: Business services (full container — GraphQL needs cross-domain access)
    """
    schema = create_graphql_schema()
    search_router = services.search_router

    def _build_graphql_context(request: Request) -> GraphQLContext:
        """Authenticate request and create GraphQL execution context."""
        user_uid = require_authenticated_user(request)
        return create_graphql_context(services, search_router, user_uid=user_uid)

    def _format_graphql_response(result: Any) -> dict[str, Any]:
        """Build standard GraphQL response dict from execution result."""
        response_data: dict[str, Any] = {"data": result.data}
        if result.errors:
            response_data["errors"] = [{"message": str(error)} for error in result.errors]
        return response_data

    async def _execute_with_timeout(
        query: str,
        variables: dict[str, Any] | None,
        context: GraphQLContext,
        operation_name: str | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL operation under the configured whole-request timeout.

        The per-resolver and query-shape limits live in the schema extensions;
        this is the outermost ceiling on total operation time (GraphQLConfig
        guardrail). On timeout the request returns a GraphQL error rather than
        tying up the worker indefinitely.
        """
        timeout = get_graphql_config().max_query_timeout_seconds
        try:
            result = await asyncio.wait_for(
                schema.execute(
                    query=query,
                    variable_values=variables,
                    context_value=context,
                    operation_name=operation_name,
                ),
                timeout=timeout,
            )
        except TimeoutError:
            logger.warning("GraphQL operation exceeded the %ss request timeout", timeout)
            return {
                "data": None,
                "errors": [{"message": f"Query exceeded the {timeout}s execution timeout"}],
            }
        return _format_graphql_response(result)

    @rt("/graphql")
    async def graphql_handler(request: Request) -> Any:
        """
        GraphQL endpoint - handles both GET (playground) and POST (API).

        GET: Returns FastHTML playground UI
        POST: Executes GraphQL query and returns JSON
        """
        # GET request - return playground UI (requires authentication)
        if request.method == "GET":
            require_authenticated_user(request)
            # Sample query to help users get started
            sample_query = """query {
  knowledgeUnits(limit: 5) {
    uid
    title
    domain
    prerequisites {
      uid
      title
    }
  }
}"""

            return Title("SKUEL GraphQL"), Div(
                Card(
                    H1("SKUEL GraphQL Playground"),
                    P("Enter your GraphQL query below and click Execute"),
                    cls="mb-4",
                ),
                Card(
                    Form(
                        Div(
                            H3("Query"),
                            Textarea(
                                sample_query,
                                name="query",
                                id="graphql-query",
                                rows="12",
                                cls="w-full font-mono text-sm border rounded p-2",
                                placeholder="Enter GraphQL query...",
                            ),
                            cls="mb-4",
                        ),
                        Div(
                            H3("Variables (JSON)", cls="mb-2"),
                            Textarea(
                                "{}",
                                name="variables",
                                id="graphql-variables",
                                rows="4",
                                cls="w-full font-mono text-sm border rounded p-2",
                                placeholder='{"uid": "ku.example"}',
                            ),
                            cls="mb-4",
                        ),
                        Button("Execute Query", type="submit", cls=ButtonT.primary),
                        hx_post="/graphql/execute",
                        hx_target="#graphql-result",
                        hx_swap="innerHTML",
                    ),
                    cls="mb-4",
                ),
                Card(
                    CardHeader(CardTitle("Result")),
                    CardBody(
                        Div(
                            P(
                                "Execute a query to see results here...",
                                cls="text-muted-foreground",
                            ),
                            id="graphql-result",
                            cls="font-mono text-sm",
                        ),
                    ),
                ),
                cls="container mx-auto p-4",
            )

        # POST request - execute GraphQL query and return JSON
        body = await request.json()
        context = _build_graphql_context(request)
        logger.info(f"GraphQL request from authenticated user: {context.user_uid}")

        return await _execute_with_timeout(
            body.get("query", ""),
            body.get("variables"),
            context,
            body.get("operationName"),
        )

    @rt("/graphql/execute")
    @csrf_protected
    async def graphql_execute(request: Request) -> Div:
        """
        Execute GraphQL query from playground form.

        Returns formatted HTML result for display in playground.
        """
        # Get form data
        form_data = await request.form()
        query = form_data.get("query", "")
        variables_str = form_data.get("variables", "{}")

        # Starlette FormData returns str | UploadFile — reject file uploads posted
        # to these text fields (narrows the type AND closes a latent crash in
        # json.loads / _execute_with_timeout, both of which require str).
        if not isinstance(query, str) or not isinstance(variables_str, str):
            return Div(
                Pre("Invalid request: query and variables must be text fields", cls="text-error"),
                cls="p-4 bg-error/10 rounded",
            )

        # Parse variables JSON
        try:
            variables = json.loads(variables_str) if variables_str else {}
        except json.JSONDecodeError:
            return Div(
                Pre("Invalid JSON in variables field", cls="text-error"),
                cls="p-4 bg-error/10 rounded",
            )

        context = _build_graphql_context(request)
        response_data = await _execute_with_timeout(query, variables, context)

        formatted_json = json.dumps(response_data, indent=2)

        if response_data.get("errors"):
            return Div(Pre(formatted_json, cls="text-error"), cls="p-4 bg-error/10 rounded")
        else:
            return Div(Pre(formatted_json, cls="text-success"), cls="p-4 bg-success/10 rounded")

    logger.info("GraphQL routes registered:")
    logger.info("  - GET  /graphql         -> FastHTML playground")
    logger.info("  - POST /graphql         -> JSON API for tests/clients")
    logger.info("  - POST /graphql/execute -> Playground form submission")
