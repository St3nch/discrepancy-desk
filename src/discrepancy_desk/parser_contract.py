from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PACKAGE_SCHEMA_VERSION = "m06a.normalized-package.v1"
CANONICAL_JSON_VERSION = "m06a.canonical-json.v1"
DETERMINISTIC_CONTRACT_VERSION = "m06a.parser-determinism.v1"
SECURITY_PROFILE_ID = "m06a.parser-worker.windows.v1"
PARSER_ID = "m06a.text.v1"
PARSER_IMPLEMENTATION_VERSION = "1.0.0"
PARSER_IMPLEMENTATION_SHA256 = "ca83f246b915fb584f9dad6d590e211aed6822631fc572fb319de29cba4e9677"
WARNING_POLICY_VERSION = "m06a.text.warnings.v1"
WORKER_PROTOCOL_VERSION = "m06a.parser-worker.v1"

INITIAL_TEXT_CONFIG: dict[str, object] = {
    "character_limit": 1_000_000,
    "element_limit": 50_000,
    "input_size_limit_bytes": 10_485_760,
    "line_limit": 100_000,
    "maximum_line_bytes": 1_048_576,
    "normalize_line_endings_in_derivative": "LF",
    "paragraph_separator": "one-or-more blank logical lines",
    "partial_output": "prohibited",
    "preserve_blank_regions": True,
    "unicode_normalization": "none",
    "warning_policy_version": WARNING_POLICY_VERSION,
}

ALLOWED_WARNINGS = frozenset({"encoding_bom_removed", "line_ending_normalized"})
TERMINAL_FAILURES = frozenset(
    {
        "encoding_failure",
        "limit_exceeded",
        "malformed_input",
        "partial_output_failure",
        "security_boundary_violation",
        "determinism_failure",
        "packaging_mismatch",
        "internal_error",
    }
)


class ParserContractError(ValueError):
    code = "internal_error"


class EncodingFailure(ParserContractError):
    code = "encoding_failure"


class LimitExceeded(ParserContractError):
    code = "limit_exceeded"


class MalformedInput(ParserContractError):
    code = "malformed_input"


class PartialOutputFailure(ParserContractError):
    code = "partial_output_failure"


class PackagingMismatch(ParserContractError):
    code = "packaging_mismatch"


class DeterminismFailure(ParserContractError):
    code = "determinism_failure"


class SecurityBoundaryViolation(ParserContractError):
    code = "security_boundary_violation"


def _reject_nonfinite(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("canonical JSON forbids NaN and Infinity")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON object keys must be strings")
            _reject_nonfinite(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_nonfinite(child)


def canonical_json(value: object) -> bytes:
    _reject_nonfinite(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_sha256(value: str, *, label: str = "SHA-256") -> str:
    normalized = value.strip()
    if len(normalized) != 64 or normalized != normalized.lower() or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{label} is invalid")
    return normalized


def package_relative_path(package_sha256: str) -> str:
    normalized = require_sha256(package_sha256, label="package SHA-256")
    return f"packages/sha256/{normalized[:2]}/{normalized[2:4]}/{normalized}.json"


def canonical_config_bytes() -> bytes:
    return canonical_json(INITIAL_TEXT_CONFIG)


@dataclass(frozen=True, slots=True)
class ParserTuple:
    parser_id: str
    implementation_version: str
    implementation_sha256: str
    resource_manifest_sha256: str
    dependency_lock_sha256: str
    config_sha256: str
    package_schema_version: str = PACKAGE_SCHEMA_VERSION
    deterministic_contract_version: str = DETERMINISTIC_CONTRACT_VERSION
    security_profile_id: str = SECURITY_PROFILE_ID

    def material(self) -> dict[str, str]:
        return {
            "config_sha256": self.config_sha256,
            "dependency_lock_sha256": self.dependency_lock_sha256,
            "deterministic_contract_version": self.deterministic_contract_version,
            "implementation_sha256": self.implementation_sha256,
            "implementation_version": self.implementation_version,
            "package_schema_version": self.package_schema_version,
            "parser_id": self.parser_id,
            "resource_manifest_sha256": self.resource_manifest_sha256,
            "security_profile_id": self.security_profile_id,
        }

    def sha256(self) -> str:
        return sha256_bytes(canonical_json(self.material()))


def validate_coverage(coverage: object, *, input_size: int) -> dict[str, object]:
    if not isinstance(coverage, dict):
        raise PartialOutputFailure("coverage is missing")
    required = {
        "input_byte_count",
        "consumed_byte_ranges",
        "decoded_character_count",
        "source_line_count",
        "emitted_element_count",
        "emitted_region_count",
        "complete",
    }
    if set(coverage) != required:
        raise PartialOutputFailure("coverage fields are incomplete")
    if coverage["input_byte_count"] != input_size or coverage["complete"] is not True:
        raise PartialOutputFailure("coverage does not claim the complete input")
    ranges = coverage["consumed_byte_ranges"]
    if not isinstance(ranges, list):
        raise PartialOutputFailure("coverage ranges are malformed")
    expected = [] if input_size == 0 else [[0, input_size]]
    if ranges != expected:
        raise PartialOutputFailure("coverage ranges do not cover the input exactly")
    for name in (
        "decoded_character_count",
        "source_line_count",
        "emitted_element_count",
        "emitted_region_count",
    ):
        if type(coverage[name]) is not int or int(coverage[name]) < 0:
            raise PartialOutputFailure(f"coverage {name} is invalid")
    return dict(coverage)


def validate_candidate_core(candidate: object, *, input_size: int) -> dict[str, object]:
    if not isinstance(candidate, dict):
        raise PackagingMismatch("candidate package is not an object")
    required = {
        "encoding",
        "line_ending_profile",
        "coverage",
        "elements",
        "regions",
        "warnings",
    }
    if set(candidate) != required:
        raise PackagingMismatch("candidate package fields diverge from the contract")
    coverage = validate_coverage(candidate["coverage"], input_size=input_size)
    elements = candidate["elements"]
    regions = candidate["regions"]
    warnings = candidate["warnings"]
    if not isinstance(elements, list) or not isinstance(regions, list) or not isinstance(warnings, list):
        raise PackagingMismatch("candidate package arrays are malformed")
    if coverage["emitted_element_count"] != len(elements) or coverage["emitted_region_count"] != len(regions):
        raise PartialOutputFailure("coverage counts do not match emitted records")
    if warnings != sorted(set(warnings)) or any(value not in ALLOWED_WARNINGS for value in warnings):
        raise PackagingMismatch("warning vocabulary is invalid")
    for index, element in enumerate(elements):
        if not isinstance(element, dict) or element.get("ordinal") != index:
            raise PackagingMismatch("element ordinals are not contiguous")
    for index, region in enumerate(regions):
        if not isinstance(region, dict) or region.get("ordinal") != index:
            raise PackagingMismatch("region ordinals are not contiguous")
    return {
        "encoding": candidate["encoding"],
        "line_ending_profile": candidate["line_ending_profile"],
        "coverage": coverage,
        "elements": elements,
        "regions": regions,
        "warnings": warnings,
    }


def require_deterministic_candidates(first: bytes, second: bytes) -> str:
    first_sha256 = sha256_bytes(first)
    second_sha256 = sha256_bytes(second)
    if first != second or first_sha256 != second_sha256:
        raise DeterminismFailure("identical parser inputs produced different candidate bytes")
    return first_sha256


def assemble_normalized_package(
    *,
    candidate: object,
    input_size: int,
    vault_account_id: str,
    source_artifact_sha256: str,
    parser_tuple: ParserTuple,
    parser_admission_id: str,
) -> tuple[dict[str, object], bytes]:
    core = validate_candidate_core(candidate, input_size=input_size)
    package: dict[str, object] = {
        "coverage": core["coverage"],
        "elements": core["elements"],
        "encoding": core["encoding"],
        "line_ending_profile": core["line_ending_profile"],
        "parser_admission_id": parser_admission_id,
        "parser_config_sha256": parser_tuple.config_sha256,
        "parser_id": parser_tuple.parser_id,
        "parser_implementation_sha256": parser_tuple.implementation_sha256,
        "parser_implementation_version": parser_tuple.implementation_version,
        "regions": core["regions"],
        "schema_version": parser_tuple.package_schema_version,
        "security_profile_id": parser_tuple.security_profile_id,
        "source_artifact_sha256": require_sha256(
            source_artifact_sha256, label="source artifact SHA-256"
        ),
        "vault_account_id": vault_account_id,
        "warnings": core["warnings"],
    }
    rendered = canonical_json(package)
    if rendered.endswith(b"\n") or rendered.startswith(b"\xef\xbb\xbf"):
        raise PackagingMismatch("canonical package framing is invalid")
    return package, rendered


def load_canonical_json_bytes(value: bytes) -> Any:
    try:
        decoded = value.decode("utf-8")
        parsed = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackagingMismatch("canonical JSON is malformed") from exc
    if canonical_json(parsed) != value:
        raise PackagingMismatch("JSON bytes are not canonical")
    return parsed
