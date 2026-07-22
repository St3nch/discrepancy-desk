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
  VaultHealth,
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
      return;
    }
    setVaultHealth(await desktopClient.vaultHealth(selected));
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
        <section>
          <h2>Local Manual Vaults</h2>
          <p>Vault selection is independent from platform-account selection.</p>
          <pre>{JSON.stringify(vaultHealth, null, 2)}</pre>
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
          <p>No content or parser is admitted by creating a Phase 1 Vault.</p>
        </section>
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
