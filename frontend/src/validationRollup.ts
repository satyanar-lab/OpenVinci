// Validation → tree-node rollup.
//
// Given the list of issues from the engine and the in-memory tree, we
// want two views of the same data:
//
//   1. Per-tree-node severity counts that include all descendants. This
//      drives the red/amber dot on ancestor nodes ("a container with a
//      problem inside" — the IDE signal an editor user reads first).
//   2. Per-field issue lookup for the property grid. The Editor shows
//      a small inline marker next to a field when an issue points
//      exactly at that field (path = node.pointer + [fieldName]).
//
// Both are pure derivations of (tree, issues); App.tsx memoises them
// alongside `tree` so the cost is negligible.

import type { Issue, TreeNode } from "./types";

export type IssueRollup = {
  errors: number;
  warnings: number;
  /** Direct issues — not from descendants. Lets the UI distinguish
   * "this node IS the problem" from "a child has a problem". */
  selfErrors: number;
  selfWarnings: number;
};

const EMPTY: IssueRollup = {
  errors: 0,
  warnings: 0,
  selfErrors: 0,
  selfWarnings: 0,
};

/**
 * Walk the tree and count issues at-or-below each node. An issue at
 * (module, path) is considered "below" a node iff:
 *  - issue.module === node.module
 *  - node.pointer is a prefix of issue.path (segment-wise equality).
 */
export function rollupIssues(
  tree: TreeNode[],
  issues: Issue[],
): Map<string, IssueRollup> {
  const out = new Map<string, IssueRollup>();
  for (const root of tree) visit(root, issues, out);
  return out;
}

function visit(
  node: TreeNode,
  issues: Issue[],
  out: Map<string, IssueRollup>,
): IssueRollup {
  let selfErrors = 0;
  let selfWarnings = 0;
  let totalErrors = 0;
  let totalWarnings = 0;

  for (const issue of issues) {
    if (issue.module !== node.module) continue;
    if (!pointerIsPrefix(node.pointer, issue.path)) continue;
    if (issue.severity === "error") totalErrors++;
    else if (issue.severity === "warning") totalWarnings++;
    // "Direct" = path is exactly node.pointer or one step deeper
    // (a field on this node). Anything deeper is owned by a child.
    if (issue.path.length <= node.pointer.length + 1) {
      if (issue.severity === "error") selfErrors++;
      else if (issue.severity === "warning") selfWarnings++;
    }
  }
  // Recurse so the descendant counts in `out` are populated even though
  // we re-derive `total*` from the issues list. The descent's only
  // observable side-effect is populating `out` for child ids.
  if (node.children) {
    for (const child of node.children) visit(child, issues, out);
  }
  const rollup: IssueRollup = {
    errors: totalErrors,
    warnings: totalWarnings,
    selfErrors,
    selfWarnings,
  };
  if (totalErrors > 0 || totalWarnings > 0) out.set(node.id, rollup);
  return rollup;
}

/**
 * Issues whose path lands exactly on a named field of `node`. Used by
 * the Editor for inline per-field markers.
 */
export function fieldIssuesFor(node: TreeNode, issues: Issue[]): Map<string, Issue[]> {
  const out = new Map<string, Issue[]>();
  for (const issue of issues) {
    if (issue.module !== node.module) continue;
    if (issue.path.length !== node.pointer.length + 1) continue;
    if (!pointerIsPrefix(node.pointer, issue.path)) continue;
    const fieldName = String(issue.path[node.pointer.length]);
    const bucket = out.get(fieldName);
    if (bucket) bucket.push(issue);
    else out.set(fieldName, [issue]);
  }
  return out;
}

/** Read a node's rolled-up severity; safe default for nodes with none. */
export function rollupAt(
  rollup: Map<string, IssueRollup>,
  id: string,
): IssueRollup {
  return rollup.get(id) ?? EMPTY;
}

function pointerIsPrefix(
  prefix: (string | number)[],
  path: (string | number)[],
): boolean {
  if (prefix.length > path.length) return false;
  for (let i = 0; i < prefix.length; i++) {
    if (String(prefix[i]) !== String(path[i])) return false;
  }
  return true;
}
