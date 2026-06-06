// Wire types — exact JSON shapes the backend serves. Names mirror the
// Python dataclasses / dicts so a TS reader can grep backend code.

export type ConfigClass = "Can" | "CanIf" | "CanTp" | "PduR" | "Com";

export type ProjectRaw = Partial<Record<ConfigClass, Record<string, unknown>>>;

export type SchemaBundle = Record<ConfigClass, JSONSchema>;

export type JSONSchema = {
  title?: string;
  description?: string;
  type?: string | string[];
  properties?: Record<string, JSONSchema>;
  required?: string[];
  enum?: unknown[];
  default?: unknown;
  items?: JSONSchema;
  $ref?: string;
  $defs?: Record<string, JSONSchema>;
  anyOf?: JSONSchema[];
  pattern?: string;
  minimum?: number;
  maximum?: number;
  const?: unknown;
  // OpenVinci-specific
  description_?: string;
};

export type Severity = "error" | "warning" | "info";

export type Fix = {
  description: string;
  patches: Record<string, JSONPatchOp[]>;
};

export type JSONPatchOp = {
  op: string;
  path: string;
  value?: unknown;
};

export type Issue = {
  rule: string;
  severity: Severity;
  message: string;
  module: string;
  path: (string | number)[];
  fix: Fix | null;
};

export type ValidationReport = {
  ok: boolean;
  errorCount: number;
  warningCount: number;
  issues: Issue[];
};

export type GeneratedFile = {
  path: string;
  module: string;
  size_bytes: number;
};

export type CompileMessage = {
  file: string;
  line: number | null;
  column: number | null;
  severity: Severity;
  message: string;
};

export type CompileResult = {
  // "ok"          — every file compiled clean.
  // "errors"      — at least one gcc error.
  // "unavailable" — no C toolchain on the host; verification was
  //                 skipped. Generation still succeeded — used by
  //                 the desktop launcher on a clean machine.
  status: "ok" | "errors" | "unavailable";
  command: string[];
  messages: CompileMessage[];
};

export type GenerateResponse = {
  project: string;
  files: GeneratedFile[];
  compileResult: CompileResult | null;
};

export type DbcImportResponse = {
  source: string;
  network: string;
  me: string;
  project: ProjectRaw;
  validation: ValidationReport;
};

// Tree model (UI-only)

export type TreeNodeKind =
  | "module"
  | "container"
  | "item"; // a single leaf object: network, message, signal, pdu, routine, controller, channel

export type TreeNode = {
  id: string; // stable path within the project (e.g. "Com/networks/0/messages/2")
  label: string;
  kind: TreeNodeKind;
  module: ConfigClass;
  pointer: (string | number)[]; // JSON pointer into project[module]
  children?: TreeNode[];
};
