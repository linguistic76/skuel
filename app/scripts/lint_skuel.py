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
  SKUEL023: core/ thin services must type self.backend against a core/ports protocol
  SKUEL024: No cls= / **kwargs collision in FT helpers (latent TypeError crash)
  SKUEL025: No deleted Activity *UpdatePayload — use the frozen *UpdateIntent (ADR-066)
  SKUEL027: ui/ must not import adapters/ at runtime (ui renders; routes compose)

WARNING (blocks `./dev lint` / `./dev quality` via --strict; plain runs report only):
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
  SKUEL026: Suppression comment that suppresses nothing (rot / typo / unsupported rule)

INFO (informational, visibility only):
  SKUEL006: TODO/FIXME comments - track technical debt

AUTO-FIXABLE:
  SKUEL003: .is_err → .is_error
  SKUEL009: Single-element tuple defaults (int = (0,) → int = 0)
  SKUEL010: Nested empty tuple defaults (((),) → ())

Usage:
    uv run python scripts/lint_skuel.py              # Report violations (with code context)
    uv run python scripts/lint_skuel.py --fix        # Auto-fix where possible
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
import io
import re
import subprocess
import sys
import time
import tokenize
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import ClassVar

from core.utils.terminal_colors import Colors


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

For simple attribute or item extraction use operator.attrgetter / operator.itemgetter —
they are named, stdlib callables that satisfy this rule.
Define a named helper only for domain logic, None-fallback, or composite sort keys.
Do NOT add one-liner wrappers to sort_functions.py for plain field access.

Exceptions: tests/, examples/, scripts/.
Suppress: # skuel-lint: disable=SKUEL012 -- <reason>
File-level: # skuel-lint: disable-file=SKUEL012 -- <reason>""",
        "good": """from operator import attrgetter, itemgetter

tasks.sort(key=attrgetter('due_date'))
results.sort(key=itemgetter(1), reverse=True)

# Only define a named helper when there is real logic:
def get_priority_value(item):
    \"\"\"Convert priority enum/string to numeric, with Neo4j string fallback.\"\"\"
    ...

tasks.sort(key=get_priority_value)""",
        "bad": """tasks.sort(key=lambda t: t.priority.to_numeric())
get_priority = lambda item: item.priority.to_numeric()

# Also bad — one-liner wrappers in sort_functions.py are not the solution:
# def get_due_date(task): return task.due_date  (use attrgetter instead)""",
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
    "SKUEL023": {
        "title": "Type Against ports, Not Adapter Classes",
        "severity": "ERROR",
        "description": """The hexagonal dependency direction is core → adapter (ADR-044).
SKUEL022 enforces this at the *runtime import* layer (a runtime `import adapters` from
inside core/ is banned). That rule deliberately exempts `if TYPE_CHECKING:` blocks
because they never execute — they cannot create a runtime dependency.

SKUEL023 closes the remaining *static-type direction* gap. Even when an adapter import
is TYPE_CHECKING-only, typing ``self.backend: KuBackend`` against the concrete adapter
class is design-coupling: it locks the service to a specific adapter instead of the
``core/ports`` protocol it should depend on. The protocol is the contract; the adapter
is one implementation of it.

Facade vs thin: facades (KuService, PsService sub-services, LpService sub-services,
UserService, UserContextBuilder) are explicitly allowlisted — CLAUDE.md commits to
"Facade IS the contract": facades aggregate sub-services + a direct backend handle for
cross-cutting operations the protocol doesn't enumerate. Thin services in core/ that
take a single backend handle must annotate against the ports protocol.

AST-based, fail-closed: walks both runtime AND TYPE_CHECKING imports of `adapters.*`,
then flags annotations (instance attribute, function parameter, class-body attribute)
that reference one of those imports. Forward references (string annotations) are
parsed. Subscripts (Optional[X], list[X]) recurse. ``Attribute`` chains walk to the
root Name so module-style aliases (`import adapters.x as xb` + `backend: xb.XBackend`)
are caught. Fully-qualified forward-ref strings (`backend: "adapters.x.XBackend"`,
no import) are caught via the same path — the parsed Attribute chain's root Name is
`adapters`, which the check treats as an implicit adapter reference.

**Import-site rule (primary):** adapter imports in ``core/`` must be the plain
``from adapters.<...> import <Name>`` form — no aliasing (``as Y``) and no
module-style imports (``import adapters[...]`` with or without alias). Aliasing
adapter imports in ``core/`` has no demonstrated positive purpose (zero uses in
the codebase as of the rule's introduction) and creates bypass classes for the
annotation-level checks. The annotation-level checks remain as defense in depth
for any path the import gate might miss (e.g. fully-qualified forward-ref strings).

Suffix heuristic: only flags names ending in Backend / Executor / Adapter / Repository /
Client / Driver — naturally excludes adapter enums, configs, and pure-data exports
that legitimately cross the boundary as types.

Fix: switch the TYPE_CHECKING import from the concrete adapter to its
``core/ports/*Operations`` protocol; switch the annotation to the protocol name. The
runtime injection at the composition root is unchanged — the adapter still satisfies
the protocol structurally.

Suppress: # skuel-lint: disable=SKUEL023 -- <reason>
File-level: # skuel-lint: disable-file=SKUEL023 -- <reason>""",
        "good": """# Thin service types against the ports protocol
if TYPE_CHECKING:
    from core.ports.sharing_protocols import SharingOperations

class UnifiedSharingService:
    def __init__(self, backend: "SharingOperations") -> None:
        self.backend = backend""",
        "bad": """# Thin service types against the concrete adapter — design coupling
if TYPE_CHECKING:
    from adapters.persistence.neo4j.backends.sharing_backend import SharingBackend

class UnifiedSharingService:
    def __init__(self, backend: "SharingBackend") -> None:
        self.backend = backend""",
    },
    "SKUEL024": {
        "title": "No cls= / **kwargs Collision in FT Helpers",
        "severity": "ERROR",
        "description": """A helper that hardcodes a ``cls=`` keyword AND splats ``**kwargs``
into the SAME call, without declaring an explicit ``cls`` parameter to absorb a
caller-supplied one, is a latent crash. The moment any caller passes ``cls=``, that value
lands in ``**kwargs`` and collides with the hardcoded keyword:
``TypeError: <fn>() got multiple values for keyword argument 'cls'``.

This bit production: ``SmallText("Recommended Actions:", cls="font-semibold mb-1")`` 500'd
the /insights page (PR #154), and an AST sweep found five more sites (#156/#157). It is
invisible to mypy and ruff — only a caller that actually passes ``cls=`` triggers it, so a
helper can ship the landmine and sit dormant until the first styling override.

AST-based, scope-resolution: for each call passing both a ``cls=`` keyword and a ``**Name``
splat, resolve ``Name`` to the nearest enclosing function scope that binds it, and flag iff
``Name`` is that scope's ``**kwargs`` parameter and the scope has no keyword-passable ``cls``
param (a positional-only ``cls`` does not count). Resolution is STRUCTURAL (compile-time
scope binding), so closures (a nested ``def``/``lambda`` splatting the outer ``**kwargs``)
and rebinds (an inner factory with its own ``cls`` or a local ``kwargs = {}``) are handled
soundly. There is no ``kwargs.pop("cls")`` / reassignment exemption — proving a pop or a
conditional/post-splat reassign sanitizes every path needs control-flow domination, and the
explicit ``cls: str = ""`` parameter is the contract anyway, so such helpers are flagged.

Documented boundary — the rule resolves a NAME's scope but does not track a local
variable's VALUE, so value-flow / alias / taint cases are not chased: ``attrs = kwargs;
Div(.., **attrs)`` and copies/merges (``dict(kwargs)``, ``{**kwargs}``, ``kwargs | extra``).
Sound detection there needs control-flow analysis (the same reason there is no pop/reassign
exemption), these forms do not occur in real helpers, and the explicit parameter removes the
whole class regardless. Adopt the explicit parameter, or suppress with a reason.

Fix: add ``cls: str = ""`` and merge it into the base classes
(``cls=f"...base... {cls}".strip()``). See ui/text.py / ui/patterns/ for the pattern, and
tests/unit/ui/test_cls_merge_contract.py for the contract guard.

Suppress: # skuel-lint: disable=SKUEL024 -- <reason>
File-level: # skuel-lint: disable-file=SKUEL024 -- <reason>""",
        "good": """# Explicit cls param merged into the base classes — no collision
def SmallText(text: str, cls: str = "", **kwargs: Any) -> Span:
    return Span(text, cls=f"text-sm {cls}".strip(), **kwargs)""",
        "bad": """# Hardcoded cls= AND **kwargs, no cls param — caller cls= raises TypeError
def SmallText(text: str, **kwargs: Any) -> Span:
    return Span(text, cls="text-sm", **kwargs)  # SmallText("x", cls="y") -> crash""",
    },
    "SKUEL025": {
        "title": "No Deleted Activity *UpdatePayload (ADR-066)",
        "severity": "ERROR",
        "description": """ADR-066 (Phase 7a) replaced the six Activity Domain ``*UpdatePayload``
TypedDicts with frozen ``*UpdateIntent`` dataclasses and a CRUD base parameterized over the
update type ``U``. The old names — ``TaskUpdatePayload``, ``GoalUpdatePayload``,
``HabitUpdatePayload``, ``EventUpdatePayload``, ``ChoiceUpdatePayload``,
``PrincipleUpdatePayload`` — are deleted. Referencing one rebuilds the abandoned dict
write-path (One Path Forward).

The curriculum (``KuUpdatePayload``/``PsUpdatePayload``/``LpUpdatePayload``), finance, and
report payloads are intentionally NOT forbidden — they remain valid for the non-activity
domains, which flow as ``RawChanges`` through the same base ``U``.

Trivially sound + AST-structural: flags an import alias, a bare ``Name``, or an ``Attribute``
whose identifier is one of the six fixed forbidden names. No flow analysis — a string literal
naming a type is not a ``Name``/``Attribute`` node, so it is never flagged.

Fix: use the domain ``*UpdateIntent`` (``core/models/<domain>/<domain>_update_intent.py``) or
build it from the request via ``*UpdateRequest.to_intent()``.

Suppress: # skuel-lint: disable=SKUEL025 -- <reason>
File-level: # skuel-lint: disable-file=SKUEL025 -- <reason>""",
        "good": """# Activity update uses the frozen intent
from core.models.task import TaskUpdateIntent
await tasks_service.update_task(uid, TaskUpdateIntent(status="in_progress"))""",
        "bad": """# Resurrects the deleted TypedDict write-path
from core.ports.query_types import TaskUpdatePayload  # SKUEL025
updates: TaskUpdatePayload = {"status": "in_progress"}""",
    },
    "SKUEL026": {
        "title": "Unused Suppression Comment",
        "severity": "WARNING",
        "description": """A ``# skuel-lint: disable[-file]=SKUELXXX`` comment that suppresses
nothing. After the normal scan, the linter re-lints every file containing suppression
comments with suppressions ignored; a comment is USED iff the named rule would fire at
that line (line-level) or anywhere in the file (file-level). Anything else is rot:

- the violation it once guarded was refactored away,
- the named rule does not support inline suppression (only rules that call the
  suppression helpers honor the comment — see SUPPRESSIBLE_RULES),
- the rule ID is unknown / a typo, or
- the comment is malformed (the checkers match the exact substring
  ``# skuel-lint: disable=SKUELXXX`` — e.g. a missing space disables nothing).

Suppressions are exemptions from enforced rules; an inert one silently widens what
readers believe is exempted. Delete it (git history keeps the reason).

Detection is structural: real ``#`` comments are discovered via tokenize, so
suppression examples inside string literals / docstrings are never audited.
This rule is itself not suppressible.""",
        "good": """route_count = len(app.routes) if hasattr(app, "routes") else 0  # skuel-lint: disable=SKUEL011 -- FastHTML app attribute check
# (SKUEL011 fires on this line without the comment -> the suppression is USED)""",
        "bad": """value = compute()  # skuel-lint: disable=SKUEL011 -- no hasattr here anymore
# (SKUEL011 would not fire on this line -> the comment is rot; delete it)""",
    },
    "SKUEL027": {
        "title": "ui/ Must Not Import adapters/",
        "severity": "ERROR",
        "description": """ui/ is pure presentation — it renders what routes hand it. The
dependency arrows point inward: adapters/inbound (routes) imports ui/ components, never
the reverse at runtime. A runtime `import adapters` inside ui/ inverts that layering.
SKUEL022 enforces the same direction for core/; before this rule existed, no lint watched
ui/, which is how `ui/calendar/converters.py` grew an adapters import (fixed in #653) and
CSRF render helpers were consumed from `adapters/inbound/csrf.py` (split into
`core/utils/csrf_token_context.py` + `ui/patterns/csrf.py` in #654).

AST-based, same mechanics as SKUEL022: flags `import adapters...` /
`from adapters... import ...` at module scope OR inside a function (a function-local
import is the same runtime dependency, deferred past module load — exactly where the
last violations hid: BasePage/navbar's function-local `adapters.inbound.auth` imports,
cleared by the middleware-set auth context in #655).

TYPE_CHECKING-only imports are EXEMPT: an import under `if TYPE_CHECKING:` never
executes, so it cannot create a runtime ui→adapters dependency. Typing a parameter
against `adapters.inbound.fasthtml_types.Request` under TYPE_CHECKING is fine — the
Request protocol lives at the FastHTML boundary by design (CLAUDE.md § FastHTML
boundary).

Fix: move the shared code inward (`core/utils/` or `ui/`) or pass the value in from the
route. For request-derived state, use a middleware-set ContextVar
(`core/utils/auth_context.py`, `core/utils/csrf_token_context.py`) — values flow inward,
ui/ never reaches out.

Suppress: # skuel-lint: disable=SKUEL027 -- <reason>
File-level: # skuel-lint: disable-file=SKUEL027 -- <reason>""",
        "good": """# Route derives state and hands it to the UI; ui/ reads inward-facing context
if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import Request  # type-only, never executes

from core.utils.auth_context import current_user_role  # middleware-set, flows inward""",
        "bad": """# Runtime adapter import inside a ui/ module — presentation reaching outward
from adapters.inbound.auth import get_session_user

def Navbar(request):
    # ...or hidden inside a function (still a runtime ui→adapters dependency):
    from adapters.inbound.auth import get_session_user
    user = get_session_user(request)""",
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
    # Inclusive 1-based line range where a `# skuel-lint: disable=` comment is
    # honored for this violation. None → exactly line_number (the default for
    # single-line constructs). Rules over multi-line headers (SKUEL005 defs,
    # SKUEL017 excepts) set this to the full header span so a suppression
    # survives ruff-format wrapping the statement (the #590 stranding class);
    # the SKUEL026 audit reads the SAME span, keeping checker and audit in
    # lockstep.
    suppression_span: tuple[int, int] | None = None


@dataclass
class SuppressionComment:
    """A genuine `# skuel-lint: disable[-file]=SKUELXXX` comment found by tokenize.

    `used` is set by the suppression audit: True iff the named rule would fire at
    this line (line-level) / anywhere in this file (file-level) with suppressions
    ignored — i.e. the comment actually suppresses something.
    """

    file_path: Path  # relative to project root, like Violation.file_path
    line_number: int
    rule_id: str
    file_level: bool
    line_content: str = ""
    used: bool = False


@dataclass
class LintResult:
    """Results from linting."""

    violations: list[Violation] = field(default_factory=list)
    suppressions: list[SuppressionComment] = field(default_factory=list)
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

    # Directory names excluded wherever they appear in the path. Matched as whole
    # path SEGMENTS — the old substring match swallowed real modules ("build" in
    # "query_builder.py" silently unlinted every *builder* file, 19 files total).
    EXCLUDED_DIR_NAMES: ClassVar[frozenset[str]] = frozenset(
        {
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
            ".claude",  # Claude Code config/skills (documentation only)
        }
    )

    # Root-relative path prefixes excluded as a unit.
    EXCLUDED_PATH_PREFIXES: ClassVar[tuple[str, ...]] = (
        "scripts/migrations",  # Migration scripts document old patterns
        "scripts/lint_skuel",  # Linter files document patterns they check
    )

    def _is_excluded(self, py_file: Path) -> bool:
        """True if the file lives under an excluded directory / path prefix."""
        rel = py_file.relative_to(self.root_dir)
        if any(part in self.EXCLUDED_DIR_NAMES for part in rel.parts):
            return True
        return rel.as_posix().startswith(self.EXCLUDED_PATH_PREFIXES)

    # Rules that honor `# skuel-lint: disable[-file]=SKUELXXX` — exactly the set
    # whose checkers call _is_line_suppressed/_is_file_suppressed. A suppression
    # comment naming any OTHER rule does nothing and is flagged by SKUEL026.
    # Guarded against drift by test_lint_skuel.py (source-scan of the call sites).
    SUPPRESSIBLE_RULES: ClassVar[frozenset[str]] = frozenset(
        {
            "SKUEL005",
            "SKUEL011",
            "SKUEL012",
            "SKUEL015",
            "SKUEL017",
            "SKUEL018",
            "SKUEL019",
            "SKUEL020",
            "SKUEL021",
            "SKUEL022",
            "SKUEL023",
            "SKUEL024",
            "SKUEL025",
            "SKUEL027",
        }
    )

    # Deliberately looser than the exact substring the checkers match, so typos
    # ("#skuel-lint:disable=...", stray spaces) are DISCOVERED and then reported
    # as unused by SKUEL026 instead of silently doing nothing.
    _SUPPRESSION_COMMENT_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"#\s*skuel-lint:\s*disable(?P<filelevel>-file)?\s*=\s*(?P<rule>SKUEL\d{3})"
    )

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

    # Rules whose checkers consume the shared AST. `_lint_file` parses each file
    # ONCE and hands the tree to these checkers (None on SyntaxError — every AST
    # rule skips unparseable files; ruff flags the syntax error anyway). The list
    # gates the parse itself: a run filtered to purely line-based rules (e.g. the
    # SKUEL026 shadow-lint of a file whose only suppression names SKUEL012) never
    # pays for a parse.
    AST_RULE_IDS: ClassVar[frozenset[str]] = frozenset(
        {
            "SKUEL001",
            "SKUEL002",
            "SKUEL005",
            "SKUEL013",
            "SKUEL014",
            "SKUEL017",
            "SKUEL020",
            "SKUEL021",
            "SKUEL022",
            "SKUEL023",
            "SKUEL024",
            "SKUEL025",
            "SKUEL027",
        }
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

    # SKUEL023: facades are allowed to type self.backend against the concrete adapter
    # class — CLAUDE.md commits to "Facade IS the contract" for these. They aggregate
    # sub-services + a direct backend handle for cross-cutting operations the ports
    # protocol doesn't enumerate (KU/PS/LP/UserService each delegate ~50+ methods).
    # The allowlist is intentionally narrow: directory prefixes for the multi-file
    # sub-service packages, and explicit files for the standalone facade modules.
    #
    # InsightStore is also allowlisted: it originated as a thin delegating service but
    # has grown into a facade with 6+ methods that compose on top of the backend
    # (bulk_dismiss, bulk_mark_actioned, smart_dismiss, filter_insights, chart builders).
    # InsightStore IS the contract; InsightBackend is one implementation of it.
    SKUEL023_FACADE_ALLOWLIST_PREFIXES: ClassVar[tuple[str, ...]] = (
        "core/services/ku/",
        "core/services/ps/",
        "core/services/lp/",
        "core/services/user/",
        "core/services/insight/",
    )
    SKUEL023_FACADE_ALLOWLIST_FILES: ClassVar[tuple[str, ...]] = (
        "core/services/ku_service.py",
        "core/services/user_service.py",
    )

    # SKUEL023: suffix heuristic — only annotations whose bare type name ends in one
    # of these is treated as a "backend-like" adapter export. Naturally excludes
    # enums (e.g. QueryOptimizationStrategy), configs, dataclasses, and other pure
    # data that legitimately crosses the boundary as a type.
    SKUEL023_BACKEND_SUFFIXES: ClassVar[tuple[str, ...]] = (
        "Backend",
        "Executor",
        "Adapter",
        "Repository",
        "Client",
        "Driver",
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
        ignore_suppressions: bool = False,
    ) -> None:
        self.root_dir = root_dir
        self.target_path = target_path
        self.rules_filter = rules_filter
        self.changed_files = changed_files
        # Shadow-lint mode for the SKUEL026 suppression audit: rules behave as if
        # no suppression comments existed, so the audit can see what WOULD fire.
        self.ignore_suppressions = ignore_suppressions
        self.result = LintResult()
        # Per-file memo for _inert_string_constant_ids — SKUEL001 and SKUEL021
        # share the same inert-docstring walk over the same tree. Keyed by the
        # tree OBJECT (identity compare on a held strong ref, so a recycled
        # id() can never alias two trees).
        self._inert_ids_memo: tuple[ast.AST, set[int]] | None = None

    @staticmethod
    def _git_changed_files(root_dir: Path, staged_only: bool = False) -> list[Path] | None:
        """Get Python files changed via git. Returns None if git is unavailable."""
        try:
            # --relative: git prints paths relative to the REPO ROOT by default,
            # but root_dir here is app/ (a subdirectory of the repo). Without it,
            # every path fails the .exists() join below and the mode silently
            # lints nothing. --relative re-roots paths to cwd AND excludes
            # changes outside it — both exactly what we want.
            if staged_only:
                cmd = ["git", "diff", "--relative", "--name-only", "--cached", "--diff-filter=ACMR"]
            else:
                cmd = [
                    "git",
                    "diff",
                    "--relative",
                    "--name-only",
                    "main...HEAD",
                    "--diff-filter=ACMR",
                ]
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
        except subprocess.TimeoutExpired, FileNotFoundError:
            return None

    def lint(self) -> LintResult:
        """Run all linting rules."""
        start_time = time.time()
        python_files = self._find_python_files()
        self.result.files_scanned = len(python_files)

        for file_path in python_files:
            self._lint_file(file_path)

        # SKUEL026 suppression audit — skipped in shadow mode (the audit's own
        # re-lint) and when a --rule filter excludes it.
        if not self.ignore_suppressions and self._should_run_rule("SKUEL026"):
            self._audit_suppressions(python_files)

        self.result.scan_time_ms = (time.time() - start_time) * 1000
        return self.result

    def _should_run_rule(self, rule_id: str) -> bool:
        """Check if a rule should run based on filter."""
        if self.rules_filter is None:
            return True
        return rule_id in self.rules_filter

    def _is_line_suppressed(self, line: str, rule_id: str) -> bool:
        """Check for inline suppression: # skuel-lint: disable=SKUEL011"""
        if self.ignore_suppressions:
            return False
        return f"# skuel-lint: disable={rule_id}" in line

    def _is_file_suppressed(self, content: str, rule_id: str) -> bool:
        """Check for file-level suppression: # skuel-lint: disable-file=SKUEL011"""
        if self.ignore_suppressions:
            return False
        return f"# skuel-lint: disable-file={rule_id}" in content

    def _find_suppression_comments(self, file_path: Path) -> list[SuppressionComment]:
        """
        Find genuine `# skuel-lint: disable[-file]=SKUELXXX` comments in a file.

        Uses tokenize so only real COMMENT tokens count — suppression examples
        inside string literals / docstrings (linter tests, rule docs) are never
        audited. Returns [] on unreadable or syntactically untokenizable files.
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            return []
        # Cheap pre-filter: tokenizing every file would dominate the audit cost.
        if "skuel-lint:" not in content:
            return []

        rel_path = file_path.relative_to(self.root_dir)
        comments: list[SuppressionComment] = []
        try:
            tokens = tokenize.generate_tokens(io.StringIO(content).readline)
            for tok in tokens:
                if tok.type != tokenize.COMMENT:
                    continue
                for match in self._SUPPRESSION_COMMENT_RE.finditer(tok.string):
                    comments.append(
                        SuppressionComment(
                            file_path=rel_path,
                            line_number=tok.start[0],
                            rule_id=match.group("rule"),
                            file_level=bool(match.group("filelevel")),
                            line_content=tok.line.strip(),
                        )
                    )
        except tokenize.TokenError, IndentationError, SyntaxError:
            return []
        return comments

    def _audit_suppressions(self, python_files: list[Path]) -> None:
        """
        SKUEL026: flag suppression comments that suppress nothing.

        For every file containing suppression comments, shadow-lint that file
        with suppressions ignored and only the named rules enabled. A comment is
        USED iff its rule fires in the shadow run (at its line for line-level /
        anywhere in the file for file-level) AND is absent from the main run —
        i.e. the comment actually suppressed something. A rule that fires in
        BOTH runs was not suppressed (non-suppressible rule, malformed comment),
        so the comment is flagged alongside the visible violation.

        Line matching is span-aware: a checker reads the suppression off the
        exact line it reports (`lines[lineno - 1]`) OR, for multi-line header
        constructs, off any line in the violation's ``suppression_span``
        (SKUEL005 def signatures, SKUEL017 except clauses). The Violation
        carries that span, so checker and audit honor the SAME set of lines.
        """

        # Snapshot BEFORE any SKUEL026 findings are appended below.
        main_violations = list(self.result.violations)
        main_file_hits = {(str(v.file_path), v.rule_id) for v in main_violations}

        for file_path in python_files:
            comments = self._find_suppression_comments(file_path)
            if not comments:
                continue

            shadow = SkuelLinter(
                self.root_dir,
                rules_filter=sorted({c.rule_id for c in comments}),
                ignore_suppressions=True,
            )
            shadow._lint_file(file_path)
            shadow_violations = shadow.result.violations
            fired_rules = {v.rule_id for v in shadow_violations}

            for comment in comments:
                rel_str = str(comment.file_path)
                fired = (
                    comment.rule_id in fired_rules
                    if comment.file_level
                    else self._fires_at_line(
                        shadow_violations, comment.rule_id, comment.line_number
                    )
                )
                if comment.file_level:
                    comment.used = fired and (rel_str, comment.rule_id) not in main_file_hits
                else:
                    hit_in_main = self._fires_at_line(
                        [v for v in main_violations if str(v.file_path) == rel_str],
                        comment.rule_id,
                        comment.line_number,
                    )
                    comment.used = fired and not hit_in_main
                self.result.suppressions.append(comment)
                if comment.used:
                    continue

                scope = "in this file" if comment.file_level else "at this line"
                if comment.rule_id not in RULE_DOCS:
                    why = f"'{comment.rule_id}' is not a SKUEL rule (typo?)"
                elif comment.rule_id not in self.SUPPRESSIBLE_RULES:
                    why = f"{comment.rule_id} does not support inline suppression"
                elif fired:
                    why = (
                        f"{comment.rule_id} fires {scope} but was not suppressed "
                        f"(malformed comment? the checkers match the exact substring)"
                    )
                else:
                    why = f"{comment.rule_id} would not fire {scope}"
                self.result.violations.append(
                    Violation(
                        file_path=comment.file_path,
                        line_number=comment.line_number,
                        column=0,
                        severity=Severity.WARNING,
                        rule_id="SKUEL026",
                        message=f"Suppression comment suppresses nothing — {why}",
                        suggestion=(
                            "Delete the comment (git history keeps the reason). If it "
                            "was meant to suppress a real violation, the checkers match "
                            "the exact substring '# skuel-lint: disable[-file]=SKUELXXX' "
                            "on the flagged line."
                        ),
                        line_content=comment.line_content,
                    )
                )

    def _find_python_files(self) -> list[Path]:
        """Find all Python files to lint."""
        # Git-aware mode: use pre-resolved changed files
        if self.changed_files is not None:
            return [f for f in self.changed_files if not self._is_excluded(f)]

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
            if self._is_excluded(py_file):
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
            # Other service-only rules (SKUEL002/004/005/007/014) stay on is_service;
            # SKUEL013 additionally covers the inbound/presentation layers (see below).
            path_str = str(file_path)
            is_core = "/core/" in path_str and file_path.suffix == ".py"
            is_ui = "/ui/" in path_str and file_path.suffix == ".py"
            # is_service is a strict subset of is_core today (no /services/ tree lives
            # outside core/), but keep it in the OR so a future non-core service dir
            # still gets the boundary rules.
            is_below_boundary = is_core or is_service

            # Shared parse: every AST rule reads the SAME tree, parsed once per
            # file (previously each rule re-parsed independently — ~7 parses/file
            # dominated full-scan time). None = syntax error → AST rules skip.
            tree: ast.Module | None = None
            if not is_test and any(self._should_run_rule(r) for r in self.AST_RULE_IDS):
                try:
                    tree = ast.parse(content)
                except SyntaxError:
                    tree = None

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
                self._check_broad_exception_catches(file_path, rel_path, content, lines, tree)
            if self._should_run_rule("SKUEL018") and not is_test:
                self._check_rich_only_field_access(file_path, rel_path, content, lines)
            if self._should_run_rule("SKUEL019") and not is_test:
                self._check_credential_env_reads(file_path, rel_path, content, lines)
            if self._should_run_rule("SKUEL020") and not is_test:
                self._check_request_annotation(file_path, rel_path, content, lines, tree)
            if self._should_run_rule("SKUEL024") and not is_test:
                self._check_cls_kwargs_collision(file_path, rel_path, content, lines, tree)
            if self._should_run_rule("SKUEL025") and not is_test:
                self._check_deleted_activity_update_payloads(
                    file_path, rel_path, content, lines, tree
                )

            # INFO rules (always run for visibility)
            if self._should_run_rule("SKUEL006"):
                self._check_todo_comments(file_path, rel_path, content, lines)

            # Boundary rules (ADR-044): no APOC, no raw Cypher anywhere in core/.
            if is_below_boundary and not is_test:
                if self._should_run_rule("SKUEL001"):
                    self._check_apoc_in_services(file_path, rel_path, content, lines, tree)
                if self._should_run_rule("SKUEL021"):
                    self._check_raw_cypher_in_services(file_path, rel_path, content, lines, tree)

            # Import-direction rule (ADR-044): all of core/, not just services.
            if is_core and not is_test and self._should_run_rule("SKUEL022"):
                self._check_core_imports_adapter(file_path, rel_path, content, lines, tree)

            # Import-direction rule (SoC): ui/ renders what routes hand it — no
            # runtime adapters imports (SKUEL022's sibling for the ui/ layer).
            if is_ui and not is_test and self._should_run_rule("SKUEL027"):
                self._check_ui_imports_adapter(file_path, rel_path, content, lines, tree)

            # Static type-direction rule (ADR-044): all of core/, not just services.
            # Closes the TYPE_CHECKING exemption gap left open by SKUEL022.
            if is_core and not is_test and self._should_run_rule("SKUEL023"):
                self._check_adapter_type_annotations(file_path, rel_path, content, lines, tree)

            if is_service and not is_test:
                if self._should_run_rule("SKUEL002"):
                    self._check_semantic_type_strings(file_path, rel_path, content, lines, tree)
                if self._should_run_rule("SKUEL005"):
                    self._check_result_return_types(file_path, rel_path, content, lines, tree)
                if self._should_run_rule("SKUEL007"):
                    self._check_string_result_fail(file_path, rel_path, content, lines)
                if self._should_run_rule("SKUEL014"):
                    self._check_entity_type_strings(file_path, rel_path, content, lines, tree)

            # Inbound/presentation layers (routes, UI renderers, api/ models) —
            # raw relationship-type strings creep in here too, so SKUEL013 runs
            # on these layers in addition to services. SKUEL014/SKUEL007 stay
            # service-only for now; widening them is staged as follow-up PRs.
            is_inbound_layer = rel_path.as_posix().startswith(("adapters/inbound/", "ui/", "api/"))
            if (is_service or is_inbound_layer) and not is_test:
                if self._should_run_rule("SKUEL013"):
                    self._check_relationship_name_strings(file_path, rel_path, content, lines, tree)

            if "/adapters/persistence/" in str(file_path):
                if self._should_run_rule("SKUEL008"):
                    self._check_backend_wrappers(file_path, rel_path, content)

        except Exception as e:
            print(f"Error linting {file_path}: {e}", file=sys.stderr)

    # =========================================================================
    # CRITICAL RULES
    # =========================================================================

    def _check_apoc_in_services(
        self,
        file_path: Path,
        rel_path: Path,
        content: str,
        lines: list[str],
        tree: ast.Module | None,
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

        if tree is None:
            return

        inert_ids = self._inert_ids_for(tree)
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

    @staticmethod
    def _fires_at_line(violations: list[Violation], rule_id: str, line: int) -> bool:
        """True if any violation of ``rule_id`` covers ``line`` — where "covers"
        means the exact reported line, or any line of the violation's
        ``suppression_span`` for multi-line header constructs."""
        for v in violations:
            if v.rule_id != rule_id:
                continue
            start, end = v.suppression_span or (v.line_number, v.line_number)
            if start <= line <= end:
                return True
        return False

    def _inert_ids_for(self, tree: ast.AST) -> set[int]:
        """Memoized `_inert_string_constant_ids` — one walk per file, shared by
        every string-constant rule (SKUEL001/021 today)."""
        if self._inert_ids_memo is not None and self._inert_ids_memo[0] is tree:
            return self._inert_ids_memo[1]
        ids = self._inert_string_constant_ids(tree)
        self._inert_ids_memo = (tree, ids)
        return ids

    def _check_raw_cypher_in_services(
        self,
        file_path: Path,
        rel_path: Path,
        content: str,
        lines: list[str],
        tree: ast.Module | None,
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

        if tree is None:
            return

        inert_ids = self._inert_ids_for(tree)
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

    # SKUEL002: the SemanticRelationshipType member names. A string literal whose
    # value IS one of these (exact match) is a magic string standing in for the enum.
    SEMANTIC_TYPE_NAMES: ClassVar[frozenset[str]] = frozenset(
        {
            "REQUIRES_THEORETICAL_UNDERSTANDING",
            "REQUIRES_PRACTICAL_APPLICATION",
            "REQUIRES_CONCEPTUAL_FOUNDATION",
            "BUILDS_ON_FOUNDATION",
            "HAS_BROADER_CONCEPT",
            "HAS_NARROWER_CONCEPT",
            "SHARES_PRINCIPLE_WITH",
            "ANALOGOUS_TO",
        }
    )

    def _check_semantic_type_strings(
        self,
        file_path: Path,
        rel_path: Path,
        content: str,
        lines: list[str],
        tree: ast.Module | None,
    ) -> None:
        """
        SKUEL002 [ERROR]: Use SemanticRelationshipType enum, not magic strings.

        AST-based, docstring-aware (same model as SKUEL021): flags a *used* string
        Constant whose value is exactly a SemanticRelationshipType member name.
        Inert bare-string statements (docstrings, USAGE EXAMPLES blocks) and
        comments are never string nodes in play, so prose mentioning a semantic
        type name cannot trip the rule. Exact-value matching means a name embedded
        in a longer string (e.g. quoted inside documentation text) is not flagged —
        only a literal standing in for the enum member is.
        """
        if tree is None:
            return

        inert_ids = self._inert_ids_for(tree)
        reported_lines: set[int] = set()

        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if id(node) in inert_ids:
                continue
            if node.value not in self.SEMANTIC_TYPE_NAMES:
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
                    severity=Severity.ERROR,
                    rule_id="SKUEL002",
                    message=f"Magic string '{node.value}' - use enum instead",
                    suggestion=f"Use SemanticRelationshipType.{node.value}",
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

    # SKUEL005: method names exempt from the Result[T] contract — cache-style
    # utilities and event-style fire-and-forget handlers (mirrors the old
    # line-substring patterns, translated onto the method NAME).
    RESULT_EXEMPT_NAMES: ClassVar[frozenset[str]] = frozenset(
        {"get", "set", "delete", "clear", "get_hit_rate", "is_expired"}
    )
    RESULT_EXEMPT_PREFIXES: ClassVar[tuple[str, ...]] = (
        "handle_",
        "learn_from_",
        "increment_",
        "ensure_",
    )

    # Annotation text that satisfies SKUEL005: `Result`, `Result[T]`,
    # `Result[T] | None`, and string forward-refs thereof. Word-bounded so
    # `LintResult` / `Results` don't pass.
    _RESULT_ANNOTATION_RE: ClassVar[re.Pattern[str]] = re.compile(r"\bResult\b")

    def _check_result_return_types(
        self,
        file_path: Path,
        rel_path: Path,
        content: str,
        lines: list[str],
        tree: ast.Module | None,
    ) -> None:
        """
        SKUEL005 [WARNING]: Service methods should return Result[T].

        AST-based: flags every top-level-or-method ``async def`` (not nested
        inside another function) whose return annotation does not reference
        ``Result`` — including multi-line signatures, which the old
        single-physical-line check was completely blind to. Functions without a
        return annotation are not flagged (mypy's disallow_untyped_defs owns
        missing annotations in core.services).

        Skips: private methods (``_``-prefixed), ``@classmethod`` factories, and
        the utility-name exemptions in RESULT_EXEMPT_NAMES / _PREFIXES.

        The ``# skuel-lint: disable=SKUEL005`` comment is honored on any line of
        the def header (the ``async def`` line through the line before the body),
        so a suppression survives ruff-format wrapping a long signature; the
        violation carries that span for the SKUEL026 audit.
        """
        if "protocol" in str(file_path).lower():
            return

        if self._is_file_suppressed(content, "SKUEL005"):
            return
        if tree is None:
            return

        # Functions nested inside another function/lambda are helpers, not the
        # service surface — collect them so the main walk can skip them. Methods
        # of Protocol classes are contract stubs, not implementations — the
        # implementing service is where the Result[T] contract is enforced
        # (protocols declared in *protocol*-named files are already exempt via
        # the file-name check; this catches Protocol classes declared inline).
        nested_ids: set[int] = set()
        for scope in ast.walk(tree):
            if isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
                for child in ast.walk(scope):
                    if child is not scope and isinstance(child, ast.AsyncFunctionDef):
                        nested_ids.add(id(child))
            elif isinstance(scope, ast.ClassDef) and any(
                (isinstance(base, ast.Name) and base.id == "Protocol")
                or (isinstance(base, ast.Attribute) and base.attr == "Protocol")
                for base in scope.bases
            ):
                for child in ast.walk(scope):
                    if isinstance(child, ast.AsyncFunctionDef):
                        nested_ids.add(id(child))

        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            if id(node) in nested_ids:
                continue
            if node.returns is None:
                continue
            name = node.name
            if name.startswith("_"):
                continue
            if name in self.RESULT_EXEMPT_NAMES or name.startswith(self.RESULT_EXEMPT_PREFIXES):
                continue
            # @classmethod factories (dataclass builders, not service methods)
            if any(
                (isinstance(d, ast.Name) and d.id == "classmethod")
                or (isinstance(d, ast.Attribute) and d.attr == "classmethod")
                for d in node.decorator_list
            ):
                continue
            if self._RESULT_ANNOTATION_RE.search(ast.unparse(node.returns)):
                continue

            start = node.lineno
            end = max(start, node.body[0].lineno - 1) if node.body else start
            # Suppression: any def-header line (span recorded on the violation).
            if any(
                self._is_line_suppressed(lines[i], "SKUEL005")
                for i in range(start - 1, min(end, len(lines)))
            ):
                continue

            line = lines[start - 1] if 0 < start <= len(lines) else ""
            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=start,
                    column=node.col_offset,
                    severity=Severity.WARNING,
                    rule_id="SKUEL005",
                    message="Service method should return Result[T]",
                    suggestion="Change return type to Result[T]",
                    line_content=line.strip(),
                    suppression_span=(start, end),
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
        if "/examples/" in file_str or "/scripts/" in file_str:
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
                    suggestion="Use operator.attrgetter/itemgetter for simple extraction; define a named helper only for domain logic or None-fallback",
                    line_content=line.strip(),
                )
            )

    # SKUEL013: relationship type names that must go through the RelationshipName
    # enum. A string literal whose value IS one of these (exact match) is a magic
    # string standing in for the enum member.
    RELATIONSHIP_NAMES: ClassVar[frozenset[str]] = frozenset(
        {
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
        }
    )

    def _check_relationship_name_strings(
        self,
        file_path: Path,
        rel_path: Path,
        content: str,
        lines: list[str],
        tree: ast.Module | None,
    ) -> None:
        """
        SKUEL013 [WARNING]: Use RelationshipName enum instead of magic strings.

        AST-based, docstring-aware (same model as SKUEL021): flags a *used* string
        Constant whose value is exactly a relationship type name. Comments and
        inert bare-string statements (docstrings, USAGE EXAMPLES blocks) never
        reach the check, and exact-value matching means a relationship name inside
        a longer string (Cypher text, prose) is not flagged — which structurally
        replaces the old 10-line "am I inside a Cypher query" lookback heuristic.
        Cypher itself cannot legitimately exist in this rule's scope anyway:
        SKUEL021 bans it across core/.
        """
        if tree is None:
            return

        inert_ids = self._inert_ids_for(tree)
        reported: set[tuple[int, str]] = set()

        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if id(node) in inert_ids:
                continue
            if node.value not in self.RELATIONSHIP_NAMES:
                continue

            line_num = node.lineno
            if (line_num, node.value) in reported:
                continue
            reported.add((line_num, node.value))
            line = lines[line_num - 1] if 0 < line_num <= len(lines) else ""
            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=node.col_offset,
                    severity=Severity.WARNING,
                    rule_id="SKUEL013",
                    message=f"Magic string '{node.value}' - use RelationshipName enum",
                    suggestion=f"Use RelationshipName.{node.value}",
                    line_content=line.strip(),
                )
            )

    # SKUEL014: entity-type identifiers that must be compared via the
    # EntityType / NonKuDomain enums, never as raw strings.
    ENTITY_TYPE_STRINGS: ClassVar[frozenset[str]] = frozenset(
        {
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
            "entry_report",
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
        }
    )

    @staticmethod
    def _mentions_enum_name(node: ast.AST) -> bool:
        """True if any Name inside ``node`` is EntityType / NonKuDomain — the
        comparison already routes through the enum (e.g. ``EntityType.TASK.value
        == raw``), so a string operand is not a magic-string violation."""
        return any(
            isinstance(n, ast.Name) and n.id in ("EntityType", "NonKuDomain")
            for n in ast.walk(node)
        )

    def _check_entity_type_strings(
        self,
        file_path: Path,
        rel_path: Path,
        content: str,
        lines: list[str],
        tree: ast.Module | None,
    ) -> None:
        """
        SKUEL014 [WARNING]: Use EntityType/NonKuDomain enum instead of magic strings.

        AST-based: flags COMPARISONS against raw entity-type strings — the shapes
        that should route through the enum:

        - equality:    ``entity_type == "task"``   (either side, case-insensitive)
        - membership:  ``"task" in contexts``      (string on the left)
        - membership:  ``entity_type in ("task", "goal")`` (literal container)

        A Compare that already references EntityType / NonKuDomain anywhere in it
        (e.g. ``EntityType.TASK.value == raw``) is exempt — the enum is in play.
        Plain string literals outside comparisons (dict keys, log messages,
        docstrings) are deliberately NOT flagged: "task" the word is ubiquitous;
        only comparison context makes it an entity-type discriminator.
        """
        if tree is None:
            return

        reported_lines: set[int] = set()

        def flag(line_num: int, col: int, value: str) -> None:
            if line_num in reported_lines:
                return
            reported_lines.add(line_num)
            line = lines[line_num - 1] if 0 < line_num <= len(lines) else ""
            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=col,
                    severity=Severity.WARNING,
                    rule_id="SKUEL014",
                    message=f"Magic string '{value}' - use EntityType/NonKuDomain enum",
                    suggestion=f"Use EntityType.{value.upper()} or NonKuDomain.{value.upper()}",
                    line_content=line.strip(),
                )
            )

        def entity_string(node: ast.expr) -> ast.Constant | None:
            """The node as an entity-type string Constant, else None."""
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value.lower() in self.ENTITY_TYPE_STRINGS
            ):
                return node
            return None

        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            if self._mentions_enum_name(node):
                continue

            left = node.left
            for op, right in zip(node.ops, node.comparators, strict=True):
                if isinstance(op, ast.Eq | ast.NotEq):
                    for side in (left, right):
                        hit = entity_string(side)
                        if hit is not None:
                            flag(hit.lineno, hit.col_offset, str(hit.value))
                elif isinstance(op, ast.In | ast.NotIn):
                    # "task" in contexts — string on the left of `in`
                    hit = entity_string(left)
                    if hit is not None:
                        flag(hit.lineno, hit.col_offset, str(hit.value))
                    # entity_type in ("task", "goal") — literal container of strings
                    elif isinstance(right, ast.Tuple | ast.List | ast.Set):
                        for elt in right.elts:
                            hit = entity_string(elt)
                            if hit is not None:
                                flag(hit.lineno, hit.col_offset, str(hit.value))
                                break
                left = right

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

    # SKUEL016: precompiled once — this rule runs on EVERY file (tests included),
    # and per-call re.search with an inline pattern made it the single hottest
    # checker in a full scan before the `poetry` content pre-filter below.
    POETRY_PATTERNS: ClassVar[tuple[tuple[re.Pattern[str], str, str], ...]] = (
        (re.compile(r"\bpoetry\s+install\b", re.IGNORECASE), "poetry install", "uv sync"),
        (re.compile(r"\bpoetry\s+add\b", re.IGNORECASE), "poetry add", "uv add"),
        (re.compile(r"\bpoetry\s+remove\b", re.IGNORECASE), "poetry remove", "uv remove"),
        (re.compile(r"\bpoetry\s+run\b", re.IGNORECASE), "poetry run", "uv run"),
        (re.compile(r"\bpoetry\s+lock\b", re.IGNORECASE), "poetry lock", "uv lock"),
        (re.compile(r"\bpoetry\s+update\b", re.IGNORECASE), "poetry update", "uv lock --upgrade"),
        (re.compile(r"\bpoetry\.lock\b", re.IGNORECASE), "poetry.lock", "uv.lock"),
        (re.compile(r"\[tool\.poetry\b", re.IGNORECASE), "[tool.poetry]", "[project]"),
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

        # Cheap pre-filter: every pattern contains the literal "poetry".
        if "poetry" not in content.lower():
            return

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Skip comments that explain the migration itself
            if stripped.startswith("#") and (
                "migrat" in stripped.lower() or "was" in stripped.lower()
            ):
                continue

            for pattern, match_text, replacement in self.POETRY_PATTERNS:
                match = pattern.search(line)
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

    @staticmethod
    def _catches_bare_exception(handler_type: ast.expr | None) -> bool:
        """True if an except clause catches the bare ``Exception`` class —
        directly (``except Exception``) or inside a tuple
        (``except (ValueError, Exception)``). ``except:`` (type None) is ruff
        E722's territory, not this rule's."""
        if isinstance(handler_type, ast.Name):
            return handler_type.id == "Exception"
        if isinstance(handler_type, ast.Tuple):
            return any(
                isinstance(elt, ast.Name) and elt.id == "Exception" for elt in handler_type.elts
            )
        return False

    def _check_broad_exception_catches(
        self,
        file_path: Path,
        rel_path: Path,
        content: str,
        lines: list[str],
        tree: ast.Module | None,
    ) -> None:
        """
        SKUEL017 [WARNING]: Bare `except Exception` without justification.

        AST-based: flags every ``ast.ExceptHandler`` whose type resolves to
        ``Exception`` (bare Name or inside a tuple) — including formatter-wrapped
        clauses like ``except (\\n    Exception\\n) as e:`` that the old
        single-line regex was blind to. Docstring mentions are structurally
        immune (a string is not an ExceptHandler).

        Justification markers ``# intentional-broad:`` / ``# safety-net:`` are
        honored on the line above the ``except`` and on any line of the clause
        header (the ``except`` line through the line before the body). The
        ``# skuel-lint: disable=SKUEL017`` comment is honored on any header line
        (the violation carries that span for the SKUEL026 audit).

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

        if self._is_file_suppressed(content, "SKUEL017"):
            return
        if tree is None:
            return

        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if not self._catches_bare_exception(node.type):
                continue

            start = node.lineno
            end = max(start, node.body[0].lineno - 1) if node.body else start

            # Markers: line above the except + any clause-header line.
            marker_zone = lines[max(0, start - 2) : end]
            if any(
                "# intentional-broad:" in marker_line or "# safety-net:" in marker_line
                for marker_line in marker_zone
            ):
                continue

            # Suppression: any clause-header line (span recorded on the violation).
            if any(
                self._is_line_suppressed(lines[i], "SKUEL017")
                for i in range(start - 1, min(end, len(lines)))
            ):
                continue

            line = lines[start - 1] if 0 < start <= len(lines) else ""
            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=start,
                    column=node.col_offset,
                    severity=Severity.WARNING,
                    rule_id="SKUEL017",
                    message="Bare `except Exception` — use specific exception types",
                    suggestion=(
                        "Import from core.utils.exception_types "
                        "(NEO4J_EXCEPTIONS, LLM_EXCEPTIONS, etc.) "
                        "or add `# intentional-broad: <reason>` comment"
                    ),
                    line_content=line.strip(),
                    suppression_span=(start, end),
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
        self,
        file_path: Path,
        rel_path: Path,
        content: str,
        lines: list[str],
        tree: ast.Module | None,
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

        # Cheap pre-filter: only walk files that actually register routes. Every
        # decorator we match renders as `@rt...` or `@app....` in source.
        if "@rt" not in content and "@app." not in content:
            return

        if tree is None:
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

    @staticmethod
    def _locally_assigned_names(fn: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> set:
        """Names REBOUND in ``fn``'s own scope (not params), excluding nested scopes.

        Any assignment to a name makes it function-local for that whole scope (Python
        scoping). So ``def make(): kwargs = {...}; Div(cls=.., **kwargs)`` splats a LOCAL
        dict — a caller's ``cls=`` cannot collide — even though an outer ``**kwargs`` shares
        the name. Collects ``=`` / ``:=`` / augmented / annotated assignments, ``for`` /
        ``with`` / ``except`` targets, import names, and nested ``def``/``class`` names,
        WITHOUT descending into nested function/lambda/class bodies (their assignments are
        their own). Names declared ``global`` / ``nonlocal`` are excluded — they refer
        outward, so they do not shadow.
        """
        nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
        assigned: set[str] = set()
        outward: set[str] = set()

        def add_target(target: ast.AST) -> None:
            for n in ast.walk(target):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                    assigned.add(n.id)

        def visit(n: ast.AST) -> None:
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    add_target(t)
            elif isinstance(n, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
                add_target(n.target)
            elif isinstance(n, (ast.For, ast.AsyncFor)):
                add_target(n.target)
            elif isinstance(n, (ast.With, ast.AsyncWith)):
                for item in n.items:
                    if item.optional_vars is not None:
                        add_target(item.optional_vars)
            elif isinstance(n, ast.ExceptHandler):
                if n.name:
                    assigned.add(n.name)
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                for alias in n.names:
                    assigned.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(n, (ast.Global, ast.Nonlocal)):
                outward.update(n.names)
            for child in ast.iter_child_nodes(n):
                if isinstance(child, nested):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        assigned.add(child.name)  # binds the def/class NAME in this scope
                    continue  # but do not descend — its body is its own scope
                visit(child)

        body = fn.body if isinstance(fn.body, list) else [fn.body]  # Lambda body is an expr
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                assigned.add(stmt.name)
                continue
            if isinstance(stmt, ast.Lambda):
                continue
            visit(stmt)
        return assigned - outward

    @classmethod
    def _cls_scope_descriptor(
        cls, fn: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda
    ) -> tuple:
        """Describe a function scope for ``**kwargs`` / ``cls=`` resolution.

        Returns ``(fn, kwarg_name, param_names, absorbs_cls, assigned_names)``:
        - ``param_names`` — every parameter the scope binds.
        - ``absorbs_cls`` — True iff the scope has a KEYWORD-PASSABLE ``cls`` param
          (positional-or-keyword or keyword-only; a positional-only ``cls`` does NOT
          absorb a keyword ``cls=`` and is excluded).
        - ``assigned_names`` — names locally rebound in the scope (see
          ``_locally_assigned_names``). Used ONLY for resolution/shadowing: a scope
          binds a name if it is in ``param_names`` OR ``assigned_names``, so a nested
          ``def make(): kwargs = {}; Div(cls=.., **kwargs)`` resolves the splat to
          ``make`` (a local dict), not an outer ``**kwargs``. It is NOT used to clear a
          collision in the ``**kwargs``-owning scope — a conditional/post-splat reassign
          does not sanitize every path (no control-flow domination), mirroring the
          absent ``kwargs.pop("cls")`` exemption.

        The rule resolves a splat NAME to its binding scope (a structural, compile-time
        fact), but does not track a local variable's VALUE — value-flow / alias / taint
        analysis (``attrs = kwargs``, ``dict(kwargs)``) is a documented boundary, since it
        cannot be done soundly without control-flow analysis.
        """
        args = fn.args
        kwarg_name = args.kwarg.arg if args.kwarg else None
        param_names = {a.arg for a in args.posonlyargs + args.args + args.kwonlyargs}
        if args.vararg:
            param_names.add(args.vararg.arg)
        if kwarg_name:
            param_names.add(kwarg_name)
        # A @classmethod's first parameter (conventionally `cls`) is the bound class
        # receiver, NOT a caller-passable style arg — `M(cls="x")` can't bind to it and
        # collides in **kwargs. Exclude it from the absorbing-cls set so the rule still
        # flags `@classmethod def M(cls, **kw): Span(cls="x", **kw)`.
        decorators = getattr(fn, "decorator_list", [])
        is_classmethod = any(
            (isinstance(d, ast.Name) and d.id == "classmethod")
            or (isinstance(d, ast.Attribute) and d.attr == "classmethod")
            for d in decorators
        )
        positional = args.posonlyargs + args.args
        receiver = positional[0].arg if is_classmethod and positional else None
        absorbs_cls = "cls" in {a.arg for a in args.args + args.kwonlyargs if a.arg != receiver}
        return (fn, kwarg_name, param_names, absorbs_cls, cls._locally_assigned_names(fn))

    def _check_cls_kwargs_collision(
        self,
        file_path: Path,
        rel_path: Path,
        content: str,
        lines: list[str],
        tree: ast.Module | None,
    ) -> None:
        """
        SKUEL024 [ERROR]: a helper must not hardcode ``cls=`` AND splat ``**kwargs``
        into the same call without an explicit ``cls`` parameter.

        Such a helper raises ``TypeError: got multiple values for keyword argument
        'cls'`` the moment a caller passes ``cls=`` — the value lands in ``**kwargs``
        and collides with the hardcoded keyword. This 500'd /insights via ``SmallText``
        (PR #154). Invisible to mypy/ruff; only a caller passing ``cls=`` surfaces it.

        Scope-resolution model: walk the tree carrying a stack of enclosing function
        scopes. For each call passing both a ``cls=`` keyword and a ``**Name`` splat,
        resolve ``Name`` to the NEAREST enclosing scope that binds it (handles closures —
        a nested ``def``/``lambda`` splatting the outer ``**kwargs`` — and rebinds — an
        inner factory with its OWN ``cls``/``**kwargs``). Flag iff that binding scope's
        bound name is its ``**kwargs`` and it has no keyword-passable ``cls`` param.

        No ``kwargs.pop("cls")`` exemption: proving a pop defuses the splat needs
        control-flow domination (a conditional or post-splat pop does not), and the
        explicit ``cls: str = ""`` parameter is the contract anyway — so pop-based helpers
        are flagged too. Adopt the explicit parameter, or suppress with a reason if a
        sound pop form is genuinely needed.
        """
        if self._is_file_suppressed(content, "SKUEL024"):
            return

        # Cheap pre-filter: a collision needs both a `cls` keyword and a `**` splat to
        # appear at all. Match the bare `cls` substring (NOT `cls=`) so a spaced keyword
        # (`cls = "x"`, valid Python) isn't skipped — the AST check below is the authority.
        if "cls" not in content or "**" not in content:
            return

        if tree is None:
            return

        scope_types = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
        reported: set[int] = set()  # binding-scope ids — one violation per binder

        def resolve_binder(name: str, stack: list[tuple]) -> tuple | None:
            for desc in reversed(stack):  # nearest enclosing scope wins (shadowing)
                if name in desc[2] or name in desc[4]:  # param_names or local assignments
                    return desc
            return None

        def flag(call: ast.Call, binder: tuple) -> None:
            fn, kw_name = binder[0], binder[1]
            if id(fn) in reported:
                return
            line_num = call.lineno
            line = lines[line_num - 1] if 0 < line_num <= len(lines) else ""
            if self._is_line_suppressed(line, "SKUEL024"):
                return  # don't mark reported — another non-suppressed call may still fire
            reported.add(id(fn))
            fn_name = getattr(fn, "name", "<lambda>")
            target = call.func
            target_name = getattr(target, "id", getattr(target, "attr", "the call"))
            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=call.col_offset,
                    severity=Severity.ERROR,
                    rule_id="SKUEL024",
                    message=(
                        f"`{fn_name}` passes `cls=` and `**{kw_name}` to `{target_name}(...)` "
                        f"with no `cls` parameter — a caller passing `cls=` raises "
                        f"TypeError (multiple values for 'cls')"
                    ),
                    suggestion=(
                        'Add an explicit `cls: str = ""` parameter and merge it: '
                        'cls=f"...base... {cls}".strip()'
                    ),
                    line_content=line.strip(),
                )
            )

        def walk(node: ast.AST, stack: list[tuple]) -> None:
            if isinstance(node, ast.Call) and any(k.arg == "cls" for k in node.keywords):
                for k in node.keywords:
                    if k.arg is None and isinstance(k.value, ast.Name):
                        name = k.value.id
                        binder = resolve_binder(name, stack)
                        # Flag iff the splat NAME is the resolved scope's **kwargs param
                        # and that scope has no keyword-passable cls. This is structural
                        # (compile-time scope binding); the rule does NOT track a local
                        # variable's VALUE. A local reassignment of an owned **kwargs is
                        # not treated as clearing the collision (no control-flow
                        # domination, same as the absent kwargs.pop("cls") exemption);
                        # value-flow / alias / taint cases (attrs = kwargs, dict(kwargs))
                        # are a documented boundary, not chased.
                        if binder and binder[1] == name and not binder[3]:
                            flag(node, binder)
                            break
            child_stack = stack
            if isinstance(node, scope_types):
                child_stack = stack + [self._cls_scope_descriptor(node)]
            for child in ast.iter_child_nodes(node):
                walk(child, child_stack)

        walk(tree, [])

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

    def _collect_runtime_adapter_imports(self, tree: ast.Module) -> list[tuple[ast.stmt, str]]:
        """``(node, module)`` for every runtime ``adapters`` import in *tree*.

        Shared scan behind SKUEL022 (core/) and SKUEL027 (ui/) — the layer scope,
        suppression, and message live in each rule's checker. Flags imports at module
        scope AND inside functions (a function-local import is the same runtime
        dependency, deferred past module load — the dodge a module-level-only check
        would miss).

        ``TYPE_CHECKING``-only imports are excluded: they never execute, so they cannot
        create a runtime dependency. Only the ``if`` BODY is exempt, never the
        ``else``/``elif`` branch — an import there DOES execute at runtime. Relative
        imports (``level > 0``) are never top-level ``adapters`` imports — including
        ``from .adapters import x``, a sibling module that happens to share the name
        (``node.module`` is ``"adapters"`` there but ``level`` is 1).
        """
        type_checking_lines: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and self._is_type_checking_test(node.test):
                for stmt in node.body:
                    for child in ast.walk(stmt):
                        lineno = getattr(child, "lineno", None)
                        if lineno is not None:
                            type_checking_lines.add(lineno)

        found: list[tuple[ast.stmt, str]] = []
        for node in ast.walk(tree):
            imported_modules: list[str] = []
            if isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    imported_modules.append(node.module)
            elif isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            else:
                continue

            adapter_modules = [
                m for m in imported_modules if m == "adapters" or m.startswith("adapters.")
            ]
            if not adapter_modules:
                continue
            if node.lineno in type_checking_lines:
                continue  # TYPE_CHECKING-only — cannot create a runtime dependency

            found.append((node, adapter_modules[0]))
        return found

    def _check_core_imports_adapter(
        self,
        file_path: Path,
        rel_path: Path,
        content: str,
        lines: list[str],
        tree: ast.Module | None,
    ) -> None:
        """
        SKUEL022 [ERROR]: a ``core/`` module must not import from ``adapters/``.

        The hexagonal dependency direction is core → adapter (ADR-044). A runtime
        import of an adapter inside ``core/`` inverts it. Scan mechanics (function-local
        imports flagged, TYPE_CHECKING body exempt): ``_collect_runtime_adapter_imports``.

        Typing an annotation against a concrete adapter class under
        ``if TYPE_CHECKING:`` is a separate purity concern (SKUEL023), not a layering
        violation.

        Fix: depend on a ``core/ports`` protocol and inject the concrete adapter at the
        composition root (``services_bootstrap/`` or a factory below the boundary).

        Suppress: # skuel-lint: disable=SKUEL022 -- <reason>
        File-level: # skuel-lint: disable-file=SKUEL022 -- <reason>
        """
        if self._is_file_suppressed(content, "SKUEL022"):
            return
        # Cheap pre-filter: only walk files that mention adapters at all.
        if "adapters" not in content:
            return

        if tree is None:
            return

        for node, module in self._collect_runtime_adapter_imports(tree):
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
                        f"core/ module imports adapter '{module}' at runtime "
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

    def _check_ui_imports_adapter(
        self,
        file_path: Path,
        rel_path: Path,
        content: str,
        lines: list[str],
        tree: ast.Module | None,
    ) -> None:
        """
        SKUEL027 [ERROR]: a ``ui/`` module must not import from ``adapters/`` at runtime.

        ``ui/`` is pure presentation — routes (``adapters/inbound``) compose UI
        components, never the reverse. Scan mechanics (function-local imports flagged,
        TYPE_CHECKING body exempt): ``_collect_runtime_adapter_imports``. A type-only
        ``adapters.inbound.fasthtml_types.Request`` annotation is fine — the Request
        protocol lives at the FastHTML boundary by design.

        Fix: move the shared code inward (``core/utils/`` or ``ui/``) or pass the value
        in from the route; request-derived state flows in via middleware-set ContextVars
        (``core/utils/auth_context.py``, ``core/utils/csrf_token_context.py``).

        Suppress: # skuel-lint: disable=SKUEL027 -- <reason>
        File-level: # skuel-lint: disable-file=SKUEL027 -- <reason>
        """
        if self._is_file_suppressed(content, "SKUEL027"):
            return
        # Cheap pre-filter: only walk files that mention adapters at all.
        if "adapters" not in content:
            return

        if tree is None:
            return

        for node, module in self._collect_runtime_adapter_imports(tree):
            line = lines[node.lineno - 1] if 0 < node.lineno <= len(lines) else ""
            if self._is_line_suppressed(line, "SKUEL027"):
                continue

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=node.lineno,
                    column=node.col_offset,
                    severity=Severity.ERROR,
                    rule_id="SKUEL027",
                    message=(
                        f"ui/ module imports adapter '{module}' at runtime "
                        f"— presentation must not depend on the boundary layer "
                        f"(routes compose UI, never the reverse)"
                    ),
                    suggestion=(
                        "Move the shared code inward (core/utils/ or ui/) or pass the "
                        "value in from the route; or move a type-only import under "
                        "`if TYPE_CHECKING:`"
                    ),
                    line_content=line.strip(),
                )
            )

    # The six Activity Domain update payloads deleted by ADR-066 Phase 7a. The
    # curriculum (Ku/Ps/Lp), finance, and report ``*UpdatePayload`` TypedDicts are
    # intentionally OUT of this set — they survive for non-activity domains.
    _DELETED_ACTIVITY_UPDATE_PAYLOADS: frozenset[str] = frozenset(
        {
            "TaskUpdatePayload",
            "GoalUpdatePayload",
            "HabitUpdatePayload",
            "EventUpdatePayload",
            "ChoiceUpdatePayload",
            "PrincipleUpdatePayload",
        }
    )

    def _check_deleted_activity_update_payloads(
        self,
        file_path: Path,
        rel_path: Path,
        content: str,
        lines: list[str],
        tree: ast.Module | None,
    ) -> None:
        """
        SKUEL025 [ERROR]: no reference to a deleted Activity Domain ``*UpdatePayload``.

        ADR-066 replaced the six activity ``*UpdatePayload`` TypedDicts with frozen
        ``*UpdateIntent`` dataclasses and the parameterized CRUD base (Phase 7a). The
        old names are gone; reintroducing one rebuilds the abandoned dict write-path
        (One Path Forward). The curriculum (Ku/Ps/Lp), finance, and report payloads are
        NOT in the forbidden set — they remain valid for non-activity domains.

        Trivially sound + AST-structural: flags an import alias, a bare ``Name``, or an
        ``Attribute`` access whose identifier is one of the six fixed forbidden names.
        No flow analysis — a string literal naming the type (e.g. in a test asserting
        its removal, or in this rule's own metadata) is never a ``Name``/``Attribute``
        node, so it is not flagged.

        Fix: use the domain ``*UpdateIntent`` (`core/models/<domain>/<domain>_update_intent.py`)
        or build it from the request via ``*UpdateRequest.to_intent()``.

        Suppress: # skuel-lint: disable=SKUEL025 -- <reason>
        File-level: # skuel-lint: disable-file=SKUEL025 -- <reason>
        """
        if self._is_file_suppressed(content, "SKUEL025"):
            return
        # Cheap pre-filter: the substring must appear at all.
        if "UpdatePayload" not in content:
            return

        if tree is None:
            return

        forbidden = self._DELETED_ACTIVITY_UPDATE_PAYLOADS
        seen: set[tuple[int, str]] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in forbidden:
                        # Use the alias's own location, not the `from ... import (` line —
                        # in a parenthesized multi-line import they differ, and an inline
                        # suppression sits on the alias line (Python 3.10+ gives aliases a
                        # lineno; fall back to the statement line if absent).
                        a_line = getattr(alias, "lineno", None) or node.lineno
                        a_col = getattr(alias, "col_offset", None)
                        if a_col is None:
                            a_col = node.col_offset
                        self._flag_deleted_payload(rel_path, lines, a_line, a_col, alias.name, seen)
                continue
            if isinstance(node, ast.Name):
                name: str = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            else:
                continue
            if name not in forbidden:
                continue
            self._flag_deleted_payload(rel_path, lines, node.lineno, node.col_offset, name, seen)

    def _flag_deleted_payload(
        self,
        rel_path: Path,
        lines: list[str],
        lineno: int,
        col: int,
        name: str,
        seen: set[tuple[int, str]],
    ) -> None:
        """Record one SKUEL025 violation, deduped per (line, name), honoring suppression."""
        if (lineno, name) in seen:
            return
        seen.add((lineno, name))
        line = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
        if self._is_line_suppressed(line, "SKUEL025"):
            return
        self.result.violations.append(
            Violation(
                file_path=rel_path,
                line_number=lineno,
                column=col,
                severity=Severity.ERROR,
                rule_id="SKUEL025",
                message=(
                    f"'{name}' was deleted by ADR-066 (Phase 7a) — Activity Domain updates "
                    f"use the frozen '{name.replace('UpdatePayload', 'UpdateIntent')}', not a TypedDict"
                ),
                suggestion=(
                    "Use the domain *UpdateIntent (core/models/<domain>/<domain>_update_intent.py) "
                    "or build it from the request via *UpdateRequest.to_intent()"
                ),
                line_content=line.strip(),
            )
        )

    # -------------------------------------------------------------------------
    # SKUEL023 helpers: collect adapter imports, extract bare type names from
    # annotations (including forward-reference strings + Subscript chains).
    # -------------------------------------------------------------------------

    @staticmethod
    def _is_adapter_module(module: str) -> bool:
        """True if ``module`` is ``adapters`` or under ``adapters.*``."""
        return module == "adapters" or module.startswith("adapters.")

    def _flag_aliased_or_module_style_adapter_imports(
        self, rel_path: Path, tree: ast.Module, lines: list[str]
    ) -> None:
        """Emit SKUEL023 violations for adapter imports that take a banned form.

        Tier-4 closure: in core/, an adapter import must be the plain
        ``from adapters.<...> import <Name>`` form. Any of the following are
        violations regardless of whether they are referenced in annotations:

        - ``from adapters... import X as Y`` — local-name aliasing dodges the
          annotation-level suffix check when ``Y`` happens not to end in a
          backend suffix.
        - ``import adapters[.x[.y]] [as Z]`` — module-style import (with or
          without alias) is what lets ``backend: <module>.XBackend`` annotations
          slip past the bare-Name lookup.

        These forms have zero uses in core/ as of rule introduction; banning
        them costs nothing and removes the bypass classes structurally.
        Line-level suppressions are honored via ``# skuel-lint: disable=SKUEL023``.
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if not node.module or not self._is_adapter_module(node.module):
                    continue
                line = lines[node.lineno - 1] if 0 < node.lineno <= len(lines) else ""
                if self._is_line_suppressed(line, "SKUEL023"):
                    continue
                for alias in node.names:
                    if alias.asname is None:
                        continue
                    self.result.violations.append(
                        Violation(
                            file_path=rel_path,
                            line_number=node.lineno,
                            column=node.col_offset,
                            severity=Severity.ERROR,
                            rule_id="SKUEL023",
                            message=(
                                f"core/ aliases adapter import '{alias.name}' "
                                f"as '{alias.asname}' (from '{node.module}') — "
                                f"adapter-import aliasing in core/ is banned "
                                f"(ADR-044); use the plain 'from {node.module} "
                                f"import {alias.name}' form or import the "
                                f"core/ports protocol instead"
                            ),
                            suggestion=(
                                f"Replace with: from {node.module} import "
                                f"{alias.name}. If the alias was hiding the "
                                f"adapter under a non-backend-shaped name to "
                                f"evade the annotation suffix check, the "
                                f"correct fix is to annotate against the "
                                f"core/ports/*Operations protocol."
                            ),
                            line_content=line.strip(),
                        )
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if not self._is_adapter_module(alias.name):
                        continue
                    line = lines[node.lineno - 1] if 0 < node.lineno <= len(lines) else ""
                    if self._is_line_suppressed(line, "SKUEL023"):
                        continue
                    display = (
                        f"{alias.name} as {alias.asname}"
                        if alias.asname is not None
                        else alias.name
                    )
                    self.result.violations.append(
                        Violation(
                            file_path=rel_path,
                            line_number=node.lineno,
                            column=node.col_offset,
                            severity=Severity.ERROR,
                            rule_id="SKUEL023",
                            message=(
                                f"core/ uses module-style adapter import "
                                f"'import {display}' — module-style imports of "
                                f"adapters in core/ are banned (ADR-044); they "
                                f"enable 'backend: <module>.XBackend' annotations "
                                f"that dodge the boundary"
                            ),
                            suggestion=(
                                f"Use 'from {alias.name} import <Name>' to "
                                f"import the specific class, or — preferably "
                                f"— import the matching core/ports/*Operations "
                                f"protocol and annotate against that."
                            ),
                            line_content=line.strip(),
                        )
                    )

    @staticmethod
    def _collect_adapter_imports(tree: ast.Module) -> dict[str, str]:
        """Walk the whole tree (runtime AND TYPE_CHECKING blocks) and return a
        ``{local_name: module_path}`` map for every ``from adapters... import X``
        and ``import adapters...``.

        Both layers are collected because SKUEL023 fires on the *annotation*, not
        the import — even an exempt TYPE_CHECKING-only import of an adapter class
        used as a type annotation is the design coupling we're catching.
        """
        imports: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if not node.module or not SkuelLinter._is_adapter_module(node.module):
                    continue
                for alias in node.names:
                    local = alias.asname or alias.name
                    imports[local] = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if SkuelLinter._is_adapter_module(alias.name):
                        local = alias.asname or alias.name.split(".")[0]
                        imports[local] = alias.name
        return imports

    @staticmethod
    def _extract_annotation_refs(annotation: ast.expr) -> list[tuple[str, str]]:
        """Recurse into an annotation expression and return ``(lookup_key, type_name)``
        pairs for every type reference inside it.

        - ``lookup_key`` is what the check loop matches against the
          ``{local_name -> module}`` import map (or the sentinel ``"adapters"``
          for Tier-3 fully-qualified references that bypass the import map).
        - ``type_name`` is the tail used both for the backend-suffix heuristic
          and the violation message.

        For most annotation shapes the two are identical. They diverge for
        ``Attribute`` chains, which is where the two bypass classes live:

        - **Tier 2 — module-style alias.** ``import adapters.x as xb`` plus
          ``backend: xb.XBackend`` parses to ``Attribute(value=Name("xb"),
          attr="XBackend")``. The import map keys on ``xb``, not ``XBackend``;
          walking to the root Name lets the lookup succeed.
        - **Tier 3 — fully-qualified string.** ``backend: "adapters.persistence.
          neo4j.x.XBackend"`` (no import at all) parses through the forward-ref
          path into the same Attribute chain whose root Name is ``adapters``.
          The sentinel ``("adapters", "XBackend")`` lets the check loop flag it
          even though the import map is empty.

        Handles:
        - ``Name("KuBackend")``                            -> ``[("KuBackend", "KuBackend")]``
        - ``Constant("KuBackend")`` (forward reference)    -> parsed via ``ast.parse``
        - ``Subscript`` (``Optional[X]``, ``list[X]``, ...) -> recurse into both halves
        - ``BinOp`` (``X | None`` PEP 604 unions)          -> recurse into both sides
        - ``Attribute`` (``a.b.C``)                        -> root Name as lookup, tail as type
        - ``Tuple`` slices (``Callable[[A, B], C]`` etc.)  -> recurse into each elt
        """
        refs: list[tuple[str, str]] = []
        if isinstance(annotation, ast.Name):
            refs.append((annotation.id, annotation.id))
        elif isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
            # Forward reference: parse as an expression and recurse.
            try:
                parsed = ast.parse(annotation.value, mode="eval").body
            except SyntaxError:
                return refs
            refs.extend(SkuelLinter._extract_annotation_refs(parsed))
        elif isinstance(annotation, ast.Subscript):
            refs.extend(SkuelLinter._extract_annotation_refs(annotation.value))
            refs.extend(SkuelLinter._extract_annotation_refs(annotation.slice))
        elif isinstance(annotation, ast.Tuple):
            for elt in annotation.elts:
                refs.extend(SkuelLinter._extract_annotation_refs(elt))
        elif isinstance(annotation, ast.BinOp):
            # PEP 604 unions (X | Y) reach us as BinOp(BitOr) in annotation context.
            refs.extend(SkuelLinter._extract_annotation_refs(annotation.left))
            refs.extend(SkuelLinter._extract_annotation_refs(annotation.right))
        elif isinstance(annotation, ast.Attribute):
            # Walk the value chain to the root Name. The root is what the
            # import map keys on (module alias for Tier 2, sentinel "adapters"
            # for Tier 3); the tail attr is the type name for suffix + reporting.
            root: ast.expr = annotation
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                refs.append((root.id, annotation.attr))
        # Anything else (Call, Lambda, ...) doesn't appear in a sane annotation.
        return refs

    def _check_adapter_type_annotations(
        self,
        file_path: Path,
        rel_path: Path,
        content: str,
        lines: list[str],
        tree: ast.Module | None,
    ) -> None:
        """
        SKUEL023 [ERROR]: a ``core/`` module must not type an annotation against a
        concrete adapter class.

        SKUEL022 enforces the runtime import direction (core → adapter banned at
        runtime); it deliberately exempts ``if TYPE_CHECKING:`` blocks because they
        never execute. That exemption is correct at the runtime layer but leaves a
        design-coupling gap: typing ``self.backend: KuBackend`` locks the service to
        the concrete adapter when it should depend on the ``core/ports`` protocol.

        AST-based, fail-closed. Walks runtime AND TYPE_CHECKING imports of
        ``adapters.*`` to build a ``{local_name -> module}`` map. Then walks the
        whole tree looking for type annotations (AnnAssign at any scope,
        FunctionDef arg annotations + return annotations) and flags any annotation
        whose ``(lookup_key, type_name)`` pair matches an adapter reference AND
        whose ``type_name`` ends in a backend-shaped suffix (``Backend`` /
        ``Executor`` / ``Adapter`` / ``Repository`` / ``Client`` / ``Driver``).
        The suffix heuristic excludes enums (e.g. ``QueryOptimizationStrategy``),
        configs, and pure-data adapter exports.

        Four bypass classes closed:
        - **Tier 1** — ``from adapters.x import XB`` + ``backend: XB``: the
          common pattern. ``lookup_key`` is ``XB``, found in the import map.
        - **Tier 2** — ``import adapters.x as xb`` + ``backend: xb.XBackend``:
          module-style alias. Caught at the import site (Tier 4 rule below)
          and also caught at the annotation site by ``_extract_annotation_refs``
          walking the ``Attribute`` chain to the root Name.
        - **Tier 3** — ``backend: "adapters.persistence.neo4j.x.XBackend"``
          (fully-qualified forward-ref string, no import at all). The string
          is parsed as an expression; the resulting ``Attribute`` chain has
          ``Name("adapters")`` at its root. The check treats the literal
          ``"adapters"`` lookup key as an implicit adapter reference so the
          import map can be empty and the violation still fires.
        - **Tier 4** — ``from adapters.x import XBackend as XB`` + ``backend: XB``:
          ImportFrom alias to a non-backend-suffix local name. Closed by the
          import-site rule (see ``_check_aliased_or_module_style_adapter_imports``):
          aliasing adapter imports in core/ — and module-style adapter imports
          — are banned outright, because the practice has no demonstrated
          positive purpose in this codebase (0 uses at rule introduction). The
          annotation-level suffix check is then sound on the only remaining
          form: ``from adapters.<...> import <Name>`` where ``<Name>`` is what
          gets the suffix check.

        Facade allowlist: KU / PS / LP / UserService and the per-domain sub-service
        packages are exempt — CLAUDE.md commits to "Facade IS the contract" for
        these. The thin/ISP services in the rest of core/ are not.

        Fix: switch the TYPE_CHECKING import from the adapter to its
        ``core/ports/*Operations`` protocol; switch the annotation to the protocol
        name. The composition-root injection is unchanged — the adapter satisfies
        the protocol structurally.

        Suppress: # skuel-lint: disable=SKUEL023 -- <reason>
        File-level: # skuel-lint: disable-file=SKUEL023 -- <reason>
        """
        if self._is_file_suppressed(content, "SKUEL023"):
            return

        # Facade allowlist: skip the entire file.
        rel_str = str(rel_path).replace("\\", "/")
        if any(rel_str.startswith(p) for p in self.SKUEL023_FACADE_ALLOWLIST_PREFIXES):
            return
        if rel_str in self.SKUEL023_FACADE_ALLOWLIST_FILES:
            return

        # Cheap pre-filter: nothing to flag if the file doesn't even mention adapters.
        if "adapters" not in content:
            return

        if tree is None:
            return

        # ── Import-site rule (Tier 4) ─────────────────────────────────────
        # Aliased ImportFrom (`from adapters... import X as Y`) and any
        # module-style import (`import adapters.x [as Y]`) are banned in core/
        # regardless of the local name. Both create bypass classes for the
        # annotation-level suffix check and have zero demonstrated positive
        # use in this codebase. The only permitted form is the plain
        # ``from adapters.<...> import <Name>``.
        self._flag_aliased_or_module_style_adapter_imports(rel_path, tree, lines)

        adapter_imports = self._collect_adapter_imports(tree)
        # Don't early-return when the import map is empty: Tier-3 fully-qualified
        # references (`backend: "adapters.x.XBackend"`) parse through the
        # forward-ref path and surface as a `("adapters", "XBackend")` ref pair
        # whose lookup key is the literal `"adapters"` sentinel — no import needed.

        # Walk every annotation site and gather (lineno, col, lookup_key, type_name).
        annotation_sites: list[tuple[int, int, str, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and node.annotation is not None:
                for lookup, type_name in self._extract_annotation_refs(node.annotation):
                    annotation_sites.append((node.lineno, node.col_offset, lookup, type_name))
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                # Positional, keyword-only, vararg, kwarg, and posonly args all
                # carry an optional .annotation; the return annotation lives on
                # the FunctionDef itself.
                all_args: list[ast.arg] = []
                all_args.extend(node.args.args)
                all_args.extend(node.args.kwonlyargs)
                all_args.extend(node.args.posonlyargs)
                if node.args.vararg is not None:
                    all_args.append(node.args.vararg)
                if node.args.kwarg is not None:
                    all_args.append(node.args.kwarg)
                for arg in all_args:
                    if arg.annotation is None:
                        continue
                    for lookup, type_name in self._extract_annotation_refs(arg.annotation):
                        annotation_sites.append((arg.lineno, arg.col_offset, lookup, type_name))
                if node.returns is not None:
                    for lookup, type_name in self._extract_annotation_refs(node.returns):
                        annotation_sites.append(
                            (node.returns.lineno, node.returns.col_offset, lookup, type_name)
                        )

        for lineno, col, lookup_key, type_name in annotation_sites:
            # Two resolution paths:
            # - Tier 1/2: lookup_key is a local import name (Name, or Attribute
            #   root for module-style aliases like `xb` in `xb.XBackend`)
            # - Tier 3: lookup_key is the literal sentinel `"adapters"` (root of
            #   a fully-qualified forward-ref like `"adapters.x.XBackend"`),
            #   which is an adapter reference regardless of any import.
            if lookup_key == "adapters":
                module = "adapters.*"
            elif lookup_key in adapter_imports:
                module = adapter_imports[lookup_key]
            else:
                continue
            # Suffix heuristic: only flag backend-shaped names (skip enums/configs).
            if not type_name.endswith(self.SKUEL023_BACKEND_SUFFIXES):
                continue
            line = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
            if self._is_line_suppressed(line, "SKUEL023"):
                continue

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=lineno,
                    column=col,
                    severity=Severity.ERROR,
                    rule_id="SKUEL023",
                    message=(
                        f"core/ module types annotation against concrete adapter "
                        f"'{type_name}' (from '{module}') — type against the "
                        f"core/ports protocol instead (ADR-044)"
                    ),
                    suggestion=(
                        f"Switch the TYPE_CHECKING import from '{module}' to the "
                        f"matching core/ports/*Operations protocol; annotate against "
                        f"the protocol name. Facades may keep the concrete typing "
                        f"— see CLAUDE.md '## Protocol-Based Architecture'."
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
                suppression_note = ""
                if self.result.suppressions:
                    # No violations => no SKUEL026 => every suppression is used.
                    suppression_note = f", {len(self.result.suppressions)} suppressions (all used)"
                print(
                    f"{Colors.GREEN}✅ No SKUEL violations found!{Colors.RESET} "
                    f"({self.result.files_scanned} files scanned in "
                    f"{self.result.scan_time_ms:.0f}ms{suppression_note})"
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

        # Suppression visibility — active exemptions are part of the picture
        if self.result.suppressions:
            used = sum(1 for s in self.result.suppressions if s.used)
            unused = len(self.result.suppressions) - used
            unused_note = f", {Colors.YELLOW}{unused} unused{Colors.RESET}" if unused else ""
            print(
                f"\n  {Colors.BOLD}Suppressions:{Colors.RESET} "
                f"{len(self.result.suppressions)} active ({used} used{unused_note})"
            )
            per_rule: dict[str, int] = {}
            for s in self.result.suppressions:
                if s.used:
                    per_rule[s.rule_id] = per_rule.get(s.rule_id, 0) + 1
            if per_rule:
                breakdown = ", ".join(f"{r}: {n}" for r, n in sorted(per_rule.items()))
                print(f"    {Colors.DIM}used by rule: {breakdown}{Colors.RESET}")

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
  %(prog)s --quiet --strict         # CI/gate mode (warnings fail)
        """,
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
            "suppressions": {
                "total": len(linter.result.suppressions),
                "used": sum(1 for s in linter.result.suppressions if s.used),
                "unused": sum(1 for s in linter.result.suppressions if not s.used),
                "comments": [
                    {
                        "file": str(s.file_path),
                        "line": s.line_number,
                        "rule_id": s.rule_id,
                        "file_level": s.file_level,
                        "used": s.used,
                    }
                    for s in linter.result.suppressions
                ],
            },
        }
        print(json.dumps(output, indent=2))
        # Same severity semantics as print_report — INFO never fails a run.
        if linter.result.has_critical or linter.result.has_error:
            exit_code = 2
        elif args.strict and linter.result.has_warning:
            exit_code = 1
        else:
            exit_code = 0
    else:
        show_context = not args.no_context
        exit_code = linter.print_report(
            strict=args.strict, quiet=args.quiet, show_context=show_context
        )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
