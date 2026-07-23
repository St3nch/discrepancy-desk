from __future__ import annotations

import codecs
from pathlib import Path

from .parser_contract import (
    SECURITY_PROFILE_ID,
    ParserTuple,
    PackagingMismatch,
    PartialOutputFailure,
    canonical_json,
    require_sha256,
    sha256_bytes,
    validate_coverage,
)

VTT_PARSER_ID = "m06a.vtt.v1"
VTT_IMPLEMENTATION_VERSION = "0.1.0"
VTT_IMPLEMENTATION_SHA256 = "8e98ac8552ba6048af37adb1f0c2cc1946bf5153537bc019dcd0056ae145b350"
VTT_RESOURCE_MANIFEST_SHA256 = "9eb1be7efda9707d9eaeebb5f69e68f32fce6da816b11c8183fdea6b1368dbb7"
VTT_CONFIG_SHA256 = "2caf5a54bbf13c470c09428d191921203cbe23443168211dc76c9068a89afce5"
VTT_SCHEMA_SHA256 = "1121baef45ab0f8582ee7d2005b81f235beb720520cab36791eb3d52fd595aa9"
VTT_DEPENDENCY_LOCK_SHA256 = "feb1aea2f45166a25c6b1618798790f65656db9490dc63d77481c519c8765351"
VTT_PACKAGE_SCHEMA_VERSION = "m06a.normalized-package.vtt.v1"
VTT_DETERMINISTIC_CONTRACT_VERSION = "m06a.vtt-determinism.v1"
VTT_WARNING_POLICY_VERSION = "m06a.vtt.warnings.v1"
VTT_WORKER_PROTOCOL_VERSION = "m06a.vtt-worker.v1"
VTT_SECURITY_PROFILE_ID = SECURITY_PROFILE_ID

INITIAL_VTT_CONFIG: dict[str, object] = {
    "cue_limit": 100_000,
    "element_limit": 100_000,
    "input_size_limit_bytes": 10_485_760,
    "line_limit": 300_000,
    "maximum_cue_bytes": 1_048_576,
    "maximum_cue_identifier_bytes": 16_384,
    "maximum_header_bytes": 16_384,
    "maximum_note_bytes": 1_048_576,
    "maximum_setting_token_bytes": 16_384,
    "maximum_settings_per_cue": 16,
    "maximum_timestamp_milliseconds": 86_400_000,
    "note_policy": "preserve_inert_region",
    "partial_output": "prohibited",
    "region_block_policy": "reject",
    "region_cue_setting_policy": "reject",
    "region_limit": 300_000,
    "source_order": "preserved",
    "style_block_policy": "reject",
    "warning_policy_version": VTT_WARNING_POLICY_VERSION,
}

VTT_ALLOWED_WARNINGS = frozenset(
    {
        "cue_markup_preserved_inert",
        "encoding_bom_removed",
        "line_ending_normalized",
        "overlapping_cues",
        "unsupported_cue_setting_preserved",
    }
)


def canonical_vtt_config_bytes() -> bytes:
    return canonical_json(INITIAL_VTT_CONFIG)


def vtt_parser_tuple(
    *, resource_manifest_sha256: str, dependency_lock_sha256: str, config_sha256: str
) -> ParserTuple:
    return ParserTuple(
        parser_id=VTT_PARSER_ID,
        implementation_version=VTT_IMPLEMENTATION_VERSION,
        implementation_sha256=VTT_IMPLEMENTATION_SHA256,
        resource_manifest_sha256=resource_manifest_sha256,
        dependency_lock_sha256=dependency_lock_sha256,
        config_sha256=config_sha256,
        package_schema_version=VTT_PACKAGE_SCHEMA_VERSION,
        deterministic_contract_version=VTT_DETERMINISTIC_CONTRACT_VERSION,
        security_profile_id=VTT_SECURITY_PROFILE_ID,
    )


def _source(input_bytes: bytes) -> tuple[str, int]:
    if input_bytes.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        raise PartialOutputFailure("VTT candidate cannot reproduce UTF-16 source")
    bom_size = len(codecs.BOM_UTF8) if input_bytes.startswith(codecs.BOM_UTF8) else 0
    try:
        text = input_bytes[bom_size:].decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise PartialOutputFailure("VTT candidate encoding cannot reproduce source bytes") from exc
    return text, bom_size


def _offsets(text: str, bom_size: int) -> list[int]:
    result = [bom_size]
    current = bom_size
    for character in text:
        current += len(character.encode("utf-8"))
        result.append(current)
    return result


def _locator(value: object, *, input_size: int, allow_zero: bool = False) -> dict[str, int]:
    required = {
        "source_byte_end", "source_byte_start", "source_character_end",
        "source_character_start", "source_line_end", "source_line_start",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise PackagingMismatch("VTT source locator fields are invalid")
    if any(type(value[name]) is not int for name in required):
        raise PackagingMismatch("VTT source locator values must be integers")
    result = {name: int(value[name]) for name in required}
    if allow_zero and result["source_character_start"] == result["source_character_end"] == 0:
        if not (0 <= result["source_byte_start"] < result["source_byte_end"] <= input_size):
            raise PartialOutputFailure("VTT zero-character locator is outside the input")
        return result
    if not (0 <= result["source_byte_start"] < result["source_byte_end"] <= input_size):
        raise PartialOutputFailure("VTT byte locator is outside the input")
    if not (0 <= result["source_character_start"] < result["source_character_end"]):
        raise PartialOutputFailure("VTT character locator is invalid")
    if result["source_line_start"] <= 0 or result["source_line_end"] < result["source_line_start"]:
        raise PartialOutputFailure("VTT line locator is invalid")
    return result


def _validate_record_slice(
    record: dict[str, object], *, text: str, offsets: list[int], input_bytes: bytes,
    locator_name: str, raw_name: str, allow_zero: bool = False,
) -> tuple[int, int, int, int]:
    loc = _locator(record.get(locator_name), input_size=len(input_bytes), allow_zero=allow_zero)
    bs, be = loc["source_byte_start"], loc["source_byte_end"]
    cs, ce = loc["source_character_start"], loc["source_character_end"]
    raw = record.get(raw_name)
    if not isinstance(raw, str):
        raise PackagingMismatch("VTT raw source field is invalid")
    if allow_zero:
        if raw or input_bytes[bs:be] != codecs.BOM_UTF8:
            raise PartialOutputFailure("VTT encoding preamble does not match source")
    else:
        if bs != offsets[cs] or be != offsets[ce]:
            raise PartialOutputFailure("VTT byte and character locators diverge")
        if text[cs:ce] != raw or input_bytes[bs:be].decode("utf-8") != raw:
            raise PartialOutputFailure("VTT locator does not reproduce source text")
    return bs, be, cs, ce


def validate_vtt_candidate(candidate: object, *, input_bytes: bytes) -> dict[str, object]:
    if not isinstance(candidate, dict):
        raise PackagingMismatch("VTT candidate is not an object")
    required = {"coverage", "elements", "encoding", "line_ending_profile", "regions", "warnings"}
    if set(candidate) != required:
        raise PackagingMismatch("VTT candidate fields diverge from the contract")
    if candidate.get("encoding") != "utf-8":
        raise PackagingMismatch("VTT candidate encoding is not admitted")
    warnings = candidate.get("warnings")
    elements = candidate.get("elements")
    regions = candidate.get("regions")
    if not isinstance(warnings, list) or warnings != sorted(set(warnings)):
        raise PackagingMismatch("VTT warnings are not canonical")
    if any(value not in VTT_ALLOWED_WARNINGS for value in warnings):
        raise PackagingMismatch("VTT warning vocabulary is invalid")
    if not isinstance(elements, list) or not isinstance(regions, list):
        raise PackagingMismatch("VTT candidate arrays are malformed")
    coverage = validate_coverage(candidate.get("coverage"), input_size=len(input_bytes))
    if coverage["emitted_element_count"] != len(elements) or coverage["emitted_region_count"] != len(regions):
        raise PartialOutputFailure("VTT coverage counts diverge from emitted records")

    text, bom_size = _source(input_bytes)
    offsets = _offsets(text, bom_size)
    byte_spans: list[tuple[int, int]] = []
    char_spans: list[tuple[int, int]] = []
    preambles = 0
    for ordinal, region in enumerate(regions):
        if not isinstance(region, dict) or region.get("ordinal") != ordinal:
            raise PackagingMismatch("VTT region ordinal is invalid")
        kind = region.get("kind")
        if kind not in {"encoding_preamble", "file_header", "note_block", "blank_separator"}:
            raise PackagingMismatch("VTT region kind is invalid")
        bs, be, cs, ce = _validate_record_slice(
            region, text=text, offsets=offsets, input_bytes=input_bytes,
            locator_name="source_locator", raw_name="raw_text",
            allow_zero=kind == "encoding_preamble",
        )
        if region.get("content_sha256") != sha256_bytes(
            input_bytes[bs:be] if kind == "encoding_preamble" else str(region["raw_text"]).encode("utf-8")
        ):
            raise PackagingMismatch("VTT region content hash is invalid")
        byte_spans.append((bs, be))
        if kind == "encoding_preamble":
            preambles += 1
        else:
            char_spans.append((cs, ce))

    element_fields = {
        "content_sha256", "cue_identifier", "cue_payload_raw", "cue_payload_source_locator",
        "end_milliseconds", "kind", "normalized_text", "ordinal", "raw_text", "settings",
        "source_locator", "start_milliseconds", "timing_line_raw", "timing_line_source_locator",
        "warnings",
    }
    for ordinal, element in enumerate(elements):
        if not isinstance(element, dict) or set(element) != element_fields or element.get("ordinal") != ordinal:
            raise PackagingMismatch("VTT cue fields or ordinal are invalid")
        if element.get("kind") != "webvtt_cue" or element.get("warnings") != warnings:
            raise PackagingMismatch("VTT cue kind or warnings are invalid")
        bs, be, cs, ce = _validate_record_slice(
            element, text=text, offsets=offsets, input_bytes=input_bytes,
            locator_name="source_locator", raw_name="raw_text",
        )
        if element.get("content_sha256") != sha256_bytes(str(element["raw_text"]).encode("utf-8")):
            raise PackagingMismatch("VTT cue content hash is invalid")
        byte_spans.append((bs, be))
        char_spans.append((cs, ce))
        for locator_name, raw_name in (
            ("timing_line_source_locator", "timing_line_raw"),
            ("cue_payload_source_locator", "cue_payload_raw"),
        ):
            nbs, nbe, ncs, nce = _validate_record_slice(
                element, text=text, offsets=offsets, input_bytes=input_bytes,
                locator_name=locator_name, raw_name=raw_name,
            )
            if not (bs <= nbs < nbe <= be and cs <= ncs < nce <= ce):
                raise PartialOutputFailure("VTT nested cue locator escapes its cue")
        settings = element.get("settings")
        if not isinstance(settings, list):
            raise PackagingMismatch("VTT settings are malformed")
        for setting_ordinal, setting in enumerate(settings):
            if not isinstance(setting, dict) or set(setting) != {"name", "ordinal", "raw_text", "recognized", "value"}:
                raise PackagingMismatch("VTT setting fields are invalid")
            if setting.get("ordinal") != setting_ordinal or type(setting.get("recognized")) is not bool:
                raise PackagingMismatch("VTT setting metadata is invalid")

    if preambles != (1 if bom_size else 0):
        raise PartialOutputFailure("VTT encoding preamble coverage is incomplete")
    for spans, expected, label in (
        (sorted(byte_spans), len(input_bytes), "byte"),
        (sorted(char_spans), len(text), "character"),
    ):
        cursor = 0
        for start, end in spans:
            if start != cursor:
                raise PartialOutputFailure(f"VTT {label} locators contain a gap or overlap")
            cursor = end
        if cursor != expected:
            raise PartialOutputFailure(f"VTT {label} locators omit source content")

    from .parsers.vtt_v1 import parse_bytes

    expected = parse_bytes(input_bytes, INITIAL_VTT_CONFIG)
    if canonical_json(expected) != canonical_json(candidate):
        raise PackagingMismatch("VTT candidate diverges from the deterministic contract")
    return {
        "coverage": coverage,
        "elements": elements,
        "encoding": "utf-8",
        "line_ending_profile": candidate["line_ending_profile"],
        "regions": regions,
        "warnings": warnings,
    }


def assemble_vtt_normalized_package(
    *, candidate: object, input_bytes: bytes, vault_account_id: str,
    source_artifact_sha256: str, parser_tuple: ParserTuple, parser_admission_id: str,
) -> tuple[dict[str, object], bytes]:
    core = validate_vtt_candidate(candidate, input_bytes=input_bytes)
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
    if rendered.startswith(codecs.BOM_UTF8) or rendered.endswith(b"\n"):
        raise PackagingMismatch("VTT canonical package framing is invalid")
    return package, rendered


def sha256_file(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
