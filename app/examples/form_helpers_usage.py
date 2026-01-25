"""
Example: Type-Safe Form Data Extraction with safe_form_string

This demonstrates how to safely extract form data in FastHTML routes
without triggering MyPy union-attr errors.
"""

from core.utils.form_helpers import safe_form_bool, safe_form_int, safe_form_string


# ❌ BEFORE: Unsafe pattern (MyPy error)
async def old_registration_handler(request):
    """This causes MyPy error: Item "UploadFile" has no attribute "strip" """
    form_data = await request.form()

    # MyPy error: UploadFile | str | None doesn't have .strip()
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
