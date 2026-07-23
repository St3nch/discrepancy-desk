from __future__ import annotations

import codecs
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PACKAGE_SCHEMA_VERSION = "m06a.normalized-package.v1"
CANONICAL_JSON_VERSION = "m06a.canonical-json.v1"
DETERMINISTIC_CONTRACT_VERSION = "m06a.parser-determinism.v2"
SECURITY_PROFILE_ID = "m06a.parser-worker.windows.v2"
PARSER_ID = "m06a.text.v1"
PARSER_IMPLEMENTATION_VERSION = "1.1.0"
PARSER_IMPLEMENTATION_SHA256 = "d0d5a2973d4cf2f4327708255e7403659e51baa255658223c0f3d84f62ec3f67"
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


def _decode_candidate_source(input_bytes: bytes, encoding: object) -> tuple[str, int, bytes]:
    if encoding == "utf-8":
        bom = codecs.BOM_UTF8 if input_bytes.startswith(codecs.BOM_UTF8) else b""
    elif encoding == "utf-16-le":
        bom = codecs.BOM_UTF16_LE
        if not input_bytes.startswith(bom):
            raise PartialOutputFailure("UTF-16 LE candidate omitted its source BOM")
    elif encoding == "utf-16-be":
        bom = codecs.BOM_UTF16_BE
        if not input_bytes.startswith(bom):
            raise PartialOutputFailure("UTF-16 BE candidate omitted its source BOM")
    else:
        raise PackagingMismatch("candidate encoding is not admitted")
    try:
        text = input_bytes[len(bom):].decode(str(encoding), errors="strict")
    except UnicodeDecodeError as exc:
        raise PartialOutputFailure("candidate encoding cannot reproduce the source bytes") from exc
    return text, len(bom), bom


def _logical_line_ranges(text: str) -> list[tuple[int, int, int]]:
    ranges: list[tuple[int, int, int]] = []
    if not text:
        return ranges
    start = 0
    index = 0
    line_number = 1
    while index < len(text):
        character = text[index]
        if character == "\r":
            end = index + 2 if index + 1 < len(text) and text[index + 1] == "\n" else index + 1
            ranges.append((start, end, line_number))
            start = end
            index = end
            line_number += 1
        elif character == "\n":
            end = index + 1
            ranges.append((start, end, line_number))
            start = end
            index = end
            line_number += 1
        else:
            index += 1
    if start < len(text):
        ranges.append((start, len(text), line_number))
    return ranges


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


def _require_locator(record: dict[str, object], *, input_size: int) -> dict[str, int]:
    locator = record.get("source_locator")
    required = {
        "source_byte_end",
        "source_byte_start",
        "source_character_end",
        "source_character_start",
        "source_line_end",
        "source_line_start",
    }
    if not isinstance(locator, dict) or set(locator) != required:
        raise PackagingMismatch("source locator fields are invalid")
    if any(type(locator[name]) is not int for name in required):
        raise PackagingMismatch("source locator values must be integers")
    result = {name: int(locator[name]) for name in required}
    if not (0 <= result["source_byte_start"] < result["source_byte_end"] <= input_size):
        raise PartialOutputFailure("source byte locator is outside the input")
    if not (0 <= result["source_character_start"] <= result["source_character_end"]):
        raise PartialOutputFailure("source character locator is invalid")
    return result


def validate_candidate_core(candidate: object, *, input_bytes: bytes) -> dict[str, object]:
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
    coverage = validate_coverage(candidate["coverage"], input_size=len(input_bytes))
    elements = candidate["elements"]
    regions = candidate["regions"]
    warnings = candidate["warnings"]
    if not isinstance(elements, list) or not isinstance(regions, list) or not isinstance(warnings, list):
        raise PackagingMismatch("candidate package arrays are malformed")
    if coverage["emitted_element_count"] != len(elements) or coverage["emitted_region_count"] != len(regions):
        raise PartialOutputFailure("coverage counts do not match emitted records")
    if warnings != sorted(set(warnings)) or any(value not in ALLOWED_WARNINGS for value in warnings):
        raise PackagingMismatch("warning vocabulary is invalid")

    text, bom_size, bom_bytes = _decode_candidate_source(input_bytes, candidate["encoding"])
    line_ranges = _logical_line_ranges(text)
    if coverage["decoded_character_count"] != len(text):
        raise PartialOutputFailure("coverage character count does not match the source")
    if coverage["source_line_count"] != len(line_ranges):
        raise PartialOutputFailure("coverage line count does not match the source")

    byte_spans: list[tuple[int, int]] = []
    character_spans: list[tuple[int, int]] = []
    preamble_count = 0

    def validate_record(record: object, *, ordinal: int, element: bool) -> None:
        nonlocal preamble_count
        if not isinstance(record, dict) or record.get("ordinal") != ordinal:
            raise PackagingMismatch("record ordinals are not contiguous")
        required_fields = (
            {"content_sha256", "kind", "normalized_text", "ordinal", "raw_text", "source_locator", "warnings"}
            if element
            else {"content_sha256", "kind", "ordinal", "raw_text", "source_locator"}
        )
        if set(record) != required_fields:
            raise PackagingMismatch("parser record fields diverge from the contract")
        raw_text = record.get("raw_text")
        if not isinstance(raw_text, str):
            raise PackagingMismatch("parser record raw text is invalid")
        locator = _require_locator(record, input_size=len(input_bytes))
        byte_start = locator["source_byte_start"]
        byte_end = locator["source_byte_end"]
        char_start = locator["source_character_start"]
        char_end = locator["source_character_end"]
        kind = record.get("kind")
        if kind == "encoding_preamble":
            if element or raw_text or char_start != 0 or char_end != 0:
                raise PartialOutputFailure("encoding preamble locator is invalid")
            if byte_start != 0 or byte_end != bom_size or input_bytes[byte_start:byte_end] != bom_bytes:
                raise PartialOutputFailure("encoding preamble does not match the source BOM")
            if record.get("content_sha256") != sha256_bytes(bom_bytes):
                raise PackagingMismatch("encoding preamble hash is invalid")
            if locator["source_line_start"] != 0 or locator["source_line_end"] != 0:
                raise PartialOutputFailure("encoding preamble line locator is invalid")
            preamble_count += 1
        else:
            if kind not in ({"paragraph"} if element else {"blank_separator"}):
                raise PackagingMismatch("parser record kind is invalid")
            if not (0 <= char_start < char_end <= len(text)):
                raise PartialOutputFailure("source character locator is outside the decoded input")
            try:
                decoded_slice = input_bytes[byte_start:byte_end].decode(str(candidate["encoding"]), errors="strict")
            except UnicodeDecodeError as exc:
                raise PartialOutputFailure("source byte locator cannot reproduce record text") from exc
            if decoded_slice != raw_text or text[char_start:char_end] != raw_text:
                raise PartialOutputFailure("record text does not match its source locator")
            if record.get("content_sha256") != sha256_bytes(raw_text.encode("utf-8")):
                raise PackagingMismatch("record content hash is invalid")
            touched = [line for line in line_ranges if not (line[1] <= char_start or line[0] >= char_end)]
            if not touched:
                raise PartialOutputFailure("record locator does not map to a logical line")
            if locator["source_line_start"] != touched[0][2] or locator["source_line_end"] != touched[-1][2]:
                raise PartialOutputFailure("record line locator does not match its character span")
            character_spans.append((char_start, char_end))
            if element:
                normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
                if record.get("normalized_text") != normalized:
                    raise PackagingMismatch("element normalized text is invalid")
                record_warnings = record.get("warnings")
                if record_warnings != warnings:
                    raise PackagingMismatch("element warnings diverge from the package warnings")
        byte_spans.append((byte_start, byte_end))

    for index, element_record in enumerate(elements):
        validate_record(element_record, ordinal=index, element=True)
    for index, region_record in enumerate(regions):
        validate_record(region_record, ordinal=index, element=False)

    expected_preamble = 1 if bom_size else 0
    if preamble_count != expected_preamble:
        raise PartialOutputFailure("encoding preamble coverage is incomplete")
    if bool(bom_size) != ("encoding_bom_removed" in warnings):
        raise PackagingMismatch("encoding BOM warning does not match the source")

    ordered_bytes = sorted(byte_spans)
    if not input_bytes:
        if ordered_bytes:
            raise PartialOutputFailure("empty input emitted source spans")
    else:
        cursor = 0
        for start, end in ordered_bytes:
            if start != cursor:
                raise PartialOutputFailure("emitted byte locators contain a gap or overlap")
            cursor = end
        if cursor != len(input_bytes):
            raise PartialOutputFailure("emitted byte locators omit terminal source bytes")

    ordered_characters = sorted(character_spans)
    if not text:
        if ordered_characters:
            raise PartialOutputFailure("empty decoded input emitted character spans")
    else:
        cursor = 0
        for start, end in ordered_characters:
            if start != cursor:
                raise PartialOutputFailure("emitted character locators contain a gap or overlap")
            cursor = end
        if cursor != len(text):
            raise PartialOutputFailure("emitted character locators omit terminal text")

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
    input_bytes: bytes,
    vault_account_id: str,
    source_artifact_sha256: str,
    parser_tuple: ParserTuple,
    parser_admission_id: str,
) -> tuple[dict[str, object], bytes]:
    core = validate_candidate_core(candidate, input_bytes=input_bytes)
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
