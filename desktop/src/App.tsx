import { useEffect, useState } from "react";
import { desktopClient } from "./api/client";
import type { DesktopHealth } from "./api/types";

export default function App() {
  const [health, setHealth] = useState<DesktopHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    desktopClient.health().then(setHealth).catch((value: unknown) => {
      setError(value instanceof Error ? value.message : "Backend unavailable");
    });
  }, []);
  return <main><header><p>B1-L7 CONTROL ROOM</p><h1>The Discrepancy Desk</h1></header><section><h2>Desktop foundation</h2>{health ? <p>Backend {health.status} · API v{health.api_version} · DB {health.migration}</p> : <p>{error ?? "Starting governed backend…"}</p>}<p>The M04 web harness remains the authority regression surface while desktop parity is built.</p></section></main>;
}
