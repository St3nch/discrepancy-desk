from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from discrepancy_desk.parser_contract import (
    EncodingFailure,
    INITIAL_TEXT_CONFIG,
    LimitExceeded,
    MalformedInput,
    canonical_json,
)
from discrepancy_desk.parsers.plain_text_v1 import parse_bytes


def _fixtures() -> Path:
    return Path(__file__).parent / "fixtures" / "m06a" / "parsers"


def _config(**overrides: object) -> dict[str, object]:
    return {**INITIAL_TEXT_CONFIG, **overrides}


def test_fixture_manifest_is_complete_and_exact() -> None:
    root = _fixtures()
    entries: dict[str, tuple[str, int]] = {}
    for line in (root / "manifest.sha256").read_text(encoding="utf-8").splitlines():
        name, digest, size = line.split(" ")
        entries[name] = (digest, int(size))
    actual = {path.name for path in root.iterdir() if path.is_file() and path.name != "manifest.sha256"}
    assert set(entries) == actual
    for name, (digest, size) in entries.items():
        data = (root / name).read_bytes()
        assert len(data) == size
        assert hashlib.sha256(data).hexdigest() == digest


def test_plain_text_corpus_preserves_complete_coverage_and_stable_bytes() -> None:
    root = _fixtures()
    accepted = (
        "ascii_utf8.txt",
        "multilingual_utf8.txt",
        "utf8_bom.txt",
        "utf16_le.txt",
        "utf16_be.txt",
        "lf.txt",
        "crlf.txt",
        "cr_utf16_le.bin",
        "empty.txt",
        "leading_trailing_blank_utf16_le.bin",
        "repeated_blank.txt",
        "combining.txt",
        "zero_width.txt",
    )
    for name in accepted:
        data = (root / name).read_bytes()
        first = parse_bytes(data)
        second = parse_bytes(data)
        assert canonical_json(first) == canonical_json(second)
        assert first["coverage"]["input_byte_count"] == len(data)
        assert first["coverage"]["complete"] is True
        assert first["coverage"]["consumed_byte_ranges"] == ([] if not data else [[0, len(data)]])


def test_m06a_ht_042_limits_fail_closed() -> None:
    admitted = parse_bytes(b"12345678", _config(input_size_limit_bytes=8))
    assert admitted["coverage"]["complete"] is True
    with pytest.raises(LimitExceeded, match="size limit"):
        parse_bytes(b"123456789", _config(input_size_limit_bytes=8))

    admitted_line = parse_bytes(b"12345678", _config(maximum_line_bytes=8))
    assert admitted_line["coverage"]["complete"] is True
    with pytest.raises(LimitExceeded, match="logical line"):
        parse_bytes(b"123456789", _config(maximum_line_bytes=8))

    with pytest.raises(LimitExceeded, match="logical-line"):
        parse_bytes(b"a\nb\nc", _config(line_limit=2))
    with pytest.raises(LimitExceeded, match="element limit"):
        parse_bytes(b"a\n\nb", _config(element_limit=1))
    with pytest.raises(LimitExceeded, match="character limit"):
        parse_bytes("éé".encode("utf-8"), _config(character_limit=1))


def test_m06a_ht_043_encoding_is_explicit() -> None:
    root = _fixtures()
    assert parse_bytes((root / "utf8_bom.txt").read_bytes())["encoding"] == "utf-8"
    assert parse_bytes((root / "utf16_le.txt").read_bytes())["encoding"] == "utf-16-le"
    assert parse_bytes((root / "utf16_be.txt").read_bytes())["encoding"] == "utf-16-be"
    with pytest.raises(EncodingFailure):
        parse_bytes((root / "invalid_utf8.bin").read_bytes())
    with pytest.raises(EncodingFailure, match="explicit BOM"):
        parse_bytes((root / "utf16_without_bom.bin").read_bytes())
    with pytest.raises(MalformedInput, match="NUL"):
        parse_bytes((root / "embedded_nul.bin").read_bytes())
    with pytest.raises(EncodingFailure, match="replacement-character"):
        parse_bytes("already replaced \ufffd".encode("utf-8"))


def test_plain_text_line_endings_and_blank_regions_are_explicit() -> None:
    crlf = parse_bytes((_fixtures() / "crlf.txt").read_bytes())
    assert crlf["line_ending_profile"] == "CRLF"
    assert "line_ending_normalized" in crlf["warnings"]
    separated = parse_bytes((_fixtures() / "repeated_blank.txt").read_bytes())
    assert len(separated["elements"]) == 2
    assert len(separated["regions"]) == 1
    assert separated["regions"][0]["kind"] == "blank_separator"


def test_hashed_boundary_recipes_generate_the_admitted_corpus_edges() -> None:
    recipes = json.loads(
        (_fixtures() / "boundary-recipes.json").read_text(encoding="utf-8")
    )
    assert recipes["schema_version"] == "m06a.parser-fixture-recipes.v1"
    boundaries = {item["name"]: item for item in recipes["generated_boundaries"]}
    maximum = boundaries["maximum-admitted-line"]
    maximum_result = parse_bytes(b"x" * int(maximum["byte_length"]))
    assert maximum_result["coverage"]["complete"] is True
    assert len(maximum_result["elements"]) == 1

    exact = boundaries["input-exact-isolated-limit"]
    exact_result = parse_bytes(
        b"x" * int(exact["byte_length"]),
        _config(**exact["config_override"]),
    )
    assert exact_result["coverage"]["complete"] is True

    over_input = boundaries["input-one-byte-over-isolated-limit"]
    with pytest.raises(LimitExceeded, match="size limit"):
        parse_bytes(
            b"x" * int(over_input["byte_length"]),
            _config(**over_input["config_override"]),
        )

    over_line = boundaries["line-one-byte-over-isolated-limit"]
    with pytest.raises(LimitExceeded, match="logical line"):
        parse_bytes(
            b"x" * int(over_line["byte_length"]),
            _config(**over_line["config_override"]),
        )

    double_names = {item["name"] for item in recipes["test_doubles"]}
    assert double_names == {
        "socket-egress",
        "dns-http-egress",
        "subprocess-shell-filesystem-escape",
        "incomplete-coverage",
        "nondeterministic-output",
    }
