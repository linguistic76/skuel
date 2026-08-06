"""Drift guard: no CI job may let uv rewrite ``app/uv.lock`` (PR #935).

WHY THIS EXISTS

Both ``uv sync`` and ``uv run`` LOCK before doing their work — ``uv run --frozen``
is documented as "Run without updating the uv.lock file", which is only worth
saying because the bare form updates it. A job that re-locks measures a
resolution it just generated while reporting on the committed one. That is not
theoretical: it is exactly how the required *Dependency CVE Audit* passed
VACUOUSLY before PR #935. ``audit_dependencies.sh`` runs ``uv export --locked``
precisely to refuse a stale lock, but a bare ``uv sync`` earlier in the job had
already rewritten ``uv.lock``, so the ``--locked`` assertion held against uv's
own fresh output and the gate went green over a stale lock.

THE INVARIANT

  1. A job that invokes uv and does NOT pass an explicit ``--locked`` must
     declare ``UV_FROZEN`` at JOB (or workflow) level.

     Job level, not step level: the CI jobs run up to ~20 ``uv run`` commands
     each. PR #931 pinned only the ``uv sync`` install step, and the ``uv run``
     steps kept re-locking — per-step coverage is precisely the thing that was
     already got wrong once.

  2. A job that DOES pass ``--locked`` must NOT declare ``UV_FROZEN`` at all.
     uv treats the two as a hard conflict::

         error: the argument `--locked` cannot be used with `UV_FROZEN`
                (environment variable)

     (exit 2, verified on uv 0.10.9). Those jobs pin their sync with an
     explicit ``--frozen`` FLAG instead, and the script's own ``--locked`` stays
     the staleness detector.

  3. …and because rule 2 leaves them with no env-level protection, EVERY
     lock-touching uv command in such a job must carry its own ``--frozen`` or
     ``--locked``. This half is the original defect, not a corollary: before
     PR #935 ``pip_audit`` ran a bare ``uv sync --no-install-project`` and then
     ``uv export --locked``, so the export asserted freshness against the lock
     the sync had just rewritten. Rule 2 alone is blind to that — it was
     already satisfied on the broken tree.

  4. A job that never invokes uv must not declare ``UV_FROZEN`` — inert config
     that reads as protection.

KEYED ON BEHAVIOUR, NOT ON JOB NAMES

Rule 2 currently applies to ``ci.yml::pip_audit`` and
``dependency-audit.yml::python_audit``, but neither is named here. Both reach
their ``--locked`` through ``bash scripts/audit_dependencies.sh`` — so this
guard follows shell scripts a job invokes and reads the uv commands inside
them. When PR #932's osv-scanner migration replaces that script, the guard
follows whatever replaces it; if the replacement drops ``--locked``, rule 1
takes over and demands ``UV_FROZEN``. No name to update either way.

DIRECTION OF ERROR

Over-detecting ``--locked`` EXCUSES a job from rule 1 and silently reopens the
hole; under-detecting it demands a ``UV_FROZEN`` that fails loudly. So pin
evidence has to survive two separate ways of not being uv's:

  * Wrong COMMAND. ``echo "- A stale lock (\\`uv export --locked\\` refuses)"``
    is prose these workflows really do contain. Commands come from a real bash
    parse and only the command NAME counts, so an echoed ``--locked`` is never
    evidence.
  * Wrong ARGUMENT OWNER. ``uv run [OPTIONS] COMMAND [ARGS]`` — uv's options
    stop at the child. On uv 0.10.9, ``uv run python -c '…' --locked`` hands
    ``--locked`` to Python and uv still syncs unfrozen, so crediting it to uv
    would mark the job ``--locked`` while nothing pinned the lock at all
    (Codex, PR #959). Only uv's own option region counts.

Both cuts can drop real pin evidence, never invent it — but "conservative" is
NOT the same as safe. Dropping pin evidence also disables rule 2, so a command
that would exit 2 under ``UV_FROZEN`` passes unnoticed. There is no reading
that is safe for both rules at once.

PARSE WHAT IS SYNTAX; REFUSE WHAT IS NOT  (rule 0)

Seven review rounds produced fourteen findings, and sorting them settles how
this is built. They fell into two kinds:

  * SYNTAX — which token is the command. A hand-written tokenizer got this
    wrong in four rounds (``env -u X uv sync``, ``bash -c 'uv sync'``,
    ``uv --directory sync run …``), every time silently, and separately
    invented 21 phantom commands out of this repo's own workflows by
    mis-splitting ``$(…)`` concatenation, ``NAME+=(…)``, ``for`` and
    ``[[ … ]]``. This is a solved problem and is not solved here: the bash
    grammar parses it (tree-sitter-bash, MIT). Measured on these workflows,
    that took the command vocabulary from 47 names to 24 — every phantom gone
    — while finding the same 30 uv invocations.

  * NOT SYNTAX — what a command MEANS. No parser answers whether ``--locked``
    is uv's or the child's, what ``env -u`` does to a wrapper's argv, or what
    ``UV_FROZEN`` is worth at runtime. Guessing here is what reopened the hole
    each round, so these are REPORTED, never assumed:

      - a bare ``uv`` inside another command's arguments (an unskippable
        wrapper);
      - a ``--frozen``/``--locked`` whose owner cannot be settled — ``--opt
        value`` is indistinguishable from ``--flag POSITIONAL``, at the child
        boundary AND at the subcommand scan; the fix is ``--opt=value``;
      - an unrecognised command VERB, because the whitelist is the only part
        that fails closed on a shell feature nobody modelled;
      - ``export``/``declare`` of anything, a write to ``$GITHUB_ENV``, a
        command-local ``UV_FROZEN=``, or a step-level ``env:`` — four separate
        scopes that override the job's, none of them visible in a command name;
      - a script that does not resolve, including after a ``cd`` moved the
        working directory;
      - a region the grammar itself rejects.

The claim is therefore not "this understands your shell" — it is "this parses
the syntax and refuses the semantics it cannot settle". Refusals are finite and
actionable; an arity table for uv and for every wrapper would be a second,
drifting copy of someone else's CLI. On the real workflows the refusal count is
zero, so none of it is noise today.

Still unreached, and documented rather than claimed: uv shelled out from a
PYTHON script, and a whitelisted verb that writes ``$GITHUB_ENV`` internally.
Both need a workflow author to hide an env change inside a program, and both
fail in the loud direction if the guard is ever wrong about them.

See: PR #935, docs/guides/UV_GUIDE.md § Freezing the lock in CI
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePath, PurePosixPath
from typing import NamedTuple

import tree_sitter_bash
import yaml
from tree_sitter import Language, Node, Parser

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# Job/workflow-level `env: UV_FROZEN:` values that count as "the lock is pinned".
# Anything else (absent, "", "0", "false") counts as NOT pinned, so an ambiguous
# value fails rule 1 with its actual value named rather than being waved through.
_ENABLED_VALUES = frozenset({"1", "true"})

# Commands whose first non-flag argument is a script to descend into.
_INTERPRETERS = frozenset({"bash", "sh", "zsh", "dash", "ksh", "source", "."})

# Per-command ways to say "do not touch uv.lock".
_PIN_FLAGS = frozenset({"--frozen", "--locked"})

# uv subcommands that provably do not read or rewrite the project lock. Every
# other subcommand — sync, run, export, lock, add, remove, tree, build — is
# treated as lock-touching. The allowlist is deliberately the SHORT side: a
# subcommand wrongly listed here silently drops a job out of rule 3, while one
# wrongly omitted only demands a --frozen that was already harmless.
#
# NOT `version`, despite the name reading like a query. `uv version [VALUE]`
# WRITES the version, and its own `--frozen` is documented as "Update the
# version without re-locking the project" — so the mutating form re-locks
# (Codex, PR #959). Telling it from the read-only form needs option arity, and
# arity is exactly what this guard refuses to model, so both forms count as
# lock-touching: `uv version` in a --locked job must carry --frozen.
_LOCK_SAFE_SUBCOMMANDS = frozenset(
    {"pip", "python", "tool", "venv", "cache", "self", "auth", "help"}
)

# Every uv subcommand, so the option region can be located by name rather than
# by "first token without a dash" — which a global option's VALUE would win
# (`uv --directory app run …` would read `app` as the subcommand).
_UV_SUBCOMMANDS = _LOCK_SAFE_SUBCOMMANDS | {
    "run",
    "init",
    "add",
    "remove",
    "sync",
    "lock",
    "export",
    "tree",
    "build",
    "publish",
    "format",
    "version",
}

# `uv run [OPTIONS] COMMAND [ARGS]` — uv's options STOP at the child command.
_SUBCOMMANDS_WITH_CHILD = frozenset({"run"})

# Unambiguous lock-touching subcommand names, used as a backstop: if one of
# these appears anywhere in uv's own option region, the command touches the
# lock no matter which token was picked as the subcommand.
_LOCK_TOUCHING_SUBCOMMANDS = frozenset({"sync", "run", "lock", "export", "add", "remove", "tree"})

# Leading tokens that precede the real command name in a command position.
_COMMAND_PREFIXES = frozenset(
    {
        "if",
        "then",
        "elif",
        "else",
        "fi",
        "while",
        "until",
        "do",
        "done",
        "for",
        "case",
        "esac",
        "function",
        "!",
        "time",
        "exec",
        "sudo",
        "command",
        "builtin",
        "nohup",
        "env",
        "xargs",
    }
)

# Unquoted characters that end one command position and begin another.
_SEPARATORS = frozenset({"\n", ";", "&", "|", "(", ")", "{", "}", "<", ">"})

# Redirections whose TARGET changes what later steps see. GitHub Actions reads
# $GITHUB_ENV after each step and exports it to the next, so `echo "UV_FROZEN=0"
# >> $GITHUB_ENV` unpins every following step — an env scope that has nothing to
# do with shell syntax and that no amount of parsing would reveal.
_ENV_MUTATING_TARGETS = ("GITHUB_ENV",)

# Command verbs that cannot change what uv sees: they touch neither the
# environment of later commands nor the working directory. This is a WHITELIST,
# and that direction is the point — an unrecognised verb is REFUSED, so a shell
# feature nobody modelled (`export`, `source`, `pushd`, `eval`, and whatever
# comes next) fails closed instead of passing silently. Adding a verb here is a
# semantic judgement about that one verb, not a new special case in a parser.
#
# Deliberately absent: export, unset, source, ., eval, pushd, popd, exec, cd.
_STATE_NEUTRAL_VERBS = frozenset(
    {
        "echo",
        "printf",
        "cat",
        "head",
        "tail",
        "tee",
        "cut",
        "sed",
        "awk",
        "grep",
        "sort",
        "uniq",
        "wc",
        "tr",
        "jq",
        "date",
        "sha256sum",
        "dirname",
        "basename",
        "mktemp",
        "mkdir",
        "rm",
        "cp",
        "mv",
        "ls",
        "touch",
        "chmod",
        "find",
        "sleep",
        "true",
        "false",
        "exit",
        "return",
        "test",
        "[",
        "[[",
        "trap",
        "read",
        "shift",
        "git",
        "npm",
        "node",
        "npx",
        "python",
        "python3",
        "pip",
        "docker",
        "curl",
        "wget",
        "tar",
        "unzip",
        "google-chrome-stable",
        "sudo",
    }
)


# --------------------------------------------------------------------------
# Shell parsing
#
# A hand-written tokenizer got this wrong in four separate review rounds, each
# time silently (`env -u X uv sync`, `bash -c 'uv sync'`, `uv --directory sync
# run …`). It also mis-split four real shell constructs — `$(…)` concatenation,
# `NAME+=(…)` array assignment, `for` loops, `|` inside `[[ … ]]` — inventing
# 21 phantom "commands" out of the repo's own workflows.
#
# So the grammar is not approximated here: tree-sitter-bash parses it. Measured
# on this repo's workflows, that takes the command vocabulary from 47 names to
# 24 — every phantom gone — while finding the same 30 uv invocations. What a
# parser CANNOT settle (which flags are uv's, what a wrapper does to the
# environment) is refused instead, by the rules below.
# --------------------------------------------------------------------------

# GitHub Actions interpolates `${{ … }}` before the shell ever runs, so leaving
# it in the source is asking bash to parse something bash never sees — the only
# two parse errors across every workflow, both of them ours to fix, not the
# grammar's.
_ACTIONS_EXPRESSION = re.compile(r"\$\{\{.*?\}\}", re.DOTALL)

# `export`/`declare`/`local`/`readonly` are a distinct grammar node, never a
# `command` — so the verb whitelist would never see them. They are the shapes
# that mutate the environment, so they are named here explicitly.
_DECLARATION_KEYWORDS = frozenset({"export", "declare", "local", "readonly", "typeset"})


@lru_cache(maxsize=1)
def _bash_parser() -> Parser:
    return Parser(Language(tree_sitter_bash.language()))


class _ShellCommand(NamedTuple):
    """One node of a parsed shell fragment, in the terms this guard reasons in."""

    kind: str  # "command" | "declaration" | "redirect" | "unparsed"
    name: str | None  # command basename, e.g. "uv"
    written: str  # command as written, e.g. "./scripts/foo.sh"
    argv: list[str]  # arguments, unquoted
    assignments: tuple[str, ...]  # NAME=VALUE prefixes on this command
    rendered: str  # the source text, for messages


def _node_text(node: Node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf8", "replace")


def _word(node: Node, src: bytes) -> str:
    """A shell word with its quoting removed, as the command would receive it.

    Concatenation is joined, not left raw: bash hands `--loc"ked"` to uv as
    `--locked`, and a guard that read it as the literal `--loc"ked"` would miss
    a pin flag it was looking straight at (Codex, PR #959). Only QUOTING is
    resolved here — an expansion stays visible as `$…`, because what it expands
    to is not a question about syntax.
    """
    if node.type == "concatenation":
        return "".join(_word(child, src) for child in node.children)
    text = _node_text(node, src)
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    return text


def _is_dynamic(word: str) -> bool:
    """Does this argument's value depend on something only the shell knows?"""
    return "$" in word or "`" in word


def _shell_commands(text: str) -> list[_ShellCommand]:
    """Every command, declaration, redirection and unparsable region, in order.

    Commands inside `$(…)`, backticks, pipelines, loops and conditionals are
    all reached: they are `command` nodes wherever they sit in the tree.
    """
    src = _ACTIONS_EXPRESSION.sub("ACTIONS_EXPR", text).encode()
    found: list[_ShellCommand] = []

    def visit(node: Node) -> None:
        if node.type == "ERROR":
            # Refused, not skipped: a region the grammar could not parse may
            # hold anything, including a uv command.
            found.append(_ShellCommand("unparsed", None, "", [], (), _node_text(node, src)))
            return
        if node.type == "command":
            name_node = node.child_by_field_name("name")
            assignments = tuple(
                _node_text(c, src) for c in node.named_children if c.type == "variable_assignment"
            )
            argv = [
                _word(c, src)
                for c in node.named_children
                if c.type not in ("command_name", "variable_assignment", "file_redirect")
            ]
            written = _word(name_node, src) if name_node is not None else ""
            found.append(
                _ShellCommand(
                    "command",
                    PurePosixPath(written).name if written else None,
                    written,
                    argv,
                    assignments,
                    _node_text(node, src),
                )
            )
        elif node.type == "declaration_command":
            words = [_node_text(c, src) for c in node.children]
            found.append(
                _ShellCommand(
                    "declaration",
                    words[0] if words else None,
                    words[0] if words else "",
                    words[1:],
                    tuple(w for w in words[1:] if "=" in w),
                    _node_text(node, src),
                )
            )
        elif node.type == "variable_assignment" and (
            node.parent is None or node.parent.type not in ("command", "declaration_command")
        ):
            # A bare `UV_FROZEN=0` statement. Because the job's env is already
            # EXPORTED, reassigning it re-exports the new value — verified:
            # `UV_FROZEN=1 bash -c 'UV_FROZEN=0; printenv UV_FROZEN'` prints 0.
            text = _node_text(node, src)
            found.append(_ShellCommand("assignment", None, "", [], (text,), text))
        elif node.type == "file_redirect":
            destination = node.child_by_field_name("destination")
            found.append(
                _ShellCommand(
                    "redirect",
                    None,
                    _word(destination, src) if destination is not None else "",
                    [],
                    (),
                    _node_text(node, src),
                )
            )
        for child in node.children:
            visit(child)

    visit(_bash_parser().parse(src).root_node)
    return found


def _split_commands(text: str) -> list[list[str]]:
    """Command positions as token lists — `[name, *argv]` for each command."""
    return [
        [c.written, *c.argv] for c in _shell_commands(text) if c.kind == "command" and c.written
    ]


def _command_name(tokens: list[str]) -> tuple[str | None, str, list[str]]:
    """``(basename, written form, arguments)`` for an already-split command."""
    if not tokens:
        return None, "", []
    return PurePosixPath(tokens[0]).name, tokens[0], tokens[1:]


# --------------------------------------------------------------------------
# Job census
# --------------------------------------------------------------------------


class _UvParse(NamedTuple):
    """How much of a `uv …` command this guard could settle."""

    subcommand: str | None
    option_region: tuple[str, ...]
    uncertain: tuple[str, ...]  # tokens whose owner could not be determined
    reason: str  # "" when nothing is uncertain
    dynamic: tuple[str, ...] = ()  # option-position words the shell computes


def _uv_option_region(args: list[str]) -> _UvParse:
    """uv's subcommand, the tokens that are uv's OWN options, and ambiguity.

    `uv run [OPTIONS] COMMAND [ARGS]` — everything after COMMAND belongs to the
    CHILD. Verified on uv 0.10.9: `uv run python -c '…' --locked` hands
    `--locked` to Python and uv still syncs unfrozen, so crediting it to uv
    would EXCUSE the job from rule 1. The region is therefore cut at the first
    non-flag token after the subcommand.

    But that cut cannot tell a child command from an OPTION VALUE without
    knowing every uv option's arity — in `uv run --with requests --locked …`
    the cut lands on `requests` and drops a `--locked` that really is uv's.
    Cutting early is not simply "safe": losing pin evidence also disables
    rule 2, so a command that WILL exit 2 under UV_FROZEN would pass unnoticed.

    So the boundary reports whether it is ambiguous — the token before it is a
    valueless-looking flag — and the caller refuses to guess rather than
    silently choosing a reading. An arity table would be a second, drifting
    copy of uv's CLI; refusing is stable across uv versions.

    The SAME discriminator applies to the subcommand itself, which is the
    other place a positional gets interpreted: in
    `uv --directory sync run python x.py --locked`, `sync` is `--directory`'s
    value, but it is also a subcommand name — so the scan matched it, the
    region swallowed the child's `--locked`, and the job was credited as
    --locked and excused from rule 1 (Codex, PR #959).
    """

    def _value_of_a_flag(index: int) -> bool:
        """Could ``args[index]`` be the preceding option's value?

        `--opt value` and `--flag positional` are indistinguishable without
        arity. `--opt=value` is self-delimiting, so it settles the question.
        """
        if index == 0:
            return False
        previous = args[index - 1]
        return previous.startswith("-") and "=" not in previous

    def _dynamic_options(region: tuple[str, ...]) -> tuple[str, ...]:
        """Computed words sitting where a FLAG could sit, inside uv's options.

        `uv export --output-file $REQ` is fine: $REQ follows a valueless-looking
        flag, so it reads as that flag's value — and both real audit jobs do
        exactly this. `uv export "$PIN"` is not: nothing says $PIN is not
        `--locked`, and uv would then exit 2 under UV_FROZEN with this guard
        reporting clean. Same discriminator as the two ambiguity checks.
        """
        return tuple(
            word
            for position, word in enumerate(region)
            if _is_dynamic(word)
            and not (
                position > 0
                and region[position - 1].startswith("-")
                and "=" not in region[position - 1]
            )
        )

    subcommand: str | None = None
    sub_index = -1
    for index, token in enumerate(args):
        if not token.startswith("-") and token in _UV_SUBCOMMANDS:
            if _value_of_a_flag(index):
                # The whole region is suspect: if this token is really an
                # option's value, the true subcommand lies further right and
                # every flag after it may belong to a child.
                return _UvParse(
                    token,
                    tuple(args),
                    tuple(args),
                    f"{token!r} was read as the subcommand, but it directly follows "
                    f"{args[index - 1]!r} and may be that option's value instead",
                )
            subcommand, sub_index = token, index
            break

    if subcommand is None or subcommand not in _SUBCOMMANDS_WITH_CHILD:
        return _UvParse(subcommand, tuple(args), (), "", _dynamic_options(tuple(args)))

    for index in range(sub_index + 1, len(args)):
        if not args[index].startswith("-"):
            if _value_of_a_flag(index):
                return _UvParse(
                    subcommand,
                    tuple(args[:index]),
                    tuple(args[index:]),
                    f"uv's options were cut at {args[index]!r}, but that may be "
                    f"{args[index - 1]!r}'s value rather than the command uv runs",
                    _dynamic_options(tuple(args[:index])),
                )
            return _UvParse(
                subcommand,
                tuple(args[:index]),
                (),
                "",
                _dynamic_options(tuple(args[:index])),
            )
    return _UvParse(subcommand, tuple(args), (), "", _dynamic_options(tuple(args)))


@dataclass(frozen=True)
class RefusedCommand:
    """A command this guard declines to interpret, rather than guess at.

    Never silently dropped. Every shape that reaches here — a wrapper whose
    options it cannot skip, a shell payload it cannot recover — would
    otherwise make a uv-using job read as uv-free, which is the silent
    direction. A refusal is a finite, actionable answer; a parser that keeps
    growing special cases is not.
    """

    origin: str
    rendered: str
    reason: str
    headline: str = "a uv command this guard cannot classify"
    fix: str = (
        "invoke uv directly (`uv sync --frozen …`) so the command is plainly "
        "visible in the workflow"
    )


@dataclass(frozen=True)
class UvInvocation:
    """One `uv ...` command found in a job, with where it came from."""

    origin: str  # "step 'Install dependencies'" or "scripts/audit_dependencies.sh"
    rendered: str
    subcommand: str | None
    option_region: tuple[str, ...]  # the tokens that belong to uv, not a child
    uncertain: tuple[str, ...] = ()  # tokens whose owner could not be settled
    uncertain_reason: str = ""
    dynamic: tuple[str, ...] = ()  # option-position words the shell computes

    @property
    def ambiguous_pin(self) -> bool:
        """A --frozen/--locked sits where ownership could not be settled.

        Ambiguity alone is not a finding — `uv run --quiet --locked pip-audit`
        cuts after a flag too. It only matters when a PIN flag is the token in
        doubt, because that is what decides rules 1 and 2.
        """
        return any(t in _PIN_FLAGS for t in self.uncertain)

    @property
    def _flags(self) -> set[str]:
        return {t for t in self.option_region if t.startswith("-")}

    @property
    def _words(self) -> set[str]:
        return {t for t in self.option_region if not t.startswith("-")}

    @property
    def locked(self) -> bool:
        return "--locked" in self._flags

    @property
    def touches_lock(self) -> bool:
        if self._words & _LOCK_TOUCHING_SUBCOMMANDS:
            return True
        if self.subcommand is not None:
            return self.subcommand not in _LOCK_SAFE_SUBCOMMANDS
        # A positional we don't recognise is a subcommand uv grew after this
        # was written: assume it locks. Only `uv --version`-shaped commands,
        # with no positional at all, are treated as lock-free.
        return bool(self._words)

    @property
    def pinned(self) -> bool:
        """Carries its own instruction not to rewrite the lock."""
        return bool(_PIN_FLAGS & self._flags)


@dataclass(frozen=True)
class JobUvUsage:
    """What one workflow job does with uv, and how it declares UV_FROZEN."""

    workflow: str
    job_id: str
    invocations: tuple[UvInvocation, ...]
    refused: tuple[RefusedCommand, ...]
    frozen_scope: str | None  # "workflow" / "job" — where UV_FROZEN was declared
    frozen_value: str | None
    step_frozen: tuple[str, ...]  # step names declaring UV_FROZEN (never sufficient)

    @property
    def label(self) -> str:
        return f"{self.workflow}::{self.job_id}"

    @property
    def uses_uv(self) -> bool:
        return bool(self.invocations)

    @property
    def locked_invocations(self) -> tuple[UvInvocation, ...]:
        return tuple(i for i in self.invocations if i.locked)

    @property
    def unpinned_invocations(self) -> tuple[UvInvocation, ...]:
        """Lock-touching uv commands carrying no --frozen/--locked of their own."""
        return tuple(i for i in self.invocations if i.touches_lock and not i.pinned)

    @property
    def passes_locked(self) -> bool:
        return bool(self.locked_invocations)

    @property
    def frozen_declared(self) -> bool:
        return self.frozen_scope is not None

    @property
    def frozen_enabled(self) -> bool:
        return (self.frozen_value or "").strip().lower() in _ENABLED_VALUES


def _env_value(container: object, key: str) -> tuple[bool, str | None]:
    """(declared, value-as-string) for ``key`` in a mapping's ``env:`` block."""
    if not isinstance(container, dict):
        return False, None
    env = container.get("env")
    if not isinstance(env, dict) or key not in env:
        return False, None
    raw = env[key]
    return True, "" if raw is None else str(raw)


def _dash_c_payload(args: list[str]) -> str | None:
    """The command STRING from `sh -c '…'` — shell source, not a file path.

    getopt clustering is real (`bash -lc '…'`), so any short-option bundle
    ending in `c` counts, as does the glued `-c'…'` form.
    """
    for index, token in enumerate(args):
        if not token.startswith("-") or token.startswith("--"):
            continue
        letters = token[1:]
        if letters.endswith("c"):
            return args[index + 1] if index + 1 < len(args) else ""
        head, sep, rest = letters.partition("c")
        if sep and head.isalpha():
            return rest
    return None


def _collect_from_shell(
    text: str,
    origin: str,
    workdir: Path,
    root: Path,
    seen: set[Path],
    inputs: set[Path],
    refused: list[RefusedCommand],
) -> list[UvInvocation]:
    """uv invocations in a shell fragment, descending into scripts it runs."""
    found: list[UvInvocation] = []
    # A `cd` earlier in the fragment moves the ground under every later script
    # path. Rather than model shell cwd state, the fragment stops trusting its
    # own resolution from that point on (Codex, PR #959).
    cwd_moved = False
    for command in _shell_commands(text):
        tokens = [command.written, *command.argv]
        name, written, args = command.name, command.written, command.argv
        assignments = command.assignments

        if command.kind == "unparsed":
            refused.append(
                RefusedCommand(
                    origin=origin,
                    rendered=command.rendered[:120],
                    headline="a shell fragment the bash grammar could not parse",
                    reason="an unparsable region may hold anything, including a uv "
                    "command, so it is reported rather than assumed empty",
                    fix="rewrite the fragment as valid bash",
                )
            )
            continue

        if command.kind == "declaration":
            refused.append(
                RefusedCommand(
                    origin=origin,
                    rendered=command.rendered,
                    headline=f"an environment declaration ({name!r})",
                    reason="`export`/`declare` change the environment of every LATER "
                    "command in the step, so a UV_FROZEN set here would override the "
                    "job's env for uv commands this guard reads as pinned",
                    fix="set UV_FROZEN only in the job's `env:` block",
                )
            )
            continue

        if command.kind == "redirect":
            if any(t in command.written for t in _ENV_MUTATING_TARGETS):
                refused.append(
                    RefusedCommand(
                        origin=origin,
                        rendered=command.rendered,
                        headline="a step writes $GITHUB_ENV",
                        reason="GitHub Actions exports $GITHUB_ENV to every LATER step, "
                        "so a UV_FROZEN written here silently overrides the job's env "
                        "for uv commands this guard reads as pinned",
                        fix="set UV_FROZEN only in the job's `env:` block, and do not "
                        "write it to $GITHUB_ENV",
                    )
                )
            continue

        # UV_FROZEN must not appear in executable shell AT ALL — not as a
        # command prefix, a bare assignment, an `export`, a `printf -v`, a
        # `read`, or anything invented later. Enumerating the mechanisms is
        # what put this dimension in three separate review rounds; the NAME is
        # the thing worth guarding, and it occurs zero times in this repo's
        # shell today, so the rule costs nothing.
        #
        # It genuinely overrides the job: the job's env is exported, so
        # reassignment re-exports the new value, and uv reads the VALUE —
        # `UV_FROZEN=1 bash -c 'UV_FROZEN=0; printenv UV_FROZEN'` prints 0.
        if any("UV_FROZEN" in word for word in (written, *args, *assignments)):
            refused.append(
                RefusedCommand(
                    origin=origin,
                    rendered=command.rendered,
                    headline="UV_FROZEN is written inside a shell command",
                    reason="whatever the mechanism, this reassigns a variable the job "
                    "already exports, so uv sees the new value while this guard reads "
                    "the job's `env:` and reports it pinned",
                    fix="set UV_FROZEN only in the job's `env:` block",
                )
            )
            continue

        if name is None:
            continue

        if name == "uv":
            parsed = _uv_option_region(args)
            found.append(
                UvInvocation(
                    origin=origin,
                    rendered=" ".join([name, *args]),
                    subcommand=parsed.subcommand,
                    option_region=parsed.option_region,
                    uncertain=parsed.uncertain,
                    uncertain_reason=parsed.reason,
                    dynamic=parsed.dynamic,
                )
            )
            continue

        if name in _INTERPRETERS:
            payload = _dash_c_payload(args)
            if payload is not None:
                found.extend(
                    _collect_from_shell(payload, origin, workdir, root, seen, inputs, refused)
                )
                continue

        script = None if cwd_moved else _resolve_script(name, written, args, workdir, root)
        if script is not None:
            inputs.add(script)
            if script not in seen:
                seen.add(script)
                found.extend(
                    _collect_from_shell(
                        script.read_text(encoding="utf-8", errors="replace"),
                        origin=str(script.relative_to(root)),
                        workdir=workdir,
                        root=root,
                        seen=seen,
                        inputs=inputs,
                        refused=refused,
                    )
                )
            continue

        # A bare `uv` token sitting in some other command's arguments means a
        # wrapper whose options this guard could not skip (`env -u X uv sync`
        # leaves `-u` as the command name). Prose never reaches here: an echoed
        # mention is one quoted token, not the bare word.
        if "uv" in args:
            refused.append(
                RefusedCommand(
                    origin=origin,
                    rendered=" ".join(tokens),
                    reason=f"uv is invoked through {name!r}, whose options this "
                    "guard cannot skip without an arity table for it",
                )
            )
            continue

        if name in _INTERPRETERS:
            refused.append(
                RefusedCommand(
                    origin=origin,
                    rendered=" ".join(tokens),
                    headline="a shell invocation this guard cannot follow",
                    reason=f"{name!r} runs something that does not resolve to a file in "
                    "this repo"
                    + (
                        ", because an earlier `cd` moved the working directory" if cwd_moved else ""
                    ),
                    fix="invoke the script by a path that resolves from the step's "
                    "`working-directory`, without an intervening `cd`",
                )
            )
            continue

        if name not in _STATE_NEUTRAL_VERBS:
            if name == "set" and not {"-a", "+a", "allexport"} & set(args):
                # Shell OPTIONS (`set -euo pipefail`) touch neither env nor cwd.
                # `set -a` would, by exporting every later assignment, so it is
                # the one form that stays refused.
                continue
            if name == "cd":
                # Not a finding on its own: audit_dependencies.sh opens with a
                # `cd`, and it resolves no further scripts. It only invalidates
                # what comes after.
                cwd_moved = True
                continue
            refused.append(
                RefusedCommand(
                    origin=origin,
                    rendered=" ".join(tokens),
                    headline=f"an unrecognised command verb ({name!r})",
                    reason="this guard accepts only verbs it knows cannot change uv's "
                    "environment or working directory, so anything else — `export`, "
                    "`source`, `eval`, `pushd`, or something newer — fails closed "
                    "instead of passing while it quietly moves the ground",
                    fix=f"if {name!r} genuinely cannot affect UV_FROZEN or the working "
                    "directory, add it to _STATE_NEUTRAL_VERBS with that judgement",
                )
            )
    return found


def _resolve_script(
    name: str, written: str, args: list[str], workdir: Path, root: Path
) -> Path | None:
    """The shell script this command runs, if it is one tracked in this repo.

    Only shell scripts: a uv call made from a Python script is out of reach,
    which errs toward demanding UV_FROZEN (loud) rather than excusing a job
    (silent). See the module docstring.
    """
    if name in _INTERPRETERS:
        # `bash scripts/foo.sh` — the script is the first non-flag argument.
        candidate = next((a for a in args if not a.startswith("-")), None)
    elif name.endswith(".sh"):
        # `./scripts/foo.sh` — the command IS the script, and it must resolve
        # by its written path, not the basename `name` has been reduced to.
        candidate = written
    else:
        return None
    if not candidate:
        return None

    for base in (workdir, root):
        path = (base / candidate).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            continue
        if path.is_file():
            return path
    return None


def audit_workflow(
    path: Path, root: Path = REPO_ROOT, inputs: set[Path] | None = None
) -> list[JobUvUsage]:
    """Census of uv usage and UV_FROZEN declarations, one entry per job.

    ``inputs``, if given, collects every file this read — the workflow, the
    shell scripts it follows, the composite actions it expands. The CI path
    filter that decides whether this guard runs at all must cover all of them
    (see ``test_every_file_this_guard_reads_triggers_the_job_that_runs_it``).
    """
    if inputs is not None:
        inputs.add(path)
    else:
        inputs = set()
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    workflow_declared, workflow_value = _env_value(document, "UV_FROZEN")
    workflow_defaults = (document.get("defaults") or {}).get("run") or {}

    usages: list[JobUvUsage] = []
    for job_id, job in (document.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        job_declared, job_value = _env_value(job, "UV_FROZEN")
        job_defaults = (job.get("defaults") or {}).get("run") or {}
        default_workdir = job_defaults.get("working-directory") or (
            workflow_defaults.get("working-directory")
        )

        invocations: list[UvInvocation] = []
        refused: list[RefusedCommand] = []
        step_frozen: list[str] = []
        seen: set[Path] = set()

        for index, step in enumerate(job.get("steps") or []):
            if not isinstance(step, dict):
                continue
            step_name = step.get("name") or step.get("uses") or f"step {index + 1}"
            if _env_value(step, "UV_FROZEN")[0]:
                step_frozen.append(str(step_name))

            workdir = root / (step.get("working-directory") or default_workdir or ".")
            if step.get("run"):
                invocations.extend(
                    _collect_from_shell(
                        str(step["run"]),
                        origin=f"step {step_name!r}",
                        workdir=workdir,
                        root=root,
                        seen=seen,
                        inputs=inputs,
                        refused=refused,
                    )
                )
            # Local composite actions run their steps inside this job, under
            # this job's env — so their uv commands are this job's uv commands.
            uses = step.get("uses")
            if isinstance(uses, str) and uses.startswith("./"):
                invocations.extend(
                    _collect_from_composite(
                        root / uses[2:], root, seen, str(step_name), inputs, refused
                    )
                )

        usages.append(
            JobUvUsage(
                workflow=path.name,
                job_id=str(job_id),
                invocations=tuple(invocations),
                refused=tuple(refused),
                frozen_scope=("job" if job_declared else "workflow" if workflow_declared else None),
                frozen_value=job_value if job_declared else workflow_value,
                step_frozen=tuple(step_frozen),
            )
        )
    return usages


def _collect_from_composite(
    action_dir: Path,
    root: Path,
    seen: set[Path],
    step_name: str,
    inputs: set[Path],
    refused: list[RefusedCommand],
) -> list[UvInvocation]:
    """uv invocations inside a local composite action's own steps.

    Composite actions nest: a local action may itself `uses:` another local
    action, up to 10 deep. Handling only `run` steps here would let an
    unpinned `uv run` in an INNER action produce no invocations for the
    calling job at all — so the job reads as uv-free and rule 1 never applies.
    ``seen`` doubles as the cycle guard, since A -> B -> A is expressible.
    """
    for filename in ("action.yml", "action.yaml"):
        manifest = action_dir / filename
        if manifest.is_file():
            break
    else:
        return []

    inputs.add(manifest)
    if manifest in seen:
        return []
    seen.add(manifest)

    document = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    found: list[UvInvocation] = []
    for index, step in enumerate((document.get("runs") or {}).get("steps") or []):
        if not isinstance(step, dict):
            continue
        # A composite step's own `env:` overrides the CALLING job's, exactly as
        # a workflow step's does. audit_workflow() has always rejected the
        # workflow-step form; applying it only there was the same one-layer-away
        # miss as the path filter and the recursion (Codex, PR #959).
        declared, value = _env_value(step, "UV_FROZEN")
        if declared:
            refused.append(
                RefusedCommand(
                    origin=f"{manifest.relative_to(root)} (via {step_name!r})",
                    rendered=f"env: UV_FROZEN: {value!r}",
                    headline="UV_FROZEN is set on a composite action's step",
                    reason="a composite step's env overrides the calling job's for that "
                    "step, so this pin neither matches nor is visible from the job that "
                    "carries the invariant",
                    fix="delete it; the calling job's `env:` is the one place this belongs",
                )
            )
        if step.get("run"):
            workdir = root / (step.get("working-directory") or ".")
            found.extend(
                _collect_from_shell(
                    str(step["run"]),
                    origin=f"{manifest.relative_to(root)} (via {step_name!r})",
                    workdir=workdir,
                    root=root,
                    seen=seen,
                    inputs=inputs,
                    refused=refused,
                )
            )
        uses = step.get("uses")
        if isinstance(uses, str) and uses.startswith("./"):
            inner = step.get("name") or uses or f"step {index + 1}"
            found.extend(
                _collect_from_composite(
                    root / uses[2:], root, seen, f"{step_name} -> {inner}", inputs, refused
                )
            )
    return found


# --------------------------------------------------------------------------
# The invariant
# --------------------------------------------------------------------------


def _render(invocations: tuple[UvInvocation, ...], limit: int = 4) -> str:
    lines = [f"      {i.rendered}   [{i.origin}]" for i in invocations[:limit]]
    if len(invocations) > limit:
        lines.append(f"      ... and {len(invocations) - limit} more")
    return "\n".join(lines)


def violations(usage: JobUvUsage) -> list[str]:
    """Every way ``usage`` breaks the invariant, as ready-to-print messages."""
    problems: list[str] = []

    # Rule 0. Before any verdict: refuse the shapes this guard cannot read,
    # rather than reporting a clean result over a command it never saw.
    problems.extend(
        f"{usage.label}: {item.headline} [{item.origin}].\n"
        f"      {item.rendered}\n"
        f"    Why: {item.reason}.\n"
        "    Unhandled, this job's lock goes unpinned while the guard reports clean.\n"
        f"    Fix: {item.fix}."
        for item in usage.refused
    )

    problems.extend(
        f"{usage.label}: a uv option is computed by the shell, so this guard cannot "
        f"see what uv receives [{item.origin}].\n"
        f"      {item.rendered}\n"
        f"    Computed in option position: {', '.join(item.dynamic)}.\n"
        "    Nothing rules out its expanding to --locked or --frozen. Read as an\n"
        "    ordinary argument, rule 2 misses a command that exits 2 under\n"
        "    UV_FROZEN; read as a pin, rule 1 excuses an unpinned job.\n"
        "    Fix: write uv's own options literally. A computed VALUE is fine —\n"
        "    `--output-file $REQ` reads as that flag's value, which is why both\n"
        "    audit jobs pass."
        for item in usage.invocations
        if item.dynamic
    )

    problems.extend(
        f"{usage.label}: cannot tell whether --frozen/--locked belongs to uv or to "
        f"the command uv runs [{item.origin}].\n"
        f"      {item.rendered}\n"
        f"    Why: {item.uncertain_reason}.\n"
        "    A bare `--opt value` pair is indistinguishable from `--flag POSITIONAL`\n"
        "    without an arity table for every uv option — which would be a second,\n"
        "    drifting copy of uv's CLI. Guessing either way is wrong: read it as\n"
        "    uv's and rule 1 excuses an unpinned job; read it as the child's and\n"
        "    rule 2 misses a command that exits 2 under UV_FROZEN.\n"
        "    Fix: write uv's options in `--opt=value` form, which is\n"
        "    self-delimiting, or move the pin to a job-level UV_FROZEN."
        for item in usage.invocations
        if item.ambiguous_pin
    )

    if usage.step_frozen:
        problems.append(
            f"{usage.label}: UV_FROZEN is declared at STEP level "
            f"({', '.join(repr(s) for s in usage.step_frozen)}).\n"
            "    A step-level pin covers that step only, and these jobs run many uv\n"
            "    commands — `uv run` re-locks just like `uv sync`. That is the exact\n"
            "    gap PR #931 left and PR #935 closed.\n"
            '    Fix: move it to the job\'s own `env:` block as `UV_FROZEN: "1"`.'
        )

    if usage.passes_locked and usage.frozen_enabled:
        problems.append(
            f"{usage.label}: passes an explicit --locked AND declares UV_FROZEN "
            f"(at {usage.frozen_scope} level, {usage.frozen_value!r}). uv rejects that:\n"
            "        error: the argument `--locked` cannot be used with `UV_FROZEN`\n"
            "    (exit 2) — so this job would go red on every run.\n"
            "    Fix: drop UV_FROZEN here and pin the sync with an explicit --frozen\n"
            "    flag instead; the --locked below stays the staleness detector.\n"
            f"{_render(usage.locked_invocations)}"
        )

    if usage.passes_locked and usage.unpinned_invocations:
        problems.append(
            f"{usage.label}: passes --locked, so it cannot use UV_FROZEN — but these "
            "uv commands carry no --frozen/--locked of their own\n"
            "    and will rewrite app/uv.lock before the --locked check ever runs:\n"
            f"{_render(usage.unpinned_invocations)}\n"
            "    That is the PR #935 defect exactly: the staleness assertion then holds\n"
            "    against the lock uv itself just wrote, and the required CVE gate goes\n"
            "    green over a stale lock.\n"
            "    Fix: add --frozen to each (NOT --locked — this step is skipped on a\n"
            "    cache hit, so --locked here would make staleness detection depend on\n"
            "    whether the cache was warm)."
        )

    if usage.uses_uv and not usage.passes_locked and not usage.frozen_enabled:
        if usage.frozen_declared:
            detail = (
                f"    UV_FROZEN is declared at {usage.frozen_scope} level but set to "
                f"{usage.frozen_value!r}, which does not enable it."
            )
        else:
            detail = "    No UV_FROZEN in the job's `env:` block (nor the workflow's)."
        problems.append(
            f"{usage.label}: invokes uv without pinning app/uv.lock.\n"
            f"{detail}\n"
            "    Both `uv sync` and `uv run` LOCK before running, so an unpinned job\n"
            "    can rewrite uv.lock and then measure its own fresh resolution — how\n"
            "    the required CVE gate passed vacuously before PR #935.\n"
            '    Fix: add `env:\\n  UV_FROZEN: "1"` at JOB level (not per step).\n'
            f"{_render(usage.invocations)}"
        )

    # Not `elif`: rules 1-3 are independent. But rule 4 is gated on rule 0 —
    # "never invokes uv" is a claim the guard cannot make about a job holding a
    # command it could not read.
    # Rule 2 keys on the VALUE now that uv's semantics are measured
    # (UV_FROZEN=1 conflicts with --locked; UV_FROZEN=0 does not), so a
    # declared-but-off pin would otherwise slip past every rule in a --locked
    # job. Rule 1 already names the value in the non-locked case.
    if usage.frozen_declared and not usage.frozen_enabled and usage.passes_locked:
        problems.append(
            f"{usage.label}: declares UV_FROZEN at {usage.frozen_scope} level as "
            f"{usage.frozen_value!r}, which uv reads as OFF.\n"
            "    Measured on uv 0.10.9: `UV_FROZEN=1` conflicts with --locked,\n"
            "    `UV_FROZEN=0` does not — so this neither pins anything nor\n"
            "    conflicts. It is config that reads as protection and is not.\n"
            "    Fix: delete it. A --locked job pins its sync with --frozen."
        )

    if not usage.uses_uv and not usage.refused and usage.frozen_declared:
        problems.append(
            f"{usage.label}: declares UV_FROZEN (at {usage.frozen_scope} level) but "
            "never invokes uv.\n"
            "    Inert config that reads as protection.\n"
            "    Fix: remove it, or move the uv command back into this job."
        )

    return problems


def _workflow_paths(directory: Path) -> list[Path]:
    """Every workflow file GitHub Actions would run.

    Both suffixes: Actions discovers `.yml` AND `.yaml`, so a `*.yml` glob
    would let `foo.yaml` carry a bare `uv run` past this guard entirely.
    """
    return sorted(p for p in directory.iterdir() if p.suffix in (".yml", ".yaml"))


def _audit_all() -> list[JobUvUsage]:
    return [u for path in _workflow_paths(WORKFLOWS_DIR) for u in audit_workflow(path)]


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


def test_workflows_are_reachable_from_the_test_tree() -> None:
    """The guard fails loudly rather than passing vacuously on a bad path.

    Tests run with cwd=app while the workflows live at the repo root, so a
    wrong `parents[N]` would make every assertion below hold over an empty
    census — a green run that checked nothing.
    """
    assert WORKFLOWS_DIR.is_dir(), (
        f"{WORKFLOWS_DIR} not found — this guard reads the repo-root workflows "
        f"from app/tests/unit/, via parents[3]. Without them it would pass "
        f"vacuously."
    )
    usages = _audit_all()
    assert usages, f"No jobs parsed out of {WORKFLOWS_DIR}"
    assert {u.workflow for u in usages} >= {"ci.yml", "dependency-audit.yml"}


def _py_filter_patterns() -> list[str]:
    """The path globs that decide whether ci.yml's `unit_tests` job runs."""
    document = yaml.safe_load((WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8"))
    for step in document["jobs"]["changes"]["steps"]:
        filters = (step.get("with") or {}).get("filters")
        if filters:
            patterns = yaml.safe_load(filters)["py"]
            assert isinstance(patterns, list) and patterns
            return [str(p) for p in patterns]
    raise AssertionError("ci.yml's `changes` job has no paths-filter step")


def test_every_file_this_guard_reads_triggers_the_job_that_runs_it() -> None:
    """A guard that does not RUN on the change that breaks it protects nothing.

    `unit_tests` is gated on ci.yml's `py` path filter, and the CI gate accepts
    a skipped job as green. So every file this guard reads — the workflows, the
    shell scripts it follows, the composite actions it expands — has to be in
    that filter, or a PR touching only that file sails past in silence. This
    already happened twice: the filter listed `.github/workflows/ci.yml` alone
    (so dependency-audit.yml was unguarded), and then still omitted
    `app/scripts/audit_dependencies.sh`, whose --locked is the ONLY thing
    keeping the CVE-audit jobs out of rule 1 (Codex P1, PR #959).

    Asserting coverage rather than listing it is the point: the guard follows
    whatever the workflows invoke, so the filter is derived from what was
    actually read. Add a script to a workflow and this fails until the filter
    catches up — including through PR #932's osv-scanner rename.
    """
    inputs: set[Path] = set()
    for path in _workflow_paths(WORKFLOWS_DIR):
        audit_workflow(path, inputs=inputs)

    patterns = _py_filter_patterns()
    relative = sorted(str(p.relative_to(REPO_ROOT)) for p in inputs)
    assert relative, "collected no inputs — the traversal recorded nothing"

    uncovered = [rel for rel in relative if not any(PurePath(rel).full_match(p) for p in patterns)]
    assert not uncovered, (
        "These files are read by this guard but do not match ci.yml's `py` path "
        "filter, so a PR touching only them would skip `unit_tests` — and the CI "
        "gate treats a skip as green:\n"
        + "".join(f"    {rel}\n" for rel in uncovered)
        + f"  py filter patterns: {patterns}\n"
        "  Fix: add a pattern covering them to the `py` filter in ci.yml. Prefer a "
        "class ('app/scripts/**/*.sh') over a name, so a rename cannot re-open this."
    )


def test_uv_lock_is_pinned_in_every_workflow_job() -> None:
    """THE INVARIANT. See the module docstring."""
    problems = [message for usage in _audit_all() for message in violations(usage)]
    assert not problems, (
        "GitHub Actions jobs must not let uv rewrite app/uv.lock (PR #935):\n\n"
        + "\n\n".join(problems)
    )


# --- Instrument checks: the detector is live on the real workflows ---------


def test_detector_sees_uv_in_the_real_workflows() -> None:
    """A `uses_uv` that never fires would make the invariant test vacuous."""
    uv_jobs = [u.label for u in _audit_all() if u.uses_uv]
    assert len(uv_jobs) >= 8, f"Expected the uv-using jobs to be found; got {uv_jobs}"
    assert "ci.yml::mypy" in uv_jobs


def test_detector_follows_scripts_to_find_locked() -> None:
    """`--locked` reaches this guard only through a script a job runs.

    No job passes --locked in its own YAML; both that do reach it via
    `bash scripts/audit_dependencies.sh`. If script-following broke, every
    `passes_locked` would go False, rule 2 would stop protecting anything, and
    rule 1 would start demanding the UV_FROZEN that takes those jobs red — so
    this asserts the limb is live without naming the jobs the invariant covers.
    """
    locked = [u for u in _audit_all() if u.passes_locked]
    assert locked, "No job detected as passing --locked — script-following is dead"
    for usage in locked:
        assert not any(i.locked for i in usage.invocations if i.origin.startswith("step ")), (
            f"{usage.label} passes --locked inline; this test's premise (that "
            f"--locked is only reachable through a script) no longer holds"
        )


def test_prose_mentioning_uv_is_not_read_as_a_command() -> None:
    """Guards the direction of error that would silently reopen the hole.

    Both strings below are real lines out of these workflows' run blocks —
    dependency-audit.yml's issue-body help text and ci.yml's docs summary.
    Counting either as evidence would excuse its job from rule 1.
    """
    commands = _split_commands(
        # Escaped backtick: literal to bash, so `uv export` here is prose.
        'echo "- A stale lock (\\`uv export --locked\\` refuses) -> re-lock and commit."\n'
        'echo "  Run locally: uv run python scripts/docs_freshness.py --critical-only"\n'
        "# uv sync --frozen in a comment\n"
    )
    names = [_command_name(tokens)[0] for tokens in commands]
    assert "uv" not in names, f"prose read as a uv command: {commands}"


def test_unescaped_backtick_substitution_is_a_real_command_position() -> None:
    """The complement of the test above, and the reason it must not over-fit.

    Escaping is what makes the line prose. Drop the backslashes and bash
    really does run it — `bash -c 'echo "(`echo X`)"'` prints `(X)` — so this
    must NOT be filtered out along with the prose.
    """
    commands = _split_commands('echo "a (`uv export --locked` refuses) b"')
    assert ("uv", ["export", "--locked"]) in [
        (name, args) for name, _, args in map(_command_name, commands)
    ]


def test_command_positions_are_recovered_through_shell_syntax() -> None:
    """Real run blocks hide uv behind pipes, ||, and command substitution."""
    text = (
        "set -o pipefail\n"
        "uv run mypy . | tee mypy_output.txt\n"
        "uv run python scripts/skills_validator.py || echo 'skills_failed=true'\n"
        'MISSING=$(uv run --locked python scripts/docs_freshness.py --json | python -c "x")\n'
    )
    uv_commands = [
        (name, args) for name, _, args in map(_command_name, _split_commands(text)) if name == "uv"
    ]
    assert len(uv_commands) == 3, uv_commands
    assert [a for _, a in uv_commands if "--locked" in a] == [
        ["run", "--locked", "python", "scripts/docs_freshness.py", "--json"]
    ]


# --- Positive controls: each rule goes RED on a synthetic violation --------


def _write_workflow(tmp_path: Path, body: str) -> Path:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    path = workflows / "synthetic.yml"
    path.write_text(body, encoding="utf-8")
    return path


def _problems(tmp_path: Path, body: str) -> list[str]:
    return [
        message
        for usage in audit_workflow(_write_workflow(tmp_path, body), root=tmp_path)
        for message in violations(usage)
    ]


_PINNED_JOB = """
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      UV_FROZEN: "1"
    steps:
      - run: uv sync --frozen --no-install-project
      - run: uv run pytest tests/unit/
"""


def test_control_a_pinned_job_is_accepted(tmp_path: Path) -> None:
    """Negative control: the shape every uv job in ci.yml has must pass."""
    assert _problems(tmp_path, _PINNED_JOB) == []


def test_control_unpinned_uv_job_is_rejected(tmp_path: Path) -> None:
    """Rule 1: a new job that forgets UV_FROZEN."""
    problems = _problems(tmp_path, _PINNED_JOB.replace('    env:\n      UV_FROZEN: "1"\n', ""))
    assert len(problems) == 1
    assert "invokes uv without pinning app/uv.lock" in problems[0]


def test_control_uv_run_alone_is_enough_to_require_pinning(tmp_path: Path) -> None:
    """`uv run` re-locks too — a job with no `uv sync` is still in scope.

    This is the half PR #931 missed; a guard keyed only on `uv sync` would
    pass here.
    """
    problems = _problems(
        tmp_path,
        """
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - run: uv run python scripts/census.py
""",
    )
    assert len(problems) == 1
    assert "invokes uv without pinning" in problems[0]


def test_control_step_level_pin_is_rejected(tmp_path: Path) -> None:
    """Rule 1, the PR #931 shape: pinned install step, unpinned `uv run`."""
    problems = _problems(
        tmp_path,
        """
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: uv sync --frozen --no-install-project
        env:
          UV_FROZEN: "1"
      - run: uv run pytest tests/unit/
""",
    )
    assert any("declared at STEP level" in p for p in problems)
    assert any("invokes uv without pinning" in p for p in problems)


def test_control_disabled_value_is_rejected(tmp_path: Path) -> None:
    """`UV_FROZEN: "0"` must not read as protection."""
    problems = _problems(tmp_path, _PINNED_JOB.replace('UV_FROZEN: "1"', 'UV_FROZEN: "0"'))
    assert len(problems) == 1
    assert "set to '0'" in problems[0]


def test_control_locked_plus_frozen_is_rejected(tmp_path: Path) -> None:
    """Rule 2: "helpfully" adding UV_FROZEN to the CVE audit job — exit 2."""
    problems = _problems(
        tmp_path,
        """
jobs:
  cve:
    runs-on: ubuntu-latest
    env:
      UV_FROZEN: "1"
    steps:
      - run: uv sync --frozen --no-install-project
      - run: uv export --locked --format requirements.txt
""",
    )
    assert len(problems) == 1
    assert "cannot be used with `UV_FROZEN`" in problems[0]


def test_control_locked_without_frozen_is_accepted(tmp_path: Path) -> None:
    """Negative control: the pip_audit shape must pass."""
    assert (
        _problems(
            tmp_path,
            """
jobs:
  cve:
    runs-on: ubuntu-latest
    steps:
      - run: uv sync --frozen --no-install-project
      - run: uv export --locked --format requirements.txt
""",
        )
        == []
    )


def test_control_the_original_935_defect_is_rejected(tmp_path: Path) -> None:
    """Rule 3, on the literal shape ci.yml::pip_audit had before PR #935.

    The ONLY difference from the accepted job above is the missing --frozen on
    the sync. Rule 2 is satisfied here (no UV_FROZEN alongside --locked) and
    rule 1 does not apply, so this is the case that would slip through a guard
    checking only "is UV_FROZEN set where it should be".
    """
    problems = _problems(
        tmp_path,
        """
jobs:
  pip_audit:
    runs-on: ubuntu-latest
    steps:
      - run: uv sync --no-install-project
      - run: uv export --locked --format requirements.txt
""",
    )
    assert len(problems) == 1
    assert "carry no --frozen/--locked of their own" in problems[0]
    assert "uv sync --no-install-project" in problems[0]


def test_control_child_command_flags_are_not_uv_flags(tmp_path: Path) -> None:
    """`uv run python x.py --locked` gives `--locked` to PYTHON, not to uv.

    Verified on uv 0.10.9 (`uv run [OPTIONS] [COMMAND]`): the child receives
    it and uv still syncs unfrozen. Crediting it to uv is the silent failure —
    the job reads as `--locked`, rule 2 excuses it from UV_FROZEN, and nothing
    pins the lock at all.
    """
    problems = _problems(
        tmp_path,
        """
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: uv run python scripts/census.py --locked --frozen
""",
    )
    assert len(problems) == 1
    assert "invokes uv without pinning" in problems[0]


def test_control_uv_flags_before_the_child_command_still_count(tmp_path: Path) -> None:
    """The complement: uv's OWN options must not be cut away with the child's.

    `uv run --quiet --locked pip-audit --strict` is the real shape inside
    audit_dependencies.sh — `--locked` precedes the child, so it is uv's.
    """
    parsed = _uv_option_region(["run", "--quiet", "--locked", "pip-audit", "--strict"])
    subcommand, region, ambiguous = parsed.subcommand, parsed.option_region, parsed.uncertain
    assert subcommand == "run"
    assert region == ("run", "--quiet", "--locked")
    # The cut follows a flag, so `pip-audit --strict` is the uncertain tail —
    # but no PIN flag is in it, so nothing is reported. Ambiguity alone is not
    # a finding, only ambiguity about a --frozen/--locked.
    assert ambiguous == ("pip-audit", "--strict")


def test_control_a_global_option_value_cannot_pose_as_the_subcommand() -> None:
    """`uv --directory app run …` — `app` is a VALUE, not the subcommand.

    Picking it would make the region span the child's args again.
    """
    parsed = _uv_option_region(["--directory", "app", "run", "python", "x.py", "--locked"])
    subcommand, region = parsed.subcommand, parsed.option_region
    assert subcommand == "run"
    assert "--locked" not in region


def _write_composite(tmp_path: Path, name: str, steps: str) -> None:
    path = tmp_path / ".github" / "actions" / name / "action.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"runs:\n  using: composite\n  steps:\n{steps}", encoding="utf-8")


_COMPOSITE_JOB = """
jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: ./.github/actions/outer
"""


def test_control_uv_behind_an_unskippable_wrapper_is_reported(tmp_path: Path) -> None:
    """`env -u UNUSED uv sync` — stripping `env` leaves `-u` as the command.

    Skipping a wrapper's options needs an arity table per wrapper. Rather than
    grow one (and miss `timeout 60 uv sync` next), the guard reports what it
    cannot read. Silent before (Codex, PR #959).
    """
    for wrapper in ("env -u UNUSED uv sync", "timeout 60 uv sync"):
        problems = _problems(
            tmp_path,
            f"""
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      UV_FROZEN: "1"
    steps:
      - run: {wrapper}
""",
        )
        assert len(problems) == 1, wrapper
        assert "cannot classify" in problems[0], wrapper


def test_control_shell_dash_c_payloads_are_parsed(tmp_path: Path) -> None:
    """`bash -c 'uv sync'` is shell source, not a path to resolve.

    `-c` is exact, so this one is parsed rather than refused — including the
    clustered `-lc` form, which getopt really does accept.
    """
    for command in ("bash -c 'uv sync'", "sh -lc 'uv run pytest tests/'"):
        problems = _problems(
            tmp_path,
            f"""
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: {command}
""",
        )
        assert len(problems) == 1, command
        assert "invokes uv without pinning" in problems[0], command


def test_control_ambiguous_pin_flag_is_reported_not_guessed(tmp_path: Path) -> None:
    """`uv run --with requests --locked python …` — is `requests` the child?

    Without uv's option arity, `--opt value CHILD` and `--flag CHILD` look
    identical. Guessing is wrong either way: read `--locked` as uv's and rule 1
    excuses an unpinned job; read it as the child's and rule 2 misses a command
    that exits 2 under UV_FROZEN — which is what this job would do.
    """
    problems = _problems(
        tmp_path,
        """
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      UV_FROZEN: "1"
    steps:
      - run: uv run --with requests --locked python -c pass
""",
    )
    assert len(problems) == 1
    assert "cannot tell whether --frozen/--locked belongs to uv" in problems[0]


def test_control_global_option_value_naming_a_subcommand_is_reported(
    tmp_path: Path,
) -> None:
    """`uv --directory sync run python x.py --locked` — `sync` is a DIRECTORY.

    It is also a subcommand name, so the scan matched it, the region ran to the
    end of the args, and the child's `--locked` was credited to uv — excusing
    an unpinned job. The same discriminator that guards the child boundary
    guards the subcommand scan (Codex, PR #959).
    """
    problems = _problems(
        tmp_path,
        """
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: uv --directory sync run python x.py --locked
""",
    )
    assert len(problems) == 1
    assert "cannot tell whether --frozen/--locked belongs to uv" in problems[0]
    assert "may be that option's value instead" in problems[0]


def test_control_command_local_uv_frozen_override_is_rejected(tmp_path: Path) -> None:
    """`UV_FROZEN=0 uv sync` under a job pinned to "1" re-locks anyway.

    Measured on uv 0.10.9, uv reads the VALUE, not the presence:
        UV_FROZEN=1 uv export --locked  -> error: cannot be used with UV_FROZEN
        UV_FROZEN=0 uv export --locked  -> runs clean
    So `0` genuinely disables the pin. Stripping the assignment as noise made
    the audit credit the job-level pin to a command that ran without it
    (Codex, PR #959).
    """
    problems = _problems(
        tmp_path,
        """
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      UV_FROZEN: "1"
    steps:
      - run: UV_FROZEN=0 uv sync --no-install-project
""",
    )
    assert len(problems) == 1
    assert "UV_FROZEN is written inside a shell command" in problems[0]


def test_control_command_local_override_is_caught_through_a_script(
    tmp_path: Path,
) -> None:
    """...including when it prefixes a wrapper rather than uv itself.

    `UV_FROZEN=0 bash scripts/x.sh` exports the override to every uv command
    inside the script. Checking only uv-headed commands would be the same
    one-layer-away miss as rounds 2, 3 and 5.
    """
    script = tmp_path / "app" / "scripts" / "build.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("uv sync --no-install-project\n", encoding="utf-8")
    problems = _problems(
        tmp_path,
        """
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      UV_FROZEN: "1"
    steps:
      - working-directory: app
        run: UV_FROZEN=0 bash scripts/build.sh
""",
    )
    assert len(problems) == 1
    assert "UV_FROZEN is written inside a shell command" in problems[0]


def test_control_unrelated_env_prefixes_are_still_ignored(tmp_path: Path) -> None:
    """Only UV_FROZEN matters — `FOO=1 uv sync` must not be reported."""
    assert (
        _problems(
            tmp_path,
            """
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      UV_FROZEN: "1"
    steps:
      - run: FOO=1 CI=true uv sync --no-install-project
""",
        )
        == []
    )


def test_control_disabled_frozen_in_a_locked_job_is_reported(tmp_path: Path) -> None:
    """`UV_FROZEN: "0"` alongside --locked pins nothing AND conflicts with nothing.

    Rule 2 keys on the value now that uv's semantics are measured, so without
    this check a declared-but-off pin would slip past every rule in a --locked
    job while reading, to a human, as protection.
    """
    problems = _problems(
        tmp_path,
        """
jobs:
  cve:
    runs-on: ubuntu-latest
    env:
      UV_FROZEN: "0"
    steps:
      - run: uv sync --frozen --no-install-project
      - run: uv export --locked --format requirements.txt
""",
    )
    assert len(problems) == 1
    assert "which uv reads as OFF" in problems[0]


def test_the_bash_grammar_invents_no_phantom_commands() -> None:
    """The four constructs a hand-written tokenizer mis-split, all real.

    Each produced a phantom "command" — `/..`, `IGNORE_ARGS+=`, the loop
    VARIABLE, the tail of a `[[ … ]]` test — and a verb whitelist judging
    phantoms is unusable. Every line here is lifted from this repo's own
    workflows or audit_dependencies.sh.
    """
    verbs = {
        c.name
        for c in _shell_commands(
            'cd "$(dirname "$0")/.."\n'
            'IGNORE_ARGS+=(--ignore-vuln "$id")\n'
            "for r in $a $b; do echo $r; done\n"
            "[[ $r == success || $r == cancelled ]] && echo ok\n"
        )
        if c.kind == "command"
    }
    assert verbs == {"cd", "dirname", "echo"}, verbs


def test_quote_concatenation_is_resolved_to_what_uv_receives() -> None:
    """`--loc"ked"` IS `--locked` — bash strips the quotes before uv sees it.

    Pure syntax, so it is parsed rather than refused. Reading the raw token
    would have missed a pin flag in plain sight (Codex, PR #959).
    """
    (command,) = [
        c for c in _shell_commands("uv export --loc\"ked\" --form'at' x") if c.name == "uv"
    ]
    assert command.argv == ["export", "--locked", "--format", "x"]


def test_control_shell_computed_uv_option_is_refused(tmp_path: Path) -> None:
    """`uv export "$PIN"` — nothing says $PIN is not `--locked`.

    Not syntax: no parser resolves it. Under a job pinned to "1" uv would exit
    2, and the guard reported clean.
    """
    problems = _problems(
        tmp_path,
        """
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      UV_FROZEN: "1"
    steps:
      - run: |
          PIN=--locked
          uv export "$PIN" --format requirements.txt
""",
    )
    assert len(problems) == 1
    assert "computed by the shell" in problems[0]


def test_control_a_computed_option_value_is_not_refused(tmp_path: Path) -> None:
    """The shape both real audit jobs use, which must stay silent.

    `--output-file $REQ` puts the expansion where a flag's VALUE goes, not
    where a flag goes. Refusing it would redden the CVE gate on main — the
    exact outcome this guard exists to prevent.
    """
    assert (
        _problems(
            tmp_path,
            """
jobs:
  cve:
    runs-on: ubuntu-latest
    steps:
      - run: |
          REQ=$(mktemp)
          uv export --locked --format requirements.txt --output-file "$REQ"
""",
        )
        == []
    )


def test_actions_expressions_are_not_parsed_as_bash() -> None:
    """`${{ … }}` is interpolated by the runner before the shell sees it.

    Left in, it is the only thing in any workflow the grammar cannot parse —
    and an unparsable region is refused, so this would fail two real jobs.
    """
    commands = _shell_commands('x="${{ steps.a.outputs.b }}"\nuv sync --frozen\n')
    assert not [c for c in commands if c.kind == "unparsed"]
    assert [c.name for c in commands if c.kind == "command"] == ["uv"]


def test_control_unparsable_shell_is_refused(tmp_path: Path) -> None:
    """A region the grammar rejects may hold anything, including uv."""
    problems = _problems(
        tmp_path,
        """
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      UV_FROZEN: "1"
    steps:
      - run: "for ((\\n"
""",
    )
    assert any("could not parse" in p for p in problems), problems


def test_control_every_route_to_assigning_uv_frozen_is_refused(tmp_path: Path) -> None:
    """The NAME is guarded, not the mechanism — three rounds' worth of routes.

    Each of these reassigns a variable the job already exports, so bash
    re-exports the new value and uv reads it. Verified, not assumed::

        $ UV_FROZEN=1 bash -c 'UV_FROZEN=0;         printenv UV_FROZEN'  -> 0
        $ UV_FROZEN=1 bash -c 'printf -v UV_FROZEN 0; printenv UV_FROZEN' -> 0
        $ UV_FROZEN=1 bash -c 'read UV_FROZEN <<< 0; printenv UV_FROZEN'  -> 0

    `printf` and `read` are on the state-neutral whitelist for their ordinary
    use, which is exactly why guarding verbs was not enough (Codex, PR #959).
    """
    for mutation in (
        "UV_FROZEN=0",  # bare assignment statement
        "UV_FROZEN=0 uv sync --frozen",  # command prefix
        "printf -v UV_FROZEN 0",  # whitelisted verb, state-mutating mode
        "read UV_FROZEN <<< 0",  # ditto
        'eval "UV_FROZEN=0"',  # not enumerable at all
    ):
        problems = _problems(
            tmp_path,
            f"""
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      UV_FROZEN: "1"
    steps:
      - run: |
          {mutation}
          uv sync --no-install-project
""",
        )
        assert problems, f"{mutation} passed clean"
        assert any("UV_FROZEN" in p for p in problems), mutation


def test_control_export_of_uv_frozen_is_refused(tmp_path: Path) -> None:
    """`export UV_FROZEN=0` unpins every later command in the step.

    `export` is a `declaration_command` in the grammar, never a `command`, so
    the verb whitelist would never have seen it (Codex, PR #959).
    """
    problems = _problems(
        tmp_path,
        """
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      UV_FROZEN: "1"
    steps:
      - run: |
          export UV_FROZEN=0
          uv sync --no-install-project
""",
    )
    assert len(problems) == 1
    assert "environment declaration" in problems[0]


def test_control_writing_uv_frozen_to_github_env_is_refused(tmp_path: Path) -> None:
    """The Actions-native override, which no bash parser would reveal.

    `echo "UV_FROZEN=0" >> $GITHUB_ENV` is idiomatic GitHub Actions: the runner
    exports it to every LATER step. The verb is `echo`, so only the redirection
    TARGET gives it away.
    """
    problems = _problems(
        tmp_path,
        """
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      UV_FROZEN: "1"
    steps:
      - run: echo "UV_FROZEN=0" >> $GITHUB_ENV
      - run: uv sync --no-install-project
""",
    )
    # Two true reports, from two independent rules: the NAME appears in shell,
    # and a $GITHUB_ENV write could carry it even when the name is computed.
    assert any("UV_FROZEN is written inside a shell command" in p for p in problems)
    assert any("$GITHUB_ENV" in p for p in problems)


def test_control_cd_before_a_script_refuses_rather_than_skips(tmp_path: Path) -> None:
    """`cd app && bash scripts/a.sh` moved the ground under resolution.

    The script did not resolve, so it was skipped and its unpinned `uv sync`
    yielded no invocation at all — the job read as uv-free (Codex, PR #959).
    A bare `cd` with no later resolution stays silent: audit_dependencies.sh
    opens with one.
    """
    script = tmp_path / "app" / "scripts" / "a.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("uv sync --no-install-project\n", encoding="utf-8")
    problems = _problems(
        tmp_path,
        """
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: cd app && bash scripts/a.sh
""",
    )
    assert len(problems) == 1
    assert "cannot follow" in problems[0]


def test_control_composite_step_env_is_refused(tmp_path: Path) -> None:
    """A composite step's `env:` overrides the CALLING job's.

    audit_workflow() has always rejected the workflow-step form; applying it
    only there was the same one-layer-away miss as the path filter and the
    recursion (Codex, PR #959).
    """
    action = tmp_path / ".github" / "actions" / "report" / "action.yml"
    action.parent.mkdir(parents=True, exist_ok=True)
    action.write_text(
        "runs:\n  using: composite\n  steps:\n    - run: uv sync\n      shell: bash\n"
        '      env:\n        UV_FROZEN: "0"\n',
        encoding="utf-8",
    )
    problems = _problems(
        tmp_path,
        """
jobs:
  report:
    runs-on: ubuntu-latest
    env:
      UV_FROZEN: "1"
    steps:
      - uses: ./.github/actions/report
""",
    )
    assert any("composite action's step" in p for p in problems), problems


def test_control_uv_version_is_lock_touching(tmp_path: Path) -> None:
    """`uv version <VALUE>` WRITES the version, and writing re-locks.

    uv's own help gives it away: `--frozen` is "Update the version without
    re-locking the project". Classifying `version` as lock-safe let it rewrite
    uv.lock inside a --locked job, making the staleness check vacuous — the
    #935 defect in a second costume (Codex, PR #959).
    """
    problems = _problems(
        tmp_path,
        """
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - run: uv version 1.2.3
      - run: uv export --locked --format requirements.txt
""",
    )
    assert len(problems) == 1
    assert "carry no --frozen/--locked of their own" in problems[0]
    assert "uv version 1.2.3" in problems[0]


def test_control_self_delimiting_options_are_not_ambiguous(tmp_path: Path) -> None:
    """The documented fix must actually clear the report.

    `--with=requests` is self-delimiting, so `python` is unmistakably the child
    and `--locked` unmistakably uv's — which makes this a rule 2 conflict, the
    real defect the ambiguity was hiding.
    """
    problems = _problems(
        tmp_path,
        """
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      UV_FROZEN: "1"
    steps:
      - run: uv run --with=requests --locked python -c pass
""",
    )
    assert len(problems) == 1
    assert "cannot be used with `UV_FROZEN`" in problems[0]


def test_control_ordinary_uv_commands_are_never_reported_as_ambiguous(
    tmp_path: Path,
) -> None:
    """Rule 0 must not fire on the shapes these workflows actually use.

    `uv run --quiet --locked pip-audit --strict` cuts after a flag too, but no
    pin flag lies beyond the cut, so there is nothing to be ambiguous about.
    """
    assert (
        _problems(
            tmp_path,
            """
jobs:
  cve:
    runs-on: ubuntu-latest
    steps:
      - run: uv sync --frozen --no-install-project
      - run: uv run --quiet --locked pip-audit --strict --disable-pip
      - run: uv run --frozen pytest tests/unit/ -x
""",
        )
        == []
    )


def test_control_nested_composite_actions_are_recursed_into(tmp_path: Path) -> None:
    """A local composite may `uses:` another local composite, up to 10 deep.

    Stopping at `run` steps would hide the inner action's uv entirely: the job
    reads as uv-free, rule 1 never applies, and the change to
    `.github/actions/**` triggers this test while it sees nothing (Codex,
    PR #959).
    """
    _write_composite(tmp_path, "outer", "    - uses: ./.github/actions/inner\n")
    _write_composite(
        tmp_path, "inner", "    - run: uv run python app/scripts/report.py\n      shell: bash\n"
    )
    problems = _problems(tmp_path, _COMPOSITE_JOB)
    assert len(problems) == 1
    assert "invokes uv without pinning" in problems[0]
    assert "inner/action.yml" in problems[0]


def test_control_composite_action_cycles_terminate(tmp_path: Path) -> None:
    """A -> B -> A is expressible; the traversal must not recurse forever."""
    _write_composite(
        tmp_path,
        "outer",
        "    - uses: ./.github/actions/inner\n    - run: uv sync\n      shell: bash\n",
    )
    _write_composite(tmp_path, "inner", "    - uses: ./.github/actions/outer\n")
    problems = _problems(tmp_path, _COMPOSITE_JOB)
    assert len(problems) == 1
    assert "invokes uv without pinning" in problems[0]


def test_control_yaml_suffix_workflows_are_audited(tmp_path: Path) -> None:
    """GitHub Actions runs `.yaml` too; a `*.yml` glob would skip it silently."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    body = """
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: uv run pytest tests/unit/
"""
    (workflows / "a.yml").write_text(body, encoding="utf-8")
    (workflows / "b.yaml").write_text(body, encoding="utf-8")
    (workflows / "README.md").write_text("not a workflow\n", encoding="utf-8")

    assert [p.name for p in _workflow_paths(workflows)] == ["a.yml", "b.yaml"]
    flagged = [
        u.label
        for path in _workflow_paths(workflows)
        for u in audit_workflow(path, root=tmp_path)
        if violations(u)
    ]
    assert flagged == ["a.yml::build", "b.yaml::build"]


def test_control_lock_free_uv_subcommands_do_not_need_pinning(tmp_path: Path) -> None:
    """Rule 3 must not demand --frozen from commands that never lock."""
    assert (
        _problems(
            tmp_path,
            """
jobs:
  cve:
    runs-on: ubuntu-latest
    steps:
      - run: uv --version
      - run: uv python install 3.14
      - run: uv export --locked --format requirements.txt
""",
        )
        == []
    )


def test_control_locked_reached_through_a_script_is_accepted(tmp_path: Path) -> None:
    """Rule 2 through the indirection both real jobs actually use.

    Keyed on behaviour, not on `pip_audit` or `audit_dependencies.sh`: rename
    the script (PR #932's osv-scanner migration) and this still holds.
    """
    script = tmp_path / "app" / "scripts" / "scan_dependencies.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "#!/usr/bin/env bash\n"
        "uv export --locked --format requirements.txt --all-groups \\\n"
        "  --no-emit-project > requirements.txt\n"
        "uv run --quiet --locked osv-scanner --lockfile=requirements.txt\n",
        encoding="utf-8",
    )
    body = """
jobs:
  cve:
    runs-on: ubuntu-latest
    steps:
      - working-directory: app
        run: uv sync --frozen --no-install-project
      - working-directory: app
        run: bash scripts/scan_dependencies.sh
"""
    assert _problems(tmp_path, body) == []

    # ... and the same job with UV_FROZEN added is caught through the script.
    frozen = body.replace(
        "    runs-on: ubuntu-latest\n",
        '    runs-on: ubuntu-latest\n    env:\n      UV_FROZEN: "1"\n',
    )
    problems = _problems(tmp_path, frozen)
    assert len(problems) == 1
    assert "cannot be used with `UV_FROZEN`" in problems[0]
    assert "scan_dependencies.sh" in problems[0]


def test_control_directly_executed_script_is_followed(tmp_path: Path) -> None:
    """`./scripts/foo.sh` — no `bash` prefix, so the command IS the path.

    A resolver that reduced this to its basename would look for the script at
    the working directory root, miss it, and stop following — dropping the job
    to "uses no uv" and passing it in silence.
    """
    script = tmp_path / "app" / "scripts" / "scan.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("uv sync --no-install-project\n", encoding="utf-8")
    problems = _problems(
        tmp_path,
        """
jobs:
  cve:
    runs-on: ubuntu-latest
    steps:
      - working-directory: app
        run: ./scripts/scan.sh
""",
    )
    assert len(problems) == 1
    assert "invokes uv without pinning" in problems[0]
    assert "app/scripts/scan.sh" in problems[0]


def test_control_script_that_drops_locked_requires_pinning(tmp_path: Path) -> None:
    """The migration hazard: a replacement scanner that loses --locked.

    Rule 2 stops applying and rule 1 takes over, so the job cannot end up
    covered by neither.
    """
    script = tmp_path / "app" / "scripts" / "scan_dependencies.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("uv run osv-scanner --lockfile=uv.lock\n", encoding="utf-8")
    problems = _problems(
        tmp_path,
        """
jobs:
  cve:
    runs-on: ubuntu-latest
    steps:
      - working-directory: app
        run: bash scripts/scan_dependencies.sh
""",
    )
    assert len(problems) == 1
    assert "invokes uv without pinning" in problems[0]


def test_control_inert_frozen_on_a_uv_free_job_is_rejected(tmp_path: Path) -> None:
    """Rule 4: UV_FROZEN left behind on a job with no uv."""
    problems = _problems(
        tmp_path,
        """
jobs:
  js_tests:
    runs-on: ubuntu-latest
    env:
      UV_FROZEN: "1"
    steps:
      - run: npm ci
""",
    )
    assert len(problems) == 1
    assert "never invokes uv" in problems[0]


def test_control_uv_free_job_without_frozen_is_accepted(tmp_path: Path) -> None:
    """Negative control: js_tests / content_boundary / gate must stay clean."""
    assert (
        _problems(
            tmp_path,
            """
jobs:
  js_tests:
    runs-on: ubuntu-latest
    steps:
      - run: npm ci
      - run: echo "uv run pytest is what the python job does"
""",
        )
        == []
    )


def test_control_workflow_level_env_counts_as_pinned(tmp_path: Path) -> None:
    """A workflow-level pin is strictly wider than a job-level one."""
    assert (
        _problems(
            tmp_path,
            """
env:
  UV_FROZEN: "1"
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: uv run pytest tests/unit/
""",
        )
        == []
    )


def test_control_composite_action_uv_is_attributed_to_the_job(tmp_path: Path) -> None:
    """A local composite action's steps run under the calling job's env."""
    action = tmp_path / ".github" / "actions" / "report" / "action.yml"
    action.parent.mkdir(parents=True, exist_ok=True)
    action.write_text(
        "runs:\n  using: composite\n  steps:\n"
        "    - run: uv run python app/scripts/report.py\n      shell: bash\n",
        encoding="utf-8",
    )
    problems = _problems(
        tmp_path,
        """
jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: ./.github/actions/report
""",
    )
    assert len(problems) == 1
    assert "invokes uv without pinning" in problems[0]
