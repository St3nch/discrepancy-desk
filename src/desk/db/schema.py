"""SQLAlchemy Core table definitions (no ORM). STRICT tables via migrations."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, MetaData, Table, Text

metadata = MetaData()

# Case — durable investigation into one topic. Never completes; no closed state.
# No account_id: one brand per deployment (D17).
cases = Table(
    "cases",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("title", Text, nullable=False),
    Column("created_at", Text, nullable=False),
)

# Run — question-scoped research job (ADR 5, ADR 8).
runs = Table(
    "runs",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("case_id", Integer, ForeignKey("cases.id"), nullable=False),
    Column("status", Text, nullable=False),
    Column("question", Text, nullable=False),
    Column("scope", Text, nullable=False),
    Column("rubric_version", Text, nullable=False),
    Column("rubric_text", Text, nullable=False),
    Column("capture_budget", Integer, nullable=False),
    # Operator-set at dispatch (D20). NULL = pre-D20 run; never counts toward a stage.
    # Not executor-writable; not set at close_run. create_run always sets a value.
    Column("coverage_dimension", Text, nullable=True),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    # ISO-8601 UTC (+00:00); set while status=claimed. Null when not under lease.
    Column("lease_expires_at", Text, nullable=True),
    # Opaque claim-instance token (not executor identity). Cleared on reclaim.
    Column("claim_token", Text, nullable=True),
    # Projection of the latest/open suspension for list rendering (F-28).
    # Authoritative history lives in run_suspensions.
    Column("suspension_question", Text, nullable=True),
    Column("suspension_uncertainty", Text, nullable=True),
    Column("suspension_default_action", Text, nullable=True),
    Column("suspended_at", Text, nullable=True),
    Column("human_answer", Text, nullable=True),
    Column("answered_at", Text, nullable=True),
)

# Operator attestation that a coverage stage is complete (D20 / ticket 10).
# History is append-only; latest row per (case_id, stage) is current intent.
# Derived reading may still show worked if the attestation is stale.
coverage_attestations = Table(
    "coverage_attestations",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("case_id", Integer, ForeignKey("cases.id"), nullable=False),
    Column("stage", Text, nullable=False),
    Column("actor", Text, nullable=False),
    Column("attested_at", Text, nullable=False),
)

# Durable suspend-and-ask instances (ticket 07 / F-28). Ordered per run.
run_suspensions = Table(
    "run_suspensions",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("run_id", Integer, ForeignKey("runs.id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("question", Text, nullable=False),
    Column("uncertainty", Text, nullable=False),
    Column("default_action", Text, nullable=False),
    Column("suspended_at", Text, nullable=False),
    Column("human_answer", Text, nullable=True),
    Column("answered_at", Text, nullable=True),
)

# Vault capture envelope (ADR 1). Raw bytes live on the governed filesystem.
# run_id / case_id nullable: lead captures have neither until attached (ticket 09).
captures = Table(
    "captures",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("run_id", Integer, ForeignKey("runs.id"), nullable=True),
    Column("case_id", Integer, ForeignKey("cases.id"), nullable=True),
    Column("url", Text, nullable=False),
    Column("sha256", Text, nullable=False),
    Column("content_type", Text, nullable=False),
    Column("byte_size", Integer, nullable=False),
    Column("vault_relpath", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("created_at", Text, nullable=False),
)

# Lead inbox (ADR 7 / D18). Holds material, never claims. Unattached to any case
# until the operator attaches or promotes. Capture is always attempted on drop.
leads = Table(
    "leads",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("url", Text, nullable=False),
    Column("note", Text, nullable=False),
    Column("summary", Text, nullable=True),
    Column("material_status", Text, nullable=False),
    Column("capture_id", Integer, ForeignKey("captures.id"), nullable=True),
    Column("inbox_status", Text, nullable=False),
    Column("case_id", Integer, ForeignKey("cases.id"), nullable=True),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)

document_versions = Table(
    "document_versions",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("capture_id", Integer, ForeignKey("captures.id"), nullable=False),
    Column("version_number", Integer, nullable=False),
    Column("parser_name", Text, nullable=False),
    Column("created_at", Text, nullable=False),
)

elements = Table(
    "elements",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("document_version_id", Integer, ForeignKey("document_versions.id"), nullable=False),
    Column("locator", Text, nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("element_type", Text, nullable=False),
    Column("text", Text, nullable=False),
)

# Regions store character spans within an element. Locators may address a range
# as e/{n}/r/{start}-{end} (F-22). Full-span rows (0..len) are still written at capture.
regions = Table(
    "regions",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("element_id", Integer, ForeignKey("elements.id"), nullable=False),
    Column("start_offset", Integer, nullable=False),
    Column("end_offset", Integer, nullable=False),
)

# Claims enter unconfirmed (ADR 2). Confirmation attaches at angle link (ticket 11).
claims = Table(
    "claims",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("case_id", Integer, ForeignKey("cases.id"), nullable=False),
    Column("run_id", Integer, ForeignKey("runs.id"), nullable=False),
    Column("proposition", Text, nullable=False),
    Column("confirmation_status", Text, nullable=False),
    Column("source_basis", Text, nullable=False),
    Column("corroboration", Text, nullable=False),
    Column("certainty", Text, nullable=False),
    Column("posture", Text, nullable=False),
    Column("qualification", Text, nullable=False),
    Column("publication_risk", Text, nullable=False),
    Column("rubric_version", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("confirmed_at", Text, nullable=True),
)

# Durable confirmation history (VISION §18 / F-28). claims columns = projection.
claim_confirmations = Table(
    "claim_confirmations",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("claim_id", Integer, ForeignKey("claims.id"), nullable=False),
    Column("proposed_source_basis", Text, nullable=False),
    Column("proposed_corroboration", Text, nullable=False),
    Column("proposed_certainty", Text, nullable=False),
    Column("proposed_posture", Text, nullable=False),
    Column("proposed_qualification", Text, nullable=False),
    Column("proposed_publication_risk", Text, nullable=False),
    Column("confirmed_source_basis", Text, nullable=False),
    Column("confirmed_corroboration", Text, nullable=False),
    Column("confirmed_certainty", Text, nullable=False),
    Column("confirmed_posture", Text, nullable=False),
    Column("confirmed_qualification", Text, nullable=False),
    Column("confirmed_publication_risk", Text, nullable=False),
    Column("actor", Text, nullable=False),
    Column("confirmed_at", Text, nullable=False),
)

# Angle Room (ticket 11). Angles link claims; dismissals are durable.
angles = Table(
    "angles",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("case_id", Integer, ForeignKey("cases.id"), nullable=False),
    Column("title", Text, nullable=False),
    Column("summary", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("dismissal_reason", Text, nullable=True),
    Column("dismissed_at", Text, nullable=True),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)

angle_claims = Table(
    "angle_claims",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("angle_id", Integer, ForeignKey("angles.id"), nullable=False),
    Column("claim_id", Integer, ForeignKey("claims.id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("linked_at", Text, nullable=False),
)

public_questions = Table(
    "public_questions",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("case_id", Integer, ForeignKey("cases.id"), nullable=False),
    Column("question_text", Text, nullable=False),
    Column("circulating_version", Text, nullable=False),
    Column("where_asked", Text, nullable=False),
    Column("origin", Text, nullable=False),
    Column("created_at", Text, nullable=False),
)

public_question_claims = Table(
    "public_question_claims",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("public_question_id", Integer, ForeignKey("public_questions.id"), nullable=False),
    Column("claim_id", Integer, ForeignKey("claims.id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("linked_at", Text, nullable=False),
)

# Operator-selected quotations (VISION Angle Room — not an auto-dump of bindings).
quotation_shelf_entries = Table(
    "quotation_shelf_entries",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("case_id", Integer, ForeignKey("cases.id"), nullable=False),
    Column("claim_id", Integer, ForeignKey("claims.id"), nullable=False),
    Column("capture_id", Integer, ForeignKey("captures.id"), nullable=False),
    Column("locator", Text, nullable=False),
    Column("quoted_text", Text, nullable=False),
    Column("speaker", Text, nullable=False),
    Column("attribution_frame", Text, nullable=False),
    Column("actor", Text, nullable=False),
    Column("added_at", Text, nullable=False),
)

claim_quote_bindings = Table(
    "claim_quote_bindings",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("claim_id", Integer, ForeignKey("claims.id"), nullable=False),
    Column("capture_id", Integer, ForeignKey("captures.id"), nullable=False),
    Column("locator", Text, nullable=False),
    Column("quoted_text", Text, nullable=False),
    Column("ordinal", Integer, nullable=False),
)

claim_inference_citations = Table(
    "claim_inference_citations",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("claim_id", Integer, ForeignKey("claims.id"), nullable=False),
    Column("cited_claim_id", Integer, ForeignKey("claims.id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
)

# Renditions (ticket 12 / D2 / D7) — one angle → N independent platform-native drafts.
# current_approval_id is a projection pointer only (ticket 13); standing is derived.
renditions = Table(
    "renditions",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("case_id", Integer, ForeignKey("cases.id"), nullable=False),
    Column("angle_id", Integer, ForeignKey("angles.id"), nullable=False),
    Column("run_id", Integer, ForeignKey("runs.id"), nullable=False),
    Column("platform", Text, nullable=False),
    Column("format", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("rubric_version", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("current_approval_id", Integer, nullable=True),
)

rendition_units = Table(
    "rendition_units",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("rendition_id", Integer, ForeignKey("renditions.id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("body", Text, nullable=False),
)

rendition_unit_claims = Table(
    "rendition_unit_claims",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("unit_id", Integer, ForeignKey("rendition_units.id"), nullable=False),
    Column("claim_id", Integer, ForeignKey("claims.id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
)

# Append-only exact-content clearances (ticket 13 / VISION §14). History is never
# the projection alone — same shape as claim_confirmations / run_suspensions.
rendition_approvals = Table(
    "rendition_approvals",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("rendition_id", Integer, ForeignKey("renditions.id"), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("actor", Text, nullable=False),
    Column("approved_at", Text, nullable=False),
)

rendition_approval_units = Table(
    "rendition_approval_units",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("approval_id", Integer, ForeignKey("rendition_approvals.id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("body", Text, nullable=False),
)

# Open questions proposed at run close (ticket 08 / D13). Disposition set on approve.
open_questions = Table(
    "open_questions",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("case_id", Integer, ForeignKey("cases.id"), nullable=False),
    Column("introduced_by_run_id", Integer, ForeignKey("runs.id"), nullable=False),
    # Lineage: the research question that prompted the introducing run.
    Column("source_run_question", Text, nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("proposed_text", Text, nullable=False),
    Column("rationale", Text, nullable=False),
    Column("proposed_scope", Text, nullable=False),
    Column("agenda_decision", Text, nullable=False),
    Column("disposition", Text, nullable=True),
    Column("settled_text", Text, nullable=True),
    Column("settled_scope", Text, nullable=True),
    Column("created_at", Text, nullable=False),
    Column("decided_at", Text, nullable=True),
)

run_low_confidence = Table(
    "run_low_confidence",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("run_id", Integer, ForeignKey("runs.id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("statement", Text, nullable=False),
)
