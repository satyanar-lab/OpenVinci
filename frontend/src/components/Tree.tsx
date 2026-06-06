import { useState } from "react";
import {
  Box,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  FileCode,
  Folder,
  FolderOpen,
  Layers,
  TriangleAlert,
} from "lucide-react";
import type { TreeNode, TreeNodeKind } from "../types";
import { rollupAt, type IssueRollup } from "../validationRollup";

const ROW_INDENT = 14; // pixels per depth level

export function Tree({
  nodes,
  selectedId,
  onSelect,
  rollup,
}: {
  nodes: TreeNode[];
  selectedId: string | null;
  onSelect: (n: TreeNode) => void;
  /** Per-node rolled-up severities. Optional — tree still renders if
   *  validation hasn't completed yet. */
  rollup?: Map<string, IssueRollup>;
}) {
  return (
    <ul className="tree" role="tree">
      {nodes.map((n) => (
        <TreeItem
          key={n.id}
          node={n}
          selectedId={selectedId}
          onSelect={onSelect}
          depth={0}
          rollup={rollup}
        />
      ))}
    </ul>
  );
}

function TreeItem({
  node,
  selectedId,
  onSelect,
  depth,
  rollup,
}: {
  node: TreeNode;
  selectedId: string | null;
  onSelect: (n: TreeNode) => void;
  depth: number;
  rollup?: Map<string, IssueRollup>;
}) {
  const hasChildren = !!node.children?.length;
  const [open, setOpen] = useState<boolean>(depth < 1);
  const selected = selectedId === node.id;
  const sev = rollup ? rollupAt(rollup, node.id) : undefined;

  return (
    <li role="treeitem" aria-expanded={hasChildren ? open : undefined}>
      <div
        className={`tree-row${selected ? " selected" : ""}`}
        style={{ paddingLeft: 6 + depth * ROW_INDENT }}
      >
        {/* Indentation guide rails — one vertical 1px line per depth. */}
        {Array.from({ length: depth }, (_, i) => (
          <span
            key={i}
            className="tree-guide"
            style={{ left: 6 + i * ROW_INDENT + 8 }}
            aria-hidden
          />
        ))}
        <span
          className="tree-twisty"
          onClick={() => hasChildren && setOpen(!open)}
          aria-hidden
        >
          {hasChildren ? (
            open ? (
              <ChevronDown size={12} />
            ) : (
              <ChevronRight size={12} />
            )
          ) : (
            <span className="tree-dot" />
          )}
        </span>
        <span
          className={`tree-label kind-${node.kind}`}
          onClick={() => onSelect(node)}
          title={node.id}
        >
          <KindIcon kind={node.kind} open={open} />
          <span className="label-text">{node.label}</span>
        </span>
        {sev && (sev.errors > 0 || sev.warnings > 0) && (
          <SeverityBadge sev={sev} />
        )}
      </div>
      {hasChildren && open && (
        <ul className="tree" role="group">
          {node.children!.map((c) => (
            <TreeItem
              key={c.id}
              node={c}
              selectedId={selectedId}
              onSelect={onSelect}
              depth={depth + 1}
              rollup={rollup}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

function KindIcon({ kind, open }: { kind: TreeNodeKind; open: boolean }) {
  const size = 13;
  switch (kind) {
    case "module":
      return <Layers size={size} className="kind-icon module" aria-hidden />;
    case "container":
      return open ? (
        <FolderOpen size={size} className="kind-icon container" aria-hidden />
      ) : (
        <Folder size={size} className="kind-icon container" aria-hidden />
      );
    case "item":
      // Pick a slightly different mark for items so e.g. a "controller" and
      // a "PDU" don't look like containers — they're parameter records.
      return <Box size={size} className="kind-icon item" aria-hidden />;
    default:
      return <FileCode size={size} aria-hidden />;
  }
}

function SeverityBadge({ sev }: { sev: IssueRollup }) {
  // Errors win when both present (an error already implies "open me"); a
  // warning-only count gets the amber marker. `self*` distinguishes "I
  // am the problem" from "a descendant is" — when only descendants are
  // affected we still mark, but the title hints at the difference so
  // the user knows to keep drilling.
  const isSelf = sev.selfErrors > 0 || sev.selfWarnings > 0;
  if (sev.errors > 0) {
    return (
      <span
        className="tree-sev tree-sev-err"
        title={
          isSelf
            ? `${sev.errors} error(s) here`
            : `${sev.errors} error(s) in descendants`
        }
      >
        <CircleAlert size={11} aria-hidden />
        <span className="count">{sev.errors}</span>
      </span>
    );
  }
  return (
    <span
      className="tree-sev tree-sev-warn"
      title={
        isSelf
          ? `${sev.warnings} warning(s) here`
          : `${sev.warnings} warning(s) in descendants`
      }
    >
      <TriangleAlert size={11} aria-hidden />
      <span className="count">{sev.warnings}</span>
    </span>
  );
}
