"""Pydantic input/output models for governed operations."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from desk.service.run_status import RunStatus

# Coverage vocabulary lives in coverage.py; imported lazily in validators to
# avoid circular imports with CaseCoverageGauge definitions below.


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Case (ticket 02) ---


class CreateCaseInput(_StrictModel):
    title: str


class CaseRecord(_StrictModel):
    case_id: int
    title: str
    created_at: str


class CreateCaseResult(CaseRecord):
    pass


class ListCasesInput(_StrictModel):
    """No filters today; empty input keeps the governed-operation signature uniform."""


class ListCasesResult(_StrictModel):
    cases: list[CaseRecord]


class GetCaseInput(_StrictModel):
    case_id: int


# --- Run (ticket 03) ---


class SuspensionRecord(_StrictModel):
    """One durable mid-flight suspend-and-ask instance (F-28)."""

    suspension_id: int
    run_id: int
    ordinal: int
    question: str
    uncertainty: str
    default_action: str
    suspended_at: str
    human_answer: str | None = None
    answered_at: str | None = None


# D9 / F-29: answering resolves this instance; rubric amendment resolves the class.
INSTANCE_VS_CLASS_NOTICE: str = (
    "This answer resolves this run instance only. If the same uncertainty "
    "keeps recurring, amend the relevant rubric separately."
)


class RunRecord(_StrictModel):
    run_id: int
    case_id: int
    status: RunStatus
    question: str
    scope: str
    rubric_version: str
    rubric_text: str
    capture_budget: int
    captures_used: int
    # Operator-set at dispatch (D20). NULL = pre-D20; never counts toward a stage.
    coverage_dimension: str | None = None
    created_at: str
    updated_at: str
    lease_expires_at: str | None = None
    # Projection of the latest suspension (open or most recently written).
    suspension_question: str | None = None
    suspension_uncertainty: str | None = None
    suspension_default_action: str | None = None
    suspended_at: str | None = None
    human_answer: str | None = None
    answered_at: str | None = None
    # Full ordered history of suspension instances (F-28).
    suspensions: list[SuspensionRecord] = Field(default_factory=list)
    # Set when status is suspended so the operator UI distinguishes remedies (F-29).
    instance_vs_class_notice: str | None = None

    @field_validator("coverage_dimension")
    @classmethod
    def _coverage_dimension_vocab(cls, value: str | None) -> str | None:
        from desk.service.coverage import COVERAGE_STAGE_IDS

        if value is None:
            return None
        if value not in COVERAGE_STAGE_IDS:
            raise ValueError(f"coverage_dimension must be one of {sorted(COVERAGE_STAGE_IDS)}")
        return value


class CreateRunInput(_StrictModel):
    case_id: int
    question: str
    scope: str
    # Required: which coverage dimension this run targets (D20). Human-only at dispatch.
    coverage_dimension: str
    rubric_version: str | None = None
    rubric_text: str | None = None
    capture_budget: int | None = None

    @field_validator("coverage_dimension")
    @classmethod
    def _coverage_dimension_vocab(cls, value: str) -> str:
        from desk.service.coverage import COVERAGE_STAGE_IDS

        if value not in COVERAGE_STAGE_IDS:
            raise ValueError(f"coverage_dimension must be one of {sorted(COVERAGE_STAGE_IDS)}")
        return value


class CreateRunResult(RunRecord):
    pass


class ApproveRunInput(_StrictModel):
    run_id: int


class ApproveRunResult(RunRecord):
    pass


class ListRunsInput(_StrictModel):
    case_id: int


class ListRunsResult(_StrictModel):
    case_id: int
    runs: list[RunRecord]


class ClaimNextRunInput(_StrictModel):
    """Empty input: pull is untargeted (ADR 8)."""


class ClaimedRunPacket(_StrictModel):
    """Work packet handed to an executor on successful claim.

    ``claim_token`` identifies this claim instance (ADR 8 — not an executor id).
    All subsequent run-touching tools must present it.

    ``is_resume`` is true when this run already has captures or claims (lease
    reclaim / second claim). Counts let the executor avoid re-doing work.

    ``coverage_dimension`` is operator-set at dispatch (D20) — read-only for the
    executor; nothing at close_run may change it.
    """

    run_id: int
    case_id: int
    status: RunStatus
    question: str
    scope: str
    rubric_version: str
    rubric_text: str
    capture_budget: int
    captures_used: int
    coverage_dimension: str | None = None
    claims_made: int = 0
    is_resume: bool = False
    lease_expires_at: str | None = None
    claim_token: str
    # Projection + full history so a reclaimer sees every prior answer (F-28).
    suspension_question: str | None = None
    suspension_uncertainty: str | None = None
    suspension_default_action: str | None = None
    human_answer: str | None = None
    suspensions: list[SuspensionRecord] = Field(default_factory=list)


class ClaimNextRunResult(_StrictModel):
    """Pull result. Idle is normal — not a refusal.

    When no run is `approved`, `run` is null. Executors poll this constantly;
    treating idle as DeskRefusal would make the happy path look like an error.
    """

    run: ClaimedRunPacket | None


# --- Suspend / resume / cancel (ticket 07) ---


class SuspendRunInput(_StrictModel):
    """Executor mid-flight: ask the human; run becomes suspended."""

    run_id: int
    claim_token: str
    question: str
    uncertainty: str
    default_action: str


class SuspendRunResult(RunRecord):
    pass


class AnswerSuspendedRunInput(_StrictModel):
    """Human-only: answer a suspended run and return it to claimed."""

    run_id: int
    answer: str


class AnswerSuspendedRunBody(_StrictModel):
    """HTTP path carries run_id; body is the answer only."""

    answer: str


class AnswerSuspendedRunResult(RunRecord):
    pass


class CancelRunInput(_StrictModel):
    """Human-only: kill a run that is not yet complete (F-26)."""

    run_id: int


class CancelRunResult(RunRecord):
    pass


# --- Capture / Vault (ticket 04) ---


class LocatorElement(_StrictModel):
    locator: str
    ordinal: int
    element_type: str
    text: str


class CaptureUrlInput(_StrictModel):
    run_id: int
    url: str
    claim_token: str


class CaptureUrlResult(_StrictModel):
    capture_id: int
    run_id: int
    case_id: int
    url: str
    sha256: str
    content_type: str
    byte_size: int
    status: str
    element_count: int
    elements_returned: int
    truncated: bool
    elements: list[LocatorElement]
    # Generated convenience view — not authoritative for quotation (ADR 1 / ticket 04).
    projection_markdown: str
    projection_is_authoritative: bool = False


class ReadCaptureInput(_StrictModel):
    capture_id: int
    claim_token: str
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=500)


class ReadCaptureResult(_StrictModel):
    capture_id: int
    offset: int
    limit: int
    element_count: int
    elements_returned: int
    truncated: bool
    elements: list[LocatorElement]
    projection_markdown: str
    projection_is_authoritative: bool = False


# --- Claims (ticket 05) ---


class EvidenceDimensions(_StrictModel):
    """Six proposed dimensions (VISION §11). Publication risk is a control, not strength."""

    source_basis: str
    corroboration: str
    certainty: str
    posture: str
    publication_risk: str


class QuoteBindingInput(_StrictModel):
    capture_id: int
    locator: str
    quoted_text: str


class QuoteBindingRecord(_StrictModel):
    capture_id: int
    locator: str
    quoted_text: str
    ordinal: int


class ProposeClaimInput(_StrictModel):
    """propose_claim — quote-bound and/or inference paths.

    Quote path: provide quote_bindings and/or a single capture_id+locator+quoted_text.
    Inference path: source_basis desk_inference with cited_claim_ids (no captures).
    """

    run_id: int
    claim_token: str
    proposition: str
    dimensions: EvidenceDimensions
    qualification: str = ""
    quote_bindings: list[QuoteBindingInput] | None = None
    capture_id: int | None = None
    locator: str | None = None
    quoted_text: str | None = None
    cited_claim_ids: list[int] | None = None


class ClaimRecord(_StrictModel):
    claim_id: int
    case_id: int
    run_id: int
    # Lineage: research question that prompted the introducing run (ticket 08).
    source_run_question: str
    proposition: str
    confirmation_status: str
    source_basis: str
    corroboration: str
    certainty: str
    posture: str
    qualification: str
    publication_risk: str
    rubric_version: str
    quote_bindings: list[QuoteBindingRecord]
    cited_claim_ids: list[int]
    created_at: str
    # Set when human confirms dimensions at angle link (ADR 2 / ticket 11).
    confirmed_at: str | None = None


class ProposeClaimResult(ClaimRecord):
    pass


# --- Run close / open questions (ticket 08 / D13) ---


OPEN_QUESTION_DISPOSITIONS: frozenset[str] = frozenset(
    {
        "unresolved-likely-permanent",
        "unresolved-awaiting-external-development",
        "not-yet-worked",
    }
)

AGENDA_DECISIONS: frozenset[str] = frozenset({"pending", "approved", "rejected", "replaced"})


class ProposedOpenQuestionInput(_StrictModel):
    """One agenda item the executor proposes at close_run."""

    text: str
    rationale: str
    proposed_scope: str


class OpenQuestionRecord(_StrictModel):
    open_question_id: int
    case_id: int
    introduced_by_run_id: int
    source_run_question: str
    ordinal: int
    proposed_text: str
    rationale: str
    proposed_scope: str
    agenda_decision: str
    disposition: str | None = None
    settled_text: str | None = None
    settled_scope: str | None = None
    created_at: str
    decided_at: str | None = None


class CloseRunInput(_StrictModel):
    """Executor close packet.

    ``examined_capture_ids``: uncited captures the executor looked at and found
    nothing worth claiming. Only these become ``examined`` (F-32). Uncited
    captures omitted stay ``unexamined``.
    """

    run_id: int
    claim_token: str
    proposed_questions: list[ProposedOpenQuestionInput] = Field(default_factory=list)
    low_confidence_areas: list[str] = Field(default_factory=list)
    examined_capture_ids: list[int] = Field(default_factory=list)


class CloseRunResult(_StrictModel):
    run: RunRecord
    agenda: list[OpenQuestionRecord]
    captures_count: int
    claims_count: int
    captures_marked_examined: int
    low_confidence_areas: list[str]


class DecideOpenQuestionInput(_StrictModel):
    """Human-only: approve / reject / replace one proposed agenda item."""

    open_question_id: int
    decision: str  # approve | reject | replace
    disposition: str | None = None
    text: str | None = None
    scope: str | None = None


class DecideOpenQuestionBody(_StrictModel):
    """HTTP path carries open_question_id; body is the decision fields."""

    decision: str
    disposition: str | None = None
    text: str | None = None
    scope: str | None = None


class DecideOpenQuestionResult(OpenQuestionRecord):
    pass


class CreateOperatorOpenQuestionInput(_StrictModel):
    """Human-only: operator originates an open question on a completed run (F-31).

    Does not require a prior executor proposal. Settles immediately with disposition.
    """

    run_id: int
    text: str
    scope: str
    disposition: str


class CreateOperatorOpenQuestionBody(_StrictModel):
    """HTTP path carries run_id; body is text/scope/disposition."""

    text: str
    scope: str
    disposition: str


class CreateOperatorOpenQuestionResult(OpenQuestionRecord):
    pass


class CaptureCloseRecord(_StrictModel):
    capture_id: int
    run_id: int
    url: str
    status: str
    created_at: str


class GetRunCloseInput(_StrictModel):
    run_id: int


class GetRunCloseResult(_StrictModel):
    """D13 ordering: agenda → counts → low confidence → detail behind fold."""

    run: RunRecord
    agenda: list[OpenQuestionRecord]
    captures_count: int
    claims_count: int
    low_confidence_areas: list[str]
    # Behind the fold — not the primary decision surface.
    claims: list[ClaimRecord]
    captures: list[CaptureCloseRecord]


class StageCoverageReading(_StrictModel):
    """One stage of the coverage gauge — derived, never declared by the executor."""

    stage: str
    label: str
    reading: str
    signals: list[str] = Field(default_factory=list)
    note: str | None = None

    @field_validator("stage")
    @classmethod
    def _stage_vocab(cls, value: str) -> str:
        from desk.service.coverage import COVERAGE_STAGE_IDS

        if value not in COVERAGE_STAGE_IDS:
            raise ValueError(f"stage must be one of {sorted(COVERAGE_STAGE_IDS)}")
        return value

    @field_validator("reading")
    @classmethod
    def _reading_vocab(cls, value: str) -> str:
        from desk.service.coverage import COVERAGE_READINGS

        if value not in COVERAGE_READINGS:
            raise ValueError(f"reading must be one of {sorted(COVERAGE_READINGS)}")
        return value


class CaseCoverageGauge(_StrictModel):
    """Six-stage readiness reading for a case (VISION; ADR 3 / D20).

    Not a state machine: no ordering, no advancement, stages may be revisited.
    complete is operator attestation, not a count.
    """

    case_id: int
    banner: str
    stages: list[StageCoverageReading]
    official_foundation_complete: bool


class GetCaseCoverageInput(_StrictModel):
    case_id: int


class AttestCoverageInput(_StrictModel):
    """Human-only: attest that a measurable coverage stage is complete (D20).

    ``examined_capture_ids``: unexamined case captures the operator looked at and
    found nothing worth claiming (same act as close_run / F-32). Marked examined
    in this transaction before the unexamined-count refusal is evaluated.
    """

    case_id: int
    stage: str
    actor: str = "operator"
    examined_capture_ids: list[int] = Field(default_factory=list)

    @field_validator("stage")
    @classmethod
    def _stage_vocab(cls, value: str) -> str:
        from desk.service.coverage import COVERAGE_STAGE_IDS

        if value not in COVERAGE_STAGE_IDS:
            raise ValueError(f"stage must be one of {sorted(COVERAGE_STAGE_IDS)}")
        return value


class AttestCoverageBody(_StrictModel):
    """HTTP path carries case_id and stage; body is actor + optional examined ids."""

    actor: str = "operator"
    examined_capture_ids: list[int] = Field(default_factory=list)


class AttestCoverageResult(_StrictModel):
    case_id: int
    stage: str
    actor: str
    attested_at: str
    # Derived reading after this write (complete when successful).
    reading: str
    captures_marked_examined: int
    coverage: CaseCoverageGauge


class AssertOfficialFoundationInput(_StrictModel):
    """Gate for angle work — call before any angle operation (ticket 11)."""

    case_id: int


class AssertOfficialFoundationResult(_StrictModel):
    case_id: int
    official_foundation_complete: bool
    coverage: CaseCoverageGauge


class CaseCaptureSummary(_StrictModel):
    """Thin case-page capture row (id + status + url) for coverage attest UI."""

    capture_id: int
    url: str
    status: str


# --- Angle Room (ticket 11 / ADR 2) ---


class AngleClaimLink(_StrictModel):
    claim_id: int
    ordinal: int
    linked_at: str


class AngleRecord(_StrictModel):
    angle_id: int
    case_id: int
    title: str
    summary: str
    status: str
    dismissal_reason: str | None = None
    dismissed_at: str | None = None
    claim_ids: list[int] = Field(default_factory=list)
    links: list[AngleClaimLink] = Field(default_factory=list)
    created_at: str
    updated_at: str


class LinkClaimDimensions(_StrictModel):
    """Authoritative dimensions when confirming an unconfirmed claim at link time."""

    source_basis: str
    corroboration: str
    certainty: str
    posture: str
    publication_risk: str
    qualification: str = ""


class CreateAngleInput(_StrictModel):
    case_id: int
    title: str
    summary: str = ""
    # Optional initial claims; unconfirmed ones require dimensions_by_claim_id.
    claim_ids: list[int] = Field(default_factory=list)
    dimensions_by_claim_id: dict[int, LinkClaimDimensions] = Field(default_factory=dict)


class CreateAngleResult(AngleRecord):
    pass


class LinkClaimToAngleInput(_StrictModel):
    angle_id: int
    claim_id: int
    # Required when claim is unconfirmed — becomes the authoritative dimensions.
    dimensions: LinkClaimDimensions | None = None


class LinkClaimToAngleBody(_StrictModel):
    """HTTP path carries angle_id; body is claim + optional confirmation dimensions."""

    claim_id: int
    dimensions: LinkClaimDimensions | None = None


class LinkClaimToAngleResult(AngleRecord):
    pass


class DismissAngleInput(_StrictModel):
    angle_id: int
    reason: str


class DismissAngleBody(_StrictModel):
    reason: str


class DismissAngleResult(AngleRecord):
    pass


class ChooseAngleInput(_StrictModel):
    angle_id: int


class ChooseAngleResult(AngleRecord):
    pass


class PublicQuestionClaimLink(_StrictModel):
    claim_id: int
    ordinal: int
    linked_at: str


class PublicQuestionRecord(_StrictModel):
    public_question_id: int
    case_id: int
    question_text: str
    circulating_version: str
    where_asked: str
    origin: str
    claim_ids: list[int] = Field(default_factory=list)
    links: list[PublicQuestionClaimLink] = Field(default_factory=list)
    created_at: str


class CreatePublicQuestionInput(_StrictModel):
    case_id: int
    question_text: str
    circulating_version: str
    where_asked: str
    origin: str
    # Optional initial claims; unconfirmed ones require dimensions_by_claim_id.
    claim_ids: list[int] = Field(default_factory=list)
    dimensions_by_claim_id: dict[int, LinkClaimDimensions] = Field(default_factory=dict)


class CreatePublicQuestionResult(PublicQuestionRecord):
    pass


class LinkClaimToPublicQuestionInput(_StrictModel):
    public_question_id: int
    claim_id: int
    dimensions: LinkClaimDimensions | None = None


class LinkClaimToPublicQuestionBody(_StrictModel):
    claim_id: int
    dimensions: LinkClaimDimensions | None = None


class LinkClaimToPublicQuestionResult(PublicQuestionRecord):
    pass


class QuotationShelfItem(_StrictModel):
    """Operator-selected shelf entry — speaker + attribution frame required."""

    shelf_entry_id: int
    case_id: int
    claim_id: int
    capture_id: int
    locator: str
    quoted_text: str
    speaker: str
    attribution_frame: str
    actor: str
    added_at: str
    confirmation_status: str


class AddQuotationShelfInput(_StrictModel):
    case_id: int
    claim_id: int
    capture_id: int
    locator: str
    quoted_text: str
    speaker: str
    attribution_frame: str
    # Required when claim is unconfirmed.
    dimensions: LinkClaimDimensions | None = None
    actor: str = "operator"


class AddQuotationShelfResult(QuotationShelfItem):
    pass


class RenditionEligibleClaimsInput(_StrictModel):
    """D2 / VISION §14: pool is one angle's linked confirmed claims, not case-wide."""

    angle_id: int


class RenditionEligibleClaimsResult(_StrictModel):
    angle_id: int
    case_id: int
    claims: list[ClaimRecord]


# --- Renditions (ticket 12 / D2 / D7) ---


class RenditionUnitInput(_StrictModel):
    """One ordered unit (e.g. one post in an X thread)."""

    body: str
    claim_ids: list[int] = Field(default_factory=list)


class ProposeRenditionInput(_StrictModel):
    """propose_rendition — executor composes under a claimed run (MCP).

    Backend never calls a model. Units cite only the angle's confirmed claims.
    """

    run_id: int
    claim_token: str
    angle_id: int
    platform: str
    format: str
    units: list[RenditionUnitInput]


class RenditionUnitRecord(_StrictModel):
    unit_id: int
    ordinal: int
    body: str
    claim_ids: list[int]


class RenditionRecord(_StrictModel):
    rendition_id: int
    case_id: int
    angle_id: int
    run_id: int
    platform: str
    format: str
    status: str
    rubric_version: str
    created_at: str
    units: list[RenditionUnitRecord]


class ProposeRenditionResult(RenditionRecord):
    pass


class GetCaseResult(_StrictModel):
    """Case detail projection — incomplete by design; grows ticket by ticket."""

    case: CaseRecord
    runs: list[RunRecord]
    captures: list[CaseCaptureSummary]
    claims: list[ClaimRecord]
    open_questions: list[OpenQuestionRecord]
    coverage: CaseCoverageGauge
    angles: list[AngleRecord]
    public_questions: list[PublicQuestionRecord]
    quotation_shelf: list[QuotationShelfItem]
    renditions: list[RenditionRecord]


# --- Executor case context (ticket 07 / F-27) ---


class ReadCaseContextInput(_StrictModel):
    """Executor: read case material and the run held by this claim_token.

    claim_token proves authority over the held run; it does not itself carry
    decisions. Suspension answers and run state are returned here so the
    executor is never blind after resume, refusal, or any mid-flight event.
    """

    case_id: int
    claim_token: str


class ExecutorHeldRun(_StrictModel):
    """Executor-facing view of the run this claim_token currently holds."""

    run_id: int
    case_id: int
    status: RunStatus
    question: str
    scope: str
    rubric_version: str
    rubric_text: str
    capture_budget: int
    captures_used: int
    # Operator-set at dispatch (D20) — read-only for the executor. NULL if pre-D20.
    coverage_dimension: str | None = None
    claims_made: int
    lease_expires_at: str | None = None
    suspensions: list[SuspensionRecord] = Field(default_factory=list)
    current_suspension: SuspensionRecord | None = None


class ReadCaseContextResult(_StrictModel):
    case: CaseRecord
    held_run: ExecutorHeldRun
    claims: list[ClaimRecord]
    captures: list[CaseCaptureSummary]
    open_questions: list[OpenQuestionRecord]
    angles: list[AngleRecord]
    public_questions: list[PublicQuestionRecord]
    quotation_shelf: list[QuotationShelfItem]
    renditions: list[RenditionRecord]


# --- Lead inbox (ticket 09 / ADR 7 / D18) ---


class LeadRecord(_StrictModel):
    """A URL dropped into the inbox — material only, never claims."""

    lead_id: int
    url: str
    note: str
    summary: str | None = None
    # captured | identity_only | unsupported_type — see LEAD_MATERIAL_STATUSES / D19.
    material_status: str
    capture_id: int | None = None
    # Capture examination status when material_status is captured (always unexamined
    # on drop; no run to mark examined). Null when capture_id is null.
    capture_status: str | None = None
    # open | attached | promoted | disposed
    inbox_status: str
    case_id: int | None = None
    created_at: str
    updated_at: str
    # Present when material was retained (not identity-only).
    sha256: str | None = None
    content_type: str | None = None
    byte_size: int | None = None
    element_count: int | None = None
    # Non-authoritative browse view; never for quotation.
    projection_markdown: str | None = None
    projection_is_authoritative: bool = False


class AddLeadInput(_StrictModel):
    """Drop a URL into the lead inbox. Capture is always attempted (ADR 7).

    Executor (MCP) path: pass run_id + claim_token (lease validated, no budget).
    Operator (API) path: omit both — no run in play.
    """

    url: str
    note: str = ""
    # Required together on the MCP tool surface; omitted on API.
    run_id: int | None = None
    claim_token: str | None = None


class AddLeadResult(LeadRecord):
    pass


class ListLeadsInput(_StrictModel):
    """List leads. Default: open inbox only. Pass inbox_status to filter."""

    inbox_status: str | None = None


class ListLeadsResult(_StrictModel):
    leads: list[LeadRecord]


class AttachLeadInput(_StrictModel):
    """Human-only: attach an open lead to an existing case."""

    lead_id: int
    case_id: int


class AttachLeadBody(_StrictModel):
    """HTTP path carries lead_id; body is case_id only."""

    case_id: int


class AttachLeadResult(LeadRecord):
    pass


class PromoteLeadInput(_StrictModel):
    """Human-only: create a new case from an open lead and attach the lead to it."""

    lead_id: int
    title: str


class PromoteLeadBody(_StrictModel):
    """HTTP path carries lead_id; body is title only."""

    title: str


class PromoteLeadResult(LeadRecord):
    pass


class DisposeLeadInput(_StrictModel):
    """Human-only: dispose an open lead (not worth pursuing)."""

    lead_id: int


class DisposeLeadResult(LeadRecord):
    pass


class SummariseLeadInput(_StrictModel):
    """Human-only: optional summary for browsability. Skippable — never required.

    ``summary`` is description, not claim extraction (ADR 7). Model generation
    may fill this later; today the operator (or a future generator) supplies text.
    """

    lead_id: int
    summary: str


class SummariseLeadBody(_StrictModel):
    """HTTP path carries lead_id; body is the summary text."""

    summary: str


class SummariseLeadResult(LeadRecord):
    pass
