"""
UserEntry ingestion helper — bridges YAML files into ``UserEntryService``.

`/upload` and `/submit` are the two front-ends on the same UserEntry creation
pipeline. This module is the bridge for the YAML-driven side: it validates
the per-file frontmatter (pipeline + audience), expands the
``audience: teachers`` default into explicit group UIDs via the
``AudienceResolver``, builds a ``UserEntryCreateRequest``, and delegates to
``UserEntryService.create_entry()`` so every downstream step (Interaction
audit, TRANSFORMS edges, sharing fan-out, compensation delete) is identical
to the form path.

See: /docs/decisions/ADR-054-user-entry-unified-submissions.md
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityStatus
from core.models.enums.metadata_enums import Visibility
from core.models.enums.pipeline import JeUse, Pipeline
from core.models.enums.user_enums import UserRole
from core.models.type_hints import UserUID
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from pathlib import Path

    from core.models.user_entry.user_entry import UserEntry
    from core.services.user_entry.audience_resolver import AudienceResolver
    from core.services.user_entry.user_entry_processing_service import (
        UserEntryProcessingService,
    )
    from core.services.user_entry.user_entry_service import UserEntryService
    from core.services.user_service import UserService

logger = get_logger("skuel.services.ingestion.user_entry")

# /upload is YAML-only — audio pipelines need actual audio bytes, not YAML.
_AUDIO_PIPELINES: frozenset[Pipeline] = frozenset(
    {Pipeline.TRANSCRIBE, Pipeline.TRANSCRIBE_AND_STRUCTURE}
)


def _yaml_pipeline_values() -> str:
    """The ``pipeline:`` values a YAML-ingested UserEntry may declare.

    Every ``Pipeline`` member except the audio two — derived, so the error
    messages below can never drift from the enum (they once named three
    values while the parser admitted seven).
    """
    return ", ".join(p.value for p in Pipeline if p not in _AUDIO_PIPELINES)


@dataclass(frozen=True)
class _AudienceSpec:
    """Parsed `audience:` field. Internal to this module."""

    kind: str  # "teachers" | "group" | "public" | "private"
    group_uid: str | None = None


def _parse_audience(raw: Any, *, default_kind: str) -> Result[_AudienceSpec]:
    """Parse the YAML ``audience:`` field.

    ``default_kind`` is what an absent field means — ``"teachers"`` for
    submission-shaped pipelines, ``"private"`` for the vault-note pipelines
    (``knowledge``, ``extract_activities``) — decided by
    ``Pipeline.shares_by_default`` at the call site, never here.
    """
    if raw is None:
        return Result.ok(_AudienceSpec(kind=default_kind))
    if not isinstance(raw, str):
        return Result.fail(
            Errors.validation(
                f"audience must be a string, got {type(raw).__name__}",
                field="audience",
            )
        )
    value = raw.strip().lower()
    if value == "teachers":
        return Result.ok(_AudienceSpec(kind="teachers"))
    if value == "private":
        return Result.ok(_AudienceSpec(kind="private"))
    if value == "public":
        return Result.ok(_AudienceSpec(kind="public"))
    if value.startswith("group:"):
        group_uid = value[len("group:") :].strip()
        if not group_uid:
            return Result.fail(
                Errors.validation(
                    "audience 'group:' must include a group UID (e.g., group:group_abc)",
                    field="audience",
                )
            )
        return Result.ok(_AudienceSpec(kind="group", group_uid=group_uid))
    return Result.fail(
        Errors.validation(
            f"Unknown audience '{raw}'. Expected one of: teachers, group:<uid>, public, private.",
            field="audience",
        )
    )


def _parse_pipeline(raw: Any, file_name: str) -> Result[Pipeline]:
    """Parse and validate the ``pipeline:`` field for a UserEntry YAML."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return Result.fail(
            Errors.validation(
                f"UserEntry YAML {file_name} is missing required 'pipeline:' field. "
                f"Set one of: {_yaml_pipeline_values()}.",
                field="pipeline",
            )
        )
    if not isinstance(raw, str):
        return Result.fail(
            Errors.validation(
                f"pipeline must be a string, got {type(raw).__name__}",
                field="pipeline",
            )
        )
    value = raw.strip().lower()
    try:
        pipeline = Pipeline(value)
    except ValueError:
        return Result.fail(
            Errors.validation(
                f"Unknown pipeline '{raw}'. Expected one of: {_yaml_pipeline_values()}.",
                field="pipeline",
            )
        )
    if pipeline in _AUDIO_PIPELINES:
        return Result.fail(
            Errors.validation(
                f"pipeline='{pipeline.value}' is an audio pipeline and requires "
                "the audio-upload flow, not /upload (which is YAML-only).",
                field="pipeline",
            )
        )
    return Result.ok(pipeline)


def _parse_status(raw: Any) -> Result[EntityStatus | None]:
    """Parse the optional ``status:`` field for a UserEntry YAML.

    Absent or empty → ``None`` (the service applies its pipeline default:
    SUBMITTED for TEACHER_REVIEW, ACTIVE otherwise). Alias-aware via
    ``EntityStatus.from_string`` (e.g. "in process" → ACTIVE). Unrecognized
    values fail loudly — the honest alternative to silently dropping an
    authored status.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return Result.ok(None)
    status = EntityStatus.from_string(str(raw))
    if status is None:
        return Result.fail(
            Errors.validation(
                f"Unrecognized status '{raw}'. Expected one of: "
                f"{', '.join(s.value for s in EntityStatus)}.",
                field="status",
            )
        )
    return Result.ok(status)


def _parse_je_use(raw: Any) -> Result[JeUse]:
    """Validate the optional ``je_use:`` field (je_pro dual-duty scoping).

    The consent gate itself lives at collection level (``je_pro_skip_reason``
    in ingestion config) — a je_pro file reaching this builder has already
    consented, and the ``je_use`` value governs the DISK-side exemplar loader,
    not the graph node. This validator exists to fail loudly on a typo'd
    value anywhere in the doorway folders — the honest alternative to
    silently ignoring an authored scoping intent.
    """
    je_use = JeUse.from_string(raw)
    if je_use is None:
        return Result.fail(
            Errors.validation(
                f"Unrecognized je_use '{raw}'. Expected one of: "
                f"{', '.join(u.value for u in JeUse)}.",
                field="je_use",
            )
        )
    return Result.ok(je_use)


def _parse_private(raw: Any) -> Result[bool]:
    """Validate the optional ``private:`` field (companion-retrieval opt-out).

    Absent → ``False`` (default retrievable). Only a genuine YAML boolean is
    accepted — a quoted ``"true"``, a stray string, or any other type fails
    loudly (mirroring ``_parse_je_use``): silently ignoring an authored
    privacy intent would be the one unacceptable failure mode here.
    """
    if raw is None:
        return Result.ok(False)
    if isinstance(raw, bool):
        return Result.ok(raw)
    return Result.fail(
        Errors.validation(
            f"private must be a YAML boolean (true/false), got {type(raw).__name__} "
            f"'{raw}'. Quoted values like 'true' are strings — remove the quotes.",
            field="private",
        )
    )


def _verify_declared_ownership(data: dict[str, Any], user_uid: UserUID) -> Result[None]:
    """Validate the optional ``ownership:`` / ``user_uid:`` frontmatter claim.

    Ownership is ALWAYS stamped from the syncing user (the file cannot
    transfer it — that would let YAML smuggle entries into another account).
    The declared field is a consistency check: ``ownership: linguistic76``
    (or canonical ``user_linguistic76``) must match the syncing user;
    a mismatch fails honestly instead of the entry being silently claimed
    by whoever happened to run the sync.
    """
    raw = data.get("ownership") or data.get("user_uid")
    if raw is None or not str(raw).strip():
        return Result.ok(None)
    declared = str(raw).strip()
    canonical = declared if declared.startswith("user_") else f"user_{declared}"
    if canonical != user_uid:
        return Result.fail(
            Errors.forbidden(
                action="ingest user entry with declared ownership",
                reason=(
                    f"File declares ownership '{declared}' but is being synced by "
                    f"'{user_uid}'. Ownership always follows the syncing user — "
                    "fix the frontmatter or sync from the declared account."
                ),
            )
        )
    return Result.ok(None)


async def build_user_entry_request(
    data: dict[str, Any],
    file_path: Path,
    user_uid: UserUID,
    audience_resolver: AudienceResolver,
    user_service: UserService | None = None,
    body: str | None = None,
    prior_uid: str | None = None,
) -> Result[UserEntryCreateRequest]:
    """Validate YAML + build a ``UserEntryCreateRequest`` ready for the service.

    Expands ``audience: teachers`` (the default for submission-shaped
    pipelines — a ``knowledge`` or ``extract_activities`` vault note with no
    ``audience:`` is private, ``Pipeline.shares_by_default``) into explicit
    group UIDs by looking up the
    user's group memberships through the resolver. A user who
    is in no groups gets an empty share list — the entry is persisted but
    private (no compensation delete in that branch, since the absence of
    teachers is a state-of-the-world fact, not a sharing failure).

    ``audience: public`` is gated on ``UserRole.TEACHER`` — a REGISTERED user
    cannot publish portfolio-visible content through YAML upload. The role is
    resolved via ``user_service``; when unavailable the public audience is
    rejected (fail-closed).

    ``prior_uid`` is path-keyed identity for uid-less vault entries: the
    tracker's prior ``path → uid`` row (resolved by the caller). A knowledge
    note with no authored ``uid:`` mints a random uid on first sync; reusing
    that uid on every later sync routes the note through the MERGE-on-uid
    living-entry channel instead of orphaning the old node. Hard-gated (see
    below) — an authored/periodic uid, a turn-in file, or an upload never
    honors it. See: docs/roadmap/done/uidless-vault-entry-identity-upsert.md
    """
    pipeline_result = _parse_pipeline(data.get("pipeline"), file_path.name)
    if pipeline_result.is_error:
        return Result.fail(pipeline_result)
    pipeline = pipeline_result.value

    ownership_check = _verify_declared_ownership(data, user_uid)
    if ownership_check.is_error:
        return Result.fail(ownership_check)

    status_result = _parse_status(data.get("status"))
    if status_result.is_error:
        return Result.fail(status_result)
    authored_status = status_result.value

    je_use_result = _parse_je_use(data.get("je_use"))
    if je_use_result.is_error:
        return Result.fail(je_use_result)

    private_result = _parse_private(data.get("private"))
    if private_result.is_error:
        return Result.fail(private_result)
    private = private_result.value

    audience_result = _parse_audience(
        data.get("audience"),
        default_kind="teachers" if pipeline.shares_by_default() else "private",
    )
    if audience_result.is_error:
        return Result.fail(audience_result)
    audience = audience_result.value

    # Pipelines that don't allow sharing (REFERENCE, TRANSCRIBE_AND_STRUCTURE)
    # are always private — coerce any explicit or defaulted audience to private so
    # reference-archive files don't need `audience: private` in every frontmatter block.
    if not pipeline.allows_sharing():
        audience = _AudienceSpec(kind="private")

    share_with_groups: list[str] = []
    visibility: Visibility | None = None

    if audience.kind == "teachers":
        # Expand to the user's group memberships. Empty list means the user
        # has no groups; entry persists privately with no shares.
        share_with_groups = await audience_resolver.resolve_default_teachers(user_uid)
    elif audience.kind == "group":  # skuel-lint: disable=SKUEL014 -- audience kind, not domain
        assert audience.group_uid is not None  # parser guarantees this
        share_with_groups = [audience.group_uid]
    elif audience.kind == "public":
        role_check = await _require_teacher_for_public(user_uid, user_service)
        if role_check.is_error:
            return Result.fail(role_check)
        visibility = Visibility.PUBLIC
    # "private" → no shares, default visibility

    # Authorization guard on raw UID references before the request is built.
    # Prevents YAML from smuggling arbitrary exercise / predecessor UIDs that
    # the uploader has no legitimate relationship to.
    fulfills_exercise_uid = data.get("fulfills_exercise_uid")
    transforms_of_uid = data.get("transforms_of_uid")
    refs_check = await audience_resolver.validate_references(
        user_uid=user_uid,
        fulfills_exercise_uid=fulfills_exercise_uid,
        transforms_of_uid=transforms_of_uid,
    )
    if refs_check.is_error:
        return Result.fail(refs_check)

    title = data.get("title") or data.get("name") or file_path.stem.replace("-", " ").title()
    raw_description = data.get("description")
    description = None if raw_description is None else str(raw_description)
    tags_raw = data.get("tags") or []
    tags = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else []
    metadata = data.get("metadata") or {}
    if not isinstance(metadata, dict):
        return Result.fail(
            Errors.validation(
                f"metadata must be a mapping, got {type(metadata).__name__}",
                field="metadata",
            )
        )

    # Markdown body capture: a periodic note carries its checkbox lines / prose
    # in the body, not a `content:` field. Explicit `content:` wins — even when
    # falsy (an intentional ``content: ""`` suppresses body capture), so we test
    # key presence, not truthiness; otherwise the parsed body becomes the entry
    # content (so EXTRACT_ACTIVITIES has the `- [ ]` lines to work with).
    content = data.get("content", body)

    # Stamp the vault file path in metadata so VaultReconciler can write back
    # (ID injection, status round-trip). Only for vault/ingested entries that
    # have an absolute file path — upload-side callers pass a temp path.
    ingestion_metadata = dict(metadata)
    if file_path.is_absolute():
        ingestion_metadata["vault_file_path"] = str(file_path)

    # ``moc: true`` rides into metadata as an inert, human-visible marker —
    # nothing queries it (MOC identity is emergent: a node with ORGANIZES
    # edges). The frontmatter flag's one live effect is the edge pass the
    # ingestion door runs post-persist.
    if data.get("moc") is True:
        ingestion_metadata["moc"] = True

    # Derive a deterministic UID for periodic notes so vault-synced files land
    # on the same UID that the calendar routes use:
    # ue:{entry_kind}:{user_uid}:{period_key}.  This makes the SKUEL journal
    # page show Obsidian content rather than a blank placeholder.  Falls back
    # to the explicit `uid:` field, or None (random mint) for non-periodic
    # entries.  The `date:` field is parsed by PyYAML as datetime.date, so
    # .isoformat() normalises it to the string the routes expect.
    uid_override: str | None = data.get("uid")
    if uid_override:
        # Authored uids pass through verbatim (authored = stored; the colon
        # input alias was deleted 2026-08-14). The prefix is opaque
        # provenance, never type information (ADR-013 never-sniff), so any
        # authored DOT/underscore prefix is accepted — but the retired colon
        # spelling is rejected loudly: forwarding it would upsert a NEW node
        # under the colon identity, silently splitting a note previously
        # stored in dot form (Codex P1 #1054). The DERIVED periodic uids
        # below keep their colon form (``ue:daily:{user}:{date}``) by design
        # — internal machine identifiers are BUILT here, never authored; a
        # periodic note needs no ``uid:`` line at all.
        uid_override = str(uid_override)
        if ":" in uid_override:
            return Result.fail(
                Errors.validation(
                    f"Authored uid '{uid_override}' uses the retired colon "
                    f"spelling — author the stored dot form "
                    f"('{uid_override.replace(':', '.')}'), or remove the "
                    f"uid line (periodic notes derive their identity)",
                    field="uid",
                )
            )
    if not uid_override:
        entry_kind = metadata.get("entry_kind") if isinstance(metadata, dict) else None
        if entry_kind == "daily":
            raw_date = data.get("date")
            if raw_date is not None:
                date_str = (
                    raw_date.isoformat()
                    if isinstance(raw_date, (date, datetime))
                    else str(raw_date)
                )
                uid_override = f"ue:daily:{user_uid}:{date_str}"
        elif entry_kind == "weekly":
            week_of = data.get("week_of")
            if week_of is not None:
                uid_override = f"ue:weekly:{user_uid}:{week_of}"
        elif entry_kind == "monthly":
            month_of = data.get("month_of")
            if month_of is not None:
                month_str = (
                    month_of.isoformat()[:7]
                    if isinstance(month_of, (date, datetime))
                    else str(month_of)
                )
                uid_override = f"ue:monthly:{user_uid}:{month_str}"
        elif entry_kind == "quarterly":
            quarter_of = data.get("quarter_of")
            if quarter_of is not None:
                uid_override = f"ue:quarterly:{user_uid}:{quarter_of}"
        elif entry_kind == "yearly":
            year_of = data.get("year_of")
            if year_of is not None:
                # ``year_of: 2026`` parses as an int, ``"2026"`` as a str, and a
                # bare-year date coerces to a date — all three name one year.
                year_str = (
                    f"{year_of.year:04d}"
                    if isinstance(year_of, (date, datetime))
                    else str(year_of).strip()
                )
                uid_override = f"ue:yearly:{user_uid}:{year_str}"

    # Path-keyed identity for uid-less vault entries (contract:
    # docs/roadmap/done/uidless-vault-entry-identity-upsert.md). When the file carries no
    # authored/periodic uid, reuse the tracker's prior uid for this path so the
    # note upserts in place instead of minting a fresh random uid every sync
    # (which orphans the old node — 276 stale copies measured 2026-07-12). Path
    # is already the deletion-propagation identity; updates now honor the same
    # contract. Three hard gates:
    #   - ``uid_override is None`` — an authored ``uid:`` or a derived periodic
    #     uid always wins (never overridden).
    #   - ``fulfills_exercise_uid is None`` — CRITICAL: injecting a uid into a
    #     turn-in request silently kills the turn-in channel
    #     (``user_entry_service.py`` ``turn_in_exercise_uid = None if request.uid
    #     else …``): no frozen copy, no edge, no revision, no teacher routing.
    #   - ``file_path.is_absolute()`` — vault-tracked files only; ``/upload``
    #     callers pass a temp path and must keep minting fresh uids.
    if (
        uid_override is None
        and prior_uid is not None
        and fulfills_exercise_uid is None
        and file_path.is_absolute()
    ):
        uid_override = prior_uid

    request = UserEntryCreateRequest(
        uid=uid_override,
        title=str(title),
        content=content,
        description=description,
        status=authored_status,
        tags=tags,
        metadata=ingestion_metadata,
        pipeline=pipeline,
        private=private,
        instructions=data.get("instructions"),
        fulfills_exercise_uid=fulfills_exercise_uid,
        transforms_of_uid=transforms_of_uid,
        share_with_groups=share_with_groups,
        share_with_users=[],
        visibility=visibility,
    )

    # Pre-validate the assembled request so we surface audience-policy
    # failures (e.g. teacher_review with no resolvable audience for a
    # student in zero groups) before the service runs.
    validate_result = audience_resolver.validate(request)
    if validate_result.is_error:
        return Result.fail(validate_result)

    return Result.ok(request)


async def _require_teacher_for_public(
    user_uid: UserUID,
    user_service: UserService | None,
) -> Result[None]:
    """Reject ``audience: public`` unless the caller is TEACHER or higher."""
    if user_service is None:
        return Result.fail(
            Errors.forbidden(
                action="publish public UserEntry",
                reason=(
                    "'audience: public' requires TEACHER role but role cannot be "
                    "resolved (user_service unavailable)."
                ),
                required_role=UserRole.TEACHER.value,
            )
        )
    user_result = await user_service.get_user(user_uid)
    if user_result.is_error:
        return Result.fail(user_result)
    user = user_result.value
    if user is None or not user.has_permission(UserRole.TEACHER):
        return Result.fail(
            Errors.forbidden(
                action="publish public UserEntry",
                reason=(
                    "'audience: public' requires TEACHER role; this user does not "
                    "have permission to publish."
                ),
                required_role=UserRole.TEACHER.value,
            )
        )
    return Result.ok(None)


async def ingest_user_entry(
    data: dict[str, Any],
    file_path: Path,
    user_uid: UserUID,
    user_entry_service: UserEntryService,
    user_service: UserService | None = None,
    body: str | None = None,
    user_entry_processor: UserEntryProcessingService | None = None,
    prior_uid: str | None = None,
) -> Result[dict[str, Any]]:
    """Ingest a single UserEntry through ``UserEntryService.create_entry()``.

    ``body`` is the parsed markdown body (None for YAML files); it becomes the
    entry ``content`` when no explicit ``content:`` field is present, so a
    periodic note's checkbox lines survive ingestion.

    **Vault exercise channel** (deterministic ``uid:`` + ``fulfills_exercise_uid:``):
    the file is a LIVING entry — one node, upserted in place every sync, the
    exercise declaration stored as intent (never a ``FULFILLS_EXERCISE`` edge).
    Authoring ``status: submitted`` is the deliberate turn-in signal: sync files
    a frozen copy through the existing turn-in machinery (fresh node, edge +
    revision, Interaction, teacher-group routing) — but only when the content
    changed since the last copy, so idle re-syncs while still marked
    ``submitted`` are no-ops and editing while submitted is a re-submission.
    The living entry itself stays ``active`` while the file says ``submitted``
    — it is not in a review queue; the copy carries the truthful ``submitted``
    (the #507 service chokepoint stamps it). Sync never writes into the user's
    file. A submitted copy that reaches no teacher/group is compensated
    (deleted) and surfaced as a sync error — never a silent drop.

    ``user_entry_processor``, when supplied, runs the entry's pipeline after
    persistence. For ``Pipeline.EXTRACT_ACTIVITIES`` this turns the captured
    ``- [ ]`` body lines into Tasks (ADR-069, ``EXTRACTED_FROM`` edges).
    ``force=True`` makes edits re-extract (line-hash dedup is the real
    idempotency guard). Extraction is **failure-isolated**: an error there is
    logged and surfaced in the result dict's ``extraction_error`` field but does
    not fail persistence of the journal node — a re-sync retries.

    ``prior_uid`` (the tracker's prior ``path → uid`` for this file, resolved by
    the caller) gives uid-less vault notes a stable identity: it is reused as
    ``request.uid`` so the note upserts in place rather than orphaning the old
    node each sync. Hard-gated in ``build_user_entry_request`` (authored/periodic
    uid wins; turn-in files and uploads never honor it).

    Returns the standard ingestion result dict (uid, title, entity_type, ...)
    so callers don't need to reach into ``ShareOutcome`` to format a response.
    """
    request_result = await build_user_entry_request(
        data=data,
        file_path=file_path,
        user_uid=user_uid,
        audience_resolver=user_entry_service.audience_resolver,
        user_service=user_service,
        body=body,
        prior_uid=prior_uid,
    )
    if request_result.is_error:
        return Result.fail(request_result)
    request = request_result.value

    # Submit signal: a living-channel file (deterministic uid + declared
    # exercise) authored `status: submitted`. The living upsert proceeds with
    # status ACTIVE — the submitted state belongs to the frozen copy filed
    # below, not to the notebook the user keeps editing.
    submit_signal = bool(
        request.uid and request.fulfills_exercise_uid and request.status == EntityStatus.SUBMITTED
    )
    if submit_signal:
        request = request.model_copy(update={"status": EntityStatus.ACTIVE})

    create_result = await user_entry_service.create_entry(
        request=request,
        user_uid=user_uid,
    )
    if create_result.is_error:
        return Result.fail(create_result)

    entry, outcome = create_result.value

    submitted_copy_uid: str | None = None
    if submit_signal:
        copy_result = await _file_submission_copy(request, entry.uid, user_uid, user_entry_service)
        if copy_result.is_error:
            # Living entry persisted (idempotent); failing the file keeps it
            # out of the tracker's success set so the next sync retries the
            # copy — the honest alternative to a silently unshared turn-in.
            return Result.fail(copy_result)
        submitted_copy_uid = copy_result.value
    logger.info(
        f"Ingested user_entry: {entry.uid} (pipeline={entry.pipeline.value}, "
        f"shared_groups={len(outcome.shared_groups)})"
    )

    # Post-persist pipeline trigger (ADR-069). EXTRACT_ACTIVITIES turns the
    # captured `- [ ]` body lines into Tasks linked back via EXTRACTED_FROM.
    # Failure-isolated: an extraction error never fails the journal node that is
    # already committed — log it and surface it, let a re-sync retry.
    extraction_error: str | None = None
    extraction_warnings: list[str] = []
    if user_entry_processor is not None and entry.pipeline == Pipeline.EXTRACT_ACTIVITIES:
        try:
            # force=True: edits must re-extract (the completed-run guard would
            # else no-op); line-hash dedup remains the idempotency guard.
            process_result = await user_entry_processor.process(entry, force=True)
            if process_result.is_error:
                extraction_error = str(process_result.expect_error())
                logger.warning(
                    f"EXTRACT_ACTIVITIES failed for {entry.uid} (journal persisted): "
                    f"{extraction_error}"
                )
            else:
                # Per-line problems from a run that COMPLETED (partial
                # failures): historically these lived only in the entry-node
                # metadata, invisible to every sync surface (G10). Surface
                # them as warnings — the entry persisted, but the user must
                # see which lines were dropped and why.
                extraction_warnings = _extraction_warnings_from_entry(process_result.value)
        except Exception as exc:  # safety-net: extraction must not unwind persistence
            extraction_error = str(exc)
            logger.exception(f"EXTRACT_ACTIVITIES raised for {entry.uid} (journal persisted)")

    # The FULFILLS_EXERCISE edge only exists when a frozen copy was filed —
    # a living entry's declared exercise is a node property, not an edge.
    is_turn_in = bool(request.fulfills_exercise_uid) and not request.uid
    return Result.ok(
        {
            "uid": entry.uid,
            "title": entry.title,
            "entity_type": "user_entry",
            "format": "yaml",
            "success": True,
            "nodes_created": 2 if submitted_copy_uid else 1,
            "nodes_updated": 0,
            "relationships_created": (
                len(outcome.shared_groups)
                + len(outcome.shared_users)
                + (1 if (is_turn_in or submitted_copy_uid) else 0)
            ),
            # The ingest_file USER_ENTRY branch runs the shared chunk step off
            # these two flags (canon P3 substrate) and overwrites
            # chunks_generated with the real outcome.
            "pipeline": entry.pipeline.value,
            "private": entry.private,
            "chunks_generated": False,
            "share_outcome": outcome.to_payload(),
            "submitted_copy_uid": submitted_copy_uid,
            "extraction_error": extraction_error,
            "extraction_warnings": extraction_warnings,
        }
    )


async def _file_submission_copy(
    request: UserEntryCreateRequest,
    living_uid: str,
    user_uid: UserUID,
    user_entry_service: UserEntryService,
) -> Result[str | None]:
    """File a frozen submission copy for a living entry marked ``submitted``.

    The dedup state is the copies themselves: a new copy is filed only when
    the living content differs from the newest ``FULFILLS_EXERCISE``-bearing
    turn-in's content (no hash bookkeeping to drift; idle re-syncs while the
    file stays ``submitted`` are no-ops). The copy goes through
    ``create_entry`` with no uid — the existing turn-in machinery mints the
    fresh node, edge + revision, Interaction, and teacher-group routing.

    Returns the copy's uid, or ``None`` when content is unchanged since the
    last copy. A copy that reaches no teacher/group is compensated (deleted)
    and returned as an error — Mike's invariant: every exercise has a
    reachable teacher; an unreviewable turn-in is never a silent success.
    """
    exercise_uid = request.fulfills_exercise_uid
    assert exercise_uid is not None  # caller gates on submit_signal

    latest = await user_entry_service.get_latest_entry_for_exercise(user_uid, exercise_uid)
    if latest.is_error:
        return Result.fail(latest)
    if latest.value is not None:
        last_content = str(latest.value.get("content") or "")
        if (request.content or "") == last_content:
            logger.info(
                f"Submit signal on {living_uid}: content unchanged since last "
                f"copy ({latest.value.get('uid')}) — no new submission filed"
            )
            return Result.ok(None)

    copy_request = UserEntryCreateRequest(
        title=request.title,
        content=request.content,
        description=request.description,
        tags=list(request.tags),
        # Provenance only — deliberately NOT vault_file_path: the copy is a
        # frozen artifact, invisible to VaultReconciler write-back.
        metadata={"submitted_from_entry": living_uid},
        pipeline=Pipeline.TEACHER_REVIEW,
        fulfills_exercise_uid=exercise_uid,
    )
    copy_result = await user_entry_service.create_entry(copy_request, user_uid)
    if copy_result.is_error:
        return Result.fail(copy_result)
    copy, copy_outcome = copy_result.value

    if not copy_outcome.any_success:
        # Zero successful shares AND zero failures slips past the service's
        # compensation (which requires an attempted-but-failed target). For
        # the vault channel that silence is an error state: nobody will ever
        # review the copy. Compensate and surface.
        delete_result = await user_entry_service.delete_entry(copy.uid, user_uid)
        if delete_result.is_error:
            logger.error(
                f"Compensation delete of unreachable submission copy {copy.uid} "
                f"failed: {delete_result.expect_error()}"
            )
        return Result.fail(
            Errors.validation(
                f"Submission for exercise {exercise_uid} reached no teacher or "
                "group — the exercise has no reviewer reachable from your "
                "memberships. Fix the exercise's group assignment (or your "
                "enrollment) and re-sync; the living entry itself is saved.",
                field="fulfills_exercise_uid",
            )
        )

    logger.info(
        f"Filed frozen submission copy {copy.uid} for living entry {living_uid} "
        f"(exercise={exercise_uid}, groups={list(copy_outcome.shared_groups)})"
    )
    return Result.ok(copy.uid)


def _extraction_warnings_from_entry(entry: UserEntry | None) -> list[str]:
    """Per-line extraction problems recorded on a COMPLETED run (G10).

    ``UserEntryProcessingService`` stores its run summary under
    ``metadata.activity_extraction``; parse/creation/link errors there mean
    lines were dropped without failing the file. Pull them out so the sync
    stats can show them instead of leaving them buried on the node.
    """
    if entry is None:
        return []
    summary = (entry.metadata or {}).get("activity_extraction")
    if not isinstance(summary, dict):
        return []
    warnings: list[str] = []
    for key in ("parse_errors", "creation_errors", "link_errors", "unrouted_lines", "tag_warnings"):
        for problem in summary.get(key) or []:
            warnings.append(str(problem))
    return warnings


__all__ = ["build_user_entry_request", "ingest_user_entry"]
