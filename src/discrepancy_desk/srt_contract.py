from __future__ import annotations

import codecs
import re
from dataclasses import dataclass
from pathlib import Path

from .parser_contract import (
    SECURITY_PROFILE_ID,
    ParserTuple,
    PartialOutputFailure,
    PackagingMismatch,
    canonical_json,
    require_sha256,
    sha256_bytes,
    validate_coverage,
)

SRT_PARSER_ID = "m06a.srt.v1"
SRT_IMPLEMENTATION_VERSION = "0.1.0"
SRT_IMPLEMENTATION_SHA256 = "e8bc536aac12e60ebfa0962177af34fa4d05a6d564d08fcbf694dee1a88ccb2a"
SRT_RESOURCE_MANIFEST_SHA256 = "04d9f9780e13bc3658194d3f0d6cc8f6ce9426e154b8d229e4d5c80b2e20dd41"
SRT_CONFIG_SHA256 = "88db85d7b93ca55cf2f1bc3104941cf3076943ed388c4e803a480b75e5bbf309"
SRT_SCHEMA_SHA256 = "99ec97748389d61ead4d06b91416c64163b3f40269a473b9f1786ba20b0ba551"
SRT_DEPENDENCY_LOCK_SHA256 = "feb1aea2f45166a25c6b1618798790f65656db9490dc63d77481c519c8765351"
SRT_PACKAGE_SCHEMA_VERSION = "m06a.normalized-package.srt.v1"
SRT_DETERMINISTIC_CONTRACT_VERSION = "m06a.srt-determinism.v1"
SRT_WARNING_POLICY_VERSION = "m06a.srt.warnings.v1"
SRT_WORKER_PROTOCOL_VERSION = "m06a.srt-worker.v1"
SRT_SECURITY_PROFILE_ID = SECURITY_PROFILE_ID

INITIAL_SRT_CONFIG: dict[str, object] = {
    "cue_limit": 100_000,
    "input_size_limit_bytes": 10_485_760,
    "line_limit": 300_000,
    "maximum_cue_bytes": 1_048_576,
    "maximum_timestamp_milliseconds": 86_400_000,
    "partial_output": "prohibited",
    "preserve_blank_regions": True,
    "source_order": "preserved",
    "warning_policy_version": SRT_WARNING_POLICY_VERSION,
}

SRT_ALLOWED_WARNINGS = frozenset(
    {
        "encoding_bom_removed",
        "line_ending_normalized",
        "nonsequential_cue_index",
        "overlapping_cues",
    }
)

_TIMESTAMP = re.compile(
    r"^(?P<sh>\d{2}):(?P<sm>\d{2}):(?P<ss>\d{2}),(?P<sms>\d{3})"
    r" --> "
    r"(?P<eh>\d{2}):(?P<em>\d{2}):(?P<es>\d{2}),(?P<ems>\d{3})$"
)
_LINE_PATTERN = re.compile(r"[^\r\n]*(?:\r\n|\r|\n|$)")


@dataclass(frozen=True, slots=True)
class _Line:
    content: str
    full_text: str
    char_start: int
    char_end: int
    line_number: int


def canonical_srt_config_bytes() -> bytes:
    return canonical_json(INITIAL_SRT_CONFIG)


def srt_parser_tuple(
    *,
    resource_manifest_sha256: str,
    dependency_lock_sha256: str,
    config_sha256: str,
) -> ParserTuple:
    return ParserTuple(
        parser_id=SRT_PARSER_ID,
        implementation_version=SRT_IMPLEMENTATION_VERSION,
        implementation_sha256=SRT_IMPLEMENTATION_SHA256,
        resource_manifest_sha256=resource_manifest_sha256,
        dependency_lock_sha256=dependency_lock_sha256,
        config_sha256=config_sha256,
        package_schema_version=SRT_PACKAGE_SCHEMA_VERSION,
        deterministic_contract_version=SRT_DETERMINISTIC_CONTRACT_VERSION,
        security_profile_id=SRT_SECURITY_PROFILE_ID,
    )


def _decode_source(data: bytes, encoding: object) -> tuple[str, int, bytes]:
    if encoding == "utf-8":
        bom = codecs.BOM_UTF8 if data.startswith(codecs.BOM_UTF8) else b""
    elif encoding == "utf-16-le":
        bom = codecs.BOM_UTF16_LE
        if not data.startswith(bom):
            raise PartialOutputFailure("SRT candidate omitted its UTF-16 LE BOM")
    elif encoding == "utf-16-be":
        bom = codecs.BOM_UTF16_BE
        if not data.startswith(bom):
            raise PartialOutputFailure("SRT candidate omitted its UTF-16 BE BOM")
    else:
        raise PackagingMismatch("SRT candidate encoding is not admitted")
    try:
        text = data[len(bom):].decode(str(encoding), errors="strict")
    except UnicodeDecodeError as exc:
        raise PartialOutputFailure("SRT candidate encoding cannot reproduce source bytes") from exc
    return text, len(bom), bom


def _lines(text: str) -> list[_Line]:
    if not text:
        return []
    result: list[_Line] = []
    cursor = 0
    line_number = 1
    for match in _LINE_PATTERN.finditer(text):
        full = match.group(0)
        if not full:
            break
        if full.endswith("\r\n"):
            content = full[:-2]
        elif full.endswith(("\r", "\n")):
            content = full[:-1]
        else:
            content = full
        end = cursor + len(full)
        result.append(_Line(content, full, cursor, end, line_number))
        cursor = end
        line_number += 1
    if cursor != len(text):
        raise PartialOutputFailure("SRT validator did not consume decoded source")
    return result


def _line_profile(text: str) -> str:
    has_crlf = "\r\n" in text
    remaining = text.replace("\r\n", "")
    values = [
        name
        for present, name in (
            (has_crlf, "CRLF"),
            ("\r" in remaining, "CR"),
            ("\n" in remaining, "LF"),
        )
        if present
    ]
    if not values:
        return "none"
    return values[0] if len(values) == 1 else "mixed:" + ",".join(values)


def _byte_offsets(text: str, *, encoding: str, bom_size: int) -> list[int]:
    offsets = [bom_size]
    current = bom_size
    for character in text:
        current += len(character.encode(encoding))
        offsets.append(current)
    return offsets


def _locator(value: object, *, input_size: int, allow_zero: bool = False) -> dict[str, int]:
    required = {
        "source_byte_end",
        "source_byte_start",
        "source_character_end",
        "source_character_start",
        "source_line_end",
        "source_line_start",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise PackagingMismatch("SRT source locator fields are invalid")
    if any(type(value[name]) is not int for name in required):
        raise PackagingMismatch("SRT source locator values must be integers")
    result = {name: int(value[name]) for name in required}
    if (
        allow_zero
        and result["source_character_start"] == result["source_character_end"] == 0
        and 0 <= result["source_byte_start"] < result["source_byte_end"] <= input_size
    ):
        return result
    if not (0 <= result["source_byte_start"] < result["source_byte_end"] <= input_size):
        raise PartialOutputFailure("SRT byte locator is outside the input")
    if not (0 <= result["source_character_start"] < result["source_character_end"]):
        raise PartialOutputFailure("SRT character locator is invalid")
    return result


def _timestamp_ms(match: re.Match[str], prefix: str) -> int:
    hours = int(match.group(prefix + "h"))
    minutes = int(match.group(prefix + "m"))
    seconds = int(match.group(prefix + "s"))
    milliseconds = int(match.group(prefix + "ms"))
    if minutes >= 60 or seconds >= 60:
        raise PackagingMismatch("SRT timestamp fields are invalid")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + milliseconds


def _cue_metadata(raw_text: str) -> tuple[int | None, int, int, int, int, str]:
    lines = _lines(raw_text)
    if not lines or any(not line.content.strip() for line in lines):
        raise PackagingMismatch("SRT cue block contains an unexpected blank line")
    cursor = 0
    cue_index: int | None = None
    if lines[0].content.isdigit():
        cue_index = int(lines[0].content)
        cursor = 1
    if cursor >= len(lines):
        raise PackagingMismatch("SRT cue timestamp is missing")
    match = _TIMESTAMP.fullmatch(lines[cursor].content)
    if match is None:
        raise PackagingMismatch("SRT cue timestamp is malformed")
    text_lines = lines[cursor + 1:]
    if not text_lines:
        raise PackagingMismatch("SRT cue text is missing")
    cue_text_start = text_lines[0].char_start
    cue_text_end = text_lines[-1].char_end
    cue_text = raw_text[cue_text_start:cue_text_end]
    return (
        cue_index,
        _timestamp_ms(match, "s"),
        _timestamp_ms(match, "e"),
        cue_text_start,
        cue_text_end,
        cue_text,
    )


def validate_srt_candidate(candidate: object, *, input_bytes: bytes) -> dict[str, object]:
    if not isinstance(candidate, dict):
        raise PackagingMismatch("SRT candidate is not an object")
    required = {"coverage", "elements", "encoding", "line_ending_profile", "regions", "warnings"}
    if set(candidate) != required:
        raise PackagingMismatch("SRT candidate fields diverge from the contract")
    coverage = validate_coverage(candidate["coverage"], input_size=len(input_bytes))
    elements = candidate["elements"]
    regions = candidate["regions"]
    warnings = candidate["warnings"]
    if not isinstance(elements, list) or not isinstance(regions, list) or not isinstance(warnings, list):
        raise PackagingMismatch("SRT candidate arrays are malformed")
    if warnings != sorted(set(warnings)) or any(value not in SRT_ALLOWED_WARNINGS for value in warnings):
        raise PackagingMismatch("SRT warning vocabulary is invalid")
    if coverage["emitted_element_count"] != len(elements) or coverage["emitted_region_count"] != len(regions):
        raise PartialOutputFailure("SRT coverage counts diverge from emitted records")

    text, bom_size, bom_bytes = _decode_source(input_bytes, candidate["encoding"])
    source_lines = _lines(text)
    offsets = _byte_offsets(text, encoding=str(candidate["encoding"]), bom_size=bom_size)
    if coverage["decoded_character_count"] != len(text) or coverage["source_line_count"] != len(source_lines):
        raise PartialOutputFailure("SRT coverage metadata diverges from the source")
    if candidate["line_ending_profile"] != _line_profile(text):
        raise PackagingMismatch("SRT line-ending profile is invalid")

    byte_spans: list[tuple[int, int]] = []
    char_spans: list[tuple[int, int]] = []
    observed_indexes: list[int | None] = []
    observed_times: list[tuple[int, int]] = []
    preambles = 0

    element_fields = {
        "content_sha256", "cue_index", "cue_text_raw", "cue_text_source_locator",
        "end_milliseconds", "kind", "normalized_text", "ordinal", "raw_text",
        "source_locator", "start_milliseconds", "warnings",
    }
    for ordinal, record in enumerate(elements):
        if not isinstance(record, dict) or set(record) != element_fields or record.get("ordinal") != ordinal:
            raise PackagingMismatch("SRT cue element fields or ordinal are invalid")
        if record.get("kind") != "subtitle_cue" or record.get("warnings") != warnings:
            raise PackagingMismatch("SRT cue kind or warnings are invalid")
        raw_text = record.get("raw_text")
        if not isinstance(raw_text, str):
            raise PackagingMismatch("SRT cue raw text is invalid")
        loc = _locator(record.get("source_locator"), input_size=len(input_bytes))
        bs, be = loc["source_byte_start"], loc["source_byte_end"]
        cs, ce = loc["source_character_start"], loc["source_character_end"]
        if bs != offsets[cs] or be != offsets[ce]:
            raise PartialOutputFailure("SRT cue byte and character locators diverge")
        try:
            decoded = input_bytes[bs:be].decode(str(candidate["encoding"]), errors="strict")
        except UnicodeDecodeError as exc:
            raise PartialOutputFailure("SRT cue byte locator cannot be decoded") from exc
        if decoded != raw_text or text[cs:ce] != raw_text:
            raise PartialOutputFailure("SRT cue raw text does not match source locators")
        if record.get("content_sha256") != sha256_bytes(raw_text.encode("utf-8")):
            raise PackagingMismatch("SRT cue content hash is invalid")
        cue_index, start_ms, end_ms, local_start, local_end, cue_text = _cue_metadata(raw_text)
        if record.get("cue_index") != cue_index:
            raise PackagingMismatch("SRT cue index is invalid")
        if record.get("start_milliseconds") != start_ms or record.get("end_milliseconds") != end_ms:
            raise PackagingMismatch("SRT cue timing metadata is invalid")
        if record.get("cue_text_raw") != cue_text:
            raise PackagingMismatch("SRT cue text is invalid")
        expected_normalized = cue_text.replace("\r\n", "\n").replace("\r", "\n")
        if record.get("normalized_text") != expected_normalized:
            raise PackagingMismatch("SRT normalized cue text is invalid")
        text_loc = _locator(record.get("cue_text_source_locator"), input_size=len(input_bytes))
        expected_cs = cs + local_start
        expected_ce = cs + local_end
        if text_loc["source_character_start"] != expected_cs or text_loc["source_character_end"] != expected_ce:
            raise PartialOutputFailure("SRT cue text character locator is invalid")
        if text_loc["source_byte_start"] != offsets[expected_cs] or text_loc["source_byte_end"] != offsets[expected_ce]:
            raise PartialOutputFailure("SRT cue text byte locator is invalid")
        if text[expected_cs:expected_ce] != cue_text:
            raise PartialOutputFailure("SRT cue text locator does not reproduce the source")
        touched = [line for line in source_lines if not (line.char_end <= cs or line.char_start >= ce)]
        cue_touched = [line for line in source_lines if not (line.char_end <= expected_cs or line.char_start >= expected_ce)]
        if not touched or loc["source_line_start"] != touched[0].line_number or loc["source_line_end"] != touched[-1].line_number:
            raise PartialOutputFailure("SRT cue line locator is invalid")
        if not cue_touched or text_loc["source_line_start"] != cue_touched[0].line_number or text_loc["source_line_end"] != cue_touched[-1].line_number:
            raise PartialOutputFailure("SRT cue text line locator is invalid")
        byte_spans.append((bs, be))
        char_spans.append((cs, ce))
        observed_indexes.append(cue_index)
        observed_times.append((start_ms, end_ms))

    region_fields = {"content_sha256", "kind", "ordinal", "raw_text", "source_locator"}
    for ordinal, record in enumerate(regions):
        if not isinstance(record, dict) or set(record) != region_fields or record.get("ordinal") != ordinal:
            raise PackagingMismatch("SRT region fields or ordinal are invalid")
        raw_text = record.get("raw_text")
        if not isinstance(raw_text, str):
            raise PackagingMismatch("SRT region raw text is invalid")
        kind = record.get("kind")
        loc = _locator(record.get("source_locator"), input_size=len(input_bytes), allow_zero=kind == "encoding_preamble")
        bs, be = loc["source_byte_start"], loc["source_byte_end"]
        cs, ce = loc["source_character_start"], loc["source_character_end"]
        if kind == "encoding_preamble":
            if raw_text or bs != 0 or be != bom_size or cs != 0 or ce != 0 or input_bytes[bs:be] != bom_bytes:
                raise PartialOutputFailure("SRT encoding preamble is invalid")
            if record.get("content_sha256") != sha256_bytes(bom_bytes):
                raise PackagingMismatch("SRT encoding preamble hash is invalid")
            preambles += 1
        elif kind == "blank_separator":
            if bs != offsets[cs] or be != offsets[ce]:
                raise PartialOutputFailure(
                    "SRT blank separator byte and character locators diverge"
                )
            if text[cs:ce] != raw_text or raw_text.strip():
                raise PartialOutputFailure("SRT blank separator does not match source text")
            if record.get("content_sha256") != sha256_bytes(raw_text.encode("utf-8")):
                raise PackagingMismatch("SRT blank separator hash is invalid")
            char_spans.append((cs, ce))
        else:
            raise PackagingMismatch("SRT region kind is invalid")
        byte_spans.append((bs, be))

    if preambles != (1 if bom_size else 0):
        raise PartialOutputFailure("SRT encoding preamble coverage is incomplete")
    if bool(bom_size) != ("encoding_bom_removed" in warnings):
        raise PackagingMismatch("SRT BOM warning does not match source input")
    if (_line_profile(text) not in {"none", "LF"}) != ("line_ending_normalized" in warnings):
        raise PackagingMismatch("SRT line-ending warning does not match source input")

    expected_nonseq = False
    previous_index: int | None = None
    for value in observed_indexes:
        if value is not None and previous_index is not None and value != previous_index + 1:
            expected_nonseq = True
        if value is not None:
            previous_index = value
    expected_overlap = any(observed_times[i][0] < observed_times[i - 1][1] for i in range(1, len(observed_times)))
    if expected_nonseq != ("nonsequential_cue_index" in warnings):
        raise PackagingMismatch("SRT index warning does not match cue sequence")
    if expected_overlap != ("overlapping_cues" in warnings):
        raise PackagingMismatch("SRT overlap warning does not match cue timing")

    ordered_bytes = sorted(byte_spans)
    cursor = 0
    for start, end in ordered_bytes:
        if start != cursor:
            raise PartialOutputFailure("SRT byte locators contain a gap or overlap")
        cursor = end
    if cursor != len(input_bytes):
        raise PartialOutputFailure("SRT byte locators omit source bytes")
    ordered_chars = sorted(char_spans)
    cursor = 0
    for start, end in ordered_chars:
        if start != cursor:
            raise PartialOutputFailure("SRT character locators contain a gap or overlap")
        cursor = end
    if cursor != len(text):
        raise PartialOutputFailure("SRT character locators omit source text")

    return {
        "coverage": coverage,
        "elements": elements,
        "encoding": candidate["encoding"],
        "line_ending_profile": candidate["line_ending_profile"],
        "regions": regions,
        "warnings": warnings,
    }


def assemble_srt_normalized_package(
    *,
    candidate: object,
    input_bytes: bytes,
    vault_account_id: str,
    source_artifact_sha256: str,
    parser_tuple: ParserTuple,
    parser_admission_id: str,
) -> tuple[dict[str, object], bytes]:
    core = validate_srt_candidate(candidate, input_bytes=input_bytes)
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
        "source_artifact_sha256": require_sha256(source_artifact_sha256, label="source artifact SHA-256"),
        "vault_account_id": vault_account_id,
        "warnings": core["warnings"],
    }
    rendered = canonical_json(package)
    if rendered.endswith(b"\n") or rendered.startswith(codecs.BOM_UTF8):
        raise PackagingMismatch("SRT canonical package framing is invalid")
    return package, rendered


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
