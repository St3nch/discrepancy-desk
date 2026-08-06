"""Case coverage gauge — derived readiness reading (VISION / ADR 3 / D20).

Coverage is **derived**, never declared by the executor. A run's coverage
dimension is set by the operator at dispatch and never touched at close_run.
Captures and claims inherit that dimension through run lineage.

It is a **gauge, not a state machine.** Stages may be worked in any order and
revisited; nothing advances, and nothing is locked after a complete reading.

Readings (D20):

| Reading | Meaning |
|---|---|
| unworked | No completed run targets this dimension (producing claims) |
| worked | ≥1 completed run targets it and produced claims |
| complete | Operator attestation stands (not stale) |
| unmeasurable | No first-class measuring object exists yet for this stage |

Measurable today via run.coverage_dimension: official_foundation, deep_context.
Unmeasurable until their tables exist: public_question, story_intelligence,
editorial_development, composition (D20 / F-32 honesty — absence of a table is
not "nobody worked this").

complete is human attestation only. An attestation is stale when any unexamined
capture is on the case (including lead material attached after the fact) — the
reading returns to worked with the reason stated.

Official-foundation gate: assert_official_foundation_complete. Sole intended
call site is ticket 11. Tested at the service seam (F-03).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Connection, func, insert, select

from desk.db.schema import captures, cases, claims, coverage_attestations, runs
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
    attestation = _latest_attestation(conn, case_id, stage)

    # complete only if attested and no unexamined captures on the case.
    # Unexamined material (including lead attaches) makes any attestation stale.
    if attestation is not None and unexamined == 0:
        actor, attested_at = attestation
        signals.append(f"attested by {actor} at {attested_at}")
        return _reading(
            stage=stage,
            label=label,
            reading="complete",
            signals=signals,
            note=None,
        )

    if attestation is not None and unexamined > 0:
        actor, attested_at = attestation
        signals.append(
            f"attestation by {actor} at {attested_at} is stale: "
            f"{unexamined} unexamined capture(s) on the case"
        )
        # Fall through to worked or unworked with the stale reason in signals.

    if completed_runs >= 1 and claim_count >= 1:
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
        else:
            stages.append(
                _unmeasurable_stage(
                    stage_id,
                    label,
                    reason=(
                        "No first-class measuring object exists for this stage yet "
                        "(public questions / Angle Room / angles / renditions arrive "
                        "in later tickets). Absence of that table is not 'unworked' — "
                        "nothing could record the work (D20)."
                    ),
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
    if stage not in _RUN_MEASURABLE_STAGES:
        raise DeskRefusal(
            code="COVERAGE_STAGE_UNMEASURABLE",
            what_happened=(f"Stage {stage!r} has no measuring object yet and cannot be attested."),
            what_was_preserved="Existing attestations are unchanged.",
            what_was_not_changed="No attestation was written.",
            what_you_can_do=(
                "Attest only official_foundation or deep_context until later tickets "
                "introduce measuring objects for other stages."
            ),
        )

    row = conn.execute(select(cases.c.id).where(cases.c.id == params.case_id)).one_or_none()
    if row is None:
        raise DeskRefusal(
            code="CASE_NOT_FOUND",
            what_happened=f"No case exists with id {params.case_id}.",
            what_was_preserved="Existing cases are unchanged.",
            what_was_not_changed="No attestation was written.",
            what_you_can_do="Attest coverage on an existing case_id.",
        )

    actor = (params.actor or "").strip() or "operator"
    # Require worked activity before attestation — judgement about evidence.
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

    **Call site:** ticket 11 angle operations must call this before creating an
    angle or confirming claims into one. Ticket 10 has no angle surface — this
    function is the seam contract those operations will use. Tested here so the
    refusal is proven real (F-03).
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
