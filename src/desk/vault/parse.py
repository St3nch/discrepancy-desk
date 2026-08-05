"""Parse capture bytes into ordered elements with locators.

Parser output is an observation, not truth (R-M06-04). Locators are stable
addresses within this document_version for claim binding.

Quotation surface (F-13): claim verification compares against elements.text, not
raw Vault bytes. This module *derives* that text (strip, join, charrefs).
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Final

from desk.refusals import DeskRefusal

PARSER_NAME: Final[str] = "desk.html.stdlib-v1"

# Media types this parser genuinely handles. Everything else → CAPTURE_UNSUPPORTED_TYPE.
_SUPPORTED_TYPE_MARKERS: Final[tuple[str, ...]] = (
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "text/markdown",
    "text/csv",
)


@dataclass(frozen=True, slots=True)
class ParsedElement:
    ordinal: int
    locator: str
    element_type: str
    text: str


_BLOCK_TAGS = frozenset(
    {
        "p",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "pre",
        "blockquote",
        "td",
        "th",
        "dt",
        "dd",
        "figcaption",
        "caption",
    }
)


class _BlockCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[str] = []
        self._buf: list[str] = []
        self.blocks: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _BLOCK_TAGS:
            self._stack.append(tag)
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _BLOCK_TAGS and self._stack and self._stack[-1] == tag:
            text = "".join(self._buf).strip()
            if text:
                self.blocks.append((tag, text))
            self._stack.pop()
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._stack:
            self._buf.append(data)


def normalize_media_type(content_type: str) -> str:
    """Return lowercased type/subtype without parameters."""
    return content_type.split(";")[0].strip().lower() or "application/octet-stream"


def assert_content_type_supported(content_type: str, data: bytes) -> str:
    """Refuse types we cannot parse into a real quotation surface (F-14).

    Returns the normalized media type when supported.
    """
    media = normalize_media_type(content_type)
    if media in _SUPPORTED_TYPE_MARKERS:
        return media
    if media.startswith("text/") and "html" in media:
        return media
    # Sniff HTML when the server lied or omitted a type.
    if _looks_like_html(data):
        return "text/html"
    raise DeskRefusal(
        code="CAPTURE_UNSUPPORTED_TYPE",
        what_happened=(
            f"Content type {media!r} is not supported by the current parser "
            f"({PARSER_NAME}). Only HTML and plain text families are handled."
        ),
        what_was_preserved="Existing captures and the run budget are unchanged.",
        what_was_not_changed=("No capture was written to the Record or Vault for this response."),
        what_you_can_do=(
            f"Capture an HTML or plain-text resource, or wait until a parser for {media!r} exists."
        ),
    )


def parse_bytes(data: bytes, content_type: str) -> list[ParsedElement]:
    """Parse raw bytes into locator-addressable elements.

    Call assert_content_type_supported first — this function assumes a supported type.
    """
    media = normalize_media_type(content_type)
    if "html" in media or _looks_like_html(data):
        return _parse_html(data)
    return _parse_plain(data)


def _looks_like_html(data: bytes) -> bool:
    sample = data[:200].lstrip().lower()
    return sample.startswith(b"<!doctype html") or sample.startswith(b"<html")


def _parse_html(data: bytes) -> list[ParsedElement]:
    text = data.decode("utf-8", errors="replace")
    collector = _BlockCollector()
    collector.feed(text)
    collector.close()
    if not collector.blocks:
        stripped = " ".join(text.split())
        if stripped:
            return [
                ParsedElement(
                    ordinal=0,
                    locator="e/0",
                    element_type="document",
                    text=stripped,
                )
            ]
        return []
    return [
        ParsedElement(
            ordinal=i,
            locator=f"e/{i}",
            element_type=tag,
            text=block_text,
        )
        for i, (tag, block_text) in enumerate(collector.blocks)
    ]


def _parse_plain(data: bytes) -> list[ParsedElement]:
    text = data.decode("utf-8", errors="replace")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs and text.strip():
        paragraphs = [text.strip()]
    return [
        ParsedElement(
            ordinal=i,
            locator=f"e/{i}",
            element_type="paragraph",
            text=p,
        )
        for i, p in enumerate(paragraphs)
    ]
