from __future__ import annotations

import json
from pathlib import Path


DESKTOP = Path("desktop")
TAURI = DESKTOP / "src-tauri"


def test_windows_package_is_current_user_nsis_without_updater() -> None:
    config = json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))
    assert config["bundle"]["targets"] == ["nsis"]
    assert config["bundle"]["windows"]["nsis"]["installMode"] == "currentUser"
    serialized = json.dumps(config).lower()
    assert "updater" not in serialized
    assert "endpoint" not in serialized


def test_required_windows_icon_exists_and_is_nonempty() -> None:
    icon = TAURI / "icons" / "icon.ico"
    assert icon.is_file()
    assert icon.stat().st_size > 0


def test_generated_native_outputs_are_not_tracked_source() -> None:
    assert not (DESKTOP / "node_modules").exists()
    assert not (DESKTOP / "dist").exists()
    assert not (TAURI / "target").exists()
    assert not (TAURI / "gen").exists()
    assert not (DESKTOP / "pnpm-lock.yaml").exists()
    assert not (TAURI / "Cargo.lock").exists()


def test_dependency_authority_is_the_admitted_npm_lock() -> None:
    lock = json.loads((DESKTOP / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["lockfileVersion"] == 3
    assert lock["packages"]
