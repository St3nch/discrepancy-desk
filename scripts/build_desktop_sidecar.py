from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime" / "desktop-sidecar-build"
BINARIES = ROOT / "desktop" / "src-tauri" / "binaries"
TARGET_DIR = BINARIES / "discrepancy-desk-backend"
TARGET = TARGET_DIR / "discrepancy-desk-backend.exe"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if RUNTIME.exists():
        shutil.rmtree(RUNTIME)
    RUNTIME.mkdir(parents=True)
    BINARIES.mkdir(parents=True, exist_ok=True)
    if TARGET_DIR.exists():
        shutil.rmtree(TARGET_DIR)
    launcher = RUNTIME / "desktop_backend_launcher.py"
    launcher.write_text(
        "import sys\n"
        "if __name__ == '__main__':\n"
        "    if '--m06a-parser-worker' in sys.argv:\n"
        "        from discrepancy_desk.parser_worker import main\n"
        "        raise SystemExit(main())\n"
        "    if '--m06a-srt-parser-worker' in sys.argv:\n"
        "        from discrepancy_desk.srt_worker import main\n"
        "        raise SystemExit(main())\n"
        "    if '--m06a-vtt-parser-worker' in sys.argv:\n"
        "        from discrepancy_desk.vtt_worker import main\n"
        "        raise SystemExit(main())\n"
        "    from discrepancy_desk.web import desktop_main\n"
        "    desktop_main()\n",
        encoding="utf-8",
        newline="\n",
    )
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        "discrepancy-desk-backend",
        "--distpath",
        str(BINARIES),
        "--workpath",
        str(RUNTIME / "work"),
        "--specpath",
        str(RUNTIME),
        "--paths",
        str(ROOT / "src"),
        "--collect-all",
        "discrepancy_desk",
        "--add-data",
        f"{ROOT / 'migrations'};migrations",
        "--add-data",
        f"{ROOT / 'vault_migrations'};vault_migrations",
        "--add-data",
        f"{ROOT / 'parser_resources'};parser_resources",
        "--add-data",
        f"{ROOT / 'uv.lock'};.",
        "--add-data",
        f"{ROOT / 'alembic.ini'};.",
        str(launcher),
    ]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0 or not TARGET.is_file():
        if TARGET_DIR.exists():
            shutil.rmtree(TARGET_DIR)
        return completed.returncode or 1
    evidence = {
        "schema_version": 1,
        "artifact": str(TARGET.relative_to(ROOT)).replace("\\", "/"),
        "sha256": sha256(TARGET),
        "executable_size_bytes": TARGET.stat().st_size,
        "package_size_bytes": sum(item.stat().st_size for item in TARGET_DIR.rglob("*") if item.is_file()),
        "python_version": sys.version.split()[0],
        "command": command,
    }
    (RUNTIME / "sidecar-build-evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
