import { FormEvent, useEffect, useState } from "react";
import { desktopClient } from "./api/client";
import type { CommandCenterResponse, DesktopHealth, OwnedAccount, ScheduleRow, SystemStatus } from "./api/types";

type Page = "command" | "calendar" | "work" | "system";
export default function App() {
  const [page, setPage] = useState<Page>("command");
  const [health, setHealth] = useState<DesktopHealth | null>(null);
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [accounts, setAccounts] = useState<OwnedAccount[]>([]);
  const [accountId, setAccountId] = useState("");
  const [center, setCenter] = useState<CommandCenterResponse | null>(null);
  const [schedule, setSchedule] = useState<ScheduleRow[]>([]);
  const [selectedWork, setSelectedWork] = useState<Record<string, unknown> | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const refresh = async (selected = accountId) => { if (!selected) return; setCenter(await desktopClient.commandCenter(selected)); setSchedule(await desktopClient.schedule(selected)); };
  useEffect(() => { desktopClient.health().then(setHealth).catch((e: Error) => setError(e.message)); desktopClient.system().then(setSystem).catch((e: Error) => setError(e.message)); desktopClient.accounts().then((rows) => { setAccounts(rows); if (rows[0]) { setAccountId(rows[0].id); void refresh(rows[0].id); } }).catch((e: Error) => setError(e.message)); }, []);
  const capture = async (event: FormEvent) => { event.preventDefault(); if (!title.trim()) return; try { const result = await desktopClient.capture(title.trim()); setTitle(""); await refresh(); setSelectedWork(await desktopClient.workItem(result.work_item_id)); setPage("work"); } catch (e) { setError(e instanceof Error ? e.message : "Capture refused"); } };
  const openWork = async (id: string) => { setSelectedWork(await desktopClient.workItem(id)); setPage("work"); };
  return <main><header><p>B1-L7 CONTROL ROOM</p><h1>The Discrepancy Desk</h1><p>{health ? `Backend ${health.status} · API v${health.api_version} · DB ${health.migration}` : error ?? "Starting governed backend…"}</p></header><nav>{(["command","calendar","work","system"] as Page[]).map((name) => <button key={name} onClick={() => setPage(name)} disabled={name === "work" && !selectedWork}>{name}</button>)}<button disabled>Metrics</button></nav><section><label>Active account <select value={accountId} onChange={(e) => { setAccountId(e.target.value); void refresh(e.target.value); }}>{accounts.map((a) => <option key={a.id} value={a.id}>{a.platform} — {a.username ?? a.id}</option>)}</select></label></section>{page === "command" && <><section><form onSubmit={capture}><input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Capture work item"/><button>Capture</button></form></section>{center && Object.entries(center.data).map(([name, rows]) => <section key={name}><h2>{name.replaceAll("_", " ")}</h2><ul>{rows.length ? rows.map((row, index) => <li key={String(row.id ?? index)}><button onClick={() => void openWork(String(row.id))}>{String(row.title ?? row.id ?? "record")}</button></li>) : <li>None.</li>}</ul></section>)}</>}{page === "calendar" && <section><h2>90-day calendar</h2><ul>{schedule.length ? schedule.map((row) => <li key={row.id}><button onClick={() => void openWork(row.work_item_id)}>{row.title}</button> — {row.scheduled_for ?? "Reserve"}</li>) : <li>No scheduled work.</li>}</ul></section>}{page === "work" && <section><h2>Work detail</h2><pre>{JSON.stringify(selectedWork, null, 2)}</pre></section>}{page === "system" && <section><h2>System</h2><pre>{JSON.stringify(system, null, 2)}</pre></section>}</main>;
}
