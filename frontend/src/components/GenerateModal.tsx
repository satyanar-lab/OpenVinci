import { useEffect, useState } from "react";
import { generate } from "../api";
import type { GenerateResponse, ProjectRaw } from "../types";
import { Modal } from "./Modal";

export function GenerateModal({
  project,
  sourceProject,
  onClose,
}: {
  project: ProjectRaw;
  sourceProject: string | undefined;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState<boolean>(true);
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    generate(project, sourceProject)
      .then(setResult)
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
    // we intentionally don't re-run on changes — the modal is one shot
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const cr = result?.compileResult;
  const status = cr?.status ?? (busy ? "running" : "—");

  return (
    <Modal title="Generate + compile" onClose={onClose}>
      <p className="hint">
        Stages the project to a workdir, runs the upstream generators,
        then <code>gcc -c -fsyntax-only</code>s every <code>*_Cfg.c</code>
        against <code>vendor/as</code>'s BSW headers.
      </p>
      <div className="gen-summary">
        <span
          className={`status status-${status}`}
          data-testid="generate-status"
        >
          {status}
        </span>
        {cr && (
          <span className="counts">
            {cr.messages.filter((m) => m.severity === "error").length} errors,{" "}
            {cr.messages.filter((m) => m.severity === "warning").length} warnings
          </span>
        )}
      </div>
      {error && <pre className="error">{error}</pre>}
      {result && (
        <div className="gen-result">
          <details open>
            <summary>{result.files.length} generated files</summary>
            <table className="files">
              <thead>
                <tr>
                  <th>path</th>
                  <th>module</th>
                  <th>size</th>
                </tr>
              </thead>
              <tbody>
                {result.files.map((f) => (
                  <tr key={f.path}>
                    <td>
                      <code>{f.path}</code>
                    </td>
                    <td>{f.module}</td>
                    <td>{f.size_bytes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
          <details open={cr?.status === "errors"}>
            <summary>
              {cr?.messages.length ?? 0} compile message(s)
            </summary>
            {cr && cr.messages.length > 0 ? (
              <ul className="diag">
                {cr.messages.map((m, i) => (
                  <li key={i} className={`severity-${m.severity}`}>
                    <span className="loc">
                      {m.file}:{m.line ?? "?"}
                    </span>
                    <span className="msg">
                      {m.severity}: {m.message}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="hint">Clean build — no warnings, no errors.</p>
            )}
          </details>
        </div>
      )}
      <div className="modal-footer">
        <button onClick={onClose} className="primary">
          Close
        </button>
      </div>
    </Modal>
  );
}
