from __future__ import annotations

import hashlib
import json
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from discrepancy_desk.parser_contract import canonical_json
from discrepancy_desk.parser_worker import sanitized_worker_environment
from discrepancy_desk.srt_contract import (
    SRT_CONFIG_SHA256,
    SRT_DEPENDENCY_LOCK_SHA256,
    SRT_IMPLEMENTATION_SHA256,
    SRT_PARSER_ID,
    SRT_RESOURCE_MANIFEST_SHA256,
    SRT_SCHEMA_SHA256,
    SRT_SECURITY_PROFILE_ID,
    SRT_WORKER_PROTOCOL_VERSION,
)
from discrepancy_desk.srt_service import load_srt_resources, run_under_test_srt_worker


def _fixture(name: str = "valid-indexed.srt") -> bytes:
    corpus = Path("tests/fixtures/m06a/parsers/srt/corpus.zip")
    with zipfile.ZipFile(corpus) as archive:
        return archive.read(name)


def _security_child(expression: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    project_root = Path(__file__).resolve().parents[1]
    operation = tmp_path / "operation"
    operation.mkdir(parents=True)
    script = f"""
import sys
from pathlib import Path
sys.path.insert(0, {str(project_root / 'src')!r})
from discrepancy_desk.parser_worker import install_security_controls
from discrepancy_desk.parser_contract import SecurityBoundaryViolation
operation=Path({str(operation)!r})
resources=Path({str(project_root / 'parser_resources' / 'm06a.srt.v1')!r})
outside=operation.parent / 'outside-security-probe.txt'
outside.write_text('synthetic', encoding='utf-8')
install_security_controls(operation_root=operation, resource_root=resources)
try:
    {expression}
except SecurityBoundaryViolation:
    print('DENIED')
else:
    raise SystemExit('operation was not denied')
"""
    return subprocess.run(
        [sys.executable, "-I", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )


def _build_packaged_sidecar(project_root: Path) -> Path:
    completed = subprocess.run(
        [sys.executable, "scripts/build_desktop_sidecar.py"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    executable = (
        project_root
        / "desktop"
        / "src-tauri"
        / "binaries"
        / "discrepancy-desk-backend"
        / "discrepancy-desk-backend.exe"
    )
    assert executable.is_file()
    return executable


def _run_packaged_srt_worker(
    executable: Path,
    operation_root: Path,
    input_bytes: bytes,
    *,
    config_sha256: str = SRT_CONFIG_SHA256,
    implementation_sha256: str = SRT_IMPLEMENTATION_SHA256,
) -> tuple[int, dict[str, object], bytes | None]:
    operation_root.mkdir(parents=True)
    input_path = operation_root / "verified-input.bin"
    input_path.write_bytes(input_bytes)
    request = {
        "config_sha256": config_sha256,
        "implementation_sha256": implementation_sha256,
        "output_filename": "candidate-package.json",
        "parser_id": SRT_PARSER_ID,
        "protocol_version": SRT_WORKER_PROTOCOL_VERSION,
        "security_profile_id": SRT_SECURITY_PROFILE_ID,
        "verified_input_relative_name": "verified-input.bin",
        "verified_input_sha256": hashlib.sha256(input_bytes).hexdigest(),
        "verified_input_size": len(input_bytes),
    }
    request_bytes = canonical_json(request)
    completed = subprocess.run(
        [str(executable), "--m06a-srt-parser-worker"],
        cwd=operation_root,
        input=struct.pack(">Q", len(request_bytes)) + request_bytes,
        capture_output=True,
        check=False,
        timeout=60,
        env=sanitized_worker_environment(),
    )
    receipt = json.loads(
        (operation_root / "worker-receipt.json").read_text(encoding="utf-8")
    )
    candidate_path = operation_root / "candidate-package.json"
    candidate = candidate_path.read_bytes() if candidate_path.is_file() else None
    return completed.returncode, receipt, candidate


def _copy_packaged_sidecar(executable: Path, target: Path) -> Path:
    shutil.copytree(executable.parent, target)
    return target / executable.name


@pytest.fixture(scope="module")
def packaged_srt_sidecar() -> Path:
    project_root = Path(__file__).resolve().parents[1]
    executable = (
        project_root
        / "desktop"
        / "src-tauri"
        / "binaries"
        / "discrepancy-desk-backend"
        / "discrepancy-desk-backend.exe"
    )
    return executable if executable.is_file() else _build_packaged_sidecar(project_root)


def _assert_packaging_mismatch(
    executable: Path,
    operation_root: Path,
    *,
    config_sha256: str = SRT_CONFIG_SHA256,
) -> None:
    code, receipt, candidate = _run_packaged_srt_worker(
        executable,
        operation_root,
        _fixture(),
        config_sha256=config_sha256,
    )
    assert code != 0
    assert receipt["state"] == "failed"
    assert receipt["terminal_outcome"] == "packaging_mismatch"
    assert receipt["error_stage"] == "validate_packaged_resources"
    assert candidate is None


def test_m06a_srt_018_source_worker_denials_and_failure_output(tmp_path: Path) -> None:
    attempts = (
        "__import__('socket').getaddrinfo('example.com', 443)",
        "__import__('subprocess').run(['cmd', '/c', 'echo', 'no'])",
        "open(str(operation.parent / 'escape.txt'), 'wb')",
        "__import__('os').open(operation.parent / 'low-level.txt', "
        "__import__('os').O_WRONLY | __import__('os').O_CREAT)",
        "__import__('os').remove(outside)",
        "__import__('os').execv(str(operation / 'missing.exe'), ['missing.exe'])",
    )
    for index, expression in enumerate(attempts):
        completed = _security_child(expression, tmp_path / f"denial-{index}")
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.strip() == "DENIED"
        assert not (tmp_path / f"denial-{index}" / "operation" / "candidate-package.json").exists()

    malformed = run_under_test_srt_worker(
        _fixture("malformed-arrow.srt")
    )
    assert malformed.exit_code != 0
    assert malformed.candidate is None
    assert malformed.candidate_bytes is None
    assert malformed.receipt["terminal_outcome"] == "malformed_input"
    assert set(malformed.receipt["controls"]) >= {
        "socket_denied",
        "dns_denied",
        "subprocess_denied",
        "filesystem_mutation_denied",
        "exec_denied",
        "bounded_filesystem",
        "audit_hook_installed",
        "self_tested_denials",
    }


def test_m06a_srt_019_real_packaged_sidecar_uses_exact_resources(
    tmp_path: Path, packaged_srt_sidecar: Path
) -> None:
    executable = packaged_srt_sidecar
    code, receipt, candidate = _run_packaged_srt_worker(
        executable, tmp_path / "packaged-srt-worker", _fixture()
    )
    assert code == 0
    assert receipt["state"] == "succeeded"
    assert receipt["parser_id"] == SRT_PARSER_ID
    assert receipt["security_profile_id"] == SRT_SECURITY_PROFILE_ID
    assert candidate
    assert set(receipt["controls"]) >= {
        "socket_denied",
        "dns_denied",
        "subprocess_denied",
        "filesystem_mutation_denied",
        "exec_denied",
        "bounded_filesystem",
        "audit_hook_installed",
        "self_tested_denials",
    }


def test_m06a_srt_023_plain_text_and_backup_regression_surface_is_unchanged() -> None:
    root_manifest = Path("parser_resources/manifest.sha256").read_text(encoding="utf-8")
    assert "m06a.srt.v1" not in root_manifest
    assert "plain_text_v1" in root_manifest
    source = Path("src/discrepancy_desk/vault_backup.py").read_text(encoding="utf-8")
    assert "normalized_packages" in source
    assert "package inventory" in source


def test_m06a_srt_024_no_later_capability_leakage() -> None:
    paths = (
        Path("src/discrepancy_desk/srt_contract.py"),
        Path("src/discrepancy_desk/srt_service.py"),
        Path("src/discrepancy_desk/srt_worker.py"),
        Path("src/discrepancy_desk/parsers/srt_v1.py"),
        Path("desktop/src/App.tsx"),
        Path("src/discrepancy_desk/web.py"),
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths).lower()
    for forbidden in (
        "m06a.vtt.v1",
        "m06a.json.v1",
        "m06a.markdown.v1",
        "qdrant_client",
        "/providers/",
        "provider_client",
        "parse-all",
        "admit-all",
        "autonomous posting",
    ):
        assert forbidden not in combined


def test_m06a_srt_c1_001_exact_resource_constants_match_live_bytes() -> None:
    resources = load_srt_resources()
    assert resources.manifest_sha256 == SRT_RESOURCE_MANIFEST_SHA256
    assert resources.config_sha256 == SRT_CONFIG_SHA256
    assert resources.schema_sha256 == SRT_SCHEMA_SHA256
    assert resources.implementation_sha256 == SRT_IMPLEMENTATION_SHA256
    assert resources.dependency_lock_sha256 == SRT_DEPENDENCY_LOCK_SHA256


def test_m06a_srt_c1_002_packaged_schema_tamper_fails(
    tmp_path: Path, packaged_srt_sidecar: Path
) -> None:
    executable = _copy_packaged_sidecar(
        packaged_srt_sidecar, tmp_path / "schema-tamper-sidecar"
    )
    schema = (
        executable.parent
        / "_internal"
        / "parser_resources"
        / SRT_PARSER_ID
        / "schema.json"
    )
    schema.write_text('{"tampered":true}\n', encoding="utf-8", newline="\n")
    _assert_packaging_mismatch(executable, tmp_path / "schema-tamper-operation")


def test_m06a_srt_c1_003_packaged_config_self_hash_tamper_fails(
    tmp_path: Path, packaged_srt_sidecar: Path
) -> None:
    executable = _copy_packaged_sidecar(
        packaged_srt_sidecar, tmp_path / "config-tamper-sidecar"
    )
    config = (
        executable.parent
        / "_internal"
        / "parser_resources"
        / SRT_PARSER_ID
        / "config.json"
    )
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["input_size_limit_bytes"] = int(payload["input_size_limit_bytes"]) + 1
    config.write_text(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
        newline="",
    )
    _assert_packaging_mismatch(
        executable,
        tmp_path / "config-tamper-operation",
        config_sha256=hashlib.sha256(config.read_bytes()).hexdigest(),
    )


@pytest.mark.parametrize("target_name", ["manifest", "dependency-lock"])
def test_m06a_srt_c1_004_packaged_manifest_and_lock_tamper_fail(
    tmp_path: Path, packaged_srt_sidecar: Path, target_name: str
) -> None:
    executable = _copy_packaged_sidecar(
        packaged_srt_sidecar, tmp_path / f"{target_name}-tamper-sidecar"
    )
    if target_name == "manifest":
        target = (
            executable.parent
            / "_internal"
            / "parser_resources"
            / SRT_PARSER_ID
            / "manifest.sha256"
        )
    else:
        target = executable.parent / "_internal" / "uv.lock"
    target.write_bytes(target.read_bytes() + b"\nD041-tamper\n")
    _assert_packaging_mismatch(
        executable, tmp_path / f"{target_name}-tamper-operation"
    )


def test_m06a_srt_c1_005_packaged_implementation_tamper_fails(
    tmp_path: Path, packaged_srt_sidecar: Path
) -> None:
    executable = _copy_packaged_sidecar(
        packaged_srt_sidecar, tmp_path / "implementation-tamper-sidecar"
    )
    implementation = (
        executable.parent
        / "_internal"
        / "discrepancy_desk"
        / "parsers"
        / "srt_v1.py"
    )
    implementation.write_bytes(implementation.read_bytes() + b"\n# D041 tamper\n")
    _assert_packaging_mismatch(
        executable, tmp_path / "implementation-tamper-operation"
    )


def test_m06a_srt_c1_006_valid_packaged_execution_remains_green(
    tmp_path: Path, packaged_srt_sidecar: Path
) -> None:
    code, receipt, candidate = _run_packaged_srt_worker(
        packaged_srt_sidecar, tmp_path / "valid-c1-operation", _fixture()
    )
    assert code == 0
    assert receipt["state"] == "succeeded"
    assert candidate is not None


def test_m06a_srt_c1_008_no_srt_mutation_or_canonical_authority() -> None:
    source = "\n".join(
        Path(name).read_text(encoding="utf-8")
        for name in (
            "src/discrepancy_desk/srt_contract.py",
            "src/discrepancy_desk/srt_service.py",
            "src/discrepancy_desk/srt_worker.py",
            "src/discrepancy_desk/web.py",
        )
    ).lower()
    for forbidden in (
        "/parsers/m06a.srt.v1/admit",
        "/parse-srt",
        "owner_admitted', ?, ?, ?, ?, ?, ?, ?,",
        "canonical_parse_srt",
        "parse-all",
        "admit-all",
    ):
        assert forbidden not in source
