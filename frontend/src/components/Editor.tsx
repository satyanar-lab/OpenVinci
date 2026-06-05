// Typed editor for a selected tree node. The schema controls rendering:
// enums → <select>; booleans → checkbox; numbers → number input; strings
// → text input. Reference fields (PduR from/to/name, CanIf up) use the
// helper in ../references.ts to render a select of valid targets.

import { useMemo } from "react";
import type {
  JSONSchema,
  ProjectRaw,
  SchemaBundle,
  TreeNode,
} from "../types";
import { getAtPointer, setAtPointer } from "../treeModel";
import { resolveSchema, schemaAt } from "../schemaWalk";
import { referenceSourceFor } from "../references";

export function Editor({
  node,
  project,
  schemas,
  onChange,
}: {
  node: TreeNode | null;
  project: ProjectRaw;
  schemas: SchemaBundle;
  onChange: (p: ProjectRaw) => void;
}) {
  if (!node) {
    return (
      <div className="editor empty">
        <p>Select a node from the tree to edit.</p>
      </div>
    );
  }

  const rootSchema = schemas[node.module];
  const value = useMemo(
    () => getAtPointer(project[node.module] ?? {}, node.pointer),
    [project, node],
  );
  const schema = useMemo(
    () => schemaAt(rootSchema, node.pointer),
    [rootSchema, node],
  );

  function commit(newValue: unknown) {
    const moduleData = project[node!.module] ?? {};
    const updatedModule = setAtPointer(moduleData, node!.pointer, newValue);
    onChange({ ...project, [node!.module]: updatedModule });
  }

  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return (
      <div className="editor">
        <h2>
          {node.module} / {node.label}
        </h2>
        <p className="hint">
          This node is a {Array.isArray(value) ? "container" : "leaf"}.
          Drill into the tree to edit individual items.
        </p>
      </div>
    );
  }

  const obj = value as Record<string, unknown>;
  const fieldNames = orderedFieldNames(schema, obj);

  return (
    <div className="editor">
      <h2>
        <span className="badge">{node.module}</span> {node.label}
      </h2>
      {schema.description && <p className="hint">{schema.description}</p>}
      <table className="fields">
        <tbody>
          {fieldNames.map((name) => (
            <tr key={name}>
              <th>{name}</th>
              <td>
                <Field
                  name={name}
                  value={obj[name]}
                  fieldSchema={resolveSchema(
                    schema.properties?.[name],
                    rootSchema,
                  )}
                  rootSchema={rootSchema}
                  node={node}
                  project={project}
                  onChange={(v) => commit({ ...obj, [name]: v })}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function orderedFieldNames(
  schema: JSONSchema,
  current: Record<string, unknown>,
): string[] {
  const declared = Object.keys(schema.properties || {});
  const extras = Object.keys(current).filter(
    (k) => !declared.includes(k) && k !== "class",
  );
  return [...declared.filter((k) => k !== "class"), ...extras];
}

function Field({
  name,
  value,
  fieldSchema,
  rootSchema,
  node,
  project,
  onChange,
}: {
  name: string;
  value: unknown;
  fieldSchema: JSONSchema;
  rootSchema: JSONSchema;
  node: TreeNode;
  project: ProjectRaw;
  onChange: (v: unknown) => void;
}) {
  const refSource = referenceSourceFor(node, name, project);

  if (refSource) {
    return (
      <select
        value={typeof value === "string" ? value : ""}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">— choose —</option>
        {refSource.values.map((v) => (
          <option key={v} value={v}>
            {v}
          </option>
        ))}
      </select>
    );
  }

  if (fieldSchema.enum) {
    return (
      <select
        value={typeof value === "string" ? value : ""}
        onChange={(e) => onChange(e.target.value)}
      >
        {(fieldSchema.enum as unknown[]).map((v) => (
          <option key={String(v)} value={String(v)}>
            {String(v)}
          </option>
        ))}
      </select>
    );
  }

  if (
    fieldSchema.type === "boolean" ||
    (Array.isArray(fieldSchema.type) && fieldSchema.type.includes("boolean"))
  ) {
    return (
      <input
        type="checkbox"
        checked={!!value}
        onChange={(e) => onChange(e.target.checked)}
      />
    );
  }

  if (
    fieldSchema.type === "integer" ||
    fieldSchema.type === "number" ||
    (Array.isArray(fieldSchema.type) &&
      (fieldSchema.type.includes("integer") || fieldSchema.type.includes("number")))
  ) {
    return (
      <input
        type="number"
        value={value === undefined || value === null ? "" : (value as number)}
        onChange={(e) =>
          onChange(
            e.target.value === ""
              ? undefined
              : fieldSchema.type === "integer"
                ? parseInt(e.target.value, 10)
                : Number(e.target.value),
          )
        }
      />
    );
  }

  if (fieldSchema.type === "array") {
    // Show count + read-only summary; the tree drills into entries.
    const arr = Array.isArray(value) ? value : [];
    return <span className="readonly">[{arr.length} entries]</span>;
  }

  // Strings (incl. HexString with pattern) and anything else as text.
  const placeholder = fieldSchema.pattern || "";
  return (
    <input
      type="text"
      value={value === undefined || value === null ? "" : String(value)}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value === "" ? undefined : e.target.value)}
    />
  );
}
