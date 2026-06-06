import { ChevronRight, Folder, FileCode, Layers } from "lucide-react";
import type { TreeNode, TreeNodeKind } from "../types";

/**
 * Module → container → parameter path for the active tree selection.
 * Walks the tree once to find the ancestor chain of the selected node,
 * then renders each label with a kind-appropriate icon. Reads like
 * `Com / networks[0] / messages[2] / Counter` in monospace for the leaf.
 */
export function Breadcrumb({
  tree,
  selectedId,
}: {
  tree: TreeNode[];
  selectedId: string | null;
}) {
  const trail = selectedId ? findTrail(tree, selectedId) : [];

  if (trail.length === 0) {
    return (
      <div className="breadcrumb" aria-label="selection path">
        <span className="crumb empty">no selection</span>
      </div>
    );
  }
  return (
    <div className="breadcrumb" aria-label="selection path">
      {trail.map((node, i) => {
        const isLeaf = i === trail.length - 1;
        return (
          <span
            key={node.id}
            className={`crumb${isLeaf ? " leaf" : ""}`}
            title={node.id}
          >
            <KindIcon kind={node.kind} />
            <span className="label-text">{node.label}</span>
            {!isLeaf && (
              <ChevronRight size={12} className="sep" aria-hidden />
            )}
          </span>
        );
      })}
    </div>
  );
}

function findTrail(tree: TreeNode[], targetId: string): TreeNode[] {
  for (const root of tree) {
    const path = walk(root, targetId, []);
    if (path) return path;
  }
  return [];
}

function walk(
  node: TreeNode,
  targetId: string,
  acc: TreeNode[],
): TreeNode[] | null {
  const next = [...acc, node];
  if (node.id === targetId) return next;
  if (!node.children) return null;
  for (const child of node.children) {
    const found = walk(child, targetId, next);
    if (found) return found;
  }
  return null;
}

function KindIcon({ kind }: { kind: TreeNodeKind }) {
  switch (kind) {
    case "module":
      return <Layers size={12} aria-hidden />;
    case "container":
      return <Folder size={12} aria-hidden />;
    case "item":
      return <FileCode size={12} aria-hidden />;
    default:
      return null;
  }
}
