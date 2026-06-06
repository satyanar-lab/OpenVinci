import { Check, CircleAlert, Hammer, Network, Sigma, TriangleAlert } from "lucide-react";
import type { ProjectRaw, ValidationReport } from "../types";

/**
 * Bottom status bar — the IDE signature this UI was missing.
 * Pixel-thin, full-width, always present. Each segment is a tiny fact
 * about the active project; nothing here triggers async work, the bar
 * is just a denser repeat of what the panels above already show.
 */
export function StatusBar({
  projectName,
  validation,
  validating,
  lastGenStatus,
  project,
  onClickProblems,
}: {
  projectName: string | null;
  validation: ValidationReport | null;
  validating: boolean;
  lastGenStatus: "ok" | "errors" | null;
  project: ProjectRaw | null;
  onClickProblems?: () => void;
}) {
  const errors = validation?.errorCount ?? 0;
  const warnings = validation?.warningCount ?? 0;
  const { pduCount, signalCount, networkCount } = countModel(project);

  return (
    <footer className="statusbar" role="contentinfo" aria-label="status bar">
      <span className="seg" title="active project">
        <Network size={12} aria-hidden />
        <span className="lbl">project</span>
        <span className="val">{projectName ?? "—"}</span>
      </span>

      <ValidationSeg
        validating={validating}
        validation={validation}
        errors={errors}
        warnings={warnings}
        onClick={onClickProblems}
      />

      <span className="seg" title="last generate result">
        <Hammer size={12} aria-hidden />
        <span className="lbl">gen</span>
        <span className="val">
          {lastGenStatus === null ? "—" : lastGenStatus}
        </span>
      </span>

      <span className="spacer" />

      <span className="seg" title="CanIf PDUs (rx + tx) across all networks">
        <Sigma size={12} aria-hidden />
        <span className="lbl">pdus</span>
        <span className="val">{pduCount}</span>
      </span>
      <span className="seg" title="Com signals across all networks">
        <Sigma size={12} aria-hidden />
        <span className="lbl">signals</span>
        <span className="val">{signalCount}</span>
      </span>
      <span className="seg" title="Com + CanIf networks">
        <Sigma size={12} aria-hidden />
        <span className="lbl">nets</span>
        <span className="val">{networkCount}</span>
      </span>
    </footer>
  );
}

function ValidationSeg({
  validating,
  validation,
  errors,
  warnings,
  onClick,
}: {
  validating: boolean;
  validation: ValidationReport | null;
  errors: number;
  warnings: number;
  onClick?: () => void;
}) {
  const clickable = typeof onClick === "function";
  if (validating) {
    return (
      <span className={`seg${clickable ? " clickable" : ""}`} onClick={onClick}>
        <CircleAlert size={12} aria-hidden />
        <span className="lbl">validating…</span>
      </span>
    );
  }
  if (!validation) {
    return (
      <span className={`seg${clickable ? " clickable" : ""}`} onClick={onClick}>
        <span className="lbl">no report</span>
      </span>
    );
  }
  if (errors === 0 && warnings === 0) {
    return (
      <span
        className={`seg${clickable ? " clickable" : ""}`}
        onClick={onClick}
        title="validation clean"
      >
        <Check size={12} aria-hidden />
        <span className="lbl">clean</span>
      </span>
    );
  }
  return (
    <span
      className={`seg${clickable ? " clickable" : ""}`}
      onClick={onClick}
      title="open problems panel"
    >
      {errors > 0 && (
        <>
          <span className="sev-dot err" aria-hidden />
          <CircleAlert size={12} aria-hidden />
          <span className="val">{errors}</span>
        </>
      )}
      {warnings > 0 && (
        <>
          <span className="sev-dot warn" aria-hidden />
          <TriangleAlert size={12} aria-hidden />
          <span className="val">{warnings}</span>
        </>
      )}
    </span>
  );
}

type Counts = { pduCount: number; signalCount: number; networkCount: number };

function countModel(project: ProjectRaw | null): Counts {
  if (!project) return { pduCount: 0, signalCount: 0, networkCount: 0 };

  let pduCount = 0;
  const canifNets = arrField(project.CanIf, "networks");
  for (const net of canifNets) {
    pduCount +=
      arrField(net, "RxPdus").length + arrField(net, "TxPdus").length;
  }

  let signalCount = 0;
  const comNets = arrField(project.Com, "networks");
  const networkNames = new Set<string>();
  for (const net of comNets) {
    if (typeof (net as { name?: unknown }).name === "string") {
      networkNames.add((net as { name: string }).name);
    }
    const messages = arrField(net, "messages");
    for (const msg of messages) {
      signalCount += arrField(msg, "signals").length;
    }
  }
  for (const net of canifNets) {
    if (typeof (net as { name?: unknown }).name === "string") {
      networkNames.add((net as { name: string }).name);
    }
  }

  return { pduCount, signalCount, networkCount: networkNames.size };
}

function arrField(parent: unknown, key: string): unknown[] {
  if (!parent || typeof parent !== "object") return [];
  const v = (parent as Record<string, unknown>)[key];
  return Array.isArray(v) ? v : [];
}
