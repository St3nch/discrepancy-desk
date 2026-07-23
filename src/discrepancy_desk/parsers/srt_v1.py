from __future__ import annotations

import codecs
import re
from dataclasses import dataclass

from discrepancy_desk.parser_contract import (
    EncodingFailure,
    LimitExceeded,
    MalformedInput,
    sha256_bytes,
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

    @property
    def blank(self) -> bool:
        return not self.content.strip()


def _decode(data: bytes) -> tuple[str, str, int, list[str]]:
    warnings: list[str] = []
    if data.startswith(codecs.BOM_UTF8):
        encoding = "utf-8"
        bom_size = len(codecs.BOM_UTF8)
        payload = data[bom_size:]
        warnings.append("encoding_bom_removed")
    elif data.startswith(codecs.BOM_UTF16_LE):
        encoding = "utf-16-le"
        bom_size = len(codecs.BOM_UTF16_LE)
        payload = data[bom_size:]
        warnings.append("encoding_bom_removed")
    elif data.startswith(codecs.BOM_UTF16_BE):
        encoding = "utf-16-be"
        bom_size = len(codecs.BOM_UTF16_BE)
        payload = data[bom_size:]
        warnings.append("encoding_bom_removed")
    else:
        encoding = "utf-8"
        bom_size = 0
        payload = data
        if len(payload) >= 4 and len(payload) % 2 == 0:
            half = len(payload) // 2
            if payload[0::2].count(0) * 4 >= half * 3 or payload[1::2].count(0) * 4 >= half * 3:
                raise EncodingFailure("UTF-16-like input requires an explicit BOM")
    try:
        text = payload.decode(encoding, errors="strict")
    except UnicodeDecodeError as exc:
        raise EncodingFailure("input cannot be decoded under the explicit SRT encoding contract") from exc
    if "\ufffd" in text:
        raise EncodingFailure("replacement-character recovery is prohibited")
    if "\x00" in text:
        raise MalformedInput("NUL-bearing input is rejected as binary-like")
    return text, encoding, bom_size, warnings


def _byte_offsets(text: str, *, encoding: str, bom_size: int) -> list[int]:
    offsets = [bom_size]
    current = bom_size
    for character in text:
        current += len(character.encode(encoding))
        offsets.append(current)
    return offsets


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
        raise RuntimeError("SRT line scanner failed to consume the decoded input")
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


def _locator(
    *,
    byte_start: int,
    byte_end: int,
    char_start: int,
    char_end: int,
    line_start: int,
    line_end: int,
) -> dict[str, int]:
    return {
        "source_byte_end": byte_end,
        "source_byte_start": byte_start,
        "source_character_end": char_end,
        "source_character_start": char_start,
        "source_line_end": line_end,
        "source_line_start": line_start,
    }


def _timestamp_milliseconds(match: re.Match[str], prefix: str, maximum: int) -> int:
    hours = int(match.group(prefix + "h"))
    minutes = int(match.group(prefix + "m"))
    seconds = int(match.group(prefix + "s"))
    milliseconds = int(match.group(prefix + "ms"))
    if minutes >= 60 or seconds >= 60:
        raise MalformedInput("SRT timestamp fields are invalid")
    total = ((hours * 60 + minutes) * 60 + seconds) * 1000 + milliseconds
    if total > maximum:
        raise LimitExceeded("SRT timestamp exceeds the configured maximum")
    return total


def parse_bytes(data: bytes, config: dict[str, object]) -> dict[str, object]:
    size_limit = int(config["input_size_limit_bytes"])
    cue_limit = int(config["cue_limit"])
    maximum_cue_bytes = int(config["maximum_cue_bytes"])
    line_limit = int(config["line_limit"])
    maximum_timestamp = int(config["maximum_timestamp_milliseconds"])
    if len(data) > size_limit:
        raise LimitExceeded("SRT input exceeds the configured size limit")

    text, encoding, bom_size, warnings = _decode(data)
    lines = _lines(text)
    if len(lines) > line_limit:
        raise LimitExceeded("SRT input exceeds the configured logical-line limit")
    offsets = _byte_offsets(text, encoding=encoding, bom_size=bom_size)
    profile = _line_ending_profile(text)
    if profile not in {"none", "LF"}:
        warnings.append("line_ending_normalized")

    elements: list[dict[str, object]] = []
    regions: list[dict[str, object]] = []
    if bom_size:
        regions.append(
            {
                "content_sha256": sha256_bytes(data[:bom_size]),
                "kind": "encoding_preamble",
                "ordinal": 0,
                "raw_text": "",
                "source_locator": _locator(
                    byte_start=0,
                    byte_end=bom_size,
                    char_start=0,
                    char_end=0,
                    line_start=0,
                    line_end=0,
                ),
            }
        )

    previous_end: int | None = None
    previous_index: int | None = None
    index = 0
    while index < len(lines):
        blank = lines[index].blank
        start = index
        while index < len(lines) and lines[index].blank == blank:
            index += 1
        group = lines[start:index]
        char_start = group[0].char_start
        char_end = group[-1].char_end
        raw_group = text[char_start:char_end]
        group_locator = _locator(
            byte_start=offsets[char_start],
            byte_end=offsets[char_end],
            char_start=char_start,
            char_end=char_end,
            line_start=group[0].line_number,
            line_end=group[-1].line_number,
        )
        if blank:
            regions.append(
                {
                    "content_sha256": sha256_bytes(raw_group.encode("utf-8")),
                    "kind": "blank_separator",
                    "ordinal": len(regions),
                    "raw_text": raw_group,
                    "source_locator": group_locator,
                }
            )
            continue

        if offsets[char_end] - offsets[char_start] > maximum_cue_bytes:
            raise LimitExceeded("SRT cue exceeds the configured byte limit")
        cursor = 0
        cue_index: int | None = None
        if group[0].content.isdigit():
            cue_index = int(group[0].content)
            cursor = 1
        if cursor >= len(group):
            raise MalformedInput("SRT cue is missing its timestamp line")
        timestamp_line = group[cursor]
        match = _TIMESTAMP.fullmatch(timestamp_line.content)
        if match is None:
            raise MalformedInput("SRT timestamp or arrow is malformed")
        start_ms = _timestamp_milliseconds(match, "s", maximum_timestamp)
        end_ms = _timestamp_milliseconds(match, "e", maximum_timestamp)
        if end_ms < start_ms:
            raise MalformedInput("SRT cue has a negative duration")
        text_lines = group[cursor + 1 :]
        if not text_lines:
            raise MalformedInput("SRT cue is missing cue text")
        for position, line in enumerate(text_lines):
            if _TIMESTAMP.fullmatch(line.content):
                raise MalformedInput("SRT cues require blank-line separation")
            if line.content.isdigit() and position + 1 < len(text_lines):
                if _TIMESTAMP.fullmatch(text_lines[position + 1].content):
                    raise MalformedInput("SRT cues require blank-line separation")

        cue_text_start = text_lines[0].char_start
        cue_text_end = text_lines[-1].char_end
        cue_text = text[cue_text_start:cue_text_end]
        cue_text_locator = _locator(
            byte_start=offsets[cue_text_start],
            byte_end=offsets[cue_text_end],
            char_start=cue_text_start,
            char_end=cue_text_end,
            line_start=text_lines[0].line_number,
            line_end=text_lines[-1].line_number,
        )
        if cue_index is not None and previous_index is not None and cue_index != previous_index + 1:
            warnings.append("nonsequential_cue_index")
        if previous_end is not None and start_ms < previous_end:
            warnings.append("overlapping_cues")
        if cue_index is not None:
            previous_index = cue_index
        previous_end = end_ms
        elements.append(
            {
                "content_sha256": sha256_bytes(raw_group.encode("utf-8")),
                "cue_index": cue_index,
                "cue_text_raw": cue_text,
                "cue_text_source_locator": cue_text_locator,
                "end_milliseconds": end_ms,
                "kind": "subtitle_cue",
                "normalized_text": cue_text.replace("\r\n", "\n").replace("\r", "\n"),
                "ordinal": len(elements),
                "raw_text": raw_group,
                "source_locator": group_locator,
                "start_milliseconds": start_ms,
                "warnings": [],
            }
        )
        if len(elements) > cue_limit:
            raise LimitExceeded("SRT input exceeds the configured cue limit")

    if not elements:
        raise MalformedInput("SRT input contains no cues")
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
        "encoding": encoding,
        "line_ending_profile": profile,
        "regions": regions,
        "warnings": warnings,
    }
