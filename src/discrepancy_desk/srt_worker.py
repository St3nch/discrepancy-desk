from __future__ import annotations

import json
import os
import struct
import sys
from pathlib import Path

from .parser_contract import ParserContractError, canonical_json, require_sha256, sha256_bytes
from .parser_worker import install_security_controls
from .srt_contract import (
    SRT_IMPLEMENTATION_SHA256,
    SRT_PARSER_ID,
    SRT_SECURITY_PROFILE_ID,
    SRT_WORKER_PROTOCOL_VERSION,
    validate_srt_candidate,
)

MAX_REQUEST_BYTES = 64 * 1024
INPUT_NAME = "verified-input.bin"
OUTPUT_NAME = "candidate-package.json"
RECEIPT_NAME = "worker-receipt.json"


def _resource_root() -> Path:
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "parser_resources" / SRT_PARSER_ID)
    candidates.extend(
        [
            Path(__file__).resolve().parents[2] / "parser_resources" / SRT_PARSER_ID,
            Path(sys.executable).resolve().parent / "parser_resources" / SRT_PARSER_ID,
        ]
    )
    for candidate in candidates:
        if (candidate / "manifest.sha256").is_file():
            return candidate.resolve()
    raise FileNotFoundError("packaged SRT parser resources are unavailable")


def _read_request() -> dict[str, object]:
    header = sys.stdin.buffer.read(8)
    if len(header) != 8:
        raise ValueError("SRT worker request length prefix is missing")
    length = struct.unpack(">Q", header)[0]
    if length <= 0 or length > MAX_REQUEST_BYTES:
        raise ValueError("SRT worker request length is invalid")
    payload = sys.stdin.buffer.read(length)
    if len(payload) != length or sys.stdin.buffer.read(1):
        raise ValueError("SRT worker request framing is invalid")
    parsed = json.loads(payload.decode("utf-8"))
    if canonical_json(parsed) != payload or not isinstance(parsed, dict):
        raise ValueError("SRT worker request is not canonical JSON")
    required = {
        "protocol_version",
        "parser_id",
        "implementation_sha256",
        "config_sha256",
        "security_profile_id",
        "verified_input_relative_name",
        "verified_input_sha256",
        "verified_input_size",
        "output_filename",
    }
    if set(parsed) != required:
        raise ValueError("SRT worker request fields diverge from the fixed protocol")
    return parsed


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_exact(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _write_receipt(operation_root: Path, payload: dict[str, object]) -> None:
    receipt = operation_root / RECEIPT_NAME
    if receipt.exists():
        return
    _write_exact(receipt, canonical_json(payload))


def _validate_request(request: dict[str, object], *, operation_root: Path, resource_root: Path) -> Path:
    if request["protocol_version"] != SRT_WORKER_PROTOCOL_VERSION:
        raise ValueError("SRT worker protocol version mismatch")
    if request["parser_id"] != SRT_PARSER_ID:
        raise ValueError("SRT worker parser identity mismatch")
    if require_sha256(str(request["implementation_sha256"])) != SRT_IMPLEMENTATION_SHA256:
        raise ValueError("SRT worker implementation hash mismatch")
    if request["security_profile_id"] != SRT_SECURITY_PROFILE_ID:
        raise ValueError("SRT worker security profile mismatch")
    if request["verified_input_relative_name"] != INPUT_NAME or request["output_filename"] != OUTPUT_NAME:
        raise ValueError("SRT worker filenames are not fixed")
    config_path = resource_root / "config.json"
    if require_sha256(str(request["config_sha256"])) != _sha256_file(config_path):
        raise ValueError("SRT worker configuration hash mismatch")
    input_path = operation_root / INPUT_NAME
    if not input_path.is_file() or input_path.is_symlink():
        raise ValueError("verified SRT worker input is unavailable")
    expected_size = request["verified_input_size"]
    if type(expected_size) is not int or expected_size < 0 or input_path.stat().st_size != expected_size:
        raise ValueError("verified SRT worker input size mismatch")
    if _sha256_file(input_path) != require_sha256(str(request["verified_input_sha256"])):
        raise ValueError("verified SRT worker input hash mismatch")
    return input_path


def main() -> int:
    operation_root = Path.cwd().resolve()
    resource_root = _resource_root()
    stage = "read_request"
    controls: tuple[str, ...] = ()
    try:
        request = _read_request()
        stage = "install_security_controls"
        controls = install_security_controls(operation_root=operation_root, resource_root=resource_root)
        stage = "validate_request"
        input_path = _validate_request(request, operation_root=operation_root, resource_root=resource_root)
        stage = "load_config"
        config = json.loads((resource_root / "config.json").read_text(encoding="utf-8"))
        stage = "import_parser"
        from .parsers.srt_v1 import parse_bytes

        stage = "read_verified_input"
        input_bytes = input_path.read_bytes()
        stage = "parse_input"
        candidate = parse_bytes(input_bytes, config)
        stage = "validate_candidate"
        candidate = validate_srt_candidate(candidate, input_bytes=input_bytes)
        rendered = canonical_json(candidate)
        stage = "write_candidate"
        _write_exact(operation_root / OUTPUT_NAME, rendered)
        stage = "write_success_receipt"
        _write_receipt(
            operation_root,
            {
                "candidate_package_sha256": sha256_bytes(rendered),
                "controls": list(controls),
                "parser_id": SRT_PARSER_ID,
                "protocol_version": SRT_WORKER_PROTOCOL_VERSION,
                "security_profile_id": SRT_SECURITY_PROFILE_ID,
                "state": "succeeded",
                "terminal_outcome": "success_with_warnings" if candidate["warnings"] else "success",
                "warnings": candidate["warnings"],
            },
        )
        return 0
    except ParserContractError as exc:
        _write_receipt(
            operation_root,
            {
                "candidate_package_sha256": None,
                "controls": list(controls),
                "error_code": exc.code,
                "error_stage": stage,
                "parser_id": SRT_PARSER_ID,
                "protocol_version": SRT_WORKER_PROTOCOL_VERSION,
                "security_profile_id": SRT_SECURITY_PROFILE_ID,
                "state": "failed",
                "terminal_outcome": exc.code,
                "warnings": [],
            },
        )
        return 20
    except Exception as exc:
        try:
            _write_receipt(
                operation_root,
                {
                    "candidate_package_sha256": None,
                    "controls": list(controls),
                    "error_code": type(exc).__name__,
                    "error_stage": stage,
                    "parser_id": SRT_PARSER_ID,
                    "protocol_version": SRT_WORKER_PROTOCOL_VERSION,
                    "security_profile_id": SRT_SECURITY_PROFILE_ID,
                    "state": "failed",
                    "terminal_outcome": "internal_error",
                    "warnings": [],
                },
            )
        except Exception:
            pass
        return 21


if __name__ == "__main__":
    raise SystemExit(main())
