"""
Form data extraction helpers for type-safe FastHTML form handling.

FastHTML form data can return str | UploadFile | None for any field.
These helpers provide type-safe extraction with proper type guards.
"""

from starlette.datastructures import UploadFile


def safe_form_string(value: str | UploadFile | None, default: str = "") -> str:
    """
    Extract string from form data safely.

    Args:
        value: Form field value (may be str, UploadFile, or None)
        default: Default value if extraction fails

    Returns:
        Stripped string value or default

    Example:
        >>> form_data = await request.form()
        >>> username = safe_form_string(form_data.get("username"))
        >>> email = safe_form_string(form_data.get("email"), default="")
    """
    if isinstance(value, str):
        return value.strip()
    return default


def safe_form_int(value: str | UploadFile | None, default: int = 0) -> int:
    """
    Extract integer from form data safely.

    Args:
        value: Form field value (may be str, UploadFile, or None)
        default: Default value if extraction/parsing fails

    Returns:
        Parsed integer or default

    Example:
        >>> age = safe_form_int(form_data.get("age"), default=0)
    """
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def safe_form_bool(value: str | UploadFile | None, default: bool = False) -> bool:
    """
    Extract boolean from form data safely.

    Treats "true", "1", "yes", "on" as True (case-insensitive).

    Args:
        value: Form field value (may be str, UploadFile, or None)
        default: Default value if extraction fails

    Returns:
        Boolean value or default

    Example:
        >>> is_active = safe_form_bool(form_data.get("active"))
    """
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return default
