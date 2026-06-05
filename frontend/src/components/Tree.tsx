import { useState } from "react";
import type { TreeNode } from "../types";

export function Tree({
  nodes,
  selectedId,
  onSelect,
}: {
  nodes: TreeNode[];
  selectedId: string | null;
  onSelect: (n: TreeNode) => void;
}) {
  return (
    <ul className="tree">
      {nodes.map((n) => (
        <TreeItem
          key={n.id}
          node={n}
          selectedId={selectedId}
          onSelect={onSelect}
          depth={0}
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
}: {
  node: TreeNode;
  selectedId: string | null;
  onSelect: (n: TreeNode) => void;
  depth: number;
}) {
  const hasChildren = !!node.children?.length;
  const [open, setOpen] = useState<boolean>(depth < 1);
  const selected = selectedId === node.id;
  return (
    <li>
      <div
        className={`tree-row ${selected ? "selected" : ""}`}
        style={{ paddingLeft: 6 + depth * 14 }}
      >
        <span
          className="tree-twisty"
          onClick={() => hasChildren && setOpen(!open)}
          aria-hidden
        >
          {hasChildren ? (open ? "▾" : "▸") : "·"}
        </span>
        <span className={`tree-label kind-${node.kind}`} onClick={() => onSelect(node)}>
          {node.label}
        </span>
      </div>
      {hasChildren && open && (
        <ul className="tree">
          {node.children!.map((c) => (
            <TreeItem
              key={c.id}
              node={c}
              selectedId={selectedId}
              onSelect={onSelect}
              depth={depth + 1}
            />
          ))}
        </ul>
      )}
    </li>
  );
}
