import type { Issue } from "../types";

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
  const errors = issues.filter((i) => i.severity === "error").length;
  const warnings = issues.filter((i) => i.severity === "warning").length;
  return (
    <div className="problems">
      <header>
        <strong>Problems</strong>
        <span className="counts">
          {errors > 0 && <span className="badge err">{errors} errors</span>}
          {warnings > 0 && <span className="badge warn">{warnings} warnings</span>}
          {!errors && !warnings && (
            <span className="badge ok">no issues</span>
          )}
          {loading && <span className="counts dim"> · validating…</span>}
        </span>
      </header>
      <ul>
        {issues.length === 0 && !loading && (
          <li className="empty">All rules pass.</li>
        )}
        {issues.map((i, idx) => (
          <li key={`${i.rule}-${idx}`} className={`severity-${i.severity}`}>
            <span className="rule">{i.rule}</span>
            <span className="loc">
              {i.module}
              {i.path.length > 0 ? ` · ${i.path.join(".")}` : ""}
            </span>
            <span className="msg">{i.message}</span>
            <span className="actions">
              <button onClick={() => onSelect(i)} className="link">go to</button>
              {i.fix && (
                <button
                  className="primary small"
                  onClick={() => onApplyFix(i)}
                  title={i.fix.description}
                >
                  Fix
                </button>
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
