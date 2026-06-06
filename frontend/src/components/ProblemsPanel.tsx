import { useMemo, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  Loader,
  TriangleAlert,
  Wrench,
} from "lucide-react";
import type { Issue, Severity } from "../types";

type Filter = "all" | "error" | "warning";

export function ProblemsPanel({
  issues,
  loading,
  onApplyFix,
  onSelect,
}: {
  issues: Issue[];
  loading: boolean;
  onApplyFix: (i: Issue) => void;
  onSelect: (i: Issue) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [groupByModule, setGroupByModule] = useState<boolean>(false);

  const errors = issues.filter((i) => i.severity === "error").length;
  const warnings = issues.filter((i) => i.severity === "warning").length;

  const visible = useMemo(
    () =>
      issues.filter((i) => {
        if (filter === "all") return true;
        return i.severity === filter;
      }),
    [issues, filter],
  );

  const allClean = errors === 0 && warnings === 0 && !loading;

  return (
    <div className="problems">
      <header>
        <strong className="problems-title">
          <Wrench size={12} aria-hidden />
          <span>Problems</span>
        </strong>

        <span className="counts">
          {errors > 0 && (
            <span className="badge err">
              <CircleAlert size={11} aria-hidden /> {errors}
            </span>
          )}
          {warnings > 0 && (
            <span className="badge warn">
              <TriangleAlert size={11} aria-hidden /> {warnings}
            </span>
          )}
          {allClean && (
            <span className="badge ok">
              <Check size={11} aria-hidden /> clean
            </span>
          )}
          {loading && (
            <span className="counts dim">
              <Loader size={11} aria-hidden className="spin" /> validating…
            </span>
          )}
        </span>

        <span className="filter-chips" role="tablist" aria-label="severity filter">
          <FilterChip
            label="All"
            count={issues.length}
            active={filter === "all"}
            onClick={() => setFilter("all")}
          />
          <FilterChip
            label="Errors"
            icon={<CircleAlert size={11} aria-hidden />}
            count={errors}
            active={filter === "error"}
            onClick={() => setFilter("error")}
            tone="err"
          />
          <FilterChip
            label="Warnings"
            icon={<TriangleAlert size={11} aria-hidden />}
            count={warnings}
            active={filter === "warning"}
            onClick={() => setFilter("warning")}
            tone="warn"
          />
        </span>

        <span className="problems-toggles">
          <label className="toggle">
            <input
              type="checkbox"
              checked={groupByModule}
              onChange={(e) => setGroupByModule(e.target.checked)}
            />
            <span>Group by module</span>
          </label>
        </span>
      </header>

      <ProblemsList
        issues={visible}
        loading={loading}
        groupByModule={groupByModule}
        allClean={allClean}
        onApplyFix={onApplyFix}
        onSelect={onSelect}
      />
    </div>
  );
}

function ProblemsList({
  issues,
  loading,
  groupByModule,
  allClean,
  onApplyFix,
  onSelect,
}: {
  issues: Issue[];
  loading: boolean;
  groupByModule: boolean;
  allClean: boolean;
  onApplyFix: (i: Issue) => void;
  onSelect: (i: Issue) => void;
}) {
  if (allClean) {
    return (
      <div className="problems-empty">
        <Check size={24} aria-hidden className="problems-empty-icon" />
        <p className="problems-empty-title">No problems — configuration valid</p>
        <p className="problems-empty-sub">
          Every engine rule passed. Edit the project to re-trigger validation.
        </p>
      </div>
    );
  }
  if (issues.length === 0 && !loading) {
    return (
      <div className="problems-empty">
        <Check size={20} aria-hidden className="problems-empty-icon dim" />
        <p className="problems-empty-title dim">No items match the current filter.</p>
      </div>
    );
  }

  if (!groupByModule) {
    return (
      <ul className="problems-rows">
        {issues.map((i, idx) => (
          <ProblemRow
            key={`${i.rule}-${idx}`}
            issue={i}
            onSelect={onSelect}
            onApplyFix={onApplyFix}
          />
        ))}
      </ul>
    );
  }

  const byModule = new Map<string, Issue[]>();
  for (const issue of issues) {
    const bucket = byModule.get(issue.module);
    if (bucket) bucket.push(issue);
    else byModule.set(issue.module, [issue]);
  }
  const orderedModules = [...byModule.keys()].sort();

  return (
    <div className="problems-rows grouped">
      {orderedModules.map((mod) => {
        const list = byModule.get(mod)!;
        return (
          <ProblemModuleGroup
            key={mod}
            module={mod}
            issues={list}
            onSelect={onSelect}
            onApplyFix={onApplyFix}
          />
        );
      })}
    </div>
  );
}

function ProblemModuleGroup({
  module,
  issues,
  onSelect,
  onApplyFix,
}: {
  module: string;
  issues: Issue[];
  onSelect: (i: Issue) => void;
  onApplyFix: (i: Issue) => void;
}) {
  const [open, setOpen] = useState(true);
  const errors = issues.filter((i) => i.severity === "error").length;
  const warnings = issues.filter((i) => i.severity === "warning").length;
  return (
    <div className="problems-group">
      <button
        className="problems-group-header"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown size={12} aria-hidden />
        ) : (
          <ChevronRight size={12} aria-hidden />
        )}
        <span className="problems-group-name">{module}</span>
        <span className="problems-group-meta">
          {errors > 0 && (
            <span className="badge err">
              <CircleAlert size={11} aria-hidden /> {errors}
            </span>
          )}
          {warnings > 0 && (
            <span className="badge warn">
              <TriangleAlert size={11} aria-hidden /> {warnings}
            </span>
          )}
        </span>
      </button>
      {open && (
        <ul className="problems-rows">
          {issues.map((i, idx) => (
            <ProblemRow
              key={`${i.rule}-${idx}`}
              issue={i}
              onSelect={onSelect}
              onApplyFix={onApplyFix}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function ProblemRow({
  issue,
  onSelect,
  onApplyFix,
}: {
  issue: Issue;
  onSelect: (i: Issue) => void;
  onApplyFix: (i: Issue) => void;
}) {
  return (
    <li className={`severity-${issue.severity}`}>
      <span
        className={`row-sev sev-${issue.severity}`}
        aria-label={issue.severity}
        title={issue.severity}
      >
        <SeverityIcon severity={issue.severity} />
      </span>
      <span className="rule" title={issue.rule}>{issue.rule}</span>
      <span className="loc">
        {issue.module}
        {issue.path.length > 0 ? ` · ${issue.path.join(".")}` : ""}
      </span>
      <span className="msg">{issue.message}</span>
      <span className="actions">
        <button onClick={() => onSelect(issue)} className="link" title="navigate">
          go to
        </button>
        {issue.fix && (
          <button
            className="primary small"
            onClick={() => onApplyFix(issue)}
            title={issue.fix.description}
          >
            Fix
          </button>
        )}
      </span>
    </li>
  );
}

function SeverityIcon({ severity }: { severity: Severity }) {
  if (severity === "error") return <CircleAlert size={13} aria-hidden />;
  if (severity === "warning") return <TriangleAlert size={13} aria-hidden />;
  return <Check size={13} aria-hidden />;
}

function FilterChip({
  label,
  icon,
  count,
  active,
  onClick,
  tone,
}: {
  label: string;
  icon?: React.ReactNode;
  count: number;
  active: boolean;
  onClick: () => void;
  tone?: "err" | "warn";
}) {
  const klass = ["chip", active ? "active" : "", tone ? `tone-${tone}` : ""]
    .filter(Boolean)
    .join(" ");
  return (
    <button
      role="tab"
      aria-selected={active}
      className={klass}
      onClick={onClick}
    >
      {icon}
      <span className="chip-label">{label}</span>
      <span className="chip-count">{count}</span>
    </button>
  );
}
