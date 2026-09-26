"""
UserEntry ingestion helper — bridges vault notes into ``UserEntryService``.

The vault and ``/submissions/submit`` are two doors on the same UserEntry creation
pipeline. This module is the vault's: it parses the per-file frontmatter
(pipeline, status, privacy, and ``audience:`` in the one vocabulary —
``AudienceSpec``), builds a ``UserEntryCreateRequest``, and delegates to
``UserEntryService.create_entry()`` so every downstream step (audience
validation and writes, Interaction audit, TRANSFORMS edges, compensation)
is identical to the form path. ``build_user_entry_request`` is pure: no
lookup happens before ``create_entry`` runs them all, once.

Every vault note is a draft (Submit & Share arc R9): one living node,
upserted in place every sync, never submitted or shared. Its ``audience:``
does nothing until ``status: submitted`` files a frozen copy — and the copy,
a fresh node, is what reaches a teacher or a reader.

See: /docs/decisions/ADR-054-user-entry-unified-submissions.md
See: /docs/decisions/ADR-088-submit-and-share.md
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityStatus
from core.models.enums.pipeline import JeUse, Pipeline
from core.models.type_hints import UserUID
from core.models.user_entry.audience import AudienceSpec
from core.models.user_entry.submitted_copy import SubmittedCopy, submission_fingerprint
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.utils.logging import get_logger
from core.utils.result_simplified import ErrorCategory, Errors, Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from pathlib import Path

    from core.models.user_entry.user_entry import UserEntry
    from core.services.user_entry.audience_resolver import ShareOutcome
    from core.services.user_entry.user_entry_processing_service import (
        UserEntryProcessingService,
    )
    from core.services.user_entry.user_entry_service import UserEntryService

logger = get_logger("skuel.services.ingestion.user_entry")

# Vault ingest is text-only — audio pipelines need actual audio bytes.
_AUDIO_PIPELINES: frozenset[Pipeline] = frozenset(
    {Pipeline.TRANSCRIBE, Pipeline.TRANSCRIBE_AND_STRUCTURE}
)
# A vault note is a draft (R9) — the feedback request is its frozen copy.
_VAULT_EXCLUDED: frozenset[Pipeline] = frozenset({Pipeline.TEACHER_REVIEW})


def _yaml_pipeline_values(vault: bool) -> str:
    """The ``pipeline:`` values an ingested UserEntry may declare.

    Every ``Pipeline`` member except the audio two — and, for a vault note,
    except ``teacher_review`` (a vault note is a draft; its frozen copy is
    the submission). Derived, so the error messages below can never drift
    from the enum (they once named three values while the parser admitted
    seven).
    """
    excluded = _AUDIO_PIPELINES | (_VAULT_EXCLUDED if vault else frozenset())
    return ", ".join(p.value for p in Pipeline if p not in excluded)


def _parse_pipeline(raw: Any, file_path: Path) -> Result[Pipeline]:
    """Parse and validate the ``pipeline:`` field for an ingested UserEntry.

    A vault note (an absolute path) may not declare ``teacher_review``: a
    feedback request is always a frozen copy, and a vault note is the draft
    the copy is filed from (R9). Relative paths come only from scripts and
    tests, which file a submission directly.
    """
    vault = file_path.is_absolute()
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return Result.fail(
            Errors.validation(
                f"UserEntry {file_path.name} is missing required 'pipeline:' field. "
                f"Set one of: {_yaml_pipeline_values(vault)}.",
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
                f"Unknown pipeline '{raw}'. Expected one of: {_yaml_pipeline_values(vault)}.",
                field="pipeline",
            )
        )
    if pipeline in _AUDIO_PIPELINES:
        return Result.fail(
            Errors.validation(
                f"pipeline='{pipeline.value}' is an audio pipeline and requires "
                "the audio-upload flow, not vault ingest (which reads text notes).",
                field="pipeline",
            )
        )
    if vault and pipeline == Pipeline.TEACHER_REVIEW:
        return Result.fail(
            Errors.validation(
                "pipeline: teacher_review is not a vault pipeline — a vault note is a "
                "draft. Keep the note on its own pipeline (none, knowledge, …) and set "
                "'status: submitted' to file a frozen copy for your teachers "
                "(audience: teachers, the default).",
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


def build_user_entry_request(
    data: dict[str, Any],
    file_path: Path,
    user_uid: UserUID,
    body: str | None = None,
    prior_uid: str | None = None,
) -> Result[UserEntryCreateRequest]:
    """Parse the frontmatter + build a ``UserEntryCreateRequest`` ready for the service.

    ``audience:`` is parsed by ``AudienceSpec.parse`` — one value or a list,
    in the one vocabulary (``teachers``, ``teacher:<group_uid>``,
    ``group:<uid>``, ``user:<username>``, ``public``, ``private``); case is
    preserved after the colon (a username matches ``User.title`` exactly).
    On a vault note it is the audience of the frozen copy
    ``status: submitted`` files — ``ingest_user_entry`` never applies it to
    the note itself (R9). Nothing is looked up here — ``create_entry``
    validates every target (co-membership, group reach, the ``teachers``
    expansion, the TEACHER gate on ``public``) before it writes.

    Every vault note (an absolute path) carries a uid, so it always takes
    the living channel (``create_entry`` upserts on a caller uid) and never
    the turn-in branch — the frozen copy does. An authored or derived
    periodic uid wins; otherwise ``prior_uid`` — the tracker's prior
    ``path → uid`` row, resolved by the caller — keeps the note on the node
    its earlier syncs wrote; a note synced for the first time mints one.
    See: docs/roadmap/done/uidless-vault-entry-identity-upsert.md
    """
    pipeline_result = _parse_pipeline(data.get("pipeline"), file_path)
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

    audience_result = AudienceSpec.parse(data.get("audience"))
    if audience_result.is_error:
        return Result.fail(audience_result)
    audience = audience_result.value

    # Raw uid references ride onto the request as authored; ``create_entry``
    # verifies the uploader's claim to each (an exercise they may use, a
    # predecessor they own) before anything is written.
    fulfills_exercise_uid = data.get("fulfills_exercise_uid")
    transforms_of_uid = data.get("transforms_of_uid")

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

    # Path-keyed identity for uid-less vault notes (contract:
    # docs/roadmap/done/uidless-vault-entry-identity-upsert.md). When the file
    # carries no authored/periodic uid, reuse the tracker's prior uid for this
    # path so the note upserts in place instead of orphaning the old node, and
    # mint one on the note's first sync so it is a living draft from sync one
    # — with or without a declared exercise: a vault file never enters the
    # turn-in branch, its frozen copy does (R9). An authored or derived
    # periodic uid always wins. Relative paths come only from scripts and
    # tests and keep minting in the service.
    if not uid_override and file_path.is_absolute():
        uid_override = prior_uid or UIDGenerator.generate_random_uid("ue")

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
        audience=audience,
    )
    return Result.ok(request)


# The non-content field a refused frozen copy is reported on
# (``batch.classify_user_entry_failure``): the note itself has synced by the
# time its copy is filed, so a refusal is a sync error to fix, never a note
# "ignored" for its frontmatter.
SUBMISSION_FIELD = "submission"


async def ingest_user_entry(
    data: dict[str, Any],
    file_path: Path,
    user_uid: UserUID,
    user_entry_service: UserEntryService,
    body: str | None = None,
    user_entry_processor: UserEntryProcessingService | None = None,
    prior_uid: str | None = None,
) -> Result[dict[str, Any]]:
    """Ingest a single UserEntry through ``UserEntryService.create_entry()``.

    ``body`` is the parsed markdown body (None for YAML files); it becomes the
    entry ``content`` when no explicit ``content:`` field is present, so a
    periodic note's checkbox lines survive ingestion.

    **A vault note is a draft** (Submit & Share arc R9): one living node,
    upserted in place every sync, never submitted or shared — with or
    without a declared exercise, which it stores as intent (never a
    ``FULFILLS_EXERCISE`` edge). Its ``audience:`` applies only to the frozen
    copy ``status: submitted`` files: after the note syncs, the copy — a
    fresh node through ``create_entry``, with the turn-in edge, revision and
    Interaction when the note declares an exercise — goes to the note's
    audience, ``teachers`` when it names none. A copy is filed only when what
    was authored differs from the note's newest copy (the fingerprint), so an
    idle re-sync while the file still says ``submitted`` files nothing and
    rings no one, and editing while submitted is a re-submission. The note
    itself stays ``active`` while the file says ``submitted``. Sync never
    writes into the user's file. A copy that cannot be filed is a sync error
    on the ``submission`` field and is retried by the next sync.

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
    node each sync (an authored or periodic uid wins; see
    ``build_user_entry_request``).

    Returns the standard ingestion result dict (uid, title, entity_type, ...)
    so callers don't need to reach into ``ShareOutcome`` to format a response.
    ``share_outcome`` is where this sync's audience went — the frozen copy's
    links when one was filed.
    """
    request_result = build_user_entry_request(
        data=data,
        file_path=file_path,
        user_uid=user_uid,
        body=body,
        prior_uid=prior_uid,
    )
    if request_result.is_error:
        return Result.fail(request_result)
    request = request_result.value

    # A caller uid is the living channel — every vault note carries one. It
    # is a draft: its audience rides on the frozen copy alone, and its submit
    # signal is `status: submitted` alone. The note proceeds as ACTIVE — the
    # submitted state belongs to the copy filed below.
    audience = request.audience
    living = bool(request.uid)
    submit_signal = living and request.status == EntityStatus.SUBMITTED
    if living:
        request = request.model_copy(
            update={
                "audience": AudienceSpec(),
                "status": EntityStatus.ACTIVE if submit_signal else request.status,
            }
        )

    create_result = await user_entry_service.create_entry(
        request=request,
        user_uid=user_uid,
    )
    if create_result.is_error:
        return Result.fail(create_result)

    entry, outcome = create_result.value

    warnings: list[str] = []
    if living and not submit_signal and (audience.names_feedback_target or audience.names_share):
        warnings.append(
            f"audience {', '.join(audience.values())} does nothing on a draft — it "
            "applies when 'status: submitted' files a frozen copy"
        )

    copy: UserEntry | None = None
    if submit_signal:
        copy_result = await _file_submission_copy(
            request, audience, entry.uid, user_uid, user_entry_service
        )
        if copy_result.is_error:
            # The note persisted (idempotent); failing the file keeps it out
            # of the tracker's success set so the next sync retries the copy
            # — the honest alternative to a silently unfiled submission.
            return Result.fail(copy_result)
        if copy_result.value is not None:
            copy, outcome = copy_result.value
    logger.info(
        f"Ingested user_entry: {entry.uid} (pipeline={entry.pipeline.value}, "
        f"copy={copy.uid if copy else '-'}, "
        f"submitted_groups={len(outcome.submitted_groups)}, "
        f"shared_groups={len(outcome.shared_groups)})"
    )

    # Post-persist pipeline trigger (ADR-069). EXTRACT_ACTIVITIES turns the
    # captured `- [ ]` body lines into Tasks linked back via EXTRACTED_FROM.
    # Failure-isolated: an extraction error never fails the journal node that is
    # already committed — log it and surface it, let a re-sync retry.
    extraction_error: str | None = None
    reconciliation_refusals = 0
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
                warnings.extend(_extraction_warnings_from_entry(process_result.value))
                reconciliation_refusals = _reconciliation_refusals_of(process_result.value)
        except Exception as exc:  # safety-net: extraction must not unwind persistence
            extraction_error = str(exc)
            logger.exception(f"EXTRACT_ACTIVITIES raised for {entry.uid} (journal persisted)")

    # A FULFILLS_EXERCISE edge exists only on a node filed through the
    # turn-in branch: the frozen copy of a note that declares an exercise, or
    # a script's direct turn-in (no uid). A living note's exercise is intent.
    has_turn_in_edge = bool(request.fulfills_exercise_uid) and (copy is not None or not living)
    return Result.ok(
        {
            "uid": entry.uid,
            "title": entry.title,
            "entity_type": "user_entry",
            "format": "yaml",
            "success": True,
            "nodes_created": 2 if copy else 1,
            "nodes_updated": 0,
            "relationships_created": (
                len(outcome.newly_submitted_groups)
                + len(outcome.shared_groups)
                + len(outcome.shared_users)
                + (1 if has_turn_in_edge else 0)
            ),
            # The ingest_file USER_ENTRY branch runs the shared chunk step off
            # these two flags (canon P3 substrate) and overwrites
            # chunks_generated with the real outcome.
            "pipeline": entry.pipeline.value,
            "private": entry.private,
            "chunks_generated": False,
            "share_outcome": outcome.to_payload(),
            "submitted_copy_uid": copy.uid if copy else None,
            "extraction_error": extraction_error,
            "warnings": warnings,
            # A refused vault edit re-warns every sync until the line and the
            # task agree: the batch door leaves the file un-stamped while this
            # is nonzero, so smart mode re-ingests it next sync (ADR-070
            # Decision 3, R4 C1 — the same standing visibility as an ignored
            # file).
            "reconciliation_refusals": reconciliation_refusals,
        }
    )


async def _file_submission_copy(
    note: UserEntryCreateRequest,
    audience: AudienceSpec,
    note_uid: str,
    user_uid: UserUID,
    user_entry_service: UserEntryService,
) -> Result[tuple[UserEntry, ShareOutcome] | None]:
    """File a frozen copy of a vault note marked ``status: submitted`` (R9).

    The copy is the note's authored snapshot — title, content, description,
    tags, the ``private`` flag and the exercise it answers — sent to the
    note's ``audience:``, ``teachers`` when it names none: on
    ``teacher_review`` when that audience names a teacher (a feedback
    request), otherwise on ``none`` (a share). AI feedback is never
    sync-triggered. The copy is stamped ``submitted`` whatever its pipeline,
    and carries no ``vault_file_path`` — a frozen artifact, invisible to
    write-back.

    Dedup: the copy's fingerprint is compared with the fingerprint stamped
    on the note's newest copy when it was filed — never with that copy's
    live links, so a Stop sharing is not read as an audience edit and does
    not re-file the copy. Equal → ``None``, nothing filed.

    A refused copy is returned on the ``submission`` field when the refusal
    is a validation error (the note has synced — see ``SUBMISSION_FIELD``);
    ``create_entry`` refuses a copy that would reach no teacher before it
    writes, and compensates one whose audience write is refused after.
    """
    if audience.private:
        return _refused(
            "the note says 'status: submitted' but 'audience: private' — nothing to "
            "submit to. Name an audience (teachers is the default), or change the status"
        )
    effective = AudienceSpec(teachers=True) if audience.is_empty else audience
    # The note's pipeline privacy travels with its words: the copy is a
    # plain submission, so the rule `create_entry` enforces on the pipeline
    # is applied here, on the note's.
    if effective.names_share and not note.pipeline.allows_sharing():
        return _refused(
            f"pipeline={note.pipeline.value} is private (journals are not shareable), so "
            "its copy cannot be shared; a feedback request (teachers / "
            "teacher:<group_uid>) is still allowed"
        )

    copy_request = UserEntryCreateRequest(
        title=note.title,
        content=note.content,
        description=note.description,
        tags=list(note.tags),
        private=note.private,
        status=EntityStatus.SUBMITTED,
        pipeline=(Pipeline.TEACHER_REVIEW if effective.names_feedback_target else Pipeline.NONE),
        fulfills_exercise_uid=note.fulfills_exercise_uid,
        audience=effective,
    )
    fingerprint = submission_fingerprint(copy_request)

    latest = await user_entry_service.get_latest_copy_of_note(user_uid, note_uid)
    if latest.is_error:
        return Result.fail(latest)
    if latest.value is not None and latest.value.get("submission_fingerprint") == fingerprint:
        logger.info(
            f"Submit signal on {note_uid}: unchanged since its copy "
            f"{latest.value.get('uid')} — no new copy filed"
        )
        return Result.ok(None)

    copy_result = await user_entry_service.create_entry(
        copy_request,
        user_uid,
        copy_of=SubmittedCopy(submitted_from_uid=note_uid, fingerprint=fingerprint),
    )
    if copy_result.is_error:
        error = copy_result.expect_error()
        if error.category == ErrorCategory.VALIDATION:
            return _refused(error.message)
        return Result.fail(copy_result)
    copy, copy_outcome = copy_result.value

    logger.info(
        f"Filed frozen copy {copy.uid} of vault note {note_uid} "
        f"(pipeline={copy.pipeline.value}, exercise={note.fulfills_exercise_uid or '-'}, "
        f"submitted_groups={list(copy_outcome.submitted_groups)}, "
        f"shared_groups={list(copy_outcome.shared_groups)}, "
        f"shared_users={list(copy_outcome.shared_users)})"
    )
    return Result.ok((copy, copy_outcome))


def _refused(reason: str) -> Result[tuple[UserEntry, ShareOutcome] | None]:
    """A frozen copy that was not filed, on the non-content ``submission`` field."""
    return Result.fail(
        Errors.validation(
            f"'status: submitted' filed no copy — {reason}",
            field=SUBMISSION_FIELD,
        )
    )


def _reconciliation_refusals_of(entry: UserEntry | None) -> int:
    """How many recognised 🆔 lines of a COMPLETED run had their vault edit refused.

    Read off the same run summary as the warnings. Nonzero means at least one
    edge held its base for a retry; the file must not be stamped as
    up-to-date, or the retry — and the warning — would wait for the next
    edit of the note instead of the next sync.
    """
    if entry is None:
        return 0
    summary = (entry.metadata or {}).get("activity_extraction")
    if not isinstance(summary, dict):
        return 0
    return len(summary.get("reconciliation_errors") or [])


def _extraction_warnings_from_entry(entry: UserEntry | None) -> list[str]:
    """Per-line extraction problems recorded on a COMPLETED run (G10).

    ``UserEntryProcessingService`` stores its run summary under
    ``metadata.activity_extraction``; parse/creation/link errors there mean
    lines were dropped without failing the file, and a reconciliation error
    means a vault-side edit of a 🆔 line was refused by the task's domain door
    (its edge holds its base, so it is retried — and re-warned — every sync
    until the line and the task agree; ADR-070 Decision 3, R4). Pull them out
    so the sync stats can show them instead of leaving them buried on the node.
    """
    if entry is None:
        return []
    summary = (entry.metadata or {}).get("activity_extraction")
    if not isinstance(summary, dict):
        return []
    warnings: list[str] = []
    for key in (
        "parse_errors",
        "creation_errors",
        "link_errors",
        "unrouted_lines",
        "tag_warnings",
        "reconciliation_errors",
    ):
        for problem in summary.get(key) or []:
            warnings.append(str(problem))
    return warnings


__all__ = ["SUBMISSION_FIELD", "build_user_entry_request", "ingest_user_entry"]
