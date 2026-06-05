// Pure functions: derive the left-pane tree from a Project, look up
// nodes by id, and apply edits at a JSON pointer.

import type { ConfigClass, ProjectRaw, TreeNode } from "./types";

const MODULE_ORDER: ConfigClass[] = ["Can", "CanIf", "CanTp", "PduR", "Com"];

export function buildTree(project: ProjectRaw): TreeNode[] {
  const out: TreeNode[] = [];
  for (const module of MODULE_ORDER) {
    const data = project[module];
    if (!data) continue;
    out.push(buildModuleNode(module, data));
  }
  return out;
}

function buildModuleNode(
  module: ConfigClass,
  data: Record<string, unknown>,
): TreeNode {
  const children: TreeNode[] = [];
  if (module === "Can") {
    children.push(
      ...arrayChildren(module, [], "controllers", data["controllers"], "name"),
    );
  } else if (module === "CanIf") {
    children.push(...canIfChildren(module, data));
  } else if (module === "CanTp") {
    children.push(
      ...arrayChildren(module, [], "channels", data["channels"], "name"),
    );
  } else if (module === "PduR") {
    children.push(
      ...arrayChildren(module, [], "routines", data["routines"], "name"),
    );
    if (Array.isArray(data["networks"])) {
      children.push(
        ...arrayChildren(module, [], "networks", data["networks"], "name"),
      );
    }
  } else if (module === "Com") {
    children.push(...comChildren(module, data));
  }
  return {
    id: module,
    label: module,
    kind: "module",
    module,
    pointer: [],
    children,
  };
}

function canIfChildren(
  module: ConfigClass,
  data: Record<string, unknown>,
): TreeNode[] {
  const networks = (data["networks"] as Array<Record<string, unknown>>) || [];
  return networks.map((net, i): TreeNode => ({
    id: `${module}/networks/${i}`,
    label: String(net["name"] ?? `network ${i}`),
    kind: "item",
    module,
    pointer: ["networks", i],
    children: [
      ...arrayChildren(module, ["networks", i], "RxPdus", net["RxPdus"], "name"),
      ...arrayChildren(module, ["networks", i], "TxPdus", net["TxPdus"], "name"),
    ],
  }));
}

function comChildren(
  module: ConfigClass,
  data: Record<string, unknown>,
): TreeNode[] {
  const networks = (data["networks"] as Array<Record<string, unknown>>) || [];
  return networks.map((net, i): TreeNode => {
    const messages = (net["messages"] as Array<Record<string, unknown>>) || [];
    return {
      id: `${module}/networks/${i}`,
      label: String(net["name"] ?? `network ${i}`),
      kind: "item",
      module,
      pointer: ["networks", i],
      children: messages.map((msg, mi): TreeNode => {
        const signals =
          (msg["signals"] as Array<Record<string, unknown>>) || [];
        return {
          id: `${module}/networks/${i}/messages/${mi}`,
          label: String(msg["name"] ?? `message ${mi}`),
          kind: "item",
          module,
          pointer: ["networks", i, "messages", mi],
          children: signals.map((sig, si) => ({
            id: `${module}/networks/${i}/messages/${mi}/signals/${si}`,
            label: String(sig["name"] ?? `signal ${si}`),
            kind: "item" as const,
            module,
            pointer: ["networks", i, "messages", mi, "signals", si],
          })),
        };
      }),
    };
  });
}

function arrayChildren(
  module: ConfigClass,
  parentPointer: (string | number)[],
  field: string,
  raw: unknown,
  labelKey: string,
): TreeNode[] {
  if (!Array.isArray(raw)) return [];
  return [{
    id: `${module}/${[...parentPointer, field].join("/")}`,
    label: `${field} (${raw.length})`,
    kind: "container",
    module,
    pointer: [...parentPointer, field],
    children: raw.map((item, i) => ({
      id: `${module}/${[...parentPointer, field, i].join("/")}`,
      label: String((item as Record<string, unknown>)[labelKey] ?? `${field} ${i}`),
      kind: "item" as const,
      module,
      pointer: [...parentPointer, field, i],
    })),
  }];
}

export function findNodeById(roots: TreeNode[], id: string): TreeNode | null {
  for (const r of roots) {
    if (r.id === id) return r;
    if (r.children) {
      const found = findNodeById(r.children, id);
      if (found) return found;
    }
  }
  return null;
}

export function getAtPointer(
  obj: unknown,
  pointer: (string | number)[],
): unknown {
  let cur: unknown = obj;
  for (const seg of pointer) {
    if (cur == null) return undefined;
    cur = (cur as Record<string | number, unknown>)[seg];
  }
  return cur;
}

export function setAtPointer<T>(
  obj: T,
  pointer: (string | number)[],
  value: unknown,
): T {
  if (pointer.length === 0) return value as T;
  const head = pointer[0];
  const rest = pointer.slice(1);
  if (Array.isArray(obj)) {
    const copy = [...obj];
    copy[Number(head)] = setAtPointer(copy[Number(head)], rest, value);
    return copy as unknown as T;
  }
  if (obj && typeof obj === "object") {
    const copy: Record<string | number, unknown> = { ...(obj as object) };
    copy[head] = setAtPointer(copy[head], rest, value);
    return copy as unknown as T;
  }
  return obj;
}
