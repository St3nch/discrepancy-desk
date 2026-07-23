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
from discrepancy_desk.vtt_contract import (
    VTT_CONFIG_SHA256,
    VTT_IMPLEMENTATION_SHA256,
    VTT_PARSER_ID,
    VTT_SECURITY_PROFILE_ID,
    VTT_WORKER_PROTOCOL_VERSION,
)
from discrepancy_desk.vtt_service import run_under_test_vtt_worker


def _fixture() -> bytes:
    with zipfile.ZipFile("tests/fixtures/m06a/parsers/vtt/corpus.zip") as archive:
        return archive.read("valid-basic.vtt")


def _build_sidecar(project_root: Path) -> Path:
    completed = subprocess.run(
        [sys.executable, "scripts/build_desktop_sidecar.py"], cwd=project_root,
        capture_output=True, text=True, check=False, timeout=300,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    executable = project_root / "desktop/src-tauri/binaries/discrepancy-desk-backend/discrepancy-desk-backend.exe"
    assert executable.is_file()
    return executable


@pytest.fixture(scope="module")
def packaged_vtt_sidecar() -> Path:
    project_root = Path(__file__).resolve().parents[1]
    executable = project_root / "desktop/src-tauri/binaries/discrepancy-desk-backend/discrepancy-desk-backend.exe"
    return executable if executable.is_file() else _build_sidecar(project_root)


def _copy_sidecar(executable: Path, target: Path) -> Path:
    shutil.copytree(executable.parent, target)
    return target / executable.name


def _run(
    executable: Path, operation_root: Path, *, config_sha256: str = VTT_CONFIG_SHA256
) -> tuple[int, dict[str, object], bytes | None]:
    data = _fixture()
    operation_root.mkdir(parents=True)
    (operation_root / "verified-input.bin").write_bytes(data)
    request = {
        "config_sha256": config_sha256,
        "implementation_sha256": VTT_IMPLEMENTATION_SHA256,
        "output_filename": "candidate-package.json",
        "parser_id": VTT_PARSER_ID,
        "protocol_version": VTT_WORKER_PROTOCOL_VERSION,
        "security_profile_id": VTT_SECURITY_PROFILE_ID,
        "verified_input_relative_name": "verified-input.bin",
        "verified_input_sha256": hashlib.sha256(data).hexdigest(),
        "verified_input_size": len(data),
    }
    payload = canonical_json(request)
    completed = subprocess.run(
        [str(executable), "--m06a-vtt-parser-worker"], cwd=operation_root,
        input=struct.pack(">Q", len(payload)) + payload, capture_output=True,
        check=False, timeout=60, env=sanitized_worker_environment(),
    )
    receipt = json.loads((operation_root / "worker-receipt.json").read_text(encoding="utf-8"))
    candidate_path = operation_root / "candidate-package.json"
    return completed.returncode, receipt, candidate_path.read_bytes() if candidate_path.is_file() else None


def _assert_mismatch(executable: Path, operation: Path, *, config_sha256: str = VTT_CONFIG_SHA256) -> None:
    code, receipt, candidate = _run(executable, operation, config_sha256=config_sha256)
    assert code != 0
    assert receipt["state"] == "failed"
    assert receipt["terminal_outcome"] == "packaging_mismatch"
    assert receipt["error_stage"] == "validate_packaged_resources"
    assert candidate is None


def test_m06a_vtt_003_packaged_worker_rejects_full_tuple_tamper(
    tmp_path: Path, packaged_vtt_sidecar: Path
) -> None:
    cases = ("schema", "config", "manifest", "lock", "implementation")
    for name in cases:
        executable = _copy_sidecar(packaged_vtt_sidecar, tmp_path / f"{name}-sidecar")
        internal = executable.parent / "_internal"
        config_hash = VTT_CONFIG_SHA256
        if name == "schema":
            target = internal / "parser_resources" / VTT_PARSER_ID / "schema.json"
            target.write_text('{"tampered":true}', encoding="utf-8")
        elif name == "config":
            target = internal / "parser_resources" / VTT_PARSER_ID / "config.json"
            payload = json.loads(target.read_text(encoding="utf-8"))
            payload["cue_limit"] += 1
            target.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True), encoding="utf-8")
            config_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        elif name == "manifest":
            target = internal / "parser_resources" / VTT_PARSER_ID / "manifest.sha256"
            target.write_bytes(target.read_bytes() + b"\nD045-tamper\n")
        elif name == "lock":
            target = internal / "uv.lock"
            target.write_bytes(target.read_bytes() + b"\nD045-tamper\n")
        else:
            target = internal / "discrepancy_desk" / "parsers" / "vtt_v1.py"
            target.write_bytes(target.read_bytes() + b"\n# D045 tamper\n")
        _assert_mismatch(executable, tmp_path / f"{name}-operation", config_sha256=config_hash)


def test_m06a_vtt_023_source_worker_denials_and_failure_receipt(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    operation = tmp_path / "security-operation"
    operation.mkdir()
    script = f"""
import sys
from pathlib import Path
sys.path.insert(0, {str(project_root / 'src')!r})
from discrepancy_desk.parser_worker import install_security_controls
from discrepancy_desk.parser_contract import SecurityBoundaryViolation
operation=Path({str(operation)!r})
resources=Path({str(project_root / 'parser_resources' / 'm06a.vtt.v1')!r})
install_security_controls(operation_root=operation, resource_root=resources)
try:
    __import__('socket').getaddrinfo('example.com', 443)
except SecurityBoundaryViolation:
    print('DENIED')
else:
    raise SystemExit('network was not denied')
"""
    completed = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "DENIED"
    malformed = run_under_test_vtt_worker(b"not webvtt")
    assert malformed.exit_code != 0
    assert malformed.candidate is None
    assert malformed.receipt["terminal_outcome"] == "malformed_input"
    assert set(malformed.receipt["controls"]) >= {
        "socket_denied", "dns_denied", "subprocess_denied", "filesystem_mutation_denied",
        "exec_denied", "bounded_filesystem", "audit_hook_installed", "self_tested_denials",
    }


def test_m06a_vtt_024_real_packaged_sidecar_uses_exact_resources(
    tmp_path: Path, packaged_vtt_sidecar: Path
) -> None:
    code, receipt, candidate = _run(packaged_vtt_sidecar, tmp_path / "valid-packaged")
    assert code == 0
    assert receipt["state"] == "succeeded"
    assert receipt["parser_id"] == VTT_PARSER_ID
    assert candidate is not None
    assert set(receipt["controls"]) >= {
        "socket_denied", "dns_denied", "subprocess_denied", "filesystem_mutation_denied",
        "exec_denied", "bounded_filesystem", "audit_hook_installed", "self_tested_denials",
    }


def test_m06a_vtt_028_inherited_and_no_later_capability_surface() -> None:
    root_manifest = Path("parser_resources/manifest.sha256").read_text(encoding="utf-8")
    assert "m06a.vtt.v1" not in root_manifest
    assert "plain_text_v1" in root_manifest
    combined = "\n".join(
        Path(name).read_text(encoding="utf-8").lower()
        for name in (
            "src/discrepancy_desk/vtt_contract.py", "src/discrepancy_desk/vtt_service.py",
            "src/discrepancy_desk/vtt_worker.py", "src/discrepancy_desk/parsers/vtt_v1.py",
            "src/discrepancy_desk/web.py", "desktop/src/App.tsx",
        )
    )
    for forbidden in (
        "m06a.json.v1", "m06a.markdown.v1", "qdrant_client", "/providers/",
        "provider_client", "parse-all", "admit-all", "canonical_parse_vtt",
        "/parsers/m06a.vtt.v1/admit", "/parse-vtt",
    ):
        assert forbidden not in combined
