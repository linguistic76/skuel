#!/usr/bin/env python3
"""
SKUEL Unified Linter
====================

Single linter enforcing all SKUEL architectural and code patterns.

RULES (by severity):

CRITICAL (blocks CI):
  SKUEL001: No APOC path procedures in domain services

ERROR (blocks CI):
  SKUEL002: Semantic type enums (not magic strings)
  SKUEL003: .is_err deprecated - use .is_error
  SKUEL020: FastHTML @rt handlers must annotate `request: Request` (not Any)
  SKUEL021: No raw Cypher in the service layer (lives below the boundary, ADR-044)
  SKUEL022: core/ must not import adapters/ (dependency direction, ADR-044)

WARNING (reported, doesn't block):
  SKUEL004: Confidence thresholds on semantic queries
  SKUEL005: Result[T] return types on service methods
  SKUEL007: String-based Result.fail() - use Errors factory
  SKUEL008: No wrapper classes around UniversalNeo4jBackend
  SKUEL011: hasattr() in production code - use Protocol/isinstance
  SKUEL012: Lambda expressions - use named functions
  SKUEL013: RelationshipName enum usage (not magic strings)
  SKUEL014: EntityType/NonKuDomain enum usage (not magic strings)
  SKUEL015: print() in production code - use logger instead
  SKUEL016: Stale Poetry references - SKUEL uses uv
  SKUEL017: Bare except Exception - use specific exception types
  SKUEL018: Direct access to RichUserContext RICH_ONLY_FIELDS - use accessors
  SKUEL019: Credential-shaped env reads bypassing get_credential()

INFO (informational, visibility only):
  SKUEL006: TODO/FIXME comments - track technical debt

AUTO-FIXABLE:
  SKUEL003: .is_err → .is_error
  SKUEL009: Single-element tuple defaults (int = (0,) → int = 0)
  SKUEL010: Nested empty tuple defaults (((),) → ())

Usage:
    uv run python scripts/lint_skuel.py              # Report violations (with code context)
    uv run python scripts/lint_skuel.py --fix        # Auto-fix where possible
    uv run python scripts/lint_skuel.py --check      # Exit 1 if violations (for CI)
    uv run python scripts/lint_skuel.py --strict     # Treat warnings as errors
    uv run python scripts/lint_skuel.py --changed    # Lint only files changed vs main branch
    uv run python scripts/lint_skuel.py --staged     # Lint only staged files (pre-commit)
    uv run python scripts/lint_skuel.py --file core/services/  # Lint specific path
    uv run python scripts/lint_skuel.py --rule SKUEL003  # Run specific rule only
    uv run python scripts/lint_skuel.py --explain SKUEL003  # Show rule documentation
    uv run python scripts/lint_skuel.py --quiet      # Minimal output for CI
    uv run python scripts/lint_skuel.py --no-context  # Hide code context

Last Updated: April 2026
"""

import ast
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import ClassVar


# ANSI color codes for terminal output
class Colors:
    """Terminal colors for better output readability."""

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    @classmethod
    def disable(cls) -> None:
        """Disable colors (for non-TTY output)."""
        cls.RED = ""
        cls.GREEN = ""
        cls.YELLOW = ""
        cls.BLUE = ""
        cls.CYAN = ""
        cls.BOLD = ""
        cls.DIM = ""
        cls.RESET = ""


class Severity(Enum):
    """Violation severity levels."""

    CRITICAL = "CRITICAL"  # Blocks CI, must fix
    ERROR = "ERROR"  # Blocks CI, must fix
    WARNING = "WARNING"  # Reported, doesn't block
    INFO = "INFO"  # Informational only


# Rule documentation for --explain
RULE_DOCS: dict[str, dict[str, str]] = {
    "SKUEL001": {
        "title": "No APOC in Domain Services",
        "severity": "CRITICAL",
        "description": """APOC procedures are banned in domain services (core/services/*).
Use CypherGenerator or pure Cypher instead.

APOC is only allowed in adapter layer (adapters/persistence/*) for complex traversals.""",
        "good": """# Use CypherGenerator
query = CypherGenerator.build_prerequisite_chain(uid)
result = await backend.execute_query(query)""",
        "bad": """# Don't use APOC in services
query = "CALL apoc.path.subgraphAll(n, {...})"
result = await backend.execute_query(query)""",
    },
    "SKUEL002": {
        "title": "Use SemanticRelationshipType Enum",
        "severity": "ERROR",
        "description": """Use SemanticRelationshipType enum instead of magic strings
for semantic relationship types. This ensures type safety and autocomplete.""",
        "good": """from core.models.enums import SemanticRelationshipType
rel_type = SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING""",
        "bad": """# Magic string - error prone
rel_type = "REQUIRES_THEORETICAL_UNDERSTANDING" """,
    },
    "SKUEL003": {
        "title": "Use .is_error Instead of .is_err",
        "severity": "ERROR",
        "description": """The .is_err property is deprecated. Use .is_error for better
readability and consistency with .is_ok/.is_error naming.""",
        "good": """if result.is_error:
    return result""",
        "bad": """if result.is_err:  # Deprecated
    return result""",
        "autofix": "Automatically replaced by --fix",
    },
    "SKUEL004": {
        "title": "Confidence Thresholds on Semantic Queries",
        "severity": "WARNING",
        "description": """Semantic relationship queries should include confidence thresholds
to filter out low-confidence relationships.""",
        "good": """MATCH (a)-[r:REQUIRES_THEORETICAL_UNDERSTANDING]->(b)
WHERE r.confidence >= $min_confidence
RETURN b""",
        "bad": """MATCH (a)-[r:REQUIRES_THEORETICAL_UNDERSTANDING]->(b)
RETURN b  -- No confidence filter!""",
    },
    "SKUEL005": {
        "title": "Service Methods Should Return Result[T]",
        "severity": "WARNING",
        "description": """Public async service methods should return Result[T] for
consistent error handling throughout the application.

Suppress: # skuel-lint: disable=SKUEL005 -- <reason>
File-level: # skuel-lint: disable-file=SKUEL005 -- <reason>""",
        "good": """async def get_task(self, uid: str) -> Result[Task]:
    ...""",
        "bad": """async def get_task(self, uid: str) -> Task:  # Should be Result[Task]
    ...""",
    },
    "SKUEL006": {
        "title": "TODO/FIXME Comments",
        "severity": "INFO",
        "description": """Tracks TODO and FIXME comments for technical debt visibility.
Categorized TODOs use parenthetical tags to indicate blocker type:

- TODO(blocked:<reason>): Waiting on external dependency (graph-data, embeddings, test-infra)
- TODO(deferred): Deliberately postponed feature work
- TODO(implementable): Ready to implement, no blockers

Uncategorized TODOs should be tagged with one of the above categories.""",
        "good": """# TODO(blocked:graph-data): Needs alignment snapshot nodes in Neo4j
# TODO(deferred): Record context-aware completion data""",
        "bad": """# TODO: Implement this feature later
# FIXME: This needs to be refactored""",
    },
    "SKUEL007": {
        "title": "Use Errors Factory for Result.fail()",
        "severity": "WARNING",
        "description": """Use the Errors factory (Errors.validation(), Errors.not_found(), etc.)
instead of string-based Result.fail() for structured error handling.""",
        "good": """return Result.fail(Errors.not_found("Task", uid))
return Result.fail(Errors.validation("Invalid input", field="email"))""",
        "bad": """return Result.fail("Task not found")  # String-based
return Result.fail(f"Error: {e}")  # String-based""",
    },
    "SKUEL008": {
        "title": "No Wrapper Classes Around UniversalNeo4jBackend",
        "severity": "WARNING",
        "description": """Use UniversalNeo4jBackend directly instead of creating wrapper classes.
Domain backends in adapters/persistence/neo4j/backends/ are legitimate extensions with
domain-specific relationship Cypher. New wrapper classes outside backends/ are violations.""",
        "good": """tasks_backend = UniversalNeo4jBackend[Task](driver, "Task", Task)
# Domain backends in backends/ are legitimate (TasksBackend, PsBackend, etc.)""",
        "bad": """class TasksBackend(UniversalNeo4jBackend[Task]):  # Don't create outside backends/
    pass""",
    },
    "SKUEL009": {
        "title": "Single-Element Tuple Defaults Are Bugs",
        "severity": "WARNING",
        "description": """A single-element tuple like (0,) is usually a mistake. If you want
a scalar default, remove the parentheses and comma.""",
        "good": """count: int = 0
name: str = "" """,
        "bad": """count: int = (0,)  # Probably meant 0
name: str = ("",)  # Probably meant "" """,
        "autofix": "Automatically replaced by --fix",
    },
    "SKUEL010": {
        "title": "Nested Empty Tuples Can't Be Stored",
        "severity": "WARNING",
        "description": """Neo4j cannot store nested collections. Use () instead of ((),).""",
        "good": """items: tuple = ()""",
        "bad": """items: tuple = ((),)  # Neo4j can't store this""",
        "autofix": "Automatically replaced by --fix",
    },
    "SKUEL011": {
        "title": "No hasattr() in Production Code",
        "severity": "WARNING",
        "description": """Use explicit type checks (isinstance, Protocol) instead of hasattr().
hasattr() is error-prone and bypasses type safety.

Exceptions: tests/, sort_functions.py.
Suppress: # skuel-lint: disable=SKUEL011 -- <reason>
File-level: # skuel-lint: disable-file=SKUEL011 -- <reason>""",
        "good": """# Use Protocol checking
if isinstance(obj, HasValue):
    return obj.value

# Use explicit attribute check
if user.preferences is not None:
    prefs = user.preferences

# Use helper for enums
from core.ports import get_enum_value
value = get_enum_value(obj)""",
        "bad": """# hasattr bypasses type safety
if hasattr(obj, 'value'):
    return obj.value

if hasattr(user, 'preferences'):
    prefs = user.preferences""",
    },
    "SKUEL012": {
        "title": "No Lambda Expressions",
        "severity": "WARNING",
        "description": """Use named functions instead of lambda expressions. Named functions
are self-documenting, testable, and reusable.

Exceptions: tests/, examples/.
Suppress: # skuel-lint: disable=SKUEL012 -- <reason>
File-level: # skuel-lint: disable-file=SKUEL012 -- <reason>""",
        "good": """from core.utils.sort_functions import get_priority_value

def get_priority(item):
    \"\"\"Get numeric priority for sorting.\"\"\"
    return item.priority.to_numeric()

tasks.sort(key=get_priority_value)""",
        "bad": """tasks.sort(key=lambda t: t.priority.to_numeric())
get_priority = lambda item: item.priority.to_numeric()""",
    },
    "SKUEL013": {
        "title": "Use RelationshipName Enum",
        "severity": "WARNING",
        "description": """Use RelationshipName enum instead of magic strings for
relationship type parameters. Single source of truth in relationship_names.py.""",
        "good": """from core.models.relationship_names import RelationshipName
await backend.add_relationship(uid1, RelationshipName.SERVES_GOAL, uid2)""",
        "bad": """# Magic string - error prone
await backend.add_relationship(uid1, "SERVES_GOAL", uid2)""",
    },
    "SKUEL014": {
        "title": "Use EntityType/NonKuDomain Enum",
        "severity": "WARNING",
        "description": """Use EntityType or NonKuDomain enum instead of magic strings for entity type
identification. Provides type safety and compile-time verification.""",
        "good": """from core.models.enums.entity_enums import EntityType
if entity.entity_type == EntityType.TASK:
    ...
if EntityType.TASK in activity.contexts:
    ...""",
        "bad": """# String comparison - error prone
if entity_type == "task":
    ...
if "task" in contexts:
    ...""",
    },
    "SKUEL015": {
        "title": "No print() in Production Code",
        "severity": "WARNING",
        "description": """Use logger.*() instead of print() for production runtime output.
Print bypasses logging infrastructure, making debugging and monitoring harder.

Exceptions: scripts/, debug utilities, docstring examples, __main__ blocks.
Suppress: # skuel-lint: disable=SKUEL015 -- <reason>
File-level: # skuel-lint: disable-file=SKUEL015 -- <reason>""",
        "good": """from core.utils.logging import get_logger
logger = get_logger("skuel.config")

def validate_config():
    if missing:
        logger.error("Missing config", missing=missing)
        return False""",
        "bad": """def validate_config():
    if missing:
        print(f"Missing: {missing}")  # Bypasses logging
        return False""",
    },
    "SKUEL016": {
        "title": "No Stale Poetry References",
        "severity": "WARNING",
        "description": """SKUEL migrated from Poetry to uv. References to poetry commands,
poetry.lock, or [tool.poetry] sections should be updated to their uv equivalents.

Common replacements:
  poetry install → uv sync
  poetry add → uv add
  poetry run → uv run
  poetry.lock → uv.lock
  [tool.poetry] → [project]""",
        "good": """# Install dependencies
uv sync

# Add a package
uv add weasyprint

# Run a script
uv run python scripts/my_script.py""",
        "bad": """# Stale Poetry references
poetry install
poetry add weasyprint
poetry run python scripts/my_script.py""",
    },
    "SKUEL017": {
        "title": "Narrow except Exception Catches",
        "severity": "WARNING",
        "description": """Bare `except Exception` catches mask bugs and make debugging harder.
Use specific exception types from core.utils.exception_types instead.

Allowed markers that suppress this rule:
  # intentional-broad: <reason>  — for catches that must remain broad (event handlers, monadic boundaries)
  # safety-net: <reason>         — for temporary broad catches during narrowing rollout

Import exception tuples from core.utils.exception_types:
  NEO4J_EXCEPTIONS, LLM_EXCEPTIONS, OPENAI_EXCEPTIONS, ANTHROPIC_EXCEPTIONS,
  FILE_IO_EXCEPTIONS, PARSING_EXCEPTIONS, DATA_CONVERSION_EXCEPTIONS, CONFIG_EXCEPTIONS""",
        "good": """from core.utils.exception_types import NEO4J_EXCEPTIONS
try:
    result = await self.backend.get(uid)
except NEO4J_EXCEPTIONS as e:
    return Result.fail(Errors.database(operation="get", message=str(e)))""",
        "bad": """try:
    result = await self.backend.get(uid)
except Exception as e:  # Too broad — masks non-database bugs
    return Result.fail(Errors.database(operation="get", message=str(e)))""",
    },
    "SKUEL018": {
        "title": "No Direct Access to RichUserContext RICH_ONLY_FIELDS",
        "severity": "WARNING",
        "description": """RichUserContext.RICH_ONLY_FIELDS default to None at standard depth and
are populated only by build_rich(). Direct attribute reads silently leak None
into call sites and defeat the accessor contract.

Use accessors from UserContext:
  Strict (raises at standard depth):   get_X() / get_tasks_by_goal() / get_blocked_tasks()
  Graceful (empty fallback):           X_or_empty() / tasks_by_goal_or_empty() /
                                       blocked_task_uids_or_empty()

Rich-only fields:
  tasks_by_goal, habits_by_goal, at_risk_habits, blocked_task_uids,
  principle_guided_choice_counts, recent_principle_aligned_choices

Relationship to RichUserContext (design note):
  RichUserContext narrows these fields to non-None at the type level. That
  guard is about static None-safety, not about bypassing this rule. This
  check is intentionally name-based (not type-aware) so every consumer uses
  the same read path — accessors — regardless of whether its local context
  is typed as UserContext or RichUserContext. The two mechanisms stack:
  narrow the type for compile-time safety, call the accessor at the read site.

Whitelisted files (direct access allowed):
  core/services/user/unified_user_context.py   — accessor definitions
  core/services/user/user_context_populator.py — rich-build writes
  tests/**                                     — fixtures and assertions
  (RichUserContext-typed consumers are NOT whitelisted — they still go
  through accessors.)""",
        "good": """# Strict: crash if not rich (intelligence services)
habits = self.context.get_habits_by_goal()

# Graceful: empty fallback (UI, stats)
at_risk = context.at_risk_habits_or_empty()
if at_risk := context.at_risk_habits_or_empty():
    ...""",
        "bad": """# Silent None leak at standard depth
if user_context.at_risk_habits:
    ...

# Asserts only fire in debug builds
assert self.context.habits_by_goal is not None
for goal_uid in self.context.habits_by_goal:
    ...""",
    },
    "SKUEL019": {
        "title": "Credential Reads Must Go Through get_credential()",
        "severity": "ERROR / WARNING",
        "description": """Credential-shaped env reads (`os.getenv`, `os.environ.get`,
`os.environ[K]`) must route through `get_credential()` from
`core.config.credential_store`. The funnel dispatches to the active backend
(`SKUEL_CREDENTIAL_BACKEND=keyring` → OS keychain, unset → Fernet-encrypted JSON)
and falls back to env when neither has the value. Raw `os.getenv` reads silently
skip the keychain under Stage 3 and only happen to work if the user runs through
the `with-secrets` wrapper — fragile and inconsistent.

Severity is decided by name:
  ERROR    — Name matches the credential catalog mirrored from
             `core/config/credential_setup.py::CredentialSetup.CREDENTIALS`
             (e.g. NEO4J_PASSWORD, OPENAI_API_KEY, RESEND_API_KEY).
  WARNING  — Name matches the credential-shape regex (`*_PASSWORD`, `*_TOKEN`,
             `*_API_KEY`, `*_SECRET`, `*_AUTH`, `*_PAT_*`) but isn't yet in
             the catalog — likely a new credential that should be added.

Exempt files (raw env reads are the implementation):
  core/config/credential_store.py        — defines get_credential()
  core/config/credential_setup.py        — checks SKUEL_MASTER_KEY
  scripts/migrate_secrets_to_homedir.py  — Stage 2 migration source
  scripts/migrate_secrets_to_keychain.py — Stage 3 migration source
  Test files                             — fixtures often poke env directly

Suppress: # skuel-lint: disable=SKUEL019 -- <reason>
File-level: # skuel-lint: disable-file=SKUEL019 -- <reason>""",
        "good": """from core.config.credential_store import get_credential

api_key = get_credential("OPENAI_API_KEY", fallback_to_env=True)
if not api_key:
    raise RuntimeError("OPENAI_API_KEY missing — set via `uv run python -m core.config`")""",
        "bad": """import os

api_key = os.environ.get("OPENAI_API_KEY")              # ERROR — in catalog
hf_token = os.getenv("HF_API_TOKEN")                    # ERROR — in catalog
neo4j_auth = os.environ["NEO4J_AUTH"]                   # WARNING — matches *_AUTH regex
stripe = os.getenv("CUSTOM_INTEGRATION_TOKEN")          # WARNING — matches *_TOKEN regex""",
    },
    "SKUEL020": {
        "title": "FastHTML Route Handlers Must Annotate request: Request",
        "severity": "ERROR",
        "description": """A FastHTML route handler (decorated with @rt(...), @app.get/post/
put/delete/patch/route(...)) whose parameter named `request` is annotated as anything
other than `Request` (e.g. `request: Any`) is silently broken.

FastHTML resolves handler annotations at runtime and instantiates the annotated class
(anno(**cargs)). Annotated `request: Any`, it treats `request` as a REQUIRED input field
to extract from the query/body and returns 400 "Missing required field: request" for every
caller — BEFORE any wrapping decorator runs. @boundary_handler, @csrf_protected, and
@require_* all use @wraps, so they preserve the broken inner annotation and the 400 fires
through them. The route fails closed (no data leak) but is dead, and its auth/CSRF gate
never executes.

This is invisible to mypy/ruff/the Route Security Audit — only a live request surfaces it.

Fix: annotate `request: Request` and add a RUNTIME import
`from adapters.inbound.fasthtml_types import Request` (not TYPE_CHECKING-only — files with
`from __future__ import annotations` still need the name resolvable at runtime). Unannotated
`request` is fine — FastHTML injects it. Helpers/middleware that are not @rt-decorated are
never bound by FastHTML and are not flagged.

Suppress: # skuel-lint: disable=SKUEL020 -- <reason>
File-level: # skuel-lint: disable-file=SKUEL020 -- <reason>""",
        "good": """from adapters.inbound.fasthtml_types import Request

@rt("/manifest.json")
async def pwa_manifest(request: Request) -> FileResponse:
    ...""",
        "bad": """@rt("/manifest.json")
async def pwa_manifest(request: Any) -> FileResponse:  # 400s before any gate runs
    ...""",
    },
    "SKUEL021": {
        "title": "No Raw Cypher in the Service Layer",
        "severity": "ERROR",
        "description": """ADR-044 places the hexagonal boundary at UniversalNeo4jBackend /
adapters/persistence/neo4j/. All Cypher lives below that boundary; services orchestrate and
call backend methods — they do not author Cypher. (SKUEL001 only bans APOC procedures; this
rule covers raw Cypher generally, which was previously unguarded.)

The detector flags high-signal, paren/sigil-anchored Cypher clauses (MATCH (, MERGE (,
OPTIONAL MATCH (, CREATE (, UNWIND $, CALL db.) so prose/comments are not caught. Comment
lines are skipped.

Fix: relocate the query into an adapter backend (adapters/persistence/neo4j/) behind a
core/ports protocol. See the relationship / ps_engagement / ingestion / query backends for
the pattern.

Suppress: # skuel-lint: disable=SKUEL021 -- <reason>
File-level: # skuel-lint: disable-file=SKUEL021 -- <reason>""",
        "good": """# Service delegates to the backend (Cypher lives below the boundary)
result = await self.backend.get_pinned_entities(user_uid)""",
        "bad": """# Raw Cypher authored in a core/services file
result = await self.executor.execute(
    query="MATCH (u:User {uid: $uid})-[:PINNED]->(e) RETURN e.uid", ...
)""",
    },
    "SKUEL022": {
        "title": "core/ Must Not Import adapters/",
        "severity": "ERROR",
        "description": """The hexagonal dependency direction is core → adapter, never the
reverse (ADR-044). A module under core/ that imports from adapters/ inverts that
direction: core is meant to define ports (protocols) and receive concrete adapters by
injection at the composition root, not reach down into them.

AST-based: flags `import adapters...` / `from adapters... import ...` at module scope
OR inside a function (a function-local import is the same runtime dependency, just
deferred past module load — and is the dodge a module-level-only check would miss).

TYPE_CHECKING-only imports are EXEMPT: an import under `if TYPE_CHECKING:` never executes,
so it cannot create a runtime core→adapter dependency (you can't smuggle a real runtime
dependency through it — it would NameError at runtime). Typing `self.backend` against a
concrete adapter class under TYPE_CHECKING is a separate, lower-priority purity concern,
not a layering violation.

Fix: depend on a core/ports protocol and receive the concrete adapter by injection;
build the adapter at the composition root (services_bootstrap/, or a factory below the
boundary). See the PsEngagement / ingestion / finance-renderer inversions for the pattern.

Suppress: # skuel-lint: disable=SKUEL022 -- <reason>
File-level: # skuel-lint: disable-file=SKUEL022 -- <reason>""",
        "good": """# core service depends on a port; the adapter is injected at composition
def __init__(self, backend: PsEngagementOperations) -> None:
    self._backend = backend

# TYPE_CHECKING-only adapter import for an annotation is fine (never executes)
if TYPE_CHECKING:
    from adapters.persistence.neo4j.ps_engagement_backend import PsEngagementBackend""",
        "bad": """# Runtime import of an adapter inside a core/ module — wrong direction
from adapters.persistence.neo4j.ps_engagement_backend import PsEngagementBackend

def __init__(self, executor) -> None:
    # ...or hidden inside a function (still a runtime core→adapter dependency):
    from adapters.persistence.neo4j.ps_engagement_backend import PsEngagementBackend
    self._backend = PsEngagementBackend(executor)""",
    },
}


@dataclass
class Violation:
    """A linting violation."""

    file_path: Path
    line_number: int
    column: int
    severity: Severity
    rule_id: str
    message: str
    suggestion: str
    fix_available: bool = False
    original_text: str = ""
    fixed_text: str = ""
    line_content: str = ""  # The actual line of code


@dataclass
class LintResult:
    """Results from linting."""

    violations: list[Violation] = field(default_factory=list)
    files_scanned: int = 0
    scan_time_ms: float = 0.0

    @property
    def has_critical(self) -> bool:
        return any(v.severity == Severity.CRITICAL for v in self.violations)

    @property
    def has_error(self) -> bool:
        return any(v.severity == Severity.ERROR for v in self.violations)

    @property
    def has_warning(self) -> bool:
        return any(v.severity == Severity.WARNING for v in self.violations)

    def by_severity(self, severity: Severity) -> list[Violation]:
        return [v for v in self.violations if v.severity == severity]

    def by_file(self) -> dict[Path, list[Violation]]:
        """Group violations by file for easier reading."""
        result: dict[Path, list[Violation]] = {}
        for v in self.violations:
            if v.file_path not in result:
                result[v.file_path] = []
            result[v.file_path].append(v)
        return result

    def by_rule(self, rule_id: str) -> list[Violation]:
        return [v for v in self.violations if v.rule_id == rule_id]


class SkuelLinter:
    """
    Unified SKUEL linter combining architecture and pattern rules.

    Design principles:
    - High-value rules only (no pedantic checks)
    - Auto-fix where possible
    - Clear, actionable suggestions
    - Minimal false positives
    """

    # Directories to exclude
    EXCLUDED_PATHS: ClassVar[list[str]] = [
        ".venv",
        "venv",
        "__pycache__",
        ".git",
        "node_modules",
        "dist",
        "build",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "htmlcov",
        "backup_archive",
        "z_archives",
        "zarchives",
        "scripts/migrations",  # Migration scripts document old patterns
        "scripts/lint_skuel",  # Linter files document patterns they check
        ".claude",  # Claude Code config/skills (documentation only)
    ]

    # Domain backends that legitimately extend UniversalNeo4jBackend
    CURRICULUM_BACKENDS: ClassVar[list[str]] = [
        "neo4j/backends/",  # All 27 domain backends live in the backends/ cluster package
    ]

    # SKUEL018: UserContext fields that default to None at standard depth and are
    # populated only by build_rich(). Direct reads must route through accessors
    # (get_X() strict / X_or_empty() graceful). Scalar rich-only fields have no
    # graceful accessor — a standard-depth read is a bug, not a degraded path.
    #
    # Canonical source of truth: `RichUserContext.RICH_ONLY_FIELDS` in
    # `core/services/user/unified_user_context.py`. Mirrored here because the
    # linter deliberately has no runtime dependency on `core/`. Keep both in
    # sync — `test_user_context_rich_only_drift.py` pins the contract.
    RICH_ONLY_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "tasks_by_goal",
            "habits_by_goal",
            "at_risk_habits",
            "blocked_task_uids",
            "principle_guided_choice_counts",
            "recent_principle_aligned_choices",
            "principle_integration_score",
        }
    )

    RICH_ONLY_WHITELIST: ClassVar[tuple[str, ...]] = (
        "core/services/user/unified_user_context.py",
        "core/services/user/user_context_populator.py",
    )

    # SKUEL019: Credential keys that must route through get_credential().
    #
    # Mirrored from `core/config/credential_setup.py::CredentialSetup.CREDENTIALS`.
    # The linter deliberately has no runtime dependency on `core/`, so the catalog
    # is duplicated here and pinned by `test_credential_catalog_drift.py`.
    # Keep both in sync — add a new credential to CREDENTIALS and the test will
    # tell you to mirror it here.
    CREDENTIAL_CATALOG: ClassVar[frozenset[str]] = frozenset(
        {
            "NEO4J_PASSWORD",
            "SESSION_SECRET_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "HF_API_TOKEN",
            "DEEPGRAM_API_KEY",
            "FIREFLY_APP_KEY",
            "FIREFLY_DB_PASSWORD",
            "FIREFLY_PAT_PERSONAL",
            "FIREFLY_PAT_SKUEL",
            "STRIPE_WEBHOOK_SECRET",
            "RESEND_API_KEY",
            "TEST_ADMIN_PASSWORD",
            "TEST_USER_PASSWORD",
        }
    )

    # SKUEL019: Names that match this regex but aren't in CREDENTIAL_CATALOG are
    # flagged as warnings — they're credential-shaped and probably belong in the
    # catalog. Matches `_(PASSWORD|TOKEN|API_KEY|SECRET|AUTH|PAT)` followed by
    # end-of-string or another underscore. So `SESSION_SECRET_KEY` matches via
    # `_SECRET_`, `FIREFLY_PAT_PERSONAL` matches via `_PAT_`, while `SKUEL_MASTER_KEY`
    # and `INGESTION_PATH` don't match anything.
    CREDENTIAL_SHAPE_RE: ClassVar[str] = r"_(PASSWORD|TOKEN|API_KEY|SECRET|AUTH|PAT)(?:_|$)"

    # SKUEL019: Files where raw env reads ARE the implementation. The funnel reads
    # env internally; the migration scripts parse env-shaped files; everything else
    # routes through get_credential().
    CREDENTIAL_PLUMBING_FILES: ClassVar[tuple[str, ...]] = (
        "core/config/credential_store.py",
        "core/config/credential_setup.py",
        "scripts/migrate_secrets_to_homedir.py",
        "scripts/migrate_secrets_to_keychain.py",
    )

    # Field → (strict_accessor, graceful_accessor). Strict raises at standard depth;
    # graceful returns an empty container. Fields with per-key accessors (e.g.
    # get_tasks_for_goal(uid)) also have dict-level strict accessors listed here.
    # graceful=None for scalar fields where a standard-depth read is a bug.
    RICH_ONLY_ACCESSORS: ClassVar[dict[str, tuple[str, str | None]]] = {
        "tasks_by_goal": ("get_tasks_by_goal()", "tasks_by_goal_or_empty()"),
        "habits_by_goal": ("get_habits_by_goal()", "habits_by_goal_or_empty()"),
        "at_risk_habits": (
            "get_habits_needing_reinforcement()",
            "at_risk_habits_or_empty()",
        ),
        "blocked_task_uids": ("get_blocked_tasks()", "blocked_task_uids_or_empty()"),
        "principle_guided_choice_counts": (
            "get_principle_guided_choice_counts()",
            "principle_guided_choice_counts_or_empty()",
        ),
        "recent_principle_aligned_choices": (
            "get_recent_principle_aligned_choices()",
            "recent_principle_aligned_choices_or_empty()",
        ),
        "principle_integration_score": ("get_principle_integration_score()", None),
    }

    def __init__(
        self,
        root_dir: Path,
        target_path: str | None = None,
        rules_filter: list[str] | None = None,
        changed_files: list[Path] | None = None,
    ) -> None:
        self.root_dir = root_dir
        self.target_path = target_path
        self.rules_filter = rules_filter
        self.changed_files = changed_files
        self.result = LintResult()

    @staticmethod
    def _git_changed_files(root_dir: Path, staged_only: bool = False) -> list[Path] | None:
        """Get Python files changed via git. Returns None if git is unavailable."""
        try:
            if staged_only:
                cmd = ["git", "diff", "--name-only", "--cached", "--diff-filter=ACMR"]
            else:
                cmd = ["git", "diff", "--name-only", "main...HEAD", "--diff-filter=ACMR"]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=root_dir, timeout=5)
            if result.returncode != 0:
                return None
            files = []
            for line in result.stdout.strip().splitlines():
                if line.endswith(".py"):
                    full_path = root_dir / line
                    if full_path.exists():
                        files.append(full_path)
            return files
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def lint(self) -> LintResult:
        """Run all linting rules."""
        start_time = time.time()
        python_files = self._find_python_files()
        self.result.files_scanned = len(python_files)

        for file_path in python_files:
            self._lint_file(file_path)

        self.result.scan_time_ms = (time.time() - start_time) * 1000
        return self.result

    def _should_run_rule(self, rule_id: str) -> bool:
        """Check if a rule should run based on filter."""
        if self.rules_filter is None:
            return True
        return rule_id in self.rules_filter

    def _is_line_suppressed(self, line: str, rule_id: str) -> bool:
        """Check for inline suppression: # skuel-lint: disable=SKUEL011"""
        return f"# skuel-lint: disable={rule_id}" in line

    def _is_file_suppressed(self, content: str, rule_id: str) -> bool:
        """Check for file-level suppression: # skuel-lint: disable-file=SKUEL011"""
        return f"# skuel-lint: disable-file={rule_id}" in content

    def _find_python_files(self) -> list[Path]:
        """Find all Python files to lint."""
        # Git-aware mode: use pre-resolved changed files
        if self.changed_files is not None:
            filtered = []
            for py_file in self.changed_files:
                rel_path = str(py_file.relative_to(self.root_dir))
                if not any(excluded in rel_path for excluded in self.EXCLUDED_PATHS):
                    filtered.append(py_file)
            return filtered

        python_files = []

        # Determine search path
        if self.target_path:
            search_root = self.root_dir / self.target_path
            if not search_root.exists():
                print(f"Error: Path not found: {search_root}", file=sys.stderr)
                return []
            if search_root.is_file():
                return [search_root] if search_root.suffix == ".py" else []
        else:
            search_root = self.root_dir

        for py_file in search_root.rglob("*.py"):
            rel_path = str(py_file.relative_to(self.root_dir))

            # Skip excluded paths
            if any(excluded in rel_path for excluded in self.EXCLUDED_PATHS):
                continue

            python_files.append(py_file)

        return python_files

    def _lint_file(self, file_path: Path) -> None:
        """Lint a single file."""
        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.split("\n")
            rel_path = file_path.relative_to(self.root_dir)
            is_test = "test_" in file_path.name or "/tests/" in str(file_path)
            is_service = "/services/" in str(file_path) and file_path.suffix == ".py"
            # SKUEL001 (APOC), SKUEL021 (raw Cypher), and SKUEL022 (import direction)
            # all enforce the ADR-044 hexagonal boundary, and all three now share the
            # SAME scope: every module under core/. Cypher of any kind is authored only
            # BELOW the boundary (adapters/persistence/neo4j/); core/ orchestrates and
            # calls backend methods. The scope grew to all of core/ once the last
            # Cypher-authoring leaks outside core/services|ingestion|infrastructure were
            # relocated below the boundary — core/utils (connection_fetcher, PR #75) and
            # core/models (search_request, PR #78). The SKUEL021 checker is AST-based and
            # skips docstring / bare-string example blocks, so the legitimate Cypher
            # examples in core/utils docstrings (processor_functions, neo4j_mapper, ...)
            # do not trip it; SKUEL001 has no hits in core/ outside the old gate.
            # Other service-only rules (SKUEL002/004/005/007/013/014) stay on is_service.
            path_str = str(file_path)
            is_core = "/core/" in path_str and file_path.suffix == ".py"
            # is_service is a strict subset of is_core today (no /services/ tree lives
            # outside core/), but keep it in the OR so a future non-core service dir
            # still gets the boundary rules.
            is_below_boundary = is_core or is_service

            # Run applicable rules
            if self._should_run_rule("SKUEL003"):
                self._check_is_err_usage(file_path, rel_path, content, lines)
            if self._should_run_rule("SKUEL009") and not is_test:
                self._check_tuple_defaults(file_path, rel_path, content, lines)
            if self._should_run_rule("SKUEL010") and not is_test:
                self._check_nested_tuple_defaults(file_path, rel_path, content, lines)
            if self._should_run_rule("SKUEL011") and not is_test:
                self._check_hasattr_usage(file_path, rel_path, content, lines)
            if self._should_run_rule("SKUEL012") and not is_test:
                self._check_lambda_usage(file_path, rel_path, content, lines)
            if self._should_run_rule("SKUEL015") and not is_test:
                self._check_print_statements(file_path, rel_path, content, lines)
            if self._should_run_rule("SKUEL016"):
                self._check_poetry_references(file_path, rel_path, content, lines)
            if self._should_run_rule("SKUEL017") and not is_test:
                self._check_broad_exception_catches(file_path, rel_path, content, lines)
            if self._should_run_rule("SKUEL018") and not is_test:
                self._check_rich_only_field_access(file_path, rel_path, content, lines)
            if self._should_run_rule("SKUEL019") and not is_test:
                self._check_credential_env_reads(file_path, rel_path, content, lines)
            if self._should_run_rule("SKUEL020") and not is_test:
                self._check_request_annotation(file_path, rel_path, content, lines)

            # INFO rules (always run for visibility)
            if self._should_run_rule("SKUEL006"):
                self._check_todo_comments(file_path, rel_path, content, lines)

            # Boundary rules (ADR-044): no APOC, no raw Cypher anywhere in core/.
            if is_below_boundary and not is_test:
                if self._should_run_rule("SKUEL001"):
                    self._check_apoc_in_services(file_path, rel_path, content, lines)
                if self._should_run_rule("SKUEL021"):
                    self._check_raw_cypher_in_services(file_path, rel_path, content, lines)

            # Import-direction rule (ADR-044): all of core/, not just services.
            if is_core and not is_test and self._should_run_rule("SKUEL022"):
                self._check_core_imports_adapter(file_path, rel_path, content, lines)

            if is_service and not is_test:
                if self._should_run_rule("SKUEL002"):
                    self._check_semantic_type_strings(file_path, rel_path, content, lines)
                if self._should_run_rule("SKUEL004"):
                    self._check_confidence_thresholds(file_path, rel_path, content, lines)
                if self._should_run_rule("SKUEL005"):
                    self._check_result_return_types(file_path, rel_path, content, lines)
                if self._should_run_rule("SKUEL007"):
                    self._check_string_result_fail(file_path, rel_path, content, lines)
                if self._should_run_rule("SKUEL013"):
                    self._check_relationship_name_strings(file_path, rel_path, content, lines)
                if self._should_run_rule("SKUEL014"):
                    self._check_entity_type_strings(file_path, rel_path, content, lines)

            if "/adapters/persistence/" in str(file_path):
                if self._should_run_rule("SKUEL008"):
                    self._check_backend_wrappers(file_path, rel_path, content)

        except Exception as e:
            print(f"Error linting {file_path}: {e}", file=sys.stderr)

    # =========================================================================
    # CRITICAL RULES
    # =========================================================================

    def _check_apoc_in_services(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL001 [CRITICAL]: No banned APOC procedures authored above the boundary.

        APOC is a Neo4j server-side procedure namespace invoked via ``CALL apoc...``
        inside Cypher — it belongs to the adapter, not core/ (ADR-044); domain code
        uses pure Cypher / CypherGenerator. Like SKUEL021, this is AST-based: a banned
        procedure only matters when it appears in a *used* string literal (the Cypher
        a service would hand to the driver, incl. f-string parts). Inert bare-string
        statements — docstrings AND mid-body ``USAGE EXAMPLES`` blocks — are skipped by
        node identity, and comments (full-line AND inline) are not string nodes at all,
        so an APOC name in documentation/prose (e.g. explaining *why* APOC is banned)
        never trips this rule. That keeps it correct now that its gate covers all of
        core/. CRITICAL and intentionally unsuppressable.
        """
        banned_apoc = (
            "apoc.path.subgraphNodes",
            "apoc.path.subgraphAll",
            "apoc.path.expandConfig",
            "apoc.path.spanningTree",
            "apoc.cypher.run",
            "apoc.cypher.runMany",
            "apoc.map.",
            "apoc.schema.",
            "apoc.meta.",
        )

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return

        inert_ids = self._inert_string_constant_ids(tree)
        reported_lines: set[int] = set()

        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if id(node) in inert_ids:
                continue
            apoc_proc = next((p for p in banned_apoc if p in node.value), None)
            if apoc_proc is None:
                continue

            line_num = node.lineno
            if line_num in reported_lines:
                continue
            reported_lines.add(line_num)
            line = lines[line_num - 1] if 0 < line_num <= len(lines) else ""
            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=node.col_offset,
                    severity=Severity.CRITICAL,
                    rule_id="SKUEL001",
                    message=f"APOC procedure '{apoc_proc}' authored above the boundary",
                    suggestion="Use CypherGenerator or pure Cypher instead",
                    line_content=line.strip(),
                )
            )

    # Paren/sigil-anchored Cypher clause markers that essentially never appear in
    # prose. (DETACH DELETE is intentionally excluded — real Cypher uses a variable,
    # `DETACH DELETE n`, which is indistinguishable from docstring prose like
    # "cascade DETACH DELETE (default False)".)
    CYPHER_MARKERS: ClassVar[tuple[str, ...]] = (
        "MATCH (",
        "MERGE (",
        "OPTIONAL MATCH (",
        "OPTIONAL MATCH path",
        "CREATE (",
        "UNWIND $",
        "CALL db.",
    )

    @staticmethod
    def _inert_string_constant_ids(tree: ast.AST) -> set[int]:
        """``id()``s of string Constants that are inert bare-expression statements.

        Module / class / function docstrings AND mid-body ``USAGE EXAMPLES`` blocks
        are bare string statements — never assigned, passed, or executed — and may
        legitimately quote Cypher. They are skipped by node identity so the
        raw-Cypher check fires only on Cypher that is actually *used* (assigned,
        passed, returned, interpolated). Mirrors the proven technique in
        ``tests/test_core_utils_boundary.py``.
        """
        inert: set[int] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                inert.add(id(node.value))
        return inert

    def _check_raw_cypher_in_services(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL021 [ERROR]: No raw Cypher authored above the hexagonal boundary.

        ADR-044 puts the boundary at ``UniversalNeo4jBackend`` /
        ``adapters/persistence/neo4j/``: all Cypher lives below it. Code above the
        boundary (all of ``core/``) orchestrates and calls backend methods; it does
        not author Cypher. (Note SKUEL001 only bans APOC — this rule covers raw
        Cypher generally.)

        AST-based, not a line scan: Cypher only matters when it is *used* (assigned,
        passed, returned, interpolated). String literals that are inert bare
        expression statements — docstrings AND mid-body ``USAGE EXAMPLES`` blocks —
        legitimately quote Cypher and are skipped by node identity. f-string literal
        parts are scanned (a marker interpolated into a query is still authored
        Cypher). This keeps the rule quiet on the docstring Cypher examples that live
        throughout ``core/utils`` while still catching real leaks anywhere in core/.

        High-signal clause markers only, to avoid flagging prose. Relocate the query
        into an adapter backend behind a ``core/ports`` protocol (see the
        connection-fetch / relationship / ingestion backends for the pattern).

        Suppress: # skuel-lint: disable=SKUEL021 -- <reason>
        File-level: # skuel-lint: disable-file=SKUEL021 -- <reason>
        """
        if self._is_file_suppressed(content, "SKUEL021"):
            return

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return

        inert_ids = self._inert_string_constant_ids(tree)
        reported_lines: set[int] = set()

        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if id(node) in inert_ids:
                continue
            marker = next((m for m in self.CYPHER_MARKERS if m in node.value), None)
            if marker is None:
                continue

            line_num = node.lineno
            # One violation per source line (matches the old line-granularity and
            # collapses the several Constant parts an f-string splits into).
            if line_num in reported_lines:
                continue
            # Per-line suppression honours a comment on the literal's first line.
            line = lines[line_num - 1] if 0 < line_num <= len(lines) else ""
            if self._is_line_suppressed(line, "SKUEL021"):
                continue

            reported_lines.add(line_num)
            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=node.col_offset,
                    severity=Severity.ERROR,
                    rule_id="SKUEL021",
                    message=f"Raw Cypher ('{marker.strip()}') authored above the boundary",
                    suggestion=(
                        "Relocate the query to an adapter backend "
                        "(adapters/persistence/neo4j/) behind a core/ports protocol (ADR-044)"
                    ),
                    line_content=line.strip(),
                )
            )

    # =========================================================================
    # ERROR RULES
    # =========================================================================

    def _check_semantic_type_strings(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL002 [ERROR]: Use SemanticRelationshipType enum, not magic strings.
        """
        semantic_types = [
            "REQUIRES_THEORETICAL_UNDERSTANDING",
            "REQUIRES_PRACTICAL_APPLICATION",
            "REQUIRES_CONCEPTUAL_FOUNDATION",
            "BUILDS_ON_FOUNDATION",
            "HAS_BROADER_CONCEPT",
            "HAS_NARROWER_CONCEPT",
            "SHARES_PRINCIPLE_WITH",
            "ANALOGOUS_TO",
        ]

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#") or '"""' in line or "'''" in line:
                continue

            for sem_type in semantic_types:
                if f'"{sem_type}"' in line or f"'{sem_type}'" in line:
                    if f"SemanticRelationshipType.{sem_type}" not in line:
                        self.result.violations.append(
                            Violation(
                                file_path=rel_path,
                                line_number=line_num,
                                column=line.find(sem_type),
                                severity=Severity.ERROR,
                                rule_id="SKUEL002",
                                message=f"Magic string '{sem_type}' - use enum instead",
                                suggestion=f"Use SemanticRelationshipType.{sem_type}",
                                line_content=line.strip(),
                            )
                        )

    def _check_is_err_usage(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL003 [ERROR]: Use .is_error instead of deprecated .is_err.
        """
        if "lint_skuel" in str(file_path):
            return

        pattern = r"\.is_err\b"

        for match in re.finditer(pattern, content):
            line_num = content[: match.start()].count("\n") + 1
            line = lines[line_num - 1]
            col = match.start() - content[: match.start()].rfind("\n") - 1

            if ".is_error" in line:
                continue

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=col,
                    severity=Severity.ERROR,
                    rule_id="SKUEL003",
                    message="Deprecated .is_err - use .is_error instead",
                    suggestion="Replace .is_err with .is_error",
                    fix_available=True,
                    original_text=".is_err",
                    fixed_text=".is_error",
                    line_content=line.strip(),
                )
            )

    # =========================================================================
    # WARNING RULES
    # =========================================================================

    def _check_confidence_thresholds(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL004 [WARNING]: Semantic queries should have confidence thresholds.
        """
        semantic_patterns = [
            "REQUIRES_THEORETICAL_UNDERSTANDING",
            "REQUIRES_PRACTICAL_APPLICATION",
            "REQUIRES_CONCEPTUAL_FOUNDATION",
            "BUILDS_ON_FOUNDATION",
            "SHARES_PRINCIPLE_WITH",
            "ANALOGOUS_TO",
        ]

        structural_patterns = [
            "APPLIES_KNOWLEDGE",
            "ENABLES",
            "PREREQUISITE",
            "HAS_STEP",
            "HAS_PATH",
            "CONTRIBUTES_TO",
        ]

        for line_num, line in enumerate(lines, start=1):
            if "MATCH" not in line:
                continue

            has_semantic = any(p in line for p in semantic_patterns)
            has_structural = any(p in line for p in structural_patterns)

            if has_semantic and not has_structural:
                context = "\n".join(lines[line_num : min(line_num + 5, len(lines))])
                if "confidence" not in context:
                    self.result.violations.append(
                        Violation(
                            file_path=rel_path,
                            line_number=line_num,
                            column=0,
                            severity=Severity.WARNING,
                            rule_id="SKUEL004",
                            message="Semantic query without confidence threshold",
                            suggestion="Add: WHERE r.confidence >= $min_confidence",
                            line_content=line.strip(),
                        )
                    )

    def _check_result_return_types(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL005 [WARNING]: Service methods should return Result[T].
        """
        if "protocol" in str(file_path).lower():
            return

        if self._is_file_suppressed(content, "SKUEL005"):
            return

        utility_patterns = [
            "get(self, key:",
            "set(self, key:",
            "delete(self, key:",
            "clear(self)",
            "_get_",
            "get_hit_rate",
            "is_expired",
            "_evict",
            "_adaptive",
            "_update_access",
            "_remove_from",
            "handle_",
            "learn_from_",
            "increment_",
            "ensure_",
        ]

        base_method_indent: int | None = None

        for line_num, line in enumerate(lines, start=1):
            if not line.strip():
                continue

            stripped = line.lstrip()
            indent = len(line) - len(stripped)

            if stripped.startswith(("def ", "async def ")):
                if base_method_indent is None:
                    base_method_indent = indent
                elif indent <= base_method_indent:
                    base_method_indent = indent

            if "async def" in line and "->" in line:
                if base_method_indent is not None and indent > base_method_indent:
                    continue

                if "def _" in line or "def __" in line:
                    continue

                if any(p in line for p in utility_patterns):
                    continue

                # Skip @classmethod methods (factory methods on dataclasses, not services)
                is_classmethod = False
                for prev_idx in range(line_num - 2, max(0, line_num - 5), -1):
                    prev_stripped = lines[prev_idx].strip()
                    if prev_stripped == "@classmethod":
                        is_classmethod = True
                        break
                    if not prev_stripped.startswith("@"):
                        break
                if is_classmethod:
                    continue

                if "Result[" not in line and not self._is_line_suppressed(line, "SKUEL005"):
                    self.result.violations.append(
                        Violation(
                            file_path=rel_path,
                            line_number=line_num,
                            column=0,
                            severity=Severity.WARNING,
                            rule_id="SKUEL005",
                            message="Service method should return Result[T]",
                            suggestion="Change return type to Result[T]",
                            line_content=line.strip(),
                        )
                    )

    def _check_string_result_fail(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL007 [WARNING]: Use Errors factory instead of string Result.fail().
        """
        pattern = r'Result\.fail\s*\(\s*[f]?["\']'

        for match in re.finditer(pattern, content):
            line_num = content[: match.start()].count("\n") + 1
            line = lines[line_num - 1]

            if "Errors." in line or "result.error" in line or ".error)" in line:
                continue

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=0,
                    severity=Severity.WARNING,
                    rule_id="SKUEL007",
                    message="String-based Result.fail() - use Errors factory",
                    suggestion="Use Errors.validation(), Errors.not_found(), etc.",
                    line_content=line.strip(),
                )
            )

    def _check_backend_wrappers(self, file_path: Path, rel_path: Path, content: str) -> None:
        """
        SKUEL008 [WARNING]: No wrapper classes around UniversalNeo4jBackend.

        Exception: Curriculum backends (ls, lp, moc, ku) legitimately extend
        UniversalNeo4jBackend to add domain-specific methods.
        """
        if "universal_backend" in str(file_path):
            return

        # Skip curriculum backends - these legitimately extend for domain methods
        if any(backend in str(file_path) for backend in self.CURRICULUM_BACKENDS):
            return

        if "UniversalNeo4jBackend" not in content:
            return

        pattern = r"class\s+(\w+Backend)\([^)]*UniversalNeo4jBackend"
        lines = content.split("\n")
        for match in re.finditer(pattern, content):
            class_name = match.group(1)
            line_num = content[: match.start()].count("\n") + 1

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=0,
                    severity=Severity.WARNING,
                    rule_id="SKUEL008",
                    message=f"Wrapper class '{class_name}' around UniversalNeo4jBackend",
                    suggestion="Use UniversalNeo4jBackend directly (100% dynamic pattern)",
                    line_content=lines[line_num - 1].strip() if line_num <= len(lines) else "",
                )
            )

    def _check_hasattr_usage(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL011 [WARNING]: No hasattr() in production code.
        """
        if self._is_file_suppressed(content, "SKUEL011"):
            return

        file_str = str(file_path)
        # Sort functions use hasattr for generic attribute access
        if "sort_functions.py" in file_str:
            return

        pattern = r"\bhasattr\s*\("

        # Track docstring state to skip mentions in docstrings
        in_docstring = False
        docstring_delim = None
        docstring_lines: set[int] = set()
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            for delim in ('"""', "'''"):
                count = stripped.count(delim)
                if count >= 2 and stripped.startswith(delim):
                    docstring_lines.add(i)
                elif count == 1:
                    if not in_docstring:
                        in_docstring = True
                        docstring_delim = delim
                    elif docstring_delim == delim:
                        in_docstring = False
                        docstring_delim = None
            if in_docstring:
                docstring_lines.add(i)

        for match in re.finditer(pattern, content):
            line_num = content[: match.start()].count("\n") + 1
            line = lines[line_num - 1]

            # Skip comments and docstrings
            if line.strip().startswith("#") or line_num in docstring_lines:
                continue

            # Skip if hasattr appears after a # comment on the same line
            col = match.start() - content[: match.start()].rfind("\n") - 1
            before_match = line[:col]
            if "#" in before_match:
                continue

            if self._is_line_suppressed(line, "SKUEL011"):
                continue

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=col,
                    severity=Severity.WARNING,
                    rule_id="SKUEL011",
                    message="hasattr() usage - use Protocol/isinstance instead",
                    suggestion="Use isinstance(obj, Protocol) or explicit attribute checks",
                    line_content=line.strip(),
                )
            )

    def _check_lambda_usage(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL012 [WARNING]: No lambda expressions - use named functions.
        """
        if self._is_file_suppressed(content, "SKUEL012"):
            return

        file_str = str(file_path)
        if "/examples/" in file_str:
            return

        pattern = r"\blambda\s+\w*\s*:"

        for match in re.finditer(pattern, content):
            line_num = content[: match.start()].count("\n") + 1
            line = lines[line_num - 1]

            # Skip comments and docstrings
            stripped = line.strip()
            if stripped.startswith("#") or '"""' in line or "'''" in line:
                continue

            if self._is_line_suppressed(line, "SKUEL012"):
                continue

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=match.start() - content[: match.start()].rfind("\n") - 1,
                    severity=Severity.WARNING,
                    rule_id="SKUEL012",
                    message="Lambda expression - use named function instead",
                    suggestion="Define a named function or use sort_functions helper",
                    line_content=line.strip(),
                )
            )

    def _check_relationship_name_strings(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL013 [WARNING]: Use RelationshipName enum instead of magic strings.
        """
        # Common relationship names that should use enum
        relationship_names = [
            # Core domain relationships
            "SERVES_GOAL",
            "SERVES_LIFE_PATH",
            "APPLIES_KNOWLEDGE",
            "REQUIRES_KNOWLEDGE",
            "REINFORCES_KNOWLEDGE",
            "FULFILLS_GOAL",
            "SUPPORTS_GOAL",
            "ALIGNED_WITH_PRINCIPLE",
            "GUIDED_BY_PRINCIPLE",
            "GUIDES_GOAL",
            "GUIDES_CHOICE",
            "HAS_STEP",
            "HAS_PATH",
            "CONTRIBUTES_TO",
            "ENABLES",
            "PREREQUISITE",
            # Curriculum composition
            "USES_KU",
            "TRAINS_KU",
            "ORGANIZES",
            # Lateral relationships (Phase 5)
            "BLOCKS",
            "BLOCKED_BY",
            "DEPENDS_ON",
            "COMPLEMENTARY_TO",
            "ALTERNATIVE_TO",
            "PREREQUISITE_FOR",
            "SIBLING",
            # Sharing & groups
            "SHARES_WITH",
            "SHARED_WITH_GROUP",
            "MEMBER_OF",
            # Ownership
            "OWNS",
        ]

        # Track docstring context
        in_docstring = False
        docstring_delimiter = None

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Track docstring state
            if not in_docstring:
                for delim in ['"""', "'''"]:
                    if delim in stripped:
                        count = stripped.count(delim)
                        if count == 1:
                            in_docstring = True
                            docstring_delimiter = delim
                            break
                        # Single-line docstring - skip this line
                        if count >= 2 and stripped.startswith(delim):
                            continue
            else:
                if docstring_delimiter and docstring_delimiter in stripped:
                    in_docstring = False
                    docstring_delimiter = None
                continue  # Skip lines inside docstrings

            if stripped.startswith("#"):
                continue

            # Skip if already using enum
            if "RelationshipName." in line:
                continue

            for rel_name in relationship_names:
                # Check for quoted string usage in function calls
                if f'"{rel_name}"' in line or f"'{rel_name}'" in line:
                    # Skip if it's in a Cypher query string (those need literal strings)
                    if "MATCH" in line or "-[:" in line or "]->" in line or "CREATE" in line:
                        continue

                    # Skip if we're inside a multi-line Cypher query (check context)
                    # Look at surrounding lines for Cypher indicators
                    context_start = max(0, line_num - 10)
                    context_lines = lines[context_start:line_num]
                    in_cypher_context = any(
                        "MATCH" in l or "WHERE any(r in relationships" in l or "type(r) IN" in l
                        for l in context_lines
                    )
                    if in_cypher_context:
                        continue

                    self.result.violations.append(
                        Violation(
                            file_path=rel_path,
                            line_number=line_num,
                            column=line.find(rel_name),
                            severity=Severity.WARNING,
                            rule_id="SKUEL013",
                            message=f"Magic string '{rel_name}' - use RelationshipName enum",
                            suggestion=f"Use RelationshipName.{rel_name}",
                            line_content=line.strip(),
                        )
                    )

    def _check_entity_type_strings(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL014 [WARNING]: Use EntityType/NonKuDomain enum instead of magic strings.
        """
        # Entity types that should use enum
        entity_types = [
            # Activity domains
            "task",
            "habit",
            "goal",
            "event",
            "choice",
            "principle",
            # Curriculum
            "ku",
            "path_step",
            "learning_path",
            "exercise",
            "revised_exercise",
            # Forms
            "form_template",
            "form_submission",
            # Curated
            "resource",
            # Content processing
            "exercise_submission",
            "activity_report",
            "exercise_report",
            "interaction",
            # Journal
            "je_input",
            "je_output",
            # Destination
            "life_path",
            # NonKuDomain
            "finance",
            # Old aliases (catch stale magic strings)
            "article",
            "lesson",
            "submission",
            "journal",
            "submission_report",
        ]

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#") or '"""' in line or "'''" in line:
                continue

            # Skip if already using enum
            if "EntityType." in line or "NonKuDomain." in line:
                continue

            # Skip imports and type hints
            if "import" in line or "EntityType" in line or "NonKuDomain" in line:
                continue

            for entity_type in entity_types:
                # Look for entity type comparisons like == "task" or in ["task", ...]
                patterns_to_check = [
                    f'== "{entity_type}"',
                    f"== '{entity_type}'",
                    f'"{entity_type}" in ',
                    f"'{entity_type}' in ",
                    f'entity_type == "{entity_type}"',
                    f"entity_type == '{entity_type}'",
                ]

                for pattern in patterns_to_check:
                    if pattern in line.lower():
                        self.result.violations.append(
                            Violation(
                                file_path=rel_path,
                                line_number=line_num,
                                column=0,
                                severity=Severity.WARNING,
                                rule_id="SKUEL014",
                                message=f"Magic string '{entity_type}' - use EntityType/NonKuDomain enum",
                                suggestion=f"Use EntityType.{entity_type.upper()} or NonKuDomain.{entity_type.upper()}",
                                line_content=line.strip(),
                            )
                        )
                        break  # Only report once per line

    def _check_print_statements(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL015 [WARNING]: No print() in production code - use logger.

        Exception: CLI utilities, scripts, tests, docstrings, __main__ blocks.
        """
        if self._is_file_suppressed(content, "SKUEL015"):
            return

        file_str = str(file_path)
        # Directory-scoped exemptions: scripts, examples, debug utilities
        if any(
            pattern in file_str
            for pattern in ["/scripts/", "/examples/", "debug_", "lint_skuel.py", "dev"]
        ):
            return

        # Track context state
        in_docstring = False
        in_main_block = False
        docstring_delimiter = None

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Track docstring state (handles multi-line docstrings)
            if not in_docstring:
                # Check for docstring start
                for delim in ['"""', "'''"]:
                    if delim in stripped:
                        # Count occurrences to detect single-line vs multi-line
                        count = stripped.count(delim)
                        if count == 1:
                            # Multi-line docstring starts
                            in_docstring = True
                            docstring_delimiter = delim
                            break
                        if count >= 2:
                            # Single-line docstring or line with string literal
                            # Skip this line entirely if it looks like a docstring
                            if stripped.startswith(delim):
                                break
            else:
                # Check for docstring end
                if docstring_delimiter and docstring_delimiter in stripped:
                    in_docstring = False
                    docstring_delimiter = None
                continue  # Skip all lines inside docstrings

            # Track __main__ block
            if 'if __name__ == "__main__"' in line or "if __name__ == '__main__'" in line:
                in_main_block = True
                continue

            # Skip if in __main__ block (rest of file after that)
            if in_main_block:
                continue

            # Skip comments
            if stripped.startswith("#"):
                continue

            # Skip doctest examples (>>> prefix)
            if stripped.startswith(">>>"):
                continue

            # Check for print() calls
            pattern = r"\bprint\s*\("
            for match in re.finditer(pattern, line):
                # Skip if it's a comment on the same line before print
                before_print = line[: match.start()]
                if "#" in before_print:
                    continue

                # Skip if print is inside a string (rough heuristic)
                # Count quotes before the print to detect if we're in a string
                quote_count = before_print.count('"') + before_print.count("'")
                if quote_count % 2 == 1:
                    continue  # Odd number of quotes = likely inside a string

                if self._is_line_suppressed(line, "SKUEL015"):
                    continue

                self.result.violations.append(
                    Violation(
                        file_path=rel_path,
                        line_number=line_num,
                        column=match.start(),
                        severity=Severity.WARNING,
                        rule_id="SKUEL015",
                        message="print() in production code - use logger instead",
                        suggestion="Use logger.info(), logger.debug(), or logger.error()",
                        line_content=line.strip(),
                    )
                )

    def _check_poetry_references(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL016 [WARNING]: No stale Poetry references — SKUEL uses uv.

        Catches: poetry install, poetry add, poetry run, poetry.lock,
        [tool.poetry], pyproject.toml poetry sections.

        Exceptions: Migration scripts, ADR docs (historical), this linter's rule docs.
        """
        file_str = str(file_path)

        # Skip files where poetry references are historical/expected
        if any(
            skip in file_str
            for skip in [
                "/migrations/",
                "lint_skuel.py",  # This linter documents the pattern
                "detect_library_changes.py",  # May reference lock file names
            ]
        ):
            return

        poetry_patterns = [
            (r"\bpoetry\s+install\b", "poetry install", "uv sync"),
            (r"\bpoetry\s+add\b", "poetry add", "uv add"),
            (r"\bpoetry\s+remove\b", "poetry remove", "uv remove"),
            (r"\bpoetry\s+run\b", "poetry run", "uv run"),
            (r"\bpoetry\s+lock\b", "poetry lock", "uv lock"),
            (r"\bpoetry\s+update\b", "poetry update", "uv lock --upgrade"),
            (r"\bpoetry\.lock\b", "poetry.lock", "uv.lock"),
            (r"\[tool\.poetry\b", "[tool.poetry]", "[project]"),
        ]

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Skip comments that explain the migration itself
            if stripped.startswith("#") and (
                "migrat" in stripped.lower() or "was" in stripped.lower()
            ):
                continue

            for pattern, match_text, replacement in poetry_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    self.result.violations.append(
                        Violation(
                            file_path=rel_path,
                            line_number=line_num,
                            column=match.start(),
                            severity=Severity.WARNING,
                            rule_id="SKUEL016",
                            message=f"Stale Poetry reference '{match_text}' — SKUEL uses uv",
                            suggestion=f"Replace with: {replacement}",
                            line_content=line.strip(),
                        )
                    )
                    break  # Only report once per line

    def _check_broad_exception_catches(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL017 [WARNING]: Bare `except Exception` without justification.

        Flags `except Exception` catches that don't have an `# intentional-broad:`
        or `# safety-net:` comment on the same line or the line above.

        Exceptions: test files, scripts/, CLI entrypoints, this linter.
        """
        file_str = str(file_path)

        # Skip files where broad catches are expected
        if any(
            skip in file_str
            for skip in [
                "lint_skuel.py",
                "/scripts/",
                "result_simplified.py",  # Monadic boundaries are annotated separately
            ]
        ):
            return

        pattern = re.compile(r"\bexcept\s+Exception\b")

        # Track whether we're inside a docstring
        in_docstring = False
        docstring_delim = None

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Track docstring boundaries
            for delim in ('"""', "'''"):
                count = stripped.count(delim)
                if count >= 2:
                    pass  # Opening and closing on same line
                elif count == 1:
                    if not in_docstring:
                        in_docstring = True
                        docstring_delim = delim
                    elif docstring_delim == delim:
                        in_docstring = False
                        docstring_delim = None

            if in_docstring:
                continue

            if not pattern.search(line):
                continue

            # Skip comments
            if stripped.startswith("#"):
                continue

            # Check if the same line has a suppression comment
            if (
                "# intentional-broad:" in line
                or "# safety-net:" in line
                or self._is_line_suppressed(line, "SKUEL017")
            ):
                continue

            # Check if the line above has a suppression comment
            if line_num >= 2:
                prev_line = lines[line_num - 2]
                if "# intentional-broad:" in prev_line or "# safety-net:" in prev_line:
                    continue

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=line.find("except"),
                    severity=Severity.WARNING,
                    rule_id="SKUEL017",
                    message="Bare `except Exception` — use specific exception types",
                    suggestion=(
                        "Import from core.utils.exception_types "
                        "(NEO4J_EXCEPTIONS, LLM_EXCEPTIONS, etc.) "
                        "or add `# intentional-broad: <reason>` comment"
                    ),
                    line_content=line.strip(),
                )
            )

    def _check_rich_only_field_access(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL018 [WARNING]: Direct access to RichUserContext RICH_ONLY_FIELDS.

        Flags `.<rich_field>` attribute reads outside whitelisted files. Writes
        (assignment targets) and the accessor methods (`.get_X()`, `.X_or_empty()`)
        are not flagged. The word boundary `\\b` anchors rejection of
        `.at_risk_habits_or_empty` (underscore is a word character).

        Whitelist: unified_user_context.py (accessor bodies),
        user_context_populator.py (rich-build writes), and all test files.
        """
        if self._is_file_suppressed(content, "SKUEL018"):
            return

        rel_str = str(rel_path).replace("\\", "/")
        if any(rel_str.endswith(w) for w in self.RICH_ONLY_WHITELIST):
            return

        field_alternatives = "|".join(sorted(self.RICH_ONLY_FIELDS))
        pattern = re.compile(rf"\.({field_alternatives})\b")

        in_docstring = False
        docstring_delim: str | None = None

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Track docstring boundaries (skip doc examples)
            for delim in ('"""', "'''"):
                count = stripped.count(delim)
                if count >= 2:
                    pass
                elif count == 1:
                    if not in_docstring:
                        in_docstring = True
                        docstring_delim = delim
                    elif docstring_delim == delim:
                        in_docstring = False
                        docstring_delim = None

            if in_docstring:
                continue
            if stripped.startswith("#"):
                continue

            for match in pattern.finditer(line):
                field_name = match.group(1)
                col = match.start()

                # Skip writes: `.field =` (but not `==`). Look forward past whitespace.
                rest = line[match.end() :]
                rest_stripped = rest.lstrip()
                if rest_stripped.startswith("=") and not rest_stripped.startswith("=="):
                    continue

                if self._is_line_suppressed(line, "SKUEL018"):
                    continue

                strict, graceful = self.RICH_ONLY_ACCESSORS[field_name]
                if graceful is None:
                    suggestion = (
                        f"Use `{strict}` (strict, raises at standard depth). "
                        f"No graceful accessor — standard-depth read is a bug. "
                        f"See RichUserContext.RICH_ONLY_FIELDS."
                    )
                else:
                    suggestion = (
                        f"Use `{strict}` (strict, raises at standard depth) "
                        f"or `{graceful}` (graceful fallback). "
                        f"See RichUserContext.RICH_ONLY_FIELDS."
                    )
                self.result.violations.append(
                    Violation(
                        file_path=rel_path,
                        line_number=line_num,
                        column=col,
                        severity=Severity.WARNING,
                        rule_id="SKUEL018",
                        message=(
                            f"Direct read of UserContext rich-only field "
                            f"`.{field_name}` — use accessor"
                        ),
                        suggestion=suggestion,
                        line_content=line.strip(),
                    )
                )

    def _check_credential_env_reads(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL019 [ERROR / WARNING]: Credential-shaped env reads must route
        through ``get_credential()``.

        Detects three call shapes:
          os.getenv("KEY")              and  os.getenv("KEY", default)
          os.environ.get("KEY")         and  os.environ.get("KEY", default)
          os.environ["KEY"]             (subscript form)

        Severity is decided by name:
          ERROR    — key is in ``CREDENTIAL_CATALOG`` (mirrored from
                     credential_setup.py).
          WARNING  — key matches ``CREDENTIAL_SHAPE_RE`` but isn't catalogued
                     yet (probably belongs in the catalog).

        Exempt files: the credential plumbing in ``CREDENTIAL_PLUMBING_FILES``
        (env reads ARE the implementation) and the linter itself. Tests are
        already filtered out by the caller in ``_lint_file``.
        """
        if self._is_file_suppressed(content, "SKUEL019"):
            return

        rel_str = str(rel_path).replace("\\", "/")
        if rel_str in self.CREDENTIAL_PLUMBING_FILES or rel_str.endswith("scripts/lint_skuel.py"):
            return

        shape_re = re.compile(self.CREDENTIAL_SHAPE_RE)
        # Match the three call forms in one pass. Group 1 captures the key for
        # os.getenv / os.environ.get; group 2 captures the key for os.environ[K].
        call_re = re.compile(
            r"""os\.(?:getenv|environ\.get)\s*\(\s*['"]([A-Z_][A-Z_0-9]*)['"]"""
            r"""|os\.environ\s*\[\s*['"]([A-Z_][A-Z_0-9]*)['"]\s*\]"""
        )

        in_docstring = False
        docstring_delim: str | None = None

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Track docstring boundaries (skip doc examples)
            for delim in ('"""', "'''"):
                count = stripped.count(delim)
                if count >= 2:
                    pass
                elif count == 1:
                    if not in_docstring:
                        in_docstring = True
                        docstring_delim = delim
                    elif docstring_delim == delim:
                        in_docstring = False
                        docstring_delim = None

            if in_docstring:
                continue
            if stripped.startswith("#"):
                continue
            if self._is_line_suppressed(line, "SKUEL019"):
                continue

            for match in call_re.finditer(line):
                key = match.group(1) or match.group(2)
                if not key:
                    continue

                in_catalog = key in self.CREDENTIAL_CATALOG
                shape_match = bool(shape_re.search(key))

                if not in_catalog and not shape_match:
                    continue

                severity = Severity.ERROR if in_catalog else Severity.WARNING
                if in_catalog:
                    message = (
                        f"Credential `{key}` read via env — must go through "
                        f"`get_credential()` so SKUEL_CREDENTIAL_BACKEND is honored"
                    )
                else:
                    message = (
                        f"`{key}` looks credential-shaped — read it via "
                        f"`get_credential()` and add it to the catalog if needed"
                    )

                self.result.violations.append(
                    Violation(
                        file_path=rel_path,
                        line_number=line_num,
                        column=match.start(),
                        severity=severity,
                        rule_id="SKUEL019",
                        message=message,
                        suggestion=(
                            f"from core.config.credential_store import get_credential\n"
                            f'    value = get_credential("{key}", fallback_to_env=True)'
                        ),
                        line_content=line.strip(),
                    )
                )

    # SKUEL020: decorator attributes that register a route on `app`/`rt`.
    # `ws`/`websocket` are deliberately absent: FastHTML websocket handlers receive
    # a `ws` connection, not a `request`, so the "Missing required field: request"
    # 400 this rule guards cannot bite them.
    ROUTE_DECORATOR_ATTRS: ClassVar[frozenset[str]] = frozenset(
        {"route", "get", "post", "put", "delete", "patch"}
    )
    ROUTE_DECORATOR_BASES: ClassVar[frozenset[str]] = frozenset({"app", "rt"})

    # SKUEL020: the only annotations that resolve to a real Starlette ``Request``.
    # The codebase canonically uses the bare ``Request`` Name (re-exported from
    # ``adapters.inbound.fasthtml_types``); the qualified spellings below are the
    # only other forms that name the same class. An arbitrary ``*.Request`` (e.g.
    # the `requests` HTTP library's ``requests.Request``, or a local class shadowing
    # the name) is NOT a FastHTML request and would 400 — so it must be flagged, not
    # exempted (this mirrors the SKUEL022 base-pinning fix: don't accept a loose tail
    # match). An unusual-but-valid alias produces a safe, suppressible false-positive.
    VALID_REQUEST_QUALNAMES: ClassVar[frozenset[str]] = frozenset(
        {
            "Request",  # canonical bare Name (re-exported via fasthtml_types)
            "starlette.requests.Request",  # fully-qualified Starlette
            "fasthtml_types.Request",  # module-qualified local alias
            "adapters.inbound.fasthtml_types.Request",  # fully-qualified local alias
        }
    )

    @staticmethod
    def _dotted_name(node: ast.expr) -> str | None:
        """Return the dotted path of a Name/Attribute chain (``a.b.C``), else None.

        ``Name('Request')`` -> ``"Request"``; ``Attribute(Attribute(Name('a'),'b'),'C')``
        -> ``"a.b.C"``. Returns None for any other expression (subscript, call, ...).
        """
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = SkuelLinter._dotted_name(node.value)
            return f"{base}.{node.attr}" if base is not None else None
        return None

    @staticmethod
    def _is_route_decorator(dec: ast.expr) -> bool:
        """True if ``dec`` registers a FastHTML route.

        Matches ``@rt`` / ``@rt(...)`` (Name ``rt``) and
        ``@app.get`` / ``@rt.post`` / ``@app.route(...)`` etc. (Attribute whose
        method is a routing verb and whose base is ``app`` or ``rt``).
        """
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Name):
            return target.id == "rt"
        if isinstance(target, ast.Attribute):
            if target.attr in SkuelLinter.ROUTE_DECORATOR_ATTRS:
                base = target.value
                return isinstance(base, ast.Name) and base.id in SkuelLinter.ROUTE_DECORATOR_BASES
        return False

    @staticmethod
    def _find_request_arg(func: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.arg | None:
        """Return the parameter named ``request``, or None if absent."""
        a = func.args
        for arg in (*a.posonlyargs, *a.args, *a.kwonlyargs):
            if arg.arg == "request":
                return arg
        return None

    @staticmethod
    def _annotation_is_request(annotation: ast.expr | None) -> bool:
        """True if the annotation is acceptable for a FastHTML ``request`` param.

        Accepts the unannotated case (FastHTML injects the request when there is no
        hint) and any spelling in :data:`VALID_REQUEST_QUALNAMES` — the bare
        ``Request`` Name, the fully-qualified ``starlette.requests.Request``
        Attribute, the ``fasthtml_types`` alias forms, and their string-forward-ref
        equivalents. A loose ``*.Request`` tail match is deliberately rejected: an
        annotation like ``request: foo.Request`` is not a real Starlette Request and
        would 400 at runtime — the exact failure SKUEL020 guards — so it is flagged.
        """
        if annotation is None:
            return True
        if isinstance(annotation, ast.Name | ast.Attribute):
            return SkuelLinter._dotted_name(annotation) in SkuelLinter.VALID_REQUEST_QUALNAMES
        if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
            # String forward-ref, e.g. "Request" or "starlette.requests.Request".
            return annotation.value.strip() in SkuelLinter.VALID_REQUEST_QUALNAMES
        return False

    def _check_request_annotation(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL020 [ERROR]: FastHTML route handlers must annotate ``request: Request``.

        A parameter named ``request`` annotated as anything other than ``Request``
        (e.g. ``request: Any``) makes FastHTML treat ``request`` as a required input
        field and return 400 "Missing required field: request" for every caller —
        before any ``@require_*`` / ``@csrf_protected`` / ``@boundary_handler``
        decorator runs (all use ``@wraps``, preserving the broken inner annotation).
        The route fails closed but is dead. Only a live request surfaces it; mypy,
        ruff, and the Route Security Audit do not.

        AST-based: flags any function decorated with a route decorator (including
        nested ``handler`` defs in factory functions) whose ``request`` parameter
        has a non-``Request`` annotation. Unannotated ``request`` is fine.
        """
        if self._is_file_suppressed(content, "SKUEL020"):
            return

        # Cheap pre-filter: only parse files that actually register routes. Every
        # decorator we match renders as `@rt...` or `@app....` in source.
        if "@rt" not in content and "@app." not in content:
            return

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not any(self._is_route_decorator(d) for d in node.decorator_list):
                continue

            request_arg = self._find_request_arg(node)
            if request_arg is None:
                continue
            annotation = request_arg.annotation
            if annotation is None or self._annotation_is_request(annotation):
                continue

            line_num = request_arg.lineno
            line = lines[line_num - 1] if 0 < line_num <= len(lines) else ""
            if self._is_line_suppressed(line, "SKUEL020"):
                continue

            annotation_src = ast.unparse(annotation)
            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=request_arg.col_offset,
                    severity=Severity.ERROR,
                    rule_id="SKUEL020",
                    message=(
                        f"Route handler `{node.name}` annotates `request: {annotation_src}` — "
                        f"FastHTML 400s 'Missing required field: request' before any gate runs"
                    ),
                    suggestion=(
                        "Change to `request: Request` and add a runtime import "
                        "`from adapters.inbound.fasthtml_types import Request`"
                    ),
                    line_content=line.strip(),
                )
            )

    # -------------------------------------------------------------------------
    # Authoring AST rules — the "iterate the field, never walk the node" rule.
    #
    # When a rule collects the lines/nodes *inside* a compound statement (``If``,
    # ``Try``, ``For``, ``While``, ``With``, ``FunctionDef``), iterate the specific
    # field (``node.body``) — never ``ast.walk(node)`` on the whole node. ``ast.walk``
    # also descends into the *sibling* fields (``orelse``, ``handlers``, ``finalbody``,
    # a loop's ``else``), which execute at runtime. Walking the whole ``if
    # TYPE_CHECKING:`` node, for example, would sweep its ``else:`` branch into the
    # "type-only, exempt" set and silently bypass SKUEL022 — the exact bug PR #64
    # fixed. Descending *within* ``node.body`` (recursing into nested structures) is
    # correct and expected; it's the jump to a sibling field that leaks.
    # -------------------------------------------------------------------------

    @staticmethod
    def _is_type_checking_test(test: ast.expr) -> bool:
        """True if ``test`` is the ``TYPE_CHECKING`` guard of an ``if`` block.

        Matches ``TYPE_CHECKING`` (Name) and ``typing.TYPE_CHECKING`` (Attribute).
        """
        if isinstance(test, ast.Name):
            return test.id == "TYPE_CHECKING"
        if isinstance(test, ast.Attribute):
            # Only `typing.TYPE_CHECKING`, not an arbitrary `obj.TYPE_CHECKING`
            # (e.g. `settings.TYPE_CHECKING` could be a real runtime flag — exempting
            # imports under it would be a false-negative bypass of SKUEL022).
            return (
                test.attr == "TYPE_CHECKING"
                and isinstance(test.value, ast.Name)
                and test.value.id == "typing"
            )
        return False

    def _check_core_imports_adapter(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL022 [ERROR]: a ``core/`` module must not import from ``adapters/``.

        The hexagonal dependency direction is core → adapter (ADR-044). A runtime
        import of an adapter inside ``core/`` inverts it. Flagged at module scope AND
        inside functions (a function-local import is the same runtime dependency,
        deferred past module load — the dodge a module-level-only check would miss).

        ``TYPE_CHECKING``-only imports are exempt: they never execute, so they cannot
        create a runtime dependency. Typing an annotation against a concrete adapter
        class under ``if TYPE_CHECKING:`` is a separate purity concern, not a layering
        violation.

        Fix: depend on a ``core/ports`` protocol and inject the concrete adapter at the
        composition root (``services_bootstrap/`` or a factory below the boundary).

        Suppress: # skuel-lint: disable=SKUEL022 -- <reason>
        File-level: # skuel-lint: disable-file=SKUEL022 -- <reason>
        """
        if self._is_file_suppressed(content, "SKUEL022"):
            return
        # Cheap pre-filter: only parse files that mention adapters at all.
        if "adapters" not in content:
            return

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return

        # Collect line numbers inside the BODY of `if TYPE_CHECKING:` blocks — exempt.
        # Only the `if` body, never the `else`/`elif` branch: an import under
        # `else:` (or `elif`) DOES execute at runtime, so it must still be flagged.
        type_checking_lines: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and self._is_type_checking_test(node.test):
                for stmt in node.body:
                    for child in ast.walk(stmt):
                        if hasattr(child, "lineno"):
                            type_checking_lines.add(child.lineno)

        for node in ast.walk(tree):
            imported_modules: list[str] = []
            if isinstance(node, ast.ImportFrom):
                # Ignore relative imports (node.module is None for `from . import x`).
                if node.module:
                    imported_modules.append(node.module)
            elif isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            else:
                continue

            if not any(m == "adapters" or m.startswith("adapters.") for m in imported_modules):
                continue
            if node.lineno in type_checking_lines:
                continue  # TYPE_CHECKING-only — cannot create a runtime dependency

            line = lines[node.lineno - 1] if 0 < node.lineno <= len(lines) else ""
            if self._is_line_suppressed(line, "SKUEL022"):
                continue

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=node.lineno,
                    column=node.col_offset,
                    severity=Severity.ERROR,
                    rule_id="SKUEL022",
                    message=(
                        f"core/ module imports adapter '{imported_modules[0]}' at runtime "
                        f"— wrong dependency direction (core → adapter only, ADR-044)"
                    ),
                    suggestion=(
                        "Depend on a core/ports protocol and inject the concrete adapter "
                        "at the composition root; or move a type-only import under "
                        "`if TYPE_CHECKING:`"
                    ),
                    line_content=line.strip(),
                )
            )

    # =========================================================================
    # INFO RULES (visibility only)
    # =========================================================================

    def _check_todo_comments(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL006 [INFO]: Track TODO/FIXME comments for technical debt visibility.

        This rule is informational only - it doesn't block CI but makes
        technical debt visible during code review.
        """
        pattern = r"#.*\b(TODO|FIXME)(?:\(([^)]+)\))?"

        for line_num, line in enumerate(lines, start=1):
            match = re.search(pattern, line)
            if match:
                # Verify the '#' is an actual comment, not inside a string literal
                hash_pos = match.start()
                before_hash = line[:hash_pos]
                quote_count = before_hash.count('"') + before_hash.count("'")
                if quote_count % 2 == 1:
                    continue  # Odd number of quotes = inside a string

                marker = match.group(1)
                category = match.group(2)
                if category:
                    message = f"{marker}({category}) - categorized debt marker"
                    suggestion = f"Category: {category}"
                else:
                    message = f"{marker} comment - uncategorized debt marker"
                    suggestion = (
                        "Add category: TODO(blocked:<reason>), "
                        "TODO(deferred), or TODO(implementable)"
                    )
                self.result.violations.append(
                    Violation(
                        file_path=rel_path,
                        line_number=line_num,
                        column=match.start(),
                        severity=Severity.INFO,
                        rule_id="SKUEL006",
                        message=message,
                        suggestion=suggestion,
                        line_content=line.strip(),
                    )
                )

    # =========================================================================
    # AUTO-FIXABLE RULES
    # =========================================================================

    def _check_tuple_defaults(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL009 [WARNING]: Single-element tuple defaults are usually bugs.
        """
        pattern = r":\s*\w+\s*=\s*\(([^)]+),\s*\)"

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()

            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if "→" in line:
                continue
            if "tuple[" in line.lower() or "Tuple[" in line:
                continue
            if "field(" in line and "default_factory" in line:
                continue

            match = re.search(pattern, line)
            if match:
                value = match.group(1).strip()
                original = f"({value},)"
                fixed = value

                self.result.violations.append(
                    Violation(
                        file_path=rel_path,
                        line_number=line_num,
                        column=line.find(original),
                        severity=Severity.WARNING,
                        rule_id="SKUEL009",
                        message="Single-element tuple default - likely a bug",
                        suggestion=f"Change = ({value},) to = {value}",
                        fix_available=True,
                        original_text=f"= {original}",
                        fixed_text=f"= {fixed}",
                        line_content=line.strip(),
                    )
                )

    def _check_nested_tuple_defaults(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL010 [WARNING]: Nested empty tuples can't be stored in Neo4j.
        """
        pattern = r"=\s*\(\(\s*\)\s*,\s*\)"

        for match in re.finditer(pattern, content):
            line_num = content[: match.start()].count("\n") + 1
            line = lines[line_num - 1].strip()

            if line.startswith("#") or line.startswith('"""') or line.startswith("'''"):
                continue
            if "→" in line:
                continue

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=0,
                    severity=Severity.WARNING,
                    rule_id="SKUEL010",
                    message="Nested empty tuple - Neo4j can't store nested collections",
                    suggestion="Change ((),) to ()",
                    fix_available=True,
                    original_text="((),)",
                    fixed_text="()",
                    line_content=line,
                )
            )

    # =========================================================================
    # AUTO-FIX
    # =========================================================================

    def apply_fixes(self) -> int:
        """Apply auto-fixes to violations that support it."""
        fixable = [v for v in self.result.violations if v.fix_available]

        if not fixable:
            print("No auto-fixable violations found.")
            return 0

        by_file: dict[Path, list[Violation]] = {}
        for v in fixable:
            full_path = self.root_dir / v.file_path
            if full_path not in by_file:
                by_file[full_path] = []
            by_file[full_path].append(v)

        fixed_count = 0
        for file_path, violations in by_file.items():
            content = file_path.read_text(encoding="utf-8")
            original = content

            for v in sorted(violations, key=lambda x: x.line_number, reverse=True):
                if v.original_text and v.fixed_text:
                    content = content.replace(v.original_text, v.fixed_text, 1)
                    fixed_count += 1

            if content != original:
                file_path.write_text(content, encoding="utf-8")
                rel_path = file_path.relative_to(self.root_dir)
                print(
                    f"{Colors.GREEN}✓{Colors.RESET} Fixed {len(violations)} violation(s) in {rel_path}"
                )

        print(
            f"\n{Colors.GREEN}✓{Colors.RESET} Applied {fixed_count} auto-fixes across {len(by_file)} files"
        )
        return fixed_count

    # =========================================================================
    # REPORTING
    # =========================================================================

    def print_report(
        self, strict: bool = False, quiet: bool = False, show_context: bool = False
    ) -> int:
        """
        Print violations report.

        Returns exit code:
            0 - No blocking violations
            1 - Warnings found (only in strict mode)
            2 - Errors or critical violations found
        """
        if not self.result.violations:
            if not quiet:
                print(
                    f"{Colors.GREEN}✅ No SKUEL violations found!{Colors.RESET} "
                    f"({self.result.files_scanned} files scanned in {self.result.scan_time_ms:.0f}ms)"
                )
            return 0

        if quiet:
            # Minimal output for CI
            critical = len(self.result.by_severity(Severity.CRITICAL))
            errors = len(self.result.by_severity(Severity.ERROR))
            warnings = len(self.result.by_severity(Severity.WARNING))
            print(f"SKUEL: {critical} critical, {errors} errors, {warnings} warnings")
            if critical or errors:
                return 2
            if strict and warnings:
                return 1
            return 0

        print(f"\n{Colors.BOLD}{'=' * 80}{Colors.RESET}")
        print(f"{Colors.BOLD}SKUEL LINTER{Colors.RESET}")
        print(f"{'=' * 80}")
        print(f"Scanned {self.result.files_scanned} files in {self.result.scan_time_ms:.0f}ms")
        print()

        # Group and print by severity
        for severity in [Severity.CRITICAL, Severity.ERROR, Severity.WARNING, Severity.INFO]:
            violations = self.result.by_severity(severity)
            if not violations:
                continue

            icon, color = {
                Severity.CRITICAL: ("🔴", Colors.RED),
                Severity.ERROR: ("❌", Colors.RED),
                Severity.WARNING: ("⚠️ ", Colors.YELLOW),
                Severity.INFO: ("ℹ️ ", Colors.BLUE),
            }[severity]

            print(
                f"{icon} {color}{Colors.BOLD}{severity.value}: {len(violations)} violation(s){Colors.RESET}"
            )
            print(f"{Colors.DIM}{'-' * 80}{Colors.RESET}")

            # Group by file for better readability
            by_file: dict[Path, list[Violation]] = {}
            for v in violations:
                if v.file_path not in by_file:
                    by_file[v.file_path] = []
                by_file[v.file_path].append(v)

            for file_path, file_violations in sorted(by_file.items()):
                print(f"\n  {Colors.CYAN}{file_path}{Colors.RESET}")
                for v in sorted(file_violations, key=lambda x: x.line_number):
                    fix_tag = f" {Colors.GREEN}[auto-fix]{Colors.RESET}" if v.fix_available else ""
                    print(
                        f"    {Colors.DIM}L{v.line_number}:{v.column}{Colors.RESET} [{v.rule_id}] {v.message}{fix_tag}"
                    )
                    print(f"    {Colors.DIM}💡{Colors.RESET} {v.suggestion}")

                    if show_context and v.line_content:
                        print(f"    {Colors.DIM}│{Colors.RESET} {v.line_content}")

            print()

        # Summary
        print(f"{'=' * 80}")
        print(f"{Colors.BOLD}SUMMARY{Colors.RESET}")
        print(f"{'-' * 80}")

        critical_count = len(self.result.by_severity(Severity.CRITICAL))
        error_count = len(self.result.by_severity(Severity.ERROR))
        warning_count = len(self.result.by_severity(Severity.WARNING))
        info_count = len(self.result.by_severity(Severity.INFO))

        if critical_count:
            print(f"  {Colors.RED}Critical: {critical_count}{Colors.RESET}")
        else:
            print(f"  Critical: {critical_count}")

        if error_count:
            print(f"  {Colors.RED}Errors:   {error_count}{Colors.RESET}")
        else:
            print(f"  Errors:   {error_count}")

        if warning_count:
            print(f"  {Colors.YELLOW}Warnings: {warning_count}{Colors.RESET}")
        else:
            print(f"  Warnings: {warning_count}")

        print(f"  Info:     {info_count}")

        # Per-rule breakdown
        rule_counts: dict[str, int] = {}
        rule_severity: dict[str, Severity] = {}
        for v in self.result.violations:
            rule_counts[v.rule_id] = rule_counts.get(v.rule_id, 0) + 1
            if v.rule_id not in rule_severity:
                rule_severity[v.rule_id] = v.severity

        if rule_counts:
            print(f"\n  {Colors.BOLD}By rule:{Colors.RESET}")
            for rule_id in sorted(rule_counts.keys()):
                count = rule_counts[rule_id]
                severity = rule_severity[rule_id]
                color = {
                    Severity.CRITICAL: Colors.RED,
                    Severity.ERROR: Colors.RED,
                    Severity.WARNING: Colors.YELLOW,
                    Severity.INFO: Colors.BLUE,
                }.get(severity, "")
                title = RULE_DOCS.get(rule_id, {}).get("title", "")
                print(
                    f"    {color}{rule_id}{Colors.RESET}: {count}  "
                    f"{Colors.DIM}{title}{Colors.RESET}"
                )

        print(f"\n  {Colors.BOLD}Total:    {len(self.result.violations)}{Colors.RESET}")

        fixable = len([v for v in self.result.violations if v.fix_available])
        if fixable:
            print(
                f"\n{Colors.GREEN}💡 {fixable} violation(s) can be auto-fixed with --fix{Colors.RESET}"
            )

        print(f"{'=' * 80}")

        # Determine exit code
        if self.result.has_critical or self.result.has_error:
            print(
                f"\n{Colors.RED}❌ Critical/Error violations found - must fix before merging{Colors.RESET}"
            )
            return 2

        if strict and self.result.has_warning:
            print(f"\n{Colors.YELLOW}⚠️ Warnings treated as errors (--strict mode){Colors.RESET}")
            return 1

        if self.result.has_warning:
            print(f"\n{Colors.YELLOW}⚠️ Warnings found - review before merging{Colors.RESET}")

        return 0


def explain_rule(rule_id: str) -> None:
    """Print detailed explanation of a rule."""
    rule_id = rule_id.upper()
    if rule_id not in RULE_DOCS:
        print(f"{Colors.RED}Unknown rule: {rule_id}{Colors.RESET}")
        print(f"\nAvailable rules: {', '.join(sorted(RULE_DOCS.keys()))}")
        sys.exit(1)

    doc = RULE_DOCS[rule_id]

    print(f"\n{Colors.BOLD}{Colors.CYAN}{rule_id}: {doc['title']}{Colors.RESET}")
    print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}")
    print(f"Severity: {doc['severity']}")

    if "autofix" in doc:
        print(f"{Colors.GREEN}Auto-fixable: {doc['autofix']}{Colors.RESET}")

    print(f"\n{doc['description']}")

    if "good" in doc:
        print(f"\n{Colors.GREEN}✅ Good:{Colors.RESET}")
        print(f"{Colors.DIM}{doc['good']}{Colors.RESET}")

    if "bad" in doc:
        print(f"\n{Colors.RED}❌ Bad:{Colors.RESET}")
        print(f"{Colors.DIM}{doc['bad']}{Colors.RESET}")

    print()


def list_rules() -> None:
    """List all available rules."""
    print(f"\n{Colors.BOLD}Available SKUEL Rules:{Colors.RESET}")
    print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}\n")

    for rule_id in sorted(RULE_DOCS.keys()):
        doc = RULE_DOCS[rule_id]
        severity_color = {
            "CRITICAL": Colors.RED,
            "ERROR": Colors.RED,
            "WARNING": Colors.YELLOW,
            "INFO": Colors.BLUE,
        }.get(doc["severity"], "")
        autofix = " [auto-fix]" if "autofix" in doc else ""
        print(f"  {Colors.CYAN}{rule_id}{Colors.RESET}: {doc['title']}")
        print(
            f"         {severity_color}{doc['severity']}{Colors.RESET}{Colors.GREEN}{autofix}{Colors.RESET}"
        )
        print()


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="SKUEL Unified Linter - architecture and pattern enforcement",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Lint entire project (with code context)
  %(prog)s --changed                # Lint only files changed vs main
  %(prog)s --staged                 # Lint only staged files (pre-commit)
  %(prog)s --file core/services/    # Lint specific directory
  %(prog)s --rule SKUEL003          # Run only specific rule
  %(prog)s --explain SKUEL003       # Show rule documentation
  %(prog)s --fix                    # Auto-fix violations
  %(prog)s --no-context             # Hide code context
  %(prog)s --quiet --check          # CI mode
        """,
    )
    parser.add_argument(
        "--check", action="store_true", help="Exit with code 1 if any violations (for CI)"
    )
    parser.add_argument("--fix", action="store_true", help="Auto-fix violations where possible")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    parser.add_argument("--json", action="store_true", help="Output violations as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output (for CI)")
    parser.add_argument(
        "--context",
        "-c",
        action="store_true",
        help="Show code context (now default; kept for backward compat)",
    )
    parser.add_argument(
        "--no-context", action="store_true", help="Hide code context around violations"
    )
    parser.add_argument(
        "--changed",
        action="store_true",
        help="Lint only files changed vs main branch",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Lint only staged files (ideal for pre-commit)",
    )
    parser.add_argument(
        "--file", "-f", type=str, help="Lint specific file or directory (relative to project root)"
    )
    parser.add_argument(
        "--rule",
        "-r",
        type=str,
        action="append",
        help="Run only specific rule(s). Can be used multiple times.",
    )
    parser.add_argument(
        "--explain", "-e", type=str, help="Explain a specific rule (e.g., --explain SKUEL003)"
    )
    parser.add_argument("--list-rules", action="store_true", help="List all available rules")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    args = parser.parse_args()

    # Disable colors if requested or not a TTY
    if args.no_color or not sys.stdout.isatty():
        Colors.disable()

    # Validate mutually exclusive file selection flags
    file_flags = sum([bool(args.changed), bool(args.staged), bool(args.file)])
    if file_flags > 1:
        parser.error("--changed, --staged, and --file are mutually exclusive")

    # Handle --explain
    if args.explain:
        explain_rule(args.explain)
        sys.exit(0)

    # Handle --list-rules
    if args.list_rules:
        list_rules()
        sys.exit(0)

    # Find project root
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent

    # Resolve git-aware file selection
    changed_files = None
    if args.changed:
        changed_files = SkuelLinter._git_changed_files(project_root, staged_only=False)
        if changed_files is None:
            print(
                f"{Colors.YELLOW}Warning: --changed failed (git unavailable?), "
                f"falling back to full scan{Colors.RESET}",
                file=sys.stderr,
            )
        elif not changed_files:
            print(f"{Colors.GREEN}No changed Python files vs main.{Colors.RESET}")
            sys.exit(0)
    elif args.staged:
        changed_files = SkuelLinter._git_changed_files(project_root, staged_only=True)
        if changed_files is None:
            print(
                f"{Colors.YELLOW}Warning: --staged failed (git unavailable?), "
                f"falling back to full scan{Colors.RESET}",
                file=sys.stderr,
            )
        elif not changed_files:
            print(f"{Colors.GREEN}No staged Python files.{Colors.RESET}")
            sys.exit(0)

    # Run linter
    rules_filter = [r.upper() for r in args.rule] if args.rule else None
    linter = SkuelLinter(
        project_root,
        target_path=args.file,
        rules_filter=rules_filter,
        changed_files=changed_files,
    )
    linter.lint()

    # Apply fixes if requested
    if args.fix:
        if not args.quiet:
            print()
            print(f"{'=' * 80}")
            print("APPLYING AUTO-FIXES")
            print(f"{'=' * 80}")
            print()
        linter.apply_fixes()

        if not args.quiet:
            print()

        # Re-run to show remaining violations
        linter = SkuelLinter(
            project_root,
            target_path=args.file,
            rules_filter=rules_filter,
            changed_files=changed_files,
        )
        linter.lint()

    # Output
    if args.json:
        import json

        output = {
            "files_scanned": linter.result.files_scanned,
            "scan_time_ms": linter.result.scan_time_ms,
            "violations": [
                {
                    "file": str(v.file_path),
                    "line": v.line_number,
                    "column": v.column,
                    "severity": v.severity.value,
                    "rule_id": v.rule_id,
                    "message": v.message,
                    "suggestion": v.suggestion,
                    "fix_available": v.fix_available,
                    "line_content": v.line_content,
                }
                for v in linter.result.violations
            ],
            "summary": {
                "critical": len(linter.result.by_severity(Severity.CRITICAL)),
                "error": len(linter.result.by_severity(Severity.ERROR)),
                "warning": len(linter.result.by_severity(Severity.WARNING)),
                "info": len(linter.result.by_severity(Severity.INFO)),
            },
        }
        print(json.dumps(output, indent=2))
        exit_code = 1 if linter.result.violations else 0
    else:
        show_context = not args.no_context
        exit_code = linter.print_report(
            strict=args.strict, quiet=args.quiet, show_context=show_context
        )

    # Exit
    if args.check:
        sys.exit(1 if linter.result.violations else 0)
    else:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
