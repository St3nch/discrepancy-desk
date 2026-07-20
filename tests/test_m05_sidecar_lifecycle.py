from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


RUST_ROOT = Path("desktop/src-tauri/src")


def test_supervisor_owns_single_child_and_clears_session_on_stop() -> None:
    backend = (RUST_ROOT / "backend.rs").read_text(encoding="utf-8")
    assert "Mutex<Option<Child>>" in backend
    assert "backend already owns the desktop database" in backend
    assert "child.kill()" in backend
    assert "child.wait()" in backend
    assert "= None" in backend


def test_sidecar_receives_token_and_loopback_by_environment_only() -> None:
    backend = (RUST_ROOT / "backend.rs").read_text(encoding="utf-8")
    assert 'DISCREPANCY_DESK_DESKTOP_TOKEN' in backend
    assert 'DISCREPANCY_DESK_DESKTOP_HOST", "127.0.0.1"' in backend
    assert 'DISCREPANCY_DESK_DESKTOP_PORT' in backend
    assert 'DISCREPANCY_DESK_DESKTOP_DATABASE' in backend
    assert 'DISCREPANCY_DESK_DESKTOP_EVIDENCE_ROOT' in backend
    assert 'DISCREPANCY_DESK_DESKTOP_MIGRATIONS_ROOT' in backend
    assert ".arg(&token)" not in backend
    assert "stdout(Stdio::null())" in backend


def test_rust_command_surface_exposes_session_not_business_mutations() -> None:
    commands = (RUST_ROOT / "commands.rs").read_text(encoding="utf-8")
    library = (RUST_ROOT / "lib.rs").read_text(encoding="utf-8")
    assert "backend_session" in commands
    assert "commands::backend_session" in library
    assert "commands::import_evidence_file" in library
    for forbidden in (
        "approve_revision",
        "record_publication",
        "schedule_work_item",
        "open_database",
        "execute_sql",
    ):
        assert forbidden not in commands
        assert forbidden not in library


def test_supervisor_reserves_dynamic_loopback_port_and_polls_health() -> None:
    backend = (RUST_ROOT / "backend.rs").read_text(encoding="utf-8")
    assert 'TcpListener::bind(("127.0.0.1", 0))' in backend
    assert "reserve_loopback_port" in backend
    assert "/desktop-api/v1/health" in backend
    assert "X-Discrepancy-Desk-Token" in backend
    assert "health check timed out" in backend
    assert "backend exited before becoming healthy" in backend


def test_tauri_setup_starts_fixed_executable_and_exit_stops_child() -> None:
    library = (RUST_ROOT / "lib.rs").read_text(encoding="utf-8")
    assert 'std::env::var("DISCREPANCY_DESK_BACKEND_EXECUTABLE")' in library
    assert 'resource_dir.join("backend").join("discrepancy-desk-backend.exe")' in library
    assert "current_exe()" in library
    assert ".start(" in library
    assert "&database_path.to_string_lossy()" in library
    assert "&evidence_root.to_string_lossy()" in library
    assert "&migrations_root.to_string_lossy()" in library
    assert "RunEvent::Exit" in library
    assert "RunEvent::ExitRequested" in library
    assert "supervisor.stop()" in library
    assert "Command::new" not in library


def test_real_python_desktop_backend_starts_authenticates_and_stops(tmp_path: Path) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    token = "t" * 64
    env = os.environ.copy()
    env.update(
        {
            "DISCREPANCY_DESK_DESKTOP_TOKEN": token,
            "DISCREPANCY_DESK_DESKTOP_HOST": "127.0.0.1",
            "DISCREPANCY_DESK_DESKTOP_PORT": str(port),
            "DISCREPANCY_DESK_DESKTOP_DATABASE": str(tmp_path / "desk.sqlite3"),
            "DISCREPANCY_DESK_DESKTOP_EVIDENCE_ROOT": str(tmp_path / "evidence"),
            "DISCREPANCY_DESK_DESKTOP_MIGRATIONS_ROOT": str(Path("migrations").resolve()),
        }
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from discrepancy_desk.web import desktop_main; desktop_main()",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 15
        payload = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stderr = process.stderr.read() if process.stderr is not None else ""
                raise AssertionError(f"desktop backend exited early: {stderr}")
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/desktop-api/v1/health",
                headers={"X-Discrepancy-Desk-Token": token},
            )
            try:
                with urllib.request.urlopen(request, timeout=1) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    break
            except OSError:
                time.sleep(0.1)
        assert payload is not None
        assert payload["status"] == "healthy"
        assert payload["api_version"] == "1"
        assert payload["migration"] == "0004"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    assert process.poll() is not None


def test_packaged_proof_auto_exit_is_bounded_and_disabled_by_default() -> None:
    library = (RUST_ROOT / "lib.rs").read_text(encoding="utf-8")
    assert "DISCREPANCY_DESK_DESKTOP_PROOF_AUTO_EXIT_MS" in library
    assert "100..=60_000" in library
    assert "let _ = supervisor.stop();" in library
    assert "handle.exit(0)" in library
    assert "if let Ok(value)" in library


def test_supervisor_drop_is_last_resort_cleanup() -> None:
    backend = (RUST_ROOT / "backend.rs").read_text(encoding="utf-8")
    assert "impl Drop for BackendSupervisor" in backend
    assert "let _ = self.stop();" in backend
