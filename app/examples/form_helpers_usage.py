# mypy: disable-error-code="attr-defined"
"""
Example: Type-Safe Form Data Extraction

Demonstrates two approaches:
1. Individual field helpers (safe_form_string, safe_form_int, etc.)
2. Structured body helpers (parse_json_body, parse_form_body)
"""

from adapters.inbound.form_helpers import (
    parse_form_body,
    parse_json_body,
    safe_form_bool,
    safe_form_int,
    safe_form_string,
)


# ❌ BEFORE: Unsafe pattern (MyPy error, type fragility)
async def old_registration_handler(request):
    """This causes MyPy error: Item "UploadFile" has no attribute "strip" """
    form_data = await request.form()

    # MyPy error: UploadFile | str | None doesn't have .strip()
    # Also fragile — if field contains UploadFile, .strip() crashes at runtime
    username = form_data.get("username", "").strip()
    email = form_data.get("email", "").strip()

    return {"username": username, "email": email}


# ✅ AFTER: Type-safe pattern (No MyPy errors)
async def new_registration_handler(request):
    """This passes MyPy type checking cleanly"""
    form_data = await request.form()

    # Type-safe extraction with proper type guards
    username = safe_form_string(form_data.get("username"))
    email = safe_form_string(form_data.get("email"))
    age = safe_form_int(form_data.get("age"), default=0)
    is_admin = safe_form_bool(form_data.get("is_admin"))

    return {
        "username": username,
        "email": email,
        "age": age,
        "is_admin": is_admin,
    }


# ✅ REAL WORLD EXAMPLE: Login form
async def login_handler(request):
    """Production-ready form handling"""
    form_data = await request.form()

    # Extract and validate
    email_or_username = safe_form_string(form_data.get("username"))
    password = safe_form_string(form_data.get("password"))

    # Validation
    if not email_or_username or not password:
        return {"error": "All fields are required"}

    # Proceed with authentication...
    return {"success": True}


# ============================================================================
# STRUCTURED BODY HELPERS — parse_json_body / parse_form_body
# ============================================================================
# Use these when a route accepts a structured Pydantic model rather than
# a handful of individual fields.


# ✅ parse_json_body — JSON POST body → Pydantic model → Result[T]
async def json_body_example(request):
    """Replaces the try/except ValidationError boilerplate."""
    from core.models.teaching.teaching_request import RequestRevisionRequest

    result = await parse_json_body(request, RequestRevisionRequest)
    if result.is_error:
        return result  # 422 with validation details
    req = result.value
    return {"notes": req.notes}


# ✅ parse_json_body with extra — merging entity UID from ownership decorator
async def json_body_with_extra_example(request, entity):
    """Use `extra=` to inject fields not in the request body."""
    from core.models.habit.habit_request import TrackHabitRequest

    result = await parse_json_body(request, TrackHabitRequest, extra={"habit_uid": entity.uid})
    if result.is_error:
        return result
    return {"tracked": True}


# ✅ parse_form_body — HTML form data → Pydantic model → Result[T]
async def form_body_example(request):
    """Replaces manual (body.get("field") or "").strip() + enum try/except chains."""
    from core.models.teaching.teaching_request import CreateTeachingExerciseRequest

    result = await parse_form_body(request, CreateTeachingExerciseRequest)
    if result.is_error:
        return result  # 422 with validation details
    req = result.value
    return {"name": req.name, "scope": req.scope.value}
