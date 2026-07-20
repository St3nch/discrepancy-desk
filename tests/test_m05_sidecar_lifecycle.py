from __future__ import annotations

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
    assert ".arg(&token)" not in backend
    assert "stdout(Stdio::null())" in backend


def test_rust_command_surface_exposes_session_not_business_mutations() -> None:
    commands = (RUST_ROOT / "commands.rs").read_text(encoding="utf-8")
    library = (RUST_ROOT / "lib.rs").read_text(encoding="utf-8")
    assert "backend_session" in commands
    assert "generate_handler![commands::backend_session]" in library
    for forbidden in (
        "approve_revision",
        "record_publication",
        "schedule_work_item",
        "open_database",
        "execute_sql",
    ):
        assert forbidden not in commands
        assert forbidden not in library
