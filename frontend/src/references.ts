// What "valid targets" mean for the well-known cross-file reference
// fields. The Editor uses these to render dropdowns instead of free
// text. Keep this file the single source of UI-side cross-reference
// knowledge — it's small enough to live in one place.

import type { ConfigClass, ProjectRaw, TreeNode } from "./types";

export type RefSource =
  | { kind: "modules"; values: string[] }
  | { kind: "canifPduNames"; values: string[] }
  | { kind: "canControllers"; values: string[] }
  | { kind: "comNetworks"; values: string[] };

/** Returns a dropdown source for a named field at a given node, or null
 * if the field has no special reference behaviour. */
export function referenceSourceFor(
  node: TreeNode,
  fieldName: string,
  project: ProjectRaw,
): RefSource | null {
  // PduR routine: from/to are module enums; name should match a CanIf PDU.
  if (
    node.module === "PduR" &&
    node.pointer[0] === "routines" &&
    typeof node.pointer[1] === "number"
  ) {
    if (fieldName === "from" || fieldName === "to") {
      return { kind: "modules", values: bswModules() };
    }
    if (fieldName === "name") {
      return { kind: "canifPduNames", values: allCanIfPduNames(project) };
    }
  }

  // CanIf PDU: up references a module or a User callback prefix.
  if (
    node.module === "CanIf" &&
    (node.pointer.includes("RxPdus") || node.pointer.includes("TxPdus"))
  ) {
    if (fieldName === "up") {
      return { kind: "modules", values: [...bswModules(), "UserAppRx", "UserAppTx"] };
    }
  }

  // Com network: device + network enums handled by schema; me is free text
  // but should suggest existing nodes. Skip for now.

  return null;
}

function bswModules(): string[] {
  return [
    "CanIf",
    "CanTp",
    "OsekNm",
    "CanNm",
    "PduR",
    "Dcm",
    "Com",
    "LinTp",
    "DoIP",
    "J1939Tp",
    "SecOC",
    "Mirror",
    "Xcp",
    "CanTSyn",
  ];
}

function allCanIfPduNames(project: ProjectRaw): string[] {
  const canif = project["CanIf"] as Record<string, unknown> | undefined;
  if (!canif) return [];
  const out: string[] = [];
  for (const net of (canif["networks"] as Array<Record<string, unknown>>) || []) {
    for (const list of [net["RxPdus"], net["TxPdus"]]) {
      for (const pdu of (list as Array<Record<string, unknown>>) || []) {
        if (pdu["name"]) out.push(String(pdu["name"]));
      }
    }
  }
  return out;
}

export function canControllerNames(project: ProjectRaw): string[] {
  const can = project["Can"] as Record<string, unknown> | undefined;
  if (!can) return [];
  return ((can["controllers"] as Array<Record<string, unknown>>) || []).map(
    (c) => String(c["name"] ?? ""),
  );
}

export function moduleHas(project: ProjectRaw, module: ConfigClass): boolean {
  return !!project[module];
}
