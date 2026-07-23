from __future__ import annotations

import re
import shutil
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


def test_m06a_text_canon_011_v0004_desktop_visibility_and_end_to_end(tmp_path: Path) -> None:
    headers = {"x-discrepancy-desk-token": TOKEN}
    with _client(tmp_path) as client:
        created = client.post(
            "/desktop-api/v1/vaults",
            headers=headers,
            json={
                "display_name": "Canonical Text Vault",
                "relative_root": "canonical-text",
                "owned_account_ids": [],
                "operation_key": "text:desktop:create",
            },
        )
        assert created.status_code == 201
        vault_id = created.json()["vault_id"]
        health = client.get(
            f"/desktop-api/v1/vaults/{vault_id}/health", headers=headers
        )
        assert health.status_code == 200
        assert health.json()["migration"] == "V0004"

        parser_status = client.get(
            f"/desktop-api/v1/vaults/{vault_id}/parsers", headers=headers
        )
        assert parser_status.status_code == 200
        parser = parser_status.json()["parsers"][0]
        assert parser["admission_ready"] is True
        manifest = parser["admission_manifest"]

        admitted = client.post(
            f"/desktop-api/v1/vaults/{vault_id}/parsers/m06a.text.v1/admit",
            headers=headers,
            json={
                "operation_key": "text:desktop:admit",
                "confirmation_text": manifest["confirmation_text"],
                "expected_manifest": manifest,
            },
        )
        assert admitted.status_code == 201
        admission_id = admitted.json()["parser_admission_version_id"]
        assert admitted.json()["canonical_available"] is True

        intake = client.post(
            f"/desktop-api/v1/vaults/{vault_id}/intake",
            headers=headers,
            json={
                "source_kind": "manual_file",
                "descriptor_class": "file",
                "display_label": "canonical.txt",
                "retention_classification": "preservation_compatible",
                "policy_basis_reference": "D039 desktop synthetic proof",
                "human_classification_note": "safe fixture",
                "client_nonce": "text-desktop-nonce",
                "operation_key": "text:desktop:intake",
                "expects_bytes": True,
                "supplied_filename": "canonical.txt",
                "supplied_media_type": "text/plain",
                "advisory_byte_size": 11,
            },
        )
        assert intake.status_code == 201
        acquisition_id = intake.json()["acquisition_id"]
        uploaded = client.post(
            f"/desktop-api/v1/vaults/{vault_id}/acquisitions/{acquisition_id}/artifact",
            headers=headers,
            data={
                "upload_authorization_id": intake.json()["upload_authorization_id"],
                "operation_key": "text:desktop:upload",
            },
            files={"artifact": ("canonical.txt", b"alpha\nbeta\n", "text/plain")},
        )
        assert uploaded.status_code == 201

        records = client.get(
            f"/desktop-api/v1/vaults/{vault_id}/intake", headers=headers
        )
        assert records.status_code == 200
        link_id = records.json()["artifacts"][0]["acquisition_artifact_link_id"]
        parsed = client.post(
            f"/desktop-api/v1/vaults/{vault_id}/artifacts/{link_id}/parse-text",
            headers=headers,
            json={
                "operation_key": "text:desktop:parse",
                "expected_parser_admission_version_id": admission_id,
            },
        )
        assert parsed.status_code == 201
        assert parsed.json()["document_version_id"]

        documents = client.get(
            f"/desktop-api/v1/vaults/{vault_id}/documents", headers=headers
        )
        assert documents.status_code == 200
        assert len(documents.json()["documents"]) == 1
        assert "alpha" not in documents.text
        assert str(tmp_path) not in documents.text


def test_m06a_text_canon_026_api_ui_mutation_surface_is_exact(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        route_paths = {route.path for route in client.app.routes}
    assert "/desktop-api/v1/vaults/{vault_id}/parsers/m06a.text.v1/admit" in route_paths
    assert (
        "/desktop-api/v1/vaults/{vault_id}/artifacts/{acquisition_artifact_link_id}/parse-text"
        in route_paths
    )
    assert "/desktop-api/v1/vaults/{vault_id}/documents" in route_paths
    forbidden = ("suspend", "revoke", "retire", "prohibit", "parse-all", "admit-all")
    assert not any(any(value in path for value in forbidden) for path in route_paths)
    app_source = Path("desktop/src/App.tsx").read_text(encoding="utf-8")
    assert 'nextHealth.migration === "V0004"' in app_source
    assert "ADMIT m06a.text.v1 FOR THIS VAULT" not in app_source
    assert "Parse as plain text" in app_source
    assert "parser configuration" not in app_source.lower()


def test_m06a_text_canon_027_no_path_secret_evidence_or_content_leakage() -> None:
    web_source = Path("src/discrepancy_desk/web.py").read_text(encoding="utf-8")
    client_source = Path("desktop/src/api/client.ts").read_text(encoding="utf-8")
    app_source = Path("desktop/src/App.tsx").read_text(encoding="utf-8")
    combined = web_source + client_source + app_source
    assert "evidence/" not in client_source
    assert "runtime/test-evidence" not in combined
    assert "fixture_manifest_sha256" not in app_source
    assert "raw_text" not in client_source
    assert "normalized_text" not in client_source


def test_m06a_text_canon_028_no_later_parser_or_capability_leakage() -> None:
    web_source = Path("src/discrepancy_desk/web.py").read_text(encoding="utf-8")
    client_source = Path("desktop/src/api/client.ts").read_text(encoding="utf-8")
    app_source = Path("desktop/src/App.tsx").read_text(encoding="utf-8")
    combined = (web_source + client_source + app_source).lower()
    for forbidden in (
        "m06a.srt.v1",
        "m06a.vtt.v1",
        "m06a.json.v1",
        "qdrant_client",
        "/providers/",
        "provider_client",
        "parse-all",
        "admit-all",
    ):
        assert forbidden not in combined


def test_m06a_srt_022_desktop_status_is_read_only_under_test(tmp_path: Path) -> None:
    headers = {"x-discrepancy-desk-token": TOKEN}
    with _client(tmp_path) as client:
        created = client.post(
            "/desktop-api/v1/vaults",
            headers=headers,
            json={
                "display_name": "SRT Status Vault",
                "relative_root": "srt-status-vault",
                "owned_account_ids": [],
                "operation_key": "d040:srt-status:create",
            },
        )
        assert created.status_code == 201
        vault_id = created.json()["vault_id"]
        response = client.get(
            f"/desktop-api/v1/vaults/{vault_id}/parsers",
            headers=headers,
        )
        assert response.status_code == 200
        parsers = response.json()["parsers"]
        srt = [row for row in parsers if row["parser_id"] == "m06a.srt.v1"]
        assert len(srt) == 1
        assert srt[0]["display_name"] == "SubRip (SRT)"
        assert srt[0]["state"] == "under_test"
        assert srt[0]["canonical_available"] is False
        assert srt[0]["admission_ready"] is False
        assert srt[0]["admission_manifest"] is None

        route_paths = {route.path for route in client.app.routes}
        assert "/desktop-api/v1/vaults/{vault_id}/parsers/m06a.srt.v1/admit" not in route_paths
        assert (
            "/desktop-api/v1/vaults/{vault_id}/artifacts/{acquisition_artifact_link_id}/parse-srt"
            not in route_paths
        )

    app_source = Path("desktop/src/App.tsx").read_text(encoding="utf-8")
    assert "SubRip (SRT)" not in app_source
    assert "Admit SRT" not in app_source
    assert "Parse as SRT" not in app_source


def test_m06a_srt_c1_007_srt_resource_failure_preserves_plain_text_status(
    tmp_path: Path, monkeypatch: Any
) -> None:
    headers = {"x-discrepancy-desk-token": TOKEN}
    with _client(tmp_path) as client:
        created = client.post(
            "/desktop-api/v1/vaults",
            headers=headers,
            json={
                "display_name": "SRT Isolation Vault",
                "relative_root": "srt-isolation-vault",
                "owned_account_ids": [],
                "operation_key": "d041:srt-status:create",
            },
        )
        assert created.status_code == 201
        vault_id = created.json()["vault_id"]

        fake_project = tmp_path / "fake-project"
        shutil.copytree(Path("parser_resources"), fake_project / "parser_resources")
        shutil.copy2(Path("uv.lock"), fake_project / "uv.lock")
        (fake_project / "parser_resources" / "m06a.srt.v1" / "schema.json").write_text(
            '{"tampered":true}\n', encoding="utf-8", newline="\n"
        )
        monkeypatch.setattr(web_module, "PROJECT_ROOT", fake_project)

        response = client.get(
            f"/desktop-api/v1/vaults/{vault_id}/parsers",
            headers=headers,
        )
        assert response.status_code == 200
        parsers = response.json()["parsers"]
        plain_text = [row for row in parsers if row["parser_id"] == "m06a.text.v1"]
        srt = [row for row in parsers if row["parser_id"] == "m06a.srt.v1"]
        assert len(plain_text) == 1
        assert plain_text[0]["state"] == "under_test"
        assert plain_text[0]["admission_ready"] is True
        assert plain_text[0]["admission_manifest"] is not None
        assert len(srt) == 1
        assert srt[0]["state"] == "unavailable"
        assert srt[0]["canonical_available"] is False
        assert srt[0]["admission_ready"] is False
        assert srt[0]["admission_manifest"] is None
        assert srt[0]["reason_code"] == "packaged_tuple_mismatch"
        assert str(tmp_path) not in response.text
        assert "tampered" not in response.text
