from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from discrepancy_desk.web import create_app

TOKEN = "phase-2-test-token-" + "x" * 32
HEADERS = {"x-discrepancy-desk-token": TOKEN}


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


def _create_vault(client: TestClient) -> str:
    response = client.post(
        "/desktop-api/v1/vaults",
        headers=HEADERS,
        json={
            "display_name": "Phase 2 Vault",
            "relative_root": "phase-2-vault",
            "owned_account_ids": [],
            "operation_key": "phase2:create",
        },
    )
    assert response.status_code == 201
    return str(response.json()["vault_id"])


def _start_file(client: TestClient, vault_id: str, key: str) -> dict[str, object]:
    response = client.post(
        f"/desktop-api/v1/vaults/{vault_id}/intake",
        headers=HEADERS,
        json={
            "source_kind": "manual_file",
            "descriptor_class": "file",
            "display_label": f"{key}.txt",
            "retention_classification": "preservation_compatible",
            "policy_basis_reference": "owner-authorized local preservation",
            "human_classification_note": "manual Phase 2 fixture",
            "client_nonce": f"nonce:{key}",
            "operation_key": f"intake:{key}",
            "expects_bytes": True,
            "supplied_filename": f"{key}.txt",
            "supplied_media_type": "text/plain",
            "advisory_byte_size": 12,
            "actor_id": "fabricated-request-actor",
            "vault_path": "C:/fabricated",
        },
    )
    assert response.status_code == 201
    return dict(response.json())


def test_phase2_desktop_intake_and_backup_flow_is_governed(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        vault_id = _create_vault(client)
        health = client.get(
            f"/desktop-api/v1/vaults/{vault_id}/health", headers=HEADERS
        )
        assert health.status_code == 200
        assert health.json()["migration"] == "V0002"

        invalid_type = client.post(
            f"/desktop-api/v1/vaults/{vault_id}/intake",
            headers=HEADERS,
            json={
                "source_kind": "manual_file",
                "descriptor_class": "file",
                "display_label": "invalid type",
                "retention_classification": "preservation_compatible",
                "policy_basis_reference": "owner local preservation",
                "human_classification_note": "must reject type",
                "client_nonce": "nonce:invalid-type",
                "operation_key": "phase2:invalid-type",
                "expects_bytes": "false",
            },
        )
        assert invalid_type.status_code == 400
        assert invalid_type.json()["message"] == "expects_bytes must be a boolean"

        rejected = client.post(
            f"/desktop-api/v1/vaults/{vault_id}/intake",
            headers=HEADERS,
            json={
                "source_kind": "manual_file",
                "descriptor_class": "file",
                "display_label": "must-not-persist.txt",
                "retention_classification": "timed_deletion_required",
                "policy_basis_reference": "delete after seven days",
                "human_classification_note": "reject before bytes",
                "client_nonce": "nonce:reject",
                "operation_key": "phase2:reject",
                "expects_bytes": True,
                "supplied_filename": "must-not-persist.txt",
                "actor_id": "fabricated-request-actor",
            },
        )
        assert rejected.status_code == 422
        assert rejected.json()["status"] == "rejected"
        assert rejected.json()["reason_code"] == "timed_deletion_required"
        assert not any(path.is_file() for path in (tmp_path / "vaults" / "phase-2-vault" / "temp").rglob("*"))

        first = _start_file(client, vault_id, "first")
        upload = client.post(
            f"/desktop-api/v1/vaults/{vault_id}/acquisitions/{first['acquisition_id']}/artifact",
            headers=HEADERS,
            data={
                "upload_authorization_id": first["upload_authorization_id"],
                "operation_key": "phase2:upload:first",
            },
            files={"artifact": ("first.txt", b"shared bytes", "text/plain")},
        )
        assert upload.status_code == 201
        admitted = upload.json()
        assert admitted["byte_size"] == len(b"shared bytes")
        assert admitted["reused_existing"] is False
        assert str(tmp_path) not in upload.text

        second = _start_file(client, vault_id, "second")
        duplicate = client.post(
            f"/desktop-api/v1/vaults/{vault_id}/acquisitions/{second['acquisition_id']}/artifact",
            headers=HEADERS,
            data={
                "upload_authorization_id": second["upload_authorization_id"],
                "operation_key": "phase2:upload:second",
            },
            files={"artifact": ("second.txt", b"shared bytes", "text/plain")},
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["artifact_id"] == admitted["artifact_id"]
        assert duplicate.json()["reused_existing"] is True

        locator = client.post(
            f"/desktop-api/v1/vaults/{vault_id}/intake",
            headers=HEADERS,
            json={
                "source_kind": "manual_locator",
                "descriptor_class": "locator",
                "display_label": "Manual locator",
                "locator": "https://example.invalid/record",
                "retention_classification": "preservation_compatible",
                "policy_basis_reference": "locator only",
                "human_classification_note": "no remote retrieval",
                "client_nonce": "nonce:locator",
                "operation_key": "phase2:locator",
                "expects_bytes": False,
            },
        )
        assert locator.status_code == 201
        assert locator.json()["status"] == "recorded"

        records = client.get(
            f"/desktop-api/v1/vaults/{vault_id}/intake", headers=HEADERS
        )
        assert records.status_code == 200
        assert len(records.json()["acquisitions"]) == 3
        assert len(records.json()["artifacts"]) == 1
        assert len(records.json()["rejections"]) == 1
        assert "fabricated-request-actor" not in records.text
        assert "C:/fabricated" not in records.text

        backup = client.post(
            f"/desktop-api/v1/vaults/{vault_id}/backups",
            headers=HEADERS,
            json={"operation_key": "phase2:backup"},
        )
        assert backup.status_code == 201
        generation_id = str(backup.json()["generation_id"])
        verification = client.post(
            f"/desktop-api/v1/vaults/{vault_id}/backups/{generation_id}/verify",
            headers=HEADERS,
            json={"operation_key": "phase2:backup:verify"},
        )
        assert verification.status_code == 200
        assert verification.json()["status"] == "verified"
        assert verification.json()["artifact_count"] == 1
        replay_verification = client.post(
            f"/desktop-api/v1/vaults/{vault_id}/backups/{generation_id}/verify",
            headers=HEADERS,
            json={"operation_key": "phase2:backup:verify"},
        )
        assert replay_verification.status_code == 200
        assert replay_verification.json() == verification.json()
        escaped_generation = client.post(
            f"/desktop-api/v1/vaults/{vault_id}/backups/..%2Fdatabase/verify",
            headers=HEADERS,
            json={"operation_key": "phase2:backup:escape"},
        )
        assert escaped_generation.status_code in {404, 409}
        proof_root = tmp_path / "runtime" / "restore-proofs"
        assert not proof_root.exists() or not any(proof_root.rglob("*"))

        route_paths = {route.path for route in client.app.routes}
        assert "/vaults" not in route_paths
        assert "/desktop-api/v1/vaults/{vault_id}/intake" in route_paths
        assert "/desktop-api/v1/vaults/{vault_id}/backups" in route_paths

    client_source = Path("desktop/src/api/client.ts").read_text(encoding="utf-8")
    app_source = Path("desktop/src/App.tsx").read_text(encoding="utf-8")
    assert "startVaultIntake" in client_source
    assert "uploadVaultArtifact" in client_source
    assert "sqlite" not in client_source.lower()
    assert "actor_id" not in client_source
    assert 'type="file"' in app_source
    assert not Path("src/discrepancy_desk/templates/vaults.html").exists()
