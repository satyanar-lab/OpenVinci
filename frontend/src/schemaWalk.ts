// Walk Layer-1 JSON Schemas to find the schema applicable at a given
// JSON pointer. Resolves local $refs (`#/$defs/...`) only — the
// cross-file refs in the shared/types schema are inlined for the UI's
// rendering needs (HexString, BSWModule, SimDevice, etc.).

import type { JSONSchema } from "./types";

const SHARED_DEFS: Record<string, JSONSchema> = {
  HexString: { type: "string", pattern: "^0x[0-9A-Fa-f]+$" },
  Identifier: { type: "string" },
  BSWModule: {
    type: "string",
    enum: [
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
    ],
  },
  NetworkKind: { type: "string", enum: ["CAN", "CANFD", "LIN"] },
  SimDevice: {
    type: "string",
    enum: ["simulator", "simulator_v2", "qemu", "vxl", "peak", "zlg"],
  },
};

export function resolveRef(
  ref: string,
  rootSchema: JSONSchema,
): JSONSchema {
  if (ref.startsWith("https://openvinci.dev/schema/shared/types.json#/$defs/")) {
    const key = ref.split("/").pop()!;
    return SHARED_DEFS[key] ?? {};
  }
  if (ref.startsWith("#/$defs/")) {
    const key = ref.split("/").pop()!;
    return rootSchema.$defs?.[key] ?? {};
  }
  return {};
}

export function resolveSchema(
  schema: JSONSchema | undefined,
  rootSchema: JSONSchema,
): JSONSchema {
  if (!schema) return {};
  if (schema.$ref) return resolveSchema(resolveRef(schema.$ref, rootSchema), rootSchema);
  return schema;
}

/** Walk along a JSON pointer through a schema, returning the schema
 * that applies to the value at that pointer. */
export function schemaAt(
  rootSchema: JSONSchema,
  pointer: (string | number)[],
): JSONSchema {
  let cur: JSONSchema = resolveSchema(rootSchema, rootSchema);
  for (const seg of pointer) {
    cur = resolveSchema(cur, rootSchema);
    if (typeof seg === "number" || /^\d+$/.test(String(seg))) {
      if (cur.items) {
        cur = resolveSchema(cur.items, rootSchema);
        continue;
      }
    }
    if (cur.properties && cur.properties[String(seg)]) {
      cur = resolveSchema(cur.properties[String(seg)], rootSchema);
      continue;
    }
    return {};
  }
  return cur;
}
