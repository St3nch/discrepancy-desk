import { FormEvent, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { desktopClient } from "./api/client";
import type {
  CommandCenterResponse,
  DesktopHealth,
  MetricRow,
  OwnedAccount,
  ScheduleRow,
  SourceRow,
  SystemStatus,
  VaultBackupResult,
  VaultBackupVerification,
  VaultHealth,
  VaultIntakeRecords,
  VaultSummary,
} from "./api/types";

type Page =
  | "command"
  | "calendar"
  | "work"
  | "records"
  | "metrics"
  | "system"
  | "vaults"
  | "release"
  | "library";

function selectedWorkId(value: Record<string, unknown> | null): string | null {
  const work = value?.work_item;
  if (typeof work !== "object" || work === null) return null;
  const id = (work as Record<string, unknown>).id;
  return typeof id === "string" ? id : null;
}

export default function App() {
  const [page, setPage] = useState<Page>("command");
  const [health, setHealth] = useState<DesktopHealth | null>(null);
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [accounts, setAccounts] = useState<OwnedAccount[]>([]);
  const [accountId, setAccountId] = useState("");
  const [vaults, setVaults] = useState<VaultSummary[]>([]);
  const [vaultId, setVaultId] = useState("");
  const [vaultHealth, setVaultHealth] = useState<VaultHealth | null>(null);
  const [vaultName, setVaultName] = useState("The Discrepancy Desk");
  const [vaultRoot, setVaultRoot] = useState("discrepancy-desk");
  const [vaultRecords, setVaultRecords] = useState<VaultIntakeRecords | null>(null);
  const [vaultBackup, setVaultBackup] = useState<VaultBackupResult | null>(null);
  const [vaultBackupVerification, setVaultBackupVerification] =
    useState<VaultBackupVerification | null>(null);
  const [intakeLabel, setIntakeLabel] = useState("");
  const [intakeLocator, setIntakeLocator] = useState("");
  const [policyBasis, setPolicyBasis] = useState("owner-authorized local preservation");
  const [classificationNote, setClassificationNote] = useState("");
  const [retentionClassification, setRetentionClassification] = useState<
    "preservation_compatible" | "timed_deletion_required" | "unknown"
  >("preservation_compatible");
  const [selectedVaultFile, setSelectedVaultFile] = useState<File | null>(null);
  const [vaultOperationStatus, setVaultOperationStatus] = useState<string | null>(null);
  const [center, setCenter] = useState<CommandCenterResponse | null>(null);
  const [schedule, setSchedule] = useState<ScheduleRow[]>([]);
  const [records, setRecords] = useState<SourceRow[]>([]);
  const [metrics, setMetrics] = useState<MetricRow[]>([]);
  const [selectedWork, setSelectedWork] = useState<Record<string, unknown> | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = async (selected = accountId) => {
    if (!selected) return;
    const [nextCenter, nextSchedule, nextRecords, nextMetrics, nextSystem] =
      await Promise.all([
        desktopClient.commandCenter(selected),
        desktopClient.schedule(selected),
        desktopClient.records(selected),
        desktopClient.metrics(selected),
        desktopClient.system(),
      ]);
    setCenter(nextCenter);
    setSchedule(nextSchedule);
    setRecords(nextRecords);
    setMetrics(nextMetrics);
    setSystem(nextSystem);
  };

  const refreshVault = async (selected = vaultId) => {
    if (!selected) {
      setVaultHealth(null);
      setVaultRecords(null);
      return;
    }
    const nextHealth = await desktopClient.vaultHealth(selected);
    setVaultHealth(nextHealth);
    if (nextHealth.status === "healthy" && nextHealth.migration === "V0002") {
      setVaultRecords(await desktopClient.vaultIntakeRecords(selected));
    } else {
      setVaultRecords(null);
    }
  };

  useEffect(() => {
    desktopClient.health().then(setHealth).catch((value: Error) => setError(value.message));
    desktopClient
      .vaults()
      .then((rows) => {
        setVaults(rows);
        if (rows[0]) {
          setVaultId(rows[0].vault_id);
          void refreshVault(rows[0].vault_id);
        }
      })
      .catch((value: Error) => setError(value.message));
    desktopClient
      .accounts()
      .then((rows) => {
        setAccounts(rows);
        if (rows[0]) {
          setAccountId(rows[0].id);
          void refresh(rows[0].id);
        }
      })
      .catch((value: Error) => setError(value.message));
  }, []);

  const createVault = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const result = await desktopClient.createVault(vaultName.trim(), vaultRoot.trim());
      const rows = await desktopClient.vaults();
      setVaults(rows);
      setVaultId(result.vault_id);
      await refreshVault(result.vault_id);
      setPage("vaults");
    } catch (value) {
      setError(value instanceof Error ? value.message : "Vault creation refused");
    }
  };

  const migrateSelectedVault = async () => {
    if (!vaultId) return;
    try {
      await desktopClient.migrateVault(vaultId);
      await refreshVault(vaultId);
      setVaultOperationStatus("Vault migration completed at V0002.");
    } catch (value) {
      setError(value instanceof Error ? value.message : "Vault migration refused");
    }
  };

  const submitVaultIntake = async (event: FormEvent) => {
    event.preventDefault();
    if (!vaultId || !intakeLabel.trim()) return;
    try {
      const hasFile = selectedVaultFile !== null;
      const result = await desktopClient.startVaultIntake(vaultId, {
        sourceKind: hasFile ? "manual_file" : "manual_locator",
        descriptorClass: hasFile ? "file" : "locator",
        displayLabel: intakeLabel.trim(),
        locator: hasFile ? undefined : intakeLocator.trim(),
        retentionClassification,
        policyBasisReference: policyBasis.trim(),
        humanClassificationNote: classificationNote.trim(),
        expectsBytes: hasFile,
        suppliedFilename: selectedVaultFile?.name,
        suppliedMediaType: selectedVaultFile?.type || undefined,
        advisoryByteSize: selectedVaultFile?.size,
      });
      if (
        result.status === "ready_for_upload" &&
        result.acquisition_id &&
        result.upload_authorization_id &&
        selectedVaultFile
      ) {
        const admitted = await desktopClient.uploadVaultArtifact(
          vaultId,
          result.acquisition_id,
          result.upload_authorization_id,
          selectedVaultFile,
        );
        setVaultOperationStatus(
          `Artifact admitted: ${admitted.sha256} (${admitted.byte_size} bytes).`,
        );
      } else if (result.status === "recorded") {
        setVaultOperationStatus("Locator-only observation recorded without an artifact.");
      } else {
        setVaultOperationStatus(`Intake rejected: ${result.reason_code ?? "policy refusal"}.`);
      }
      setSelectedVaultFile(null);
      setIntakeLabel("");
      setIntakeLocator("");
      setClassificationNote("");
      await refreshVault(vaultId);
    } catch (value) {
      setError(value instanceof Error ? value.message : "Vault intake refused");
    }
  };

  const createAndVerifyVaultBackup = async () => {
    if (!vaultId) return;
    try {
      const backup = await desktopClient.createVaultBackup(vaultId);
      setVaultBackup(backup);
      const verification = await desktopClient.verifyVaultBackup(
        vaultId,
        backup.generation_id,
      );
      setVaultBackupVerification(verification);
      setVaultOperationStatus(`Backup ${backup.generation_id} verified.`);
    } catch (value) {
      setError(value instanceof Error ? value.message : "Vault backup refused");
    }
  };

  const capture = async (event: FormEvent) => {
    event.preventDefault();
    if (!title.trim()) return;
    try {
      const result = await desktopClient.capture(title.trim());
      setTitle("");
      await refresh();
      setSelectedWork(await desktopClient.workItem(result.work_item_id));
      setPage("work");
    } catch (value) {
      setError(value instanceof Error ? value.message : "Capture refused");
    }
  };

  const openWork = async (id: string) => {
    setSelectedWork(await desktopClient.workItem(id));
    setPage("work");
  };

  const importEvidence = async () => {
    const workItemId = selectedWorkId(selectedWork);
    if (!workItemId) return;
    const selected = await open({ multiple: false, directory: false });
    if (typeof selected !== "string") return;
    try {
      const relativePath = await invoke<string>("import_evidence_file", {
        sourcePath: selected,
      });
      await desktopClient.registerEvidence(workItemId, relativePath);
      setSelectedWork(await desktopClient.workItem(workItemId));
      await refresh();
    } catch (value) {
      setError(value instanceof Error ? value.message : String(value));
    }
  };

  const pages: Page[] = [
    "command",
    "calendar",
    "work",
    "records",
    "metrics",
    "system",
    "vaults",
    "release",
    "library",
  ];

  return (
    <main>
      <header>
        <p>B1-L7 CONTROL ROOM</p>
        <h1>The Discrepancy Desk</h1>
        <p>
          {health
            ? `Backend ${health.status} · API v${health.api_version} · DB ${health.migration}`
            : error ?? "Starting governed backend…"}
        </p>
      </header>
      <nav>
        {pages.map((name) => (
          <button
            key={name}
            onClick={() => setPage(name)}
            disabled={name === "work" && !selectedWork}
          >
            {name}
          </button>
        ))}
      </nav>
      <section>
        <label>
          Active account{" "}
          <select
            value={accountId}
            onChange={(event) => {
              setAccountId(event.target.value);
              void refresh(event.target.value);
            }}
          >
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.platform} — {account.username ?? account.id}
              </option>
            ))}
          </select>
        </label>
      </section>
      <section>
        <label>
          Active Vault{" "}
          <select
            value={vaultId}
            onChange={(event) => {
              setVaultId(event.target.value);
              void refreshVault(event.target.value);
            }}
          >
            <option value="">No Vault selected</option>
            {vaults.map((vault) => (
              <option key={vault.vault_id} value={vault.vault_id}>
                {vault.display_name} — {vault.registry_state}
              </option>
            ))}
          </select>
        </label>
      </section>

      {page === "command" && (
        <>
          <section>
            <form onSubmit={capture}>
              <input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Capture work item"
              />
              <button>Capture</button>
            </form>
          </section>
          {center &&
            Object.entries(center.data).map(([name, rows]) => (
              <section key={name}>
                <h2>{name.replaceAll("_", " ")}</h2>
                <ul>
                  {rows.length ? (
                    rows.map((row, index) => (
                      <li key={String(row.id ?? index)}>
                        <button onClick={() => void openWork(String(row.id))}>
                          {String(row.title ?? row.id ?? "record")}
                        </button>
                      </li>
                    ))
                  ) : (
                    <li>None.</li>
                  )}
                </ul>
              </section>
            ))}
        </>
      )}

      {page === "calendar" && (
        <section>
          <h2>90-day calendar</h2>
          <ul>
            {schedule.length ? (
              schedule.map((row) => (
                <li key={row.id}>
                  <button onClick={() => void openWork(row.work_item_id)}>{row.title}</button>
                  {" — "}
                  {row.scheduled_for ?? "Reserve"}
                </li>
              ))
            ) : (
              <li>No scheduled work.</li>
            )}
          </ul>
        </section>
      )}

      {page === "work" && (
        <section>
          <h2>Work detail</h2>
          <button onClick={() => void importEvidence()}>Import evidence file</button>
          <pre>{JSON.stringify(selectedWork, null, 2)}</pre>
        </section>
      )}

      {page === "records" && (
        <section>
          <h2>Records</h2>
          <pre>{JSON.stringify(records, null, 2)}</pre>
        </section>
      )}

      {page === "metrics" && (
        <section>
          <h2>Manual metrics</h2>
          <pre>{JSON.stringify(metrics, null, 2)}</pre>
        </section>
      )}

      {page === "system" && (
        <section>
          <h2>System</h2>
          <pre>{JSON.stringify(system, null, 2)}</pre>
        </section>
      )}

      {page === "vaults" && (
        <>
          <section>
            <h2>Local Manual Vaults</h2>
            <p>Vault selection is independent from platform-account selection.</p>
            <pre>{JSON.stringify(vaultHealth, null, 2)}</pre>
            {vaultHealth?.status === "blocked" && vaultId && (
              <button onClick={() => void migrateSelectedVault()}>
                Run governed Vault migration
              </button>
            )}
            <form onSubmit={createVault}>
              <input
                value={vaultName}
                onChange={(event) => setVaultName(event.target.value)}
                placeholder="Vault display name"
              />
              <input
                value={vaultRoot}
                onChange={(event) => setVaultRoot(event.target.value)}
                placeholder="Relative Vault root"
              />
              <button>Create governed Vault</button>
            </form>
          </section>

          <section>
            <h2>Manual Vault intake</h2>
            <p>
              Retention eligibility is decided before file bytes are uploaded. No parser runs
              in Phase 2.
            </p>
            <form onSubmit={submitVaultIntake}>
              <input
                value={intakeLabel}
                onChange={(event) => setIntakeLabel(event.target.value)}
                placeholder="Observation label"
                required
              />
              <input
                value={intakeLocator}
                onChange={(event) => setIntakeLocator(event.target.value)}
                placeholder="Locator for locator-only intake"
                disabled={selectedVaultFile !== null}
              />
              <input
                type="file"
                onChange={(event) => setSelectedVaultFile(event.target.files?.[0] ?? null)}
              />
              <select
                value={retentionClassification}
                onChange={(event) =>
                  setRetentionClassification(
                    event.target.value as
                      | "preservation_compatible"
                      | "timed_deletion_required"
                      | "unknown",
                  )
                }
              >
                <option value="preservation_compatible">Preservation compatible</option>
                <option value="timed_deletion_required">Timed deletion required</option>
                <option value="unknown">Unknown retention</option>
              </select>
              <input
                value={policyBasis}
                onChange={(event) => setPolicyBasis(event.target.value)}
                placeholder="Policy basis reference"
                required
              />
              <textarea
                value={classificationNote}
                onChange={(event) => setClassificationNote(event.target.value)}
                placeholder="Human classification note"
              />
              <button disabled={!vaultId || vaultHealth?.status !== "healthy"}>
                Record governed intake
              </button>
            </form>
            <p>{vaultOperationStatus}</p>
            <pre>{JSON.stringify(vaultRecords, null, 2)}</pre>
          </section>

          <section>
            <h2>Per-Vault recovery proof</h2>
            <button
              onClick={() => void createAndVerifyVaultBackup()}
              disabled={!vaultId || vaultHealth?.status !== "healthy"}
            >
              Create and verify backup
            </button>
            <pre>{JSON.stringify({ vaultBackup, vaultBackupVerification }, null, 2)}</pre>
          </section>
        </>
      )}

      {page === "release" && (
        <section>
          <h2>Release Watch</h2>
          <p>Unavailable until M09. No watcher or provider is active.</p>
        </section>
      )}

      {page === "library" && (
        <section>
          <h2>Library</h2>
          <p>Unavailable until M12. No article, reply, or asset authority is active.</p>
        </section>
      )}
    </main>
  );
}
