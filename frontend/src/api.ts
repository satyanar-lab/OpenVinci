import type {
  DbcImportResponse,
  GenerateResponse,
  Issue,
  ProjectRaw,
  SchemaBundle,
  ValidationReport,
  Fix,
} from "./types";

async function jsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text}`);
  }
  return (await response.json()) as T;
}

export async function fetchSchemas(): Promise<SchemaBundle> {
  return jsonOrThrow<SchemaBundle>(await fetch("/schemas"));
}

export async function listProjects(): Promise<string[]> {
  const body = await jsonOrThrow<{ projects: string[] }>(
    await fetch("/api/projects"),
  );
  return body.projects;
}

export async function getProject(
  name: string,
): Promise<{ name: string; project: ProjectRaw }> {
  return jsonOrThrow(await fetch(`/api/projects/${encodeURIComponent(name)}`));
}

export async function validateProject(
  project: ProjectRaw,
): Promise<ValidationReport> {
  return jsonOrThrow<ValidationReport>(
    await fetch("/api/validate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ project }),
    }),
  );
}

export async function applyFix(
  project: ProjectRaw,
  fix: Fix,
): Promise<{ project: ProjectRaw; validation: ValidationReport }> {
  return jsonOrThrow(
    await fetch("/api/apply-fix", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ project, fix }),
    }),
  );
}

export async function listDbcs(): Promise<string[]> {
  const body = await jsonOrThrow<{ dbcs: string[] }>(
    await fetch("/api/dbcs"),
  );
  return body.dbcs;
}

export async function importDbc(
  dbc: string,
  network: string,
  me: string,
  baudrate = 500000,
): Promise<DbcImportResponse> {
  const params = new URLSearchParams({
    dbc,
    network,
    me,
    baudrate: String(baudrate),
  });
  return jsonOrThrow(
    await fetch(`/api/import/dbc?${params}`, { method: "POST" }),
  );
}

export async function importDbcUpload(
  file: File,
  network: string,
  me: string,
  baudrate = 500000,
): Promise<DbcImportResponse> {
  const params = new URLSearchParams({
    network,
    me,
    baudrate: String(baudrate),
  });
  const body = new FormData();
  body.append("file", file, file.name);
  return jsonOrThrow(
    await fetch(`/api/import/dbc/upload?${params}`, {
      method: "POST",
      body,
    }),
  );
}

/**
 * Board target the firmware-export endpoints use. "host" (or
 * undefined) keeps the existing host-simulator behaviour; "stm32h753zi"
 * tells /api/generate/zip to assemble the complete buildable firmware
 * project (PROMPT C4).
 */
export type Target = "host" | "stm32h753zi";

export async function generate(
  project: ProjectRaw,
  sourceProject?: string,
  target?: Target,
): Promise<GenerateResponse> {
  return jsonOrThrow(
    await fetch("/api/generate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ project, sourceProject, target }),
    }),
  );
}

/**
 * Pull the generated outputs of the same project as a STORED .zip
 * blob. Same stage+generate the regular `generate()` already runs;
 * the backend cleans the temp workdir after streaming. The arcnames
 * inside the zip are project-relative, never server filesystem
 * paths.
 */
export async function generateZip(
  project: ProjectRaw,
  sourceProject?: string,
  target?: Target,
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch("/api/generate/zip", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ project, sourceProject, target }),
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${await response.text()}`);
  }
  const filename = extractFilename(
    response.headers.get("content-disposition"),
  ) ?? "openvinci.zip";
  return { blob: await response.blob(), filename };
}

function extractFilename(disposition: string | null): string | null {
  if (!disposition) return null;
  // Accept both quoted and unquoted forms — content-disposition is
  // notoriously variable. We never need RFC 5987 (UTF-8) variants
  // because the backend constrains the label to [A-Za-z0-9._-].
  const m = /filename\s*=\s*"?([^"]+)"?/i.exec(disposition);
  return m ? m[1] : null;
}

export function issueKey(issue: Issue): string {
  return `${issue.rule}|${issue.module}|${issue.path.join(".")}|${issue.message}`;
}
