"""
Centralized Exception Type Groups
==================================

Reusable exception tuples for narrowing overly broad `except Exception` catches.
Import the appropriate tuple and use it in place of bare `except Exception`.

Usage:
    from core.utils.exception_types import NEO4J_EXCEPTIONS, DATA_CONVERSION_EXCEPTIONS

    try:
        result = await self.backend.get(uid)
    except NEO4J_EXCEPTIONS as e:
        return Result.fail(Errors.database(operation="get", message=str(e)))
    except Exception as e:  # safety-net: catch unexpected errors
        logger.error(f"Unexpected {type(e).__name__}: {e}")
        return Result.fail(Errors.system(message="Unexpected error", exception=e))

See: /docs/patterns/ERROR_HANDLING.md
"""

import json
from typing import TYPE_CHECKING

import yaml

# ============================================================================
# DATABASE EXCEPTIONS
# ============================================================================

# Import the exception CLASSES by name, guarded like every other SDK below
# (ADR-063 carve-out: exception classes are the one sanctioned SDK import in
# core). Core stays importable without the driver installed; when the driver
# is absent no driver exception can be raised, so the empty tuple is inert.
#
# The TYPE_CHECKING split keeps the static type a concrete fixed-length tuple:
# call sites star-unpack it into except clauses (`except (*NEO4J_EXCEPTIONS,
# *DATA_CONVERSION_EXCEPTIONS)`), which mypy rejects for variadic
# `tuple[type[BaseException], ...]` values.
#
# NOTE (Tier 6 consideration): a "register driver exceptions at composition
# time" design was evaluated and rejected — 100+ call sites bind this name via
# `from ... import NEO4J_EXCEPTIONS` at module import time, so a tuple
# reassigned at compose time would silently never reach existing `except`
# clauses. The guarded class import is the honest one-path version.
if TYPE_CHECKING:
    from neo4j.exceptions import (
        AuthError,
        DriverError,
        Neo4jError,
        ServiceUnavailable,
        SessionExpired,
    )

    NEO4J_EXCEPTIONS = (Neo4jError, DriverError, ServiceUnavailable, SessionExpired, AuthError)
else:
    try:
        from neo4j.exceptions import (
            AuthError,
            DriverError,
            Neo4jError,
            ServiceUnavailable,
            SessionExpired,
        )

        NEO4J_EXCEPTIONS = (Neo4jError, DriverError, ServiceUnavailable, SessionExpired, AuthError)
    except ImportError:
        NEO4J_EXCEPTIONS = ()
"""Neo4j driver and query exceptions. Map to Errors.database()."""

# ============================================================================
# AI / LLM SERVICE EXCEPTIONS
# ============================================================================

# Import lazily to avoid hard dependency when AI services aren't configured
try:
    from openai import (
        APIConnectionError as OpenAIConnectionError,
    )
    from openai import (
        APIError as OpenAIAPIError,
    )
    from openai import (
        APITimeoutError as OpenAITimeoutError,
    )
    from openai import (
        RateLimitError as OpenAIRateLimitError,
    )

    OPENAI_EXCEPTIONS: tuple[type[BaseException], ...] = (
        OpenAIAPIError,
        OpenAIConnectionError,
        OpenAITimeoutError,
        OpenAIRateLimitError,
    )
except ImportError:
    OPENAI_EXCEPTIONS = ()

try:
    from anthropic import (
        APIConnectionError as AnthropicConnectionError,
    )
    from anthropic import (
        APIError as AnthropicAPIError,
    )
    from anthropic import (
        APITimeoutError as AnthropicTimeoutError,
    )
    from anthropic import (
        RateLimitError as AnthropicRateLimitError,
    )

    ANTHROPIC_EXCEPTIONS: tuple[type[BaseException], ...] = (
        AnthropicAPIError,
        AnthropicConnectionError,
        AnthropicTimeoutError,
        AnthropicRateLimitError,
    )
except ImportError:
    ANTHROPIC_EXCEPTIONS = ()

LLM_EXCEPTIONS: tuple[type[BaseException], ...] = (*OPENAI_EXCEPTIONS, *ANTHROPIC_EXCEPTIONS)
"""All LLM provider exceptions (OpenAI + Anthropic). Map to Errors.integration()."""

# ============================================================================
# FIREFLY III HTTP CLIENT EXCEPTIONS
# ============================================================================

# Import the exception CLASSES by name (never `import httpx`, which would expose
# httpx.Client below the boundary — see tests/test_llm_sdk_boundary.py).
try:
    from httpx import HTTPError, InvalidURL, NetworkError, TimeoutException

    FIREFLY_EXCEPTIONS: tuple[type[BaseException], ...] = (
        HTTPError,
        TimeoutException,
        NetworkError,
        InvalidURL,
    )
except ImportError:
    FIREFLY_EXCEPTIONS = ()
"""httpx exceptions raised by the Firefly III REST client. Map to Errors.integration()."""

# ============================================================================
# FILE I/O EXCEPTIONS
# ============================================================================

FILE_IO_EXCEPTIONS = (FileNotFoundError, PermissionError, IsADirectoryError, OSError)
"""File system exceptions. Map to Errors.system() or context-specific error."""

# ============================================================================
# PARSING EXCEPTIONS
# ============================================================================

YAML_EXCEPTIONS = (yaml.YAMLError,)
"""YAML parsing exceptions."""

JSON_EXCEPTIONS = (json.JSONDecodeError,)
"""JSON parsing exceptions."""

PARSING_EXCEPTIONS = (
    ValueError,
    KeyError,
    json.JSONDecodeError,
    yaml.YAMLError,
)
"""Content parsing exceptions (YAML, JSON, general value errors). Map to Errors.validation()."""

# ============================================================================
# DATA CONVERSION EXCEPTIONS
# ============================================================================

DATA_CONVERSION_EXCEPTIONS = (ValueError, TypeError, AttributeError, KeyError, ZeroDivisionError)
"""Data transformation and conversion exceptions. Map to Errors.validation() or Errors.system()."""

# ============================================================================
# CONFIG EXCEPTIONS
# ============================================================================

CONFIG_EXCEPTIONS = (
    FileNotFoundError,
    json.JSONDecodeError,
    ValueError,
    OSError,
    KeyError,
    TypeError,
)
"""Configuration loading exceptions. Map to Errors.system()."""

# ============================================================================
# AUTH EXCEPTIONS
# ============================================================================

AUTH_EXCEPTIONS = (ValueError, TypeError)
"""Authentication/authorization data exceptions (non-database). Map to Errors.validation()."""

# ============================================================================
# DEEPGRAM (TRANSCRIPTION) EXCEPTIONS
# ============================================================================

try:
    from deepgram import DeepgramApiError, DeepgramError

    DEEPGRAM_EXCEPTIONS: tuple[type[BaseException], ...] = (
        DeepgramApiError,
        DeepgramError,
    )
except ImportError:
    DEEPGRAM_EXCEPTIONS = ()
