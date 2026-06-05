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

export async function generate(
  project: ProjectRaw,
  sourceProject?: string,
): Promise<GenerateResponse> {
  return jsonOrThrow(
    await fetch("/api/generate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ project, sourceProject }),
    }),
  );
}

export function issueKey(issue: Issue): string {
  return `${issue.rule}|${issue.module}|${issue.path.join(".")}|${issue.message}`;
}
