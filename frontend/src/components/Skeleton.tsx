import { FolderOpen, Inbox, Layers, Network, Upload } from "lucide-react";

/**
 * Placeholder rows that mimic the tree shape while the project is
 * loading. Looks deliberately like the real tree (icons + monospace
 * names) so the transition into the live state isn't jarring.
 */
export function TreeSkeleton({ rows = 6 }: { rows?: number }) {
  // Indented widths chosen so the rows read as "module · container ·
  // a few items". Pixels are intentional here — they're the eye-fooling
  // illusion, not real values to layout against.
  const pattern = [
    { depth: 0, width: 48 },
    { depth: 1, width: 120 },
    { depth: 2, width: 90 },
    { depth: 2, width: 70 },
    { depth: 0, width: 56 },
    { depth: 1, width: 100 },
    { depth: 1, width: 84 },
    { depth: 2, width: 78 },
  ];
  return (
    <ul className="tree tree-skeleton" aria-hidden>
      {Array.from({ length: rows }, (_, i) => {
        const p = pattern[i % pattern.length];
        return (
          <li key={i}>
            <div
              className="tree-row"
              style={{ paddingLeft: 6 + p.depth * 14 }}
            >
              <span className="skeleton-bar" style={{ width: p.width }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/** Editor placeholder while we don't have a node selected yet. */
export function EditorSkeleton() {
  return (
    <div className="editor property-grid skeleton" aria-hidden>
      <div className="skeleton-bar skeleton-bar-lg" style={{ width: 220 }} />
      <div className="skeleton-bar" style={{ width: 320, marginTop: 8 }} />
      <div className="prop-group">
        <header className="prop-group-header">
          <span>Identity</span>
        </header>
        <table className="fields">
          <tbody>
            {[160, 220, 180, 200].map((w, i) => (
              <tr key={i}>
                <th>
                  <span className="skeleton-bar" style={{ width: 100 }} />
                </th>
                <td>
                  <span className="skeleton-bar" style={{ width: w }} />
                </td>
                <td>
                  <span className="skeleton-bar skeleton-bar-faint" style={{ width: 60 }} />
                </td>
                <td></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/**
 * The "you have nothing loaded" empty state. Surfaces when the API
 * came back with zero projects (rare) or a project failed to load.
 * Reads like an IDE welcome panel: short pitch + the two relevant
 * actions, in the same toolbar above.
 */
export function NoProjectEmpty({
  onImport,
  hasProjects,
}: {
  onImport: () => void;
  hasProjects: boolean;
}) {
  return (
    <div className="empty-state">
      <div className="empty-state-card">
        <Layers size={32} aria-hidden className="empty-state-icon" />
        <h2>No project loaded</h2>
        {hasProjects ? (
          <p>
            Pick a project from the picker in the toolbar
            <Network size={12} className="inline-icon" aria-hidden /> above,
            or import a DBC to start from a comms matrix.
          </p>
        ) : (
          <p>
            No bundled examples were found. Drop a <code>.dbc</code> into
            the importer to start.
          </p>
        )}
        <div className="empty-state-actions">
          <button className="primary" onClick={onImport}>
            <Upload size={14} aria-hidden />
            <span className="lbl">Import DBC</span>
          </button>
        </div>
        <p className="empty-state-tip">
          <FolderOpen size={12} className="inline-icon" aria-hidden />
          Examples live under <code>examples/</code> in the repo —
          <code> com-minimal</code>, <code>canfd-minimal</code>,
          <code> cantp-iso15765</code>.
        </p>
      </div>
    </div>
  );
}

/** A neutral inline empty for very minor panels (the bundled-DBC
 *  list, etc.). Kept generic. */
export function InlineEmpty({ text }: { text: string }) {
  return (
    <div className="inline-empty">
      <Inbox size={14} aria-hidden />
      <span>{text}</span>
    </div>
  );
}
