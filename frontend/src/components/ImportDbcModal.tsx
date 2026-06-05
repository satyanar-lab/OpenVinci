import { useEffect, useState } from "react";
import { importDbc, listDbcs } from "../api";
import type { DbcImportResponse } from "../types";
import { Modal } from "./Modal";

export function ImportDbcModal({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: (r: DbcImportResponse) => void;
}) {
  const [dbcs, setDbcs] = useState<string[]>([]);
  const [path, setPath] = useState<string>("");
  const [network, setNetwork] = useState<string>("CAN0");
  const [me, setMe] = useState<string>("AS");
  const [busy, setBusy] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listDbcs()
      .then((list) => {
        setDbcs(list);
        if (list.length > 0) setPath(list[0]);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  async function run() {
    if (!path) return;
    setBusy(true);
    setError(null);
    try {
      const result = await importDbc(path, network, me);
      onImported(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Import DBC" onClose={onClose}>
      <p className="hint">
        Parse a CAN .dbc, map messages to Com IPDUs+signals, then auto-wire
        PduR / CanIf / Can. The current project is replaced.
      </p>
      <table className="form">
        <tbody>
          <tr>
            <th>DBC file</th>
            <td>
              <select value={path} onChange={(e) => setPath(e.target.value)}>
                {dbcs.length === 0 && <option value="">— none found —</option>}
                {dbcs.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
              <div className="hint small">
                Bundled samples live under <code>examples/dbc/</code>.
              </div>
            </td>
          </tr>
          <tr>
            <th>Network</th>
            <td>
              <input
                type="text"
                value={network}
                onChange={(e) => setNetwork(e.target.value)}
              />
            </td>
          </tr>
          <tr>
            <th>Self node (me)</th>
            <td>
              <input
                type="text"
                value={me}
                onChange={(e) => setMe(e.target.value)}
              />
            </td>
          </tr>
        </tbody>
      </table>
      {error && <pre className="error">{error}</pre>}
      <div className="modal-footer">
        <button onClick={onClose} className="link">Cancel</button>
        <button onClick={run} className="primary" disabled={busy || !path}>
          {busy ? "Importing…" : "Import"}
        </button>
      </div>
    </Modal>
  );
}
