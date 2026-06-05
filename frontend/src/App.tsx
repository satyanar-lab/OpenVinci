import { useEffect, useState } from "react";
import { fetchConfig, type ConfigResponse } from "./api";

export function App() {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchConfig("Com").then(setConfig).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "1.5rem", maxWidth: 960 }}>
      <h1>OpenVinci</h1>
      <p>Configurator for the AUTOSAR Classic COM stack, built on autoas/as.</p>
      <h2>Loaded config</h2>
      {error && <pre style={{ color: "crimson" }}>{error}</pre>}
      {!error && !config && <p>Loading…</p>}
      {config && (
        <>
          <p>
            <strong>{config.module}</strong> from <code>{config.source}</code>
          </p>
          <pre
            style={{
              background: "#f5f5f5",
              padding: "1rem",
              border: "1px solid #ddd",
              borderRadius: 4,
              maxHeight: 500,
              overflow: "auto",
            }}
          >
            {JSON.stringify(config.data, null, 2)}
          </pre>
        </>
      )}
    </main>
  );
}
