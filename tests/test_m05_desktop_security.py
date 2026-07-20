from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("desktop")


def test_capability_is_deny_by_default() -> None:
    capability = json.loads(
        (ROOT / "src-tauri/capabilities/main.json").read_text(encoding="utf-8")
    )
    assert capability["windows"] == ["main"]
    assert capability["permissions"] == ["core:default", "dialog:allow-open"]
    rendered = json.dumps(capability).lower()
    for forbidden in ("shell", "filesystem", "updater", "global-shortcut", "remote"):
        assert forbidden not in rendered


def test_tauri_config_is_loopback_and_nsis_current_user_only() -> None:
    config = json.loads((ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    assert config["build"]["devUrl"] == "http://127.0.0.1:1420"
    assert config["bundle"]["targets"] == ["nsis"]
    assert config["bundle"]["windows"]["nsis"]["installMode"] == "currentUser"
    csp = config["app"]["security"]["csp"]
    assert "127.0.0.1" in csp
    assert "https:" not in csp
    assert "updater" not in json.dumps(config).lower()


def test_frontend_has_no_sqlite_or_business_authority_dependency() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    dependencies = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    assert not any("sqlite" in name.lower() for name in dependencies)
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src").rglob("*.ts*")
    ).lower()
    assert "select * from" not in source
    assert "insert into" not in source
    assert "approve_revision" not in source
    assert "record_publication" not in source


def test_launch_token_is_not_passed_as_command_line_argument() -> None:
    backend = (ROOT / "src-tauri/src/backend.rs").read_text(encoding="utf-8")
    assert '.env("DISCREPANCY_DESK_DESKTOP_TOKEN", &token)' in backend
    assert ".arg(&token)" not in backend
    assert "127.0.0.1" in backend
    assert "backend already owns the desktop database" in backend


def test_native_evidence_import_is_bounded() -> None:
    commands = Path("desktop/src-tauri/src/commands.rs").read_text(encoding="utf-8")
    library = Path("desktop/src-tauri/src/lib.rs").read_text(encoding="utf-8")
    assert "import_evidence_file" in commands
    assert "100 * 1024 * 1024" in commands
    assert '.join("evidence")' in commands
    assert '.join("inbox")' in commands
    assert "std::fs::copy" in commands
    assert "tauri_plugin_dialog::init()" in library
    assert "execute_sql" not in commands
