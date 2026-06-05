import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  applyFix,
  fetchSchemas,
  getProject,
  listProjects,
  validateProject,
} from "./api";
import { Editor } from "./components/Editor";
import { GenerateModal } from "./components/GenerateModal";
import { ImportDbcModal } from "./components/ImportDbcModal";
import { ProblemsPanel } from "./components/ProblemsPanel";
import { Tree } from "./components/Tree";
import type {
  Issue,
  ProjectRaw,
  SchemaBundle,
  TreeNode,
  ValidationReport,
} from "./types";
import { buildTree, findNodeById } from "./treeModel";

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
  const [error, setError] = useState<string | null>(null);

  // Bootstrap: fetch schemas + project list + initial project (com-minimal)
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
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  // Re-validate whenever the project changes. Debounced lightly so the
  // user can type into a field without spamming the backend.
  const validationGen = useRef(0);
  const revalidate = useCallback(
    async (p: ProjectRaw) => {
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
    },
    [],
  );

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

  function selectIssue(issue: Issue) {
    // Find the closest tree node matching this issue's pointer path.
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
      <header className="topbar">
        <span className="brand">OpenVinci</span>
        <select
          value={projectName ?? ""}
          onChange={(e) => loadProject(e.target.value)}
          aria-label="project"
        >
          {projects.length === 0 && <option value="">— loading —</option>}
          {projects.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <span className="spacer" />
        <button onClick={() => setShowImport(true)}>Import DBC</button>
        <button
          className="primary"
          onClick={() => setShowGenerate(true)}
          disabled={!project}
        >
          Generate
        </button>
      </header>

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
              onSelect={(n) => setSelectedId(n.id)}
            />
          ) : (
            <p className="hint">Loading…</p>
          )}
        </aside>
        <section className="center">
          {schemas && project ? (
            <Editor
              node={selectedNode}
              project={project}
              schemas={schemas}
              onChange={setProject}
            />
          ) : (
            <p className="hint">Loading…</p>
          )}
        </section>
      </div>

      <ProblemsPanel
        issues={validation?.issues ?? []}
        loading={validating}
        onApplyFix={handleApplyFix}
        onSelect={selectIssue}
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
            // r already contains a validation result — use it directly
            setValidation(r.validation);
          }}
        />
      )}

      {showGenerate && project && (
        <GenerateModal
          project={project}
          sourceProject={sourceProject}
          onClose={() => setShowGenerate(false)}
        />
      )}
    </div>
  );
}
