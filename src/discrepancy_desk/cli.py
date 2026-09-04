"""Small operator command surface for the FILE-01 vertical slice."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from discrepancy_desk.config import require_data_root
from discrepancy_desk.db import (
    bootstrap_database,
    connect_admin,
    connect_human,
    connect_runtime,
)
from discrepancy_desk.evidence import (
    add_document_page_locator,
    add_document_text_locator,
    add_excerpt,
    add_media_time_locator,
    add_text_surface,
    capture_local_file,
    verify_file_evidence,
)
from discrepancy_desk.record import (
    admit_observation,
    open_discrepancy,
    open_file,
    propose_claim,
    record_decision,
    revise_discrepancy,
)
from discrepancy_desk.report import render_file_report, walkback
from discrepancy_desk.vault import Vault


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m discrepancy_desk",
        description="Operate the private Discrepancy Desk FILE-01 Record.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser(
        "bootstrap",
        help="Create capability roles and apply migrations using explicit admin authority.",
    )

    open_file_parser = commands.add_parser("open-file")
    open_file_parser.add_argument("--public-id", required=True)
    open_file_parser.add_argument("--subject", required=True)
    open_file_parser.add_argument("--question", required=True)

    capture = commands.add_parser(
        "capture",
        help="Preserve an already-downloaded local file; this command performs no network I/O.",
    )
    capture.add_argument("--file", required=True)
    capture.add_argument("--source-path", type=Path, required=True)
    capture.add_argument("--acquisition-url", required=True)
    capture.add_argument("--retrieved-at", type=_datetime, required=True)
    capture.add_argument("--reported-media-type")
    capture.add_argument("--detected-media-type", required=True)
    capture.add_argument("--expected-sha256", required=True)
    capture.add_argument("--expected-byte-size", type=int, required=True)
    capture.add_argument("--page-count", type=int)
    capture.add_argument("--duration-ms", type=int)
    capture.add_argument("--asserted-source-identity")
    capture.add_argument("--asserted-by")
    capture.add_argument(
        "--identity-verification-state",
        choices=("unverified", "contested"),
        default="unverified",
    )
    capture.add_argument("--identity-verification-basis")
    capture.add_argument("--provenance-note", required=True)
    capture.add_argument("--relevance-note", required=True)

    page = commands.add_parser("locate-document-page")
    page.add_argument("--artifact-id", required=True)
    page.add_argument("--page", type=int, required=True)

    text_range = commands.add_parser("locate-document-text")
    text_range.add_argument("--surface-id", required=True)
    text_range.add_argument("--page", type=int, required=True)
    text_range.add_argument("--start", type=int, required=True)
    text_range.add_argument("--end", type=int, required=True)

    media = commands.add_parser("locate-media-time")
    media.add_argument("--artifact-id", required=True)
    media.add_argument("--start-ms", type=int, required=True)
    media.add_argument("--end-ms", type=int, required=True)

    surface = commands.add_parser("add-text-surface")
    surface.add_argument("--artifact-id", required=True)
    surface.add_argument("--source-locator-id", required=True)
    surface.add_argument("--surface-kind", required=True)
    surface.add_argument("--text-file", type=Path, required=True)
    surface.add_argument("--produced-by-method", required=True)
    surface.add_argument("--produced-by-actor", required=True)
    surface.add_argument("--produced-by-version")
    surface.add_argument("--produced-at", type=_datetime, required=True)

    excerpt = commands.add_parser("add-excerpt")
    excerpt.add_argument("--locator-id", required=True)
    excerpt.add_argument("--surface-id")
    excerpt.add_argument("--capture-id", required=True)
    excerpt.add_argument("--text-file", type=Path, required=True)

    observation = commands.add_parser("observe")
    observation.add_argument("--file", required=True)
    observation.add_argument("--statement", required=True)
    observation.add_argument("--excerpt-id", action="append", required=True)

    claim = commands.add_parser("claim")
    claim.add_argument("--file", required=True)
    claim.add_argument("--proposition", required=True)
    claim.add_argument("--relevance-note", required=True)
    claim.add_argument(
        "--basis",
        action="append",
        required=True,
        metavar="OBSERVATION_ID:supports|contradicts",
    )

    decision = commands.add_parser(
        "decide",
        help="Requires DESK_HUMAN_POSTGRES_URL and never uses ordinary authority.",
    )
    decision.add_argument("--claim-version-id", required=True)
    decision.add_argument("--authorized-by", required=True)
    decision.add_argument("--decision-text", required=True)
    decision.add_argument(
        "--posture",
        choices=("open", "supported", "not_supported", "unresolved"),
        required=True,
    )
    decision.add_argument("--supersedes-decision-id")

    discrepancy = commands.add_parser("discrepancy")
    discrepancy.add_argument("--file", required=True)
    discrepancy.add_argument("--local-id", required=True)
    discrepancy.add_argument("--question", required=True)
    discrepancy.add_argument(
        "--state",
        choices=("open", "narrowed", "adequately_explained", "closed"),
        required=True,
    )
    discrepancy.add_argument("--observation-id", action="append", default=[])
    discrepancy.add_argument("--claim-version-id", action="append", default=[])
    discrepancy.add_argument("--revise", action="store_true")

    report = commands.add_parser("report")
    report.add_argument("--file", required=True)

    walk = commands.add_parser("walkback")
    walk.add_argument(
        "--kind",
        choices=("observation", "claim_version", "discrepancy_version"),
        required=True,
    )
    walk.add_argument("--id", required=True)

    verify = commands.add_parser("verify")
    verify.add_argument("--file", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "bootstrap":
        with connect_admin() as conn:
            bootstrap_database(conn)
        _print({"status": "bootstrapped"})
        return 0

    if args.command == "decide":
        with connect_human() as conn:
            decision_id = record_decision(
                conn,
                claim_version_id=args.claim_version_id,
                authorized_by=args.authorized_by,
                decision_text=args.decision_text,
                posture=args.posture,
                supersedes_decision_id=args.supersedes_decision_id,
            )
        _print({"decision_id": decision_id})
        return 0

    with connect_runtime() as conn:
        if args.command == "open-file":
            object_id = open_file(
                conn,
                public_id=args.public_id,
                subject=args.subject,
                investigation_question=args.question,
            )
            _print({"file_id": object_id})
        elif args.command == "capture":
            receipt = capture_local_file(
                conn,
                _vault(),
                file_public_id=args.file,
                source_path=args.source_path,
                acquisition_url=args.acquisition_url,
                retrieved_at=args.retrieved_at,
                reported_media_type=args.reported_media_type,
                detected_media_type=args.detected_media_type,
                expected_sha256=args.expected_sha256,
                expected_byte_size=args.expected_byte_size,
                page_count=args.page_count,
                duration_ms=args.duration_ms,
                asserted_source_identity=args.asserted_source_identity,
                asserted_by=args.asserted_by,
                identity_verification_state=args.identity_verification_state,
                identity_verification_basis=args.identity_verification_basis,
                provenance_note=args.provenance_note,
                relevance_note=args.relevance_note,
            )
            _print(asdict(receipt))
        elif args.command == "locate-document-page":
            _print(
                {
                    "locator_id": add_document_page_locator(
                        conn,
                        artifact_id=args.artifact_id,
                        page_number=args.page,
                    )
                }
            )
        elif args.command == "locate-document-text":
            _print(
                {
                    "locator_id": add_document_text_locator(
                        conn,
                        surface_id=args.surface_id,
                        page_number=args.page,
                        start_char=args.start,
                        end_char=args.end,
                    )
                }
            )
        elif args.command == "locate-media-time":
            _print(
                {
                    "locator_id": add_media_time_locator(
                        conn,
                        artifact_id=args.artifact_id,
                        start_ms=args.start_ms,
                        end_ms=args.end_ms,
                    )
                }
            )
        elif args.command == "add-text-surface":
            ref = add_text_surface(
                conn,
                _vault(),
                artifact_id=args.artifact_id,
                source_locator_id=args.source_locator_id,
                surface_kind=args.surface_kind,
                text=args.text_file.read_text(encoding="utf-8"),
                produced_by_method=args.produced_by_method,
                produced_by_actor=args.produced_by_actor,
                produced_by_version=args.produced_by_version,
                produced_at=args.produced_at,
            )
            _print(asdict(ref))
        elif args.command == "add-excerpt":
            object_id = add_excerpt(
                conn,
                _vault(),
                locator_id=args.locator_id,
                capture_id=args.capture_id,
                surface_id=args.surface_id,
                exact_text=args.text_file.read_text(encoding="utf-8"),
            )
            _print({"excerpt_id": object_id})
        elif args.command == "observe":
            object_id = admit_observation(
                conn,
                file_public_id=args.file,
                statement=args.statement,
                excerpt_ids=args.excerpt_id,
            )
            _print({"observation_id": object_id})
        elif args.command == "claim":
            ref = propose_claim(
                conn,
                file_public_id=args.file,
                proposition=args.proposition,
                relevance_note=args.relevance_note,
                observation_basis=[_basis(value) for value in args.basis],
            )
            _print(asdict(ref))
        elif args.command == "discrepancy":
            operation = revise_discrepancy if args.revise else open_discrepancy
            ref = operation(
                conn,
                file_public_id=args.file,
                local_id=args.local_id,
                question=args.question,
                lifecycle_state=args.state,
                observation_ids=args.observation_id,
                claim_version_ids=args.claim_version_id,
            )
            _print(asdict(ref))
        elif args.command == "report":
            print(render_file_report(conn, file_public_id=args.file), end="")
        elif args.command == "walkback":
            _print(walkback(conn, _vault(), object_kind=args.kind, object_id=args.id))
        elif args.command == "verify":
            _print(
                asdict(
                    verify_file_evidence(
                        conn,
                        _vault(),
                        file_public_id=args.file,
                    )
                )
            )
        else:
            raise AssertionError(f"Unhandled command: {args.command}")
    return 0


def _vault() -> Vault:
    return Vault(require_data_root())


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed


def _basis(value: str) -> tuple[str, str]:
    try:
        observation_id, relation = value.rsplit(":", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("basis must be OBSERVATION_ID:RELATION") from exc
    if not observation_id or relation not in {"supports", "contradicts"}:
        raise argparse.ArgumentTypeError("basis relation must be supports or contradicts")
    return observation_id, relation


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))
