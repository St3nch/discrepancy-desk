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
captures = Table(
    "captures",
    metadata,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("run_id", Integer, ForeignKey("runs.id"), nullable=False),
    Column("case_id", Integer, ForeignKey("cases.id"), nullable=False),
    Column("url", Text, nullable=False),
    Column("sha256", Text, nullable=False),
    Column("content_type", Text, nullable=False),
    Column("byte_size", Integer, nullable=False),
    Column("vault_relpath", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("created_at", Text, nullable=False),
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

# Claims enter unconfirmed (ADR 2). Confirmation is ticket 11.
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
