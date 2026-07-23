from __future__ import annotations

import builtins
import ctypes
import json
import os
import socket
import struct
import subprocess
import sys
from pathlib import Path

from .parser_contract import (
    PARSER_ID,
    PARSER_IMPLEMENTATION_SHA256,
    SECURITY_PROFILE_ID,
    WORKER_PROTOCOL_VERSION,
    ParserContractError,
    SecurityBoundaryViolation,
    canonical_json,
    require_sha256,
    sha256_bytes,
    sha256_file,
    validate_candidate_core,
)

MAX_REQUEST_BYTES = 64 * 1024
INPUT_NAME = "verified-input.bin"
OUTPUT_NAME = "candidate-package.json"
RECEIPT_NAME = "worker-receipt.json"

_DENIED_ENV_PREFIXES = (
    "AWS_",
    "AZURE_",
    "GCP_",
    "GOOGLE_",
    "HTTP_",
    "HTTPS_",
    "NO_PROXY",
    "PIP_",
    "POETRY_",
    "UV_",
)
_DENIED_ENV_NAMES = {
    "ALL_PROXY",
    "CLOUDSDK_CONFIG",
    "GITHUB_TOKEN",
    "NPM_TOKEN",
    "OPENAI_API_KEY",
    "TWINE_PASSWORD",
}


def sanitized_worker_environment(environment: dict[str, str] | None = None) -> dict[str, str]:
    sanitized = dict(os.environ if environment is None else environment)
    for name in list(sanitized):
        upper = name.upper()
        if upper in _DENIED_ENV_NAMES or any(
            upper.startswith(prefix) for prefix in _DENIED_ENV_PREFIXES
        ):
            sanitized.pop(name, None)
    sanitized["TZ"] = "UTC"
    sanitized["LC_ALL"] = "C"
    sanitized["LANG"] = "C"
    sanitized["PYTHONHASHSEED"] = "0"
    return sanitized


def _deny(message: str):
    def denied(*args, **kwargs):
        raise SecurityBoundaryViolation(message)

    return denied


def _within(path: Path, roots: tuple[Path, ...]) -> bool:
    resolved = path.resolve(strict=False)
    return any(resolved == root or root in resolved.parents for root in roots)


def install_security_controls(*, operation_root: Path, resource_root: Path) -> tuple[str, ...]:
    operation = operation_root.resolve(strict=True)
    resource = resource_root.resolve(strict=True)
    package_root = Path(__file__).resolve().parent
    packaged_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    executable_root = Path(sys.executable).resolve().parent
    stdlib_roots = tuple(
        path.resolve(strict=False)
        for path in {
            Path(sys.base_prefix),
            Path(sys.prefix),
            package_root,
            packaged_root,
            executable_root,
            resource,
            operation,
        }
        if str(path)
    )

    sanitized = sanitized_worker_environment(dict(os.environ))
    os.environ.clear()
    os.environ.update(sanitized)

    original_socket_type = socket.socket

    class DeniedSocket(original_socket_type):
        def __new__(cls, *args, **kwargs):
            raise SecurityBoundaryViolation("socket creation is denied")

    socket.socket = DeniedSocket  # type: ignore[assignment]
    socket.create_connection = _deny("network connection is denied")  # type: ignore[assignment]
    socket.getaddrinfo = _deny("DNS resolution is denied")  # type: ignore[assignment]
    subprocess.Popen = _deny("subprocess creation is denied")  # type: ignore[assignment]
    subprocess.run = _deny("subprocess creation is denied")  # type: ignore[assignment]
    subprocess.call = _deny("subprocess creation is denied")  # type: ignore[assignment]
    subprocess.check_call = _deny("subprocess creation is denied")  # type: ignore[assignment]
    subprocess.check_output = _deny("subprocess creation is denied")  # type: ignore[assignment]
    os.system = _deny("shell execution is denied")  # type: ignore[assignment]
    ctypes.CDLL = _deny("dynamic-library loading is denied")  # type: ignore[assignment]
    ctypes.PyDLL = _deny("dynamic-library loading is denied")  # type: ignore[assignment]

    original_open = builtins.open

    def guarded_open(file, mode="r", *args, **kwargs):
        if isinstance(file, int):
            return original_open(file, mode, *args, **kwargs)
        path = Path(os.fspath(file))
        if not path.is_absolute():
            path = operation / path
        writing = any(flag in str(mode) for flag in ("w", "a", "x", "+"))
        allowed_roots = (operation,) if writing else stdlib_roots
        if not _within(path, allowed_roots):
            raise SecurityBoundaryViolation("filesystem access escaped the worker boundary")
        return original_open(path, mode, *args, **kwargs)

    builtins.open = guarded_open

    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
    denied_process_events = {
        "os.system",
        "os.posix_spawn",
        "os.spawn",
        "os.exec",
        "os.startfile",
        "os.startfile/2",
        "ctypes.dlopen",
    }
    mutation_events = {
        "os.remove",
        "os.rename",
        "os.replace",
        "os.rmdir",
        "os.mkdir",
        "os.chmod",
        "os.chown",
        "os.link",
        "os.symlink",
        "os.truncate",
        "os.utime",
    }

    def resolve_audit_path(target: object) -> Path | None:
        if not isinstance(target, (str, bytes, os.PathLike)):
            return None
        path = Path(os.fsdecode(target))
        return path if path.is_absolute() else operation / path

    def audit_hook(event: str, args: tuple[object, ...]) -> None:
        if (
            event.startswith("socket.")
            or event.startswith("subprocess.")
            or event.startswith("os.exec")
            or event.startswith("os.spawn")
            or event.startswith("os.startfile")
            or event in denied_process_events
        ):
            raise SecurityBoundaryViolation(f"audit event denied: {event}")
        if event == "open" and args:
            path = resolve_audit_path(args[0])
            if path is not None:
                mode = args[1] if len(args) > 1 else "r"
                flags = args[2] if len(args) > 2 and type(args[2]) is int else 0
                writing = (
                    any(flag in str(mode) for flag in ("w", "a", "x", "+"))
                    or bool(int(flags) & write_flags)
                )
                allowed_roots = (operation,) if writing else stdlib_roots
                if not _within(path, allowed_roots):
                    raise SecurityBoundaryViolation("audit hook denied filesystem escape")
        if event in mutation_events:
            paths = [path for path in (resolve_audit_path(value) for value in args) if path is not None]
            if not paths or any(not _within(path, (operation,)) for path in paths):
                raise SecurityBoundaryViolation(f"audit hook denied filesystem mutation: {event}")

    sys.addaudithook(audit_hook)

    def require_denied(label: str, action) -> None:
        try:
            action()
        except SecurityBoundaryViolation:
            return
        except Exception as exc:
            raise RuntimeError(f"security control self-test failed open: {label}") from exc
        raise RuntimeError(f"security control self-test was not denied: {label}")

    def low_level_open_probe() -> None:
        descriptor = os.open(resource / "manifest.sha256", os.O_WRONLY)
        os.close(descriptor)

    require_denied("low_level_write", low_level_open_probe)
    require_denied("filesystem_mutation", lambda: os.remove(resource / "missing-security-probe"))
    require_denied(
        "exec",
        lambda: os.execv(str(operation / "missing-security-probe.exe"), ["missing-security-probe"]),
    )
    if hasattr(os, "startfile"):
        require_denied(
            "startfile",
            lambda: os.startfile(str(operation / "missing-security-probe.exe")),
        )

    return (
        "credential_environment_cleared",
        "socket_denied",
        "dns_denied",
        "subprocess_denied",
        "shell_denied",
        "dynamic_library_denied",
        "exec_denied",
        "filesystem_mutation_denied",
        "bounded_filesystem",
        "audit_hook_installed",
        "self_tested_denials",
    )


def _resource_root() -> Path:
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "parser_resources")
    candidates.extend(
        [
            Path(__file__).resolve().parents[2] / "parser_resources",
            Path(sys.executable).resolve().parent / "parser_resources",
        ]
    )
    for candidate in candidates:
        if (candidate / "manifest.sha256").is_file():
            return candidate.resolve()
    raise FileNotFoundError("packaged parser resources are unavailable")


def _read_request() -> dict[str, object]:
    header = sys.stdin.buffer.read(8)
    if len(header) != 8:
        raise ValueError("worker request length prefix is missing")
    length = struct.unpack(">Q", header)[0]
    if length <= 0 or length > MAX_REQUEST_BYTES:
        raise ValueError("worker request length is invalid")
    payload = sys.stdin.buffer.read(length)
    if len(payload) != length or sys.stdin.buffer.read(1):
        raise ValueError("worker request framing is invalid")
    parsed = json.loads(payload.decode("utf-8"))
    if canonical_json(parsed) != payload or not isinstance(parsed, dict):
        raise ValueError("worker request is not canonical JSON")
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
        raise ValueError("worker request fields diverge from the fixed protocol")
    return parsed


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
    if request["protocol_version"] != WORKER_PROTOCOL_VERSION:
        raise ValueError("worker protocol version mismatch")
    if request["parser_id"] != PARSER_ID:
        raise ValueError("worker parser identity mismatch")
    if require_sha256(str(request["implementation_sha256"])) != PARSER_IMPLEMENTATION_SHA256:
        raise ValueError("worker implementation hash mismatch")
    if request["security_profile_id"] != SECURITY_PROFILE_ID:
        raise ValueError("worker security profile mismatch")
    if request["verified_input_relative_name"] != INPUT_NAME or request["output_filename"] != OUTPUT_NAME:
        raise ValueError("worker filenames are not fixed")
    config_path = resource_root / "configs" / "m06a.text.v1.json"
    if require_sha256(str(request["config_sha256"])) != sha256_file(config_path):
        raise ValueError("worker configuration hash mismatch")
    input_path = operation_root / INPUT_NAME
    if not input_path.is_file() or input_path.is_symlink():
        raise ValueError("verified worker input is unavailable")
    expected_size = request["verified_input_size"]
    if type(expected_size) is not int or expected_size < 0 or input_path.stat().st_size != expected_size:
        raise ValueError("verified worker input size mismatch")
    if sha256_file(input_path) != require_sha256(str(request["verified_input_sha256"])):
        raise ValueError("verified worker input hash mismatch")
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
        config_bytes = (resource_root / "configs" / "m06a.text.v1.json").read_bytes()
        config = json.loads(config_bytes.decode("utf-8"))
        stage = "import_parser"
        from .parsers.plain_text_v1 import parse_bytes

        stage = "read_verified_input"
        input_bytes = input_path.read_bytes()
        stage = "parse_input"
        candidate = parse_bytes(input_bytes, config)
        stage = "validate_candidate"
        candidate = validate_candidate_core(candidate, input_bytes=input_bytes)
        rendered = canonical_json(candidate)
        stage = "write_candidate"
        _write_exact(operation_root / OUTPUT_NAME, rendered)
        stage = "write_success_receipt"
        _write_receipt(
            operation_root,
            {
                "candidate_package_sha256": sha256_bytes(rendered),
                "controls": list(controls),
                "parser_id": PARSER_ID,
                "protocol_version": WORKER_PROTOCOL_VERSION,
                "security_profile_id": SECURITY_PROFILE_ID,
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
                "parser_id": PARSER_ID,
                "protocol_version": WORKER_PROTOCOL_VERSION,
                "security_profile_id": SECURITY_PROFILE_ID,
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
                    "parser_id": PARSER_ID,
                    "protocol_version": WORKER_PROTOCOL_VERSION,
                    "security_profile_id": SECURITY_PROFILE_ID,
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
