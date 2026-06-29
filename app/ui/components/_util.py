from typing import Any


def _cls(*parts: Any) -> str:
    """Flatten heterogeneous cls arguments to a single space-separated string.

    Accepts any mix of str, tuple, list, None, and empty values as positional args.
    Falsy values (None, "", empty list) are silently dropped.
    """
    result: list[str] = []
    for part in parts:
        if isinstance(part, (list, tuple)):
            result.extend(str(p) for p in part if p)
        elif part:
            result.append(str(part))
    return " ".join(result).strip()
