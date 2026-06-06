import { useRef, useState, type KeyboardEvent } from "react";
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
import { findNodeById } from "../treeModel";
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
  const containerRef = useRef<HTMLUListElement>(null);
  // Roving-tabindex anchor. The row whose id matches gets tabIndex=0;
  // every other row is -1 so Shift+Tab leaves the tree in one hop
  // instead of stepping through every row.
  const [focusAnchor, setFocusAnchor] = useState<string | null>(null);
  const tabAnchor = focusAnchor ?? selectedId ?? nodes[0]?.id ?? null;

  function onKeyDown(e: KeyboardEvent<HTMLUListElement>) {
    const root = containerRef.current;
    if (!root) return;
    const active = document.activeElement;
    if (!(active instanceof HTMLElement)) return;
    if (!root.contains(active)) return;

    const rows = Array.from(
      root.querySelectorAll<HTMLElement>(".tree-row[data-tree-id]"),
    );
    const idx = rows.indexOf(active);
    if (idx === -1) return;

    const move = (next: number) => {
      const target = rows[next];
      if (!target) return;
      const id = target.dataset.treeId ?? null;
      if (id) setFocusAnchor(id);
      target.focus();
      e.preventDefault();
    };

    const li = active.closest("li");
    const hasChildren = li?.getAttribute("aria-expanded") !== null;
    const isExpanded = li?.getAttribute("aria-expanded") === "true";

    switch (e.key) {
      case "ArrowDown":
        move(idx + 1);
        return;
      case "ArrowUp":
        move(idx - 1);
        return;
      case "Home":
        move(0);
        return;
      case "End":
        move(rows.length - 1);
        return;
      case "Enter":
      case " ": {
        const id = active.dataset.treeId;
        if (id) {
          const node = findNodeById(nodes, id);
          if (node) onSelect(node);
        }
        e.preventDefault();
        return;
      }
      case "ArrowRight":
        if (hasChildren && !isExpanded) {
          const twisty = active.querySelector<HTMLElement>(".tree-twisty");
          twisty?.click();
          e.preventDefault();
        } else {
          move(idx + 1);
        }
        return;
      case "ArrowLeft":
        if (hasChildren && isExpanded) {
          const twisty = active.querySelector<HTMLElement>(".tree-twisty");
          twisty?.click();
          e.preventDefault();
        } else {
          // Move focus to the parent treeitem.
          const parentLi = li?.parentElement?.closest("li[role='treeitem']");
          const parentRow = parentLi?.querySelector<HTMLElement>(".tree-row");
          if (parentRow) {
            const id = parentRow.dataset.treeId ?? null;
            if (id) setFocusAnchor(id);
            parentRow.focus();
            e.preventDefault();
          }
        }
        return;
    }
  }

  return (
    <ul
      ref={containerRef}
      className="tree"
      role="tree"
      aria-label="project model"
      onKeyDown={onKeyDown}
    >
      {nodes.map((n) => (
        <TreeItem
          key={n.id}
          node={n}
          selectedId={selectedId}
          tabAnchorId={tabAnchor}
          onSelect={onSelect}
          onFocusRow={setFocusAnchor}
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
  tabAnchorId,
  onSelect,
  onFocusRow,
  depth,
  rollup,
}: {
  node: TreeNode;
  selectedId: string | null;
  tabAnchorId: string | null;
  onSelect: (n: TreeNode) => void;
  onFocusRow: (id: string) => void;
  depth: number;
  rollup?: Map<string, IssueRollup>;
}) {
  const hasChildren = !!node.children?.length;
  const [open, setOpen] = useState<boolean>(depth < 1);
  const selected = selectedId === node.id;
  const sev = rollup ? rollupAt(rollup, node.id) : undefined;
  const isAnchor = node.id === tabAnchorId;

  return (
    <li role="treeitem" aria-expanded={hasChildren ? open : undefined}>
      <div
        className={`tree-row${selected ? " selected" : ""}`}
        style={{ paddingLeft: 6 + depth * ROW_INDENT }}
        data-tree-id={node.id}
        tabIndex={isAnchor ? 0 : -1}
        role="presentation"
        onFocus={() => onFocusRow(node.id)}
        onClick={() => onSelect(node)}
        aria-selected={selected || undefined}
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
          onClick={(e) => {
            e.stopPropagation();
            if (hasChildren) setOpen(!open);
          }}
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
              tabAnchorId={tabAnchorId}
              onSelect={onSelect}
              onFocusRow={onFocusRow}
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
      return <Box size={size} className="kind-icon item" aria-hidden />;
    default:
      return <FileCode size={size} aria-hidden />;
  }
}

function SeverityBadge({ sev }: { sev: IssueRollup }) {
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
