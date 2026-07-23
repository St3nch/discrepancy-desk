from __future__ import annotations

import codecs
import re
from dataclasses import dataclass

from discrepancy_desk.parser_contract import EncodingFailure, LimitExceeded, MalformedInput, sha256_bytes

_LINE_PATTERN = re.compile(r"[^\r\n]*(?:\r\n|\r|\n|$)")
_SIGNATURE = re.compile(r"^WEBVTT(?:[ \t](?P<header>.*))?$")
_TIMESTAMP_TOKEN = r"(?:(?P<{p}h>\d{{2,}}):)?(?P<{p}m>\d{{2}}):(?P<{p}s>\d{{2}})\.(?P<{p}ms>\d{{3}})"
_TIMING = re.compile(
    "^"
    + _TIMESTAMP_TOKEN.format(p="s")
    + r"[ \t]+-->[ \t]+"
    + _TIMESTAMP_TOKEN.format(p="e")
    + r"(?P<settings>(?:[ \t]+.*)?)$"
)
_SETTING_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_PERCENTAGE = re.compile(r"^(?P<value>\d{1,3})%$")
_LINE_VALUE = re.compile(r"^(?P<base>-?\d+|\d{1,3}%)(?:,(?P<anchor>start|center|end))?$")
_POSITION_VALUE = re.compile(r"^(?P<base>\d{1,3}%)(?:,(?P<anchor>line-left|center|line-right))?$")


@dataclass(frozen=True, slots=True)
class _Line:
    content: str
    full_text: str
    char_start: int
    char_end: int
    line_number: int

    @property
    def blank(self) -> bool:
        return not self.content.strip()


def _decode(data: bytes) -> tuple[str, int, list[str]]:
    warnings: list[str] = []
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        raise EncodingFailure("WebVTT admits UTF-8 only")
    bom_size = len(codecs.BOM_UTF8) if data.startswith(codecs.BOM_UTF8) else 0
    payload = data[bom_size:]
    if bom_size:
        warnings.append("encoding_bom_removed")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise EncodingFailure("input cannot be decoded as strict UTF-8 WebVTT") from exc
    if "\ufffd" in text:
        raise EncodingFailure("replacement-character recovery is prohibited")
    if "\x00" in text:
        raise MalformedInput("NUL-bearing input is rejected as binary-like")
    return text, bom_size, warnings


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
        raise RuntimeError("WebVTT line scanner failed to consume the decoded input")
    return result


def _byte_offsets(text: str, *, bom_size: int) -> list[int]:
    offsets = [bom_size]
    current = bom_size
    for character in text:
        current += len(character.encode("utf-8"))
        offsets.append(current)
    return offsets


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


def _locator(
    *, byte_start: int, byte_end: int, char_start: int, char_end: int,
    line_start: int, line_end: int,
) -> dict[str, int]:
    return {
        "source_byte_end": byte_end,
        "source_byte_start": byte_start,
        "source_character_end": char_end,
        "source_character_start": char_start,
        "source_line_end": line_end,
        "source_line_start": line_start,
    }


def _timestamp_ms(match: re.Match[str], prefix: str, maximum: int) -> int:
    hours_text = match.group(prefix + "h")
    hours = int(hours_text) if hours_text is not None else 0
    minutes = int(match.group(prefix + "m"))
    seconds = int(match.group(prefix + "s"))
    milliseconds = int(match.group(prefix + "ms"))
    if minutes >= 60 or seconds >= 60:
        raise MalformedInput("WebVTT timestamp fields are invalid")
    total = ((hours * 60 + minutes) * 60 + seconds) * 1000 + milliseconds
    if total > maximum:
        raise LimitExceeded("WebVTT timestamp exceeds the configured maximum")
    return total


def _valid_percentage(value: str) -> bool:
    match = _PERCENTAGE.fullmatch(value)
    return match is not None and int(match.group("value")) <= 100


def _parse_setting(name: str, value: str) -> bool:
    if name == "vertical":
        return value in {"rl", "lr"}
    if name == "line":
        match = _LINE_VALUE.fullmatch(value)
        if match is None:
            return False
        base = match.group("base")
        if base.startswith("+"):
            return False
        return not base.endswith("%") or _valid_percentage(base)
    if name == "position":
        match = _POSITION_VALUE.fullmatch(value)
        return match is not None and _valid_percentage(match.group("base"))
    if name == "size":
        return _valid_percentage(value)
    if name == "align":
        return value in {"start", "center", "end", "left", "right"}
    return True


def _settings(raw: str, config: dict[str, object], warnings: list[str]) -> list[dict[str, object]]:
    if not raw:
        return []
    tokens = re.split(r"[ \t]+", raw.strip())
    if len(tokens) > int(config["maximum_settings_per_cue"]):
        raise LimitExceeded("WebVTT cue exceeds the settings-count limit")
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for ordinal, token in enumerate(tokens):
        if len(token.encode("utf-8")) > int(config["maximum_setting_token_bytes"]):
            raise LimitExceeded("WebVTT setting token exceeds the byte limit")
        if token.count(":") != 1:
            raise MalformedInput("WebVTT cue setting is malformed")
        name, value = token.split(":", 1)
        if not name or not value or _SETTING_NAME.fullmatch(name) is None:
            raise MalformedInput("WebVTT cue setting is malformed")
        if name in seen:
            raise MalformedInput("WebVTT cue setting name is duplicated")
        seen.add(name)
        if name == "region":
            raise MalformedInput("WebVTT region cue settings are outside the admitted subset")
        recognized = name in {"vertical", "line", "position", "size", "align"}
        if recognized and not _parse_setting(name, value):
            raise MalformedInput("WebVTT recognized cue setting has an invalid value")
        if not recognized:
            warnings.append("unsupported_cue_setting_preserved")
        result.append(
            {
                "name": name,
                "ordinal": ordinal,
                "raw_text": token,
                "recognized": recognized,
                "value": value,
            }
        )
    return result


def parse_bytes(data: bytes, config: dict[str, object]) -> dict[str, object]:
    if len(data) > int(config["input_size_limit_bytes"]):
        raise LimitExceeded("WebVTT input exceeds the configured size limit")
    text, bom_size, warnings = _decode(data)
    lines = _lines(text)
    if len(lines) > int(config["line_limit"]):
        raise LimitExceeded("WebVTT input exceeds the logical-line limit")
    if not lines:
        raise MalformedInput("WebVTT signature is missing")
    offsets = _byte_offsets(text, bom_size=bom_size)
    profile = _line_ending_profile(text)
    if profile not in {"none", "LF"}:
        warnings.append("line_ending_normalized")

    signature = _SIGNATURE.fullmatch(lines[0].content)
    if signature is None:
        raise MalformedInput("WebVTT signature is malformed")
    header_text = signature.group("header") or ""
    if "-->" in header_text or "X-TIMESTAMP-MAP" in header_text.upper():
        raise MalformedInput("WebVTT header extension is outside the admitted subset")
    if len(lines[0].full_text.encode("utf-8")) > int(config["maximum_header_bytes"]):
        raise LimitExceeded("WebVTT header exceeds the configured byte limit")
    if len(lines) < 2 or not lines[1].blank:
        raise MalformedInput("WebVTT signature must be followed by a blank line")

    elements: list[dict[str, object]] = []
    regions: list[dict[str, object]] = []

    def add_region(kind: str, char_start: int, char_end: int, line_start: int, line_end: int, raw: str) -> None:
        regions.append(
            {
                "content_sha256": sha256_bytes(raw.encode("utf-8")) if kind != "encoding_preamble" else sha256_bytes(data[:bom_size]),
                "kind": kind,
                "ordinal": len(regions),
                "raw_text": raw,
                "source_locator": _locator(
                    byte_start=0 if kind == "encoding_preamble" else offsets[char_start],
                    byte_end=bom_size if kind == "encoding_preamble" else offsets[char_end],
                    char_start=char_start,
                    char_end=char_end,
                    line_start=line_start,
                    line_end=line_end,
                ),
            }
        )
        if len(regions) > int(config["region_limit"]):
            raise LimitExceeded("WebVTT input exceeds the region limit")

    if bom_size:
        add_region("encoding_preamble", 0, 0, 0, 0, "")
    add_region("file_header", lines[0].char_start, lines[0].char_end, 1, 1, lines[0].full_text)

    previous_start: int | None = None
    previous_end: int | None = None
    cue_identifiers: set[str] = set()
    index = 1
    while index < len(lines):
        blank = lines[index].blank
        start = index
        while index < len(lines) and lines[index].blank == blank:
            index += 1
        group = lines[start:index]
        char_start = group[0].char_start
        char_end = group[-1].char_end
        raw_group = text[char_start:char_end]
        if blank:
            add_region(
                "blank_separator", char_start, char_end,
                group[0].line_number, group[-1].line_number, raw_group,
            )
            continue

        first = group[0].content
        upper_first = first.upper()
        if upper_first.startswith("X-TIMESTAMP-MAP"):
            raise MalformedInput("WebVTT timeline mapping is outside the admitted subset")
        if first == "STYLE" or first.startswith(("STYLE ", "STYLE\t")):
            raise MalformedInput("WebVTT STYLE blocks are outside the admitted subset")
        if first == "REGION" or first.startswith(("REGION ", "REGION\t")):
            raise MalformedInput("WebVTT REGION blocks are outside the admitted subset")
        if first == "NOTE" or first.startswith(("NOTE ", "NOTE\t")):
            if any("-->" in line.content for line in group):
                raise MalformedInput("WebVTT NOTE blocks may not contain the cue arrow")
            if len(raw_group.encode("utf-8")) > int(config["maximum_note_bytes"]):
                raise LimitExceeded("WebVTT NOTE block exceeds the configured byte limit")
            add_region(
                "note_block", char_start, char_end,
                group[0].line_number, group[-1].line_number, raw_group,
            )
            continue

        if len(raw_group.encode("utf-8")) > int(config["maximum_cue_bytes"]):
            raise LimitExceeded("WebVTT cue exceeds the configured byte limit")
        cursor = 0
        cue_identifier: str | None = None
        if "-->" not in group[0].content:
            cue_identifier = group[0].content
            if not cue_identifier:
                raise MalformedInput("WebVTT cue identifier is empty")
            if len(cue_identifier.encode("utf-8")) > int(config["maximum_cue_identifier_bytes"]):
                raise LimitExceeded("WebVTT cue identifier exceeds the configured byte limit")
            if cue_identifier in cue_identifiers:
                raise MalformedInput("WebVTT cue identifier is duplicated")
            cue_identifiers.add(cue_identifier)
            cursor = 1
        if cursor >= len(group):
            raise MalformedInput("WebVTT cue timing line is missing")
        timing_line = group[cursor]
        match = _TIMING.fullmatch(timing_line.content)
        if match is None:
            raise MalformedInput("WebVTT cue timing or arrow is malformed")
        start_ms = _timestamp_ms(match, "s", int(config["maximum_timestamp_milliseconds"]))
        end_ms = _timestamp_ms(match, "e", int(config["maximum_timestamp_milliseconds"]))
        if end_ms <= start_ms:
            raise MalformedInput("WebVTT cue duration must be positive")
        if previous_start is not None and start_ms < previous_start:
            raise MalformedInput("WebVTT cue start times must be nondecreasing")
        if previous_end is not None and start_ms < previous_end:
            warnings.append("overlapping_cues")
        previous_start, previous_end = start_ms, end_ms
        setting_records = _settings(match.group("settings").strip(), config, warnings)

        payload_lines = group[cursor + 1:]
        if not payload_lines:
            raise MalformedInput("WebVTT cue payload is missing")
        if any("-->" in line.content for line in payload_lines):
            raise MalformedInput("WebVTT cue payload may not contain the cue arrow")
        payload_start = payload_lines[0].char_start
        payload_end = payload_lines[-1].char_end
        payload = text[payload_start:payload_end]
        if "<" in payload or "&" in payload:
            warnings.append("cue_markup_preserved_inert")
        timing_locator = _locator(
            byte_start=offsets[timing_line.char_start], byte_end=offsets[timing_line.char_end],
            char_start=timing_line.char_start, char_end=timing_line.char_end,
            line_start=timing_line.line_number, line_end=timing_line.line_number,
        )
        payload_locator = _locator(
            byte_start=offsets[payload_start], byte_end=offsets[payload_end],
            char_start=payload_start, char_end=payload_end,
            line_start=payload_lines[0].line_number, line_end=payload_lines[-1].line_number,
        )
        source_locator = _locator(
            byte_start=offsets[char_start], byte_end=offsets[char_end],
            char_start=char_start, char_end=char_end,
            line_start=group[0].line_number, line_end=group[-1].line_number,
        )
        elements.append(
            {
                "content_sha256": sha256_bytes(raw_group.encode("utf-8")),
                "cue_identifier": cue_identifier,
                "cue_payload_raw": payload,
                "cue_payload_source_locator": payload_locator,
                "end_milliseconds": end_ms,
                "kind": "webvtt_cue",
                "normalized_text": payload.replace("\r\n", "\n").replace("\r", "\n"),
                "ordinal": len(elements),
                "raw_text": raw_group,
                "settings": setting_records,
                "source_locator": source_locator,
                "start_milliseconds": start_ms,
                "timing_line_raw": timing_line.full_text,
                "timing_line_source_locator": timing_locator,
                "warnings": [],
            }
        )
        if len(elements) > int(config["cue_limit"]) or len(elements) > int(config["element_limit"]):
            raise LimitExceeded("WebVTT input exceeds the cue or element limit")

    warnings = sorted(set(warnings))
    for element in elements:
        element["warnings"] = list(warnings)
    return {
        "coverage": {
            "complete": True,
            "consumed_byte_ranges": [] if not data else [[0, len(data)]],
            "decoded_character_count": len(text),
            "emitted_element_count": len(elements),
            "emitted_region_count": len(regions),
            "input_byte_count": len(data),
            "source_line_count": len(lines),
        },
        "elements": elements,
        "encoding": "utf-8",
        "line_ending_profile": profile,
        "regions": regions,
        "warnings": warnings,
    }
