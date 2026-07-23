from __future__ import annotations

import copy
import hashlib
import subprocess
import zipfile
from pathlib import Path

import pytest

import discrepancy_desk.parsers.vtt_v1 as vtt_parser_module

from discrepancy_desk.parser_contract import (
    EncodingFailure,
    LimitExceeded,
    MalformedInput,
    PartialOutputFailure,
    canonical_json,
)
from discrepancy_desk.parsers.vtt_v1 import parse_bytes
from discrepancy_desk.vtt_contract import (
    INITIAL_VTT_CONFIG,
    VTT_CONFIG_SHA256,
    VTT_DEPENDENCY_LOCK_SHA256,
    VTT_IMPLEMENTATION_SHA256,
    VTT_RESOURCE_MANIFEST_SHA256,
    VTT_SCHEMA_SHA256,
    validate_vtt_candidate,
)
from discrepancy_desk.vtt_service import (
    assemble_under_test_vtt_package,
    list_vtt_status,
    load_vtt_resources,
    run_under_test_vtt_worker,
)

BASELINE_COMMIT = "6a8082253a52a601291efaf3ed85ee411b04be20"
FROZEN_PATHS = (
    "pyproject.toml",
    "uv.lock",
    "parser_resources/manifest.sha256",
    "parser_resources/configs/m06a.text.v1.json",
    "parser_resources/schemas/m06a.normalized-package.v1.json",
    "parser_resources/m06a.srt.v1/config.json",
    "parser_resources/m06a.srt.v1/schema.json",
    "parser_resources/m06a.srt.v1/manifest.sha256",
    "src/discrepancy_desk/parser_contract.py",
    "src/discrepancy_desk/parser_worker.py",
    "src/discrepancy_desk/parsers/plain_text_v1.py",
    "src/discrepancy_desk/parsers/srt_v1.py",
    "src/discrepancy_desk/srt_contract.py",
    "src/discrepancy_desk/srt_service.py",
    "src/discrepancy_desk/srt_worker.py",
)


def _fixture(name: str) -> bytes:
    with zipfile.ZipFile("tests/fixtures/m06a/parsers/vtt/corpus.zip") as archive:
        return archive.read(name)


def test_m06a_vtt_001_closed_text_and_srt_tuple_inputs_are_byte_identical() -> None:
    for path in FROZEN_PATHS:
        baseline = subprocess.run(
            ["git", "show", f"{BASELINE_COMMIT}:{path}"],
            capture_output=True,
            check=True,
        ).stdout
        assert Path(path).read_bytes() == baseline, path


def test_m06a_vtt_002_scoped_manifest_is_complete_and_exact() -> None:
    resources = load_vtt_resources()
    assert resources.root.name == "m06a.vtt.v1"
    assert resources.parser_tuple().parser_id == "m06a.vtt.v1"
    assert hashlib.sha256((resources.root / "config.json").read_bytes()).hexdigest() == resources.config_sha256
    assert hashlib.sha256((resources.root / "schema.json").read_bytes()).hexdigest() == resources.schema_sha256
    assert hashlib.sha256(Path("src/discrepancy_desk/parsers/vtt_v1.py").read_bytes()).hexdigest() == resources.implementation_sha256
    fixture_root = Path("tests/fixtures/m06a/parsers/vtt")
    digest, filename = (fixture_root / "manifest.sha256").read_text(encoding="utf-8").strip().split("  ")
    assert filename == "corpus.zip"
    assert hashlib.sha256((fixture_root / filename).read_bytes()).hexdigest() == digest
    with zipfile.ZipFile(fixture_root / filename) as archive:
        assert set(archive.namelist()) >= {
            "valid-basic.vtt", "header-only.vtt", "header-only-crlf.vtt",
            "header-only-cr.vtt", "multiline-mixed.vtt", "notes-all-positions.vtt",
            "active-looking-payload.vtt", "notes-settings.vtt", "style.vtt",
            "region.vtt", "utf16-le.vtt", "invalid-utf8.vtt",
            "nonascii-arabic-indic-timestamp.vtt",
            "nonascii-extended-arabic-timestamp.vtt",
            "nonascii-fullwidth-timestamp.vtt",
            "nonascii-devanagari-timestamp.vtt",
            "nonascii-arabic-line.vtt", "nonascii-fullwidth-size.vtt",
            "nonascii-devanagari-position.vtt", "boundary-recipes.json",
        }
        assert all(".." not in Path(name).parts and not Path(name).is_absolute() for name in archive.namelist())


def test_m06a_vtt_004_fresh_v0004_vault_installs_under_test_only(m06a_phase3a_vault) -> None:
    _, opened = m06a_phase3a_vault
    vault_id = opened.identity.vault_account_id
    status = list_vtt_status(opened.connection, vault_account_id=vault_id)
    assert status["state"] == "under_test"
    assert status["canonical_available"] is False
    assert status["admission_ready"] is False
    assert opened.connection.execute(
        """SELECT count(*) FROM parser_admission_versions a
        JOIN parser_definitions d ON d.vault_account_id=a.vault_account_id AND d.id=a.parser_definition_id
        WHERE d.format_id='text/vtt' AND a.state='owner_admitted'"""
    ).fetchone()[0] == 0


def test_m06a_vtt_005_no_admission_or_canonical_surface() -> None:
    combined = "\n".join(
        Path(name).read_text(encoding="utf-8")
        for name in (
            "src/discrepancy_desk/web.py", "src/discrepancy_desk/vtt_service.py",
            "src/discrepancy_desk/vtt_worker.py", "desktop/src/App.tsx",
        )
    ).lower()
    for forbidden in (
        "/parsers/m06a.vtt.v1/admit", "/parse-vtt", "admit vtt", "parse as vtt",
        "canonical_parse_vtt", "parse-all", "admit-all",
    ):
        assert forbidden not in combined


def test_m06a_vtt_006_signature_header_and_blank_separation() -> None:
    data = _fixture("header-text-crlf.vtt")
    candidate = parse_bytes(data, INITIAL_VTT_CONFIG)
    assert candidate["elements"][0]["cue_payload_raw"] == "Header text\r\n"
    assert [row["kind"] for row in candidate["regions"]][:2] == ["file_header", "blank_separator"]
    assert "line_ending_normalized" in candidate["warnings"]
    validate_vtt_candidate(candidate, input_bytes=data)


@pytest.mark.parametrize(
    ("name", "profile"),
    (("header-only.vtt", "LF"), ("header-only-crlf.vtt", "CRLF"), ("header-only-cr.vtt", "CR")),
)
def test_m06a_vtt_007_header_only_is_valid_with_complete_coverage(
    name: str, profile: str
) -> None:
    data = _fixture(name)
    candidate = parse_bytes(data, INITIAL_VTT_CONFIG)
    assert candidate["elements"] == []
    assert candidate["coverage"]["complete"] is True
    assert candidate["coverage"]["input_byte_count"] == len(data)
    assert candidate["line_ending_profile"] == profile
    validate_vtt_candidate(candidate, input_bytes=data)


def test_m06a_vtt_008_encoding_contract() -> None:
    bom = _fixture("utf8-bom.vtt")
    candidate = parse_bytes(bom, INITIAL_VTT_CONFIG)
    assert "encoding_bom_removed" in candidate["warnings"]
    validate_vtt_candidate(candidate, input_bytes=bom)
    for name, error in (
        ("utf16-le.vtt", EncodingFailure),
        ("invalid-utf8.vtt", EncodingFailure),
        ("binary-nul.vtt", MalformedInput),
    ):
        with pytest.raises(error):
            parse_bytes(_fixture(name), INITIAL_VTT_CONFIG)
    with pytest.raises(EncodingFailure):
        parse_bytes(b"WEBVTT\n\n00:00.000 --> 00:01.000\n\xef\xbf\xbd\n", INITIAL_VTT_CONFIG)


def test_m06a_vtt_009_short_and_hours_timestamps_parse_exactly() -> None:
    data = (
        b"WEBVTT\n\n00:01.250 --> 00:02.500\nShort\n\n"
        b"23:59:59.000 --> 24:00:00.000\nBoundary\n"
    )
    candidate = parse_bytes(data, INITIAL_VTT_CONFIG)
    assert [(row["start_milliseconds"], row["end_milliseconds"]) for row in candidate["elements"]] == [
        (1250, 2500), (86_399_000, 86_400_000)
    ]


def test_m06a_vtt_010_duration_and_nondecreasing_start_order() -> None:
    equal = b"WEBVTT\n\n00:00.000 --> 00:02.000\nOne\n\n00:00.000 --> 00:01.000\nTwo\n"
    assert len(parse_bytes(equal, INITIAL_VTT_CONFIG)["elements"]) == 2
    for data in (
        _fixture("out-of-order.vtt"),
        b"WEBVTT\n\n00:01.000 --> 00:01.000\nZero\n",
        b"WEBVTT\n\n00:02.000 --> 00:01.000\nNegative\n",
    ):
        with pytest.raises(MalformedInput):
            parse_bytes(data, INITIAL_VTT_CONFIG)


def test_m06a_vtt_011_overlap_warning_is_exact() -> None:
    candidate = parse_bytes(_fixture("overlap.vtt"), INITIAL_VTT_CONFIG)
    assert candidate["warnings"] == ["overlapping_cues"]


def test_m06a_vtt_012_identifiers_are_optional_bounded_and_unique() -> None:
    candidate = parse_bytes(_fixture("valid-basic.vtt"), INITIAL_VTT_CONFIG)
    assert [row["cue_identifier"] for row in candidate["elements"]] == ["cue-1", None]
    with pytest.raises(MalformedInput):
        parse_bytes(_fixture("duplicate-id.vtt"), INITIAL_VTT_CONFIG)
    config = dict(INITIAL_VTT_CONFIG)
    config["maximum_cue_identifier_bytes"] = 2
    with pytest.raises(LimitExceeded):
        parse_bytes(_fixture("valid-basic.vtt"), config)


def test_m06a_vtt_013_recognized_settings_use_closed_grammar() -> None:
    data = b"WEBVTT\n\n00:00.000 --> 00:01.000 vertical:lr line:-2,end position:25%,line-left size:100% align:right\nSettings\n"
    settings = parse_bytes(data, INITIAL_VTT_CONFIG)["elements"][0]["settings"]
    assert [row["name"] for row in settings] == ["vertical", "line", "position", "size", "align"]
    assert all(row["recognized"] is True for row in settings)


def test_m06a_vtt_014_malformed_duplicate_region_and_excessive_settings_fail() -> None:
    values = (
        b"vertical:up", b"line:+1", b"position:101%", b"size:101%", b"align:middle",
        b"align:start align:end", b"region:r1", b"broken",
    )
    for value in values:
        with pytest.raises(MalformedInput):
            parse_bytes(b"WEBVTT\n\n00:00.000 --> 00:01.000 "+value+b"\nBad\n", INITIAL_VTT_CONFIG)
    config = dict(INITIAL_VTT_CONFIG)
    config["maximum_settings_per_cue"] = 1
    with pytest.raises(LimitExceeded):
        parse_bytes(b"WEBVTT\n\n00:00.000 --> 00:01.000 align:start size:50%\nBad\n", config)


def test_m06a_vtt_015_unknown_setting_is_preserved_inert() -> None:
    candidate = parse_bytes(_fixture("notes-settings.vtt"), INITIAL_VTT_CONFIG)
    future = [row for row in candidate["elements"][0]["settings"] if row["name"] == "future"][0]
    assert future == {"name": "future", "ordinal": 5, "raw_text": "future:value", "recognized": False, "value": "value"}
    assert "unsupported_cue_setting_preserved" in candidate["warnings"]


def test_m06a_vtt_016_note_blocks_are_inert_regions() -> None:
    data = _fixture("notes-all-positions.vtt")
    candidate = parse_bytes(data, INITIAL_VTT_CONFIG)
    notes = [row for row in candidate["regions"] if row["kind"] == "note_block"]
    assert len(notes) == 3
    assert [row["raw_text"].splitlines()[0] for row in notes] == [
        "NOTE before", "NOTE between", "NOTE after"
    ]
    assert [row["normalized_text"].strip() for row in candidate["elements"]] == ["One", "Two"]
    assert all("body" not in row["normalized_text"] for row in candidate["elements"])
    validate_vtt_candidate(candidate, input_bytes=data)


def test_m06a_vtt_017_style_region_and_timeline_mapping_fail() -> None:
    for name in ("style.vtt", "region.vtt", "x-timestamp-map.vtt"):
        with pytest.raises(MalformedInput):
            parse_bytes(_fixture(name), INITIAL_VTT_CONFIG)
    with pytest.raises(MalformedInput):
        parse_bytes(b"WEBVTT\n\n00:00.000 --> 00:01.000 region:r1\nNo\n", INITIAL_VTT_CONFIG)


def test_m06a_vtt_018_payload_markup_is_preserved_inert() -> None:
    for name in ("notes-settings.vtt", "active-looking-payload.vtt"):
        data = _fixture(name)
        candidate = parse_bytes(data, INITIAL_VTT_CONFIG)
        payload = candidate["elements"][0]["cue_payload_raw"]
        assert candidate["elements"][0]["normalized_text"] == payload.replace("\r\n", "\n").replace("\r", "\n")
        assert "cue_markup_preserved_inert" in candidate["warnings"]
        validate_vtt_candidate(candidate, input_bytes=data)
    assert b"https://example.invalid" in _fixture("active-looking-payload.vtt")


@pytest.mark.parametrize(
    "data",
    [
        _fixture("malformed-signature.vtt"), _fixture("missing-separator.vtt"),
        _fixture("empty-payload.vtt"), _fixture("payload-arrow.vtt"),
        b"WEBVTT\n\n00:00.000 -> 00:01.000\nBad\n",
        b"WEBVTT\n\n00:60.000 --> 01:00.000\nBad\n",
    ],
)
def test_m06a_vtt_019_malformed_structure_fails(data: bytes) -> None:
    with pytest.raises((MalformedInput, LimitExceeded)):
        parse_bytes(data, INITIAL_VTT_CONFIG)


def test_m06a_vtt_020_all_limits_fail_closed() -> None:
    valid = _fixture("notes-settings.vtt")
    cases = (
        {"input_size_limit_bytes": len(valid)-1}, {"line_limit": 2},
        {"cue_limit": 0}, {"element_limit": 0}, {"region_limit": 1},
        {"maximum_cue_bytes": 10}, {"maximum_note_bytes": 10},
        {"maximum_header_bytes": 3}, {"maximum_setting_token_bytes": 3},
    )
    for override in cases:
        config = dict(INITIAL_VTT_CONFIG)
        config.update(override)
        with pytest.raises(LimitExceeded):
            parse_bytes(valid, config)


def test_m06a_vtt_021_coverage_reconciliation_detects_tamper() -> None:
    data = _fixture("valid-basic.vtt")
    candidate = parse_bytes(data, INITIAL_VTT_CONFIG)
    tampered = copy.deepcopy(candidate)
    tampered["elements"][0]["source_locator"]["source_byte_end"] -= 1
    with pytest.raises(PartialOutputFailure):
        validate_vtt_candidate(tampered, input_bytes=data)
    tampered = copy.deepcopy(candidate)
    tampered["elements"][0]["cue_payload_source_locator"]["source_character_start"] += 1
    with pytest.raises(PartialOutputFailure):
        validate_vtt_candidate(tampered, input_bytes=data)


def test_m06a_vtt_022_source_worker_and_package_are_deterministic() -> None:
    data = _fixture("valid-basic.vtt")
    first = run_under_test_vtt_worker(data)
    second = run_under_test_vtt_worker(data)
    assert first.exit_code == second.exit_code == 0
    assert first.candidate_bytes == second.candidate_bytes
    kwargs = {
        "vault_account_id": "synthetic-vtt-vault",
        "source_artifact_sha256": hashlib.sha256(data).hexdigest(),
        "parser_admission_id": "synthetic-vtt-under-test",
    }
    assert assemble_under_test_vtt_package(data, **kwargs)[1] == assemble_under_test_vtt_package(data, **kwargs)[1]


def test_m06a_vtt_025_receipt_data_is_not_in_package() -> None:
    data = _fixture("valid-basic.vtt")
    package, rendered, worker = assemble_under_test_vtt_package(
        data,
        vault_account_id="synthetic-vtt-vault",
        source_artifact_sha256=hashlib.sha256(data).hexdigest(),
        parser_admission_id="synthetic-vtt-under-test",
    )
    assert canonical_json(package) == rendered
    assert worker.receipt_bytes not in rendered
    for forbidden in ("controls", "error_stage", "state", "terminal_outcome"):
        assert forbidden not in package


def test_m06a_vtt_026_under_test_creates_no_vault_output_authority(m06a_phase3a_vault) -> None:
    _, opened = m06a_phase3a_vault
    vault_id = opened.identity.vault_account_id
    admission_id = opened.connection.execute(
        """SELECT a.id FROM parser_admission_versions a
        JOIN parser_definitions d ON d.vault_account_id=a.vault_account_id AND d.id=a.parser_definition_id
        WHERE d.format_id='text/vtt' AND a.state='under_test'"""
    ).fetchone()[0]
    data = _fixture("valid-basic.vtt")
    assemble_under_test_vtt_package(
        data,
        vault_account_id=vault_id,
        source_artifact_sha256=hashlib.sha256(data).hexdigest(),
        parser_admission_id=str(admission_id),
    )
    for table in ("parser_executions", "normalized_packages", "document_versions", "elements", "regions"):
        assert opened.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_m06a_vtt_c1_001_corrected_resource_constants_match_live_bytes() -> None:
    resources = load_vtt_resources()
    assert resources.manifest_sha256 == VTT_RESOURCE_MANIFEST_SHA256
    assert resources.config_sha256 == VTT_CONFIG_SHA256
    assert resources.schema_sha256 == VTT_SCHEMA_SHA256
    assert resources.implementation_sha256 == VTT_IMPLEMENTATION_SHA256
    assert resources.dependency_lock_sha256 == VTT_DEPENDENCY_LOCK_SHA256
    assert hashlib.sha256(Path("src/discrepancy_desk/parsers/vtt_v1.py").read_bytes()).hexdigest() == VTT_IMPLEMENTATION_SHA256
    assert hashlib.sha256((resources.root / "manifest.sha256").read_bytes()).hexdigest() == VTT_RESOURCE_MANIFEST_SHA256


@pytest.mark.parametrize(
    "name",
    (
        "nonascii-arabic-indic-timestamp.vtt",
        "nonascii-extended-arabic-timestamp.vtt",
        "nonascii-fullwidth-timestamp.vtt",
        "nonascii-devanagari-timestamp.vtt",
        "nonascii-arabic-line.vtt",
        "nonascii-fullwidth-size.vtt",
        "nonascii-devanagari-position.vtt",
    ),
)
def test_m06a_vtt_c1_002_non_ascii_numeric_grammar_is_rejected(name: str) -> None:
    data = _fixture(name)
    with pytest.raises(MalformedInput):
        parse_bytes(data, INITIAL_VTT_CONFIG)
    worker = run_under_test_vtt_worker(data)
    assert worker.exit_code != 0
    assert worker.candidate is None
    assert worker.receipt["terminal_outcome"] == "malformed_input"


def _validate_with_parser_repeating(
    monkeypatch: pytest.MonkeyPatch, candidate: dict[str, object], data: bytes
) -> None:
    monkeypatch.setattr(vtt_parser_module, "parse_bytes", lambda *_args, **_kwargs: candidate)
    validate_vtt_candidate(candidate, input_bytes=data)


def test_m06a_vtt_c1_003_independent_line_reconciliation_rejects_parser_repetition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _fixture("multiline-mixed.vtt")
    base = parse_bytes(data, INITIAL_VTT_CONFIG)
    cases: list[dict[str, object]] = []
    for locator_path in (
        ("elements", 0, "source_locator"),
        ("elements", 0, "timing_line_source_locator"),
        ("elements", 0, "cue_payload_source_locator"),
        ("regions", 0, "source_locator"),
    ):
        candidate = copy.deepcopy(base)
        locator = candidate[locator_path[0]][locator_path[1]][locator_path[2]]
        locator["source_line_start"] = 999
        locator["source_line_end"] = 999
        cases.append(candidate)
    for candidate in cases:
        with pytest.raises(PartialOutputFailure):
            _validate_with_parser_repeating(monkeypatch, candidate, data)


def test_m06a_vtt_c1_004_independent_counts_and_warnings_reject_parser_repetition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _fixture("valid-basic.vtt")
    base = parse_bytes(data, INITIAL_VTT_CONFIG)
    mutations = []
    candidate = copy.deepcopy(base)
    candidate["coverage"]["source_line_count"] = 999
    mutations.append(candidate)
    candidate = copy.deepcopy(base)
    candidate["coverage"]["decoded_character_count"] = 999
    mutations.append(candidate)
    candidate = copy.deepcopy(base)
    candidate["line_ending_profile"] = "CR"
    mutations.append(candidate)
    candidate = copy.deepcopy(base)
    candidate["warnings"] = ["overlapping_cues"]
    for element in candidate["elements"]:
        element["warnings"] = ["overlapping_cues"]
    mutations.append(candidate)
    for candidate in mutations:
        with pytest.raises(PartialOutputFailure):
            _validate_with_parser_repeating(monkeypatch, candidate, data)


def test_m06a_vtt_c1_007_expanded_fixture_corpus_and_direct_mappings() -> None:
    fixture_root = Path("tests/fixtures/m06a/parsers/vtt")
    digest, filename = (fixture_root / "manifest.sha256").read_text(encoding="utf-8").strip().split("  ")
    archive_path = fixture_root / filename
    assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == digest
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        required = {
            "header-only.vtt", "header-only-crlf.vtt", "header-only-cr.vtt",
            "multiline-mixed.vtt", "notes-all-positions.vtt",
            "active-looking-payload.vtt", "nonascii-arabic-indic-timestamp.vtt",
            "nonascii-extended-arabic-timestamp.vtt", "nonascii-fullwidth-timestamp.vtt",
            "nonascii-devanagari-timestamp.vtt", "nonascii-arabic-line.vtt",
            "nonascii-fullwidth-size.vtt", "nonascii-devanagari-position.vtt",
        }
        assert required <= names
    mixed = parse_bytes(_fixture("multiline-mixed.vtt"), INITIAL_VTT_CONFIG)
    assert mixed["line_ending_profile"] == "mixed:CRLF,CR,LF"
    assert mixed["elements"][0]["normalized_text"] == "Line one\nLine two\n"
    validate_vtt_candidate(mixed, input_bytes=_fixture("multiline-mixed.vtt"))
