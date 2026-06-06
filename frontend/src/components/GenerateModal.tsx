import { useEffect, useState } from "react";
import {
  Check,
  CircleAlert,
  Download,
  FileCode,
  FolderOpen,
  Hammer,
  Loader,
  Play,
  Terminal,
  TriangleAlert,
} from "lucide-react";
import { generate, generateZip } from "../api";
import type { CompileMessage, GenerateResponse, ProjectRaw, Severity } from "../types";
import { Modal } from "./Modal";
import { unzipStored, type UnzipEntry } from "../unzipStored";

type Phase = "running" | "ok" | "errors" | "failed";

export function GenerateModal({
  project,
  sourceProject,
  onClose,
  onComplete,
}: {
  project: ProjectRaw;
  sourceProject: string | undefined;
  onClose: () => void;
  onComplete?: (status: "ok" | "errors") => void;
}) {
  const [busy, setBusy] = useState<boolean>(true);
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    generate(project, sourceProject)
      .then((r) => {
        setResult(r);
        const status = r.compileResult?.status;
        if (status === "ok" || status === "errors") {
          onComplete?.(status);
        }
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
    // we intentionally don't re-run on changes — the modal is one shot
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const cr = result?.compileResult;
  const phase: Phase = error
    ? "failed"
    : busy
      ? "running"
      : cr?.status === "ok"
        ? "ok"
        : cr?.status === "errors"
          ? "errors"
          : "ok";

  const errorCount = cr?.messages.filter((m) => m.severity === "error").length ?? 0;
  const warningCount =
    cr?.messages.filter((m) => m.severity === "warning").length ?? 0;

  return (
    <Modal
      title="Generate + compile"
      icon={<Hammer size={14} aria-hidden />}
      onClose={onClose}
    >
      <BuildBanner phase={phase} errorCount={errorCount} warningCount={warningCount} />

      <p className="hint">
        Stages the project to a workdir, runs the upstream generators, then
        <code> gcc -c -fsyntax-only</code> every <code>*_Cfg.c</code> against
        <code> vendor/as</code>'s BSW headers.
      </p>

      {error && (
        <pre className="error">{error}</pre>
      )}

      {result && (
        <>
          <FilesSection result={result} />
          <DiagnosticsSection cr={cr} />
          {cr?.command && <CommandPreview command={cr.command} />}
        </>
      )}

      <div className="modal-footer">
        <DownloadActions
          project={project}
          sourceProject={sourceProject}
          result={result}
          phase={phase}
        />
        <button onClick={onClose} className="primary">
          Close
        </button>
      </div>
    </Modal>
  );
}

// --- Download / save-to-folder actions --------------------------------

type SavePhase = "idle" | "downloading" | "saving" | "done" | "error";

function DownloadActions({
  project,
  sourceProject,
  result,
  phase,
}: {
  project: ProjectRaw;
  sourceProject: string | undefined;
  result: GenerateResponse | null;
  phase: Phase;
}) {
  const [save, setSave] = useState<SavePhase>("idle");
  const [savedFolder, setSavedFolder] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Don't offer retrieval when generation never produced files. Compile
  // errors with non-empty files (a partial build the user may still
  // want) are fine — that's what "errors" phase means.
  const hideForFailure = phase === "running" || phase === "failed";
  const noFiles = !result || result.files.length === 0;
  if (hideForFailure || noFiles) return null;

  const hasDirPicker =
    typeof window !== "undefined" &&
    typeof (window as unknown as { showDirectoryPicker?: unknown })
      .showDirectoryPicker === "function";

  async function onDownload() {
    setSave("downloading");
    setSaveError(null);
    try {
      const { blob, filename } = await generateZip(project, sourceProject);
      triggerBrowserDownload(blob, filename);
      setSave("done");
    } catch (e) {
      setSave("error");
      setSaveError((e as Error).message);
    }
  }

  async function onSaveToFolder() {
    setSave("saving");
    setSaveError(null);
    setSavedFolder(null);
    try {
      // `as unknown as` because the File System Access API types ship
      // under @types/wicg-file-system-access — not in our deps. The
      // call is guarded by the hasDirPicker check above.
      const w = window as unknown as {
        showDirectoryPicker: (opts?: {
          mode?: "read" | "readwrite";
        }) => Promise<DirectoryHandle>;
      };
      const dirHandle = await w.showDirectoryPicker({ mode: "readwrite" });
      const { blob } = await generateZip(project, sourceProject);
      const entries = await unzipStored(blob);
      await writeEntriesToDirectory(dirHandle, entries);
      setSavedFolder(dirHandle.name);
      setSave("done");
    } catch (e) {
      // AbortError = user cancelled the picker — silently reset.
      if ((e as { name?: string })?.name === "AbortError") {
        setSave("idle");
        return;
      }
      setSave("error");
      setSaveError((e as Error).message);
    }
  }

  return (
    <div className="download-actions">
      {save === "done" && savedFolder && (
        <span className="hint small">
          <Check size={11} aria-hidden /> wrote to <code>{savedFolder}</code>
        </span>
      )}
      {save === "done" && !savedFolder && (
        <span className="hint small">
          <Check size={11} aria-hidden /> download started
        </span>
      )}
      {save === "error" && saveError && (
        <span className="hint small download-error" title={saveError}>
          <CircleAlert size={11} aria-hidden /> {saveError.slice(0, 64)}
        </span>
      )}
      {hasDirPicker && (
        <button
          type="button"
          onClick={onSaveToFolder}
          disabled={save === "saving" || save === "downloading"}
          title="Pick a folder and write the generated files individually"
        >
          <FolderOpen size={14} aria-hidden />
          <span className="lbl">
            {save === "saving" ? "Saving…" : "Save to folder…"}
          </span>
        </button>
      )}
      <button
        type="button"
        className="primary"
        onClick={onDownload}
        disabled={save === "downloading" || save === "saving"}
        title="Download a .zip containing every generated file"
      >
        <Download size={14} aria-hidden />
        <span className="lbl">
          {save === "downloading" ? "Preparing…" : "Download .zip"}
        </span>
      </button>
    </div>
  );
}

function triggerBrowserDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  // Defer revoke + remove so Firefox has a chance to start the
  // download. 0 ms tick is enough — the click is synchronous here.
  setTimeout(() => {
    a.remove();
    URL.revokeObjectURL(url);
  }, 0);
}

// File System Access API — only the bits we actually call. Avoids
// pulling @types/wicg-file-system-access into the dev deps.
type DirectoryHandle = {
  name: string;
  getDirectoryHandle: (
    name: string,
    opts?: { create?: boolean },
  ) => Promise<DirectoryHandle>;
  getFileHandle: (
    name: string,
    opts?: { create?: boolean },
  ) => Promise<FileHandle>;
};
type FileHandle = {
  createWritable: () => Promise<WritableStream<Uint8Array>>;
};

async function writeEntriesToDirectory(
  root: DirectoryHandle,
  entries: UnzipEntry[],
): Promise<void> {
  for (const entry of entries) {
    const segments = entry.path.split("/").filter(Boolean);
    if (segments.length === 0) continue;
    const fileName = segments.pop()!;
    let dir = root;
    for (const seg of segments) {
      dir = await dir.getDirectoryHandle(seg, { create: true });
    }
    const fh = await dir.getFileHandle(fileName, { create: true });
    const ws = await fh.createWritable();
    const writer = ws.getWriter();
    await writer.write(entry.content);
    await writer.close();
  }
}

// --- Status banner ---------------------------------------------------

function BuildBanner({
  phase,
  errorCount,
  warningCount,
}: {
  phase: Phase;
  errorCount: number;
  warningCount: number;
}) {
  const meta: Record<Phase, { icon: JSX.Element; label: string; tone: string }> = {
    running: {
      icon: <Loader size={14} aria-hidden className="spin" />,
      label: "running",
      tone: "running",
    },
    ok: {
      icon: <Check size={14} aria-hidden />,
      label: "clean build",
      tone: "ok",
    },
    errors: {
      icon: <CircleAlert size={14} aria-hidden />,
      label: "compile errors",
      tone: "errors",
    },
    failed: {
      icon: <CircleAlert size={14} aria-hidden />,
      label: "generate failed",
      tone: "errors",
    },
  };
  const m = meta[phase];
  return (
    <div className={`build-banner tone-${m.tone}`}>
      <span className="build-pill">
        {m.icon}
        <span>{m.label}</span>
      </span>
      <span className="build-counts">
        {errorCount > 0 && (
          <span className="badge err">
            <CircleAlert size={11} aria-hidden /> {errorCount}
          </span>
        )}
        {warningCount > 0 && (
          <span className="badge warn">
            <TriangleAlert size={11} aria-hidden /> {warningCount}
          </span>
        )}
        {phase === "ok" && (
          <span className="badge ok">
            <Check size={11} aria-hidden /> no diagnostics
          </span>
        )}
      </span>
    </div>
  );
}

// --- Files section ----------------------------------------------------

function FilesSection({ result }: { result: GenerateResponse }) {
  return (
    <details className="gen-section" open>
      <summary>
        <FileCode size={12} aria-hidden />
        <span>Generated files</span>
        <span className="gen-section-count">{result.files.length}</span>
      </summary>
      <table className="files">
        <thead>
          <tr>
            <th>path</th>
            <th className="col-module">module</th>
            <th className="col-size">size</th>
          </tr>
        </thead>
        <tbody>
          {result.files.map((f) => (
            <tr key={f.path}>
              <td className="path mono">{f.path}</td>
              <td className="col-module">{f.module}</td>
              <td className="col-size mono">{formatBytes(f.size_bytes)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

// --- Diagnostics section ---------------------------------------------

function DiagnosticsSection({
  cr,
}: {
  cr: GenerateResponse["compileResult"] | undefined;
}) {
  const messages = cr?.messages ?? [];
  return (
    <details className="gen-section" open={(cr?.status ?? "ok") === "errors"}>
      <summary>
        <Play size={12} aria-hidden />
        <span>Compiler output</span>
        <span className="gen-section-count">{messages.length}</span>
      </summary>
      {messages.length === 0 ? (
        <p className="hint mono build-log-empty">
          <Check size={12} aria-hidden /> clean — no warnings, no errors.
        </p>
      ) : (
        <ul className="build-log">
          {messages.map((m, i) => (
            <BuildLogLine key={i} message={m} />
          ))}
        </ul>
      )}
    </details>
  );
}

function BuildLogLine({ message }: { message: CompileMessage }) {
  return (
    <li className={`build-log-line sev-${message.severity}`}>
      <SeverityGlyph severity={message.severity} />
      <span className="loc">
        {message.file}
        {message.line != null ? `:${message.line}` : ""}
        {message.column != null ? `:${message.column}` : ""}
      </span>
      <span className="sev">{message.severity}:</span>
      <span className="msg">{message.message}</span>
    </li>
  );
}

function SeverityGlyph({ severity }: { severity: Severity }) {
  if (severity === "error")
    return <CircleAlert size={12} aria-hidden className="glyph" />;
  if (severity === "warning")
    return <TriangleAlert size={12} aria-hidden className="glyph" />;
  return <Check size={12} aria-hidden className="glyph" />;
}

// --- Command preview --------------------------------------------------

function CommandPreview({ command }: { command: string[] }) {
  return (
    <details className="gen-section">
      <summary>
        <Terminal size={12} aria-hidden />
        <span>Compile command</span>
      </summary>
      <pre className="build-cmd mono">{command.join(" ")}</pre>
    </details>
  );
}

// --- Helpers ---------------------------------------------------------

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
