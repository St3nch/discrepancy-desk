from __future__ import annotations

import copy
import hashlib
import subprocess
import zipfile
from pathlib import Path

import pytest

from discrepancy_desk.parser_contract import (
    EncodingFailure,
    LimitExceeded,
    MalformedInput,
    PartialOutputFailure,
    canonical_json,
)
from discrepancy_desk.parsers.srt_v1 import parse_bytes
from discrepancy_desk.srt_contract import INITIAL_SRT_CONFIG, validate_srt_candidate
from discrepancy_desk.srt_service import (
    assemble_under_test_srt_package,
    list_srt_status,
    load_srt_resources,
    run_under_test_srt_worker,
)

BASELINE_COMMIT = "7980b1e7ab3fff51a705d61a93ac9e26b4c26ca9"
FROZEN_D039_PATHS = (
    "parser_resources/manifest.sha256",
    "parser_resources/configs/m06a.text.v1.json",
    "parser_resources/schemas/m06a.normalized-package.v1.json",
    "src/discrepancy_desk/parsers/plain_text_v1.py",
    "src/discrepancy_desk/parser_contract.py",
    "src/discrepancy_desk/parser_worker.py",
    "uv.lock",
    "pyproject.toml",
)


def _fixture(name: str) -> bytes:
    corpus = Path("tests/fixtures/m06a/parsers/srt/corpus.zip")
    with zipfile.ZipFile(corpus) as archive:
        return archive.read(name)


def test_m06a_srt_001_d039_tuple_inputs_are_byte_identical() -> None:
    for path in FROZEN_D039_PATHS:
        baseline = subprocess.run(
            ["git", "show", f"{BASELINE_COMMIT}:{path}"],
            capture_output=True,
            check=True,
        ).stdout
        assert Path(path).read_bytes() == baseline, path


def test_m06a_srt_002_scoped_manifest_is_complete_and_exact() -> None:
    resources = load_srt_resources()
    assert resources.root.name == "m06a.srt.v1"
    assert resources.config_sha256 == hashlib.sha256((resources.root / "config.json").read_bytes()).hexdigest()
    assert resources.schema_sha256 == hashlib.sha256((resources.root / "schema.json").read_bytes()).hexdigest()
    assert resources.implementation_sha256 == hashlib.sha256(
        Path("src/discrepancy_desk/parsers/srt_v1.py").read_bytes()
    ).hexdigest()
    assert resources.parser_tuple().parser_id == "m06a.srt.v1"
    fixture_root = Path("tests/fixtures/m06a/parsers/srt")
    manifest_line = (fixture_root / "manifest.sha256").read_text(encoding="utf-8")
    expected_hash, fixture_name = manifest_line.split("  ", 1)
    assert fixture_name == "corpus.zip"
    assert hashlib.sha256((fixture_root / fixture_name).read_bytes()).hexdigest() == expected_hash
    with zipfile.ZipFile(fixture_root / fixture_name) as archive:
        assert set(archive.namelist()) >= {
            "valid-indexed.srt",
            "valid-no-index.srt",
            "multiline-crlf.srt",
            "malformed-arrow.srt",
            "binary-nul.srt",
            "utf16-le.srt",
            "utf16-be.srt",
            "boundary-recipes.json",
        }


def test_m06a_srt_003_fresh_v0004_vault_installs_under_test_only(m06a_phase3a_vault) -> None:
    _, opened = m06a_phase3a_vault
    vault_id = opened.identity.vault_account_id
    status = list_srt_status(opened.connection, vault_account_id=vault_id)
    assert status["state"] == "under_test"
    assert status["canonical_available"] is False
    assert status["admission_ready"] is False
    assert opened.connection.execute(
        """SELECT count(*) FROM parser_admission_versions a
        JOIN parser_definitions d ON d.vault_account_id=a.vault_account_id AND d.id=a.parser_definition_id
        WHERE d.format_id='application/x-subrip' AND a.state='owner_admitted'"""
    ).fetchone()[0] == 0


def test_m06a_srt_004_no_admission_or_canonical_surface() -> None:
    web = Path("src/discrepancy_desk/web.py").read_text(encoding="utf-8")
    app = Path("desktop/src/App.tsx").read_text(encoding="utf-8")
    combined = web + app
    assert "/parsers/m06a.srt.v1/admit" not in combined
    assert "/parse-srt" not in combined
    assert "Admit SRT" not in combined
    assert "Parse as SRT" not in combined


def test_m06a_srt_005_valid_indexed_single_line_cues() -> None:
    candidate = parse_bytes(_fixture("valid-indexed.srt"), INITIAL_SRT_CONFIG)
    assert [row["cue_index"] for row in candidate["elements"]] == [1, 2]
    assert candidate["elements"][0]["start_milliseconds"] == 1000
    assert candidate["elements"][1]["end_milliseconds"] == 4000
    validate_srt_candidate(candidate, input_bytes=_fixture("valid-indexed.srt"))


def test_m06a_srt_006_optional_index() -> None:
    candidate = parse_bytes(_fixture("valid-no-index.srt"), INITIAL_SRT_CONFIG)
    assert candidate["elements"][0]["cue_index"] is None
    validate_srt_candidate(candidate, input_bytes=_fixture("valid-no-index.srt"))


def test_m06a_srt_007_multiline_and_blank_locator_fidelity() -> None:
    data = _fixture("multiline-crlf.srt")
    candidate = parse_bytes(data, INITIAL_SRT_CONFIG)
    assert candidate["elements"][0]["normalized_text"] == "First line\nSecond line\n"
    assert [row["kind"] for row in candidate["regions"]] == ["blank_separator"]
    assert "line_ending_normalized" in candidate["warnings"]
    validate_srt_candidate(candidate, input_bytes=data)


def test_m06a_srt_008_nonsequential_indexes_warn() -> None:
    candidate = parse_bytes(_fixture("nonsequential.srt"), INITIAL_SRT_CONFIG)
    assert candidate["warnings"] == ["nonsequential_cue_index"]


def test_m06a_srt_009_overlap_warns() -> None:
    candidate = parse_bytes(_fixture("overlap.srt"), INITIAL_SRT_CONFIG)
    assert candidate["warnings"] == ["overlapping_cues"]


def test_m06a_srt_010_source_order_is_preserved() -> None:
    data = (
        b"2\n00:00:05,000 --> 00:00:06,000\nLater\n\n"
        b"1\n00:00:01,000 --> 00:00:02,000\nEarlier\n"
    )
    candidate = parse_bytes(data, INITIAL_SRT_CONFIG)
    assert [row["cue_text_raw"] for row in candidate["elements"]] == ["Later\n", "Earlier\n"]
    assert "nonsequential_cue_index" in candidate["warnings"]
    assert "overlapping_cues" in candidate["warnings"]


@pytest.mark.parametrize(
    "data",
    [
        _fixture("malformed-arrow.srt"),
        b"1\n00:00:01.000 --> 00:00:02,000\nBad\n",
        b"1\n00:00:01,000  --> 00:00:02,000\nBad\n",
    ],
)
def test_m06a_srt_011_malformed_timestamp_or_arrow_fails(data: bytes) -> None:
    with pytest.raises(MalformedInput):
        parse_bytes(data, INITIAL_SRT_CONFIG)


@pytest.mark.parametrize(
    "data, error",
    [
        (_fixture("negative-duration.srt"), MalformedInput),
        (b"1\n00:60:01,000 --> 00:00:02,000\nBad\n", MalformedInput),
        (b"1\n24:00:00,001 --> 24:00:00,001\nBad\n", LimitExceeded),
    ],
)
def test_m06a_srt_012_invalid_fields_duration_and_maximum_fail(data: bytes, error: type[Exception]) -> None:
    with pytest.raises(error):
        parse_bytes(data, INITIAL_SRT_CONFIG)


@pytest.mark.parametrize("name", ["missing-text.srt", "missing-separator.srt"])
def test_m06a_srt_013_missing_text_or_separator_fails(name: str) -> None:
    with pytest.raises(MalformedInput):
        parse_bytes(_fixture(name), INITIAL_SRT_CONFIG)


def test_m06a_srt_014_all_limits_fail_closed() -> None:
    valid = _fixture("valid-indexed.srt")
    cases = [
        {"input_size_limit_bytes": len(valid) - 1},
        {"cue_limit": 1},
        {"maximum_cue_bytes": 10},
        {"line_limit": 2},
    ]
    for override in cases:
        config = dict(INITIAL_SRT_CONFIG)
        config.update(override)
        with pytest.raises(LimitExceeded):
            parse_bytes(valid, config)


@pytest.mark.parametrize("name", ["utf8-bom.srt", "utf16-le.srt", "utf16-be.srt"])
def test_m06a_srt_015_admitted_encodings(name: str) -> None:
    data = _fixture(name)
    candidate = parse_bytes(data, INITIAL_SRT_CONFIG)
    assert "encoding_bom_removed" in candidate["warnings"]
    validate_srt_candidate(candidate, input_bytes=data)


@pytest.mark.parametrize("name,error", [("invalid-utf8.srt", EncodingFailure), ("binary-nul.srt", MalformedInput)])
def test_m06a_srt_015_invalid_encoding_and_nul_fail(name: str, error: type[Exception]) -> None:
    with pytest.raises(error):
        parse_bytes(_fixture(name), INITIAL_SRT_CONFIG)


def test_m06a_srt_016_independent_coverage_reconciliation() -> None:
    data = _fixture("valid-indexed.srt")
    candidate = parse_bytes(data, INITIAL_SRT_CONFIG)
    tampered = copy.deepcopy(candidate)
    tampered["elements"][0]["source_locator"]["source_byte_end"] -= 1
    with pytest.raises(PartialOutputFailure):
        validate_srt_candidate(tampered, input_bytes=data)
    tampered = copy.deepcopy(candidate)
    tampered["elements"][0]["cue_text_source_locator"]["source_character_start"] += 1
    with pytest.raises(PartialOutputFailure):
        validate_srt_candidate(tampered, input_bytes=data)


def test_m06a_srt_017_source_worker_is_deterministic() -> None:
    data = _fixture("valid-indexed.srt")
    first = run_under_test_srt_worker(data)
    second = run_under_test_srt_worker(data)
    assert first.exit_code == second.exit_code == 0
    assert first.candidate_bytes == second.candidate_bytes
    package_a = assemble_under_test_srt_package(
        data,
        vault_account_id="synthetic-srt-vault",
        source_artifact_sha256=hashlib.sha256(data).hexdigest(),
        parser_admission_id="synthetic-srt-under-test",
    )[1]
    package_b = assemble_under_test_srt_package(
        data,
        vault_account_id="synthetic-srt-vault",
        source_artifact_sha256=hashlib.sha256(data).hexdigest(),
        parser_admission_id="synthetic-srt-under-test",
    )[1]
    assert package_a == package_b


def test_m06a_srt_020_receipt_data_is_separate_from_package() -> None:
    data = _fixture("valid-indexed.srt")
    package, rendered, worker = assemble_under_test_srt_package(
        data,
        vault_account_id="synthetic-srt-vault",
        source_artifact_sha256=hashlib.sha256(data).hexdigest(),
        parser_admission_id="synthetic-srt-under-test",
    )
    assert canonical_json(package) == rendered
    assert worker.receipt_bytes not in rendered
    for forbidden in ("controls", "error_stage", "state", "terminal_outcome"):
        assert forbidden not in package


def test_m06a_srt_021_under_test_creates_no_vault_output_authority(m06a_phase3a_vault) -> None:
    _, opened = m06a_phase3a_vault
    vault_id = opened.identity.vault_account_id
    admission_id = opened.connection.execute(
        """SELECT a.id FROM parser_admission_versions a
        JOIN parser_definitions d ON d.vault_account_id=a.vault_account_id AND d.id=a.parser_definition_id
        WHERE d.format_id='application/x-subrip' AND a.state='under_test'"""
    ).fetchone()[0]
    data = _fixture("valid-indexed.srt")
    assemble_under_test_srt_package(
        data,
        vault_account_id=vault_id,
        source_artifact_sha256=hashlib.sha256(data).hexdigest(),
        parser_admission_id=str(admission_id),
    )
    for table in ("parser_executions", "normalized_packages", "document_versions", "elements", "regions"):
        assert opened.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
