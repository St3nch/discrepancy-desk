from __future__ import annotations

import json
import subprocess
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
    completed = subprocess.run(
        ["git", "ls-files", "--", "desktop"],
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = set(completed.stdout.splitlines())
    forbidden_prefixes = (
        "desktop/node_modules/",
        "desktop/dist/",
        "desktop/src-tauri/binaries/",
        "desktop/src-tauri/gen/",
        "desktop/src-tauri/target/",
    )
    assert not any(path.startswith(forbidden_prefixes) for path in tracked)
    assert "desktop/pnpm-lock.yaml" not in tracked

def test_dependency_authority_is_the_admitted_npm_lock() -> None:
    lock = json.loads((DESKTOP / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["lockfileVersion"] == 3
    assert lock["packages"]
    assert (TAURI / "Cargo.lock").is_file()
