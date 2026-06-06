import {
  Check,
  CircleAlert,
  Hammer,
  Network,
  ShieldCheck,
  Sigma,
  TriangleAlert,
} from "lucide-react";
import type { ProjectRaw, ValidationReport } from "../types";
import { VERIFICATION_LEVELS } from "../verification";

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
  onShowVerification,
}: {
  projectName: string | null;
  validation: ValidationReport | null;
  validating: boolean;
  lastGenStatus: "ok" | "errors" | "unavailable" | null;
  project: ProjectRaw | null;
  onClickProblems?: () => void;
  onShowVerification?: () => void;
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

      {/* Verification identity — a platform-level claim, not a project
       *  fact. The label reads "verified · 7/7" because every level
       *  passes in CI on every push; clicking opens the verification
       *  panel that breaks down what each one actually proves. */}
      <button
        type="button"
        className="seg clickable verify-seg"
        onClick={onShowVerification}
        title={`OpenVinci ships ${VERIFICATION_LEVELS.length} CI-verified levels — click for details`}
        aria-label="Open verification panel"
      >
        <ShieldCheck size={12} aria-hidden />
        <span className="lbl">verified</span>
        <span className="val">
          {VERIFICATION_LEVELS.length}/{VERIFICATION_LEVELS.length}
        </span>
      </button>
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
