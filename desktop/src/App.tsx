import { FormEvent, useEffect, useState } from "react";
import { desktopClient } from "./api/client";
import type { CommandCenterResponse, DesktopHealth, OwnedAccount } from "./api/types";

export default function App() {
  const [health, setHealth] = useState<DesktopHealth | null>(null);
  const [accounts, setAccounts] = useState<OwnedAccount[]>([]);
  const [accountId, setAccountId] = useState("");
  const [center, setCenter] = useState<CommandCenterResponse | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const refresh = async (selected = accountId) => { if (selected) setCenter(await desktopClient.commandCenter(selected)); };
  useEffect(() => { desktopClient.health().then(setHealth).catch((e: Error) => setError(e.message)); desktopClient.accounts().then((rows) => { setAccounts(rows); if (rows[0]) { setAccountId(rows[0].id); void refresh(rows[0].id); } }).catch((e: Error) => setError(e.message)); }, []);
  const capture = async (event: FormEvent) => { event.preventDefault(); if (!title.trim()) return; try { await desktopClient.capture(title.trim()); setTitle(""); await refresh(); } catch (e) { setError(e instanceof Error ? e.message : "Capture refused"); } };
  return <main><header><p>B1-L7 CONTROL ROOM</p><h1>The Discrepancy Desk</h1><p>{health ? `Backend ${health.status} · API v${health.api_version} · DB ${health.migration}` : error ?? "Starting governed backend…"}</p></header><nav><button>Command Center</button><button disabled>Calendar</button><button disabled>Work</button><button disabled>Metrics</button><button disabled>System</button></nav><section><label>Active account <select value={accountId} onChange={(e) => { setAccountId(e.target.value); void refresh(e.target.value); }}>{accounts.map((a) => <option key={a.id} value={a.id}>{a.platform} — {a.username ?? a.id}</option>)}</select></label><form onSubmit={capture}><input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Capture work item"/><button>Capture</button></form></section>{center && Object.entries(center.data).map(([name, rows]) => <section key={name}><h2>{name.replaceAll("_", " ")}</h2><ul>{rows.length ? rows.map((row, index) => <li key={String(row.id ?? index)}>{String(row.title ?? row.id ?? "record")}</li>) : <li>None.</li>}</ul></section>)}</main>;
}
