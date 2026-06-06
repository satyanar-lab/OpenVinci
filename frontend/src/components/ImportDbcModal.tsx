import { useEffect, useRef, useState } from "react";
import { importDbc, importDbcUpload, listDbcs } from "../api";
import type { DbcImportResponse } from "../types";
import { Modal } from "./Modal";

type Source =
  | { kind: "bundled"; path: string }
  | { kind: "upload"; file: File };

export function ImportDbcModal({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: (r: DbcImportResponse) => void;
}) {
  const [dbcs, setDbcs] = useState<string[]>([]);
  const [bundled, setBundled] = useState<string>("");
  const [upload, setUpload] = useState<File | null>(null);
  const [network, setNetwork] = useState<string>("CAN0");
  const [me, setMe] = useState<string>("AS");
  const [busy, setBusy] = useState<boolean>(false);
  const [dragging, setDragging] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    listDbcs()
      .then((list) => {
        setDbcs(list);
        if (list.length > 0) setBundled(list[0]);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  function pickedSource(): Source | null {
    if (upload) return { kind: "upload", file: upload };
    if (bundled) return { kind: "bundled", path: bundled };
    return null;
  }

  function acceptFile(f: File | null | undefined) {
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".dbc")) {
      setError(`not a .dbc file: ${f.name}`);
      return;
    }
    setError(null);
    setUpload(f);
  }

  async function run() {
    const source = pickedSource();
    if (!source) return;
    setBusy(true);
    setError(null);
    try {
      const result =
        source.kind === "upload"
          ? await importDbcUpload(source.file, network, me)
          : await importDbc(source.path, network, me);
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

      <div
        className={`dropzone ${dragging ? "dragging" : ""} ${upload ? "filled" : ""}`}
        data-testid="dbc-dropzone"
        onDragEnter={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          acceptFile(e.dataTransfer.files?.[0]);
        }}
        onClick={() => fileInput.current?.click()}
        role="button"
        tabIndex={0}
        aria-label="drop a .dbc file or click to browse"
      >
        <input
          ref={fileInput}
          type="file"
          accept=".dbc"
          style={{ display: "none" }}
          onChange={(e) => acceptFile(e.target.files?.[0])}
          aria-label="dbc file input"
        />
        {upload ? (
          <>
            <strong>{upload.name}</strong>
            <span className="dim">
              {" "}
              · {Math.round(upload.size / 102.4) / 10} KB
            </span>
            <button
              className="link small"
              onClick={(e) => {
                e.stopPropagation();
                setUpload(null);
                if (fileInput.current) fileInput.current.value = "";
              }}
            >
              clear
            </button>
          </>
        ) : (
          <>
            <strong>Drop a .dbc here</strong>
            <span className="dim"> or click to browse</span>
          </>
        )}
      </div>

      <details className="bundled-picker">
        <summary>…or use a bundled sample</summary>
        <table className="form">
          <tbody>
            <tr>
              <th>DBC file</th>
              <td>
                <select
                  value={bundled}
                  onChange={(e) => {
                    setBundled(e.target.value);
                    setUpload(null);
                  }}
                  disabled={!!upload}
                >
                  {dbcs.length === 0 && <option value="">— none found —</option>}
                  {dbcs.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </td>
            </tr>
          </tbody>
        </table>
      </details>

      <table className="form">
        <tbody>
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
        <button onClick={onClose} className="link">
          Cancel
        </button>
        <button
          onClick={run}
          className="primary"
          disabled={busy || !pickedSource()}
        >
          {busy ? "Importing…" : "Import"}
        </button>
      </div>
    </Modal>
  );
}
