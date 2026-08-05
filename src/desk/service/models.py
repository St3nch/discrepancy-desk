"""Pydantic input/output models for governed operations."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from desk.service.run_status import RunStatus


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
    created_at: str
    updated_at: str
    lease_expires_at: str | None = None


class CreateRunInput(_StrictModel):
    case_id: int
    question: str
    scope: str
    rubric_version: str | None = None
    rubric_text: str | None = None
    capture_budget: int | None = None


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
    claims_made: int = 0
    is_resume: bool = False
    lease_expires_at: str | None = None
    claim_token: str


class ClaimNextRunResult(_StrictModel):
    """Pull result. Idle is normal — not a refusal.

    When no run is `approved`, `run` is null. Executors poll this constantly;
    treating idle as DeskRefusal would make the happy path look like an error.
    """

    run: ClaimedRunPacket | None


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


class ProposeClaimResult(ClaimRecord):
    pass


class GetCaseResult(_StrictModel):
    """Case detail projection — incomplete by design; grows ticket by ticket."""

    case: CaseRecord
    runs: list[RunRecord]
    captures: list[str]
    claims: list[ClaimRecord]
    open_questions: list[str]
    angles: list[str]
    renditions: list[str]
