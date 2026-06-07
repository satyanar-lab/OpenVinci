import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CircleAlert,
  Moon,
  Network,
  Play,
  Sun,
  Upload,
  Wrench,
} from "lucide-react";
import {
  applyFix,
  fetchSchemas,
  getProject,
  listProjects,
  validateProject,
} from "./api";
import type { Target } from "./api";
import { Breadcrumb } from "./components/Breadcrumb";
import { Editor } from "./components/Editor";
import { GenerateModal } from "./components/GenerateModal";
import { ImportDbcModal } from "./components/ImportDbcModal";
import { ProblemsPanel } from "./components/ProblemsPanel";
import {
  EditorSkeleton,
  NoProjectEmpty,
  TreeSkeleton,
} from "./components/Skeleton";
import { StatusBar } from "./components/StatusBar";
import { Tree } from "./components/Tree";
import { VerificationPanel } from "./components/VerificationPanel";
import type {
  Issue,
  ProjectRaw,
  SchemaBundle,
  TreeNode,
  ValidationReport,
} from "./types";
import { buildTree, findNodeById } from "./treeModel";
import { rollupIssues } from "./validationRollup";

type Theme = "light" | "dark";

export function App() {
  const [schemas, setSchemas] = useState<SchemaBundle | null>(null);
  const [projects, setProjects] = useState<string[]>([]);
  const [projectName, setProjectName] = useState<string | null>(null);
  const [sourceProject, setSourceProject] = useState<string | undefined>(undefined);
  const [project, setProject] = useState<ProjectRaw | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [validation, setValidation] = useState<ValidationReport | null>(null);
  const [validating, setValidating] = useState<boolean>(false);
  const [showImport, setShowImport] = useState<boolean>(false);
  const [showGenerate, setShowGenerate] = useState<boolean>(false);
  const [showVerification, setShowVerification] = useState<boolean>(false);
  const [lastGenStatus, setLastGenStatus] = useState<
    "ok" | "errors" | "unavailable" | null
  >(null);
  const [theme, setTheme] = useState<Theme>("light");
  const [error, setError] = useState<string | null>(null);
  // PROMPT C5: which board the user wants to generate against. "host"
  // keeps the existing JSON-files behaviour; "stm32h753zi" routes
  // /api/generate/zip to the full-firmware export.
  const [target, setTarget] = useState<Target>("host");

  // Apply theme to <html data-theme> so the CSS variables pick it up.
  // Persisting across sessions would need localStorage — not used here
  // per the environment constraint; theme resets to light on reload.
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  // Bootstrap: fetch schemas + project list + initial project (com-minimal).
  useEffect(() => {
    Promise.all([fetchSchemas(), listProjects()])
      .then(([s, list]) => {
        setSchemas(s);
        setProjects(list);
        const initial = list.includes("com-minimal") ? "com-minimal" : list[0];
        if (initial) loadProject(initial);
      })
      .catch((e: Error) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadProject(name: string) {
    try {
      const r = await getProject(name);
      setProjectName(name);
      setSourceProject(name);
      setProject(r.project);
      setSelectedId(null);
      setLastGenStatus(null);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  // Re-validate whenever the project changes. Debounced lightly so the
  // user can type into a field without spamming the backend.
  const validationGen = useRef(0);
  const revalidate = useCallback(async (p: ProjectRaw) => {
    const gen = ++validationGen.current;
    setValidating(true);
    try {
      const report = await validateProject(p);
      if (gen === validationGen.current) setValidation(report);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      if (gen === validationGen.current) setValidating(false);
    }
  }, []);

  useEffect(() => {
    if (!project) return;
    const handle = window.setTimeout(() => void revalidate(project), 200);
    return () => window.clearTimeout(handle);
  }, [project, revalidate]);

  const tree = useMemo(() => (project ? buildTree(project) : []), [project]);
  const selectedNode = useMemo(
    () => (selectedId ? findNodeById(tree, selectedId) : null),
    [tree, selectedId],
  );
  const issueRollup = useMemo(
    () => rollupIssues(tree, validation?.issues ?? []),
    [tree, validation],
  );

  function selectIssue(issue: Issue) {
    if (!project) return;
    let candidateId: string | null = issue.module;
    const path = [...issue.path];
    while (path.length > 0) {
      const id = `${issue.module}/${path.join("/")}`;
      if (findNodeById(tree, id)) {
        candidateId = id;
        break;
      }
      path.pop();
    }
    setSelectedId(candidateId);
  }

  async function handleApplyFix(issue: Issue) {
    if (!project || !issue.fix) return;
    try {
      const r = await applyFix(project, issue.fix);
      setProject(r.project);
      setValidation(r.validation);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="app">
      <TopBar
        projectName={projectName}
        projects={projects}
        onSelectProject={loadProject}
        onImport={() => setShowImport(true)}
        onGenerate={() => setShowGenerate(true)}
        onValidate={() => project && void revalidate(project)}
        canGenerate={!!project}
        canValidate={!!project}
        validating={validating}
        theme={theme}
        onToggleTheme={() => setTheme(theme === "light" ? "dark" : "light")}
        tree={tree}
        selectedId={selectedId}
        target={target}
        onTargetChange={setTarget}
        project={project}
      />

      {error && (
        <div className="banner error" onClick={() => setError(null)}>
          {error} <span className="dim">(click to dismiss)</span>
        </div>
      )}

      <div className="main">
        <aside className="left">
          {schemas && project ? (
            <Tree
              nodes={tree}
              selectedId={selectedId}
              onSelect={(n: TreeNode) => setSelectedId(n.id)}
              rollup={issueRollup}
            />
          ) : (
            <TreeSkeleton />
          )}
        </aside>
        <section className="center">
          {schemas && project ? (
            <Editor
              node={selectedNode}
              project={project}
              schemas={schemas}
              validation={validation}
              onChange={setProject}
            />
          ) : schemas ? (
            <NoProjectEmpty
              onImport={() => setShowImport(true)}
              hasProjects={projects.length > 0}
            />
          ) : (
            <EditorSkeleton />
          )}
        </section>
      </div>

      <ProblemsPanel
        issues={validation?.issues ?? []}
        loading={validating}
        onApplyFix={handleApplyFix}
        onSelect={selectIssue}
      />

      <StatusBar
        projectName={projectName}
        validation={validation}
        validating={validating}
        lastGenStatus={lastGenStatus}
        project={project}
        onShowVerification={() => setShowVerification(true)}
      />

      {showImport && (
        <ImportDbcModal
          onClose={() => setShowImport(false)}
          onImported={(r) => {
            setProject(r.project);
            setProjectName(`dbc:${r.source}`);
            setSourceProject(undefined);
            setSelectedId(null);
            setShowImport(false);
            setValidation(r.validation);
          }}
        />
      )}

      {showGenerate && project && (
        <GenerateModal
          project={project}
          sourceProject={sourceProject}
          target={target}
          onClose={() => setShowGenerate(false)}
          onComplete={(status) => setLastGenStatus(status)}
        />
      )}

      {showVerification && (
        <VerificationPanel onClose={() => setShowVerification(false)} />
      )}
    </div>
  );
}

// --- TopBar ----------------------------------------------------------

function TopBar({
  projectName,
  projects,
  onSelectProject,
  onImport,
  onGenerate,
  onValidate,
  canGenerate,
  canValidate,
  validating,
  theme,
  onToggleTheme,
  tree,
  selectedId,
  target,
  onTargetChange,
  project,
}: {
  projectName: string | null;
  projects: string[];
  onSelectProject: (name: string) => void;
  onImport: () => void;
  onGenerate: () => void;
  onValidate: () => void;
  canGenerate: boolean;
  canValidate: boolean;
  validating: boolean;
  theme: Theme;
  onToggleTheme: () => void;
  tree: TreeNode[];
  selectedId: string | null;
  target: Target;
  onTargetChange: (t: Target) => void;
  project: ProjectRaw | null;
}) {
  // Pull board-options data from the project's Com config. Only used
  // when target === "stm32h753zi" — the host path doesn't display
  // these. baudrate / FD detection comes straight from the model so
  // edits in the Editor flow through automatically.
  const boardOpts = describeBoardOptions(project);
  return (
    <header className="topbar">
      <div className="group">
        <span className="brand">
          <Network size={14} className="logo-mark" aria-hidden />
          <span>OpenVinci</span>
        </span>
      </div>

      <div className="group project-picker">
        <label htmlFor="project-select">project</label>
        <select
          id="project-select"
          value={projectName ?? ""}
          onChange={(e) => onSelectProject(e.target.value)}
          aria-label="project"
        >
          {projects.length === 0 && <option value="">— loading —</option>}
          {projects.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </div>

      <div className="group target-picker" data-testid="target-picker">
        <label htmlFor="target-select">target</label>
        <select
          id="target-select"
          value={target}
          onChange={(e) => onTargetChange(e.target.value as Target)}
          aria-label="board target"
        >
          <option value="host">Host (simulation)</option>
          <option value="stm32h753zi">STM32H753ZI</option>
        </select>
        {target === "stm32h753zi" && boardOpts && (
          <span
            className="board-options"
            data-testid="board-options"
            title="Bit-timing is computed from these at generate time."
          >
            <span className="board-opt">
              kernel <strong>80 MHz</strong>
            </span>
            <span className="board-opt">
              baud <strong>{boardOpts.baud}</strong>
            </span>
            {boardOpts.fd && (
              <span className="board-opt board-fd">
                FD <strong>data {boardOpts.dataBaud}</strong>
              </span>
            )}
          </span>
        )}
      </div>

      <div className="group">
        <button
          className="toolbar-btn"
          onClick={onImport}
          title="Import DBC into a new project"
        >
          <Upload size={14} aria-hidden />
          <span className="lbl">Import DBC</span>
        </button>
        <button
          className="toolbar-btn"
          onClick={onValidate}
          disabled={!canValidate || validating}
          title="Re-run engine validation"
        >
          {validating ? (
            <CircleAlert size={14} aria-hidden />
          ) : (
            <Wrench size={14} aria-hidden />
          )}
          <span className="lbl">Validate</span>
        </button>
        <button
          className="toolbar-btn primary"
          onClick={onGenerate}
          disabled={!canGenerate}
          title="Generate + compile-check the project"
        >
          <Play size={14} aria-hidden />
          <span className="lbl">Generate</span>
        </button>
      </div>

      <Breadcrumb tree={tree} selectedId={selectedId} />

      <div className="group">
        <button
          className="toolbar-btn theme-toggle"
          onClick={onToggleTheme}
          title={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
          aria-label="toggle theme"
        >
          {theme === "light" ? (
            <Moon size={14} aria-hidden />
          ) : (
            <Sun size={14} aria-hidden />
          )}
        </button>
      </div>
    </header>
  );
}

// --- Board-options summary -------------------------------------------

/**
 * Pull a kbit/s string and FD-data-rate from the first Com network in
 * the project. The H7 generator already reads baudrate from
 * Com.networks[0]; surfacing it here keeps the user oriented when
 * they switch to the STM32H753ZI target without diving into the Com
 * editor first. Returns null if the project has no Com config — the
 * selector still renders, but the badge row stays empty.
 */
type BoardOptions = {
  baud: string;
  fd: boolean;
  dataBaud: string | null;
};

function describeBoardOptions(project: ProjectRaw | null): BoardOptions | null {
  const com = project?.Com as
    | { networks?: Array<Record<string, unknown>> }
    | undefined;
  const net = com?.networks?.[0];
  if (!net) return null;
  const baud = typeof net.baudrate === "number" ? formatBaud(net.baudrate) : "—";
  const fd = net.network === "CANFD";
  const dataBaudRaw = net.data_baudrate;
  const dataBaud =
    fd && typeof dataBaudRaw === "number" ? formatBaud(dataBaudRaw) : null;
  return { baud, fd, dataBaud };
}

function formatBaud(hz: number): string {
  if (hz >= 1_000_000 && hz % 1_000_000 === 0) return `${hz / 1_000_000} Mb/s`;
  if (hz >= 1_000 && hz % 1_000 === 0) return `${hz / 1_000} kb/s`;
  return `${hz} b/s`;
}
