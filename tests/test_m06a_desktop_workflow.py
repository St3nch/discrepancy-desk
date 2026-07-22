from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import discrepancy_desk.web as web_module
from discrepancy_desk.web import create_app

TOKEN = "phase-1-test-token-" + "x" * 32


def _client(tmp_path: Path) -> TestClient:
    app = create_app(
        database_path=tmp_path / "runtime" / "central.sqlite3",
        evidence_root=tmp_path / "evidence",
        migrations_root=Path("migrations"),
        vault_base=tmp_path / "vaults",
        vault_migrations_root=Path("vault_migrations"),
        desktop_token=TOKEN,
        desktop_api_version="1",
    )
    return TestClient(app)


def test_m06a_ht_075_logs_cache_temp_are_vault_scoped(tmp_path: Path) -> None:
    headers = {"x-discrepancy-desk-token": TOKEN}
    with _client(tmp_path) as client:
        first = client.post(
            "/desktop-api/v1/vaults",
            headers=headers,
            json={
                "display_name": "Brand A",
                "relative_root": "brand-a",
                "owned_account_ids": [],
                "operation_key": "phase1:leak:a",
            },
        )
        second = client.post(
            "/desktop-api/v1/vaults",
            headers=headers,
            json={
                "display_name": "Brand B",
                "relative_root": "brand-b",
                "owned_account_ids": [],
                "operation_key": "phase1:leak:b",
            },
        )
        assert first.status_code == 201
        assert second.status_code == 201
        first_id = first.json()["vault_id"]
        second_id = second.json()["vault_id"]
        sentinel = "brand-a-private-sentinel"
        first_temp = tmp_path / "vaults" / "brand-a" / "temp" / "fixture"
        first_temp.mkdir()
        (first_temp / "sentinel.txt").write_text(sentinel, encoding="utf-8")

        response = client.get(
            f"/desktop-api/v1/vaults/{second_id}/health",
            headers=headers,
        )
        assert response.status_code == 200
        body = response.text
        assert second_id in body
        assert first_id not in body
        assert sentinel not in body
        assert str(first_temp) not in body

        second_database = tmp_path / "vaults" / "brand-b" / "database" / "vault.sqlite3"
        second_database.unlink()
        blocked = client.get(
            f"/desktop-api/v1/vaults/{second_id}/health",
            headers=headers,
        )
        assert blocked.status_code == 409
        assert blocked.json()["reason_code"] == "vault_resource_unavailable"
        assert str(tmp_path) not in blocked.text
        assert "brand-b" not in blocked.text

        duplicate = client.post(
            "/desktop-api/v1/vaults",
            headers=headers,
            json={
                "display_name": "Duplicate Brand",
                "relative_root": "brand-a",
                "owned_account_ids": [],
                "operation_key": "phase1:leak:duplicate",
            },
        )
        assert duplicate.status_code == 400
        assert duplicate.json()["message"] == "Vault root is already in use."
        assert str(tmp_path) not in duplicate.text
        assert "brand-a" not in duplicate.text

        fabricated = client.get(
            "/desktop-api/v1/vaults/fabricated/health",
            headers=headers,
        )
        assert fabricated.status_code == 409
        assert "brand-a" not in fabricated.text
        assert "brand-b" not in fabricated.text


def test_m06a_ht_076_secret_leakage_detected() -> None:
    roots = [
        Path("src/discrepancy_desk"),
        Path("migrations"),
        Path("vault_migrations"),
        Path("scripts"),
        Path("desktop/src"),
        Path("desktop/src-tauri/src"),
    ]
    patterns = [
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
        re.compile(r"AGE-SECRET-KEY-[A-Z0-9]+"),
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    ]
    findings: list[str] = []
    for root in roots:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {
                ".py",
                ".ts",
                ".tsx",
                ".rs",
                ".html",
                ".ini",
                ".mako",
            }:
                text = path.read_text(encoding="utf-8", errors="replace")
                if any(pattern.search(text) for pattern in patterns):
                    findings.append(path.as_posix())
    assert findings == []


def test_m06a_ht_108_tauri_api_uses_governed_service(
    tmp_path: Path, monkeypatch: Any
) -> None:
    calls: list[dict[str, object]] = []
    real_provision = web_module.provision_vault

    def tracked_provision(connection: Any, **kwargs: object) -> str:
        calls.append(dict(kwargs))
        return real_provision(connection, **kwargs)

    monkeypatch.setattr(web_module, "provision_vault", tracked_provision)
    headers = {"x-discrepancy-desk-token": TOKEN}

    with _client(tmp_path) as client:
        response = client.post(
            "/desktop-api/v1/vaults",
            headers=headers,
            json={
                "display_name": "Desktop Brand",
                "relative_root": "desktop-brand",
                "owned_account_ids": [],
                "operation_key": "phase1:tauri-service:desktop",
                "actor_id": "fabricated-request-actor",
            },
        )
        assert response.status_code == 201
        vault_id = response.json()["vault_id"]

        assert len(calls) == 1
        assert calls[0]["owner_actor_id"] == "owner-local"
        assert calls[0]["operation_key"] == "phase1:tauri-service:desktop"
        assert "fabricated-request-actor" not in calls[0].values()

        health = client.get(
            f"/desktop-api/v1/vaults/{vault_id}/health",
            headers=headers,
        )
        assert health.status_code == 200
        assert health.json()["status"] == "healthy"

        route_paths = {route.path for route in client.app.routes}
        assert "/desktop-api/v1/vaults" in route_paths
        assert "/desktop-api/v1/vaults/{vault_id}/health" in route_paths
        assert "/vaults" not in route_paths

    client_source = Path("desktop/src/api/client.ts").read_text(encoding="utf-8")
    assert "createVault" in client_source
    assert 'request<{ vault_id: string }>("/desktop-api/v1/vaults"' in client_source
    assert "sqlite" not in client_source.lower()
    assert not Path("src/discrepancy_desk/templates/vaults.html").exists()

    marker_text = (
        tmp_path / "vaults" / "desktop-brand" / "VAULT_IDENTITY.json"
    ).read_text(encoding="utf-8")
    assert vault_id in marker_text
    assert "fabricated-request-actor" not in marker_text
