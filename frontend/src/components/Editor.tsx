// Typed editor for a selected tree node.
//
// Visually: a property grid. Fields are grouped into sections by a
// small set of name-based buckets (Identity, Layout, Network, Routing,
// Timing, Behavior, Notifications, Other) so a 30-field message form
// doesn't read as a flat brick of inputs. The grouping is a UI-only
// presentation concern — the underlying model and the schema walk are
// unchanged.
//
// Each row shows:
//   - the field name (with tooltip = description if the schema has one),
//   - a typed input (the same widget we always had),
//   - a subtle type/range hint to the right,
//   - an inline severity marker when the engine has an issue exactly
//     on this field (e.g. com.message-dlc-valid lives on `messages/i/dlc`).

import { useMemo } from "react";
import {
  CircleAlert,
  Hash,
  Info,
  TriangleAlert,
} from "lucide-react";
import type {
  Issue,
  JSONSchema,
  ProjectRaw,
  SchemaBundle,
  TreeNode,
  ValidationReport,
} from "../types";
import { getAtPointer, setAtPointer } from "../treeModel";
import { resolveSchema, schemaAt } from "../schemaWalk";
import { referenceSourceFor } from "../references";
import { fieldIssuesFor } from "../validationRollup";

// Ordered group buckets. The first bucket a field name matches wins —
// putting more specific groups before "Other" keeps things predictable.
const GROUPS: Array<{ id: string; title: string; fields: ReadonlySet<string> }> = [
  {
    id: "identity",
    title: "Identity",
    fields: new Set(["name", "id", "label", "kind"]),
  },
  {
    id: "layout",
    title: "Frame & bit layout",
    fields: new Set([
      "dlc",
      "fd",
      "hoh",
      "mask",
      "start",
      "size",
      "endian",
      "sign",
      "BitPosition",
      "BitSize",
      "UpdateBit",
    ]),
  },
  {
    id: "network",
    title: "Network",
    fields: new Set([
      "network",
      "device",
      "port",
      "baudrate",
      "samplePoint",
      "hwInstanceId",
      "me",
      "node",
      "NumHth",
      "NumHrh",
    ]),
  },
  {
    id: "routing",
    title: "Routing",
    fields: new Set(["from", "to", "dest", "fake", "up", "destinations"]),
  },
  {
    id: "timing",
    title: "Timing",
    fields: new Set([
      "CycleTime",
      "FirstTime",
      "FirstTimeout",
      "Timeout",
      "TxTimeout",
      "STmin",
      "BS",
      "WftMax",
      "N_As",
      "N_Bs",
      "N_Cr",
      "MainFunctionPeriod",
      "timeout_factor",
    ]),
  },
  {
    id: "behaviour",
    title: "Behaviour",
    fields: new Set([
      "dynamic",
      "isGroup",
      "group",
      "factor",
      "offset",
      "min",
      "max",
      "InitialValue",
      "RxDataTimeoutAction",
      "DataInvalidAction",
      "TimeoutSubstitutionValue",
      "LL_DL",
      "padding",
      "ComType",
      "AddressingFormat",
      "N_TA",
      "trigger",
      "use_dbc",
      "use_ldf",
      "dbc",
      "ldf",
      "ignore",
    ]),
  },
  {
    id: "notifications",
    title: "Notifications & callouts",
    fields: new Set([
      // Filled by name heuristic below as well; the explicit list keeps
      // the order predictable when the schema doesn't ship a description.
      "InvalidNotification",
      "RxNotification",
      "RxTOut",
      "ErrorNotification",
      "TxNotification",
      "RxIpduCallout",
      "TxIpduCallout",
      "enable_message_tx_callout",
      "enable_message_rx_callout",
      "enable_message_rx_notificaiton",
      "enable_signal_rx_notification",
      "enable_message_rx_timeout_notificaiton",
      "enable_signal_rx_timeout_notification",
      "E2E",
    ]),
  },
];

function groupFor(name: string): string {
  for (const g of GROUPS) {
    if (g.fields.has(name)) return g.id;
  }
  // Heuristic catch-all so we never miss new notification-family fields.
  if (
    /Notification$/i.test(name) ||
    /(Callout|TOut|Timeout)$/i.test(name) ||
    /^enable_/i.test(name)
  ) {
    return "notifications";
  }
  return "other";
}

const ORDERED_GROUP_IDS = [...GROUPS.map((g) => g.id), "other"];
const GROUP_TITLE: Record<string, string> = {
  ...Object.fromEntries(GROUPS.map((g) => [g.id, g.title])),
  other: "Other",
};

export function Editor({
  node,
  project,
  schemas,
  validation,
  onChange,
}: {
  node: TreeNode | null;
  project: ProjectRaw;
  schemas: SchemaBundle;
  /** Optional — when present, fields show inline per-field issue
   *  markers. Keeps the editor usable before the first validation. */
  validation?: ValidationReport | null;
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
  const fieldIssues = useMemo(
    () => fieldIssuesFor(node, validation?.issues ?? []),
    [node, validation],
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
          <span className="badge">{node.module}</span>
          <span className="title-text">{node.label}</span>
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

  // Bucket fields by group, preserving declared order within each.
  const fieldsByGroup: Record<string, string[]> = {};
  for (const name of fieldNames) {
    const g = groupFor(name);
    (fieldsByGroup[g] ||= []).push(name);
  }

  return (
    <div className="editor property-grid">
      <h2>
        <span className="badge">{node.module}</span>
        <span className="title-text">{node.label}</span>
      </h2>
      {schema.description && <p className="hint">{schema.description}</p>}

      {ORDERED_GROUP_IDS.map((gid) => {
        const fields = fieldsByGroup[gid];
        if (!fields || fields.length === 0) return null;
        return (
          <section className="prop-group" key={gid}>
            <header className="prop-group-header">
              <span>{GROUP_TITLE[gid] ?? gid}</span>
              <span className="prop-group-count">{fields.length}</span>
            </header>
            <table className="fields">
              <tbody>
                {fields.map((name) => {
                  const fieldSchema = resolveSchema(
                    schema.properties?.[name],
                    rootSchema,
                  );
                  const issues = fieldIssues.get(name) ?? [];
                  return (
                    <PropertyRow
                      key={name}
                      name={name}
                      value={obj[name]}
                      fieldSchema={fieldSchema}
                      rootSchema={rootSchema}
                      node={node}
                      project={project}
                      issues={issues}
                      onChange={(v) => commit({ ...obj, [name]: v })}
                    />
                  );
                })}
              </tbody>
            </table>
          </section>
        );
      })}
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

// --- Single property row ----------------------------------------------

function PropertyRow({
  name,
  value,
  fieldSchema,
  rootSchema,
  node,
  project,
  issues,
  onChange,
}: {
  name: string;
  value: unknown;
  fieldSchema: JSONSchema;
  rootSchema: JSONSchema;
  node: TreeNode;
  project: ProjectRaw;
  issues: Issue[];
  onChange: (v: unknown) => void;
}) {
  const hint = describeType(fieldSchema);
  const hasError = issues.some((i) => i.severity === "error");
  const hasWarning = issues.some((i) => i.severity === "warning");
  const sevClass = hasError ? "row-error" : hasWarning ? "row-warning" : "";

  return (
    <tr className={`property-row ${sevClass}`}>
      <th>
        <span className="prop-name">
          <span className="name-text">{name}</span>
          {fieldSchema.description && (
            <span className="prop-desc" title={fieldSchema.description}>
              <Info size={11} aria-hidden />
            </span>
          )}
        </span>
      </th>
      <td className="prop-input">
        <Field
          name={name}
          value={value}
          fieldSchema={fieldSchema}
          rootSchema={rootSchema}
          node={node}
          project={project}
          onChange={onChange}
        />
      </td>
      <td className="prop-hint">
        {hint && (
          <span className="type-hint" title={hint.full}>
            {hint.short}
          </span>
        )}
      </td>
      <td className="prop-issue">
        {issues.map((issue, i) => (
          <span
            key={i}
            className={`field-marker sev-${issue.severity}`}
            title={`${issue.rule}: ${issue.message}`}
          >
            {issue.severity === "error" ? (
              <CircleAlert size={12} aria-hidden />
            ) : (
              <TriangleAlert size={12} aria-hidden />
            )}
          </span>
        ))}
      </td>
    </tr>
  );
}

// --- Type/range hint --------------------------------------------------

type TypeHint = { short: string; full: string };

function describeType(fieldSchema: JSONSchema): TypeHint | null {
  const t = fieldSchema.type;
  if (fieldSchema.enum) {
    const opts = (fieldSchema.enum as unknown[])
      .map((v) => String(v))
      .join(" | ");
    return { short: "enum", full: `enum: ${opts}` };
  }
  if (t === "string" || (Array.isArray(t) && t.includes("string"))) {
    if (fieldSchema.pattern) {
      return { short: `string`, full: `string · pattern: ${fieldSchema.pattern}` };
    }
    return { short: "string", full: "string" };
  }
  if (t === "integer" || t === "number") {
    const lo = fieldSchema.minimum;
    const hi = fieldSchema.maximum;
    if (lo !== undefined && hi !== undefined) {
      return { short: `${t} · ${lo}..${hi}`, full: `${t} · ${lo}..${hi}` };
    }
    if (lo !== undefined) return { short: `${t} · ≥${lo}`, full: `${t} · ≥${lo}` };
    if (hi !== undefined) return { short: `${t} · ≤${hi}`, full: `${t} · ≤${hi}` };
    return { short: t, full: t };
  }
  if (t === "boolean") return { short: "bool", full: "boolean" };
  if (t === "array") return { short: "array", full: "array" };
  return null;
}

// --- Inputs (the same widgets as before, kept locally) ---------------

function Field({
  name: _name,
  value,
  fieldSchema,
  node,
  project,
  onChange,
}: {
  name: string;
  value: unknown;
  fieldSchema: JSONSchema;
  // Threaded for future cross-schema lookups; not used here.
  rootSchema: JSONSchema;
  node: TreeNode;
  project: ProjectRaw;
  onChange: (v: unknown) => void;
}) {
  const refSource = referenceSourceFor(node, _name, project);

  if (refSource) {
    // Proper combobox: free typing + datalist of valid targets, so the
    // user can paste an as-yet-undefined name and still get suggestions.
    const listId = `ref-${node.id.replace(/[^a-zA-Z0-9_-]/g, "_")}-${_name}`;
    return (
      <span className="combobox">
        <input
          type="text"
          list={listId}
          value={typeof value === "string" ? value : ""}
          placeholder={
            refSource.values.length > 0
              ? refSource.values[0]
              : "— no targets —"
          }
          onChange={(e) =>
            onChange(e.target.value === "" ? undefined : e.target.value)
          }
        />
        <datalist id={listId}>
          {refSource.values.map((v) => (
            <option key={v} value={v} />
          ))}
        </datalist>
      </span>
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
      (fieldSchema.type.includes("integer") ||
        fieldSchema.type.includes("number")))
  ) {
    return (
      <span className="num-input">
        <Hash size={11} className="num-prefix" aria-hidden />
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
      </span>
    );
  }

  if (fieldSchema.type === "array") {
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
      onChange={(e) =>
        onChange(e.target.value === "" ? undefined : e.target.value)
      }
    />
  );
}
