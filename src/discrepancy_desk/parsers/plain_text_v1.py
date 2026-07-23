from __future__ import annotations

import codecs
import re
from dataclasses import dataclass

from discrepancy_desk.parser_contract import (
    EncodingFailure,
    INITIAL_TEXT_CONFIG,
    LimitExceeded,
    MalformedInput,
    sha256_bytes,
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
        if payload.startswith((b"\xff\xfe", b"\xfe\xff")):
            raise EncodingFailure("UTF-16 requires an explicit BOM")
        if len(payload) >= 4 and len(payload) % 2 == 0:
            even_nuls = payload[0::2].count(0)
            odd_nuls = payload[1::2].count(0)
            half = len(payload) // 2
            if even_nuls * 4 >= half * 3 or odd_nuls * 4 >= half * 3:
                raise EncodingFailure("UTF-16-like input requires an explicit BOM")
    try:
        text = payload.decode(encoding, errors="strict")
    except UnicodeDecodeError as exc:
        raise EncodingFailure("input cannot be decoded under the explicit encoding contract") from exc
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
        result.append(
            _Line(
                content=content,
                full_text=full,
                char_start=cursor,
                char_end=end,
                line_number=line_number,
            )
        )
        cursor = end
        line_number += 1
    if cursor != len(text):
        raise RuntimeError("plain-text line scanner failed to consume the decoded input")
    return result


def _line_ending_profile(text: str) -> str:
    has_crlf = "\r\n" in text
    without_crlf = text.replace("\r\n", "")
    has_cr = "\r" in without_crlf
    has_lf = "\n" in without_crlf
    values = [name for present, name in ((has_crlf, "CRLF"), (has_cr, "CR"), (has_lf, "LF")) if present]
    if not values:
        return "none"
    if len(values) == 1:
        return values[0]
    return "mixed:" + ",".join(values)


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


def parse_bytes(data: bytes, config: dict[str, object] | None = None) -> dict[str, object]:
    effective = dict(INITIAL_TEXT_CONFIG if config is None else config)
    size_limit = int(effective["input_size_limit_bytes"])
    character_limit = int(effective["character_limit"])
    line_limit = int(effective["line_limit"])
    maximum_line_bytes = int(effective["maximum_line_bytes"])
    element_limit = int(effective["element_limit"])
    if len(data) > size_limit:
        raise LimitExceeded("input exceeds the configured size limit")

    text, encoding, bom_size, warnings = _decode(data)
    if len(text) > character_limit:
        raise LimitExceeded("decoded input exceeds the configured character limit")
    lines = _lines(text)
    if len(lines) > line_limit:
        raise LimitExceeded("input exceeds the configured logical-line limit")
    offsets = _byte_offsets(text, encoding=encoding, bom_size=bom_size)
    for line in lines:
        content_end = line.char_start + len(line.content)
        if offsets[content_end] - offsets[line.char_start] > maximum_line_bytes:
            raise LimitExceeded("a logical line exceeds the configured byte limit")

    profile = _line_ending_profile(text)
    if profile not in {"none", "LF"}:
        warnings.append("line_ending_normalized")
    warnings = sorted(set(warnings))

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
    index = 0
    while index < len(lines):
        blank = lines[index].blank
        start = index
        while index < len(lines) and lines[index].blank == blank:
            index += 1
        group = lines[start:index]
        char_start = group[0].char_start
        char_end = group[-1].char_end
        raw_text = text[char_start:char_end]
        locator = _locator(
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
                    "content_sha256": sha256_bytes(raw_text.encode("utf-8")),
                    "kind": "blank_separator",
                    "ordinal": len(regions),
                    "raw_text": raw_text,
                    "source_locator": locator,
                }
            )
        else:
            normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
            elements.append(
                {
                    "content_sha256": sha256_bytes(raw_text.encode("utf-8")),
                    "kind": "paragraph",
                    "normalized_text": normalized,
                    "ordinal": len(elements),
                    "raw_text": raw_text,
                    "source_locator": locator,
                    "warnings": list(warnings),
                }
            )
            if len(elements) > element_limit:
                raise LimitExceeded("input exceeds the configured element limit")

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
