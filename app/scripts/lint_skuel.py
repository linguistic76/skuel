#!/usr/bin/env python3
"""
SKUEL Unified Linter
====================

Single linter enforcing all SKUEL architectural and code patterns.

RULES (by severity):

CRITICAL (blocks CI):
  SKUEL001: No APOC path procedures above the boundary (core/, routes, ui/)

ERROR (blocks CI):
  SKUEL002: Semantic type enums (not magic strings)
  SKUEL003: .is_err deprecated - use .is_error
  SKUEL020: FastHTML @rt handlers must annotate `request: Request` (not Any)
  SKUEL021: No raw Cypher above the boundary — core/, routes, ui/ (ADR-044)
  SKUEL022: core/ must not import adapters/ (dependency direction, ADR-044)
  SKUEL023: core/ must type backend against a core/ports protocol — not a concrete
            adapter class, and not Any / bare-unannotated, whether the class assigns
            self.backend or only declares it (ADR-044)
  SKUEL024: No cls= / **kwargs collision in FT helpers (latent TypeError crash)
  SKUEL025: No deleted Activity *UpdatePayload — use the frozen *UpdateIntent (ADR-066)
  SKUEL027: ui/ must not import adapters/ at runtime (ui renders; routes compose)
  SKUEL032: core/ must not import ui/ at runtime (ADR-058; SKUEL022's ui/ twin)

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
  SKUEL028: Result.fail(result.expect_error()) - use Result.fail(result) to propagate
  SKUEL030: Unregistered relationship type / node label in persistence Cypher
  SKUEL031: Stale pip references - SKUEL uses uv
  SKUEL033: Above-boundary docstring opens with, or hosts, Cypher — intent, not mechanism
            (SERVICE_DOCSTRING_STYLE.md § Where this applies)

INFO (informational, visibility only):
  SKUEL006: TODO/FIXME comments - track technical debt

OPT-IN AUDIT (excluded from default sweeps; run via --rule):
  SKUEL029: async def without await - sync body declared async
            (~205 sites as of 2026-07; opt-in until that debt shrinks, then promote)

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
import itertools
import re
import subprocess
import sys
import time
import tokenize
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import ClassVar

from core.utils.terminal_colors import Colors

# Shared with cypher_linter.py (CYP011) — one registry reader, one name scanner.
sys.path.insert(0, str(Path(__file__).parent))
from cypher_vocabulary import (  # type: ignore[import-not-found]
    INTERPOLATION_SENTINEL,
    Vocabulary,
    bare_alternation_parts,
    fstring_part_ids,
    leading_cypher_clause,
    load_vocabulary,
    render_fstring,
    scanning_fragment_at,
    unregistered_edge_names,
    unregistered_names,
)

# Shared with audit_raw_headers.py — one exclusion vocabulary, one walk helper.
from quality_discovery import is_excluded  # type: ignore[import-not-found]


class Severity(Enum):
    """Violation severity levels."""

    CRITICAL = "CRITICAL"  # Blocks CI, must fix
    ERROR = "ERROR"  # Blocks CI, must fix
    WARNING = "WARNING"  # Reported, doesn't block
    INFO = "INFO"  # Informational only


# Rule documentation for --explain
RULE_DOCS: dict[str, dict[str, str]] = {
    "SKUEL001": {
        "title": "No APOC Above the Hexagonal Boundary",
        "severity": "CRITICAL",
        "description": """APOC is banned everywhere above the ADR-044 boundary:
core/, any /services/ path, and the inbound/presentation layers (adapters/inbound/, ui/).
The fix is not "swap APOC for hand-written Cypher" — code above the boundary may not
author Cypher at all (SKUEL021), nor import adapters (SKUEL022). Move the query onto the
domain backend and call a named backend method from the service. The backend composes its
Cypher from the pure-Cypher build_* functions in adapters/persistence/neo4j/query/cypher/.

APOC is only allowed in adapter layer (adapters/persistence/*) for complex traversals.
Shares SKUEL021's gate — a CALL apoc... is Cypher, so the layers that may not author
Cypher may not author APOC either.

Matches the `apoc.` NAMESPACE, not a curated procedure list: apoc.convert.*,
apoc.coll.*, apoc.text.*, apoc.periodic.* and every future APOC addition are covered
without maintenance. apoc.meta.* is NOT an exception — that allowance is the Neo4j
server plugin allowlist (dbms_security_procedures_allowlist), exercised only by
tests/integration/test_apoc_canary.py, which this rule skips as a test file.""",
        "good": """# In a service: call the named method — no Cypher, no APOC, no execute_query().
# RelationshipOperationsMixin.get_prerequisites delegates to
# self.backend.prerequisite_traversal(), which composes pure Cypher below the
# boundary from the build_* functions in adapters/persistence/neo4j/query/cypher/.
prereqs = await self.get_prerequisites(uid, depth=3)

# No mixin method for your query yet? Add one to the DOMAIN BACKEND and call that —
# never inline Cypher in the service:
#     rows = await self.backend.prerequisite_traversal(uid, rel_types, depth=3)""",
        "bad": """# Don't use APOC above the boundary
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
instead of string-based Result.fail() for structured error handling. Catches both
string literals and str(...) wraps; propagate existing failures with
Result.fail(result), not Result.fail(str(result.error)).

Scope: core/services/ plus the inbound/presentation layers (adapters/inbound/,
ui/, api/).""",
        "good": """return Result.fail(Errors.not_found("Task", uid))
return Result.fail(Errors.validation("Invalid input", field="email"))
return Result.fail(result)  # Error propagation""",
        "bad": """return Result.fail("Task not found")  # String-based
return Result.fail(f"Error: {e}")  # String-based
return Result.fail(str(result.error))  # str() wrap - use Result.fail(result)""",
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
from core.utils.type_converters import get_enum_value
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
relationship type parameters. Single source of truth in relationship_names.py.
Scope: any /services/ path plus adapters/inbound/, ui/, and api/.

Suppress (boundary-shaped literals, e.g. an external system's status string
that collides with a relationship name):
  # skuel-lint: disable=SKUEL013 -- <reason>
File-level: # skuel-lint: disable-file=SKUEL013 -- <reason>""",
        "good": """from core.models.relationship_names import RelationshipName
await backend.add_relationship(uid1, RelationshipName.SUPPORTS_GOAL, uid2)""",
        "bad": """# Magic string - error prone
await backend.add_relationship(uid1, "SUPPORTS_GOAL", uid2)""",
    },
    "SKUEL014": {
        "title": "Use EntityType/NonKuDomain Enum",
        "severity": "WARNING",
        "description": """Use EntityType or NonKuDomain enum instead of magic strings for entity type
identification. Provides type safety and compile-time verification.
Scope: any /services/ path plus adapters/inbound/, ui/, and api/.

Suppress (boundary-shaped comparisons against a local taxonomy whose values
merely collide with entity-type names — form-state protocols, tab ids,
source-kind unions, display labels):
  # skuel-lint: disable=SKUEL014 -- <reason>
File-level: # skuel-lint: disable-file=SKUEL014 -- <reason>""",
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
        "title": "No Raw Cypher Above the Hexagonal Boundary",
        "severity": "ERROR",
        "description": """ADR-044 places the hexagonal boundary at UniversalNeo4jBackend /
adapters/persistence/neo4j/. All Cypher lives below that boundary; everything above it
orchestrates and calls backend methods — it does not author Cypher. (SKUEL001 only bans
APOC procedures; this rule covers raw Cypher generally, which was previously unguarded.)

Scope: core/, any /services/ path, and the inbound/presentation layers
(adapters/inbound/, ui/). Routes and renderers are above the boundary for exactly the
reason core/ is — a route composes services, it does not talk to the driver. The inbound
half mirrors SKUEL027, the ui/ sibling SKUEL022 grew for the import-direction rule.

The detector uses two anchors so prose/comments are not caught. Either a paren/sigil-anchored
clause anywhere in the literal (MATCH (, MERGE (, OPTIONAL MATCH (, CREATE (, UNWIND $,
CALL db.), or an UPPERCASE clause keyword at the HEAD of the literal followed by an operand
(RETURN, SHOW, PROFILE, EXPLAIN, DELETE, DETACH DELETE, SET, REMOVE, LOAD CSV, CALL, ...).
The head anchor covers statement families that have no paren or sigil to match on — a
`RETURN 1 as ping` health probe is Cypher; "... via ``DETACH DELETE`` on next failure" is prose.
Comment lines and docstrings are skipped.

All three of the head anchor's conditions — head position, UPPERCASE, and the
whitespace+operand requirement — are load-bearing, and the presentation layer is where
that is easiest to see. Measured across adapters/inbound/ + ui/: relax the anchor to be
case-insensitive and it yields ~80 hits, every one of them an English string that merely
opens with a clause word ("Create Invoice", "Delete", "Show All", "Set your goals",
"Remove this relationship?", methods=["DELETE"]) and not one of them Cypher. Keep all
three and it yields zero. TestSKUEL021::test_english_ui_strings_are_not_cypher pins that
corpus so a future relaxation cannot regress it silently.

Fix: relocate the query into an adapter backend (adapters/persistence/neo4j/) behind a
core/ports protocol. See the relationship / ps_engagement / ingestion / query backends for
the pattern. A composition-root liveness probe on a driver the root itself built is the
one shape that is NOT a port candidate — see services_bootstrap/_system_health.py.

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

Unconditional in core/: there is no facade allowlist. The shrinking debt register that
once parked KU/PS/LP, then UserService / UserContextBuilder / InsightStore, was emptied
and removed in July 2026 once every site it covered had a satisfiable core/ports
protocol. CLAUDE.md's "Facade IS the contract" governs the route→service boundary — a
facade being concrete to its *callers* never licensed a concrete ``self.backend``.

AST-based, fail-closed: walks both runtime AND TYPE_CHECKING imports of `adapters.*`,
then flags annotations (instance attribute, function parameter, class-body attribute)
that reference one of those imports. Forward references (string annotations) are
parsed. Subscripts (Optional[X], list[X]) recurse. ``Attribute`` chains walk to the
root Name so module-style aliases (`import adapters.x as xb` + `backend: xb.XBackend`)
are caught. Fully-qualified forward-ref strings (`backend: "adapters.x.XBackend"`,
no import) are caught via the same path — the parsed Attribute chain's root Name is
`adapters`, which the check treats as an implicit adapter reference.

**Annotation-strength sub-check (PR2b, 2026-08):** the checks above ask *which*
type an annotation names; this one asks whether it names anything. A ``core/``
class that ASSIGNS ``self.backend`` — or merely DECLARES a class-body
``backend:`` — must type it against a ``core/ports`` protocol. ``Any`` and
bare-unannotated defeat the boundary just as completely as a concrete adapter,
because either way every ``self.backend.<method>()`` call in the class goes
unchecked (the phantom-method class). Resolution order for an assigner:
``self.backend: X = ...`` → class-body ``backend: X`` → the matching ``__init__``
parameter's annotation → unannotated. Forward-ref strings are parsed, so
``"Any | None"`` is caught with bare ``Any``. TypeVars need no exemption
(``backend: B`` / ``backend: Ops`` is not ``Any``).

Declaration-only ``backend: Any`` — the mixin shape, where the host constructs
the object — triggers as of 2026-08 (PR-C). The host owning the object never made
the mixin's own calls checkable. A *dead* declaration (no ``self.backend`` call
anywhere in the class) flags too; there the fix is deleting the line. The trigger
landed only after all 27 such sites were clean, so it went green with zero
suppressions.

⚠ A **file-level** ``disable-file=SKUEL023`` silences BOTH sub-checks; line-level
suppressions are unaffected.

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
    "SKUEL028": {
        "title": "Propagate Errors with Result.fail(result), Not .expect_error()",
        "severity": "ERROR",
        "description": """`Result.fail(result)` is THE propagation path across type boundaries —
it re-wraps the failed result's error without unwrapping it. `.expect_error()` exists to
READ the error (logging, branching on category), not to feed it back into `Result.fail()`:
the round-trip is noise at best, and the sibling shape
`Errors.database(op, str(result.error))` flattens a typed error into a stringly Database
error, losing the original category (the shape #674 cleaned out of ingestion_tracker).

AST-based: flags any `Result.fail(...)` whose argument expression contains an
`.expect_error()` call — including conditional-expression and `str(...)`-wrapped forms.

Suppress: # skuel-lint: disable=SKUEL028 -- <reason>
File-level: # skuel-lint: disable-file=SKUEL028 -- <reason>""",
        "good": """if result.is_error:
    return Result.fail(result)  # propagates the typed error as-is

# Reading the error is what .expect_error() is FOR:
logger.warning(f"lookup failed: {result.expect_error().message}")""",
        "bad": """return Result.fail(result.expect_error())  # pointless unwrap/re-wrap
return Result.fail(
    other.expect_error() if other.is_error else Errors.not_found("Task", uid)
)""",
    },
    "SKUEL029": {
        "title": "async def Without await",
        "severity": "ERROR",
        "description": """CLAUDE.md's async/sync rule: async for I/O, sync for computation —
"if you need await inside the function, make it async def; otherwise use def." An
`async def` whose body never awaits (no `await`, `async for`, `async with`) wraps a
synchronous computation in a coroutine: every caller pays the event-loop round-trip and
the signature lies about the function doing I/O.

PROMOTED 2026-07-18: the reduction arc drove the 215-site baseline (2026-07-17) to 0
(PRs #679-#696), so the rule now runs in every default sweep as an ERROR. Genuine
interface-required async (Protocol/ABC overrides, awaited callbacks, facade delegation,
async context managers) keeps `async def` + an inline suppression.

Trivial bodies are exempt (docstring-only, `pass`, `...`, bare `raise`) — protocol
methods and abstract stubs are declarations, not offenders. Async generators (an own
`yield`) are exempt: `async def` is load-bearing there even without awaits. Awaits inside
NESTED functions don't count for the enclosing def (they belong to the nested one).""",
        "good": """async def fetch_task(self, uid: str) -> Result[Task]:
    return await self.backend.get_by_uid(uid)  # awaits — genuinely async

def score_insights(self, insights: list[Insight]) -> list[Insight]:
    return sorted(insights, key=self._priority)  # pure computation — sync def""",
        "bad": """async def score_insights(self, insights: list[Insight]) -> list[Insight]:
    # no await anywhere — a sync computation wearing an async signature
    return sorted(insights, key=self._priority)""",
    },
    "SKUEL030": {
        "title": "Persistence Cypher Vocabulary Must Be Registered",
        "severity": "WARNING",
        "description": """Every relationship type and node label written in persistence-layer
Cypher must be a registered member of `RelationshipName` / `NeoLabel`. Those enums
document themselves as THE single source of truth ("All valid Neo4j relationship type
names" / "All valid Neo4j node labels in SKUEL"); an edge or label the registry has
never heard of makes that claim false.

This is a VOCABULARY rule, not an interpolation-style rule. `[:OWNS]` written as a plain
literal is fine — SKUEL013's `[:{RelationshipName.OWNS}]` interpolation is NOT required
below the boundary. What is checked is only that the NAME exists in the registry.

Why it matters: Neo4j does not validate labels or relationship types. A typo'd
`(:KnowlegeDomain)` or `[:OWNS_ENTITY]` raises no error — the MATCH simply returns zero
rows, silently, forever. This rule is the only thing standing between a one-character
typo and a feature that quietly returns nothing in production.

Scope: `adapters/persistence/**` (.py string literals + .cypher templates). Docstrings
and other inert bare-string statements are skipped (same model as SKUEL001/SKUEL021), so
illustrative Cypher in prose never trips it. Dynamic names built by interpolation
(`[:HAS_{domain.upper()}]`) are unresolvable statically and are skipped.

`scripts/migrations/*.cypher` are EXCLUDED by design: a migration's whole job is to
reference the old vocabulary it is renaming away, so retired names there are correct.

Suppress (a label/edge genuinely owned by an external or infrastructural schema that the
domain registry should not absorb):
  # skuel-lint: disable=SKUEL030 -- <reason>
File-level: # skuel-lint: disable-file=SKUEL030 -- <reason>""",
        "good": """# Name exists in the registry — literal form is fine below the boundary
query = "MATCH (u:User)-[:OWNS]->(t:Task) RETURN t"

# Interpolated form is equally fine — the rule reads the NAME, not the syntax
query = f"MATCH (u:User)-[:{RelationshipName.OWNS}]->(t:Task) RETURN t\"""",
        "bad": """# 'OWNS_ENTITY' is not a RelationshipName member — silently matches nothing
query = "MATCH (u:User)-[:OWNS_ENTITY]->(t:Task) RETURN t"

# 'Taskk' is a typo — not a NeoLabel member, so the query matches zero rows
query = "MATCH (u:User)-[:OWNS]->(t:Taskk) RETURN t\"""",
    },
    "SKUEL031": {
        "title": "No Stale pip References",
        "severity": "WARNING",
        "description": """SKUEL's environments are lockfile-managed by uv end to end (uv sync /
uv add / uv.lock; the production image builds with `uv sync --frozen --no-dev`). A pip
invocation recommended in an error message, docstring, or script installs OUTSIDE the
lock — the resulting environment no longer matches uv.lock, which is the same class of
drift SKUEL016 closed for Poetry.

`uv pip install` is deliberately caught too: uv's pip interface also bypasses uv.lock.

Common replacements:
  pip install <pkg> → uv add <pkg>  (new dependency)
  pip install ...   → uv sync       (restoring a broken/missing environment)
  pip uninstall     → uv remove
  pip freeze        → uv export --format requirements.txt
  python -m pip ... → the uv equivalents above

NOT caught (correct as-is): the pip-audit tool (`pip-audit`, `pip_audit`,
`./dev audit-deps`) — a scanner, not an installer — and read-only `uv pip show/list`
introspection.""",
        "good": """# Restore the locked environment
raise RuntimeError("Neo4j driver not installed. Run: uv sync")

# Add a new dependency
uv add weasyprint""",
        "bad": """# Ad-hoc install outside uv.lock — env no longer matches the lockfile
raise RuntimeError("Neo4j driver not installed. Run: pip install neo4j")

# Same drift through uv's pip interface
uv pip install weasyprint""",
    },
    "SKUEL032": {
        "title": "core/ Must Not Import ui/",
        "severity": "ERROR",
        "description": """SKUEL022's presentation-side twin, and the last unguarded edge of the
ADR-044 hexagon. `core/` computes; `ui/` renders what a route hands it. A runtime
`import ui` inside `core/` inverts that — the domain layer reaching outward to
construct a display type.

ADR-058 § Placement already stated the rule in prose ("putting it in `core/` would
invert the `core → ui` import direction"), and CLAUDE.md repeats it for page contexts —
but nothing enforced it, and the class regrew: `fe3f7a9c2` relocated `core/ui/` to
`ui/` precisely to "remove presentation layer from core domain", yet
`core/services/lp_service.py` still reached back into `ui.ui_types` to CONSTRUCT
`ActivePathData` / `LearningStatsData`, formatting "12h total" and a difficulty label
inside a core service (fixed alongside this rule, #839).

AST-based, same mechanics as SKUEL022/SKUEL027: flags `import ui...` /
`from ui... import ...` at module scope OR inside a function. The function-local case
is the one that matters — BOTH founding violations were function-local, and a
module-level-only check would have reported zero.

TYPE_CHECKING-only imports are EXEMPT: they never execute. Note the limit that follows
from that — hoisting an import under `if TYPE_CHECKING:` satisfies this rule while a
`core/` signature still returns a `ui/` type. Green here means the runtime edge is gone,
not that the layering was fixed.

Scope is `core/` only. `adapters/inbound/` importing `ui/` is the composition a route
exists to do (the same carve-out SKUEL022 makes for `adapters/inbound/` → `adapters/`).

Fix: return domain values and let `ui/` build the display type. `core/ports/query_types`
row TypedDicts are the established carrier — 9 `ui/` modules already import them at
runtime (e.g. `ui/learning_loop/exercise_status.py` ← `ExerciseStatusRow`).

Suppress: # skuel-lint: disable=SKUEL032 -- <reason>
File-level: # skuel-lint: disable-file=SKUEL032 -- <reason>""",
        "good": """# Service returns domain values; ui/ owns every presentation decision
from core.ports.query_types import LpActivePathProgress

def calculate(self, paths) -> list[LpActivePathProgress]:
    return [LpActivePathProgress(uid=p.uid, estimated_hours=p.estimated_hours or 0.0, ...)]

# ui/pathways/components.py
def to_active_path_data(row: LpActivePathProgress) -> ActivePathData:
    return ActivePathData(estimated_completion=f"{int(row['estimated_hours'])}h total", ...)""",
        "bad": """# Core service constructing a UI dataclass and formatting display strings
from ui.ui_types import ActivePathData  # even under TYPE_CHECKING this signature is wrong

def calculate(self, paths) -> list[ActivePathData]:
    # ...or hidden inside a function (still a runtime core→ui dependency):
    from ui.ui_types import ActivePathData
    return [ActivePathData(estimated_completion=f"{int(p.estimated_hours or 0)}h total", ...)]""",
    },
    "SKUEL033": {
        "title": "Above-Boundary Docstrings State Intent, Not Cypher",
        "severity": "WARNING",
        "description": """`docs/patterns/SERVICE_DOCSTRING_STYLE.md` has said since 2026-05 that
docstrings in `core/services/`, `core/orchestrator/`, `core/ports/`, and `core/models/`
describe INTENT in domain language, with mechanism living in the backend docstring. Its
own § Relationship to SKUEL021 called the gap out: "SKUEL021 will not fail your build if
you describe Cypher in a service docstring", and floated "a *warning-level* lint over
[the above-boundary trees] that flags Cypher-shaped fragments in docstrings" as the way to
close it. CLAUDE.md repeated the rule and the same caveat ("isn't lint-enforced"). This is
that lint.

Scope is the style guide's OWN table (§ Where this applies), not a fresh judgement — the
four trees whose "Cypher in docstrings OK?" cell reads No. `core/utils/` is EXCLUDED
because the same table answers Yes for it (USAGE EXAMPLES blocks are the teaching subject
there), and SKUEL021's docstring already names that tree as the reason its carve-out
exists. Measured at introduction: the excluded tree has zero head-position hits, so the
exclusion costs no coverage — it prevents a rule from contradicting the document it
enforces.

TWO SHAPES, both reading the same three-part test SKUEL030/SKUEL021 use through
`cypher_vocabulary.leading_cypher_clause` (uppercase clause + whitespace + operand):

1. HEAD — the docstring OPENS with a clause, i.e. describes ITSELF in mechanism terms.
2. QUERY BLOCK — two or more non-head lines are each themselves Cypher, i.e. the
   docstring HOSTS a query (classically indented under a `Pattern:` heading). Added in
   #875 after the style guide had named this shape in writing as a violation the rule did
   not catch. All three sites it found had DRIFTED from the backend they documented — one
   advertised a whole `entry` node where the backend returns 14 flat scalars, another a
   `$email`-keyed MATCH the backend writes as a WHERE, a third a `shared_count: 1`
   literal where the generator does a two-step aggregation. That is the style guide's own
   stated reason for the rule ("drifts from the backend, no enforced link"), measured.

A docstring that merely NAMES a clause mid-sentence ("returns the rows its RETURN clause
produces") is prose describing a neighbour, and is deliberately NOT flagged under either
shape — the distinction is the one `CYPHER_LEADING_CLAUSES` already draws, and the one
that keeps this rule from firing on `query_types.py`'s row-shape references, where the
alias IS the contract because nothing statically links it to a TypedDict key.

The block scan reads PHYSICAL SOURCE LINES, never the AST string value, so its results ARE
source line numbers. An AST string is a DECODED value: `clean=True` also dedents (reporting
one line early on a docstring whose quotes sit alone), and even `clean=False` has already
turned `\n` escapes into real newlines, which invented lines that do not exist and reported
past the end of the file. Both are one mistake — a string value's offsets are not source
coordinates. A decoded-to-source map would have grown a classifier; source lines remove
the mapping instead.

A line opening with a BACKTICK is a reference, never query text, and is skipped before any
counting. Earlier revisions stripped the literal markers and then matched, which turned
every sanctioned ``RETURN <alias>`` into candidate query text — two references separated by
a blank line, then two adjacent, which the run requirement could not see. Two consecutive
RETURN clauses cannot be one Cypher query. Removing the strip costs zero coverage: no real
site wraps its query lines in markers, and a ```cypher fence puts its own markers on
separate lines.

Four review rounds landed on this one helper (#875), each fix pinned by a test shaped like
the bug that prompted it, each fixture accidentally avoiding the next shape. The guard is
now a PROPERTY — every report must land inside its docstring's span on a non-blank line —
because a case list cannot anticipate the shape nobody has hit yet.

Known and deliberate limit: the block threshold is TWO clause lines IN ONE contiguous run
of non-blank lines, so a ONE-line query embedded mid-docstring stays legal, as does a
query split across a blank line. Both halves are load-bearing. A wrapped English sentence
puts a clause word at a line head with an operand after it, and the one-line threshold
measured 8 sites with 5 of them legitimate. The run requirement is what keeps a docstring
documenting TWO non-adjacent aliases — legitimate under the style guide — from reaching
the threshold on two prose references (Codex P2, #875); a query survives it because its
own continuations (WHERE / AND / an indented field list) are non-blank, while prose
separates paragraphs with blank lines. The failure direction is a miss, which is the
fail-safe one here given SKUEL033 DOES fail `--strict`, and both limits are asserted by
tests so a genuine improvement turns them red instead of reading as a regression.

Fix: say what the operation MEANS and what it guarantees. Note that `MERGE` carries real
upsert semantics — flattening it to "Create" loses the contract, so state the idempotency
instead.

Suppress: # skuel-lint: disable=SKUEL033 -- <reason>
File-level: # skuel-lint: disable-file=SKUEL033 -- <reason>""",
        "good": '''async def record_view(self, user_uid, ku_uid, now, time_spent) -> Result[...]:
    """Record a user's visit to a KU; repeat visits accumulate count and time spent.

    One view record per user/KU pair, but NOT idempotent: every call increments
    the view count and adds to total time spent, so a retry double-counts
    engagement. The first-viewed timestamp is set once and survives later
    visits; the running view count comes back on the row.
    """''',
        "bad": '''async def record_view(self, user_uid, ku_uid, now, time_spent) -> Result[...]:
    """MERGE a VIEWED edge with timestamp and view-count tracking."""
    # The port now documents the backend's mechanism. It drifts the moment the
    # backend changes, and says nothing about what the caller is guaranteed.''',
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

    # Excluded directory names live in quality_discovery.EXCLUDED_DIR_NAMES —
    # the shared vocabulary (segment-matched; see that module for the
    # substring-bug history). Only the lint-specific scope stays here:

    # Root-relative path prefixes excluded as a unit.
    EXCLUDED_PATH_PREFIXES: ClassVar[tuple[str, ...]] = (
        "scripts/migrations",  # Migration scripts document old patterns
        "scripts/lint_skuel",  # Linter files document patterns they check
    )

    def _is_excluded(self, py_file: Path) -> bool:
        """True if the file lives under an excluded directory / path prefix."""
        rel = py_file.relative_to(self.root_dir)
        return is_excluded(rel, path_prefixes=self.EXCLUDED_PATH_PREFIXES)

    # Rules that honor `# skuel-lint: disable[-file]=SKUELXXX` — exactly the set
    # whose checkers call _is_line_suppressed/_is_file_suppressed. A suppression
    # comment naming any OTHER rule does nothing and is flagged by SKUEL026.
    # Guarded against drift by test_lint_skuel.py (source-scan of the call sites).
    SUPPRESSIBLE_RULES: ClassVar[frozenset[str]] = frozenset(
        {
            "SKUEL005",
            "SKUEL011",
            "SKUEL012",
            "SKUEL013",
            "SKUEL014",
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
            "SKUEL028",
            "SKUEL029",
            "SKUEL030",
            "SKUEL032",
            "SKUEL033",
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
            "SKUEL028",
            "SKUEL029",
            "SKUEL030",
            "SKUEL032",
            "SKUEL033",
        }
    )

    # Rules excluded from default sweeps — run only when named explicitly via
    # --rule. For audits whose hit count is far too large to block on; the staged
    # path is CYP003's: codify now, shrink the debt, then promote by removing the
    # rule from this set. Currently empty — SKUEL029 (the ~215-site 2026-07 audit)
    # was promoted to ERROR on 2026-07-18 after the reduction arc hit 0 (#679-#696).
    OPT_IN_RULES: ClassVar[frozenset[str]] = frozenset()

    # The inbound/presentation layers: HTTP routes and the renderers they hand FTs
    # to. Repo-relative path prefixes, matched against `rel_path.as_posix()`.
    #
    # Gates SKUEL007/013/014 (raw error / relationship / entity strings) and, since
    # the raw-Cypher scope extension, SKUEL001/021 as well — routes orchestrate and
    # UI renders; neither authors Cypher, exactly as core/ does not (ADR-044).
    #
    # A ClassVar rather than an inline literal so `_lint_file` and the scope mirror
    # in tests/unit/scripts/test_lint_skuel.py read the SAME tuple. They had already
    # drifted (the mirror carried a phantom "api/" prefix for a directory that does
    # not exist, so three tests asserted a scope production never had).
    INBOUND_LAYER_PREFIXES: ClassVar[tuple[str, ...]] = ("adapters/inbound/", "ui/")

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

    # SKUEL023 used to carry a facade allowlist — a parked-debt register that let
    # named `core/` paths keep a concrete-adapter annotation. It is GONE (SoC arc
    # PR 7, 2026-07-27): PR 6 removed the KU / PS / LP entries and PR 7 removed the
    # last three (`core/services/user/`, `core/services/insight/`,
    # `core/services/user_service.py` — InsightBackend + UserContextQueryExecutor).
    # Every site they covered now types against a core/ports protocol, each proven
    # satisfiable by the injected object with an `x: Protocol = concrete` MyPy probe.
    #
    # The mechanism was deleted with the last entry rather than left as two empty
    # tuples: an allowlist nobody is on is a branch that can never fire, and this
    # codebase has repeatedly found such guards to be vacuous. SKUEL023 is now
    # unconditional in `core/`, and "facade IS the contract" (CLAUDE.md) stays true
    # of the route→service boundary only — it never licensed a concrete
    # `self.backend`. Pinned by TestSKUEL023::test_no_core_path_is_allowlisted.

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
        self._comment_lines_memo: tuple[str, dict[int, str]] | None = None

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
            # Default sweep: opt-in audit rules only run when named explicitly.
            return rule_id not in self.OPT_IN_RULES
        return rule_id in self.rules_filter

    def _is_line_suppressed(self, line: str, rule_id: str) -> bool:
        """Check for inline suppression: # skuel-lint: disable=SKUEL011"""
        if self.ignore_suppressions:
            return False
        return f"# skuel-lint: disable={rule_id}" in line

    def _is_file_suppressed(self, content: str, rule_id: str) -> bool:
        """Check for file-level suppression: # skuel-lint: disable-file=SKUEL011

        Only a REAL `#` comment suppresses. A raw substring test cannot tell a
        comment from string content, and that was not hypothetical: this very
        file documents each rule's escape inside `RULE_DOCS`, which silently
        file-suppressed **18 rules on `scripts/lint_skuel.py`** — the linter was
        blind to most of itself. Proven with an injected `hasattr()`: SKUEL011
        reported nothing before this change and fires after it. Measured cost of
        closing it: zero new violations tree-wide, because the unmasked rules
        were already clean here (#868).

        The substring test stays as a cheap pre-filter, so a file that never
        mentions the escape is never tokenized. Untokenizable files now honour no
        file-level suppression — ruff reports the syntax error anyway, and for a
        suppression mechanism, failing closed is the safe direction.
        """
        if self.ignore_suppressions:
            return False
        marker = f"# skuel-lint: disable-file={rule_id}"
        if marker not in content:
            return False
        return any(marker in comment for comment in self._comment_lines(content).values())

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
                comments.extend(
                    SuppressionComment(
                        file_path=rel_path,
                        line_number=tok.start[0],
                        rule_id=match.group("rule"),
                        file_level=bool(match.group("filelevel")),
                        line_content=tok.line.strip(),
                    )
                    for match in self._SUPPRESSION_COMMENT_RE.finditer(tok.string)
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

            # The suppression-honored baseline: violations that SURVIVE with the
            # comment's strict-substring semantics applied. For rules the main
            # sweep ran, that IS `main_violations`. But an OPT_IN_RULES member
            # (e.g. SKUEL029) never ran in the main sweep, so a MALFORMED comment
            # there (loosely discovered but not strictly matched by
            # `_is_line_suppressed`) has no main violation to compare against and
            # would be wrongly credited as used. Reconstruct the honored baseline
            # for those rules with a suppression-respecting shadow lint so a
            # comment that does not actually suppress is still flagged (Codex P2
            # on #679; the `suppressible`-only guard sufficed only while SKUEL029
            # was non-suppressible — #678).
            opt_in_rules = sorted(
                {c.rule_id for c in comments if not self._should_run_rule(c.rule_id)}
            )
            honored_violations: list[Violation] = []
            if opt_in_rules:
                honored = SkuelLinter(
                    self.root_dir,
                    rules_filter=opt_in_rules,
                    ignore_suppressions=False,
                )
                honored._lint_file(file_path)
                honored_violations = honored.result.violations
            # `main_violations` is the global snapshot; `honored_violations` is
            # this file only. Both are filtered per-comment by `rel_str` below.
            baseline_violations = main_violations + honored_violations
            baseline_file_hits = main_file_hits | {
                (str(v.file_path), v.rule_id) for v in honored_violations
            }

            for comment in comments:
                rel_str = str(comment.file_path)
                fired = (
                    comment.rule_id in fired_rules
                    if comment.file_level
                    else self._fires_at_line(
                        shadow_violations, comment.rule_id, comment.line_number
                    )
                )
                # Only a SUPPRESSIBLE rule can earn "used" credit: for any other
                # rule the comment is inert by construction. Combined with the
                # honored baseline above, this flags both non-suppressible-rule
                # comments and malformed comments for opt-in suppressible rules.
                suppressible = comment.rule_id in self.SUPPRESSIBLE_RULES
                if comment.file_level:
                    comment.used = (
                        suppressible
                        and fired
                        and (rel_str, comment.rule_id) not in baseline_file_hits
                    )
                else:
                    hit_in_baseline = self._fires_at_line(
                        [v for v in baseline_violations if str(v.file_path) == rel_str],
                        comment.rule_id,
                        comment.line_number,
                    )
                    comment.used = suppressible and fired and not hit_in_baseline
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
            # all enforce the ADR-044 hexagonal boundary. Cypher of any kind is authored
            # only BELOW the boundary (adapters/persistence/neo4j/); everything above it
            # orchestrates and calls backend methods. For SKUEL001/021 "above" is now the
            # whole above-boundary surface: core/ (grew here once the last leaks in
            # core/utils — connection_fetcher, PR #75 — and core/models — search_request,
            # PR #78 — were relocated) PLUS the inbound/presentation layers, which are
            # above the boundary for the same reason core/ is: routes orchestrate and UI
            # renders; neither authors queries. Extending them there mirrors SKUEL027,
            # the ui/ sibling SKUEL022 grew for the import-direction rule.
            # Both checkers are AST-based and skip docstring / bare-string example
            # blocks, so the legitimate Cypher examples in core/utils docstrings
            # (processor_functions, neo4j_mapper, ...) do not trip them.
            # SKUEL022 stays core/-only — ui/ has its own sibling rule (SKUEL027), and
            # adapters/inbound/ importing adapters/ is the composition it exists to do.
            # Other service-only rules (SKUEL002/004/005) stay on is_service;
            # SKUEL007/013/014 share the inbound/presentation scope (see below).
            path_str = str(file_path)
            is_core = "/core/" in path_str and file_path.suffix == ".py"
            is_ui = "/ui/" in path_str and file_path.suffix == ".py"
            # Routes (adapters/inbound/) + renderers (ui/). Single-sourced as a class
            # constant so the test harness's scope mirror cannot drift from this gate.
            is_inbound_layer = rel_path.as_posix().startswith(self.INBOUND_LAYER_PREFIXES)
            # is_service is a strict subset of is_core today (no /services/ tree lives
            # outside core/), but keep it in the OR so a future non-core service dir
            # still gets the boundary rules.
            is_above_boundary = is_core or is_service or is_inbound_layer

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
            if self._should_run_rule("SKUEL031"):
                self._check_pip_references(file_path, rel_path, content, lines)
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
            if self._should_run_rule("SKUEL028") and not is_test:
                self._check_result_fail_expect_error(file_path, rel_path, content, lines, tree)

            # Graph-vocabulary rule: persistence Cypher may only name labels and
            # relationship types the enum registry knows (migrations excepted —
            # renaming away from a retired name requires naming it).
            is_persistence = "/adapters/persistence/" in path_str
            if (
                is_persistence
                and not is_test
                and not rel_path.as_posix().startswith(self.SKUEL030_EXCLUDED_PREFIXES)
                and self._should_run_rule("SKUEL030")
            ):
                self._check_cypher_vocabulary(file_path, rel_path, content, lines, tree)

            # INFO rules (always run for visibility)
            if self._should_run_rule("SKUEL006"):
                self._check_todo_comments(file_path, rel_path, content, lines)

            # Opt-in audit rules (OPT_IN_RULES — skipped by default sweeps)
            if self._should_run_rule("SKUEL029") and not is_test:
                self._check_async_without_await(file_path, rel_path, content, lines, tree)

            # Boundary rules (ADR-044): no APOC, no raw Cypher anywhere above the
            # boundary — core/, any /services/ path, and the inbound/presentation layers.
            if is_above_boundary and not is_test:
                if self._should_run_rule("SKUEL001"):
                    self._check_apoc_in_services(file_path, rel_path, content, lines, tree)
                if self._should_run_rule("SKUEL021"):
                    self._check_raw_cypher_in_services(file_path, rel_path, content, lines, tree)

            # Docstring-discipline rule: above the boundary a docstring states
            # intent. Scope is SERVICE_DOCSTRING_STYLE.md's own table, so this is
            # NOT `is_above_boundary` — core/utils/ sits above the boundary and is
            # explicitly allowed Cypher in docstrings by that same table.
            if (
                not is_test
                and rel_path.as_posix().startswith(self.DOCSTRING_INTENT_ONLY_TREES)
                and self._should_run_rule("SKUEL033")
            ):
                self._check_docstring_cypher(file_path, rel_path, content, lines, tree)

            # Import-direction rule (ADR-044): all of core/, not just services.
            if is_core and not is_test and self._should_run_rule("SKUEL022"):
                self._check_core_imports_adapter(file_path, rel_path, content, lines, tree)

            # Import-direction rule (SoC): ui/ renders what routes hand it — no
            # runtime adapters imports (SKUEL022's sibling for the ui/ layer).
            if is_ui and not is_test and self._should_run_rule("SKUEL027"):
                self._check_ui_imports_adapter(file_path, rel_path, content, lines, tree)

            # Import-direction rule (ADR-058): the other end of the same seam — core/
            # must not reach outward into ui/ either. adapters/inbound/ is deliberately
            # out of scope: composing UI is what a route is for.
            if is_core and not is_test and self._should_run_rule("SKUEL032"):
                self._check_core_imports_ui(file_path, rel_path, content, lines, tree)

            # Static type-direction rule (ADR-044): all of core/, not just services.
            # Closes the TYPE_CHECKING exemption gap left open by SKUEL022.
            if is_core and not is_test and self._should_run_rule("SKUEL023"):
                self._check_adapter_type_annotations(file_path, rel_path, content, lines, tree)
                # Second sub-check: annotation STRENGTH. Deliberately outside the
                # adapter check's `"adapters" not in content` pre-filter — a class
                # typing self.backend as Any usually never mentions adapters at all.
                self._check_backend_annotation_strength(file_path, rel_path, content, lines, tree)

            if is_service and not is_test:
                if self._should_run_rule("SKUEL002"):
                    self._check_semantic_type_strings(file_path, rel_path, content, lines, tree)
                if self._should_run_rule("SKUEL005"):
                    self._check_result_return_types(file_path, rel_path, content, lines, tree)

            # Inbound/presentation layers (routes, UI renderers) — raw
            # relationship-type / entity-type / error strings creep in here
            # too, so SKUEL007, SKUEL013, and SKUEL014 run on these layers in
            # addition to services. (is_inbound_layer is computed above, where the
            # boundary rules now share it.)
            if (is_service or is_inbound_layer) and not is_test:
                if self._should_run_rule("SKUEL007"):
                    self._check_string_result_fail(file_path, rel_path, content, lines)
                if self._should_run_rule("SKUEL013"):
                    self._check_relationship_name_strings(file_path, rel_path, content, lines, tree)
                if self._should_run_rule("SKUEL014"):
                    self._check_entity_type_strings(file_path, rel_path, content, lines, tree)

            if "/adapters/persistence/" in str(file_path) and self._should_run_rule("SKUEL008"):
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
        SKUEL001 [CRITICAL]: No APOC authored above the boundary.

        APOC is a Neo4j server-side procedure namespace invoked via ``CALL apoc...``
        inside Cypher — it belongs to the adapter, not to anything above the boundary
        (ADR-044); domain code uses pure Cypher (the ``query/cypher/`` ``build_*``
        functions). Shares SKUEL021's
        gate: core/, any /services/ path, and the inbound/presentation layers
        (``adapters/inbound/``, ``ui/``). Like SKUEL021, this is AST-based: APOC only
        matters when it appears in a *used* string literal (the Cypher a service would
        hand to the driver, incl. f-string parts). Inert bare-string statements —
        docstrings AND mid-body ``USAGE EXAMPLES`` blocks — are skipped by node
        identity, and comments (full-line AND inline) are not string nodes at all, so
        an APOC name in documentation/prose (e.g. explaining *why* APOC is banned)
        never trips this rule. CRITICAL and intentionally unsuppressable.

        **Namespace-matched, not a curated procedure list.** This used to enumerate
        nine prefixes, which meant anything outside them — ``apoc.convert.*``,
        ``apoc.coll.*``, ``apoc.text.*``, ``apoc.periodic.*``, and every APOC release's
        new additions — passed silently. The invariant is "no APOC above the boundary",
        so the matcher is the namespace itself; a selective list can only ever be a
        lagging approximation of it. Measured before the change: **zero** used string
        constants containing ``apoc.`` anywhere in scope, so nothing legitimate is
        caught by widening. Note ``apoc.meta.*`` is NOT an exception here — that
        allowance is the Neo4j *server* plugin allowlist
        (``dbms_security_procedures_allowlist``), exercised only by
        ``tests/integration/test_apoc_canary.py``, which this rule skips as a test file.

        **Invocation, not mention.** A bare namespace match would flag prose that
        merely *names* a procedure — ``logger.warning("apoc.convert.fromJsonMap is
        unavailable")`` — and this rule is CRITICAL and unsuppressable, so a false
        positive is unfixable except by rewording the string. Cypher only ever
        *invokes* APOC two ways: ``CALL apoc.x.y(...)`` (procedure) or bare
        ``apoc.x.y(...)`` in a RETURN/WHERE (function). Both are anchored — a
        preceding ``CALL`` or a following ``(`` — and requiring one of those is the
        same paren/sigil discipline that keeps SKUEL021's CYPHER_MARKERS off prose.

        Anchoring alone, though, misses a query assembled across constants:
        ``proc = "apoc.path.subgraphAll"`` then ``q = f"CALL {proc}(n)"``. The
        ``CALL`` and the ``(`` live in a different AST node than the name, so neither
        anchor is present on the node that carries it — and SKUEL021 does not cover
        it either, since ``CALL apoc.`` is not a CYPHER_MARKER. Hence the third form:
        a used string whose *entire* value is a dotted apoc path. Prose cannot take
        that shape (it has other words in it), so the discrimination holds in both
        directions. What remains genuinely undetectable by any string rule is a split
        that puts no apoc text in any single literal (``"CALL " + proc`` where ``proc``
        arrives from elsewhere) — out of reach of static string matching, not an
        oversight.
        """
        # 1: `CALL apoc.x.y` — procedure invocation; the paren may be interpolated,
        #    which is why the CALL branch exists rather than requiring a paren alone
        #    (f"CALL apoc.periodic.iterate{args}").
        # 2: `apoc.x.y(` — function invocation inside a RETURN/WHERE.
        # 3: the whole string IS the dotted path — a name assembled into a query
        #    elsewhere. Prose never fullmatches.
        # Each branch captures the path so the message names what it found.
        #
        # Case-SENSITIVE, and `\b` before CALL. Both are load-bearing against English
        # prose, and each kills a different case: without the uppercase requirement
        # "Please call apoc.convert.fromJsonMap during diagnosis" reads as a CALL
        # invocation, and without the word boundary the "call" inside "Recall
        # apoc.meta.stats" does. Neither is a false positive this rule can afford —
        # SKUEL001 is CRITICAL and unsuppressable, so the only remedy would be
        # rewording the string. Nothing real is lost: Cypher in this tree is written
        # uppercase (the same assumption cypher_vocabulary's clause list makes), and Neo4j
        # procedure names are themselves case-sensitive lowercase — `APOC.meta.data`
        # does not resolve on the server, so it is not a query worth catching.
        apoc_pattern = re.compile(
            r"\bCALL\s+(apoc(?:\.[A-Za-z_][A-Za-z0-9_]*)+)"
            r"|(\bapoc(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\s*\("
            r"|^\s*(apoc(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\s*$"
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
            apoc_match = apoc_pattern.search(node.value)
            if apoc_match is None:
                continue
            # Exactly one branch participates per match.
            apoc_proc = apoc_match.group(1) or apoc_match.group(2) or apoc_match.group(3)

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
                    suggestion=(
                        "Move this query onto the domain backend and call a named "
                        "backend method — code above the boundary may not author "
                        "Cypher or APOC"
                    ),
                    line_content=line.strip(),
                )
            )

    # --- SKUEL021 detection: two anchors, one rule -------------------------
    #
    # Anchor 1 (CYPHER_MARKERS) — substring, matched ANYWHERE in the literal.
    # Because position carries no signal here, each marker must earn its keep
    # from shape alone: a paren or sigil that essentially never follows the
    # keyword in prose. That constraint is also this anchor's ceiling — whole
    # statement families have no paren/sigil to hang a substring on, so for
    # years the rule was structurally blind to `RETURN`-only queries,
    # `SHOW INDEXES`, `PROFILE`/`EXPLAIN`, and statements led by `DELETE`,
    # `DETACH DELETE`, `SET`, `REMOVE` or `LOAD CSV`. A real leak sat inside
    # that blind spot: `session.run("RETURN 1 as ping")` lived in core/ with no
    # suppression comment and never once tripped the rule.
    #
    # This anchor is NOT comment-masked, and anchor 2 is — a deliberate
    # asymmetry, decided rather than inherited. Masking here would be defensible
    # on the merits (a commented-out `MATCH (` cannot execute, which is the
    # reasoning that already exempts docstrings), but it is the wrong trade for
    # THIS anchor. Anchor 2 matches at one position and masking only ever moves
    # that position past a planner hint; anchor 1 matches anywhere in every
    # string in core/ + adapters/inbound/ + ui/, so masking it can only ever
    # REMOVE detections — and a silent miss is the exact failure SKUEL021 exists
    # to prevent, on an ERROR rule guarding a hexagonal boundary. Over-reporting
    # a commented-out query is suppressible; under-reporting a live one is not
    # noticeable. Measured across all three trees when the anchors were
    # consolidated: masking would have changed zero verdicts (40 non-inert
    # constants there contain `//` or `/*`; none of their verdicts move), so
    # there is no live cost to leaving it unmasked and no live problem to fix.
    # `TestSKUEL021AnchorMaskingAsymmetry` pins it so it stays a decision.
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
    def _flatten_concat(root: ast.BinOp) -> tuple[list[ast.expr], list[ast.BinOp]]:
        """Spine operands and nested ``+`` BinOps of a concatenation chain.

        Walks only the ``Add`` spine — never into an operand's own expression —
        so a string literal buried in an interpolated call argument is not
        mistaken for part of the query being concatenated.
        """
        leaves: list[ast.expr] = []
        nested: list[ast.BinOp] = []

        def visit(node: ast.expr) -> None:
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                if node is not root:
                    nested.append(node)
                visit(node.left)
                visit(node.right)
            else:
                leaves.append(node)

        visit(root)
        return leaves, nested

    @staticmethod
    def _render_parts(leaves: list[ast.expr]) -> str:
        """Flatten concat operands to text, non-literals replaced by the sentinel."""
        return "".join(
            leaf.value
            if isinstance(leaf, ast.Constant) and isinstance(leaf.value, str)
            else render_fstring(leaf)
            if isinstance(leaf, ast.JoinedStr)
            else INTERPOLATION_SENTINEL
            for leaf in leaves
        )

    @staticmethod
    def _literal_pieces(leaves: list[ast.expr]) -> list[str]:
        """The literal texts inside ``leaves`` that the per-piece pass will see.

        Exactly the strings a whole-composite report would duplicate — no more.
        Deliberately does NOT descend into an operand's own expression: a literal
        passed as a call argument is its own detection, not a piece of the query
        being assembled around it.
        """
        pieces: list[str] = []
        for leaf in leaves:
            if isinstance(leaf, ast.Constant) and isinstance(leaf.value, str):
                pieces.append(leaf.value)
            elif isinstance(leaf, ast.JoinedStr):
                pieces.extend(
                    part.value
                    for part in leaf.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                )
        return pieces

    # Anchor 2 — clause keywords that may BEGIN a Cypher statement, matched only
    # at the head of the literal. Position is the signal, so it needs no
    # paren/sigil and the families anchor 1 cannot see stop being invisible.
    #
    # Both the clause list and the matcher live in `cypher_vocabulary`, applied
    # below through `leading_cypher_clause`. SKUEL030 and CYP011 ask the identical
    # question of `adapters/persistence/` and `.cypher` files; three rules, one
    # answer. See that module's `CYPHER_LEADING_CLAUSES` block for the full
    # reasoning — why head position + UPPERCASE + a following operand are each
    # load-bearing against prose, why lowercase Cypher is a deliberate known
    # limit, why the list is derived rather than pruned to "clauses that can carry
    # vocabulary", and why admin/security DDL (GRANT, REVOKE, DENY, ALTER) is
    # deliberately absent from it.
    #
    # This rule had its own copy of both for one release (#829). They had drifted
    # in five behaviours by the time they were merged, every one of them making
    # THIS copy the narrower gate. The lesson is in that module's block; what
    # belongs here is the consequence: there is no SKUEL021-specific clause list
    # to tune. A clause that should open a statement is added there, once.
    @classmethod
    def iter_authored_cypher(cls, tree: ast.AST, inert_ids: set[int]) -> list[tuple[ast.expr, str]]:
        """Every string in ``tree`` that reads as authored Cypher, as (node, marker).

        THE single traversal behind SKUEL021. ``tests/unit/test_core_utils_boundary.py``
        calls it too, so the boundary guard cannot drift from the rule it derives
        from — sharing only the predicate was not enough, and the two disagreed
        on f-strings until they shared the walk as well (Codex, PR #829).

        Composite strings are judged as a WHOLE, never as the fragments
        ``ast.walk`` hands out. ``f"RETURN {v}"`` and ``"RETURN " + v`` each tear
        into a leading piece with no operand left to anchor on, while
        ``f"cascade {mode} DETACH DELETE (...)"`` tears into a trailing piece
        that FALSELY leads with a clause keyword. Rendering the whole — with
        interpolations replaced by a sentinel — is right in both directions.
        """
        fstring_parts = fstring_part_ids(tree)
        composite_leaves: set[int] = set()
        nested_concats: set[int] = set()
        concat_roots: list[tuple[ast.BinOp, list[ast.expr]]] = []

        # Pass 1: resolve concatenation chains to their outermost root, so a
        # nested `+` never re-reports the text its root already covers.
        for node in ast.walk(tree):
            if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)):
                continue
            if id(node) in nested_concats:
                continue
            leaves, nested = cls._flatten_concat(node)
            if not any(
                (isinstance(leaf, ast.Constant) and isinstance(leaf.value, str))
                or isinstance(leaf, ast.JoinedStr)
                for leaf in leaves
            ):
                continue
            nested_concats.update(id(n) for n in nested)
            composite_leaves.update(
                id(leaf) for leaf in leaves if isinstance(leaf, ast.Constant | ast.JoinedStr)
            )
            concat_roots.append((node, leaves))

        found: list[tuple[ast.expr, str]] = []

        def take_whole(node: ast.expr, leaves: list[ast.expr]) -> None:
            # Skip only what the per-piece pass ACTUALLY reports — a piece that
            # matched — never merely "the rendered whole matched". Those differ:
            # `"MATCH " + "(n) RETURN n"` renders to a marker that no single
            # piece contains, because two literal operands concatenate with
            # nothing between them. (An f-string cannot hit this: the parser
            # never leaves two adjacent Constant parts, so its pieces really are
            # sentinel-separated. Concatenation broke that invariant when it was
            # added — Codex, PR #829.)
            pieces = cls._literal_pieces(leaves)
            if any(m in piece for piece in pieces for m in cls.CYPHER_MARKERS):
                return
            rendered = cls._render_parts(leaves)
            marker = next(
                (m for m in cls.CYPHER_MARKERS if m in rendered), None
            ) or leading_cypher_clause(rendered)
            if marker is not None:
                found.append((node, marker))

        for root, leaves in concat_roots:
            take_whole(root, leaves)

        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                if id(node) not in composite_leaves:
                    take_whole(node, [node])
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) in inert_ids:
                    continue
                # Anywhere-markers keep their per-piece granularity (and line
                # numbers); the head anchor only ever runs on a whole.
                marker = next((m for m in cls.CYPHER_MARKERS if m in node.value), None)
                if marker is None and id(node) not in fstring_parts | composite_leaves:
                    marker = leading_cypher_clause(node.value)
                if marker is not None:
                    found.append((node, marker))

        return found

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

    def _comment_lines(self, content: str) -> dict[int, str]:
        """1-based line number -> the REAL `#` comment token text on that line.

        Needed wherever a suppression is honoured over a multi-line span. A raw
        line scan cannot tell a comment from string content, so a docstring whose
        own text contains `# skuel-lint: disable=SKUEL033` would suppress the very
        rule reading it — and SKUEL026 would not report the bypass either, since
        it correctly audits only real comment tokens (Codex P2, #868). tokenize is
        the same mechanism `_find_suppression_comments` already trusts for that
        reason; this variant takes content in hand rather than a path, so
        synthetic test input goes down the identical route as a real file.

        Empty on untokenizable input: ruff reports the syntax error, and failing
        open here would resurrect the bypass this exists to close.
        """
        if self._comment_lines_memo is not None and self._comment_lines_memo[0] is content:
            return self._comment_lines_memo[1]
        found: dict[int, str] = {}
        if "#" in content:
            try:
                for tok in tokenize.generate_tokens(io.StringIO(content).readline):
                    if tok.type == tokenize.COMMENT:
                        found[tok.start[0]] = tok.string
            except tokenize.TokenError, IndentationError, SyntaxError:
                found = {}
        self._comment_lines_memo = (content, found)
        return found

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
        boundary — all of ``core/`` plus the inbound/presentation layers
        (``adapters/inbound/``, ``ui/``) — orchestrates and calls backend methods;
        it does not author Cypher. (Note SKUEL001 only bans APOC — this rule covers
        raw Cypher generally.)

        AST-based, not a line scan: Cypher only matters when it is *used* (assigned,
        passed, returned, interpolated). String literals that are inert bare
        expression statements — docstrings AND mid-body ``USAGE EXAMPLES`` blocks —
        legitimately quote Cypher and are skipped by node identity. f-string literal
        parts are scanned (a marker interpolated into a query is still authored
        Cypher). This keeps the rule quiet on the docstring Cypher examples that live
        throughout ``core/utils`` while still catching real leaks anywhere in core/.

        Two anchors decide whether a literal is Cypher: a paren/sigil-anchored
        marker anywhere in the string (``CYPHER_MARKERS``, this class), OR a clause
        keyword at its head (``cypher_vocabulary.leading_cypher_clause``, shared
        with SKUEL030 and CYP011). See the ``CYPHER_MARKERS`` block for the full
        reasoning, including why only one of the two anchors masks comments. The
        head anchor is what covers the statement families a substring test cannot
        see — ``RETURN``-only queries, ``SHOW INDEXES``, ``PROFILE``/``EXPLAIN``,
        and ``DELETE`` / ``DETACH DELETE`` / ``SET`` / ``REMOVE`` / ``LOAD CSV``
        statements — without lighting up prose that merely names a clause.

        Relocate the query into an adapter backend behind a ``core/ports``
        protocol (see the connection-fetch / relationship / ingestion backends
        for the pattern).

        Suppress: # skuel-lint: disable=SKUEL021 -- <reason>
        File-level: # skuel-lint: disable-file=SKUEL021 -- <reason>
        """
        if self._is_file_suppressed(content, "SKUEL021"):
            return

        if tree is None:
            return

        reported_lines: set[int] = set()

        for node, marker in self.iter_authored_cypher(tree, self._inert_ids_for(tree)):
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

    # SKUEL033: the trees whose "Cypher in docstrings OK?" cell reads **No** in
    # SERVICE_DOCSTRING_STYLE.md § Where this applies. Transcribed from that
    # table rather than chosen here, so the rule cannot outgrow the document it
    # enforces — and `core/utils/`, whose cell reads **Yes**, is absent for the
    # same reason. That exclusion is not a concession: measured at introduction,
    # `core/utils/` had ZERO head-position hits (its docstring Cypher all sits in
    # `query='MATCH ...'` example lines), so excluding it cost no coverage while
    # keeping the rule from contradicting its own source of truth.
    DOCSTRING_INTENT_ONLY_TREES: ClassVar[tuple[str, ...]] = (
        "core/services/",
        "core/orchestrator/",
        "core/ports/",
        "core/models/",
    )

    # SKUEL033 shape 2: how many clause-leading lines make a docstring host a
    # QUERY rather than reference a clause. Two, measured — not chosen.
    #
    # Scored over the four in-scope trees at introduction (#875):
    #
    #   any clause word anywhere  54 docstrings — 20 of them "AI services are
    #                                OPTIONAL", 1 "Export as CSV". Unusable.
    #   >=1 clause-leading line    8 docstrings — 5 legitimate: the four
    #                                `query_types.py` row-shape refs whose
    #                                ``RETURN <alias>`` opens a line inside
    #                                backticks, plus one WRAPPED SENTENCE
    #                                ("the MEGA-QUERY's OPTIONAL\nMATCH
    #                                collects ..."). 62% precision.
    #   >=2 clause-leading lines   3 docstrings — all three real query blocks,
    #                                zero false positives.
    #
    # A wrapped sentence is why 1 cannot be the threshold: prose breaking across
    # a line boundary puts a clause word at a line head with an operand after it,
    # and no amount of tuning distinguishes that from a one-line query. Requiring
    # a SECOND such line asks for the thing a query has and a sentence does not —
    # more than one clause.
    #
    # The two must also be in the SAME contiguous run of non-blank lines, and
    # that is not a refinement — it is the difference between a sound predicate
    # and one that only happens to score well on today's corpus (Codex P2, #875).
    # A docstring documenting TWO non-adjacent aliases — entirely legitimate
    # under the style guide, and the shape `query_types.py` is one blank line away
    # from — would otherwise reach the threshold on two prose references and be
    # flagged. That matters more than a WARNING usually would, because SKUEL033
    # DOES fail `--strict`: a false positive here blocks CI and the only escapes
    # are deleting sanctioned documentation or suppressing the rule.
    #
    # A query survives this test because its own continuation lines (WHERE / AND /
    # ORDER BY / an indented field list) are non-blank, so the whole statement is
    # one run; prose separates its paragraphs with blank lines. Verified on all
    # three real sites: none has adjacent clause lines, and every one is a single
    # non-blank run.
    #
    # The threshold's failure direction is a MISS: a one-line query embedded
    # mid-docstring stays legal, as does a query split across a blank line. That
    # is deliberate and asserted by `test_single_clause_line_is_not_flagged` — for
    # a rule whose job is to name a documented gap, a quiet miss is recoverable
    # and a false failure trains authors to suppress. Raising coverage here means
    # finding a signal a wrapped sentence cannot have, NOT lowering the threshold.
    DOCSTRING_QUERY_BLOCK_MIN_CLAUSE_LINES: ClassVar[int] = 2

    # Delimiters and string prefixes to shave off a PHYSICAL source line before
    # matching. Only the outermost pair can appear on a docstring's own lines.
    _DOCSTRING_EDGE_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"""^(?:[rRbBuUfF]{0,2})(?:\"\"\"|''')|(?:\"\"\"|''')$"""
    )

    def _docstring_query_lines(self, lines: list[str], start: int, end: int) -> list[int]:
        """ABSOLUTE source line numbers, inside a docstring, that are Cypher.

        Reads PHYSICAL SOURCE LINES, never the AST string value, and that is the
        third and last subtraction this helper needed (Codex P2 ×3, #875). An AST
        string is a DECODED value: `clean=False` stops the dedenting, but `\\n`
        escapes have already become real newlines, so `splitlines()` invents
        physical lines that do not exist. A one-source-line docstring written with
        `\\n` escapes produced four "lines" and reported the violation PAST THE
        END OF THE FILE with empty diagnostic context. Its predecessor bug was the
        cleaned-vs-raw off-by-one. Both are the same mistake — treating a string
        value's offsets as source coordinates.

        Source lines ARE the coordinates, so there is no mapping left to get
        wrong. The alternative on offer was a decoded-to-source line map; that
        grows a classifier, which is the shape #868 watched generate a new finding
        every round. Three rounds on one helper is the documented stop signal, and
        what converged there was narrowing the claim and writing the limit down.

        The claim is now exactly: **two or more physical source lines, inside one
        docstring, each of which is itself a Cypher clause.** Consequences, all
        deliberate, all fail-safe, all asserted by tests:

        * a docstring squeezed onto ONE physical line is never a query block, no
          matter what its decoded value looks like;
        * a line opening with a BACKTICK is a reference, never query text — this
          killed rounds 1 and 2 (a sanctioned ``RETURN <alias>`` combining with a
          second one, separated then adjacent) and costs no coverage, since real
          embedded queries carry no per-line markers and a ```cypher fence keeps
          its markers on their own lines;
        * the first NON-BLANK line is the summary, which the head check owns.

        `leading_cypher_clause` stays the only matcher — the same anchor the head
        check, SKUEL021 and SKUEL030 read, so there is no further copy to drift.
        """
        found: list[int] = []
        seen_head = False
        for lineno in range(max(start, 1), min(end, len(lines)) + 1):
            text = self._DOCSTRING_EDGE_RE.sub("", lines[lineno - 1].strip()).strip()
            if not seen_head:
                # The first NON-BLANK line is the summary. Skipping by position
                # instead would skip nothing when the opening quotes sit alone on
                # their line, and would double-report that docstring's summary.
                if text:
                    seen_head = True
                continue
            if text.startswith("`"):
                continue  # a literal reference, or a fence marker — never query text
            if leading_cypher_clause(text) is not None:
                found.append(lineno)
        return found

    def _query_block_run(self, lines: list[str], candidates: list[int]) -> list[int]:
        """The first run of >=N ``candidates`` sharing one contiguous non-blank span.

        Returns the RUN, not a bool, so the violation anchors to the query's own
        first line even when a lone prose reference sits above it — reporting
        `candidates[0]` would point at the reference and send the reader to the one
        line that is allowed to stay.
        """
        if len(candidates) < self.DOCSTRING_QUERY_BLOCK_MIN_CLAUSE_LINES:
            return []
        run = [candidates[0]]
        for previous, current in itertools.pairwise(candidates):
            # Contiguous run = no BLANK line between them. Intervening non-blank
            # lines are the query's own continuations (WHERE / AND / field list).
            separated = any(
                not lines[gap - 1].strip()
                for gap in range(previous + 1, current)
                if 0 < gap <= len(lines)
            )
            run = [current] if separated else [*run, current]
            if len(run) >= self.DOCSTRING_QUERY_BLOCK_MIN_CLAUSE_LINES:
                return run
        return []

    def _check_docstring_cypher(
        self,
        file_path: Path,
        rel_path: Path,
        content: str,
        lines: list[str],
        tree: ast.Module | None,
    ) -> None:
        """
        SKUEL033 [WARNING]: an above-boundary docstring states intent, not Cypher.

        The mechanised half of SERVICE_DOCSTRING_STYLE.md § Where this applies.
        That doc, and CLAUDE.md after it, both stated the rule and then recorded
        that nothing enforced it — the doc even specified the shape ("a
        *warning-level* lint ... that flags Cypher-shaped fragments in
        docstrings"). Left to convention it rotted: 14 docstrings across 6 files
        opened with `MERGE`/`DELETE`/`CREATE` naming the edge their backend
        writes, and one of them had quietly become a lint fixture.

        TWO SHAPES, one standard, both reading the shared
        `cypher_vocabulary.leading_cypher_clause` — the same anchor SKUEL021 and
        SKUEL030 read, so there is no fourth copy to drift:

        1. HEAD — the docstring OPENS with a clause. It is describing itself in
           mechanism terms, which is what the style guide forbids.
        2. QUERY BLOCK — `DOCSTRING_QUERY_BLOCK_MIN_CLAUSE_LINES` or more
           non-head lines are each themselves Cypher, i.e. the docstring HOSTS a
           query (classically indented under a `Pattern:` heading). The style
           guide named this shape in writing as "still a violation of this
           document that the rule does not catch"; #875 closed it after
           measuring, and all three sites it found had DRIFTED from the backend
           they claimed to document — one advertised a whole `entry` node where
           the backend returns 14 flat scalars.

        A docstring that merely NAMES a clause mid-sentence stays legal under
        both shapes: it is prose about a neighbour, not documentation of itself.
        That is the distinction `CYPHER_LEADING_CLAUSES` already draws, and it is
        what keeps this rule off `query_types.py`'s row-shape references — where
        the ``RETURN <alias>`` IS the contract, because nothing statically links
        a Cypher alias to a TypedDict key.

        Suppress: # skuel-lint: disable=SKUEL033 -- <reason>
        File-level: # skuel-lint: disable-file=SKUEL033 -- <reason>
        """
        if tree is None or self._is_file_suppressed(content, "SKUEL033"):
            return

        docstring_owners = (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef, ast.Module)

        for node in ast.walk(tree):
            if not isinstance(node, docstring_owners):
                continue
            doc = (ast.get_docstring(node) or "").strip()
            if not doc:
                continue

            clause = leading_cypher_clause(doc)

            # Report on the docstring's own first line, not the def's — that is
            # where a reader looks. But HONOUR a suppression anywhere in the
            # docstring's line span: for a multi-line docstring the only place a
            # real comment can go is after the closing quotes, since an interior
            # `#` is just more string content. Checking the opening line alone
            # made the documented escape unusable on exactly the docstrings most
            # likely to need it, and left SKUEL026 reporting the closing-line
            # comment as suppressing nothing (Codex P2, #868).
            body = getattr(node, "body", None)
            expr = body[0] if body else node
            start = getattr(expr, "lineno", 1)
            end = getattr(expr, "end_lineno", None) or start

            # The block half reads PHYSICAL SOURCE LINES over the docstring's own
            # span, so its results are already source line numbers — an AST string
            # value's offsets are not source coordinates (see
            # `_docstring_query_lines`).
            block = self._query_block_run(lines, self._docstring_query_lines(lines, start, end))
            if clause is None and not block:
                continue
            # Only a REAL comment token suppresses. Every line in the span except
            # the closing one is string content, so scanning raw lines would let a
            # docstring suppress itself by quoting the escape.
            comments = self._comment_lines(content)
            if any(
                self._is_line_suppressed(comments[lineno], "SKUEL033")
                for lineno in range(start, end + 1)
                if lineno in comments
            ):
                continue

            # HEAD outranks QUERY BLOCK: a docstring that both opens with a clause
            # and hosts a block is one violation with one fix, and the head is the
            # line a reader lands on. One report per docstring either way.
            if clause is not None:
                report_line = start
                message = (
                    f"Docstring opens with the Cypher clause '{clause.strip()}' — "
                    "above the boundary a docstring states intent, not mechanism"
                )
            else:
                # Point at the query's FIRST line, not the docstring's — the block
                # is what has to go, and it can sit far below the summary. Already
                # a source line number; no offset arithmetic left to get wrong.
                report_line = block[0]
                message = (
                    f"Docstring hosts a Cypher query ({len(block)} clause lines) — "
                    "above the boundary a docstring states intent, not mechanism"
                )

            line = lines[report_line - 1] if 0 < report_line <= len(lines) else ""

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=report_line,
                    column=getattr(expr, "col_offset", 0),
                    severity=Severity.WARNING,
                    rule_id="SKUEL033",
                    message=message,
                    suggestion=(
                        "Say what the operation means and guarantees; leave the query to "
                        "the backend docstring (docs/patterns/SERVICE_DOCSTRING_STYLE.md). "
                        "MERGE is an upsert — state the idempotency, don't flatten to 'Create'"
                    ),
                    line_content=line.strip(),
                    # So SKUEL026's audit knows a closing-line comment is USED.
                    suppression_span=(start, end),
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

        Scope: services + inbound/presentation layers (adapters/inbound/, ui/,
        api/) — see the shared widened gate in _lint_file.

        Two string shapes: a literal first argument (``Result.fail("...")`` /
        f-string) and a ``str(...)`` wrap (``Result.fail(str(e))`` /
        ``Result.fail(str(result.error))``). The latter is how real violations
        dodged the literal-only pattern — error propagation should be
        ``Result.fail(result)``, exception paths an Errors factory call.
        """
        pattern = r'Result\.fail\s*\(\s*(?:f?["\']|str\s*\()'

        for match in re.finditer(pattern, content):
            line_num = content[: match.start()].count("\n") + 1
            line = lines[line_num - 1]

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=0,
                    severity=Severity.WARNING,
                    rule_id="SKUEL007",
                    message="String-based Result.fail() - use Errors factory",
                    suggestion=(
                        "Use Errors.validation(), Errors.not_found(), etc.; "
                        "propagate failures with Result.fail(result)"
                    ),
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
    #
    # Read straight from `RelationshipName` in `core/models/relationship_names.py`
    # by AST-parsing the declaration site — no import, so the linter still carries
    # no runtime dependency on `core/`. This replaced a 170-entry hand-mirror that
    # had already drifted once to a ~30-value subset with four stale names,
    # silently under-enforcing the rule for months. A parser cannot drift.
    @property
    def RELATIONSHIP_NAMES(self) -> frozenset[str]:  # noqa: N802  (was a ClassVar constant)
        """Every registered RelationshipName value."""
        return load_vocabulary().relationships

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

        Suppressible: boundary-shaped literals (e.g. mapping an EXTERNAL system's
        status/type string that merely collides with a relationship name) are
        legitimate — annotate with `# skuel-lint: disable=SKUEL013 -- <reason>`.
        """
        if tree is None:
            return
        if self._is_file_suppressed(content, "SKUEL013"):
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
            if self._is_line_suppressed(line, "SKUEL013"):
                continue
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
    #
    # Canonical source of truth: `EntityType` + `NonKuDomain` in
    # `core/models/enums/` — ENTITY_TYPE_ENUM_VALUES is the FULL set of both
    # enums' values. Mirrored here because the linter deliberately has no
    # runtime dependency on `core/`. Keep in sync — `TestEntityTypeCatalogDrift`
    # in `test_lint_skuel.py` pins the contract (the catalog previously drifted
    # to 22 of 29 values: all six *_template types, user_entry, and the
    # group/calendar/learning NonKuDomain values were missing).
    ENTITY_TYPE_ENUM_VALUES: ClassVar[frozenset[str]] = frozenset(
        {
            # EntityType — Activity domains
            "task",
            "habit",
            "goal",
            "event",
            "choice",
            "principle",
            # EntityType — Activity templates
            "task_template",
            "habit_template",
            "goal_template",
            "event_template",
            "choice_template",
            "principle_template",
            # EntityType — Curriculum
            "ku",
            "path_step",
            "learning_path",
            "exercise",
            # EntityType — Forms
            "form_template",
            "form_submission",
            # EntityType — Learning loop
            "user_entry",
            "entry_report",
            "activity_report",
            "interaction",
            # EntityType — Other
            "revised_exercise",
            "life_path",
            "resource",
            # NonKuDomain
            "finance",
            "group",
            "calendar",
            "learning",
        }
    )

    # Stale identifiers from removed/renamed entity types. Comparing against one
    # of these is doubly wrong (magic string AND a type that no longer exists) —
    # kept in the catalog so the stale comparison is surfaced, not silently dead.
    # Hand-curated: not pinned to any enum, prune when a name stops appearing.
    LEGACY_ENTITY_TYPE_ALIASES: ClassVar[frozenset[str]] = frozenset(
        {
            "article",
            "lesson",
            "submission",
            "exercise_submission",
            "submission_report",
            "journal",
            "je_input",
            "je_output",
        }
    )

    ENTITY_TYPE_STRINGS: ClassVar[frozenset[str]] = (
        ENTITY_TYPE_ENUM_VALUES | LEGACY_ENTITY_TYPE_ALIASES
    )

    @staticmethod
    def _mentions_enum_name(node: ast.AST) -> bool:
        """True if any Name inside ``node`` is EntityType / NonKuDomain / Domain —
        the comparison already routes through an enum (e.g. ``EntityType.TASK.value
        == raw``), so a string operand is not a magic-string violation. Domain is
        included because its values overlap the catalog ("learning", "finance",
        ...) — a comparison routed through Domain is enum-safe, just a different
        taxonomy than this rule's suggestion."""
        return any(
            isinstance(n, ast.Name) and n.id in ("EntityType", "NonKuDomain", "Domain")
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

        Suppressible: boundary-shaped comparisons against a LOCAL taxonomy whose
        values merely collide with entity-type names (form-state protocols, tab
        ids, source-kind unions, display labels) are legitimate — annotate with
        `# skuel-lint: disable=SKUEL014 -- <reason>`.
        """
        if tree is None:
            return
        if self._is_file_suppressed(content, "SKUEL014"):
            return

        reported_lines: set[int] = set()

        def flag(line_num: int, col: int, value: str) -> None:
            if line_num in reported_lines:
                return
            reported_lines.add(line_num)
            line = lines[line_num - 1] if 0 < line_num <= len(lines) else ""
            if self._is_line_suppressed(line, "SKUEL014"):
                return
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
                        # Single-line docstring or line with string literal —
                        # skip this line entirely if it looks like a docstring
                        if count >= 2 and stripped.startswith(delim):
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

    # SKUEL031: precompiled like SKUEL016 — same every-file scan, same reason.
    # `pip\s+` (whitespace required) keeps the pip-audit tool name (`pip-audit`,
    # `pip_audit`) out of scope; `uv pip install` is caught on purpose (it
    # bypasses uv.lock just like bare pip).
    PIP_PATTERNS: ClassVar[tuple[tuple[re.Pattern[str], str, str], ...]] = (
        (
            re.compile(r"\bpip3?\s+install\b", re.IGNORECASE),
            "pip install",
            "uv add <pkg> (new dep) / uv sync (restore env)",
        ),
        (re.compile(r"\bpip3?\s+uninstall\b", re.IGNORECASE), "pip uninstall", "uv remove"),
        (
            re.compile(r"\bpip3?\s+freeze\b", re.IGNORECASE),
            "pip freeze",
            "uv export --format requirements.txt",
        ),
        (
            re.compile(r"\bpython3?\s+-m\s+pip\b", re.IGNORECASE),
            "python -m pip",
            "the uv equivalent (uv add / uv sync / uv remove)",
        ),
    )

    def _check_pip_references(
        self, file_path: Path, rel_path: Path, content: str, lines: list[str]
    ) -> None:
        """
        SKUEL031 [WARNING]: No stale pip references — SKUEL uses uv.

        Catches: pip/pip3 install|uninstall|freeze, python -m pip — including
        through uv's pip interface (`uv pip install`), which bypasses uv.lock.

        Exceptions: Migration scripts, this linter's rule docs.
        """
        file_str = str(file_path)

        # Skip files where pip references are historical/expected
        if any(
            skip in file_str
            for skip in [
                "/migrations/",
                "lint_skuel.py",  # This linter documents the pattern
                "detect_library_changes.py",  # May reference installer tooling
            ]
        ):
            return

        # Cheap pre-filter: every pattern contains the literal "pip".
        if "pip" not in content.lower():
            return

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Skip comments that explain the migration itself
            if stripped.startswith("#") and (
                "migrat" in stripped.lower() or "was" in stripped.lower()
            ):
                continue

            for pattern, match_text, replacement in self.PIP_PATTERNS:
                match = pattern.search(line)
                if match:
                    self.result.violations.append(
                        Violation(
                            file_path=rel_path,
                            line_number=line_num,
                            column=match.start(),
                            severity=Severity.WARNING,
                            rule_id="SKUEL031",
                            message=f"Stale pip reference '{match_text}' — SKUEL uses uv",
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
        if isinstance(target, ast.Attribute) and target.attr in SkuelLinter.ROUTE_DECORATOR_ATTRS:
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
            elif isinstance(
                n, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr, ast.For, ast.AsyncFor)
            ):
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
                child_stack = [*stack, self._cls_scope_descriptor(node)]
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

    def _collect_runtime_layer_imports(
        self, tree: ast.Module, target: str
    ) -> list[tuple[ast.stmt, str]]:
        """``(node, module)`` for every runtime *target*-package import in *tree*.

        Shared scan behind SKUEL022 (core/→adapters/), SKUEL027 (ui/→adapters/) and
        SKUEL032 (core/→ui/) — the layer scope, suppression, and message live in each
        rule's checker. *target* is the imported top-level package; every other
        behaviour here is layer-agnostic, so a third rule is one more argument, not a
        second walker. Flags imports at module scope AND inside functions (a
        function-local import is the same runtime dependency, deferred past module
        load — the dodge a module-level-only check would miss, and where BOTH of
        SKUEL032's founding violations hid).

        ``TYPE_CHECKING``-only imports are excluded: they never execute, so they cannot
        create a runtime dependency. Only the ``if`` BODY is exempt, never the
        ``else``/``elif`` branch — an import there DOES execute at runtime. Relative
        imports (``level > 0``) are never top-level *target* imports — including
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

            target_modules = [
                m for m in imported_modules if m == target or m.startswith(f"{target}.")
            ]
            if not target_modules:
                continue
            if node.lineno in type_checking_lines:
                continue  # TYPE_CHECKING-only — cannot create a runtime dependency

            found.append((node, target_modules[0]))
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
        imports flagged, TYPE_CHECKING body exempt): ``_collect_runtime_layer_imports``.

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

        for node, module in self._collect_runtime_layer_imports(tree, "adapters"):
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
        TYPE_CHECKING body exempt): ``_collect_runtime_layer_imports``. A type-only
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

        for node, module in self._collect_runtime_layer_imports(tree, "adapters"):
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

    def _check_core_imports_ui(
        self,
        file_path: Path,
        rel_path: Path,
        content: str,
        lines: list[str],
        tree: ast.Module | None,
    ) -> None:
        """
        SKUEL032 [ERROR]: a ``core/`` module must not import from ``ui/`` at runtime.

        SKUEL022's presentation-side twin. ADR-058 § Placement already states the rule in
        prose — a view shape "lives under ``ui/`` (not ``core/services/``) because the
        output is a page context, not a service-layer contract; putting it in ``core/``
        would invert the ``core → ui`` import direction" — but nothing enforced it, and
        the class regrew: commit ``fe3f7a9c2`` relocated ``core/ui/`` to ``ui/`` to
        "remove presentation layer from core domain", and ``core/services/lp_service.py``
        still reached back into ``ui.ui_types`` to *construct* display DTOs (fixed with
        this rule, #839). Scan mechanics (function-local imports flagged, TYPE_CHECKING
        body exempt): ``_collect_runtime_layer_imports``.

        Deliberately NOT extended to ``adapters/inbound/``: a route composing UI
        components is the job it exists to do (the same carve-out SKUEL022 makes).

        HONEST LIMIT: this measures the runtime *import*, not the layering intent.
        Hoisting the import under ``if TYPE_CHECKING:`` satisfies the rule while a
        ``core/`` signature still returns a ``ui/`` type. Green here is not proof the
        inversion was fixed.

        Note there is no ``if "ui" not in content`` pre-filter, unlike the two adapters
        rules: measured on 777 ``core/*.py`` files, ``"adapters"`` is a substring of 75
        (9.7%) but ``"ui"`` is a substring of 655 (84.3%) — it would filter nothing. The
        AST is parsed once per file and shared, so the scan is already cheap.

        Fix: return domain values from the service and build the display type in ``ui/``
        (``core/ports/query_types.py`` row TypedDicts are the established carrier — 9
        ``ui/`` modules already import them); or move a type-only import under
        ``if TYPE_CHECKING:``.

        Suppress: # skuel-lint: disable=SKUEL032 -- <reason>
        File-level: # skuel-lint: disable-file=SKUEL032 -- <reason>
        """
        if self._is_file_suppressed(content, "SKUEL032"):
            return

        if tree is None:
            return

        for node, module in self._collect_runtime_layer_imports(tree, "ui"):
            line = lines[node.lineno - 1] if 0 < node.lineno <= len(lines) else ""
            if self._is_line_suppressed(line, "SKUEL032"):
                continue

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=node.lineno,
                    column=node.col_offset,
                    severity=Severity.ERROR,
                    rule_id="SKUEL032",
                    message=(
                        f"core/ module imports presentation module '{module}' at runtime "
                        f"— wrong dependency direction (ui/ renders what core/ returns, "
                        f"never the reverse; ADR-058)"
                    ),
                    suggestion=(
                        "Return domain values (a core/ports/query_types row TypedDict) and "
                        "build the display type in ui/; or move a type-only import under "
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

        No allowlist: every ``core/`` path is checked. The facade allowlist that
        parked KU/PS/LP and then user/insight is gone (SoC arc PRs 6–7, July
        2026) — CLAUDE.md's "Facade IS the contract" is about the route→service
        boundary and never licensed a concrete ``self.backend``. Only the
        ordinary line/file suppression comments can silence this rule now.

        Fix: switch the TYPE_CHECKING import from the adapter to its
        ``core/ports/*Operations`` protocol; switch the annotation to the protocol
        name. The composition-root injection is unchanged — the adapter satisfies
        the protocol structurally.

        Suppress: # skuel-lint: disable=SKUEL023 -- <reason>
        File-level: # skuel-lint: disable-file=SKUEL023 -- <reason>
        """
        if self._is_file_suppressed(content, "SKUEL023"):
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
                        f"the protocol name. Facades are NOT exempt — 'Facade IS the "
                        f"contract' is about the route→service boundary, not "
                        f"self.backend; see CLAUDE.md '## Protocol-Based Architecture'."
                    ),
                    line_content=line.strip(),
                )
            )

    # =========================================================================
    # SKUEL023 second sub-check: annotation STRENGTH on self.backend
    # =========================================================================

    @staticmethod
    def _collect_any_aliases(tree: ast.Module) -> set[str]:
        """Local names that mean ``typing.Any`` in this module.

        ``from typing import Any as BackendT`` + ``backend: BackendT`` would
        otherwise read as a concrete type and pass. Same bypass class the rule's
        Tier-4 import gate already closes for adapter imports — an alias must not
        buy an exemption the spelled-out form does not get. ``typing.Any`` written
        out needs no entry: ``_extract_annotation_refs`` returns ``Any`` as the
        Attribute chain's tail.
        """
        aliases = {"Any"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "typing":
                aliases.update(a.asname for a in node.names if a.name == "Any" and a.asname)
            elif isinstance(node, ast.Assign):
                # Module-level `X = Any` (or `X = typing.Any`) re-export.
                value = node.value
                is_any = (isinstance(value, ast.Name) and value.id in aliases) or (
                    isinstance(value, ast.Attribute) and value.attr == "Any"
                )
                if is_any:
                    aliases.update(t.id for t in node.targets if isinstance(t, ast.Name))
        return aliases

    @staticmethod
    def _find_class_body_backend_declaration(cls: ast.ClassDef) -> ast.AnnAssign | None:
        """The lowest-line ``backend: X`` declaration in ``cls``'s own class-body scope.

        Pruned at every scope boundary — ``FunctionDef``, ``AsyncFunctionDef``,
        ``ClassDef`` — which is what makes this *class-body scope* rather than
        "the class subtree". Both exclusions are load-bearing in opposite
        directions:

        - stopping at nested ``ClassDef`` keeps an inner class's declaration off
          its outer class (the false positive Codex caught on the assignment side
          of this rule, #1092);
        - stopping at functions keeps a method-local ``backend: Any = ...`` from
          reading as a class attribute, which is the same mistake mirrored.

        It does NOT stop at compound statements, because those share class-body
        scope: ``if TYPE_CHECKING: backend: Any`` in a class body declares the
        attribute as far as a type checker is concerned, so the rule must see it
        too. Iterating ``cls.body`` directly missed exactly that shape and left a
        silent bypass (Codex, this PR).

        Lowest line number, not traversal order: ``_walk_pruned`` is LIFO, so
        "first found" would not be stable, and the violation is anchored here.
        """
        matches = [
            node
            for node in SkuelLinter._walk_pruned(
                cls, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            )
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "backend"
        ]
        return min(matches, key=lambda n: n.lineno) if matches else None

    @staticmethod
    def _resolve_backend_annotation(
        cls: ast.ClassDef, assign: ast.Assign | ast.AnnAssign
    ) -> ast.expr | None:
        """The annotation governing ``self.backend`` for one class, or None if unannotated.

        Precedence — the middle form is the one a naive attribute-only reader
        misses, and it is the form most services actually use:

        1. ``self.backend: X = ...``     (AnnAssign on the attribute)
        2. class-body ``backend: X``     (the BaseService shape)
        3. RHS is a plain Name matching an ``__init__`` parameter → that param's
           annotation (``def __init__(self, backend: X): self.backend = backend``)
        4. nothing → None (``self.backend = service.backend`` lands here)
        """
        if isinstance(assign, ast.AnnAssign):
            return assign.annotation

        declaration = SkuelLinter._find_class_body_backend_declaration(cls)
        if declaration is not None:
            return declaration.annotation

        if isinstance(assign.value, ast.Name):
            for stmt in cls.body:
                if not isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if stmt.name != "__init__":
                    continue
                args = [
                    *stmt.args.posonlyargs,
                    *stmt.args.args,
                    *stmt.args.kwonlyargs,
                ]
                for arg in args:
                    if arg.arg == assign.value.id and arg.annotation is not None:
                        return arg.annotation
        return None

    def _check_backend_annotation_strength(
        self,
        file_path: Path,
        rel_path: Path,
        content: str,
        lines: list[str],
        tree: ast.Module | None,
    ) -> None:
        """
        SKUEL023 [ERROR]: a ``core/`` class that assigns OR declares ``backend`` must
        type it against a ``core/ports`` protocol — ``Any`` and bare-unannotated both
        defeat the boundary.

        The sibling of the adapter-annotation check above. That one asks *which*
        type the annotation names (protocol, not concrete adapter); this one asks
        whether the annotation carries any information at all. Both failures cost
        the same thing: every ``self.backend.<method>()`` in the class goes
        unchecked, so a renamed or deleted backend method reads as green — the
        phantom-method class this codebase has repeatedly found.

        Two triggers, one verdict:

        1. **Assignment** — the class owns the object (``ast.Assign`` /
           ``ast.AnnAssign`` targeting ``self.backend``). Annotation resolved by
           the precedence in ``_resolve_backend_annotation``.
        2. **Declaration-only** (PR-C, 2026-08) — a class-body ``backend: X`` with
           no assignment anywhere in the class: the mixin shape, where the *host*
           constructs the object. The host owning the object never made the mixin's
           calls checkable; ``backend: Any`` there costs exactly what it costs on an
           assigner. Fix: name the host's protocol. This trigger was added only
           after all 27 such sites were clean (#1093, #1094), so it went green with
           zero suppressions.

        A dead declaration — ``backend: Any`` in a class with no ``self.backend``
        call at all — flags too, and the fix is deletion (8 of the 27 were this).
        Deliberate: keying on use rather than on the declaration would make the same
        line legal or illegal depending on lines elsewhere, and would stay silent at
        the moment that actually matters — when someone later adds the first call to
        a declaration that predates it.

        Only ``Any`` can flag on the declaration branch: a class-body ``backend``
        with no annotation is not a declaration at all (it is a bare ``Name``
        expression), so "is unannotated" is reachable only through assignment.

        Verdict on the resolved annotation (see ``_resolve_backend_annotation``
        for how it is found):
        - unresolvable → flag (unannotated)
        - any extracted name means ``Any`` → flag. Forward-reference strings are
          parsed, so ``"Any | None"`` is caught alongside bare ``Any``,
          ``Optional[Any]`` and ``list[Any]`` — the reuse of
          ``_extract_annotation_refs`` is deliberate: one parser, not two.
          Local aliases count (``from typing import Any as X``); see
          ``_collect_any_aliases``.
        - otherwise → clean

        TypeVars need no exemption branch: ``backend: B`` on a generic base
        (``BaseService[B, T, U]``, the seven mixins in core/services/mixins/,
        ``BasePlanningService``'s ``BackendT``) extracts the name ``B`` / ``BackendT``,
        which is not ``Any`` and so is already clean. A name-based exemption list
        would also have to avoid special-casing the literal ``B``, which is exactly
        the kind of vacuous branch this codebase deletes.

        Suppress: # skuel-lint: disable=SKUEL023 -- <reason>
        File-level: # skuel-lint: disable-file=SKUEL023 -- <reason>
        """
        if tree is None or self._is_file_suppressed(content, "SKUEL023"):
            return

        any_aliases = self._collect_any_aliases(tree)

        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            assign = self._find_self_backend_assignment(cls)
            declaration = self._find_class_body_backend_declaration(cls) if assign is None else None
            if assign is not None:
                anchor: ast.stmt = assign
                assigns = True
                annotation = self._resolve_backend_annotation(cls, assign)
            elif declaration is not None:
                anchor = declaration
                assigns = False
                annotation = declaration.annotation
            else:
                continue

            if annotation is None:
                verdict = "is unannotated"
            elif any_aliases.intersection(
                name for _lookup, name in self._extract_annotation_refs(annotation)
            ):
                verdict = "is typed `Any`"
            else:
                continue

            lineno = anchor.lineno
            line = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
            if self._is_line_suppressed(line, "SKUEL023"):
                continue

            if assigns:
                message = (
                    f"'{cls.name}.backend' {verdict} — type `self.backend` against a "
                    f"core/ports protocol (ADR-044); `Any` and bare-unannotated both "
                    f"defeat the boundary"
                )
                suggestion = (
                    "Declare (or reuse) a `*BackendOperations` protocol in core/ports "
                    "covering exactly the methods this class calls, and annotate the "
                    "__init__ parameter with it. Facades are NOT exempt — 'Facade IS "
                    "the contract' is about the route→service boundary, not "
                    "self.backend; see CLAUDE.md '## Protocol-Based Architecture'."
                )
            else:
                message = (
                    f"'{cls.name}.backend' {verdict} — a declaration-only `backend: Any` "
                    f"leaves every `self.backend.<method>()` in this class unchecked just "
                    f"as completely as an assigned one (ADR-044)"
                )
                suggestion = (
                    "Name the core/ports protocol this mixin's HOST types its backend "
                    "against — resolve the host through the importing module, never by "
                    "bare class name (four different `_AnalyticsMixin` classes exist). "
                    "If the class never reads `self.backend`, the declaration is dead: "
                    "delete the line rather than typing it."
                )

            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=lineno,
                    column=anchor.col_offset,
                    severity=Severity.ERROR,
                    rule_id="SKUEL023",
                    message=message,
                    suggestion=suggestion,
                    line_content=line.strip(),
                )
            )

    @staticmethod
    def _walk_pruned(node: ast.AST, stop: tuple[type[ast.AST], ...]) -> Iterator[ast.AST]:
        """Every node under ``node``, not descending into any node in ``stop``.

        ``ast.walk`` has no pruning, and both SKUEL023 backend lookups need it —
        for different boundaries. Pruning by node type rather than by enumerating
        ``body``/``orelse``/``handlers``/``finalbody`` means compound statements
        (``if``, ``try``, ``with``, ``match``) are traversed without listing their
        fields, so a new statement form cannot silently open a hole.
        """
        stack: list[ast.AST] = list(ast.iter_child_nodes(node))
        while stack:
            child = stack.pop()
            if isinstance(child, stop):
                continue
            yield child
            stack.extend(ast.iter_child_nodes(child))

    @staticmethod
    def _walk_own_body(cls: ast.ClassDef) -> Iterator[ast.AST]:
        """Every node under ``cls`` EXCEPT those inside a nested class.

        ``ast.walk`` descends into nested ``ClassDef`` nodes, which would credit
        an inner class's ``self.backend = backend`` to its outer class — and the
        outer class, having no ``__init__`` and no class-body ``backend:``, would
        then be reported unannotated. A nested class owns its own assignment and
        is visited in its own right by the caller's ClassDef loop.
        """
        return SkuelLinter._walk_pruned(cls, (ast.ClassDef,))

    @staticmethod
    def _find_self_backend_assignment(cls: ast.ClassDef) -> ast.Assign | ast.AnnAssign | None:
        """The first ``self.backend = ...`` / ``self.backend: X = ...`` owned by ``cls``."""
        for node in SkuelLinter._walk_own_body(cls):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and target.attr == "backend"
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"
                    ):
                        return node
            elif isinstance(node, ast.AnnAssign):
                target = node.target
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr == "backend"
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    return node
        return None

    # =========================================================================
    def _check_result_fail_expect_error(
        self,
        file_path: Path,
        rel_path: Path,
        content: str,
        lines: list[str],
        tree: ast.Module | None,
    ) -> None:
        """
        SKUEL028 [ERROR]: Use Result.fail(result) to propagate, not .expect_error().

        AST-based: flags a ``Result.fail(...)`` call whose argument expression
        contains an ``.expect_error()`` call anywhere in its subtree — the direct
        unwrap/re-wrap, conditional-expression forms, and category-flattening
        wraps like ``Errors.database(op, str(result.expect_error()))`` alike.
        ``.expect_error()`` outside a ``Result.fail(...)`` argument (logging,
        branching on category) is the sanctioned READ use and is not flagged.

        Suppressible: `# skuel-lint: disable=SKUEL028 -- <reason>`.
        """
        if tree is None:
            return
        if self._is_file_suppressed(content, "SKUEL028"):
            return

        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "fail"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "Result"
            ):
                continue

            # Positional AND keyword arguments — Result.fail(error=r.expect_error())
            # is the same bypass shape (Codex P2 on #678).
            arg_exprs = [*node.args, *(kw.value for kw in node.keywords)]
            unwrap = next(
                (
                    sub
                    for arg in arg_exprs
                    for sub in ast.walk(arg)
                    if isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "expect_error"
                ),
                None,
            )
            if unwrap is None:
                continue

            line_num = unwrap.lineno
            line = lines[line_num - 1] if 0 < line_num <= len(lines) else ""
            if self._is_line_suppressed(line, "SKUEL028"):
                continue
            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=unwrap.col_offset,
                    severity=Severity.ERROR,
                    rule_id="SKUEL028",
                    message="Result.fail(...expect_error()) - use Result.fail(result)",
                    suggestion=(
                        "Propagate with Result.fail(result); "
                        ".expect_error() is for reading the error only"
                    ),
                    line_content=line.strip(),
                )
            )

    # SKUEL030: migrations are the one persistence path that SHOULD name retired
    # vocabulary — a rename migration must reference what it is renaming away.
    SKUEL030_EXCLUDED_PREFIXES: ClassVar[tuple[str, ...]] = ("scripts/migrations",)

    # SKUEL030 baseline — (file, name) pairs of KNOWN FINDINGS: reads against
    # vocabulary nothing writes, so the query silently returns zero rows today.
    # Baselined rather than registered because registering them would bless the
    # bug — the fix is to repoint or delete the reader, which changes query
    # semantics and belongs in its own PR.
    #
    # EMPTY as of the semantic-relationship-layer roadmap Phase 1 (2026-07-20):
    # the last two entries (EXTENDS_PATTERN / DEEPENS_UNDERSTANDING in
    # _knowledge_context_mixin.py) were NOT writer-less after all — the semantic
    # layer's live admin writer (POST /api/path-steps/relationships →
    # build_semantic_merge) emitted them. Phase 1 made to_neo4j_name() return a
    # RelationshipName, so those edges now persist as RELATED_TO (the coarse
    # bucket) with the precise predicate in the `semantic_type` property, and the
    # reader was repointed to RELATED_TO. See CYPHER_VOCABULARY_FINDINGS.md §9.
    #
    # Entries are (file, name) pairs, NOT bare names — scoping to the file that
    # already has the finding keeps a NEW bad name elsewhere failing (Codex P2 on
    # #732). File-level, not line-level, to avoid churn. SHRINKING list, never
    # growing. Full triage: docs/patterns/CYPHER_VOCABULARY_FINDINGS.md
    SKUEL030_BASELINE: ClassVar[frozenset[tuple[str, str]]] = frozenset()

    def _check_cypher_vocabulary(
        self,
        file_path: Path,
        rel_path: Path,
        content: str,
        lines: list[str],
        tree: ast.Module | None,
    ) -> None:
        """
        SKUEL030 [WARNING]: Unregistered relationship type / node label in Cypher.

        Neo4j silently matches zero rows against a label or relationship type that
        does not exist, so a typo below the boundary is invisible until a feature
        is quietly empty in production. Every name written in persistence Cypher is
        checked against ``RelationshipName`` / ``NeoLabel`` — the enums that declare
        themselves the single source of truth for the graph vocabulary.

        Vocabulary only: a plain ``[:OWNS]`` literal is fine. This rule does NOT
        require SKUEL013-style interpolation below the boundary — it reads the NAME,
        never the syntax around it.

        AST-based and docstring-aware (same inert-string model as SKUEL001/021), so
        illustrative Cypher in prose is skipped. f-strings are flattened whole before
        scanning, and names touching an interpolation are skipped as unresolvable.

        Suppressible: `# skuel-lint: disable=SKUEL030 -- <reason>`.
        """
        if tree is None:
            return
        if self._is_file_suppressed(content, "SKUEL030"):
            return

        vocabulary = load_vocabulary()
        inert_ids = self._inert_ids_for(tree)
        part_ids = fstring_part_ids(tree)
        reported: set[tuple[int, str]] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                fragment = render_fstring(node)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # Inert = docstring/example block. Part = a torn f-string
                # fragment already covered by its parent JoinedStr.
                if id(node) in inert_ids or id(node) in part_ids:
                    continue
                fragment = node.value
            else:
                continue

            # `scanning_fragment_at` is diagnostics-only and a no-op unless
            # `scripts/cypher_scan_diagnostics.py` is recording; it gives the
            # scanner's own dropped-span report an absolute file line to point at.
            with scanning_fragment_at(node.lineno):
                unregistered = unregistered_names(fragment, vocabulary)
            for name in unregistered:
                if (rel_path.as_posix(), name.value) in self.SKUEL030_BASELINE:
                    continue
                line_num = node.lineno + name.line_offset
                if (line_num, name.value) in reported:
                    continue
                reported.add((line_num, name.value))
                line = lines[line_num - 1] if 0 < line_num <= len(lines) else ""
                if self._is_line_suppressed(line, "SKUEL030"):
                    continue
                enum_name = vocabulary.enum_for(name.kind)
                self.result.violations.append(
                    Violation(
                        file_path=rel_path,
                        line_number=line_num,
                        column=node.col_offset,
                        severity=Severity.WARNING,
                        rule_id="SKUEL030",
                        message=(
                            f"Cypher {name.kind.value} '{name.value}' is not a {enum_name} member"
                        ),
                        suggestion=(
                            f"Register '{name.value}' in {enum_name}, or fix the "
                            "name — Neo4j matches zero rows on an unknown "
                            f"{name.kind.value} instead of erroring"
                        ),
                        line_content=line.strip(),
                    )
                )

        self._check_python_edge_lists(rel_path, lines, tree, vocabulary, inert_ids)

    def _check_python_edge_lists(
        self,
        rel_path: Path,
        lines: list[str],
        tree: ast.Module,
        vocabulary: Vocabulary,
        inert_ids: set[int],
    ) -> None:
        """SKUEL030, second position: edge names held in PYTHON, not Cypher.

        The Cypher scanner reads string literals that look like Cypher. But an
        alternation is just as often assembled from a Python list —
        ``{"practice": ["PRACTICES", "REINFORCES", "APPLIES_KNOWLEDGE"]}`` — or
        from a bare pipe string in a query spec (``"rel_types": "A|B"``). Those
        names never appear inside a Cypher fragment at lint time, so they were
        invisible to the rule while being exactly as load-bearing: the built
        alternation matches only its live arms and the dead ones contribute
        nothing, silently.

        Three such sites surfaced in three consecutive tranches (the two
        ``_INTENT_EDGE_SETS`` entries and ``domain_queries``' ``rel_types``),
        which is what motivated closing this gap.

        Corroboration keeps the false-positive rate at zero: see
        ``unregistered_edge_names``. Same baseline, suppression and severity as
        the Cypher half — this is one rule with two scanners, not two rules.
        """
        reported: set[tuple[int, str]] = set()

        def report(name: str, line_num: int, col: int) -> None:
            if (rel_path.as_posix(), name) in self.SKUEL030_BASELINE:
                return
            if (line_num, name) in reported:
                return
            reported.add((line_num, name))
            line = lines[line_num - 1] if 0 < line_num <= len(lines) else ""
            if self._is_line_suppressed(line, "SKUEL030"):
                return
            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=line_num,
                    column=col,
                    severity=Severity.WARNING,
                    rule_id="SKUEL030",
                    message=(
                        f"Python edge list names '{name}', which is not a RelationshipName member"
                    ),
                    suggestion=(
                        f"Register '{name}' in RelationshipName, or fix the name "
                        "— an alternation built from this list matches only its "
                        "live arms, so the dead ones contribute nothing silently"
                    ),
                    line_content=line.strip(),
                )
            )

        for node in ast.walk(tree):
            # Position 1: a list/tuple/set literal of bare edge names.
            if isinstance(node, ast.List | ast.Tuple | ast.Set):
                elements = [
                    elt
                    for elt in node.elts
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                ]
                if len(elements) < 2:
                    continue
                by_value: dict[str, ast.Constant] = {}
                for elt in elements:
                    by_value.setdefault(elt.value, elt)
                for bad in unregistered_edge_names(list(by_value), vocabulary):
                    elt = by_value[bad]
                    report(bad, elt.lineno, elt.col_offset)

            # Position 2: a bare `"A|B"` alternation string (query-spec shape).
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) in inert_ids:
                    continue
                parts = bare_alternation_parts(node.value)
                if not parts:
                    continue
                for bad in unregistered_edge_names(parts, vocabulary):
                    report(bad, node.lineno, node.col_offset)

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

    def _check_async_without_await(
        self,
        file_path: Path,
        rel_path: Path,
        content: str,
        lines: list[str],
        tree: ast.Module | None,
    ) -> None:
        """
        SKUEL029 [ERROR]: async def whose body never awaits.

        CLAUDE.md async/sync rule: async for I/O, sync for computation. Flags an
        ``async def`` with a real body but no ``await`` / ``async for`` /
        ``async with`` of its own (nested defs' awaits belong to the nested
        function). Trivial bodies — docstring-only, ``pass``, ``...``, a bare
        ``raise`` — are exempt: protocol methods and stubs are declarations.
        Async GENERATORS (an own ``yield``) are exempt too: their ``async def``
        is load-bearing without awaits — sync-ifying breaks ``async for`` callers.
        """
        if self._is_file_suppressed(content, "SKUEL029"):
            return
        if tree is None:
            return

        def own_statements(fn: ast.AsyncFunctionDef) -> list[ast.AST]:
            """Every node in fn's body, without descending into nested defs."""
            found: list[ast.AST] = []
            stack: list[ast.AST] = list(fn.body)
            while stack:
                n = stack.pop()
                found.append(n)
                if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    stack.extend(ast.iter_child_nodes(n))
            return found

        def is_trivial(fn: ast.AsyncFunctionDef) -> bool:
            body = fn.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body = body[1:]  # skip docstring
            if not body:
                return True
            if len(body) == 1:
                stmt = body[0]
                if isinstance(stmt, (ast.Pass, ast.Raise)):
                    return True
                if (
                    isinstance(stmt, ast.Expr)
                    and isinstance(stmt.value, ast.Constant)
                    and stmt.value.value is ...
                ):
                    return True
            return False

        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef) or is_trivial(node):
                continue
            # An own yield makes this an ASYNC GENERATOR — `async def` is
            # load-bearing there even without awaits: converting to `def`
            # turns the async iterator into a sync generator and breaks every
            # `async for` caller. Likewise an async comprehension
            # (`[x async for x in ...]`) is ast.comprehension(is_async=1),
            # not ast.AsyncFor (both Codex findings on #678).
            if any(
                isinstance(sub, (ast.Await, ast.AsyncFor, ast.AsyncWith, ast.Yield))
                or (isinstance(sub, ast.comprehension) and sub.is_async)
                for sub in own_statements(node)
            ):
                continue

            # Suppression honored on any line of the (possibly ruff-wrapped)
            # async-def header; the span is recorded so the SKUEL026 audit reads
            # the SAME lines (matches SKUEL005's def-signature handling).
            start = node.lineno
            end = max(start, node.body[0].lineno - 1) if node.body else start
            if any(
                self._is_line_suppressed(lines[i], "SKUEL029")
                for i in range(start - 1, min(end, len(lines)))
            ):
                continue

            line = lines[start - 1] if 0 < start <= len(lines) else ""
            self.result.violations.append(
                Violation(
                    file_path=rel_path,
                    line_number=start,
                    column=node.col_offset,
                    severity=Severity.ERROR,
                    rule_id="SKUEL029",
                    message=f"async def '{node.name}' never awaits - sync body in async signature",
                    suggestion=(
                        "Make it a plain def (and un-await call sites), or keep async "
                        "only if an interface/protocol requires it"
                    ),
                    line_content=line.strip(),
                    suppression_span=(start, end),
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
