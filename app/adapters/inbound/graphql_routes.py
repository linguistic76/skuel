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

from typing import Any

from fasthtml.common import (
    H1,
    H3,
    Button,
    Card,
    Div,
    Form,
    P,
    Pre,
    Textarea,
    Title,
)

from adapters.inbound.auth.session import require_authenticated_user
from core.utils.logging import get_logger
from routes.graphql import create_graphql_context, create_graphql_schema
from services_bootstrap import Services

logger = get_logger(__name__)


# Manual implementation using FastHTML routes (not FastAPI mounting)


def create_graphql_routes_manual(app: Any, rt: Any, services: Services, search_router: Any) -> None:
    """
    Wire GraphQL routes manually (if mounting doesn't work with FastHTML).

    Args:
        app: FastHTML app
        rt: FastHTML router
        services: Business services
        search_router: SearchRouter for search functionality (One Path Forward)

    This creates routes directly without mounting.
    """
    schema = create_graphql_schema()

    @rt("/graphql")
    async def graphql_handler(request) -> Any:
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
                        Button("Execute Query", type="submit", cls="btn btn-primary"),
                        hx_post="/graphql/execute",
                        hx_target="#graphql-result",
                        hx_swap="innerHTML",
                    ),
                    cls="mb-4",
                ),
                Card(
                    H3("Result"),
                    Div(
                        P("Execute a query to see results here...", cls="text-base-content/60"),
                        id="graphql-result",
                        cls="font-mono text-sm",
                    ),
                ),
                cls="container mx-auto p-4",
            )

        # POST request - execute GraphQL query and return JSON
        # Get request body
        body = await request.json()

        # AUTHENTICATION: Require authenticated user (January 2026 hardening)
        user_uid = require_authenticated_user(request)

        logger.info(f"GraphQL request from authenticated user: {user_uid}")

        # Create authenticated context with search router
        context = create_graphql_context(services, search_router, user_uid=user_uid)

        # Execute query
        result = await schema.execute(
            query=body.get("query", ""),
            variable_values=body.get("variables"),
            context_value=context,
            operation_name=body.get("operationName"),
        )

        # Return result as dict - FastHTML will serialize to JSON
        response_data = {"data": result.data}
        if result.errors:
            response_data["errors"] = [{"message": str(error)} for error in result.errors]

        return response_data

    @rt("/graphql/execute")
    async def graphql_execute(request) -> Div:
        """
        Execute GraphQL query from playground form.

        Returns formatted HTML result for display in playground.
        """
        # Get form data
        form_data = await request.form()
        query = form_data.get("query", "")
        variables_str = form_data.get("variables", "{}")

        # Parse variables JSON
        try:
            import json

            variables = json.loads(variables_str) if variables_str else {}
        except json.JSONDecodeError:
            return Div(
                Pre("Invalid JSON in variables field", cls="text-red-600"),
                cls="p-4 bg-red-50 rounded",
            )

        # AUTHENTICATION: Require authenticated user (January 2026 hardening)
        user_uid = require_authenticated_user(request)

        # Create authenticated context with search router
        context = create_graphql_context(services, search_router, user_uid=user_uid)

        # Execute query
        result = await schema.execute(query=query, variable_values=variables, context_value=context)

        # Format result
        response_data = {"data": result.data}
        if result.errors:
            response_data["errors"] = [{"message": str(error)} for error in result.errors]

        # Return formatted JSON in a Pre element
        import json

        formatted_json = json.dumps(response_data, indent=2)

        if result.errors:
            return Div(Pre(formatted_json, cls="text-red-600"), cls="p-4 bg-red-50 rounded")
        else:
            return Div(Pre(formatted_json, cls="text-green-600"), cls="p-4 bg-green-50 rounded")

    logger.info("✅ GraphQL routes registered manually:")
    logger.info("  - GET  /graphql         → FastHTML playground (no React!)")
    logger.info("  - POST /graphql         → JSON API for tests/clients")
    logger.info("  - POST /graphql/execute → Playground form submission")
