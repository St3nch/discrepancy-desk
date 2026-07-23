from __future__ import annotations

import codecs
import re
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
VTT_IMPLEMENTATION_SHA256 = "291c6389a39683a7dab2a471a58773ecc90de711a667e3afb6f0a652d3da850a"
VTT_RESOURCE_MANIFEST_SHA256 = "2723624c58b5bdbfeffd8404b49261ee96de820f0d4a7244e4ae338cce8bc18b"
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


_CONTRACT_TIMESTAMP_TOKEN = r"(?:(?P<{p}h>[0-9]{{2,}}):)?(?P<{p}m>[0-9]{{2}}):(?P<{p}s>[0-9]{{2}})\.(?P<{p}ms>[0-9]{{3}})"
_CONTRACT_TIMING = re.compile(
    "^"
    + _CONTRACT_TIMESTAMP_TOKEN.format(p="s")
    + r"[ \t]+-->[ \t]+"
    + _CONTRACT_TIMESTAMP_TOKEN.format(p="e")
    + r"(?P<settings>(?:[ \t]+.*)?)$"
)
_RECOGNIZED_SETTINGS = frozenset({"vertical", "line", "position", "size", "align"})


def _logical_line_spans(text: str) -> list[tuple[int, int, int]]:
    result: list[tuple[int, int, int]] = []
    cursor = 0
    number = 1
    while cursor < len(text):
        start = cursor
        while cursor < len(text) and text[cursor] not in "\r\n":
            cursor += 1
        if cursor < len(text):
            if text[cursor] == "\r" and cursor + 1 < len(text) and text[cursor + 1] == "\n":
                cursor += 2
            else:
                cursor += 1
        result.append((start, cursor, number))
        number += 1
    return result


def _line_ending_profile(text: str) -> str:
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


def _strip_line_ending(raw: str) -> str:
    if raw.endswith("\r\n"):
        return raw[:-2]
    if raw.endswith(("\r", "\n")):
        return raw[:-1]
    return raw


def _timestamp_from_match(match: re.Match[str], prefix: str) -> int:
    hours = int(match.group(prefix + "h") or "0")
    minutes = int(match.group(prefix + "m"))
    seconds = int(match.group(prefix + "s"))
    milliseconds = int(match.group(prefix + "ms"))
    if minutes >= 60 or seconds >= 60:
        raise PackagingMismatch("VTT timing source fields are invalid")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + milliseconds


def _validate_exact_line_locator(
    locator: dict[str, int],
    *,
    char_start: int,
    char_end: int,
    starts: dict[int, int],
    ends: dict[int, int],
) -> None:
    expected_start = starts.get(char_start)
    expected_end = ends.get(char_end)
    if expected_start is None or expected_end is None or expected_end < expected_start:
        raise PartialOutputFailure("VTT locator does not align to complete logical lines")
    if (
        locator["source_line_start"] != expected_start
        or locator["source_line_end"] != expected_end
    ):
        raise PartialOutputFailure("VTT line locator does not reproduce source lines")


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
        if result["source_line_start"] != 0 or result["source_line_end"] != 0:
            raise PartialOutputFailure("VTT encoding preamble line locator is invalid")
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
    logical_lines = _logical_line_spans(text)
    line_starts = {start: number for start, _end, number in logical_lines}
    line_ends = {end: number for _start, end, number in logical_lines}
    profile = _line_ending_profile(text)
    if coverage["decoded_character_count"] != len(text):
        raise PartialOutputFailure("VTT decoded-character count diverges from source")
    if coverage["source_line_count"] != len(logical_lines):
        raise PartialOutputFailure("VTT source-line count diverges from source")
    if candidate.get("line_ending_profile") != profile:
        raise PartialOutputFailure("VTT line-ending profile diverges from source")
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
            _validate_exact_line_locator(
                region["source_locator"],
                char_start=cs,
                char_end=ce,
                starts=line_starts,
                ends=line_ends,
            )
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
        _validate_exact_line_locator(
            element["source_locator"],
            char_start=cs,
            char_end=ce,
            starts=line_starts,
            ends=line_ends,
        )
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
            _validate_exact_line_locator(
                element[locator_name],
                char_start=ncs,
                char_end=nce,
                starts=line_starts,
                ends=line_ends,
            )
        timing_content = _strip_line_ending(str(element["timing_line_raw"]))
        timing_match = _CONTRACT_TIMING.fullmatch(timing_content)
        if timing_match is None:
            raise PackagingMismatch("VTT timing source does not match the independent grammar")
        independent_start = _timestamp_from_match(timing_match, "s")
        independent_end = _timestamp_from_match(timing_match, "e")
        if (
            element.get("start_milliseconds") != independent_start
            or element.get("end_milliseconds") != independent_end
        ):
            raise PartialOutputFailure("VTT emitted timestamps diverge from timing source")
        payload = str(element["cue_payload_raw"])
        if element.get("normalized_text") != payload.replace("\r\n", "\n").replace("\r", "\n"):
            raise PartialOutputFailure("VTT normalized payload diverges from source")
        settings = element.get("settings")
        if not isinstance(settings, list):
            raise PackagingMismatch("VTT settings are malformed")
        raw_settings = timing_match.group("settings").strip()
        setting_tokens = re.split(r"[ \t]+", raw_settings) if raw_settings else []
        if len(settings) != len(setting_tokens):
            raise PartialOutputFailure("VTT setting records diverge from timing source")
        for setting_ordinal, (setting, token) in enumerate(zip(settings, setting_tokens, strict=True)):
            if not isinstance(setting, dict) or set(setting) != {"name", "ordinal", "raw_text", "recognized", "value"}:
                raise PackagingMismatch("VTT setting fields are invalid")
            if setting.get("ordinal") != setting_ordinal or type(setting.get("recognized")) is not bool:
                raise PackagingMismatch("VTT setting metadata is invalid")
            if token.count(":") != 1:
                raise PackagingMismatch("VTT timing source contains a malformed setting")
            name, value = token.split(":", 1)
            expected_recognized = name in _RECOGNIZED_SETTINGS
            if (
                setting.get("raw_text") != token
                or setting.get("name") != name
                or setting.get("value") != value
                or setting.get("recognized") is not expected_recognized
            ):
                raise PartialOutputFailure("VTT setting metadata diverges from timing source")

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

    expected_warnings: set[str] = set()
    if bom_size:
        expected_warnings.add("encoding_bom_removed")
    if profile not in {"none", "LF"}:
        expected_warnings.add("line_ending_normalized")
    previous_end: int | None = None
    for element in elements:
        start_value = int(element["start_milliseconds"])
        end_value = int(element["end_milliseconds"])
        if previous_end is not None and start_value < previous_end:
            expected_warnings.add("overlapping_cues")
        previous_end = end_value
        payload = str(element["cue_payload_raw"])
        if "<" in payload or "&" in payload:
            expected_warnings.add("cue_markup_preserved_inert")
        if any(setting.get("recognized") is False for setting in element["settings"]):
            expected_warnings.add("unsupported_cue_setting_preserved")
    if warnings != sorted(expected_warnings):
        raise PartialOutputFailure("VTT warning facts diverge from source")
    for element in elements:
        if element.get("warnings") != warnings:
            raise PartialOutputFailure("VTT element warnings diverge from candidate warnings")

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
