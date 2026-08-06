"""Case coverage gauge — derived readiness reading (VISION / ADR 3 / D20).

Coverage is **derived**, never declared by the executor. A run's coverage
dimension is set by the operator at dispatch and never touched at close_run.
Captures and claims inherit that dimension through run lineage.

It is a **gauge, not a state machine.** Stages may be worked in any order and
revisited; nothing advances, and nothing is locked after a complete reading.

Readings (D20):

| Reading | Meaning |
|---|---|
| unworked | No measuring object activity yet |
| worked | Measuring objects present; not (yet) attested complete |
| complete | Operator attestation stands (not stale) |
| unmeasurable | No first-class measuring object exists yet for this stage |

Measurable (D20 + ticket 11 objects):

| Stage | Measuring objects |
|---|---|
| official_foundation | completed runs with coverage_dimension + claims |
| deep_context | completed runs with coverage_dimension + claims |
| public_question | public_questions with ≥1 claim link |
| editorial_development | angles with ≥1 claim link |

Still unmeasurable (no first-class object — explicit decision, not neglect):

| Stage | Why |
|---|---|
| story_intelligence | no table / object yet |
| composition | renditions arrive ticket 12 |

complete is human attestation only. An attestation is stale when any unexamined
capture is on the case (including lead material attached after the fact) — the
reading returns to worked with the reason stated.

Official-foundation gate: assert_official_foundation_complete. Call sites are
ticket 11 Angle Room write paths.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Connection, func, insert, select

from desk.db.schema import (
    angle_claims,
    angles,
    captures,
    cases,
    claims,
    coverage_attestations,
    public_question_claims,
    public_questions,
    runs,
)
from desk.refusals import DeskRefusal
from desk.service.examination import mark_reported_examined
from desk.service.models import (
    AssertOfficialFoundationInput,
    AssertOfficialFoundationResult,
    AttestCoverageInput,
    AttestCoverageResult,
    CaseCoverageGauge,
    GetCaseCoverageInput,
    StageCoverageReading,
)

# Ordered for display only — not a pipeline sequence.
COVERAGE_STAGE_ORDER: tuple[tuple[str, str], ...] = (
    ("official_foundation", "Official foundation"),
    ("public_question", "The public question"),
    ("deep_context", "Deep context"),
    ("story_intelligence", "Story intelligence"),
    ("editorial_development", "Editorial development"),
    ("composition", "Composition"),
)

COVERAGE_STAGE_IDS: frozenset[str] = frozenset(s for s, _ in COVERAGE_STAGE_ORDER)

# Derived readings only — never a declared stage label from the executor.
COVERAGE_READINGS: frozenset[str] = frozenset({"unworked", "worked", "complete", "unmeasurable"})

# Stages measured by completed runs with that coverage_dimension (D20).
_RUN_MEASURABLE_STAGES: frozenset[str] = frozenset({"official_foundation", "deep_context"})

# Stages measured by Angle Room first-class objects (ticket 11 / D20).
_OBJECT_MEASURABLE_STAGES: frozenset[str] = frozenset({"public_question", "editorial_development"})

# Explicit unmeasurable — no measuring object yet (ticket 12 for composition).
_UNMEASURABLE_STAGES: frozenset[str] = frozenset({"story_intelligence", "composition"})

_MEASURABLE_STAGES: frozenset[str] = _RUN_MEASURABLE_STAGES | _OBJECT_MEASURABLE_STAGES

_UNMEASURABLE_REASONS: dict[str, str] = {
    "story_intelligence": (
        "No first-class measuring object for story intelligence yet "
        "(entities/conflicts/timeline tables not built). Absence is not "
        "'unworked' — nothing could record the work (D20)."
    ),
    "composition": (
        "No first-class measuring object for composition yet (renditions "
        "arrive ticket 12). Absence is not 'unworked' (D20)."
    ),
}

_GAUGE_BANNER = (
    "Derived readiness reading from operator-scoped runs and activity beneath "
    "them — not a state machine. Stages may be worked in any order and revisited. "
    "complete is an operator attestation, not a count."
)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _validate_stage(stage: str) -> str:
    if stage not in COVERAGE_STAGE_IDS:
        raise DeskRefusal(
            code="COVERAGE_STAGE_INVALID",
            what_happened=(
                f"coverage stage {stage!r} is not recognised. "
                f"Use one of: {sorted(COVERAGE_STAGE_IDS)}."
            ),
            what_was_preserved="Existing coverage is unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Pass a stage id from the coverage vocabulary.",
        )
    return stage


def _reading(
    *,
    stage: str,
    label: str,
    reading: str,
    signals: list[str],
    note: str | None = None,
) -> StageCoverageReading:
    if reading not in COVERAGE_READINGS:
        raise RuntimeError(f"internal coverage reading {reading!r} not in vocabulary")
    if stage not in COVERAGE_STAGE_IDS:
        raise RuntimeError(f"internal coverage stage {stage!r} not in vocabulary")
    return StageCoverageReading(
        stage=stage,
        label=label,
        reading=reading,
        signals=signals,
        note=note,
    )


def _capture_status_counts(conn: Connection, case_id: int) -> tuple[int, int, int, int]:
    """Return (total, unexamined, examined, cited) for case-owned captures."""
    rows = conn.execute(select(captures.c.status).where(captures.c.case_id == case_id)).all()
    total = len(rows)
    unexamined = sum(1 for r in rows if str(r.status) == "unexamined")
    examined = sum(1 for r in rows if str(r.status) == "examined")
    cited = sum(1 for r in rows if str(r.status) == "cited")
    return total, unexamined, examined, cited


def _dimension_activity(
    conn: Connection,
    case_id: int,
    stage: str,
) -> tuple[int, int]:
    """Return (completed_runs_targeting_stage, claims_from_those_runs).

    Pre-D20 runs have coverage_dimension NULL and never match ``stage``.
    """
    completed_runs = conn.execute(
        select(runs.c.id)
        .where(runs.c.case_id == case_id)
        .where(runs.c.status == "complete")
        .where(runs.c.coverage_dimension == stage)
    ).all()
    run_ids = [int(r.id) for r in completed_runs]
    if not run_ids:
        return 0, 0
    claim_count = int(
        conn.execute(
            select(func.count())
            .select_from(claims)
            .where(claims.c.case_id == case_id)
            .where(claims.c.run_id.in_(run_ids))
        ).scalar_one()
    )
    return len(run_ids), claim_count


def _public_question_activity(conn: Connection, case_id: int) -> tuple[int, int]:
    """Return (public_question_count, questions_with_≥1_claim_link)."""
    pq_n = int(
        conn.execute(
            select(func.count())
            .select_from(public_questions)
            .where(public_questions.c.case_id == case_id)
        ).scalar_one()
    )
    with_links = int(
        conn.execute(
            select(func.count(func.distinct(public_question_claims.c.public_question_id)))
            .select_from(
                public_question_claims.join(
                    public_questions,
                    public_question_claims.c.public_question_id == public_questions.c.id,
                )
            )
            .where(public_questions.c.case_id == case_id)
        ).scalar_one()
    )
    return pq_n, with_links


def _editorial_activity(conn: Connection, case_id: int) -> tuple[int, int]:
    """Return (angle_count, angles_with_≥1_claim_link)."""
    angle_n = int(
        conn.execute(
            select(func.count()).select_from(angles).where(angles.c.case_id == case_id)
        ).scalar_one()
    )
    with_links = int(
        conn.execute(
            select(func.count(func.distinct(angle_claims.c.angle_id)))
            .select_from(angle_claims.join(angles, angle_claims.c.angle_id == angles.c.id))
            .where(angles.c.case_id == case_id)
        ).scalar_one()
    )
    return angle_n, with_links


def _object_stage_worked(conn: Connection, case_id: int, stage: str) -> tuple[bool, list[str]]:
    """Whether an object-backed stage has enough activity to count as worked."""
    if stage == "public_question":
        pq_n, with_links = _public_question_activity(conn, case_id)
        signals = [
            f"{pq_n} public question(s) on the case",
            f"{with_links} with ≥1 claim link",
        ]
        return with_links >= 1, signals
    if stage == "editorial_development":
        angle_n, with_links = _editorial_activity(conn, case_id)
        signals = [
            f"{angle_n} angle(s) on the case",
            f"{with_links} with ≥1 claim link",
        ]
        return with_links >= 1, signals
    raise RuntimeError(f"not an object-backed stage: {stage!r}")


def _latest_attestation(
    conn: Connection,
    case_id: int,
    stage: str,
) -> tuple[str, str] | None:
    """Return (actor, attested_at) for the latest attestation, or None."""
    row = conn.execute(
        select(
            coverage_attestations.c.actor,
            coverage_attestations.c.attested_at,
        )
        .where(coverage_attestations.c.case_id == case_id)
        .where(coverage_attestations.c.stage == stage)
        .order_by(coverage_attestations.c.id.desc())
        .limit(1)
    ).one_or_none()
    if row is None:
        return None
    return str(row.actor), str(row.attested_at)


def _apply_attestation_and_staleness(
    *,
    stage: str,
    label: str,
    unexamined: int,
    signals: list[str],
    is_worked: bool,
    attestation: tuple[str, str] | None,
) -> StageCoverageReading:
    if attestation is not None and unexamined == 0 and is_worked:
        actor, attested_at = attestation
        signals = [*signals, f"attested by {actor} at {attested_at}"]
        return _reading(
            stage=stage,
            label=label,
            reading="complete",
            signals=signals,
            note=None,
        )

    if attestation is not None and unexamined > 0:
        actor, attested_at = attestation
        signals = [
            *signals,
            (
                f"attestation by {actor} at {attested_at} is stale: "
                f"{unexamined} unexamined capture(s) on the case"
            ),
        ]

    if is_worked:
        return _reading(
            stage=stage,
            label=label,
            reading="worked",
            signals=signals,
            note=(
                "Attestation stale — re-examine unexamined material and re-attest."
                if attestation is not None and unexamined > 0
                else None
            ),
        )

    return _reading(
        stage=stage,
        label=label,
        reading="unworked",
        signals=signals,
        note=None,
    )


def _derive_run_measurable_stage(
    conn: Connection,
    *,
    case_id: int,
    stage: str,
    label: str,
    unexamined: int,
    examined: int,
    cited: int,
    capture_total: int,
) -> StageCoverageReading:
    completed_runs, claim_count = _dimension_activity(conn, case_id, stage)
    signals = [
        f"{completed_runs} completed run(s) targeting {stage}",
        f"{claim_count} claim(s) from those runs",
        f"case corpus: {capture_total} capture(s) "
        f"({cited} cited, {examined} examined, {unexamined} unexamined)",
    ]
    is_worked = completed_runs >= 1 and claim_count >= 1
    return _apply_attestation_and_staleness(
        stage=stage,
        label=label,
        unexamined=unexamined,
        signals=signals,
        is_worked=is_worked,
        attestation=_latest_attestation(conn, case_id, stage),
    )


def _derive_object_measurable_stage(
    conn: Connection,
    *,
    case_id: int,
    stage: str,
    label: str,
    unexamined: int,
    examined: int,
    cited: int,
    capture_total: int,
) -> StageCoverageReading:
    is_worked, signals = _object_stage_worked(conn, case_id, stage)
    signals = [
        *signals,
        f"case corpus: {capture_total} capture(s) "
        f"({cited} cited, {examined} examined, {unexamined} unexamined)",
    ]
    return _apply_attestation_and_staleness(
        stage=stage,
        label=label,
        unexamined=unexamined,
        signals=signals,
        is_worked=is_worked,
        attestation=_latest_attestation(conn, case_id, stage),
    )


def _unmeasurable_stage(stage: str, label: str, *, reason: str) -> StageCoverageReading:
    return _reading(
        stage=stage,
        label=label,
        reading="unmeasurable",
        signals=[],
        note=reason,
    )


def derive_case_coverage(conn: Connection, case_id: int) -> CaseCoverageGauge:
    """Derive the six-stage coverage gauge for a case. No writes."""
    capture_total, unexamined, examined, cited = _capture_status_counts(conn, case_id)

    stages: list[StageCoverageReading] = []
    for stage_id, label in COVERAGE_STAGE_ORDER:
        if stage_id in _RUN_MEASURABLE_STAGES:
            stages.append(
                _derive_run_measurable_stage(
                    conn,
                    case_id=case_id,
                    stage=stage_id,
                    label=label,
                    unexamined=unexamined,
                    examined=examined,
                    cited=cited,
                    capture_total=capture_total,
                )
            )
        elif stage_id in _OBJECT_MEASURABLE_STAGES:
            stages.append(
                _derive_object_measurable_stage(
                    conn,
                    case_id=case_id,
                    stage=stage_id,
                    label=label,
                    unexamined=unexamined,
                    examined=examined,
                    cited=cited,
                    capture_total=capture_total,
                )
            )
        else:
            # Explicit unmeasurable set — not "forgot to wire ticket 11 objects".
            assert stage_id in _UNMEASURABLE_STAGES, (
                f"stage {stage_id!r} is neither measurable nor in the explicit "
                "unmeasurable set — update coverage stage classification"
            )
            stages.append(
                _unmeasurable_stage(
                    stage_id,
                    label,
                    reason=_UNMEASURABLE_REASONS[stage_id],
                )
            )

    of = next(s for s in stages if s.stage == "official_foundation")
    return CaseCoverageGauge(
        case_id=case_id,
        banner=_GAUGE_BANNER,
        stages=stages,
        official_foundation_complete=(of.reading == "complete"),
    )


def get_case_coverage(
    conn: Connection,
    params: GetCaseCoverageInput,
) -> CaseCoverageGauge:
    """Governed read: coverage gauge for one case."""
    row = conn.execute(select(cases.c.id).where(cases.c.id == params.case_id)).one_or_none()
    if row is None:
        raise DeskRefusal(
            code="CASE_NOT_FOUND",
            what_happened=f"No case exists with id {params.case_id}.",
            what_was_preserved="Existing cases are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="List cases and open an existing case_id.",
        )
    return derive_case_coverage(conn, params.case_id)


def attest_coverage(
    conn: Connection,
    params: AttestCoverageInput,
) -> AttestCoverageResult:
    """Human-only: record that a measurable stage is complete (D20).

    Refuses while any unexamined capture remains after applying
    ``examined_capture_ids`` in this transaction (same F-32 report as close_run).
    That refusal keeps staleness simple: zero unexamined at write time means
    any later unexamined capture is material that arrived after attestation.
    """
    stage = _validate_stage(params.stage)
    if stage not in _MEASURABLE_STAGES:
        raise DeskRefusal(
            code="COVERAGE_STAGE_UNMEASURABLE",
            what_happened=(f"Stage {stage!r} has no measuring object yet and cannot be attested."),
            what_was_preserved="Existing attestations are unchanged.",
            what_was_not_changed="No attestation was written.",
            what_you_can_do=(
                "Attest only measurable stages: official_foundation, deep_context, "
                "public_question, editorial_development. story_intelligence and "
                "composition remain unmeasurable until their objects exist."
            ),
        )

    row = conn.execute(select(cases.c.id).where(cases.c.id == params.case_id)).one_or_none()
    if row is None:
        raise DeskRefusal(
            code="CASE_NOT_FOUND",
            what_happened=f"No case exists with id {params.case_id}.",
            what_was_preserved="Existing attestations are unchanged.",
            what_was_not_changed="No attestation was written.",
            what_you_can_do="Attest coverage on an existing case_id.",
        )

    actor = (params.actor or "").strip() or "operator"

    # Require worked activity before attestation — judgement about evidence.
    if stage in _RUN_MEASURABLE_STAGES:
        completed_runs, claim_count = _dimension_activity(conn, params.case_id, stage)
        if completed_runs < 1 or claim_count < 1:
            raise DeskRefusal(
                code="COVERAGE_NOT_WORKED",
                what_happened=(
                    f"Stage {stage!r} is not yet worked: need a completed run targeting "
                    f"it that produced claims "
                    f"(have {completed_runs} run(s), {claim_count} claim(s))."
                ),
                what_was_preserved="Existing attestations are unchanged.",
                what_was_not_changed="No attestation was written.",
                what_you_can_do=(
                    "Dispatch and complete a run with this coverage dimension that "
                    "proposes claims, then attest."
                ),
            )
    else:
        is_worked, signals = _object_stage_worked(conn, params.case_id, stage)
        if not is_worked:
            raise DeskRefusal(
                code="COVERAGE_NOT_WORKED",
                what_happened=(
                    f"Stage {stage!r} is not yet worked: "
                    f"{'; '.join(signals)}. "
                    "Object-backed stages require at least one Angle Room object "
                    "with a claim link (VISION §7)."
                ),
                what_was_preserved="Existing attestations are unchanged.",
                what_was_not_changed="No attestation was written.",
                what_you_can_do=(
                    "Create the measuring object and link at least one claim, then attest."
                ),
            )

    # Operator may report examined captures (incl. abandoned-run leftovers) first.
    marked = mark_reported_examined(
        conn,
        case_id=params.case_id,
        capture_ids=list(params.examined_capture_ids),
        run_id=None,
    )

    _, unexamined, _, _ = _capture_status_counts(conn, params.case_id)
    if unexamined > 0:
        raise DeskRefusal(
            code="COVERAGE_UNEXAMINED_REMAIN",
            what_happened=(
                f"Cannot attest {stage!r}: {unexamined} unexamined capture(s) "
                "remain on the case. Attestation is a judgement about evidence "
                "with the evidence in view."
            ),
            what_was_preserved="Existing attestations are unchanged.",
            what_was_not_changed=(
                "No attestation was written; capture statuses are unchanged "
                "(the whole unit of work rolls back)."
            ),
            what_you_can_do=(
                f"Pass all {unexamined} unexamined capture id(s) in "
                "examined_capture_ids (you looked and found nothing worth "
                "claiming), or cite them via claims, then re-attest."
            ),
        )

    now = _utc_now()
    conn.execute(
        insert(coverage_attestations).values(
            case_id=params.case_id,
            stage=stage,
            actor=actor,
            attested_at=now,
        )
    )
    gauge = derive_case_coverage(conn, params.case_id)
    stage_reading = next(s for s in gauge.stages if s.stage == stage)
    return AttestCoverageResult(
        case_id=params.case_id,
        stage=stage,
        actor=actor,
        attested_at=now,
        reading=stage_reading.reading,
        captures_marked_examined=marked,
        coverage=gauge,
    )


def assert_official_foundation_complete(
    conn: Connection,
    params: AssertOfficialFoundationInput,
) -> AssertOfficialFoundationResult:
    """Refuse unless official-foundation coverage reads complete.

    Absolute gate: no angle work before the official spine is complete
    (VISION / ADR 3 / D20). Evaluated against the derived-plus-attested gauge.

    **Call site:** ticket 11 Angle Room write paths call this before creating
    an angle, confirming claims into one, or other gated Angle Room writes.
    """
    gauge = get_case_coverage(conn, GetCaseCoverageInput(case_id=params.case_id))
    if not gauge.official_foundation_complete:
        of = next(s for s in gauge.stages if s.stage == "official_foundation")
        raise DeskRefusal(
            code="OFFICIAL_FOUNDATION_INCOMPLETE",
            what_happened=(
                f"Case {params.case_id} official-foundation coverage reads "
                f"{of.reading!r}; angle work is refused until it reads complete. "
                f"Signals: {'; '.join(of.signals)}."
            ),
            what_was_preserved="Existing cases, captures, claims, and angles are unchanged.",
            what_was_not_changed="No angle was created; no claim was confirmed.",
            what_you_can_do=(
                "Complete research runs targeting official_foundation that produce "
                "claims, examine or cite all case captures, then attest official "
                "foundation complete as operator, then retry angle work."
            ),
        )
    return AssertOfficialFoundationResult(
        case_id=params.case_id,
        official_foundation_complete=True,
        coverage=gauge,
    )
